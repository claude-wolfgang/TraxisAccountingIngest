"""Write VPOs to ProShop via addPurchaseOrder under basic auth.

P35 Phase 2. Pairs find_last_vpo_line() (most recent prior purchase for an
entity) with create_vpo() (assemble payload + run mutation). The worker
thread (worker.py) glues these to the orders queue.

Repeat-purchase shape locked 2026-05-06: last 1 prior VPO, blind-copy vendor.
Schema: AddPurchaseOrderInput is 40 fields (only poType required);
UpdatePurchaseOrderPoItemsDataInput is 44 fields. See P35 PLAN.md.

CLI:
    python -m purchasing.proshop_vpo --entity LUB-116 --qty 5
    python -m purchasing.proshop_vpo --entity LUB-116 --qty 5 --live
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import proshop_basic_auth as ba

# Memory project_vpo_defaults.md — Traxis MFG ship-to standard.
SHIPTO_DEFAULTS = {
    "shipToAddressee": "Traxis MFG",
    "shipToAddress": "511 E St. Elmo Rd",
    "shipToCity": "Austin",
    "shipToState": "TX",
    "shipToZipCode": "78745",
    "shipToCountry": "USA",
}

# Scope: even the *PlainText helper fields enforce read scope on the underlying
# module (tested 2026-05-06 — got "scope does not grant read access to Tools").
# So we still need tools:r/ots:r/contacts:r alongside purchaseorders:rwdp.
P35_SCOPE = "purchaseorders:rwdp+tools:r+ots:r+contacts:r"

# ProShop's PurchaseOrderFilter doesn't index line-item content, so we page
# newest-first and scan poItems client-side. Cap to bound the work per Buy click.
SCAN_PAGE_SIZE = 50
# 10 pages × 50 = 500 most-recent VPOs. With ~300 VPOs/year that's ~1.5 yr.
# Each Buy click triggers up to 10 GraphQL calls in the no-match worst case.
DEFAULT_MAX_PAGES = 10


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_year():
    return str(datetime.now(timezone.utc).year)


def find_last_vpo_line(session, entity_id, max_pages=DEFAULT_MAX_PAGES):
    """Most-recent purchaseOrder line whose toolNumber == entity_id.

    Returns {vpo_id, vpo_date, supplier, costPer, quantity, orderNumber,
    toolNumber, description} or None.
    """
    # Use *PlainText helpers so we don't need tools/ots/contacts read scopes.
    # The "COTS / Tool #" column in the UI maps to two separate API fields:
    # toolNumberPlainText (when the line is a tool) and otsPlainText (when
    # it's a COTS item). Match against both — entity_id appears in exactly one.
    # purchaseOrders default order is OLDEST first; sortBy date DESC fixes that.
    query = """
    query RecentPOs($pageStart: Int) {
        purchaseOrders(pageSize: %d, pageStart: $pageStart,
                       sortBy: "date", sortOrder: DESC) {
            records {
                id date supplierPlainText
                poItems(pageSize: 50) {
                    records {
                        toolNumberPlainText otsPlainText
                        orderNumber description
                        quantity costPer
                    }
                }
            }
        }
    }
    """ % SCAN_PAGE_SIZE

    for page in range(max_pages):
        body = session.execute(query, {"pageStart": page * SCAN_PAGE_SIZE})
        records = (((body.get("data") or {}).get("purchaseOrders") or {})
                   .get("records") or [])
        if not records:
            break
        for po in records:
            for line in ((po.get("poItems") or {}).get("records") or []):
                tool_id = line.get("toolNumberPlainText") or ""
                cots_id = line.get("otsPlainText") or ""
                if entity_id in (tool_id, cots_id):
                    return {
                        "vpo_id": po.get("id"),
                        "vpo_date": po.get("date"),
                        "supplier": po.get("supplierPlainText"),
                        "costPer": line.get("costPer"),
                        "quantity": line.get("quantity"),
                        "orderNumber": line.get("orderNumber"),
                        "toolNumber": tool_id or None,
                        "ots": cots_id or None,
                        "description": line.get("description"),
                    }
    return None


def build_payload(queue_row, prior_line=None):
    """Assemble AddPurchaseOrderInput from queue_row + optional prior line.

    queue_row: dict with entity_type, entity_id, qty, unit_cost, vendor, brand, edp.
    prior_line: dict from find_last_vpo_line(); supplies blind-copy supplier
                and cost/orderNumber/description fallbacks. May be None.
    """
    payload = {
        "poType": "Standard",
        "year": _now_year(),
        "date": _today(),
        "remarks": "P35 auto-generated (Buy-button approval).",
    }
    payload.update(SHIPTO_DEFAULTS)

    supplier = (prior_line or {}).get("supplier") or queue_row.get("vendor")
    if supplier:
        payload["supplier"] = supplier

    line = {}
    # Tools go in `toolNumber`, COTS go in `ots` — the UI's "COTS / Tool #"
    # column is two API fields. Both take String input (the entity id).
    entity_id = queue_row.get("entity_id")
    entity_type = (queue_row.get("entity_type") or "").lower()
    if entity_id:
        if entity_type == "cots":
            line["ots"] = entity_id
        else:
            line["toolNumber"] = entity_id

    brand = queue_row.get("brand")
    edp = queue_row.get("edp")
    if brand and edp:
        line["orderNumber"] = f"{brand} {edp}"
    elif (prior_line or {}).get("orderNumber"):
        line["orderNumber"] = prior_line["orderNumber"]

    if (prior_line or {}).get("description"):
        line["description"] = prior_line["description"]

    qty = queue_row.get("qty") or 1
    # Drop trailing .0 on integer-valued floats — ProShop expects "1" not "1.0".
    line["quantity"] = str(int(qty)) if float(qty).is_integer() else str(qty)

    cost = queue_row.get("unit_cost")
    if cost is None:
        cost = (prior_line or {}).get("costPer")
    if cost is not None:
        line["costPer"] = float(cost)

    payload["poItems"] = [line]
    return payload


def create_vpo(session, queue_row, prior_line=None):
    """Run the mutation and return {id, proshopUrl}."""
    payload = build_payload(queue_row, prior_line)
    mutation = """
    mutation AddVPO($data: AddPurchaseOrderInput!) {
        addPurchaseOrder(data: $data) { id proshopUrl }
    }
    """
    body = session.execute(mutation, {"data": payload})
    return ((body.get("data") or {}).get("addPurchaseOrder") or {})


# ── CLI test harness ─────────────────────────────────────────────────────────

def _load_session_from_env():
    env_path = (Path(__file__).resolve().parents[3]
                / "1. Proshop Automations" / ".traxis.env")
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return ba.BasicAuthSession(
        base_url="https://traxismfg.adionsystems.com",
        username=env["PROSHOP_USERNAME"],
        password=env["PROSHOP_PASSWORD"],
        scope=P35_SCOPE,
    )


def _cli():
    p = argparse.ArgumentParser()
    p.add_argument("--entity", required=True, help='e.g. "LUB-116" or a toolNumber')
    p.add_argument("--type", default="tool", choices=["tool", "cots"],
                   help="entity_type — controls whether entity_id goes in toolNumber or ots")
    p.add_argument("--qty", type=float, default=1)
    p.add_argument("--unit-cost", type=float, default=None)
    p.add_argument("--vendor", default=None)
    p.add_argument("--brand", default=None)
    p.add_argument("--edp", default=None)
    p.add_argument("--live", action="store_true",
                   help="actually create the VPO (otherwise dry-run prints payload only)")
    args = p.parse_args()

    queue_row = {
        "entity_type": args.type,
        "entity_id": args.entity,
        "qty": args.qty,
        "unit_cost": args.unit_cost,
        "vendor": args.vendor,
        "brand": args.brand,
        "edp": args.edp,
    }

    with _load_session_from_env() as session:
        print(f"Looking up prior VPO line for {args.entity}...")
        prior = find_last_vpo_line(session, args.entity)
        if prior:
            print(f"  Prior VPO {prior['vpo_id']} dated {prior['vpo_date']} "
                  f"from {prior['supplier']!r} — orderNumber={prior['orderNumber']!r}, "
                  f"costPer=${prior['costPer']}, qty={prior['quantity']}")
        else:
            print("  No prior VPO line found.")

        payload = build_payload(queue_row, prior)
        print("\nPayload:")
        print(json.dumps(payload, indent=2))

        if args.live:
            print("\nLIVE — creating VPO...")
            result = create_vpo(session, queue_row, prior)
            print(json.dumps(result, indent=2))
            print("\n*** Test VPO created. Delete from ProShop UI. ***")
        else:
            print("\nDry-run (no mutation). Pass --live to create the VPO.")


if __name__ == "__main__":
    _cli()
