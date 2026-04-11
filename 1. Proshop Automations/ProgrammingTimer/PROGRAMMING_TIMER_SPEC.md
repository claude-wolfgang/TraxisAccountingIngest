# Programming Timer — Fusion 360 Add-In Spec

## Purpose

A standalone Fusion 360 add-in that automatically tracks programming time per document. It runs silently in the background, detecting when the programmer is actively working, idle, or switched away. It logs session data locally with timestamps and durations so Traxis Manufacturing can build a reliable dataset of actual programming time per part.

This is Phase 1 — timer only, no ProShop integration. It will later be folded into the ProShop Bridge add-in where it will inherit work order mapping and API push capabilities.

---

## Core Behavior

### Automatic Start
- When a Fusion 360 document is opened, check if it's a **company file** (see Company File Detection below).
- If it's a company file, the timer **must** start. There is no opt-out.
- On first open: show a dialog asking the user to confirm or enter the **part identifier** (document name is the default — this is a placeholder until ProShop Bridge integration adds WO selection).
- On subsequent opens: the add-in remembers the mapping and starts the timer automatically. Show a brief **toast notification**: "Tracking time: [document name]" so the programmer knows it's running.

### Company File Detection
- Detect based on **file path or Fusion 360 project/hub location**. Company files live in the Traxis team hub or a specific local/Dropbox folder.
- The detection rule should be **configurable** — store the matching pattern (path prefix, hub name, etc.) in a simple config so it can be adjusted without editing code.
- Non-company files (personal projects, test files, tutorials) are ignored entirely — no dialog, no tracking.

### Document Switching
- Fusion 360 fires a `documentActivated` event when switching between open documents.
- When the active document changes:
  - **Pause** the timer for the previous document.
  - **Resume** (or start) the timer for the newly active document.
- Maintain a **dictionary of active timers** keyed by document identifier. Each document accumulates time independently.

### Idle Detection
- Monitor for user inactivity (no mouse movement or keyboard input **within Fusion 360**).
- **Idle buffer: 2 minutes.** If no input for 2 minutes, the timer retroactively stops the clock at the **timestamp of the last detected activity**, not at the moment the buffer expires.
- Example: Last activity at 10:15. Buffer expires at 10:17. Timer records up to 10:15. User returns at 10:40 — timer resumes from 10:40.
- Use the Fusion 360 API's input events if available, or a polling approach checking mouse position / application state at regular intervals (e.g., every 15-30 seconds).

### Background/Foreground Detection
- If Fusion 360 loses focus (user switches to Chrome, file explorer, etc.), **all timers pause**.
- When Fusion 360 regains focus, the timer for the **currently active document** resumes.
- Use `applicationActivated` / `applicationDeactivated` events if available in the Fusion API, or check window focus state via polling.

### Session Management
- A **session** is a continuous period of active programming on one document.
- Sessions end when:
  - The document is closed.
  - The idle buffer expires (session ends at last activity timestamp).
  - Fusion 360 is closed.
  - The add-in is stopped.
- A new session starts when:
  - Activity resumes after an idle timeout.
  - The document is re-opened (same day or different day).
- Each session records:
  - `document_name` — Fusion document name
  - `document_path` — full path or hub location if available
  - `part_identifier` — user-confirmed part name/number (defaults to document name)
  - `date` — calendar date (YYYY-MM-DD)
  - `start_time` — ISO 8601 timestamp
  - `end_time` — ISO 8601 timestamp
  - `duration_seconds` — total active seconds in this session
  - `programmer` — Windows username or configurable name
  - `seat` — machine/computer name

### Gap Detection
- If more than **30 minutes** have elapsed since the last recorded activity on a document (e.g., overnight, long meeting), start a **new session** rather than appending to the old one.
- This prevents a single session from spanning overnight or across long breaks.

---

## Data Storage

