# Traxis Claude Code Session — 2026-03-07

## Session Summary

Deployment architecture review for connecting ~10 shop floor PCs to all Traxis web services. Discovered the Overseer already solves central service management — the remaining gap is a shop-floor portal page and IPC extension deployment.

---

## Task 1: Deployment Architecture Review

### Goal
Decide the best way to simply and reliably connect and update all Traxis services across ~10 shop PCs.

### Services Inventoried

| Service | Project | Type | Port | Managed By |
|---------|---------|------|------|------------|
| ProShop Message Notifier | 18 | Flask web app | 5050 | Overseer |
| COTS Crib Kiosk | 17 | Flask web app | 5000 | Overseer |
| TimeTrackerDashboard | 1 | Flask web app | 8050 | Overseer |
| FASDataDashboard | 1 | Flask web app | 8070 | Overseer |
| FocasMonitor | 12 | Windows Service | — | Windows / Overseer monitors |
| Traxis IPC v2 | 14 | Chrome Extension (MV3) | — | Manual install per browser |
| Overseer Dashboard | 1 | Flask web app | 8060 | Self |

### Key Finding: Overseer Already Solves Central Service Management

The Overseer (`1. Proshop Automations/Overseer/overseer.py`, v1.2) already:
- Runs on the TRAXIS server PC
- Auto-starts 4 Python services (TimeTracker, FASData, MessageNotifier, COTSCribKiosk)
- Monitors all 5 services with health checks every 60s
- Auto-restarts on failure (3 consecutive failures or 5+ degraded)
- Provides admin dashboard at `:8060`
- Code updates deploy via Dropbox sync + service restart

**The central server pattern is already in place.** Shop PCs access services by pointing browsers at the TRAXIS machine.

### What's Missing

1. **Shop-floor portal page** — One URL/bookmark for all shop PCs instead of remembering individual ports. The Overseer dashboard is an admin tool, not a user-facing launcher.

2. **IPC extension deployment** — Currently a Chrome extension (Manifest V3) requiring manual install on each browser. Two options discussed:
   - **Convert to web app** served from the central server (eliminates per-PC install entirely)
   - **Keep as extension**, deploy via shared network folder + Chrome enterprise policy

3. **PC discovery** — Shop PCs need to know the server hostname/IP. Could be solved by the portal page + one bookmark or homepage setting.

### Recommended Architecture

```
TRAXIS Server PC (already running)
├── Overseer (:8060)          — admin dashboard, manages all below
├── Portal Page (:80 or :8060/portal) — shop floor landing page [TO BUILD]
├── Message Notifier (:5050)  — already running
├── COTS Kiosk (:5000)        — already running
├── TimeTracker (:8050)       — already running
├── FASData Dashboard (:8070) — already running
├── IPC Tool (:????)          — convert from Chrome ext to web app [TO BUILD]
└── FocasMonitor (service)    — already running

Shop PCs (x10)
└── Chrome → http://traxis-server/  (one bookmark, that's it)
```

### Decision Points (not yet decided)

- [ ] Build portal page? (Where to serve it — new port, or add route to Overseer?)
- [ ] Convert IPC Chrome extension to web app? (Eliminates per-PC install friction)
- [ ] How to handle IPC's ProShop API auth from browser? (Currently uses Chrome extension host_permissions for cross-origin access — web app would need a backend proxy)

---

## Task 2: Project 19 — Shop Floor Scheduler (Full Build)

### Goal
Build an interactive drag-and-drop shop floor scheduler that pulls WOs/ops from ProShop, displays them on a Gantt-style board, and lets operators mark progress.

### What Was Built

**11 files, ~2,100 lines of code:**

