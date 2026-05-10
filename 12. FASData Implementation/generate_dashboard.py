#!/usr/bin/env python3
"""
FASData Shop Floor Dashboard Generator
Traxis Manufacturing

Reads report_data.json (produced by generate_report.py) and generates a
self-contained Aztec/Mesoamerican-themed HTML dashboard designed for a 32"
1080p TV on the shop floor.

Usage:
  python generate_dashboard.py
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
REPORT_ASSETS_DIR = SCRIPT_DIR / "report_assets"

DROPBOX_REPORT_PATHS = [
    Path(r"D:\Dropbox\MACHINE COMM Traxis\FASData\reports"),
    Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\reports"),
    Path(r"C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports"),
]

GREEN_THRESHOLD = 30
YELLOW_THRESHOLD = 10


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_report_data():
    json_path = REPORT_ASSETS_DIR / "report_data.json"
    if not json_path.exists():
        print(f"ERROR: {json_path} not found. Run generate_report.py first.")
        sys.exit(1)
    with open(json_path) as f:
        return json.load(f)


def status_color(status):
    return {
        "GREEN": "#2d8659",
        "YELLOW": "#d4a926",
        "RED": "#b91c1c",
        "OFFLINE": "#555555",
        "NO DATA": "#555555",
    }.get(status, "#555555")


def status_glow(status):
    return {
        "GREEN": "rgba(45,134,89,0.5)",
        "YELLOW": "rgba(212,169,38,0.5)",
        "RED": "rgba(185,28,28,0.5)",
        "OFFLINE": "rgba(85,85,85,0.15)",
        "NO DATA": "rgba(85,85,85,0.15)",
    }.get(status, "rgba(85,85,85,0.15)")


def status_label(status):
    return {
        "GREEN": "ON TARGET",
        "YELLOW": "BELOW TARGET",
        "RED": "CRITICAL",
        "OFFLINE": "OFFLINE",
        "NO DATA": "NO DATA",
    }.get(status, "UNKNOWN")


# ── SVG Gauge ────────────────────────────────────────────────────────────────

def make_gauge_svg(pct, status):
    """Generate an SVG donut ring gauge with percentage centered inside."""
    color = status_color(status)
    cx, cy, r = 100, 100, 78
    circumference = 2 * math.pi * r  # ~490.1

    # Background ring
    bg = (f'<circle cx="{cx}" cy="{cy}" r="{r}" '
          f'fill="none" stroke="#1a1508" stroke-width="14"/>')

    # Tick marks at thresholds
    ticks = ""
    for thr in [GREEN_THRESHOLD, YELLOW_THRESHOLD]:
        a = math.radians(-90 + (thr / 100) * 360)
        x1 = cx + (r - 12) * math.cos(a)
        y1 = cy + (r - 12) * math.sin(a)
        x2 = cx + (r + 12) * math.cos(a)
        y2 = cy + (r + 12) * math.sin(a)
        ticks += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
                  f'x2="{x2:.1f}" y2="{y2:.1f}" '
                  f'stroke="#4a3a20" stroke-width="2"/>')

    if status in ("OFFLINE", "NO DATA"):
        label = (f'<text x="{cx}" y="{cy+8}" text-anchor="middle" '
                 f'fill="#555" font-size="26" font-weight="bold" '
                 f'font-family="Arial,sans-serif">OFFLINE</text>')
        return f'<svg viewBox="0 0 200 200" class="gauge">{bg}{ticks}{label}</svg>'

    pct_c = max(0, min(100, pct))

    # Value arc (circle with dashoffset, rotated to start from top)
    if pct_c <= 0:
        val_arc = ""
    else:
        offset = circumference * (1 - pct_c / 100)
        val_arc = (f'<circle cx="{cx}" cy="{cy}" r="{r}" '
                   f'fill="none" stroke="{color}" stroke-width="14" stroke-linecap="round" '
                   f'class="gauge-arc" '
                   f'transform="rotate(-90 {cx} {cy})" '
                   f'style="stroke-dasharray:{circumference:.1f};'
                   f'stroke-dashoffset:{offset:.1f}"/>')

    # Percentage text (centered inside the ring)
    txt = (f'<text x="{cx}" y="{cy+8}" text-anchor="middle" fill="{color}" '
           f'font-size="46" font-weight="bold" font-family="Arial,sans-serif">'
           f'{pct:.1f}%</text>')

    return f'<svg viewBox="0 0 200 200" class="gauge">{bg}{val_arc}{ticks}{txt}</svg>'


# ── Machine Card ─────────────────────────────────────────────────────────────

def make_machine_card(mid, stats):
    color = status_color(stats["status"])
    glow = status_glow(stats["status"])
    label = status_label(stats["status"])
    cutting_pct = stats.get("cutting_pct", 0)
    gauge = make_gauge_svg(cutting_pct, stats["status"])
    status_cls = stats["status"].lower().replace(" ", "-")

    if stats["status"] in ("OFFLINE", "NO DATA"):
        detail = '<div class="card-detail">No connection</div>'
    else:
        hc = stats.get("hours_cutting", 0)
        ha = stats.get("hours_available", 0)
        sp = stats.get("spindle_only_pct", 0)
        detail = (f'<div class="card-detail">{hc}h cutting / {ha}h avail</div>'
                  f'<div class="card-detail-sub">{sp}% spindle only</div>')

    return f"""
        <div class="machine-card status-{status_cls}"
             style="--sc:{color};--sg:{glow}">
            <div class="card-aztec-top"></div>
            <div class="card-body">
                <div class="card-id">{mid}</div>
                <div class="card-name">{stats['name']}</div>
                <div class="card-gauge">{gauge}</div>
                {detail}
                <div class="card-status">{label}</div>
            </div>
            <div class="card-aztec-bottom"></div>
        </div>"""


# ── Aztec Sun Motif SVG ─────────────────────────────────────────────────────

AZTEC_SUN = """<svg viewBox="0 0 60 60" width="56" height="56" class="aztec-sun">
  <circle cx="30" cy="30" r="27" fill="none" stroke="#c45a3c" stroke-width="1.5" opacity="0.7"/>
  <circle cx="30" cy="30" r="20" fill="none" stroke="#d4a926" stroke-width="1" opacity="0.6"/>
  <circle cx="30" cy="30" r="11" fill="none" stroke="#c45a3c" stroke-width="2"/>
  <circle cx="30" cy="30" r="4" fill="#d4a926"/>
  <polygon points="30,1 27.5,9 32.5,9" fill="#d4a926" opacity="0.8"/>
  <polygon points="30,59 27.5,51 32.5,51" fill="#d4a926" opacity="0.8"/>
  <polygon points="1,30 9,27.5 9,32.5" fill="#d4a926" opacity="0.8"/>
  <polygon points="59,30 51,27.5 51,32.5" fill="#d4a926" opacity="0.8"/>
  <polygon points="9,9 13.5,14 16,11.5" fill="#c45a3c" opacity="0.6"/>
  <polygon points="51,51 46.5,46 44,48.5" fill="#c45a3c" opacity="0.6"/>
  <polygon points="51,9 46.5,14 44,11.5" fill="#c45a3c" opacity="0.6"/>
  <polygon points="9,51 13.5,46 16,48.5" fill="#c45a3c" opacity="0.6"/>
  <circle cx="30" cy="16" r="2" fill="#3eb8a0" opacity="0.7"/>
  <circle cx="30" cy="44" r="2" fill="#3eb8a0" opacity="0.7"/>
  <circle cx="16" cy="30" r="2" fill="#3eb8a0" opacity="0.7"/>
  <circle cx="44" cy="30" r="2" fill="#3eb8a0" opacity="0.7"/>
