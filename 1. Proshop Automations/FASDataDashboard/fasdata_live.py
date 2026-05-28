#!/usr/bin/env python3
"""
Traxis Shop Hub Dashboard v2.0
================================
Live machine utilization dashboard with ProShop ERP integration
and shop floor messaging. Extends FASData Live Dashboard v1.0.

Reads machine data from FocasMonitor SQLite database, looks up
work orders via ProShop GraphQL API, and provides real-time
messaging between shop floor stations.

Serves an Aztec-themed 1920x1080 dashboard for shop floor display.

Usage:
    python fasdata_live.py
    Then open http://localhost:8070 in a browser.

Dependencies:
    pip install flask requests
"""

import os
import sys
import json
import time
import sqlite3
import logging
import threading
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

try:
    from flask import Flask, jsonify, send_file, request
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: py -m pip install flask")
    sys.exit(1)

from part_parser import extract_part_number
from proshop_client import ProShopClient
from message_store import MessageStore

# ============================================================================
# CONFIGURATION
# ============================================================================

HOST = "0.0.0.0"
PORT = 8070
DB_PATH = os.environ.get("TRAXIS_FOCAS_DB", r"C:\FASData\monitoring.db")

# --- Breakeven dashboard (P32), served from this same process off the live DB ---
BREAKEVEN_DIR = Path(__file__).resolve().parent.parent.parent / "32. Breakeven Dashboard"
SNAPSHOT_DIR = Path(os.environ.get("TRAXIS_BREAKEVEN_DIR", r"C:\FASData\breakeven"))
SNAPSHOT_JSON = SNAPSHOT_DIR / "runtime_snapshot.json"
SNAPSHOT_JS = SNAPSHOT_DIR / "runtime_snapshot.js"
AGG_INTERVAL_S = 150          # regenerate snapshot every 2.5 min (client refreshes every 5)
AGG_HISTORY_WEEKS = 4
AGG_TZ = "America/Chicago"

SHIFT_START_HOUR = 6   # 6 AM
SHIFT_END_HOUR = 19    # 7 PM
SHIFT_DAYS = range(0, 5)  # Mon-Fri

GREEN_THRESHOLD = 30
YELLOW_THRESHOLD = 10

# FOCAS spindle_speed values above this are flag/error codes (e.g. 131072 = 0x20000)
SPINDLE_SPEED_MAX_VALID = 100000

# Machine display names (from machines.json)
MACHINE_NAMES = {
    "T2": ("YCM NTC1600LY", "Lathe"),
    "M2": ("FANUC Mill 2", "Mill"),
    "M3": ("FANUC Mill 3", "Mill"),
    "M4": ("Robodrill 4", "Mill"),
    "M5": ("Robodrill 5", "Mill"),
    "M6": ("FANUC Mill 6", "Mill"),
    "M7": ("Robodrill 7", "Mill"),
    "M8": ("FANUC Mill 8", "Mill"),
}

VERSION = "2.1"

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ShopHub")

# ============================================================================
# SHOP HUB SERVICES (initialized in main())
# ============================================================================

proshop: ProShopClient | None = None
messages: MessageStore | None = None

# ============================================================================
# DATABASE QUERIES
# ============================================================================

