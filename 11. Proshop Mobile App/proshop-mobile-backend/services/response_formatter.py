"""
Response Formatter for ProShop API.
Converts raw GraphQL JSON responses to readable text output.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime


def format_date(date_str: Optional[str]) -> str:
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return date_str


def format_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        if isinstance(value, float):
            return f"{value:,.{decimals}f}"
        return f"{value:,}"
    except (ValueError, TypeError):
        return str(value)


def format_hours(hours: Any) -> str:
    if hours is None:
        return "N/A"
    try:
        return f"{float(hours):.2f} hrs"
    except (ValueError, TypeError):
        return str(hours)


def format_seconds_as_time(seconds: Any) -> str:
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
            return f"{secs / 60:.0f} min"
    except (ValueError, TypeError):
        return str(seconds)


def format_currency(amount: Any) -> str:
    if amount is None:
        return "N/A"
    try:
        return f"${float(amount):,.2f}"
    except (ValueError, TypeError):
        return str(amount)


def format_percentage(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return str(value)


def truncate(text: str, max_length: int = 50) -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def format_work_order_status(data: Dict) -> str:
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
    if not data:
        return "Work order not found."
    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Status: {data.get('status', 'N/A')}",
        "", "Operations:",
    ]
    ops = data.get("ops", {}).get("records", [])
    if not ops:
        lines.append("  No operations found.")
    else:
        for op in ops:
            complete = "Yes" if op.get("isOpComplete") else "No"
            lines.append(
                f"  Op {op.get('operationNumber', ''):>3} | "
                f"{truncate(op.get('operationDescription', ''), 30):30} | "
                f"Complete: {complete} | "
                f"Setup: {format_seconds_as_time(op.get('setupTime'))} | "
                f"Run: {format_seconds_as_time(op.get('runTime'))}"
            )
    return "\n".join(lines)


def format_work_order_current_op(data: Dict) -> str:
    if not data:
        return "Work order not found."
    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Status: {data.get('status', 'N/A')}",
        "",
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
    records = data.get("timeTracking", {}).get("records", [])
    if records:
        lines.append("")
        lines.append(f"Time Entries ({len(records)} records):")
        for entry in records[:10]:
            lines.append(
                f"  Op {entry.get('operationNumber', '')} | "
                f"{truncate(entry.get('spentDoing', ''), 20)} | "
                f"{format_date(entry.get('timeIn'))} - {format_date(entry.get('timeOut'))}"
            )
        if len(records) > 10:
            lines.append(f"  ... and {len(records) - 10} more entries")
    return "\n".join(lines)


def format_work_order_due_date(data: Dict) -> str:
    if not data:
        return "Work order not found."
    due_date = data.get("dueDate")
    lines = [
        f"Work Order: {data.get('workOrderNumber', 'N/A')}",
        f"Due Date: {format_date(due_date)}",
        f"Status: {data.get('status', 'N/A')}",
        f"Progress: {data.get('qtyComplete', 0)}/{data.get('quantityOrdered', 0)} complete",
    ]
    if due_date:
        try:
            due = datetime.fromisoformat(due_date.replace("Z", "+00:00")).date()
            today = datetime.now().date()
            if due < today and data.get("status") not in ["Complete", "Closed", "Shipped"]:
                lines.append(f"** LATE by {(today - due).days} day(s)! **")
        except (ValueError, TypeError):
            pass
    return "\n".join(lines)


def format_work_order_quantity(data: Dict) -> str:
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
    if not data:
        return "No data returned."
    total = data.get("totalRecords", 0)
    records = data.get("records", [])
    filter_applied = data.get("filter_applied", "")
    lines = [f"Work Orders ({total} found){' - ' + filter_applied if filter_applied else ''}:", ""]
    if not records:
        lines.append("No work orders found matching criteria.")
    else:
        for wo in records[:50]:
            lines.append(
                f"  {wo.get('workOrderNumber', ''):10} | "
                f"{wo.get('status', ''):25} | "
                f"Due: {format_date(wo.get('dueDate')):12} | "
                f"Qty: {wo.get('qtyComplete', 0)}/{wo.get('quantityOrdered', 0)}"
            )
        if len(records) > 50:
            lines.append(f"\n... showing 50 of {len(records)} results")
    return "\n".join(lines)


def format_open_work_order_count(data: Dict) -> str:
    if not data:
        return "Unable to count work orders."
    return f"Open Work Orders: {data.get('count', 0)} (out of {data.get('total', 0)} total)"


def format_largest_active_order(data: Dict) -> str:
    if not data:
        return "No active work orders found."
    lines = [
        "Largest Active Work Order:", "",
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
    if not data:
        return "No profitability data available."
    records = data.get("records", [])
    if not records:
        return "No work orders with profitability data found."
    lines = ["Work Order Profitability:", ""]
    for wo in records:
        prof = wo.get("profitability") or {}
        lines.append(
            f"  {wo.get('workOrderNumber', ''):10} | "
            f"{wo.get('status', ''):15} | "
            f"DLH: {format_hours(prof.get('dlh'))} | "
            f"Profit: {format_currency(prof.get('profit'))} | "
            f"Margin: {format_percentage(prof.get('profitMargin'))} | "
            f"Cost: {format_currency(prof.get('totalCost'))}"
        )
    return "\n".join(lines)


def format_part_info(data: List) -> str:
    if not data:
        return "Part not found."
    lines = []
    for part in data:
        lines.extend([
            f"Part Number: {part.get('partNumber', 'N/A')}",
            f"Description: {part.get('partDescription', 'N/A')}",
            "",
        ])
    return "\n".join(lines).strip()


def format_part_operations(data: List) -> str:
    if not data:
        return "Part not found."
    lines = []
    for part in data:
        lines.extend([
            f"Part: {part.get('partNumber', 'N/A')}",
            f"Description: {part.get('partDescription', 'N/A')}",
            "", "Operations:",
        ])
        ops = part.get("operations", {}).get("records", [])
        if not ops:
            lines.append("  No operations defined.")
        else:
            for op in ops:
                lines.append(f"  Op {op.get('opNumber', ''):>3} | {truncate(op.get('operationDescription', ''), 50)}")
    return "\n".join(lines)


def format_part_operation_details(data: List) -> str:
    if not data:
        return "Part not found."
    lines = []
    for part in data:
        lines.extend([
            f"Part: {part.get('partNumber', 'N/A')}",
            f"Description: {part.get('partDescription', 'N/A')}",
            "",
        ])
        ops = part.get("operations", {}).get("records", [])
        if not ops:
            lines.append("No operations found.")
            continue
        for op in ops:
            lines.extend([
                f"Op {op.get('opNumber', 'N/A')}: {op.get('operationDescription', 'N/A')}",
                "",
            ])
            written = op.get("writtenDescriptions", {}).get("records", [])
            if written:
                lines.append("Instructions:")
                for wd in written:
                    desc = wd.get("writtenDescription", "")
                    if desc:
                        lines.append(f"  {desc}")
                lines.append("")
            tools = op.get("tools", {}).get("records", [])
            if tools:
                lines.append("Tools:")
                for tool in tools:
                    lines.append(
                        f"  Seq {tool.get('sequenceNumber', ''):>3} | "
                        f"Holder: {tool.get('holder', '') or 'N/A':10} | "
                        f"Tool: {tool.get('outOfHolder', '') or 'N/A':15} | "
                        f"{truncate(tool.get('sequenceDescription', ''), 40)}"
                    )
                lines.append("")
    return "\n".join(lines).strip()


def format_parts_list(data: Dict) -> str:
    if not data:
        return "No parts found."
    total = data.get("totalRecords", 0)
    records = data.get("records", [])
    lines = [f"Parts ({total} total):", ""]
    if not records:
        lines.append("No parts found.")
    else:
        for p in records:
            lines.append(f"  {p.get('partNumber', ''):20} | {truncate(p.get('partDescription', ''), 50)}")
    return "\n".join(lines)


def format_help() -> str:
    return """ProShop Assistant - Example Queries
