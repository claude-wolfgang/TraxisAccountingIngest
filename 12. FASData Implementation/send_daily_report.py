#!/usr/bin/env python3
"""
FASData Daily Report Sender
Traxis Manufacturing

Generates an HTML utilization report and:
  1. Saves it to Dropbox for browser viewing
  2. Optionally sends it via email if SMTP is configured

Usage:
  python send_daily_report.py                    # Generate report for latest data
  python send_daily_report.py 2026-01-27 2026-01-31  # Custom date range
  python send_daily_report.py --no-email         # Skip email, only save to Dropbox

Scheduled via Windows Task Scheduler to run daily at 7 PM.
"""

import os
import sys
import json
import base64
import smtplib
import subprocess
from datetime import datetime
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

# ── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
REPORT_ASSETS_DIR = SCRIPT_DIR / "report_assets"
EMAIL_CONFIG_PATH = SCRIPT_DIR / "email_config.json"

# Output locations
DROPBOX_REPORTS_DIR = Path(r"D:\Dropbox\MACHINE COMM Traxis\FASData\reports")
DROPBOX_REPORTS_DIR_ALT = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\reports")

# Python executable path
PYTHON_EXE = Path(r"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe")
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

# Thresholds (must match generate_report.py)
GREEN_THRESHOLD = 30
YELLOW_THRESHOLD = 10


