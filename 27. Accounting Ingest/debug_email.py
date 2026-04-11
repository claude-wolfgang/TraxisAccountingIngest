"""Debug: find the Gmail test email in the accounting inbox."""
import sys, requests, sqlite3
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import GraphClient, ENV, DB_PATH, db

g = GraphClient()
mailbox = ENV["GRAPH_MAILBOX"]

# Try to get recent emails (without $orderby since it conflicts with $filter)
url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/inbox/messages"

# First: with our normal filter
print("=== With app filter (hasAttachments + since March 15) ===")
params = {
    "$filter": "hasAttachments eq true and receivedDateTime ge 2026-03-15T00:00:00Z",
    "$select": "id,subject,from,receivedDateTime",
    "$top": "50",
}
r = requests.get(url, headers=g._headers(), params=params)
msgs = r.json().get("value", [])
gmail_msgs = [m for m in msgs if "gmail" in m.get("from", {}).get("emailAddress", {}).get("address", "").lower()]
print(f"Total: {len(msgs)} messages, Gmail matches: {len(gmail_msgs)}")
for m in gmail_msgs:
    sender = m["from"]["emailAddress"]["address"]
    print(f"  {m['receivedDateTime'][:19]}  {sender}  {m.get('subject','')}")

# Second: search specifically for gmail
print("\n=== Search for gmail sender ===")
params2 = {
    "$filter": f"from/emailAddress/address eq 'wolfganggriffith@gmail.com'",
    "$select": "id,subject,from,receivedDateTime,hasAttachments",
    "$top": "5",
}
r2 = requests.get(url, headers=g._headers(), params=params2)
if r2.ok:
    msgs2 = r2.json().get("value", [])
    print(f"Found {len(msgs2)} from gmail:")
    for m in msgs2:
        print(f"  {m['receivedDateTime'][:19]}  hasAttach={m.get('hasAttachments')}  {m.get('subject','')}")
else:
    print(f"Search failed: {r2.status_code} {r2.text[:200]}")

# Third: check email_log for what's been processed
print("\n=== Email log (already processed) ===")
con = db()
rows = con.execute("SELECT from_addr, subject, received_at FROM email_log ORDER BY id DESC LIMIT 10").fetchall()
con.close()
print(f"Last {len(rows)} processed:")
for r in rows:
    print(f"  {r[2][:19] if r[2] else '?'}  {r[0]}  {r[1]}")

# Fourth: check queue
print("\n=== Queue (recent) ===")
con = db()
rows = con.execute("SELECT id, doc_type, source, status, from_addr, created_at FROM queue ORDER BY id DESC LIMIT 10").fetchall()
con.close()
for r in rows:
    print(f"  #{r[0]}  {r[1]:20}  {r[2]:8}  {r[3]:10}  {r[4] or '':30}  {(r[5] or '')[:19]}")

print("\nDone.")
