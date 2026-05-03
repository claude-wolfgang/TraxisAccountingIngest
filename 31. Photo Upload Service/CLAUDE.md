# Project 31: Photo Upload Service

Simple photo capture from shop floor Samsung tablet, queued for upload to ProShop entity pages. Operators tap entity type, search, snap, done. Photos queue locally and upload to ProShop via Selenium browser automation (Phase 2).

## Architecture

- Flask app on MainPC, port 5003
- Tablet connects over LAN via Fully Kiosk Browser (Android kiosk lockdown)
- Camera access via `<input type="file" capture="environment">` (works over HTTP)
- Photos resized to max 2000px, JPEG 85% quality
- SQLite tracks photo metadata and upload queue
- Background worker (Phase 2) uploads to ProShop via headless Selenium
- Three-layer QR decode: BarcodeDetector → jsQR → pyzbar server-side
- Label printing via Pillow + Brother PT-P700 print service (P30 designs ported server-side)

## Key Files

- `photo-uploader/app.py` — Flask app + routes (including /api/qr-decode, /api/suggest, /api/print-label)
- `photo-uploader/config.py` — Ports, paths, ProShop URLs
- `photo-uploader/database.py` — SQLite schema + CRUD
- `photo-uploader/proshop_client.py` — OAuth GraphQL client; `get_label_data()` fetches per-type label fields
- `photo-uploader/label_generator.py` — Pillow renderers (material, box, equipment, tool, COTS) — port of P30 Canvas generators
- `photo-uploader/upload_worker.py` — Selenium upload worker (headless Chrome → CKEditor image upload)
- `photo-uploader/inspect_upload.py` — Visible-mode CKEditor discovery script (run once to inspect dialog DOM)
- `photo-uploader/static/photo.js` — Frontend logic (search, QR decode, capture, upload, suggestions, print-label)
- `photo-uploader/static/style.css` — Kiosk-style dark theme CSS, 3-column grid
- `photo-uploader/static/manifest.json` — PWA manifest
- `photo-uploader/templates/` — Jinja2 templates (home, queue)
- `suggestions.md` — Operator feedback file (appended by /api/suggest)

## Entity Types

- **workorder** — Search by WO number (flexible: "26120" matches "26-0120"), select operation, upload to written description
- **part** — Search by part number/name, select operation, upload to written description (same URL pattern as WO)
- **tool** — Search by tool number/description, upload to tool page
- **equipment** — Search by number/description/location/type (flexible digit matching), upload to equipment page
- **fixture** — Search by fixture number/description
- **cots** — Search by number/description (digit-only matching, prefix-flexible)
- **ncr** — Search by NCR ref number/WO number/notes, upload to NCR page
- **claude** — Local-only photos saved to data/photos/claude/ (Dropbox-synced, no ProShop upload)
- **QR scan** — Scan ProShop QR label to auto-detect entity type and ID

## Phase Status

- **Phase 1** (done): Tablet → Flask → local storage + entity search. Queue page.
- **Phase 2** (done): Selenium upload worker. Base64 inline image via CKEditor insertHtml. Tested on WO, equipment, parts.
- **Phase 3** (done): Overseer integration, jsQR CDN, parseProShopUrl() for all entity URL patterns.
- **Phase 4** (done): Full entity expansion (fixtures, COTS, equipment, NCR, parts with ops), Claude local-only category, suggestion button, Fully Kiosk Browser tablet setup, three-layer QR decode.

## ProShop Written Description Upload — Technical Notes
- CKEditor dialog: name="image", tabs=[Image Info, Link, Upload, Advanced]
- Upload tab has file input inside an iframe, but no server-side upload handler (filebrowserImageUploadUrl=None)
- Working approach: insertHtml with base64 data URI, then save via fetch() interceptor
- Written description URL: `{BASE}/procnc/parts/{customer}/{partNumber}$formName=writtenDescription&opId={opNumber}`
- Customer prefix extracted from `part.proshopUrl` (e.g., `/parts/R2S1/R2S1-10020` → `R2S1`)
- Non-WO entities (equipment, tools, etc.) navigate directly to their proshop_url

## Interfaces

Produces: Flask UI (port 5003), photos.db (SQLite at photo-uploader/data/photos.db), JPEG photos (photo-uploader/data/photos/{type}/{id}/), /api/health endpoint, /api/print-label endpoint (renders + sends PNG to Brother PT-P700), suggestions.md (operator feedback)
Consumes: ProShop GraphQL API (workorders, tools, equipment, parts, fixtures, cotsItems, nonConformanceReports), ProShop web UI via headless Selenium, Brother PT-P700 print service at http://10.1.1.242:5002/api/print-image (shared with P9/P22/P30), .traxis.env (PROSHOP_CLIENT_ID, PROSHOP_CLIENT_SECRET, PROSHOP_SCOPE, PROSHOP_USERNAME, PROSHOP_PASSWORD)
Contracts: Port 5003 must not conflict with other services. Photo storage at photo-uploader/data/photos/ syncs via Dropbox. Upload worker consumes ProShop web UI via headless Selenium. Written description URL pattern: `{BASE}/procnc/parts/{customer}/{partNumber}$formName=writtenDescription&opId={opNumber}`. OAuth scope requires: parts:rwdp, workorders:rwdp, users:r, tools:rwdp, toolpots:r, fixtures:r, ots:r, equipment:r, nonconformancereports:r. Print label endpoint POSTs `{image_base64, copies, label_name}` to print service (same payload as P30). Label designs match P30 exactly: material/equipment/tool/box auto-width 128px tall, COTS fixed 450×128px, all at 180 DPI for 24mm tape.
