#!/usr/bin/env python3
"""
Traxis Service Overseer v1.2
=============================
Monitors and manages Traxis automation services.
Auto-restarts failed services. Provides a status dashboard.

Supports two service types:
  - process: Python scripts managed via subprocess (start/stop/restart)
  - windows_service: Windows Services monitored via sc query + SQLite DB checks

Usage:
    python overseer.py
    Then open http://localhost:8060 in a browser.

Dependencies:
    pip install flask requests
"""

import os
import sys
import json
import time
import threading
import logging
import subprocess
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import deque

try:
    from flask import Flask, jsonify, send_file, request
    import requests as http_requests
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: py -m pip install flask requests")
    sys.exit(1)

# ============================================================================
# LOGGING
# ============================================================================

LOG_DIR = Path(__file__).parent
LOG_FILE = LOG_DIR / "overseer.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Overseer")

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
log.addHandler(_file_handler)

# ============================================================================
# CONFIGURATION
# ============================================================================

HOST = "0.0.0.0"
PORT = 8060
CHECK_INTERVAL = 60
STARTUP_GRACE = 30
MAX_EVENTS = 200

PYTHON_EXE = r"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe"
PYTHONW_EXE = r"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\pythonw.exe"
BASE_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations")

PROGRAMMING_LOG = BASE_DIR / "ProgrammingTimer" / "programming_time_log.jsonl"

COTS_KIOSK_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\17. COTS - Tools Crib Kiosk\cots-kiosk")
TOOL_KIOSK_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\22. Tool Assembly Management\tool-kiosk")
MSG_NOTIFIER_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\18. ProShop Message Notifier")
AIR_COMPRESSOR_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\23. Air Compressor communication GUI")
SHOP_SCHEDULER_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\19. Shop Scheduler")
AGENT_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\25. Agent Exploration")
PHOTO_UPLOADER_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\31. Photo Upload Service\photo-uploader")

BUSINESS_HOURS_START = (5, 15)   # (hour, minute) — 5:15 AM
BUSINESS_HOURS_END = (18, 0)     # (hour, minute) — 6:00 PM
BUSINESS_DAYS = range(0, 5)

# ---- Service Definitions ---------------------------------------------------
#
# service_type:  "process" — managed via subprocess (Python scripts, etc.)
#                "windows_service" — managed via sc commands
#
# check_type:    "http" — GET health_url, expect 200 + JSON, pass to validator
#                "database" — validator called directly (no HTTP probe)

