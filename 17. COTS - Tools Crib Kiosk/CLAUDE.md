# Project 17 — COTS Crib Kiosk

Touch-screen kiosk for tool crib COTS inventory checkout via QR scanning. Also includes a CLI label generator for printing COTS QR labels on Brother PT-P700.

## Key Files

| File | Purpose |
|------|---------|
| `cots-kiosk/app.py` | Flask web server — kiosk UI, browse, edit, API endpoints |
| `cots-kiosk/proshop_client.py` | ProShop GraphQL client (COTS CRUD, inventory checkout/checkin) |
| `cots-kiosk/config.py` | Configuration (ProShop API URLs, Flask port) |
| `cots-kiosk/transaction_log.py` | Local CSV transaction logging |
| `cots-kiosk/kiosk_launcher.py` | Watchdog — starts Flask + Chrome kiosk, auto-restarts |
| `generate_cots_labels.py` | CLI label generator — PNG labels from CSV or ProShop API |
| `COTS_Labels_All.csv` | Master label data (197 items) |
| `COTS P-Touch Label Layout.lbx` | Legacy P-touch Editor template (superseded by generate_cots_labels.py) |

## Interfaces

Produces: COTS label PNGs (450px wide, 128px tall, 180 DPI), transaction log CSV, Flask kiosk UI (port 5000)
Consumes: ProShop GraphQL API (OAuth client credentials, scope `ots:rwdp+cots:rwdp+parts:r+users:r`), Brother PT-P700 print service at http://10.1.1.242:5002/api/print-image, COTS_Labels_All.csv
Contracts: Print payload `{image_base64, copies, label_name}` to P22 print service `/api/print-image` (same as P9/P30). Labels are 128px tall, 450px wide (2.5"), 180 DPI. QR codes encode full ProShop URL (`https://traxismfg.adionsystems.com/procnc/ots/{TYPE}/{COTS_ID}`).
