"""
Traxis Agent Scheduler -- Periodic Task Runner

Long-running process that replaces the scheduled task logic from service_wrapper.py.
Managed by Overseer (start/stop/restart via dashboard).

Tasks:
  - check_reminders.py  every 15 min
  - run_audit.py         every 60 min
  - scan_projects.py     daily at midnight (00:00-00:15 window)

Health endpoint on port 8101 for Overseer monitoring.

Usage:
    python agent_scheduler.py          # Run the scheduler loop
    python agent_scheduler.py --once   # Run all tasks once and exit
"""

import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ---- Configuration ----------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent
PYTHON = sys.executable

HEALTH_PORT = 8101
LOOP_INTERVAL = 30  # seconds between checks

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Task intervals (seconds)
REMINDER_INTERVAL = 900    # 15 min
AUDIT_INTERVAL = 3600      # 60 min

# ---- Logging ----------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("agent_scheduler")

_file_handler = logging.FileHandler(LOG_DIR / "agent_scheduler.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
log.addHandler(_file_handler)

# ---- State ------------------------------------------------------------------

_start_time = time.time()
_last_reminders_run = None
_last_audit_run = None
_last_scan_run = None
_reminders_ok = True
_audit_ok = True
_scan_ok = True
_reminders_exit_code = 0
_audit_exit_code = 0
_scan_exit_code = 0

# ---- Health Endpoint --------------------------------------------------------

class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint for Overseer monitoring."""

    def do_GET(self):
        if self.path == "/api/health":
            data = {
                "status": "ok",
                "uptime_seconds": int(time.time() - _start_time),
                "last_reminders_run": _last_reminders_run,
                "last_audit_run": _last_audit_run,
                "last_scan_run": _last_scan_run,
                "reminders_ok": _reminders_ok,
                "reminders_exit_code": _reminders_exit_code,
                "audit_ok": _audit_ok,
                "audit_exit_code": _audit_exit_code,
                "scan_ok": _scan_ok,
                "scan_exit_code": _scan_exit_code,
            }
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging

# ---- Task Runner ------------------------------------------------------------

def _run_task(script_name, timeout_s=300):
    """Run a one-shot script. Returns (success, returncode)."""
    script = str(PROJECT_ROOT / script_name)
    log.info("Running %s ...", script_name)
    try:
        result = subprocess.run(
            [PYTHON, script],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            log.info("%s completed successfully.", script_name)
        else:
            log.warning("%s exited with code %d.", script_name, result.returncode)
            if result.stderr:
                log.debug("%s stderr: %s", script_name, result.stderr[:500])
        return True, result.returncode
    except subprocess.TimeoutExpired:
        log.error("%s timed out after %ds.", script_name, timeout_s)
        return False, -1
    except Exception as e:
        log.error("Failed to run %s: %s", script_name, e)
        return False, -1


def _should_run_reminders():
    """Check if 15+ minutes since last run."""
    if _last_reminders_run is None:
        return True
    try:
        last = datetime.fromisoformat(_last_reminders_run)
        return (datetime.now() - last).total_seconds() >= REMINDER_INTERVAL
    except (ValueError, TypeError):
        return True


def _should_run_audit():
    """Check if 60+ minutes since last run."""
    if _last_audit_run is None:
        return True
    try:
        last = datetime.fromisoformat(_last_audit_run)
        return (datetime.now() - last).total_seconds() >= AUDIT_INTERVAL
    except (ValueError, TypeError):
        return True


def _should_run_scanner():
    """Check if in midnight window (00:00-00:15) and not run today."""
    now = datetime.now()
    in_window = now.hour == 0 and now.minute < 15
    if not in_window:
        return False
    if _last_scan_run is None:
        return True
    try:
        last = datetime.fromisoformat(_last_scan_run)
        return last.date() != now.date()
    except (ValueError, TypeError):
        return True


# ---- Main Loop --------------------------------------------------------------

def scheduler_loop():
    """Main scheduler loop. Runs tasks at their configured intervals."""
    global _last_reminders_run, _last_audit_run, _last_scan_run
    global _reminders_ok, _audit_ok, _scan_ok
    global _reminders_exit_code, _audit_exit_code, _scan_exit_code

    log.info("Scheduler loop started.")

    while True:
        try:
            if _should_run_reminders():
                ok, rc = _run_task("check_reminders.py", timeout_s=300)
                _last_reminders_run = datetime.now().isoformat(timespec="seconds")
                _reminders_ok = ok and rc == 0
                _reminders_exit_code = rc

            if _should_run_audit():
                ok, rc = _run_task("run_audit.py", timeout_s=300)
                _last_audit_run = datetime.now().isoformat(timespec="seconds")
                # run_audit.py exits 1 when it finds data-quality issues —
                # that's a normal audit outcome, not a script failure.
                _audit_ok = ok and rc in (0, 1)
                _audit_exit_code = rc

            if _should_run_scanner():
                ok, rc = _run_task("scan_projects.py", timeout_s=600)
                _last_scan_run = datetime.now().isoformat(timespec="seconds")
                _scan_ok = ok and rc == 0
                _scan_exit_code = rc

        except Exception as e:
            log.error("Scheduler loop error: %s", e, exc_info=True)

        time.sleep(LOOP_INTERVAL)


def run_once():
    """Run all tasks once and exit (for testing)."""
    global _last_reminders_run, _last_audit_run, _last_scan_run
    global _reminders_ok, _audit_ok, _scan_ok
    global _reminders_exit_code, _audit_exit_code, _scan_exit_code

    log.info("Running all tasks once...")

    ok, rc = _run_task("check_reminders.py", timeout_s=300)
    _last_reminders_run = datetime.now().isoformat(timespec="seconds")
    _reminders_ok = ok and rc == 0
    _reminders_exit_code = rc

    ok, rc = _run_task("run_audit.py", timeout_s=300)
    _last_audit_run = datetime.now().isoformat(timespec="seconds")
    _audit_ok = ok and rc in (0, 1)
    _audit_exit_code = rc

    ok, rc = _run_task("scan_projects.py", timeout_s=600)
    _last_scan_run = datetime.now().isoformat(timespec="seconds")
    _scan_ok = ok and rc == 0
    _scan_exit_code = rc

    log.info("All tasks complete. Reminders=%s Audit=%s Scanner=%s",
             _reminders_ok, _audit_ok, _scan_ok)


def main():
    if "--once" in sys.argv:
        run_once()
        return

    log.info("Traxis Agent Scheduler starting...")

    # Start health endpoint
    try:
        health_server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
        threading.Thread(target=health_server.serve_forever, daemon=True).start()
        log.info("Health endpoint listening on port %d", HEALTH_PORT)
    except Exception as e:
        log.warning("Could not start health endpoint on port %d: %s", HEALTH_PORT, e)

    # Run scheduler loop (blocks forever)
    scheduler_loop()


if __name__ == "__main__":
    main()
