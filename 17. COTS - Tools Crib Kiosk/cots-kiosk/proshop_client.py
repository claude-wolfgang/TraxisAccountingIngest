import time
import threading
import requests


class ProShopClient:
    """ProShop ERP GraphQL client with OAuth token management."""

    CACHE_TTL = 120  # seconds — re-fetch after 2 minutes

    # Fields to request when querying COTS items
    COTS_FIELDS = """
        otsId number aka type subclass description location
        quantity inventoryQuantity material thread od length units
        isSerialized minimumQuantityOnHand minReorderPoint
        partPlainText createdTime lastModifiedTime
        leastAmountToOrder suggestedMaximumQuantity
    """

    COTS_DETAIL_FIELDS = COTS_FIELDS + """
        adhesiveType amps application bearingType bondType coating
        connectorType cureType driveType gage hardness hardnessScale
        headType height idThreadLength idThreadSize insertIDThread
        insertODThread insertType internalDiameter lockingElement
        materialSpec mountingType oal odSize ohms pinStyle powerSupply
        purchasingNotes reliefType rpm sealed shoulderDiameter
        shoulderThickness taxType threadLength throwDistance volts
        wallThickness watts width descriptionForSales
    """

    def __init__(self, graphql_url, token_url, client_id, client_secret, scope):
        self.graphql_url = graphql_url
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._token = None
        self._token_obtained_at = 0
        self._token_expires_in = 86400  # default 24h
        self._lock = threading.Lock()
        self._entity_cache = {}
        self._cache_lock = threading.Lock()

    def _ensure_token(self):
        now = time.time()
        if self._token and now < (self._token_obtained_at + self._token_expires_in - 300):
            return
        with self._lock:
            # Double-check after acquiring lock
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
        # If 401, try refreshing token once
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

    # ── Cache Helpers ────────────────────────────────────────────────────

    def _get_cached(self, key):
        with self._cache_lock:
            entry = self._entity_cache.get(key)
            if entry and (time.time() - entry[0]) < self.CACHE_TTL:
                return entry[1]
        return None

    def _set_cached(self, key, records):
        with self._cache_lock:
            self._entity_cache[key] = (time.time(), records)

    # ── COTS Queries ──────────────────────────────────────────────────────

    def _fetch_all_cots(self):
        """Fetch all COTS items and cache for fast local search."""
        cached = self._get_cached("all_cots")
        if cached is not None:
            return cached

        result = self._execute(f"""
            {{
                cotsItems(pageSize: 1000) {{
                    totalRecords
                    records {{ {self.COTS_FIELDS} }}
                }}
            }}
        """)
        records = result.get("data", {}).get("cotsItems", {}).get("records", [])
        self._set_cached("all_cots", records)
        return records

    def get_cots_items(self, search=None, page_size=100, page_start=0):
        """Fetch COTS items with local multi-field search and pagination."""
        all_records = self._fetch_all_cots()

        if search:
            q = search.lower()
            q_digits = "".join(c for c in q if c.isdigit()).lstrip("0")
            filtered = []
            for r in all_records:
                ots_id = (r.get("otsId") or "").lower()
                number = str(r.get("number") or "").lower()
                aka = (r.get("aka") or "").lower()
                desc = (r.get("description") or "").lower()
                location = (r.get("location") or "").lower()
                item_type = (r.get("type") or "").lower()
                subclass = (r.get("subclass") or "").lower()
                searchable = f"{ots_id} {number} {aka} {desc} {location} {item_type} {subclass}"
                num_digits = "".join(c for c in number if c.isdigit()).lstrip("0")
                if q in searchable or (q_digits and q_digits in num_digits):
                    filtered.append(r)
        else:
            filtered = all_records

        total = len(filtered)
        start = page_start * page_size if page_start else 0
        page_records = filtered[start:start + page_size]
        return {"totalRecords": total, "records": page_records}

    def get_cots_item(self, ots_id):
        result = self._execute(f"""
            query ($otsId: String!) {{
                cotsItem(otsId: $otsId) {{ {self.COTS_DETAIL_FIELDS} }}
            }}
        """, {"otsId": ots_id})
        return result.get("data", {}).get("cotsItem")

    def update_cots(self, ots_id, data):
        result = self._execute("""
            mutation ($otsId: String!, $data: UpdateCOTSInput!) {
                updateCOTS(otsId: $otsId, data: $data) {
                    otsId aka quantity inventoryQuantity minimumQuantityOnHand
                }
            }
        """, {"otsId": ots_id, "data": data})
        return result.get("data", {}).get("updateCOTS")

    def add_cots(self, data):
        result = self._execute("""
            mutation ($data: AddCOTSInput!) {
                addCOTS(data: $data) {
                    otsId aka type subclass description location quantity
                }
            }
        """, {"data": data})
        return result.get("data", {}).get("addCOTS")

    def delete_cots(self, ots_id):
        result = self._execute("""
            mutation ($otsId: String!) {
                deleteCOTS(otsId: $otsId)
            }
        """, {"otsId": ots_id})
        return result.get("data", {}).get("deleteCOTS")

    # ── COTS Inventory (via leftoverParts) ───────────────────────────────

    def cots_checkout(self, ots_id, quantity, work_order, employee=""):
        """Check out items: adds a negative leftoverParts entry with WO."""
        note = f"Checkout by {employee}" if employee else "Checkout via kiosk"
        result = self._execute("""
            mutation ($otsId: String!, $data: UpdateCOTSInput!) {
                updateCOTS(otsId: $otsId, data: $data) {
                    otsId quantity inventoryQuantity
                }
            }
        """, {
            "otsId": ots_id,
            "data": {
                "leftoverParts": [{
                    "data": {
                        "quantity": -abs(quantity),
                        "workOrderOut": work_order,
                        "note": note,
                    }
                }]
            }
        })
        return result.get("data", {}).get("updateCOTS")

    def cots_checkin(self, ots_id, quantity, ref_type, ref_number, employee=""):
        """Check in items: adds a positive leftoverParts entry with WO or PO."""
        note = f"Return by {employee}" if employee else "Return via kiosk"
        entry_data = {
            "quantity": abs(quantity),
            "note": note,
        }
        if ref_type == "po":
            entry_data["purchaseOrderIn"] = ref_number
        else:
            entry_data["workOrder"] = ref_number
        result = self._execute("""
            mutation ($otsId: String!, $data: UpdateCOTSInput!) {
                updateCOTS(otsId: $otsId, data: $data) {
                    otsId quantity inventoryQuantity
                }
            }
        """, {
            "otsId": ots_id,
            "data": {
                "leftoverParts": [{
                    "data": entry_data
                }]
            }
        })
        return result.get("data", {}).get("updateCOTS")

    # ── Users ─────────────────────────────────────────────────────────────

    def get_users(self):
        result = self._execute(f"""
            {{
                users(pageSize: 200) {{
                    records {{
                        id firstName lastName isActive
                    }}
                }}
            }}
        """)
        records = result.get("data", {}).get("users", {}).get("records", [])
        # Filter active users, exclude system accounts
        excluded = {"system user", "system agent", "system", "api"}
        return [
            u for u in records
            if u.get("isActive")
            and u.get("firstName", "").lower() not in excluded
            and u.get("lastName", "").lower() not in excluded
        ]

    # ── Clock Punch ─────────────────────────────────────────────────────

    def get_clocked_in_ids(self):
        """Return set of user IDs currently clocked in."""
        result = self._execute("""
            {
                clockPunch {
                    latestClockPunches(pageSize: 200) {
                        records { operator inOrOut }
                    }
                }
            }
        """)
        records = (result.get("data", {})
                   .get("clockPunch", {})
                   .get("latestClockPunches", {})
                   .get("records", []))
        return {
            r["operator"]
            for r in records
            if r.get("inOrOut", "").lower() == "in"
        }

    # ── Health Check ──────────────────────────────────────────────────────

    def check_health(self):
        try:
            self._ensure_token()
            result = self._execute("{ cotsItems(pageSize: 1) { totalRecords } }")
            total = result.get("data", {}).get("cotsItems", {}).get("totalRecords", 0)
            return {
                "api_reachable": True,
                "token_valid": True,
                "total_cots_items": total,
                "token_age_seconds": int(time.time() - self._token_obtained_at),
            }
        except Exception as e:
            return {
                "api_reachable": False,
                "token_valid": self._token is not None,
                "error": str(e),
            }


class GraphQLError(Exception):
    def __init__(self, errors):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__("; ".join(messages))
