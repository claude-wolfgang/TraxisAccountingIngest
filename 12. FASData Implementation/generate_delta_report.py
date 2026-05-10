#!/usr/bin/env python3
"""
Delta Report Generator — CAM Intelligence
Traxis Manufacturing

Reads diff JSONL files from Programming Sessions/diffs/ and generates
an HTML report showing fidelity trends, common corrections, and
tool-specific patterns.

Usage:
  python generate_delta_report.py
  python generate_delta_report.py --diffs-dir path/to/diffs
  python generate_delta_report.py --output report.html
"""

import json
import os
import sys
import glob
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Default diffs directory locations to check
DEFAULT_DIFFS_DIRS = [
    r"D:\Dropbox\MACHINE COMM Traxis\Programming Sessions\diffs",
    os.path.join(SCRIPT_DIR, "test_diffs"),
]

DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "delta_report.html")


def find_diffs_dir():
    """Find the diffs directory."""
    for path in DEFAULT_DIFFS_DIRS:
        if os.path.isdir(path):
            return path
    return None


def read_all_diffs(diffs_dir):
    """Read all diff JSONL files."""
    records = []
    for filepath in sorted(glob.glob(os.path.join(diffs_dir, "*_diff.jsonl"))):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as e:
            print(f"  Warning: Could not read {filepath}: {e}")
    return records


def analyze_records(records):
    """Analyze diff records and produce summary metrics."""
    if not records:
        return None

    # Fidelity scores over time
    fidelity_timeline = []
    for rec in records:
        diff = rec.get("diff", {})
        score = diff.get("fidelity_score")
        if score is not None:
            fidelity_timeline.append({
                "session_id": rec.get("session_id", ""),
                "document": rec.get("document", ""),
                "origin": rec.get("origin", ""),
                "fidelity_score": score,
                "date": rec.get("started_at", "")[:10],
            })

    # Common corrections (aggregated)
    corrections = defaultdict(lambda: {
        "count": 0, "jobs": set(), "from_values": [], "to_values": []
    })
    for rec in records:
        diff = rec.get("diff", {})
        delta = diff.get("delta", {})
        doc = rec.get("document", "")
        for mod in delta.get("operations_modified", []):
            tool_id = mod.get("tool_id", "")
            for change in mod.get("changes", []):
                field = change.get("field", "")
                key = (field, tool_id)
                corrections[key]["count"] += 1
                corrections[key]["jobs"].add(doc)
                corrections[key]["from_values"].append(change.get("from"))
                corrections[key]["to_values"].append(change.get("to"))

    # Sort by frequency
    top_corrections = sorted(
        corrections.items(), key=lambda x: -x[1]["count"])[:20]

    # Origin breakdown
    origins = defaultdict(int)
    for rec in records:
        origins[rec.get("origin", "unknown")] += 1

    # Average fidelity by origin
    fidelity_by_origin = defaultdict(list)
    for item in fidelity_timeline:
        fidelity_by_origin[item["origin"]].append(item["fidelity_score"])

    avg_fidelity = {}
    for origin, scores in fidelity_by_origin.items():
        avg_fidelity[origin] = round(sum(scores) / len(scores), 1)

    return {
        "total_sessions": len(records),
        "fidelity_timeline": fidelity_timeline,
        "top_corrections": [
            {
                "field": k[0],
                "tool_id": k[1],
                "count": v["count"],
                "jobs": sorted(v["jobs"]),
                "from_values": v["from_values"][:5],
                "to_values": v["to_values"][:5],
            }
            for k, v in top_corrections
        ],
        "origins": dict(origins),
        "avg_fidelity_by_origin": avg_fidelity,
        "overall_avg_fidelity": round(
            sum(f["fidelity_score"] for f in fidelity_timeline)
            / max(len(fidelity_timeline), 1), 1),
    }


def _fidelity_color(score):
    """Return CSS color for a fidelity score."""
    if score >= 90:
        return "#22c55e"  # green
    elif score >= 70:
        return "#eab308"  # yellow
    elif score >= 50:
        return "#f97316"  # orange
    else:
        return "#ef4444"  # red


