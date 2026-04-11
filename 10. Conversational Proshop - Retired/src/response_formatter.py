"""
Response Formatter for ProShop Conversational Interface.
Converts raw GraphQL JSON responses to readable text output.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime


# =============================================================================
# Formatting Utilities
# =============================================================================

def format_date(date_str: Optional[str]) -> str:
    """Format an ISO date string to readable format."""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return date_str


def format_number(value: Any, decimals: int = 2) -> str:
    """Format a number with optional decimal places."""
    if value is None:
        return "N/A"
    try:
        if isinstance(value, float):
            return f"{value:,.{decimals}f}"
        return f"{value:,}"
    except (ValueError, TypeError):
        return str(value)


def format_hours(hours: Any) -> str:
    """Format hours with 2 decimal places."""
    if hours is None:
        return "N/A"
    try:
        return f"{float(hours):.2f} hrs"
    except (ValueError, TypeError):
        return str(hours)


def format_seconds_as_time(seconds: Any) -> str:
    """Convert seconds to hours/minutes display."""
    if seconds is None:
        return "N/A"
    try:
        secs = float(seconds)
        if secs == 0:
            return "0"
        hours = secs / 3600
        if hours >= 1:
            return f"{hours:.1f} hrs"
        else:
            mins = secs / 60
            return f"{mins:.0f} min"
    except (ValueError, TypeError):
        return str(seconds)


def format_currency(amount: Any) -> str:
    """Format as currency."""
    if amount is None:
        return "N/A"
    try:
        return f"${float(amount):,.2f}"
    except (ValueError, TypeError):
        return str(amount)


def format_percentage(value: Any) -> str:
    """Format as percentage."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return str(value)


def truncate(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def make_table(headers: List[str], rows: List[List[str]], max_width: int = 80) -> str:
    """Create a simple ASCII table."""
    if not rows:
        return "(No data)"

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Build table
    lines = []

    # Header
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Rows
    for row in rows:
        row_line = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        lines.append(row_line)

    return "\n".join(lines)


# =============================================================================
# Template-Specific Formatters
# =============================================================================

def format_work_order_status(data: Dict) -> str:
    """Format work order status response."""
    if not data:
        return "Work order not found."

    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Status: {data.get('status', 'N/A')}",
        f"Due Date: {format_date(data.get('dueDate'))}",
        f"Quantity: {data.get('qtyComplete', 0)}/{data.get('quantityOrdered', 0)} complete",
        f"Hours Spent: {format_hours(data.get('hoursTotalSpent'))}",
    ]

    if data.get("part"):
        part = data["part"]
        lines.append(f"Part: {part.get('partNumber', '')} - {part.get('partDescription', '')}")

    return "\n".join(lines)


def format_work_order_operations(data: Dict) -> str:
    """Format work order operations response."""
    if not data:
        return "Work order not found."

    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Status: {data.get('status', 'N/A')}",
        "",
        "Operations:"
    ]

    ops = data.get("ops", {}).get("records", [])
    if not ops:
        lines.append("  No operations found.")
    else:
        headers = ["Op#", "Description", "Complete", "Setup", "Run"]
        rows = []
        for op in ops:
            complete = "Yes" if op.get("isOpComplete") else "No"
            rows.append([
                str(op.get("operationNumber", "")),
                truncate(op.get("operationDescription", ""), 30),
                complete,
                format_seconds_as_time(op.get("setupTime")),
                format_seconds_as_time(op.get("runTime")),
            ])
        lines.append(make_table(headers, rows))

    return "\n".join(lines)


