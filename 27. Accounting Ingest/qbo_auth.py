"""
QBO OAuth2 Authorization Helper
Run this ONCE to authorize the app against your Traxis QBO company.
Stores the refresh token + realm ID to .traxis.env automatically.
"""

import webbrowser
import urllib.parse
import http.server
import threading
import requests
import base64
import json
from pathlib import Path

CLIENT_ID     = "ABUzGC136n1xBLRxJoanvwymVg8l61yOxgrnG8ZecQBrHL7nM5"
CLIENT_SECRET = "qeiAtzuJKUmuXOYIbALlnKWwUdnjNKDlddFaO5Hs"
REDIRECT_URI  = "http://localhost:8085/callback"
SCOPE         = "com.intuit.quickbooks.accounting"
AUTH_URL      = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL     = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
ENV_PATH      = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")

import secrets as _secrets

auth_code = None
realm_id  = None
csrf_state = None
done      = threading.Event()

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, realm_id
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # CSRF check — verify state matches what we sent
        returned_state = params.get("state", [None])[0]
        if returned_state != csrf_state:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"<h2>CSRF error: state mismatch. Authorization rejected.</h2>")
            print("ERROR: CSRF state mismatch — possible forgery. Aborting.")
            done.set()
            return

        # Check for error response from Intuit
        if params.get("error"):
            self.send_response(400)
            self.end_headers()
            err = params["error"][0]
            desc = params.get("error_description", [""])[0]
            self.wfile.write(f"<h2>Authorization error: {err}</h2><p>{desc}</p>".encode())
            print(f"ERROR: Intuit returned error: {err} — {desc}")
            done.set()
            return

        auth_code = params.get("code", [None])[0]
        realm_id  = params.get("realmId", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
        done.set()

    def log_message(self, *args):
        pass  # suppress server logs

def main():
    global csrf_state
    csrf_state = _secrets.token_urlsafe(32)

    # Start local callback server
    server = http.server.HTTPServer(("localhost", 8085), CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    # Build auth URL with random CSRF state
    params = {
        "client_id":     CLIENT_ID,
        "response_type": "code",
        "scope":         SCOPE,
        "redirect_uri":  REDIRECT_URI,
        "state":         csrf_state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("Opening browser for QBO authorization...")
    print(f"If browser doesn't open, go to:\n{url}\n")
    webbrowser.open(url)

    # Wait for callback
    done.wait(timeout=120)
    server.shutdown()

    if not auth_code or not realm_id:
        print("ERROR: Authorization timed out or failed.")
        return

    print(f"Got auth code. Realm ID: {realm_id}")

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

    # Append to .traxis.env
    env_text = ENV_PATH.read_text()
    new_lines = f"""
# QuickBooks Online API
QBO_CLIENT_ID={CLIENT_ID}
QBO_CLIENT_SECRET={CLIENT_SECRET}
QBO_REALM_ID={realm_id}
QBO_REFRESH_TOKEN={refresh_token}
"""
    # Remove any existing QBO lines first
    filtered = "\n".join(
        line for line in env_text.splitlines()
        if not line.startswith("QBO_")
    )
    ENV_PATH.write_text(filtered.rstrip() + "\n" + new_lines)
    print(f"\nCredentials saved to {ENV_PATH}")
    print("\nQBO authorization complete. You can now run the main app.")

if __name__ == "__main__":
    main()