def get_db():
    """Open a read-only connection to the monitoring database."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def query_current_status():
    """Get the latest sample for each machine."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT ms.*
            FROM machine_samples ms
            INNER JOIN (
                SELECT machine_id, MAX(timestamp) as max_ts
                FROM machine_samples
                GROUP BY machine_id
            ) latest ON ms.machine_id = latest.machine_id
                     AND ms.timestamp = latest.max_ts
            ORDER BY ms.machine_id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_today_utilization():
    """Compute today's utilization per machine during shift hours."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Shift window for today
    shift_start = f"{today_str}T{SHIFT_START_HOUR:02d}:00:00"
    shift_end = f"{today_str}T{SHIFT_END_HOUR:02d}:00:00"

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT
                machine_id,
                COUNT(*) as total_samples,
                SUM(CASE
                    WHEN connected = 1
                    AND (run_status IN ('STRT','MSTR')
                         OR (spindle_speed > 0 AND spindle_speed < ?))
                    THEN 1 ELSE 0
                END) as running_samples,
                SUM(CASE
                    WHEN connected = 1
                    AND (run_status IN ('STRT','MSTR')
                         OR (spindle_speed > 0 AND spindle_speed < ?))
                    AND (motion IN ('MTN','DWL','MOTION')
                         OR feed_rate > 0)
                    THEN 1 ELSE 0
                END) as cutting_samples,
                SUM(CASE WHEN connected = 1 THEN 1 ELSE 0 END) as connected_samples
            FROM machine_samples
            WHERE date(timestamp, 'localtime') = ?
            GROUP BY machine_id
            ORDER BY machine_id
        """, (SPINDLE_SPEED_MAX_VALID, SPINDLE_SPEED_MAX_VALID,
              today_str)).fetchall()
        return {r["machine_id"]: dict(r) for r in rows}
    finally:
        conn.close()


# ============================================================================
# API DATA BUILDER
# ============================================================================

