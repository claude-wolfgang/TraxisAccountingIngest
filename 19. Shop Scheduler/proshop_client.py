import time
import threading
import requests


class ProShopClient:
    """ProShop ERP GraphQL client with OAuth token management.
    Adapted from COTS Kiosk pattern for scheduler use."""

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

    # ── Work Orders ───────────────────────────────────────────────────────

    def get_work_orders(self, status="active", page_size=200, page_start=0):
        result = self._execute("""
            query ($pageSize: Int, $pageStart: Int, $query: WorkOrderQuery) {
                workOrders(pageSize: $pageSize, pageStart: $pageStart, query: $query) {
                    totalRecords
                    records {
                        workOrderNumber partPlainText
                        dueDate quantityOrdered qtyComplete
                        status deliverypriority
                        partStockStatuses(pageSize: 5) {
                            records {
                                material partStockType psPONumberPlainText
                                psPONumber { received orderStatus }
                            }
                        }
                    }
                }
            }
        """, {
            "pageSize": page_size,
            "pageStart": page_start,
            "query": {"status": {"exactly": status}} if status else None
        })
        return (result.get("data") or {}).get("workOrders", {"totalRecords": 0, "records": []})

    def get_work_order(self, wo_number):
        result = self._execute("""
            query ($workOrderNumber: String!) {
                workOrder(workOrderNumber: $workOrderNumber) {
                    workOrderNumber partPlainText
                    dueDate quantityOrdered qtyComplete
                    status deliverypriority
                }
            }
        """, {"workOrderNumber": wo_number})
        return (result.get("data") or {}).get("workOrder")

    # ── Operations ────────────────────────────────────────────────────────

    def get_operations(self, wo_number):
        result = self._execute("""
            query ($workOrderNumber: String!) {
                workOrder(workOrderNumber: $workOrderNumber) {
                    quantityOrdered
                    ops {
                        records {
                            operationNumber operationDescription operationType
                            workCenterPlainText
                            minutesPerPart runTime setupTime totalCycleTime
                            perOpQtyComplete isOpComplete
                            partOperation {
                                operationDescription
                            }
                        }
                    }
                }
            }
        """, {"workOrderNumber": wo_number})
        wo = (result.get("data") or {}).get("workOrder")
        if wo:
            qty = wo.get("quantityOrdered", 0)
            ops = wo.get("ops", {}).get("records", [])
            # Attach WO qty to each op for duration calculation
            for op in ops:
                op["_woQty"] = qty
            return ops
        return []

    # ── Work Cells (Machines) ─────────────────────────────────────────────

    def get_work_cells(self, page_size=100):
        result = self._execute("""
            query ($pageSize: Int) {
                workCells(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workCellId name type isActive
                    }
                }
            }
        """, {"pageSize": page_size})
        return (result.get("data") or {}).get("workCells", {"totalRecords": 0, "records": []})

    # ── Writeback: Update Operation Progress ──────────────────────────────

    def update_operation_qty(self, wo_number, op_number, qty_complete):
        result = self._execute("""
            mutation ($woNumber: String, $opNumber: String, $opDefinition: updateWorkOrderOperationInput) {
                updateWorkOrderOperation(woNumber: $woNumber, opNumber: $opNumber, opDefinition: $opDefinition)
            }
        """, {
            "woNumber": wo_number,
            "opNumber": str(op_number),
            "opDefinition": {"perOpQtyComplete": qty_complete}
        })
        return (result.get("data") or {}).get("updateWorkOrderOperation")

    def complete_operation(self, wo_number, op_number):
        result = self._execute("""
            mutation ($woNumber: String, $opNumber: String, $opDefinition: updateWorkOrderOperationInput) {
                updateWorkOrderOperation(woNumber: $woNumber, opNumber: $opNumber, opDefinition: $opDefinition)
            }
        """, {
            "woNumber": wo_number,
            "opNumber": str(op_number),
            "opDefinition": {"isOpComplete": True}
        })
        return (result.get("data") or {}).get("updateWorkOrderOperation")

    # ── Vendor POs (Material Readiness) ──────────────────────────────────

    def get_outstanding_vpos(self, page_size=500):
        """Query outstanding material vendor POs to check material readiness."""
        result = self._execute("""
            query ($pageSize: Int, $query: VendorPOQuery) {
                vendorPOs(pageSize: $pageSize, query: $query) {
                    totalRecords
                    records {
                        poType
                        poItems(pageSize: 100) {
                            records {
                                workOrderPlainText receivedDate
                                description
                            }
                        }
                    }
                }
            }
        """, {
            "pageSize": page_size,
            "query": {"poType": {"exactly": "Material"}}
        })
        return (result.get("data") or {}).get("vendorPOs", {"totalRecords": 0, "records": []})

    # ── Work Cell Pockets (Machine Tool Layout) ──────────────────────────

    def get_work_cell_pockets(self, pot_id):
        """Query all pockets for a ProShop work cell by potId (e.g., 'Mill-2')."""
        result = self._execute("""
            query ($potId: String!) {
                workCell(potId: $potId) {
                    potId numberOfPockets
                    pockets(pageSize: 100) {
                        records {
                            legacyId toolPlainText outOfHolder
                            holder
                        }
                    }
                }
            }
        """, {"potId": pot_id})
        wc = (result.get("data") or {}).get("workCell")
        return wc

    # ── Operation Tool Requirements ──────────────────────────────────────

    def get_operation_tools(self, wo_number):
        """Query tool requirements for all ops on a WO via partOperation.tools.

        Returns {op_number: [tool_records]} dict.
        """
        result = self._execute("""
            query ($workOrderNumber: String!) {
                workOrder(workOrderNumber: $workOrderNumber) {
                    ops {
                        records {
                            operationNumber
                            partOperation {
                                tools(pageSize: 50) {
                                    records {
                                        tool { toolNumber description }
                                        holder outOfHolder sequenceNumber
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """, {"workOrderNumber": wo_number})
        wo = (result.get("data") or {}).get("workOrder")
        if not wo:
            return {}
        ops = (wo.get("ops") or {}).get("records", [])
        tools_by_op = {}
        for op in ops:
            op_num = op.get("operationNumber")
            if op_num is None:
                continue
            part_op = op.get("partOperation") or {}
            tools_data = (part_op.get("tools") or {}).get("records", [])
            if tools_data:
                tools_by_op[op_num] = tools_data
        return tools_by_op

    # ── Part Drawing ───────────────────────────────────────────────────────

    def get_part_drawing(self, wo_number):
        """Get the part drawing/file URL for a work order.

        Checks part.partFiles.partfile first (primary drawing),
        then falls back to workOrderFiles for any attached file.
        Returns {title, fileUrl} or None.
        """
        result = self._execute("""
            query ($workOrderNumber: String!) {
                workOrder(workOrderNumber: $workOrderNumber) {
                    part {
                        partFiles {
                            partfile {
                                title fileUrl
                            }
                        }
                    }
                    workOrderFiles(pageSize: 5) {
                        records {
                            title fileUrl
                        }
                    }
                }
            }
        """, {"workOrderNumber": wo_number})
        wo = (result.get("data") or {}).get("workOrder")
        if not wo:
            return None

        # Primary: part drawing
        part = wo.get("part") or {}
        part_files = part.get("partFiles") or {}
        partfile = part_files.get("partfile")
        if partfile and partfile.get("fileUrl"):
            return {"title": partfile.get("title", ""), "fileUrl": partfile["fileUrl"]}

        # Fallback: first WO-level file (setup sheet, drawing, etc.)
        wo_files = (wo.get("workOrderFiles") or {}).get("records", [])
        for f in wo_files:
            if f.get("fileUrl"):
                return {"title": f.get("title", ""), "fileUrl": f["fileUrl"]}

        return None

    # ── Health Check ──────────────────────────────────────────────────────

    def check_health(self):
        try:
            self._ensure_token()
            result = self._execute("""
                { workOrders(pageSize: 1, query: {status: {exactly: "active"}}) { totalRecords } }
            """)
            total = (result.get("data") or {}).get("workOrders", {}).get("totalRecords", 0)
            return {
                "api_reachable": True,
                "token_valid": True,
                "active_work_orders": total,
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
