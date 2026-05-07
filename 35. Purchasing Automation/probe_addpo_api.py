"""Probe addPurchaseOrder via basic-auth session token.

Default: read-only.
  - beginsession (basic auth)
  - introspect AddPurchaseOrderInput + AddPurchaseOrderPoItemInput
  - read a recent VPO record (richer field selection than P27's diag)
  - compare against the field-set used by P27's _upload_purchase_order
  - endsession

--live: additionally send a minimal mutation (poType=Standard, year=2026).
  Wolfgang must clean the test PO from ProShop UI manually after.

Run:
    python probe_addpo_api.py             # introspection only
    python probe_addpo_api.py --live      # creates one real test VPO

Why basic auth: service user auth_010 was deleted 2026-05-06; OAuth via
AccountingConnector currently maps to nothing. Basic auth (/api/beginsession)
is the path proven yesterday for addCustomerPo; this probe confirms parity
for addPurchaseOrder.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import requests

ENV_PATH = Path(
    r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis"
    r"\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env"
)
BASE = "https://traxismfg.adionsystems.com"
BEGIN_URL = f"{BASE}/api/beginsession"
END_URL = f"{BASE}/api/endsession"
GQL_URL = f"{BASE}/api/graphql"

# Fields P27 currently writes — the baseline to compare introspection against.
KNOWN_PO_FIELDS = {
    "poType", "supplier", "date", "confirmationNumber",
    "remarks", "specialInstructions", "poItems", "year",
}
KNOWN_POITEM_FIELDS = {
    "toolNumber", "description", "quantity", "costPer", "total",
}


def load_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def begin_session(env: dict) -> str:
    u = env["PROSHOP_USERNAME"]
    username = u if "@" in u else f"{u}@traxismfg.com"
    scope = env["ACCOUNTING_SCOPE"].replace("+", " ")
    r = requests.post(
        BEGIN_URL,
        headers={"Content-Type": "application/json"},
        json={"username": username, "password": env["PROSHOP_PASSWORD"], "scope": scope},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["authorizationResult"]["token"]


def gql(token: str, query: str, variables: dict | None = None) -> tuple[int, dict]:
    r = requests.post(
        GQL_URL,
        params={"token": token},
        headers={"Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    return r.status_code, r.json()


def type_name(t: dict) -> str:
    if not t:
        return "?"
    if t.get("name"):
        return t["name"]
    kind = t.get("kind", "")
    inner = t.get("ofType")
    if kind == "NON_NULL":
        return type_name(inner) + "!"
    if kind == "LIST":
        return "[" + type_name(inner) + "]"
    return "?"


INTROSPECT_Q = """
query($name: String!) {
  __type(name: $name) {
    kind
    inputFields {
      name
      type { name kind ofType { name kind ofType { name kind ofType { name kind ofType { name } } } } }
    }
  }
}
"""


def introspect(token: str, type_name_arg: str) -> list[dict]:
    status, data = gql(token, INTROSPECT_Q, {"name": type_name_arg})
    t = (data.get("data") or {}).get("__type")
    if not t:
        print(f"    {type_name_arg}: NOT FOUND ({json.dumps(data)[:200]})")
        return []
    return t.get("inputFields") or []


def print_fields(label: str, fields: list[dict], known: set[str]) -> set[str]:
    """Print fields, marking required (!) and unknown-to-P27 (NEW)."""
    print(f"\n{label} ({len(fields)} fields):")
    seen = set()
    for f in sorted(fields, key=lambda x: x["name"]):
        tn = type_name(f["type"])
        req = " *REQUIRED" if tn.endswith("!") else ""
        new = " <NEW>" if f["name"] not in known else ""
        print(f"    {f['name']:>32}  {tn}{req}{new}")
        seen.add(f["name"])
    return seen


def show_recent_vpo(token: str) -> None:
    """Read one recent VPO with a wide field selection — shows what ProShop populates."""
    q = """
    {
      purchaseOrders(pageSize: 1) {
        records {
          id
          poType
          year
          date
          supplier { name companyName }
          supplierAddressee
          confirmationNumber
          orderStatus
          received
          poRevision
          shipToAddressee
          shipToCity
          shipToState
          shipToZipCode
          shipToCountry
          shipVia
          remarks
          specialInstructions
          freightOnBoard
          taxable
          poItems(pageSize: 5) {
            records {
              orderNumber
              toolNumber
              itemNumber
              description
              quantity
              costPer
              total
              units
              workOrder
              receivedQty
              releasedQty
            }
          }
        }
      }
    }
    """
    status, data = gql(token, q)
    if "errors" in data:
        print(f"\nrecent VPO read BLOCKED: {data['errors']}")
        return
    recs = (data.get("data") or {}).get("purchaseOrders", {}).get("records", [])
    if not recs:
        print("\nno VPOs visible")
        return
    print("\nRecent VPO (sample shape):")
    print(json.dumps(recs[0], indent=2))


def live_mutation(token: str) -> None:
    print("\n" + "=" * 70)
    print("  LIVE MUTATION — creates a real test VPO")
    print("=" * 70)
    mutation = """
    mutation AddPurchaseOrder($data: AddPurchaseOrderInput!) {
      addPurchaseOrder(data: $data) { id proshopUrl }
    }
    """
    payload = {
        "poType": "Standard",
        "year": "2026",
        "remarks": "API-PROBE-2026-05-06 — DELETE ME",
    }
    print(f"payload: {json.dumps(payload)}")
    status, data = gql(token, mutation, {"data": payload})
    print(f"HTTP {status}")
    print(json.dumps(data, indent=2))
    if "errors" not in data:
        print("\n*** Test VPO created. Delete from ProShop UI. ***")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true",
                   help="run a real addPurchaseOrder mutation (creates a test VPO)")
    args = p.parse_args()

    env = load_env()
    token = begin_session(env)
    print(f"session token: {token[:16]}...")

    try:
        print("\n=== AddPurchaseOrderInput ===")
        po_fields = introspect(token, "AddPurchaseOrderInput")
        print_fields("AddPurchaseOrderInput", po_fields, KNOWN_PO_FIELDS)

        # poItems input type is UpdatePurchaseOrderPoItemsDataInput per AddPurchaseOrderInput.poItems
        print("\n=== UpdatePurchaseOrderPoItemsDataInput (poItems shape) ===")
        item_fields = introspect(token, "UpdatePurchaseOrderPoItemsDataInput")
        print_fields("UpdatePurchaseOrderPoItemsDataInput", item_fields, KNOWN_POITEM_FIELDS)

        # Custom enums referenced by AddPurchaseOrderInput / poItems
        for enum_name in ("PurchaseOrderType", "PurchaseOrderShipVia",
                          "PurchaseOrderOrderStatus", "PurchaseOrderFreightOnBoard",
                          "PurchaseOrderUnits", "PurchaseOrderExtraChargeType",
                          "PurchaseOrderShippingAgent"):
            enum_q = """
            query($name: String!) {
              __type(name: $name) { kind enumValues { name } }
            }
            """
            _, ed = gql(token, enum_q, {"name": enum_name})
            t = (ed.get("data") or {}).get("__type")
            if t and t.get("enumValues"):
                vals = [v["name"] for v in t["enumValues"]]
                print(f"\n{enum_name}: {vals}")

        show_recent_vpo(token)

        if args.live:
            live_mutation(token)
    finally:
        try:
            requests.get(END_URL, params={"token": token}, timeout=15)
        except requests.RequestException:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
