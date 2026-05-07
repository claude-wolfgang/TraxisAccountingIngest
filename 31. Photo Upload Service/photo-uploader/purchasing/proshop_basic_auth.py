"""Basic-auth session wrapper for ProShop GraphQL API.

Wraps /api/beginsession → token (query-param auth) → /api/endsession.

Why basic auth: bypasses OAuth's acceptNewRecord gate (proven 2026-05-06
for addCustomerPo and addPurchaseOrder). Service user auth_010 was deleted
2026-05-06; the AccountingConnector OAuth client now maps to nothing.

Session token expires ~300s of inactivity. execute() retries once on 401
by re-running beginsession.

Shared between P31 (purchasing) and P27 (accounting ingest, basic-auth
migration in P27 Next Steps). Build once; import from both.
"""
from __future__ import annotations
import threading
import requests


class GraphQLError(Exception):
    def __init__(self, errors):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__("; ".join(messages))


class BasicAuthSession:
    """Thread-safe ProShop basic-auth session with auto-refresh on 401."""

    def __init__(self, base_url, username, password, scope, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.gql_url = f"{self.base_url}/api/graphql"
        self.begin_url = f"{self.base_url}/api/beginsession"
        self.end_url = f"{self.base_url}/api/endsession"
        # ProShop expects a full email username; .traxis.env may store the bare local part.
        self.username = username if "@" in username else f"{username}@traxismfg.com"
        self.password = password
        # /api/beginsession wants space-delimited scope; .traxis.env uses '+'.
        self.scope = scope.replace("+", " ")
        self.timeout = timeout
        self._token = None
        self._lock = threading.Lock()

    def _refresh_locked(self):
        r = requests.post(
            self.begin_url,
            headers={"Content-Type": "application/json"},
            json={"username": self.username, "password": self.password,
                  "scope": self.scope},
            timeout=self.timeout,
        )
        r.raise_for_status()
        token = r.json().get("authorizationResult", {}).get("token")
        if not token:
            raise RuntimeError(f"beginsession returned no token: {r.text[:200]}")
        self._token = token

    def _ensure_token(self):
        if self._token is None:
            with self._lock:
                if self._token is None:
                    self._refresh_locked()

    def execute(self, query, variables=None):
        """Run a GraphQL operation. Retries once on 401 (session expired)."""
        self._ensure_token()
        payload = {"query": query, "variables": variables or {}}
        for attempt in range(2):
            r = requests.post(
                self.gql_url,
                params={"token": self._token},
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            if r.status_code == 401 and attempt == 0:
                with self._lock:
                    self._refresh_locked()
                continue
            r.raise_for_status()
            body = r.json()
            if "errors" in body and not body.get("data"):
                raise GraphQLError(body["errors"])
            return body
        raise RuntimeError("execute() exhausted retries")

    def close(self):
        if self._token is None:
            return
        try:
            requests.get(self.end_url, params={"token": self._token},
                         timeout=self.timeout)
        except requests.RequestException:
            pass
        self._token = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
