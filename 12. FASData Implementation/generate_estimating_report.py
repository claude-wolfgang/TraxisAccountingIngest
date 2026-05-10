#!/usr/bin/env python3
"""
Estimating Corrections Report — CAM Intelligence
Traxis Manufacturing

Cross-references diff records with ProgrammingTimer session durations
to show where Toolpath accuracy correlates with programming time.

Generates an HTML report with:
  - Fidelity trends by job/part type
  - Programming time vs fidelity score scatter
  - Correction categories that consume the most time

Usage:
  python generate_estimating_report.py
  python generate_estimating_report.py --diffs-dir path/to/diffs
  python generate_estimating_report.py --sessions-dir path/to/sessions
"""

import json
import os
import sys
import glob
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_DIFFS_DIRS = [
    r"D:\Dropbox\MACHINE COMM Traxis\Programming Sessions\diffs",
]
DEFAULT_SESSIONS_DIRS = [
    r"D:\Dropbox\MACHINE COMM Traxis\Programming Sessions",
]
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "estimating_report.html")


def find_dir(candidates):
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def read_all_diffs(diffs_dir):
    """Read all diff JSONL files."""
    records = []
    if not diffs_dir or not os.path.isdir(diffs_dir):
        return records
    for filepath in sorted(glob.glob(os.path.join(diffs_dir, "*_diff.jsonl"))):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            continue
    return records


def read_session_durations(sessions_dir):
    """Read ProgrammingTimer session JSONL files.

    Returns dict mapping part_identifier -> total minutes.
    """
    durations = {}
    if not sessions_dir or not os.path.isdir(sessions_dir):
        return durations

    for filepath in glob.glob(os.path.join(sessions_dir, "*.jsonl")):
        # Skip diffs subdirectory files
        if "diffs" in filepath:
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    part = rec.get("part_identifier", "")
                    dur = rec.get("duration_seconds", 0)
                    if part and dur > 0:
                        durations[part] = durations.get(part, 0) + dur / 60.0
        except Exception:
            continue
    return durations


def analyze(records, durations):
    """Cross-reference diffs with session durations."""
    if not records:
        return None

    # Per-part analysis
    parts = defaultdict(lambda: {
        "sessions": 0,
        "fidelity_scores": [],
        "correction_counts": [],
        "categories": defaultdict(int),
    })

    for rec in records:
        doc = rec.get("document", "unknown")
        diff = rec.get("diff", {})
        fidelity = diff.get("fidelity_score")
        delta = diff.get("delta", {})

        parts[doc]["sessions"] += 1
        if fidelity is not None:
            parts[doc]["fidelity_scores"].append(fidelity)

        # Count corrections by category
        corrections = 0
        for mod in delta.get("operations_modified", []):
            for change in mod.get("changes", []):
                category = change.get("category", "other")
                parts[doc]["categories"][category] += 1
                corrections += 1
        parts[doc]["correction_counts"].append(corrections)

    # Build per-part summary with duration matching
    part_summaries = []
    for part, data in parts.items():
        avg_fidelity = (
            round(sum(data["fidelity_scores"]) / len(data["fidelity_scores"]), 1)
            if data["fidelity_scores"] else None
        )
        avg_corrections = (
            round(sum(data["correction_counts"]) / len(data["correction_counts"]), 1)
            if data["correction_counts"] else 0
        )

        # Try to match with ProgrammingTimer duration
        prog_minutes = durations.get(part, 0)

        part_summaries.append({
            "part": part,
            "sessions": data["sessions"],
            "avg_fidelity": avg_fidelity,
            "avg_corrections": avg_corrections,
            "programming_minutes": round(prog_minutes, 1),
            "categories": dict(data["categories"]),
        })

    # Sort by fidelity (worst first)
    part_summaries.sort(key=lambda x: x["avg_fidelity"] or 0)

    # Category totals
    cat_totals = defaultdict(int)
    for data in parts.values():
        for cat, count in data["categories"].items():
            cat_totals[cat] += count

    return {
        "total_sessions": len(records),
        "total_parts": len(parts),
        "part_summaries": part_summaries,
        "category_totals": dict(
            sorted(cat_totals.items(), key=lambda x: -x[1])),
    }


