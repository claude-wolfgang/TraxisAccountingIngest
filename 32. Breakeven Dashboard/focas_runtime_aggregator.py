#!/usr/bin/env python3
"""FOCAS Runtime Aggregator — queries FASData monitoring.db and outputs
a JSON snapshot of per-machine weekly runtime for the breakeven dashboard."""

import argparse
import json
import logging
import os
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "focas_aggregator.log")
TZ_DEFAULT = "America/Chicago"
RUNNING_STATE = "STRT"
# Gap threshold: if two consecutive samples are more than this many seconds
# apart, do not count the interval (monitor was likely down).
GAP_THRESHOLD_S = 120
# Machine status thresholds
STALE_THRESHOLD_S = 600     # 10 minutes
OFFLINE_THRESHOLD_S = 86400  # 24 hours


def setup_logging():
    logger = logging.getLogger("focas_agg")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def load_config():
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if not os.path.exists(config_path):
        return {
            "db_path": r"C:\FASData\monitoring.db",
            "timezone": TZ_DEFAULT,
        }
    with open(config_path, "r") as f:
        return json.load(f)


def get_enabled_machines(config):
    """Load machine list from machines.json or config."""
    machines_file = config.get("machines_file")
    if machines_file and os.path.exists(machines_file):
        with open(machines_file, "r") as f:
            data = json.load(f)
        return [m for m in data.get("machines", []) if m.get("enabled", True)]

    # Fallback: look relative to db_path
    db_dir = os.path.dirname(config.get("db_path", ""))
    candidate = os.path.join(db_dir, "machines.json")
    if os.path.exists(candidate):
        with open(candidate, "r") as f:
            data = json.load(f)
        return [m for m in data.get("machines", []) if m.get("enabled", True)]

    # Hard fallback: return None so we discover from DB
    return None


def week_bounds(tz, week_str=None):
    """Return (monday_00:00, sunday_23:59:59) as aware datetimes for the
    given ISO week string (e.g. '2026-W16') or the current week."""
    if week_str:
        # Parse ISO week: YYYY-Www
        year, wk = week_str.split("-W")
        # Monday of that week
        jan4 = datetime(int(year), 1, 4, tzinfo=tz)
        start_of_w1 = jan4 - timedelta(days=jan4.weekday())
        monday = start_of_w1 + timedelta(weeks=int(wk) - 1)
    else:
        now = datetime.now(tz)
        monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def parse_ts(ts_str, tz):
    """Parse a .NET-style ISO timestamp from the DB into an aware datetime."""
    # Format: 2026-04-16T10:30:35.4393845-05:00
    # Python can't parse 7-digit fractional seconds — truncate to 6.
    if not ts_str:
        return None
    try:
        # Split off the timezone offset
        # Find the last + or - that's part of the offset (after the T)
        t_idx = ts_str.index("T")
        rest = ts_str[t_idx:]
        # Find the timezone offset: look for +/- after seconds
        off_idx = -1
        for i in range(len(rest) - 1, 0, -1):
            if rest[i] in "+-":
                off_idx = t_idx + i
                break
        if off_idx == -1:
            # No offset, treat as local
            base = ts_str
            off_str = None
        else:
            base = ts_str[:off_idx]
            off_str = ts_str[off_idx:]

        # Truncate fractional seconds to 6 digits
        if "." in base:
            dot = base.index(".")
            frac = base[dot + 1:]
            if len(frac) > 6:
                frac = frac[:6]
            base = base[:dot + 1] + frac

        if off_str:
            full = base + off_str
            dt = datetime.fromisoformat(full)
        else:
            dt = datetime.fromisoformat(base).replace(tzinfo=tz)
        return dt
    except (ValueError, IndexError):
        return None


def compute_runtime(rows, tz, gap_threshold=GAP_THRESHOLD_S):
    """Given sorted (timestamp, run_status) rows for one machine in one week,
    compute total runtime seconds using the sample-interval method."""
    if len(rows) < 2:
        return 0.0, 0.0

    # Parse all timestamps
    parsed = []
    for ts_str, status in rows:
        dt = parse_ts(ts_str, tz)
        if dt:
            parsed.append((dt, status))
    parsed.sort(key=lambda x: x[0])

    if len(parsed) < 2:
        return 0.0, 0.0

    # Compute intervals between consecutive samples
    intervals = []
    for i in range(1, len(parsed)):
        gap = (parsed[i][0] - parsed[i - 1][0]).total_seconds()
        if 0 < gap <= gap_threshold:
            intervals.append(gap)

    median_interval = statistics.median(intervals) if intervals else 60.0

    # Count runtime: for each sample (except last), if it's STRT and the
    # gap to next sample is within threshold, count median_interval seconds.
    runtime_s = 0.0
    for i in range(len(parsed) - 1):
        dt_now, status_now = parsed[i]
        dt_next = parsed[i + 1][0]
        gap = (dt_next - dt_now).total_seconds()
        if status_now == RUNNING_STATE and 0 < gap <= gap_threshold:
            runtime_s += min(gap, median_interval * 1.5)
            # Use actual gap but cap at 1.5x median to avoid over-counting
            # from occasional longer intervals

    return runtime_s, median_interval


