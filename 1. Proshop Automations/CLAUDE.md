# ProShop Bridge — Fusion 360 Add-in

## What This Is
A Fusion 360 palette add-in that connects to ProShop ERP via GraphQL API.
Lets users browse work orders, export CAM data, and push sequence-detail tools
and written-description HTML back to ProShop — all without leaving Fusion.

Replaces the earlier `ProShopConnector` (now in `OLD/`), `EXPORT TO PROSHOP`,
and `proshop_gui`.

## Architecture
- `ProShopBridge.py` — Python add-in: toolbar button, OAuth, GraphQL queries, palette bridge, push-to-ProShop orchestration
- `palette.html` — Embedded HTML/CSS/JS UI panel (runs in Fusion's Chromium)
- `ProShopBridge.manifest` — Fusion add-in metadata
- `proshop_selenium_helper.py` — Out-of-process Selenium helper for CKEditor written-description push (system Python, not Fusion's)
- `composite_screenshots.ps1` — PowerShell quadrant composite (top/front/right/iso) for the written description

## Key Technical Details
- Palette communicates with Python via `adsk.fusionSendData()` bridge
- OAuth 2.0 client credentials flow to ProShop API
- Credentials read from ~/.traxis.env (local) or ~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env (shared)
- ProShop GraphQL endpoint: https://traxismfg.adionsystems.com/api/graphql
- Token endpoint: https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
- Fusion 360 uses Python 3.14 internally

## ProShop API Details
- OAuth: POST form-urlencoded to token endpoint with grant_type=client_credentials, client_id, client_secret, scope
- Scope: "parts:rwdp+workorders:rwdp" (current client; users:r+toolpots:r not yet added)
- GraphQL: POST JSON with Bearer token
- Work orders filtered by year string (e.g., "2026"), pageSize: 500
- `part` is a nested object: `part { partNumber partName }`, `partRev` is a scalar string

## Palette Bridge
- JS→Python: `adsk.fusionSendData(action, dataStr)` triggers `HTMLEventHandler.notify()`
- Python→JS: `app.fireCustomEvent()` → `CustomEventHandler` → `palette.sendInfoToHTML()` (thread-safe)
- JS receives via `window.fusionJavaScriptHandler.handle(action, dataStr)` with Promise callbacks
- Return values from `fusionSendData` are BROKEN in this Fusion version — do NOT use `html_args.returnData`
- Actions: fetchWorkOrders, fetchMultiYearWorkOrders, fetchSingleWO, openInBrowser, getConfig, testConnection, getDocumentInfo
- TIMING ISSUE: palette HTML loads before Python bridge — `waitForBridge()` polls up to 15s

## Toolbar Registration
- Panel is registered on UtilitiesTab as custom panel "proshopConnectorPanel"
- CAM workspace panel IDs confirmed via dump: UtilitiesTab > CAMScriptsAddinsPanel, etc.
- Current approach: creates own panel on UtilitiesTab (shows as PROSHOP dropdown)

## Implementation Status (v1.5.3)

### DONE: Move API calls off UI thread
All HTTP calls run on background threads via `threading.Thread`. Responses marshalled to main thread via `app.fireCustomEvent()` → `CustomEventHandler` → `palette.sendInfoToHTML()`.

### DONE: Parallelize year fetches
`fetch_multi_year_work_orders()` spawns two threads (one per year), joins both, then combines results.

### DONE: Auto-detect from active Fusion document
`getDocumentInfo` action reads `app.activeDocument.name`, extracts first token as part number (e.g., "10983 P1 v21" → "10983"). JS pre-fills search box with detected part before loading WOs.

### DONE: Lazy loading
Palette only created when button clicked. Data only fetched after bridge ready + auto-detect.

### DONE: Search matches part numbers
`applyFilters()` searches `wo.part?.partNumber`, `wo.part?.partName`, WO number, status, partRev, and operation descriptions.

## How to Test Changes
1. In Fusion: Shift+S → Add-Ins → toggle ProShopBridge OFF
2. Edit files here
3. Toggle ProShopBridge back ON
4. Click PROSHOP button in Utilities tab toolbar
5. Check Text Commands panel at bottom of Fusion for log output (lines prefixed with [Bridge])

## File Locations
- Add-in folder: %appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProShopBridge\ (symlink/junction back to this Dropbox folder — created by `setup_fusion_addins.bat`, run as admin per PC)
- Credentials: C:\Users\TRAXIS\.traxis.env (local) or ~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env (shared)
- ProShop base URL: https://traxismfg.adionsystems.com/procnc

## Interfaces
Produces: Overseer dashboard (port 8060) under waitress with POST /api/shutdown, /api/status, /api/services/*/restart|stop|start, /api/programming-sessions, programming_time_log.jsonl, overseer.log, **Telegram alerts on service outage/recovery** (one message per outage via Telegram Bot API, resets on recovery); **FASDataDashboard service (port 8070)** — live FOCAS dashboard (`/`, `/api/status`) and, as of 2026-05-28, the Breakeven dashboard (`/breakeven` + `/runtime_snapshot.js|json`) regenerated in-process every ~2.5 min from the live monitoring.db (see P32)
Consumes: Health endpoints from 13 managed services (ports 5000-8101 + 5003), FOCAS monitoring.db (path via `TRAXIS_FOCAS_DB` env var; default `C:\FASData\monitoring.db`), ProShop GraphQL API (via managed services), P25 Agent Exploration (TelegramBot :8100, AgentScheduler :8101), P31 Photo Upload Service (:5003), **Telegram Bot API** (via `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars — same vars as P25)
Contracts: Overseer expects each HTTP service to expose a health URL returning JSON. Validators in VALIDATORS dict must match service names in SERVICES_CONFIG. P25 services use PYTHON_EXE (not PYTHONW_EXE) with -u flag. AGENT_DIR path must match P25 folder location. **All managed Flask services expose POST /api/shutdown** — Overseer's `_stop_process` POSTs there first (2s timeout) and waits 5s for natural exit before terminate()/kill(). Paths and Python interpreter are env-driven via `TRAXIS_BASE_DIR`, `TRAXIS_PYTHON`, `TRAXIS_PYTHONW`, `TRAXIS_AIRCOMPRESSOR_PYTHONW`. **Production host is srv-01 (10.1.1.161) as of 2026-05-22**; literal-secret + literal-path fallbacks in code preserved for .71 rollback until soak window closes (~2 weeks), then to be stripped per "Phase A literal-fallback cleanup" Next Step. Per-service OAuth secrets (`PROSHOP_CLIENT_SECRET_BRIDGE` for MsgNotifier+COTSCribKiosk, `PROSHOP_CLIENT_SECRET_TOOLKIOSK` for ToolAssemblyKiosk) injected via env={} in SERVICES_CONFIG. **Telegram alerting** fires on "down" state only (not degraded); `ServiceState.alerted` flag prevents duplicates; recovery message sent when service returns to healthy. **TimeTracker staleness threshold** is 1200s during business hours / 7200s off-hours (was hard 300s — caused restart loops).

## Version
Current: 1.5.3 — increment version in both .manifest and .py docstring on changes. CHANGELOG.md gets a dated entry per release.

## Next Steps
- **Selenium written-description save-verifier false negative** — push to `ICO1-10-02003` Op 60 on 2026-05-13 reported `Save FAILED: Save not verified — marker not in response (HTTP 200, 289543 chars)`. Payload was only ~57.8KB, well below any plausible limit (also see v1.5.3 — fake 256KB limit removed). Marker `push-1778698658` injected into CKEditor content but not echoed in the 289KB response — likely either ProShop sanitization strips the JS-injected marker, or the response body is a different page view than the saved content. Save may have actually succeeded; verifier is over-strict. Investigation: load the page manually after a failed push and confirm whether the content is actually there, then either relax the verifier or pick a marker that survives sanitization (e.g., a benign HTML comment vs. an inline element).
- **Add scopes to OAuth client** — `contacts:r+toolpots:r` not yet added to ProShop OAuth client. Would enable customer prefix tags and machine names in the WO browser. (Current `SCOPES = "parts:rwdp+workorders:rwdp+users:r"`.)
- **Re-run `setup_fusion_addins.bat` as admin on this PC (Superuser)** to upgrade the ProShopBridge directory junction created 2026-05-13 to a real symlink, matching the other 5 Traxis add-ins.
