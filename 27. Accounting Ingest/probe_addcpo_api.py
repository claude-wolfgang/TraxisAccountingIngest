"""Probe addCustomerPo via basic-auth session — READ-ONLY introspection.

Twin of P35's probe_addpo_api.py, targeted at customer POs. Confirms the
field shapes we need before bundling the field-shape fixes flagged in P27
CLAUDE.md item 38 (partsOrdered, shiptoAddress, QBO fields).

  - beginsession (basic auth — same path the live _upload_customer_po uses)
  - introspect AddCustomerPoInput
  - introspect the partsOrdered nested input type (name TBD by introspection)
  - introspect AddCustomerPoShiptoAddressInput (or whatever the type resolves to)
  - read one recent CustomerPo with a wide field selection so we can see what
    ProShop actually populates
  - print known-CPO enums
  - endsession

No --live flag — we don't need a write to learn the schema. Run:
    python probe_addcpo_api.py
"""
from __future__ import annotations
import json
import sys
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

# Fields _upload_customer_po currently writes — the baseline for diff.
KNOWN_CPO_FIELDS = {
    "client", "clientPONumber", "dateEntered", "buyer",
    "paymentTerms", "notes", "year",
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


def inner_type_name(t: dict) -> str:
    """Strip NON_NULL/LIST wrappers to get the leaf input type name."""
    while t and t.get("ofType"):
        t = t["ofType"]
    return (t or {}).get("name") or ""


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
    print(f"\n{label} ({len(fields)} fields):")
    seen = set()
    for f in sorted(fields, key=lambda x: x["name"]):
        tn = type_name(f["type"])
        req = " *REQUIRED" if tn.endswith("!") else ""
        new = " <NEW>" if f["name"] not in known else ""
        print(f"    {f['name']:>36}  {tn}{req}{new}")
        seen.add(f["name"])
    return seen


def show_recent_cpo(token: str) -> None:
    """Read one recent CustomerPo with a wide field selection."""
    q = """
    {
      customerPOs(pageSize: 1) {
        records {
          poId
          year
          dateEntered
          client { name companyName }
          clientPONumber
          buyer
          paymentTerms
          paymentTermsDiscount
          paymentTermsDiscountDays
          taxStatus
          currency
          notes
          confirmationSent
          confirmationSentBy { name }
          confirmationNotes
          shiptoAddress
          partsOrdered(pageSize: 5) {
            records {
              part { partNumber }
              clientPartNumber
              quantityOrdered
              pricePer
              dueDate
              requestDate
              partRev
              drawingRev
              lineItemNotes
              firstArticleRequired
            }
          }
        }
      }
    }
    """
    status, data = gql(token, q)
    if "errors" in data:
        print(f"\nrecent CPO read BLOCKED: {data['errors']}")
        return
    recs = (data.get("data") or {}).get("customerPOs", {}).get("records", [])
    if not recs:
        print("\nno CPOs visible")
        return
    print("\nRecent CPO (sample shape):")
    print(json.dumps(recs[0], indent=2, default=str))


def main() -> int:
    env = load_env()
    token = begin_session(env)
    print(f"session token: {token[:16]}...")

    try:
        # 1) AddCustomerPoInput — the top-level mutation input
        print("\n=== AddCustomerPoInput ===")
        cpo_fields = introspect(token, "AddCustomerPoInput")
        print_fields("AddCustomerPoInput", cpo_fields, KNOWN_CPO_FIELDS)

        # 2) Find the nested input types we need to recurse into.
        # partsOrdered + shiptoAddress are the high-value targets, but we don't
        # know their exact input-type names — derive from introspection result.
        candidates = {}
        for f in cpo_fields:
            leaf = inner_type_name(f["type"])
            if leaf and leaf.startswith(("Add", "Update")) and leaf.endswith("Input"):
                candidates[f["name"]] = leaf

        print("\n--- nested input types referenced by AddCustomerPoInput ---")
        for field, leaf in sorted(candidates.items()):
            print(f"    {field}  ->  {leaf}")

        # 3) Recurse into the high-value ones (and any others we spot).
        for field in ("partsOrdered", "shiptoAddress", "billToAddress",
                      "shipFromAddress"):
            leaf = candidates.get(field)
            if not leaf:
                continue
            print(f"\n=== {leaf} (shape of {field}) ===")
            sub = introspect(token, leaf)
            print_fields(leaf, sub, set())

        # 4) Known CPO enums — what values are legal for tax/currency/etc.
        # Note casing: ProShop uses CustomerPO… (uppercase PO), not CustomerPo….
        for enum_name in ("CustomerPOTaxStatus", "CustomerPOPaymentTerms",
                          "CustomerPOFOB", "CustomerPOIsComplete",
                          "CustomerPODeliveryPriority", "CustomerPOLineItemStatus",
                          "CustomerPOLineItemType", "CustomerPOOrderType"):
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

        show_recent_cpo(token)

    finally:
        try:
            requests.get(END_URL, params={"token": token}, timeout=15)
        except requests.RequestException:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
