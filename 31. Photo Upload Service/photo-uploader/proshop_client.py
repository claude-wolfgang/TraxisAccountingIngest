"""Photo Upload Service — ProShop GraphQL client.

Adapted from P22 tool-kiosk proshop_client.py. Provides entity search
queries for work orders, tools, equipment, parts, and COTS items.

ProShop's StringQueryInput only supports: exactly, in, not — no substring
search. So we fetch broader sets and filter in Python, with a TTL cache
to avoid redundant API calls during rapid typing.
"""

import time
import threading
import requests

import config


class GraphQLError(Exception):
    def __init__(self, errors):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__("; ".join(messages))


class ProShopClient:
    """ProShop ERP GraphQL client with OAuth token management."""

    CACHE_TTL = 120  # seconds — re-fetch entity lists after 2 minutes

    def __init__(self):
        self.graphql_url = config.PROSHOP_GRAPHQL_URL
        self.token_url = config.PROSHOP_TOKEN_URL
        self.client_id = config.PROSHOP_CLIENT_ID
        self.client_secret = config.PROSHOP_CLIENT_SECRET
        self.scope = config.PROSHOP_SCOPE
        self.base_url = config.PROSHOP_BASE_URL
        self._token = None
        self._token_obtained_at = 0
        self._token_expires_in = 86400
        self._lock = threading.Lock()
        # Entity cache: {entity_type: (timestamp, records)}
        self._entity_cache = {}
        self._cache_lock = threading.Lock()

    def _ensure_token(self):
        now = time.time()
        if self._token and now < (self._token_obtained_at + self._token_expires_in - 300):
            return
        with self._lock:
            now = time.time()
            if self._token and now < (self._token_obtained_at + self._token_expires_in - 300):
                return
            self._refresh_token()

    def _refresh_token(self):
        resp = requests.post(self.token_url, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_obtained_at = time.time()
        self._token_expires_in = data.get("expires_in", 86400)

    def _execute(self, query, variables=None):
        self._ensure_token()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = requests.post(
            self.graphql_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code == 401:
            self._refresh_token()
            resp = requests.post(
                self.graphql_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body and not body.get("data"):
            raise GraphQLError(body["errors"])
        return body

    # ── Cache helpers ─────────────────────────────────────────────────────

    def _get_cached(self, key):
        with self._cache_lock:
            entry = self._entity_cache.get(key)
            if entry and (time.time() - entry[0]) < self.CACHE_TTL:
                return entry[1]
        return None

    def _set_cached(self, key, records):
        with self._cache_lock:
            self._entity_cache[key] = (time.time(), records)

    # ── Fetch + Filter Methods ────────────────────────────────────────────

    def _fetch_work_orders(self):
        """Fetch all active/queued/scheduled work orders."""
        cached = self._get_cached("workorders")
        if cached is not None:
            return cached

        all_records = []
        for status in ["Active", "Queued", "Scheduled"]:
            try:
                result = self._execute("""
                    query ($status: String!) {
                        workOrders(
                            pageSize: 500,
                            query: { status: { exactly: $status } }
                        ) {
                            records {
                                workOrderNumber status partPlainText
                                quantityOrdered
                            }
                        }
                    }
                """, {"status": status})
                records = result.get("data", {}).get("workOrders", {}).get("records", [])
                all_records.extend(records)
            except Exception:
                pass
        self._set_cached("workorders", all_records)
        return all_records

    def search_work_orders(self, query_text):
        """Search work orders by number or part name (substring match in Python)."""
        records = self._fetch_work_orders()
        q = query_text.lower()
        matches = []
        for r in records:
            wo_num = r.get("workOrderNumber") or ""
            part = r.get("partPlainText") or ""
            if q in wo_num.lower() or q in part.lower():
                matches.append({
                    "id": wo_num,
                    "name": part,
                    "detail": f"Qty: {r.get('quantityOrdered', '?')} | {r.get('status', '')}",
                    "proshop_url": f"{self.base_url}/workorders/{wo_num}",
                })
        return matches[:20]

    def _fetch_tools(self):
        """Fetch all tools from the tool library."""
        cached = self._get_cached("tools")
        if cached is not None:
            return cached

        result = self._execute("""
            {
                tools(pageSize: 1000) {
                    records { toolNumber description }
                }
            }
        """)
        records = result.get("data", {}).get("tools", {}).get("records", [])
        self._set_cached("tools", records)
        return records

    def search_tools(self, query_text):
        """Search tools by number or description (substring match in Python)."""
        records = self._fetch_tools()
        q = query_text.lower()
        matches = []
        for r in records:
            tn = r.get("toolNumber") or ""
            desc = r.get("description") or ""
            if q in tn.lower() or q in desc.lower():
                matches.append({
                    "id": tn,
                    "name": desc,
                    "detail": "",
                    "proshop_url": f"{self.base_url}/tools/{tn}",
                })
        return matches[:20]

    def _fetch_parts(self):
        """Fetch parts. Note: parts filter is known-broken in ProShop API."""
        cached = self._get_cached("parts")
        if cached is not None:
            return cached

        try:
            result = self._execute("""
                {
                    parts(pageSize: 500) {
                        records { partNumber partName }
                    }
                }
            """)
            records = result.get("data", {}).get("parts", {}).get("records", [])
        except Exception:
            records = []
        self._set_cached("parts", records)
        return records

    def search_parts(self, query_text):
        """Search parts by number or name (substring match in Python)."""
        records = self._fetch_parts()
        q = query_text.lower()
        matches = []
        for r in records:
            pn = r.get("partNumber") or ""
            name = r.get("partName") or ""
            if q in pn.lower() or q in name.lower():
                matches.append({
                    "id": pn,
                    "name": name,
                    "detail": "",
                    "proshop_url": f"{self.base_url}/parts/{pn}",
                })
        return matches[:20]

    def get_work_order_ops(self, wo_number):
        """Fetch operations for a specific work order."""
        result = self._execute("""
            query ($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber partPlainText
                    ops(pageSize: 50) {
                        records {
                            operationNumber
                            workCenterPlainText
                            partOperation {
                                operationDescription
                            }
                        }
                    }
                }
            }
        """, {"woNumber": wo_number})
        wo = (result.get("data") or {}).get("workOrder")
        if not wo:
            return []
        ops = (wo.get("ops") or {}).get("records", [])
        return [
            {
                "opNumber": op["operationNumber"],
                "description": (op.get("partOperation") or {}).get("operationDescription", ""),
                "workCenter": op.get("workCenterPlainText") or "",
            }
            for op in ops
        ]

    def get_work_order_detail(self, wo_number):
        """Fetch part number, customer, and op list for a work order.

        Needed to construct written description URLs:
        {BASE_URL}/procnc/parts/{customer}/{part_number}$formName=writtenDescription&opId={op_number}
        """
        result = self._execute("""
            query ($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    partPlainText
                    part { partNumber partName proshopUrl }
                    ops(pageSize: 50) {
                        records {
                            operationNumber
                            workCenterPlainText
                            partOperation {
                                operationDescription
                            }
                        }
                    }
                }
            }
        """, {"woNumber": wo_number})
        wo = (result.get("data") or {}).get("workOrder")
        if not wo:
            return None
        part = wo.get("part") or {}
        part_number = part.get("partNumber") or wo.get("partPlainText", "")
        # Extract customer prefix from part's proshopUrl or part number
        part_url = part.get("proshopUrl") or ""
        if "/parts/" in part_url:
            # URL: .../parts/R2S1/R2S1-10020 → customer = R2S1
            segments = part_url.split("/parts/")[1].split("/")
            customer = segments[0] if len(segments) >= 2 else ""
        else:
            customer = part_number.split("-")[0] if "-" in part_number else part_number
        ops = (wo.get("ops") or {}).get("records", [])
        return {
            "workOrderNumber": wo.get("workOrderNumber", ""),
            "partNumber": part_number,
            "partPlainText": wo.get("partPlainText", ""),
            "customerName": customer,
            "partUrl": part_url,
            "ops": [
                {
                    "opNumber": op["operationNumber"],
                    "description": (op.get("partOperation") or {}).get("operationDescription", ""),
                    "workCenter": op.get("workCenterPlainText") or "",
                }
                for op in ops
            ],
        }

    def search_equipment(self, query_text):
        """Equipment search — returns empty (API requires tool param, not a list query).

        Operators can type the equipment ID/name manually; it will be stored
        even without API validation.
        """
        return []

    def search_cots(self, query_text):
        """COTS search — requires 'ots' scope which is not in current client.

        Operators can type the COTS ID manually.
        """
        return []

    def search_entity(self, entity_type, query_text):
        """Dispatch search to the appropriate method based on entity_type."""
        dispatch = {
            "workorder": self.search_work_orders,
            "tool": self.search_tools,
            "equipment": self.search_equipment,
            "part": self.search_parts,
            "fixture": self.search_parts,  # fixtures are ProShop parts
            "cots": self.search_cots,
        }
        method = dispatch.get(entity_type)
        if not method:
            return []
        return method(query_text)

    # ── Health Check ──────────────────────────────────────────────────────

    def check_health(self):
        try:
            self._ensure_token()
            return {
                "api_reachable": True,
                "token_valid": True,
                "token_age_seconds": int(time.time() - self._token_obtained_at),
            }
        except Exception as e:
            return {
                "api_reachable": False,
                "token_valid": self._token is not None,
                "error": str(e),
            }
