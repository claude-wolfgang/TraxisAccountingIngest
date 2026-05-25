"""
Download + AI-extract a targeted set of vendor-invoice PDFs from the
"Bills and Invoices" mail folder, so amounts/doc numbers can be reconciled
against QBO before any bill entry. Read-only against the mailbox (no
mark-read); writes downloaded PDFs to logs/extract_tmp/ and a JSON summary
to logs/new_bills_extracted.json.

Reads mailbox + folder_id from logs/bills_folder_recon.json (run
read_bills_folder.py first).
"""
import json
import base64
import re
from pathlib import Path
from datetime import datetime, timezone

import requests
from accounting_ingest import load_env, GRAPH_TOKEN_URL, AIExtractor

ENV = load_env()
GRAPH = "https://graph.microsoft.com/v1.0"
RECON = Path("logs/bills_folder_recon.json")
TMP = Path("logs/extract_tmp")

# Target attachment filenames (the unique new-bill PDFs + Hillary for dup-tag).
TARGETS = [
    "Inv1878933.pdf",
    "Inv1880454.pdf",
    "Inv1880461.pdf",
    "Inv1880885.pdf",
    "IV_I021530150100AR_.pdf",                                  # Hadco 2153015
    "Invoice- Traxis MFG Rotor Wheel  263050 #260091.pdf",     # LP Machine 260091
    "PH_13_051826_75903239.PDF",                               # Dixie Tool Crib
    "Traxis_Invoice_2026-05-14-1.pdf",                         # Sam (portal man)
    "May invoice.pdf",                                         # Sentry May
    "Inv_153025_from_Hillary_Machinery_Inc_22468.pdf",        # Hillary (dup-tag)
]


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


TARGET_SET = {norm(t) for t in TARGETS}


def get_token():
    url = GRAPH_TOKEN_URL.format(tenant_id=ENV["GRAPH_TENANT_ID"])
    r = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": ENV["GRAPH_CLIENT_ID"],
        "client_secret": ENV["GRAPH_CLIENT_SECRET"],
        "scope": "https://graph.microsoft.com/.default",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def list_messages(tok, mailbox, folder_id):
    url = f"{GRAPH}/users/{mailbox}/mailFolders/{folder_id}/messages"
    params = {"$top": "50", "$orderby": "receivedDateTime desc",
              "$select": "id,subject,hasAttachments"}
    out = []
    while url:
        r = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, params=params)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("value", []))
        url = d.get("@odata.nextLink")
        params = None
    return out


def get_attachments(tok, mailbox, msg_id):
    url = f"{GRAPH}/users/{mailbox}/messages/{msg_id}/attachments"
    r = requests.get(url, headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    return r.json().get("value", [])


def main():
    meta = json.loads(RECON.read_text())
    mailbox, folder_id = meta["mailbox"], meta["folder_id"]
    tok = get_token()
    TMP.mkdir(parents=True, exist_ok=True)

    extractor = AIExtractor()
    msgs = list_messages(tok, mailbox, folder_id)

    seen = {}
    results = []
    for m in msgs:
        if not m.get("hasAttachments"):
            continue
        if set(seen) >= TARGET_SET:
            break
        for a in get_attachments(tok, mailbox, m["id"]):
            nm = a.get("name")
            if a.get("isInline") or norm(nm) not in TARGET_SET or norm(nm) in seen:
                continue
            content = a.get("contentBytes")
            if not content:
                continue
            local = TMP / nm
            local.write_bytes(base64.b64decode(content))
            print(f"Extracting: {nm} ...")
            try:
                ex = extractor.extract(str(local), "VENDOR_INVOICE")
            except Exception as e:
                ex = {"error": str(e)}
            results.append({"file": nm, "subject": m.get("subject"), "extracted": ex})
            seen[norm(nm)] = nm

    missing = TARGET_SET - set(seen)
    print("\n" + "=" * 100)
    print(f"{'Vendor':28.28} {'Invoice #':14.14} {'Date':11.11} {'Total':>11} {'Lines':>5}  File")
    print("-" * 100)
    for r in results:
        ex = r["extracted"]
        if "error" in ex:
            print(f"{'[EXTRACT ERROR]':28.28} {'':14} {'':11} {'':>11} {'':>5}  {r['file']}  ({ex['error'][:40]})")
            continue
        print(f"{(ex.get('vendor_name') or '?'):28.28} "
              f"{str(ex.get('invoice_number') or '?'):14.14} "
              f"{str(ex.get('invoice_date') or '?'):11.11} "
              f"{str(ex.get('total_amount') or '?'):>11} "
              f"{len(ex.get('line_items') or []):>5}  {r['file']}")
    if missing:
        print(f"\nNOT FOUND in folder: {sorted(missing)}")

    Path("logs/new_bills_extracted.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "results": results, "missing": sorted(missing)}, indent=2))
    print(f"\nWrote logs/new_bills_extracted.json ({len(results)} extracted).")


if __name__ == "__main__":
    main()
