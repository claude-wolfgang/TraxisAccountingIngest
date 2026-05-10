# Claude Code Task: Update FASData Project Documentation

## Task

Update the project reference document with everything built in the February 4-5, 2026 sessions.

## File to Update

```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\FASData System Reference.md
```

If this file doesn't exist, create it.

## What to Document

Add a dated section (2026-02-05) covering the following items that were built:

### 1. Utilization Report Generator

**Files created:**
- `generate_report.py` — Python script that queries monitoring.db, calculates utilization metrics, generates PNG charts, outputs JSON data
- `build_report.js` — Node.js script that consumes JSON + charts and produces a formatted Word document
- `run_report.bat` — Batch wrapper that runs both scripts in sequence
- `send_daily_report.py` — Python script for automated daily report generation with HTML output and optional email delivery
- `email_config.json` — SMTP configuration template (blank, ready for user to fill in)

**Output locations:**
- Word reports: Generated in the project folder
- HTML reports: `D:\Dropbox\MACHINE COMM Traxis\FASData\reports\`
  - `utilization_YYYY-MM-DD.html` — Dated archives
  - `utilization_latest.html` — Always-current version

**Dependencies:**
- Python 3.8+ with matplotlib (`pip install matplotlib`)
- Node.js with docx package (`npm install docx` in project folder)
- Python path on main PC: `C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe`

**Usage:**
```
run_report.bat                                    # auto-finds DB in Dropbox
run_report.bat path\to\monitoring.db              # explicit path
run_report.bat monitoring.db 2026-01-27 2026-01-31  # date range
```

### 2. Utilization Thresholds (Updated)

Previous thresholds (70/50) were too aggressive for current shop capacity. New thresholds:

| Status | Threshold |
|--------|-----------|
| Green (On Target) | ≥ 30% |
| Yellow (Below Target) | 10% – 29% |
| Red (Critical) | < 10% |

Updated in: `generate_report.py`, `build_report.js`, `send_daily_report.py`, `generate_dashboard.py`

### 3. Shop Floor Display Dashboard

**Purpose:** Full-screen utilization display for 32" 1080p TV mounted on shop floor

**Files created:**
- `generate_dashboard.py` — Generates self-contained HTML dashboard with embedded data and Aztec/industrial styling
- `start_display.bat` — Launches browser in kiosk mode on display PC
- `dashboard.html` — Output file (auto-generated, synced via Dropbox)

**Design:**
- Aztec/Mesoamerican industrial theme
- Obsidian black background, terracotta/turquoise/jade accents
- Large gauges readable from 20 feet
- Auto-refreshes every 5 minutes

**Display PC setup:**
- PC user: `traxi`
- Dropbox path: `C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports\dashboard.html`
- Browser: Chrome or Edge in kiosk mode
- Auto-start: Place `start_display.bat` shortcut in Windows Startup folder
- Monitor control: Smart plug recommended for on/off scheduling (6 AM on, 7 PM off)

### 4. Scheduled Tasks

**Daily Report (7 PM):**
```
schtasks /create /tn "FASData Daily Report" /tr "\"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe\" \"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\send_daily_report.py\" --no-email" /sc daily /st 19:00
```

### 5. ProShop API Discovery

**Finding:** ProShop's GraphQL API has messaging types (`Message`, `MessageTo`, `MessageFilter`, `UserInboxType`) but they are READ-ONLY. No mutations exist to send messages via API.

**Files created:**
- `discover_proshop_messaging.py` — API discovery script
- `proshop_api_discovery.json` — Discovery results

**Implication:** Cannot auto-send utilization reports via ProShop messaging. Using email and Dropbox-shared HTML reports instead.

### 6. File Organization

```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\
├── generate_report.py          # Report data + charts generator
├── build_report.js             # Word document builder
├── run_report.bat              # Combined report runner
├── send_daily_report.py        # Daily HTML report + email
├── generate_dashboard.py       # Shop floor dashboard generator
├── start_display.bat           # Kiosk launcher for display PC
├── email_config.json           # SMTP settings (user fills in)
├── node_modules/               # Node.js dependencies
├── package.json
└── FASData System Reference.md # This document

D:\Dropbox\MACHINE COMM Traxis\FASData\
├── monitoring.db               # SQLite database (synced from collector)
├── sync.log                    # Sync timestamps
└── reports/
    ├── dashboard.html          # Shop floor display (auto-generated)
    ├── utilization_latest.html # Current HTML report
    └── utilization_YYYY-MM-DD.html  # Archived reports
```

### 7. Known Issues / Next Steps

- [ ] M3 ethernet adapter replacement — USB adapter on order
- [ ] Connect Robodrills M4, M5, M7 to network
- [ ] Set up email delivery (fill in `email_config.json`)
- [ ] Tie utilization data to ProShop operator logins for per-person metrics
- [ ] Investigate low utilization root causes (loading vs efficiency problem)

---

## Standard CC Task Footer

**Remember:** After completing any future FASData task, update this reference document with what was built/changed.
