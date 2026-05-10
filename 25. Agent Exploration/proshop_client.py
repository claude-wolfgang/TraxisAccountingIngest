"""
ProShop ERP GraphQL client for the Data Quality Agent.
Adapted from Project 19 (Shop Scheduler) with additional queries
for data quality auditing.

Thread-safe OAuth 2.0 client credentials flow with auto-refresh.
"""

import time
import threading
import json
import requests


class GraphQLError(Exception):
    def __init__(self, errors):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__("; ".join(messages))


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

    def execute(self, query, variables=None):
        """Execute a GraphQL query. Returns parsed JSON body."""
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
            timeout=120,
        )
        # Auto-retry on 401 (expired token)
        if resp.status_code == 401:
            self._refresh_token()
            resp = requests.post(
                self.graphql_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body and not body.get("data"):
            raise GraphQLError(body["errors"])
        return body

    # ── Health Check ─────────────────────────────────────────────────────

    def check_health(self):
        """Quick connectivity and auth check."""
        try:
            self._ensure_token()
            result = self.execute("""
                { workOrders(pageSize: 1, query: {status: {exactly: "active"}}) { totalRecords } }
            """)
            total = (result.get("data") or {}).get("workOrders", {}).get("totalRecords", 0)
            return {
                "healthy": True,
                "active_work_orders": total,
                "token_age_seconds": int(time.time() - self._token_obtained_at),
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    # ── Work Orders (Full Audit Payload) ─────────────────────────────────

    def get_all_active_work_orders(self, page_size=100):
        """Fetch active WOs with scalar fields for audit. Smaller page size avoids timeout."""
        result = self.execute("""
            query ($pageSize: Int) {
                workOrders(pageSize: $pageSize, query: {status: {exactly: "active"}}) {
                    totalRecords
                    records {
                        workOrderNumber
                        partPlainText
                        status
                        dueDate
                        scheduledEndDate
                        quantityOrdered
                        qtyComplete
                        deliverypriority
                        earlyAsPossible
                        hoursCurrentTarget
                        hoursTotalSpent
                        programmingPercentComplete
                        planningPercentComplete
                        planningLevel
                        part {
                            partNumber
                            partDescription
                            family
                            customerPartNumber
                        }
                        ops {
                            records {
                                operationNumber
                                operationDescription
                                operationType
                                workCenterPlainText
                                minutesPerPart
                                runTime
                                setupTime
                                totalCycleTime
                                runTimeSpent
                                setupTimeSpent
                                percentComplete
                                perOpQtyComplete
                                isOpComplete
                                certifiedToRun
                                firstArticleComplete
                                preProcessingCheckComplete
                                breakdownComplete
                                scheduledStartDate
                            }
                        }
                    }
                }
            }
        """, {"pageSize": page_size})
        return (result.get("data") or {}).get("workOrders", {"totalRecords": 0, "records": []})

    def get_completed_work_orders(self, page_size=500):
        """Fetch completed/shipped/invoiced WOs for overrun analysis."""
        all_records = []
        for status in ["Complete", "Shipped", "Invoiced"]:
            result = self.execute("""
                query ($pageSize: Int, $query: WorkOrderQuery) {
                    workOrders(pageSize: $pageSize, query: $query) {
                        totalRecords
                        records {
                            workOrderNumber
                            partPlainText
                            status
                            dueDate
                            quantityOrdered
                            hoursCurrentTarget
                            hoursTotalSpent
                            part {
                                partNumber
                                family
                            }
                        }
                    }
                }
            """, {
                "pageSize": page_size,
                "query": {"status": {"exactly": status}},
            })
            wo_data = (result.get("data") or {}).get("workOrders", {})
            all_records.extend(wo_data.get("records", []))
        return all_records

    # ── Material / Stock Status ──────────────────────────────────────────

    def get_part_stock_statuses(self, part_number):
        """Get material stock info for a part (limited by scope)."""
        result = self.execute("""
            query ($partNumber: [String!]!) {
                parts(filter: {partNumber: $partNumber}) {
                    records {
                        partNumber
                        partStockStatuses {
                            records {
                                stockStatus
                                psETA
                                psActualETA
                                psQuantityOnHand
                                psQuantityOrdered
                            }
                        }
                    }
                }
            }
        """, {"partNumber": [part_number]})
        parts = (result.get("data") or {}).get("parts", {}).get("records", [])
        if parts:
            return (parts[0].get("partStockStatuses") or {}).get("records", [])
        return []

    # ── Work Cells ───────────────────────────────────────────────────────

    def get_work_cells(self, page_size=100):
        """Get all work cells (machines) for mapping."""
        result = self.execute("""
            query ($pageSize: Int) {
                workCells(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workCellId
                        name
                        type
                        isActive
                    }
                }
            }
        """, {"pageSize": page_size})
        return (result.get("data") or {}).get("workCells", {"totalRecords": 0, "records": []})

    # ── Single Work Order Lookup ─────────────────────────────────────────

    def get_work_order(self, wo_number):
        """Fetch a single work order by number with ops, hours, dates, part info."""
        result = self.execute("""
            query GetWorkOrder($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    status
                    dueDate
                    scheduledEndDate
                    quantityOrdered
                    qtyComplete
                    hoursCurrentTarget
                    hoursTotalSpent
                    programmingPercentComplete
                    planningPercentComplete
                    deliverypriority
                    earlyAsPossible
                    part {
                        partNumber
                        partDescription
                        family
                        customerPartNumber
                    }
                    ops {
                        records {
                            operationNumber
                            operationDescription
                            operationType
                            workCenterPlainText
                            isOpComplete
                            percentComplete
                            setupTime
                            runTime
                            setupTimeSpent
                            runTimeSpent
                            certifiedToRun
                            scheduledStartDate
                        }
                    }
                }
            }
        """, {"woNumber": wo_number})
        return (result.get("data") or {}).get("workOrder")

    def get_work_order_time_tracking(self, wo_number):
        """Fetch time tracking entries for a single work order."""
        result = self.execute("""
            query GetWorkOrderTime($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    status
                    hoursTotalSpent
                    runningTimeHoursActualLabor
                    setupTimeHoursActualLabel
                    timeTracking {
                        totalRecords
                        records {
                            operationNumber
                            timeIn
                            timeOut
                            spentDoing
                        }
                    }
                }
            }
        """, {"woNumber": wo_number})
        return (result.get("data") or {}).get("workOrder")

    def get_work_order_profitability(self, page_size=500):
        """Fetch profitability data for all work orders."""
        result = self.execute("""
            query GetProfitability($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    records {
                        workOrderNumber
                        status
                        partPlainText
                        profitability {
                            dlh
                            profit
                            profitMargin
                            totalCost
                        }
                    }
                }
            }
        """, {"pageSize": page_size})
        return (result.get("data") or {}).get("workOrders", {"records": []})

    # ── Part Queries ──────────────────────────────────────────────────────

    def get_part(self, part_number):
        """Fetch a single part by part number."""
        result = self.execute("""
            query GetPart($partNumber: [String!]!) {
                parts(filter: { partNumber: $partNumber }) {
                    records {
                        partNumber
                        partDescription
                        family
                        customerPartNumber
                    }
                }
            }
        """, {"partNumber": [part_number]})
        records = (result.get("data") or {}).get("parts", {}).get("records", [])
        return records[0] if records else None

    def get_part_operations(self, part_number):
        """Fetch a part with its full operations list (master routing)."""
        result = self.execute("""
            query GetPartOps($partNumber: [String!]!) {
                parts(filter: { partNumber: $partNumber }) {
                    records {
                        partNumber
                        partDescription
                        operations {
                            records {
                                opNumber
                                operationDescription
                                setupTime
                                runTime
                            }
                        }
                    }
                }
            }
        """, {"partNumber": [part_number]})
        records = (result.get("data") or {}).get("parts", {}).get("records", [])
        return records[0] if records else None

    # ── Vendor POs (Material Readiness) ──────────────────────────────────

    def get_outstanding_material_pos(self, page_size=500):
        """Query outstanding material vendor POs."""
        try:
            result = self.execute("""
                query ($pageSize: Int, $query: VendorPOQuery) {
                    vendorPOs(pageSize: $pageSize, query: $query) {
                        totalRecords
                        records {
                            poType
                            poItems(pageSize: 100) {
                                records {
                                    workOrderPlainText
                                    receivedDate
                                    description
                                }
                            }
                        }
                    }
                }
            """, {
                "pageSize": page_size,
                "query": {"poType": {"exactly": "Material"}},
            })
            return (result.get("data") or {}).get("vendorPOs", {"totalRecords": 0, "records": []})
        except (GraphQLError, Exception):
            # Scope may not be available — fail gracefully
            return {"totalRecords": -1, "records": [], "error": "scope_missing"}
