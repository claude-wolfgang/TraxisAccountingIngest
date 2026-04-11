# Traxis Claude Code Session — 2026-03-02

## Session Summary

Two tasks completed: a full project inventory across all Traxis automation locations, and documentation + deployment of Project 16 (Fusion Tool Library Auditor).

---

## Task 1: Project Inventory

**Output file:** `PROJECT_INVENTORY_2026-03-02.md`

Scanned four locations and cataloged everything:

### Location 1: Dropbox Project Root
16 numbered projects inventoried with git status, README presence, key tech, version numbers, last-modified dates, and activity status.

| Active Projects | Last Modified |
|----------------|---------------|
| 1. Proshop Automations (Overseer, ProShopBridge, ProgrammingTimer, dashboards) | 2026-03-02 |
| 12. FASData Implementation (focasmonitor, reports, TraxisPostProcessor) | 2026-03-02 |

| Semi-Active Projects | Last Modified |
|---------------------|---------------|
| 4. Inspection Print & ProShop | 2026-02-24 |
| 9. Shop Floor Automations | 2026-02-13 |
| 11. ProShop Mobile App | 2026-02-20 |
| 14. Workstation Display | 2026-02-26 |
| 16. Fusion Tool Library Auditor | 2026-02-28 |

| Dormant/Research Projects | Last Modified |
|--------------------------|---------------|
| 2, 3, 5, 6, 7, 8, 10, 13, 15 | Jan–Feb 2026 |

### Location 2: ProShop Exports
Exists, 17 items, last modified 2026-02-11. Not enumerated.

### Location 3: Fusion 360 AddIns
2 symlinked add-ins found (ProShopBridge v1.4.0, TraxisPostProcessor v1.0.0). ProgrammingTimer and FusionToolAuditor were missing.

### Location 4: Fusion 360 Scripts
2 scripts found (Dump_parameters, GenerateSetupSheet). Both local copies, not symlinked from Dropbox.

### Key Housekeeping Findings
- Only Project 1 has git — 15 other projects have no version control
- `API Projects/` folder is a stale duplicate of several numbered projects
- `Keys/` folder is empty; credentials scattered across .env files
- `nul` file at root is junk (0 bytes)
- TraxisPostProcessor lives in Project 12 but is architecturally unrelated to FASData

---

## Task 2: Project 16 — Document & Deploy

### Step 1: Read & Understand (16 files read)

