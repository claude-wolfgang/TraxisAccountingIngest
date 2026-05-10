# Project 22: Tool Assembly Management

Touch-screen kiosk for tool assembly management with ProShop inventory sync and label printing. Runs on kiosk PC (10.1.1.142) with print service on MainPC (10.1.1.71).

## Key Files

- `tool-kiosk/app.py` — Flask web server (port 5001, kiosk UI, ProShop integration)
- `tool-kiosk/config.py` — Configuration (machines, URLs, timeouts)
- `tool-kiosk/database.py` — SQLite data layer (tooling.db at tool-kiosk/data/tooling.db)
- `tool-kiosk/proshop_client.py` — ProShop GraphQL client (tools, RTAs, work cells, pockets)
- `tool-kiosk/print_service.py` — Label printing server (port 5002, Brother PT-D610BT via b-PAC SDK)
- `tool-kiosk/inventory_sync.py` — Pushes cabinet counts to ProShop (off-hours only)
- `tool-kiosk/tool_usage_rollup.py` — Aggregates tool usage from FOCAS data
- `tool-kiosk/kiosk_launcher.py` — Launcher + watchdog (Flask + Chrome kiosk mode)

## Interfaces

Produces: tooling.db (SQLite at tool-kiosk/data/tooling.db), Flask kiosk UI (port 5001), /api/print-label proxy to print service, /api/print-inventory-label proxy, /api/print-image (generic PNG label printing for any project), /api/restart (remote process restart), /api/health endpoint, heartbeat.json (Overseer health check)
Consumes: ProShop GraphQL API (tools, RTAs, work cells, pockets, users, work orders), .traxis.env (TOOLKIOSK_CLIENT_ID, TOOLKIOSK_CLIENT_SECRET, TOOLKIOSK_SCOPE), Overseer (managed service), FocasMonitor monitoring.db (read-only, for tool_usage_rollup.py), Brother PT-P700 printer (USB on 10.1.1.242)
Contracts: P19 reads tooling.db read-only at ../22. Tool Assembly Management/tool-kiosk/data/tooling.db — path must not change without updating P19 config.py:35. Schema contract: tool_inventory table must have columns tool_number, tool_description, qty_blue, qty_green, min_quantity, last_counted_at. P22 print_service runs on port 5002 on 10.1.1.242 — P9 and kiosk app consume it. /api/print-image accepts {image_base64, copies, label_name}.
