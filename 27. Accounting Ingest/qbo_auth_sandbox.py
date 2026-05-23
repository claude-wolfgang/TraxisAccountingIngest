"""
QBO OAuth2 Authorization Helper — Sandbox

Same OAuth flow as qbo_auth.py, but writes the resulting refresh token and
realm id to QBO_SANDBOX_REFRESH_TOKEN / QBO_SANDBOX_REALM_ID in .traxis.env
so production keys are untouched.

Run this once to attach to your sandbox QBO company. When the browser shows
the company picker, pick the company labeled "[SANDBOX]" — not production.
"""

import urllib.parse
import webbrowser
import requests
import base64
import secrets as _secrets
from pathlib import Path

CLIENT_ID     = "AB0z1VxUYr1x9DMoGvbVTPjKBLJGI8IPq9WB9JmTXnD61LUAHW"
CLIENT_SECRET = "NAjbOzHOiqcPapYqkmdmX8zn60N0PKCZ72yrAaXQ"
REDIRECT_URI  = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
SCOPE         = "com.intuit.quickbooks.accounting"
AUTH_URL      = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL     = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
ENV_PATH      = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")


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

    print("Opening browser for QBO SANDBOX authorization...")
    print("  >>> When the company picker appears, choose the company labelled [SANDBOX].")
    print(f"\nIf browser doesn't open, go to:\n{url}\n")
    webbrowser.open(url)

    print("=" * 60)
    print("After authorization, copy the FULL redirect URL from your")
    print("browser's address bar and paste it below.")
    print("=" * 60)
    callback_url = input("\nPaste the redirect URL here: ").strip()

    parsed = urllib.parse.urlparse(callback_url)
    qs = urllib.parse.parse_qs(parsed.query)

    if qs.get("state", [None])[0] != csrf_state:
        print("ERROR: CSRF state mismatch — aborting for safety.")
        return
    if qs.get("error"):
        print(f"ERROR: {qs['error'][0]} — {qs.get('error_description', [''])[0]}")
        return

    auth_code = qs.get("code", [None])[0]
    realm_id  = qs.get("realmId", [None])[0]
    if not auth_code or not realm_id:
        print("ERROR: Could not extract auth code or realm ID from URL.")
        print(f"  code: {auth_code}")
        print(f"  realmId: {realm_id}")
        return

    print(f"\nGot auth code. Sandbox realm ID: {realm_id}")

    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(TOKEN_URL, headers={
        "Authorization": f"Basic {creds}",
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
    print(f"Access token : {access_token[:30]}...")
    print(f"Refresh token: {refresh_token[:30]}...")
    print(f"Realm ID     : {realm_id}")

    # Update .traxis.env — only the SANDBOX keys, leave production alone
    lines = ENV_PATH.read_text().splitlines()
    keep = [ln for ln in lines
            if not ln.startswith("QBO_SANDBOX_REFRESH_TOKEN=")
            and not ln.startswith("QBO_SANDBOX_REALM_ID=")]
    keep.append(f"QBO_SANDBOX_REFRESH_TOKEN={refresh_token}")
    keep.append(f"QBO_SANDBOX_REALM_ID={realm_id}")
    ENV_PATH.write_text("\n".join(keep).rstrip() + "\n")
    print(f"\nSandbox credentials saved to {ENV_PATH}")
    print("Production QBO_REFRESH_TOKEN / QBO_REALM_ID untouched.")
    print("\nTo switch the running ingest to sandbox, set QBO_ENVIRONMENT=sandbox in .traxis.env.")


if __name__ == "__main__":
    main()
