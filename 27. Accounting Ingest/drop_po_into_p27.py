"""Download a specific PDF attachment from tom@'s Orders folder and drop it
into the P27 SCAN_FOLDER so the FolderWatcher picks it up.

Use when an email arrived only at tom@traxismfg.com (e.g. R2Sonic POs that
NetSuite emails to tom@ but not accounting@). The accounting@ poller skips
@traxismfg.com senders so Tom's FW:'d copy never enters the queue.

Pass the message subject (substring) and optionally the attachment-name
substring to disambiguate.
"""

from pathlib import Path
import base64
import json
import sys
import requests

import reconcile_folders as rf

ENV = rf.ENV
SCAN_FOLDER = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\Scanned")

def find_message(mailbox, folder_name, subject_needle):
    folders = rf.list_all_folders(mailbox)
    target = next((f for f in folders if f["displayName"].lower() == folder_name.lower()), None)
    if not target:
        raise RuntimeError(f"Folder {folder_name!r} not found in {mailbox}")
    msgs = rf.messages_in_folder(mailbox, target["id"], rf.LOOKBACK_DAYS)
    hits = [m for m in msgs if subject_needle.lower() in (m.get("subject") or "").lower()]
    return hits

def download_pdf_attachments(mailbox, msg_id, attachment_substr=None):
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{msg_id}/attachments"
    data = rf.graph_get(url)
    saved = []
    for att in data.get("value", []):
        if att.get("isInline"):
            continue
        name = att.get("name", "")
        if not name.lower().endswith(".pdf"):
            continue
        if attachment_substr and attachment_substr.lower() not in name.lower():
            continue
        # Re-fetch the single attachment to ensure we get contentBytes
        att_url = f"{url}/{att['id']}"
        full = rf.graph_get(att_url)
        content_b64 = full.get("contentBytes")
        if not content_b64:
            continue
        SCAN_FOLDER.mkdir(parents=True, exist_ok=True)
        safe_name = name.replace("/", "_").replace("\\", "_")
        out_path = SCAN_FOLDER / safe_name
        if out_path.exists():
            stem = out_path.stem
            out_path = out_path.with_name(f"{stem}__from_tom_orders.pdf")
        out_path.write_bytes(base64.b64decode(content_b64))
        saved.append(out_path)
        print(f"  saved -> {out_path}")
    return saved

def main():
    if len(sys.argv) < 2:
        print("Usage: drop_po_into_p27.py <subject substring> [attachment substring]")
        sys.exit(1)
    needle = sys.argv[1]
    att_sub = sys.argv[2] if len(sys.argv) > 2 else None
    hits = find_message("tom@traxismfg.com", "Orders", needle)
    print(f"Found {len(hits)} messages matching subject {needle!r}:")
    for m in hits:
        frm = (m.get("from") or {}).get("emailAddress", {}).get("address", "")
        print(f"  - {m.get('receivedDateTime','')[:10]}  {frm}  {m.get('subject')}")
    # Prefer the original from netsuite/customer (not the FW: from tom@)
    originals = [m for m in hits
                 if not (m.get("from") or {}).get("emailAddress", {}).get("address", "")
                 .lower().endswith("@traxismfg.com")]
    if not originals:
        print("No external-sender message matched; using all hits.")
        originals = hits
    if not originals:
        print("No message to act on.")
        sys.exit(1)
    for m in originals:
        print(f"\nDownloading from msg {m.get('subject')}:")
        download_pdf_attachments("tom@traxismfg.com", m["id"], att_sub)

if __name__ == "__main__":
    main()
