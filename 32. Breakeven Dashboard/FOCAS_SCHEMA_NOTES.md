# FOCAS Database Schema Notes

Discovered 2026-04-16 by inspecting `C:\FASData\monitoring.db` (SQLite).

## Database Location & Engine

- **Engine:** SQLite 3
- **Path:** `C:\FASData\monitoring.db`
- **Config source:** `focasmonitor/machines.json` — `databasePath` field
- **Poll interval:** 60 seconds (configured in machines.json)

## Tables

| Table | Rows | Notes |
|-------|------|-------|
| machine_samples | 236,305 | Primary runtime/status log |
| alarm_history | 172 | Alarm events |
| parameter_snapshots | 39,465 | CNC parameter backups |
| program_directory | 0 | Empty |
| tool_life_samples | 0 | Empty |
| tool_wear_samples | 0 | Empty |
| wco_samples | 0 | Empty |

## machine_samples — Primary Table

### Date Range

- **Earliest:** 2026-03-11T11:12:09 CDT
- **Latest:** 2026-04-16T10:30:35 CDT (~5 weeks of data)

### Machines in DB

| machine_id | machine_name | Rows | Notes |
|------------|-------------|------|-------|
| M2 | FANUC Mill 2 | 47,263 | Enabled |
| M3 | FANUC Mill 3 | 47,263 | Enabled |
| M6 | FANUC Mill 6 | 47,263 | Enabled |
| M8 | FANUC Mill 8 | 11,818 | Name changed mid-stream |
| M8 | Hyundai-Wia KF5600II | 35,445 | Current name for M8 |
| T2 | YCM NTC1600LY | 47,263 | Lathe |

**Note:** M8 has two names in the DB. "FANUC Mill 8" is the old name; "Hyundai-Wia KF5600II" is current. The aggregator should treat both as machine_id=M8.

machines.json lists 8 machines but only 5 are `enabled: true` (M2, M3, M6, M8, T2). M4, M5, M7 are disabled (Robodrills needing Ethernet).

### Key Columns for Runtime

| Column | Type | Values Observed |
|--------|------|-----------------|
| run_status | TEXT | `STRT`, `STOP`, `HOLD`, `***`, NULL |
| mode | TEXT | `MEM`, `MDI`, `HANDLE`, `EDIT`, `JOG`, `REF`, NULL |
| motion | TEXT | `MTN`, `DWL`, `***`, NULL |
| connected | INTEGER | 0 or 1 |
| spindle_speed | INTEGER | 0-8999+ |
| spindle_load | INTEGER | 0-100+ |
| program_number | INTEGER | O-number |
| tool_number | INTEGER | Active tool |

### run_status Distribution (all data)

| Value | Count | Meaning |
|-------|-------|---------|
| NULL | 157,834 | Machine disconnected (correlates 1:1 with connected=0) |
| `***` | 38,345 | Reset / not executing |
| `STRT` | 19,322 | Program running — **this is the runtime signal** |
| `STOP` | 18,881 | Program stopped |
| `HOLD` | 1,928 | Feed hold |

### Runtime Signal Decision

**Chosen signal: `run_status = 'STRT'`**

This maps directly to FOCAS2 `cnc_statinfo.run` = RUN (program executing). It is present in the DB and well-populated. No fallback to spindle RPM needed.

- NULL run_status = machine not connected (confirmed: 157,834 nulls = 157,833 disconnected rows, off by 1)
- `***` = machine connected but no program active
- `STRT` = actively cutting or traversing within a program — this is billable time

### Sample Interval

~60 seconds between samples per machine (confirmed from timestamps). The aggregator should compute median interval per machine dynamically in case the poll rate changes.

### Diagnostic Counters

`diag_power_on_min`, `diag_cutting_min`, `diag_cycle_min` columns exist but are **all NULL** for every row. These Fanuc diagnostic counters are not being captured by the current collector. Not usable for runtime calculation.

**Follow-up:** Consider extending FocasMonitor.exe to read FOCAS diagnostic parameters 6750 (power-on time) and 6752 (cutting time). These are cumulative counters and would provide a second source of truth.

### Gap Handling

With 60s polling, any gap > 120s between consecutive samples for a machine should be treated as monitor downtime. The spec says 60s threshold; given the 60s poll interval, using 120s (2x interval) is more appropriate to avoid false gaps.

## Other Tables

### alarm_history
172 rows. Contains alarm_number, alarm_type, alarm_message per machine with timestamps. Not needed for runtime but useful for future dashboards.

### parameter_snapshots
39,465 rows. CNC parameter backups per machine. Not relevant to runtime.
