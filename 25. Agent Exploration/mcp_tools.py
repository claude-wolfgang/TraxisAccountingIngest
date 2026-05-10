"""
MCP tool definitions for the Traxis Data Quality Agent.

Wraps ProShopClient, FocasReader, and AuditDB as in-process MCP tools
for use with the Claude Agent SDK. Tools are grouped into three servers:
  - proshop: ProShop ERP queries
  - focas: FOCAS machine monitoring queries
  - audit: Audit engine and history queries
"""

import json
import time
from datetime import datetime, timedelta
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

import config
from proshop_client import ProShopClient
from focas_reader import FocasReader
from audit_db import AuditDB
from audit_engine import AuditEngine


# -- Lazy Client Singletons ------------------------------------------------
# Initialized on first tool call, shared across all calls in the process.

_proshop = None
_focas = None
_audit_db = None


def _get_proshop():
    global _proshop
    if _proshop is None:
        _proshop = ProShopClient(
            graphql_url=config.PROSHOP_GRAPHQL_URL,
            token_url=config.PROSHOP_TOKEN_URL,
            client_id=config.PROSHOP_CLIENT_ID,
            client_secret=config.PROSHOP_CLIENT_SECRET,
            scope=config.PROSHOP_SCOPE,
        )
    return _proshop


def _get_focas():
    global _focas
    if _focas is None:
        db_path = config.get_focas_db_path()
        if not db_path:
            raise FileNotFoundError("No FOCAS database found")
        _focas = FocasReader(db_path)
    return _focas


def _get_audit_db():
    global _audit_db
    if _audit_db is None:
        _audit_db = AuditDB(config.AUDIT_DB_PATH)
    return _audit_db


def _json_response(data):
    """Format a successful JSON response for MCP."""
    return {
        "content": [{"type": "text", "text": json.dumps(data, default=str, indent=2)}]
    }


def _error_response(error_msg):
    """Format an error response that keeps the agent loop alive."""
    return {
        "content": [{"type": "text", "text": json.dumps({"error": str(error_msg)})}],
        "is_error": True,
    }


# ==========================================================================
# PROSHOP TOOLS
# ==========================================================================

