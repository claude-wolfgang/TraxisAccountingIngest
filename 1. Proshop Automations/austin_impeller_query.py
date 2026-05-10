"""One-off query: pull Austin Pump impeller work orders + notes, summarize sizes/qtys."""
import os, re, sys
from pathlib import Path
from dotenv import load_dotenv
import requests

ENV = Path(__file__).parent / ".traxis.env"
load_dotenv(ENV)

GRAPHQL = "https://traxismfg.adionsystems.com/api/graphql"
TOKEN = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
CID = os.environ["PROSHOP_CLIENT_ID"]
SEC = os.environ["PROSHOP_CLIENT_SECRET"]
SCOPE = os.environ.get("PROSHOP_SCOPE", "parts:rwdp+workorders:rwdp")

r = requests.post(TOKEN, data={
    "grant_type":"client_credentials","client_id":CID,"client_secret":SEC,"scope":SCOPE
}, timeout=15)
r.raise_for_status()
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}", "Content-Type":"application/json"}

def gql(q, v=None):
    p = {"query": q}
    if v: p["variables"] = v
    rr = requests.post(GRAPHQL, json=p, headers=H, timeout=30)
    rr.raise_for_status()
    return rr.json()

# Schema probe — find a type containing workOrder fields
import json
schema = gql("""{ __schema { types { name kind } } }""")
types = (schema.get("data",{}).get("__schema") or {}).get("types") or []
wo_types = [t["name"] for t in types if t.get("name") and "workorder" in t["name"].lower()]
print("[schema] WO-related types:", wo_types)

STATUSES = ["ACTIVE","EXPECTED","ON_HOLD","COMPLETE","MANUFACTURING_COMPLETE","SHIPPED","INVOICED","CANCELED"]
all_wos = []
for st in STATUSES:
    try:
        r = gql("""
          query($s:String!){
            workOrders(pageSize:500, query:{ status:{ exactly:$s } }){
              records {
                workOrderNumber status quantityOrdered qtyComplete qtyShipped
                partPlainText partRev
                notes workOrderNotes
              }
            }
          }
        """, {"s": st})
        recs = (r.get("data",{}).get("workOrders") or {}).get("records") or []
        all_wos.extend(recs)
        print(f"[{st}] {len(recs)}")
    except Exception as e:
        print(f"[{st}] error: {e}")

print(f"\nTotal WOs fetched: {len(all_wos)}")

# Filter to AUS1-Impeller only (definitive Austin Pump impeller match)
aus = [w for w in all_wos if "aus1-impeller" in (w.get("partPlainText") or "").lower()]
print(f"AUS1-Impeller WOs: {len(aus)}")

# Strip HTML tags and extract diameter
TAG = re.compile(r"<[^>]+>")
NBSP = re.compile(r"&nbsp;|&amp;")
# Match: any number (with optional decimal/fraction) followed optionally by " or in
DIA = re.compile(r'(\d+(?:[.\-/]\d+)?)\s*(?:["”]|inch|in\b)?', re.I)

def clean(s):
    if not s: return ""
    s = NBSP.sub(" ", s)
    s = TAG.sub(" ", s)
    return " ".join(s.split())

def extract_dia(notes):
    """Pull the trim diameter from notes like 'TRIM TO 6.813" Diameter' or 'Trim to 5.2'"""
    txt = clean(notes).lower()
    m = re.search(r'trim\s+to\s+([\d.\-/]+)', txt)
    if m: return m.group(1)
    return None

print(f"\n{'WO':<10} {'Status':<10} {'Qty':<5} {'Trim Ø':<10} Notes")
print("-"*100)
rows = []
for w in sorted(aus, key=lambda x: x.get("workOrderNumber") or ""):
    notes = (w.get("notes") or "") + " " + (w.get("workOrderNotes") or "")
    dia = extract_dia(notes)
    qty = w.get("quantityOrdered") or 0
    raw = clean(notes)[:80] if notes.strip() else "(empty)"
    rows.append((w.get("workOrderNumber"), w.get("status"), qty, dia, raw))
    print(f"{w.get('workOrderNumber'):<10} {w.get('status'):<10} {qty:<5} {(dia or '-'):<10} {raw}")

# Summary by diameter
print("\n=== Summary by trim diameter ===")
from collections import Counter
by_dia = Counter()
no_dia = 0
for _, st, qty, dia, _ in rows:
    if dia:
        by_dia[dia] += int(qty or 0)
    else:
        no_dia += int(qty or 0)

for dia, total in sorted(by_dia.items(), key=lambda x: float(x[0].replace("-","."))):
    print(f"  {dia}\"  →  {total} pcs")
print(f"  (no diameter in WO notes)  →  {no_dia} pcs across {sum(1 for r in rows if not r[3])} WOs")

print(f"\n=== {len(hits)} matching WOs ===\n")
for w in hits:
    print(f"WO {w.get('workOrderNumber')} | {w.get('status')} | qtyOrd={w.get('quantityOrdered')} qtyComp={w.get('qtyComplete')} qtyShp={w.get('qtyShipped')}")
    print(f"  cust: {w.get('customerPlainText')}")
    print(f"  part: {w.get('partPlainText')} rev {w.get('partRev')}")
    n = w.get("notes") or ""
    wn = w.get("workOrderNotes") or ""
    if n: print(f"  notes: {n[:500]}")
    if wn: print(f"  workOrderNotes: {wn[:500]}")
    print()
