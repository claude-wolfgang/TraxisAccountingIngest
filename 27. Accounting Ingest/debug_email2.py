"""Debug: find the Gmail test email."""
import sys, requests
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import GraphClient, ENV

g = GraphClient()
mailbox = ENV["GRAPH_MAILBOX"]
url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/inbox/messages"

# Search for April emails only (skip the old March backlog)
print("=== April emails with attachments ===")
params = {
    "$filter": "hasAttachments eq true and receivedDateTime ge 2026-04-01T00:00:00Z",
    "$select": "id,subject,from,receivedDateTime",
    "$top": "50",
}
r = requests.get(url, headers=g._headers(), params=params)
msgs = r.json().get("value", [])
print(f"Found {len(msgs)}")
for m in msgs:
    sender = m.get("from", {}).get("emailAddress", {}).get("address", "")
    print(f"  {m['receivedDateTime'][:19]}  {sender:40}  {m.get('subject','')[:50]}")

# Search specifically for thomasbuerkle
print("\n=== Search for thomasbuerkle@gmail.com ===")
params2 = {
    "$search": '"from:thomasbuerkle@gmail.com"',
    "$select": "id,subject,from,receivedDateTime,hasAttachments",
    "$top": "5",
}
r2 = requests.get(url, headers=g._headers(), params=params2)
if r2.ok:
    msgs2 = r2.json().get("value", [])
    print(f"Found {len(msgs2)}")
    for m in msgs2:
        sender = m.get("from", {}).get("emailAddress", {}).get("address", "")
        print(f"  {m['receivedDateTime'][:19]}  attach={m.get('hasAttachments')}  {sender}  {m.get('subject','')}")
else:
    print(f"Error: {r2.status_code} {r2.text[:200]}")

print("\nDone.")
