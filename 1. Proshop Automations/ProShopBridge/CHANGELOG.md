# ProShopBridge Changelog

## 2026-05-13 — v1.5.3 — Drop fake ~256KB written-description limit

The "ProShop has a ~256KB limit on the written description field" rule was
folklore, not real. Three pieces of defensive code built on top of it were
either harmless-but-misleading or actively harmful:

- `ProShopBridge.py` push flow: if payload > 250 KB, silently regenerated the
  written-description HTML with all screenshots stripped before sending.
  Removed — pushes that would have worked now go through with their images.
- `proshop_selenium_helper.py`: pre-flight check that hard-aborted with
  `sys.exit(1)` if payload > 250 KB. Removed — Selenium will attempt any size.
- `composite_screenshots.ps1`: comment justifying the 1280×720 quadrant target
  with the fake limit. Updated to drop the reason. Dimensions kept as a
  reasonable default; bump them later if you want sharper screenshots.

Unrelated to the suppression-filter work in v1.5.1/v1.5.2 — those are still in
effect.

## 2026-05-13 — v1.5.2 — Suppression filter: use isSuppressed + parent walk

### Bug
v1.5.1 still let suppressed operations through to sequence detail and written
description.

### Root Cause
v1.5.1 filtered on `getattr(op, 'isActive', True)`. `isActive` is not exposed on
`adsk.cam.Operation` in this Fusion version, so `getattr` returned the default
`True` for every op and the filter never removed anything — a silent no-op.

### Fix
New `_is_op_suppressed()` helper checks `op.isSuppressed` directly, then walks
the parent chain (bounded to 16 hops) checking each ancestor's `isSuppressed`.
That covers both a directly-suppressed op and an op inside a suppressed
folder/pattern.

Log line now names each skipped op so we can verify behavior in Text Commands:
`Skipped 2 suppressed op(s) in setup 'Op10': Drill Ø.250, Chamfer`.

## 2026-05-13 — v1.5.1 — Skip suppressed operations

### Bug
Push to ProShop included suppressed operations: their tools/descriptions appeared in
sequence detail rows and in the written description HTML, even though Fusion itself
excludes suppressed ops from posted G-code. User observed two suppressed ops landing
in sequence detail.

### Root Cause
`get_all_operations(setup)` iterated `setup.allOperations` (with folder/pattern
fallbacks) and returned every op with no active/suppressed filter. Both
`generate_sequence_details()` and `generate_written_description_html()` consumed the
unfiltered list.

### Fix
Added `_filter_active()` helper applied at both return paths of `get_all_operations()`.
Filter checks `getattr(op, 'isActive', True)` — `isActive` is False if the op itself
is suppressed OR any ancestor folder/pattern is suppressed, so a single check covers
both cases. The `getattr` default of `True` is defensive for op types (e.g. manual NC)
that may not expose the property.

Side effect: setup picker `operationCount` in the UI now reflects active-only too,
matching what'll actually be pushed.

Skipped ops logged for forensics: `Skipped N suppressed/inactive operation(s) in setup '<name>'`.

## 2026-03-23 — Fix camera reset after screenshot capture

### Bug
Pushing written description to ProShop left Fusion's viewport in perspective/ISO mode.
The user's orthographic view was not preserved.

### Root Cause
`capture_setup_screenshots_base64()` iterates through 4 views (top, front, right, ISO),
ending with the ISO view in `PerspectiveCameraType`. The function never restored the
original camera state, so the viewport remained in perspective after returning.

Same issue in `_capture_single_screenshot()` (audit screenshots).

### Fix
Both functions now save the viewport camera before manipulation and restore it after
all screenshots are captured. Camera restoration runs in both success and error paths.

## 2026-03-13 — Selenium & Tampermonkey Fixes (VERIFIED WORKING)

Debug session on Garrett's ASUS workstation. Investigated G-Code Tool # showing product ID
(`460`) instead of Fusion tool number (`11`) for T11 on NP000674 Op 60.

### Investigation: G-Code Tool # API Field

Ran full GraphQL introspection against `UpdatePartOperationToolInputData` via Node.js.
Confirmed that **G-Code Tool # has no corresponding GraphQL field**. The HTML form uses
`machinetoolnumber` but ProShop/Adion does not expose it in the API. All 17 writable
fields documented in `PROSHOP_BRIDGE_REFERENCE.md`.

Previously tried field names (all rejected): `machineToolNumber`, `gCodeTool`, `gcodeTool`,
`toolNumber`, `gcodeToolNumber`, `ncToolNumber`.

