# FASData Utilization Report System

**Project:** 12. FASData Implementation — Reporting Module  
**Location:** `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\`  
**Last Updated:** 2026-02-04  
**Status:** Operational — collecting data, reports generating

---

## Overview

Automated CNC machine utilization reporting system for Traxis Manufacturing. Reads FOCAS-collected machine data from SQLite, calculates utilization metrics (cutting vs spindle-only vs idle), generates charts and reports, and publishes to Dropbox for shop-wide access.

**Key distinction:** Utilization = actual cutting time only. Spindle warmup and air spinning are tracked separately and do not count toward utilization targets.

---

## Architecture

```
FANUC CNC Machines (5 active)
        │
        │ FOCAS protocol, polled every 60 seconds
        ▼
Collector PC (WrkStationC)
├── FocasMonitor.exe (Windows service, auto-start)
├── C:\FASData\monitoring.db (live SQLite database)
└── sync-fasdata.bat (hourly copy to Dropbox)
        │
        │ Dropbox sync
        ▼
D:\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db
        │
        │ Scheduled task, daily at 7 PM
        ▼
generate_report.py
├── Queries database
├── Calculates utilization (cutting vs spindle-only)
├── Generates PNG charts (matplotlib)
├── Generates HTML dashboard (self-contained, tiled for 1440x900)
├── Saves JSON data for Word report builder
└── Publishes to Dropbox reports folder
        │
        ▼
