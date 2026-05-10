"""Backfill trim diameters into the 5 pre-2023 AUS1 WO notes.

Two-stage:
  python austin_wo_backfill.py preview   -> show payloads only
  python austin_wo_backfill.py write     -> execute mutations
"""
import os, sys, json
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).parent / ".traxis.env")
GRAPHQL = "https://traxismfg.adionsystems.com/api/graphql"
TOKEN = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
CID = os.environ["PROSHOP_CLIENT_ID"]
SEC = os.environ["PROSHOP_CLIENT_SECRET"]
SCOPE = os.environ["PROSHOP_SCOPE"]

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

# Backfill values: WO -> diameter string (verbatim from PO, verified 2026-05-02)
BACKFILL = {
    "21-0133": "7.19",
    "21-0230": "6.75",
    "22-0001": "6.12",
    "22-0066": "6.813",
    "22-0169": "6.70",
}
TODAY = date.today().isoformat()

def note_html(dia):
    """Match the format of existing modern WO notes (h2 header)."""
    return (
        f'<h2>TRIM TO {dia}" Diameter</h2>'
        f'<p><em>(Backfilled {TODAY} from customer PO - original WO note was empty.)</em></p>'
    )

mode = sys.argv[1] if len(sys.argv) > 1 else "preview"

if mode == "probe":
    # Find the right mutation + input shape
    s = gql('{ __schema { mutationType { fields(includeDeprecated:false) { name args { name type { name kind ofType { name kind } } } } } } }')
    muts = (s.get("data",{}).get("__schema",{}).get("mutationType",{}) or {}).get("fields") or []
    print(f"Total mutations: {len(muts)}")
    wo_muts = [m for m in muts if any(k in m["name"].lower() for k in ("workorder","wo","order"))]
    print(f"WO-ish mutations ({len(wo_muts)}):")
    for m in wo_muts:
        args = ", ".join(f'{a["name"]}:{a["type"].get("name") or (a["type"].get("ofType") or {}).get("name") or a["type"].get("kind")}' for a in m["args"])
        print(f"  {m['name']}({args})")

    for tn in ["UpdateWorkOrderInput"]:
        t = gql(f'{{ __type(name:"{tn}"){{ inputFields {{ name type {{ name kind ofType {{ name kind }} }} }} }} }}')
        flds = (t.get("data",{}).get("__type") or {}).get("inputFields") or []
        print(f"\n{tn} fields:")
        for f in flds:
            ot = f["type"].get("ofType") or {}
            print(f"  {f['name']}: {f['type'].get('name') or ot.get('name') or f['type'].get('kind')}")
    sys.exit(0)

if mode == "preview":
    print("=== DRY RUN PREVIEW ===\n")
    for wo, dia in BACKFILL.items():
        body = note_html(dia)
        print(f"WO {wo}  ->  {dia}\"")
        print(f"  notes (and workOrderNotes) will be set to:")
        print(f"    {body}")
        print()
    print("Run with `write` to execute (5 mutations).")
    sys.exit(0)

if mode == "write":
    print("=== WRITING ===\n")
    for wo, dia in BACKFILL.items():
        body = note_html(dia)
        m = gql("""
          mutation($wo:String!, $data:UpdateWorkOrderInput!){
            updateWorkOrder(workOrderNumber:$wo, data:$data){
              workOrderNumber notes
            }
          }
        """, {"wo": wo, "data": {"notes": body}})
        if "errors" in m:
            print(f"WO {wo}  XX  {m['errors']}")
        else:
            wn = (m.get("data",{}).get("updateWorkOrder") or {}).get("notes","")
            print(f"WO {wo}  OK  -> {dia}\"  (notes now: {wn[:80]}...)")
    sys.exit(0)

print(f"Unknown mode: {mode}")
