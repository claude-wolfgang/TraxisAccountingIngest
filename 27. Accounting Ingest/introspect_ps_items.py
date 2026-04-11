import sys
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import ProShopClient
ps = ProShopClient()

for t in ["UpdatePackingSlipItemsShippedDataInput", "AddBillItemsDataInput"]:
    print(f"\n=== {t} ===")
    gql = 'query($n: String!) { __type(name: $n) { inputFields { name type { name kind ofType { name } } } } }'
    data = ps.query(gql, {"n": t})
    typ = data.get("__type")
    if not typ:
        print("  (not found)")
        continue
    for f in typ["inputFields"]:
        ft = f["type"]
        tname = ft.get("name") or (ft.get("ofType") or {}).get("name", "?")
        print(f"  {f['name']:>25}  {tname}")
