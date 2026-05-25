"""
Read-only recon of the Outlook "Bills and Invoices" mail folder.

Locates the named mail folder (recursing nested folders) in the target
mailbox via Microsoft Graph (app-only credentials from .traxis.env, same
as accounting_ingest.GraphClient), then lists its messages + attachment
metadata. No writes, no marking-read, no downloads.

Usage:
    python read_bills_folder.py [mailbox] [folder-name]

Defaults: mailbox=tom@traxismfg.com, folder="Bills and Invoices".
Writes a JSON sidecar to logs/bills_folder_recon.json.
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests
from accounting_ingest import load_env, GRAPH_TOKEN_URL

ENV = load_env()
GRAPH = "https://graph.microsoft.com/v1.0"

DEFAULT_MAILBOX = "tom@traxismfg.com"
DEFAULT_FOLDER = "Bills and Invoices"


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


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def walk_folders(tok, mailbox, parent="msgfolderroot", path="", depth=0, out=None):
    """Recursively enumerate mail folders. Returns list of dicts."""
    if out is None:
        out = []
    if depth > 6:
        return out
    url = f"{GRAPH}/users/{mailbox}/mailFolders/{parent}/childFolders"
    params = {"$top": "100",
              "$select": "id,displayName,childFolderCount,totalItemCount,unreadItemCount"}
    while url:
        r = requests.get(url, headers=hdr(tok), params=params)
        r.raise_for_status()
        data = r.json()
        for f in data.get("value", []):
            fpath = f"{path}/{f['displayName']}" if path else f["displayName"]
            rec = {"id": f["id"], "name": f["displayName"], "path": fpath,
                   "total": f.get("totalItemCount"), "children": f.get("childFolderCount")}
            out.append(rec)
            if f.get("childFolderCount"):
                walk_folders(tok, mailbox, f["id"], fpath, depth + 1, out)
        url = data.get("@odata.nextLink")
        params = None
    return out


def list_messages(tok, mailbox, folder_id, cap=200):
    url = f"{GRAPH}/users/{mailbox}/mailFolders/{folder_id}/messages"
    params = {"$top": "50", "$orderby": "receivedDateTime desc",
              "$select": "id,subject,from,receivedDateTime,hasAttachments,bodyPreview"}
    msgs = []
    while url and len(msgs) < cap:
        r = requests.get(url, headers=hdr(tok), params=params)
        r.raise_for_status()
        data = r.json()
        msgs.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None
    return msgs[:cap]


def list_attachments(tok, mailbox, msg_id):
    url = f"{GRAPH}/users/{mailbox}/messages/{msg_id}/attachments"
    r = requests.get(url, headers=hdr(tok),
                     params={"$select": "id,name,contentType,size,isInline"})
    r.raise_for_status()
    return r.json().get("value", [])


def main():
    mailbox = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAILBOX
    target = (sys.argv[2] if len(sys.argv) > 2 else DEFAULT_FOLDER).strip().lower()

    tok = get_token()
    print(f"Mailbox: {mailbox}")
    folders = walk_folders(tok, mailbox)
    print(f"Enumerated {len(folders)} folders.")

    match = [f for f in folders if f["name"].strip().lower() == target]
    if not match:
        print(f"\nNo folder named '{target}'. Candidates containing 'bill' or 'invoice':")
        for f in folders:
            n = f["name"].lower()
            if "bill" in n or "invoic" in n:
                print(f"  - {f['path']}  ({f['total']} items)")
        # dump full tree to help
        Path("logs").mkdir(exist_ok=True)
        Path("logs/bills_folder_recon.json").write_text(
            json.dumps({"mailbox": mailbox, "folders": folders}, indent=2))
        print("\nFull folder tree written to logs/bills_folder_recon.json")
        return

    folder = match[0]
    print(f"\nFound: {folder['path']}  (id={folder['id'][:24]}...)  {folder['total']} items")

    msgs = list_messages(tok, mailbox, folder["id"])
    print(f"Listed {len(msgs)} messages.\n")

    report = []
    for m in msgs:
        frm = (m.get("from") or {}).get("emailAddress", {})
        atts = []
        if m.get("hasAttachments"):
            try:
                for a in list_attachments(tok, mailbox, m["id"]):
                    if not a.get("isInline"):
                        atts.append({"name": a.get("name"),
                                     "type": a.get("contentType"),
                                     "size": a.get("size")})
            except Exception as e:
                atts.append({"error": str(e)})
        report.append({
            "received": m.get("receivedDateTime"),
            "from": frm.get("address"),
            "subject": m.get("subject"),
            "preview": (m.get("bodyPreview") or "")[:120],
            "attachments": atts,
        })

    for r in report:
        print(f"{r['received'][:10]}  {r['from'] or '?':35.35}  {r['subject'][:55]:55.55}")
        for a in r["attachments"]:
            if "error" in a:
                print(f"        [attach error] {a['error']}")
            else:
                print(f"        * {a['name']}  ({a['type']}, {a['size']} bytes)")

    Path("logs").mkdir(exist_ok=True)
    out = {"mailbox": mailbox, "folder": folder["path"], "folder_id": folder["id"],
           "generated": datetime.now(timezone.utc).isoformat(),
           "message_count": len(report), "messages": report}
    Path("logs/bills_folder_recon.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote logs/bills_folder_recon.json ({len(report)} messages).")


if __name__ == "__main__":
    main()
