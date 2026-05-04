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

- `photo-uploader/app.py` — Flask app + routes (including /api/qr-decode, /api/suggest, /api/print-label, /api/queue-order, /api/approve, /api/reject, /approvals)
- `photo-uploader/config.py` — Ports, paths, ProShop URLs
- `photo-uploader/database.py` — SQLite schema + CRUD
- `photo-uploader/proshop_client.py` — OAuth GraphQL client; `get_label_data()` fetches per-type label fields
- `photo-uploader/label_generator.py` — Pillow renderers (material, box, equipment, tool, COTS) — port of P30 Canvas generators
- `photo-uploader/upload_worker.py` — Selenium upload worker (headless Chrome → CKEditor image upload)
- `photo-uploader/inspect_upload.py` — Visible-mode CKEditor discovery script (run once to inspect dialog DOM)
- `photo-uploader/purchasing/` — P35 purchasing automation (folded into this project per PLAN.md)
- `photo-uploader/purchasing/queue.py` — SQLite orders.db CRUD
- `photo-uploader/purchasing/rules.py` — auto-approve evaluator (amount-only; interval check planned for Phase 2)
- `photo-uploader/purchasing/rules.json` — per-item / per-category rules (defaults to manual review)
- `photo-uploader/purchasing/vendors.py` — vendor_map.json lookup + first-name extraction
- `photo-uploader/purchasing/email_draft.py` — Microsoft Graph helper to draft messages in tom@'s "Purchasing - To Review" folder
- `photo-uploader/static/photo.js` — Frontend logic (search, QR decode, capture, upload, suggestions, print-label)
- `photo-uploader/static/approvals.js` — Approve/Reject/Approve-All handlers for the /approvals page
- `photo-uploader/static/style.css` — Kiosk-style dark theme CSS, 3-column grid
- `photo-uploader/static/manifest.json` — PWA manifest
- `photo-uploader/templates/` — Jinja2 templates (home, queue, approvals)
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

## Next Steps

- **P35 Phase 2** — Selenium VPO creation. Write `purchasing/inspect_vpo_form.py` first (visible-mode driver of ProShop's "New VPO" form) to discover selectors before building the worker. Mirrors how `inspect_upload.py` enabled the photo-upload Selenium work.
- **Fix `email_draft._ensure_folder()`** — only searches root-level mail folders. If the "Purchasing - To Review" folder gets nested under another folder, Flask creates a duplicate at root on next restart. Either walk childFolders recursively or persist the folder ID across restarts.
- **COTS Cost-scrape brittleness** — heuristic in P30's `buy-content.js` worked for LUB-116 but missed for THI-17. Inspect the THI-17 page DOM and tighten the column-finder so the auto-quote path stops being the default for items that DO have a price on screen.
- **Email name-extraction polish** — `purchasing/vendors.first_name_of()` only confidently extracts a first name when the local part has a dot (e.g. jaime.gomez). For `briannab@`-style addresses it falls back to "Hello,". Consider adding an optional `first_name` field to `vendor_map.json` entries.

## Interfaces

Produces: Flask UI (port 5003), photos.db (SQLite at photo-uploader/data/photos.db), purchasing.db (SQLite for P35 order queue at photo-uploader/data/purchasing.db), JPEG photos (photo-uploader/data/photos/{type}/{id}/), /api/health endpoint, /api/print-label endpoint (renders + sends PNG to Brother PT-P700), /api/queue-order + /api/approve/<id> + /api/reject/<id> + /approvals page (P35 purchasing approval queue), Outlook drafts in tom@traxismfg.com's "Purchasing - To Review" folder via Microsoft Graph, suggestions.md (operator feedback)
Consumes: ProShop GraphQL API (workorders, tools, equipment, parts, fixtures, cotsItems, nonConformanceReports), ProShop web UI via headless Selenium, Brother PT-P700 print service at http://10.1.1.242:5002/api/print-image (shared with P9/P22/P30), Microsoft Graph API (Mail.ReadWrite app permission) for purchasing email drafts, vendor_map.json from `35. Purchasing Automation/` for P35 vendor lookup, .traxis.env (PROSHOP_CLIENT_ID, PROSHOP_CLIENT_SECRET, PROSHOP_SCOPE, PROSHOP_USERNAME, PROSHOP_PASSWORD, GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET)
Contracts: Port 5003 must not conflict with other services. Photo storage at photo-uploader/data/photos/ syncs via Dropbox. Upload worker consumes ProShop web UI via headless Selenium. Written description URL pattern: `{BASE}/procnc/parts/{customer}/{partNumber}$formName=writtenDescription&opId={opNumber}`. OAuth scope requires: parts:rwdp, workorders:rwdp, users:r, tools:rwdp, toolpots:r, fixtures:r, ots:r, equipment:r, nonconformancereports:r. Print label endpoint POSTs `{image_base64, copies, label_name}` to print service (same payload as P30). Label designs match P30 exactly: material/equipment/tool/box auto-width 128px tall, COTS fixed 450×128px, all at 180 DPI for 24mm tape. P30 extension's "Buy" button POSTs `{entity_type, entity_id, qty, unit_cost?, vendor?, brand?}` to /api/queue-order; backend either auto-approves under-threshold orders or drafts a vendor quote-request email (capped 3/day per vendor) when unit_cost is missing. Outlook draft folder lookup is root-level only — folder must stay at the mailbox root.
