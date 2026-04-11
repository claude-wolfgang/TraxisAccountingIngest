"""
GraphQL Query Templates for ProShop ERP.
Each template defines a query, its variables, and how to extract results.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time

from config import MAX_RESULTS_PER_QUERY, DEFAULT_LOOKBACK_MONTHS

_last_query_time = 0


# =============================================================================
# Query Template Definitions
# =============================================================================

QUERY_TEMPLATES = {
    "work_order_status": {
        "description": "Get status and details of a specific work order",
        "example": "What's the status of WO 25-0001?",
        "query": """
            query GetWorkOrderStatus($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    status
                    dueDate
                    quantityOrdered
                    qtyComplete
                    hoursTotalSpent
                    partRev
                    part {
                        partNumber
                        partDescription
                    }
                }
            }
        """,
        "variables": ["woNumber"],
        "extract": lambda data: data.get("workOrder"),
    },

    "work_order_operations": {
        "description": "Get operations for a specific work order",
        "example": "What operations are on WO 25-0001?",
        "query": """
            query GetWorkOrderOps($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    status
                    ops {
                        records {
                            operationNumber
                            operationDescription
                            isOpComplete
                            setupTime
                            runTime
                        }
                    }
                }
            }
        """,
        "variables": ["woNumber"],
        "extract": lambda data: data.get("workOrder"),
    },

    "work_order_current_op": {
        "description": "Get the current (incomplete) operation for a work order",
        "example": "What's the current operation for WO 25-0001?",
        "query": """
            query GetWorkOrderCurrentOp($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    status
                    ops {
                        records {
                            operationNumber
                            operationDescription
                            isOpComplete
                        }
                    }
                }
            }
        """,
        "variables": ["woNumber"],
        "extract": lambda data: data.get("workOrder"),
        "post_process": "find_current_operation",
    },

    "work_order_time_tracking": {
        "description": "Get time tracking data for a work order",
        "example": "How much time has been spent on WO 25-0001?",
        "query": """
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
        """,
        "variables": ["woNumber"],
        "extract": lambda data: data.get("workOrder"),
    },

    "work_order_due_date": {
        "description": "Get the due date for a work order",
        "example": "When is WO 25-0001 due?",
        "query": """
            query GetWorkOrderDueDate($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    dueDate
                    status
                    quantityOrdered
                    qtyComplete
                }
            }
        """,
        "variables": ["woNumber"],
        "extract": lambda data: data.get("workOrder"),
    },

    "work_order_quantity": {
        "description": "Get quantity info for a work order",
        "example": "What's the quantity for WO 25-0001?",
        "query": """
            query GetWorkOrderQty($woNumber: String!) {
                workOrder(workOrderNumber: $woNumber) {
                    workOrderNumber
                    quantityOrdered
                    qtyComplete
                    status
                }
            }
        """,
        "variables": ["woNumber"],
        "extract": lambda data: data.get("workOrder"),
    },

    "list_work_orders": {
        "description": "List work orders (last 12 months)",
        "example": "Show me all work orders",
        "query": """
            query ListWorkOrders($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workOrderNumber
                        status
                        dueDate
                        quantityOrdered
                        qtyComplete
                        partRev
                        part {
                            partNumber
                            partDescription
                        }
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 2500},
        "extract": lambda data: data.get("workOrders"),
        "post_process": "filter_recent_only",
        "slow_query": True,
    },

    "list_work_orders_by_status": {
        "description": "List work orders filtered by status (last 12 months)",
        "example": "Show me all open work orders",
        "query": """
            query ListWorkOrdersByStatus($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workOrderNumber
                        status
                        dueDate
                        quantityOrdered
                        qtyComplete
                        partRev
                        part {
                            partNumber
                            partDescription
                        }
                    }
                }
            }
        """,
        "variables": ["status"],
        "defaults": {"pageSize": 2500},
        "extract": lambda data: data.get("workOrders"),
        "post_process": "filter_by_status_recent",
        "slow_query": True,
    },

    "work_orders_due_this_week": {
        "description": "List work orders due this week",
        "example": "What work orders are due this week?",
        "query": """
            query ListWorkOrdersDueThisWeek($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workOrderNumber
                        status
                        dueDate
                        quantityOrdered
                        qtyComplete
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 2500},
        "extract": lambda data: data.get("workOrders"),
        "post_process": "filter_due_this_week",
        "slow_query": True,
    },

    "late_work_orders": {
        "description": "List work orders that are past due",
        "example": "Are there any late work orders?",
        "query": """
            query ListLateWorkOrders($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workOrderNumber
                        status
                        dueDate
                        quantityOrdered
                        qtyComplete
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 2500},
        "extract": lambda data: data.get("workOrders"),
        "post_process": "filter_late_recent",
        "slow_query": True,
    },

    "open_work_order_count": {
        "description": "Count of open work orders (last 12 months)",
        "example": "How many open work orders do we have?",
        "query": """
            query CountOpenWorkOrders($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workOrderNumber
                        status
                        dueDate
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 2500},
        "extract": lambda data: data.get("workOrders"),
        "post_process": "count_open_recent",
        "slow_query": True,
    },

    "largest_active_order": {
        "description": "Find the largest active work order by quantity",
        "example": "Show me the largest active order",
        "query": """
            query ListActiveWorkOrders($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    totalRecords
                    records {
                        workOrderNumber
                        status
                        dueDate
                        quantityOrdered
                        qtyComplete
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 2500},
        "extract": lambda data: data.get("workOrders"),
        "post_process": "find_largest_active",
        "slow_query": True,
    },

    "work_order_profitability": {
        "description": "Get profitability data for work orders",
        "example": "Show me work order profitability",
        "query": """
            query GetWorkOrderProfitability($pageSize: Int) {
                workOrders(pageSize: $pageSize) {
                    records {
                        workOrderNumber
                        status
                        profitability {
                            dlh
                            profit
                            profitMargin
                            totalCost
                        }
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 20},
        "extract": lambda data: data.get("workOrders"),
    },

    # Parts
    "part_info": {
        "description": "Get information about a specific part",
        "example": "Show me part TRA1-TEMP",
        "query": """
            query GetPart($partNumber: [String!]!) {
                parts(filter: { partNumber: $partNumber }) {
                    records {
                        partNumber
                        partDescription
                    }
                }
            }
        """,
        "variables": ["partNumber"],
        "extract": lambda data: data.get("parts", {}).get("records", []),
    },

    "part_operations": {
        "description": "Get operations for a specific part",
        "example": "What operations are on part TRA1-TEMP?",
        "query": """
            query GetPartOperations($partNumber: [String!]!) {
                parts(filter: { partNumber: $partNumber }) {
                    records {
                        partNumber
                        partDescription
                        operations {
                            records {
                                opNumber
                                operationDescription
                            }
                        }
                    }
                }
            }
        """,
        "variables": ["partNumber"],
        "extract": lambda data: data.get("parts", {}).get("records", []),
    },

    "part_operation_details": {
        "description": "Get detailed operation info including tools and written descriptions",
        "example": "Show me the details for Op 60 on part TRA1-TEMP",
        "query": """
            query GetPartOperationDetails($partNumber: [String!]!) {
                parts(filter: { partNumber: $partNumber }) {
                    records {
                        partNumber
                        partDescription
                        operations {
                            records {
                                opNumber
                                operationDescription
                                writtenDescriptions {
                                    records {
                                        writtenDescription
                                    }
                                }
                                tools {
                                    records {
                                        sequenceNumber
                                        outOfHolder
                                        holder
                                        sequenceDescription
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """,
        "variables": ["partNumber"],
        "extract": lambda data: data.get("parts", {}).get("records", []),
        "post_process": "filter_operation",
    },

    "list_parts": {
        "description": "List all parts",
        "example": "Show me all parts",
        "query": """
            query ListParts($pageSize: Int) {
                parts(pageSize: $pageSize) {
                    totalRecords
                    records {
                        partNumber
                        partDescription
                    }
                }
            }
        """,
        "variables": [],
        "defaults": {"pageSize": 50},
        "extract": lambda data: data.get("parts"),
    },

    "help": {
        "description": "Show available commands and examples",
        "example": "help",
        "query": None,
        "variables": [],
        "extract": lambda data: None,
    },
}


# =============================================================================
# Post-Processing Functions
# =============================================================================

def find_current_operation(data: Dict, variables: Dict) -> Dict:
    if not data or "ops" not in data:
        return data
    ops = data.get("ops", {}).get("records", [])
    current_op = None
    for op in ops:
        if not op.get("isOpComplete"):
            current_op = op
            break
    data["current_operation"] = current_op
    return data


def parse_date(date_str: str):
    if not date_str:
        return None
    formats = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.split("T")[0], fmt).date()
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def is_within_lookback(wo: Dict, months: int = DEFAULT_LOOKBACK_MONTHS) -> bool:
    wo_num = wo.get("workOrderNumber", "")
    if not wo_num or "-" not in wo_num:
        return True
    try:
        year_prefix = wo_num.split("-")[0]
        wo_year = 2000 + int(year_prefix)
        cutoff_year = datetime.now().year - (months // 12)
        return wo_year >= cutoff_year
    except (ValueError, IndexError):
        return True


def filter_recent_only(data: Dict, variables: Dict) -> Dict:
    if not data or "records" not in data:
        return data
    filtered = [wo for wo in data["records"] if is_within_lookback(wo)]
    return {
        "totalRecords": len(filtered),
        "records": filtered[:MAX_RESULTS_PER_QUERY],
        "filter_applied": f"last {DEFAULT_LOOKBACK_MONTHS} months",
    }


def filter_by_status_recent(data: Dict, variables: Dict) -> Dict:
    if not data or "records" not in data:
        return data
    recent = [wo for wo in data["records"] if is_within_lookback(wo)]
    target_status = variables.get("status", "").lower()
    if not target_status:
        return {
            "totalRecords": len(recent),
            "records": recent[:MAX_RESULTS_PER_QUERY],
            "filter_applied": f"last {DEFAULT_LOOKBACK_MONTHS} months",
        }
    status_mapping = {
        "open": ["Active"],
        "active": ["Active"],
        "in process": ["Active", "Manufacturing Complete"],
        "pending": ["Active"],
        "complete": ["Complete", "Manufacturing Complete", "Invoiced"],
        "closed": ["Invoiced"],
        "shipped": ["Shipped"],
        "invoiced": ["Invoiced"],
        "canceled": ["Canceled"],
        "manufacturing complete": ["Manufacturing Complete"],
    }
    target_statuses = status_mapping.get(target_status, [target_status])
    filtered = [
        wo for wo in recent
        if wo.get("status") in target_statuses or target_status in wo.get("status", "").lower()
    ]
    return {
        "totalRecords": len(filtered),
        "records": filtered[:MAX_RESULTS_PER_QUERY],
        "filter_applied": f"status={target_status}, last {DEFAULT_LOOKBACK_MONTHS} months",
    }


def filter_due_this_week(data: Dict, variables: Dict) -> Dict:
    if not data or "records" not in data:
        return data
    today = datetime.now().date()
    week_end = today + timedelta(days=(6 - today.weekday()))
    filtered = []
    for wo in data["records"]:
        due_date = parse_date(wo.get("dueDate"))
        if due_date and today <= due_date <= week_end:
            filtered.append(wo)
    return {
        "totalRecords": len(filtered),
        "records": filtered,
        "filter_applied": f"due between {today} and {week_end}",
    }


def filter_late_recent(data: Dict, variables: Dict) -> Dict:
    if not data or "records" not in data:
        return data
    today = datetime.now().date()
    complete_statuses = ["Complete", "Invoiced", "Shipped", "Canceled"]
    filtered = []
    for wo in data["records"]:
        if not is_within_lookback(wo):
            continue
        if wo.get("status") in complete_statuses:
            continue
        due_date = parse_date(wo.get("dueDate"))
        if due_date and due_date < today:
            filtered.append(wo)
    return {
        "totalRecords": len(filtered),
        "records": filtered[:MAX_RESULTS_PER_QUERY],
        "filter_applied": f"late (due before {today}), last {DEFAULT_LOOKBACK_MONTHS} months",
    }


def count_open_recent(data: Dict, variables: Dict) -> Dict:
    if not data or "records" not in data:
        return {"count": 0, "status": "unknown"}
    recent = [wo for wo in data["records"] if is_within_lookback(wo)]
    open_statuses = ["Active", "Manufacturing Complete"]
    count = sum(1 for wo in recent if wo.get("status") in open_statuses)
    return {
        "count": count,
        "total": len(recent),
        "filter_applied": f"open (Active/Mfg Complete), last {DEFAULT_LOOKBACK_MONTHS} months",
    }


def find_largest_active(data: Dict, variables: Dict) -> Dict:
    if not data or "records" not in data:
        return None
    active_statuses = ["Active", "Manufacturing Complete"]
    active_orders = [
        wo for wo in data["records"]
        if wo.get("status") in active_statuses and is_within_lookback(wo)
    ]
    if not active_orders:
        return None
    return max(active_orders, key=lambda wo: wo.get("quantityOrdered") or 0)


def filter_operation(data: Dict, variables: Dict) -> Dict:
    if not data:
        return data
    op_number = variables.get("opNumber")
    if not op_number:
        return data
    for part in data:
        if "operations" in part and "records" in part["operations"]:
            ops = part["operations"]["records"]
            filtered_ops = [op for op in ops if str(op.get("opNumber")) == str(op_number)]
            part["operations"]["records"] = filtered_ops
    return data


POST_PROCESSORS = {
    "find_current_operation": find_current_operation,
    "filter_by_status_recent": filter_by_status_recent,
    "filter_due_this_week": filter_due_this_week,
    "filter_late_recent": filter_late_recent,
    "count_open_recent": count_open_recent,
    "filter_operation": filter_operation,
    "filter_recent_only": filter_recent_only,
    "find_largest_active": find_largest_active,
}


def get_template(template_name: str) -> Optional[Dict]:
    return QUERY_TEMPLATES.get(template_name)


def list_templates() -> List[Dict[str, str]]:
    return [
        {"name": name, "description": t["description"], "example": t.get("example", "")}
        for name, t in QUERY_TEMPLATES.items()
    ]


def execute_template(client, template_name: str, variables: Dict[str, Any] = None) -> Any:
    """Execute a query template with the given variables."""
    global _last_query_time

    template = get_template(template_name)
    if not template:
        raise ValueError(f"Unknown template: {template_name}")

    if template["query"] is None:
        return None

    # Rate limiting
    from config import RATE_LIMIT_SECONDS
    elapsed = time.time() - _last_query_time
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)

    # Merge defaults with provided variables
    query_vars = template.get("defaults", {}).copy()
    if variables:
        query_vars.update(variables)

    _last_query_time = time.time()
    data = client.execute(template["query"], query_vars)

    result = template["extract"](data)

    if "post_process" in template:
        processor = POST_PROCESSORS.get(template["post_process"])
        if processor:
            result = processor(result, variables or {})

    return result
