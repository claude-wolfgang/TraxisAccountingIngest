"""
Traxis Manufacturing Telegram Bot.

Claude-powered shop intelligence assistant. Full access to ProShop ERP,
FOCAS machine monitoring, data quality audits, project management,
reminders, and notes -- all from your phone.

Usage:
    python telegram_bot.py              # Run the bot (long-running)
    python telegram_bot.py --test       # Send a test message and exit

Requires:
    TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars
    ANTHROPIC_API_KEY env var
    pip install python-telegram-bot anthropic
"""

import os
import sys
import json
import time
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
import anthropic

import config
from audit_db import AuditDB

# -- Setup ------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Console logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# File logging for errors
_err_handler = logging.FileHandler(LOG_DIR / "telegram_errors.log")
_err_handler.setLevel(logging.ERROR)
_err_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
log.addHandler(_err_handler)

PROJECT_DIR = Path(__file__).parent
ROOT_DIR = PROJECT_DIR.parent
INDEX_PATH = PROJECT_DIR / "project_index.json"
DB = AuditDB(config.AUDIT_DB_PATH)

ALLOWED_CHAT_ID = int(config.TELEGRAM_CHAT_ID) if config.TELEGRAM_CHAT_ID else None

claude = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

conversation_history = []
MAX_HISTORY = 60

# -- Health Tracking -------------------------------------------------------

HEALTH_PORT = 8100
_start_time = time.time()
_last_message_at = None
_messages_handled = 0


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint for Overseer monitoring."""

    def do_GET(self):
        if self.path == "/api/health":
            data = {
                "status": "ok",
                "uptime_seconds": int(time.time() - _start_time),
                "tools_loaded": len(TOOLS),
                "last_message_at": _last_message_at,
                "messages_handled": _messages_handled,
                "conversation_length": len(conversation_history),
            }
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging

    def write(self, data):
        self.wfile.write(data)


# -- Lazy Client Singletons ------------------------------------------------

_proshop = None
_focas = None
_audit_db = None


def _get_proshop():
    global _proshop
    if _proshop is None:
        from proshop_client import ProShopClient
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
        from focas_reader import FocasReader
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


# -- Project Index ----------------------------------------------------------

def load_project_index():
    if INDEX_PATH.exists():
        with open(INDEX_PATH) as f:
            return json.load(f)
    return {}


# -- Status Mapping (from mcp_tools.py) ------------------------------------

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


# -- System Prompt ----------------------------------------------------------

def build_system_prompt():
    index = load_project_index()
    now = datetime.now().strftime("%A, %B %d %Y %I:%M %p")

    # Latest audit score
    latest_run = DB.get_latest_run()
    if latest_run:
        audit_line = f"Latest audit: {latest_run.get('summary', 'N/A')} (run #{latest_run['id']}, {latest_run.get('timestamp', '?')})"
    else:
        audit_line = "No audit runs yet."

    # Pending reminders
    pending = DB.get_pending_reminders()
    if pending:
        reminder_lines = [f"- #{r['id']} at {r['remind_at']}: {r['message']}" for r in pending[:10]]
        reminders_text = "\n".join(reminder_lines)
    else:
        reminders_text = "None."

    # Recent notes
    recent_notes = DB.get_recent_notes(limit=5)
    if recent_notes:
        notes_lines = [f"- [{n['created_at'][:10]}] P{n['project_id'] or '?'}: {n['text'][:80]}" for n in recent_notes]
        notes_text = "\n".join(notes_lines)
    else:
        notes_text = "None."

    # Project summary (compact)
    active_projects = []
    blocked_projects = []
    for p in index.get("projects", []):
        if p.get("status") == "active":
            active_projects.append(f"P{p['id']}: {p['name']}")
        if p.get("waiting_on"):
            blocked_projects.append(f"P{p['id']}: {p['waiting_on'][:60]}")

    people = index.get("company", {}).get("people", {})
    people_text = "\n".join(f"- {name}: {role}" for name, role in people.items())

    return f"""\
You are the Traxis Manufacturing shop intelligence assistant on Telegram.
You help Wolfgang (the owner) run a 5-person precision CNC job shop from his phone.

Current date/time: {now}

## Shop Context
- 8 mills + 2 lathes. FOCAS-connected: M2 (Fanuc), M3 (Fanuc), M6 (Chevalier/Fanuc), M8 (Hyundai-Wia KF5600II), T2 (YCM NTC1600LY lathe)
- ERP: ProShop (GraphQL API). WO format: YY-NNNN (e.g., 26-0042)
- CAM: Fusion 360. NC programs stored in Dropbox/NC Programs/<customerPartNumber>/
- Collector PC: 10.1.1.71 runs Overseer, dashboards, services
- Kiosk PC: 10.1.1.142 for tool assembly management

## Team
{people_text}

