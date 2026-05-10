# CC_BREAKEVEN_DASHBOARD.md

Claude Code task: integrate the weekly break-even runtime progress dashboard
into the existing FOCAS monitor stack.

---

## Objective

Replace the manual-entry break-even dashboard with a live version that reads
runtime data from the FOCAS monitor database. The dashboard should show
progress toward the weekly break-even target (143 hrs across 9 machines,
~15.9 hrs per machine) without anyone having to hand-enter hours.

The dashboard is a single-page HTML file. The data pipe is a Python script
that queries the FOCAS database, aggregates weekly runtime per machine, and
writes a JSON snapshot the dashboard reads. Keep the dashboard static — no
server, no Flask, no firewall work.

---

## Context — what already exists

- **FOCAS Monitor** — C# Windows service (`FocasMonitor.exe`) logging Fanuc
  0i-MF data every few seconds. Runs as `FocasMonitor` service on the
  accounting/automation server.
- **Machines** — 9 revenue-generating: 8 mills + 1 lathe (YCM NTC1600LY).
  Machine IDs/names defined in `machines.json` alongside the exe.
- **Break-even math** (from the existing dashboard, confirmed with Wolfgang):
  - Weekly nut: $13,550 (labor fully burdened $7,500 + overhead ~$6,050)
  - Billable rate: $95/hr
  - Revenue machines: 9
  - Operating window: 50 hrs/week (staggered schedule)
  - Target: 143 total hrs/week → 15.9 hrs/machine → 32% utilization
- **Existing dashboard artifact** — manual entry per machine, browser
  localStorage for persistence, progress bars with red/amber/green/teal
  thresholds, assumptions panel for rate/nut/op-hours/machine-count.
