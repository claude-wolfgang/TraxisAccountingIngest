# ProShop Bridge — Reference for Claude

Use this file as context when working on the ProShop Bridge Fusion 360 add-in.

## What This Is

A Fusion 360 palette add-in (v1.1.0) for Traxis Manufacturing that connects to ProShop ERP via GraphQL API. It combines three previous tools into one:

1. **Tab 1: Work Orders** — browse/search WOs, expand for operations, select for export
2. **Tab 2: Export & Push** — map Fusion CAM setups to ProShop operations, push sequence details + written descriptions

## Files

| File | Purpose |
|------|---------|
| `ProShopBridge.py` | Main Python add-in (~1320 lines) |
| `palette.html` | Two-tab embedded HTML/CSS/JS UI |
| `ProShopBridge.manifest` | Fusion add-in metadata |
| `proshop_bridge_tampermonkey.user.js` | Browser userscript for written descriptions (v1.3.1) |
| `proshop_selenium_helper.py` | Headless Chrome: sets G-Code Tool # + sorts rows + saves (v1.1) |

### Locations

- **Source:** `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProShopBridge\`
- **Deployed:** `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProShopBridge\`
- **Always sync both locations** after edits

## ProShop API

- **GraphQL:** `https://traxismfg.adionsystems.com/api/graphql`
- **OAuth token:** `POST https://traxismfg.adionsystems.com/home/member/oauth/accesstoken`
  - `Content-Type: application/x-www-form-urlencoded`
  - Body: `grant_type=client_credentials&client_id=ID&client_secret=SECRET&scope=parts:rwdp+workorders:rwdp+users:r`
- **Credentials file:** `C:\Users\TRAXIS\.traxis.env` (single source of truth — never cache elsewhere)
- **Active client:** `0615-12FB-C88D` (FusionConnector)
- **Broken client:** `3923-9C1C-7291` (scope corrupted — do not use)

## Architecture

### Threading Model (v1.1.0)

Fusion 360's API is **not thread-safe**. All Fusion API calls must run on the main thread. HTTP calls must run on background threads to avoid freezing the UI.

**Thread-safe response delivery:**
- Background threads must NOT call `palette.sendInfoToHTML()` directly
- Instead: `_send_from_thread(action, data)` → puts on `queue.Queue` → fires `RESPONSE_EVENT_ID` custom event → `ResponseEventHandler` delivers on main thread
- Main-thread code can call `_send_response(action, data)` directly

**Push orchestration (state machine):**
1. `_start_push(mappings)` — initializes `_push_state`, calls `_process_next_setup()`
2. `_process_next_setup()` — extracts CAM data + screenshots (main thread), spawns background thread for HTTP push
3. Background thread pushes sequence details + written description, waits 12s for Tampermonkey, puts result on `_push_result_queue`, fires `PUSH_NEXT_EVENT_ID`
4. `PushNextEventHandler` — stores result, increments index, calls `_process_next_setup()` for next setup
5. When all setups done, sends `pushComplete` to palette

### Palette Bridge (JS ↔ Python)

| Direction | Mechanism |
|-----------|-----------|
| JS → Python | `adsk.fusionSendData(action, dataStr)` → `HTMLEventHandler.notify()` |
| Python → JS (main thread) | `_send_response(action, data)` → `palette.sendInfoToHTML()` |
| Python → JS (background thread) | `_send_from_thread(action, data)` → queue → custom event → `sendInfoToHTML()` |

**JS receives** via `window.fusionJavaScriptHandler.handle(action, dataStr)` with Promise callbacks.

**IMPORTANT:** Return values from `adsk.fusionSendData` are BROKEN in this Fusion version. Never use `html_args.returnData`.

### Bridge Actions

| Action | Response Event | Thread |
|--------|---------------|--------|
| `fetchWorkOrders` | `fetchWorkOrdersResponse` | background |
| `fetchMultiYearWorkOrders` | `fetchMultiYearWorkOrdersResponse` | background |
| `fetchSingleWO` | `fetchSingleWOResponse` | background |
| `getDocumentInfo` | `getDocumentInfoResponse` | main |
| `openInBrowser` | — | main |
| `testConnection` | `testConnectionResponse` | background |
| `getSetups` | `getSetupsResponse` | main |
| `pushToProShop` | `pushProgress` + `pushComplete` | main + background |

### Push Data Flow