## Machine Map
| ProShop | FOCAS | Machine | Connected |
|---------|-------|---------|-----------|
| Mill-1 | -- | Haas VF-5 | No |
| Mill-2 | M2 | Fanuc Mill 2 | Yes |
| Mill-3 | M3 | Fanuc Mill 3 | Yes (intermittent) |
| Mill-6 | M6 | Fanuc Mill 6 | Yes |
| Mill-8 | M8 | Hyundai-Wia KF5600II | Yes |
| Lathe-2 | T2 | YCM NTC1600LY | Yes |

## Live Data
{audit_line}
Active projects: {len(active_projects)}
Blocked: {len(blocked_projects)}

## Pending Reminders
{reminders_text}

## Recent Notes
{notes_text}

## Data Quality Notes
- ProShop scheduledEndDate is 0% populated -- don't trust it
- qtyComplete is always 0 in ProShop -- use perOpQtyComplete from ops instead
- certifiedToRun is 2% true -- mostly unfilled, not necessarily uncertified
- minutesPerPart only 27% populated -- use hoursCurrentTarget for estimates
- FOCAS data on this PC is Dropbox sync copy, may be stale vs collector PC

## Behavior Rules
- Keep responses SHORT. This is a phone. No walls of text.
- Use plain text, minimal formatting. Telegram supports *bold* and _italic_ only.
- Lead with the answer, then context. Don't restate the question.
- When using tools, pick the most targeted one. Don't fetch everything when one WO will do.
- For overrun questions, use get_overrun_summary (active) or get_completed_work_orders (historical).
- If a tool fails, say what went wrong clearly. Don't retry silently.
- When saving notes, confirm what was saved and any project tag.
- When scheduling reminders, confirm the exact date/time.
- If asked "what needs attention?" lead with highest-impact items: overdue jobs, alarms, blocked projects.
- WO numbers: always YY-NNNN format. If the user says "42" they probably mean the most recent WO ending in that number.
"""


# -- Tool Definitions (Anthropic SDK format) --------------------------------

TOOLS = [
    # ---- ProShop (10) ----
    {
        "name": "check_proshop_health",
        "description": "Check ProShop API connectivity and auth status. Returns healthy/unhealthy, active WO count, token age.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_active_work_orders",
        "description": "Get all active work orders with operations, hours, due dates, part info. Returns full list -- use for broad questions about the shop floor.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_completed_work_orders",
        "description": "Get completed/shipped/invoiced WOs for historical overrun analysis. Returns target vs actual hours per job.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_work_cells",
        "description": "Get all work cells (machines) configured in ProShop with names, types, active status.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_work_order",
        "description": "Get a single work order by number. Fast targeted lookup. WO numbers are YY-NNNN format (e.g. 26-0042).",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number": {"type": "string", "description": "Work order number (e.g. 26-0042)"},
            },
            "required": ["wo_number"],
        },
    },
    {
        "name": "get_work_order_time_tracking",
        "description": "Get time tracking entries for a work order: labor hours, setup hours, individual time clock entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number": {"type": "string", "description": "Work order number (e.g. 26-0042)"},
            },
            "required": ["wo_number"],
        },
    },
    {
        "name": "get_work_order_profitability",
        "description": "Get profitability data: DLH, profit, profit margin, total cost per job. Useful for financial analysis.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_part_info",
        "description": "Get part details by part number: partNumber, partDescription, family, customerPartNumber. Case-sensitive.",
        "input_schema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "Part number (case-sensitive, e.g. TRA1-TEMP)"},
            },
            "required": ["part_number"],
        },
    },
    {
        "name": "get_part_operations",
        "description": "Get master routing (operations list) for a part: op numbers, descriptions, setup/run times (in seconds).",
        "input_schema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "Part number (case-sensitive)"},
            },
            "required": ["part_number"],
        },
    },
    {
        "name": "search_work_orders",
        "description": "Search/filter work orders by status or due date. Filters: open, active, complete, shipped, invoiced, canceled, late (past due), due this week.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Filter: open, active, complete, shipped, late, due this week, canceled"},
            },
            "required": ["filter"],
        },
    },
    # ---- FOCAS (4) ----
    {
        "name": "check_focas_health",
        "description": "Check FOCAS machine monitoring database health: per-machine last sample time, staleness, sample counts. Machines: M2, M3, M6, M8, T2.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_machine_utilization",
        "description": "Get machine utilization (spindle running during 6AM-7PM shift). No args = today. Set days for historical range. Machine IDs: M2, M3, M6, M8, T2.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of history (omit for today only)"},
            },
        },
    },
    {
        "name": "get_recent_alarms",
        "description": "Get machine alarms: timestamps, machine IDs, alarm numbers, messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Days to look back (default: 7)"},
            },
        },
    },
    {
        "name": "get_active_programs",
        "description": "Get CNC programs running recently on FOCAS machines. Returns program numbers, machine IDs, run duration, spindle/feed data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_back": {"type": "integer", "description": "Hours to look back (default: 4)"},
            },
        },
    },
    # ---- Audit (4) ----
    {
        "name": "run_full_audit",
        "description": "Run complete data quality audit (45+ checks, 8 categories). Takes 30-60 seconds. Returns score, grade, key findings.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_latest_audit",
        "description": "Get most recent audit results from audit.db. Optionally filter findings by severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "description": "Filter: pass, info, warning, failure, error (optional)"},
            },
        },
    },
    {
        "name": "get_audit_history",
        "description": "Get audit run history showing scores over time. Answers 'is data quality improving?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Days of history (default: 30)"},
            },
        },
    },
    {
        "name": "get_metric_trend",
        "description": "Get trend of a specific metric over time. Common: overrun_rate_pct, active_work_orders, nc_programs_found_pct, alarms_7day, utilization_M2/M3/M6/M8/T2.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_name": {"type": "string", "description": "Metric name to trend"},
                "days": {"type": "integer", "description": "Days of history (default: 30)"},
            },
            "required": ["metric_name"],
        },
    },
    # ---- Reminders (3) ----
    {
        "name": "schedule_reminder",
        "description": "Schedule a Telegram reminder. Use YYYY-MM-DD HH:MM format.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Reminder message"},
                "remind_at": {"type": "string", "description": "When to remind (YYYY-MM-DD HH:MM)"},
            },
            "required": ["message", "remind_at"],
        },
    },
    {
        "name": "list_reminders",
        "description": "List all pending (unsent, uncanceled) reminders.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a pending reminder by ID. Use list_reminders to find the ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {"type": "integer", "description": "Reminder ID to cancel"},
            },
            "required": ["reminder_id"],
        },
    },
    # ---- Notes (2) ----
    {
        "name": "save_note",
        "description": "Save a thought, idea, or note. Optionally tag to a project number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The note text"},
                "project_id": {"type": "integer", "description": "Project number (1-27) if relevant"},
                "tags": {"type": "string", "description": "Comma-separated tags (optional)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "search_notes",
        "description": "Search saved notes by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
    # ---- New Tools (5) ----
    {
        "name": "get_project_index",
        "description": "Get project status from the 27-project index. Filter by project number, status (active/stalled/complete/retired), or text search. No args = full list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Project number (e.g. '19'), status keyword (e.g. 'active'), or text search"},
            },
        },
    },
    {
        "name": "get_scheduler_briefing",
        "description": "Get the latest scheduler briefing report from Project 19 (Shop Scheduler). Shows job readiness, machine openings, bottlenecks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_overrun_summary",
        "description": "Get active work orders ranked by overrun (worst first). Shows WO number, part, planned hours, actual hours, overrun %. Use for 'what jobs are overrunning?'",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "write_note_to_project",
        "description": "Append a timestamped note to a project's notes.md file. Creates the file if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project number (1-27)"},
                "note_text": {"type": "string", "description": "Note content to append"},
            },
            "required": ["project_id", "note_text"],
        },
    },
    {
        "name": "get_nc_program_status",
        "description": "Check if NC programs exist for a work order or part. Searches the NC Programs filesystem by customerPartNumber.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number_or_part": {"type": "string", "description": "Work order number (e.g. 26-0042) or part number"},
            },
            "required": ["wo_number_or_part"],
        },
    },
]


# -- Tool Execution ---------------------------------------------------------

def execute_tool(name, args):
    """Execute a tool and return the result as a string."""
    try:
        # ---- ProShop tools ----
        if name == "check_proshop_health":
            result = _get_proshop().check_health()
            return json.dumps(result, default=str, indent=2)

        elif name == "get_active_work_orders":
            data = _get_proshop().get_all_active_work_orders()
            records = data.get("records", [])
            summary = {
                "total_records": data.get("totalRecords", 0),
                "work_orders": [],
            }
            for wo in records:
                ops = (wo.get("ops") or {}).get("records", [])
                active_ops = [op for op in ops if not op.get("isOpComplete")]
                try:
                    target_f = float(wo.get("hoursCurrentTarget") or 0)
                    spent_f = float(wo.get("hoursTotalSpent") or 0)
                except (ValueError, TypeError):
                    target_f, spent_f = 0, 0
                summary["work_orders"].append({
                    "workOrderNumber": wo.get("workOrderNumber"),
                    "partNumber": (wo.get("part") or {}).get("partNumber"),
                    "partDescription": (wo.get("part") or {}).get("partDescription"),
                    "customerPartNumber": (wo.get("part") or {}).get("customerPartNumber"),
                    "family": (wo.get("part") or {}).get("family"),
                    "status": wo.get("status"),
                    "dueDate": wo.get("dueDate"),
                    "quantityOrdered": wo.get("quantityOrdered"),
                    "hoursTarget": target_f,
                    "hoursSpent": spent_f,
                    "hoursOver": round(spent_f - target_f, 1) if target_f > 0 else None,
                    "programmingPct": wo.get("programmingPercentComplete"),
                    "totalOps": len(ops),
                    "activeOps": len(active_ops),
                })
            return json.dumps(summary, default=str, indent=2)

        elif name == "get_completed_work_orders":
            records = _get_proshop().get_completed_work_orders()
            results = []
            for wo in records:
                try:
                    target_f = float(wo.get("hoursCurrentTarget") or 0)
                    spent_f = float(wo.get("hoursTotalSpent") or 0)
                except (ValueError, TypeError):
                    target_f, spent_f = 0, 0
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
                "overrunning": len([r for r in results if (r["overrunPct"] or 0) > 0]),
                "work_orders": results,
            }
            return json.dumps(summary, default=str, indent=2)

        elif name == "get_work_cells":
            result = _get_proshop().get_work_cells()
            return json.dumps(result, default=str, indent=2)

        elif name == "get_work_order":
            wo = _get_proshop().get_work_order(args["wo_number"])
            if not wo:
                return json.dumps({"error": f"Work order {args['wo_number']} not found"})
            ops = (wo.get("ops") or {}).get("records", [])
            wo["ops"] = ops
            return json.dumps(wo, default=str, indent=2)

        elif name == "get_work_order_time_tracking":
            wo = _get_proshop().get_work_order_time_tracking(args["wo_number"])
            if not wo:
                return json.dumps({"error": f"Work order {args['wo_number']} not found"})
            return json.dumps(wo, default=str, indent=2)

        elif name == "get_work_order_profitability":
            data = _get_proshop().get_work_order_profitability()
            records = data.get("records", [])
            with_profit = [r for r in records if r.get("profitability")]
            return json.dumps({
                "total_records": len(records),
                "with_profitability_data": len(with_profit),
                "work_orders": with_profit,
            }, default=str, indent=2)

        elif name == "get_part_info":
            part = _get_proshop().get_part(args["part_number"])
            if not part:
                return json.dumps({"error": f"Part {args['part_number']} not found"})
            return json.dumps(part, default=str, indent=2)

        elif name == "get_part_operations":
            part = _get_proshop().get_part_operations(args["part_number"])
            if not part:
                return json.dumps({"error": f"Part {args['part_number']} not found"})
            return json.dumps(part, default=str, indent=2)

        elif name == "search_work_orders":
            return _execute_search_work_orders(args)

        # ---- FOCAS tools ----
        elif name == "check_focas_health":
            result = _get_focas().check_health()
            return json.dumps(result, default=str, indent=2)

        elif name == "get_machine_utilization":
            focas = _get_focas()
            days = args.get("days")
            if days and days > 0:
                result = focas.get_utilization_range(days=days)
                return json.dumps({"period_days": days, "machines": result}, default=str, indent=2)
            else:
                result = focas.get_utilization_today()
                return json.dumps({"period": "today", "machines": result}, default=str, indent=2)

        elif name == "get_recent_alarms":
            days = args.get("days", 7)
            alarms = _get_focas().get_recent_alarms(days=days)
            counts = _get_focas().get_alarm_counts(days=days)
            return json.dumps({
                "period_days": days,
                "total_alarms": len(alarms),
                "by_machine": counts,
                "alarms": alarms[:50],
            }, default=str, indent=2)

        elif name == "get_active_programs":
            hours = args.get("hours_back", 4)
            programs = _get_focas().get_active_programs(hours_back=hours)
            mappings = config.get_program_mappings()
            if mappings:
                for prog in programs:
                    o_num = prog.get("program_number", "")
                    o_key = f"O{o_num}" if isinstance(o_num, int) else str(o_num).upper()
                    if o_key in mappings:
                        m = mappings[o_key]
                        prog["mapped_part_number"] = m.get("part_number")
                        prog["mapped_description"] = m.get("description")
            return json.dumps({"period_hours": hours, "programs": programs}, default=str, indent=2)

        # ---- Audit tools ----
        elif name == "run_full_audit":
            return _execute_run_full_audit()

        elif name == "get_latest_audit":
            db = _get_audit_db()
            run = db.get_latest_run()
            if not run:
                return json.dumps({"error": "No audit runs found. Run a full audit first."})
            severity = args.get("severity")
            findings = db.get_run_findings(run["id"], severity=severity)
            return json.dumps({
                "run": run,
                "findings_count": len(findings),
                "findings": findings[:50],
            }, default=str, indent=2)

        elif name == "get_audit_history":
            db = _get_audit_db()
            days = args.get("days", 30)
            runs = db.get_run_history(days=days)
            return json.dumps({
                "period_days": days,
                "total_runs": len(runs),
                "runs": runs,
            }, default=str, indent=2)

        elif name == "get_metric_trend":
            db = _get_audit_db()
            metric_name = args["metric_name"]
            days = args.get("days", 30)
            trend = db.get_metric_trend(metric_name, days=days)
            return json.dumps({
                "metric": metric_name,
                "period_days": days,
                "data_points": len(trend),
                "trend": trend,
            }, default=str, indent=2)

        # ---- Reminders ----
        elif name == "schedule_reminder":
            remind_at = args["remind_at"]
            if len(remind_at) == 16:
                remind_at += ":00"
            rid = DB.add_reminder(args["message"], remind_at)
            return f"Reminder #{rid} scheduled for {args['remind_at']}."

        elif name == "list_reminders":
            pending = DB.get_pending_reminders()
            if not pending:
                return "No pending reminders."
            lines = [f"#{r['id']} | {r['remind_at']} | {r['message']}" for r in pending]
            return "\n".join(lines)

        elif name == "cancel_reminder":
            ok = DB.cancel_reminder(args["reminder_id"])
            return f"Reminder #{args['reminder_id']} canceled." if ok else f"Reminder #{args['reminder_id']} not found or already sent."

        # ---- Notes ----
        elif name == "save_note":
            nid = DB.add_note(
                args["text"],
                project_id=args.get("project_id"),
                tags=args.get("tags"),
            )
            project_label = f" (tagged to P{args['project_id']})" if args.get("project_id") else ""
            return f"Note #{nid} saved{project_label}."

        elif name == "search_notes":
            results = DB.search_notes(args["query"])
            if not results:
                return f"No notes matching '{args['query']}'."
            lines = [f"#{n['id']} [{n['created_at']}] P{n['project_id'] or '?'}: {n['text']}" for n in results]
            return "\n".join(lines)

        # ---- New tools ----
        elif name == "get_project_index":
            return _execute_get_project_index(args)

        elif name == "get_scheduler_briefing":
            return _execute_get_scheduler_briefing()

        elif name == "get_overrun_summary":
            return _execute_get_overrun_summary()

        elif name == "write_note_to_project":
            return _execute_write_note_to_project(args)

        elif name == "get_nc_program_status":
            return _execute_get_nc_program_status(args)

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        log.error(f"Tool {name} failed: {e}", exc_info=True)
        return f"Error in {name}: {str(e)[:300]}"


# -- Complex Tool Implementations ------------------------------------------

def _execute_search_work_orders(args):
    """Search/filter work orders."""
    filter_str = args["filter"].lower().strip()
    ps = _get_proshop()

    if filter_str in ("complete", "shipped", "invoiced", "closed"):
        records = ps.get_completed_work_orders()
        target_statuses = _STATUS_MAP.get(filter_str, [filter_str.title()])
        filtered = [wo for wo in records if wo.get("status") in target_statuses]
        return json.dumps({"filter": filter_str, "count": len(filtered), "work_orders": filtered[:50]}, default=str, indent=2)

    data = ps.get_all_active_work_orders()
    records = data.get("records", [])
    today = datetime.now().date()

    if filter_str in ("late", "overdue", "past due"):
        filtered = [wo for wo in records if _parse_date(wo.get("dueDate")) and _parse_date(wo.get("dueDate")) < today]
        label = f"late (due before {today})"
    elif filter_str in ("due this week", "this week"):
        week_end = today + timedelta(days=(6 - today.weekday()))
        filtered = [wo for wo in records if _parse_date(wo.get("dueDate")) and today <= _parse_date(wo.get("dueDate")) <= week_end]
        label = f"due {today} - {week_end}"
    else:
        target_statuses = _STATUS_MAP.get(filter_str, [filter_str.title()])
        filtered = [wo for wo in records if wo.get("status") in target_statuses]
        label = f"status in {target_statuses}"

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
    return json.dumps({"filter": label, "count": len(results), "work_orders": results[:50]}, default=str, indent=2)


def _execute_run_full_audit():
    """Run full data quality audit."""
    from audit_engine import AuditEngine

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

    run_id = db.start_run()
    for f in findings:
        db.add_finding(run_id, f.category, f.check_name, f.severity,
                       f.message, f.subject, f.details, f.auto_fixable)
    for mname, (value, context) in metrics.items():
        db.add_metric(run_id, mname, value, context)
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
    return json.dumps(summary, default=str, indent=2)


def _execute_get_project_index(args):
    """Get project index, optionally filtered."""
    index = load_project_index()
    projects = index.get("projects", [])
    filter_str = args.get("filter", "").strip()

    if filter_str:
        # Try numeric project ID first
        try:
            pid = int(filter_str)
            projects = [p for p in projects if p["id"] == pid]
        except ValueError:
            # Status keyword or text search
            fl = filter_str.lower()
            if fl in ("active", "stalled", "complete", "retired", "investigation"):
                projects = [p for p in projects if p.get("status") == fl]
            else:
                projects = [p for p in projects if
                            fl in p.get("name", "").lower() or
                            fl in p.get("short", "").lower() or
                            fl in json.dumps(p.get("subprojects", [])).lower()]

    results = []
    for p in projects:
        entry = {
            "id": p["id"],
            "name": p["name"],
            "status": p.get("status"),
            "short": p.get("short"),
        }
        if p.get("waiting_on"):
            entry["waiting_on"] = p["waiting_on"]
        if p.get("needs_from_user"):
            entry["needs_from_user"] = p["needs_from_user"]
        if p.get("subprojects"):
            entry["subprojects"] = p["subprojects"]
        if p.get("affects"):
            entry["affects"] = p["affects"]
        results.append(entry)

    return json.dumps({"count": len(results), "projects": results}, default=str, indent=2)


def _execute_get_scheduler_briefing():
    """Read the latest scheduler briefing from Project 19."""
    # Check for scheduler briefing files
    briefing_paths = [
        ROOT_DIR / "19. Shop Scheduler" / "SCHEDULER_BRIEFING_RESULTS.md",
        ROOT_DIR / "19. Shop Scheduler" / "CC_SCHEDULER_BRIEFING.md",
    ]
    # Also check for a priority engine report
    priority_report = ROOT_DIR / "19. Shop Scheduler" / "reports"
    if priority_report.exists():
        # Look for latest.md or most recent report
        latest = priority_report / "latest.md"
        if latest.exists():
            briefing_paths.insert(0, latest)

    for path in briefing_paths:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                # Truncate if very long for Telegram context
                if len(content) > 6000:
                    content = content[:6000] + "\n\n... (truncated, full file at " + str(path) + ")"
                return f"Source: {path.name}\n\n{content}"
            except Exception as e:
                return f"Error reading {path}: {e}"

    return "No scheduler briefing file found. Available paths checked:\n" + "\n".join(f"- {p}" for p in briefing_paths)


def _execute_get_overrun_summary():
    """Get active WOs ranked by overrun."""
    data = _get_proshop().get_all_active_work_orders()
    records = data.get("records", [])
    overruns = []

    for wo in records:
        try:
            target_f = float(wo.get("hoursCurrentTarget") or 0)
            spent_f = float(wo.get("hoursTotalSpent") or 0)
        except (ValueError, TypeError):
            target_f, spent_f = 0, 0

        if target_f <= 0:
            continue

        over_hours = round(spent_f - target_f, 1)
        over_pct = round((spent_f / target_f - 1) * 100, 1)

        overruns.append({
            "workOrderNumber": wo.get("workOrderNumber"),
            "partNumber": (wo.get("part") or {}).get("partNumber"),
            "customerPartNumber": (wo.get("part") or {}).get("customerPartNumber"),
            "dueDate": wo.get("dueDate"),
            "hoursTarget": target_f,
            "hoursSpent": spent_f,
            "hoursOver": over_hours,
            "overrunPct": over_pct,
        })

    # Sort worst first
    overruns.sort(key=lambda x: x["overrunPct"], reverse=True)

    # Split into overrunning vs on track
    over = [x for x in overruns if x["overrunPct"] > 0]
    under = [x for x in overruns if x["overrunPct"] <= 0]

    total_target = sum(x["hoursTarget"] for x in overruns)
    total_spent = sum(x["hoursSpent"] for x in overruns)
    total_over = sum(x["hoursOver"] for x in over) if over else 0

    return json.dumps({
        "summary": {
            "total_active_with_hours": len(overruns),
            "overrunning": len(over),
            "on_track": len(under),
            "total_hours_target": round(total_target, 1),
            "total_hours_spent": round(total_spent, 1),
            "total_hours_over": round(total_over, 1),
        },
        "worst_overruns": over[:15],
        "best_performers": under[-5:] if under else [],
    }, default=str, indent=2)


def _execute_write_note_to_project(args):
    """Append a timestamped note to a project folder."""
    pid = args["project_id"]
    note_text = args["note_text"]
    index = load_project_index()

    # Find the project folder
    target_dir = None
    for p in index.get("projects", []):
        if p["id"] == pid:
            # Find the matching folder
            for item in ROOT_DIR.iterdir():
                if item.is_dir() and item.name.startswith(f"{pid}."):
                    target_dir = item
                    break
            break

    if not target_dir:
        # Fallback: scan directory
        for item in ROOT_DIR.iterdir():
            if item.is_dir() and item.name.startswith(f"{pid}."):
                target_dir = item
                break

    if not target_dir:
        return f"Project folder for P{pid} not found."

    notes_file = target_dir / "notes.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = f"\n## {timestamp}\n{note_text}\n"

    if notes_file.exists():
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(entry)
    else:
        with open(notes_file, "w", encoding="utf-8") as f:
            f.write(f"# Project {pid} Notes\n{entry}")

    return f"Note appended to {notes_file.relative_to(ROOT_DIR)}"


def _execute_get_nc_program_status(args):
    """Check NC program filesystem for a WO or part."""
    query = args["wo_number_or_part"]

    # Determine if it's a WO number or part number
    customer_part = None
    wo_info = None

    if "-" in query and len(query) <= 8:
        # Looks like a WO number
        try:
            wo = _get_proshop().get_work_order(query)
            if wo:
                wo_info = {
                    "workOrderNumber": wo.get("workOrderNumber"),
                    "partNumber": (wo.get("part") or {}).get("partNumber"),
                    "customerPartNumber": (wo.get("part") or {}).get("customerPartNumber"),
                }
                customer_part = wo_info["customerPartNumber"]
        except Exception as e:
            return f"Error looking up WO {query}: {e}"
    else:
        # Treat as part number -- look up customerPartNumber
        try:
            part = _get_proshop().get_part(query)
            if part:
                customer_part = part.get("customerPartNumber")
                wo_info = {"partNumber": query, "customerPartNumber": customer_part}
            else:
                # Maybe it IS the customerPartNumber already
                customer_part = query
                wo_info = {"customerPartNumber": query}
        except Exception as e:
            return f"Error looking up part {query}: {e}"

    if not customer_part:
        return json.dumps({
            "status": "no_customer_part",
            "message": f"Could not determine customerPartNumber for '{query}'",
            "wo_info": wo_info,
        }, default=str, indent=2)

    # Check NC Programs filesystem
    if not config.NC_PROGRAMS_ROOT or not config.NC_PROGRAMS_ROOT.exists():
        return json.dumps({
            "status": "filesystem_unavailable",
            "message": "NC Programs root directory not found",
            "customerPartNumber": customer_part,
        }, default=str, indent=2)

    nc_dir = config.NC_PROGRAMS_ROOT / customer_part
    if nc_dir.exists() and nc_dir.is_dir():
        # List contents
        files = sorted(nc_dir.iterdir())
        nc_files = [f.name for f in files if f.suffix.lower() in (".nc", ".txt", ".tap", ".gcode", ".mpf")]
        all_files = [f.name for f in files[:20]]
        return json.dumps({
            "status": "found",
            "customerPartNumber": customer_part,
            "path": str(nc_dir),
            "nc_program_count": len(nc_files),
            "nc_files": nc_files[:20],
            "total_files": len(list(nc_dir.iterdir())),
            "sample_files": all_files,
            "wo_info": wo_info,
        }, default=str, indent=2)
    else:
        # Check for partial matches
        matches = []
        if config.NC_PROGRAMS_ROOT.exists():
            cp_lower = customer_part.lower()
            for d in config.NC_PROGRAMS_ROOT.iterdir():
                if d.is_dir() and cp_lower in d.name.lower():
                    matches.append(d.name)

        return json.dumps({
            "status": "not_found",
            "customerPartNumber": customer_part,
            "expected_path": str(nc_dir),
            "similar_folders": matches[:5],
            "wo_info": wo_info,
        }, default=str, indent=2)


# -- Claude Conversation ----------------------------------------------------

def chat(user_message):
    """Send a message to Claude with tools and conversation history. Returns response text."""
    global conversation_history

    conversation_history.append({"role": "user", "content": user_message})

    # Trim history
    if len(conversation_history) > MAX_HISTORY * 2:
        conversation_history = conversation_history[-(MAX_HISTORY * 2):]

    system_prompt = build_system_prompt()

    # Loop for tool use
    while True:
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=conversation_history,
        )

        assistant_content = response.content
        conversation_history.append({"role": "assistant", "content": assistant_content})

        tool_uses = [b for b in assistant_content if b.type == "tool_use"]
        if not tool_uses:
            text_parts = [b.text for b in assistant_content if b.type == "text"]
            return "\n".join(text_parts) if text_parts else "(no response)"

        # Execute tools and feed results back
        tool_results = []
        for tu in tool_uses:
            result = execute_tool(tu.name, tu.input)
            log.info(f"Tool {tu.name}({json.dumps(tu.input)[:80]}) -> {result[:100]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })

        conversation_history.append({"role": "user", "content": tool_results})


# -- Message Chunking -------------------------------------------------------

def chunk_message(text, max_len=4000):
    """Split text into Telegram-friendly chunks at paragraph boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""

    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > max_len:
            if current:
                chunks.append(current.strip())
                current = ""
            # If a single paragraph is too long, split at line boundaries
            if len(paragraph) > max_len:
                for line in paragraph.split("\n"):
                    if len(current) + len(line) + 1 > max_len:
                        if current:
                            chunks.append(current.strip())
                        current = line + "\n"
                    else:
                        current += line + "\n"
            else:
                current = paragraph + "\n\n"
        else:
            current += paragraph + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_len]]


