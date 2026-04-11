"""Quick QBO connection test."""
import sys
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import QBOClient, ENV

print("QBO_CLIENT_ID:", ENV.get("QBO_CLIENT_ID", "MISSING")[:10] + "...")
print("QBO_REALM_ID:", ENV.get("QBO_REALM_ID", "MISSING"))
print("QBO_REFRESH_TOKEN:", ENV.get("QBO_REFRESH_TOKEN", "MISSING")[:15] + "...")
print()

qbo = QBOClient()
print("Refreshing token...")
token = qbo._refresh()
print("Access token:", token[:30] + "...")
print()

print("Querying vendors...")
vendors = qbo.get_vendors()
print(f"Found {len(vendors)} vendors:")
for v in vendors[:10]:
    vid = v.get("Id", "")
    vname = v.get("DisplayName", "")
    print(f"  ID={vid:>4}  {vname}")
if len(vendors) > 10:
    print(f"  ... and {len(vendors)-10} more")
print()

print("Querying expense accounts...")
acct = qbo.get_default_expense_account()
print(f"Default expense account: {acct}")
print()

print("Querying existing bills...")
data = qbo.qbo_query("SELECT * FROM Bill MAXRESULTS 5")
bills = data.get("QueryResponse", {}).get("Bill", [])
print(f"Found {len(bills)} bill(s)")
for b in bills:
    bid = b.get("Id", "")
    docnum = b.get("DocNumber", "")
    vendor = b.get("VendorRef", {}).get("name", "")
    total = b.get("TotalAmt", "")
    print(f"  Bill #{bid}  DocNum={docnum}  Vendor={vendor}  Total=${total}")

print()
print("QBO connection: OK")