```
User selects WO → "Select for Export" → ops loaded → switches to Export tab
  → CAM setups auto-loaded via getSetups
  → User maps setups to ProShop ops via dropdowns
  → "Push to ProShop" clicked
  → FOR EACH mapped setup:
      1. [MAIN] Extract CAM data (operations, tools, WCS, stock)
      2. [MAIN] Capture 4 screenshots (960x540, WCS-aligned camera, base64)
      3. [BG] Push sequence details via GraphQL mutation (one tool per call)
      4. [BG] Run Selenium helper: checkout page → sort rows → fill G-Code Tool # from T## prefix → save
      5. [BG] Generate written description HTML (inline base64 images)
      6. [BG] Copy to clipboard with marker, open ProShop URL
      7. Tampermonkey detects marker, auto-fills editor, clicks Save
      8. [BG] Wait 12s → fire PushNextEventHandler → next setup
  → pushComplete event with results summary
```

### Sequence Detail: G-Code Tool # (CRITICAL)

**G-Code Tool # has NO GraphQL API field.** The HTML form uses `machinetoolnumber` but ProShop's GraphQL schema does not expose it. Confirmed via introspection 2026-03-13 — all 17 writable fields on `UpdatePartOperationToolInputData` documented, none map to G-Code Tool #.

**Primary mechanism: Selenium helper** (`proshop_selenium_helper.py`)
- Runs as subprocess after GraphQL sequence push, on the push machine only
- Logs into ProShop, navigates to sequence detail page, checks out, parses `T##:` prefix from descriptions, fills G-Code Tool # inputs, saves
- Saves server-side — visible to ALL machines without Tampermonkey
- **Requires**: System Python + `selenium` package + ChromeDriver on push machine
- **Bug fixed 2026-03-13**: URL had `$formName` instead of `?formName` — Selenium was navigating to broken URLs and silently failing
- **Bug fixed 2026-03-13**: Now overwrites existing G-Code Tool # values (previously skipped non-empty fields)

**Fallback: Tampermonkey** (v1.3.1) — does the same T## extraction client-side, but only works on machines with TM installed. Not reliable for shop-wide viewing.

### Tampermonkey Userscript (v1.3.1)

- Matches `https://traxismfg.adionsystems.com/*`
- **Written descriptions**: Reads clipboard → checks `<!--PROSHOP_BRIDGE:uuid-->` marker → clicks Checkout → sets editor content → clicks Save
- **Frameset fix (v1.3.1)**: ProShop uses `<frameset>` pages. Bridge params (`psBridge=`, `writtenDescription`) are only on the top-level URL. Script now checks `window.top.location.href` so child frames detect bridge mode.
- Editor detection: CKEditor → TinyMCE → contenteditable → iframe
- Fallback: floating paste button if clipboard API needs user gesture
- **Sequence detail** (secondary/fallback): Also parses T## from descriptions on sequence detail pages. Not the primary mechanism — Selenium should handle this at push time.

## Key Functions

### CAM Extraction (main thread only)
- `get_all_operations(setup)` — recursively collects ops from setup/folders/patterns
- `extract_operation_data(op, seq)` — op name, type, tool data, manual NC handling
- `extract_tool_data(op)` — tool number, description, dimensions, holder info
- `get_wcs_info(setup)` — WCS G-code, origin mode, stickout calculation
- `capture_setup_screenshots_base64(setup, idx)` — 4 views via WCS-aligned camera

### Push Pipeline (background thread)
- `generate_sequence_details(setup_data)` — builds tool array for API. Adds `T##:` prefix to `sequenceDescription` for Selenium extraction.
- `push_sequence_details(part_number, op_number, tools_list)` — GraphQL mutation (one tool per call for correct row ordering)
- `_run_selenium_sequence_fix(part_number, op_number)` — headless Chrome: checkout → sort rows → extract T## from descriptions → fill G-Code Tool # → clean descriptions → save
- `generate_written_description_html(...)` — HTML with header table, images, ops list
- `push_written_description_via_clipboard(...)` — PowerShell clipboard + browser open

## Known Issues & Gotchas

