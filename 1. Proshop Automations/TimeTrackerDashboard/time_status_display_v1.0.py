#!/usr/bin/env python3
"""
Traxis Time Tracking Status Display v1.0
=========================================
Management dashboard showing real-time time tracking status for all shop employees.
Polls ProShop API for clock punches and active time tracking entries.
Serves a web dashboard accessible from any browser on the network.

Purpose: Let Wolfgang see at a glance who's clocked in, who's tracking time
to a job, and who might be idle.

Usage:
    python time_status_display_v1.0.py

    Then open http://localhost:8050 in a browser.

Dependencies:
    pip install flask requests

Author: Wolfgang / Claude
"""

import os
import sys
import json
import time
import threading
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from flask import Flask, jsonify, send_file
    import requests
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: py -m pip install flask requests")
    sys.exit(1)

# ============================================================================
# .ENV FILE SUPPORT
# ============================================================================

def load_env_file():
    """Load variables from .env file if it exists. Checks local dir and common paths."""
    search_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent / "traxis.env",
        Path(r"C:\Users\TRAXIS\.traxis.env"),
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent / "traxis.env",
        Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\4. Inspection Print and Proshop Automation\Dimension Extraction Automation\dist\dist\.env"),
        Path(r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\.env"),
        Path(r"D:\Dropbox\MACHINE COMM Traxis\.env"),
    ]
    for env_path in search_paths:
        if env_path.exists():
            print(f"[INFO] Loading .env from {env_path}")
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value:
                            os.environ.setdefault(key, value)
            return
    print("[INFO] No .env file found, using environment variables only")

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("TimeStatus")

# ============================================================================
# CONFIGURATION
# ============================================================================

load_env_file()

CLIENT_ID = os.environ.get("PROSHOP_CLIENT_ID", "B769-88F7-A69B")
CLIENT_SECRET = os.environ.get("PROSHOP_CLIENT_SECRET", "")
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
SCOPES = "parts:rwdp+workorders:rwdp+users:r+toolpots:r"

HOST = "0.0.0.0"
PORT = 8050
POLL_INTERVAL = 900  # 15 min — was 30s, reduced to cut API load

# Employee IDs to exclude (ProShop system users, etc.)
EXCLUDED_USER_IDS = {"124", "999"}  # System User, System Agent

VERSION = "1.1"

# ============================================================================
# PROSHOP API
# ============================================================================

class ProShopAPI:
    """Handles OAuth2 auth and GraphQL queries to ProShop."""

    def __init__(self):
        self.token = None
        self.token_expires = None
        self.session = requests.Session()

    def get_token(self):
        """Get or refresh OAuth2 access token."""
        now = time.time()
        if self.token and self.token_expires and now < self.token_expires - 60:
            return self.token

        secret = CLIENT_SECRET
        if not secret:
            log.error("PROSHOP_CLIENT_SECRET not set! Set env var or edit script.")
            return None

        log.info("Requesting token with client_id=%s, secret=%s...", CLIENT_ID, secret[:4] + "****")
        try:
            resp = self.session.post(TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": secret,
                "scope": SCOPES,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            log.info("Token response: %s %s", resp.status_code, resp.text[:200])
            resp.raise_for_status()
            data = resp.json()
            self.token = data["access_token"]
            self.token_expires = now + data.get("expires_in", 3600)
            log.info("Token refreshed, expires in %ds", data.get("expires_in", 3600))
            return self.token
        except Exception as e:
            log.error("Token error: %s", e)
            return None

    def query(self, graphql_query, variables=None):
        """Execute a GraphQL query."""
        token = self.get_token()
        if not token:
            return None

        payload = {"query": graphql_query}
        if variables:
            payload["variables"] = variables

        try:
            resp = self.session.post(
                GRAPHQL_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}"}
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                log.warning("GraphQL errors: %s", result["errors"])
            return result.get("data")
        except Exception as e:
            log.error("Query error: %s", e)
            return None


# ============================================================================
# HELPERS
# ============================================================================

import re

def _fix_proshop_date(s):
    """Convert ProShop compact date (2026-02-18T150000Z) to ISO 8601 (2026-02-18T15:00:00Z)."""
    # Match compact time format: T followed by 6+ digits before Z
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})(\d{2})Z$', s)
    if m:
        return f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}Z"
    return s