@tool(
    "check_proshop_health",
    "Check ProShop ERP API connectivity and authentication status. "
    "Returns whether the API is healthy, active work order count, and token age.",
    {},
)
async def check_proshop_health(args: dict[str, Any]) -> dict:
    try:
        result = _get_proshop().check_health()
        return _json_response(result)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_active_work_orders",
    "Get all active work orders from ProShop with their operations. "
    "Returns work order numbers, part info, due dates, hours target/spent, "
    "and operation details including scheduling and certification status.",
    {},
)
async def get_active_work_orders(args: dict[str, Any]) -> dict:
    try:
        data = _get_proshop().get_all_active_work_orders()
        records = data.get("records", [])
        summary = {
            "total_records": data.get("totalRecords", 0),
            "work_orders": [],
        }
        for wo in records:
            ops = (wo.get("ops") or {}).get("records", [])
            active_ops = [op for op in ops if not op.get("isOpComplete")]
            target = wo.get("hoursCurrentTarget") or 0
            spent = wo.get("hoursTotalSpent") or 0
            try:
                target_f = float(target)
                spent_f = float(spent)
            except (ValueError, TypeError):
                target_f = 0
                spent_f = 0
            summary["work_orders"].append({
                "workOrderNumber": wo.get("workOrderNumber"),
                "partNumber": (wo.get("part") or {}).get("partNumber"),
                "partDescription": (wo.get("part") or {}).get("partDescription"),
                "family": (wo.get("part") or {}).get("family"),
                "status": wo.get("status"),
                "dueDate": wo.get("dueDate"),
                "quantityOrdered": wo.get("quantityOrdered"),
                "qtyComplete": wo.get("qtyComplete"),
                "hoursTarget": target_f,
                "hoursSpent": spent_f,
                "hoursOver": round(spent_f - target_f, 1) if target_f > 0 else None,
                "programmingPct": wo.get("programmingPercentComplete"),
                "totalOps": len(ops),
                "activeOps": len(active_ops),
                "completedOps": len(ops) - len(active_ops),
            })
        return _json_response(summary)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_completed_work_orders",
    "Get completed/shipped/invoiced work orders for overrun analysis. "
    "Returns target vs actual hours for each job to identify quoting accuracy issues.",
    {},
)
async def get_completed_work_orders(args: dict[str, Any]) -> dict:
    try:
        records = _get_proshop().get_completed_work_orders()
        results = []
        for wo in records:
            target = wo.get("hoursCurrentTarget")
            spent = wo.get("hoursTotalSpent")
            try:
                target_f = float(target) if target else 0
                spent_f = float(spent) if spent else 0
            except (ValueError, TypeError):
                target_f = 0
                spent_f = 0
            overrun_pct = round((spent_f / target_f - 1) * 100, 1) if target_f > 0 else None
            results.append({
                "workOrderNumber": wo.get("workOrderNumber"),
                "partNumber": (wo.get("part") or {}).get("partNumber"),
                "family": (wo.get("part") or {}).get("family"),
                "status": wo.get("status"),
                "dueDate": wo.get("dueDate"),
                "hoursTarget": target_f,
                "hoursSpent": spent_f,
                "overrunPct": overrun_pct,
                "hoursOver": round(spent_f - target_f, 1) if target_f > 0 else None,
            })
        summary = {
            "total": len(results),
            "with_hours": len([r for r in results if r["hoursTarget"] > 0 and r["hoursSpent"] > 0]),
            "overrunning": len([r for r in results if (r["overrunPct"] or 0) > 0]),
            "work_orders": results,
        }
        return _json_response(summary)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_work_cells",
    "Get all work cells (machines) configured in ProShop. "
    "Returns machine names, types, and active status.",
    {},
)
async def get_work_cells(args: dict[str, Any]) -> dict:
    try:
        result = _get_proshop().get_work_cells()
        return _json_response(result)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_work_order",
    "Get a single work order by number. Fast targeted lookup. "
    "Returns status, dates, hours target/spent, part info, and all operations. "
    "WO numbers are in YY-NNNN format (e.g. 25-0001).",
    {"type": "object", "properties": {
        "wo_number": {"type": "string", "description": "Work order number (e.g. 25-0001)"},
    }, "required": ["wo_number"]},
)
async def get_work_order(args: dict[str, Any]) -> dict:
    try:
        wo = _get_proshop().get_work_order(args["wo_number"])
        if not wo:
            return _json_response({"error": f"Work order {args['wo_number']} not found"})
        # Flatten ops for readability
        ops = (wo.get("ops") or {}).get("records", [])
        wo["ops"] = ops
        return _json_response(wo)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_work_order_time_tracking",
    "Get time tracking entries for a work order. Shows hoursTotalSpent, "
    "actual labor/setup hours, and individual time clock entries with timeIn/timeOut.",
    {"type": "object", "properties": {
        "wo_number": {"type": "string", "description": "Work order number (e.g. 25-0001)"},
    }, "required": ["wo_number"]},
)
async def get_work_order_time_tracking(args: dict[str, Any]) -> dict:
    try:
        wo = _get_proshop().get_work_order_time_tracking(args["wo_number"])
        if not wo:
            return _json_response({"error": f"Work order {args['wo_number']} not found"})
        return _json_response(wo)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_work_order_profitability",
    "Get profitability data for work orders. Returns DLH (direct labor hours), "
    "profit, profit margin, and total cost per job. Useful for financial analysis.",
    {},
)
async def get_work_order_profitability(args: dict[str, Any]) -> dict:
    try:
        data = _get_proshop().get_work_order_profitability()
        records = data.get("records", [])
        # Filter to records that have profitability data
        with_profit = [r for r in records if r.get("profitability")]
        return _json_response({
            "total_records": len(records),
            "with_profitability_data": len(with_profit),
            "work_orders": with_profit,
        })
    except Exception as e:
        return _error_response(e)