Dropbox\...\FASData\reports\
├── utilization_latest.html  ← Display PC opens this
└── utilization_2026-02-04.html  ← Dated archive
```

---

## Machines Monitored

| ID | Machine | IP | Port | Control | Status |
|----|---------|-----|------|---------|--------|
| T2 | YCM NTC1600LY (lathe) | 10.1.1.82 | 8193 | 0i-TF | Active |
| M2 | FANUC Mill 2 | 10.1.1.72 | 8193 | — | Active |
| M3 | FANUC Mill 3 | — | 8193 | — | Offline (ethernet adapter failed) |
| M6 | FANUC Mill 6 | 10.1.1.192 | 8193 | — | Active |
| M8 | FANUC Mill 8 | 10.1.1.202 | 8193 | — | Active |

Robodrills M4, M5, M7 not yet connected to network.

---

## Utilization Calculation

### What Counts as "Cutting" (utilization)

A sample counts as cutting if ALL of:
- Machine is connected
- Spindle speed > 0 OR run_status is STRT/MSTR
- AND at least one of: motion status is MOTION/DWL, or feed_rate > 0

### What Counts as "Spindle Only" (not utilization)

Spindle is running but no axis motion and no feed rate. This captures:
- Warmup cycles
- Air spinning between cuts
- Tool change dwells
- Probing (depending on machine)

### Thresholds

| Status | Cutting % |
|--------|-----------|
| Green (on target) | ≥ 70% |
| Yellow (below target) | 50–69% |
| Red (critical) | < 50% |

### Shift Hours

6:00 AM – 7:00 PM, Monday–Friday. Samples outside shift hours are excluded from calculations.

---

## Data Collected Per Sample

The collector records these fields every 60 seconds per machine:

| Field | Type | Used In Report | Notes |
|-------|------|----------------|-------|
| timestamp | TEXT | ✅ | ISO 8601 format |
| machine_id | TEXT | ✅ | T2, M2, M3, M6, M8 |
| machine_name | TEXT | ✅ | Human-readable name |
| connected | INTEGER | ✅ | 1 = connected, 0 = offline |
| error_message | TEXT | — | Connection error text |
| mode | TEXT | Future | MEM, MDI, JOG, EDIT, HANDLE |
| run_status | TEXT | ✅ | STRT, STOP, HOLD, MSTR |
| motion | TEXT | ✅ | MOTION, DWL, or null |
| program_number | INTEGER | Future | Current program number |
| main_program | INTEGER | Future | Main program number |
| spindle_speed | INTEGER | ✅ | RPM |
| feed_rate | INTEGER | ✅ | mm/min or in/min |
| spindle_override | INTEGER | Future | Percentage (0–200) |
| feedrate_override | INTEGER | Future | Percentage (0–200) |
| emergency | INTEGER | Future | E-stop status |
| alarm | INTEGER | Future | Alarm code |
| alarm_message | TEXT | Future | Alarm description |
| axis_x | INTEGER | Future | Position (÷1000 for mm) |
| axis_y | INTEGER | Future | Position (÷1000 for mm) |
| axis_z | INTEGER | Future | Position (÷1000 for mm) |

---

## Files

### Report Generator

| File | Language | Purpose |
|------|----------|---------|
| `generate_report.py` | Python 3.14 | Queries database, calculates metrics, generates charts + HTML dashboard |
| `build_report.js` | Node.js | Builds formatted Word document from JSON + chart PNGs |
| `run_report.bat` | Batch | One-click: runs Python → opens HTML report |

### Dependencies

| Tool | Package | Install Command |
|------|---------|-----------------|
| Python 3.14 | matplotlib | `py -m pip install matplotlib` |
| Node.js | docx | `npm install docx` (in project folder) |

### Python Executable Path

```
C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe
```

⚠️ The system `python` command may resolve to a different version. Always use the full path or `py` launcher.

### Output Files

| File | Location | Purpose |
|------|----------|---------|
| `utilization_report.html` | Project folder | Local copy, opened by bat file |
| `utilization_latest.html` | Dropbox `..\FASData\reports\` | Always-current, for display PC |
| `utilization_YYYY-MM-DD.html` | Dropbox `..\FASData\reports\` | Dated archive |
| `FASData_Utilization_Report.docx` | Project folder | Formal Word report (requires Node.js step) |
| `report_assets/report_data.json` | Project folder | Raw analysis data |
| `report_assets/utilization_bar.png` | Project folder | Bar chart image |
| `report_assets/utilization_trend.png` | Project folder | Daily trend chart |
| `report_assets/hours_breakdown.png` | Project folder | Hours stacked bar chart |

---

## Usage

### One-Click Report (HTML)

Double-click `run_report.bat`. It:
1. Finds the database in Dropbox automatically
2. Queries all data (or specify date range)
3. Generates charts and HTML dashboard
4. Saves HTML to Dropbox for all PCs
5. Opens the report in your browser

### Word Document Report

For formal reports (monthly reviews, presentations):

```
run_report.bat
node build_report.js
```

### Custom Date Range

```
run_report.bat monitoring.db 2026-01-27 2026-01-31
```

### Scheduled Daily Report

Run in admin PowerShell on main PC:

```
schtasks /create /tn "FASData Daily Report" /tr "\"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe\" \"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\generate_report.py\"" /sc daily /st 19:00
```

This generates the HTML report at 7 PM daily and pushes it to Dropbox.

---

## Shop Floor Display

### Setup

A spare PC with Dropbox installed shows the dashboard on a dedicated monitor.

1. Open in browser: `C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports\utilization_latest.html`
2. Press F11 for full-screen
3. The page auto-refreshes every 5 minutes

### Display Layout (1440×900)

Tiled dashboard, no scrolling:
- **Left column:** Shop metrics (utilization %, cutting hours, available hours, active machines) + per-machine status cards with color coding
- **Top right:** Utilization bar chart (stacked: cutting + spindle-only)
- **Top far right:** Hours breakdown chart (cutting + spindle-only + idle)
- **Bottom right:** Daily trend lines (spans full width)

Dark theme for wall display readability.

### Smart Plug (Recommended)

Use a TP-Link Kasa or Amazon smart plug on the monitor to schedule power on/off (e.g., 5:45 AM on, 7:15 PM off). The PC stays on 24/7 with the browser running.

---

## Database Locations (Auto-Detected)

The report generator checks these paths in order:

1. `D:\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db` (main PC)
2. `C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db` (collector PC)
3. `./monitoring.db` (local fallback)

Dropbox report output paths checked:

1. `D:\Dropbox\MACHINE COMM Traxis\FASData\reports\` (main PC)
2. `C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\FASData\reports\` (collector PC)
3. `C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports\` (display PC)

---

## ProShop Integration Findings

### Messaging API (Investigated 2026-02-04)

ProShop's GraphQL API exposes messaging types (`Message`, `MessageTo`, `MessageFilter`, `UserInboxType`) with `message` and `messages` queries — but **no mutations exist to send messages**. The API is read-only for messaging.

### Email Delivery (Ready, Not Configured)

`send_daily_report.py` (built by Claude Code) supports SMTP email delivery. Configure `email_config.json`:

```json
{
  "smtp_server": "",
  "smtp_port": 587,
  "username": "",
  "password": "",
  "from_address": "",
  "to_addresses": [],
  "subject_prefix": "FASData Daily Report"
}
```

Run with `--no-email` flag to skip email and just generate reports.

---

## Future Possibilities

Data already collected supports these analyses without any collector changes:

### Ready to Build
- **Auto vs manual time** — MEM mode = running program, MDI/JOG/HANDLE = manual
- **Idle gap detection** — flag machines idle >15 min during shift
- **Override tracking** — feedrate/spindle override % patterns per machine
- **Alarm frequency report** — which machines alarm most, what codes, recovery time
- **E-stop tracking** — emergency stop frequency
- **Program run logging** — which programs run where, for how long
- **Shift heatmap** — hour-by-hour utilization grid
- **Monday/Friday vs mid-week** — quantify staffing impact

### Requires Additional Data
- **Operator-to-machine mapping** — needs ProShop login or badge system
- **Job costing** — needs work order integration
- **OEE** — needs scrap/NCR data from ProShop

---

## Troubleshooting

### Report fails: "No database found"
- Check that Dropbox has synced `monitoring.db`
- Verify the file exists at one of the auto-detected paths
- Pass the path explicitly: `run_report.bat D:\path\to\monitoring.db`

### Python errors: "No module named matplotlib"
```
"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe" -m pip install matplotlib
```

### Node.js errors: "Cannot find module docx"
```
cd "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation"
npm install docx
```

### Word report won't build but HTML works fine
The Word report requires Node.js + docx package. The HTML report only needs Python. For daily use, the HTML report is preferred.

### Display PC shows stale data
- Verify Dropbox is syncing on the display PC
- Check that the scheduled task is running on the main PC: `schtasks /query /tn "FASData Daily Report"`
- Manually run `run_report.bat` to force a refresh

### Cutting % seems too low
The cutting calculation requires motion OR feed_rate to be active in addition to spindle running. Machines that spend significant time on spindle warmup, probing, or dwelling between cuts will show lower cutting % than total spindle time. This is by design — it shows actual chip-making time.

---

## Version History

| Date | Change |
|------|--------|
| 2026-02-03 | Initial report generator (Python + Node.js → Word doc) |
| 2026-02-04 | Added cutting vs spindle-only distinction |
| 2026-02-04 | Utilization status based on cutting % only |
| 2026-02-04 | Added HTML dashboard output with tiled layout |
| 2026-02-04 | Auto-save to Dropbox (latest + dated archive) |
| 2026-02-04 | One-click bat file (no Node.js required for HTML) |
| 2026-02-04 | ProShop messaging API investigated — read-only, no send capability |
| 2026-02-04 | Email delivery script created (send_daily_report.py) |
