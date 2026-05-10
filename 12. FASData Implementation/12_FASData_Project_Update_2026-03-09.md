# 12. FASData Project Update
**Traxis Manufacturing — CNC Machine Utilization Monitoring**
**Project:** 12. FASData Implementation
**Date:** March 9, 2026

---

## Session Summary: Extended Collector Deployed

### What Was Done

**Problem:** The FocasMonitor collector source code had been significantly expanded (from 21 to 43 columns in `machine_samples`, plus 6 new tables), but the updated build was never deployed to the collector PC (WrkStationC). The production database was still running the original 21-column schema from February 2026.

**Changes Made:**

1. **Added auto-migration to Database.cs** — The collector now automatically detects the old schema on startup and adds missing columns via `ALTER TABLE`. No external Python script or manual migration needed.

2. **Rebuilt the collector** — Built with `dotnet publish -c Release -r win-x86 --self-contained true` so it runs on WrkStationC without needing .NET runtime installed separately.

3. **Created UPDATE_FOCASMONITOR.bat** — One-click deployment script placed in the publish folder. Handles stopping the service, killing lingering processes, copying files, and restarting. Right-click → Run as administrator.

4. **Deployed to WrkStationC** — Service successfully updated and running.

### New Data Being Collected

**machine_samples** expanded from 21 → 43 columns:
- System info: `cnc_type`, `mt_type`, `series`, `sw_version`, `max_axes`, `cnc_id`
- Extended status: `edit_status`, `warning`
- Program execution: `sequence_number`, `block_count`
- Active block: `active_block_content`, `capture_session_id`, `capture_op_id`, `capture_tool_id`
- Spindle: `spindle_load`
- Tooling: `tool_number`, `active_wcs`
- Additional axes: `axis_a`, `axis_b`
- Machine coordinates: `mach_x`, `mach_y`, `mach_z`
- Distance to go: `dtg_x`, `dtg_y`, `dtg_z`
- Servo loads: `servo_load_x`, `servo_load_y`, `servo_load_z`, `servo_load_a`
- Life counters: `diag_power_on_min`, `diag_cutting_min`, `diag_cycle_min`
- Tool life config: `tool_life_enabled`, `tool_life_type`

**6 new tables:**
- `tool_wear_samples` — H/D offset wear and geometry values
- `tool_life_samples` — Tool life management groups and remaining life
- `wco_samples` — Work coordinate offsets (G54-G59) with change detection
- `alarm_history` — Full alarm event log with deduplication
- `parameter_snapshots` — Periodic CNC parameter captures (~10 min interval)
- `program_directory` — Snapshot of programs loaded in controller memory

### Files Modified
- `FocasMonitor\Database.cs` — Added `MigrateSchema()` method

### Files Created
- `FocasMonitor\publish\UPDATE_FOCASMONITOR.bat` — One-click deployment script
- `12_FASData_Project_Update_2026-03-09.md` — This session log

### Verification
- Service confirmed running on WrkStationC
- Dropbox sync is hourly; new data will be visible on TRAXIS after next sync cycle

### Next Steps
- [ ] Verify new columns are populated after next Dropbox sync
- [ ] Update reporting scripts (`generate_report.py`, `generate_dashboard.py`) to use new fields
- [ ] Add per-tool cutting time queries (e.g., "how long did T23 cut on M8 today?")
- [ ] `active_wcs` column still not populated (FOCAS `cnc_modal()` struct marshaling needed)

---

*Session date: March 9, 2026*