def format_work_order_current_op(data: Dict) -> str:
    """Format current operation response."""
    if not data:
        return "Work order not found."

    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Status: {data.get('status', 'N/A')}",
        ""
    ]

    current_op = data.get("current_operation")
    if current_op:
        lines.append(f"Current Operation: Op {current_op.get('operationNumber', 'N/A')}")
        lines.append(f"Description: {current_op.get('operationDescription', 'N/A')}")
    else:
        all_ops = data.get("ops", {}).get("records", [])
        if all_ops and all(op.get("isOpComplete") for op in all_ops):
            lines.append("All operations are complete!")
        else:
            lines.append("No active operation found.")

    return "\n".join(lines)


def format_work_order_time_tracking(data: Dict) -> str:
    """Format time tracking response."""
    if not data:
        return "Work order not found."

    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Status: {data.get('status', 'N/A')}",
        "",
        "Time Summary:",
        f"  Total Hours: {format_hours(data.get('hoursTotalSpent'))}",
        f"  Setup Hours: {format_hours(data.get('setupTimeHoursActualLabel'))}",
        f"  Run Hours: {format_hours(data.get('runningTimeHoursActualLabor'))}",
    ]

    time_tracking = data.get("timeTracking", {})
    records = time_tracking.get("records", [])
    if records:
        lines.append("")
        lines.append(f"Time Entries ({len(records)} records):")
        headers = ["Op#", "Activity", "Time In", "Time Out"]
        rows = []
        for entry in records[:10]:  # Limit to 10 entries
            rows.append([
                str(entry.get("operationNumber", "")),
                truncate(entry.get("spentDoing", ""), 20),
                format_date(entry.get("timeIn")),
                format_date(entry.get("timeOut")),
            ])
        lines.append(make_table(headers, rows))
        if len(records) > 10:
            lines.append(f"  ... and {len(records) - 10} more entries")

    return "\n".join(lines)


def format_work_order_due_date(data: Dict) -> str:
    """Format due date response."""
    if not data:
        return "Work order not found."

    due_date = data.get("dueDate")
    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Due Date: {format_date(due_date)}",
        f"Status: {data.get('status', 'N/A')}",
        f"Progress: {data.get('qtyComplete', 0)}/{data.get('quantityOrdered', 0)} complete",
    ]

    # Check if late
    if due_date:
        try:
            due = datetime.fromisoformat(due_date.replace("Z", "+00:00")).date()
            today = datetime.now().date()
            if due < today and data.get("status") not in ["Complete", "Closed", "Shipped"]:
                days_late = (today - due).days
                lines.append(f"** LATE by {days_late} day(s)! **")
        except (ValueError, TypeError):
            pass

    return "\n".join(lines)


def format_work_order_quantity(data: Dict) -> str:
    """Format quantity response."""
    if not data:
        return "Work order not found."

    qty_ordered = data.get("quantityOrdered", 0)
    qty_complete = data.get("qtyComplete", 0)
    remaining = qty_ordered - qty_complete if qty_ordered and qty_complete else "N/A"

    return "\n".join([
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Quantity Ordered: {format_number(qty_ordered, 0)}",
        f"Quantity Complete: {format_number(qty_complete, 0)}",
        f"Remaining: {format_number(remaining, 0) if isinstance(remaining, (int, float)) else remaining}",
        f"Status: {data.get('status', 'N/A')}",
    ])


def format_work_order_list(data: Dict) -> str:
    """Format work order list response."""
    if not data:
        return "No data returned."

    total = data.get("totalRecords", 0)
    records = data.get("records", [])
    filter_applied = data.get("filter_applied", "")

    lines = [f"Work Orders ({total} found){' - ' + filter_applied if filter_applied else ''}:", ""]

    if not records:
        lines.append("No work orders found matching criteria.")
    else:
        headers = ["WO#", "Status", "Due Date", "Qty"]
        rows = []
        for wo in records[:50]:  # Limit display to 50 rows
            rows.append([
                wo.get("workOrderNumber", ""),
                wo.get("status", ""),
                format_date(wo.get("dueDate")),
                f"{wo.get('qtyComplete', 0)}/{wo.get('quantityOrdered', 0)}",
            ])
        lines.append(make_table(headers, rows))
        if len(records) > 50:
            lines.append(f"\n... showing 50 of {len(records)} results")

    return "\n".join(lines)


