"""Test ProShop API connection and introspect available input fields."""
import sys, json
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import ProShopClient, ENV

ps = ProShopClient()

print("ProShop API Connection Test")
print("=" * 50)

# Test auth
print("\nAuthenticating...")
token = ps._get_token()
print(f"Token: {token[:30]}...")

# Test contacts
print("\nFetching contacts...")
contacts = ps.get_contacts()
print(f"Found {len(contacts)} contacts")
for c in contacts[:5]:
    print(f"  {c.get('name'):>20}  {c.get('companyName','')}")

# Introspect all input types we use
input_types = [
    "AddPackingSlipInput",
    "AddCustomerPoInput",
    "AddPurchaseOrderInput",
    "AddQuoteInput",
    "AddBillInput",
]

for itype in input_types:
    print(f"\n{'-' * 50}")
    print(f"Fields for {itype}:")
    gql = """
    query IntrospectInput($name: String!) {
      __type(name: $name) {
        inputFields {
          name
          type { name kind ofType { name kind } }
        }
      }
    }"""
    try:
        data = ps.query(gql, {"name": itype})
        fields = data.get("__type", {}).get("inputFields", [])
        for f in fields:
            t = f["type"]
            type_name = t.get("name") or (t.get("ofType", {}).get("name", "?"))
            required = "REQUIRED" if t.get("kind") == "NON_NULL" else ""
            print(f"  {f['name']:>30}  {type_name:>10}  {required}")
    except Exception as e:
        print(f"  Error: {e}")

# Test duplicate check queries
print(f"\n{'─' * 50}")
print("Testing duplicate check queries...")
for query_name, field in [("packingSlips", "packingSlipId"), ("customerPOs", "poId"), ("quotes", "quoteId")]:
    try:
        gql = f'{{ {query_name}(pageSize: 1) {{ records {{ {field} proshopUrl }} }} }}'
        data = ps.query(gql)
        records = data.get(query_name, {}).get("records", [])
        print(f"  {query_name}: {len(records)} record(s) returned (of many)")
    except Exception as e:
        print(f"  {query_name}: Error — {e}")

print("\nDone.")
