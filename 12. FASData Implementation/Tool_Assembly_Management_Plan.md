# Tool Assembly Management System — Implementation Plan

## Context

Traxis Manufacturing needs to track physical tool assemblies (CAT40 holders + cutters) through their lifecycle: cutter installation, machine assignment, usage accumulation, cutter replacement, and cross-machine movement. Currently there is no system linking a physical tool to its cutting history, wear data, or job usage. Setup guys cross-reference paper setup sheets, ProShop pocket tables, and their own memory.

The system integrates three existing platforms:
- **ProShop ERP** — work cell pockets (tool assignments, wear, offsets), sequence details (tool lists per job), scheduled work
- **FASData/FocasMonitor** — real-time machine data (cutting time, spindle load, tool wear registers) polled every 60s
- **COTS Kiosk** (Project 17) — proven Flask + QR scanning + touch UI architecture, ~85% reusable

## Core Concept

**The CAT40 holder is the tracked entity.** Each holder gets a laser-engraved QR code (paper labels for prototyping). Cutter swaps are events logged against the holder. FASData accumulates cutting time and wear passively. ProShop stays synchronized.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tracking level | Holder (not individual cutter) | Holders are persistent, cutters are consumable swap events |
| Database | Separate tooling.db (not in monitoring.db) | Avoids concurrent writer conflicts with FocasMonitor C# service |
| Usage rollup | Python script every 5 min via Task Scheduler | No modifications to stable FocasMonitor service |
| Machine-to-ProShop mapping | Add proshop_pot_id to machines.json | FocasMonitor ignores unknown fields, clean single source of truth |
| QR encoding | H-NNNN format (e.g., H-0047) | Short, distinct from ProShop tool numbers (A16, B9) |
| Kiosk hardware | Dedicated PC near tool storage | Same Flask+Chrome+scanner pattern as COTS kiosk |
| Presetter integration | Optional future phase — system works without it | Slots into assemblies table when ready |


---


## Data Model

All tables in C:\FASData\tooling.db (WAL mode, busy_timeout=5000):

### holders — Physical holders with QR codes
- holder_id TEXT PK — "H-0047" (engraved/labeled)
- holder_type TEXT — "CAT40 ER32", "CAT40 Shrink Fit"
- collet_size TEXT — "1/2", "3/8"
- default_tool TEXT — ProShop tool # usually held (nullable)
- notes, status (active/retired), created_at, retired_at

### assemblies — Each cutter installation into a holder
- assembly_id INTEGER PK AUTO
- holder_id FK -> holders
- proshop_tool_number TEXT — "A16", "I460", "B9"
- tool_description TEXT
- ooh_inches REAL — stick-out
- measured_length REAL — from presetter (nullable, future)
- measured_diameter REAL — from presetter (nullable, future)
- measured_at TEXT — when last measured (nullable, future)
- installed_at, retired_at, retire_reason (worn/broken/reground)
- installed_by, retired_by — employee name

### assignments — Where the assembly is right now
- assignment_id INTEGER PK AUTO
- holder_id FK -> holders
- machine_id TEXT — "M2", "M6"
- pocket_number INTEGER — T-slot in the machine
- work_order TEXT (nullable, may span multiple WOs)
- assigned_at, removed_at, assigned_by, removed_by

### tool_usage_segments — FASData-derived cutting stats
- segment_id INTEGER PK AUTO
- holder_id, assembly_id FKs
- machine_id, work_order
- cutting_minutes REAL, sample_count INTEGER
- avg_spindle_load REAL, peak_spindle_load INTEGER
- length_wear_start/end, radius_wear_start/end INTEGER (microns)
- segment_start, segment_end, last_processed_at

### activity_log — Audit trail
- log_id INTEGER PK AUTO
- timestamp, action, holder_id, machine_id, pocket_number, employee, details (JSON)


---


## Three Core Workflows

### Workflow 1: New Job Setup

1. Setup guy selects machine on kiosk
2. Kiosk queries ProShop: scheduled/queued WOs for that machine
3. Pulls sequence detail -> full tool list with ProShop tool #, OOH
4. Diffs against current pocket assignments (local DB + ProShop pockets)
5. Shows: KEEP (common tools already loaded), LOAD (new tools needed), REMOVE (not needed)
6. Setup guy scans each holder QR to load, confirms pocket #
7. Kiosk writes assignments locally + syncs to ProShop updateWorkCellPocket