# ── HTML Template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>FASData Utilization Report - {date_range}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a365d;
            border-bottom: 3px solid #2b6cb0;
            padding-bottom: 15px;
            margin-top: 0;
        }}
        h2 {{
            color: #2d3748;
            margin-top: 30px;
        }}
        .summary-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .summary-box h3 {{
            margin-top: 0;
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .summary-box .big-number {{
            font-size: 3em;
            font-weight: bold;
            line-height: 1;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #4299e1;
        }}
        .stat-card.green {{ border-left-color: #38a169; }}
        .stat-card.yellow {{ border-left-color: #d69e2e; }}
        .stat-card.red {{ border-left-color: #e53e3e; }}
        .stat-card.gray {{ border-left-color: #a0aec0; }}
        .stat-label {{
            font-size: 0.85em;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: #2d3748;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background: #edf2f7;
            font-weight: 600;
            color: #4a5568;
        }}
        tr:hover {{
            background: #f7fafc;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .status-green {{ background: #c6f6d5; color: #22543d; }}
        .status-yellow {{ background: #fefcbf; color: #744210; }}
        .status-red {{ background: #fed7d7; color: #742a2a; }}
        .status-offline {{ background: #e2e8f0; color: #4a5568; }}
        .chart-container {{
            margin: 25px 0;
            text-align: center;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            font-size: 0.85em;
            color: #718096;
            text-align: center;
        }}
        .progress-bar {{
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }}
        .progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}
        .progress-fill.green {{ background: #38a169; }}
        .progress-fill.yellow {{ background: #d69e2e; }}
        .progress-fill.red {{ background: #e53e3e; }}
        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .container {{ padding: 15px; }}
            .summary-box .big-number {{ font-size: 2em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>CNC Machine Utilization Report</h1>
        <p><strong>Date Range:</strong> {date_start} to {date_end} ({num_days} day{days_plural})</p>
        <p><strong>Shift Hours:</strong> {shift_hours}</p>
        <p><strong>Report Generated:</strong> {report_time}</p>

        <div class="summary-box">
            <h3>Shop Average Utilization</h3>
            <div class="big-number">{shop_avg}%</div>
            <p style="margin-bottom:0">{active_count} of {total_count} machines active | {total_running}h running / {total_available}h available</p>
        </div>

        <h2>Machine Summary</h2>
        <div class="summary-grid">
{machine_cards}
        </div>

        <h2>Detailed Status</h2>
        <table>
            <thead>
                <tr>
                    <th>Machine</th>
                    <th>Utilization</th>
                    <th>Hours Running</th>
                    <th>Hours Available</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
{table_rows}
            </tbody>
        </table>

        <h2>Utilization Chart</h2>
        <div class="chart-container">
            {bar_chart}
        </div>

        <h2>Daily Trend</h2>
        <div class="chart-container">
            {trend_chart}
        </div>

        <h2>Hours Breakdown</h2>
        <div class="chart-container">
            {hours_chart}
        </div>

        <div class="footer">
            <p>Generated by FASData Monitoring System | Traxis Manufacturing</p>
            <p>Data collected via FOCAS from FANUC CNC controllers</p>
        </div>
    </div>
</body>
</html>
"""

MACHINE_CARD_TEMPLATE = """            <div class="stat-card {status_class}">
                <div class="stat-label">{machine_id} - {machine_name}</div>
                <div class="stat-value">{utilization}%</div>
                <div class="progress-bar">
                    <div class="progress-fill {status_class}" style="width: {utilization_capped}%"></div>
                </div>
                <div class="stat-label" style="margin-top:5px">{hours_running}h / {hours_available}h</div>
            </div>"""

TABLE_ROW_TEMPLATE = """                <tr>
                    <td><strong>{machine_id}</strong><br><small>{machine_name}</small></td>
                    <td>{utilization}%</td>
                    <td>{hours_running}h</td>
                    <td>{hours_available}h</td>
                    <td><span class="status-badge status-{status_lower}">{status}</span></td>
                </tr>"""


# ── Helper Functions ─────────────────────────────────────────────────────────

def get_status_class(status):
    """Map status to CSS class."""
    return {
        "GREEN": "green",
        "YELLOW": "yellow",
        "RED": "red",
        "OFFLINE": "gray",
        "NO DATA": "gray",
    }.get(status, "gray")


def load_email_config():
    """Load email configuration from JSON file."""
    if not EMAIL_CONFIG_PATH.exists():
        return None

    with open(EMAIL_CONFIG_PATH) as f:
        config = json.load(f)

    # Check if configured
    if not config.get("smtp_server") or not config.get("to_addresses"):
        return None

    return config


def image_to_base64(image_path):
    """Convert image to base64 data URI for embedding."""
    if not Path(image_path).exists():
        return ""

    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")

    return f'<img src="data:{mime};base64,{data}" alt="Chart">'


def image_to_cid(image_path, cid_name):
    """Return img tag with CID reference for email embedding."""
    if not Path(image_path).exists():
        return ""
    return f'<img src="cid:{cid_name}" alt="Chart">'


def find_dropbox_reports_dir():
    """Find the Dropbox reports directory."""
    for path in [DROPBOX_REPORTS_DIR, DROPBOX_REPORTS_DIR_ALT]:
        if path.parent.exists():
            path.mkdir(parents=True, exist_ok=True)
            return path
    # Fallback to local
    local = SCRIPT_DIR / "reports"
    local.mkdir(exist_ok=True)
    return local


# ── Report Generation ────────────────────────────────────────────────────────

def run_generate_report(start_date=None, end_date=None):
    """Run generate_report.py to create fresh data and charts."""
    print("Running generate_report.py...")

    cmd = [str(PYTHON_EXE), str(SCRIPT_DIR / "generate_report.py")]
    if start_date and end_date:
        cmd.extend([start_date, end_date])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPT_DIR))

    if result.returncode != 0:
        print(f"Warning: generate_report.py returned code {result.returncode}")
        print(result.stderr)
    else:
        print("Report data generated successfully.")


def load_report_data():
    """Load the generated report data."""
    json_path = REPORT_ASSETS_DIR / "report_data.json"
    if not json_path.exists():
        print(f"ERROR: Report data not found at {json_path}")
        print("Run generate_report.py first.")
        sys.exit(1)

    with open(json_path) as f:
        return json.load(f)


def generate_html_report(data, embed_images=True):
    """Generate HTML report from data."""

    # Machine cards
    machine_cards = []
    for mid, stats in sorted(data["machines"].items()):
        card = MACHINE_CARD_TEMPLATE.format(
            machine_id=mid,
            machine_name=stats["name"],
            utilization=stats["utilization_pct"],
            utilization_capped=min(stats["utilization_pct"], 100),
            hours_running=stats["hours_running"],
            hours_available=stats["hours_available"],
            status_class=get_status_class(stats["status"]),
        )
        machine_cards.append(card)

    # Table rows
    table_rows = []
    for mid, stats in sorted(data["machines"].items()):
        row = TABLE_ROW_TEMPLATE.format(
            machine_id=mid,
            machine_name=stats["name"],
            utilization=stats["utilization_pct"],
            hours_running=stats["hours_running"],
            hours_available=stats["hours_available"],
            status=stats["status"],
            status_lower=stats["status"].lower().replace(" ", "-"),
        )
        table_rows.append(row)

    # Charts
    if embed_images:
        bar_chart = image_to_base64(REPORT_ASSETS_DIR / "utilization_bar.png")
        trend_chart = image_to_base64(REPORT_ASSETS_DIR / "utilization_trend.png")
        hours_chart = image_to_base64(REPORT_ASSETS_DIR / "hours_breakdown.png")
    else:
        # Use CID references for email
        bar_chart = image_to_cid(REPORT_ASSETS_DIR / "utilization_bar.png", "bar_chart")
        trend_chart = image_to_cid(REPORT_ASSETS_DIR / "utilization_trend.png", "trend_chart")
        hours_chart = image_to_cid(REPORT_ASSETS_DIR / "hours_breakdown.png", "hours_chart")

    # Parse report time
    try:
        report_dt = datetime.fromisoformat(data["report_generated"])
        report_time = report_dt.strftime("%B %d, %Y at %I:%M %p")
    except:
        report_time = data["report_generated"]

    # Fill template
    html = HTML_TEMPLATE.format(
        date_range=f"{data['date_start']} to {data['date_end']}",
        date_start=data["date_start"],
        date_end=data["date_end"],
        num_days=data["num_days"],
        days_plural="s" if data["num_days"] != 1 else "",
        shift_hours=data["shift_hours"],
        report_time=report_time,
        shop_avg=data["shop_avg_utilization"],
        active_count=data["active_machine_count"],
        total_count=data["total_machine_count"],
        total_running=data["total_hours_running"],
        total_available=data["total_hours_available"],
        machine_cards="\n".join(machine_cards),
        table_rows="\n".join(table_rows),
        bar_chart=bar_chart,
        trend_chart=trend_chart,
        hours_chart=hours_chart,
    )

    return html


# ── Email Sending ────────────────────────────────────────────────────────────

def send_email(html_content, data, config):
    """Send report via email with embedded images."""
    print("\nSending email...")

    # Create message
    msg = MIMEMultipart("related")
    msg["Subject"] = f"{config['subject_prefix']} - {data['date_start']} to {data['date_end']}"
    msg["From"] = config["from_address"]
    msg["To"] = ", ".join(config["to_addresses"])

    # Attach HTML (with CID references)
    html_for_email = generate_html_report(data, embed_images=False)
    msg_alt = MIMEMultipart("alternative")
    msg_alt.attach(MIMEText(html_for_email, "html"))
    msg.attach(msg_alt)

    # Attach images
    images = [
        ("utilization_bar.png", "bar_chart"),
        ("utilization_trend.png", "trend_chart"),
        ("hours_breakdown.png", "hours_chart"),
    ]

    for filename, cid in images:
        img_path = REPORT_ASSETS_DIR / filename
        if img_path.exists():
            with open(img_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-ID", f"<{cid}>")
                img.add_header("Content-Disposition", "inline", filename=filename)
                msg.attach(img)

    # Send
    try:
        if config["smtp_port"] == 465:
            # SSL
            server = smtplib.SMTP_SSL(config["smtp_server"], config["smtp_port"])
        else:
            # TLS
            server = smtplib.SMTP(config["smtp_server"], config["smtp_port"])
            server.starttls()

        if config.get("username") and config.get("password"):
            server.login(config["username"], config["password"])

        server.sendmail(
            config["from_address"],
            config["to_addresses"],
            msg.as_string()
        )
        server.quit()

        print(f"Email sent successfully to: {', '.join(config['to_addresses'])}")
        return True

    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("FASData Daily Report Generator")
    print("=" * 60)

    # Parse arguments
    args = sys.argv[1:]
    skip_email = "--no-email" in args
    args = [a for a in args if not a.startswith("--")]

    start_date = args[0] if len(args) > 0 else None
    end_date = args[1] if len(args) > 1 else None

    # Run report generator
    run_generate_report(start_date, end_date)

    # Load data
    data = load_report_data()
    print(f"\nReport period: {data['date_start']} to {data['date_end']}")
    print(f"Shop average utilization: {data['shop_avg_utilization']}%")

    # Generate HTML
    print("\nGenerating HTML report...")
    html = generate_html_report(data, embed_images=True)

    # Save to Dropbox
    reports_dir = find_dropbox_reports_dir()
    filename = f"utilization_{data['date_end']}.html"
    html_path = reports_dir / filename

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved HTML report: {html_path}")

    # Also save a "latest" copy
    latest_path = reports_dir / "utilization_latest.html"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved latest copy: {latest_path}")

    # Send email if configured
    if not skip_email:
        email_config = load_email_config()
        if email_config:
            send_email(html, data, email_config)
        else:
            print("\nEmail not configured. Edit email_config.json to enable.")
            print("Report is available at:")
            print(f"  {html_path}")
    else:
        print("\nSkipping email (--no-email flag)")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
