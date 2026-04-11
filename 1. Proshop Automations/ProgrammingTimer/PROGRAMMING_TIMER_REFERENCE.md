# Programming Timer — Development Log & Reference

## Status: Phase 1 Complete — Core Timer Working

As of 2026-02-15, the Programming Timer Fusion 360 add-in is deployed and logging data on the TRAXIS machine via Dropbox. Core functionality is verified.

---

## What It Does

Automatically tracks programming time per Fusion 360 document. Detects company files, starts a timer, pauses on document switch or idle, and logs sessions to a shared JSONL file. No manual start/stop required — the programmer barely notices it's running.

---

## Deployment

### File Locations
- **Source of truth:** `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProgrammingTimer\`
- **Fusion reads from:** `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProgrammingTimer\`
- **TRAXIS machine:** Symlinked — AddIns folder points to Dropbox via `mklink /D`
- **AbsoluteArm machine:** Needs symlink setup (same process)

### Symlink Setup (Per Machine)
Run as Administrator:
```
rmdir /s /q "%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProgrammingTimer"
mklink /D "%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProgrammingTimer" "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProgrammingTimer"
```
Adjust `D:\Dropbox` if Dropbox is on a different drive.

If Fusion loses the add-in from the list after symlink creation: Shift+S → Add-Ins → green + → "Script or add-in from device" → navigate to `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProgrammingTimer` → select `ProgrammingTimer.py`.

### Required Files in Add-In Folder
Only these 7 files should be in the deployed folder. No `.md` files, no `lib/`, no `commands/`, no `__pycache__/`. Fusion tries to compile everything in the folder and non-Python files can cause errors.

| File | Purpose |
|------|---------|
| `ProgrammingTimer.py` | Main add-in entry point |
| `ProgrammingTimer.manifest` | Fusion add-in metadata |
| `timer_core.py` | Timer logic, session management |
| `idle_detector.py` | Windows API idle/focus detection |
| `data_logger.py` | JSONL logging, mappings, crash recovery |
| `config.py` | Configuration loading, company file detection |
| `timer_config.json` | User-editable settings |

### Important: Folder/File Naming
Fusion 360 requires the folder name, `.py` filename, and `.manifest` filename to all match exactly. Easiest method: create via Fusion UI, then replace the `.py` contents.

---

## Configuration

### timer_config.json
```json
{
  "company_file_patterns": ["Traxis Main", "hub://Traxis", "D:/Dropbox/MACHINE COMM Traxis"],
  "idle_timeout_seconds": 120,
  "gap_threshold_seconds": 1800,
  "log_folder": "D:\\Dropbox\\MACHINE COMM Traxis\\Proshop Automation and Claude Projects\\1. Proshop Automations\\ProgrammingTimer",
  "programmer_name": "",
  "poll_interval_seconds": 15
}
```

- `company_file_patterns`: Matched against the full document path including project name. "Traxis Main" is the primary pattern.
- `idle_timeout_seconds`: 120 (2 minutes). Clock retroactively stops at last activity, not when buffer expires.
- `gap_threshold_seconds`: 1800 (30 minutes). Gaps longer than this start a new session.
- `programmer_name`: Empty = uses Windows username.
- `poll_interval_seconds`: 15. How often idle/focus state is checked.

---

## How It Works

### Company File Detection
- `get_document_path()` walks up the Fusion data file folder hierarchy and prepends `dataFile.parentProject.name`
- Result looks like: `Traxis Main/Parts library/ICON Tech/10-02004 (1) v32`
- `is_company_file()` checks if any pattern from `company_file_patterns` appears in this path
- "Traxis Main" matches all files under the Traxis hub

### Timer Flow
1. Document opens → check if company file → if yes, check for existing mapping
2. First open: dialog asks for part identifier (defaults to first word of doc name)
3. Subsequent opens: auto-starts with stored mapping, logs "[Timer] Tracking resumed: ..."
4. Document switch: previous timer pauses, new timer starts/resumes
5. Idle > 2 min: timer stops retroactively at last activity timestamp
6. Alt-tab away: all timers pause (detected via polling `is_fusion_foreground()`)
7. Document close or Fusion close: session finalized and written to JSONL

### Focus Detection
Fusion 360 does not expose `applicationActivated`/`applicationDeactivated` events. Focus is detected by polling every 15 seconds using Windows API (`GetForegroundWindow` + checking if Fusion is the active window).

### Crash Recovery
- `timer_state.json` stores active sessions with last activity timestamp
- On startup, orphaned sessions are finalized using `last_activity` as end time
- No data lost on Fusion crash

---

## Data Output

### Session Log
**File:** `programming_time_log.jsonl` in the ProgrammingTimer Dropbox folder

Each line is one completed session:
```json
{
  "document_name": "10-02004 (1) v32",
  "document_path": "Traxis Main/Parts library/ICON Tech/10-02004 (1) v32",
  "part_identifier": "10-02004",
  "date": "2026-02-15",
  "start_time": "2026-02-15T13:04:27",
  "end_time": "2026-02-15T13:12:50",
  "duration_seconds": 159,
  "programmer": "TRAXIS",
  "seat": "DESKTOP-NU8H1LI",
  "idle_timeout_count": 1,
  "version": "1.0.0"
}
```

### Document Mappings
**File:** `document_mappings.json` — stores document name → part identifier associations so the dialog doesn't appear on subsequent opens.

---

## Bugs Fixed During Development

### config.py Unicode Escape Error
**Problem:** CC wrote path strings with backslashes that Python interpreted as unicode escapes (`\U` in `\Users`).
**Fix:** Replaced all path construction with `os.path.join()` — no backslash literals anywhere in the file.

### applicationActivated Event Doesn't Exist
**Problem:** Fusion 360's `Application` object doesn't have `applicationActivated`/`applicationDeactivated` events. CC assumed they existed.
**Fix:** Removed event registrations. Focus detection moved to polling via `PollEventHandler` which calls `is_fusion_foreground()` from `idle_detector.py` every poll interval.

### Company File Path Missing Project Name
**Problem:** `get_document_path()` only returned `parentFolder.name/doc.name` (e.g., `ICON Tech/10-02004`). "Traxis Main" wasn't in the path so company file pattern matching failed.
**Fix:** Updated `get_document_path()` to use `dataFile.parentProject.name` and prepend it to the path.

### Fusion Template Files Causing Errors
**Problem:** Creating an add-in via Fusion UI generates `lib/`, `commands/`, `AddInIcon.svg`, and boilerplate files. These interfere with the add-in.
**Fix:** Delete everything except the 7 required files. Keep `.md` docs and extras out of the deployed folder.

---

## What's Verified (Test Results 2026-02-15)

| Test | Result |
|------|--------|
| Company file detection | PASS — "Traxis Main" in path, dialog appears |
| Non-company file ignored | PASS — files outside Traxis Main not tracked |
| Part identifier dialog | PASS — shows on first open, defaults to first word of doc name |
| Subsequent open skips dialog | PASS — "Tracking resumed" message |
| Document switching | PASS — pauses/resumes correct timers |
| Status panel | PASS — shows active/paused with correct times |
| Idle detection | PASS — idle_timeout_count incremented in log |
| Focus detection (alt-tab) | PASS — "deactivated/activated" messages in log |
| JSONL logging | PASS — clean entries with all fields |
| Multi-seat data | PARTIAL — TRAXIS machine logging, AbsoluteArm needs symlink |

---

## Phase 2: Bridge Integration (Future)

When ready to merge into ProShop Bridge:

- Replace text field part identifier dialog with Bridge's WO finder
- Associate timer sessions with work order numbers
- Push time data to ProShop (pending `users:w` scope resolution or Selenium/Tampermonkey workaround)
- Add timer display to Bridge palette UI
- Remove standalone add-in, fold all logic into `ProShopBridge.py`

---

## Phase 2: Other Enhancements (Future)

- Stopwatch icon for the Timer toolbar button
- Refine default part identifier parsing (currently takes first word — "Toolpath-Item 149" becomes "Toolpath-Item" which may not be ideal)
- Reporting/dashboard for accumulated data
- Shared credential/config utility across all Traxis automations
- AbsoluteArm machine symlink deployment