### Workflow 2: Cutter Replacement

1. Setup guy scans holder QR -> sees current assembly, usage stats, wear
2. Taps "Replace Cutter", selects reason (worn/broken/reground)
3. Old assembly closed (retired_at + reason), new assembly created on same holder
4. ProShop pocket wear fields zeroed via updateWorkCellPocket

### Workflow 3: Common Tool Movement

1. Scan holder -> system shows it's in M2 pocket T4
2. Tap "Move to different machine" -> select M6, enter pocket #
3. Assignment closed on M2, new assignment on M6
4. Usage segment closed on M2, new segment opened on M6
5. ProShop pockets updated on both machines
6. Full cutting history follows the holder across machines


---


## Phased Build

### Phase 0: Infrastructure + API Validation

- Copy COTS kiosk scaffolding into new project (22. Tool Assembly Management\tool-kiosk\)
- Create new ProShop OAuth client with scope: toolpots:rwdp+parts:r+workorders:r+users:r+tools:r
- API exploration script: test workCell query with pockets, test updateWorkCellPocket mutation
- Add proshop_pot_id to machines.json (M2->"Mill-2", M6->"Mill-6", etc.)
- Generate paper QR labels for H-0001 through H-0010
- ProShop tool & purchasing data discovery:
  - Query vendorPOs (1,510 records, no scope needed) — examine line item fields for tool references, quantities, dates; cross-reference to find most frequently ordered tools
  - Query tools with tools:r scope — test whether this returns ProShop's full tool library (tool numbers, descriptions, specs, vendors)
  - Document what fields are available on both entities for use in the kiosk (tool lookup, smart suggestions, reorder alerts)

### Phase 1: Holder Registry + Scan Lookup

- SQLite database module for tooling.db with all tables
- Flask routes: register holder, install cutter, retire cutter, lookup by scan
- Kiosk UI: employee selection, scan/search, holder detail, register, install cutter, replace cutter
- Scanner detection reused from COTS kiosk base.html pattern
- Activity log for all mutations

### Phase 2: Machine Assignment + ProShop Pocket Sync

- ProShop client methods: get_work_cell_pockets(), update_work_cell_pocket()
- Flask routes: assign holder to machine+pocket, remove, view machine pockets, sync to ProShop
- On assign: push tool#, OOH to ProShop pocket
- On cutter replace: zero wear fields
- On remove: clear ProShop pocket

### Phase 3: Job Setup Diff (highest value workflow)

- ProShop client: get_work_order_ops(), get_part_op_tools(), get_scheduled_work()
- Diff engine: current pockets vs. required tools -> keep/load/remove lists
- Kiosk UI: machine select -> upcoming job -> setup diff -> step-through load workflow
- Bulk pocket update to ProShop on apply

### Phase 4: FASData Usage Rollup

- tool_usage_rollup.py — reads monitoring.db, writes to tooling.db
- Joins: assignments.machine_id + pocket_number <-> machine_samples.machine_id + tool_number
- Computes cutting minutes, avg/peak spindle load, wear deltas
- Runs every 5 min via Windows Task Scheduler
- Holder detail page shows real cutting time and wear data

### Phase 5: Cross-Machine Movement

- Scan holder -> detect current assignment -> move to new machine+pocket
- Auto-close/open assignments and usage segments
- ProShop sync on both source and destination machines

### Phase 6: Reporting + Dashboard

- Usage reports by tool type, machine, holder
- Machine pocket status display (shop floor TV)
- Tool life predictions from wear rate trends
- CSV/Excel export

### Future: Presetter Integration

- Add measured_length, measured_diameter, measured_at to assemblies
- Presetter exports CSV/file -> kiosk watches folder, matches by scanned QR
- Measured offsets stored in assembly, pushed to ProShop pocket on assign
- Enables "measure once, use anywhere" — offsets travel with the holder across machines
- Eliminates re-touch-off when tools move between machines


---


## ProShop API Integration

