"""Verify new OAuth scope, then walk WO -> CustomerPO -> pOImages for the 5 empty-notes AUS1 WOs."""
import os, json
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).parent / ".traxis.env")
GRAPHQL = "https://traxismfg.adionsystems.com/api/graphql"
TOKEN = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
CID = os.environ["PROSHOP_CLIENT_ID"]
SEC = os.environ["PROSHOP_CLIENT_SECRET"]
SCOPE = os.environ.get("PROSHOP_SCOPE")

print(f"client_id: {CID}")
print(f"scope sent: {SCOPE}")

r = requests.post(TOKEN, data={
    "grant_type":"client_credentials","client_id":CID,"client_secret":SEC,"scope":SCOPE
}, timeout=15)
r.raise_for_status()
TOK = r.json()["access_token"]
H = {"Authorization": f"Bearer {TOK}", "Content-Type":"application/json"}

def gql(q, v=None):
    p = {"query": q}
    if v: p["variables"] = v
    rr = requests.post(GRAPHQL, json=p, headers=H, timeout=30)
    return rr.json()

EMPTY_WOS = ["21-0133","21-0230","22-0001","22-0066","22-0169"]

# Probe CustomerPOImage and PaginatedCustomerPOImageResult shape
for tn in ["CustomerPOImage","PaginatedCustomerPOImageResult"]:
    t = gql(f'{{ __type(name:"{tn}"){{ fields(includeDeprecated:false){{ name type {{ name kind ofType {{ name }} }} }} }} }}')
    fields = (t.get("data",{}).get("__type") or {}).get("fields") or []
    print(f"\n{tn} fields:")
    for f in fields:
        ot = f["type"].get("ofType") or {}
        print(f"  {f['name']}: {f['type'].get('name') or ot.get('name') or f['type'].get('kind')}")

# Pull each empty-notes WO -> CustomerPO -> notes/files
QUERY = """
  query($wo:String!){
    workOrder(workOrderNumber:$wo){
      workOrderNumber customerPlainText customerPONumberPlainText
      customerPONumber {
        clientPONumber poId proshopUrl
        notes
        pOImages(pageSize:20){
          records {
            poimage(pageSize:10){
              records { title description fileUrl fileLoc uploadedTime }
            }
          }
        }
      }
    }
  }
"""

results = {}
for wo in EMPTY_WOS:
    r = gql(QUERY, {"wo": wo})
    if "errors" in r:
        print(f"\n[WO {wo}] ERROR:", r["errors"]); continue
    w = (r.get("data",{}).get("workOrder")) or {}
    print(f"\n=== WO {wo} ===")
    print(f"  customer: {w.get('customerPlainText')}")
    po = w.get("customerPONumber") or {}
    print(f"  PO#: {po.get('clientPONumber')} (poId={po.get('poId')})")
    print(f"  PO url: {po.get('proshopUrl')}")
    if po.get("notes"):
        print(f"  PO notes: {po['notes'][:400]}")
    files = []
    for img_rec in (po.get("pOImages") or {}).get("records", []):
        for f in (img_rec.get("poimage") or {}).get("records", []):
            files.append(f)
    print(f"  attached files: {len(files)}")
    for f in files:
        print(f"    - {f.get('title')} | {f.get('fileUrl')}")
    results[wo] = {"po": po, "files": files}

# Save results for next-step PDF download
import pickle
with open("austin_po_results.pkl","wb") as fh:
    pickle.dump(results, fh)
print(f"\nSaved {len(results)} WO results.")