def generate_html(analysis, output_path):
    """Generate HTML estimating report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if analysis is None:
        html = f"""<!DOCTYPE html><html><head>
        <meta charset="UTF-8">
        <title>Estimating Corrections Report</title></head><body>
        <h1>Estimating Corrections Report</h1>
        <p>Generated {now}</p>
        <p>No data available. Sessions will appear after TraxisCapture runs.</p>
        </body></html>"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return

    # Part summary rows
    part_rows = ""
    for p in analysis["part_summaries"]:
        fid = p["avg_fidelity"]
        if fid is not None:
            if fid >= 90:
                color = "#22c55e"
            elif fid >= 70:
                color = "#eab308"
            elif fid >= 50:
                color = "#f97316"
            else:
                color = "#ef4444"
            fid_str = f'<span style="color:{color};font-weight:bold">{fid}%</span>'
        else:
            fid_str = "—"

        time_str = f"{p['programming_minutes']:.0f} min" if p["programming_minutes"] > 0 else "—"

        part_rows += f"""
        <tr>
            <td>{p['part']}</td>
            <td>{p['sessions']}</td>
            <td>{fid_str}</td>
            <td>{p['avg_corrections']}</td>
            <td>{time_str}</td>
        </tr>"""

    # Category rows
    cat_rows = ""
    for cat, count in analysis["category_totals"].items():
        cat_rows += f"<tr><td>{cat}</td><td>{count}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Estimating Corrections Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 20px; }}
    h1 {{ color: #f8fafc; margin-bottom: 4px; font-size: 24px; }}
    h2 {{ color: #94a3b8; margin: 24px 0 12px; font-size: 18px;
          border-bottom: 1px solid #334155; padding-bottom: 6px; }}
    .meta {{ color: #64748b; font-size: 13px; margin-bottom: 20px; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 16px;
             margin-bottom: 16px; }}
    .stat-row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
    .stat-box {{ background: #1e293b; border-radius: 8px; padding: 16px;
                 flex: 1; min-width: 150px; text-align: center; }}
    .stat-value {{ font-size: 32px; font-weight: bold; }}
    .stat-label {{ color: #94a3b8; font-size: 13px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th {{ text-align: left; padding: 8px 12px; background: #334155;
          color: #94a3b8; font-weight: 600; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; }}
    tr:hover {{ background: #1e293b; }}
    .note {{ color: #94a3b8; font-size: 13px; font-style: italic;
             margin-top: 8px; }}
</style>
</head>
<body>
<h1>Estimating Corrections Report</h1>
<p class="meta">Generated {now} &mdash; Traxis Manufacturing</p>

<div class="stat-row">
    <div class="stat-box">
        <div class="stat-value">{analysis['total_sessions']}</div>
        <div class="stat-label">Sessions Analyzed</div>
    </div>
    <div class="stat-box">
        <div class="stat-value">{analysis['total_parts']}</div>
        <div class="stat-label">Unique Parts</div>
    </div>
</div>

<h2>Part Fidelity &amp; Programming Time</h2>
<p class="note">Parts with low fidelity and high programming time indicate
systematic gaps in Toolpath Cut Config — priority candidates for correction.</p>
<div class="card">
<table>
    <tr><th>Part</th><th>Sessions</th><th>Avg Fidelity</th>
        <th>Avg Corrections</th><th>Programming Time</th></tr>
    {part_rows}
</table>
</div>

<h2>Correction Categories</h2>
<p class="note">Categories that appear most frequently are the best
targets for Toolpath library updates.</p>
<div class="card">
<table>
    <tr><th>Category</th><th>Total Corrections</th></tr>
    {cat_rows}
</table>
</div>

</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate estimating corrections report")
    parser.add_argument("--diffs-dir", help="Path to diffs directory")
    parser.add_argument("--sessions-dir", help="Path to sessions directory")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    diffs_dir = args.diffs_dir or find_dir(DEFAULT_DIFFS_DIRS)
    sessions_dir = args.sessions_dir or find_dir(DEFAULT_SESSIONS_DIRS)

    print(f"Diffs dir:    {diffs_dir or 'not found'}")
    print(f"Sessions dir: {sessions_dir or 'not found'}")

    records = read_all_diffs(diffs_dir)
    durations = read_session_durations(sessions_dir)
    print(f"Diff records: {len(records)}")
    print(f"Timer parts:  {len(durations)}")

    analysis = analyze(records, durations)
    generate_html(analysis, args.output)
    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()
