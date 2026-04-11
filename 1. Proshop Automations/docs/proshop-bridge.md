# ProShop Bridge Add-in Details

## Version
v1.3.0 (Feb 2026)

## Purpose
Unified Fusion 360 add-in that replaces three separate tools:
1. **ProShopConnector** (WO browser) → Tab 1: Work Orders
2. **EXPORT TO PROSHOP** (CAM data extraction) → integrated into push pipeline
3. **proshop_gui_v1_5.py** (setup→op mapping + push) → Tab 2: Export & Push

Uses **Tampermonkey** userscript instead of Selenium for written descriptions.

## Location
- Source: `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProShopBridge\`
- Deployed: `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProShopBridge\`
- **Always sync both locations** after edits (cp source → deploy)

## Files
- `ProShopBridge.py` — Main Python add-in (~1400 lines, v1.2.0)
- `palette.html` — Two-tab embedded UI (WO browser + Export & Push)
- `ProShopBridge.manifest` — Fusion metadata (v1.2.0)
- `proshop_bridge_tampermonkey.user.js` — Browser userscript for written descriptions (v1.1.0)

## Architecture

### Python Backend (ProShopBridge.py)
- **Credentials/Auth**: Reads `.traxis.env`, OAuth token management
- **GraphQL**: WO fetch (bulk, multi-year, single with ops), push sequence details mutation
- **CAM Extraction**: `get_all_operations()`, `extract_operation_data()`, `extract_tool_data()`, `get_wcs_info()`, `is_turning_setup()`, `get_stock_info()`, `get_stock_wcs_bounds()`
- **WCS Decomposition**: `_decompose_wcs(setup)` — decomposes `Matrix3D` from `setup.workCoordinateSystem` into `(origin, xAxis, yAxis, zAxis)` via `getAsCoordinateSystem()`
- **Screenshots**: `capture_setup_screenshots_base64()` — 960x540, WCS-based camera, returns `list[(view_name, b64)]` tuples
- **Sequence Details**: `generate_sequence_details()` — builds tool array for API
- **Written Description**: `generate_written_description_html()` — HTML with:
  - Header table: Program, Name, WCS G-code, WCS Origin XYZ, Material Stickout, Stock Size DX/DY/DZ, Stock Lower/Upper in WCS, Stock Mode, Stock Offsets, Setup Notes, Est. Machining Time
  - 4 labeled screenshots (TOP VIEW, FRONT VIEW, ISO VIEW, REVERSE ISO)
  - Operations list with coolant type per operation
- **Clipboard Push**: `push_written_description_via_clipboard()` — PowerShell Set-Clipboard, opens browser URL
- **Orchestrator**: `_start_push()` + `_process_next_setup()` — state machine: extract CAM on main thread → push HTTP on background thread → `PushNextEventHandler` advances to next setup
- **Thread-safe responses**: `_send_from_thread()` queues data → `ResponseEventHandler` delivers via `sendInfoToHTML` on main thread

### HTML Frontend (palette.html)
- **Tab 1: Work Orders** — full WO browser (search, active filter, user detection, ops on-demand)
  - "Select for Export" button on each expanded WO card
- **Tab 2: Export & Push** — selected WO bar, CAM setup cards with op-mapping dropdowns, Push button, progress bar + log
- **permanentHandlers** — `pushProgress` and `pushComplete` events (not promise-based)

### Selenium Helper (`proshop_selenium_helper.py` v1.1)
**Primary mechanism for G-Code Tool #** — runs at push time on the push machine.
- Called as subprocess after GraphQL sequence push
- Logs into ProShop via headless Chrome, navigates to sequence detail page
- Checks out page → sorts rows by Seq # → parses `T##:` prefix from descriptions → fills G-Code Tool # inputs → cleans descriptions → saves
- **Saves server-side** — data is correct for ALL viewers, no browser extension needed
- **Requires**: System Python + `selenium` + ChromeDriver on push machine
- **Fixed 2026-03-13**: URL bug (`$formName` → `?formName`), now overwrites existing G-Code Tool # values

### Tampermonkey Userscript (v1.3.1)
- Matches `https://traxismfg.adionsystems.com/*`
- **Written descriptions**: read clipboard → check `<!--PROSHOP_BRIDGE:uuid-->` marker → click Checkout → set editor content (prepend) → click Save → clear clipboard
- **Frameset fix (v1.3.1)**: Checks `window.top.location.href` for bridge params — ProShop uses framesets where child frames have different URLs than the parent
- Editor detection chain: CKEditor → TinyMCE → contenteditable → iframe
- Fallback: floating "Paste Written Description" button if clipboard API needs user gesture
- **Sequence detail (fallback only)**: Also parses T## on machines with TM installed, but Selenium is the primary mechanism

