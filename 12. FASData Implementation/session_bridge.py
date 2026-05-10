#!/usr/bin/env python3
"""
Session Bridge Report — CAM vs Machine Execution
Traxis Manufacturing

Joins TraxisCapture diff records (what the programmer changed) with
FocasMonitor machine execution data (what actually happened on the CNC)
by matching on capture_session_id.

Usage:
  python session_bridge.py                   # auto-detect paths, demo if no data
  python session_bridge.py --demo            # force sample data mode
  python session_bridge.py --db path.db --diffs-dir path/to/diffs
"""

import json
import os
import sys
import glob
import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_DIFFS_DIRS = [
    r"D:\Dropbox\MACHINE COMM Traxis\Programming Sessions\diffs",
    r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Programming Sessions\diffs",
    os.path.join(SCRIPT_DIR, "test_diffs"),
]

DEFAULT_DB_PATHS = [
    r"D:\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db",
    r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db",
    os.path.join(SCRIPT_DIR, "monitoring.db"),
]

DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "session_bridge_report.html")


# ---------------------------------------------------------------------------
# Path detection
# ---------------------------------------------------------------------------

def find_diffs_dir():
    """Find the diffs directory."""
    for path in DEFAULT_DIFFS_DIRS:
        if os.path.isdir(path):
            return path
    return None


def find_database():
    """Find monitoring.db."""
    for path in DEFAULT_DB_PATHS:
        if os.path.isfile(path):
            return path
    return None


# ---------------------------------------------------------------------------
# JSONL reader
# ---------------------------------------------------------------------------

def read_all_diffs(diffs_dir):
    """Read all diff JSONL files, return dict keyed by session_id."""
    sessions = {}
    for filepath in sorted(glob.glob(os.path.join(diffs_dir, "*_diff.jsonl"))):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        sid = rec.get("session_id")
                        if sid:
                            sessions[sid] = rec
        except Exception as e:
            print(f"  Warning: Could not read {filepath}: {e}")
    return sessions


# ---------------------------------------------------------------------------
# SQLite reader
# ---------------------------------------------------------------------------

def query_capture_sessions(db_path):
    """Query monitoring.db for all capture-tagged data, grouped by session."""
    if not os.path.isfile(db_path):
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sessions = defaultdict(lambda: {
        "samples": [], "tool_wear": [], "alarms": [],
        "machine_id": None, "machine_name": None,
    })

    # Machine samples
    try:
        for row in conn.execute("""
            SELECT capture_session_id, capture_op_id, capture_tool_id,
                   machine_id, machine_name, timestamp,
                   spindle_speed, feed_rate, spindle_load,
                   feedrate_override, spindle_override,
                   run_status, motion, program_number, tool_number
            FROM machine_samples
            WHERE capture_session_id IS NOT NULL
            ORDER BY capture_session_id, timestamp
        """):
            sid = row["capture_session_id"]
            sessions[sid]["samples"].append(dict(row))
            if sessions[sid]["machine_id"] is None:
                sessions[sid]["machine_id"] = row["machine_id"]
                sessions[sid]["machine_name"] = row["machine_name"]
    except Exception as e:
        print(f"  Warning: machine_samples query failed: {e}")

    # Tool wear
    try:
        for row in conn.execute("""
            SELECT capture_session_id, tool_number,
                   length_wear, diameter_wear, timestamp
            FROM tool_wear_samples
            WHERE capture_session_id IS NOT NULL
            ORDER BY capture_session_id, timestamp
        """):
            sessions[row["capture_session_id"]]["tool_wear"].append(dict(row))
    except Exception as e:
        print(f"  Warning: tool_wear query failed: {e}")

    # Alarms
    try:
        for row in conn.execute("""
            SELECT capture_session_id, alarm_number, alarm_message,
                   timestamp, program_number
            FROM alarm_history
            WHERE capture_session_id IS NOT NULL
            ORDER BY capture_session_id, timestamp
        """):
            sessions[row["capture_session_id"]]["alarms"].append(dict(row))
    except Exception as e:
        print(f"  Warning: alarm_history query failed: {e}")

    conn.close()
    return dict(sessions)


# ---------------------------------------------------------------------------
# Session matching
# ---------------------------------------------------------------------------