# ============================================================================
# DATA COLLECTOR
# ============================================================================

# Query: get all active users with their latest clock punch and today's time tracking
EMPLOYEE_STATUS_QUERY = """
query($userId: String!, $todayDate: String!) {
  user(id: $userId) {
    id
    firstName
    lastName
    isActive
    timeClock(filter: { punchDate: { greaterThanOrEqual: $todayDate } }, pageSize: 5) {
      records {
        clockPunchId
        punchDate
        inOrOut
      }
    }
    timeTracking(filter: { timeIn: { greaterThanOrEqual: $todayDate } }, pageSize: 50) {
      records {
        id
        timeIn
        timeOut
        status
        operationNumber
        spentDoing
        qtyRun
        percentTime
        workOrderPlainText
        workCellPlainText
      }
    }
  }
}
"""

USERS_LIST_QUERY = """
query {
  users(pageSize: 50) {
    records {
      id
      firstName
      lastName
      isActive
    }
  }
}
"""


class DataCollector:
    """Polls ProShop and maintains current status for all employees."""

    def __init__(self, api: ProShopAPI):
        self.api = api
        self.active_users = []  # list of {id, firstName, lastName}
        self.status_data = {}   # user_id -> status dict
        self.last_update = None
        self.lock = threading.Lock()
        self.error_msg = None

    def load_users(self):
        """Fetch active user list from ProShop."""
        data = self.api.query(USERS_LIST_QUERY)
        if not data or "users" not in data:
            log.error("Failed to load users")
            self.error_msg = "Failed to load users from ProShop"
            return

        users = []
        for u in data["users"].get("records", []):
            uid = u.get("id", "")
            if u.get("isActive") and uid not in EXCLUDED_USER_IDS:
                users.append({
                    "id": uid,
                    "firstName": u.get("firstName", ""),
                    "lastName": u.get("lastName", ""),
                })
        self.active_users = sorted(users, key=lambda x: x["firstName"])
        log.info("Loaded %d active users: %s",
                 len(self.active_users),
                 ", ".join(f'{u["firstName"]} {u["lastName"]}' for u in self.active_users))

    def poll_user(self, user):
        """Get current status for one user."""
        now = datetime.now(timezone.utc)
        # Use local date for filtering (shop is Pacific time, UTC offset matters)
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_start = datetime.strptime(today_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        data = self.api.query(EMPLOYEE_STATUS_QUERY, {"userId": user["id"], "todayDate": today_str})
        if not data or "user" not in data:
            return None

        u = data["user"]

        # --- Clock status ---
        clock_records = u.get("timeClock", {}).get("records", [])
        clocked_in = False
        last_punch_time = None
        clock_punches = []  # all punches for display

        for rec in clock_records:
            punch_str = rec.get("punchDate", "")
            in_or_out = rec.get("inOrOut", "").lower()
            if punch_str:
                fixed = _fix_proshop_date(punch_str)
                clock_punches.append({"time": fixed, "inOrOut": in_or_out})

        if clock_records:
            latest = clock_records[-1]
            clocked_in = (latest.get("inOrOut", "").lower() == "in")
            punch_str = latest.get("punchDate", "")
            if punch_str:
                last_punch_time = _fix_proshop_date(punch_str)

        # --- Clocked hours (wall time from punch pairs) ---
        clocked_hours = 0.0
        parsed_punches = []
        for rec in clock_records:
            punch_str = rec.get("punchDate", "")
            if punch_str:
                fixed = _fix_proshop_date(punch_str)
                try:
                    pt = datetime.fromisoformat(fixed.replace("Z", "+00:00"))
                except Exception:
                    try:
                        pt = datetime.fromisoformat(fixed)
                        if pt.tzinfo is None:
                            pt = pt.replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
                parsed_punches.append((pt, rec.get("inOrOut", "").lower()))

        # Pair IN→OUT punches; unpaired IN uses now
        i = 0
        while i < len(parsed_punches):
            pt, direction = parsed_punches[i]
            if direction == "in":
                # Look for next OUT
                if i + 1 < len(parsed_punches) and parsed_punches[i + 1][1] == "out":
                    clocked_hours += (parsed_punches[i + 1][0] - pt).total_seconds() / 3600.0
                    i += 2
                else:
                    # Still clocked in
                    clocked_hours += (now - pt).total_seconds() / 3600.0
                    i += 1
            else:
                i += 1  # skip unpaired OUT

        # --- Time tracking entries ---
        tt_records = u.get("timeTracking", {}).get("records", [])

        # Find active entry (has timeIn but no timeOut)
        active_entry = None
        today_entries = []

        for entry in tt_records:
            time_in_str = entry.get("timeIn", "")
            time_out_str = entry.get("timeOut", "")

            # Parse timeIn
            time_in = None
            if time_in_str:
                try:
                    time_in = datetime.fromisoformat(time_in_str.replace("Z", "+00:00"))
                except:
                    try:
                        time_in = datetime.fromisoformat(time_in_str)
                        if time_in.tzinfo is None:
                            time_in = time_in.replace(tzinfo=timezone.utc)
                    except:
                        pass

            # Parse timeOut
            time_out = None
            if time_out_str:
                try:
                    time_out = datetime.fromisoformat(time_out_str.replace("Z", "+00:00"))
                except:
                    try:
                        time_out = datetime.fromisoformat(time_out_str)
                        if time_out.tzinfo is None:
                            time_out = time_out.replace(tzinfo=timezone.utc)
                    except:
                        pass

            # Active = has timeIn, no timeOut, status suggests running
            status = entry.get("status", "")
            if time_in and not time_out:
                active_entry = entry
                active_entry["_parsed_timeIn"] = time_in

            # Collect today's entries
            if time_in and time_in >= today_start:
                duration = 0
                if time_out:
                    duration = (time_out - time_in).total_seconds() / 3600.0
                elif time_in:
                    # Still running — count up to now
                    duration = (now - time_in).total_seconds() / 3600.0

                today_entries.append({
                    "workOrder": entry.get("workOrderPlainText", ""),
                    "operation": entry.get("operationNumber", ""),
                    "spentDoing": entry.get("spentDoing", ""),
                    "workCell": entry.get("workCellPlainText", ""),
                    "hours": round(duration, 2),
                    "active": (time_out is None),
                    "qtyRun": entry.get("qtyRun"),
                    "percentTime": entry.get("percentTime"),
                })

        # Total hours today
        total_hours_today = sum(e["hours"] for e in today_entries)

        # --- WO breakdown (group entries by work order) ---
        wo_map = {}
        for entry in today_entries:
            wo = entry["workOrder"] or "Unknown"
            if wo not in wo_map:
                wo_map[wo] = 0.0
            wo_map[wo] += entry["hours"]

        wo_breakdown = []
        for wo, hours in sorted(wo_map.items(), key=lambda x: x[1], reverse=True):
            pct = (hours / total_hours_today * 100) if total_hours_today > 0 else 0
            wo_breakdown.append({
                "workOrder": wo,
                "totalHours": round(hours, 2),
                "percent": round(pct, 1),
            })

        # --- Coverage: tracked vs clocked ---
        coverage_percent = 0.0
        if clocked_hours > 0:
            coverage_percent = min((total_hours_today / clocked_hours) * 100, 100.0)

        # Build active job description
        active_job = None
        if active_entry:
            elapsed = 0
            if active_entry.get("_parsed_timeIn"):
                elapsed = (now - active_entry["_parsed_timeIn"]).total_seconds() / 3600.0
            active_job = {
                "workOrder": active_entry.get("workOrderPlainText", ""),
                "operation": active_entry.get("operationNumber", ""),
                "spentDoing": active_entry.get("spentDoing", ""),
                "workCell": active_entry.get("workCellPlainText", ""),
                "elapsedHours": round(elapsed, 2),
            }

        return {
            "id": user["id"],
            "firstName": user["firstName"],
            "lastName": user["lastName"],
            "clockedIn": clocked_in,
            "lastPunchTime": last_punch_time,
            "clockPunches": clock_punches,
            "clockedHours": round(clocked_hours, 2),
            "activeJob": active_job,
            "todayEntries": today_entries,
            "totalHoursToday": round(total_hours_today, 2),
            "woBreakdown": wo_breakdown,
            "coveragePercent": round(coverage_percent, 1),
            "trackingActive": active_job is not None,
        }

    def poll_all(self):
        """Poll all active users and update status."""
        if not self.active_users:
            self.load_users()
            if not self.active_users:
                return

        results = {}
        for user in self.active_users:
            try:
                status = self.poll_user(user)
                if status:
                    results[user["id"]] = status
            except Exception as e:
                log.error("Error polling %s: %s", user["firstName"], e)

        with self.lock:
            self.status_data = results
            self.last_update = datetime.now(timezone.utc).isoformat()
            self.error_msg = None

        log.info("Updated %d employees", len(results))

    def get_snapshot(self):
        """Return current status data for the API."""
        with self.lock:
            return {
                "employees": list(self.status_data.values()),
                "lastUpdate": self.last_update,
                "error": self.error_msg,
                "version": VERSION,
            }

    def run_poll_loop(self):
        """Background thread: poll at POLL_INTERVAL."""
        log.info("Starting poll loop (interval=%ds)", POLL_INTERVAL)
        self.load_users()
        while True:
            try:
                self.poll_all()
            except Exception as e:
                log.error("Poll loop error: %s", e)
                with self.lock:
                    self.error_msg = str(e)
            time.sleep(POLL_INTERVAL)


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)
collector = None  # initialized in main