## Key Bridge Actions (JS→Python)
| Action | Response | Thread |
|--------|----------|--------|
| `fetchWorkOrders` | `fetchWorkOrdersResponse` | background |
| `fetchMultiYearWorkOrders` | `fetchMultiYearWorkOrdersResponse` | background |
| `fetchSingleWO` | `fetchSingleWOResponse` | background |
| `getDocumentInfo` | `getDocumentInfoResponse` | main |
| `openInBrowser` | — | main |
| `testConnection` | `testConnectionResponse` | background |
| `getSetups` | `getSetupsResponse` | main |
| `pushToProShop` | `pushProgress`* + `pushComplete`* | main + background |

\* = permanent handlers (multiple events, not promise-based)

## Data Flow
```
User selects WO → clicks "Select for Export" → ops loaded → switches to Export tab
  → CAM setups auto-loaded via getSetups action
  → User maps setups to ProShop ops via dropdowns
  → User clicks "Push to ProShop"
  → FOR EACH mapped setup:
      1. Extract CAM data + WCS + stock bounds (main thread)
      2. Capture 4 labeled screenshots (960x540, base64, WCS-aligned camera)
      3. [BG THREAD] Push sequence details via GraphQL mutation (one tool per call)
      4. [BG THREAD] Run Selenium helper: checkout → sort rows → fill G-Code Tool # from T## → save
      5. [BG THREAD] Generate written description HTML (header table + labeled images + ops with coolant)
      6. [BG THREAD] Copy to clipboard with marker, open ProShop URL
      7. Tampermonkey auto-fills editor, clicks Save
      8. [BG THREAD] Wait 12s, fire PushNextEventHandler → next setup
  → pushComplete event with results summary
```

## Written Description Fields (v1.2.0)
| Field | Source | Notes |
|-------|--------|-------|
| Program | `job_programName` param | Prefixed with "O" if numeric |
| Name | `job_programComment` or doc name | |
| WCS | `job_workOffset` → G-code | G54, G55, G54.1 P1, etc. |
| WCS Origin | `_decompose_wcs()` → origin Point3D | cm→inches |
| Material Stickout | Computed from chuck pos + stockZHigh | Turning only |
| Stock Size | `get_stock_wcs_bounds()` → stock solid AABB projected to WCS | DX/DY/DZ in inches |
| Stock Lower/Upper | Same function → min/max corners in WCS | X/Y/Z in inches |
| Stock Mode | `job_stockMode` param | Hidden if conditional expression |
| Stock Offsets | `job_stockOffset*` params | Sides/Top/Bottom in inches |
| Setup Notes | `job_description` param | |
| Est. Machining Time | Sum of `machiningTime` from all operations | Minutes + seconds |
| Screenshots | 4 views: top, front, iso, rev_iso | Labeled with view name |
| Operations | All ops with tool number, name | Coolant shown per op |

## Credentials
- Active client: `0615-12FB-C88D` (FusionConnector)
- Scope: `parts:rwdp+workorders:rwdp+users:r`
- Loaded from `~/.traxis.env` (local) or Dropbox fallback

## Known Issues (v1.5.0 / 2026-03-13)
- **G-Code Tool # not in ProShop GraphQL API**: HTML form field `machinetoolnumber` has no GraphQL equivalent. Must use Selenium helper at push time. This is a ProShop/Adion API gap.
- **Selenium requires Python + ChromeDriver on push machine**: Not available on all workstations. Primary push machine (TRAXIS) must have these installed.
- **Setup2 seq FAIL on 10981**: Sequence details push fails for Op 60 — needs investigation
- **Conditional expressions**: Some CAM params (`wcs_origin_mode`, `job_stockMode`) return ternary formulas. Fixed by filtering `?`+`==` in `_pexpr()` and `get_stock_info()`.
- **Tampermonkey may not auto-fire**: If browser doesn't have focus, clipboard read fails. User sees fallback paste button.
- **ProShop framesets**: TM script must check `window.top.location.href` for bridge params (fixed v1.3.1)
- **`Unknown action: response`** log spam: palette JS sends "response" actions that Python doesn't handle. Harmless but noisy.