@tool(
    "get_part_info",
    "Get details for a specific part by part number. Returns partNumber, "
    "partDescription, family, and customerPartNumber. "
    "Part numbers are case-sensitive (e.g. TRA1-TEMP, R2S-HOUSING).",
    {"type": "object", "properties": {
        "part_number": {"type": "string", "description": "Part number (case-sensitive, e.g. TRA1-TEMP)"},
    }, "required": ["part_number"]},
)
async def get_part_info(args: dict[str, Any]) -> dict:
    try:
        part = _get_proshop().get_part(args["part_number"])
        if not part:
            return _json_response({"error": f"Part {args['part_number']} not found"})
        return _json_response(part)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_part_operations",
    "Get the master routing (operations list) for a part. Returns operation numbers, "
    "descriptions, setup and run times. Note: setupTime and runTime are in SECONDS.",
    {"type": "object", "properties": {
        "part_number": {"type": "string", "description": "Part number (case-sensitive, e.g. TRA1-TEMP)"},
    }, "required": ["part_number"]},
)
async def get_part_operations(args: dict[str, Any]) -> dict:
    try:
        part = _get_proshop().get_part_operations(args["part_number"])
        if not part:
            return _json_response({"error": f"Part {args['part_number']} not found"})
        return _json_response(part)
    except Exception as e:
        return _error_response(e)


# Status mapping for search_work_orders (from Project 10)
_STATUS_MAP = {
    "open": ["Active"],
    "active": ["Active"],
    "in process": ["Active", "Manufacturing Complete"],
    "complete": ["Complete", "Manufacturing Complete", "Invoiced"],
    "closed": ["Invoiced"],
    "shipped": ["Shipped"],
    "invoiced": ["Invoiced"],
    "canceled": ["Canceled"],
    "manufacturing complete": ["Manufacturing Complete"],
}


