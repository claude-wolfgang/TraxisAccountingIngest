# FASData Project Update — 2026-03-19

## TraxisTransfer: Right Panel Rework (Active WO + Smart Last-Sent)

Replaced the dual-pane file browser layout with a workflow-driven right panel.

### New Layout (top to bottom)
1. **Active Work Order** — queries ProShop for the WO running on the selected machine
2. **Last Sent Program** — shows the latest version of the last-sent file, with embedded SEND button
3. **CNC Programs** — existing program browser (unchanged), with RECEIVE button below

### New Files
- `src/traxistransfer/ui/wo_panel.py` — `WorkOrderPanel(CTkFrame)` displaying WO#, Part#, Customer PN. States: loading, WO info, no active WO, ProShop unavailable.
- `src/traxistransfer/ui/last_sent_panel.py` — `LastSentPanel(CTkFrame)` displaying the ready-to-send file with SEND button. Shows version hint when a newer version exists on disk (e.g., "latest — v3 was last sent"). States: file ready, no history, file missing.

### Modified Files
- `services/audit_log.py` — Added `get_last_sent_to_machine(conn, machine_id)` to query the most recent successful SEND for a machine. Uses `ORDER BY timestamp DESC, id DESC` for deterministic ordering.
- `services/folder_resolver.py` — Added `find_latest_version(file_name, folders)` static method. Parses TPM naming (`{PN}_OP{XX}_v{N}.nc`) to find the highest version of the same PN+OP across resolved folders. Falls back to exact filename match for non-TPM files.
- `ui/app_window.py` — Removed `FileBrowser` and action button bar. Replaced with stacked WO panel + Last Sent panel + Program browser + Receive button. Send button moved into `LastSentPanel`. Removed `_selected_file` and `_update_button_state` (no longer needed).
- `main.py` — On machine select: (1) async ProShop WO lookup → `WorkOrderPanel`, (2) audit log last-sent query + `find_latest_version` → `LastSentPanel`, (3) async CNC program listing → `ProgramBrowser`. After successful send, Last Sent panel auto-refreshes.

### Kept As-Is
- `ui/file_browser.py` — still in codebase, no longer used in main layout (available for future use)
- `ui/program_browser.py` — unchanged, lower pane

### Tests
- **84 tests passing** (was 72)
- +4 tests for `get_last_sent_to_machine` (most recent send, ignores failures, scoped to machine, returns None)
- +8 tests for `find_latest_version` (higher version, same file, different OP/PN, non-TPM found/missing, TPM missing, multi-folder search)

### Next Steps
- Launch app and verify visually with a real Fanuc machine
- Confirm WO panel populates when ProShop is reachable
- Confirm Last Sent panel shows latest version after a previous send
- Confirm Send/Receive buttons work from their new locations