====================================

Work Order Queries:
  "What's the status of WO 25-0001?"
  "Show me all open work orders"
  "What work orders are due this week?"
  "Are there any late work orders?"
  "What operations are on WO 25-0001?"
  "What's the current operation for WO 25-0001?"
  "How much time has been spent on WO 25-0001?"
  "How many open work orders do we have?"
  "Show me work order profitability"

Part Queries:
  "What operations are on part TRA1-TEMP?"
  "Show me part TRA1-TEMP"
  "Show me the details for Op 60 on part TRA1-TEMP"
  "Show me all parts"

Tips:
  - Work order numbers are like: 25-0001
  - Part numbers are like: TRA1-TEMP"""


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
    formatter = FORMATTERS.get(template_name)
    if formatter:
        try:
            return formatter(data)
        except Exception as e:
            return f"Error formatting response: {e}\n\nRaw data: {data}"
    return f"Response:\n{json.dumps(data, indent=2, default=str)}"


def format_error(error: Exception) -> str:
    error_msg = str(error)
    if "INVALID_PERMISSIONS" in error_msg:
        return "Permission denied. This query requires additional API access."
    if "not found" in error_msg.lower():
        return "Not found. Please check the work order or part number."
    if "authentication" in error_msg.lower():
        return "Authentication failed. Please check credentials."
    return f"Error: {error_msg}"
