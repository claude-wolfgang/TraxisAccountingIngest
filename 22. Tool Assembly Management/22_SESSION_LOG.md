# Tool Assembly Management — Session Log

## 2026-04-11 — Inventory Sync Service + Live Push to ProShop

### Inventory Sync Script (`inventory_sync.py`)
- New standalone script that pushes cabinet inventory counts to ProShop via GraphQL API
- Reads `tooling.db` cabinet counts (518 of 542 tools from April 6-7 kiosk sessions)
- Queries RTAs and work cell pockets from ProShop for in-use tool counts
- Ground truth = `cabinet_total + max(rta_count, wc_count)` per tool
- Pushes: `qtyInBin` (blue+green), `quantity` (total in shop), `purchasingNotes` (yellow/red condition)
- Notes format: `[Kiosk 2026-04-07] 2 worn, 1 replace` — replaces prior kiosk lines
- Off-hours gate (18:00-05:00 weekdays, all day weekends)
- `--dry-run` and `--loop N` flags
- Sync log table tracks pushes to avoid redundant writes

### Overseer Integration
- Added `InventorySync` service to Overseer with `--loop 3600` (hourly)
- Database health validator checks sync log freshness and push counts

### Live Run Results
- **485 tools updated**, 242 condition notes written, 0 errors, 16 not in ProShop
- Key corrections: R66 (4→6, +1 work cell), A1039 (4→1, +1 work cell), A1003 (4→5, +1 RTA)
- Corrects 118+ false tool shortages caused by inflated ProShop quantities

### Key Findings
- `qtyInBin` is writable but returns null when read via API
- ProShop quantities systematically inflated (purchases auto-add, retirements rarely happen)
- 62 tools found in work cells but NOT in any RTA — must query both sources
- `max(rta, wc)` avoids double-counting tools that are in both an RTA and a work cell pocket

### Files Created/Modified
- `inventory_sync.py` — new sync script (460 lines)
- `1. Proshop Automations/Overseer/overseer.py` — added InventorySync service config + validator

---

## 2026-04-06 (Session 2) — Cleanup, Inventory Import, Touchscreen Fix

### Directory Cleanup
- Created `tool-kiosk/old/` directory
- Moved 11 non-essential files out of root: one-time fix scripts (`fix_h0024_rta.py`, `populate_mill8.py`), debug utilities (`debug_oauth.py`, `introspect_rta.py`, `test_pocket_write.py`), old shortcuts, `nul` file, `session_log.md`, `setup_kiosk_pc.bat`, `tool computer db path.txt.txt`
- Root now has only essential runtime files
- Created `INSTRUCTIONS.txt` with start/stop/restart procedures

### Touchscreen Fix
- Diagnosed touch not working on Kiosk PC — was a Windows display-touch mapping issue, not code
- Created `Fix Touchscreen.md` guide for future reference
- Added `/touch-test` diagnostic page to Flask app for verifying touch events

### ProShop Tool Import
- Fixed `proshop_client.py` `get_all_tools()` — removed unsupported `page` argument from GraphQL query, increased `pageSize` to 1000
- Imported 907 tools from ProShop into `tool_inventory` table
- Deleted 365 auto-generated D10xxx drill catalog entries (ProShop system tools)
- Added D10xxx filter to import endpoint so they won't come back on re-import
- Renamed G-252 to G252 to match ProShop fix
- **542 tools** now in inventory, ready for Full Inventory sessions

### Inventory Sort Order
- Fixed tool inventory sort: now sorts by numeric suffix first (`A1, R2, O3, O4, R5...`) instead of alphabetically by tool number
- SQL: `ORDER BY CAST(REPLACE(LTRIM(tool_number, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '-', '') AS INTEGER), tool_number`
- Applied to all 3 inventory queries in `database.py` (list, search, session next item)

### Inventory Session Management
- `startFullInventory()` now reuses existing open session instead of creating duplicates
- Added "Abandon" button + `POST /api/inventory/session/<id>/abandon` endpoint to delete stale sessions
- Cleared 4 orphaned open sessions from database

### Browser Caching Disabled
- Added `@app.after_request` handler sending `Cache-Control: no-cache, no-store, must-revalidate` on all responses
- Removed cache buster versions (`?v=N`) from `style.css` and `kiosk.js` references — no longer needed

### Chrome Crash Loop
- Identified Chrome crash-looping (36+ consecutive crashes) from `kiosk_launcher.log`
- Root cause: corrupted `ToolKioskChromeProfile` — fix is to delete `%LOCALAPPDATA%\ToolKioskChromeProfile`

### STOP KIOSK.bat Fix
- Added fallback methods to close the START KIOSK console window (wildcard title match + cmd.exe process kill)

### Files Modified
- `app.py` — no-cache headers, touch-test page, abandon session endpoint, D10xxx import filter
- `database.py` — natural numeric sort on inventory queries
- `proshop_client.py` — fixed `get_all_tools()` pagination
- `kiosk.js` — session reuse in `startFullInventory()`, `abandonInventorySession()` function
- `kiosk.html` — Abandon button on resume bar, removed JS cache buster
- `base.html` — removed CSS cache buster
- `STOP KIOSK.bat` — better launcher window cleanup
- `INSTRUCTIONS.txt` — new file
- `Fix Touchscreen.md` — new file
