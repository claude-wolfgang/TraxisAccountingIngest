# Project 19: Shop Scheduler

Daily job readiness scheduler surfacing machine openings, job readiness status, and bottleneck diagnostics. Flask web app on port 5080, managed by Overseer.

## Key Files

- `app.py` — Flask routes and API endpoints
- `config.py` — All configuration (API creds, paths, intervals)
- `database.py` — SQLite schema and queries (`scheduler.db`)
- `sync.py` — ProShop sync engine (WOs, ops, machines, tools, pockets)
- `priority_engine.py` — Urgency scoring, bottleneck analysis, daily report generation
- `suggest.py` — Next-job suggestions per machine
- `proshop_client.py` — ProShop GraphQL client (OAuth 2.0)

## Interfaces

Produces: scheduler.db (SQLite, local), Flask web UI (port 5080), /api/priorities/report endpoint, /api/tool-demand endpoint, heartbeat.json (Overseer health check)
Consumes: ProShop GraphQL API (WOs, ops, machines, tools, toolpots, purchaseOrders), P22 tooling.db (read-only via config.KIOSK_DB_PATH), Overseer (managed service), .traxis.env (PROSHOP_CLIENT_SECRET)
Contracts: P19 reads P22's tooling.db read-only at ../22. Tool Assembly Management/tool-kiosk/data/tooling.db — path is set in config.py:35 as KIOSK_DB_PATH and must not change without updating config.py. P19 reads tool_inventory table columns: tool_number, tool_description, qty_blue, qty_green, min_quantity, last_counted_at.