def match_sessions(diff_sessions, machine_sessions):
    """Join JSONL diff data with SQLite machine data by session_id."""
    matched = []
    common_ids = set(diff_sessions.keys()) & set(machine_sessions.keys())
    for sid in sorted(common_ids):
        matched.append({
            "session_id": sid,
            "diff_data": diff_sessions[sid],
            "machine_data": machine_sessions[sid],
        })
    return matched


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _safe_avg(values):
    """Average of non-zero values, or 0."""
    filtered = [v for v in values if v and v > 0]
    return round(sum(filtered) / len(filtered), 1) if filtered else 0


def _safe_max(values):
    """Max of values, or 0."""
    filtered = [v for v in values if v is not None]
    return max(filtered) if filtered else 0


def analyze_matched_session(match):
    """Analyze a single matched session."""
    diff_data = match["diff_data"]
    machine_data = match["machine_data"]
    samples = machine_data["samples"]

    # --- JSONL side ---
    diff = diff_data.get("diff", {})
    delta = diff.get("delta", {})

    changes = []
    for mod in delta.get("operations_modified", []):
        for change in mod.get("changes", []):
            changes.append({
                "operation": mod.get("operation", ""),
                "tool_id": mod.get("tool_id", ""),
                "field": change.get("field", ""),
                "from_val": change.get("from", ""),
                "to_val": change.get("to", ""),
                "category": change.get("category", ""),
            })

    ops_added = delta.get("operations_added", [])
    ops_removed = delta.get("operations_removed", [])

    # Programmed values from snapshot_b
    programmed_ops = {}
    snapshot_b = diff_data.get("snapshot_b") or {}
    for setup in snapshot_b.get("setups", []):
        for op in setup.get("operations", []):
            name = op.get("name", "")
            feeds = op.get("feeds", {})
            programmed_ops[name] = {
                "spindle_rpm": feeds.get("spindle_rpm"),
                "feed_ipm": feeds.get("cutting_feedrate_ipm"),
            }

    # --- Machine side ---
    spindle_speeds = [s.get("spindle_speed", 0) for s in samples]
    feed_rates = [s.get("feed_rate", 0) for s in samples]
    spindle_loads = [s.get("spindle_load", 0) for s in samples]
    feed_overrides = [s.get("feedrate_override") for s in samples]
    spindle_overrides = [s.get("spindle_override") for s in samples]

    # Cycle duration
    cycle_duration_min = 0
    if len(samples) >= 2:
        try:
            t0 = datetime.fromisoformat(samples[0]["timestamp"])
            t1 = datetime.fromisoformat(samples[-1]["timestamp"])
            cycle_duration_min = round((t1 - t0).total_seconds() / 60, 1)
        except Exception:
            pass

    # Tool wear deltas
    tool_wear_deltas = {}
    wear_data = machine_data.get("tool_wear", [])
    if wear_data:
        by_tool = defaultdict(list)
        for tw in wear_data:
            by_tool[tw["tool_number"]].append(tw)
        for tn, readings in by_tool.items():
            if len(readings) >= 2:
                first = readings[0]
                last = readings[-1]
                lw_delta = (last.get("length_wear") or 0) - (first.get("length_wear") or 0)
                dw_delta = (last.get("diameter_wear") or 0) - (first.get("diameter_wear") or 0)
                if lw_delta != 0 or dw_delta != 0:
                    tool_wear_deltas[tn] = {
                        "length_wear_delta": lw_delta,
                        "diameter_wear_delta": dw_delta,
                    }

    # Distinct overrides
    distinct_feed_ovr = sorted(set(
        v for v in feed_overrides if v is not None))
    distinct_spindle_ovr = sorted(set(
        v for v in spindle_overrides if v is not None))

    # Discrepancies: programmed vs actual
    discrepancies = []
    avg_rpm = _safe_avg(spindle_speeds)
    avg_feed = _safe_avg(feed_rates)

    # Per-operation discrepancies if capture_op_id available
    ops_by_id = defaultdict(list)
    for s in samples:
        op_id = s.get("capture_op_id")
        if op_id:
            ops_by_id[op_id].append(s)

    for op_name, prog_vals in programmed_ops.items():
        prog_rpm = prog_vals.get("spindle_rpm")
        prog_feed = prog_vals.get("feed_ipm")

        # Try per-op data, fall back to session averages
        op_rpm = avg_rpm
        op_feed = avg_feed
        for op_id, op_samples in ops_by_id.items():
            if op_name.lower().replace(" ", "_") in op_id.lower():
                op_rpm = _safe_avg(
                    [s.get("spindle_speed", 0) for s in op_samples])
                op_feed = _safe_avg(
                    [s.get("feed_rate", 0) for s in op_samples])
                break

        if prog_rpm and prog_rpm > 0 and op_rpm > 0:
            pct = abs(op_rpm - prog_rpm) / prog_rpm * 100
            if pct > 10:
                discrepancies.append({
                    "type": "Spindle RPM",
                    "operation": op_name,
                    "programmed": prog_rpm,
                    "actual": op_rpm,
                    "pct_diff": round(pct, 1),
                })

        if prog_feed and prog_feed > 0 and op_feed > 0:
            pct = abs(op_feed - prog_feed) / prog_feed * 100
            if pct > 10:
                discrepancies.append({
                    "type": "Feed Rate",
                    "operation": op_name,
                    "programmed": round(prog_feed, 1),
                    "actual": op_feed,
                    "pct_diff": round(pct, 1),
                })

    return {
        "session_id": match["session_id"],
        "document": diff_data.get("document", ""),
        "origin": diff_data.get("origin", ""),
        "session_date": match["session_id"][:10],
        "machine_id": machine_data.get("machine_id", ""),
        "machine_name": machine_data.get("machine_name", ""),
        "fidelity_score": diff.get("fidelity_score"),
        "changes": changes,
        "ops_added": ops_added,
        "ops_removed": ops_removed,
        "sample_count": len(samples),
        "cycle_duration_min": cycle_duration_min,
        "avg_spindle_speed": _safe_avg(spindle_speeds),
        "max_spindle_speed": _safe_max(spindle_speeds),
        "avg_feed_rate": _safe_avg(feed_rates),
        "max_feed_rate": _safe_max(feed_rates),
        "avg_spindle_load": _safe_avg(spindle_loads),
        "max_spindle_load": _safe_max(spindle_loads),
        "distinct_feed_override": distinct_feed_ovr,
        "distinct_spindle_override": distinct_spindle_ovr,
        "override_used": any(
            v != 100 for v in distinct_feed_ovr + distinct_spindle_ovr),
        "tool_wear_deltas": tool_wear_deltas,
        "alarms": machine_data.get("alarms", []),
        "discrepancies": discrepancies,
    }