# -- Telegram Handlers ------------------------------------------------------

async def _send_typing(context, chat_id):
    """Send typing indicator."""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:
        pass


async def _send_chunked(update, text):
    """Send a response, splitting into chunks if needed."""
    chunks = chunk_message(text)
    for i, chunk in enumerate(chunks):
        await update.message.reply_text(chunk)
        if i < len(chunks) - 1:
            await asyncio.sleep(0.3)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages."""
    global _last_message_at, _messages_handled

    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        log.warning(f"Ignoring message from unauthorized chat {update.effective_chat.id}")
        return

    user_text = update.message.text
    log.info(f"Received: {user_text[:100]}")

    _last_message_at = datetime.now().isoformat(timespec="seconds")
    _messages_handled += 1

    await _send_typing(context, update.effective_chat.id)

    try:
        response = chat(user_text)
        await _send_chunked(update, response)
    except Exception as e:
        log.error(f"Error processing message: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {str(e)[:200]}")


# -- Slash Commands ---------------------------------------------------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status -- shop digest: overruns + audit score."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await _send_typing(context, update.effective_chat.id)
    response = chat("Give me a quick shop status digest: top overrunning jobs, latest audit score, any alarms or issues. Keep it concise, 5-6 bullet points max.")
    await _send_chunked(update, response)


async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/notes -- show recent notes."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    notes = DB.get_recent_notes(limit=10)
    if not notes:
        await update.message.reply_text("No notes yet. Just text me any thought and I'll save it.")
        return
    lines = [f"#{n['id']} [{n['created_at'][:10]}] P{n['project_id'] or '?'}: {n['text']}" for n in notes]
    await _send_chunked(update, "\n\n".join(lines))


async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reminders -- show pending reminders."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    pending = DB.get_pending_reminders()
    if not pending:
        await update.message.reply_text("No pending reminders.")
        return
    lines = [f"#{r['id']} | {r['remind_at']} | {r['message']}" for r in pending]
    await _send_chunked(update, "\n\n".join(lines))


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/projects -- list all projects grouped by status."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    index = load_project_index()
    groups = {}
    for p in index.get("projects", []):
        status = p.get("status", "unknown")
        if status not in groups:
            groups[status] = []
        groups[status].append(p)

    lines = []
    for status in ["active", "investigation", "stalled", "complete", "retired"]:
        if status in groups:
            lines.append(f"*{status.upper()}*")
            for p in groups[status]:
                icon = {"active": ">>", "complete": "OK", "stalled": "..", "retired": "xx", "investigation": "??"}.get(status, "  ")
                lines.append(f"  [{icon}] P{p['id']:2d}: {p['name']}")
            lines.append("")

    await _send_chunked(update, "\n".join(lines))


async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/audit -- run full data quality audit."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await update.message.reply_text("Running full audit (30-60 seconds)...")
    await _send_typing(context, update.effective_chat.id)
    response = chat("Run a full data quality audit and give me the summary: score, grade, top issues. Keep the response concise.")
    await _send_chunked(update, response)


async def cmd_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/machines -- get machine utilization for today."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await _send_typing(context, update.effective_chat.id)
    response = chat("Show me today's machine utilization for all FOCAS machines. Format as a quick list with machine name and utilization %.")
    await _send_chunked(update, response)


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/briefing -- get scheduler briefing."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await _send_typing(context, update.effective_chat.id)
    response = chat("Get the scheduler briefing and summarize the key points: what machines are opening, what jobs are ready, what's blocked.")
    await _send_chunked(update, response)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help -- list all commands."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    help_text = """\