def machine_status(last_sample_dt, now):
    """Determine online/stale/offline from last sample time."""
    if last_sample_dt is None:
        return "offline"
    delta = (now - last_sample_dt).total_seconds()
    if delta <= STALE_THRESHOLD_S:
        return "online"
    elif delta <= OFFLINE_THRESHOLD_S:
        return "stale"
    return "offline"


def aggregate_week(db_path, tz, week_start, week_end, machine_list, logger):
    """Aggregate runtime for all machines for a given week."""
    now = datetime.now(tz)

    try:
        conn = sqlite3.connect(db_path, timeout=10)
    except Exception as e:
        logger.error("Cannot connect to DB %s: %s", db_path, e)
        # Return error snapshot
        machines_out = []
        if machine_list:
            for m in machine_list:
                machines_out.append({
                    "id": m["id"],
                    "name": m["name"],
                    "runtime_hours": 0,
                    "last_sample_at": None,
                    "status": "offline",
                })
        return machines_out, str(e)

    cur = conn.cursor()

    # Get all machine IDs from DB if no machine_list provided
    if not machine_list:
        cur.execute("SELECT DISTINCT machine_id FROM machine_samples ORDER BY machine_id")
        machine_list = [{"id": r[0], "name": r[0]} for r in cur.fetchall()]

    # Resolve names from DB for each machine (use latest name)
    machine_names = {}
    for m in machine_list:
        cur.execute(
            "SELECT machine_name FROM machine_samples WHERE machine_id=? "
            "ORDER BY id DESC LIMIT 1",
            (m["id"],),
        )
        row = cur.fetchone()
        machine_names[m["id"]] = row[0] if row else m.get("name", m["id"])

    ws = week_start.isoformat()
    we = week_end.isoformat()

    machines_out = []
    for m in machine_list:
        mid = m["id"]

        # Fetch samples for this machine in the week window
        cur.execute(
            "SELECT timestamp, run_status FROM machine_samples "
            "WHERE machine_id=? AND timestamp >= ? AND timestamp <= ? "
            "ORDER BY timestamp",
            (mid, ws, we),
        )
        rows = cur.fetchall()

        runtime_s, median_int = compute_runtime(rows, tz)

        # Last sample overall (not just this week)
        cur.execute(
            "SELECT timestamp FROM machine_samples WHERE machine_id=? "
            "ORDER BY id DESC LIMIT 1",
            (mid,),
        )
        last_row = cur.fetchone()
        last_sample_dt = parse_ts(last_row[0], tz) if last_row else None
        last_sample_str = last_sample_dt.isoformat() if last_sample_dt else None

        status = machine_status(last_sample_dt, now)

        machines_out.append({
            "id": mid,
            "name": machine_names.get(mid, m.get("name", mid)),
            "runtime_hours": round(runtime_s / 3600, 2),
            "runtime_seconds": round(runtime_s, 1),
            "median_sample_interval_s": round(median_int, 1),
            "samples_in_week": len(rows),
            "last_sample_at": last_sample_str,
            "status": status,
        })
        logger.info(
            "Machine %s: %.1f hrs (%d samples, median=%.0fs, status=%s)",
            mid, runtime_s / 3600, len(rows), median_int, status,
        )

    conn.close()
    return machines_out, None


