#!/usr/bin/env python3
"""
FASData Utilization Report Generator
Traxis Manufacturing

Queries the monitoring.db SQLite database and generates:
  1. PNG chart images (bar chart + daily trend)
  2. A JSON data file consumed by the docx builder

Usage:
  python generate_report.py                          # uses sample data
  python generate_report.py path/to/monitoring.db    # uses real database
  python generate_report.py monitoring.db 2026-01-27 2026-01-31  # custom date range
"""

import sqlite3
import json
import os
import sys
import random
from datetime import datetime, timedelta
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ── Configuration ────────────────────────────────────────────────────────────

SHIFT_START_HOUR = 6   # 6 AM
SHIFT_END_HOUR = 19    # 7 PM (19:00)
SHIFT_DAYS = [0, 1, 2, 3, 4]  # Mon-Fri

MACHINES = {
    "T2": "YCM NTC1600LY",
    "M2": "FANUC Mill 2",
    "M3": "FANUC Mill 3",
    "M6": "FANUC Mill 6",
    "M8": "FANUC Mill 8",
}

GREEN_THRESHOLD = 30
YELLOW_THRESHOLD = 10

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "report_assets")

# Default database locations to check (in order)
DEFAULT_DB_PATHS = [
    r"D:\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db",
    r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db",
    os.path.join(SCRIPT_DIR, "monitoring.db"),
]

# ── Sample Data Generator ────────────────────────────────────────────────────

def generate_sample_data():
    """Generate realistic sample data for demonstration."""
    print("No database found — generating sample data for report preview...")
    
    # Simulate one work week: Mon Jan 27 - Fri Jan 31, 2026
    start_date = datetime(2026, 1, 27, 6, 0, 0)
    end_date = datetime(2026, 1, 31, 19, 0, 0)
    
    # Each machine has a characteristic utilization profile
    machine_profiles = {
        "T2": {"base_util": 0.72, "variability": 0.15, "label": "YCM NTC1600LY"},
        "M2": {"base_util": 0.65, "variability": 0.12, "label": "FANUC Mill 2"},
        "M3": {"base_util": 0.0,  "variability": 0.0,  "label": "FANUC Mill 3"},  # offline
        "M6": {"base_util": 0.58, "variability": 0.18, "label": "FANUC Mill 6"},
        "M8": {"base_util": 0.61, "variability": 0.14, "label": "FANUC Mill 8"},
    }
    
    rows = []
    current = start_date
    while current <= end_date:
        weekday = current.weekday()
        hour = current.hour
        
        # Only generate during shift hours on weekdays
        if weekday in SHIFT_DAYS and SHIFT_START_HOUR <= hour < SHIFT_END_HOUR:
            for mid, profile in machine_profiles.items():
                base = profile["base_util"]
                var = profile["variability"]
                
                if base == 0:
                    # M3 is offline — show as disconnected
                    rows.append({
                        "timestamp": current.isoformat(),
                        "machine_id": mid,
                        "machine_name": profile["label"],
                        "connected": 0,
                        "run_status": None,
                        "mode": None,
                        "spindle_speed": 0,
                        "emergency": 0,
                        "alarm": 0,
                    })
                else:
                    # Utilization varies by time of day and day of week
                    time_factor = 1.0
                    if hour < 8 or hour > 16:
                        time_factor = 0.7  # lower at edges of shift
                    if weekday in [0, 4]:
                        time_factor *= 0.85  # lighter Mon/Fri staffing
                    
                    prob = min(1.0, max(0.0, base * time_factor + random.gauss(0, var * 0.3)))
                    is_running = random.random() < prob
                    
                    rows.append({
                        "timestamp": current.isoformat(),
                        "machine_id": mid,
                        "machine_name": profile["label"],
                        "connected": 1,
                        "run_status": "STRT" if is_running else "STOP",
                        "mode": "MEM" if is_running else random.choice(["MEM", "MDI", "JOG", "EDIT"]),
                        "spindle_speed": random.randint(800, 12000) if is_running else 0,
                        "motion": random.choices(["MOTION", "DWL", None], weights=[0.75, 0.10, 0.15])[0] if is_running else None,
                        "feed_rate": random.randint(50, 5000) if (is_running and random.random() < 0.80) else 0,
                        "emergency": 0,
                        "alarm": 0,
                    })
        
        current += timedelta(minutes=1)
    
    return rows


