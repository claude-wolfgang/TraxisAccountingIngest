# 12. FASData Project Update
**Traxis Manufacturing — Closing the Loop: TPM + TraxisCapture + FASData**
**Project:** 12. FASData Implementation
**Date:** March 14, 2026

---

## Session Summary: TPM v1.3.0 — NC Program Naming, Versioning & Post-Completion Pipeline

### Goals
Close the traceability loop between three systems:
1. **TraxisProgramManager (TPM)** — Names/versions NC programs in Fusion 360
2. **TraxisCapture** — Captures programmer changes (Snapshot A → B diffs), injects CAPTURE tags into NC files
3. **FASData/FocasMonitor** — Reads CAPTURE tags from CNC active blocks, logs machine execution data

### System Architecture Understanding

**TraxisCapture** (Fusion add-in):
- Registers DocumentOpened, DocumentClosing, CommandTerminated handlers
- On doc open: detects origin (toolpath/prior_program/fresh), takes Snapshot A
- On post complete: takes Snapshot B, injects `(CAPTURE:SESSION=...)` tags into NC files
- On doc close: computes diff (A vs B), writes JSONL via io_worker
- **Current status**: All 13 existing sessions have `snapshot_b: null` — post event never fired (same `IronPostProcess` command ID issue TPM had — see Key Discovery #1)

**FocasMonitor** (Windows Service on WrkStationC):
- CAPTURE tag parsing: FULLY IMPLEMENTED in C# (`Focas.ParseCaptureTags()`)
- Reads `(CAPTURE:SESSION=...)`, `(CAPTURE:OP_ID=...)`, `(CAPTURE:TOOL_ID=...)` from active G-code blocks
- Stores `capture_session_id`, `capture_op_id`, `capture_tool_id` in `machine_samples` table

**Session Bridge** (`session_bridge.py`):
- Joins TraxisCapture diff JSONL records with FocasMonitor machine execution data by `capture_session_id`
- Generates HTML report with fidelity score, parameter changes, machine execution metrics
- Currently falls back to demo data (no real matched sessions yet)

**Pattern Accumulator**:
- Aggregates programmer corrections across sessions
- Generates writeback candidates for tool library preset updates
- Running but 0 output (because all sessions have snapshot_b: null)

### Changes Made to TPM (v1.2.0 → v1.3.0)

#### 1. O-Number Versioning System
- **New scheme**: `program_number = op_number + version`, zero-padded to 4 digits
  - OP60 v1 → `0061`, OP60 v2 → `0062`
  - OP70 v1 → `0071`, OP100 v1 → `0101`
- `get_program_number(op_number, version)` generates the 4-digit number
- `_read_version_from_header(nc_path)` reads `(VERSION: N)` from existing NC file headers (first 20 lines)
- `get_current_version()` reads header first, falls back to `_v*.nc` filename scan (legacy)
- `job_programName` set to the O-number → populates "Name/number" field in post dialog

#### 2. Setup Naming
- Setups renamed to `{PartNumber}:{OpNumber}` convention (e.g., `TRA1-027336:60`)
- `job_programComment` set to `{PartNumber}_OP{OpNumber}` (e.g., `TRA1-027336_OP60`)
- Comment appears on the O-line in posted NC file: `O0061 (TRA1-027336_OP60)`

#### 3. Post-Completion Handler (IronPostProcess)
- **Critical discovery**: Fusion's post command ID is `IronPostProcess`, NOT `PostProcess`
  - `IronNcProgram` = the NC Program creation dialog (reason=1 on close)
  - `IronPostProcess` = the actual G-code generation (reason=2 on completion)
  - Neither contains "Post" lowercase — original `'Post' in cmd_id` check never matched
- Handler now explicitly matches `cmd_id in ('IronPostProcess', 'IronNcProgram')`
- Skips `IronNcProgram` (dialog only), processes `IronPostProcess` (file generation)
- **terminationReason**: 0=CompletedSuccessfully, 1=Cancelled, 2=Aborted (but IronPostProcess uses 2 for success)

#### 4. Background Thread for File Processing
- **Critical discovery**: `time.sleep()` on Fusion's main thread blocks ALL file I/O
- Fusion needs the main thread free to finish writing/flushing the NC file after `IronPostProcess` terminates
- `PostCompletedHandler.notify()` now spawns a daemon `threading.Thread` that:
  1. Waits 2 seconds for Fusion to complete the file write
  2. Uses `os.listdir()` (not `os.path.isfile()` — more reliable in Fusion's Python)
  3. Retries up to 4 times with 1-second delays if needed
- This pattern applies to ALL Fusion add-in post-completion work

#### 5. NC File Finding & Processing Pipeline
After post completes (on background thread):
1. **Find file** — `_find_posted_nc()` searches multiple folders for the O-number-named file using `os.listdir()`
2. **Inject header** — Adds metadata with retry logic for file locking (PermissionError)
3. **Rename** — `_rename_nc_file()` renames `0061.nc` → `TRA1-027336_OP60.nc` (backs up existing files with timestamp suffix)
4. **Copy to Dropbox NC Programs** — `D:\Dropbox\NC Programs\{PartNumber}\`
5. **Copy to PART FILES** — `D:\Dropbox\PART FILES Traxis\{Customer}\{PartNumber}\`

#### 6. NC Program Entity Rename
- `_update_nc_programs(cam)` moved from pre-post (CommandExecuteHandler) to post-completion (PostCompletedHandler)
- Pre-post: `cam.ncPrograms` returns count 0 (entities don't exist yet)
- Post-completion: `cam.ncPrograms` returns the created entities (up to 7 found in testing)
- Sets NC Program name to `{PartNumber}_OP{OpNumber}` so future post dialogs show correct name
- **Note**: Currently runs on main thread before background thread spawns. May need `fireCustomEvent` pattern if timing issues arise.

### Key Discoveries

#### 1. Fusion Post Command IDs
| Command | ID | terminationReason |
|---|---|---|
| TPM dialog | `traxisProgramManagerCmd` | 1 (cancelled/dismissed) |
| NC Program dialog | `IronNcProgram` | 1 |
| Post process (G-code gen) | `IronPostProcess` | 2 (success!) |

This was the primary blocker — the post-completion handler never fired because the command ID filter (`'Post' in cmd_id`) didn't match `IronPostProcess`.

**TraxisCapture has the same bug** — `'Post' in cmd_id` in its `CommandTerminatedHandler` will never match `IronPostProcess`. This is why all 13 capture sessions have `snapshot_b: null`.

#### 2. Main Thread File I/O Blocking
- `IronPostProcess` terminates (reason=2) BEFORE the NC file is fully flushed to disk
- Fusion needs the main thread to complete the file write
- `time.sleep()` on the main thread prevents Fusion from ever writing the file
- Solution: spawn a background thread, sleep there, then search for the file
- `os.listdir()` is more reliable than `os.path.isfile()` in Fusion's Python environment

#### 3. Cascading Rename Bug (Fixed)
- When only 1 setup is posted, the handler processes all 6 setups in `_naming_state`
- The "scan for any recent .nc file" fallback found the file just created for setup 1 and kept renaming it through all 6 setups
- Fix: only search for the EXACT filename (no fallback scan for recent files)

#### 4. Setup Name Accumulation
- Setting `job_programName = '0061'` causes Fusion to asynchronously append the last digit (`1`) to the setup name
- `TRA1-027336:60` becomes `TRA1-027336:601` after Fusion's deferred update
- Pattern: `:60` + `1` = `:601`, `:70` + `1` = `:701`, etc.
- TPM corrects this on each run (renames back to `:60`), but it recurs
- **Status**: Cosmetic issue, self-correcting on each TPM run

#### 5. Fusion Output & Parameters
- Fusion posts to `D:\Users\MainPC\Documents\NC Files For Transfer\` (user's configured default)
- `job_outputFolder` does NOT exist as a setup parameter — can't control output folder via API
- Only `job_programName`, `job_programComment`, `job_description` exist as setup parameters
- TPM must find the file wherever Fusion puts it, then copy to Dropbox

#### 6. File Locking
- Fusion may still hold the NC file locked when `IronPostProcess` terminates
- `inject_header_into_file()` retries up to 5 times with increasing delays on `PermissionError`
- Rename via `shutil.move()` succeeds even when read is locked (observed in testing)

### Verified End-to-End Output (v1.3.0)

```
%
O0061 (TRA1-027336_OP60_v1)
(PART: TRA1-027336)
(OP: 60)
(VERSION: 1)
(POSTED: 2026-03-14 17:24:18)
(PROGRAMMER: Thomas Buerkle)
(POST HYUNDAI KF5600II FANUC I V1.1.5)
(T1 D=2. CR=0.006 - ZMIN=-0.2224 - FACE MILL)
...
```

### Current Status (End of v1.3.0 Session)

**Fully Working:**
- O-number versioning in post dialog Name/number field ✅
- Setup naming `{PN}:{OP}` ✅
- Program comment on O-line ✅
- Post-completion handler fires on `IronPostProcess` ✅
- Background thread file processing ✅
- Header injection with all metadata fields ✅
- File rename `0061.nc` → `TRA1-027336_OP60.nc` ✅
- Backup of existing files before rename ✅
- Copy to Dropbox NC Programs ✅
- NC Program entities accessible after post ✅

**Known Cosmetic Issues:**
- Setup name accumulation (`:60` → `:601` between runs, self-corrects)
- NC Program "Name" field shows `NCProgram{N}` on first post from fresh document (corrected after post)
- Unposted setups wait through retry loop (~4s each) — acceptable since it's on background thread

### Files Modified (v1.3.0)
- `TraxisProgramManager\TraxisProgramManager.py` — Major rewrite: versioning, background thread, file pipeline
- `TraxisProgramManager\TraxisProgramManager.manifest` — Version bumped to 1.3.0

### Debugging Journey (v1.3.0)
This session involved extensive iterative debugging:
1. **Command ID mismatch** — `'Post' in cmd_id` didn't match `IronPostProcess` → fixed with explicit ID match
2. **terminationReason mismatch** — `reason != 0` filtered out `IronPostProcess` which uses reason=2 → removed check
3. **NC Programs count 0** — called `_update_nc_programs` before post when no entities exist → moved to post-completion
4. **File not found** — searched wrong folders → added `D:\Users\MainPC\Documents\NC Files For Transfer`
5. **File still not found** — `os.path.isfile()` unreliable → switched to `os.listdir()`
6. **File STILL not found** — `time.sleep()` on main thread blocked file write → moved to background thread ✅
7. **Cascading rename** — "any recent .nc" fallback renamed one file through all 6 setups → exact filename match only
8. **Permission denied on read** — Fusion holds file lock → retry with delays

---

## Session 2: TPM v1.4.0 — WCS Origin Description & ProShop Tool IDs

### Goals
Extend the NC file header with two new pieces of information:
1. **WCS origin description** — machinist-friendly description of where the origin is (e.g., "X: Center, Y: Near Side, Z: Top of Stock")
2. **ProShop tool IDs** — product IDs from the tool library added to existing tool comment lines

### Changes Made (v1.3.0 → v1.4.0)

#### 1. CAM Parameter Helpers
Added lightweight parameter extraction functions reused from ProShopBridge patterns:
- `_param_value(obj, param_name)` — get numeric/resolved value
- `_param_expr(obj, param_name)` — get string expression (strips quotes, skips unresolved ternaries)

#### 2. WCS Origin Description (Machinist-Friendly)
Fusion stores WCS origin as `wcs_origin_mode` (e.g., `stockFront`, `stockBoxPoint`, `modelBoxPoint`) and `wcs_origin_boxPoint` (e.g., `top center`, `top 1`). These are Fusion-internal terms.

TPM translates these into machinist-friendly descriptions:
- `_get_wcs_raw(setup)` — reads raw mode and box_point from Fusion parameters
- `_format_wcs_for_machinist(origin_mode, box_point)` — translates to shop floor language

**Translation logic:**
| Fusion Term | Machinist Description |
|---|---|
| X: left/right/center (from box_point) | X: Left / Center / Right |
| Y: front/back (from mode or box_point) | Y: Near Side / Center / Far Side |
| Z: top + stock mode | Z: Top of Stock |
| Z: top + model mode | Z: Top of Part |
| Z: bottom + stock mode | Z: Bottom of Stock |
| Z: bottom + model mode | Z: Bottom of Part |

**Fallback:** For unusual modes (selected point, model origin, feature-based) that can't be decomposed, falls back to Fusion's own text description.

**Example:** Fusion's `stockFront` + `top center` → `X: Center, Y: Near Side, Z: Top of Stock`

#### 3. ProShop Tool IDs in Tool Comments
- `_get_tool_list(setup)` — extracts unique tools from operations, reads `tool_productId` parameter for each
- `_enhance_tool_lines(lines, tools)` — finds post-processor tool comments matching `(T{N} ...)` pattern and inserts `ID={product_id}` after the tool number

**Before:** `(T1 D=2. CR=0.006 - ZMIN=-0.2224 - FACE MILL)`
**After:** `(T1 ID=I431 D=2. CR=0.006 - ZMIN=-0.2224 - FACE MILL)`

Only modifies lines where the tool has a product_id set in the Fusion tool library.

#### 4. Pipeline Integration
- WCS and tool data extracted during `apply_naming_to_setups()` and stored in `_naming_state`
- `_process_posted_files()` passes `wcs_display` and `tools` to `inject_header_into_file()`
- `inject_header_into_file()` accepts optional `wcs_display` and `tools` parameters

### Verified End-to-End Output (v1.4.0)

```
%
O0061 (TRA1-027336_OP60_v1)
(PART: TRA1-027336)
(OP: 60)
(VERSION: 1)
(WCS: G54 - X: Center, Y: Near Side, Z: Top of Stock)
(POSTED: 2026-03-14 17:51:06)
(PROGRAMMER: Thomas Buerkle)
(POST HYUNDAI KF5600II FANUC I V1.1.5)
(T1 ID=I431 D=2. CR=0.006 - ZMIN=-0.2224 - FACE MILL)
(T2 ID=B77 D=0.5 CR=0.03 - ZMIN=-0.4775 - BULLNOSE END MILL)
(T3 ID=A15 D=0.1875 CR=0. - ZMIN=-1.7128 - FLAT END MILL)
(T4 ID=Kenna1 D=0.1875 CR=0.01 - ZMIN=-1.5467 - BULLNOSE END MILL)
(T5 ID=B254 D=0.5 CR=0.09 - ZMIN=-1.5881 - BULLNOSE END MILL)
(T6 ID=Kenna2 D=0.1563 CR=0. - ZMIN=-1.6427 - FLAT END MILL)
(T7 ID=A248 D=0.5 CR=0. - ZMIN=-2.4663 - FLAT END MILL)
...
```

### Files Modified (v1.4.0)
- `TraxisProgramManager\TraxisProgramManager.py` — Added WCS description, tool ID injection, parameter helpers
- `TraxisProgramManager\TraxisProgramManager.manifest` — Version bumped to 1.4.0

### Key Design Decisions

1. **Machinist-friendly WCS vs Fusion coordinates**: Initial implementation used Fusion's internal XYZ coordinates from `setup.workCoordinateSystem`. User feedback: these are meaningless to the setup person. Replaced with origin mode/box point description translated to shop floor language (X/Y/Z relative positions).

2. **Fallback for unusual origins**: When WCS is set to a selected point, model origin, or feature, the X/Y/Z decomposition doesn't apply. Falls back to Fusion's own description text.

3. **Tool IDs from `tool_productId`**: ProShop product IDs are stored in Fusion's tool library as `tool_productId`. This links the NC file directly to ProShop's inventory system.

### Future Ideas

#### NC File Transfer Tool
Currently the programmer posts to `NC Files For Transfer` because the existing file transfer tool to CNC machines is slow to navigate to other folders. A custom transfer tool could:
- Know which part is running on which machine (via FocasMonitor + Shop Hub)
- Know where NC files live (Dropbox PART FILES, organized by Customer/PN)
- One-click transfer: pick a machine, auto-find the right program
- Tie into ProShop work order data for scheduling context
- Eliminate the need for the intermediate "NC Files For Transfer" folder

### Next Steps
- [ ] Fix TraxisCapture command ID detection (`IronPostProcess` instead of `'Post' in cmd_id`)
- [ ] Fix TraxisCapture background thread for Snapshot B (same main-thread blocking issue)
- [ ] Test full traceability chain: TPM headers + CAPTURE tags in same NC file
- [ ] Verify version incrementing on re-post (v1 → v2)
- [ ] Test PART FILES copy (need a part with existing customer folder)
- [ ] Run session_bridge.py with real data once TraxisCapture generates matched sessions
- [ ] Address setup name accumulation (investigate Fusion `job_programName` side effects)
- [ ] Build NC File Transfer Tool for direct machine transfer
- [ ] Test WCS description with different origin modes (model box point, selected point, turning)
- [ ] Verify tool IDs show correctly for tools without product_id set (should be unchanged)

---

*Session 1 date: March 14, 2026*
*Session 2 date: March 14, 2026*
