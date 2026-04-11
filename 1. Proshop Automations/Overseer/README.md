# Traxis Service Overseer

Watchdog process manager for Traxis shop floor automation services. Keeps services alive (auto-restart on crash or degraded health) and provides a real-time status dashboard.

## What It Does

- Checks each managed service every 60 seconds
- Auto-restarts services that crash or stay unhealthy too long
- Serves a web dashboard at `http://localhost:8060` with live status, action buttons, and an event log

## Managed Services

| Service | Type | Port | What It Does |
|---------|------|------|-------------|
| TimeTrackerDashboard | Python process | 8050 | Employee programming time tracking display |
| FocasMonitor | Windows Service | — | CNC machine data collection via FOCAS (5 machines) |
| FASDataDashboard | Python process | 8070 | Live CNC machine utilization display |

## How It Runs

- **On boot:** Windows Startup shortcut runs `run_overseer_silent.vbs` which launches `overseer.py` via `pythonw.exe` (no console window)
- **Manual/debug:** Run `run_overseer.bat` to see console output
- **Dashboard:** Open `http://localhost:8060` in a browser

## Configuration

All configuration lives at the top of `overseer.py` (lines 63-129).

### Business Hours

```python
BUSINESS_HOURS_START = (5, 15)   # (hour, minute) — 5:15 AM
BUSINESS_HOURS_END = (18, 0)     # (hour, minute) — 6:00 PM
BUSINESS_DAYS = range(0, 5)      # Monday (0) through Friday (4)
```

**What this controls:** During business hours, stricter health standards apply. For example, TimeTrackerDashboard reporting "no employees" is flagged as degraded during business hours but ignored off-hours. FocasMonitor with all machines stale is "down" during business hours but only "degraded" off-hours.

**To change:** Edit the `(hour, minute)` tuples in `overseer.py`. Examples:
- `(6, 0)` = 6:00 AM
- `(5, 30)` = 5:30 AM
- `(7, 45)` = 7:45 AM

For days, `range(0, 5)` is Mon-Fri. Use `range(0, 6)` to include Saturday, `range(0, 7)` for every day.

### Service Definitions

Each service in `SERVICES_CONFIG` has:

| Setting | What It Does |
|---------|-------------|
| `auto_start` | Whether Overseer launches it on startup (False for Windows Services) |
| `health_url` | HTTP endpoint to poll (None for database-checked services) |
| `restart_cooldown` | Minimum seconds between restart attempts (default 300 = 5 min) |
| `max_failures` | Consecutive failed checks before auto-restart (default 3) |
| `max_degraded` | Consecutive degraded checks before auto-restart (5 or 10) |

### General

| Setting | Value | What It Does |
|---------|-------|-------------|
| `PORT` | 8060 | Dashboard web server port |
| `CHECK_INTERVAL` | 60 | Seconds between health checks |
| `STARTUP_GRACE` | 30 | Seconds to wait after starting a service before checking health |

## Dependencies

```
pip install flask requests
```

## Files

| File | Purpose |
|------|---------|
| `overseer.py` | Main application (Flask server + health monitor + auto-restart) |
| `overseer.html` | Dashboard UI |
| `run_overseer.bat` | Manual launcher (console visible) |
| `run_overseer_silent.vbs` | Silent launcher for Windows Startup |
| `overseer.log` | Rolling log of health checks, restarts, errors |

## Known Issues

- FocasMonitor `sc start`/`sc stop` requires admin privileges — Overseer can detect problems but can't restart the Windows Service without elevation
- TimeTrackerDashboard may trigger a restart at business hours start if no one has clocked in yet
