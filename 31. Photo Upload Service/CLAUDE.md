# Project 31: Photo Upload Service

Simple photo capture from shop floor Samsung tablet, queued for upload to ProShop entity pages. Operators tap entity type, search, snap, done. Photos queue locally and upload to ProShop via Selenium browser automation (Phase 2).

## Architecture

- Flask app on MainPC (10.1.1.71), port 5003
- Tablet connects over LAN at `http://10.1.1.71:5003/`
- Camera access via `<input type="file" capture="environment">` (works over HTTP)
- Photos resized to max 2000px, JPEG 85% quality
- SQLite tracks photo metadata and upload queue
- Background worker (Phase 2) uploads to ProShop via headless Selenium

## Key Files

- `photo-uploader/app.py` — Flask app + routes
- `photo-uploader/config.py` — Ports, paths, ProShop URLs
- `photo-uploader/database.py` — SQLite schema + CRUD
- `photo-uploader/proshop_client.py` — OAuth GraphQL client for entity search
- `photo-uploader/upload_worker.py` — Selenium upload worker (headless Chrome → CKEditor image upload)
- `photo-uploader/inspect_upload.py` — Visible-mode CKEditor discovery script (run once to inspect dialog DOM)
- `photo-uploader/static/photo.js` — Frontend logic (search, capture, upload)
- `photo-uploader/static/style.css` — Kiosk-style dark theme CSS
- `photo-uploader/templates/` — Jinja2 templates (home, queue)

## Entity Types

workorder, tool, equipment, part, fixture, cots — each searchable via ProShop GraphQL API. Fixtures reuse the parts search (fixtures are ProShop parts).

## Phase Status

- **Phase 1** (done): Tablet → Flask → local storage + entity search. Queue page.
- **Phase 2** (done): Selenium upload worker. Logs into ProShop, navigates to WO written description, checks out page, inserts photo as base64 inline image via CKEditor insertHtml, saves via fetch(). DOM inspection (inspect_upload.py) confirmed ProShop has no filebrowserImageUploadUrl, so CKEditor's Upload tab is non-functional — base64 inline is the only viable approach. ProShop has ~256KB server-side limit on written description content; images are auto-resized (1200→600px) to fit remaining budget. Tested end-to-end on WO 26-0120 Op 60 (2026-04-27).
- **Phase 3** (done): Overseer integration (auto-start/restart via health check on :5003), jsQR CDN for QR code scanning, parseProShopUrl() fixed for proshop:// protocol, WO year segments, parts customer prefix, COTS /ots/ path.

## ProShop Written Description Upload — Technical Notes
- CKEditor dialog: name="image", tabs=[Image Info, Link, Upload, Advanced]
- Upload tab has file input inside an iframe, but no server-side upload handler (filebrowserImageUploadUrl=None)
- Working approach: insertHtml with base64 data URI, then save via fetch() interceptor
- ProShop API field: `partNumber` is NOT a workOrder field; use `part { partNumber proshopUrl }` instead
- Written description URL: `{BASE}/procnc/parts/{customer}/{partNumber}$formName=writtenDescription&opId={opNumber}`
- Customer prefix extracted from `part.proshopUrl` (e.g., `/parts/R2S1/R2S1-10020` → `R2S1`)

## Interfaces

Produces: Flask UI (port 5003), photos.db (SQLite at photo-uploader/data/photos.db), JPEG photos (photo-uploader/data/photos/{type}/{id}/), /api/health endpoint
Consumes: ProShop GraphQL API (workorders, tools, equipment, parts, cotsItems), .traxis.env (PROSHOP_CLIENT_ID, PROSHOP_CLIENT_SECRET, PROSHOP_SCOPE, PROSHOP_USERNAME, PROSHOP_PASSWORD)
Contracts: Port 5003 must not conflict with other services. Photo storage at photo-uploader/data/photos/ syncs via Dropbox. Upload worker consumes ProShop web UI via headless Selenium (requires PROSHOP_USERNAME/PROSHOP_PASSWORD from .traxis.env). Written description URL pattern: `{BASE}/procnc/parts/{customer}/{partNumber}$formName=writtenDescription&opId={opNumber}`.
