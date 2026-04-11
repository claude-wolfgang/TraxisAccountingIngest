"""ProShop API client for querying machine pocket layouts.

Uses urllib.request (no external dependencies) for Fusion 360 Python compatibility.
"""

import json
import ssl
import time
import os
import urllib.request
import urllib.parse


# Default ProShop endpoints
DEFAULT_GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
DEFAULT_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"

# Credentials from .traxis.env
ENV_FILE_LOCAL = os.path.join(os.path.expanduser("~"), ".traxis.env")
ENV_FILE_SHARED = os.path.join(
    os.path.expanduser("~"),
    "Dropbox", "MACHINE COMM Traxis", "Keys", ".traxis.env"
)


def _load_env():
    """Load credentials from .traxis.env file."""
    for path in [ENV_FILE_LOCAL, ENV_FILE_SHARED]:
        if os.path.exists(path):
            env = {}
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
            return env
    return {}


def _get_ssl_context():
    """Create SSL context with fallback for ProShop's certificate."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        # Fallback: disable verification (ProShop has known SSL issues from Fusion)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


class PocketClient:
    """Minimal ProShop GraphQL client for pocket queries."""

    def __init__(self):
        env = _load_env()
        self.graphql_url = env.get("PROSHOP_GRAPHQL_URL", DEFAULT_GRAPHQL_URL)
        self.token_url = env.get("PROSHOP_TOKEN_URL", DEFAULT_TOKEN_URL)
        self.client_id = env.get("PROSHOP_CLIENT_ID", "BA16-EFAF-B154")
        self.client_secret = env.get("PROSHOP_CLIENT_SECRET", "")
        self.scope = env.get("PROSHOP_SCOPE", "toolpots:r+tools:r+workorders:r+parts:r")
        self._token = None
        self._token_obtained_at = 0
        self._ssl_ctx = _get_ssl_context()

    def _ensure_token(self):
        now = time.time()
        if self._token and now < (self._token_obtained_at + 82800):  # 23h
            return
        self._refresh_token()

    def _refresh_token(self):
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }).encode("utf-8")
        req = urllib.request.Request(self.token_url, data=data)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        resp = urllib.request.urlopen(req, timeout=15, context=self._ssl_ctx)
        body = json.loads(resp.read().decode("utf-8"))
        self._token = body["access_token"]
        self._token_obtained_at = time.time()

    def _execute(self, query, variables=None):
        self._ensure_token()
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        req = urllib.request.Request(self.graphql_url, data=payload)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=30, context=self._ssl_ctx)
        body = json.loads(resp.read().decode("utf-8"))
        if "errors" in body and not body.get("data"):
            raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body

    def get_machine_pockets(self, pot_id):
        """Query pockets for a work cell. Returns {pocket_number: {tool_number, out_of_holder, holder}}."""
        result = self._execute("""
            query ($potId: String!) {
                workCell(potId: $potId) {
                    potId numberOfPockets
                    pockets(pageSize: 100) {
                        records {
                            legacyId toolPlainText outOfHolder holder
                        }
                    }
                }
            }
        """, {"potId": pot_id})
        wc = (result.get("data") or {}).get("workCell")
        if not wc:
            return {}
        pockets = (wc.get("pockets") or {}).get("records", [])
        pocket_map = {}
        for i, p in enumerate(pockets):
            pocket_num = p.get("legacyId") or (i + 1)
            tool_text = (p.get("toolPlainText") or "").strip()
            if tool_text:
                pocket_map[pocket_num] = {
                    "tool_number": tool_text,
                    "out_of_holder": p.get("outOfHolder"),
                    "holder": (p.get("holder") or "").strip(),
                }
        return pocket_map

    def get_machines(self):
        """Return list of active work cells (machines) with their potIds."""
        result = self._execute("""
            query {
                workCells(pageSize: 50) {
                    records {
                        workCellId name potId type isActive
                    }
                }
            }
        """)
        wcs = (result.get("data") or {}).get("workCells", {}).get("records", [])
        return [wc for wc in wcs if wc.get("isActive")]
