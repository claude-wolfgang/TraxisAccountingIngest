# ProShop Automation Project Memory

## Project Overview
Traxis Manufacturing automation suite: Fusion 360 add-ins, ProShop ERP integration, shop floor dashboards.
See `services-architecture.md` for services/dashboards/overseer details.
See `proshop-bridge.md` for ProShop Bridge (unified add-in) details.
See `project-structure.md` for full file locations and components.
See `proshop-api.md` for API reference, scopes, and known issues.

## Services Architecture (Feb 19, 2026)
- **Overseer v1.2** (:8060) — monitors all services, auto-restarts on failure
- **Time Tracker Dashboard** (:8050) — employee clock/tracking status from ProShop API
- **FASData Live Dashboard** (:8070) — CNC machine utilization from FocasMonitor SQLite DB
- **FocasMonitor** (Windows Service) — FOCAS CNC polling → `C:\FASData\monitoring.db`
- All Flask apps bind `0.0.0.0` — LAN accessible at `10.1.1.71:{port}`
- Overseer auto-starts TimeTracker + FASData; FocasMonitor managed by Windows
- Full details: `services-architecture.md`

## Key Credentials/Endpoints
- ProShop GraphQL: `https://traxismfg.adionsystems.com/api/graphql`
- Token endpoint: `https://traxismfg.adionsystems.com/home/member/oauth/accesstoken`
- Credentials file: `C:\Users\TRAXIS\.traxis.env`
- **Active client: `0615-12FB-C88D`** (FusionConnector) — scope: `parts:rwdp+workorders:rwdp+users:r`
- **Active client: `B769-88F7-A69B`** (TimeTrackerDashboard) — scope: `parts:rwdp+workorders:rwdp+users:r+toolpots:r`
- Client `3923-9C1C-7291` is **BROKEN** (scope corrupted during edit)
- Client `4286-5AC7-DFB2` is **BROKEN** (scope corrupted during edit)

## Known Issues
- Written Descriptions: API mutation succeeds but ProShop UI shows blank (Tampermonkey clipboard workaround)
- **G-Code Tool # NOT in ProShop GraphQL schema** — HTML form field is `machinetoolnumber` but no corresponding GraphQL field exists. Tried: `machineToolNumber`, `gCodeTool`, `gcodeTool`, `toolNumber`, `gcodeToolNumber`, `ncToolNumber` — all rejected. Must be set via Selenium at push time (headless Chrome: checkout → fill inputs → save). Tampermonkey fallback exists but is NOT reliable across all machines.
- **Time tracking API mutations** require `users:w` — ProShop won't grant it. Contact Adion Systems.
- **Setup2 sequence details push fails** on 10981 part — root cause unknown
- **Selenium helper had `$` vs `?` URL bug** (line 143) — fixed 2026-03-13. Was navigating to broken URLs, causing G-Code Tool # to never be set. Also changed to overwrite existing values instead of skip-if-filled.
- **No Python on Garrett's ASUS workstation** — Selenium can't run there. Push machine (TRAXIS) needs Python + Selenium + ChromeDriver.
- **`requests.Session` goes stale** after ~12 hours under pythonw.exe — overseer auto-restarts

## Credential Architecture
- **`.traxis.env`** is the single source of truth for ALL API credentials
- All components read from `.traxis.env`: ProShopBridge, proshop_gui, proshop_graphql_v2, TimeTrackerDashboard
- **Never cache API credentials in secondary config files**

## FOCAS Data Lessons
- **spindle_speed 131072 (0x20000)** is a FOCAS flag, NOT real RPM — filter with `< 100000`
- **Cutting** = (run_status STRT/MSTR OR real spindle) AND (motion MTN/DWL OR feed_rate > 0)
- **Running** = run_status STRT/MSTR OR real spindle speed > 0 (but not cutting)
- Motion codes: `MTN` = axis motion, `DWL` = dwell, `***` = idle
- Run status: `STRT` = running, `MSTR` = spindle master, `STOP` = stopped, `***` = idle
- FocasMonitor polls every 60s → 60 samples/hour during shift

## Key Lessons Learned
- Editing ProShop OAuth client scope can **corrupt** the client permanently. Create NEW clients.
- **ProShop OAuth scope field**: use spaces between scopes, set at creation time, don't edit after.
- **ProShop OAuth "Direct login" checkbox** = enables client credentials flow.
- `sendInfoToHTML` has payload size limit — ~40 WOs works, ~400 WOs with ops fails.
- Fusion palette bridge: `adsk.fusionSendData` return values are BROKEN.
- `sendInfoToHTML` is not thread-safe — route through `queue.Queue` + `fireCustomEvent`.
- Long main-thread work freezes Fusion — split CAM extraction from HTTP push via state machine.
- `setup.workCoordinateSystem` returns `Matrix3D` — call `matrix.getAsCoordinateSystem()`.
- Fusion CAM `param.expression` returns raw ternary formulas — use `.value` instead.
- ProShop creates sequence detail rows in creation order — push one tool per API call.
- Unicode `°` doesn't survive ProShop rich-text paste — use `&deg;` HTML entity.
- Fusion scripts must live in `%appdata%\..\API\Scripts\{ScriptName}\{ScriptName}.py`.

## Python Environment
- **Primary:** `C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\` (python.exe / pythonw.exe)
- **Secondary:** `C:\Users\TRAXIS\AppData\Local\Python\pythoncore-3.14-64\` (Windows Store)
- Git bash `python` → WindowsApps stub. Use full paths or `py` launcher to avoid ambiguity.
- Flask installed in all three environments.

## Scheduling API Probe Results (Feb 13, 2026)
- `workCenter` IS WRITABLE on UpdateWorkOrderOperationInput and UpdatePartOperationInput
- `workCell`/`workCells` queries require `toolpots:r` scope
- ProShop calls machines "WorkCells" (module: `toolpots`) — 29 related types in schema
- Full results: `scheduling_probe_results.txt`

## ProgrammingTimer v1.1.0 (Feb 16, 2026)
- `io_worker.py` — background thread for all file I/O (queue.Queue pattern)
- Today's total cached in memory — no JSONL read on button click
- Full audit report: `FREEZE_AUDIT_REPORT.md`

## ProShopBridge v1.4.0 (Feb 16, 2026)
- `_doEvents_wait(seconds)` replaces `time.sleep()` in screenshot capture
- PowerShell composite subprocess runs on background push thread
- Full audit report: `FREEZE_AUDIT_REPORT.md`

## Working Directory
`D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations`