| File | Purpose |
|------|---------|
| `app.py` | Flask routes + 16 API endpoints (blocks CRUD, operator actions, flags, sync, health) |
| `config.py` | Port 5080, ProShop API credentials, sync intervals, business hours |
| `database.py` | SQLite schema (10 tables), seed data (10 machines, work center mappings), query helpers |
| `proshop_client.py` | OAuth2 + GraphQL client adapted from COTS Kiosk, work order/operation queries, writeback mutations |
| `sync.py` | Background sync engine — full sync every 15 min, writeback queue every 2 min |
| `templates/scheduler.html` | Main Gantt board page |
| `templates/operator.html` | Single-machine operator view |
| `templates/dashboard.html` | Overview dashboard |
| `static/scheduler.js` | Gantt board logic, drag-drop from backlog via overlay zones, block details panel |
| `static/operator.js` | Progress buttons, mark complete with confetti + chime, flag modal |
| `static/dashboard.js` | Stats grid, machine status cards, past-due/flags lists |
| `static/style.css` | Dark theme, EventCalendar overrides, all component styles |
| `run_scheduler.bat` | Startup script with API secret |
| `requirements.txt` | flask, requests |

### ProShop API Integration

- **79 active WOs** pulled via GraphQL
- **525 operations** synced with duration data
- **293 ops** have real time data from `minutesPerPart × quantityOrdered / 60`
- **232 ops** estimated (no ProShop cycle time data)
- **72 ops** auto-mapped to CNC machines via work center codes (011–022)
- **Scope:** `parts:r+workorders:rwdp+users:r+toolpots:r`

### Bugs Fixed During Build

1. ProShop `StringQueryInput` uses `exactly` not `eq`
2. ProShop field name mismatches (`workOrderNumber`, `qtyComplete`, `deliverypriority`, etc.)
3. `customerPlainText` requires `contacts:r` scope — removed from queries
4. EventCalendar.create() crash killed backlog JS — wrapped in try/catch
5. HTML5 drag-drop consumed by EventCalendar — solved with transparent overlay zones
6. `minutesPerPart` field discovered for real duration calc (replaced zero-value `runTime`)
7. GraphQL `data: null` responses crash `.get()` chain — fixed with `(result.get("data") or {})` pattern

### Status
Running on `:5080`. Core scheduling functional. Needs real-world drag-drop testing and validation before enabling ProShop writeback.

---

## Files Created This Session

| File | Type | Location |
|------|------|----------|
| `SESSION_LOG_2026-03-07.md` | This file | All Projects Monitoring |
| `19. Shop Scheduler/app.py` | Flask application | Project 19 |
| `19. Shop Scheduler/config.py` | Configuration | Project 19 |
| `19. Shop Scheduler/database.py` | SQLite schema + queries | Project 19 |
| `19. Shop Scheduler/proshop_client.py` | ProShop API client | Project 19 |
| `19. Shop Scheduler/sync.py` | Sync engine | Project 19 |
| `19. Shop Scheduler/templates/*.html` | 3 page templates | Project 19 |
| `19. Shop Scheduler/static/*.js` | 3 JS files | Project 19 |
| `19. Shop Scheduler/static/style.css` | Stylesheet | Project 19 |
| `19. Shop Scheduler/run_scheduler.bat` | Startup script | Project 19 |
| `19. Shop Scheduler/requirements.txt` | Dependencies | Project 19 |

## Files Modified This Session

None (all new files).

---

## Still Outstanding (carried from 2026-03-02 + new)

### New — Shop Scheduler (Project 19)
- [ ] Real-world drag-drop testing — schedule actual jobs and verify workflow
- [ ] Pull machines from ProShop work cells API instead of hardcoded list
- [ ] FASData integration — read `monitoring.db` for live machine status on dashboard
- [ ] Enable ProShop writeback once scheduler accuracy validated
- [ ] Add to Overseer config for auto-start/monitoring

### New — Deployment
- [ ] Build shop-floor portal page (single URL for all services)
- [ ] Decide: convert IPC extension to web app or deploy via Chrome policy
- [ ] If converting IPC: build backend proxy for ProShop API calls

### Carried Forward
- [ ] Git coverage: only Project 1 has .git — consider initializing for active projects
- [ ] `API Projects/` folder: evaluate for deletion (appears stale)
- [ ] `nul` file at project root: delete
- [ ] Dump_parameters and GenerateSetupSheet scripts: local copies on TRAXIS, not symlinked from Dropbox
- [ ] TraxisPostProcessor: consider moving from Project 12 to Project 1
- [ ] Centralize credentials (currently scattered across .env files)
- [ ] Run `setup_fusion_addins.bat` on Traxis MFG machine to deploy all add-ins + scripts
