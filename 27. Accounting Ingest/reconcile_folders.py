"""Reconcile Outlook "Bills and invoices" + "Orders" folders against ProShop/QBO.

Phase 1 (this script): authenticate to Graph as the accounting mailbox, list
mail folders, find the two target folders by displayName, and dump each
message's subject/from/received/attachment-names so we can see what's in there
before deciding the dup-check strategy.
"""

from pathlib import Path
import json
import re
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

ENV_PATHS = [
    Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env"),
    Path(r"C:\Users\TRAXIS\.traxis.env"),
]

def load_env():
    for p in ENV_PATHS:
        if p.exists():
            env = {}
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            return env
    raise RuntimeError("No .traxis.env found")

ENV = load_env()

TARGET_FOLDER_NAMES = ["Bills and invoices", "Orders"]
# Fuzzy fallback patterns if exact name not found
TARGET_PATTERNS = [
    re.compile(r"^orders?$", re.I),
    re.compile(r"bill", re.I),
    re.compile(r"invoice", re.I),
]
LOOKBACK_DAYS = 180

# ─── Graph auth ─────────────────────────────────────────────────────────────

_token_cache = {"tok": None, "exp": 0}

def graph_token():
    if _token_cache["tok"] and time.time() < _token_cache["exp"] - 60:
        return _token_cache["tok"]
    url = f"https://login.microsoftonline.com/{ENV['GRAPH_TENANT_ID']}/oauth2/v2.0/token"
    r = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": ENV["GRAPH_CLIENT_ID"],
        "client_secret": ENV["GRAPH_CLIENT_SECRET"],
        "scope": "https://graph.microsoft.com/.default",
    })
    r.raise_for_status()
    data = r.json()
    _token_cache["tok"] = data["access_token"]
    _token_cache["exp"] = time.time() + data.get("expires_in", 3600)
    return _token_cache["tok"]

def graph_get(url, params=None):
    r = requests.get(url, headers={"Authorization": f"Bearer {graph_token()}"},
                     params=params)
    r.raise_for_status()
    return r.json()

def list_all_folders(mailbox):
    """Walk every folder recursively (paginating both top-level and children)."""
    out = []

    def walk(folder_id, parent_name):
        url = (f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders"
               if folder_id is None
               else f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/{folder_id}/childFolders")
        params = {"$top": "100"}
        while url:
            data = graph_get(url, params)
            for f in data.get("value", []):
                out.append({
                    "id": f["id"],
                    "displayName": f["displayName"],
                    "totalItemCount": f.get("totalItemCount"),
                    "unreadItemCount": f.get("unreadItemCount"),
                    "parent": parent_name,
                })
                if f.get("childFolderCount", 0) > 0:
                    walk(f["id"], f["displayName"])
            url = data.get("@odata.nextLink")
            params = None

    walk(None, None)
    return out

def messages_in_folder(mailbox, folder_id, lookback_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT00:00:00Z")
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/{folder_id}/messages"
    params = {
        "$filter": f"receivedDateTime ge {cutoff}",
        "$select": "id,subject,from,receivedDateTime,hasAttachments",
        "$top": "50",
        "$orderby": "receivedDateTime desc",
    }
    out = []
    while url:
        data = graph_get(url, params)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None
    return out

def attachment_names(mailbox, msg_id):
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{msg_id}/attachments"
    data = graph_get(url, {"$select": "name,contentType,size"})
    return [{"name": a.get("name"), "type": a.get("contentType"), "size": a.get("size")}
            for a in data.get("value", [])]

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    candidate_mailboxes = sys.argv[1:] if len(sys.argv) > 1 else [
        "tom@traxismfg.com",
        ENV["GRAPH_MAILBOX"],  # accounting@
    ]

    mailbox = None
    folders = None
    targets = None
    for mb in candidate_mailboxes:
        print(f"\nTrying mailbox: {mb}")
        try:
            fs = list_all_folders(mb)
        except requests.HTTPError as e:
            print(f"  failed: {e}")
            continue
        lowered = {n.lower() for n in TARGET_FOLDER_NAMES}
        hits = [f for f in fs if f["displayName"].lower() in lowered]
        if hits:
            mailbox = mb
            folders = fs
            targets = hits
            break
        else:
            print(f"  no target folders in {mb} (found {len(fs)} folders total)")

    if not targets:
        # Last-resort: dump all folders from the last attempted mailbox
        print("\nNo matching folders found in any candidate mailbox.")
        if folders:
            for f in folders:
                parent = f"  (in {f['parent']})" if f['parent'] else ""
                print(f"  - {f['displayName']}{parent}  [{f['totalItemCount']} items]")
        sys.exit(1)

    print(f"\nUsing mailbox: {mailbox}")
    print(f"Lookback: {LOOKBACK_DAYS} days\n")

    print("Found target folders:")
    for f in targets:
        parent = f"  (in {f['parent']})" if f['parent'] else ""
        print(f"  - {f['displayName']}{parent}  [{f['totalItemCount']} items, {f['unreadItemCount']} unread]")
    print()

    report = {}
    for f in targets:
        name = f["displayName"]
        print(f"\n=== {name} (lookback {LOOKBACK_DAYS}d) ===")
        msgs = messages_in_folder(mailbox, f["id"], LOOKBACK_DAYS)
        print(f"Messages in window: {len(msgs)}\n")
        folder_rows = []
        for m in msgs:
            frm = (m.get("from") or {}).get("emailAddress", {})
            row = {
                "graph_id": m["id"],
                "received": m.get("receivedDateTime", "")[:10],
                "from": frm.get("address", ""),
                "from_name": frm.get("name", ""),
                "subject": m.get("subject", "")[:120],
                "hasAttachments": m.get("hasAttachments"),
            }
            if m.get("hasAttachments"):
                try:
                    row["attachments"] = attachment_names(mailbox, m["id"])
                except Exception as e:
                    row["attachments_error"] = str(e)[:100]
            folder_rows.append(row)
            atts = ""
            if m.get("hasAttachments") and row.get("attachments"):
                atts = " | " + ", ".join(a["name"] for a in row["attachments"] if a.get("name"))
            print(f"  {row['received']}  {row['from'][:35]:<35}  {row['subject'][:80]}{atts}")
        report[name] = folder_rows

    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    out_path = logs_dir / "reconcile_folders_phase1.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote raw report -> {out_path}")

if __name__ == "__main__":
    main()