Traxis Bot Commands:

/status -- Shop digest (overruns, audit, alerts)
/machines -- Today's machine utilization
/audit -- Run full data quality audit (~60s)
/briefing -- Scheduler briefing report
/projects -- All 27 projects by status
/notes -- Recent saved notes
/reminders -- Pending reminders
/help -- This message

Or just text me anything:
- "What jobs are overrunning?"
- "Show me WO 26-0042"
- "What's running on M6?"
- "Remind me to check titanium order tomorrow at 9am"
- "Save note: need to order more 6061 bar stock"
- "What's the status of project 19?"
- "Run an audit"
- "Any alarms this week?"
"""
    await update.message.reply_text(help_text)


# -- Main -------------------------------------------------------------------

def test_message():
    """Send a test message to verify the bot works."""
    import requests
    text = "Traxis Bot v2 is online. 28 tools loaded. Send /help for commands."
    resp = requests.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=10,
    )
    if resp.ok:
        print("Test message sent!")
    else:
        print(f"Failed: {resp.status_code} {resp.text[:200]}")


def main():
    if "--test" in sys.argv:
        test_message()
        return

    if not config.TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    if not config.ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    log.info("Starting Traxis Telegram Bot v2...")
    log.info(f"Allowed chat ID: {ALLOWED_CHAT_ID}")
    log.info(f"Project index: {INDEX_PATH} ({'found' if INDEX_PATH.exists() else 'MISSING'})")
    log.info(f"Tools loaded: {len(TOOLS)}")
    log.info(f"NC Programs root: {config.NC_PROGRAMS_ROOT}")
    log.info(f"FOCAS DB: {config.get_focas_db_path()}")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("machines", cmd_machines))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("help", cmd_help))

    # Catch-all for text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start health endpoint for Overseer monitoring
    try:
        health_server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
        threading.Thread(target=health_server.serve_forever, daemon=True).start()
        log.info("Health endpoint listening on port %d", HEALTH_PORT)
    except Exception as e:
        log.warning("Could not start health endpoint on port %d: %s", HEALTH_PORT, e)

    log.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
