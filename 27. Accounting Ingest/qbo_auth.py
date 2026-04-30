"""
QBO OAuth2 Authorization Helper — Production
Run this ONCE to authorize the app against your Traxis QBO company.
Stores the refresh token + realm ID to .traxis.env automatically.

Uses Intuit's own OAuth2 Playground redirect URI (already registered in the
production app) and asks you to paste the callback URL from your browser.
"""

import urllib.parse
import webbrowser
import requests
import base64
from pathlib import Path

CLIENT_ID     = "AB0z1VxUYr1x9DMoGvbVTPjKBLJGI8IPq9WB9JmTXnD61LUAHW"
CLIENT_SECRET = "NAjbOzHOiqcPapYqkmdmX8zn60N0PKCZ72yrAaXQ"
REDIRECT_URI  = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
SCOPE         = "com.intuit.quickbooks.accounting"
AUTH_URL       = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL     = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
ENV_PATH      = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")

import secrets as _secrets

def main():
    csrf_state = _secrets.token_urlsafe(32)

    params = {
        "client_id":     CLIENT_ID,
        "response_type": "code",
        "scope":         SCOPE,
        "redirect_uri":  REDIRECT_URI,
        "state":         csrf_state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("Opening browser for QBO production authorization...")
    print(f"\nIf browser doesn't open, go to:\n{url}\n")
    webbrowser.open(url)

    print("=" * 60)
    print("After you authorize, the browser will redirect to an Intuit page.")
    print("Copy the FULL URL from your browser's address bar and paste it here.")
    print("=" * 60)
    callback_url = input("\nPaste the redirect URL here: ").strip()

    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)

    # CSRF check
    returned_state = params.get("state", [None])[0]
    if returned_state != csrf_state:
        print("ERROR: CSRF state mismatch — aborting for safety.")
        return

    if params.get("error"):
        print(f"ERROR: {params['error'][0]} — {params.get('error_description', [''])[0]}")
        return

    auth_code = params.get("code", [None])[0]
    realm_id  = params.get("realmId", [None])[0]

    if not auth_code or not realm_id:
        print("ERROR: Could not extract auth code or realm ID from URL.")
        print(f"  code: {auth_code}")
        print(f"  realmId: {realm_id}")
        return

    print(f"\nGot auth code. Realm ID: {realm_id}")

    # Exchange code for tokens
    credentials = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(TOKEN_URL, headers={
        "Authorization": f"Basic {credentials}",
        "Content-Type":  "application/x-www-form-urlencoded",
        "Accept":        "application/json",
    }, data={
        "grant_type":   "authorization_code",
        "code":         auth_code,
        "redirect_uri": REDIRECT_URI,
    })
    r.raise_for_status()
    tokens = r.json()

    access_token  = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    print(f"Access token:  {access_token[:30]}...")
    print(f"Refresh token: {refresh_token[:30]}...")
    print(f"Realm ID:      {realm_id}")

    # Update .traxis.env
    env_text = ENV_PATH.read_text()
    new_lines = f"""
# QuickBooks Online API
QBO_CLIENT_ID={CLIENT_ID}
QBO_CLIENT_SECRET={CLIENT_SECRET}
QBO_REALM_ID={realm_id}
QBO_REFRESH_TOKEN={refresh_token}
"""
    filtered = "\n".join(
        line for line in env_text.splitlines()
        if not line.startswith("QBO_")
    )
    ENV_PATH.write_text(filtered.rstrip() + "\n" + new_lines)
    print(f"\nCredentials saved to {ENV_PATH}")
    print("\nQBO production authorization complete. You can now run the main app.")

if __name__ == "__main__":
    main()