</svg>"""


# ── Full HTML Template ───────────────────────────────────────────────────────

def generate_dashboard_html(data):
    machines = data["machines"]
    mids = sorted(machines.keys())
    machine_cards_html = "\n".join(make_machine_card(mid, machines[mid]) for mid in mids)

    shop_avg = data.get("shop_avg_utilization", 0)
    shop_color = status_color(
        "GREEN" if shop_avg >= GREEN_THRESHOLD else
        "YELLOW" if shop_avg >= YELLOW_THRESHOLD else "RED"
    )
    active = data.get("active_machine_count", 0)
    total = data.get("total_machine_count", 0)
    hours_cut = data.get("total_hours_cutting", 0)
    hours_avail = data.get("total_hours_available", 0)
    shift = data.get("shift_hours", "6:00 - 19:00")
    date_start = data.get("date_start", "")
    date_end = data.get("date_end", "")

    try:
        rdt = datetime.fromisoformat(data.get("report_generated", ""))
        updated = rdt.strftime("%b %d, %Y  %I:%M %p")
    except Exception:
        updated = data.get("report_generated", "Unknown")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="300">
<title>Traxis Manufacturing - Shop Floor Dashboard</title>
<style>
/* ── Reset & Base ─────────────────────────────────────────── */
*, *::before, *::after {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{
    width:1920px; height:1080px; overflow:hidden;
    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
    background: #0e0a05;
    color: #e8dcc8;
}}

/* ── CSS Variables ────────────────────────────────────────── */
:root {{
    --obsidian: #0e0a05;
    --dark-stone: #1a1208;
    --stone: #251c0e;
    --stone-mid: #2f2415;
    --light-stone: #3d2e18;
    --terracotta: #c45a3c;
    --terracotta-dk: #8b3a25;
    --gold: #d4a926;
    --gold-dk: #8b7117;
    --jade: #2d8659;
    --jade-lt: #3aad72;
    --turquoise: #3eb8a0;
    --blood: #b91c1c;
    --blood-lt: #dc2626;
    --warm-white: #e8dcc8;
    --warm-gray: #a39580;
}}

/* ── Dashboard Grid ───────────────────────────────────────── */
.dashboard {{
    display: flex;
    flex-direction: column;
    width: 1920px;
    height: 1080px;
}}

/* ── Aztec Band Pattern ───────────────────────────────────── */
.aztec-band {{
    height: 8px;
    flex-shrink: 0;
    background: repeating-linear-gradient(90deg,
        var(--terracotta) 0 28px,
        var(--gold-dk) 28px 32px,
        var(--obsidian) 32px 36px,
        var(--gold-dk) 36px 40px,
        var(--turquoise) 40px 68px,
        var(--gold-dk) 68px 72px,
        var(--obsidian) 72px 76px,
        var(--gold-dk) 76px 80px
    );
}}
.aztec-band-thin {{
    height: 4px;
    flex-shrink: 0;
    background: repeating-linear-gradient(90deg,
        var(--terracotta) 0 14px,
        var(--gold-dk) 14px 16px,
        var(--turquoise) 16px 30px,
        var(--gold-dk) 30px 32px
    );
}}

/* ── Header ───────────────────────────────────────────────── */
.header {{
    height: 80px;
    flex-shrink: 0;
    background: linear-gradient(180deg, #1a1208 0%, #120e06 100%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 40px;
    border-bottom: 2px solid var(--terracotta-dk);
}}
.header-left {{
    display: flex;
    align-items: center;
    gap: 20px;
}}
.header-title {{
    display: flex;
    flex-direction: column;
}}
.header-title .company {{
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: var(--terracotta);
}}
.header-title .subtitle {{
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--warm-white);
}}
.header-right {{
    text-align: right;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
}}
.clock {{
    font-size: 36px;
    font-weight: 700;
    color: var(--gold);
    font-variant-numeric: tabular-nums;
    letter-spacing: 1px;
}}
.header-date {{
    font-size: 13px;
    color: var(--warm-gray);
    letter-spacing: 1px;
}}
.aztec-sun {{
    opacity: 0.85;
}}

/* ── Machine Cards Area ───────────────────────────────────── */
.machines {{
    flex: 1;
    display: flex;
    align-items: stretch;
    justify-content: center;
    gap: 20px;
    padding: 24px 36px;
}}

/* ── Machine Card ─────────────────────────────────────────── */
.machine-card {{
    flex: 1;
    max-width: 360px;
    display: flex;
    flex-direction: column;
    border-radius: 8px;
    overflow: hidden;
    background: var(--dark-stone);
    border: 2px solid var(--light-stone);
    box-shadow:
        0 0 20px var(--sg),
        inset 0 1px 0 rgba(255,255,255,0.04);
    transition: box-shadow 0.3s;
}}

/* Aztec zigzag decorations on cards */
.card-aztec-top, .card-aztec-bottom {{
    height: 10px;
    flex-shrink: 0;
    background:
        linear-gradient(135deg, var(--terracotta) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(225deg, var(--terracotta) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(315deg, var(--gold-dk) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(45deg, var(--gold-dk) 33%, transparent 33%) 0 0 / 10px 10px;
    background-color: var(--dark-stone);
}}

.card-body {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 16px 12px;
    gap: 6px;
    /* Subtle stone texture */
    background:
        radial-gradient(ellipse at 30% 20%, rgba(196,90,60,0.04) 0%, transparent 60%),
        radial-gradient(ellipse at 70% 80%, rgba(62,184,160,0.03) 0%, transparent 60%),
        var(--dark-stone);
}}

.card-id {{
    font-size: 72px;
    font-weight: 900;
    line-height: 1;
    color: var(--warm-white);
    letter-spacing: 4px;
    text-shadow: 0 2px 8px rgba(0,0,0,0.5);
}}
.card-name {{
    font-size: 16px;
    font-weight: 600;
    color: var(--warm-gray);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 4px;
}}

.card-gauge {{
    width: 100%;
    max-width: 220px;
}}
.gauge {{
    width: 100%;
    height: auto;
    display: block;
    filter: drop-shadow(0 0 6px var(--sg));
}}

/* Gauge arc animation */
.gauge-arc {{
    animation: arc-fill 1.2s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
}}
@keyframes arc-fill {{
    from {{ stroke-dashoffset: 490.1; }}
}}

.card-detail {{
    font-size: 16px;
    color: var(--warm-gray);
    letter-spacing: 0.5px;
    margin-top: 2px;
}}
.card-detail-sub {{
    font-size: 13px;
    color: #6b5d4a;
}}

.card-status {{
    margin-top: 8px;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--sc);
    text-shadow: 0 0 12px var(--sg);
    padding: 4px 16px;
    border: 2px solid var(--sc);
    border-radius: 4px;
    background: rgba(0,0,0,0.3);
}}

/* Status-specific card styles */
.status-green {{ border-color: var(--jade); }}
.status-green .card-aztec-top,
.status-green .card-aztec-bottom {{
    background:
        linear-gradient(135deg, var(--jade) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(225deg, var(--jade) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(315deg, var(--gold-dk) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(45deg, var(--gold-dk) 33%, transparent 33%) 0 0 / 10px 10px;
    background-color: var(--dark-stone);
}}

.status-yellow {{ border-color: var(--gold-dk); }}

.status-red {{ border-color: var(--blood); }}
.status-red .card-aztec-top,
.status-red .card-aztec-bottom {{
    background:
        linear-gradient(135deg, var(--blood) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(225deg, var(--blood) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(315deg, var(--terracotta-dk) 33%, transparent 33%) 0 0 / 10px 10px,
        linear-gradient(45deg, var(--terracotta-dk) 33%, transparent 33%) 0 0 / 10px 10px;
    background-color: var(--dark-stone);
}}

.status-offline {{
    border-color: #333;
    opacity: 0.6;
}}
.status-offline .card-status {{
    animation: offline-pulse 3s ease-in-out infinite;
}}
@keyframes offline-pulse {{
    0%, 100% {{ opacity: 0.5; }}
    50% {{ opacity: 1; }}
}}

/* ── Summary Bar ──────────────────────────────────────────── */
.summary-bar {{
    height: 100px;
    flex-shrink: 0;
    background: linear-gradient(180deg, #12100a 0%, #1a1208 100%);
    border-top: 2px solid var(--light-stone);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    padding: 0 40px;
}}
.summary-item {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 8px 20px;
    position: relative;
}}
.summary-item:not(:last-child)::after {{
    content: '';
    position: absolute;
    right: 0;
    top: 15%;
    height: 70%;
    width: 2px;
    background: linear-gradient(180deg, transparent, var(--terracotta-dk), transparent);
}}
.summary-value {{
    font-size: 36px;
    font-weight: 800;
    letter-spacing: 1px;
    font-variant-numeric: tabular-nums;
}}
.summary-label {{
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--warm-gray);
    margin-top: 2px;
}}

/* ── Footer ───────────────────────────────────────────────── */
.footer {{
    height: 36px;
    flex-shrink: 0;
    background: var(--obsidian);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 30px;
    font-size: 12px;
    color: #5a4d3a;
    letter-spacing: 1px;
}}
.footer span {{ opacity: 0.7; }}

/* ── Utility ──────────────────────────────────────────────── */
.diamond-sep {{
    display: inline-block;
    color: var(--terracotta-dk);
    margin: 0 8px;
    font-size: 10px;
}}
</style>
</head>
<body>
<div class="dashboard">

    <!-- Top Aztec band -->
    <div class="aztec-band"></div>

    <!-- Header -->
    <header class="header">
        <div class="header-left">
            {AZTEC_SUN}
            <div class="header-title">
                <span class="company">Traxis Manufacturing</span>
                <span class="subtitle">Machine Utilization</span>
            </div>
        </div>
        <div class="header-right">
            <div class="clock" id="clock">--:--:--</div>
            <div class="header-date">{date_start} to {date_end}</div>
        </div>
    </header>

    <div class="aztec-band-thin"></div>

    <!-- Machine Cards -->
    <div class="machines">
{machine_cards_html}
    </div>

    <!-- Summary Bar -->
    <div class="summary-bar">
        <div class="summary-item">
            <div class="summary-value" style="color:{shop_color}">{shop_avg}%</div>
            <div class="summary-label">Shop Average</div>
        </div>
        <div class="summary-item">
            <div class="summary-value" style="color:var(--turquoise)">{active} / {total}</div>
            <div class="summary-label">Active Machines</div>
        </div>
        <div class="summary-item">
            <div class="summary-value" style="color:#8aafcf">{hours_cut}h <span style="font-size:20px;color:var(--warm-gray)">/ {hours_avail}h</span></div>
            <div class="summary-label">Cutting / Available</div>
        </div>
        <div class="summary-item">
            <div class="summary-value" style="color:var(--warm-gray)">{shift}</div>
            <div class="summary-label">Shift Hours</div>
        </div>
    </div>

    <div class="aztec-band-thin"></div>

    <!-- Footer -->
    <footer class="footer">
        <span>Last updated: {updated}</span>
        <span class="diamond-sep">&#9670;</span>
        <span>Auto-refresh: 5 min</span>
        <span class="diamond-sep">&#9670;</span>
        <span>FASData Monitoring System</span>
    </footer>

    <div class="aztec-band"></div>
</div>

<script>
(function() {{
    function pad(n) {{ return n < 10 ? '0' + n : n; }}
    function tick() {{
        var d = new Date();
        var h = d.getHours(), m = d.getMinutes(), s = d.getSeconds();
        var ap = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        document.getElementById('clock').textContent =
            h + ':' + pad(m) + ':' + pad(s) + ' ' + ap;
    }}
    tick();
    setInterval(tick, 1000);
}})();
</script>
</body>
</html>"""
    return html


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Generating shop floor dashboard...")
    data = load_report_data()
    html = generate_dashboard_html(data)

    # Save locally
    local_path = SCRIPT_DIR / "dashboard.html"
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved {local_path}")

    # Save to Dropbox
    for p in DROPBOX_REPORT_PATHS:
        if p.parent.exists():
            p.mkdir(parents=True, exist_ok=True)
            dash_path = p / "dashboard.html"
            with open(dash_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  Saved {dash_path}")
            break
    else:
        print("  Dropbox reports folder not found -- skipped Dropbox save")

    print("Dashboard generation complete.")


if __name__ == "__main__":
    main()
