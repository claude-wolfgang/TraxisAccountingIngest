# Traxis Services Architecture

## Overview
Three Flask-based dashboards + one Windows Service, managed by the Overseer.
All services bind to `0.0.0.0` — accessible from any LAN machine at `10.1.1.71`.

## Network Endpoints

| Service | Port | URL | Type |
|---------|------|-----|------|
| Time Tracker Dashboard | 8050 | http://10.1.1.71:8050 | Flask (process) |
| Service Overseer | 8060 | http://10.1.1.71:8060 | Flask (process) |
| FASData Live Dashboard | 8070 | http://10.1.1.71:8070 | Flask (process) |
| FocasMonitor | — | No HTTP endpoint | Windows Service |

## Service Details

### Time Tracker Dashboard (port 8050)
- **File:** `TimeTrackerDashboard/time_status_display_v1.0.py`
- **Purpose:** Live employee clock-in/time-tracking status from ProShop API
- **Data source:** ProShop GraphQL API (OAuth2 client credentials)
- **Credentials:** `.env` in TimeTrackerDashboard dir (client `B769-88F7-A69B`)
- **API endpoint:** `/api/status` — returns employee list, clock/tracking status
- **Known issue:** `requests.Session` goes stale after ~12 hours under pythonw.exe. Overseer auto-restarts on degraded.

### FocasMonitor (Windows Service)
- **Install location:** `C:\FocasMonitor\`
- **Service name:** `FocasMonitor` (via `sc query FocasMonitor`)
- **Purpose:** Polls CNC machines via FOCAS protocol (port 8193) every 60 seconds
- **Data store:** `C:\FASData\monitoring.db` (SQLite)
- **Machines polled:** T2, M2, M3, M4, M5, M6, M7, M8 (config in `C:\FocasMonitor\machines.json`)
- **Active machines** (have Ethernet): T2, M3, M6 (M2, M8 show connected=0)
- **Install script:** `C:\FocasMonitor\Install-Service-TRAXIS.bat` (requires admin/UAC)
- **Auto-start:** Managed by Windows (Automatic startup type)
- **Failure recovery:** Configured via `sc failure FocasMonitor reset=86400 actions=restart/60000/restart/60000/restart/120000`
- **Migrated from:** WrkStationC (Feb 19, 2026) — was never installed as a service there, only manual test runs

### FASData Live Dashboard (port 8070)
- **File:** `FASDataDashboard/fasdata_live.py`
- **HTML:** `FASDataDashboard/fasdata_dashboard.html` (Aztec-themed, 1920x1080 kiosk layout)
- **Purpose:** Live CNC machine utilization dashboard for shop floor display
- **Data source:** `C:\FASData\monitoring.db` (read-only, same DB as FocasMonitor)
- **API endpoint:** `/api/status` — returns per-machine utilization, status, shop average
- **Replaces:** Static HTML pipeline from Project 12 (generate_report.py → generate_dashboard.py → Dropbox sync)
- **Shift hours:** 6 AM - 7 PM, Mon-Fri
- **Utilization thresholds:** GREEN >= 30%, YELLOW >= 10%, RED < 10%

#### FOCAS Data Interpretation
- **spindle_speed 131072 (0x20000)** is a FOCAS flag/error code, NOT real RPM. Filtered via `SPINDLE_SPEED_MAX_VALID = 100000`
- **Cutting classification** (two-tier, matching original generate_report.py):
  - **Running:** `run_status IN ('STRT','MSTR') OR (0 < spindle_speed < 100000)`
  - **Cutting:** running AND (`motion IN ('MTN','DWL','MOTION') OR feed_rate > 0`)
- **Motion codes:** `MTN` = axis motion, `DWL` = dwell, `***` = no motion (idle)
- **Run status codes:** `STRT` = program running, `MSTR` = spindle master, `STOP` = stopped, `***` = idle

### Service Overseer (port 8060)
- **File:** `Overseer/overseer.py` (v1.2)
- **HTML:** `Overseer/overseer.html`
- **Purpose:** Monitors all services, auto-restarts on failure, provides status dashboard
- **Check interval:** 60 seconds
- **Startup grace:** 30 seconds (new processes get grace period before health checks)
- **Event log:** Keeps last 200 events in memory

#### Managed Services Config
| Service | Type | Health Check | Auto-Start | Max Failures | Restart Cooldown |
|---------|------|-------------|------------|-------------|-----------------|
| TimeTrackerDashboard | process | HTTP GET :8050/api/status | Yes | 3 | 300s |
| FocasMonitor | windows_service | sc query + SQLite freshness | No (Windows manages) | 3 | 300s |
| FASDataDashboard | process | HTTP GET :8070/api/status | Yes | 3 | 300s |

#### Health Validators
- **TimeTrackerDashboard:** Checks employee count (>0 during business hours), data staleness (<300s), API errors
- **FocasMonitor:** Checks Windows service running + SQLite sample freshness (<180s per machine)
- **FASDataDashboard:** Checks machine count, online count, API errors

#### Launcher Scripts
- `Overseer/run_overseer.bat` — console mode (shows log output)
- `Overseer/run_overseer_silent.vbs` — silent mode (pythonw.exe, no console window)

## Data Flow

```
CNC Machines (T2, M2, M3, M6, M8)
    │ FOCAS protocol (port 8193, 60s polling)
    ▼
FocasMonitor (Windows Service)
    │ writes to
    ▼
C:\FASData\monitoring.db (SQLite)
    │ read-only
    ▼
FASData Live Dashboard (Flask :8070)
    │ serves
    ▼
Browser at http://10.1.1.71:8070

ProShop ERP API (GraphQL)
    │ OAuth2 + polling
    ▼
Time Tracker Dashboard (Flask :8050)
    │ serves
    ▼
Browser at http://10.1.1.71:8050

All services
    │ health checks (60s)
    ▼
Service Overseer (Flask :8060)
    │ serves
    ▼
Browser at http://10.1.1.71:8060
```

## Python Environment
- **Primary:** `C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\` (python.exe / pythonw.exe)
  - Flask installed, used by overseer's `PYTHONW_EXE` for managed process services
- **Secondary:** `C:\Users\TRAXIS\AppData\Local\Python\pythoncore-3.14-64\` (Windows Store variant)
  - Also has Flask installed
- **Git bash `python`:** Maps to `C:\Users\TRAXIS\AppData\Local\Microsoft\WindowsApps\python.exe` (store stub)
  - Flask installed here too
- **Recommendation:** Always use full path or `py` launcher to avoid ambiguity

## Windows Firewall
Ports 8050, 8060, 8070 must be allowed inbound for LAN access.
If a remote machine can't connect, check: `netsh advfirewall firewall show rule name=all | findstr "8050\|8060\|8070"`

## Startup Sequence
1. Windows boots → FocasMonitor auto-starts (Windows Service)
2. User login → run Overseer (manually or via Startup folder)
3. Overseer auto-starts TimeTrackerDashboard and FASDataDashboard
4. Overseer adopts existing processes if already running (checks port)
5. Overseer begins 60s health check loop after 30s grace period