## Future Enhancements
- **Contact Adion Systems**: Request `machineToolNumber` (G-Code Tool #) be added to `UpdatePartOperationToolInputData` GraphQL input type. This would eliminate the Selenium workaround entirely.
- **Investigate seq FAIL**: Debug why Setup2 sequence details fail on certain parts
- **Auto-create op subsections**: If a ProShop operation doesn't have a written description subsection, create via API
- **Resolve conditional expressions**: Try `param.value` vs `param.expression` to get resolved enum values
- **Reduce log noise**: Handle or suppress `Unknown action: response` messages

## Changelog
### v1.3.0 (Feb 2026)
- **Enhancement: Orthographic projection** — Top/Front/Right views use `OrthographicCameraType`; ISO stays perspective
- **Enhancement: Composite screenshot** — 4 views composited into single 2x2 JPEG via PowerShell + System.Drawing (`composite_screenshots.ps1`)
- **Enhancement: Right view replaces Reverse ISO** — Standard engineering views: top, front, right, iso
- **Enhancement: Tool list table** — Replaced `<ul>` bullet list with HTML `<table>`: T# | Description | Dia | Flutes | Vendor/Product ID
- **Cleanup: Header simplified** — Removed Stock Lower/Upper, Stock Mode, Stock Offsets
- **Enhancement: WCS display** — Shows "G54 — Model Point, Top Center" instead of raw G-code
- **Enhancement: Setup transitions** — `_describe_setup_transition()` computes rotation between WCS frames, shows "Flip 180° about X" in "From Previous Op:" row. Works from CAM setup list (single-op push OK).
- **Enhancement: Sequence detail T## prefix** — Adds `T##:` to sequence description for TM G-Code Tool # extraction
- **Enhancement: One-at-a-time sequence push** — Individual tool API calls for correct row ordering
- **Fix: gcodeToolNumber removed** — Field not in ProShop GraphQL schema
- **Fix: Degree symbol** — Uses `&deg;` HTML entity (Unicode `°` garbled in rich-text paste)
- **Fix: Year filtering** — 4-digit years (2000-2099) excluded from auto-detect search candidates
- **Fix: TM writtenDescription guard** — Sequence detail detection skipped on written description pages
- **Removed: WCS Origin XYZ** — Model-space coordinates not useful to operators
- **Backup: v1.2.0** saved as `ProShopBridge_v1.2.0_backup.py`

### v1.2.0 (Feb 2026)
- **Enhancement: View labels on screenshots** — `capture_setup_screenshots_base64()` returns `(view_name, b64)` tuples. Shows "TOP VIEW", "FRONT VIEW", "ISO VIEW", "REVERSE ISO" captions.
- **Enhancement: WCS Origin XYZ** — via `_decompose_wcs()` helper (Matrix3D → getAsCoordinateSystem)
- **Enhancement: Stock Size (DX/DY/DZ)** — `get_stock_wcs_bounds()` projects stock solid AABB onto WCS axes
- **Enhancement: Stock Lower/Upper in WCS** — Bounding box in WCS coordinates (inches)
- **Enhancement: Stock mode/offsets** — Conditional expressions filtered out
- **Enhancement: Coolant per operation** — Displays coolant type next to each op
- **Enhancement: Setup notes** — Reads `job_description` parameter
- **Enhancement: Est. machining time** — Accumulates `machiningTime` from all operations
- **Fix: Matrix3D decomposition** — `setup.workCoordinateSystem` returns Matrix3D; use `getAsCoordinateSystem()` which returns `(Point3D, Vector3D, Vector3D, Vector3D)` with NO boolean prefix
- **Fix: Conditional expression filtering** — `_pexpr()` and `get_stock_info()` skip params containing `?` + `==`
- **Cleanup: ProShopConnector removed** from Fusion AddIns deploy dir
- **Reference script: `generate_setup_sheet.py`** deployed at `Scripts/GenerateSetupSheet/`

### v1.1.0 (Feb 2026)
- Fix: Push no longer blocks main thread (state machine with background threads)
- Fix: Thread-safe `sendInfoToHTML` via queue + custom events
- Fix: Error logging improvements

### v1.0.0 (Feb 2026)
- Initial unified add-in — all phases (1-5) implemented
- Written descriptions use Tampermonkey (clipboard) instead of API (ProShop API bug)

## Status (2026-03-13)
- **ProShopBridge.py v1.5.0** deployed — all prior enhancements plus freeze audit fixes
- **Tampermonkey v1.3.1** — frameset fix for badge/button visibility, G-Code Tool # overwrite
- **Selenium helper v1.1** — URL bug fixed (`$` → `?`), now overwrites G-Code Tool # values
- **Confirmed**: G-Code Tool # has no GraphQL API field. Selenium is the only automated path. Tampermonkey is fallback on TM-equipped machines only.
- **Action needed**: Ensure TRAXIS push machine has Python + Selenium + ChromeDriver installed
- **Git repo** initialized in source folder (master branch, 5+ commits)
