# 12. FASData Project Update
**Traxis Manufacturing — CNC Machine Utilization Monitoring**  
**Project:** 12. FASData Implementation  
**Date:** February 6, 2026 (Updated)

---

## Project Status: ✅ Operational

The FASData system is live and actively monitoring CNC machine utilization across the shop floor. Shop floor display is running on a 32" TV with an Aztec-themed dashboard.

---

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  CNC Machines   │────▶│  Collector PC   │────▶│    Dropbox      │
│  (FOCAS2)       │     │  (WrkStationC)  │     │  (Sync hourly)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │ Polling every 60 sec                          │ Syncs to all PCs
        │                                               │
        ▼                                               ▼
┌─────────────────┐                     ┌───────────────────────────────┐
│  monitoring.db  │                     │         Main PC (TRAXIS)      │
│  (SQLite)       │                     │  • generate_report.py (5 min) │
└─────────────────┘                     │  • generate_dashboard.py      │
                                        │  • send_daily_report.py (7PM) │
                                        └───────────────────────────────┘
                                                        │
                                                        ▼
                                        ┌───────────────────────────────┐
                                        │      Display PC (traxi)       │
                                        │  • 32" Samsung TV (1080p)     │
                                        │  • Aztec-themed dashboard     │
                                        │  • Auto-refresh every 5 min   │
                                        └───────────────────────────────┘
```

---

## Current Machine Status

| ID | Machine | IP Address | Status | Current Util | Notes |
|----|---------|------------|--------|--------------|-------|
| T2 | YCM NTC1600LY (Lathe) | 10.1.1.82 | ✅ Active | 1.7% | FOCAS working |
| M2 | FANUC Mill 2 | 10.1.1.159 | ✅ Active | 7.4% | FOCAS working |
| M3 | FANUC Mill 3 | 10.1.1.118 | ⚠️ Degraded | 0.4% | Ethernet adapter issue |
| M6 | FANUC Mill 6 | 10.1.1.106 | ✅ Active | 17.2% | FOCAS working |
| M8 | FANUC Mill 8 | 10.1.1.202 | ✅ Active | 68.3% | Best performer |
| M4 | Robodrill 4 | — | ❌ Not Connected | — | Needs Ethernet |
| M5 | Robodrill 5 | — | ❌ Not Connected | — | Needs Ethernet |
| M7 | Robodrill 7 | — | ❌ Not Connected | — | Needs Ethernet |
| M1 | Haas Classic | — | ❌ Incompatible | — | Not FOCAS |

**Shop Average:** 13.0%  
**Cutting Hours:** 28.7h / 220.0h available  
**Active Machines:** 5 of 5 monitored

---

## Utilization Thresholds

| Status | Threshold | Color |
|--------|-----------|-------|
| On Target | ≥ 30% | 🟢 Green |
| Below Target | 10% – 29% | 🟡 Yellow |
| Critical | < 10% | 🔴 Red |
| Offline | No data | ⚫ Gray |

---

## Shop Floor Dashboard

**Hardware:**
- Display: 32" Samsung TV (1080p)
- Connected to: Display PC (user: traxi)
- Recommended: Smart plug for on/off scheduling

**Design:**
- Aztec/Mesoamerican industrial theme
- Obsidian black background
- Terracotta, jade, turquoise accents
- Large gauges readable from 20+ feet
- Auto-refresh every 5 minutes

**Screenshot:**
![Dashboard](IMG_2966.JPG)

---

## Scheduled Tasks

| Task Name | Schedule | Script | Wrapper |
|-----------|----------|--------|---------|
| FASData Report Refresh | Every 5 min | `generate_report.py` | `run_report_hidden.vbs` |
| FASData Dashboard | Hourly | `generate_dashboard.py` | `run_dashboard_hidden.vbs` |
| FASData Daily Report | 7:00 PM | `send_daily_report.py` | `run_daily_report_hidden.vbs` |
| FASData Sync | Hourly | `sync-fasdata.bat` | (on collector PC) |

**Note:** All tasks use VBScript wrappers to run hidden (no popup windows).

---

## File Locations

### Main PC (TRAXIS)
```
D:\Dropbox\MACHINE COMM Traxis\
├── FASData\
│   ├── monitoring.db                  ← Synced database
│   ├── sync.log
│   └── reports\
│       ├── dashboard.html             ← Shop floor display
│       ├── utilization_latest.html
│       └── utilization_YYYY-MM-DD.html
│
└── Proshop Automation and Claude Projects\
    └── 12. FASData Implementation\
        ├── generate_report.py         ← Data analysis + charts
        ├── generate_dashboard.py      ← Dashboard HTML generator
        ├── send_daily_report.py       ← Daily email/HTML report
        ├── build_report.js            ← Word document builder
        ├── run_report.bat             ← Manual report runner
        ├── start_display.bat          ← Kiosk launcher
        ├── run_report_hidden.vbs      ← Hidden task wrapper
        ├── run_dashboard_hidden.vbs   ← Hidden task wrapper
        ├── run_daily_report_hidden.vbs← Hidden task wrapper
        ├── email_config.json          ← SMTP settings (blank)
        ├── FASData System Reference.md
        └── node_modules/              ← Node.js dependencies