### Log File
- **Format:** JSON Lines (`.jsonl`) — one JSON object per line, one line per completed session. Easy to append, easy to parse, easy to aggregate later.
- **Location:** `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProgrammingTimer\programming_time_log.jsonl`
- **Fallback locations** (try in order):
  1. `D:\Dropbox\MACHINE COMM Traxis\...` (primary)
  2. `C:\Users\<username>\Dropbox\MACHINE COMM Traxis\...`
  3. `C:\Users\<username>\Documents\ProgrammingTimer\` (last resort)
- All seats write to the **same file** via Dropbox sync. JSONL handles concurrent appends well since each entry is a single line.

### Session Entry Format
```json
{
  "document_name": "10957 CAM",
  "document_path": "hub://Traxis/projects/...",
  "part_identifier": "10957",
  "date": "2026-02-14",
  "start_time": "2026-02-14T08:32:15",
  "end_time": "2026-02-14T09:14:42",
  "duration_seconds": 2547,
  "programmer": "TRAXIS",
  "seat": "TRAXIS-CAM1",
  "idle_timeout_count": 2,
  "version": "1.0.0"
}
```

### Document-to-Part Mapping Persistence
- Store the mapping of document names to part identifiers in a separate file: `document_mappings.json` in the same folder.
- Format:
```json
{
  "10957 CAM": "10957",
  "Mold CAM v3": "MOLD-2026-003",
  "compression disk": "TRA1-COMP-DISK"
}
```
- When a known document is opened, skip the dialog and use the stored mapping.
- When an unknown company document is opened, show the dialog, then save the mapping.

---

## User Interface

### Minimal — This Is a Background Tool
- **No palette tab, no complex UI.** This is intentionally lightweight.
- **Toolbar button** in the Utilities panel (or alongside the future Bridge button) that shows a small status panel when clicked.

### Status Panel (Small Dialog or HUD)
- Shows currently tracked documents and their running time today.
- Example:
  ```
  Programming Timer
  ─────────────────
  ● 10957 CAM        1h 23m (active)
  ○ Mold CAM v3      0h 45m (paused)
  
  Today total: 2h 08m
  ```
- `●` = actively timing, `○` = paused (document open but not active).
- Clicking the button toggles this panel. No other interaction needed.

### First-Open Dialog
- Triggered when an unrecognized company file is opened.
- Simple dialog:
  ```
  New file detected: "10957 CAM"
  
  Part identifier: [10957 CAM________]
  
  [Start Tracking]
  ```
- The text field defaults to the document name. The programmer can edit it to a part number or leave as-is.
- Single button, no cancel option — tracking is mandatory for company files.

### Toast Notification
- When a previously mapped document is opened:
  ```
  ⏱ Tracking: 10957 (resumed)
  ```
- Use Fusion's `ui.messageBox` with a short auto-dismiss if possible, or the palette message system. If Fusion doesn't support auto-dismiss, use the Text Commands log instead — just print `[Timer] Tracking resumed: 10957`.

---

## Technical Implementation Notes

### Fusion 360 API Events to Use
- `documentOpened` — trigger company file check and timer start
- `documentActivated` — switch active timer between documents
- `documentClosing` or `documentClosed` — end session, save data
- `documentSaving` — NOT relevant for timing but don't interfere with it
- Application-level activate/deactivate events for foreground detection

### Idle Detection Approach
- **Preferred:** Use Fusion's `InputChangedEvent` or mouse/keyboard events if available at the application level.
- **Fallback:** Poll at 15-second intervals. Check cursor position relative to Fusion window, or use `ctypes` / `win32gui` to check the foreground window handle against Fusion's HWND. If position hasn't changed and Fusion isn't the foreground window, increment idle counter.
- **Important:** Idle detection must work even when the programmer is just rotating the model, zooming, or orbiting — those are active programming activities. Only true inactivity (nothing happening at all) should trigger idle.

### Threading
- Timer logic should run on the **main thread** since it's mostly event-driven and lightweight.
- File I/O (appending to JSONL) can happen on the main thread too — it's a single line append, negligible time.
- No background threads needed for Phase 1. Keep it simple.

### State Recovery
- On add-in start, check for any **orphaned sessions** — sessions that were started but never properly closed (e.g., Fusion crashed).
- If found, close them with the end time set to the last recorded activity timestamp.
- Store in-progress session state in a `timer_state.json` file alongside the log:
```json
{
  "active_sessions": {
    "10957 CAM": {
      "part_identifier": "10957",
      "session_start": "2026-02-14T08:32:15",
      "last_activity": "2026-02-14T09:14:42",
      "accumulated_seconds": 2547
    }
  }
}
```
- On clean shutdown (add-in stop, Fusion close), finalize all sessions and clear the state file.
- On startup, if state file has data, finalize those orphaned sessions using `last_activity` as end time.

### Configuration File
- `timer_config.json` in the add-in folder:
```json
{
  "company_file_patterns": ["hub://Traxis", "D:\\Dropbox\\MACHINE COMM Traxis"],
  "idle_timeout_seconds": 120,
  "gap_threshold_seconds": 1800,
  "log_folder": "D:\\Dropbox\\MACHINE COMM Traxis\\Proshop Automation and Claude Projects\\1. Proshop Automations\\ProgrammingTimer",
  "programmer_name": "",
  "poll_interval_seconds": 15
}
```
- If `programmer_name` is empty, use Windows username.

---

## File Structure

```
ProgrammingTimer/
├── ProgrammingTimer.py          # Main add-in entry point
├── ProgrammingTimer.manifest    # Fusion add-in manifest
├── timer_core.py                # Timer logic, session management
├── idle_detector.py             # Idle/focus detection
├── data_logger.py               # JSONL file I/O, state persistence
├── config.py                    # Configuration loading
├── timer_config.json            # User-editable configuration
└── README.md                    # Brief usage notes
```

### Manifest
```json
{
  "autodeskProduct": "Fusion",
  "type": "addin",
  "id": "ProgrammingTimer-Traxis-001",
  "author": "Traxis Manufacturing",
  "description": {
    "": "Automatic programming time tracker"
  },
  "version": "1.0.0",
  "runOnStartup": true,
  "supportedOS": "windows"
}
```

### Deployment
- **Source:** `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProgrammingTimer\`
- **Deployed:** `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\ProgrammingTimer\`
- Same dual-location pattern as the ProShop Bridge.

---

## What This Does NOT Include (Phase 2 — Bridge Integration)

These are explicitly out of scope for now. Listing them so Claude Code doesn't try to build them:

- **No ProShop API calls.** No OAuth, no GraphQL, no time tracking mutations.
- **No work order selection.** The part identifier is just a text field for now. WO finder comes when this merges into the Bridge.
- **No ProShop push of time data.** Data stays local in the JSONL file.
- **No palette tab in the Bridge.** This is a separate add-in for now.
- **No reporting or dashboards.** The JSONL file is the output. Analysis comes later.

---

## Success Criteria

1. Opening a company file in Fusion automatically starts tracking time with no more than one click (first open only).
2. Switching between documents correctly pauses/resumes the right timers.
3. Going idle for 2+ minutes stops the clock at the right timestamp.
4. Alt-tabbing away from Fusion pauses all timers.
5. Closing a document or Fusion properly finalizes and logs the session.
6. Fusion crash doesn't lose data — orphaned sessions are recovered on next start.
7. Multiple seats can write to the same JSONL log file via Dropbox without corruption.
8. The programmer barely notices it's running.