# ── Database Query ───────────────────────────────────────────────────────────

def query_database(db_path, start_date=None, end_date=None):
    """Query monitoring.db for machine samples within date range."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    query = "SELECT * FROM machine_samples WHERE 1=1"
    params = []
    
    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date + "T23:59:59")
    
    query += " ORDER BY timestamp ASC"
    
    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    print(f"Queried {len(rows)} samples from database")
    return rows


# ── Analysis ─────────────────────────────────────────────────────────────────

def analyze_data(rows):
    """Calculate utilization metrics from raw samples."""
    
    # Filter to shift hours only
    shift_rows = []
    for r in rows:
        ts = r["timestamp"]
        try:
            dt = datetime.fromisoformat(ts)
        except:
            continue
        if dt.weekday() in SHIFT_DAYS and SHIFT_START_HOUR <= dt.hour < SHIFT_END_HOUR:
            shift_rows.append({**r, "_dt": dt})
    
    if not shift_rows:
        print("WARNING: No data within shift hours found.")
        return None
    
    # Date range
    all_dates = sorted(set(r["_dt"].date() for r in shift_rows))
    date_start = all_dates[0]
    date_end = all_dates[-1]
    num_days = len(all_dates)
    
    # Per-machine totals
    machine_stats = {}
    for mid in MACHINES:
        machine_rows = [r for r in shift_rows if r["machine_id"] == mid]
        total = len(machine_rows)
        
        if total == 0:
            machine_stats[mid] = {
                "name": MACHINES[mid],
                "total_samples": 0,
                "running_samples": 0,
                "utilization_pct": 0.0,
                "connected_pct": 0.0,
                "alarm_samples": 0,
                "status": "NO DATA",
            }
            continue
        
        connected = [r for r in machine_rows if r.get("connected")]
        running = [r for r in machine_rows if (
            r.get("connected") and (
                r.get("run_status") in ("STRT", "MSTR") or
                (r.get("spindle_speed") and r["spindle_speed"] > 0)
            )
        )]
        # Cutting = spindle on AND (motion active OR feed rate > 0)
        cutting = [r for r in running if (
            (r.get("motion") and r["motion"] in ("MOTION", "DWL")) or
            (r.get("feed_rate") and r["feed_rate"] > 0)
        )]
        # Spindle only = running but NOT cutting (warmup, air spin, tool change dwell)
        spindle_only = [r for r in running if r not in cutting]
        alarms = [r for r in machine_rows if r.get("alarm") and r["alarm"] > 0]
        
        util_pct = (len(running) / total) * 100 if total > 0 else 0
        cutting_pct = (len(cutting) / total) * 100 if total > 0 else 0
        spindle_only_pct = (len(spindle_only) / total) * 100 if total > 0 else 0
        conn_pct = (len(connected) / total) * 100 if total > 0 else 0
        
        # Status is based on CUTTING percentage only (spindle-only doesn't count)
        if conn_pct < 10:
            status = "OFFLINE"
        elif cutting_pct >= GREEN_THRESHOLD:
            status = "GREEN"
        elif cutting_pct >= YELLOW_THRESHOLD:
            status = "YELLOW"
        else:
            status = "RED"
        
        hours_available = total / 60.0
        hours_running = len(running) / 60.0
        hours_cutting = len(cutting) / 60.0
        hours_spindle_only = len(spindle_only) / 60.0
        
        machine_stats[mid] = {
            "name": MACHINES[mid],
            "total_samples": total,
            "running_samples": len(running),
            "cutting_samples": len(cutting),
            "spindle_only_samples": len(spindle_only),
            "connected_samples": len(connected),
            "utilization_pct": round(util_pct, 1),
            "cutting_pct": round(cutting_pct, 1),
            "spindle_only_pct": round(spindle_only_pct, 1),
            "connected_pct": round(conn_pct, 1),
            "hours_available": round(hours_available, 1),
            "hours_running": round(hours_running, 1),
            "hours_cutting": round(hours_cutting, 1),
            "hours_spindle_only": round(hours_spindle_only, 1),
            "alarm_samples": len(alarms),
            "status": status,
        }
    
    # Daily breakdown per machine
    daily = defaultdict(lambda: defaultdict(lambda: {"total": 0, "running": 0, "cutting": 0}))
    for r in shift_rows:
        day = r["_dt"].date().isoformat()
        mid = r["machine_id"]
        daily[day][mid]["total"] += 1
        is_running = r.get("connected") and (
            r.get("run_status") in ("STRT", "MSTR") or
            (r.get("spindle_speed") and r["spindle_speed"] > 0)
        )
        if is_running:
            daily[day][mid]["running"] += 1
            is_cutting = (
                (r.get("motion") and r["motion"] in ("MOTION", "DWL")) or
                (r.get("feed_rate") and r["feed_rate"] > 0)
            )
            if is_cutting:
                daily[day][mid]["cutting"] += 1
    
    daily_util = {}
    for day in sorted(daily.keys()):
        daily_util[day] = {}
        for mid in MACHINES:
            d = daily[day].get(mid, {"total": 0, "running": 0, "cutting": 0})
            pct = (d["running"] / d["total"] * 100) if d["total"] > 0 else 0
            cut_pct = (d["cutting"] / d["total"] * 100) if d["total"] > 0 else 0
            daily_util[day][mid] = {"running": round(pct, 1), "cutting": round(cut_pct, 1)}
    
    # Shop-wide average (based on cutting %, exclude offline machines)
    active_machines = [m for m, s in machine_stats.items() if s["status"] not in ("OFFLINE", "NO DATA")]
    shop_avg = (
        sum(machine_stats[m]["cutting_pct"] for m in active_machines) / len(active_machines)
        if active_machines else 0
    )
    
    total_available = sum(machine_stats[m]["hours_available"] for m in active_machines)
    total_running = sum(machine_stats[m]["hours_running"] for m in active_machines)
    total_cutting = sum(machine_stats[m]["hours_cutting"] for m in active_machines)
    
    shop_avg_cutting = (
        sum(machine_stats[m]["cutting_pct"] for m in active_machines) / len(active_machines)
        if active_machines else 0
    )
    
    return {
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "num_days": num_days,
        "report_generated": datetime.now().isoformat(),
        "shift_hours": f"{SHIFT_START_HOUR}:00 - {SHIFT_END_HOUR}:00",
        "green_threshold": GREEN_THRESHOLD,
        "yellow_threshold": YELLOW_THRESHOLD,
        "shop_avg_utilization": round(shop_avg, 1),
        "shop_avg_cutting": round(shop_avg_cutting, 1),
        "total_hours_available": round(total_available, 1),
        "total_hours_running": round(total_running, 1),
        "total_hours_cutting": round(total_cutting, 1),
        "active_machine_count": len(active_machines),
        "total_machine_count": len(MACHINES),
        "machines": machine_stats,
        "daily": daily_util,
    }


# ── Chart Generation ─────────────────────────────────────────────────────────

def generate_charts(analysis):
    """Create PNG chart images for the report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Color palette
    COLOR_GREEN = "#2E7D32"
    COLOR_YELLOW = "#F9A825"
    COLOR_RED = "#C62828"
    COLOR_GRAY = "#9E9E9E"
    COLOR_BG = "#FAFAFA"
    
    def status_color(pct, connected=True):
        if not connected:
            return COLOR_GRAY
        if pct >= GREEN_THRESHOLD:
            return COLOR_GREEN
        elif pct >= YELLOW_THRESHOLD:
            return COLOR_YELLOW
        return COLOR_RED
    
    machines = analysis["machines"]
    
    # ── Chart 1: Utilization Bar Chart (stacked: cutting + spindle only) ──
    
    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    
    ids = sorted(machines.keys())
    labels = [f"{mid}\n{machines[mid]['name']}" for mid in ids]
    cutting_vals = [machines[mid].get("cutting_pct", 0) for mid in ids]
    spindle_vals = [machines[mid].get("spindle_only_pct", 0) for mid in ids]
    total_vals = [machines[mid]["utilization_pct"] for mid in ids]
    
    COLOR_CUTTING = "#1565C0"   # blue for cutting
    COLOR_SPINDLE = "#90CAF9"   # light blue for spindle only
    
    bars_cut = ax.bar(labels, cutting_vals, color=COLOR_CUTTING, width=0.6,
                      edgecolor="white", linewidth=1.5, label="Cutting")
    bars_spn = ax.bar(labels, spindle_vals, bottom=cutting_vals, color=COLOR_SPINDLE,
                      width=0.6, edgecolor="white", linewidth=1.5, label="Spindle Only")
    
    # Value labels on bars
    for i, (cut, spn, total) in enumerate(zip(cutting_vals, spindle_vals, total_vals)):
        if total > 0:
            # Cutting % is the utilization number — color by status
            cut_color = COLOR_GREEN if cut >= GREEN_THRESHOLD else (COLOR_YELLOW if cut >= YELLOW_THRESHOLD else COLOR_RED)
            ax.text(i, total + 1.5,
                    f"{cut:.1f}% util", ha="center", va="bottom", fontsize=10, fontweight="bold", color=cut_color)
            if cut > 5:
                ax.text(i, cut / 2, f"{cut:.0f}%", ha="center", va="center",
                        fontsize=9, color="white", fontweight="bold")
            if spn > 5:
                ax.text(i, cut + spn / 2, f"{spn:.0f}%", ha="center", va="center",
                        fontsize=9, color="#1565C0")
        else:
            ax.text(i, 2, "OFFLINE", ha="center", va="bottom", fontsize=9,
                    color=COLOR_GRAY, fontstyle="italic")
    
    # Threshold lines
    ax.axhline(y=GREEN_THRESHOLD, color=COLOR_GREEN, linestyle="--", alpha=0.5, linewidth=1)
    ax.axhline(y=YELLOW_THRESHOLD, color=COLOR_YELLOW, linestyle="--", alpha=0.5, linewidth=1)
    ax.text(len(ids) - 0.5, GREEN_THRESHOLD + 1, f"Target ({GREEN_THRESHOLD}%)", fontsize=8,
            color=COLOR_GREEN, alpha=0.7, ha="right")
    ax.text(len(ids) - 0.5, YELLOW_THRESHOLD + 1, f"Warning ({YELLOW_THRESHOLD}%)", fontsize=8,
            color=COLOR_YELLOW, alpha=0.7, ha="right")
    
    ax.set_ylim(0, 105)
    ax.set_ylabel("Utilization %", fontsize=11)
    ax.set_title(f"Machine Utilization — {analysis['date_start']} to {analysis['date_end']}",
                 fontsize=13, fontweight="bold", pad=15)
    ax.legend(fontsize=9, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", labelsize=9)
    
    plt.tight_layout()
    bar_path = os.path.join(OUTPUT_DIR, "utilization_bar.png")
    fig.savefig(bar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {bar_path}")
    
    # ── Chart 2: Daily Trend Lines ───────────────────────────────────────
    
    daily = analysis["daily"]
    days = sorted(daily.keys())
    
    if len(days) > 1:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        
        line_colors = {
            "T2": "#1565C0",
            "M2": "#2E7D32",
            "M3": COLOR_GRAY,
            "M6": "#E65100",
            "M8": "#6A1B9A",
        }
        
        x_dates = [datetime.fromisoformat(d) for d in days]
        
        for mid in sorted(MACHINES.keys()):
            y_run = []
            y_cut = []
            for d in days:
                dd = daily[d].get(mid, {"running": 0, "cutting": 0})
                if isinstance(dd, dict):
                    y_run.append(dd.get("running", 0))
                    y_cut.append(dd.get("cutting", 0))
                else:
                    y_run.append(dd)
                    y_cut.append(0)
            
            if max(y_run) > 0:
                color = line_colors.get(mid, "#333")
                ax.plot(x_dates, y_cut, marker="o", linewidth=2, markersize=6,
                        label=f"{mid} cutting", color=color)
                ax.plot(x_dates, y_run, marker="s", linewidth=1.5, markersize=4,
                        linestyle="--", alpha=0.5, label=f"{mid} total", color=color)
        
        ax.axhline(y=GREEN_THRESHOLD, color=COLOR_GREEN, linestyle="--", alpha=0.4, linewidth=1)
        ax.axhline(y=YELLOW_THRESHOLD, color=COLOR_YELLOW, linestyle="--", alpha=0.4, linewidth=1)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a\n%m/%d"))
        ax.set_ylim(0, 105)
        ax.set_ylabel("Utilization %", fontsize=11)
        ax.set_title("Daily Utilization Trend", fontsize=13, fontweight="bold", pad=15)
        ax.legend(fontsize=9, loc="lower right", framealpha=0.9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
        
        plt.tight_layout()
        trend_path = os.path.join(OUTPUT_DIR, "utilization_trend.png")
        fig.savefig(trend_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved {trend_path}")
    
    # ── Chart 3: Hours Breakdown (stacked bar: cutting + spindle only + idle) ──
    
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    
    COLOR_CUTTING = "#1565C0"
    COLOR_SPINDLE = "#90CAF9"
    
    active_ids = [mid for mid in sorted(MACHINES.keys()) if machines[mid]["status"] not in ("OFFLINE", "NO DATA")]
    labels_h = [f"{mid}\n{machines[mid]['name']}" for mid in active_ids]
    cutting_h = [machines[mid].get("hours_cutting", 0) for mid in active_ids]
    spindle_h = [machines[mid].get("hours_spindle_only", 0) for mid in active_ids]
    idle_h = [machines[mid]["hours_available"] - machines[mid]["hours_running"] for mid in active_ids]
    
    ax.bar(labels_h, cutting_h, color=COLOR_CUTTING, label="Cutting", width=0.5)
    ax.bar(labels_h, spindle_h, bottom=cutting_h, color=COLOR_SPINDLE, label="Spindle Only", width=0.5)
    bottoms = [c + s for c, s in zip(cutting_h, spindle_h)]
    ax.bar(labels_h, idle_h, bottom=bottoms, color="#E0E0E0", label="Idle", width=0.5)
    
    for i, mid in enumerate(active_ids):
        total_h = machines[mid]["hours_available"]
        cut = cutting_h[i]
        spn = spindle_h[i]
        ax.text(i, total_h + 0.5, f"{cut:.1f}h cut / {cut+spn:.1f}h run / {total_h:.1f}h avail",
                ha="center", fontsize=8)
    
    ax.set_ylabel("Hours", fontsize=11)
    ax.set_title("Cutting vs. Spindle Only vs. Idle Hours", fontsize=13, fontweight="bold", pad=15)
    ax.legend(fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    hours_path = os.path.join(OUTPUT_DIR, "hours_breakdown.png")
    fig.savefig(hours_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {hours_path}")


# ── HTML Report ──────────────────────────────────────────────────────────────

DROPBOX_REPORT_PATHS = [
    r"D:\Dropbox\MACHINE COMM Traxis\FASData\reports",
    r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\reports",
    r"C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports",
]

def img_to_base64(path):
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def generate_html_report(analysis):
    """Generate a tiled single-screen HTML dashboard for 1440x900 display."""
    
    machines = analysis["machines"]
    mids = sorted(machines.keys())
    
    bar_img = img_to_base64(os.path.join(OUTPUT_DIR, "utilization_bar.png"))
    hours_img = img_to_base64(os.path.join(OUTPUT_DIR, "hours_breakdown.png"))
    trend_path = os.path.join(OUTPUT_DIR, "utilization_trend.png")
    trend_img = img_to_base64(trend_path) if os.path.exists(trend_path) else None
    
    def cutting_color(pct):
        if pct >= GREEN_THRESHOLD:
            return "#2E7D32"
        elif pct >= YELLOW_THRESHOLD:
            return "#F57F17"
        return "#C62828"
    
    def status_dot(m):
        s = m["status"]
        if s == "GREEN":
            return '<span style="color:#2E7D32">●</span>'
        elif s == "YELLOW":
            return '<span style="color:#F9A825">●</span>'
        elif s == "RED":
            return '<span style="color:#C62828">●</span>'
        elif s == "OFFLINE":
            return '<span style="color:#BDBDBD">○</span>'
        return '<span style="color:#BDBDBD">—</span>'
    
    # Machine cards — one per machine
    machine_cards = ""
    for mid in mids:
        m = machines[mid]
        cut = m.get("cutting_pct", 0)
        spn = m.get("spindle_only_pct", 0)
        cut_c = cutting_color(cut)
        s = m["status"]
        
        if s == "OFFLINE":
            bg = "#f5f5f5"
            border = "#e0e0e0"
            machine_cards += f"""
            <div class="mcard" style="background:{bg};border-color:{border}">
                <div class="mcard-id">{mid}</div>
                <div class="mcard-name">{m['name']}</div>
                <div class="mcard-util" style="color:#BDBDBD">OFFLINE</div>
            </div>"""
        else:
            if s == "GREEN":
                bg = "#E8F5E9"; border = "#A5D6A7"
            elif s == "YELLOW":
                bg = "#FFFDE7"; border = "#FFF59D"
            else:
                bg = "#FFEBEE"; border = "#EF9A9A"
            
            machine_cards += f"""
            <div class="mcard" style="background:{bg};border-color:{border}">
                <div class="mcard-id">{mid}</div>
                <div class="mcard-name">{m['name']}</div>
                <div class="mcard-util" style="color:{cut_c}">{cut}%</div>
                <div class="mcard-detail">
                    <span style="color:#1565C0">{m.get('hours_cutting',0)}h cut</span>
                    <span style="color:#90CAF9">{spn}% spn</span>
                </div>
            </div>"""
    
    # Trend section
    trend_html = ""
    if trend_img:
        trend_html = f'<img src="data:image/png;base64,{trend_img}" class="chart-img">'
    
    generated = datetime.now().strftime("%b %d, %Y %I:%M %p")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="300">
<title>FASData Dashboard</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{ width: 1440px; height: 900px; overflow: hidden; font-family: -apple-system, 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #eee; }}
    
    .dash {{ display: grid; grid-template-columns: 320px 1fr 1fr; grid-template-rows: auto 1fr 1fr; gap: 10px; padding: 10px; height: 900px; width: 1440px; }}
    
    /* Header bar spans full width */
    .header {{ grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; background: linear-gradient(135deg, #1B3A5C, #2E5C8A); padding: 10px 20px; border-radius: 8px; }}
    .header h1 {{ font-size: 20px; font-weight: 700; }}
    .header .date {{ font-size: 13px; opacity: 0.8; }}
    .header .gen {{ font-size: 11px; opacity: 0.5; }}
    
    /* Left column: metrics + machine cards */
    .left {{ grid-row: 2 / 4; display: flex; flex-direction: column; gap: 10px; }}
    
    /* Summary metrics row */
    .metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .metric {{ background: #16213e; border-radius: 8px; padding: 12px; text-align: center; }}
    .metric .val {{ font-size: 28px; font-weight: bold; }}
    .metric .lbl {{ font-size: 10px; color: #888; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }}
    
    /* Machine cards */
    .mcards {{ display: flex; flex-direction: column; gap: 6px; flex: 1; }}
    .mcard {{ border-radius: 8px; padding: 10px 14px; display: grid; grid-template-columns: 50px 1fr auto; grid-template-rows: auto auto; align-items: center; gap: 0 8px; border-left: 4px solid; }}
    .mcard-id {{ grid-row: 1/3; font-size: 22px; font-weight: bold; color: #333; text-align: center; }}
    .mcard-name {{ font-size: 12px; color: #555; }}
    .mcard-util {{ grid-row: 1/3; font-size: 26px; font-weight: bold; text-align: right; }}
    .mcard-detail {{ font-size: 10px; display: flex; gap: 10px; }}
    
    /* Chart panels */
    .panel {{ background: #16213e; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; overflow: hidden; }}
    .panel h2 {{ font-size: 13px; color: #7eb8da; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .panel img, .chart-img {{ width: 100%; height: auto; max-height: 100%; object-fit: contain; border-radius: 4px; flex: 1; }}
    
    /* Footer */
    .footer {{ font-size: 10px; color: #555; text-align: center; padding: 2px; }}
</style>
</head>
<body>
<div class="dash">

    <!-- Header -->
    <div class="header">
        <h1>⚙ FASData Machine Utilization</h1>
        <div class="date">{analysis['date_start']} — {analysis['date_end']}</div>
        <div class="gen">Updated {generated} · Refreshes every 5 min</div>
    </div>

    <!-- Left column -->
    <div class="left">
        <div class="metrics">
            <div class="metric">
                <div class="val" style="color:{cutting_color(analysis['shop_avg_utilization'])}">{analysis['shop_avg_utilization']}%</div>
                <div class="lbl">Shop Utilization</div>
            </div>
            <div class="metric">
                <div class="val" style="color:#64B5F6">{analysis.get('total_hours_cutting', 0)}h</div>
                <div class="lbl">Hours Cutting</div>
            </div>
            <div class="metric">
                <div class="val" style="color:#90A4AE">{analysis['total_hours_available']}h</div>
                <div class="lbl">Available</div>
            </div>
            <div class="metric">
                <div class="val" style="color:#B0BEC5">{analysis['active_machine_count']}/{analysis['total_machine_count']}</div>
                <div class="lbl">Machines Active</div>
            </div>
        </div>
        <div class="mcards">
            {machine_cards}
        </div>
    </div>

    <!-- Top right: utilization bar chart -->
    <div class="panel">
        <h2>Utilization by Machine</h2>
        <img src="data:image/png;base64,{bar_img}">
    </div>

    <!-- Top far right: hours breakdown -->
    <div class="panel">
        <h2>Hours Breakdown</h2>
        <img src="data:image/png;base64,{hours_img}">
    </div>

    <!-- Bottom right: daily trend (spans 2 columns) -->
    <div class="panel" style="grid-column: 2 / 4;">
        <h2>Daily Trend</h2>
        {trend_html if trend_html else '<div style="color:#555;text-align:center;padding:40px">Single day — no trend data yet</div>'}
    </div>

</div>
</body>
</html>"""
    
    return html


# ── Main ─────────────────────────────────────────────────────────────────────

def find_database():
    """Check default locations for monitoring.db."""
    for p in DEFAULT_DB_PATHS:
        if os.path.exists(p):
            return p
    return None


def find_dropbox_reports():
    """Find or create the Dropbox reports folder."""
    for p in DROPBOX_REPORT_PATHS:
        parent = os.path.dirname(p)
        if os.path.exists(parent):
            os.makedirs(p, exist_ok=True)
            return p
    return None


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    start_date = sys.argv[2] if len(sys.argv) > 2 else None
    end_date = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Auto-find database if not specified
    if not db_path:
        db_path = find_database()
        if db_path:
            print(f"Found database: {db_path}")
    
    # Get data
    if db_path and os.path.exists(db_path):
        print(f"Reading database: {db_path}")
        rows = query_database(db_path, start_date, end_date)
    else:
        rows = generate_sample_data()
    
    print(f"Total samples: {len(rows)}")
    
    # Analyze
    analysis = analyze_data(rows)
    if not analysis:
        print("ERROR: No usable data found.")
        sys.exit(1)
    
    # Generate charts
    print("\nGenerating charts...")
    generate_charts(analysis)
    
    # Save analysis JSON for docx builder
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "report_data.json")
    with open(json_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"\n  Saved {json_path}")
    
    # Generate HTML report
    print("\nGenerating HTML report...")
    html = generate_html_report(analysis)
    
    # Save locally
    local_html = os.path.join(SCRIPT_DIR, "utilization_report.html")
    with open(local_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved {local_html}")
    
    # Save to Dropbox (latest + dated archive)
    dropbox_dir = find_dropbox_reports()
    if dropbox_dir:
        latest_path = os.path.join(dropbox_dir, "utilization_latest.html")
        dated_path = os.path.join(dropbox_dir, f"utilization_{analysis['date_end']}.html")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html)
        with open(dated_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Saved {latest_path}")
        print(f"  Saved {dated_path}")
    else:
        print("  Dropbox reports folder not found — skipped Dropbox save")
    
    print("\nData ready. Run the docx builder next.")

    # Also generate the shop floor dashboard if the script exists
    import subprocess
    dashboard_script = os.path.join(SCRIPT_DIR, "generate_dashboard.py")
    if os.path.exists(dashboard_script):
        print("\nGenerating shop floor dashboard...")
        subprocess.run([sys.executable, dashboard_script])

    return analysis


if __name__ == "__main__":
    main()
