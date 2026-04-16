# Claude Projects — Session Log

Central log of all Claude Code sessions across Traxis projects.
Synced via Dropbox so both machines stay in sync.

---

## 2026-04-16

### P33: Tool Library Updater — API tool switchover D195-D198 and reusable CLI utility

**Task:** Test ProShop API capability to update tool library entries when switching manufacturers (GARR to Kennametal GOdrill), then build a reusable CLI tool for future switchovers.

**What was done:**

1. **Manual tool updates via ProShop GraphQL API** — Updated D195, D196, D197, D198 from GARR 5xD drills to Kennametal GOdrill 3xD KC7325 drills:
   - Queried existing tool records (description, dimensions, coating, approved brands)
   - Fetched new tool specs from Kennametal product pages (diameter, OAL, flute length, shank, helix, coating)
   - Found VPO pricing in ProShop (PO 263067, 4/9/2026) — prices $46.37-$47.12/ea
   - Updated all fields: description, overallLength, lengthOfCut, shankDiameter, coating (TIALN), helixAngle (30), ansiCatalogNumber, approved brand (KENNAMETAL + new EDP + VPO cost)
   - Preserved old GARR info in purchasingNotes with PREV: prefix, without overwriting existing notes (kiosk notes on D197 preserved)
   - Downloaded Kennametal product images (API doesn't support picture uploads)

2. **Built P33: Tool Library Updater CLI** — Reusable Python utility with subcommands:
   - `inspect` — Query/display tool records (human + JSON output)
   - `find-vpo` — Search Tool-type VPOs for pricing
   - `scrape` — Fetch specs from manufacturer websites (Kennametal scraper built, extensible registry)
   - `preview` — Dry-run diff of proposed changes
   - `update` — Execute mutations with confirmation prompt
   - `download-image` — Save product images for manual upload
   - All subcommands support `--json` for Claude Code integration

**Key discoveries:**
- BA16 OAuth client accepts `purchaseorders:r` scope at token time (not pre-registered but works)
- BA16 does NOT accept `contacts:r` — supplier names on VPOs require AccountingConnector client
- ProShop API does NOT support picture uploads on tools (read-only field)
- `updateTool` mutation uses selector/data pattern for nested `approvedBrands` table updates

**Files created:**
- `33. Tool Library Updater/CLAUDE.md`
- `33. Tool Library Updater/tool_update.py` — CLI entry point
- `33. Tool Library Updater/proshop_tools.py` — ProShop API client
- `33. Tool Library Updater/description_format.py` — Description builder + PREV formatter
- `33. Tool Library Updater/mfg_scrapers.py` — Manufacturer scrapers (Kennametal)
- `Kennametal_B041A03455CPG_GOdrill.jpg` (+ 3 more product images in project root)

**ProShop records modified:**
- D195: GARR 89321 ($15.12) -> KENNAMETAL B041A03455CPG ($46.37)
- D196: GARR 89391 ($19.06) -> KENNAMETAL B041A04217CPG ($47.12)
- D197: GARR 89346 ($16.54) -> KENNAMETAL B041A03734CPG ($46.37)
- D198: GARR 89281 ($13.58) -> KENNAMETAL B041A02800CPG ($46.46)

**Status:** Complete. CLI tested and working against live ProShop data.

---

### P31: BLE Proximity Worker Tracking — Project creation and initial hardware test

**Task:** Create new project P31, move BLE proximity research from P5, and test Feasycom beacon tags with Asus USB BT dongle on 10.1.1.178.

**What was done:**

1. Created `31. BLE Proximity Worker Tracking/` as a new project, moved `BLE_Proximity_Detection_Research.md` from P5 via `git mv` (preserving history).
2. Wrote initial BLE scan test (`ble_scan_test.py`) — confirmed dongle detects both Feasycom tags.
3. Discovered beacons use **rotating random MAC addresses** — initial monitor using hardcoded MACs only got ~2 samples/5s. Rewrote to identify beacons by **iBeacon major number** instead.
4. Discovered both beacon slots on one tag share the same major but different minors (e.g., major=40604, minor=16178/16179). Grouped by major only.
5. Built live RSSI monitor (`ble_rssi_monitor.py`) with zone classification and rolling averages.
6. **Key finding:** Asus USB dongle reads -78 to -90 dBm regardless of distance (0ft vs 50ft in metal cabinet = ~4dB difference). Not enough RSSI dynamic range for proximity detection. Need a purpose-built BLE gateway.

**Files created:**
- `31. BLE Proximity Worker Tracking/CLAUDE.md`
- `31. BLE Proximity Worker Tracking/ble_scan_test.py`
- `31. BLE Proximity Worker Tracking/ble_rssi_monitor.py`
- `31. BLE Proximity Worker Tracking/ble_raw_diag.py`

**Files moved:**
- `5. Hyundai post development/BLE_Proximity_Detection_Research.md` → `31. BLE Proximity Worker Tracking/`

**Key decisions:**
- Identify beacons by iBeacon major number (not MAC, which rotates)
- Group minor variants under same major (same physical tag)
- Asus USB dongle insufficient for production — need dedicated BLE gateway (~$35-65)

**Open items:**
- Purchase a purpose-built BLE scanning gateway (Blue Charm BCG04, MOKOSmart MKGW3, or Shelly BLU Gateway)
- Label physical Feasycom tags with their major numbers (60285 and 40604)
- Consider Feasycom config app to adjust beacon advertising interval

---

## 2026-04-15

### P30: Material Label Extension — DOM scraper fixes and label layout update (Session 2)

**Task:** Test and fix the material label data scraping on ProShop WO pages, update label layout.

**What was done:**

1. Fixed DOM scraper not finding material — "Part Stock" label wasn't matching due to `◉` bullet prefix characters. Added `[^a-z]*` prefix to all label regexes.
2. Fixed scraper using `el.textContent` which included all descendants — switched to own-text-node extraction so "Part Stock" label matches correctly.
3. Fixed "Qty Ordered" not matching — original regex only handled "Order Qty" pattern, added "Qty Ordered" variant.
4. For WOs with multiple Part Stock entries, scraper now picks the **last** material (the current/active one, since replacements are appended).
5. Updated label layout: material font increased from 18px to 24px with word wrapping (400px max width), removed quantity line, removed separate grade line. Part number stays at 14px.

**Files modified:**
- `30. Material Label Extension/traxis-material-label/src/content.js` — DOM scraper fixes (bullet-tolerant regexes, own-text extraction, Part Stock last-child logic)
- `30. Material Label Extension/traxis-material-label/src/label-generator.js` — enlarged material font, text wrapping, removed qty/grade lines

**Key decisions:**
- When multiple materials in Part Stock, always use the last one (replacement material supersedes original)
- Full Part Stock string on label (including shape/dimensions) rather than trimmed material type only
- No material selection UI — single-button print with auto-scrape

**Status:** Working. Tested on WO 26-0140 (single material), WO 26-0002 (long text wrap), and WO 26-0071 (dual materials).

---

### P17/P30: COTS PNG Label Generator + Chrome Extension Print Button

**Task:** Replace P-touch Editor .lbx template workflow for COTS labels with programmatic PNG generation (matching P9 WO label style) and add a browser-based print button on ProShop COTS pages.

**What was done:**

1. **P17 — `generate_cots_labels.py`** (new file): Python CLI that generates COTS label PNGs using Pillow + qrcode. Layout: QR code left (ProShop URL), bold COTS ID (48pt) + wrapped description (28pt) right. Fixed 450px width (2.5" at 180 DPI), 128px height. 2x supersampled with LANCZOS downsample for crisp text. Supports `--print` (sends to PT-P700 via 10.1.1.242:5002), `--all` (batch from CSV), `--copies`, and `--api` (pulls item data from ProShop GraphQL API instead of CSV).
2. **P30 — Chrome extension expanded** to also inject a "Print COTS Label" button on ProShop COTS detail pages (`/procnc/ots/*`). Added `cots-content.js` (button injection, DOM scraping for description) and `cots-label-generator.js` (Canvas-based rendering matching the Python layout). Button is fixed-positioned top-center to avoid disrupting ProShop page layout. Extension renamed to "Traxis Label Printer" v1.1.0.
3. Test-printed THI-219 labels through multiple iterations refining font sizes, text wrapping, and resolution.

**Files created:**
- `17. COTS - Tools Crib Kiosk/generate_cots_labels.py`
- `17. COTS - Tools Crib Kiosk/labels/` (generated PNGs)
- `30. Material Label Extension/traxis-material-label/src/cots-content.js`
- `30. Material Label Extension/traxis-material-label/src/cots-label-generator.js`

**Files modified:**
- `30. Material Label Extension/traxis-material-label/manifest.json` (added COTS content script, bumped version)

**Key decisions:**
- Fixed label width at 450px (2.5") per Wolfgang's constraint
- 2x supersampling for text quality, though thermal printer dithers to 1-bit
- Description font enlarged to 28pt with word wrapping (max 2 lines) per Wolfgang's feedback
- Chrome button placed as fixed-position top-center to avoid ProShop DOM interference

**Status:** Complete. Extension needs reload in chrome://extensions to pick up changes.

---

## 2026-04-13

### ProShop API — Batch WO Status Update to Invoiced

**Task:** Update 11 work orders to "Invoiced" status in ProShop based on QBO invoices created today.

**What was done:**

1. Read `wo_invoiced_today.md` — 11 WOs matched to QBO invoices created 2026-04-13
2. Investigated ProShop GraphQL schema — found `updateWorkOrder` mutation accepts `UpdateWorkOrderInput` with a `status: WorkOrderStatus` field
3. Verified all 11 WOs were in "Shipped" status
4. Test-updated 25-0300 → Invoiced successfully
5. Batch-updated remaining 10 WOs — all succeeded, zero failures

**WOs updated:** 25-0300, 25-0302, 26-0057, 26-0059, 26-0093, 26-0094, 26-0116, 26-0122, 26-0123, 26-0124, 26-0125

**Key discovery:** First use of `updateWorkOrder` mutation for WO status changes in the codebase. Pattern: `mutation($wn: String!, $data: UpdateWorkOrderInput) { updateWorkOrder(workOrderNumber: $wn, data: $data) { workOrderNumber status } }` with `{status: "Invoiced"}`.

**Files modified:** None — all work was ad-hoc API calls, no project code changed.

**Status:** Complete.

---

### Project 29: Rollo Printer App — Full Implementation

**Task:** Implement P29 Rollo Thermal Printer system tray app from spec.

**What was done:**

1. **Built `rollo_printer_app.py`** — full system tray app using pystray, PyMuPDF, pywin32. Right-click menu: Print to Rollo, Test Printer, Open Log, Quit.
2. **Smart PDF rescaling** — auto-detects ink bounding box on the page, crops to content, auto-rotates landscape→portrait, scales up to fill 4x6 label. Solves the core UPS problem where labels print tiny on thermal paper.
3. **Created PyInstaller spec** — single .exe build (40MB), no console window.
4. **Built .exe** — `dist/rollo_printer_app.exe` compiled successfully.
5. **Created shortcuts** — Desktop shortcut + Windows Startup folder shortcut for auto-launch on boot.
6. **Discovered `.pyw` not registered** on this machine — worked around with `.bat` launcher for dev, `.exe` for production.
7. **Tested end-to-end** — printed a real UPS label (`upscarmex.pdf`) to Rollo, confirmed content fills the label correctly.

**Files created:**
- `29. Rollo Printer App/rollo_printer_app.py` — main app source
- `29. Rollo Printer App/rollo_printer_app.spec` — PyInstaller spec
- `29. Rollo Printer App/rollo_printer_app.pyw` — windowless launcher copy
- `29. Rollo Printer App/Rollo Printer.bat` — bat launcher (dev fallback)
- `29. Rollo Printer App/requirements.txt` — dependencies
- `29. Rollo Printer App/CLAUDE.md` — project docs with interfaces
- `29. Rollo Printer App/dist/rollo_printer_app.exe` — compiled executable
- Desktop shortcut: `Rollo Printer.lnk`
- Startup shortcut: `Rollo Printer.lnk`

**Key decisions:**
- Used PyMuPDF (fitz) over PyPDF2 for reliable rasterization
- Content-aware cropping (ink bounding box detection) was critical — naive page scaling produced tiny labels
- Auto-rotation handles landscape UPS PDFs on portrait 4x6 labels

**Status:** Complete. App is running, printing correctly, and will auto-start on boot.

---

### Project 28: ProShop API Usage — Batch NCR Scrap Disposition

**Task:** Investigate API control over NCR (Non-Conformance Report) module and batch-disposition all outstanding NCRs as scrap.

**What was done:**

1. **Introspected ProShop GraphQL schema for NCR types** — mapped `NonConformanceReport`, `UpdateNCRInput`, `NCRDisposition`, `UpdateNonConformanceDispositionTableInput`, `NonConformanceReportFilter`, and related types
2. **Discovered OAuth scope gating** — `nonconformancereports:rwdp` scope is enforced server-side (unlike some other modules). Existing clients (FusionConnector, ClaudeCodeResearch) did not have it enabled
3. **Created new OAuth client** — `B828-32C5-5194` (2ClaudeCodeReasearch) with full scope list including NCR access. Discovered ProShop has a character limit on scope field and scopes are locked at client creation time
4. **Queried all 277 NCRs** — found 118 Outstanding, 159 Complete. Two status values only: "Outstanding" and "Complete"
5. **Tested single NCR update** — confirmed `updateNCR` mutation with disposition array adds "Scrap" disposition row and auto-flips status to "Complete"
6. **Batch processed 108 Outstanding NCRs** (on or before March 13, 2026) — all dispositioned as Scrap with note "Batch scrap disposition - API cleanup April 2026". 101 moved to Complete, 6 stayed Outstanding (0 parts affected)
7. **Processed remaining 14 NCRs** — scrapped 10 recent ones (post-March 13), deleted 4 zero-quantity NCRs
8. **Final result: 0 Outstanding NCRs remaining**

**Key findings:**
- ProShop NCR mutations: `addNCR`, `updateNCR(ncrRefNumber, data)`, `deleteNCR(ncrRefNumber)`
- Disposition is an array of `{data: {disposition, dispositionquantity, dispositionnotes}}` within `UpdateNCRInput`
- ProShop auto-completes NCRs when disposition quantity > 0 is added
- NCR dates are in `MM/DD/YYYY; HH:MM:SS AM/PM` format, not ISO
- OAuth scope field has a character limit; scopes must be set at client creation, cannot be expanded after

**Files modified:** None (all operations were API-only, no code changes)

**New OAuth client created:**
- Client ID: B828-32C5-5194
- Name: 2ClaudeCodeReasearch
- Scope includes: nonconformancereports:rwdp + full module access

**Status:** Complete. All 277 NCRs resolved (scrapped or deleted). Zero outstanding.

---

### Project 28: ProShop API Usage — Recon & Interval Reduction

**Task:** Investigate why ProShop reported ~1,600 API calls/hour from Traxis, identify culprits, and reduce call volume.

**What was done:**

1. **Full recon across all projects** — identified every script making ProShop GraphQL API calls, catalogued auth approaches, query types, polling patterns, and estimated calls/hr per service
2. **Identified top 3 culprits:**
   - Message Notifier (P18): ~2,400–4,800 calls/hr (30s per-user polling)
   - Time Status Display (P1): ~1,320 calls/hr (30s per-user polling)
   - Shop Scheduler (P19): ~1,200–1,350 calls/hr (15-min full sync with per-WO fan-out)
3. **Reduced polling intervals:**
   - P18 Message Notifier: 30s → 30 min (config.py POLL_INTERVAL)
   - P1 Time Status Display: 30s → 15 min (POLL_INTERVAL + dashboard.html POLL_MS)
   - P19 Shop Scheduler: 15 min → 2 hr (config.py SYNC_INTERVAL)
4. **Documented ProShop's response** from Joao (via Tom) — noting unfiltered bulk queries as future optimization target
5. **Wrote RECON_REPORT.md** with full findings, per-script breakdown, and recommendations
6. **Restarted all three services** via Overseer API

**Files modified:**
- `18. ProShop Message Notifier/config.py` — POLL_INTERVAL 30 → 1800
- `18. ProShop Message Notifier/templates/notifier.html` — added Check Now button, conditional auto-poll
- `18. ProShop Message Notifier/message_notifier.py` — added _single_check method
- `1. Proshop Automations/TimeTrackerDashboard/time_status_display_v1.0.py` — POLL_INTERVAL 30 → 900
- `1. Proshop Automations/TimeTrackerDashboard/dashboard.html` — POLL_MS 15000 → 900000
- `19. Shop Scheduler/config.py` — SYNC_INTERVAL 900 → 7200
- `28. Proshop API Usage/RECON_REPORT.md` — created (recon findings + ProShop reply)

**Key decisions:** Kept writeback interval (120s) unchanged in P19 since it only fires when there are queued local changes. Kept "Check Now" / "Refresh" buttons for on-demand use between intervals.

**Estimated result:** ~5,000–6,700 calls/hr → ~284–384 calls/hr

**Follow-up work (same session):**

7. **Resolved open items:**
   - Clock Feedback Display (`clock_feedback_display_v1_0_0.py`) — confirmed not running. Not on Overseer, no process found. Non-issue.
   - FusionToolAuditor hardcoded secret — removed `PROSHOP_CLIENT_SECRET` from source code, now loads from `.traxis.env` (same pattern as ProShopBridge). Also scrubbed secret from P16 CLAUDE.md.
   - GraphQL Playground — introspected 7 key filter types (`WorkOrderFilter`, `PurchaseOrderFilter`, `UserFilter`, `WorkCellFilter`, `ToolFilter`, `ContactFilter`, `ClockPunchFilter`) from live API. Documented all available filter fields in RECON_REPORT.md with recommended filter changes table.
8. **Documented Joao's (ProShop/Adion) reply** in RECON_REPORT.md — key guidance: use filters to fetch only needed records, GraphQL Playground at `/api/graphql` has full schema.
9. **Created P28 CLAUDE.md** with interfaces section.
10. **Added P28 to TRAXIS_ECOSYSTEM.md** project list.

**Additional files modified:**
- `16. Fusion Tool Library Product ID Changer/FusionToolAuditor/FusionToolAuditor.py` — replaced hardcoded credentials with `.traxis.env` loader
- `16. Fusion Tool Library Product ID Changer/CLAUDE.md` — removed hardcoded secret, updated credentials section
- `28. Proshop API Usage/CLAUDE.md` — created (interfaces)
- `28. Proshop API Usage/RECON_REPORT.md` — added ProShop reply, filter fields reference, recommended filter changes
- `TRAXIS_ECOSYSTEM.md` — added P28 entry

**Status:** Complete. Services restarted. All open items resolved except follow-up email to Tom/Joao (Wolfgang's action).

---

### Project 22: Tool Assembly Kiosk — Push to ProShop Button + Overseer Dashboard Fixes

**Task:** Move inventory sync from an always-on Overseer service to an on-demand kiosk button. Fix Overseer dashboard links and add self-restart capability.

**What was done:**

1. **Removed InventorySync from Overseer** — deleted service config, validator, and VALIDATORS entry
2. **Added "Push to ProShop" button to kiosk** — background thread + polling pattern for the ~15min sync; button on inventory menu and summary screens
3. **Added Overseer self-restart button** — `POST /api/overseer/restart` spawns replacement process; dashboard polls until it comes back
4. **Fixed Overseer "Open" links** — replaced `localhost` with `location.hostname` for remote viewing

**Status:** Complete. Overseer HTML committed. Kiosk changes sync via Dropbox.

---

## 2026-04-12

### Project 12: TPM (Traxis Program Manager) — Startup Fix + NC Program Naming (Session 5)

**Task:** Diagnose why TPM add-in won't load in Fusion 360, then review its purpose and discuss improvements.

**What was done:**

1. **Fixed startup crash** — `ModuleNotFoundError: No module named 'tpm'`. Root cause: Fusion's add-in loader doesn't add the add-in's directory to `sys.path`, so the `tpm/` subpackage (extracted in v1.6.0 on April 2) couldn't be found. Fix: `sys.path.insert(0, _addon_dir)` before the `from tpm import ...` line. Other add-ins (ProShopBridge, FusionToolAuditor) are single-file scripts so they never hit this.

2. **Added post-completion NC Program rename** — New `_rename_nc_programs()` function runs after posting (in `PostCompletedHandler`). Catches NC Programs created during posting with default names like `NCProgram4` and renames them to `PartNumber_OPxx` format using `_naming_state`.

3. **Added diagnostic logging** — `_match_nc_to_setup()` now logs which matching strategy succeeded or why it failed, so we can debug NC Program matching issues via Fusion's Text Commands panel.

4. **Proposed Name/File name improvement (DEFERRED)** — The post dialog "File name" field shows the O-code (`0071`) instead of the descriptive name (`R2S1-10130_OP70`). Fix requires a paired change: TPM sets `job_programName` to filename stem + every .cps post processor's `getProgramNumber()` handles non-numeric names by extracting OP from `_OPxx` pattern. Deferred because .cps changes are production-critical and need careful testing. Writeup documented in session for future reference.

**Files modified:**
- `12. FASData Implementation/TraxisProgramManager/TraxisProgramManager.py` — sys.path fix (lines 48-55), `_rename_nc_programs()` function, improved `_match_nc_to_setup()` logging, TODO comment on job_programName

**Key decisions:**
- O-code numbering (O0061, O0071) is cosmetic since programs are transferred via Fanuc Transfer Tool — not worth changing independently
- .cps post processor changes need careful rollout, not a quick session fix
- Version encoding in O-codes would be lost with the proposed approach — needs consideration

**Status:** TPM loads and runs. NC Program tree naming improved. File name field improvement waiting on .cps change plan.

---

### Projects 9/22/1: Generic Print Endpoint + WO Label Printing (Session 4)

**Task:** Add a generic image print endpoint to the label print service (P22) so any project can print labels, then add WO label printing capability to Project 9.

**What was done:**

1. **Generic `/api/print-image` endpoint** — Added to print_service.py on 10.1.1.242. Accepts base64-encoded PNG, copies count, and optional label_name. Uses shared `_print_image_gdi()` helper refactored from the existing `_print_png()` code.

2. **Remote restart endpoint** — Added `/api/restart` to print_service.py. Spawns a new process and exits, enabling remote restart from the overseer dashboard. Updated overseer.py to call `restart_url` for remote services instead of logging "cannot restart."

3. **WO label printing** — Added `print_wo_label()`, `make_wo_label_image()`, and `--print` CLI flag to generate_wo_labels.py (P9). Labels include QR code (encoding `proshop://wo/{wo_number}`), bold WO number, and part number + part name from ProShop API lookup.

4. **GDI print fixes** — Fixed BMP row alignment bug (image width must be padded to multiple of 4 for DWORD-aligned rows — caused 45° skew). Sized label to 128px height matching PT-P700's actual printable area (not 170px tape height). Adjusted fonts from 48pt→36pt to fit.

5. **Printer driver config** — Discovered PT-P700 "cut tape after data" setting (was cutting at fixed 3.94" regardless of content). Disabled auto power off so printer stays in sleep mode and wakes on print jobs.

6. **ProShop scope issue** — `contacts:r` needed for customer name on labels, but FusionConnector OAuth client rejects it despite ProShop admin showing it enabled. Fell back to part number + part name. Needs investigation.

7. **Camera/tablet planning** — Discussed IP camera vs GoPro vs tablet for shop floor photo capture. Decided on Android tablet as single device for walk-around setup photos, packing station box photos, tool photos, and QR scanning. Reolink IP camera order cancelled in favor of tablet. Brother ADS-2200 scanner for multi-page docs.

**Files modified:**
- `22. Tool Assembly Management/tool-kiosk/print_service.py` — /api/print-image, /api/restart, _print_image_gdi refactor, BMP row alignment fix, DEVMODE tape length
- `9. Shop Floor Cameras/config.py` — added PRINT_SERVICE_URL
- `9. Shop Floor Cameras/generate_wo_labels.py` — print_wo_label(), make_wo_label_image(), --print flag, label dimensions/fonts
- `9. Shop Floor Cameras/proshop_client.py` — added customerName field to lookup (reverted query due to scope)
- `1. Proshop Automations/Overseer/overseer.py` — restart_url config, remote restart support
- `C:\Users\TRAXIS\.traxis.env` — scope change attempted (reverted)

**Key decisions:**
- PT-P700 printable area is 128px tall (not 170px for 24mm tape) — labels must be sized to 128px
- BMP row data must be DWORD-aligned (pad image width to multiple of 4)
- "Cut tape after data" driver setting eliminates tape waste
- Tablet replaces both GoPro and fixed IP camera for shop floor photo capture
- Part number + part name on labels (customer name blocked by OAuth scope issue)

**Status:** WO label printing fully working end-to-end. Remote restart working. Camera/tablet hardware pending order.

---

### Project 1: ProShop Bridge — Orientation Cube Visual + 180° Axis Fix (Session 3)

**Task:** Refine the "From Previous Op" section of the written description push. The text-based face mapping ("Right goes to Front, Back goes to Left") was confusing and the 180° rotation axis detection was wrong.

**What was done:**

1. **Fixed 180° rotation axis detection bug** — `_rotation_summary()` used `max(diagonal)` to find the rotation axis for 180° rotations, which fails for non-cardinal axes (e.g., (1,-1,0)/√2 was falsely reported as "X axis"). Replaced with proper `(R+I)` eigenvector method that correctly finds the rotation axis for all 180° cases.

2. **Added isometric orientation cube SVGs** — New `_render_orientation_cube_svg()` function generates transparent isometric cube with two highlighted faces (green=Top, blue=Front). Before/After cube pair shows where those faces move after the rotation. Pure inline SVG, zero dependencies, microsecond generation time.

3. **Added `_render_transition_visual()`** — Composes Before→After HTML layout with cubes, arrow, color legend, and rotation summary text caption (e.g., "flip about X axis").

4. **CKEditor SVG support** — Added `editor.filter.allow()` call in Tampermonkey script to whitelist SVG/polygon/text elements through CKEditor's Advanced Content Filter. Confirmed SVG renders in ProShop.

5. **WCS debug logging** — Added raw WCS axis vector logging for both setups during push, enabling diagnosis of WCS frame mismatches.

6. **Iterative refinements** — Removed face labels (cluttered), removed dashed lines (means hidden edges in shop drawings), tried axis spear + curved arrow (too busy), settled on clean colored cubes only.

**Files modified:** `ProShopBridge/ProShopBridge.py` (orientation cube SVG, 180° fix, WCS logging), `ProShopBridge/proshop_bridge_tampermonkey.user.js` (CKEditor SVG filter)

**Key decisions:**
- Two highlighted faces (Top + Front) disambiguate all 6 faces via right-hand rule — one face is not enough
- Solid edges only — dashed lines imply hidden internal edges to machinists
- Text caption kept alongside cubes for "flip about X axis" summary
- Axis spear and curved arrow tried but removed — cubes alone are clearer
- The WCS frames from Fusion may not correspond to a clean physical flip if the programmer also rotated XY for fixture alignment — the corrected 180° detection now honestly reports "flip 180°" instead of falsely attributing a cardinal axis

**Status:** Complete. Tested end-to-end: Part 10130 Op 80 with orientation cubes rendered in ProShop written description.

---

### Project 1: ProShop Bridge — Written Description Push Fix (Session 2)

**Task:** Continued debugging the written description push to ProShop, which had stopped working after ~2 weeks of successful operation.

**What was done:**

1. **Root cause found: URL separator `?` vs `$`** — `proshop_selenium_helper.py` used `?formName=writtenDescription` but ProShop requires `$formName=writtenDescription` for subform pages. With `?`, ProShop loaded the Part details page instead of the written description subform, so CKEditor was never found. This was introduced during the 2026-03-13 "URL fix" session which correctly changed `$`→`?` for `toolDetail` but incorrectly applied the same change to `writtenDescription`.

2. **Content prepend bug fixed** — `_set_ckeditor_content()` was combining new content with existing page content (`html + '<hr>' + existing`). When the page had leftover 250KB test data from the prior debug session, the combined 366KB payload exceeded ProShop's 256KB limit and was silently discarded. Changed to replace content entirely.

3. **Marker verification hardened** — `_save_via_fetch()` was treating a missing verification marker as success ("best-effort"). Now properly returns failure when the marker isn't found in the server response, giving accurate save feedback.

**Files modified:** `ProShopBridge/proshop_selenium_helper.py` (3 changes: URL `$`, content replace, marker verification)

**Key decisions:**
- ProShop URL scheme is inconsistent: `toolDetail` uses `?`, `writtenDescription` uses `$` as path/query separator
- The 256KB server-side limit (found in Session 1) is real but was NOT the reason the tool stopped working — kept size guards as defense-in-depth
- Composite screenshots (1280x720 q65 from Session 1) produce ~108KB payloads, well under 256KB limit
- User confirmed successful end-to-end push: Part 10130 Op 80 with composite screenshots, tool list, WCS data

**Status:** Complete. Written description push working end-to-end from Fusion 360.

---

### Project 25: Agent Exploration — Ecosystem Ritual & Constellation Implementation

**Task:** Implement the Session Close Ritual, Interface Block standard, and TRAXIS_ECOSYSTEM.md constellation file from the P25 session brief designed with Web Claude on 2026-04-11.

**What was done:**

1. **Root CLAUDE.md** (new file at project root) — Four-beat session close ritual, "sir" diagnostic tell, interface block standard definition. Auto-loaded by Claude Code for every session.

2. **P19 Shop Scheduler / CLAUDE.md** (new file) — Created with `## Interfaces` section. Produces: scheduler.db, Flask UI (port 5080), priority/tool-demand APIs, heartbeat. Consumes: ProShop GraphQL, P22 tooling.db (read-only). Contract: reads tooling.db at relative path set in config.py:35.

3. **P22 Tool Assembly Management / CLAUDE.md** (new file) — Created with `## Interfaces` section. Produces: tooling.db, Flask kiosk UI (port 5001), print-label proxy, health endpoint. Consumes: ProShop GraphQL, .traxis.env, Overseer, FocasMonitor monitoring.db, Brother printer. Contracts: P19 reads tooling.db, print_service on port 5002.

4. **scan_projects.py** (modified) — Added `parse_interface_block()` for direct text parsing of `## Interfaces` sections. Added `render_ecosystem_file()` to generate TRAXIS_ECOSYSTEM.md from project_index.json. Fixed session log path mismatch (`SESSION_LOG.md` → `main_session_log.md`).

5. **alerter.py** (modified) — Daily Telegram digest now includes "ACTION ITEMS" section with top 5 open items from project_index.json.

6. **project_index.json** (modified) — Added `interfaces` field to P19 and P22 entries.

7. **TRAXIS_ECOSYSTEM.md** (new file at project root) — Initial render with 26 projects, interface map (P19/P22), 3 critical seams, 20 open items.

**Files created:** `CLAUDE.md` (root), `TRAXIS_ECOSYSTEM.md` (root), `19. Shop Scheduler/CLAUDE.md`, `22. Tool Assembly Management/CLAUDE.md`
**Files modified:** `25. Agent Exploration/scan_projects.py`, `25. Agent Exploration/alerter.py`, `25. Agent Exploration/project_index.json`

**Key decisions:**
- Interface block parsing is pure text (no Haiku call needed) — comma-separated values under Produces/Consumes/Contracts
- Contracts field uses free-text (not structured) since cross-project assumptions are too varied for a rigid schema
- Scanner fix: `SESSION_LOG.md` → `main_session_log.md` to match the actual file name
- Ecosystem file rendered at end of every non-dry-run scan

**Status:** Complete. Ritual active, seed interfaces in place, scanner ready for nightly runs. Remaining projects need `## Interfaces` backfill incrementally.

---

## 2026-04-11

### Project 22: Tool Assembly Management — Inventory Sync Service + Live Push

**Task:** Build a service to push physical cabinet inventory counts from tooling.db to ProShop via GraphQL API, correcting systematic quantity inflation (tools rarely retired, purchases auto-add).

**What was done:**

1. **`inventory_sync.py`** (new file in `tool-kiosk/`) — Standalone sync script:
   - Reads cabinet counts from `tooling.db` (518 of 542 tools counted via kiosk sessions April 6-7)
   - Queries RTAs and work cell pockets from ProShop to get in-use tool counts
   - Ground truth: `cabinet_total + max(rta_count, wc_count)` per tool number
   - Pushes `qtyInBin` (usable = blue+green), `quantity` (total in shop), `purchasingNotes` (yellow/red condition data)
   - Notes format: `[Kiosk 2026-04-07] 2 worn, 1 replace` — replaces prior kiosk lines, preserves other notes
   - `--dry-run` and `--loop N` flags, off-hours gate (18:00-05:00 weekdays, all day weekends)
   - Sync log table in tooling.db tracks what's been pushed to avoid redundant writes
   - 0.1s throttle between API calls, per-tool error handling, timeout retry on large tool fetch

2. **Overseer integration** (`overseer.py`) — Added `InventorySync` service config:
   - Subprocess service with `--loop 3600` (hourly), auto-start enabled
   - Database health validator checks sync log freshness (2h threshold) and push counts

3. **Live run executed** — 485 tools updated, 242 condition notes written, 0 errors:
   - R66: total 4→6 (cab=5 + 1 in work cell), condition notes added
   - A1039: total 4→1 (cab=0 + 1 in work cell — correctly not zeroed)
   - A157: bin qty set, condition notes added
   - 16 tools in kiosk DB not found in ProShop (skipped)

**Key decisions:**
- Always overwrite ProShop quantities with ground truth (no "skip if ProShop higher" rule — ProShop is systematically inflated)
- Use `max(rta_count, wc_count)` per tool to avoid double-counting (RTA in a work cell appears in both queries)
- `qtyInBin` is writable but returns null via API — use `quantity` ("Total in Shop") for comparison reads
- Standalone script sharing `proshop_client.py`, `database.py`, `config.py` with kiosk app (not part of Selenium bridge)

**Status:** Complete. Live push successful. Overseer service config committed. Tool Shortages report in ProShop should show dramatically fewer false shortages.

---

### Project 19: Shop Scheduler — Fix Operation Block Sizing on Drag

**Task:** Operations visually shortened/lengthened when dragged because raw millisecond duration was preserved instead of business hours.

**What was done:**
- Added `businessHoursBetween(start, end)` function to `scheduler.js`
- Updated `handleBlockMove()` to compute business-hour duration of original position, then use `addBusinessHours()` to set the new end time
- Business hours: 5 AM - 6 PM, no weekends (matches existing BH_START/BH_END constants)

**Status:** Complete. Block sizing now consistent regardless of drag position.

---

## 2026-04-10

### Project 27: Accounting Ingest — QBO API Integration + Git Repo Setup

**Task:** Replace the QBO "drop folder" approach with real QuickBooks Online API Bill creation. Also create a git repository for the project collection under Wolfgang's GitHub account.

**What was done:**

1. **`QBOClient` class** (accounting_ingest.py) — Full QBO OAuth2 integration:
   - Token refresh using stored refresh token from `.traxis.env`; automatically saves the rotated token back to the file
   - `get_vendors()` — pulls all QBO vendors (1-hour cache)
   - `fuzzy_match_vendor(name)` — difflib-based matching, same approach as ProShop contact matching
   - `get_default_expense_account()` — finds Cost of Goods Sold or any Expense account for line item billing
   - `create_bill()` — maps extracted invoice fields to QBO Bill API format; uses line items if extracted, falls back to single total-amount line
   - `check_duplicate_bill()` — queries QBO by DocNumber before pushing
   - `_update_env_value()` helper — persists refreshed QBO tokens to `.traxis.env`

2. **Ingest flow change** — Vendor invoices no longer auto-copy to a folder. They go to the PENDING review queue like packing slips, POs, etc. Full Claude extraction happens at ingest time (not just classification).

3. **UI changes:**
   - Contact/vendor panel relabels dynamically: "QBO Vendor" for invoices, "Customer / Vendor (ProShop)" for other docs
   - Vendor search for VENDOR_INVOICE queries QBO vendor list; other doc types still search ProShop contacts
   - Approve button shows "✓ APPROVE & PUSH TO QBO" vs "✓ APPROVE & PUSH TO PROSHOP" depending on doc type
   - After QBO push: status "Uploaded to QBO ✓" + clickable link to bill in QBO sandbox
   - "Open QBO" toolbar button opens QBO bills list in browser
   - QBO duplicate check before pushing (by invoice DocNumber)

4. **Git repository initialized** — `C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects` initialized as a git repo:
   - 194 files committed across locally-synced projects
   - `.gitignore` excludes `.traxis.env`, cloud-only Dropbox folders (not synced on this machine), embedded `git-history/` folders, `.lnk` shortcuts
   - Cloud-only folders (need Dropbox sync before adding): 12 FASData, 14 Workstation Display, 15 ProShop Research, 17 COTS Kiosk, 18 Notifier, 19 Shop Scheduler, 20 Traxis Data, 21 Haas, 22 Tool Assembly, 23 Air Compressor, 25 Agent Exploration, 26 SMT, API Projects, OLD
   - Embedded .git folders in sub-projects renamed to `git-history/` (preserved, not deleted)
   - Pushed to GitHub under Wolfgang's account (repo: `traxis-automation`)

**Files modified:**
- `27. Accounting Ingest/accounting_ingest.py` — v1.1.0 → v1.2.0 (QBOClient + routing changes)
- `.gitignore` — new file (project root)
- `main_session_log.md` — this entry

**Key decisions:**
- QBO sandbox credentials (`sandbox-quickbooks.api.intuit.com`) used — production requires Intuit app review checklist completion
- Expense account selected automatically (COGS preferred); no manual account selection required in UI
- Git repo covers entire project collection, not just project 27 — cloud-only folders will be added incrementally as Dropbox syncs them to each machine

**Status:** QBO Bill creation complete and syntax-verified. Needs live test with a real vendor invoice. Git repo created and pushed.

---

## 2026-04-11

### Project 27: Accounting Ingest — QBO Test, ProShop Mutations, Intuit App Review, Live Testing

**Task:** Test QBO bill creation end-to-end, complete Intuit app assessment for production keys, fix ProShop mutations with full field mapping, and live-test the app with real emails.

**What was done:**

1. **QBO Bill creation verified** — Test bill #145 created in sandbox (Bob's Burger Joint, 2 line items, $247.50). Duplicate detection confirmed. JSON payload fix (no wrapper object).

2. **Intuit app assessment completed:**
   - Created privacy policy, terms, EULA, disconnect pages on GitHub Pages
   - Added `intuit_tid` capture, CSRF verification, `invalid_grant` handling, discovery doc fetch, token revocation, PDF attachment upload
   - Added `QBO_ENVIRONMENT` toggle (sandbox/production) in `.traxis.env`
   - Submitted questionnaire — waiting for Intuit approval

3. **ProShop mutations fixed and expanded:**
   - Fixed return field names (`id` not `purchaseOrderId`/`packingSlipId`)
   - Added line item support for Bills, Packing Slips, and Purchase Orders
   - Expanded field mapping for all doc types (PO gets confirmationNumber/date/lead time, PS gets tracking/PO ref, etc.)
   - Tested: PO #263068 and Packing Slip #260411-01 created with line items

4. **Email polling fixes:**
   - Rolling 30-day window + pagination (gets all emails, not just first 50)
   - Image attachment filtering (isInline, contentType, extensions, size)
   - Whitelisted `tom@traxismfg.com` for forwarded accounting docs

5. **UI improvements:**
   - Better classify prompt (Traxis-specific Customer PO vs Vendor PO distinction)
   - Re-extract button, UPLOAD_FAILED in Pending filter, combobox dark theme fix

6. **ProShop API permission discovery:**
   - API clients map to ProShop users (AccountingConnector = User #010)
   - Two permission layers: OAuth scope AND user module permissions
   - User 010 had read-only defaults — granted full write but `addCustomerPo` still failing — escalated to ProShop support

**Key discovery:** ProShop API has two permission layers. OAuth scope gates endpoint access. User #010 permissions gate operations. Both must be configured.

**Status:** QBO pipeline fully tested (sandbox). ProShop PO + Packing Slip working. Customer PO blocked on ProShop permissions — awaiting support. Intuit production keys pending.

---

## 2026-04-08

### Project 19/22: Shop Scheduler — Tool Demand Checker + Overseer Integration

**Task:** Cross-reference tool demand (from operation_tools in scheduler DB) against physical inventory (from tool_inventory in kiosk DB) and flag shortages on the Tools page. Also add Shop Scheduler to the Overseer for auto-start and health monitoring.

**What was done:**

1. **`/api/tool-demand` endpoint** (app.py) — Queries all tools needed by active, non-hidden, incomplete operations from `operation_tools`, aggregates by tool_number (with op count + WO list), then reads the kiosk's `tooling.db` in read-only mode (`sqlite3.connect("file:...?mode=ro", uri=True)`) to look up `qty_available` (blue + green) and `min_quantity`. Classifies each tool as `out_of_stock` (qty=0), `low_stock` (qty ≤ min), `ok`, or `not_in_inventory`. Sorts flagged items first. Gracefully handles missing/locked kiosk DB.

2. **Tool Shortages UI** (tools.html) — New collapsible section above "Work Orders Needing Tools". Color-coded rows: red (out of stock), orange (low stock), gray (not tracked in inventory). Each row shows tool number, description, status badge, qty available, op count, and WO numbers (truncated at 3). Auto-refreshes every 30s. Shows warning banner if kiosk DB is unavailable.

3. **Config: `KIOSK_DB_PATH`** (config.py) — Absolute path to kiosk's tooling.db computed relative to scheduler dir (`../22. Tool Assembly Management/tool-kiosk/data/tooling.db`).

4. **Overseer: ShopScheduler service** (overseer.py) — Added `SHOP_SCHEDULER_DIR` path, `ShopScheduler` service config (process type, port 5080, `auto_start: True`, HTTP health check at `/api/health`), `validate_shop_scheduler()` validator (checks `api_reachable`, `token_valid`, reports active WO count + uptime), registered in `VALIDATORS` dict.

**Files modified:**
- `19. Shop Scheduler/config.py` — Added `KIOSK_DB_PATH`
- `19. Shop Scheduler/app.py` — Added `import os`, `/api/tool-demand` endpoint
- `19. Shop Scheduler/templates/tools.html` — Tool Shortages section + JS
- `1. Proshop Automations/Overseer/overseer.py` — ShopScheduler service + validator

**Key decisions:**
- Read-only SQLite connection to kiosk DB avoids write locks on Dropbox-synced file
- Tools classified as `not_in_inventory` when kiosk DB is available but tool isn't found (vs `unknown` when DB is unreachable)
- Overseer will auto-start scheduler on boot; needs Overseer restart to pick up new config

**Status:** Code complete, syntax verified. Needs Overseer restart and scheduler launch to test live.

---

## 2026-04-07

### Project 22: Tool Assembly Management — Remote Printing, Touchscreen UI, Overseer Update

**Task:** Get remote label printing working from the kiosk, improve touchscreen usability (fonts too small, no keyboard hint), and update the Overseer to monitor the remote print service.

**What was done:**

1. **Remote printing fixed** — The print service on .242 (PT-P700) was never reachable remotely because Windows Firewall was blocking port 5002. Ran `open_print_service_firewall.bat` as admin on .242, started print service via `start_print_service.bat`. First successful remote print: 2x H-0026 labels from MainPC to .242's PT-P700 via b-PAC. Startup folder shortcut already existed for auto-start on boot.

2. **Font sizes increased for touchscreen** — Base font 18px→22px (all rem values scale). Form inputs height 48→56px, font 1rem→1.05rem. Form labels 0.9→1rem. Nav buttons 0.9→1rem. Scan hints 0.9→1rem. Badges 0.75→0.85rem. Table text, inventory descriptions, color tags all bumped. 600px breakpoint floor 16→19px.

3. **Keyboard hint added** — "Use keyboard to type in fields below" pill displayed at the top of all form panels (Register RTA, Install Cutter, Assign to Machine, Add Inventory Tool). Styled as subtle gray rounded bar.

4. **Overseer updated for remote print service** — Changed `LabelPrintService` config from `service_type: "process"` with localhost health check to `service_type: "remote"` pointing at `http://10.1.1.242:5002/api/health`. Removed `start_cmd`/`working_dir`, set `auto_start: False`. Added `"remote"` guards in `start_service()` and `stop_service()` dispatch so Overseer won't attempt to start/stop/restart a remote service. Updated `startup()` to monitor remote services like Windows services (just health-check, no process management).

**Architecture clarification:** Three machines — Kiosk PC (.142), MainPC (.71), Print PC (.242 w/ PT-P700). PT-D610BT is on .178 (not set up). Config already pointed to `http://10.1.1.242:5002`.

**Files modified:** `tool-kiosk/static/style.css`, `tool-kiosk/templates/kiosk.html`, `1. Proshop Automations/Overseer/overseer.py`

---

## 2026-04-06

### Project 19: Shop Scheduler — Scheduler Fixes Batch

**Task:** Three bug fixes: (1) completed WOs still showing as blocks on the board, (2) no work center mappings for MILL-X-CAT40/MILL-X-PROBE so the suggestion engine couldn't route by machine capability, (3) T2 lathe ops appearing on the "needs tools" list when tooling can't be staged for the lathe.

**What was done:**
- **Fix 1:** Added `w.status = 'active'` filter to `get_schedule_blocks()` so the API never returns blocks for completed WOs. Added cleanup in `full_sync()` to delete non-locked, non-complete blocks when WOs are marked complete.
- **Fix 2:** Added `MILL-X-CAT40` and `MILL-X-PROBE` to `work_center_map` (migration + seed). Updated suggestion engine with `CAT40_MILL_IDS` (mill-1,2,3,6,8) and `PROBE_MILL_IDS` (mill-1,2,3,8) so ops route to capable machines only.
- **Fix 3:** Added `work_center != "T2"` filter to the needs-tools list builder in `app.py`.

**Files:** `database.py`, `sync.py`, `suggest.py`, `app.py`

---

### Project 25: Agent Exploration — Overseer Watchdog + Audit Alert Redesign

**Task:** (1) Add the Overseer (Flask dashboard, port 8060) as a monitored subprocess to `service_wrapper.py` so it auto-restarts on crash — it had been down silently for a full week after March 30. (2) Redesign the Telegram audit notifications from noisy hourly "Score: X%" messages to a useful daily digest with actionable items.

**What was done:**

**1. Added Overseer watchdog to `service_wrapper.py`:**
- Added constants: `OVERSEER_PYTHON` (system Python at `Programs\Python314`), `OVERSEER_SCRIPT` (path to `1. Proshop Automations/Overseer/overseer.py`), `OVERSEER_DIR`
- Why separate Python path: Flask and requests are installed under the system interpreter, not necessarily the one running service_wrapper
- Added `start_overseer()` — launches overseer.py as subprocess, logs stdout/stderr to `logs/overseer_stdout.log`, sets cwd to Overseer directory
- Added `check_overseer()` — polls `.poll()`, restarts with exponential backoff (30-300s) if crashed, resets backoff after 5 min sustained uptime
- Added `stop_overseer()` — `.terminate()` with 10s timeout, then `.kill()`
- Integrated into all control points: `_become_leader()`, `_leader_tick()`, `stop_all()`, `get_status()` (heartbeat now includes overseer status + PID)
- Follows the exact same pattern as the existing telegram_bot management

**2. Redesigned Telegram audit alerts (`alerter.py` — full rewrite):**
- **Before:** Every audit run (hourly) could send "Score: 25.9%" with pass/warn/fail counts — not actionable, too frequent
- **After:** Two alert modes:
  - **Daily digest** (once per day, first run after 6 AM): Overdue WOs by name, overrun rate + worst offenders, readiness issues (uncertified ops, missing NC programs, outstanding material POs), machine health (stale FOCAS connections, alarm counts), summary counts
  - **Immediate alerts**: Only for genuinely new system **errors** (API down, DB unreachable) that weren't in the previous run — not for every new failure/warning
- Uses `logs/last_digest.json` state file to track when last digest was sent
- Hourly audit still runs for data collection and trending — only notification behavior changed

**3. Added `get_run_metrics()` to `audit_db.py`:**
- New method to retrieve all metrics for a given run_id as a dict `{name: (value, context)}`
- Needed by the daily digest to pull actionable metrics like `overrun_rate_pct`, `overdue_work_orders`, `outstanding_material_pos`, etc.

**Files modified:**
- `25. Agent Exploration/service_wrapper.py` — Overseer subprocess management (start/check/stop + all integration points)
- `25. Agent Exploration/alerter.py` — Full rewrite: daily digest + critical-only immediate alerts
- `25. Agent Exploration/audit_db.py` — Added `get_run_metrics(run_id)` query method

**Files NOT modified:**
- `1. Proshop Automations/Overseer/overseer.py` — untouched, just managed as a subprocess now
- `25. Agent Exploration/run_audit.py` — untouched, still calls `send_audit_alert()` with same signature
- The VBS/Startup shortcut for Overseer — left in place as fallback until wrapper approach is verified

**Key decisions:**
- Overseer uses system Python (`Programs\Python314\python.exe`) not `sys.executable`, because Flask/requests are installed there
- Daily digest fires once per day at first audit run after 6 AM — simple and predictable
- Immediate alerts restricted to severity="error" only (system health failures), not "failure" or "warning" — avoids noise from known data quality issues
- Audit still runs hourly for data trending — decoupled notification frequency from collection frequency

**Verification steps (to be done):**
1. Stop the currently-running manual Overseer instance
2. Restart the service_wrapper (or let its leader tick pick up the new code)
3. Confirm the Overseer starts and port 8060 responds
4. Kill the Overseer process manually — confirm auto-restart within 30s
5. Check `service_heartbeat.json` — confirm overseer status appears
6. Wait for next audit run — confirm no hourly Telegram message (only daily digest)

### Project 22: Tool Assembly Management — Cleanup, Inventory Import, Touchscreen

**Task:** Clean up the tool-kiosk directory, import ProShop tool library into inventory, fix touchscreen, and get Full Inventory sessions working properly.

**What was done:**

1. **Directory cleanup** — Moved 11 non-essential files (one-time scripts, debug utils, old shortcuts) to `tool-kiosk/old/`. Created `INSTRUCTIONS.txt` with start/stop/restart procedures.

2. **Touchscreen fix** — Diagnosed touch not working on Kiosk PC. Added `/touch-test` diagnostic page to Flask. Confirmed it was a Windows display-touch mapping issue (not code). Created `Fix Touchscreen.md` guide.

3. **ProShop tool import** — Fixed `get_all_tools()` in `proshop_client.py` (removed unsupported `page` arg, set `pageSize=1000`). Imported 907 tools, deleted 365 auto-generated D10xxx drill catalog entries. Added D10xxx filter to import endpoint. 542 tools now in inventory.

4. **Inventory sort order** — Changed all 3 inventory queries in `database.py` from alphabetical to numeric sort by suffix: `ORDER BY CAST(REPLACE(LTRIM(...), '-', '') AS INTEGER)`. Tools now go A1, R2, O3, O4... instead of A1, A10, A1002...

5. **Inventory session management** — `startFullInventory()` now reuses open sessions instead of creating duplicates. Added Abandon button + `POST /api/inventory/session/<id>/abandon` endpoint. Cleared 4 orphaned sessions.

6. **Browser caching disabled** — Added `@app.after_request` with `Cache-Control: no-cache` headers. Removed `?v=N` cache busters from templates.

7. **Chrome crash loop** — Identified 36+ consecutive Chrome crashes from `kiosk_launcher.log`. Fix: delete corrupted `%LOCALAPPDATA%\ToolKioskChromeProfile`.

8. **STOP KIOSK.bat** — Added fallback methods to close the launcher console window.

**Lesson learned:** Dropbox sync + Python `__pycache__` is unreliable — the Kiosk PC can run stale bytecode even when .py files are synced. Must delete `__pycache__` on the Kiosk PC after code changes.

**Files modified:** `app.py`, `database.py`, `proshop_client.py`, `kiosk.js`, `kiosk.html`, `base.html`, `STOP KIOSK.bat`. New: `INSTRUCTIONS.txt`, `Fix Touchscreen.md`, `SESSION_LOG.md` (project-level).

---

## 2026-04-02

### Project 12: FASData Implementation — TraxisProgramManager Testable Architecture

**Task:** Extract all non-Fusion logic from the 1404-line monolithic Fusion 360 add-in (TraxisProgramManager.py) into a testable `tpm/` Python package, add comprehensive pytest coverage, and wire the monolith to use the package.

**What was done:**

**1. Created `tpm/` package (5 modules, ~610 lines):**
- `tpm/config.py` — Dropbox root detection, paths, credential loading
- `tpm/proshop.py` — OAuth token caching, GraphQL client, customer PN lookup
- `tpm/naming.py` — OP numbers, versioning, header parsing
- `tpm/fileops.py` — File discovery, copy, auto-catch, folder lookup
- `tpm/wcs.py` — WCS formatting (pure string logic, zero dependencies)

**2. Created test suite (52 tests across 6 files, all passing in 0.18s):**
- `test_auto_catch.py` (8 tests) — Recent file copy, PART FILES copy, no recent files, self-copy skip, empty folders, multiple files, partial failure, ProShop down graceful degradation
- `test_naming.py` (15 tests) — OP formula (setup 1->60, 2->70, 6->110), program numbers, header parsing, version increment with has_changes flag
- `test_fileops.py` (6 tests) — Folder lookup by customer/part PN, file copy
- `test_proshop.py` (6 tests) — Token caching/refresh, missing creds, customer PN lookup
- `test_config.py` (5 tests) — Dropbox detection via info.json, credential loading
- `test_wcs.py` (9 tests) — Stock/model/selected origins, all axis combinations

**3. Rewired monolith to use tpm/ package (1404 -> 915 lines):**
- Added `from tpm import config, proshop, naming, fileops, wcs` at top
- Replaced all internal calls: `get_operation_number()` -> `naming.get_operation_number()`, etc.
- Added `_FusionLogHandler` bridge in `run()` — routes `tpm.*` logging to Fusion console
- Changed `get_next_version(setup=)` -> `get_next_version(has_changes=)` (bool instead of adsk object)
- Changed `find_part_files_folder()` to accept explicit `customer_part_number=` param
- Moved Dropbox-missing error from module-level RuntimeError to `run()` messageBox

**4. Initialized git repo and committed:**
- 3 commits on main: v1.4.0 (initial), CHANGELOG, v1.6.0 (this refactor)
- Git identity configured (Wolfgang / wolf@traxismfg.com)
- `.gitignore` updated with `.pytest_cache/`

**Key decisions:**
- `tpm/` modules use stdlib `logging` (not `adsk.core.Application.get().log()`) — testable outside Fusion
- `DROPBOX_ROOT` defaults to `None` in config (no RuntimeError) — Fusion entry point handles the error with a user-friendly messageBox
- `auto_catch_posted_files()` takes `search_folders` and `delay` params so tests can inject temp dirs and skip sleeps
- Kept all `adsk.*`-dependent code in monolith: 6 handler classes, CAM parameter helpers, WCS/tool extraction, setup naming application

**Status:** Phase 1-3 complete. Phase 4 (Fusion in-app verification) pending — need to test in Fusion: TPM dialog, post, auto-catch.

---

## 2026-04-01

### Project 9: Shop Floor Cameras — BLE Proximity Time Tracking System

**Task:** Research and design an automatic time tracking system that detects which worker is at which machine using proximity sensing, replacing tedious manual time entry in ProShop.

**What was done:**

**1. Evaluated tracking approaches:**
- Discussed camera/gait analysis (too complex for shop environment), RFID tap-based (still requires interaction), and BLE proximity (fully passive — chosen approach)

**2. Created comprehensive research document:**
- `9. Shop Floor Cameras/9.BLE-Proximity-Time-Tracking-System.md`
- Full system architecture: BLE badges on workers → USB BLE dongles on station PCs → MQTT broker → Python proximity engine → database + Grafana dashboard → ProShop integration
- Identified ProShop API blocker: `users:w` scope blocked for API clients (time tracking mutations won't work). Documented 5 workaround options ranked by feasibility
- RSSI calibration strategy for metal shop environment (multipath, shielding, per-machine thresholds)
- Integration plan with existing FOCAS monitoring (combines "who is there" with "what program is running")
- 4-phase implementation roadmap

**3. Simplified hardware approach:**
- Original plan: dedicated BLE gateways ($35/ea) + PoE switch + new cable runs (~$900)
- Discovered each machine already has a Windows PC on the network → use USB BLE dongles ($12/ea) on existing PCs instead
- Pilot cost dropped from ~$900 to ~$42

**4. Mapped full shop network:**
- Documented 9 machine station PCs (Stations A–I) with IPs on 10.1.1.x
- 3 office PCs (TRAXIS PC at 10.1.1.71, plus .242 and .178)
- 5 FOCAS CNC controllers (M2, M3, M6, M8, T2)
- Ran network scan — discovered 17 devices including NVR (surveillance cameras are on the network at 10.1.1.76), Brother printer, Polycom phone, smart thermostat
- Station PCs don't respond to ping/SMB (Windows firewall) but are online — outbound MQTT will work fine

**5. Hardware ordered (Amazon, arriving Monday April 7):**

| Item | Details | Cost | Order # |
|------|---------|------|---------|
| ASUS USB-BT500 BLE 5.0 dongle | + INLAND 10-pack USB drives | $90.75 | (arriving tomorrow) |
| XBOHJOE USB extension cable 6ft | USB 3.0 A male to female | $10.81 | 113-0450575-0218623 |
| Feasycom BLE 5.1 Beacon Cards (x2) | DA14531, IP66, iBeacon, NFC | $41.12 | 113-0264462-9415452 |

**Total pilot cost:** ~$52 (dongle + cable + 2 beacons, excluding USB drives)

**Key findings:**
- T1 (Okuma Lathe) is retired from the shop
- Metal PC cabinets will block BLE signal — USB extension cable routes dongle outside cabinet
- Badge TX power is configurable from the badge side via phone app (not the dongle)
- Feasycom FSC-BP105N chosen: credit card form factor, IP66, 6-year battery, ~$20/ea on Amazon

**Next steps:**
- [ ] Test BLE dongle + beacon at one machine (RSSI readings, range, metal interference)
- [ ] Write Python BLE scanner script using `bleak` library
- [ ] Set up Mosquitto MQTT broker on TRAXIS PC
- [ ] Probe ProShop `timeClockPunchIn`/`addTimeClockPunch` mutations (may bypass `users:w` restriction)
- [ ] Contact Adion Systems about enabling `users:w` scope for API clients

**Files created/modified:**
- `9. Shop Floor Cameras/9.BLE-Proximity-Time-Tracking-System.md` — Full research & architecture document
- `9. Shop Floor Cameras/scan_network.ps1` — PowerShell network scanner
- `9. Shop Floor Cameras/scan_network_tcp.ps1` — TCP port scanner for firewalled PCs

---

## 2026-03-30

### Project 25: Agent Exploration — Service Wrapper with Leader Election Failover

**Task:** Build a single service that runs on both home PC and collector PC (10.1.1.71), using leader election so whichever machine is on runs all services. Replaces individual Windows Task Scheduler entries with one managed wrapper.

**What was done:**

**1. Created `service_wrapper.py` — leader-elected service manager:**
- Heartbeat-based leader election via `service_heartbeat.json` (synced through Dropbox)
- Leader writes heartbeat every 60s; heartbeat considered stale after 180s
- Standby polls every 30s, promotes to leader when heartbeat goes stale
- Priority tiebreaker: `"primary"` outranks `"normal"` (hostname map + env var override)
- Leader manages 4 services:
  - `telegram_bot.py`: long-running subprocess, monitored and restarted on crash with exponential backoff (30-300s)
  - `check_reminders.py`: one-shot every 15 min (300s timeout)
  - `run_audit.py`: one-shot every 60 min (300s timeout)
  - `scan_projects.py`: one-shot daily at midnight (600s timeout)
- Graceful shutdown: catches SIGTERM/SIGINT/SIGBREAK, stops bot subprocess, clears heartbeat
- Atomic heartbeat writes via tmp file + `os.replace()`
- Main loop: 10s tick, manages election state machine (LEADER/STANDBY/SHUTDOWN)
- CLI flags: `--status` (show current heartbeat), `--once` (test one election cycle)
- Logging to `logs/service_wrapper.log` + console

**2. Created `install_service.bat` — NSSM install script:**
- Uses NSSM (Non-Sucking Service Manager) to install as Windows service `TraxisAgent`
- NSSM wraps any executable as a proper Windows service (start on boot, restart on crash, log rotation)
- Auto-detects Python path and NSSM location (`Graf\services\nssm-2.24\win64\nssm.exe`)
- Configures: auto-start, log rotation at 5MB, 10s restart delay, graceful console shutdown (15s)
- Handles existing service (stops + removes before reinstall)
- Prompts to start service after install

**3. Updated CLAUDE.md:**
- Architecture diagram: added service_wrapper.py, install_service.bat, service_heartbeat.json, logs/
- Running section: added service wrapper commands
- Scheduling section: documents wrapper internals + leader election, preserves legacy Task Scheduler entries with "remove after verified" note
- Next steps: marked item 8 (deploy telegram_bot as service) DONE
- Telegram bot section: updated from "needs deployment as service" to "managed by service_wrapper.py"

**4. Bug fixes discovered during live testing:**
- **Heartbeat thread**: One-shot tasks (audit, reminders) run via blocking `subprocess.run()`, which froze the main loop for minutes during audit. Heartbeat could go stale (>180s) and trigger false failover. Fixed by moving heartbeat writes to a background daemon thread that runs independently of the main loop.
- **Bot start order**: Heartbeat was written before bot started, so first heartbeat showed `telegram_bot: stopped`. Fixed by starting bot first, then writing heartbeat.
- **Bot output logging**: Bot subprocess stdout/stderr were sent to DEVNULL, making crash debugging impossible. Changed to append to `logs/telegram_bot.log` with `-u` (unbuffered) flag.
- **Env var pre-resolution**: Child processes (telegram_bot.py, etc.) couldn't see Windows User env vars when launched from Git Bash. Added `_resolve_env_vars()` at wrapper startup -- resolves `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` via PowerShell and sets them in `os.environ` so all children inherit them.
- **Missing package**: `python-telegram-bot` wasn't installed on home PC. Installed v22.7.

**5. Environment setup on home PC (DESKTOP-NU8H1LI):**
- Set `TELEGRAM_BOT_TOKEN` as Windows User env var (retrieved from user)
- Set `TELEGRAM_CHAT_ID` as Windows User env var (retrieved via bot API getUpdates: `8740842967`)
- Set `ANTHROPIC_API_KEY` as Windows User env var (retrieved from Project 10's `.claude/settings.local.json`)

**Testing:**
- `--status` with no heartbeat: correctly reports "No service running"
- `--once`: elected leader, started telegram_bot subprocess, stopped cleanly, cleared heartbeat
- Foreground run: leader elected, bot started (PID alive, 87MB memory), reminders ran, audit ran (exit code 1 = findings, expected)
- Heartbeat thread verified: timestamp refreshed at 60s mark while audit was still blocking main loop (audit took ~4 min)
- Bot crash/restart cycle verified: exponential backoff worked correctly (30s -> 60s -> 120s) when bot couldn't start due to missing package
- After env var fix + package install: bot stays running, heartbeat shows `status=running`

**Key design decisions:**
- NSSM chosen over native win32serviceutil (simpler, already available in Graf\services\)
- Heartbeat file approach (vs network-based) because Dropbox sync is already the shared medium
- Priority map with env var override so collector PC can be set as primary without code changes
- Exponential backoff on bot restart (30s -> 60s -> 120s -> 300s cap) to avoid thrashing
- Heartbeat in daemon thread (like P18 Message Notifier pattern) to stay fresh during blocking operations

**Next steps:**
1. ~~Run `python service_wrapper.py` foreground to verify sustained operation~~ DONE
2. Install via `install_service.bat` (run as Admin), verify `net start TraxisAgent`
3. Get collector PC hostname, add to PRIORITY_MAP as `"primary"`
4. Deploy to collector PC (set env vars, install packages, run install_service.bat)
5. Verify failover in both directions
6. Remove legacy Task Scheduler entries (TraxisAudit, TraxisReminderCheck, TraxisProjectScanner)

---

### Project 17: COTS Tools Crib Kiosk — Touchmonitor Launcher Setup

**Task:** Get the COTS kiosk running again after a break; create a one-click launcher for the touchmonitor PC (10.1.1.70).

**What was done:**

1. **Created `launch_kiosk.bat`** — all-in-one launcher that:
   - Kills any existing kiosk server process
   - Sets the ProShop API secret
   - Starts the Flask server minimized in the background
   - Polls `/api/health` until server is ready (up to 15s)
   - Opens Chrome in kiosk mode (fullscreen, no address bar) to `http://localhost:5000`
   - Located at: `cots-kiosk/launch_kiosk.bat`

2. **Touchmonitor Dropbox sync** — enabled selective sync on the touchmonitor (10.1.1.70) for the `17. COTS - Tools Crib Kiosk` folder so the launcher and all kiosk code syncs over automatically.

3. **Desktop shortcut on TRAXIS PC** — created `COTS Crib Kiosk.lnk` on `C:\Users\TRAXIS\Desktop` pointing to `run_kiosk.bat`. Touchmonitor shortcut to be created manually after Dropbox sync.

**Key decisions:**
- Used `launch_kiosk.bat` (new) vs `run_kiosk.bat` (existing) — old one kept for manual/debug use, new one is the touchmonitor launcher
- Chrome `--kiosk` mode for fullscreen touchscreen experience (Alt+F4 to exit)
- Server starts minimized so the console doesn't cover the kiosk UI

**Status:** In progress — launcher created and syncing to touchmonitor. May need adjustments after first real test on the touchscreen.

---

### Project 22: Tool Assembly Management — Print Service Fix + RTA Label

**Task:** Kiosk PC on shop floor can't print RTA stickers; also print the latest RTA label (H-0024, registered today).

**What was done:**

1. **Diagnosed print connectivity issue:**
   - Both kiosk app (port 5001) and print service (port 5002) run on MainPC (10.1.1.71)
   - Brother PT-P700 is connected and available
   - JavaScript in the kiosk browser was calling `http://10.1.1.71:5002/api/print-label` directly (cross-origin from :5001)
   - Windows Firewall had **no inbound rules** for port 5002 — requests from the shop floor kiosk PC never reached the print service
   - Print service logs confirmed: only `127.0.0.1` health checks, zero remote requests ever

2. **Added firewall rule** for port 5002 (TCP inbound) — still didn't work from kiosk browser (likely additional cross-origin/network issue)

3. **Fixed with print proxy route** — the real solution:
   - Added `/api/print-label` proxy in `app.py` (port 5001) that forwards to `localhost:5002` server-side
   - Updated `kiosk.js` to call `/api/print-label` (same origin) instead of the direct `http://10.1.1.71:5002` URL
   - Bumped JS cache version to v=12 in `kiosk.html`
   - Browser now only talks to port 5001 (already working); server proxies to print service locally — no CORS or firewall issues

4. **Printed H-0024 label** — 2 copies via b-PAC on PT-P700 (CAT40 ER25, tool O51, no RTA# yet)

**Key decisions:**
- Server-side proxy is more robust than firewall rules for cross-port browser requests
- `requests` library used for proxy (already a dependency)

**Status:** Code changes saved. Kiosk app needs restart for proxy route to take effect. Pending shop floor verification.

---

## 2026-03-28

### Project 25: Agent Exploration — Absorb Project 10, Lathe Mapping, Reminders, Telegram Bot, Nightly Scanner

**Task:** Major expansion session. Merged Project 10 (Conversational ProShop) into Project 25's agent.py so there's one NL interface for everything. Built lathe program mapping infrastructure. Added a full reminder system. Built a Claude-powered Telegram bot for phone access to all 25 projects. Created a nightly project index scanner.

**What was done:**

**1. Absorbed Project 10 into agent.py:**
- Added 5 new query methods to `proshop_client.py`: `get_work_order()`, `get_work_order_time_tracking()`, `get_work_order_profitability()`, `get_part()`, `get_part_operations()`
- Added 6 new MCP tools to `mcp_tools.py`: `get_work_order`, `get_work_order_time_tracking`, `get_work_order_profitability`, `get_part_info`, `get_part_operations`, `search_work_orders`
- `search_work_orders` uses Project 10's status mapping (open/active/complete/late/due this week/shipped)
- ProShop server now has 10 tools (was 4)
- Switched `agent.py` interactive mode from stateless `query()` to stateful `ClaudeSDKClient` -- conversation context preserved between turns
- Enriched system prompt with ProShop domain knowledge: WO number format (YY-NNNN), time units (seconds), status aliases, tool selection guide, "keep responses SHORT"
- Renamed Project 10 folder to `10. Conversational Proshop - Retired`, added `RETIRED.md`

**2. Lathe program mapping (legacy T2 programs):**
- Created `lathe_programs.json` -- mapping template for O-number -> ProShop part number
- Added `get_program_mappings()` to `config.py` -- loads and validates mapping file
- Integrated into `get_active_programs` FOCAS tool -- auto-enriches running programs with `mapped_part_number`, `mapped_description`, `mapped_op_number`
- Problem: T2 lathe programs predate TPM header system, stay resident on machine, reused across jobs

**3. Reminder system:**
- Added `reminders` table to `audit_db.py` with methods: `add_reminder()`, `get_pending_reminders()`, `get_due_reminders()`, `mark_reminder_sent()`, `cancel_reminder()`
- Added 3 MCP tools: `schedule_reminder`, `list_reminders`, `cancel_reminder` + new `create_reminders_server()`
- Created `check_reminders.py` -- polls DB every 15 min (Task Scheduler: `TraxisCheckReminders`), sends due reminders via Telegram
- Injected current datetime into agent system prompt via `_make_options()` so Claude knows what time it is

**4. Notes system:**
- Added `notes` table to `audit_db.py` with methods: `add_note()`, `get_recent_notes()`, `search_notes()`
- Used by Telegram bot for thought capture

**5. Telegram bot (`telegram_bot.py`):**
- Claude-powered (Sonnet) Telegram listener using `python-telegram-bot` + `anthropic` SDK
- System prompt dynamically loads `project_index.json` with all 25 projects, pending reminders, recent notes
- 6 Claude tools: `save_note`, `schedule_reminder`, `list_reminders`, `cancel_reminder`, `search_notes`, `get_project_status`
- Slash commands: `/status`, `/notes`, `/reminders`, `/projects`
- Only responds to authorized chat ID (Wolfgang's Telegram)
- Maintains conversation history (30 turns) within a session
- Installed `python-telegram-bot` and `anthropic` pip packages

**6. Project index (`project_index.json`):**
- Surveyed all 25 project folders (3 parallel agents reading CLAUDE.md, README.md, source files)
- Structured JSON: id, name, short description, status, affects, subprojects, waiting_on, needs_from_user
- Cross-reference map: which projects share ProShop API, FOCAS, Fusion add-ins, Overseer
- Action items for Wolfgang extracted: 6 items with effort estimates

**7. Nightly scanner (`scan_projects.py`):**
- Reads per project: CLAUDE.md, README.md, session_log.md (recursive), master SESSION_LOG.md (latest entries), Claude Code MEMORY.md, file modification timestamps
- Uses Claude Haiku (~$0.02/run) to extract status, blockers, needs_from_user
- Updates project_index.json nightly (preserves static fields, refreshes dynamic)
- Rebuilds action items list automatically
- Scheduled at midnight via Task Scheduler: `TraxisProjectScan`
- Supports `--dry-run`, `--project N` for testing
- Checks both C: and D: drives for Claude memory (collector PC uses D:)

**8. Config fix for Git Bash:**
- Added `_get_env()` helper to `config.py` -- falls back to PowerShell `[Environment]::GetEnvironmentVariable()` when Git Bash can't see Windows User env vars
- Applied to `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`
- Set `ANTHROPIC_API_KEY` as Windows User env var (was only in P11's .env file)

**Key decisions:**
- Stateful `ClaudeSDKClient` for interactive mode, stateless `query()` for one-shot (best of both)
- Reuse existing `@traxis_audit_bot` Telegram bot rather than creating a new one
- `audit.db` as single SQLite database for audit results, reminders, AND notes (no new dependencies)
- Claude Haiku for nightly scanning (cheap, handles unstructured CLAUDE.md content)
- Project index is the knowledge base -- bot reads it fresh each message, scanner updates it nightly

**Files created:**
- `lathe_programs.json` -- legacy lathe program mapping template
- `telegram_bot.py` -- Telegram bot with Claude + tools
- `check_reminders.py` -- reminder delivery polling script
- `scan_projects.py` -- nightly project index scanner
- `project_index.json` -- structured index of all 25 projects
- `10. Conversational Proshop - Retired/RETIRED.md` -- retirement notice

**Files modified:**
- `proshop_client.py` -- 5 new query methods
- `mcp_tools.py` -- 9 new MCP tools, 1 new server, status mapping, date parsing
- `agent.py` -- stateful client, enriched prompt, datetime injection, reminders server
- `audit_db.py` -- reminders + notes tables and methods
- `config.py` -- `_get_env()` PowerShell fallback, `get_program_mappings()`, lathe programs path

**Scheduled tasks created:**
- `TraxisCheckReminders` -- every 15 min, sends due reminders via Telegram
- `TraxisProjectScan` -- daily at midnight, refreshes project_index.json

**Status:** Complete. Bot tested and responding on Telegram. Scanner tested. All code syntax-verified.

---

### Project 10: Conversational ProShop — RETIRED

**Task:** Retire Project 10 after absorbing its features into Project 25.

**What was done:**
- All useful features ported: single-WO queries, time tracking, profitability, part lookups, status filtering, conversation memory, domain knowledge
- Folder renamed to `10. Conversational Proshop - Retired`
- Added `RETIRED.md` documenting what was ported and why
- `query_templates.py` preserved as GraphQL field name reference

**Status:** Retired. Absorbed into Project 25 agent.py.

---

## 2026-03-16

### Project 20: Traxis Data — Rene Data Collection Guide, Privacy Setup & Target Hours Pipeline

**Task:** Multiple tasks across two sessions: (1) Create a data collection guide for Rene to gather QuickBooks/bank/utility data for the financial model. (2) Set up data privacy controls so Claude Code can only access anonymized data. (3) Set up Rene's machine with Claude Code. (4) Move token_map.json to shared Dropbox. (5) Build a pipeline to set target hours on 152 ProShop parts missing targets, writing `minutesPerPart` back via the GraphQL API.

**What was done:**

**Rene Data Collection Guide:**
- Created `RENE_DATA_COLLECTION_GUIDE.md` with 14 items across 3 phases (QuickBooks, Bank, Utilities)
- Includes priority table showing items 1-4 unlock 80% of the financial model
- Clear 3-step workflow section: (1) Rene exports raw data to folders, (2) Rene runs `anonymize.py` from terminal, (3) Claude Code analyzes anonymized output
- FASData section deferred (still under development per Project 12)
- Created `RENE_SETUP.md` with step-by-step setup: Python, Node.js, Claude Code installation, Dropbox verification, anonymizer test

**Data Privacy Controls:**
- Created `20. Traxis Data/.claude/settings.json` with deny rules blocking Claude Code from reading `quickbooks/`, `bank/`, `utilities/`, `token_map.json`, and `.env` files
- Allow rules for `anonymized/`, `proshop/`, `*.md`, `*.py`, `*.csv`
- Bash deny rules for `*token_map*`, `*quickbooks/*`, `*bank/*`, `*utilities/*`
- Updated `CLAUDE.md` with mandatory data privacy section

**Token Map Migration:**
- Moved `token_map.json` from `C:\Users\TRAXIS\Documents\` to `20. Traxis Data/` (Dropbox-synced between machines)
- Updated 6 scripts that referenced the old path:
  - `anonymize.py`, `proshop_pull.py`, `merge_fresh.py`, `proshop_merge_and_analyze.py`, `proshop_pull_gaps.py`, `proshop_pull_invoices.py`
- All now use `SCRIPT_DIR / "token_map.json"`
- Updated `MEMORY.md`, `setup.md`, `CLAUDE.md` with new location

**Target Hours Pipeline — Discovery & Architecture:**
- Investigated where target hours live in ProShop: Part Operations → `minutesPerPart` field (not on Part or WorkOrder directly)
- WO's `hoursCurrentTarget` = sum of all operation `minutesPerPart` values (read-only via API, computed from ops)
- Discovered `updatePartOperation` mutation: takes `partNumber`, `opNumber`, `opDefinition: { minutesPerPart: String }` — arg name is `opDefinition` NOT `data`
- Discovered `updatePart` mutation: takes `partNumber`, `data: { notes: String }` — arg name IS `data`

**Target Hours Pipeline — `best_targets.py` Rewrite (critical fix):**
- **Bug caught by Wolfgang:** Original script computed targets from total WO hours without dividing by quantity. Since `minutesPerPart` is per ONE part and WOs have varying quantities (1 to 1,000), targets were completely wrong.
- Rewrote to normalize by quantity: `hrs_per_part = actual_hours / qty_ordered` for each WO
- P25+10% methodology applied to per-part values (not total WO hours)
- Output column `Best Min/Part` maps directly to ProShop's `minutesPerPart`
- Excludes CUST_018 (internal work — fixtures, jigs, tooling mods)
- Skips WOs with zero/missing quantity data (3 WOs)
- Result: 127 parts analyzed, 35 high confidence (5+ runs), 22 medium (3-4), 70 low (1-2)

**Target Hours Pipeline — `set_targets.py` (new script):**
- Three modes: `--query` (read-only), `--preview` (show mutations), `--execute` (write to ProShop)
- `--query`: Pulls all 1,014 parts with nested operations from ProShop, matches against `best_targets_list.csv` using reverse token map, outputs `proshop/part_operations_audit.csv`
- Even distribution: total minutes per part split evenly across operations (placeholder for Wolfgang to refine per-op)
- `--execute`: Runs `updatePartOperation` on each op + `updatePart` to add conspicuous note ("AUTO-SET TARGETS [...]: Per-part target: X min distributed evenly... Per-op breakdown needs manual refinement")
- Safety: requires typing "YES" to proceed, 0.5s delay between mutations, logs every result to CSV
- Result: 118 parts matched in ProShop, 7 not found (likely deleted/archived)

**Bugs Fixed:**
- `sys.stdout` buffering: background Python produced no output — fixed with `line_buffering=True` + `python -u`
- `workCenter` field is an object type, not scalar — removed from query (ProShop returned "Expected a selection on object field")
- `company` field same issue — removed
- No exit condition on persistent failures — added `if total_records is None and page_start > 200: break`
- Retry loop didn't show error messages — added extraction of `result["errors"][0]["message"]`

**Key decisions:**
- Distribute target hours evenly across operations as a starting point — Wolfgang refines per-op breakdown manually
- Add conspicuous note to each part so operators know targets are auto-set placeholders
- CUST_018 excluded from analysis — internal fixtures/jigs, not billable production work
- Privacy enforced at two layers: `.claude/settings.json` deny rules (hard) + `CLAUDE.md` instructions (soft) + anonymizer workflow (data transformation)

**Files created:**
- `20. Traxis Data/RENE_DATA_COLLECTION_GUIDE.md` — 14-item data collection guide with 3-step anonymization workflow
- `20. Traxis Data/RENE_SETUP.md` — Machine setup instructions for Rene (Python, Node, Claude Code)
- `20. Traxis Data/.claude/settings.json` — Data privacy deny/allow rules
- `20. Traxis Data/set_targets.py` — 3-phase target hours pipeline (query/preview/execute)

**Files modified:**
- `20. Traxis Data/best_targets.py` — Rewritten for per-part normalization (hrs/qty), CUST_018 exclusion
- `20. Traxis Data/anonymize.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_pull.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/merge_fresh.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_merge_and_analyze.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_pull_gaps.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_pull_invoices.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/CLAUDE.md` — Added mandatory data privacy section, updated token_map location
- `20. Traxis Data/setup.md` — Updated token_map location
- `MEMORY.md` — Updated token_map location to Dropbox path

**Files generated:**
- `20. Traxis Data/best_targets_list.csv` — 127 parts with per-part suggested targets (Best Min/Part column)
- `20. Traxis Data/proshop/part_operations_audit.csv` — 118 matched parts with operation structure + proposed values

**ProShop API discoveries:**
- `minutesPerPart` on Part Operations is the correct field for setting target hours
- `updatePartOperation(partNumber, opNumber, opDefinition: { minutesPerPart })` — returns Boolean
- `updatePart(partNumber, data: { notes })` — returns Part object
- `workCenter` and `company` are object types requiring sub-selection (not scalar)
- Part `operations` supports nested pagination: `operations(pageSize: 50, pageStart: 0)`

**Status:** Pipeline ready through `--query`. Audit CSV generated with 118 parts. Next steps: (1) anonymize audit CSV, (2) Wolfgang reviews low-confidence parts (70 with only 1-2 runs), (3) run `--preview` to inspect mutations, (4) run `--execute` after approval.

---

## 2026-03-26

### Project 19: Shop Scheduler — Overlap Prevention, Board Filters, Business Hours, Material Type

**Task:** Implement no-stacking overlap prevention, rich board filters, business-hours-only scheduling, and material type filter.

**What was done:**

**Overlap Prevention (backend + frontend):**
- Added `OverlapError` exception class and `_check_overlap()` query to `database.py`
- `create_schedule_block()` and `update_schedule_block()` reject overlapping non-complete blocks on same machine (HTTP 409)
- Frontend shows toast notification when drag/drop/resize is rejected due to overlap
- No stacking allowed, period — even same-WO side 1/side 2 ops

**Rich Board Filters (collapsible filter bar):**
- Collapsible filter bar below header with toggle button
- Text search (WO#, part name, op name, customer)
- Customer dropdown (auto-populated from events)
- Status checkboxes: Scheduled, Running, Complete (defaults: Scheduled + Running)
- Urgency checkboxes: Past Due, Urgent, Normal, No Date (all checked by default)
- Material status dropdown: All / Ready / Not Ready
- Tools status dropdown: All / Ready / Not Ready
- Clear Filters button
- Filter state persisted to localStorage across page reloads
- Badge shows count of hidden events when filters active
- Client-side filtering via `allEvents` array + `applyFilters()` → `ec.setOption('events', filtered)`

**Material Type Filter (full ProShop → UI chain):**
- Added `part { materialPlainText }` to ProShop `get_work_orders()` GraphQL query
- Added `material_type TEXT` column to `work_orders` table (auto-migrated via `_migrate()`)
- Sync extracts `materialPlainText` from part data, stores in `work_orders.material_type`
- Included `w.material_type` in block and operation SQL queries
- Added `material_type` to event `extendedProps` in API response
- New "All Materials" dropdown filter populated dynamically from events (aluminum, stainless, plastic, etc.)

**Business Hours & Weekend Handling:**
- Config: `BUSINESS_HOURS_START=5` (5 AM), `BUSINESS_HOURS_END=18` (6 PM)
- EventCalendar: `slotMinTime: '05:00:00'`, `slotMaxTime: '18:00:00'`
- Created `_add_business_hours()` helper in `suggest.py` — spreads op duration across business hours only, skipping nights and weekends
- Updated `_find_next_gap()` to use business-hours-aware duration calculation

**Clear Board Button:**
- Added `POST /api/blocks/clear` endpoint — deletes all non-locked, non-complete blocks
- Button in header with confirmation dialog, shows count of deleted blocks

**Readiness Key:**
- Small legend in filter bar showing what the 4 readiness dots mean: Prog, Mat, Tools, Machine

**Version Label:**
- Added `v0.5` label in header for quick visual confirmation of which version is running

**Bug Fixes (10+):**
- `_parse_dt()` infinite recursion — was calling itself instead of `datetime.fromisoformat()` (caused /api/suggestions 500 error)
- Python 3.14 timezone-aware datetimes from "Z" suffix — `_parse_dt()` strips timezone info
- `__pycache__` with stale cpython-313 AND cpython-314 files preventing code updates
- Two-machine conflict: home computer running old scheduler on port 5080 via Dropbox sync — switched to port 5081
- EventCalendar crash from `hiddenDays: [0, 6]` — not supported in resource timeline view, removed
- `flexibleSlotTimeLimits` expanding time range beyond business hours — removed
- Weekend scheduling: ops bleeding through Saturday/Sunday due to raw `cursor + duration_td`
- Auth: tried switching to FusionConnector (403), reverted to FusionToolAuditor (BA16-EFAF-B154)
- DB locks from Dropbox syncing between two machines

**Files modified:**
- `database.py` — OverlapError, _check_overlap, _migrate(), material_type column, updated queries
- `app.py` — overlap error handling (409), /api/blocks/clear, material_type in extendedProps
- `proshop_client.py` — added `part { materialPlainText }` to WO query
- `sync.py` — extract and store material_type from ProShop part data
- `suggest.py` — _parse_dt fix, _add_business_hours, _find_next_gap business-hours-aware
- `config.py` — business hours 5AM-6PM
- `templates/scheduler.html` — filter bar, toast container, clear board, readiness key, version label, material type dropdown
- `static/scheduler.js` — allEvents tracking, full filter system with localStorage, toast notifications, clearBoard, material type filter, calendar business hours
- `static/style.css` — filter bar styles, readiness key, toast styles, version label

**Key lessons:**
- When writing helper functions, don't accidentally call the function itself (recursive bug in `_parse_dt`)
- Python 3.14 `datetime.fromisoformat("...Z")` creates tz-aware datetimes — always strip with helper
- Dropbox + two machines running same app = port conflicts, DB locks, stale code served
- `hiddenDays` and `flexibleSlotTimeLimits` crash EventCalendar in resource timeline view
- Delete `__pycache__` when switching Python versions or after code changes

**Status:** All features implemented. Material type needs verification after ProShop sync (field name `materialPlainText` may differ). Auto-schedule flow needs end-to-end test on shop-connected machine.

---

### TPM Bug Fix — Dynamic Dropbox Path Detection

**Task:** Fix `FileNotFoundError: [WinError 3] The system cannot find the path specified: 'D:\'` crash in TraxisProgramManager when running on a machine without a D: drive.

**Root cause:** `NC_PROGRAMS_ROOT` and `PART_FILES_ROOT` were hardcoded to `D:\Dropbox\...` in `TraxisProgramManager.py` (line 68-69). Machine has Dropbox on C: drive.

**What was done:**
- Added `_find_dropbox_root()` helper that reads `%LOCALAPPDATA%/Dropbox/info.json` (maintained by Dropbox on every machine) to auto-detect the Dropbox folder path
- Replaced hardcoded `D:\Dropbox\...` paths with `os.path.join(_DROPBOX, ...)` so TPM works on any machine regardless of drive letter or Dropbox location
- Raises a clear `RuntimeError` at add-in startup if Dropbox isn't installed, instead of failing deep in `makedirs`

**Files changed:**
- `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\TraxisProgramManager\TraxisProgramManager.py` — replaced constants with dynamic detection

---

## 2026-03-25

### Project 19: Shop Scheduler — Readiness Lights, Tool-Aware Scheduling, Part Drawing, Fusion ToolRenumber

**Task:** Implement 4-phase plan: readiness indicators per operation, tool-aware machine assignment, part drawing in side panel, and Fusion 360 tool renumbering add-in.

**What was done:**

**Phase 1 — Data Foundation (all complete):**
- Added 3 new DB tables: `readiness`, `machine_pockets`, `operation_tools`
- Program readiness: auto-computed per WO (checks if Programming op is complete)
- Material readiness: queries `vendorPOs` with `poType=Material`, checks `receivedDate` on `poItems`
- Machine pocket sync: pulls pocket layouts from ProShop for all 9 active machines
- Operation tool requirements: syncs `partOperation.tools` for all active WOs

**Phase 2 — Readiness UI (all complete):**
- 4 colored dots per operation: Program (green/red), Material (green/red), Tools (green/yellow), Machine (green/gray)
- Dots appear in backlog panel, Gantt blocks (bottom-right corner), and side panel (large with labels)
- Manual "Mark Tools Staged" toggle button in side panel
- API: enriched `/api/operations` and `/api/blocks` with readiness data, added `POST /api/operations/<id>/tools-ready`

**Phase 3 — Tool-Aware Scheduling (complete):**
- `_tool_overlap_score()` compares op tools vs machine pockets by tool_number AND out_of_holder (0.1" stickout tolerance)
- When multiple mills have similar load (within 2h), uses tool overlap as tiebreaker
- Suggestions include tool_match/tool_total fields, shown as "(X/Y tools)" badge on suggestion chips
- Updates `machine_ready` flag in readiness table

**Part Drawing in Side Panel (complete, untested on ProShop network):**
- `get_part_drawing(wo_number)` queries `part.partFiles.partfile` (primary drawing), falls back to `workOrderFiles`
- `/api/workorders/<wo>/drawing` endpoint returns URL + type (pdf/image)
- Side panel async-fetches drawing when opened, shows as iframe (PDF) or img tag
- Could not test — this computer has no ProShop network access (ping to 160.1.144.190 times out)

**Phase 4 — Fusion ToolRenumber Add-in (created, NOT tested):**
- 4 files in `1. Proshop Automations/ToolRenumber/`: ToolRenumber.py, .manifest, pocket_client.py, renumber_engine.py
- Reads target machine's pocket layout from ProShop, matches CAM tools to pockets, renumbers
- User expressed caution: "We need to be careful about implementing a tool number changer into the fusion world"
- Added to `setup_fusion_addins.bat`

**Config change:**
- `config.py` updated to hardcode BA16-EFAF-B154 client credentials as defaults (no env vars needed)

**Testing:**
- Created `test_readiness.py` with 10 backend tests — all 10 passing
- Live data: 159 readiness rows, 59 program ready, 210 machine pockets (83 with tools) across 9 machines, 1248 operation tool records across 160 operations
- Material readiness showed 0/159 ready because vendorPOs query was broken during initial sync — now fixed, needs re-sync on connected machine

**Bugs found and fixed (10 total):**
1. `active_numbers` used before defined in sync.py — reordered code
2. `poNumber` field doesn't exist on vendorPOs — removed (also `vendorPOId` doesn't exist)
3. `partPlainText` doesn't exist on vendorPO poItems — removed from query
4. `glotPlainText` requires `rtas` scope we don't have — removed from pockets query
5. `holder` None not subscriptable — added `or ""` guard
6. Unicode arrows crash Windows cp1252 terminal — replaced with `->`
7. FK constraint on test data — added `PRAGMA foreign_keys=OFF` for tests
8. DB locked from unclosed connections — fixed lifecycle
9. `sys.stdout` TextIOWrapper kills PowerShell output — removed, used env var
10. Float precision: `3.1-3.0 > 0.1` — fixed with `round(abs(diff), 4) <= 0.1`

**Files modified:**
- `19. Shop Scheduler/database.py` — 3 new tables, 3 indexes, 2 helper functions
- `19. Shop Scheduler/proshop_client.py` — 4 new methods (vendorPOs, pockets, op tools, part drawing)
- `19. Shop Scheduler/sync.py` — 4 new sync functions called from full_sync()
- `19. Shop Scheduler/app.py` — readiness enrichment on operations/blocks APIs, tools-ready toggle, drawing endpoint
- `19. Shop Scheduler/suggest.py` — tool overlap scoring, tiebreaker integration, machine_ready updates
- `19. Shop Scheduler/config.py` — BA16 client defaults
- `19. Shop Scheduler/static/scheduler.js` — readiness lights (backlog, Gantt, side panel), tools toggle, tool badge, drawing fetch
- `19. Shop Scheduler/static/style.css` — readiness light styles, drawing preview styles
- `19. Shop Scheduler/test_readiness.py` — 10-test validation script (new file)
- `1. Proshop Automations/ToolRenumber/` — 4 new files (Fusion add-in)
- `1. Proshop Automations/setup_fusion_addins.bat` — added ToolRenumber symlink

**ProShop API discoveries (important for future work):**
- vendorPOs: `poNumber`, `vendorPOId`, and `partPlainText` (on poItems) DO NOT EXIST as fields
- workCell pockets: `glotPlainText` requires `rtas` scope (BA16 doesn't have it)
- Part drawing: available via `part { partFiles { partfile { title fileUrl } } }` on workOrder query
- WO files: available via `workOrderFiles(pageSize: N) { records { title fileUrl } }`

**Status:** Backend complete and tested. UI needs visual verification on a ProShop-connected machine. Drawing feature and material readiness need ProShop network to function. Fusion ToolRenumber created but deliberately untested pending user approval.

**Network issue:** Session ran on a non-shop computer. ProShop at 160.1.144.190 is unreachable (DNS resolves but packets drop). Scheduler runs on cached SQLite data only. All ProShop-dependent features (drawing, material readiness re-sync) need testing from the shop network.

**Next steps:**
- Test on shop-connected machine: verify readiness lights display, material readiness populates, drawing loads in side panel
- Verify drawing URLs work in browser (may need ProShop auth — unknown)
- Decide on Fusion ToolRenumber: test in safe environment before production use

---

## 2026-03-23

### Project 1: ProShopBridge — Fix Camera Reset After Screenshot Capture
**Task:** Investigate and fix Fusion 360 viewport switching from orthographic to perspective when pushing written description to ProShop.

**Root cause:**
- `capture_setup_screenshots_base64()` iterates through 4 views (top, front, right, ISO) to take screenshots
- The ISO view is last in the loop and explicitly sets `PerspectiveCameraType`
- The function never restored the original camera state, leaving the viewport in perspective/ISO after returning
- Same issue existed in `_capture_single_screenshot()` (audit screenshots)

**What was done:**
- Added camera save/restore to `capture_setup_screenshots_base64()` — restores `base_camera` (already captured before the loop) after all screenshots are taken
- Added camera save/restore to `_capture_single_screenshot()` — restores in both success and error paths
- Updated `CHANGELOG.md` with bug description, root cause, and fix

**Files modified:**
- `ProShopBridge.py` — camera restoration in both screenshot functions
- `CHANGELOG.md` — new entry for 2026-03-23

**Status:** Complete — committed and pushed to GitHub (`5d82ee5`). Needs testing in Fusion 360.

---

## 2026-03-19

### Project 12: TraxisTransfer — Right Panel Rework (Active WO + Smart Last-Sent)
**Task:** Replace the dual-pane file browser layout with a workflow-driven right panel showing active work order, last-sent program (with version resolution), and CNC program browser.

**What was done:**

**New UI panels:**
- `ui/wo_panel.py` — `WorkOrderPanel(CTkFrame)` showing active WO for selected machine. Queries ProShop asynchronously, displays WO#, Part#, Customer PN. States: loading, WO info, no active WO, ProShop unavailable.
- `ui/last_sent_panel.py` — `LastSentPanel(CTkFrame)` showing the latest version of the last-sent program with embedded SEND button. Shows version hint when newer version exists on disk (e.g., "latest — v3 was last sent"). States: file ready, no history, file missing on disk.

**Service layer additions:**
- `audit_log.py` — Added `get_last_sent_to_machine(conn, machine_id)` — queries most recent successful SEND for a machine, ordered by `timestamp DESC, id DESC` for deterministic tiebreaking.
- `folder_resolver.py` — Added `find_latest_version(file_name, folders)` static method. Parses TPM naming (`{PN}_OP{XX}_v{N}.nc`) to find the highest version of the same PN+OP across resolved folders. Falls back to exact filename match for non-TPM files.

**Layout rework:**
- `app_window.py` — Removed `FileBrowser` and action button bar. Replaced with stacked: WorkOrderPanel (compact) → LastSentPanel (compact, with Send button) → ProgramBrowser (expandable) → Receive button. Removed `_selected_file` tracking (Send is now driven by LastSentPanel's file).
- `main.py` — On machine select: (1) async ProShop WO lookup → WorkOrderPanel, (2) audit log last-sent query + `find_latest_version()` → LastSentPanel, (3) async CNC program listing → ProgramBrowser. After successful send, Last Sent panel auto-refreshes.

**Tests:**
- 84 tests passing (was 72)
- +4 tests for `get_last_sent_to_machine` (most recent send, ignores failures, scoped to machine, returns None)
- +8 tests for `find_latest_version` (higher version, same file, different OP/PN, non-TPM found/missing, TPM missing, multi-folder search)

**Files created:** `ui/wo_panel.py`, `ui/last_sent_panel.py`
**Files modified:** `services/audit_log.py`, `services/folder_resolver.py`, `ui/app_window.py`, `main.py`, `tests/test_audit_log.py`, `tests/test_folder_resolver.py`
**Kept as-is:** `ui/file_browser.py` (still in codebase, no longer in main layout), `ui/program_browser.py` (unchanged lower pane)

**Key decisions:**
- Send button lives inside LastSentPanel (not a separate action bar) — tied directly to the displayed file
- WO lookup runs in background thread; last-sent resolution runs synchronously (just a DB query + disk scan, fast enough)
- `file_browser.py` kept in codebase for potential future use (not deleted)

**Status:** Code complete, all 84 tests pass. Needs visual verification on shop floor with a real Fanuc machine.

### Project 22: Tool Assembly Management — ToolUsageRollup Not Running (Diagnosis & Fix)
**Task:** Investigate why Mill-8 `toolLifeNow` hadn't changed all day in ProShop.

**Root cause:**
- The overseer (PID 24384) had been running since **March 16 at 10:45 AM** — before `ToolUsageRollup` and `LabelPrintService` were added to `SERVICES_CONFIG` in `overseer.py` (added later that day during Session 2).
- Since `SERVICES_CONFIG` is a module-level dict loaded once at import, the running process only knew about the original 6 services. The rollup and print service were invisible to it.
- The rollup's last run was **March 19 at 6:12 PM** (manual invocations during the previous session). No runs occurred all day on March 20.
- Meanwhile, M8 had accumulated **853 cutting samples** across 14+ tools with no one processing them.

**Investigation trail:**
1. Queried `monitoring.db` — confirmed M8 actively cutting (T3, T5, T8, T9 all STRT/MTN)
2. Queried `tooling.db` — `last_processed_at` stuck at `2026-03-19T23:12:51Z`, segments 7/8/9 never processed
3. Checked processes — no `tool_usage_rollup` running, but overseer was alive (PID 24384)
4. Queried overseer API — only 6 services returned, rollup and print service missing entirely
5. Searched 70K-line overseer log — zero mentions of "rollup", confirming it was never in the running config
6. Compared overseer start time (March 16 AM) vs config edit time (March 16 PM) — stale code

**Fix:**
- Killed old overseer (PID 24384), relaunched with `pythonw.exe overseer.py`
- New overseer picked up all 8 services, auto-started ToolUsageRollup with `--loop 300`
- First rollup processed backlog: M8 T8=79 min, T3=62 min, T9=75 min, T5=49 min
- ProShop sync: 14 RTA comments updated, 9 pockets synced, 0 errors

**Observation:** M8 T8 shows 193% peak spindle load — likely a bad `cnc_rdspmeter` reading, worth investigating separately.

**Key lesson:** When adding new services to overseer.py, the overseer process must be restarted to pick up the changes. The Startup-folder launch mechanism doesn't handle config reloads.

**Status:** Fixed. Rollup running in loop mode under overseer, Mill-8 toolLifeNow values now updating in ProShop.

---

## 2026-03-18

### Project 17: COTS Tools Crib Kiosk — Bin Label Audit & Reprint
**Task:** Photograph all COTS cabinet bins, identify which labels match the P-Touch template (QR code + ID + description), and prepare a print batch for the rest.

**What was done:**
- Reviewed 13 photos of the COTS tools crib cabinet and helicoil drawer
- Compared all bin labels against the `COTS P-Touch Label Layout.lbx` template (Helsinki font, COTS_ID + QR code linking to ProShop + description)
- Identified only 5 bins with correct new-style labels: THI-1, THI-6, THI-17, ADH-202, WOHO-199
- Cataloged 55 bins with old-style labels (text-only, no QR code) needing reprints:
  - 24 THI items (thread inserts)
  - 22 TOO items (helicoil tools, from drawer organizer)
  - 7 WOHO items (workholding clamps)
  - 1 PIN item (PIN-173)
  - 1 SHS item (SHS-203)
- Created `COTS_Labels_Print.csv` — filtered version of `COTS_Labels_All.csv` with just the 55 items needing labels
- Opened P-Touch Editor 6 with the template (`C:\Program Files (x86)\Brother\P-touch Editor\6\PtouchEditor6.Wpf.exe`)
- Template uses database merge from CSV (fields: COTS_ID, Description, URL)

**Key decisions:**
- Created separate filtered CSV rather than modifying the master CSV — user switches data source in P-Touch Editor to print only needed labels
- Confirmed all 55 items exist in the master CSV with correct ProShop URLs

**Status:** Print CSV ready, P-Touch Editor opened. User needs to switch data source to `COTS_Labels_Print.csv` and print.

---

## 2026-03-17

### Project 4: Inspection Tool — v2.3.0: ITAR Mode + Password-Protected PDF Support
**Task:** Make the Balloonerator safe for ITAR-controlled drawings and add support for password-protected PDFs.

**ITAR compliance analysis:**
- Identified that the tool sends full PDF drawings to Google Gemini (Vertex AI) and Document AI — both on standard GCP, which is NOT ITAR-compliant
- ProShop (AWS GovCloud) is already ITAR-compliant
- Wrote comprehensive ITAR compliance recommendations document (`ITAR_COMPLIANCE_RECOMMENDATIONS.md`)
- Researched alternatives: PreVeil, MS 365 GCC High, AWS GovCloud S3, Google Assured Workloads

**ITAR mode toggle:**
- New `ITAR` button in toolbar (after Redact), bold red text
- Toggle ON (safe direction): no confirmation, disables EXTRACT button, title bar shows `[ITAR MODE]`
- Toggle OFF (risky direction): confirmation dialog warns about re-enabling cloud extraction
- Guards at 4 locations: `start_processing()`, `load_pdf()`, `_proc_complete()`, `_proc_error()`
- Manual dims, balloon PDF, and ProShop push all remain available in ITAR mode

**Password-protected PDF support:**
- After `fitz.open()`, checks `doc.needs_pass`
- Prompts with masked `simpledialog.askstring(..., show='*')`
- 3 attempts with feedback on remaining tries
- Clean state reset on cancel or failure

**Files modified:**
- `traxis_inspection_tool.py` — ITAR toggle + password support (+94 lines)
- `dist/traxis_inspection_tool.py` — kept in sync
- `ITAR_COMPLIANCE_RECOMMENDATIONS.md` — new file, full compliance analysis

**Status:** v2.3.0 complete. Tool is now safe for ITAR drawings when ITAR mode is enabled.

---

## 2026-03-16 (Session 3)

### Project 22: Tool Assembly Management — RTA Recovery & Naming Convention Fix
**Task:** Recover from RTA rename corruption, re-create RTAs with ProShop's auto-numbered convention, fix tool number casing to match ProShop (uppercase).

**What was done:**

**RTA recovery after rename corruption (from Session 2):**
- Session 2 attempted to rename RTA #18 → "H0001" which corrupted ProShop's RTA module
- RTAs 19/20/21 became inoperable; all RTA-scoped writes failed; user deleted 19/20/21 from ProShop UI
- RTA #22 was created for H-0001 and verified working, but RTAs for other 3 holders were still missing
- Cleared all stale `rta_number` values (18-21) from local assemblies table
- Created 4 fresh RTAs via API: #23 (H-0001/A61), #24 (H-0013/A30), #25 (H-0002/A1), #26 (H-0006/L18)
- Pushed `glot` to all 4 Mill-6 pockets (T2, T4, T6, T7)
- Updated local DB `rta_number` for all 4 assemblies

**Naming convention — uppercase tool numbers to match ProShop:**
- ProShop uses uppercase tool numbers (A61, A30, L18); kiosk was storing lowercase
- Fixed 5 assembly records in local DB: a61→A61, a30→A30, a1→A1, l18→L18
- Updated RTAs 23-26 in ProShop via `updateRTA` mutation (tool field to uppercase)
- Re-pushed tool+glot to all 4 Mill-6 pockets to update display
- Added `.strip().upper()` normalization to `api_install_cutter` and `api_replace_cutter` endpoints
- Added `.upper()` to all 5 ProShop sync points (assign, replace, move, sync-pockets, _ensure_rta)

**Config fix — env var precedence for kiosk OAuth client:**
- `.traxis.env` has `PROSHOP_CLIENT_ID` (FusionConnector) and `TOOLKIOSK_CLIENT_ID` (kiosk) — different clients
- config.py was reading `PROSHOP_CLIENT_ID` which got overridden to the wrong client
- Fixed: config.py now prefers `TOOLKIOSK_CLIENT_ID` / `TOOLKIOSK_CLIENT_SECRET` / `TOOLKIOSK_SCOPE` over generic `PROSHOP_*` vars
- Updated `.traxis.env`: added `rtas:rwdp` to `TOOLKIOSK_SCOPE`
- Re-added `rtas:rwdp` to config.py default scope (was temporarily removed during corruption)

**Files modified:**
- `config.py` — TOOLKIOSK_* env var precedence, rtas:rwdp scope restored
- `app.py` — `.upper()` on tool numbers at all 7 points (2 input endpoints + 5 ProShop sync points)
- `~/.traxis.env` — TOOLKIOSK_SCOPE updated with +rtas:rwdp

**Current DB state:**
- H-0001 (CAT40 ER32, SN B85567) → M6 T2, tool A61, OOH 2.0, **RTA #23**
- H-0013 (CAT40 ER32, SN C37729) → M6 T4, tool A30, OOH 1.5, **RTA #24**
- H-0002 (CAT40 Hydraulic, SN c86458) → M6 T6, tool A1, OOH 0.8, **RTA #25**
- H-0006 (CAT40 ER25, SN c32822) → M6 T7, tool L18, OOH 1.4, **RTA #26**

**Key lesson learned:**
- NEVER rename ProShop RTA numbers — alphanumeric values corrupt the auto-increment and break the entire RTA module. Always use ProShop's auto-assigned sequential integers.

**Status:** Fully recovered. All 4 RTAs active, all Mill-6 pockets synced with uppercase tool numbers. Kiosk config fixed for correct OAuth client.

---

## 2026-03-16 (Session 2)

### Project 22: Tool Assembly Management — Shop Floor Testing, RTA Integration & Usage Rollup
**Task:** Deploy kiosk to shop floor, fix real-world bugs, add holder metadata fields, implement ProShop RTA (Rotating Tool Assembly) integration, and wire up FASData usage rollup.

**What was done:**

**Holder metadata enhancements:**
- Added `holder_length` INTEGER column to holders table (flange to nut face, full inch increments, collet types only)
- Added `serial_number` TEXT column for manufacturer SNs (MariTool lasered serial numbers)
- Added `rta_number` TEXT column to assemblies table for ProShop RTA# linkage
- Added CAT40 ER25 and CAT40 Hydraulic to holder type dropdown
- Changed collet size from free text to grouped dropdown (fractional inch + metric optgroups)
- Holder length shown as dropdown (2"–8"), always visible on register form
- Serial number searchable via `/api/holders/search` endpoint

**Kiosk UX improvements:**
- Register → Install Cutter → Assign to Machine flow (instead of dumping to home screen)
- Done screen shows contextual next actions ("Assign to Machine", "Scan Another")
- "Skip — Assign to Machine" button on install screen for pre-existing assemblies
- Auto-pull ProShop tool description when tool number is entered (debounced lookup)
- `extractHolderId()` fixed to handle H0001 (no hyphen) → H-0001 normalization

**Deployment & caching fixes:**
- Added `TEMPLATES_AUTO_RELOAD = True` to Flask config (template caching with DEBUG=False)
- Added `<meta http-equiv="Cache-Control" content="no-cache">` to base template
- Cache-busting `?v=N` on static JS/CSS files
- Fixed orphaned Flask processes: `kiosk_launcher.py` now has `finally` block to kill child processes + startup cleanup via PowerShell `Get-NetTCPConnection` port killer

**ProShop RTA Integration (major feature):**
- Discovered RTA (Rotating Tool Assembly) is a full CRUD entity in ProShop API
- Added `rtas:rwdp` to OAuth scope (client 8B54-3113-ED6E)
- Introspected `AddRTAInput` fields: tool, holder (RTAHolder type), outOfHolder, collet, comment, status
- Confirmed `glot` IS writable on `WorkCellPocketDataInput` — sets RTA reference on pocket
- Setting `glot` to valid RTA# causes ProShop to auto-fill tool/holder/OOH from RTA record
- Added `create_rta()`, `get_rta()`, `delete_rta()` methods to `proshop_client.py`
- Added `_build_rta_holder()` helper: "CAT40 ER32" + length 3 → "ER32 - 3\""
- Added `_build_rta_collet()` helper: ER32 holder + 1/2 collet → "ER32 1/2\""
- Added `_ensure_rta()`: creates RTA if assembly doesn't have one, stores rtaNumber on assembly
- RTA comment field stores "H-XXXX - Kiosk-managed" for traceability
- **All 5 ProShop sync points updated:**
  - Assign → creates RTA, pushes `glot` to pocket
  - Move → reuses existing RTA, pushes `glot` to new pocket
  - Replace cutter → creates new RTA for new assembly, updates pocket `glot` + zeros wear
  - Remove → clears pocket including `glot`
  - Sync pockets → creates any missing RTAs, pushes all `glot` values
- Created 4 RTA records (18-21) for existing M6 assemblies, verified on ProShop work cell page
- **WARNING:** Attempted to rename RTA 18→"H0001" — corrupted ProShop's RTA module (see Session 3 for recovery)

**ProShop Work Cell sync:**
- Pushed `holder` field (H-XXXX) to all 4 Mill-6 pockets (T2, T4, T6, T7)
- Verified tool numbers + OOH values synced correctly
- Pushed `glot` (RTA#) to all 4 pockets — ProShop auto-filled holder type from RTA records
- Added `glotPlainText` to work cell pocket query for reading back RTA numbers

**FASData Usage Rollup:**
- Fixed split-database issue: tooling.db was at `C:\FASData\` on main PC but `data\` on kiosk PC
- Updated `config.py`: tooling.db always in script-relative `data/` folder (Dropbox-synced)
- Updated `tool_usage_rollup.py` to import config instead of hardcoding paths
- Registered `ToolUsageRollup` service in overseer (process type, database check, --loop 300)
- Added `validate_tool_usage_rollup()` validator — checks log freshness + open segment count
- Test run confirmed: 4 open segments visible, 7,644 M6 monitoring samples available

**Files modified:**
- `database.py` — holder_length, serial_number, rta_number columns + migrations + set_rta_number()
- `app.py` — RTA helpers (_build_rta_holder, _build_rta_collet, _ensure_rta), all 5 ProShop sync points updated with RTA/glot, tool lookup endpoint, holder search endpoint, TEMPLATES_AUTO_RELOAD
- `proshop_client.py` — create_rta(), get_rta(), delete_rta() methods, glotPlainText in pocket query, glot in clear_work_cell_pocket
- `config.py` — tooling.db in data/ folder, rtas:rwdp added to scope
- `kiosk.html` — holder type dropdown (ER25, Hydraulic), collet size dropdown, holder length, serial number, install skip button, done screen next actions
- `kiosk.js` — extractHolderId fix, register→install→assign flow, tool number auto-lookup
- `base.html` — cache-busting, no-cache meta
- `kiosk_launcher.py` — finally block cleanup, startup orphan killer
- `tool_usage_rollup.py` — uses config.py paths
- `overseer.py` — ToolUsageRollup service + validator, TOOL_KIOSK_DIR constant

**Key discoveries:**
- ProShop `glot` pocket field IS writable (schema showed `fields: null` but introspection revealed it)
- Setting `glot` to a valid RTA# auto-fills tool/holder/OOH from the RTA record (powerful!)
- `AddRTAInput` does NOT accept `rtaNumber` — ProShop auto-assigns sequential integers
- `RTAHolder`, `RTAOOHPrefix`, `RTAStatus` types not found via introspection but accept string values
- `holder` pocket field gets overwritten when `glot` is set (ProShop fills from RTA)
- **DANGER:** Renaming RTA to alphanumeric value corrupts ProShop's RTA auto-increment — all subsequent RTA and pocket operations fail when rtas scope is on the token

**Status:** RTA integration complete but naming corruption required recovery (see Session 3). Usage rollup registered with overseer but needs machine running to collect data.

---

## 2026-03-16 (Session 1)

### Project 22: Tool Assembly Management — Full System Build, API Testing & Validation
**Task:** Implement the Tool Assembly Management kiosk system from the multi-phase plan — track CAT40 holders through cutter installation, machine assignment, usage accumulation, and cross-machine movement. Then empirically test and fix all ProShop API integrations.

**What was done:**

**Phase 0-5 scaffolding — 14 files created in `22. Tool Assembly Management\tool-kiosk\`:**
- `config.py` — Port 5001, loads machines.json, ProShop OAuth config
- `database.py` — SQLite schema (5 tables: holders, assemblies, assignments, tool_usage_segments, activity_log), WAL mode, full CRUD
- `proshop_client.py` — OAuth GraphQL client adapted from COTS kiosk, extended with work cell pocket methods (query, update, clear), user/clock-punch queries, work order queries, tool lists
- `app.py` — Flask app with 18 API endpoints covering all phases (holders CRUD, install/replace cutter, assign/remove/move, machine pockets, setup-diff, work-orders, sync-pockets, activity log, health)
- `templates/base.html` — Base template with scanner detector, toast system, health check, orange-themed nav
- `templates/kiosk.html` — 7-screen touch UI (employee, scan, detail, register, install/replace, assign/move, done)
- `templates/machine.html` — Machine pocket map with sync-to-ProShop button
- `templates/log.html` — Activity log viewer with color-coded actions
- `static/kiosk.js` — Full kiosk logic: scanner handling, holder lookup, register, install/replace cutter, assign/move/remove
- `static/style.css` — Touch-friendly CSS with orange (#f97316) accent theme
- `tool_usage_rollup.py` — Reads monitoring.db (read-only), writes cutting stats to tooling.db, supports `--loop 300`
- `kiosk_launcher.py` — Watchdog for Flask + Chrome kiosk mode
- `requirements.txt`, `run_kiosk.bat` — Dependencies and launcher with .traxis.env loading

**ProShop OAuth setup:**
- Created new authorization "ToolAssemblyKiosk" in ProShop admin
- Client ID: `8B54-3113-ED6E`, scope: `toolpots:rwdp+parts:r+workorders:r+users:r+tools:r`
- Added `TOOLKIOSK_*` credentials to `~/.traxis.env`

**machines.json updated:**
- Added `proshop_pot_id` field to all 8 machine entries (T2→"Lathe-2", M2→"Mill-2", M3→"Mill-3", M4→"Robodrill-4", M5→"Robodrill-5", M6→"Mill-6", M7→"Robodrill-7", M8→"Mill-8")

**Overseer integration:**
- Added `ToolAssemblyKiosk` service config to `overseer.py` (port 5001, auto_start=True, HTTP health check)
- Added `validate_tool_assembly_kiosk()` validator (checks API reachable, token valid, reports holder/assignment counts)
- Overseer running — all 6 services healthy including kiosk

**ProShop API bugs found and fixed (10 issues discovered via empirical testing):**

| Issue | Fix |
|-------|-----|
| `workCell(name:)` doesn't exist | `workCell(potId:)` |
| `legacyId` for pocket identification (always null) | `pocketNumber` (Int) — discovered via introspection |
| `toolPlainText` as write field | Write field is `tool` (String) — read=`toolPlainText`, write=`tool` |
| `outOfHolder: None` doesn't clear pocket | `outOfHolder: 0.0` clears it |
| `glotPlainText` requires `rtas:r` scope | Removed from query (scope not available) |
| `woNumber` field on WorkOrder | Correct field: `workOrderNumber` |
| `partOperations` on WorkOrder | Correct field: `ops` |
| `currentOperationNumber` on WorkOrder | Doesn't exist — removed |
| `sequenceDetails` on Part for tool lists | Tools are at `workOrder.ops.partOperation.tools` |
| `wo.get("ops", {})` returns None not {} | Use `(wo.get("ops") or {})` null-safe pattern |

**Key discovery — ProShop pocket input vs output field mapping:**
- Used GraphQL introspection to discover hidden `WorkCellPocketDataInput` fields
- `WorkCellPocketRow` input: `{pocketNumber: Int!, data: WorkCellPocketDataInput}` (NOT `legacyId`)
- `WorkCellPocketDataInput` write fields: `tool`, `outOfHolder` (Float), `holder`, `glot`, `toolWear`, `offset`, `radiusOffset`, `radiusWear`, `toolLifeNow`, `toolLifeWarning`
- Work order tool lists accessed via `workOrder → ops → partOperation → tools` (3 levels deep)

**End-to-end tests — all passed:**
- Register holder H-0001 (CAT40 ER32, 1/2") ✅
- Install cutter (A16, 1/2 EM 4FL, 2.5" OOH) ✅
- Look up holder detail ✅
- Assign to M2 pocket 6 → ProShop shows tool=A16, OOH=2.5 ✅
- Remove from machine → ProShop pocket cleared ✅
- Query work orders for M2 → found WO 26-0027 (R2S1-AD163-001-022, op 56) ✅
- Setup diff (keep/load/remove lists) ✅
- Pocket write + read-back verification (test_pocket_write.py) ✅

**Key decisions:**
- Separate `tooling.db` database (not in monitoring.db) to avoid concurrent writer conflicts with FocasMonitor C# service
- CAT40 holder is the tracked entity — cutters are consumable swap events logged against the holder
- QR encoding: `H-NNNN` format (e.g., H-0047), paper labels for prototyping
- Orange (#f97316) theme to distinguish from blue COTS kiosk
- Usage rollup via Python script (reads monitoring.db read-only) rather than modifying the stable FocasMonitor service

**Status:** Phases 0-3 validated and working. ProShop pocket sync confirmed end-to-end. Work order queries and setup diff pipeline functional. Phase 4 (FASData usage rollup) and Phase 5 (cross-machine movement) code written but untested. Ready for shop floor use with real holders.

---

## 2026-03-13

### Project 17: COTS Tools Crib Kiosk — Scanner Redirect & Overseer Fix
**Task:** Make barcode scans redirect back to kiosk from any page; fix Overseer not showing kiosk

**What was done:**
- Added global barcode scanner detector to `base.html` — detects rapid keystroke pattern (scanner wedge) on non-kiosk pages and redirects to `/?scan=VALUE`
- Updated `kiosk.js` with `pendingScan` flow — stashes scanned item, shows toast, auto-processes after employee selection
- Also added scanner detection on kiosk's employee screen (when scan-input doesn't have focus)
- Restarted stale Overseer process (PID 11912 → new instance) so it picks up COTS Crib Kiosk config
- All 5 Overseer services now showing healthy on `:8060`

**Key decisions:**
- 80ms char timeout threshold to distinguish scanner from human typing
- Scans on quantity/done screens are ignored (only employee and scan screens react)
- Overseer relaunched via `pythonw.exe` directly (same as `run_overseer_silent.vbs`)

**Status:** Complete — ready for shop floor testing

### Project 17: COTS Tools Crib Kiosk — Dedicated Kiosk PC Setup
**Task:** Set up standalone Windows 7 HP touchscreen as a locked-down kiosk terminal

**What was done:**
- Created `kiosk_launcher.py` — watchdog that starts Flask + Chrome kiosk mode, auto-restarts both
- Created `start_kiosk.vbs` — silent launcher for Startup folder, tries Python38/314/313
- Created helper batch files: `fix_python_path.bat`, `install_packages.bat`, `verify_setup.bat`
- Created `KIOSK_PC_SETUP_GUIDE.md` — step-by-step guide tailored for the kiosk PC
- Updated all files for Windows 7 + Python 3.8.10 + `Traxis-COTs` user profile
- Fixed PATH issue: Windows 7 `setx` truncated PATH at 1024 chars, so updated `install_packages.bat` to use full Python path directly (`python.exe -m pip`) instead of relying on PATH
- Flask + requests installed successfully on kiosk PC

**Kiosk PC details:**
- Hardware: HP touchscreen (Lenovo ThinkCentre + HP touch display)
- OS: Windows 7 (6.1.7601)
- User: `C:\Users\Traxis-COTs\`
- Python: 3.8.10 at `C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\`
- Dropbox syncing folder 17

**Key decisions:**
- Python 3.8.10 is the last version supporting Windows 7
- All batch files use full Python path — don't rely on system PATH (Win7 truncation issue)
- Chrome `--kiosk` mode + watchdog for lockdown; Task Manager disable is optional later step
- Kiosk runs server locally (not pointing at main machine) for independence

**Status:** Complete — kiosk PC set up, packages installed, Claude Code installed on programming PC

---

## 2026-01-20

### Project 1: Proshop Automations — Selenium Automation
**Task:** Build ProShop Selenium automation for Written Description page editing

**What was done:**
- API authentication working
- Sequence Details retrieval via API working
- Selenium login with navigation to Written Description page
- Identified key DOM selectors: login fields (`name="mailAddress"`, `name="password"`), CHECKOUT button (`btn btn-raised btn-secondary`), SAVE CHANGES button

**Key decisions:**
- Using Selenium for browser automation since ProShop has no API for page content editing
- GUI version: `proshop_gui_v1.4.py`

**Status:** Paused — Chrome autofill overwrites username field with full email; fix is `.clear()` before `send_keys()`

---

## 2026-02-14

### Project 1: Proshop Automations — Programming Timer
**Task:** Build Fusion 360 Programming Timer add-in from spec

**What was done:**
- Built complete Fusion 360 add-in from scratch (8 files)
- `ProgrammingTimer.py` — main entry point, registers Fusion events, toolbar button
- `timer_core.py` — `DocumentTimer` + `TimerManager` classes for per-document time tracking
- `idle_detector.py` — Windows API idle detection via `GetLastInputInfo`
- `data_logger.py` — JSONL session logging, document-to-part mappings, crash recovery
- `config.py` — config loading with fallback paths (D:/C:/Documents)
- `timer_config.json` — user-editable config (idle timeout 120s, gap threshold 1800s, poll 15s)
- `setup_fusion_addins.bat` — deployment script creating symlinks from Fusion AddIns folder to Dropbox source
- Auto-detects company files via path patterns, prompts for part ID on first open
- Document switching pauses/resumes correct timers
- Crash recovery via `timer_state.json` with orphaned session finalization
- Sessions logged to shared `programming_time_log.jsonl` via Dropbox

**Key decisions:**
- JSONL format for easy append-only multi-machine logging
- Symlink deployment so all machines share source from Dropbox
- 30-minute gap threshold starts new session (prevents overnight spanning)
- Phase 2 deferred: ProShop API integration, WO selection UI, reporting

**Status:** Code complete, needs testing on CAM computers

---

## 2026-03-07

### Project 14: Workstation Display — Traxis IPC v2
**Task:** Implement balloon location highlighting

**What was done:**
- Added balloon overlay system to IPC v2 that links dimension rows to their locations on the PDF drawing
- Modified 4 files: `ipc.html`, `ipc.css`, `api.js`, `ipc.js`
- **HTML:** Added "Balloons" button + hidden file input in the PDF file bar, and a `#balloon-highlight` div inside the PDF container
- **CSS:** Created pulsing green ring highlight (40px circle, `balloon-pulse` animation with glow + scale), status text styling, loaded-state button tint
- **API:** Added `loadBalloonData(partNumber)` / `saveBalloonData(partNumber, data)` using `chrome.storage.local` keyed by part number
- **JS:** Full highlight pipeline:
  - State: `balloons` (parsed sidecar) + `activeBalloon` (current tag)
  - `onBalloonJsonSelect()` — validates `.balloon.json`, saves to storage
  - `showBalloonHighlight(tag)` — finds balloon by tag, auto-navigates PDF pages, positions highlight
  - `repositionBalloonHighlight()` — maps normalized x/y coords to canvas CSS pixels
  - `scrollToHighlight()` — smooth-scrolls container to center on highlight
  - Dim row focus triggers highlight, blur clears with 100ms debounce
  - Row click focuses input (so clicking anywhere on row triggers highlight)
  - Highlight repositions on zoom/resize via `renderCurrentPage()`
  - Balloon data clears on WO change, auto-loads from storage on WO load

**Sidecar format consumed:** `.balloon.json` from Balloonerator (Project 4) — `{ balloons: [{ tag, page, x, y, value, type, tolerance }] }` with normalized top-left coordinates

**Status:** Code complete, needs testing with actual Balloonerator output

---

### Project 19: Shop Floor Scheduler — Full Build
**Task:** Build interactive drag-and-drop shop floor scheduler (Flask + SQLite + EventCalendar.js)

**What was done:**
- Built complete scheduler from scratch — 11 files, ~2,100 lines of code
- **Backend:** Flask app on `:5080` with 16 API endpoints, SQLite database (10 tables), ProShop sync engine
- **ProShop integration:** OAuth2 GraphQL client pulls 79 active WOs + 525 operations, maps work centers to machines, calculates durations from `minutesPerPart × qty`
- **Scheduler board (`/`):** EventCalendar.js resource-timeline Gantt view with 10 machine rows, drag-and-drop from backlog panel using transparent drop overlay zones, color-coded urgency (red/orange/yellow/blue/green), block details side panel, zoom controls (day/3-day/week/month)
- **Operator view (`/operator`):** Machine selector (localStorage), +1/+5/+10 part buttons, mark complete with confetti + 4-note chime celebration, flag issue modal (tooling/material/quality/question)
- **Dashboard (`/dashboard`):** Stats grid, machine status cards, past-due list, active flags, sync log
- **Background sync:** Full sync every 15 min, writeback queue every 2 min (writeback deferred until trust established)
- **Data:** 293/525 ops have real ProShop time data, 232 use defaults, 72 ops auto-mapped to specific CNC machines via work center codes

**Key decisions:**
- Used `minutesPerPart × quantityOrdered / 60` for block duration (not ProShop's `runTime` which was all zeros)
- HTML5 drag-drop from backlog to calendar solved with transparent drop overlay (EventCalendar consumes native drag events)
- ProShop writeback deferred — user wants to validate scheduler accuracy first
- Removed `customerPlainText` from queries (requires `contacts:r` scope not in current credentials)
- Used `(result.get("data") or {})` pattern for null-safe GraphQL response handling

**Bugs fixed during build:**
- ProShop `StringQueryInput` uses `exactly` not `eq`
- ProShop field names differ from docs (`workOrderNumber` not `woId`, `qtyComplete` not `quantityComplete`, etc.)
- `partOperation` can be null — guarded with `or {}`
- GraphQL `data: null` responses crash `.get()` — fixed with `or {}` pattern
- EventCalendar.create() crash killed subsequent JS — wrapped in try/catch, load controls first

**Status:** Running, core scheduling functional, needs real-world testing with drag-drop workflow

---

## 2026-03-08

### Project 18: ProShop Message Notifier — Chrome Extension + Desktop Overlay
**Task:** Build Chrome extension and desktop overlay to alert shop floor workers of new ProShop messages

**What was done:**
- **Chrome Extension (Manifest V3):** Built complete extension in `chrome-extension/` directory
  - `manifest.json` — permissions for storage, alarms, notifications; content script on `traxismfg.adionsystems.com/procnc/*`; host permissions for Flask API at `10.1.1.71:5050`
  - `background/service-worker.js` — alarm-based polling every 30s, `chrome.notifications` desktop alerts, badge count, user state management via `chrome.storage.local`, name-to-ID mapping via `/api/users/lookup`
  - `content/content.js` — 5-strategy user detection from DOM (3 from traxis-ipc v1 + 2 new: "Current Work Orders, X is..." pattern and "Jump to User" dropdown), pulsing disc overlay injection, 3-note chime via Web Audio API, click opens user's inbox
  - `content/notification.css` — `.psn-` prefixed styles, fixed bottom-right overlay at z-index 999999, sonar ring + disc throb animations
  - `icons/` — generated green circle PNGs (16/48/128px) via Python
  - Notification state persisted in `chrome.storage.local` so new tabs pick up active alerts

- **Desktop Overlay (`desktop_overlay.py`):** Standalone Python/tkinter always-on-top app
  - User selection dialog with scrollable employee list (filtered server-side)
  - Polls Flask API every 30s in background
  - Shows 200px pulsing green disc with sonar rings, "NEW MESSAGE" text, sender name, count
  - Canvas-based animation at ~30 FPS (throb + 3 staggered sonar rings with "CLICK HERE" labels)
  - 3-note ascending chime via `winsound.Beep`
  - Click opens user's ProShop inbox in browser + acknowledges on server
  - Launch: `run_overlay.bat` or `python desktop_overlay.py --user Tom Buerkle`

- **Flask Server Changes (`app.py`):**
  - Added `@app.after_request` CORS headers (`Access-Control-Allow-Origin: *`)
  - Added `GET /api/users/lookup?name=First Last` endpoint — matches exact name, first-name-only, or first+last-initial
  - Filtered non-employee users by ID (`025`, `047`, `004` excluded server-side)

**Bugs fixed during build:**
- `chrome.action` API requires `"action"` key in manifest — was missing, caused `setBadgeText` crash
- Template literal `$formName` in backticks parsed as template expression — switched to string concatenation
- User detection strategies 1-3 failed on ProShop home page — added strategy 4 ("Current Work Orders, X is...") and strategy 5 (Jump to User dropdown)
- Stale Flask process on port 5050 — old process survived Ctrl+C, needed `wmic process terminate`

**Key decisions:**
- Service worker `fetch()` bypasses CORS (no extension origin header), but added CORS headers on Flask as safety net
- Desktop overlay uses tkinter (stdlib, no dependencies) rather than PyQt/Electron
- User inbox URL format: `/procnc/users/{id}$formName=messageinbox`
- Notification state stored in `chrome.storage.local` with `hasNotification`/`lastSender`/`lastCount` so newly-opened tabs show active disc

**Status:** Working — both Chrome extension and desktop overlay tested and functional

---

## 2026-03-04 (retroactive — no session log kept)

### Project 12: FASData — Extended Diagnostics & TraxisCapture Integration
**Task:** Enhance FocasMonitor with full diagnostic capture and correlate CAM programmer intent with machine execution

**What was done (reconstructed from file dates and backup_20260303):**

- **FocasMonitor Service (`MonitoringService.cs`):** Extended C# Windows service from basic spindle/run-status polling to full diagnostic capture:
  - WCO (Work Coordinate Offset) tracking per machine
  - Alarm state change detection + `alarm_history` table
  - Spindle/servo load sampling per axis
  - Tool number, active WCS, distance-to-go per axis
  - Power-on/cutting time diagnostic counters (19+ counters)
  - `capture_session_id` field linking machine samples to TraxisCapture diffs
  - CNC metadata capture: `cnc_type`, `mt_type`, `series`, `sw_version`, `max_axes`, `cnc_id`

- **Database Migration (`migrate_db.py`):** Script to add ~47 new columns to `monitoring.db`:
  - Capture linkage: `capture_session_id`, `capture_op_id`, `capture_tool_id`
  - Tool/spindle: `spindle_load`, `tool_number`, `active_wcs`
  - Axis diagnostics: `axis_a`, `axis_b`, `servo_load_x/y/z/a`, `dtg_x/y/z`
  - Power diagnostics: `diag_power_on_min`, `diag_cutting_min`
  - New tables: `tool_wear_samples`, `alarm_history`

- **Session Bridge (`session_bridge.py`, 39KB):** Built correlation engine joining TraxisCapture CAM diffs (`Programming Sessions/diffs/*.diff.jsonl`) with FocasMonitor machine execution data, matched via `capture_session_id`. Generates `session_bridge_report.html`.

- **TraxisCapture (`TraxisCapture/`):** 9-file Python package hooking into Fusion 360 CAM:
  - `capture_core.py` — before/after G-code diff capture
  - `pattern_accumulator.py` — program pattern tracking
  - `naming_enforcer.py` — `{PartNumber}_OP{XX}_v{N}.nc` convention
  - `nc_injector.py` — metadata injection into G-code
  - Output: `*.diff.jsonl` files in `Programming Sessions/diffs/`

**System status at time of interruption:**
- Basic collector still running on WrkStationC (5 machines: T2, M2, M3, M6, M8)
- Dashboard live on display PC (auto-refresh 5 min)
- Extended service with new diagnostics was being tested locally
- FocasMonitor shut down, PC rebooted — lost working context

**Infrastructure:**
- Collector PC (WrkStationC): `C:\FocasMonitor\FocasMonitor.exe` + `C:\FASData\monitoring.db`
- Main PC (TRAXIS): report generation every 5 min, dashboard hourly, daily email at 7 PM
- Display PC (traxi): 32" Samsung TV, Aztec-themed `dashboard.html`
- Machines not connected: M4, M5, M7 (Robodrills need Ethernet), M1 (Haas, not FOCAS)

**Key decisions:**
- .NET 10.0 target for FocasMonitor, win-x86 (FOCAS DLLs are 32-bit)
- SQLite for data storage, synced hourly from collector to Dropbox
- VBScript wrappers for scheduled tasks (run hidden, no popup windows)

**Status:** Interrupted — extended diagnostics build/test in progress, basic monitoring still running

---

## 2026-03-09

### Project 14: Workstation Display — IPC v2 Restyle
**Task:** Restyle IPC v2 to match ProShop's blue accent color scheme

**What was done:**
- Remapped 11 CSS variables in `theme.css`: green accents → ProShop blue, green-tinted surfaces → neutral grays
- Fixed hardcoded overlay backdrop color in `ipc.css` (green-tinted rgba → neutral black)
- Fixed hardcoded injection button color in `content.js` (green → blue)
- Kept pass/fail/warn/info colors unchanged (green checkmarks, red X, orange warnings)

**Key decisions:**
- ProShop blue primary: `#1565c0`, hover: `#1976d2`, background: `#e3f2fd`
- Accent-only change — no layout, typography, or structural modifications
- Balloon highlight fallback colors (`#4caf50`) left as-is since they only fire when CSS variables are missing

**Status:** Complete — needs visual verification on shop floor

---

### Project 14: Workstation Display — IPC v2 Op Info Tabs
**Task:** Add hover-reveal Instructions and Sequence tabs below op buttons so operators can view written descriptions and tool/sequence details without leaving IPC

**What was done:**
- Modified 4 files: `api.js`, `ipc.html`, `ipc.js`, `ipc.css`
- **api.js:** Expanded GraphQL query to fetch `writtenDescriptions { records { writtenDescription } }` and `tools { records { sequenceNumber tool { toolNumber description } holder outOfHolder sequenceDescription } }` on `partOperation`
- **ipc.html:** Added `#op-info-bar` div with "Instructions" and "Sequence" tab elements and a `#info-panel` floating container, positioned between header and main content
- **ipc.js:**
  - Added `opInstructions` and `opTools` to state
  - `selectOp()` extracts written descriptions and tools from the op data, calls `renderInfoBar()`
  - `renderInfoBar()` shows/hides tabs based on data availability (hides bar entirely if op has neither)
  - `showInfoPanel(type)` renders HTML instructions or a sequence table (Seq, Tool, Holder, OOH, Description)
  - Hover delay system: `scheduleHideInfoPanel()` / `cancelHideInfoPanel()` with 150ms grace period so mouse can travel from tab to panel without it disappearing
  - `esc()` helper for safe HTML escaping in sequence table cells
- **ipc.css:** Styled `#op-info-bar` (thin flex row, `var(--s2)` background), `.info-tab` (small accent-colored labels with hover highlight), `#info-panel` (absolute-positioned dropdown with shadow, 600px max-width, 400px max-height, scrollable), `.seq-table` (compact bordered table)

**Bugs fixed during build:**
- ProShop API returned "Expected a selection on object field tool" — `tool` is a full `Tool` object type, not a string; fixed by selecting `tool { toolNumber description }` sub-fields
- Hover panel disappeared instantly when moving mouse from tab to panel — fixed with 150ms delayed hide + cancel-on-reenter pattern

**Key decisions:**
- Hover-reveal (not click-toggle) keeps it zero-footprint on screen when not needed
- Instructions tab renders raw HTML from ProShop (formatting tags only, no scripts)
- Sequence table sorted by `sequenceNumber`, shows tool description with fallback to toolNumber

**Status:** Complete and tested — working on WO 26-0070

---

## 2026-03-11

### Project 10: Conversational ProShop — Claude-Powered v2 Upgrade
**Task:** Revisit the old regex-based conversational ProShop prototype and upgrade it with Claude API capabilities

**What was done:**
- Reviewed the January 2026 regex-based prototype (68% accuracy on realistic queries)
- **Built Claude intent classifier (`claude_intent_classifier.py`):**
  - Defined all 18 query templates as Claude Haiku tools (tool-use API)
  - Claude picks the correct tool from natural language — handles typos, slang, indirect phrasing
  - Drop-in replacement for the regex `classify_intent()` function
- **Built comparison test harness (`test_classifier_comparison.py`):**
  - 25 test queries: 10 standard, 5 edge cases, 10 hard (typos, slang, no keywords)
  - Result: **Regex 68% vs Claude 100%**
  - Hard queries regex failed on: "anything running behind schedule?", "how many jobs we got going", "what's our biggest job", "pull up the ops list for 25-0001"
- **Built conversation memory (`conversation_manager.py`):**
  - Tracks last 20 user/assistant turns
  - Enables follow-up questions: "What operations does it have?" after asking about a WO
  - Tested 3-turn conversation — pronoun resolution ("it") worked perfectly
- **Built Claude response formatter (`claude_response_formatter.py`):**
  - Feeds raw ProShop JSON through Claude Haiku for natural language output
  - Proactively flags urgent items (late orders, data inconsistencies)
  - Markdown-formatted, scannable for shop floor use
- **Built integrated CLI (`cli_claude.py`, `proshop_chat_claude.py`):**
  - Wires together: Claude classification → ProShop GraphQL → Claude formatting
  - Auto-loads Anthropic API key from `../11. Proshop Mobile App/.env`
  - Supports interactive mode, single query, and debug mode
- **Fixed ProShop credentials:**
  - Old Fusion Integration (`3923-9C1C-7291`) is broken (scope corrupted)
  - Switched to `0615-12FB-C88D` ("Fusionconnector") with scope `parts:rwdp+workorders:rwdp+users:r`
- **Attempted to add `fixtures:r` scope:**
  - ProShop admin scope editor changes didn't save on `0615-12FB-C88D`
  - Discovered `BA16-EFAF-B154` ("ClaudeCodeResearch") has broader scope (`+toolpots:r+tools:r`)
  - `fixtures:r` is a separate module — not included in `tools:r`
  - Work cells (machines) and users data confirmed accessible via ClaudeCodeResearch app
- **Updated `10. PROJECT_STATUS.md`** with full v2 architecture, credentials, session log

**Performance:**
- Total query time: ~3.3s (1.3s classify + 0.4s ProShop API + 1.6s format)
- Cost per query: ~$0.002 (two Haiku calls)
- Daily cost at 100 queries: ~$0.20

**Key decisions:**
- Claude Haiku for both classification and formatting (fast + cheap)
- `tool_choice: "any"` forces Claude to always pick a tool (no free-text responses)
- Conversation history trimmed to last 6 messages for classifier (3 turns is enough for pronoun resolution)
- Kept original regex system intact for comparison/fallback

**Bugs fixed during build:**
- Windows cp1252 encoding crashes on Unicode characters from Claude (checkmarks, emojis) — fixed with `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
- `set VAR=value && python` doesn't propagate env vars reliably in sandbox — auto-load from `.env` file instead
- Box-drawing characters (`─`) fail on cp1252 — replaced with ASCII dashes in test output

**Files created:**
- `src/claude_intent_classifier.py` — Claude Haiku tool-use intent classification
- `src/claude_response_formatter.py` — Claude Haiku natural language formatting
- `src/conversation_manager.py` — Multi-turn conversation memory
- `src/cli_claude.py` — Integrated Claude-powered CLI
- `proshop_chat_claude.py` — Root launcher (v2)
- `test_classifier_comparison.py` — Side-by-side regex vs Claude test harness

**Status:** Working — Claude-powered v2 complete. Next: add machine/work cell queries (scope available), resolve fixtures scope, build web interface for shop floor.

---

### Project 12: FASData — FocasMonitor Rebuild & Dashboard v2.2
**Task:** Get the expanded FocasMonitor collector running on TRAXIS, debug all FOCAS data streams, and enhance the Shop Hub dashboard with live machine data

**What was done:**

**FocasMonitor Collector — Build & Debug:**
- Built and deployed expanded FocasMonitor C# service on TRAXIS (self-contained .NET 10.0 win-x86)
- `machine_samples` table expanded to 55 columns, 8 tables total
- Schema auto-migration in `Database.cs` — uses `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` on startup
- **Servo loads**: Switched from struct-based to raw `byte[]` buffer P/Invoke to avoid marshaling segfaults. LOADELM = 12 bytes (int data + short dec + short unit + byte name + 3 reserve). Axis identified by name byte ('X','Y','Z','A').
- **Spindle load**: Same raw buffer approach via `cnc_rdspload_raw`
- **Multiple native crash investigations**:
  - `cnc_modal` — wrong struct for this DLL version, causes 0xC0000005 segfault. Removed.
  - `cnc_rdmacro` — needs 4 params (handle, var_no, length, buf), had 3. stdcall cleanup mismatch crashes. Removed.
- **Functions confirmed NOT working** on these 0i-series controllers:
  - `cnc_rdtool` → EW_NOOPT (3) on all 5 machines — tool management option not enabled
  - `cnc_machine2` → EW_FUNC (4) on all — machine coordinates not available
  - `cnc_distance2` → -7 on all — communication error
  - `cnc_diagnoss` → EW_FUNC (4) on all — diagnosis counters not supported
- Removed `cnc_machine2` and `cnc_distance2` calls from production build
- Cleaned all diagnostic logging for stable production deployment
- Service running stable, polling 5 machines (T2, M2, M3, M6, M8) every 60s

**Data streams confirmed working:**
- Spindle speed, feed rate (mm/min), run status, mode, motion
- Axis positions (X/Y/Z via cnc_absolute, units: 1/10000 mm)
- Spindle load, servo loads (X/Y/Z/A)
- Emergency stop, alarms
- Program number, program comment
- Overrides (spindle/feed), sequence number, block count
- Parameter snapshots (575 rows captured)

**Shop Hub Dashboard v2.0 → v2.2:**
- **v2.0**: Added live data to Flask API (`fasdata_live.py`): spindle_load, servo_load_x/y/z, axis_x/y/z, emergency, sequence_number, block_count. Fixed DB_PATH from Dropbox sync path to `C:\FASData\monitoring.db`. Added E-STOP badge (flashing), alarm badge, servo load bars, DRO positions, speed/feed/program display.
- **v2.1**: Removed all messaging features per user request (per-card messages, shop-wide messages bar, SHOP MSGS button, all related CSS/JS)
- **v2.2**: Dramatic meter overhaul:
  - Spindle load: semicircle arc gauge with color-coded glow (green <50%, yellow 50-80%, red >80% with pulsing animation)
  - Servo load bars: 10px tall, gradient fills, glowing borders, pulsing red glow at >80%, numeric % readouts per axis
  - Speed/feed: large 20px bold readouts with RPM / IN/MIN / PROG labels
  - Feed rate conversion: raw mm/min from FOCAS ÷ 25.4 = inches/min
  - Idle machines: mode and program number with holding torque bars

**Key technical lessons:**
- Raw buffer P/Invoke (byte[] + BitConverter) is safer than struct marshaling for FOCAS — avoids uncatchable native segfaults
- Native crashes from wrong struct sizes or wrong param counts are NOT catchable by try-catch
- FOCAS `actf.data` returns mm/min on these controllers (unit=0). 59055 mm/min = rapid traverse, 370 mm/min = 14.6 IPM slow feed.
- `[In, Out]` attribute needed on array parameters passed to native DLLs for marshaling back
- FOCAS mode codes: 0=MDI, 1=MEM, 3=EDIT, 4=HANDLE, 5=JOG, 6=TJOG, 7=THND, 8=INC, 9=REF

**Database stats (end of session):**
- Size: 0.7 MB (service started today)
- 990 rows in machine_samples, 575 in parameter_snapshots
- Growth: ~3,900 rows/day at 60s polling (~2 MB/day, ~500 MB/year)
- No purge/retention policy needed at this scale
- Poll interval could safely drop to 10-15s (~3 GB/year at 10s)

**Files modified:**
- `12. FASData Implementation\FocasMonitor\MonitoringService.cs` — servo/spindle raw buffer polling, removed non-working calls
- `12. FASData Implementation\FocasMonitor\Focas.cs` — raw P/Invoke overloads, mode codes, [In,Out] fix
- `12. FASData Implementation\FocasMonitor\Database.cs` — auto-migration
- `1. Proshop Automations\FASDataDashboard\fasdata_live.py` — DB_PATH fix, new API fields
- `1. Proshop Automations\FASDataDashboard\fasdata_dashboard.html` — complete live data panel rewrite (v2.0→2.2)

**Status:** Running — collector stable, dashboard live at localhost:8070. M4/M5/M7 not connected (need Ethernet).

---

### Project 12: FASData — Spindle Load Fix & Dashboard v2.2 (continued session)
**Task:** Fix incorrect spindle load readings, enhance dashboard meters, convert feed rate to inches/min, investigate data querying

**What was done:**

**Spindle Load Investigation & Fix:**
- Discovered spindle load values were wrong: M2 max=32,574, M3 max=32,237, M8 values of 375-432 during cutting (impossible percentages)
- Root cause: `cnc_rdspload` struct assumption was wrong — reading `ToInt16(splBuf, 4)` from ODBSPLOAD which has the wrong layout for these controllers
- Servo loads (0-105% range) were correct because they use LOADELM via `cnc_rdsvmeter_raw`
- **Fix:** Switched spindle load to `cnc_rdspmeter` (type=0 for load), which returns LOADELM structs — same format as working servo loads
- Added `cnc_rdspmeter_raw` P/Invoke overload in `Focas.cs`
- New parsing: read LOADELM (int data + short dec + short unit + byte name), apply `data × 10^(-dec)` scaling
- Fallback: if `cnc_rdspmeter` fails, try `cnc_rdspload` as before
- **Diagnostic dump confirmed** LOADELM layout on M6 (only machine online at end of day):
  - `ret=0, count=1, data=0, dec=0, name='S1'` — correct for idle spindle
  - Other machines (T2/M2/M3/M8) were powered off, so no data to compare yet
- Needs validation tomorrow with machines under load

**Deployment Lesson:**
- Elevated PowerShell via `Start-Process -Verb RunAs -ArgumentList` with inline commands silently fails (argument quoting issue with paths containing spaces)
- **Fix:** Write a `.ps1` script file, then `Start-Process powershell -Verb RunAs -Wait -ArgumentList '-ExecutionPolicy','Bypass','-File','path\to\script.ps1'`
- Service logs go to console (nowhere for a Windows service) — used `File.AppendAllText(@"C:\FASData\diag_spindle.log")` for diagnostic output instead of `ILogger`

**M8 Data Analysis:**
- Queried DB: M8 running program O763, active block "CHAMFER DEBURR PERIMETER AND HOLES"
- Estimated cycle time from block_count resets: ~95,000 blocks per cycle
  - Cycle 1: 11:12→12:31 (~1h 19m)
  - Cycle 2: 12:31→15:23 (~2h 52m, includes operator time between parts)
- Operation sequence visible from data: Seq 80 (roughing 3820 RPM) → Seq 85 (HSM 8085 RPM) → Seq 90 (boring/reaming 1528 RPM) → Seq 95 (chamfer 4584 RPM) → Seq 100 (1819 RPM) → Seq 105 (finishing 3820 RPM)

**Dashboard v2.2 Enhancements:**
- **Dramatic spindle load gauge:** Semicircle arc meter with color-coded glow, tick marks at 50%/80%, pulsing animation at high load
- **Dramatic servo load bars:** 10px tall with gradient fills, glowing borders, pulsing red glow >80%, per-axis percentage readouts with color coding
- **Large speed/feed readouts:** 20px bold numbers with RPM / IN/MIN / PROG labels underneath
- **Feed rate in inches/min:** FOCAS returns mm/min (confirmed: 59055 = rapid, 370 = 14.6 IPM slow feed). Dashboard divides by 25.4.
- **Idle machine display:** Mode and program number with holding torque bars visible

**Sampling Rate Discussion:**
- Current: 60 seconds per poll cycle
- FOCAS poll takes ~1-3s for all 5 machines
- Can safely reduce to 10-15s without crashing
- Below 5s risks overlapping polls
- DB growth at 60s: ~3,900 rows/day, ~500 MB/year
- DB growth at 10s: ~23,400 rows/day, ~3 GB/year
- No purge/retention needed at either rate — SQLite handles it fine

**Key technical lessons (new):**
- `cnc_rdspmeter` (type=0) is the correct function for spindle load on 0i-series — returns LOADELM with data/dec/unit/name fields
- LOADELM name byte confirmed: `0x53` = 'S', suffix `0x31` = '1' (Spindle 1)
- Windows service logging: `ILogger` goes to console (invisible). Use `File.AppendAllText` for diagnostics.
- Elevated PowerShell deploy: must use a .ps1 script file, not inline commands (quoting breaks with spaces in paths)
- `program_comment` column doesn't exist in DB — the field is `active_block_content` which captures full active block G-code + comments

**Files modified:**
- `12. FASData Implementation\FocasMonitor\MonitoringService.cs` — replaced `cnc_rdspload` with `cnc_rdspmeter` for spindle load, added file-based diagnostic logging
- `12. FASData Implementation\FocasMonitor\Focas.cs` — added `cnc_rdspmeter_raw` P/Invoke overload
- `1. Proshop Automations\FASDataDashboard\fasdata_dashboard.html` — dramatic meters, IPM feed rate, spindle load arc gauge (v2.2)

**Status:** Deployed and running. Spindle load fix needs validation tomorrow with machines under load. Dashboard live at localhost:8070.

---

## 2026-03-13

### Project 16: Fusion Tool Library Product ID Changer — UX Improvements
**Task:** Improve FusionToolAuditor add-in usability

**What was done:**
- **Auto-select Document library:** Palette now automatically selects and loads the current part's tool library on open (no manual dropdown selection needed)
- **Relabeled Refresh button:** Changed "Refresh" → "Connect to Libraries" to better describe its function
- **New "Connect to ProShop Tool Data" button:** Replaced the tiny "Load" button in the stats bar with a full-sized button in the main toolbar, matching the style of "Connect to Libraries"
- **Connection status indicators:** Both "Connect to Libraries" and "Connect to ProShop Tool Data" buttons turn green when their connection succeeds
- **Close button:** Added red "Close" button to dismiss the palette, with `closePalette` handler in Python that sets `_palette.isVisible = False`

**Files modified:**
- `FusionToolAuditor/palette.html` — UI changes (auto-select, button labels, connection indicators, close button)
- `FusionToolAuditor/FusionToolAuditor.py` — Added `closePalette` action handler

**Key decisions:**
- Document library auto-selected by matching `lib.location === 'Document'` after library list populates
- Connection buttons turn green (#107c10) on success rather than using a separate indicator

**Status:** Complete — needs testing in Fusion 360

---

## 2026-04-03

### Project 23: Air Compressor Communication GUI — Build, Calibration, Remote Stop Investigation

**Task:** Build a Flask web GUI for monitoring the EMAX 20HP rotary screw compressor via Modbus TCP (PUSR DR302 gateway → Logik 26-S controller). Then investigate remote start/stop capability.

**What was done:**

**1. Built full Flask web GUI (`compressor_web.py`, ~1150 lines):**
- Live pressure bar graph with start/stop/alarm markers (120-138 PSI cycle)
- Live temperature bar graph with warning/alarm markers (~83-91°C operating)
- Status detection via HR 4244 aux register: "RUNNING (Loading)" vs "RUNNING (Unloaded)"
- Weekly schedule display + editor — reads Timer1 (Mon-Fri, HR 1800) and Timer2 (all days, HR 1920)
- Maintenance status panel with static estimates from LCD readings
- Cabinet filter manual 6-month timer tracked via `cabinet_filter.json`
- START/STOP buttons (currently schedule editors only — see below)
- Configuration panel showing pressure setpoints, temperature limits, equipment info

**2. Pressure calibration:**
- Raw hi byte showed 99 PSI when LCD read 120 — discovered linear conversion needed
- Formula: `PSI = round(hi_byte * 0.75 + 45.75)` — confirmed matching LCD in real-time

**3. Timer system discovery and bug fixes:**
- Timer1 (HR 1800): Only supports Mon-Fri (5 days × 6 regs = 30 regs). Sat/Sun = Illegal Data Address
- Timer2 (HR 1920): All 7 days (42 regs)
- Time encoding: `(minute << 8) | hour` (e.g., 7685 = 05:30)
- Fixed Timer1 overflow bug: was reading 42 regs (overflowed into unrelated data), causing Saturday ghost schedule. Fixed to read 30 regs, decode 5 days

**4. Remote start/stop investigation (BLOCKED):**
- FC01 (coils) and FC02 (discrete inputs): NOT supported by this controller
- Scanned HR 20-4600 for command registers — found serial number, config, counters, logs, but no command register
- Tried 4 timer manipulation approaches for immediate stop — all failed (controller doesn't re-evaluate mid-cycle)
- Downloaded and extracted L26-S manual PDF — Alarm 33 references separate "MODBUS protocol communication" document
- Remote start/stop IS supported but the register map is proprietary/unpublished
- Must request "Modbus Register Map" from Logika Control (info@logikacontrol.it, +39 0362/37001) or EMAX

**5. Register map documented:**
- HR 1-10: Serial number ASCII ("EC00002447")
- HR 4096-4099: Controller ID "Logik26S"
- HR 4241 hi byte: Live pressure, HR 4243 hi byte: Live temperature
- HR 1290-1292: Pressure setpoints (bar×10), HR 1312-1315: Maintenance SET values
- HR 1348-1364: Drive parameters (DR0-DA9)
- HR 1679: Load hours (~10,692)
- HR 1540-1549: Incrementing counters (possible maintenance counters — needs investigation)

**Files created/modified:**
- `23. Air Compressor communication GUI/compressor_web.py` — Main Flask GUI (port 8085)
- `23. Air Compressor communication GUI/cabinet_filter.json` — Manual filter tracking
- `23. Air Compressor communication GUI/probe_coils.py` — FC01/FC02 scanner (confirmed none exist)
- `23. Air Compressor communication GUI/scan_control.py` — Register scanner for unexplored ranges
- `23. Air Compressor communication GUI/scan_live_area.py` — Deep scan of live data areas
- `23. Air Compressor communication GUI/live_decode.py` — Diagnostic register verification tool
- `23. Air Compressor communication GUI/scan_timers.py` — Timer/counter register scanner
- `23. Air Compressor communication GUI/REGISTER_MAP.md` — Comprehensive register map document
- `23. Air Compressor communication GUI/session_log.md` — Detailed project session log

**Key decisions:**
- Pressure conversion formula derived empirically from LCD comparison (not documented anywhere)
- Timer1 limited to 5-day read (Mon-Fri only) to avoid overflow into unrelated registers
- STOP button implemented as schedule editor (changes today's OFF time) since true remote stop register is unknown
- Wt4 (unload timer) = 30 min means even schedule-based stop takes 30 min for full shutdown

**6. Pressure reading clarification:**
- HR 4241 reads **compressor outlet pressure** — shows 0 when machine is off
- Residual air in receiver tank/shop piping is NOT visible via Modbus (no system pressure sensor on controller)
- Monitoring downstream system pressure would require a standalone transducer on the receiver tank or main header

**7. Dryer activation discussion:**
- Air dryer runs at 240V, currently no automatic on/off tied to compressor
- **Recommended: pressure switch + 240V contactor** (~$50-80) — set switch at ~80 PSI, auto-powers dryer when system has pressure
- **Alternative: current-sensing relay** on compressor feed — no plumbing, but dryer shuts off immediately with compressor (no delay for residual moisture)
- Optional time-delay relay (~$20) to keep dryer running 15-30 min after compressor stops
- Need to check: dryer nameplate amps, whether dryer has built-in remote start terminal

**Status:** GUI running at http://10.1.1.71:8085. Immediate remote start/stop blocked until proprietary Modbus register map is obtained from manufacturer. Next: contact Logika Control/EMAX, investigate HR 1540 area for maintenance counters, consider reducing Wt4 from 30min, check dryer for remote start terminal and amp draw.

---

### Project 3 / 15: Automatic Ordering Research & Fearless Emu Portal Alignment

**Task:** Determine what's required to implement automatic ordering — shop floor scans low-qty items, system creates POs or online orders automatically. Remove purchasing burden from Rene. Align with Fearless Emu portal build.

**What was done:**

**1. Reviewed Project 15 purchasing & inventory architecture:**
- `08_purchasing/module_purchasing.md` — Complete PO data model, vendor integration patterns, three-way match, auto-reorder logic (1,025 lines)
- `09_inventory/module_inventory.md` — Inventory items/levels/transactions, DDMRP planning, barcode scanning (1,013 lines)
- `11_contacts/module_contacts.md` — Unified customer/vendor contact model
- `13_shop_floor/module_shop_floor.md` — Mobile scanning interfaces, kiosk designs
- `23_integrations/module_integrations.md` — Event-driven architecture, vendor integration paths (email, portal, EDI, API, punchout)
- `01_api_discovery/api_gaps.md` — Confirmed ProShop has ZERO API for purchasing or inventory
- `25_feasibility/` and `24_gap_analysis/` — Full implementation estimates and gap analysis

**2. Reviewed Fearless Emu portal current state:**
- Read `traxis-architectural-brief.pdf` — Emu's architecture: Vue/Nuxt 3, PostgreSQL as source of truth, ProShop as isolated sync module, API-first
- Read `traxis-proposal_final.docx.pdf` — 5-phase plan, 88-140 hours, $4,520-$6,600
- Read `Drawing_Revisions_Portal_Spec.docx` — Four-stage revision escalation spec (pre-quote, active quote, accepted PO, in-production). Well-designed: "portal flags, Traxis decides."
- Phase 2 done: RFQ intake, admin dashboard, file management, customer list, notifications
- Phase 3 next: Customer login, file revisions, ProShop push, quoting, PO acceptance, comment threads

**3. Determined auto-ordering fits INTO the Emu's portal, not as a separate system:**
- Same app, different roles: customer, vendor, shop floor, admin
- Same PostgreSQL database, same API layer, different views per role
- Tom's earlier Softr/Airtable/Make.com portal work acknowledged as dead end — Emu's build replaces it

**4. Sent message to Fearless Emu with four schema recommendations:**
1. Companies table with `type` field (customer, vendor, both) — not hardcoded as "customers"
2. Parts table with `item_type` field (manufactured, purchased, consumable) — unified catalog
3. File/document system generic (linked to any entity by type + ID) — not hardcoded to drawings
4. Notification system role-aware (audience parameter) — serves customer, vendor, and shop floor alerts

**5. Vendor API research:**
- McMaster-Carr: No public API, actively blocks automation. Email PO best path. OCI punchout possible long-term.
- MSC Direct: Has EDI program for business accounts. Need to call MSC rep.
- Amazon Business: Has Business API / Punchout program.
- Local vendors (DBR1, LPM1, etc.): Auto-email PO is the sweet spot. AI can parse reply emails.

**Key decisions:**
- Auto-ordering is NOT a standalone system — it's modules 8, 9, 11 from Project 15 architecture built into the Emu's portal
- Emu doesn't need to build purchasing/inventory now, but schema must accommodate it
- Emu already has access to Project 15 for full context
- Next step is Emu's response to schema recommendations + scheduling a call to walk through Phase 2

**Status:** Research complete. Awaiting Fearless Emu response. Call to be scheduled.

---

## 2026-04-11

### Project 23: Air Compressor — Timer Bypass Bug Fix, Resume Schedule Feature

**Task:** Investigate why the compressor was running on Saturday morning (7:39 AM) despite the weekly schedule having Sat/Sun OFF. Add ability to detect and resolve timer bypass condition.

**What was done:**

**1. Root cause identified:**
- `CMD_START` (0x0001) starts the compressor outside of timer control — the weekly schedule cannot turn it off afterward
- `FLAG_ON_BY_TIMER` and `FLAG_TIMER_BYPASSED` flags from HR 1034 were defined in code but never decoded or displayed in the UI
- No endpoint existed to send `CMD_STOP_BYPASS_TIMER` (0x0010) to restore timer control

**2. Backend fixes (compressor_web.py):**
- Poll loop now decodes `on_by_timer` and `timer_bypassed` booleans from HR 1034 status flags
- New endpoint: `POST /api/compressor/resume_schedule` sends `CMD_STOP_BYPASS_TIMER` (0x0010) to HR 1036

**3. UI additions (schedule panel):**
- Timer mode indicator: "ON BY SCHEDULE" (green) / "BYPASSED (manual override)" (yellow) / "OFF" (gray)
- "Resume Schedule" button — only visible when timer is bypassed, with confirmation modal

**4. Utility:** Added `restart_server.bat` as manual fallback to Overseer-managed restarts.

**Key decisions:**
- Kept existing Start/Stop buttons sending CMD_START/CMD_STOP (0x0001/0x0002) unchanged — added Resume Schedule as a separate action rather than changing Stop behavior, to avoid surprises
- Noted for future: consider whether Stop should always re-engage the timer schedule

**Status:** Code complete, pending restart of service on 10.1.1.71 via Overseer dashboard. Overseer already manages Air Compressor service with auto-start and health monitoring.

---

## 2026-04-12

### Projects 1, 25: Migrate P25 Services into Overseer
**Task:** Move Telegram bot and scheduled tasks from service_wrapper.py into Overseer-managed services, enabling remote start/stop/restart from the dashboard on port 8060.

**What was done:**

1. **telegram_bot.py** — Added stdlib HTTP health endpoint on port 8100 (daemon thread). Tracks uptime, messages handled, last message time, tools loaded, conversation length. No new dependencies.

2. **agent_scheduler.py** (NEW) — Long-running scheduler replacing service_wrapper's scheduled task logic. Runs check_reminders.py (15min), run_audit.py (60min), scan_projects.py (daily midnight). Health endpoint on port 8101 with task status and exit codes. Supports `--once` flag for testing.

3. **overseer.py** — Added `AGENT_DIR` path, two service configs (TelegramBot on :8100, AgentScheduler on :8101), and two validators (`validate_telegram_bot`, `validate_agent_scheduler`). Both use `PYTHON_EXE -u` for unbuffered output with health server threads.

4. **service_wrapper.py** — Stripped bot management (`start_bot`/`check_bot`/`stop_bot`), all scheduled task logic (`_run_oneshot`, `maybe_run_*`), and related state. Now only launches Overseer + heartbeat/leader election.

**Files modified:**
- `25. Agent Exploration/telegram_bot.py` — health endpoint added
- `25. Agent Exploration/agent_scheduler.py` — NEW file
- `1. Proshop Automations/Overseer/overseer.py` — 2 services + 2 validators added
- `25. Agent Exploration/service_wrapper.py` — bot + scheduled tasks removed

**Key decisions:**
- Used stdlib `http.server` for health endpoints (no new dependencies)
- Used `PYTHON_EXE` (not `PYTHONW_EXE`) for both P25 services since they need health server threads + unbuffered stdout
- Kept leader election and Overseer launch in service_wrapper — it's the only thing NSSM needs to start

**Status:** Code complete, all 4 files pass syntax check. Needs deployment test on 10.1.1.71 after Dropbox sync.

---

## 2026-04-14

### Project 30: Material Label Extension — Initial Build

**Task:** Build a Chrome extension (MV3) that injects a "Print Material Label" button on ProShop WO pages, generates a label PNG client-side, and sends it to the Brother PT-P700 print service.

**What was done:**

- Created full project structure at `30. Material Label Extension/traxis-material-label/`
- **manifest.json** — MV3 targeting `traxismfg.adionsystems.com/procnc/workorders/*`, host_permissions for print service at 10.1.1.242:5002
- **service-worker.js** — Proxies PRINT_LABEL and CHECK_PRINTER messages to HTTP print service (bypasses HTTPS→HTTP mixed-content block)
- **label-generator.js** — Canvas API rendering: 128px tall label matching P9 convention (QR code left encoding `proshop://wo/{woNumber}`, 4 text lines right: WO number, material, part number, quantity)
- **content.js** — WO number from URL regex, DOM scraping for material/part/qty with GraphQL API fallback via session cookie, green button injection near Part Stock row, MutationObserver with 500ms debounce for AJAX navigation
- **content.css** — Green button (#2e7d32) with printing/success/error state animations
- Downloaded `qrcode-generator` library (Kazuhiko Arase) for QR code rendering
- Iterated on button placement: moved from page top → Part Stock row area → absolute-positioned at row's right edge
- Created project CLAUDE.md with Interfaces block

**Key decisions:**

- Service worker needed as HTTPS→HTTP proxy (ProShop is HTTPS, print service is HTTP)
- Reused P9 label conventions (128px/180DPI, `proshop://wo/` QR scheme) and P22 print payload format (`{image_base64, copies, label_name}`)
- DOM scraping first with GraphQL API fallback for material data — WO number always from URL (reliable)
- XPath search for "Part Stock" text to anchor button placement (faster than full element scan)

**Files created:**

- `30. Material Label Extension/CLAUDE.md`
- `30. Material Label Extension/traxis-material-label/manifest.json`
- `30. Material Label Extension/traxis-material-label/background/service-worker.js`
- `30. Material Label Extension/traxis-material-label/src/content.js`
- `30. Material Label Extension/traxis-material-label/src/content.css`
- `30. Material Label Extension/traxis-material-label/src/label-generator.js`
- `30. Material Label Extension/traxis-material-label/lib/qrcode.min.js`

**Status:** Needs testing — button appears on WO pages, but print functionality and DOM scraping accuracy not yet verified. Button placement needs refinement once ProShop DOM structure is inspected.

---

<!-- Template for new entries:

## YYYY-MM-DD

### Project N: Project Name
**Task:** Brief description

**What was done:**
- Bullet points of changes

**Key decisions:**
- Any architectural or design choices made

**Status:** Complete / In progress / Needs testing / Blocked by X

---
-->
