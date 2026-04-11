"""
ProShop GraphQL client for Shop Hub.
Handles OAuth2 authentication and work order lookups.

Credentials loaded from C:\\Users\\TRAXIS\\.traxis.env
"""

import os
import time
import logging
import threading
from datetime import datetime
from pathlib import Path

import requests

log = logging.getLogger("ShopHub.ProShop")

TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"


def load_env_file():
    """Load .traxis.env credentials into os.environ (first found wins)."""
    search_paths = [
        Path(r"C:\Users\TRAXIS\.traxis.env"),
        Path.home() / ".traxis.env",
    ]
    for env_path in search_paths:
        if env_path.exists():
            log.info("Loading credentials from %s", env_path)
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value:
                            os.environ.setdefault(key, value)
            return True
    log.warning("No .traxis.env file found")
    return False


# GraphQL: fetch all WOs for a year with part info and operations
WO_LIST_QUERY = """
query($year: String!) {
  workOrders(filter: { year: $year }, pageSize: 500) {
    totalRecords
    records {
      workOrderNumber
      status
      partRev
      part {
        partNumber
        partName
      }
    }
  }
}
"""


class ProShopClient:
    """ProShop API client with token caching and WO lookup cache."""

    def __init__(self):
        load_env_file()
        self.client_id = os.environ.get("PROSHOP_CLIENT_ID", "")
        self.client_secret = os.environ.get("PROSHOP_CLIENT_SECRET", "")
        self.scope = os.environ.get("PROSHOP_SCOPE", "parts:rwdp+workorders:rwdp+users:r")
        self.session = requests.Session()
        self._token = None
        self._token_expires = 0.0
        # WO cache: part_number -> [wo_dict, ...]
        self._wo_cache: dict[str, list[dict]] = {}
        self._wo_cache_time = 0.0
        self._wo_cache_ttl = 300  # 5 minutes
        self._lock = threading.Lock()

    def _get_token(self) -> str | None:
        """Get or refresh OAuth2 access token."""
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token

        if not self.client_secret:
            log.error("PROSHOP_CLIENT_SECRET not set — cannot authenticate")
            return None

        try:
            resp = self.session.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires = now + expires_in
            log.info("ProShop token refreshed (expires in %ds)", expires_in)
            return self._token
        except Exception as e:
            log.error("Token error: %s", e)
            return None

    def _query(self, query: str, variables: dict | None = None) -> dict | None:
        """Execute a GraphQL query."""
        token = self._get_token()
        if not token:
            return None
        try:
            resp = self.session.post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables or {}},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                log.warning("GraphQL errors: %s", result["errors"])
            return result.get("data")
        except Exception as e:
            log.error("Query error: %s", e)
            return None

    def refresh_wo_cache(self):
        """Fetch all WOs for current year and index by part number."""
        year = str(datetime.now().year)
        log.info("Refreshing WO cache for year %s ...", year)
        data = self._query(WO_LIST_QUERY, {"year": year})
        if not data or "workOrders" not in data:
            log.error("Failed to fetch work orders")
            return

        records = data["workOrders"].get("records", [])
        index: dict[str, list[dict]] = {}
        for wo in records:
            part = wo.get("part") or {}
            pn = part.get("partNumber", "")
            if not pn:
                continue
            index.setdefault(pn, []).append({
                "workOrderNumber": wo.get("workOrderNumber", ""),
                "status": wo.get("status", ""),
                "partNumber": pn,
                "partName": part.get("partName", ""),
                "partRev": wo.get("partRev", ""),
            })

        with self._lock:
            self._wo_cache = index
            self._wo_cache_time = time.time()
        log.info("WO cache: %d parts, %d work orders", len(index), len(records))

    def lookup_part(self, part_number: str) -> list[dict]:
        """Look up active WOs for a part number. Returns empty list if not found.

        Matching strategy (first match wins):
        1. Exact match on internal PN
        2. Prefix match (base number without revision suffix)
        3. Suffix/contains match — strips customer prefix (e.g. ICO1-) from
           internal PNs and checks if the detected number appears as a
           trailing segment, with leading-zero tolerance.
           e.g. detected "2004" matches "ICO1-10-02004"
        """
        now = time.time()
        if now - self._wo_cache_time > self._wo_cache_ttl:
            self.refresh_wo_cache()

        with self._lock:
            # 1. Exact match
            results = list(self._wo_cache.get(part_number, []))

            if not results:
                # 2. Prefix match (base number without revision suffix)
                base = part_number.split("-")[0] if "-" in part_number else part_number
                for key in self._wo_cache:
                    if key == base or key.startswith(base + "-"):
                        results.extend(self._wo_cache[key])

            if not results:
                # 3. Suffix/contains match on internal PNs
                # Strip leading zeros for comparison: "2004" matches "02004"
                needle = part_number.lstrip("0")
                for key in self._wo_cache:
                    # Strip customer prefix (first segment before '-')
                    parts = key.split("-", 1)
                    tail = parts[1] if len(parts) > 1 else key
                    # Check if needle matches end of any dash-segment
                    tail_digits = tail.replace("-", "").lstrip("0")
                    if needle and tail_digits.endswith(needle):
                        results.extend(self._wo_cache[key])

        # Filter to active/in-process WOs
        active_statuses = {"active", "in process", "started"}
        return [wo for wo in results if wo.get("status", "").lower() in active_statuses]