The `ncDescription` field maps to the "Description" column (auto-populated by ProShop from
tool library when Tool # is a library number) — NOT G-Code Tool #.

**Selenium helper is the only automated way to set G-Code Tool #.**

### Fix: Selenium helper URL bug (`proshop_selenium_helper.py`)

Lines 143 and 153 used `$formName=toolDetail` instead of `?formName=toolDetail`.
This caused Selenium to navigate to broken URLs, never find the sequence detail table,
and silently fail. G-Code Tool # was never being set by Selenium.

### Fix: Selenium helper — overwrite existing values

Previously, G-Code Tool # was only filled if the field was empty (`if (!gcodeVal && gcodeInput)`).
Changed to always overwrite — Fusion data is authoritative. This fixes cases where a wrong
value (e.g. product ID digits) was already in the field.

### Fix: Tampermonkey frameset detection (v1.3.1)

ProShop uses `<frameset>` pages. The bridge parameters (`psBridge=`, `writtenDescription`)
are only on the top-level URL that Fusion opened, but the script skips frameset pages (no
`<body>` to inject into). Child frames have different URLs without these parameters.

Added `window.top.location.href` check so child frames can detect bridge mode from the
parent URL. This fixes the badge and paste button not appearing on Garrett's machine.

### Fix: Tampermonkey G-Code Tool # overwrite (v1.3.1)

Same as Selenium fix — now overwrites existing G-Code Tool # values instead of skipping.

### Setup: Garrett's ASUS workstation

Installed Python 3.14 + Selenium 4.41 on this machine. ProShopBridge.py `_find_system_python()`
auto-detects at `%USERPROFILE%\AppData\Local\Programs\Python\Python314\python.exe`.

### Verified

Ran Selenium helper manually against NP000674 Op 60:
```
python proshop_selenium_helper.py --part-number UTA1-NP000674 --op-number 60 --visible
```
Result: 16 rows sorted, 9 G-Code Tool # values set and saved. T11 now correctly shows `11`
instead of `460`. Data is saved server-side — visible on all machines without Tampermonkey.

**Note:** Part number must include customer prefix (e.g. `UTA1-NP000674`, not just `NP000674`).
This is how ProShopBridge.py calls it from the push pipeline.

## v1.4.0 — 2026-02-16 — Freeze Audit Fixes

Addresses High findings H1 and H2 from `FREEZE_AUDIT_REPORT.md`.
Reduces main-thread blocking during the push-to-ProShop workflow.

### New Function: `_doEvents_wait(seconds)` (fixes H1)

Replaces all `time.sleep()` calls in screenshot capture with a UI-friendly
alternative. Instead of a single blocking sleep, it runs micro-sleep iterations:
```
for _ in range(iterations):
    adsk.doEvents()    # let Fusion process pending UI events
    time.sleep(0.05)   # 50ms micro-sleep
```
This keeps the total wait duration the same but prevents Fusion from showing
"(Not Responding)" during screenshot capture. The UI stays responsive
between each 50ms micro-sleep.

**Affected locations** (all in `capture_setup_screenshots_base64()`):
- After `setup.activate()` — 0.5s wait (10 iterations)
- After `viewport.refresh()` — 0.5s wait (10 iterations)
- After `viewport.fit()` — 0.3s wait (6 iterations)
- Per-view camera set + fit — 0.3s x2 per view x4 views = 2.4s total (48 iterations)

### Changed: `capture_setup_screenshots_base64()` return value (fixes H2)

Now returns `(screenshots_b64, temp_dir)` tuple instead of just `screenshots_b64`.
The composite creation and temp file cleanup have been extracted into a separate
function so they can run on the background push thread.

### New Function: `_composite_and_cleanup(screenshots_b64, temp_dir, setup_idx)` (fixes H2)

Extracted from the end of `capture_setup_screenshots_base64()`. Contains:
- PowerShell `subprocess.run()` for 2x2 composite image creation (up to 15s timeout)
- Temp file cleanup (`glob` + `os.remove` + `os.rmdir`)

Now called from `_bg_push()` (background thread) instead of the main thread.
This moves 0-15 seconds of potential blocking off the main thread entirely.

### Changed: `_process_next_setup()` / `_bg_push()`

- `_process_next_setup()` unpacks the new `(screenshots_b64, temp_dir)` return value
- `_bg_push()` calls `_composite_and_cleanup()` as its first step (background thread)
- HTML generation and result reporting use `final_screenshots` from composite output

### Medium fixes

- **M3**: All 23 bare `except:` clauses replaced with `except Exception:` to avoid
  swallowing `SystemExit`/`KeyboardInterrupt`

### Findings Addressed

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| H1 | High | `time.sleep()` freezes UI for 4-5s during screenshots | Replaced with `_doEvents_wait()` micro-sleep loops |
| H2 | High | `subprocess.run(powershell, timeout=15)` on main thread | Moved to `_bg_push()` background thread |
| M3 | Medium | Bare `except:` swallows `SystemExit`/`KeyboardInterrupt` | Replaced with `except Exception:` |
| L2 | Low | Backup `.py` files (v1.2.0, v1.3.0) wasting 125KB | Deleted |