# ---------------------------------------------------------------------------
# Demo / sample data
# ---------------------------------------------------------------------------

def generate_sample_data():
    """Generate realistic demo data for preview."""
    diff_sessions = {}
    machine_sessions = {}

    # Session 1: High fidelity, clean run
    sid1 = "2026-03-01_a1b2c3"
    diff_sessions[sid1] = {
        "session_id": sid1,
        "document": "3847-C v2",
        "origin": "prior_program",
        "started_at": "2026-03-01T08:30:00",
        "ended_at": "2026-03-01T09:15:00",
        "diff": {
            "diff_type": "version_delta",
            "fidelity_score": 92.0,
            "delta": {
                "operations_added": [],
                "operations_removed": [],
                "operations_modified": [
                    {
                        "operation": "2D Contour [1]",
                        "tool_id": "1/2-2FL-EM",
                        "changes": [
                            {"field": "stepdown", "from": 0.125,
                             "to": 0.1, "category": "passes"},
                        ],
                    },
                ],
                "operations_reordered": False,
                "setup_names_changed": [],
            },
        },
        "snapshot_b": {
            "setups": [{
                "name": "Setup 1", "index": 0, "operations": [
                    {"name": "Adaptive Clearing [1]", "type": "adaptive2d",
                     "feeds": {"spindle_rpm": 8500,
                               "cutting_feedrate_ipm": 85.0}},
                    {"name": "2D Contour [1]", "type": "contour2d",
                     "feeds": {"spindle_rpm": 6000,
                               "cutting_feedrate_ipm": 30.0}},
                ],
            }],
        },
    }
    t_base = datetime(2026, 3, 1, 10, 0, 0)
    machine_sessions[sid1] = {
        "samples": [
            {"capture_session_id": sid1, "capture_op_id": "adaptive2d_000",
             "capture_tool_id": "1/2-2FL-EM",
             "machine_id": "M8", "machine_name": "FANUC Mill 8",
             "timestamp": (t_base + timedelta(seconds=i * 60)).isoformat(),
             "spindle_speed": 8500, "feed_rate": 84,
             "spindle_load": 38, "feedrate_override": 100,
             "spindle_override": 100, "run_status": "STRT",
             "motion": "MOTION", "tool_number": 5, "program_number": 1234}
            for i in range(15)
        ],
        "tool_wear": [],
        "alarms": [],
        "machine_id": "M8",
        "machine_name": "FANUC Mill 8",
    }

    # Session 2: Low fidelity, operator overrides, alarm
    sid2 = "2026-03-02_d4e5f6"
    diff_sessions[sid2] = {
        "session_id": sid2,
        "document": "SA001211 v1",
        "origin": "toolpath",
        "started_at": "2026-03-02T13:00:00",
        "ended_at": "2026-03-02T14:30:00",
        "diff": {
            "diff_type": "toolpath_delta",
            "fidelity_score": 65.0,
            "delta": {
                "operations_added": [
                    {"operation": "2D Contour [2]",
                     "tool_id": "1/4-4FL-EM", "type": "contour2d"},
                ],
                "operations_removed": [
                    {"operation": "Pocket [1]",
                     "tool_id": "3/8-3FL-EM", "type": "pocket2d"},
                ],
                "operations_modified": [
                    {
                        "operation": "Adaptive Clearing [1]",
                        "tool_id": "1/2-3FL-EM",
                        "changes": [
                            {"field": "spindle_rpm", "from": 8000,
                             "to": 10000, "category": "feeds"},
                            {"field": "cutting_feedrate",
                             "from": 80.0, "to": 95.0, "category": "feeds"},
                            {"field": "stepover", "from": 0.15,
                             "to": 0.1, "category": "passes"},
                        ],
                    },
                    {
                        "operation": "Finishing Pass [1]",
                        "tool_id": "1/4-4FL-EM",
                        "changes": [
                            {"field": "stock_to_leave", "from": 0.005,
                             "to": 0.002, "category": "passes"},
                        ],
                    },
                ],
                "operations_reordered": False,
                "setup_names_changed": [],
            },
        },
        "snapshot_b": {
            "setups": [{
                "name": "Setup 1", "index": 0, "operations": [
                    {"name": "Adaptive Clearing [1]",
                     "type": "adaptive2d",
                     "feeds": {"spindle_rpm": 10000,
                               "cutting_feedrate_ipm": 95.0}},
                    {"name": "Finishing Pass [1]",
                     "type": "contour2d",
                     "feeds": {"spindle_rpm": 12000,
                               "cutting_feedrate_ipm": 45.0}},
                    {"name": "2D Contour [2]",
                     "type": "contour2d",
                     "feeds": {"spindle_rpm": 8000,
                               "cutting_feedrate_ipm": 30.0}},
                ],
            }],
        },
    }
    t_base2 = datetime(2026, 3, 2, 15, 0, 0)
    machine_sessions[sid2] = {
        "samples": [
            {"capture_session_id": sid2, "capture_op_id": "adaptive2d_000",
             "capture_tool_id": "1/2-3FL-EM",
             "machine_id": "M6", "machine_name": "FANUC Mill 6",
             "timestamp": (t_base2 + timedelta(seconds=i * 60)).isoformat(),
             "spindle_speed": 8200, "feed_rate": 85,
             "spindle_load": 55, "feedrate_override": 100,
             "spindle_override": 82, "run_status": "STRT",
             "motion": "MOTION", "tool_number": 3, "program_number": 5678}
            for i in range(25)
        ],
        "tool_wear": [
            {"capture_session_id": sid2, "tool_number": 3,
             "length_wear": -12, "diameter_wear": -3,
             "timestamp": t_base2.isoformat()},
            {"capture_session_id": sid2, "tool_number": 3,
             "length_wear": -18, "diameter_wear": -5,
             "timestamp": (t_base2 + timedelta(minutes=20)).isoformat()},
        ],
        "alarms": [
            {"capture_session_id": sid2, "alarm_number": 510,
             "alarm_message": "SPINDLE ALARM - OVERLOAD",
             "timestamp": (t_base2 + timedelta(minutes=12)).isoformat(),
             "program_number": 5678},
        ],
        "machine_id": "M6",
        "machine_name": "FANUC Mill 6",
    }

    # Session 3: Medium fidelity, feed override
    sid3 = "2026-03-03_789abc"
    diff_sessions[sid3] = {
        "session_id": sid3,
        "document": "10150 v3",
        "origin": "prior_program",
        "started_at": "2026-03-03T07:00:00",
        "ended_at": "2026-03-03T07:45:00",
        "diff": {
            "diff_type": "version_delta",
            "fidelity_score": 78.0,
            "delta": {
                "operations_added": [],
                "operations_removed": [],
                "operations_modified": [
                    {
                        "operation": "3D Contour [1]",
                        "tool_id": "1/4-BN-EM",
                        "changes": [
                            {"field": "stepover", "from": 0.01,
                             "to": 0.008, "category": "passes"},
                            {"field": "tolerance", "from": 0.001,
                             "to": 0.0005, "category": "passes"},
                        ],
                    },
                ],
                "operations_reordered": False,
                "setup_names_changed": [],
            },
        },
        "snapshot_b": {
            "setups": [{
                "name": "Setup 1", "index": 0, "operations": [
                    {"name": "Face [1]", "type": "face",
                     "feeds": {"spindle_rpm": 4000,
                               "cutting_feedrate_ipm": 60.0}},
                    {"name": "3D Contour [1]", "type": "contour3d",
                     "feeds": {"spindle_rpm": 15000,
                               "cutting_feedrate_ipm": 120.0}},
                ],
            }],
        },
    }
    t_base3 = datetime(2026, 3, 3, 8, 0, 0)
    machine_sessions[sid3] = {
        "samples": [
            {"capture_session_id": sid3, "capture_op_id": "contour3d_001",
             "capture_tool_id": "1/4-BN-EM",
             "machine_id": "M2", "machine_name": "FANUC Mill 2",
             "timestamp": (t_base3 + timedelta(seconds=i * 60)).isoformat(),
             "spindle_speed": 15000, "feed_rate": 108,
             "spindle_load": 22, "feedrate_override": 90,
             "spindle_override": 100, "run_status": "STRT",
             "motion": "MOTION", "tool_number": 12, "program_number": 9012}
            for i in range(30)
        ],
        "tool_wear": [
            {"capture_session_id": sid3, "tool_number": 12,
             "length_wear": -5, "diameter_wear": -1,
             "timestamp": t_base3.isoformat()},
            {"capture_session_id": sid3, "tool_number": 12,
             "length_wear": -9, "diameter_wear": -2,
             "timestamp": (t_base3 + timedelta(minutes=25)).isoformat()},
        ],
        "alarms": [],
        "machine_id": "M2",
        "machine_name": "FANUC Mill 2",
    }

    return diff_sessions, machine_sessions


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def _fidelity_color(score):
    if score is None:
        return "#64748b"
    if score >= 90:
        return "#22c55e"
    elif score >= 70:
        return "#eab308"
    elif score >= 50:
        return "#f97316"
    return "#ef4444"