@app.route("/")
def index():
    """Serve the dashboard HTML."""
    html_path = Path(__file__).parent / "dashboard.html"
    return send_file(html_path)


@app.route("/api/status")
def api_status():
    """Return current employee status as JSON."""
    return jsonify(collector.get_snapshot())


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Force an immediate refresh."""
    threading.Thread(target=collector.poll_all, daemon=True).start()
    return jsonify({"status": "refreshing"})


# ============================================================================
# MAIN
# ============================================================================

def main():
    global collector

    if not CLIENT_SECRET and not os.environ.get("PROSHOP_CLIENT_SECRET"):
        print("=" * 60)
        print("  WARNING: PROSHOP_CLIENT_SECRET not set!")
        print("  Set the environment variable or edit the script.")
        print("  Running in DEMO mode with sample data.")
        print("=" * 60)

    api = ProShopAPI()
    collector = DataCollector(api)

    # Start background polling
    poll_thread = threading.Thread(target=collector.run_poll_loop, daemon=True)
    poll_thread.start()

    # Start web server
    log.info("Starting dashboard at http://localhost:%d", PORT)
    _serve_with_shutdown(app, HOST, PORT)


def _serve_with_shutdown(app, host, port, channel_timeout=30):
    """Run app under waitress with a /api/shutdown route for graceful stop."""
    import threading
    from waitress import create_server

    shutdown_event = threading.Event()

    @app.route("/api/shutdown", methods=["POST"])
    def _api_shutdown():
        shutdown_event.set()
        return ("shutting down", 200)

    server = create_server(app, host=host, port=port, channel_timeout=channel_timeout)

    def _waiter():
        shutdown_event.wait()
        server.close()

    threading.Thread(target=_waiter, daemon=True).start()
    print(f"Serving on http://{host}:{port} (waitress)", flush=True)
    server.run()


if __name__ == "__main__":
    main()