def build_machine_data():
    """Build the full machine status payload."""
    now = datetime.now()

    # Get current readings and today's utilization
    try:
        current = query_current_status()
        utilization = query_today_utilization()
    except Exception as e:
        log.error("Database error: %s", e)
        return {"error": str(e), "machines": {}, "timestamp": now.isoformat()}

    # Hours into shift today
    if now.hour < SHIFT_START_HOUR:
        shift_elapsed = 0
    elif now.hour >= SHIFT_END_HOUR:
        shift_elapsed = SHIFT_END_HOUR - SHIFT_START_HOUR
    else:
        shift_elapsed = (now.hour - SHIFT_START_HOUR) + now.minute / 60.0

    poll_interval = 60  # seconds per sample

    machines = {}
    total_cutting_hours = 0
    total_available_hours = 0
    active_count = 0

    for sample in current:
        mid = sample["machine_id"]
        name, mtype = MACHINE_NAMES.get(mid, (mid, "Unknown"))

        # Parse latest timestamp
        last_ts = sample.get("timestamp", "")
        try:
            last_dt = datetime.fromisoformat(last_ts)
            if last_dt.tzinfo:
                last_dt = last_dt.replace(tzinfo=None)
            age_seconds = (now - last_dt).total_seconds()
        except Exception:
            age_seconds = 9999

        connected = bool(sample.get("connected"))
        online = connected and age_seconds < 300  # 5 min freshness

        # Clean spindle speed (131072 = 0x20000 is a FOCAS flag, not real RPM)
        raw_spindle = sample.get("spindle_speed", 0) or 0
        display_spindle = raw_spindle if 0 < raw_spindle < SPINDLE_SPEED_MAX_VALID else 0

        # Determine if currently cutting (for live status display)
        cur_motion = sample.get("motion", "")
        cur_feed = sample.get("feed_rate", 0) or 0
        cur_run = sample.get("run_status", "")
        is_running = cur_run in ("STRT", "MSTR") or display_spindle > 0
        is_cutting = is_running and (cur_motion in ("MTN", "DWL", "MOTION") or cur_feed > 0)

        # Utilization from today's shift
        util = utilization.get(mid, {})
        total_samples = util.get("total_samples", 0)
        cutting_samples = util.get("cutting_samples", 0)
        running_samples = util.get("running_samples", 0)

        if total_samples > 0 and online:
            hours_cutting = round(cutting_samples * poll_interval / 3600.0, 1)
            hours_available = round(shift_elapsed, 1)
            cutting_pct = round(100.0 * hours_cutting / hours_available, 1) if hours_available > 0 else 0
        elif online:
            cutting_pct = 0
            hours_cutting = 0
            hours_available = round(shift_elapsed, 1)
        else:
            cutting_pct = 0
            hours_cutting = 0
            hours_available = 0

        # Status thresholds
        if not online:
            status = "OFFLINE"
        elif cutting_pct >= GREEN_THRESHOLD:
            status = "GREEN"
        elif cutting_pct >= YELLOW_THRESHOLD:
            status = "YELLOW"
        else:
            status = "RED"

        if online:
            active_count += 1
            total_cutting_hours += hours_cutting
            total_available_hours += hours_available

        # --- Shop Hub: program comment and part detection ---
        raw_comment = sample.get("program_comment", "") or ""
        detected_part = extract_part_number(raw_comment) if raw_comment else None

        # ProShop WO lookup
        wo_data = []
        if detected_part and proshop:
            try:
                wo_data = proshop.lookup_part(detected_part)
            except Exception as e:
                log.warning("ProShop lookup failed for %s: %s", detected_part, e)

        # Emergency / alarm status
        emergency = bool(sample.get("emergency"))
        alarm_val = sample.get("alarm", 0) or 0

        machines[mid] = {
            "name": name,
            "type": mtype,
            "connected": online,
            "mode": sample.get("mode", ""),
            "run_status": sample.get("run_status", ""),
            "motion": cur_motion,
            "is_running": is_running,
            "is_cutting": is_cutting,
            "spindle_speed": display_spindle,
            "feed_rate": cur_feed,
            "program_number": sample.get("program_number", 0),
            "main_program": sample.get("main_program", 0),
            "alarm": bool(alarm_val),
            "alarm_message": sample.get("alarm_message", ""),
            "emergency": emergency,
            "cutting_pct": cutting_pct,
            "hours_cutting": hours_cutting,
            "hours_available": hours_available,
            "status": status,
            "last_sample": last_ts,
            "age_seconds": round(age_seconds),
            # Live machine data
            "spindle_load": sample.get("spindle_load"),
            "servo_load_x": sample.get("servo_load_x"),
            "servo_load_y": sample.get("servo_load_y"),
            "servo_load_z": sample.get("servo_load_z"),
            "axis_x": sample.get("axis_x"),
            "axis_y": sample.get("axis_y"),
            "axis_z": sample.get("axis_z"),
            "sequence_number": sample.get("sequence_number"),
            "block_count": sample.get("block_count"),
            # Shop Hub fields
            "program_comment": raw_comment or None,
            "detected_part": detected_part,
            "work_orders": wo_data,
        }

    total_count = len(machines)
    shop_avg = round(
        100.0 * total_cutting_hours / total_available_hours, 1
    ) if total_available_hours > 0 else 0

    return {
        "machines": machines,
        "shop_avg": shop_avg,
        "active_count": active_count,
        "total_count": total_count,
        "total_hours_cutting": round(total_cutting_hours, 1),
        "total_hours_available": round(total_available_hours, 1),
        "shift_hours": f"{SHIFT_START_HOUR}:00 - {SHIFT_END_HOUR}:00",
        "date": now.strftime("%A, %B %d, %Y"),
        "timestamp": now.isoformat(),
        "version": VERSION,
        "error": None,
    }


# ============================================================================
# BREAKEVEN AGGREGATOR (P32) — runs in-process so Overseer's health check on
# this service also keeps the breakeven snapshot fresh.
# ============================================================================

def _load_aggregator():
    """Import focas_runtime_aggregator.py from the P32 folder by path."""
    path = BREAKEVEN_DIR / "focas_runtime_aggregator.py"
    spec = importlib.util.spec_from_file_location("focas_runtime_aggregator", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def aggregator_loop():
    """Regenerate the breakeven runtime snapshot from the live DB on a timer.
    Machines are discovered from the DB (no machines.json dependency)."""
    try:
        agg = _load_aggregator()
    except Exception as e:
        log.error("Breakeven aggregator unavailable (%s) — /breakeven will be empty", e)
        return

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            snap = agg.build_snapshot(DB_PATH, AGG_TZ, history=AGG_HISTORY_WEEKS, logger=log)
            agg.write_snapshot(snap, str(SNAPSHOT_JSON))
            log.info("Breakeven snapshot updated (%d machines)", len(snap.get("machines", [])))
        except Exception as e:
            log.error("Breakeven aggregation failed: %s", e)
        time.sleep(AGG_INTERVAL_S)


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)


