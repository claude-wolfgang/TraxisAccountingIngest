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
- `photo-uploader/inspect_user_page.py` — Visible-mode discovery script for ProShop User pages (probes sub-forms for CKEditor / file inputs). Verdict 2026-05-06 against user 026: User pages have no CKEditor anywhere — P31's base64-into-CKEditor path does not extend to user profiles.
- `photo-uploader/inspect_user_026.bat` — Double-clickable launcher for the user-page inspect (keeps console open for output)
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

- **[NEEDS WOLFGANG] Power `.242` back on** — Brother PT-P700 print service host. Found offline 2026-05-10 (no ICMP, not in `.71`'s ARP cache). Until it's back, *all* label printing across P9/P22/P30/P31 fails with "Print service unreachable". Single point of failure for four projects — worth considering a `/api/health` poll from Overseer once it's stable, so we know within a minute if it goes down again.
- **[NEEDS WOLFGANG] Verify material/box label print on tablet** once `.242` is up. Today's fix corrected two latent bugs (empty material string + empty customer_po on box labels) but printing was unreachable so end-to-end was untested. WO 26-0050 is a good test case (gives "Stainless Steel 304 Plate" + customer PO "ICO1-NPO-4784").
- **User-profile attach is a dead end with the current bridge** — discovery against user 026 (Josh Farnell) on 2026-05-06 confirmed ProShop User pages expose no CKEditor and no visible file inputs in non-edit view. P31's base64-image-into-CKEditor pattern cannot be reused. If we ever revisit this (e.g., to automate HR write-up filing), the next step is to re-run `inspect_user_page.py` *after* clicking Checkout on a candidate sub-form (`documentqueue` is the only one with Print/Save/Copy buttons — best initial candidate). Mechanism for any post-Checkout file input remains unknown.
- ~~**Fix the dev-server reboot cycle (waitress + /api/shutdown)**~~ — **DONE 2026-05-10** as part of the srv-01 migration. `app.py` now runs under `waitress.create_server()` with an inlined `_serve_with_shutdown()` helper exposing `POST /api/shutdown` for graceful close. Overseer's `_stop_process` POSTs there first (2s timeout) then waits 5s for natural exit before terminate(). Same pattern applied across all 9 Flask services in the Overseer fleet.
- **Exercise the new `/photo/<id>` fix-page** — open `/queue` from the tablet, tap photo #5 (`R3V1-10852`) or #6 (`ICO1-10-02004`), pick an operation from the dropdown, hit Save & Retry. Confirm the worker uploads on its next 60s cycle. Then test Delete on a junk photo. End-to-end was untested 2026-05-04 because the service was unreachable; .71 has since rebooted so this is now exercisable.
- **MFG+EDP enrichment for COTS and parts** — `_tool_purchasing_info()` only handles `entity_type == "tool"`. COTS and parts both have approvedBrands/equivalents tables in ProShop that should feed the same email-body enrichment. Mirror the tool path in `proshop_client.get_purchasing_info()` and in `app.py:449` once the COTS schema is confirmed.
- **P35 Phase 2 build in progress (API-driven)** — `purchasing/proshop_basic_auth.py` and `purchasing/proshop_vpo.py` exist; dry-run validated against LUB-116. See P35 CLAUDE.md Next Steps for the remaining checklist (run `--live` test, build `worker.py`, wire into `app.py`, add `mark_vpo_created` to `queue.py`).
- **Fix `email_draft._ensure_folder()`** — only searches root-level mail folders. If the "Purchasing - To Review" folder gets nested under another folder, Flask creates a duplicate at root on next restart. Either walk childFolders recursively or persist the folder ID across restarts.
- **COTS Cost-scrape brittleness** — heuristic in P30's `buy-content.js` worked for LUB-116 but missed for THI-17. Inspect the THI-17 page DOM and tighten the column-finder so the auto-quote path stops being the default for items that DO have a price on screen.
- **Email name-extraction polish** — `purchasing/vendors.first_name_of()` only confidently extracts a first name when the local part has a dot (e.g. jaime.gomez). For `briannab@`-style addresses it falls back to "Hello,". Consider adding an optional `first_name` field to `vendor_map.json` entries.
- **Outlook draft delete via Graph returns 404** — observed on synthetic order cleanup; uncertain if it's a permission scope issue (app token may not delete sent items) or a folder-routing quirk. Investigate next time the queue needs cleanup.
- **Graph `from`/`sender` override on draft silently ignored** — discovered 2026-05-04 while drafting an email for Wolfgang's `wolfgang@` alias. PATCH returns 200 but the From sticks at tom@. Needs `Mail.Send` permission added to the Graph app + Send-As granted on tom@'s mailbox (Exchange admin: `Add-MailboxPermission tom@ -User <app-principal> -AccessRights SendAs`). Not blocking — Wolfgang picks From in Outlook UI before sending — but if we want full programmatic identity routing for purchasing emails, fix this. See `reference_wolfgang_alias.md` in memory.

## Interfaces

Produces: Flask UI under waitress (port 5003) with POST /api/shutdown for graceful Overseer-managed stop, photos.db (SQLite at photo-uploader/data/photos.db), purchasing.db (SQLite for P35 order queue at photo-uploader/data/purchasing.db), JPEG photos (photo-uploader/data/photos/{type}/{id}/), /api/health endpoint, /api/print-label endpoint (renders + sends PNG to Brother PT-P700), /api/queue-order + /api/approve/<id> + /api/reject/<id> + /approvals page (P35 purchasing approval queue), /photo/<id> per-photo edit page + /api/photos/<id>/update + /api/photos/<id>/delete (clickable queue rows route here so operator can set a missing operation_number and retry, or delete a stuck photo), Outlook drafts in tom@traxismfg.com's "Purchasing - To Review" folder via Microsoft Graph, suggestions.md (operator feedback)
Consumes: ProShop GraphQL API (workorders, tools, equipment, parts, fixtures, cotsItems, nonConformanceReports), ProShop web UI via headless Selenium, Brother PT-P700 print service at http://10.1.1.242:5002/api/print-image (shared with P9/P22/P30), Microsoft Graph API (Mail.ReadWrite app permission) for purchasing email drafts, vendor_map.json from `35. Purchasing Automation/` for P35 vendor lookup, .traxis.env (PROSHOP_CLIENT_ID, PROSHOP_CLIENT_SECRET, PROSHOP_SCOPE, PROSHOP_USERNAME, PROSHOP_PASSWORD, GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET)
Contracts: Port 5003 must not conflict with other services. Photo storage at photo-uploader/data/photos/ syncs via Dropbox. Upload worker consumes ProShop web UI via headless Selenium. Written description URL pattern: `{BASE}/procnc/parts/{customer}/{partNumber}$formName=writtenDescription&opId={opNumber}`. OAuth scope requires: parts:rwdp, workorders:rwdp, users:r, tools:rwdp, toolpots:r, fixtures:r, ots:r, equipment:r, nonconformancereports:r. Print label endpoint POSTs `{image_base64, copies, label_name}` to print service (same payload as P30). Label designs match P30 exactly: material/equipment/tool/box auto-width 128px tall, COTS fixed 450×128px, all at 180 DPI for 24mm tape. P30 extension's "Buy" button POSTs `{entity_type, entity_id, qty, unit_cost?, vendor?, brand?}` to /api/queue-order; backend either auto-approves under-threshold orders or drafts a vendor quote-request email (capped 3/day per vendor) when unit_cost is missing. **Tool entity requests:** if no vendor scraped, server defaults to AJ Rodco; quote-request email subject/body uses `{approvedBrand} {vendorToolId/EDP}` from ProShop tool library (top approvedBrands record), with the description below — falls back to description, then entity_id, if approvedBrands is empty. Outlook draft folder lookup is root-level only — folder must stay at the mailbox root.