**FusionToolAuditor/** (Add-in, v1.0.0)
- `FusionToolAuditor.py` (682 lines) — Palette-based UI host, library discovery across Local/Cloud/Fusion360/Document, tool data extraction via JSON and parameter APIs, ProShop GraphQL client (OAuth 2.0, fetches ~900 tools with EDP data), save to Document libraries, JSON export for Cloud/Local workaround
- `palette.html` (581 lines) — Dark-themed table UI with: library dropdown, missing-ID filter, Auto-Extract IDs (regex from descriptions), Lookup by EDP (cross-ref ProShop database), EDP-to-Vendor migration, ProShop search column, Export JSON, Save Changes
- `FusionToolAuditor.manifest` — type: addin, v1.0.0, runOnStartup: false

**ExportToolLibrary/** (Script)
- `ExportToolLibrary.py` (408 lines) — One-shot export of any library to `_full.json` + `_summary.csv` with full geometry/parameter extraction and unit conversion (mm/cm to inches)
- `ExportToolLibrary.manifest` — type: script, no version

**TestScripts/** (3 dev scripts)
- Test1: enumerate library locations and counts
- Test2: read one tool's parameters
- Test3: verify toJson() structure

### Step 2: README.md Created

Wrote `16. Fusion Tool Library Product ID Changer/README.md` covering:
- Problem statement (Product IDs contain EDPs instead of ProShop IDs)
- All 3 components with descriptions
- Installation instructions (symlink commands)
- Step-by-step usage workflows for both Cloud and Document libraries
- ProShop ID format reference
- Known limitations (Cloud/Local libraries read-only via API)
- Dependencies (no external packages)
- File structure tree
- Version history

### Step 3: Symlinks Created

**AddIns folder** (now 3 symlinks):
```
FusionToolAuditor  ->  Project 16/FusionToolAuditor     [NEW]
ProShopBridge      ->  Project 1/ProShopBridge           [existing]
TraxisPostProcessor -> Project 12/TraxisPostProcessor    [existing]
```

**Scripts folder** (now 3 items):
```
ExportToolLibrary  ->  Project 16/ExportToolLibrary      [NEW - symlink]
Dump_parameters                                          [existing - local copy]
GenerateSetupSheet                                       [existing - local copy]
```

Both new symlinks verified working. Fusion 360 was confirmed not running before creation. Temporary .ps1 helper script was cleaned up after use.

---

## Files Created This Session

| File | Type | Location |
|------|------|----------|
| `PROJECT_INVENTORY_2026-03-02.md` | Inventory report | Project root |
| `16.../README.md` | Documentation | Project 16 root |
| `FusionToolAuditor` symlink | Directory symlink | Fusion AddIns folder |
| `ExportToolLibrary` symlink | Directory symlink | Fusion Scripts folder |
| `SESSION_LOG_2026-03-02.md` | This file | Project root |

## Files Modified This Session

None — all actions were either read-only or new file creation.

---

## Task 3: Overseer Deep Dive

Read all 5 files in `1. Proshop Automations/Overseer/` and documented the system.

### What It Is

Overseer (v1.2) is a **watchdog process manager** — a long-running Python/Flask app that keeps Traxis shop floor services alive and provides a real-time status dashboard at `http://localhost:8060`.

### How It Runs

- **Not a Windows Service or scheduled task** — long-running Python process
- Auto-starts on boot via `.lnk` shortcut in Windows Startup folder -> `run_overseer_silent.vbs` -> `pythonw.exe overseer.py` (no console window)
- `run_overseer.bat` is the manual/debug alternative (shows console)
- Dependencies: `flask`, `requests` (pip packages)

### What It Monitors (3 services)

| Service | Type | Port | Health Check | Auto-Start |
|---------|------|------|-------------|------------|
| **TimeTrackerDashboard** | Python process | 8050 | HTTP `/api/status` — validates employee count, clock-ins, data freshness (>5min = stale) | Yes (Overseer launches it) |
| **FocasMonitor** | Windows Service | — | `sc query` + SQLite DB freshness check on `C:\FASData\monitoring.db` — all 5 CNC machines must have samples <3 min old | No (Windows manages startup) |
| **FASDataDashboard** | Python process | 8070 | HTTP `/api/status` — validates machine count and shop utilization average | Yes (Overseer launches it) |

### Auto-Restart Logic

- **3 consecutive failures** (connection refused, HTTP error) -> auto-restart
- **5 consecutive degraded** (TimeTracker/FASData) or **10** (FocasMonitor) -> auto-restart
- **5-minute cooldown** between restart attempts to prevent loops
- **30-second grace period** after startup before first health check
- **Business hours awareness** (Mon-Fri 5:15am-6pm, changed this session from 6am): "no employees" is degraded during business hours, acceptable off-hours

### Dashboard (overseer.html)

Dark-themed web UI with:
- **Overall status badge** — "All Healthy" / "Degraded" / "Issues Detected"
- **Service cards** — status dot (animated green/yellow/red/blue/gray), message, uptime, type, port/PID, last check, restart count, last healthy time
- **Action buttons** — Start / Stop / Restart per service, plus Open button to jump to each service's own UI
- **Event log table** — timestamped history of all health transitions, restarts, errors
- Auto-refreshes every 10 seconds

### Component Interactions

| Overseer manages... | How |
|---------------------|-----|
| **TimeTrackerDashboard** | Starts via `pythonw.exe time_status_display_v1.0.py`, monitors HTTP endpoint, restarts on failure |
| **FASDataDashboard** | Starts via `pythonw.exe fasdata_live.py`, monitors HTTP endpoint, restarts on failure |
| **FocasMonitor** | Monitor-only — checks `sc query` + DB freshness. Can attempt `sc start/stop` but needs admin privileges (log shows "Access is denied" when trying) |

Does **not** interact with ProShopBridge, ProgrammingTimer, or FusionToolAuditor (those are Fusion 360 add-ins managed by Fusion itself).

### What Breaks If Overseer Stops

- **TimeTrackerDashboard** and **FASDataDashboard** won't auto-start on boot and won't be restarted if they crash
- **FocasMonitor** loses oversight — still runs (Windows Service) but nobody notices if data goes stale
- **No status dashboard** — no single view of shop floor health
- **No event history** — no record of outages and restarts

### Evidence From Log (overseer.log)

The log (2026-02-19 through 2026-03-02) shows active watchdog behavior:
- TimeTrackerDashboard auto-restarted almost every weekday at ~6am ("No employees during business hours" triggers degraded -> restart)
- FASDataDashboard auto-restarted 2026-02-26 after HTTP read timeout
- FocasMonitor went down 2026-02-19 at 5pm, auto-restart attempted but failed ("Access is denied" — needs admin)
- FocasMonitor recovered on its own within 3 minutes (likely Windows restarted it)
- Most recent entry: 2026-03-02 08:27 — all 3 services healthy

### Files

| File | Lines | Purpose |
|------|-------|---------|
| `overseer.py` | 719 | Main app: Flask server + ServiceManager + health validators + auto-restart logic |
| `overseer.html` | 420 | Dashboard UI (dark theme, service cards, event log, auto-refresh) |
| `run_overseer.bat` | 17 | Manual launcher (console visible) |
| `run_overseer_silent.vbs` | 2 | Silent launcher via pythonw.exe (used by Startup shortcut) |
| `overseer.log` | 75 | Rolling log of health checks, restarts, errors |

### Known Issues

- FocasMonitor `sc start`/`sc stop` fails without admin privileges — Overseer can detect the problem but can't fix it
- TimeTrackerDashboard triggers a false-alarm restart every weekday at 6am before anyone clocks in (business hours start at 6am but nobody arrives until ~6:15-6:30) — **mitigated this session by moving start to 5:15am**

---

## Task 4: Overseer Config Change + README

### Change 1: Business hours start — 6:00 AM to 5:15 AM (`overseer.py`)

**Lines 74-76, before:**
```python
BUSINESS_HOURS_START = 6
BUSINESS_HOURS_END = 18
BUSINESS_DAYS = range(0, 5)
```

**After:**
```python
BUSINESS_HOURS_START = (5, 15)   # (hour, minute) — 5:15 AM
BUSINESS_HOURS_END = (18, 0)     # (hour, minute) — 6:00 PM
BUSINESS_DAYS = range(0, 5)
```

**Lines 135-138, before:**
```python
def is_business_hours():
    now = datetime.now()
    return now.weekday() in BUSINESS_DAYS and BUSINESS_HOURS_START <= now.hour < BUSINESS_HOURS_END
```

**After:**
```python
def is_business_hours():
    now = datetime.now()
    now_hm = (now.hour, now.minute)
    return now.weekday() in BUSINESS_DAYS and BUSINESS_HOURS_START <= now_hm < BUSINESS_HOURS_END
```

Changed from integer-hour comparison to `(hour, minute)` tuple comparison so business hours can start at non-hour boundaries. This addresses the false-alarm restarts of TimeTrackerDashboard at 6am before employees arrive.

### Change 2: Created `Overseer/README.md`

New file documenting:
- What the Overseer does, managed services, how it runs
- **Configuration section** — business hours setting (what it controls, where to find it, how to change it), service definition settings, general settings
- Dependencies, file listing, known issues

---

## Task 5: ProgrammingTimer Symlink

Created symlink for ProgrammingTimer (v1.1.0) into Fusion AddIns folder on the TRAXIS machine:
```
ProgrammingTimer -> D:\Dropbox\...\1. Proshop Automations\ProgrammingTimer
```

Fusion AddIns folder now has 4 symlinks: ProgrammingTimer, ProShopBridge, FusionToolAuditor, TraxisPostProcessor.

---

## Task 6: Multi-Machine Deployment (Traxis MFG)

Two Fusion programmers, two machines:
- **TRAXIS** (Wolfgang) — Dropbox at `D:\Dropbox\`
- **Traxis MFG** (GRRR) — Dropbox at `C:\Users\Traxis MFG\Dropbox\`

### Updated `setup_fusion_addins.bat`

Rewrote the existing setup script (was outdated — had wrong ProgrammingTimer path, missing FusionToolAuditor and ExportToolLibrary). New version:
- Auto-detects Dropbox path (checks `D:\Dropbox\`, `C:\Users\%USERNAME%\Dropbox\`, `%USERPROFILE%\Dropbox\`)
- Checks for admin privileges and that Fusion is not running
- Creates symlinks for all 4 add-ins + 1 script
- Copies `.traxis.env` credentials to user home folder
- Prompts for programmer name (stored in per-machine local config)
- Lives in Dropbox so it's already synced to both machines

To deploy on Traxis MFG: right-click `setup_fusion_addins.bat` > Run as administrator.

---

## Task 7: ProgrammingTimer Data Review + Programmer Name Fix

### Data Summary

17 sessions logged across 6 days (Feb 15 – Mar 2), ~2h 10min total active programming time. Most-worked part: 10-02004 (ICON Tech, ~1h 14m). Data confirmed arriving from both machines — entry from "InspectionRoom" seat appeared today after setup script ran on Traxis MFG.

### Programmer Name Issue

`timer_config.json` is shared via Dropbox (symlinked add-in folder), so `programmer_name` can't be set per-machine in that file. Was falling back to Windows username, producing inconsistent names ("TRAXIS", "Traxi").

**Fix:** Added local config override support to `config.py`:
1. `timer_config.json` (shared, Dropbox) — base settings, `programmer_name` left blank
2. `%APPDATA%\Traxis\ProgrammingTimer\timer_config.local.json` (per-machine, not synced) — overrides any shared setting

**This machine:**
```
C:\Users\TRAXIS\AppData\Roaming\Traxis\ProgrammingTimer\timer_config.local.json
→ {"programmer_name": "Wolfgang"}
```

**Traxis MFG:** The setup script now prompts for the programmer's name during first run and creates the local config automatically.

---

## Files Created This Session

| File | Type | Location |
|------|------|----------|
| `PROJECT_INVENTORY_2026-03-02.md` | Inventory report | Project root |
| `16.../README.md` | Documentation | Project 16 root |
| `FusionToolAuditor` symlink | Directory symlink | Fusion AddIns folder (TRAXIS) |
| `ExportToolLibrary` symlink | Directory symlink | Fusion Scripts folder (TRAXIS) |
| `ProgrammingTimer` symlink | Directory symlink | Fusion AddIns folder (TRAXIS) |
| `1.../Overseer/README.md` | Documentation | Overseer folder |
| `%APPDATA%\Traxis\ProgrammingTimer\timer_config.local.json` | Per-machine config | TRAXIS machine only |
| `SESSION_LOG_2026-03-02.md` | This file | All Projects Monitoring |

## Task 8: Tampermonkey Badge — Show Only During Push

The "PS Bridge: Active" badge in the Tampermonkey userscript was appearing on **every** ProShop page, even during normal browsing. User wanted it to only appear when the bridge is actively pushing data.

### Changes (`proshop_bridge_tampermonkey.user.js`, v1.2.0 → v1.2.1)

1. **Badge creation deferred** — badge element no longer appended to DOM on page load. Replaced with lazy `ensureBadge()` function called only via `setStatus()`.
2. **Removed badge from non-push paths:**
   - Manual written description browsing (`Active (manual)` status removed)
   - Sequence detail pages (`Sequence Detail` and `Sorted by Seq #` statuses removed)
3. **Badge now only appears** when URL contains `psBridge=` (set by the Python add-in when it opens a page for auto-paste).
4. **Sequence detail features still work silently** — sort by Seq # and T## → G-Code Tool # fix still run, just without showing the badge.

**Note:** Tampermonkey stores its own copy of the script — editing the `.user.js` file on disk does not update the running script. Must be manually pasted into Tampermonkey Dashboard.

---

## Files Modified This Session

| File | Change |
|------|--------|
| `1.../Overseer/overseer.py` | Business hours start changed from 6:00am to 5:15am; comparison updated to support minute-level precision |
| `1.../setup_fusion_addins.bat` | Rewritten: fixed ProgrammingTimer path, added FusionToolAuditor + ExportToolLibrary, added Fusion-running check, added Dropbox auto-detect, added programmer name prompt |
| `1.../ProgrammingTimer/config.py` | Added `timer_config.local.json` override loaded from `%APPDATA%\Traxis\ProgrammingTimer\` |
| `1.../ProShopBridge/proshop_bridge_tampermonkey.user.js` | v1.2.1: Badge only shown during active bridge push (`psBridge=` in URL); lazy badge creation; removed badge from manual browsing and sequence detail pages |

---

## Still Outstanding

- [x] ~~ProgrammingTimer add-in not symlinked into Fusion AddIns~~ (done)
- [ ] Git coverage: only Project 1 has .git — consider initializing for active projects
- [ ] `API Projects/` folder: evaluate for deletion (appears stale)
- [ ] `nul` file at project root: delete
- [ ] Dump_parameters and GenerateSetupSheet scripts: local copies on TRAXIS, not symlinked from Dropbox
- [ ] TraxisPostProcessor: consider moving from Project 12 to Project 1
- [ ] Centralize credentials (currently scattered across .env files)
- [ ] Run `setup_fusion_addins.bat` on Traxis MFG machine to deploy all add-ins + scripts