def _fidelity_label(score):
    """Return label for a fidelity score."""
    if score >= 90:
        return "Excellent"
    elif score >= 70:
        return "Good"
    elif score >= 50:
        return "Needs Review"
    else:
        return "Major Rework"


def generate_html(analysis, output_path):
    """Generate HTML report from analysis data."""
    if analysis is None:
        html = """<!DOCTYPE html><html><body>
        <h1>CAM Intelligence Delta Report</h1>
        <p>No diff data found. Sessions will appear here after programmers
        use the TraxisCapture add-in.</p></body></html>"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build fidelity timeline rows
    fidelity_rows = ""
    for item in analysis["fidelity_timeline"][-50:]:  # Last 50
        score = item["fidelity_score"]
        color = _fidelity_color(score)
        fidelity_rows += f"""
        <tr>
            <td>{item['date']}</td>
            <td>{item['document']}</td>
            <td>{item['origin']}</td>
            <td style="color:{color};font-weight:bold">{score}%</td>
            <td>{_fidelity_label(score)}</td>
        </tr>"""

    # Build corrections table
    corr_rows = ""
    for corr in analysis["top_corrections"]:
        from_val = corr["from_values"][0] if corr["from_values"] else "—"
        to_val = corr["to_values"][0] if corr["to_values"] else "—"
        corr_rows += f"""
        <tr>
            <td>{corr['field']}</td>
            <td>{corr['tool_id']}</td>
            <td>{corr['count']}</td>
            <td>{from_val}</td>
            <td>{to_val}</td>
            <td>{', '.join(corr['jobs'][:3])}</td>
        </tr>"""

    # Build origin summary
    origin_rows = ""
    for origin, count in analysis["origins"].items():
        avg = analysis["avg_fidelity_by_origin"].get(origin, "—")
        origin_rows += f"""
        <tr>
            <td>{origin}</td>
            <td>{count}</td>
            <td>{avg}%</td>
        </tr>"""

    overall = analysis["overall_avg_fidelity"]
    overall_color = _fidelity_color(overall)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CAM Intelligence Delta Report</title>
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
</style>
</head>
<body>
<h1>CAM Intelligence Delta Report</h1>
<p class="meta">Generated {now} &mdash; Traxis Manufacturing</p>

<div class="stat-row">
    <div class="stat-box">
        <div class="stat-value">{analysis['total_sessions']}</div>
        <div class="stat-label">Sessions Captured</div>
    </div>
    <div class="stat-box">
        <div class="stat-value" style="color:{overall_color}">{overall}%</div>
        <div class="stat-label">Avg Fidelity Score</div>
    </div>
    <div class="stat-box">
        <div class="stat-value">{len(analysis['top_corrections'])}</div>
        <div class="stat-label">Unique Corrections</div>
    </div>
</div>

<h2>Origin Breakdown</h2>
<div class="card">
<table>
    <tr><th>Origin</th><th>Sessions</th><th>Avg Fidelity</th></tr>
    {origin_rows}
</table>
</div>

<h2>Fidelity Timeline (Last 50 Sessions)</h2>
<div class="card">
<table>
    <tr><th>Date</th><th>Document</th><th>Origin</th><th>Fidelity</th><th>Status</th></tr>
    {fidelity_rows}
</table>
</div>

<h2>Top Corrections (Most Frequent)</h2>
<div class="card">
<table>
    <tr><th>Field</th><th>Tool</th><th>Count</th><th>From</th><th>To</th><th>Jobs</th></tr>
    {corr_rows}
</table>
</div>

</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate CAM Intelligence delta report")
    parser.add_argument("--diffs-dir", help="Path to diffs directory")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output HTML path")
    args = parser.parse_args()

    diffs_dir = args.diffs_dir or find_diffs_dir()
    if diffs_dir is None:
        print("No diffs directory found. Creating empty report.")
        generate_html(None, args.output)
        print(f"Report written to: {args.output}")
        return

    print(f"Reading diffs from: {diffs_dir}")
    records = read_all_diffs(diffs_dir)
    print(f"Found {len(records)} session records")

    analysis = analyze_records(records)
    generate_html(analysis, args.output)
    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()
