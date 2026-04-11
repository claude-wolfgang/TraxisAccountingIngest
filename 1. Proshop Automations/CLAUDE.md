# ProShop Connector — Fusion 360 Add-in

## What This Is
A Fusion 360 palette add-in that connects to ProShop ERP via GraphQL API.
Lets users browse work orders and operations without leaving Fusion.

## Architecture
- `ProShopConnector.py` — Python add-in: toolbar button, OAuth, GraphQL queries, palette bridge
- `palette.html` — Embedded HTML/CSS/JS UI panel (runs in Fusion's Chromium)
- `ProShopConnector.manifest` — Fusion add-in metadata

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

## Implementation Status (v1.4.0)

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

### TODO: Add scopes to OAuth client
Add `contacts:r+toolpots:r` to the OAuth client in ProShop Admin to enable customer prefix tags and machine names.

## How to Test Changes
1. In Fusion: Shift+S → Add-Ins → toggle ProShopConnector OFF
2. Edit files here
3. Toggle ProShopConnector back ON
4. Click PROSHOP button in Utilities tab toolbar
5. Check Text Commands panel at bottom of Fusion for log output (lines prefixed with [ProShop])

## File Locations
- Add-in folder: %appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProShopConnector\
- Credentials: C:\Users\TRAXIS\.traxis.env (local) or ~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env (shared)
- ProShop base URL: https://traxismfg.adionsystems.com/procnc

## Version
Current: 1.4.0 — increment version in both .manifest and .py docstring on changes