def format_open_work_order_count(data: Dict) -> str:
    """Format open work order count response."""
    if not data:
        return "Unable to count work orders."

    return f"Open Work Orders: {data.get('count', 0)} (out of {data.get('total', 0)} total)"


def format_largest_active_order(data: Dict) -> str:
    """Format largest active work order response."""
    if not data:
        return "No active work orders found."

    lines = [
        "Largest Active Work Order:",
        "",
        f"  Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"  Status: {data.get('status', 'N/A')}",
        f"  Quantity: {data.get('quantityOrdered', 0)} ordered, {data.get('qtyComplete', 0)} complete",
        f"  Due Date: {format_date(data.get('dueDate'))}",
    ]

    if data.get("part"):
        part = data["part"]
        lines.append(f"  Part: {part.get('partNumber', '')} - {part.get('partDescription', '')}")

    return "\n".join(lines)


def format_work_order_profitability(data: Dict) -> str:
    """Format profitability response."""
    if not data:
        return "No profitability data available."

    records = data.get("records", [])
    if not records:
        return "No work orders with profitability data found."

    lines = ["Work Order Profitability:", ""]

    headers = ["WO#", "Status", "DLH", "Profit", "Margin", "Total Cost"]
    rows = []
    for wo in records:
        prof = wo.get("profitability") or {}
        rows.append([
            wo.get("workOrderNumber", ""),
            wo.get("status", ""),
            format_hours(prof.get("dlh")),
            format_currency(prof.get("profit")),
            format_percentage(prof.get("profitMargin")),
            format_currency(prof.get("totalCost")),
        ])
    lines.append(make_table(headers, rows))

    return "\n".join(lines)


def format_part_info(data: List) -> str:
    """Format part info response."""
    if not data:
        return "Part not found."

    lines = []
    for part in data:
        lines.extend([
            f"Part Number: {part.get('partNumber', 'N/A')}",
            f"Description: {part.get('partDescription', 'N/A')}",
            ""
        ])

    return "\n".join(lines).strip()


def format_part_operations(data: List) -> str:
    """Format part operations response."""
    if not data:
        return "Part not found."

    lines = []
    for part in data:
        lines.extend([
            f"Part: {part.get('partNumber', 'N/A')}",
            f"Description: {part.get('partDescription', 'N/A')}",
            "",
            "Operations:"
        ])

        ops = part.get("operations", {}).get("records", [])
        if not ops:
            lines.append("  No operations defined.")
        else:
            headers = ["Op#", "Description"]
            rows = [[str(op.get("opNumber", "")), truncate(op.get("operationDescription", ""), 50)] for op in ops]
            lines.append(make_table(headers, rows))

    return "\n".join(lines)


def format_part_operation_details(data: List) -> str:
    """Format detailed part operation response."""
    if not data:
        return "Part not found."

    lines = []
    for part in data:
        lines.extend([
            f"Part: {part.get('partNumber', 'N/A')}",
            f"Description: {part.get('partDescription', 'N/A')}",
            ""
        ])

        ops = part.get("operations", {}).get("records", [])
        if not ops:
            lines.append("No operations found.")
            continue

        for op in ops:
            lines.extend([
                f"Op {op.get('opNumber', 'N/A')}: {op.get('operationDescription', 'N/A')}",
                ""
            ])

            # Written descriptions
            written = op.get("writtenDescriptions", {}).get("records", [])
            if written:
                lines.append("Instructions:")
                for wd in written:
                    desc = wd.get("writtenDescription", "")
                    if desc:
                        lines.append(f"  {desc}")
                lines.append("")

            # Tools
            tools = op.get("tools", {}).get("records", [])
            if tools:
                lines.append("Tools:")
                headers = ["Seq", "Holder", "Tool", "Description"]
                rows = []
                for tool in tools:
                    rows.append([
                        str(tool.get("sequenceNumber", "")),
                        tool.get("holder", "") or "",
                        tool.get("outOfHolder", "") or "",
                        truncate(tool.get("sequenceDescription", ""), 40),
                    ])
                lines.append(make_table(headers, rows))
                lines.append("")

    return "\n".join(lines).strip()