```

### Collector PC (WrkStationC)
```
C:\FocasMonitor\
├── FocasMonitor.exe                   ← Windows service
├── machines.json                      ← Machine config
└── (FOCAS DLLs)

C:\FASData\
├── monitoring.db                      ← Live database
├── sync-fasdata.bat                   ← Hourly sync to Dropbox
└── logs\
```

### Display PC (traxi)
```
C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports\
└── dashboard.html                     ← Displayed in kiosk browser
```

---

## ProShop API Status

**Finding:** ProShop GraphQL API has messaging types (`Message`, `MessageTo`, `MessageFilter`) but they are **read-only**. Cannot send automated notifications via ProShop.

**Alternative:** Daily reports delivered via:
- HTML files in shared Dropbox folder
- Email (when configured)
- Shop floor display

---

## Technical Details

### FOCAS Configuration
- Library: `github.com/strangesast/fwlib`
- Port: 8193
- Compatible: 0i-TF, 0i-MF, 0i-MC, 16i

### Utilization Formula
```
Utilization % = (samples where spindle_speed > 0 OR run_status in ['STRT','MSTR']) 
                / total_samples_during_shift × 100

Shift hours: 6:00 AM – 7:00 PM, Monday–Friday
```

### Python Environment
```
Path: C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe
Packages: matplotlib, requests
```

---

## Observations

**M8 is significantly outperforming other machines (68% vs <20%).**

Questions to investigate:
- Different operator?
- Different type of work?
- Better tooling/setup?
- More consistent job loading?

**Overall shop utilization is low (13% average).**

Root cause analysis needed:
- Loading problem (not enough work)?
- Efficiency problem (setup time, programming, waiting)?
- Equipment issues?

---

## Next Steps

### Immediate
- [x] Shop floor display operational
- [x] Hidden scheduled tasks (no popups)
- [ ] Configure email delivery (`email_config.json`)
- [ ] Add `start_display.bat` to Windows Startup on display PC
- [ ] Purchase smart plug for display TV

### Hardware
- [ ] Install USB Ethernet adapter on M3
- [ ] Run Ethernet cables to Robodrills (M4, M5, M7)

### Analysis
- [ ] Investigate M8 practices — why 5x better than others?
- [ ] Correlate utilization with operator schedules
- [ ] Identify biggest time sinks (setup? waiting? programming?)

### Future Integration
- [ ] Link ProShop operator logins to utilization data
- [ ] Per-operator productivity metrics
- [ ] Automated alerts for extended downtime

---

*Document updated: February 6, 2026*