- **G-Code Tool # not in GraphQL API** — HTML form field `machinetoolnumber` has no GraphQL equivalent. Must use Selenium helper (headless Chrome) at push time. Requires Python + selenium + ChromeDriver on the push machine.
- **Selenium helper needs Python on push machine** — Not installed on Garrett's ASUS workstation. TRAXIS machine (D: drive) is the primary push machine and needs Python + Selenium.
- **Written Descriptions via API are broken** — API mutation succeeds but ProShop UI shows blank. Using Tampermonkey clipboard workaround instead.
- **ProShop uses framesets** — Tampermonkey script must check `window.top.location.href` for bridge params, not just the current frame's URL (fixed v1.3.1).
- **`sendInfoToHTML` payload size limit** — ~40 WOs works, ~400 WOs with ops fails. Bulk queries strip ops.
- **`fireCustomEvent(additionalInfo)` payload size limit** — don't pass large data in the event string. Use a queue instead.
- **`adsk.fusionSendData` return values are BROKEN** — never use `html_args.returnData`.
- **Palette loads before Python bridge** — `waitForBridge()` in JS polls up to 15s.
- **Fusion stores values in centimeters** — convert: `value_cm / 2.54` for inches.
- **ProShop field name mismatch** — query uses `operationNumber`, mutation selector uses `opNumber`.
- **Part numbers are case-sensitive** in ProShop API.
- **Editing OAuth client scope can corrupt the client permanently** — happened to 3923 client. Create new clients instead.
- **Scope param is REQUIRED** on token request (otherwise HTML error page instead of JSON).

## ProShop Sequence Detail API Fields (confirmed 2026-03-13)

Writable fields on `UpdatePartOperationToolInputData`:
| API Field | ProShop Column | Notes |
|---|---|---|
| `sequenceNumber` | Seq # | |
| `sequenceDescription` | Sequence Description | Bridge adds `T##:` prefix for Selenium extraction |
| `tool` | Tool # | Product ID from Fusion tool library |
| `ncDescription` | Description | Auto-populated by ProShop from tool library — do NOT write |
| `outOfHolder` | OOH | |
| `holder` | Holder | |
| `gTypeInsert` | G-Type Insert | |
| `gTypeQuantity` | G-Type Quantity | |
| `rta` | RTA # | |
| `toolQuantity` | Tool Qty Usage | |
| `lengthControlDim` | Length Control Dim | |
| `diameterControlDim` | Diameter Control Dim | |
| `perHowManyParts` | Per How Many Parts | |
| `outOfHolderPrefix` | OOH Prefix | |
| `holderPrefix` | Holder Prefix | |
| `latheToolLocation` | Lathe Tool Location | |
| `latheToolNose` | Lathe Tool Nose | |
| `latheToolRad` | Lathe Tool Radius | |
| — | **G-Code Tool #** | **NOT IN API** — set via Selenium only |

## How to Test Changes

1. In Fusion: Shift+S → Add-Ins → toggle ProShopBridge OFF
2. Edit files in the source folder
3. Sync to deployed folder: `cp source/FILE "$APPDATA/.../AddIns/ProShopBridge/FILE"`
4. Toggle ProShopBridge back ON
5. Click ProShop Bridge button in Utilities tab toolbar
6. Check Text Commands panel (bottom of Fusion) for log output prefixed with `[Bridge]`

## Credentials File Format (.traxis.env)

```
PROSHOP_CLIENT_ID=0615-12FB-C88D
PROSHOP_CLIENT_SECRET=<secret>
PROSHOP_USER_ID=001
```

## GraphQL Examples

### Fetch work orders
```graphql
query($year: String) {
  workOrders(filter: {year: $year}, pageSize: 500) {
    totalRecords
    records {
      workOrderNumber status partRev
      part { partNumber partName }
    }
  }
}
```

### Single WO with operations
```graphql
query($woNum: String!) {
  workOrder(workOrderNumber: $woNum) {
    workOrderNumber status partRev
    part { partNumber partName }
    ops { records {
      operationNumber operationDescription proshopUrl
      isOpComplete setupTime runTime
    }}
  }
}
```

### Push sequence details
```graphql
mutation($partNumber: String!, $opNumber: String!, $tools: [UpdatePartOperationToolInput!]!) {
  updatePart(partNumber: $partNumber, data: {
    operations: [{
      selector: { field: opNumber, value: $opNumber },
      data: { tools: $tools }
    }]
  }) { partNumber }
}
```

## Version History

- **v1.1.0** — Thread-safe `sendInfoToHTML` via queue + custom events; push orchestration moved HTTP/waits to background thread; bare `except: pass` replaced with logging
- **v1.0.0** — Initial unified add-in (phases 1-5)