def format_parts_list(data: Dict) -> str:
    """Format parts list response."""
    if not data:
        return "No parts found."

    total = data.get("totalRecords", 0)
    records = data.get("records", [])

    lines = [f"Parts ({total} total):", ""]

    if not records:
        lines.append("No parts found.")
    else:
        headers = ["Part Number", "Description"]
        rows = [[p.get("partNumber", ""), truncate(p.get("partDescription", ""), 50)] for p in records]
        lines.append(make_table(headers, rows))

    return "\n".join(lines)


def format_help() -> str:
    """Format help response."""
    return """
ProShop Assistant - Example Queries
====================================

Work Order Queries:
  "What's the status of WO 25-0001?"
  "Show me all open work orders"
  "What work orders are due this week?"
  "Are there any late work orders?"
  "What operations are on WO 25-0001?"
  "What's the current operation for WO 25-0001?"
  "How much time has been spent on WO 25-0001?"
  "When is WO 25-0001 due?"
  "What's the quantity for WO 25-0001?"
  "How many open work orders do we have?"
  "Show me work order profitability"

Part Queries:
  "What operations are on part TRA1-TEMP?"
  "Show me part TRA1-TEMP"
  "Show me the details for Op 60 on part TRA1-TEMP"
  "Show me all parts"

Tips:
  - Work order numbers are like: 25-0001
  - Part numbers are like: TRA1-TEMP
  - Type 'quit' or 'exit' to leave
  - Type 'raw' before a query to see the GraphQL
""".strip()


# =============================================================================
# Main Formatter
# =============================================================================

# Map template names to formatter functions
FORMATTERS = {
    "work_order_status": format_work_order_status,
    "work_order_operations": format_work_order_operations,
    "work_order_current_op": format_work_order_current_op,
    "work_order_time_tracking": format_work_order_time_tracking,
    "work_order_due_date": format_work_order_due_date,
    "work_order_quantity": format_work_order_quantity,
    "list_work_orders": format_work_order_list,
    "list_work_orders_by_status": format_work_order_list,
    "work_orders_due_this_week": format_work_order_list,
    "late_work_orders": format_work_order_list,
    "open_work_order_count": format_open_work_order_count,
    "largest_active_order": format_largest_active_order,
    "work_order_profitability": format_work_order_profitability,
    "part_info": format_part_info,
    "part_operations": format_part_operations,
    "part_operation_details": format_part_operation_details,
    "list_parts": format_parts_list,
    "help": lambda data: format_help(),
}


def format_response(template_name: str, data: Any) -> str:
    """
    Format a query response for display.

    Args:
        template_name: The name of the query template that was executed
        data: The extracted/processed data from the query

    Returns:
        Formatted string for display to user
    """
    formatter = FORMATTERS.get(template_name)
    if formatter:
        try:
            return formatter(data)
        except Exception as e:
            return f"Error formatting response: {e}\n\nRaw data: {data}"

    # Fallback: pretty print the data
    import json
    return f"Response:\n{json.dumps(data, indent=2, default=str)}"


def format_error(error: Exception) -> str:
    """Format an error message for display."""
    error_msg = str(error)

    # Common error translations
    if "INVALID_PERMISSIONS" in error_msg:
        return "Permission denied. This query requires additional API access."
    if "not found" in error_msg.lower():
        return "Not found. Please check the work order or part number."
    if "authentication" in error_msg.lower():
        return "Authentication failed. Please check credentials."

    return f"Error: {error_msg}"