def _parse_date(date_str):
    """Parse ProShop date strings."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.split("T")[0], fmt).date()
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


@tool(
    "search_work_orders",
    "Search and filter work orders by status or due date. "
    "Filters: 'open'/'active', 'complete', 'shipped', 'invoiced', 'canceled', "
    "'late' (active + past due), 'due this week' (active + due within current week). "
    "Fetches all active WOs and filters client-side.",
    {"type": "object", "properties": {
        "filter": {"type": "string", "description": "Filter: open, active, complete, shipped, late, due this week, canceled"},
    }, "required": ["filter"]},
)
async def search_work_orders(args: dict[str, Any]) -> dict:
    try:
        filter_str = args["filter"].lower().strip()
        ps = _get_proshop()

        # For completed/shipped/invoiced, use the completed WO query
        if filter_str in ("complete", "shipped", "invoiced", "closed"):
            records = ps.get_completed_work_orders()
            target_statuses = _STATUS_MAP.get(filter_str, [filter_str.title()])
            filtered = [wo for wo in records if wo.get("status") in target_statuses]
            return _json_response({
                "filter": filter_str,
                "count": len(filtered),
                "work_orders": filtered[:50],
            })

        # For active/late/due this week, use active WO query
        data = ps.get_all_active_work_orders()
        records = data.get("records", [])
        today = datetime.now().date()

        if filter_str in ("late", "overdue", "past due"):
            filtered = []
            for wo in records:
                due = _parse_date(wo.get("dueDate"))
                if due and due < today:
                    filtered.append(wo)
            label = f"late (due before {today})"
        elif filter_str in ("due this week", "this week"):
            week_end = today + timedelta(days=(6 - today.weekday()))
            filtered = []
            for wo in records:
                due = _parse_date(wo.get("dueDate"))
                if due and today <= due <= week_end:
                    filtered.append(wo)
            label = f"due {today} - {week_end}"
        else:
            # Default: filter by status mapping
            target_statuses = _STATUS_MAP.get(filter_str, [filter_str.title()])
            filtered = [wo for wo in records if wo.get("status") in target_statuses]
            label = f"status in {target_statuses}"

        # Slim down output
        results = []
        for wo in filtered:
            ops = (wo.get("ops") or {}).get("records", [])
            results.append({
                "workOrderNumber": wo.get("workOrderNumber"),
                "partNumber": (wo.get("part") or {}).get("partNumber"),
                "status": wo.get("status"),
                "dueDate": wo.get("dueDate"),
                "quantityOrdered": wo.get("quantityOrdered"),
                "hoursTarget": wo.get("hoursCurrentTarget"),
                "hoursSpent": wo.get("hoursTotalSpent"),
                "totalOps": len(ops),
            })

        return _json_response({
            "filter": label,
            "count": len(results),
            "work_orders": results[:50],
        })
    except Exception as e:
        return _error_response(e)


# ==========================================================================
# FOCAS TOOLS
# ==========================================================================

@tool(
    "check_focas_health",
    "Check FOCAS machine monitoring database health. "
    "Returns per-machine last sample time, staleness, and total sample counts. "
    "Machines: M2 (FANUC Mill 2), M3 (FANUC Mill 3), M6 (FANUC Mill 6), "
    "M8 (Hyundai-Wia KF5600II), T2 (YCM NTC1600LY lathe).",
    {},
)
async def check_focas_health(args: dict[str, Any]) -> dict:
    try:
        result = _get_focas().check_health()
        return _json_response(result)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_machine_utilization",
    "Get machine utilization data. With no arguments, returns today's utilization "
    "for all FOCAS-connected machines. Set 'days' to get daily utilization over a range. "
    "Utilization = spindle running during 6 AM - 7 PM shift hours. "
    "Machine IDs: M2, M3, M6, M8, T2.",
    {"type": "object", "properties": {"days": {"type": "integer", "description": "Number of days of history (default: today only)"}}, "required": []},
)
async def get_machine_utilization(args: dict[str, Any]) -> dict:
    try:
        focas = _get_focas()
        days = args.get("days")
        if days and days > 0:
            result = focas.get_utilization_range(days=days)
            return _json_response({"period_days": days, "machines": result})
        else:
            result = focas.get_utilization_today()
            return _json_response({"period": "today", "machines": result})
    except Exception as e:
        return _error_response(e)


@tool(
    "get_recent_alarms",
    "Get machine alarms from the FOCAS monitoring database. "
    "Returns alarm timestamps, machine IDs, alarm numbers, and messages.",
    {"type": "object", "properties": {"days": {"type": "integer", "description": "Number of days to look back (default: 7)"}}, "required": []},
)
async def get_recent_alarms(args: dict[str, Any]) -> dict:
    try:
        days = args.get("days", 7)
        alarms = _get_focas().get_recent_alarms(days=days)
        counts = _get_focas().get_alarm_counts(days=days)
        return _json_response({
            "period_days": days,
            "total_alarms": len(alarms),
            "by_machine": counts,
            "alarms": alarms[:50],  # Cap at 50 to avoid huge responses
        })
    except Exception as e:
        return _error_response(e)


@tool(
    "get_active_programs",
    "Get CNC programs that have been running recently on FOCAS-connected machines. "
    "Returns program numbers, machine IDs, run duration, and spindle/feed data. "
    "For T2 (lathe), legacy programs are resolved to ProShop part numbers via mapping.",
    {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Hours to look back (default: 4)"}}, "required": []},
)
async def get_active_programs(args: dict[str, Any]) -> dict:
    try:
        hours = args.get("hours_back", 4)
        programs = _get_focas().get_active_programs(hours_back=hours)
        # Enrich with legacy program mappings
        mappings = config.get_program_mappings()
        if mappings:
            for prog in programs:
                o_num = prog.get("program_number", "").upper()
                if o_num in mappings:
                    m = mappings[o_num]
                    prog["mapped_part_number"] = m.get("part_number")
                    prog["mapped_description"] = m.get("description")
                    prog["mapped_op_number"] = m.get("op_number")
        return _json_response({
            "period_hours": hours,
            "programs": programs,
        })
    except Exception as e:
        return _error_response(e)


# ==========================================================================
# AUDIT TOOLS
# ==========================================================================

@tool(
    "run_full_audit",
    "Execute a complete data quality audit across ProShop, FOCAS, and the filesystem. "
    "Runs 45+ checks across 8 categories and stores results in audit.db for trending. "
    "This takes 30-60 seconds to complete. Returns a summary with score and key findings.",
    {},
)
async def run_full_audit(args: dict[str, Any]) -> dict:
    try:
        ps = _get_proshop()
        focas = None
        try:
            focas = _get_focas()
        except FileNotFoundError:
            pass
        db = _get_audit_db()

        engine = AuditEngine(
            proshop_client=ps,
            focas_reader=focas,
            nc_programs_root=config.NC_PROGRAMS_ROOT,
            part_files_root=config.PART_FILES_ROOT,
        )

        start = time.time()
        findings, metrics, field_pops = engine.run_all()
        duration = time.time() - start

        # Store in audit.db
        from dataclasses import asdict
        run_id = db.start_run()
        for f in findings:
            db.add_finding(run_id, f.category, f.check_name, f.severity,
                           f.message, f.subject, f.details, f.auto_fixable)
        for name, (value, context) in metrics.items():
            db.add_metric(run_id, name, value, context)
        for field_name, level, total, populated in field_pops:
            db.add_field_population(run_id, field_name, level, total, populated)

        passed = sum(1 for f in findings if f.severity == "pass")
        warnings = sum(1 for f in findings if f.severity == "warning")
        failures = sum(1 for f in findings if f.severity == "failure")
        errors = sum(1 for f in findings if f.severity == "error")
        infos = sum(1 for f in findings if f.severity == "info")
        total = len(findings)

        score = round(100 * passed / total, 1) if total > 0 else 0
        if score >= 80:
            grade = "HEALTHY"
        elif score >= 60:
            grade = "WARNING"
        else:
            grade = "CRITICAL"

        db.finish_run(run_id, duration, total, passed, warnings, failures, errors,
                      f"Score: {score}% {grade}")

        summary = {
            "run_id": run_id,
            "duration_seconds": round(duration, 1),
            "score_pct": score,
            "grade": grade,
            "total_checks": total,
            "passed": passed,
            "infos": infos,
            "warnings": warnings,
            "failures": failures,
            "errors": errors,
            "key_metrics": {k: v[0] for k, v in metrics.items()},
            "top_failures": [
                {"category": f.category, "check": f.check_name,
                 "message": f.message, "subject": f.subject}
                for f in findings if f.severity in ("failure", "error")
            ][:10],
        }
        return _json_response(summary)
    except Exception as e:
        return _error_response(e)


@tool(
    "get_latest_audit",
    "Get the results of the most recent audit run from audit.db. "
    "Returns the run summary and optionally filtered findings. "
    "Use severity filter to focus on specific issue types.",
    {"type": "object", "properties": {"severity": {"type": "string", "description": "Filter findings by severity: pass, info, warning, failure, error (optional)"}}, "required": []},
)
async def get_latest_audit(args: dict[str, Any]) -> dict:
    try:
        db = _get_audit_db()
        run = db.get_latest_run()
        if not run:
            return _json_response({"error": "No audit runs found. Run a full audit first."})
        severity = args.get("severity")
        findings = db.get_run_findings(run["id"], severity=severity)
        return _json_response({
            "run": run,
            "findings_count": len(findings),
            "findings": findings,
        })
    except Exception as e:
        return _error_response(e)


@tool(
    "get_audit_history",
    "Get audit run history showing scores over time. "
    "Useful for answering 'is data quality improving or declining?'",
    {"type": "object", "properties": {"days": {"type": "integer", "description": "Number of days of history (default: 30)"}}, "required": []},
)
async def get_audit_history(args: dict[str, Any]) -> dict:
    try:
        db = _get_audit_db()
        days = args.get("days", 30)
        runs = db.get_run_history(days=days)
        return _json_response({
            "period_days": days,
            "total_runs": len(runs),
            "runs": runs,
        })
    except Exception as e:
        return _error_response(e)


@tool(
    "get_metric_trend",
    "Get the trend of a specific metric over time from audit history. "
    "Common metrics: overrun_rate_pct, total_hours_over_target, active_work_orders, "
    "active_operations, nc_programs_found_pct, alarms_7day, "
    "utilization_M2/M3/M6/M8/T2.",
    {"type": "object", "properties": {
        "metric_name": {"type": "string", "description": "Name of the metric to trend"},
        "days": {"type": "integer", "description": "Number of days of history (default: 30)"},
    }, "required": ["metric_name"]},
)
async def get_metric_trend(args: dict[str, Any]) -> dict:
    try:
        db = _get_audit_db()
        metric_name = args["metric_name"]
        days = args.get("days", 30)
        trend = db.get_metric_trend(metric_name, days=days)
        return _json_response({
            "metric": metric_name,
            "period_days": days,
            "data_points": len(trend),
            "trend": trend,
        })
    except Exception as e:
        return _error_response(e)


# ==========================================================================
# REMINDER TOOLS
# ==========================================================================

@tool(
    "schedule_reminder",
    "Schedule a Telegram reminder for a future date/time. "
    "The reminder will be sent via Telegram when the time arrives. "
    "Use ISO format for remind_at: 'YYYY-MM-DD HH:MM' (24-hour, local time). "
    "Examples: '2026-03-30 08:00', '2026-04-01 14:30'.",
    {"type": "object", "properties": {
        "message": {"type": "string", "description": "The reminder message to send"},
        "remind_at": {"type": "string", "description": "When to send the reminder (YYYY-MM-DD HH:MM)"},
    }, "required": ["message", "remind_at"]},
)
async def schedule_reminder(args: dict[str, Any]) -> dict:
    try:
        db = _get_audit_db()
        msg = args["message"]
        remind_at = args["remind_at"]
        # Normalize to full datetime string
        if len(remind_at) == 16:  # YYYY-MM-DD HH:MM
            remind_at += ":00"
        rid = db.add_reminder(msg, remind_at)
        return _json_response({
            "reminder_id": rid,
            "message": msg,
            "remind_at": remind_at,
            "status": "scheduled",
        })
    except Exception as e:
        return _error_response(e)


@tool(
    "list_reminders",
    "List all pending (unsent, uncanceled) reminders. "
    "Shows reminder ID, message, and scheduled time.",
    {},
)
async def list_reminders(args: dict[str, Any]) -> dict:
    try:
        db = _get_audit_db()
        reminders = db.get_pending_reminders()
        return _json_response({
            "count": len(reminders),
            "reminders": reminders,
        })
    except Exception as e:
        return _error_response(e)


@tool(
    "cancel_reminder",
    "Cancel a pending reminder by its ID. Use list_reminders to find the ID first.",
    {"type": "object", "properties": {
        "reminder_id": {"type": "integer", "description": "ID of the reminder to cancel"},
    }, "required": ["reminder_id"]},
)
async def cancel_reminder(args: dict[str, Any]) -> dict:
    try:
        db = _get_audit_db()
        success = db.cancel_reminder(args["reminder_id"])
        if success:
            return _json_response({"status": "canceled", "reminder_id": args["reminder_id"]})
        else:
            return _json_response({"error": f"Reminder {args['reminder_id']} not found or already sent"})
    except Exception as e:
        return _error_response(e)


# ==========================================================================
# SERVER CREATION
# ==========================================================================

def create_proshop_server():
    """Create the ProShop MCP server with all ProShop tools."""
    return create_sdk_mcp_server(
        name="proshop",
        version="1.0.0",
        tools=[
            check_proshop_health,
            get_active_work_orders,
            get_completed_work_orders,
            get_work_cells,
            get_work_order,
            get_work_order_time_tracking,
            get_work_order_profitability,
            get_part_info,
            get_part_operations,
            search_work_orders,
        ],
    )


def create_focas_server():
    """Create the FOCAS MCP server with all FOCAS tools."""
    return create_sdk_mcp_server(
        name="focas",
        version="1.0.0",
        tools=[
            check_focas_health,
            get_machine_utilization,
            get_recent_alarms,
            get_active_programs,
        ],
    )


def create_audit_server():
    """Create the Audit MCP server with all audit tools."""
    return create_sdk_mcp_server(
        name="audit",
        version="1.0.0",
        tools=[
            run_full_audit,
            get_latest_audit,
            get_audit_history,
            get_metric_trend,
        ],
    )


def create_reminders_server():
    """Create the Reminders MCP server."""
    return create_sdk_mcp_server(
        name="reminders",
        version="1.0.0",
        tools=[
            schedule_reminder,
            list_reminders,
            cancel_reminder,
        ],
    )
