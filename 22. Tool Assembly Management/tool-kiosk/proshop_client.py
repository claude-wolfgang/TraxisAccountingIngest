"""
ProShop ERP GraphQL client — adapted from COTS kiosk.

Extends the base OAuth client with work cell pocket methods for
tool assembly management.
"""

import time
import threading
import requests


class ProShopClient:
    """ProShop ERP GraphQL client with OAuth token management."""

    def __init__(self, graphql_url, token_url, client_id, client_secret, scope):
        self.graphql_url = graphql_url
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._token = None
        self._token_obtained_at = 0
        self._token_expires_in = 86400
        self._lock = threading.Lock()

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

    # ── Users ─────────────────────────────────────────────────────────────

    def get_users(self):
        result = self._execute("""
            {
                users(pageSize: 200) {
                    records {
                        id firstName lastName isActive
                    }
                }
            }
        """)
        records = result.get("data", {}).get("users", {}).get("records", [])
        excluded = {"system user", "system agent", "system", "api"}
        return [
            u for u in records
            if u.get("isActive")
            and u.get("firstName", "").lower() not in excluded
            and u.get("lastName", "").lower() not in excluded
        ]

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

    # ── Work Cell Pockets ─────────────────────────────────────────────────

    def get_work_cell_pockets(self, pot_id):
        """Query all pockets for a ProShop work cell by potId (e.g., 'Mill-2')."""
        result = self._execute("""
            query ($potId: String!) {
                workCell(potId: $potId) {
                    potId numberOfPockets
                    pockets(pageSize: 100) {
                        records {
                            legacyId toolPlainText outOfHolder
                            toolWear offset radiusOffset radiusWear
                            holder glotPlainText
                        }
                    }
                }
            }
        """, {"potId": pot_id})
        wc = result.get("data", {}).get("workCell")
        if not wc:
            return None
        return wc

    def update_work_cell_pocket(self, pot_id, pocket_number, data):
        """Update a single pocket in a ProShop work cell.

        pot_id: work cell potId (e.g., 'Mill-2')
        pocket_number: integer pocket/T-number (1, 2, 3, ...)
        data: dict with WorkCellPocketDataInput fields:
              tool (String), outOfHolder (Float), holder (String),
              toolWear, offset, radiusOffset, radiusWear (all String),
              toolLifeNow, toolLifeWarning (String)
        """
        result = self._execute("""
            mutation ($potId: String!, $pockets: [WorkCellPocketRow!]!) {
                updateWorkCellPocket(potId: $potId, pockets: $pockets) {
                    potId
                    pockets(pageSize: 100) {
                        records { toolPlainText outOfHolder toolWear }
                    }
                }
            }
        """, {"potId": pot_id, "pockets": [{"pocketNumber": int(pocket_number), "data": data}]})
        return result.get("data", {}).get("updateWorkCellPocket")

    def clear_work_cell_pocket(self, pot_id, pocket_number):
        """Clear a pocket (remove tool assignment)."""
        return self.update_work_cell_pocket(pot_id, pocket_number, {
            "tool": "",
            "holder": "",
            "glot": "",
            "outOfHolder": 0.0,
            "toolWear": "",
            "offset": "",
            "radiusOffset": "",
            "radiusWear": "",
        })

    # ── Work Orders & Scheduling ──────────────────────────────────────────

    def get_work_orders_for_machine(self, work_center_name, statuses=None):
        """Get work orders whose current operation is assigned to a work center.

        work_center_name: ProShop potId like 'Mill-2' (matched against workCenterPlainText)
        statuses: list of WO statuses to include
        """
        if statuses is None:
            statuses = ["Active", "Queued", "Scheduled"]

        all_wos = []
        for status in statuses:
            try:
                result = self._execute("""
                    query ($status: String!) {
                        workOrders(
                            pageSize: 200,
                            query: { status: { exactly: $status } }
                        ) {
                            records {
                                workOrderNumber status partPlainText
                                quantityOrdered
                                ops(pageSize: 50) {
                                    records {
                                        operationNumber workCenterPlainText
                                    }
                                }
                            }
                        }
                    }
                """, {"status": status})
                all_wos.extend(result.get("data", {}).get("workOrders", {}).get("records", []))
            except Exception:
                pass

        # Filter: keep WOs where any operation matches the work center
        matched = []
        wc_lower = work_center_name.lower()
        for wo in all_wos:
            ops = (wo.get("ops") or {}).get("records", [])
            for op in ops:
                wc_text = (op.get("workCenterPlainText") or "").lower()
                if wc_lower in wc_text:
                    matched.append({
                        "woNumber": wo.get("workOrderNumber"),
                        "status": wo.get("status"),
                        "partNumber": wo.get("partPlainText"),
                        "quantity": wo.get("quantityOrdered"),
                        "operationNumber": op.get("operationNumber"),
                        "workCenter": op.get("workCenterPlainText"),
                    })
        return matched

    def get_sequence_detail_tools(self, wo_number, operation_number):
        """Get the tool list from a work order operation's part operation tools.

        wo_number: work order number (e.g., '26-0027')
        operation_number: operation number (e.g., 56)
        """
        result = self._execute("""
            query ($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    ops(pageSize: 50) {
                        records {
                            operationNumber
                            partOperation {
                                tools(pageSize: 50) {
                                    records {
                                        sequenceNumber
                                        tool { toolNumber description }
                                        holder outOfHolder
                                        sequenceDescription
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """, {"woNumber": wo_number})
        wo = (result.get("data") or {}).get("workOrder")
        if not wo:
            return []
        op_num = str(operation_number)
        for op in (wo.get("ops") or {}).get("records", []):
            if str(op.get("operationNumber")) == op_num:
                po = op.get("partOperation") or {}
                tools = (po.get("tools") or {}).get("records", [])
                # Normalize to flat tool records
                return [
                    {
                        "toolNumber": (t.get("tool") or {}).get("toolNumber", ""),
                        "toolDescription": (t.get("tool") or {}).get("description", ""),
                        "toolOOH": t.get("outOfHolder", ""),
                        "holder": t.get("holder", ""),
                        "sequenceNumber": t.get("sequenceNumber"),
                        "sequenceDescription": t.get("sequenceDescription", ""),
                    }
                    for t in tools
                ]
        return []

    # ── RTA (Rotating Tool Assembly) ─────────────────────────────────────

    def create_rta(self, tool_number, holder_type="", ooh="",
                   collet="", comment=""):
        """Create an RTA record in ProShop.

        Returns the full RTA record dict including the auto-assigned rtaNumber.
        """
        data = {"tool": tool_number, "status": "Active"}
        if holder_type:
            data["holder"] = holder_type
        if ooh:
            data["outOfHolder"] = str(ooh)
        if collet:
            data["collet"] = collet
        if comment:
            data["comment"] = comment

        result = self._execute("""
            mutation ($data: AddRTAInput!) {
                addRTA(data: $data) {
                    rtaNumber toolPlainText holder outOfHolder
                    colletPlainText status comment
                }
            }
        """, {"data": data})
        return result.get("data", {}).get("addRTA")

    def get_rta(self, rta_number):
        """Fetch a single RTA record by number."""
        result = self._execute("""
            query ($num: String!) {
                rta(rtaNumber: $num) {
                    rtaNumber toolPlainText holder outOfHolder
                    colletPlainText status comment
                }
            }
        """, {"num": rta_number})
        return result.get("data", {}).get("rta")

    def delete_rta(self, rta_number):
        """Delete an RTA record."""
        result = self._execute("""
            mutation ($num: String!) {
                deleteRTA(rtaNumber: $num)
            }
        """, {"num": rta_number})
        return result.get("data", {}).get("deleteRTA")

    def update_rta(self, rta_number, tool_number, holder_type="", ooh="",
                   collet="", comment=""):
        """Update an existing RTA record in ProShop.

        Uses the updateRTA mutation. Returns the updated RTA dict, or raises
        GraphQLError if the mutation doesn't exist.
        """
        data = {"tool": tool_number, "status": "Active"}
        if holder_type:
            data["holder"] = holder_type
        if ooh:
            data["outOfHolder"] = str(ooh)
        if collet:
            data["collet"] = collet
        if comment:
            data["comment"] = comment

        result = self._execute("""
            mutation ($num: String!, $data: UpdateRTAInput!) {
                updateRTA(rtaNumber: $num, data: $data) {
                    rtaNumber toolPlainText holder outOfHolder
                    colletPlainText status comment
                }
            }
        """, {"num": rta_number, "data": data})
        return result.get("data", {}).get("updateRTA")

    def update_rta_comment(self, rta_number, comment):
        """Update only the comment field on an existing RTA record."""
        result = self._execute("""
            mutation ($num: String!, $data: UpdateRTAInput!) {
                updateRTA(rtaNumber: $num, data: $data) {
                    rtaNumber comment
                }
            }
        """, {"num": rta_number, "data": {"comment": comment}})
        return result.get("data", {}).get("updateRTA")

    def update_or_recreate_rta(self, rta_number, tool_number, holder_type="",
                               ooh="", collet="", comment=""):
        """Update an RTA in place, falling back to delete+recreate.

        Returns (rta_dict, rta_number_str).  The rta_number may differ from
        the input if a recreate was needed.
        """
        # Try update first
        try:
            rta = self.update_rta(rta_number, tool_number,
                                  holder_type=holder_type, ooh=ooh,
                                  collet=collet, comment=comment)
            if rta:
                return rta, rta.get("rtaNumber", rta_number)
        except GraphQLError:
            pass  # mutation doesn't exist — fall through to recreate

        # Fallback: delete + recreate
        try:
            self.delete_rta(rta_number)
        except Exception:
            pass  # may already be gone
        rta = self.create_rta(tool_number, holder_type=holder_type, ooh=ooh,
                              collet=collet, comment=comment)
        new_num = rta.get("rtaNumber", rta_number) if rta else rta_number
        return rta, new_num

    # ── Tool Lookup ─────────────────────────────────────────────────────

    def get_all_tools(self, page_size=1000):
        """Fetch all tools from the ProShop tool library.

        Returns list of dicts with toolNumber, description, qtyInBin.
        """
        result = self._execute("""
            query ($pageSize: Int!) {
                tools(pageSize: $pageSize) {
                    records { toolNumber description qtyInBin }
                    totalRecords
                }
            }
        """, {"pageSize": page_size})
        data = result.get("data", {}).get("tools", {})
        return data.get("records", [])

    def get_tool_by_number(self, tool_number):
        """Look up a tool from the ProShop tool library by tool number."""
        result = self._execute("""
            query ($tn: String!) {
                tools(pageSize: 1, query: { toolNumber: { exactly: $tn } }) {
                    records { toolNumber description qtyInBin }
                }
            }
        """, {"tn": tool_number})
        records = result.get("data", {}).get("tools", {}).get("records", [])
        return records[0] if records else None

    def update_tool(self, tool_number, data):
        """Update a tool record in ProShop.

        tool_number: ProShop tool number (e.g., 'T-1234')
        data: dict with UpdateToolInput fields (e.g., qtyInBin)
        """
        result = self._execute("""
            mutation ($tn: String!, $data: UpdateToolInput!) {
                updateTool(toolNumber: $tn, data: $data) {
                    toolNumber qtyInBin
                }
            }
        """, {"tn": tool_number, "data": data})
        return result.get("data", {}).get("updateTool")

    def retire_tool_qty(self, tool_number, qty=1):
        """Decrement a tool's Qty in Bin by the specified amount.

        Queries current qtyInBin, subtracts qty (floor at 0), and updates.
        Returns the updated tool record or None if tool not found.
        """
        tool = self.get_tool_by_number(tool_number)
        if not tool:
            print(f"[WARN] retire_tool_qty: tool {tool_number} not found in ProShop")
            return None
        current_qty_str = tool.get("qtyInBin", "0") or "0"
        try:
            current_qty = int(float(current_qty_str))
        except (ValueError, TypeError):
            current_qty = 0
        new_qty = max(0, current_qty - qty)
        print(f"[INFO] retire_tool_qty: {tool_number} qty {current_qty} -> {new_qty}")
        return self.update_tool(tool_number, {"qtyInBin": str(new_qty)})

    # ── Health Check ──────────────────────────────────────────────────────

    def check_health(self):
        try:
            self._ensure_token()
            result = self._execute('{ workCell(potId: "Mill-2") { potId } }')
            wc = result.get("data", {}).get("workCell")
            return {
                "api_reachable": True,
                "token_valid": True,
                "work_cell_found": wc is not None,
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
