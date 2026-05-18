"""One-shot: take a QBO redirect URL on argv, exchange code for tokens, write to .traxis.env.
Bypasses the interactive input() in qbo_auth.py for when we already have the callback URL.
"""
import base64
import re
import sys
import urllib.parse
from pathlib import Path

import requests

CLIENT_ID = "AB0z1VxUYr1x9DMoGvbVTPjKBLJGI8IPq9WB9JmTXnD61LUAHW"
CLIENT_SECRET = "NAjbOzHOiqcPapYqkmdmX8zn60N0PKCZ72yrAaXQ"
REDIRECT_URI = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
ENV_PATH = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")

callback_url = sys.argv[1]
parsed = urllib.parse.urlparse(callback_url)
params = urllib.parse.parse_qs(parsed.query)
auth_code = params["code"][0]
realm_id = params["realmId"][0]

creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
r = requests.post(TOKEN_URL, headers={
    "Authorization": f"Basic {creds}",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}, data={
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": REDIRECT_URI,
}, timeout=30)
if not r.ok:
    print(f"Token exchange failed {r.status_code}: {r.text}", file=sys.stderr)
    sys.exit(1)

tokens = r.json()
refresh_token = tokens["refresh_token"]
print(f"OK. realm={realm_id}  refresh={refresh_token[:14]}...")

text = ENV_PATH.read_text()
text = re.sub(r"^QBO_REFRESH_TOKEN=.*$", f"QBO_REFRESH_TOKEN={refresh_token}", text, flags=re.MULTILINE)
text = re.sub(r"^QBO_REALM_ID=.*$", f"QBO_REALM_ID={realm_id}", text, flags=re.MULTILINE)
ENV_PATH.write_text(text)
print(f"Wrote QBO_REFRESH_TOKEN + QBO_REALM_ID to {ENV_PATH.name}")
