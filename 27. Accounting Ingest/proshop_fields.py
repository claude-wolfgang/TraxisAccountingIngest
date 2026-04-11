"""Introspect return fields for ProShop mutations."""
import sys
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import ProShopClient
ps = ProShopClient()

mutations = ["addPurchaseOrder", "addPackingSlip", "addBill", "addCustomerPo", "addQuote"]
for m in mutations:
    gql = """query { __type(name: "Mutation") { fields(includeDeprecated: true) { name type { name fields(includeDeprecated: true) { name } } } } }"""
    try:
        data = ps.query(gql)
        for f in data.get("__type", {}).get("fields", []):
            if f["name"] == m:
                ret = f.get("type", {})
                ret_fields = [rf["name"] for rf in (ret.get("fields") or [])]
                print(f"{m} -> {ret.get('name')}: {ret_fields}")
                break
        else:
            print(f"{m}: not found")
    except Exception as e:
        print(f"{m}: {e}")