def compute_daily_breakdown(db_path, tz, week_start, machine_list, logger,
                            full_week=False):
    """Compute per-day runtime totals for the week, with per-machine detail.
    Only includes days up to and including today, unless full_week=True
    (used for completed past weeks)."""
    now = datetime.now(tz)

    try:
        conn = sqlite3.connect(db_path, timeout=10)
    except Exception as e:
        logger.error("Daily breakdown DB error: %s", e)
        return []

    cur = conn.cursor()

    if not machine_list:
        cur.execute("SELECT DISTINCT machine_id FROM machine_samples ORDER BY machine_id")
        machine_list = [{"id": r[0], "name": r[0]} for r in cur.fetchall()]

    days = []
    for day_offset in range(7):
        day_start = week_start + timedelta(days=day_offset)
        day_start = day_start.replace(hour=0, minute=0, second=0, microsecond=0)
        if not full_week and day_start.date() > now.date():
            break
        day_end = day_start.replace(hour=23, minute=59, second=59)

        ds = day_start.isoformat()
        de = day_end.isoformat()

        day_total_s = 0.0
        per_machine = {}
        for m in machine_list:
            cur.execute(
                "SELECT timestamp, run_status FROM machine_samples "
                "WHERE machine_id=? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp",
                (m["id"], ds, de),
            )
            rows = cur.fetchall()
            rt_s, _ = compute_runtime(rows, tz)
            day_total_s += rt_s
            per_machine[m["id"]] = round(rt_s / 3600, 2)

        days.append({
            "date": day_start.date().isoformat(),
            "day_name": day_start.strftime("%a"),
            "hours": round(day_total_s / 3600, 2),
            "machines": per_machine,
        })

    conn.close()
    logger.info("Daily breakdown: %s", [(d["day_name"], d["hours"]) for d in days])
    return days


def build_snapshot(db_path, tz_name=TZ_DEFAULT, history=0, week=None,
                   machine_list=None, logger=None):
    """Build the runtime snapshot dict (current week + optional history weeks).

    Pure compute + DB read; no file I/O. Callable both from the CLI and from
    the dashboard service's in-process aggregator loop. Pass machine_list=None
    to discover machines directly from the DB."""
    if logger is None:
        logger = logging.getLogger("focas_agg")
    tz = ZoneInfo(tz_name)

    week_start, week_end = week_bounds(tz, week)
    logger.info("Week: %s to %s", week_start.date(), week_end.date())

    machines_out, error = aggregate_week(db_path, tz, week_start, week_end, machine_list, logger)
    daily = compute_daily_breakdown(db_path, tz, week_start, machine_list, logger)

    hist = []
    if history > 0:
        for i in range(1, history + 1):
            hist_start = week_start - timedelta(weeks=i)
            hist_end = hist_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            hist_machines, _ = aggregate_week(db_path, tz, hist_start, hist_end, machine_list, logger)
            hist_daily = compute_daily_breakdown(
                db_path, tz, hist_start, machine_list, logger, full_week=True)
            total_hrs = sum(m["runtime_hours"] for m in hist_machines)
            hist.append({
                "week_start": hist_start.date().isoformat(),
                "week_end": hist_end.date().isoformat(),
                "total_hours": round(total_hrs, 2),
                "machines": hist_machines,
                "daily": hist_daily,
            })
        hist.reverse()  # chronological order

    snapshot = {
        "generated_at": datetime.now(tz).isoformat(),
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "runtime_signal": f"run_status={RUNNING_STATE}",
        "sample_interval_config_s": 60,
        "gap_threshold_s": GAP_THRESHOLD_S,
        "machines": machines_out,
        "daily": daily,
    }
    if hist:
        snapshot["history"] = hist
    if error:
        snapshot["error"] = error
    return snapshot


def write_snapshot(snapshot, out_path):
    """Write the snapshot as <out>.json plus a file://-friendly <out>.js."""
    out_path = str(out_path)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    js_path = out_path[:-5] + ".js" if out_path.endswith(".json") else out_path + ".js"
    with open(js_path, "w") as f:
        f.write("window.RUNTIME_DATA = ")
        json.dump(snapshot, f, indent=2)
        f.write(";\n")
    return out_path, js_path


def main():
    parser = argparse.ArgumentParser(description="FOCAS Runtime Aggregator")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument("--week", default=None, help="ISO week (e.g. 2026-W16)")
    parser.add_argument("--history", type=int, default=0,
                        help="Include N prior weeks of history")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=== Aggregator run started ===")

    config = load_config()
    db_path = config.get("db_path", r"C:\FASData\monitoring.db")
    tz_name = config.get("timezone", TZ_DEFAULT)
    machine_list = get_enabled_machines(config)

    snapshot = build_snapshot(db_path, tz_name, history=args.history,
                              week=args.week, machine_list=machine_list, logger=logger)

    out_path = args.out or os.path.join(SCRIPT_DIR, "runtime_snapshot.json")
    out_path, _ = write_snapshot(snapshot, out_path)

    logger.info("Wrote snapshot to %s (+.js)", out_path)
    print(f"Wrote {out_path}")
    total = sum(m["runtime_hours"] for m in snapshot["machines"])
    print(f"Total runtime this week: {total:.1f} hrs across {len(snapshot['machines'])} machines")


if __name__ == "__main__":
    main()
