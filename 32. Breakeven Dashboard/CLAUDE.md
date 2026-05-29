# P32: Breakeven Dashboard

Visual dashboard showing weekly CNC machine runtime vs breakeven target hours. Displays per-machine progress bars, daily cumulative charts, weekly trend sparklines with history navigation, and pace-based alerts.

## Key Files
- `breakeven.html` — Single-file dashboard (CSS + JS, no build step), loads from `file://`
- `focas_runtime_aggregator.py` — Queries FASData monitoring.db, outputs `runtime_snapshot.json` + `.js`
- `runtime_snapshot.json` / `.js` — Aggregated data (current week + N history weeks with daily breakdowns)
- `config.json` — DB path, timezone, machines file path

## Interfaces
Produces: `runtime_snapshot.json` + `.js` (weekly machine runtime + daily breakdown + history; `.js` sets `window.RUNTIME_DATA`). **As of 2026-05-28 these are generated server-side on srv-01 by the P1 FASDataDashboard service** (in-process aggregator loop, every ~2.5 min) into `C:\FASData\breakeven\`, and **served over HTTP** at `http://10.1.1.161:8070/breakeven` (+ `/runtime_snapshot.js|json`). The old model (a `.71` scheduled task writing the snapshot into the Dropbox project folder + opening `breakeven.html` via `file://`/SMB, per `DEPLOYMENT.md`) is **superseded** — `run_aggregator.bat`/`DEPLOYMENT.md` describe the retired `.71` setup.
Consumes: FASData `monitoring.db` (live, on srv-01; path via `TRAXIS_FOCAS_DB`, default `C:\FASData\monitoring.db`, read-only — `machine_samples` table). Machine list is now discovered from the DB (no `machines.json` dependency).
Contracts: `build_snapshot()`/`write_snapshot()` in `focas_runtime_aggregator.py` are imported and called in-process by P1 `fasdata_live.py`; keep their signatures stable. `breakeven.html` loads `runtime_snapshot.js` by **relative** path, so it must be served from the same origin (served at `/runtime_snapshot.js`). Aggregator expects `machine_samples(machine_id, timestamp, run_status)`, `STRT` = running, 60s sample interval, 120s gap threshold.

## Next Steps
- **[NEEDS WOLFGANG] Repoint the Breakeven display/bookmark to `http://10.1.1.161:8070/breakeven`** — whatever shop/desktop view shows the glass dashboard was reading `.71`'s frozen snapshot (the "wrong URL"). The new HTTP endpoint serves live current-week data off srv-01.
- **Update/retire `DEPLOYMENT.md` and `run_aggregator.bat`** — both describe the retired `.71` model (D:\Dropbox paths, `C:\Users\TRAXIS` Python, 15-min scheduled task, file://+SMB). The live model is now in-process on srv-01's FASDataDashboard. Rewrite DEPLOYMENT.md to the HTTP/in-process model or delete the stale launcher.