### Read Work Cell Pockets
- Query: workCell(potId) with pockets sub-table
- Fields: legacyId, toolPlainText, glotPlainText (RTA#), holder, outOfHolder, offset, radiusOffset, toolWear, radiusWear, toolLifeNow, toolLifeWarning
- Scope required: toolpots:r

### Write Work Cell Pockets
- Mutation: updateWorkCellPocket(potId, pockets)
- Can set: tool, holder, outOfHolder, offset, radiusOffset, toolWear, radiusWear, toolLifeNow, toolLifeWarning
- Scope required: toolpots:rwdp
- NOTE: Exact input format needs empirical testing in Phase 0

### Read Sequence Detail (Tool Lists per Job)
- Query: part operations -> tools sub-table
- Returns: ProShop tool #, OOH/stickout, pocket/T-number
- Scope required: parts:r

### Read Scheduled/Queued Work
- Query: workOrders filtered by workCenterPlainText matching machine name
- Returns: WO number, part, operations, scheduled dates
- Scope required: workorders:r


---


## Machine ID to ProShop Mapping

Current machines.json needs a new field added:

    M2  -> Mill-2   (CAT40, FANUC, Active)
    M3  -> Mill-3   (CAT40, FANUC, Configured)
    M6  -> Mill-6   (CAT40, FANUC, Active)
    M8  -> Mill-8   (CAT40, FANUC, Active)
    T2  -> (lathe, separate tooling pool)

Future:
    Haas      -> TBD  (CAT40, not on FOCAS, needs MTConnect or similar)
    Robodrills -> TBD  (BT30, separate holder pool)


---


## Key Risks and Mitigations

### updateWorkCellPocket input format undocumented
The mutation exists in the ProShop API but the exact input field names aren't in the introspection dump. Mitigation: Phase 0 includes empirical testing. Can also inspect browser network requests when editing pockets manually in ProShop UI to reverse-engineer the format.

### tool_number may be empty in FASData
cnc_rdtool() currently returns EW_NOOPT on all machines, meaning machine_samples.tool_number may not be populated. Mitigation: Use tool_wear_samples.offset_number or parse T-codes from active_block_content as fallback. Investigate cnc_rdtool2() or macro variable reads.

### ProShop scheduling data access unclear
May not be able to query "what's queued on this machine" directly. Mitigation: Query active work orders and filter by workCenterPlainText matching the machine name.

### Paper QR labels degrading in shop environment
Coolant, oil, and handling will destroy paper labels. Mitigation: Paper is prototyping only — production deployment requires laser-engraved QR on holder shank/flange. Manual holder ID entry works as fallback.

### Concurrent database access
The rollup script and kiosk app both write to tooling.db. Mitigation: SQLite WAL mode + busy_timeout=5000ms handles this for the expected write frequency (both write infrequently and briefly).


---


## Files to Reuse from Existing Projects

From COTS Kiosk (Project 17):
- app.py — Flask app structure, routes, error handling (copy + adapt)
- proshop_client.py — OAuth client, token refresh, GraphQL execution (copy + extend)
- templates/kiosk.html — Multi-screen touch UI, scanner detection (copy + rebrand)
- static/style.css — Touch-friendly CSS (copy + retheme)
- kiosk_launcher.py — Watchdog launcher (copy as-is)

From FASData (Project 12):
- focasmonitor/machines.json — Machine config (edit to add proshop_pot_id)
- focasmonitor/Database.cs — Schema reference for machine_samples and tool_wear_samples

From Conversational ProShop (Project 10):
- proshop_schema_full.json — GraphQL schema reference for field discovery


---


## Verification Checkpoints

- Phase 0: Successfully query Mill-2 pockets and write a test value to toolWear field via API
- Phase 1: Register 5 holders with paper QR, install cutters, scan and verify lookup
- Phase 2: Assign holder to M2 pocket 6, verify ProShop Work Cell page shows correct tool + OOH
- Phase 3: Pull sequence detail for a real WO, diff against current M2 pockets, apply setup
- Phase 4: Run rollup script, verify holder detail shows cutting minutes matching FASData
- Phase 5: Move holder from M2 to M6, verify both ProShop pages update and usage history is continuous
