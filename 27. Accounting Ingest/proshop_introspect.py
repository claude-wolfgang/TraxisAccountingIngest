"""Introspect ProShop nested input types."""
import sys, json
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import ProShopClient

ps = ProShopClient()

def get_type_name(t):
    if not t:
        return "?"
    name = t.get("name")
    if name:
        return name
    kind = t.get("kind", "")
    inner = t.get("ofType")
    if kind == "NON_NULL":
        return get_type_name(inner) + "!"
    if kind == "LIST":
        return "[" + get_type_name(inner) + "]"
    return "?"

types_to_check = [
    "AddBillInput",
    "AddPackingSlipInput",
    "UpdatePurchaseOrderPoItemsDataInput",
    "PurchaseOrderType",
    "PurchaseOrderShipVia",
    "PurchaseOrderOrderStatus",
    "CustomerPOFOB",
    "QuoteStatus",
    "QuoteType",
]

for itype in types_to_check:
    print(f"\n=== {itype} ===")
    gql = """
    query($name: String!) {
      __type(name: $name) {
        kind
        inputFields { name type { name kind ofType { name kind ofType { name kind ofType { name } } } } }
        enumValues(includeDeprecated: true) { name }
      }
    }"""
    try:
        data = ps.query(gql, {"name": itype})
        t = data.get("__type")
        if not t:
            print("  (not found)")
            continue
        kind = t.get("kind", "")
        print(f"  kind: {kind}")
        if t.get("enumValues"):
            for ev in t["enumValues"]:
                print(f"  - {ev['name']}")
        if t.get("inputFields"):
            for f in t["inputFields"]:
                tname = get_type_name(f["type"])
                print(f"  {f['name']:>35}  {tname}")
    except Exception as e:
        print(f"  Error: {e}")

print("\nDone.")