- **Project folder** — stage all new files under
  `MACHINE COMM Traxis\Proshop Automation and Claude Projects\` in a new
  numbered folder: `20. Breakeven Dashboard\` (confirm next available number
  before creating).

---

## Task 1 — Database discovery

Before writing any integration code, document what the FOCAS DB actually
contains. Do not assume the schema.

1. Locate the FOCAS monitor config (likely `appsettings.json` or similar
   next to `FocasMonitor.exe`) and read the connection string. Report:
   - DB engine (SQLite file? MSSQL? Something else?)
   - File path or server/instance
   - Database name
2. Connect and enumerate:
   - All tables and their row counts
   - Column names + types for any table that looks like runtime/status logs
   - Date range of data present (earliest and latest timestamp)
   - Sample 5 rows from the primary runtime log table
3. Specifically look for these signals (FOCAS2 standard fields):
   - Program execution state: `EXEC`, `STRT`, `STOP`, `HOLD`, `RSTR` (from
     `cnc_exec` / `cnc_statinfo`)
   - Spindle RPM
   - Spindle load %
   - Active program number / name (`O` number or program path)
   - Alarm state
   - Timestamp column
4. Identify how machines are keyed (machine ID string? IP address? foreign
   key to a machines table?).

Write findings to `20. Breakeven Dashboard\FOCAS_SCHEMA_NOTES.md`. If
anything is ambiguous, flag it — do not paper over gaps.

---

## Task 2 — Runtime aggregator script

Build `focas_runtime_aggregator.py`.

### Purpose

Query the FOCAS DB, compute per-machine runtime for the current week (and
optionally a rolling 4-week history), and write a JSON file the dashboard
reads.

### Runtime definition

Use **program execution state** as the runtime signal. A machine is
"running" when `exec_state` is `STRT` (start) — this is FOCAS2's "program
running" flag. `STOP`, `HOLD`, and `***` do not count. This is the right
metric for break-even because setup proveout and tool changes during a
running program ARE billable time that offsets the weekly nut.

If the execution state column is not present in the DB (flagged during
Task 1), fall back to this order:
1. Spindle RPM > 0 AND active program number != 0
2. Spindle RPM > 0 alone (note the false-positive risk from warmup in the
   output JSON)

Document the chosen signal in the JSON output under `runtime_signal` so
the dashboard can display it.

### Aggregation logic

- Week starts Monday 00:00 local time (America/Chicago), ends Sunday 23:59.
- Runtime = sum of sample intervals where the machine was in the running
  state. If samples are ~5s apart, count each running sample as 5 seconds;
  compute the median sample interval per machine so this survives polling
  changes.
- Handle gaps: if the gap between two consecutive samples exceeds 60
  seconds, do not count the gap (assume monitor was down or machine was
  off).
- Produce per-machine: `runtime_seconds`, `runtime_hours`, `last_sample_at`.

### CLI

```
python focas_runtime_aggregator.py --out runtime_snapshot.json
python focas_runtime_aggregator.py --week 2026-W16 --out ...
python focas_runtime_aggregator.py --history 4  # also emit last 4 weeks
```

### Output JSON shape

```json
{
  "generated_at": "2026-04-16T14:22:00-05:00",
  "week_start": "2026-04-13",
  "week_end": "2026-04-19",
  "runtime_signal": "exec_state=STRT",
  "machines": [
    {
      "id": "ycm_ntc1600",
      "name": "YCM NTC1600LY",
      "runtime_hours": 22.4,
      "last_sample_at": "2026-04-16T14:21:55-05:00",
      "status": "online"
    }
  ],
  "history": [
    { "week_start": "2026-03-23", "total_hours": 131.2 },
    { "week_start": "2026-03-30", "total_hours": 148.7 }
  ]
}
```

`status` values: `online` (sampled within last 10 min), `stale` (last
sample > 10 min but < 24 hr), `offline` (no samples in 24 hr).

### Config

Read from `config.json` in the same folder:

```json
{
  "db_connection": "<from Task 1>",
  "machines_file": "machines.json",
  "output_path": "D:\\Traxis\\dashboards\\runtime_snapshot.json",
  "timezone": "America/Chicago",
  "running_signal": "exec_state"
}
```

Do not hardcode connection strings. Use environment variables or the
config file. No secrets in the script.

### Error handling

- DB unreachable: write a snapshot with `status: "offline"` per machine and
  an `error` field at the top level. Dashboard must still render.
- Machine in `machines.json` but no rows in DB: emit with
  `runtime_hours: 0` and `status: "offline"`.
- Log to `focas_aggregator.log` in the same folder. Rotate at 5 MB.

---

## Task 3 — Dashboard refactor

Start from the existing manual-entry dashboard HTML (Wolfgang has the
artifact — if not in the folder, ask him to drop it in). Modify as
follows.

### Data source swap

Replace the manual number inputs with a fetch of `runtime_snapshot.json`
from the same directory as the HTML file. On load:

```js
const data = await fetch('runtime_snapshot.json?t=' + Date.now()).then(r => r.json());
```

The cache-buster is important — Chrome will cache aggressively otherwise.

### Keep these from the original

- All four summary metric cards (weekly nut, target hours/wk, per machine/wk,
  utilization target)
- Total shop progress bar at top
- Per-machine progress bar rows with color thresholds (red < 50%,
  amber 50-75%, green 75-100%, teal ≥ 100%)
- Collapsible "Adjust assumptions" panel (rate, nut, op hrs, machine count)
  — these are still manual. They recompute targets but do not affect
  runtime data.

### Remove from the original

- Per-machine number input boxes (replaced by live values)
- "Fill with target" button
- "Reset week" button
- browser localStorage persistence (no longer needed)

### Add

- **Last updated** timestamp, top-right of the header. Shows `generated_at`
  from the JSON. Warn in amber if older than 30 minutes.
- **Machine status dot** next to each machine name: green (online), amber
  (stale), gray (offline). Use `--color-background-success` / `-warning` /
  `-tertiary`.
- **Runtime signal badge** somewhere unobtrusive (footer), showing what
  counts as runtime for transparency — e.g. "Runtime: program execution
  (STRT)".
- **4-week trend sparkline** above the total progress bar. 4 bars showing
  prior weeks' total hours with the break-even line at 143 hrs marked.
  Keeps it honest — one good week doesn't mean the shop is healthy.
- **Auto-refresh** every 5 minutes via `setInterval`. No full page reload —
  just re-fetch the JSON and re-render.

### Do not change

- Color palette, typography, card structure, dark mode compatibility
- The break-even math formulas
- The assumption-panel behavior

---

## Task 4 — Scheduling

The aggregator runs via Windows Task Scheduler, not as a service.

- Task name: `Traxis - FOCAS Runtime Aggregator`
- Trigger: every 15 minutes
- Action: `python.exe D:\Traxis\scripts\focas_runtime_aggregator.py --out D:\Traxis\dashboards\runtime_snapshot.json --history 4`
- Run whether user is logged on or not
- Use the same service account as the FOCAS monitor if possible

Document the task creation command (`schtasks /create ...`) in
`DEPLOYMENT.md` so it can be recreated.

---

## Task 5 — Hosting the dashboard

The dashboard is a single HTML file + JSON snapshot. Simplest deployment:

1. Drop both files in `D:\Traxis\dashboards\` on the automation server.
2. Share that folder on the LAN (read-only) so shop floor machines can
   open it at `\\traxis-server\dashboards\breakeven.html`.
3. For mobile/remote viewing, punt — Wolfgang will decide later whether to
   expose via the existing Cloudflare tunnel or wait. Do not set up public
   access as part of this task.

Bookmark suggestion for the shop floor kiosk and Wolfgang's phone: the
UNC path works on Windows; a local web server is not needed.

---

## Files to create

```
20. Breakeven Dashboard\
  CC_BREAKEVEN_DASHBOARD.md        (this file, copied into folder)
  FOCAS_SCHEMA_NOTES.md            (Task 1 output)
  focas_runtime_aggregator.py      (Task 2)
  config.json                      (Task 2 — template with placeholders)
  breakeven.html                   (Task 3 — refactored dashboard)
  DEPLOYMENT.md                    (Task 4 + 5 notes)
  requirements.txt                 (python deps: pyodbc or sqlite3 stdlib, tzdata)