@app.route("/")
def index():
    return send_file(Path(__file__).parent / "fasdata_dashboard.html")


@app.route("/api/status")
def api_status():
    """Full machine data — used by dashboard and overseer health checks."""
    return jsonify(build_machine_data())


# --- Breakeven dashboard (P32) -------------------------------------------------

@app.route("/breakeven")
def breakeven():
    return send_file(BREAKEVEN_DIR / "breakeven.html")


@app.route("/runtime_snapshot.js")
def runtime_snapshot_js():
    """Served to /breakeven via its relative <script src="runtime_snapshot.js">."""
    if SNAPSHOT_JS.exists():
        return send_file(SNAPSHOT_JS, mimetype="application/javascript")
    return ("window.RUNTIME_DATA = null;\n", 200,
            {"Content-Type": "application/javascript"})


@app.route("/runtime_snapshot.json")
def runtime_snapshot_json():
    if SNAPSHOT_JSON.exists():
        return send_file(SNAPSHOT_JSON, mimetype="application/json")
    return jsonify({"error": "snapshot not generated yet"}), 503


# ============================================================================
# MESSAGING API
# ============================================================================

@app.route("/api/messages", methods=["GET"])
def api_messages_get():
    """Get messages for a machine or shop-wide (machine_id omitted)."""
    machine_id = request.args.get("machine_id")
    limit = min(int(request.args.get("limit", 20)), 100)
    if messages:
        return jsonify(messages.get_messages(machine_id=machine_id, limit=limit))
    return jsonify([])


@app.route("/api/messages", methods=["POST"])
def api_messages_post():
    """Post a new message."""
    if not messages:
        return jsonify({"error": "messaging not initialized"}), 503

    data = request.get_json(force=True)
    author = (data.get("author") or "").strip()
    text = (data.get("message") or "").strip()
    machine_id = data.get("machine_id")  # None for shop-wide
    work_order = data.get("work_order")

    if not author or not text:
        return jsonify({"error": "author and message required"}), 400
    if len(text) > 500:
        return jsonify({"error": "message too long (500 char max)"}), 400

    msg = messages.add_message(
        author=author,
        message=text,
        machine_id=machine_id or None,
        work_order=work_order,
    )
    return jsonify(msg), 201


@app.route("/api/messages/all", methods=["GET"])
def api_messages_all():
    """Get all recent messages across all channels."""
    limit = min(int(request.args.get("limit", 50)), 200)
    if messages:
        return jsonify(messages.get_all_recent(limit=limit))
    return jsonify([])


# ============================================================================
# MAIN
# ============================================================================

def main():
    global proshop, messages

    # Initialize messaging
    messages = MessageStore()
    log.info("Message store ready at %s", messages.db_path)

    # Initialize ProShop client with background cache refresh
    proshop = ProShopClient()

    def proshop_refresh_loop():
        while True:
            try:
                proshop.refresh_wo_cache()
            except Exception as e:
                log.error("ProShop refresh error: %s", e)
            time.sleep(300)  # 5 minutes

    refresh_thread = threading.Thread(target=proshop_refresh_loop, daemon=True)
    refresh_thread.start()

    # Breakeven snapshot regenerator (serves /breakeven off the live DB)
    agg_thread = threading.Thread(target=aggregator_loop, daemon=True)
    agg_thread.start()

    if not Path(DB_PATH).exists():
        print(f"WARNING: Database not found at {DB_PATH}")
        print("FocasMonitor service may not be running.")

    log.info("Shop Hub Dashboard v%s at http://localhost:%d", VERSION, PORT)
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
