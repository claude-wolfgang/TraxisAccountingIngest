# Programming Timer — Fusion 360 Add-In

Automatic programming time tracker for Traxis Manufacturing.

## What It Does

- Automatically tracks time spent programming in Fusion 360
- Detects company files vs personal files (only tracks company files)
- Handles document switching (pauses/resumes correct timers)
- Detects idle time (2 minute buffer) and pauses tracking
- Detects when Fusion loses focus and pauses all timers
- Logs session data to JSONL file for analysis
- Recovers gracefully from crashes

## Installation

1. Copy the `ProgrammingTimer` folder to:
   `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\`

2. In Fusion 360: Shift+S → Add-Ins → Enable ProgrammingTimer

The add-in runs automatically on startup.

## Usage

The add-in runs silently in the background. When you open a company file:

1. **First time:** A dialog asks you to confirm/enter the part identifier
2. **Subsequent times:** Tracking starts automatically with a log message

Click the **Timer Status** button in the Utilities tab to see:
- Currently tracked documents
- Time accumulated today
- Active/paused state

## Configuration

Edit `timer_config.json` to customize:

- `company_file_patterns`: Paths/hubs that identify company files
- `idle_timeout_seconds`: Time before idle detection triggers (default: 120)
- `gap_threshold_seconds`: Gap that starts a new session (default: 1800)
- `log_folder`: Where to save the time log
- `programmer_name`: Your name (uses Windows username if blank)
- `poll_interval_seconds`: How often to check for idle (default: 15)

## Data Files

All data files are stored in the log folder (shared via Dropbox):

- `programming_time_log.jsonl` — Session log (one JSON per line)
- `document_mappings.json` — Document-to-part ID mappings
- `timer_state.json` — Active sessions (for crash recovery)

## Version

1.0.0 — Phase 1: Timer only, no ProShop integration