def _deviation_color(pct):
    if pct < 5:
        return "#22c55e"
    elif pct < 15:
        return "#eab308"
    return "#ef4444"


def _override_color(val):
    if val == 100:
        return "#e2e8f0"
    elif 90 <= val <= 110:
        return "#eab308"
    return "#ef4444"


def _esc(val):
    """Escape value for HTML display."""
    if val is None:
        return "&mdash;"
    s = str(val)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_html(analysis_list, summary, output_path):
    """Generate self-contained HTML report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    is_demo = summary.get("is_demo", False)

    # Summary stats
    matched = summary.get("matched_count", 0)
    avg_fid = summary.get("avg_fidelity", 0)
    total_disc = summary.get("total_discrepancies", 0)
    total_alarms = summary.get("total_alarms", 0)
    fid_color = _fidelity_color(avg_fid)

    # Build session cards
    session_cards = ""
    for a in analysis_list:
        fid = a["fidelity_score"]
        fc = _fidelity_color(fid)
        fid_display = f"{fid}%" if fid is not None else "N/A"

        # Changes table rows
        change_rows = ""
        if a["changes"]:
            for c in a["changes"]:
                change_rows += f"""
                <tr>
                    <td>{_esc(c['operation'])}</td>
                    <td><code>{_esc(c['field'])}</code></td>
                    <td>{_esc(c['from_val'])}</td>
                    <td>{_esc(c['to_val'])}</td>
                    <td>{_esc(c['category'])}</td>
                </tr>"""
        else:
            change_rows = """
                <tr><td colspan="5" style="color:#64748b;text-align:center">
                No parameter changes detected</td></tr>"""

        # Ops added/removed
        struct_rows = ""
        for op in a.get("ops_added", []):
            struct_rows += f"""
                <tr>
                    <td style="color:#22c55e">+ Added</td>
                    <td>{_esc(op.get('operation', ''))}</td>
                    <td>{_esc(op.get('type', ''))}</td>
                    <td>{_esc(op.get('tool_id', ''))}</td>
                </tr>"""
        for op in a.get("ops_removed", []):
            struct_rows += f"""
                <tr>
                    <td style="color:#ef4444">- Removed</td>
                    <td>{_esc(op.get('operation', ''))}</td>
                    <td>{_esc(op.get('type', ''))}</td>
                    <td>{_esc(op.get('tool_id', ''))}</td>
                </tr>"""

        struct_section = ""
        if struct_rows:
            struct_section = f"""
            <h3>Operation Changes</h3>
            <table>
                <tr><th>Action</th><th>Operation</th>
                    <th>Type</th><th>Tool</th></tr>
                {struct_rows}
            </table>"""

        # Overrides
        feed_ovr = ", ".join(
            f"<span style='color:{_override_color(v)}'>{v}%</span>"
            for v in a["distinct_feed_override"]) or "N/A"
        spindle_ovr = ", ".join(
            f"<span style='color:{_override_color(v)}'>{v}%</span>"
            for v in a["distinct_spindle_override"]) or "N/A"

        override_flag = ""
        if a.get("override_used"):
            override_flag = (" <span style='color:#ef4444;font-weight:bold'>"
                             "OPERATOR OVERRIDE</span>")

        # Tool wear
        wear_rows = ""
        for tn, wd in a.get("tool_wear_deltas", {}).items():
            lw = wd["length_wear_delta"]
            dw = wd["diameter_wear_delta"]
            wear_rows += f"""
                <tr>
                    <td>T{tn}</td>
                    <td>{lw / 1000:.4f} mm</td>
                    <td>{dw / 1000:.4f} mm</td>
                </tr>"""

        wear_section = ""
        if wear_rows:
            wear_section = f"""
            <h3>Tool Wear During Session</h3>
            <table>
                <tr><th>Tool</th><th>Length Wear</th>
                    <th>Diameter Wear</th></tr>
                {wear_rows}
            </table>"""

        # Alarms
        alarm_rows = ""
        for al in a.get("alarms", []):
            alarm_rows += f"""
                <tr>
                    <td>{_esc(al.get('timestamp', '')[:19])}</td>
                    <td>{_esc(al.get('alarm_number', ''))}</td>
                    <td style="color:#ef4444">{_esc(al.get('alarm_message', ''))}</td>
                </tr>"""

        alarm_section = ""
        if alarm_rows:
            alarm_section = f"""
            <h3 style="color:#ef4444">Alarms</h3>
            <table>
                <tr><th>Time</th><th>Alarm #</th><th>Message</th></tr>
                {alarm_rows}
            </table>"""

        # Discrepancies
        disc_rows = ""
        for d in a.get("discrepancies", []):
            dc = _deviation_color(d["pct_diff"])
            disc_rows += f"""
                <tr>
                    <td>{_esc(d['type'])}</td>
                    <td>{_esc(d['operation'])}</td>
                    <td>{_esc(d['programmed'])}</td>
                    <td>{_esc(d['actual'])}</td>
                    <td style="color:{dc};font-weight:bold">
                        {d['pct_diff']}%</td>
                </tr>"""

        disc_section = ""
        if disc_rows:
            disc_section = f"""
            <h3>Discrepancies (Programmed vs Actual)</h3>
            <table>
                <tr><th>Type</th><th>Operation</th>
                    <th>Programmed</th><th>Actual Avg</th>
                    <th>Deviation</th></tr>
                {disc_rows}
            </table>"""

        session_cards += f"""
        <div class="card session-card">
            <div class="session-header">
                <div>
                    <h2 style="margin:0">{_esc(a['document'])}</h2>
                    <span class="meta">
                        {a['session_date']} &middot;
                        {_esc(a['machine_name'])} ({a['machine_id']}) &middot;
                        Origin: {a['origin']}
                    </span>
                </div>
                <div class="fidelity-badge" style="border-color:{fc}">
                    <div style="color:{fc};font-size:28px;font-weight:bold">
                        {fid_display}</div>
                    <div style="color:#94a3b8;font-size:11px">Fidelity</div>
                </div>
            </div>

            {struct_section}

            <h3>Parameter Changes</h3>
            <table>
                <tr><th>Operation</th><th>Field</th>
                    <th>From</th><th>To</th><th>Category</th></tr>
                {change_rows}
            </table>

            <h3>Machine Execution</h3>
            <div class="exec-grid">
                <div class="exec-item">
                    <div class="exec-value">{a['avg_spindle_speed']}</div>
                    <div class="exec-label">Avg RPM</div>
                </div>
                <div class="exec-item">
                    <div class="exec-value">{a['max_spindle_speed']}</div>
                    <div class="exec-label">Max RPM</div>
                </div>
                <div class="exec-item">
                    <div class="exec-value">{a['avg_feed_rate']}</div>
                    <div class="exec-label">Avg Feed</div>
                </div>
                <div class="exec-item">
                    <div class="exec-value">{a['avg_spindle_load']}%</div>
                    <div class="exec-label">Avg Spindle Load</div>
                </div>
                <div class="exec-item">
                    <div class="exec-value">{a['max_spindle_load']}%</div>
                    <div class="exec-label">Max Spindle Load</div>
                </div>
                <div class="exec-item">
                    <div class="exec-value">{a['cycle_duration_min']} min</div>
                    <div class="exec-label">Duration</div>
                </div>
                <div class="exec-item">
                    <div class="exec-value">{a['sample_count']}</div>
                    <div class="exec-label">Samples</div>
                </div>
            </div>

            <h3>Operator Overrides{override_flag}</h3>
            <div class="override-row">
                <span>Feed Override: {feed_ovr}</span>
                <span style="margin-left:32px">
                    Spindle Override: {spindle_ovr}</span>
            </div>

            {wear_section}
            {alarm_section}
            {disc_section}
        </div>"""

    # Unmatched sections
    unmatched_html = ""
    unmatched_jsonl = summary.get("unmatched_jsonl", [])
    unmatched_machine = summary.get("unmatched_machine", [])
    if unmatched_jsonl or unmatched_machine:
        jsonl_items = ""
        for sid, doc in unmatched_jsonl[:20]:
            jsonl_items += f"<li>{_esc(sid)} &mdash; {_esc(doc)}</li>"
        machine_items = ""
        for sid, mname in unmatched_machine[:20]:
            machine_items += f"<li>{_esc(sid)} &mdash; {_esc(mname)}</li>"

        unmatched_html = f"""
        <h2>Unmatched Sessions</h2>
        <div class="card">
            <div style="display:flex;gap:32px;flex-wrap:wrap">
                <div style="flex:1;min-width:300px">
                    <h3 style="color:#94a3b8">
                        Programmed Only ({len(unmatched_jsonl)})</h3>
                    <p class="meta">Have diff data but haven't run on a
                        machine yet</p>
                    <ul style="color:#64748b;padding-left:20px">
                        {jsonl_items or '<li>None</li>'}
                    </ul>
                </div>
                <div style="flex:1;min-width:300px">
                    <h3 style="color:#94a3b8">
                        Machine Only ({len(unmatched_machine)})</h3>
                    <p class="meta">Ran on machine but no matching diff
                        record found</p>
                    <ul style="color:#64748b;padding-left:20px">
                        {machine_items or '<li>None</li>'}
                    </ul>
                </div>
            </div>
        </div>"""

    demo_banner = ""
    if is_demo:
        demo_banner = """
        <div style="background:#92400e;color:#fef3c7;padding:12px 20px;
                    border-radius:8px;margin-bottom:20px;text-align:center;
                    font-weight:600">
            DEMO DATA &mdash; This report shows sample data to preview the
            layout. Real data will appear after TraxisCapture sessions run
            on CNC machines.
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Session Bridge Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                         sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 20px;
           max-width: 1200px; margin: 0 auto; }}
    h1 {{ color: #f8fafc; margin-bottom: 4px; font-size: 24px; }}
    h2 {{ color: #cbd5e1; margin: 20px 0 8px; font-size: 18px; }}
    h3 {{ color: #94a3b8; margin: 16px 0 8px; font-size: 14px;
          text-transform: uppercase; letter-spacing: 0.5px; }}
    .meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 20px;
             margin-bottom: 16px; }}
    .stat-row {{ display: flex; gap: 16px; flex-wrap: wrap;
                 margin-bottom: 20px; }}
    .stat-box {{ background: #1e293b; border-radius: 8px; padding: 16px;
                 flex: 1; min-width: 140px; text-align: center; }}
    .stat-value {{ font-size: 32px; font-weight: bold; }}
    .stat-label {{ color: #94a3b8; font-size: 13px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px;
             margin-bottom: 12px; }}
    th {{ text-align: left; padding: 6px 10px; background: #334155;
          color: #94a3b8; font-weight: 600; font-size: 12px; }}
    td {{ padding: 6px 10px; border-bottom: 1px solid #334155; }}
    code {{ background: #334155; padding: 2px 6px; border-radius: 3px;
            font-size: 12px; }}
    .session-card {{ border-left: 3px solid #334155; }}
    .session-header {{ display: flex; justify-content: space-between;
                       align-items: flex-start; margin-bottom: 12px; }}
    .fidelity-badge {{ text-align: center; padding: 8px 16px;
                       border: 2px solid; border-radius: 8px;
                       min-width: 80px; }}
    .exec-grid {{ display: grid;
                   grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                   gap: 12px; margin-bottom: 12px; }}
    .exec-item {{ background: #334155; border-radius: 6px;
                   padding: 10px; text-align: center; }}
    .exec-value {{ font-size: 20px; font-weight: bold; color: #f8fafc; }}
    .exec-label {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}
    .override-row {{ padding: 8px 0; font-size: 14px; }}
</style>
</head>
<body>
<h1>Session Bridge &mdash; CAM vs Machine Execution</h1>
<p class="meta">Generated {now} &mdash; Traxis Manufacturing</p>

{demo_banner}

<div class="stat-row">
    <div class="stat-box">
        <div class="stat-value">{matched}</div>
        <div class="stat-label">Matched Sessions</div>
    </div>
    <div class="stat-box">
        <div class="stat-value" style="color:{fid_color}">{avg_fid}%</div>
        <div class="stat-label">Avg Fidelity</div>
    </div>
    <div class="stat-box">
        <div class="stat-value" style="color:{'#ef4444' if total_disc > 0 else '#22c55e'}">{total_disc}</div>
        <div class="stat-label">Discrepancies</div>
    </div>
    <div class="stat-box">
        <div class="stat-value" style="color:{'#ef4444' if total_alarms > 0 else '#22c55e'}">{total_alarms}</div>
        <div class="stat-label">Alarms</div>
    </div>
</div>

{session_cards}

{unmatched_html}

<p class="meta" style="margin-top:32px;text-align:center">
    Session Bridge Report &mdash; Traxis Manufacturing
</p>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Session Bridge Report - CAM vs Machine Execution")
    parser.add_argument("--db", help="Path to monitoring.db")
    parser.add_argument("--diffs-dir", help="Path to diffs directory")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output HTML path")
    parser.add_argument("--demo", action="store_true",
                        help="Force demo/sample data mode")
    args = parser.parse_args()

    demo_mode = args.demo

    # Locate data sources
    diffs_dir = args.diffs_dir or find_diffs_dir()
    db_path = args.db or find_database()

    print(f"Diffs dir:  {diffs_dir or 'not found'}")
    print(f"Database:   {db_path or 'not found'}")

    # Read data
    diff_sessions = {}
    machine_sessions = {}

    if not demo_mode:
        if diffs_dir:
            diff_sessions = read_all_diffs(diffs_dir)
            print(f"JSONL sessions: {len(diff_sessions)}")
        if db_path:
            machine_sessions = query_capture_sessions(db_path)
            print(f"Machine sessions with capture data: {len(machine_sessions)}")

    # Fall back to demo if no data
    if not demo_mode and not diff_sessions and not machine_sessions:
        print("No data from either source -- generating demo report...")
        demo_mode = True

    if demo_mode:
        diff_sessions, machine_sessions = generate_sample_data()
        print(f"Demo mode: {len(diff_sessions)} JSONL, "
              f"{len(machine_sessions)} machine sessions")

    # Match and analyze
    matched = match_sessions(diff_sessions, machine_sessions)
    print(f"Matched sessions: {len(matched)}")

    analysis_list = [analyze_matched_session(m) for m in matched]

    # Summary
    fidelity_scores = [a["fidelity_score"] for a in analysis_list
                       if a["fidelity_score"] is not None]
    avg_fidelity = (round(sum(fidelity_scores) / len(fidelity_scores), 1)
                    if fidelity_scores else 0)

    unmatched_jsonl = set(diff_sessions.keys()) - set(machine_sessions.keys())
    unmatched_machine = set(machine_sessions.keys()) - set(diff_sessions.keys())

    summary = {
        "matched_count": len(matched),
        "avg_fidelity": avg_fidelity,
        "total_discrepancies": sum(
            len(a["discrepancies"]) for a in analysis_list),
        "total_alarms": sum(len(a["alarms"]) for a in analysis_list),
        "unmatched_jsonl": [
            (sid, diff_sessions[sid].get("document", ""))
            for sid in sorted(unmatched_jsonl)],
        "unmatched_machine": [
            (sid, machine_sessions[sid].get("machine_name", ""))
            for sid in sorted(unmatched_machine)],
        "is_demo": demo_mode,
    }

    generate_html(analysis_list, summary, args.output)
    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()