```

---

## Acceptance criteria

The integration is complete when:

1. `FOCAS_SCHEMA_NOTES.md` documents the actual DB structure, the chosen
   runtime signal, and any fallbacks.
2. Running the aggregator manually produces a valid `runtime_snapshot.json`
   within 10 seconds for the current week.
3. Opening `breakeven.html` in a browser shows live per-machine runtime
   pulled from the JSON, with correct progress bars and color coding.
4. The scheduled task runs every 15 minutes and the dashboard's "last
   updated" stamp advances accordingly.
5. If the FOCAS DB is unreachable, the dashboard still loads and clearly
   indicates offline status per machine — it does not hang or show broken
   UI.
6. A 4-week trend sparkline is visible and accurate against DB data.

---

## Known caveats to flag back to Wolfgang

- **NC naming convention prerequisite** — this dashboard does NOT require
  the standardized NC naming. It reports raw machine runtime regardless of
  what job was loaded. Job-level attribution (runtime per WO) is a
  separate downstream task that does need the naming convention.
- **Program execution state assumes Fanuc reports it correctly** — if the
  C# collector isn't capturing `cnc_exec` today, Task 1 will surface that
  and Task 2 will fall back to spindle RPM. Worth extending the collector
  before relying on this long-term.
- **Operator-driven false idles** — if a machine is mid-program but in
  HOLD for a long manual intervention, that time won't count as runtime.
  This is correct for break-even purposes (not billable time) but may
  surprise people used to "spindle on = running."

---

## Do not do

- Do not touch the C# FOCAS monitor source code. If a schema change is
  needed (e.g. collector isn't logging exec state), write the finding into
  `FOCAS_SCHEMA_NOTES.md` as a follow-up task. Leave the collector alone.
- Do not build a Flask/FastAPI server. Static HTML + JSON only.
- Do not introduce new dependencies beyond what's in `requirements.txt`.
  Stdlib + pyodbc (if MSSQL) is enough.
- Do not commit `config.json` with real credentials. Ship a
  `config.example.json` and document the real one going in outside of
  version control.
- Do not mention specific Traxis customer names anywhere in code,
  comments, or docs.

---

## Notes

- ASCII-only output in all files.
- Keep the dashboard under 400 lines of JS. If it's getting bigger, the
  abstraction is wrong.
- When in doubt, match the style of existing scripts in the Proshop
  Automation folder — snake_case filenames, config.json pattern, logging
  to a local .log file.
