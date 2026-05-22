# Project 22: Tool Assembly Management

Touch-screen kiosk for tool assembly management with ProShop inventory sync and label printing. Flask backend runs Overseer-managed on srv-01 (10.1.1.161, migrated from .71 on 2026-05-22). Chrome `--kiosk` touchscreen client runs on the kiosk PC (10.1.1.141) and points at the backend via `TOOLKIOSK_BACKEND_URL` (default `http://10.1.1.71:5001` in code; .141's `~/.traxis.env` overrides to `http://10.1.1.161:5001`). Print service runs on 10.1.1.242.

## Key Files

- `tool-kiosk/app.py` — Flask web server (port 5001, kiosk UI, ProShop integration)
- `tool-kiosk/config.py` — Configuration (machines, URLs, timeouts)
- `tool-kiosk/database.py` — SQLite data layer (tooling.db at tool-kiosk/data/tooling.db)
- `tool-kiosk/proshop_client.py` — ProShop GraphQL client (tools, RTAs, work cells, pockets)
- `tool-kiosk/print_service.py` — Label printing server (port 5002, Brother PT-D610BT via b-PAC SDK)
- `tool-kiosk/inventory_sync.py` — Pushes cabinet counts to ProShop (off-hours only)
- `tool-kiosk/tool_usage_rollup.py` — Aggregates tool usage from FOCAS data
- `tool-kiosk/kiosk_launcher.py` — Touchscreen launcher (runs on 10.1.1.141): detects touchscreen monitor via Win32 Pointer Device API, launches Chrome `--kiosk` pinned to that monitor, watchdogs Chrome, beats `/api/kiosk-heartbeat` every 60s. Reads `TOOLKIOSK_BACKEND_URL` from `.traxis.env` (default `http://10.1.1.71:5001`). When the URL is remote, no local Flask is started.
- `tool-kiosk/run_kiosk_silent.bat` — pythonw wrapper used by the autostart scheduled task.
- `tool-kiosk/install_autostart.bat` — one-shot installer: registers Task Scheduler entry `TraxisToolKiosk` to run the silent wrapper at every logon. Idempotent.

## Interfaces

Produces: tooling.db (SQLite at tool-kiosk/data/tooling.db), Flask kiosk UI under waitress (port 5001) with /api/health + POST /api/shutdown + POST /api/kiosk-heartbeat (touchscreen liveness beacon), /api/print-label proxy to print service, /api/print-inventory-label proxy, /api/print-image (generic PNG label printing for any project), /api/restart (remote process restart). Also produces the standalone print_service.py at port 5002 (runs on whichever PC has the Brother PT-P700 USB-attached, currently 10.1.1.242) — under waitress with /api/health + POST /api/shutdown.
Consumes: ProShop GraphQL API (tools, RTAs, work cells, pockets, users, work orders), .traxis.env (TOOLKIOSK_CLIENT_ID, TOOLKIOSK_CLIENT_SECRET, TOOLKIOSK_SCOPE, TOOLKIOSK_BACKEND_URL), Overseer (managed service), FocasMonitor monitoring.db (read-only, for tool_usage_rollup.py), Brother PT-P700 printer (USB on 10.1.1.242)
Contracts: P19 reads tooling.db read-only at ../22. Tool Assembly Management/tool-kiosk/data/tooling.db — path must not change without updating P19 config.py:35. Schema contract: tool_inventory table must have columns tool_number, tool_description, qty_blue, qty_green, min_quantity, last_counted_at. P22 print_service runs on port 5002 on 10.1.1.242 — P9 and kiosk app consume it. /api/print-image accepts {image_base64, copies, label_name}. Overseer's `validate_tool_assembly_kiosk` reads `kiosk_heartbeat_age_seconds` from /api/health and flips degraded when that value is present (a heartbeat has been seen) and exceeds 300s — so the heartbeat endpoint must stay accepting POSTs without auth. Flask persists the last heartbeat to `data/kiosk_heartbeat.txt` so the signal survives Flask restarts.