SERVICES_CONFIG = {
    "TimeTrackerDashboard": {
        "display_name": "Time Tracker Dashboard",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:8050/api/status",
        "port": 8050,
        "start_cmd": [PYTHONW_EXE, "time_status_display_v1.0.py"],
        "working_dir": str(BASE_DIR / "TimeTrackerDashboard"),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "FocasMonitor": {
        "display_name": "FOCAS Machine Monitor",
        "service_type": "windows_service",
        "windows_service_name": "FocasMonitor",
        "check_type": "database",
        "health_url": None,
        "port": None,
        "start_cmd": None,
        "working_dir": None,
        "auto_start": False,       # Windows manages startup
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 10,
        "db_path": r"C:\FASData\monitoring.db",
        "max_sample_age": 180,     # seconds — samples older = stale
    },
    "FASDataDashboard": {
        "display_name": "FASData Live Dashboard",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:8070/api/status",
        "port": 8070,
        "start_cmd": [PYTHONW_EXE, "fasdata_live.py"],
        "working_dir": str(BASE_DIR / "FASDataDashboard"),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "MessageNotifier": {
        "display_name": "ProShop Message Notifier",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:5050/api/health",
        "port": 5050,
        "start_cmd": [PYTHONW_EXE, "app.py"],
        "working_dir": str(MSG_NOTIFIER_DIR),
        "env": {"PROSHOP_CLIENT_SECRET": "E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110"},
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "COTSCribKiosk": {
        "display_name": "COTS Crib Kiosk",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:5000/api/health",
        "port": 5000,
        "start_cmd": [PYTHONW_EXE, "app.py"],
        "working_dir": str(COTS_KIOSK_DIR),
        "env": {"PROSHOP_CLIENT_SECRET": "E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110"},
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "ToolAssemblyKiosk": {
        "display_name": "Tool Assembly Kiosk",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:5001/api/health",
        "port": 5001,
        "start_cmd": [PYTHONW_EXE, "app.py"],
        "working_dir": str(TOOL_KIOSK_DIR),
        "env": {"PROSHOP_CLIENT_SECRET": "8A32CD4983CA93F9BE1FF0E651B9CDE9A28F55C66B74E1CDF5D6887EFE85D5B6"},
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "ToolUsageRollup": {
        "display_name": "Tool Usage Rollup",
        "service_type": "process",
        "check_type": "database",
        "health_url": None,
        "port": None,
        "start_cmd": [PYTHONW_EXE, "tool_usage_rollup.py", "--loop", "300"],
        "working_dir": str(TOOL_KIOSK_DIR),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 10,
        "db_path": str(TOOL_KIOSK_DIR / "data" / "tooling.db"),
    },
    "LabelPrintService": {
        "display_name": "Label Print Service (10.1.1.242)",
        "service_type": "remote",
        "check_type": "http",
        "health_url": "http://10.1.1.242:5002/api/health",
        "restart_url": "http://10.1.1.242:5002/api/restart",
        "port": 5002,
        "auto_start": False,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "AirCompressor": {
        "display_name": "Air Compressor Monitor",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:8085/api/status",
        "port": 8085,
        "start_cmd": [r"C:\Users\TRAXIS\AppData\Local\Python\bin\pythonw.exe", "compressor_web.py"],
        "working_dir": str(AIR_COMPRESSOR_DIR),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "ShopScheduler": {
        "display_name": "Shop Scheduler",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:5080/api/health",
        "port": 5080,
        "start_cmd": [PYTHONW_EXE, "app.py"],
        "working_dir": str(SHOP_SCHEDULER_DIR),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "TelegramBot": {
        "display_name": "Telegram Bot",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:8100/api/health",
        "port": 8100,
        "start_cmd": [PYTHONW_EXE, "telegram_bot.py"],
        "working_dir": str(AGENT_DIR),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "AgentScheduler": {
        "display_name": "Agent Scheduler",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:8101/api/health",
        "port": 8101,
        "start_cmd": [PYTHONW_EXE, "agent_scheduler.py"],
        "working_dir": str(AGENT_DIR),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
    "PhotoUploadService": {
        "display_name": "Photo Upload Service",
        "service_type": "process",
        "check_type": "http",
        "health_url": "http://localhost:5003/api/health",
        "port": 5003,
        "start_cmd": [PYTHONW_EXE, "app.py"],
        "working_dir": str(PHOTO_UPLOADER_DIR),
        "auto_start": True,
        "restart_cooldown": 300,
        "max_failures": 3,
        "max_degraded": 5,
    },
}

# ============================================================================
# HEALTH VALIDATORS
# ============================================================================

def is_business_hours():
    now = datetime.now()
    now_hm = (now.hour, now.minute)
    return now.weekday() in BUSINESS_DAYS and BUSINESS_HOURS_START <= now_hm < BUSINESS_HOURS_END


def validate_time_tracker(data):
    """Validate TimeTrackerDashboard /api/status response."""
    employees = data.get("employees", [])
    error = data.get("error")
    last_update_str = data.get("lastUpdate")

    if error:
        return "degraded", f"API error: {error}"

    if last_update_str:
        try:
            last_update = datetime.fromisoformat(last_update_str)
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - last_update).total_seconds()
            if age > 300:
                return "degraded", f"Data stale ({int(age)}s old)"
        except Exception:
            pass

    if not employees and is_business_hours():
        return "degraded", "No employees during business hours"

    clocked = sum(1 for e in employees if e.get("clockedIn"))
    tracking = sum(1 for e in employees if e.get("trackingActive"))
    return "healthy", f"{len(employees)} employees, {clocked} clocked in, {tracking} tracking"


def validate_focas_monitor(config):
    """Check FocasMonitor Windows service status + SQLite DB freshness."""
    svc_name = config.get("windows_service_name", "FocasMonitor")
    db_path = config.get("db_path", r"C:\FASData\monitoring.db")
    max_age = config.get("max_sample_age", 180)

    # 1. Check Windows service status
    try:
        result = subprocess.run(
            ["sc", "query", svc_name],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if "RUNNING" not in result.stdout:
            # Extract actual state
            for line in result.stdout.splitlines():
                if "STATE" in line:
                    return "down", f"Service {line.strip()}"
            return "down", "Service not running"
    except Exception as e:
        return "down", f"Cannot query service: {e}"

    # 2. Check database exists
    if not Path(db_path).exists():
        return "degraded", "Database file not found"

    # 3. Query latest samples per machine
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("""
            SELECT machine_id, MAX(timestamp) as last_reading
            FROM machine_samples
            GROUP BY machine_id
            ORDER BY machine_id
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return "degraded", f"Database error: {e}"

    if not rows:
        return "degraded", "No machine data in database"

    # 4. Check sample freshness
    now = datetime.now()
    stale = []
    fresh = 0

    for machine_id, ts_str in rows:
        try:
            ts = datetime.fromisoformat(ts_str)
            # Strip timezone for naive comparison
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            age = (now - ts).total_seconds()
            if age > max_age:
                stale.append(f"{machine_id}({int(age / 60)}m)")
            else:
                fresh += 1
        except Exception:
            stale.append(f"{machine_id}(?)")

    total = len(rows)
    if fresh == 0 and is_business_hours():
        return "down", f"All {total} machines stale: {', '.join(stale)}"
    elif fresh == 0:
        return "degraded", f"All {total} machines stale (off-hours): {', '.join(stale)}"
    elif stale:
        return "degraded", f"{fresh}/{total} fresh, stale: {', '.join(stale)}"
    else:
        return "healthy", f"All {total} machines reporting"


def validate_fasdata_dashboard(data):
    """Validate FASDataDashboard /api/status response."""
    error = data.get("error")
    if error:
        return "degraded", f"API error: {error}"

    machines = data.get("machines", {})
    if not machines:
        return "degraded", "No machine data"

    active = data.get("active_count", 0)
    total = data.get("total_count", 0)
    shop_avg = data.get("shop_avg", 0)
    return "healthy", f"{active}/{total} machines online, shop avg {shop_avg}%"


def validate_message_notifier(data):
    """Validate MessageNotifier /api/health response."""
    if data.get("status") != "ok":
        error = data.get("error", "unknown")
        return "degraded", f"Unhealthy: {error}"
    if not data.get("token_valid"):
        return "degraded", "OAuth token invalid"
    active = data.get("active_users", 0)
    uptime = data.get("uptime_seconds", 0)
    return "healthy", f"{active} active users, uptime {uptime}s"


def validate_cots_kiosk(data):
    """Validate COTSCribKiosk /api/health response."""
    if not data.get("api_reachable"):
        error = data.get("error", "Unknown")
        return "degraded", f"ProShop API unreachable: {error}"
    if not data.get("token_valid"):
        return "degraded", "OAuth token invalid"
    total = data.get("total_cots_items", 0)
    uptime = data.get("uptime_seconds", 0)
    return "healthy", f"{total} COTS items, uptime {uptime}s"


def validate_tool_assembly_kiosk(data):
    """Validate ToolAssemblyKiosk /api/health response."""
    if not data.get("api_reachable"):
        error = data.get("error", "Unknown")
        return "degraded", f"ProShop API unreachable: {error}"
    if not data.get("token_valid"):
        return "degraded", "OAuth token invalid"
    holders = data.get("active_holders", 0)
    assignments = data.get("active_assignments", 0)
    uptime = data.get("uptime_seconds", 0)
    return "healthy", f"{holders} holders, {assignments} assigned, uptime {uptime}s"


def validate_label_print_service(data):
    """Validate LabelPrintService /api/health response."""
    if not data.get("printer_available"):
        return "degraded", "Printer offline"
    printer = data.get("printer", "?")
    uptime = data.get("uptime_seconds", 0)
    return "healthy", f"{printer}, uptime {uptime}s"


def validate_air_compressor(data):
    """Validate AirCompressor /api/status response."""
    if data.get("error"):
        return "degraded", f"Error: {data['error']}"
    if not data.get("connected"):
        return "degraded", "Not connected to compressor"
    pressure = data.get("pressure_psi", 0)
    state = data.get("compressor_state", "UNKNOWN")
    alarms = data.get("active_alarms", [])
    msg = f"{pressure} PSI, {state}"
    if alarms:
        msg += f", ALARMS: {', '.join(alarms)}"
    return "healthy", msg


def validate_shop_scheduler(data):
    """Validate ShopScheduler /api/health response."""
    if not data.get("api_reachable"):
        error = data.get("error", "Unknown")
        return "degraded", f"ProShop API unreachable: {error}"
    if not data.get("token_valid"):
        return "degraded", "OAuth token invalid"
    wos = data.get("active_work_orders", 0)
    uptime = data.get("uptime_seconds", 0)
    return "healthy", f"{wos} active WOs, uptime {uptime}s"


def validate_tool_usage_rollup(config):
    """Check ToolUsageRollup by inspecting log freshness and open segments."""
    db_path = config.get("db_path")
    log_path = Path(config.get("working_dir", "")) / "data" / "logs" / "tool_usage_rollup.log"

    # 1. Check log file freshness (should update every ~5 min)
    if log_path.exists():
        age = time.time() - log_path.stat().st_mtime
        if age > 900:  # 15 min = 3 missed cycles
            return "degraded", f"Log file stale ({int(age // 60)}m ago)"
    else:
        return "degraded", "Log file not found"

    # 2. Check tooling.db for open segments
    if not db_path or not Path(db_path).exists():
        return "degraded", "tooling.db not found"

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tool_usage_segments WHERE segment_end IS NULL")
        open_segs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM assignments WHERE removed_at IS NULL")
        active_assigns = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        return "degraded", f"DB error: {e}"

    return "healthy", f"{open_segs} open segments, {active_assigns} active assignments"


def validate_telegram_bot(data):
    """Validate TelegramBot /api/health response."""
    if data.get("status") != "ok":
        return "degraded", f"Unhealthy: {data.get('status', 'unknown')}"
    tools = data.get("tools_loaded", 0)
    msgs = data.get("messages_handled", 0)
    uptime = data.get("uptime_seconds", 0)
    conv_len = data.get("conversation_length", 0)
    return "healthy", f"{tools} tools, {msgs} msgs handled, {conv_len} conv, uptime {uptime}s"


def validate_agent_scheduler(data):
    """Validate AgentScheduler /api/health response."""
    if data.get("status") != "ok":
        return "degraded", f"Unhealthy: {data.get('status', 'unknown')}"

    issues = []
    if not data.get("reminders_ok"):
        issues.append(f"reminders failing (exit {data.get('reminders_exit_code', '?')})")
    if not data.get("audit_ok"):
        issues.append(f"audit failing (exit {data.get('audit_exit_code', '?')})")
    if not data.get("scan_ok"):
        issues.append(f"scanner failing (exit {data.get('scan_exit_code', '?')})")

    uptime = data.get("uptime_seconds", 0)
    last_rem = data.get("last_reminders_run", "never")
    last_aud = data.get("last_audit_run", "never")

    if issues:
        return "degraded", f"Issues: {', '.join(issues)} | uptime {uptime}s"
    return "healthy", f"reminders={last_rem}, audit={last_aud}, uptime {uptime}s"


def validate_photo_uploader(data):
    """Validate PhotoUploadService /api/health response."""
    if data.get("status") != "ok":
        return "degraded", f"Unhealthy: {data.get('status', 'unknown')}"
    api = data.get("proshop_api", {})
    if not api.get("api_reachable"):
        return "degraded", "ProShop API unreachable"
    queue = data.get("queue", {})
    pending = queue.get("pending", 0) + queue.get("failed", 0)
    uploaded = queue.get("uploaded", 0)
    worker = "alive" if data.get("worker_alive") else "DEAD"
    return "healthy", f"{pending} pending, {uploaded} uploaded, worker {worker}"


# Map service name -> validator function
# For "http" check_type: validator receives parsed JSON response
# For "database" check_type: validator receives the service config dict
VALIDATORS = {
    "TimeTrackerDashboard": validate_time_tracker,
    "FocasMonitor": validate_focas_monitor,
    "FASDataDashboard": validate_fasdata_dashboard,
    "COTSCribKiosk": validate_cots_kiosk,
    "MessageNotifier": validate_message_notifier,
    "ToolAssemblyKiosk": validate_tool_assembly_kiosk,
    "ToolUsageRollup": validate_tool_usage_rollup,
    "LabelPrintService": validate_label_print_service,
    "AirCompressor": validate_air_compressor,
    "ShopScheduler": validate_shop_scheduler,
    "TelegramBot": validate_telegram_bot,
    "AgentScheduler": validate_agent_scheduler,
    "PhotoUploadService": validate_photo_uploader,
}


# ============================================================================
# SERVICE STATE
# ============================================================================

class ServiceState:
    """Runtime state for one managed service."""

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.status = "stopped"
        self.message = ""
        self.pid = None
        self.process = None
        self.consecutive_failures = 0
        self.consecutive_degraded = 0
        self.last_check = None
        self.last_restart = None
        self.last_healthy = None
        self.started_at = None
        self.restart_count = 0

    def to_dict(self):
        uptime = None
        if self.started_at and self.status not in ("stopped", "down"):
            uptime = (datetime.now() - self.started_at).total_seconds()
        return {
            "name": self.name,
            "displayName": self.config["display_name"],
            "serviceType": self.config.get("service_type", "process"),
            "status": self.status,
            "message": self.message,
            "pid": self.pid,
            "port": self.config.get("port"),
            "healthUrl": self.config.get("health_url"),
            "uptimeSeconds": uptime,
            "lastCheck": self.last_check.isoformat() if self.last_check else None,
            "lastRestart": self.last_restart.isoformat() if self.last_restart else None,
            "lastHealthy": self.last_healthy.isoformat() if self.last_healthy else None,
            "restartCount": self.restart_count,
            "consecutiveFailures": self.consecutive_failures,
            "consecutiveDegraded": self.consecutive_degraded,
        }


# ============================================================================
# SERVICE MANAGER
# ============================================================================

class ServiceManager:
    """Manages lifecycle and health of all registered services."""

    def __init__(self):
        self.services: dict[str, ServiceState] = {}
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self.lock = threading.Lock()

        for name, config in SERVICES_CONFIG.items():
            self.services[name] = ServiceState(name, config)

    # ---- Events ------------------------------------------------------------

    def _event(self, service_name, event_type, message):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "service": service_name,
            "type": event_type,
            "message": message,
        }
        with self.lock:
            self.events.appendleft(entry)
        log.info("[%s] %s: %s", service_name, event_type, message)

    # ---- Process helpers ---------------------------------------------------

    @staticmethod
    def _find_pid_by_port(port):
        if not port:
            return None
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        return int(parts[-1])
        except Exception:
            pass
        return None

    @staticmethod
    def _kill_pid(pid):
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    @staticmethod
    def _sc_command(action, service_name):
        """Run an sc command. Returns (success, output)."""
        try:
            result = subprocess.run(
                ["sc", action, service_name],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    # ---- Lifecycle: Process services ---------------------------------------

    def _start_process(self, name):
        state = self.services[name]
        cfg = state.config

        existing_pid = self._find_pid_by_port(cfg["port"])
        if existing_pid:
            state.pid = existing_pid
            state.status = "starting"
            state.started_at = datetime.now()
            self._event(name, "adopted", f"Found existing process PID {existing_pid}")
            return True

        try:
            env = None
            if cfg.get("env"):
                env = os.environ.copy()
                env.update(cfg["env"])
            proc = subprocess.Popen(
                cfg["start_cmd"],
                cwd=cfg["working_dir"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
            )
            state.process = proc
            state.pid = proc.pid
            state.status = "starting"
            state.started_at = datetime.now()
            state.consecutive_failures = 0
            state.consecutive_degraded = 0
            self._event(name, "started", f"PID {proc.pid}")
            return True
        except Exception as e:
            state.status = "down"
            state.message = f"Start failed: {e}"
            self._event(name, "error", f"Failed to start: {e}")
            return False

    def _stop_process(self, name):
        state = self.services[name]

        if state.process and state.process.poll() is None:
            state.process.terminate()
            try:
                state.process.wait(timeout=5)
            except Exception:
                state.process.kill()

        pid = self._find_pid_by_port(state.config.get("port"))
        if pid:
            self._kill_pid(pid)

        state.status = "stopped"
        state.pid = None
        state.process = None
        state.message = "Stopped"
        self._event(name, "stopped", "Service stopped")

    # ---- Lifecycle: Windows services ---------------------------------------

    def _start_windows_service(self, name):
        state = self.services[name]
        svc_name = state.config["windows_service_name"]

        ok, output = self._sc_command("start", svc_name)
        if ok or "ALREADY" in output.upper():
            state.status = "starting"
            state.started_at = datetime.now()
            state.consecutive_failures = 0
            state.consecutive_degraded = 0
            self._event(name, "started", f"sc start {svc_name}")
            return True
        else:
            state.status = "down"
            state.message = f"Start failed (need admin?): {output.strip()[:100]}"
            self._event(name, "error", state.message)
            return False

    def _stop_windows_service(self, name):
        state = self.services[name]
        svc_name = state.config["windows_service_name"]

        ok, output = self._sc_command("stop", svc_name)
        state.status = "stopped"
        state.pid = None
        state.message = "Stopped" if ok else f"Stop may need admin: {output.strip()[:100]}"
        self._event(name, "stopped", state.message)

    # ---- Lifecycle: Dispatch -----------------------------------------------

    def start_service(self, name):
        stype = self.services[name].config.get("service_type", "process")
        if stype == "remote":
            self._event(name, "info", "Remote service — cannot start from here")
            return False
        if stype == "windows_service":
            return self._start_windows_service(name)
        return self._start_process(name)

    def stop_service(self, name):
        stype = self.services[name].config.get("service_type", "process")
        if stype == "remote":
            self._event(name, "info", "Remote service — cannot stop from here")
            return
        if stype == "windows_service":
            self._stop_windows_service(name)
        else:
            self._stop_process(name)

    def restart_service(self, name):
        state = self.services[name]

        if state.last_restart:
            elapsed = (datetime.now() - state.last_restart).total_seconds()
            remaining = state.config["restart_cooldown"] - elapsed
            if remaining > 0:
                self._event(name, "cooldown",
                            f"Restart skipped ({int(remaining)}s cooldown remaining)")
                return False

        # Remote services: call their restart endpoint
        stype = state.config.get("service_type", "process")
        restart_url = state.config.get("restart_url")
        if stype == "remote" and restart_url:
            self._event(name, "restarting", "Sending restart to remote service...")
            try:
                resp = http_requests.post(restart_url, timeout=10)
                resp.raise_for_status()
                state.last_restart = datetime.now()
                state.restart_count += 1
                self._event(name, "info", "Remote restart triggered — waiting for service")
                return True
            except Exception as e:
                self._event(name, "error", f"Remote restart failed: {e}")
                return False

        self._event(name, "restarting", "Restarting service...")
        self.stop_service(name)
        time.sleep(3)
        ok = self.start_service(name)
        if ok:
            state.last_restart = datetime.now()
            state.restart_count += 1
        return ok

    # ---- Health checks -----------------------------------------------------

    def _check_http_service(self, name):
        """Health check for HTTP-based services."""
        state = self.services[name]
        cfg = state.config

        try:
            resp = http_requests.get(cfg["health_url"], timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except http_requests.ConnectionError:
            state.consecutive_failures += 1
            state.consecutive_degraded = 0
            state.status = "down"
            state.message = "Connection refused"

            if state.consecutive_failures >= cfg["max_failures"]:
                self._event(name, "down",
                            f"Down {state.consecutive_failures}x — auto-restarting")
                self.restart_service(name)
            else:
                self._event(name, "down",
                            f"Unreachable ({state.consecutive_failures}/{cfg['max_failures']})")
            return
        except Exception as e:
            state.consecutive_failures += 1
            state.consecutive_degraded = 0
            state.status = "down"
            state.message = str(e)
            if state.consecutive_failures >= cfg["max_failures"]:
                self._event(name, "down", f"Check error, auto-restarting: {e}")
                self.restart_service(name)
            return

        validator = VALIDATORS.get(name)
        health, msg = validator(data) if validator else ("healthy", "HTTP 200 OK")
        self._apply_health_result(name, health, msg)

    def _check_database_service(self, name):
        """Health check for database/file-based services."""
        state = self.services[name]
        cfg = state.config

        validator = VALIDATORS.get(name)
        if not validator:
            state.status = "healthy"
            state.message = "No validator configured"
            return

        try:
            health, msg = validator(cfg)
        except Exception as e:
            health, msg = "down", f"Validator error: {e}"

        self._apply_health_result(name, health, msg)

    def _apply_health_result(self, name, health, msg):
        """Apply a health/degraded/down result to a service."""
        state = self.services[name]
        cfg = state.config
        state.message = msg

        if health == "healthy":
            was_unhealthy = state.status != "healthy"
            state.status = "healthy"
            state.last_healthy = datetime.now()
            state.consecutive_failures = 0
            state.consecutive_degraded = 0
            if was_unhealthy:
                self._event(name, "healthy", msg)

        elif health == "degraded":
            state.consecutive_degraded += 1
            state.consecutive_failures = 0
            state.status = "degraded"
            if state.consecutive_degraded >= cfg["max_degraded"]:
                self._event(name, "degraded",
                            f"Degraded {state.consecutive_degraded}x — auto-restarting: {msg}")
                self.restart_service(name)
            elif state.consecutive_degraded == 1:
                self._event(name, "degraded", msg)

        elif health == "down":
            state.consecutive_failures += 1
            state.consecutive_degraded = 0
            state.status = "down"
            if state.consecutive_failures >= cfg["max_failures"]:
                self._event(name, "down",
                            f"Down {state.consecutive_failures}x — auto-restarting: {msg}")
                self.restart_service(name)
            elif state.consecutive_failures == 1:
                self._event(name, "down", msg)

    def check_service(self, name):
        state = self.services[name]
        if state.status == "stopped":
            return

        state.last_check = datetime.now()

        # Grace period after start (process services only)
        if state.status == "starting" and state.started_at:
            age = (datetime.now() - state.started_at).total_seconds()
            if age < STARTUP_GRACE:
                state.message = f"Starting ({int(STARTUP_GRACE - age)}s grace)"
                return

        check_type = state.config.get("check_type", "http")
        if check_type == "http":
            self._check_http_service(name)
        elif check_type == "database":
            self._check_database_service(name)

    # ---- Main loops --------------------------------------------------------

    def startup(self):
        for name, state in self.services.items():
            cfg = state.config
            if cfg.get("service_type") in ("windows_service", "remote"):
                # External services manage their own startup — just monitor health
                state.status = "starting"
                state.started_at = datetime.now()
                label = "Windows service" if cfg.get("service_type") == "windows_service" else "remote service"
                self._event(name, "monitoring", f"Monitoring {label}")
            elif cfg["auto_start"]:
                self.start_service(name)

        time.sleep(STARTUP_GRACE)
        for name, state in self.services.items():
            if state.status != "stopped":
                self.check_service(name)

    def run_check_loop(self):
        self.startup()
        while True:
            time.sleep(CHECK_INTERVAL)
            for name, state in self.services.items():
                if state.status != "stopped":
                    try:
                        self.check_service(name)
                    except Exception as e:
                        log.error("Check loop error for %s: %s", name, e)

    # ---- API ---------------------------------------------------------------

    def get_status(self):
        services = [s.to_dict() for s in self.services.values()]
        with self.lock:
            events = list(self.events)[:50]
        return {
            "services": services,
            "events": events,
            "checkInterval": CHECK_INTERVAL,
            "timestamp": datetime.now().isoformat(),
        }


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)
manager: ServiceManager = None  # type: ignore


@app.route("/")
def index():
    return send_file(Path(__file__).parent / "overseer.html")


@app.route("/api/status")
def api_status():
    return jsonify(manager.get_status())


@app.route("/api/services/<name>/restart", methods=["POST"])
def api_restart(name):
    if name not in manager.services:
        return jsonify({"error": "Unknown service"}), 404
    threading.Thread(target=manager.restart_service, args=(name,), daemon=True).start()
    return jsonify({"status": "restarting"})


@app.route("/api/services/<name>/stop", methods=["POST"])
def api_stop(name):
    if name not in manager.services:
        return jsonify({"error": "Unknown service"}), 404
    manager.stop_service(name)
    return jsonify({"status": "stopped"})


@app.route("/api/services/<name>/start", methods=["POST"])
def api_start(name):
    if name not in manager.services:
        return jsonify({"error": "Unknown service"}), 404
    threading.Thread(target=manager.start_service, args=(name,), daemon=True).start()
    return jsonify({"status": "starting"})


@app.route("/api/overseer/restart", methods=["POST"])
def api_overseer_restart():
    """Restart the Overseer process itself."""
    log.info("Overseer restart requested via API")
    # Stop all managed services gracefully first
    for name in list(manager.services):
        try:
            manager.stop_service(name)
        except Exception:
            pass
    # Spawn a replacement process then exit
    script = str(Path(__file__).resolve())
    subprocess.Popen(
        [sys.executable, script],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
    # Schedule self-exit after response is sent
    threading.Thread(target=lambda: (time.sleep(1), os._exit(0)), daemon=True).start()
    return jsonify({"status": "restarting"})


@app.route("/api/programming-sessions")
def api_programming_sessions():
    """Return programming timer session logs, optionally filtered by date."""
    date_filter = request.args.get("date")  # YYYY-MM-DD or "today" or "week"

    if not PROGRAMMING_LOG.exists():
        return jsonify({"sessions": [], "error": "Log file not found"})

    sessions = []
    try:
        with open(PROGRAMMING_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    sessions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        return jsonify({"sessions": [], "error": str(e)})

    # Filter by date
    today = datetime.now().strftime("%Y-%m-%d")
    if date_filter == "today" or date_filter is None:
        sessions = [s for s in sessions if s.get("date") == today]
    elif date_filter == "week":
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        sessions = [s for s in sessions if s.get("date", "") >= week_ago]
    elif date_filter != "all":
        sessions = [s for s in sessions if s.get("date") == date_filter]

    # Sort most recent first
    sessions.sort(key=lambda s: s.get("start_time", ""), reverse=True)

    # Compute summary
    total_seconds = sum(s.get("duration_seconds", 0) for s in sessions)
    parts = {}
    for s in sessions:
        pid = s.get("part_identifier", "Unknown")
        parts[pid] = parts.get(pid, 0) + s.get("duration_seconds", 0)

    return jsonify({
        "sessions": sessions,
        "summary": {
            "totalSeconds": total_seconds,
            "sessionCount": len(sessions),
            "partBreakdown": [
                {"part": p, "seconds": sec}
                for p, sec in sorted(parts.items(), key=lambda x: -x[1])
            ],
        },
    })


# ============================================================================
# MAIN
# ============================================================================

def _kill_stale_overseer():
    """If another Overseer is already bound to our port, kill it before starting."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        my_pid = os.getpid()
        for line in result.stdout.splitlines():
            if f":{PORT} " in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid = int(parts[-1])
                    if pid != my_pid:
                        log.warning("Killing stale Overseer (PID %d) on port %d", pid, PORT)
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        time.sleep(2)
    except Exception as e:
        log.warning("Stale process check failed: %s", e)


def main():
    global manager

    _kill_stale_overseer()

    manager = ServiceManager()

    check_thread = threading.Thread(target=manager.run_check_loop, daemon=True)
    check_thread.start()

    log.info("Overseer dashboard at http://localhost:%d", PORT)
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
