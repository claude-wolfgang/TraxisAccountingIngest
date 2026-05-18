"""List ProShop packing slips that have shipped but not yet been invoiced.

Bookkeeping Stage 1 — single-system view, no QBO. Output is a grouped punch
list so the user can clear them in batches.

Stage 2 (invoiced in ProShop vs posted to QBO) is read_proshop_invoices.py.

Filter:
  - shippingDate is set AND >= CUTOFF_DATE
  - invoicePlainText is blank (no linked invoice)

Per-line `doWeInvoice` is shown as Y/N/mix so free-of-charge slips can be
visually skipped — they legitimately won't get invoiced.

Read-only.

Output:
  - Console: per-customer table, totals
  - logs/proshop_unbilled_shipments_30d.json — full data for follow-up
"""

import json
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

ENV_PATH = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")
LOG_PATH = Path(__file__).parent / "logs" / "proshop_unbilled_shipments_30d.json"

PROSHOP_BASE = "https://traxismfg.adionsystems.com"
PROSHOP_BEGIN = f"{PROSHOP_BASE}/api/beginsession"
PROSHOP_GQL = f"{PROSHOP_BASE}/api/graphql"

WINDOW_DAYS = 30
CUTOFF_DATE = date.today() - timedelta(days=WINDOW_DAYS)

PAGE_SIZE = 200
ITEMS_PAGE_SIZE = 200  # warn if any slip exceeds this in itemsShipped


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s[:len(fmt)+2], fmt).date()
        except ValueError:
            continue
    return None


def proshop_begin_session(env):
    user = env["PROSHOP_USERNAME"]
    if "@" not in user:
        user = f"{user}@traxismfg.com"
    scope = env["ACCOUNTING_SCOPE"].replace("+", " ")
    r = requests.post(
        PROSHOP_BEGIN,
        headers={"Content-Type": "application/json"},
        json={"username": user, "password": env["PROSHOP_PASSWORD"], "scope": scope},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["authorizationResult"]["token"]


def fetch_slips(token):
    gql = """
    query Slips($pageSize: Int!, $pageStart: Int!, $itemsSize: Int!) {
      packingSlips(pageSize: $pageSize, pageStart: $pageStart) {
        totalRecords
        records {
          id
          shippingDate
          invoicePlainText
          shippedToPlainText
          customerPOPlainText
          proshopUrl
          itemsShipped(pageSize: $itemsSize, pageStart: 0) {
            totalRecords
            records {
              quantity
              pricePer
              doWeInvoice
              partPlainText
            }
          }
        }
      }
    }
    """
    out = []
    page_start = 0
    while True:
        r = requests.post(
            PROSHOP_GQL,
            params={"token": token},
            headers={"Content-Type": "application/json"},
            json={"query": gql, "variables": {
                "pageSize": PAGE_SIZE,
                "pageStart": page_start,
                "itemsSize": ITEMS_PAGE_SIZE,
            }},
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"ProShop GraphQL errors: {body['errors']}")
        result = body["data"]["packingSlips"]
        records = result.get("records") or []
        out.extend(records)
        total = result.get("totalRecords") or 0
        print(f"  ProShop slips {page_start}-{page_start+len(records)} of {total}")
        if len(records) < PAGE_SIZE or len(out) >= total:
            break
        page_start += PAGE_SIZE
    return out


def to_decimal(x):
    if x is None or x == "":
        return Decimal(0)
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def summarize_slip(slip):
    items_block = slip.get("itemsShipped") or {}
    items = items_block.get("records") or []
    item_total = items_block.get("totalRecords") or 0
    total = Decimal(0)
    flags = set()
    for it in items:
        qty = to_decimal(it.get("quantity"))
        price = to_decimal(it.get("pricePer"))
        total += qty * price
        flag = (it.get("doWeInvoice") or "").strip()
        flags.add(flag or "?")
    if not flags:
        bill = "-"
    elif flags == {"Yes"}:
        bill = "Y"
    elif flags == {"No"}:
        bill = "N"
    else:
        bill = "mix"
    truncated = len(items) < item_total
    return {
        "total": total,
        "bill": bill,
        "line_count": item_total,
        "items_truncated": truncated,
    }


def main():
    env = load_env()

    print(f"Window: shipped >= {CUTOFF_DATE.isoformat()} (last {WINDOW_DAYS} days), invoicePlainText blank")
    print("\nProShop: begin session...")
    token = proshop_begin_session(env)
    print("ProShop: fetching all packing slips (filtered client-side)...")
    t0 = time.time()
    all_slips = fetch_slips(token)
    print(f"  -> {len(all_slips)} slips in {time.time()-t0:.1f}s")

    unbilled = []
    truncated_warnings = []
    for s in all_slips:
        ship = parse_date(s.get("shippingDate"))
        if not ship or ship < CUTOFF_DATE:
            continue
        invoice_no = (s.get("invoicePlainText") or "").strip()
        if invoice_no:
            continue
        summary = summarize_slip(s)
        row = {
            "slip_id": s.get("id"),
            "ship_date": s.get("shippingDate"),
            "customer": s.get("shippedToPlainText") or "(blank)",
            "customer_po": s.get("customerPOPlainText") or "",
            "bill": summary["bill"],
            "lines": summary["line_count"],
            "total": str(summary["total"]),
            "url": s.get("proshopUrl"),
        }
        if summary["items_truncated"]:
            truncated_warnings.append(row["slip_id"])
        unbilled.append(row)

    by_customer = defaultdict(list)
    for row in unbilled:
        by_customer[row["customer"]].append(row)

    print("\n" + "=" * 70)
    print(f"UNBILLED SHIPMENTS — last {WINDOW_DAYS} days (since {CUTOFF_DATE.isoformat()})")
    print("=" * 70)
    print(f"  Total slips:           {len(unbilled)}")
    print(f"  Total customers:       {len(by_customer)}")
    print("  ($ values are not on the packing slip — pricePer is set at invoice creation.)")
    if truncated_warnings:
        print(f"  WARNING — line items truncated on slips: {truncated_warnings}")

    if not unbilled:
        print("\n  (nothing unbilled in window — good)")
    else:
        for customer in sorted(by_customer):
            rows = sorted(by_customer[customer], key=lambda r: r["ship_date"])
            print(f"\n--- {customer}  ({len(rows)} slips) ---")
            print(f"  {'SLIP':<12} {'SHIPPED':<12} {'CUST PO':<20} {'BILL':<5} {'LINES':<6}  URL")
            for r in rows:
                print(f"  {r['slip_id']:<12} {r['ship_date']:<12} {(r['customer_po'] or '')[:20]:<20} "
                      f"{r['bill']:<5} {str(r['lines']):<6}  {r['url']}")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps({
        "window": {"days": WINDOW_DAYS, "cutoff": CUTOFF_DATE.isoformat()},
        "counts": {
            "slips_total_fetched": len(all_slips),
            "unbilled_in_window": len(unbilled),
            "customers": len(by_customer),
        },
        "note": "pricePer is null on shipped-but-not-invoiced slips; $ totals are set at invoice creation.",
        "truncated_warnings": truncated_warnings,
        "by_customer": {c: rows for c, rows in by_customer.items()},
        "all_unbilled": unbilled,
    }, indent=2, default=str))
    print(f"\nFull results written to: {LOG_PATH}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        body = e.response.text[:600] if e.response else ""
        print(f"HTTP error: {e}\n{body}", file=sys.stderr)
        sys.exit(1)
