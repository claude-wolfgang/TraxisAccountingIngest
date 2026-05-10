"""Probe ProShop schema for Customer PO entities and file attachments."""
import os, json, re
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).parent / ".traxis.env")
GRAPHQL = "https://traxismfg.adionsystems.com/api/graphql"
TOKEN = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
CID = os.environ["PROSHOP_CLIENT_ID"]
SEC = os.environ["PROSHOP_CLIENT_SECRET"]
SCOPE = os.environ.get("PROSHOP_SCOPE")

r = requests.post(TOKEN, data={"grant_type":"client_credentials","client_id":CID,"client_secret":SEC,"scope":SCOPE}, timeout=15)
r.raise_for_status()
TOK = r.json()["access_token"]
H = {"Authorization": f"Bearer {TOK}", "Content-Type":"application/json"}

def gql(q, v=None):
    p = {"query": q}
    if v: p["variables"] = v
    rr = requests.post(GRAPHQL, json=p, headers=H, timeout=30)
    return rr.json()

# 1. Find PO / Purchase Order related types
schema = gql('{ __schema { types { name } } }')
types = [t["name"] for t in schema["data"]["__schema"]["types"] if t["name"]]
po_types = [t for t in types if any(k in t.lower() for k in ("purchaseorder","customerpo","po","sales"))]
print("PO-ish types:", po_types)

# 2. WorkOrderFiles fields
for tn in ["WorkOrderFiles", "WorkOrder"]:
    t = gql(f'{{ __type(name:"{tn}"){{ fields(includeDeprecated:false){{ name type {{ name kind ofType {{ name }} }} }} }} }}')
    fields = (t.get("data",{}).get("__type") or {}).get("fields") or []
    if not fields: continue
    interesting = [f for f in fields if any(k in f["name"].lower() for k in ("file","attach","upload","po","customer"))]
    print(f"\n{tn} file/PO fields:")
    for f in interesting:
        ofType = f["type"].get("ofType") or {}
        print(f"  {f['name']}: {f['type'].get('name') or ofType.get('name') or f['type'].get('kind')}")

# Probe FileWithMetadata
t = gql('{ __type(name:"FileWithMetadata"){ fields(includeDeprecated:false){ name } } }')
print("\nFileWithMetadata fields:", [f["name"] for f in (t.get("data",{}).get("__type") or {}).get("fields") or []])

# Probe CustomerPO
t = gql('{ __type(name:"CustomerPO"){ fields(includeDeprecated:false){ name } } }')
print("\nCustomerPO fields:", [f["name"] for f in (t.get("data",{}).get("__type") or {}).get("fields") or []])

# Try WO without customerPONumberPlainText (which needs scope)
for wo in ["21-0133","21-0230","22-0001","22-0066","22-0169"]:
    sample = gql("""
      query($wo:String!){
        workOrder(workOrderNumber:$wo){
          workOrderNumber
          workOrderFiles(pageSize:50){
            records { title description fileUrl fileLoc uploadedTime }
          }
        }
      }
    """, {"wo": wo})
    print(f"\n[WO {wo}]:", json.dumps(sample, indent=2)[:2000])
