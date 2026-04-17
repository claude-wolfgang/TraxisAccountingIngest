# P32: Breakeven Dashboard

Visual dashboard showing weekly CNC machine runtime vs breakeven target hours. Displays per-machine progress bars, daily cumulative charts, weekly trend sparklines with history navigation, and pace-based alerts.

## Key Files
- `breakeven.html` — Single-file dashboard (CSS + JS, no build step), loads from `file://`
- `focas_runtime_aggregator.py` — Queries FASData monitoring.db, outputs `runtime_snapshot.json` + `.js`
- `runtime_snapshot.json` / `.js` — Aggregated data (current week + N history weeks with daily breakdowns)
- `config.json` — DB path, timezone, machines file path

## Interfaces
Produces: runtime_snapshot.json (weekly machine runtime + daily breakdown + history), runtime_snapshot.js (same data as window.RUNTIME_DATA for file:// use)
Consumes: FASData monitoring.db (C:\FASData\monitoring.db, read-only — machine_samples table), machines.json (machine list from FASData or config)
Contracts: aggregator expects machine_samples table with columns (machine_id, timestamp, run_status), STRT = running state, 60s sample interval, gap threshold 120s
