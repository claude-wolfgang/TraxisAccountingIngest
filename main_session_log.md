# Claude Projects — Session Log

Central log of all Claude Code sessions across Traxis projects.
Synced via Dropbox so both machines stay in sync.

---

## 2026-05-04

### P29 + P31 + P1 (Overseer): FedEx label support, photo-queue fix-page, Overseer zombie-PID adoption fix

**Date:** 2026-05-04 (evening, same day)

**Task:** Three threads chained off each other: (1) make the Rollo printer auto-resizer handle FedEx labels alongside UPS, (2) make failed-upload rows in the P31 queue clickable so the operator can fix the missing-op-number error and retry, (3) when (2) led to deploying via service-restart, surface and fix a latent Overseer bug that was making restarts permanently brittle.

**What was done:**

1. **P29 — FedEx labels.** FedEx Ship Manager 8.5x11 PDFs differ from UPS in two ways: (a) page authored with `page.rotation == 270` so PyMuPDF's pixmap renders sideways, and (b) the actual 4×6 label is a separate content block from a small page-header summary (and sometimes from a doc tab). Existing UPS-tuned bbox crop pulled in everything together, shrinking the label to ~1/3 size, and rendered it upside-down. Added:
   - `page.set_rotation(0)` before render so we work in PDF-native coordinate space — text-direction analysis below would otherwise reference a different frame than the pixmap.
   - `_split_axis()` + `_find_label_region()` — two-axis whitespace-strip detection that splits the bbox into distinct content blocks (handles label+doc-tab stacked AND label+instructions side-by-side, which is what FedEx's laser fold-and-tuck format produces). Picks the largest block by area.
   - `_region_is_upside_down()` — reads PyMuPDF per-line `dir` cosine inside the chosen region; if predominantly `cos_t < -0.9` (180° rotated), flips the cropped image. FedEx ship-manager labels are intentionally upside-down on the page so a user folds the sheet for laser-print pouches.
   - Verified with sample `2026-05-04T20_32_39-FedEx-Shipping-Label.pdf` — clean 4×6 output, addresses upright, 2D barcode + tracking + ZIP barcode all readable. UPS path unchanged because multi-block detection is no-op when content is one contiguous block.

2. **P31 — queue rows clickable + per-photo fix page.** Failed photos #5 and #6 (parts R3V1-10852, ICO1-10-02004) had no `operation_number`, which the upload worker logs as a warning every 60s and can't recover from. Rows in `/queue` were previously inert. Added:
   - `database.update_photo_fields(photo_id, **kwargs)` (partial update with optional `reset_status` flag that clears error + resets retry_count) and `database.delete_photo(photo_id)` (returns file_path for caller to unlink).
   - `GET /photo/<id>` route + `templates/photo_edit.html` — shows photo, status, error, current entity, and (for workorder/part) an Operation dropdown loaded from `/api/operations`. Save & Retry sets the op + flips status back to pending so the worker re-attempts upload on its next 60s cycle.
   - `POST /api/photos/<id>/update` and `POST /api/photos/<id>/delete` — JSON endpoints driven by `static/photo_edit.js`.
   - `templates/queue.html` — added `data-href` + `.queue-row` class with a tiny inline script that navigates to `/photo/<id>` on click.
   - CSS additions for clickable rows (cursor + hover/active states), edit-grid layout (image left / metadata right), and tablet-friendly button sizes.

3. **P1 (Overseer) — zombie-PID adoption bug.** Trying to deploy the P31 changes meant restarting the Flask service. That surfaced a runaway loop: when the photo uploader was force-killed, Werkzeug's listening socket lingered as a "zombie" (kernel kept attributing it to the dead PID because of pending CLOSE_WAIT connections). Overseer's `_find_pid_by_port()` returned the zombie PID first, `_start_process()` "adopted" it as the running service, health checks then timed out forever, restarts kept re-adopting the same corpse. **Fix:** added `_pid_alive()` static method on `ServiceManager` using Win32 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess` (distinguishes `STILL_ACTIVE` from "exited but kernel hasn't reaped" — `OpenProcess` alone can succeed on a zombie). `_find_pid_by_port` now scans netstat output, skips dead PIDs, returns the first alive listener. Verified: after Overseer restart, log shows `[PhotoUploadService] started: PID NNNN` (true spawn) instead of `adopted: Found existing process PID 15884` (zombie).

4. **Where it stands as of close.** Overseer fix is good and was load-bearing — without it, future "service force-killed → zombie socket" events would put PhotoUploadService in the same flapping loop. **However**, today's specific zombie state didn't recover: 2h+ uptime, port 5003 has 9 listeners (1 alive, 8 zombies) because Overseer's restart cycles each created a fresh-then-killed process and Werkzeug + force-kill always leaves a zombie. Connections to port 5003 hash across all 9 listeners; only ~1/9 reach the alive process, so HTTP probes and tablet uploads still time out. **Wolfgang said "rebooted" but `LastBootUpTime` showed 16:01:09 — the original boot, not a fresh one.** The new edit-page code is on disk and correct; it'll go live the moment a real OS reboot clears the zombies and Overseer starts the photo uploader cleanly. Not done this session: switching the photo uploader from Werkzeug dev server to waitress (would prevent the original tablet-upload-hangs-process scenario that started this whole chain), and a stopgap in Overseer to suppress restart attempts when fewer than X connections out of Y listeners are reaching the alive PID.

**Files modified:**

- `29. Rollo Printer App/rollo_printer_app.py` — added `_split_axis()`, `_find_label_region()`, `_region_is_upside_down()`; modified `render_pdf_to_images()` to clear page rotation, run multi-block detection, and 180° auto-correct via text-direction
- `1. Proshop Automations/Overseer/overseer.py` — added `_pid_alive()` static method on `ServiceManager`; modified `_find_pid_by_port()` to verify aliveness and skip zombies
- `31. Photo Upload Service/photo-uploader/database.py` — added `update_photo_fields()`, `delete_photo()`; added `_UPDATABLE_FIELDS` whitelist
- `31. Photo Upload Service/photo-uploader/templates/queue.html` — added `.queue-row` data-href + click handler
- `31. Photo Upload Service/photo-uploader/templates/photo_edit.html` — NEW per-photo edit page
- `31. Photo Upload Service/photo-uploader/static/photo_edit.js` — NEW (loads ops, save+retry, delete handlers)
- `31. Photo Upload Service/photo-uploader/static/style.css` — clickable-row hover state + edit-page layout (.edit-grid, .edit-photo, .edit-meta, .actions-row, btn-primary/secondary/danger, mobile breakpoint)
- (Note: `app.py` already contained the `/photo/<id>`, `/api/photos/<id>/update`, `/api/photos/<id>/delete` route handlers in HEAD — `git diff` shows no change. Either committed earlier or my Edit was idempotent against pre-existing identical content. End state of the file is correct either way.)

**Status:** Code complete on disk. Two open blockers below.

**[NEEDS WOLFGANG]:**
- Real OS reboot of `.71` to clear all 9 zombie listeners on port 5003. Until then, photo upload service is unreachable from the tablet, and the new fix-page can't be exercised.
- Decide whether to switch P31 to waitress before the next deploy of the photo uploader, to prevent this whole chain happening again the next time the tablet stalls mid-upload.

---

### P26: SMC AW40-04DG-A equipment record creation via ProShop API + spare-parts quote workflow

**Date:** 2026-05-04 (later, same day)

**Task:** Create the SMC AW40-04DG-A pneumatic filter regulator as a real ProShop equipment record (the markdown reference doc had been sitting as a stub), duplicate it for the second SMT machine, and draft a vendor quote-request email for spare parts. First-ever use of ProShop's `addEquipment` mutation from this codebase.

**What was done:**

1. **`addEquipment` mutation discovery + first call** — Introspected `AddEquipmentInput` (12 fields, only `equipmentType` required). Inventoried existing `equipmentType` prefix codes (Cal, TG, MT, OM, 5S, CA, REG, PUMP, etc.) and chose `CA` for the SMC unit since it lives downstream of the air compressor. Initial mutation blocked by OAuth scope (`equipment:r` only) — Wolfgang appended `equipment:rwdp` to the BA16-EFAF-B154 client; mutation then succeeded. **No `acceptNewRecord` block** on equipment (unlike CustomerPo / PurchaseOrder), so once scope was granted the path was clean. Created **CA152** for SMT machine M2.

2. **JSON-escape passthrough bug surfaced** — em-dashes and `\n` in the original payload came back stored as literal `—` and `\n` text. ProShop's GraphQL doesn't unescape JSON escapes server-side. Fixed by patching the record with ASCII-only content and ` | ` separators instead of newlines. Saved as memory `project_proshop_equipment_api_quirks.md` to avoid relearning.

3. **`updateEquipment` / `deleteEquipment` identifier asymmetry** — Both mutations key on the **Tool #** field (`tool: String!`), NOT `equipmentNumber`. ProShop auto-builds Tool # as `equipmentType + equipmentNumber` (so CA152 → "CA152"). `EquipmentQuery` filter has no `equipmentNumber` field at all — to look records up by record ID, query by `tool` or paginate. ProShop URL pattern is `/equipment/{equipmentType}/{tool}` (so CA152 lives at `/equipment/CA/CA152`, not `/equipment/152` as the photo-uploader's `search_equipment()` constructs).

4. **CA153 created as duplicate for M3** — Same payload, location updated to "SMT machine M3 - pneumatic prep panel..." Updated CA152's location to explicitly call out M2.

5. **OC Pneumatics quote-request email drafted** — Vendor not in `vendor_map.json`; sales address resolved to `sales@ocaire.com` via web. Drafted via P31's `email_draft.create_draft()` into tom@'s "Purchasing - To Review" Outlook folder. Multiple iterations: address corrected, drain port confirmed as one-touch ø6 (so AD48-A → AD48-6-A on the BOM, but with hedging language since the one-touch is a separately-threaded adapter), made-up "Bldg 2 / Ste C" removed, signature switched to Wolfgang Griffith with `wolfgang@traxismfg.com`. Wolfgang added `wolfgang@traxismfg.com` as an Exchange alias on tom@'s mailbox via GoDaddy's M365 admin; **Graph app credential cannot programmatically override `from`/`sender`** (PATCH returns 200 but silently ignored — needs `Mail.Send` + Send-As, which app currently lacks). Wolfgang switched From manually in Outlook UI before sending. Saved alias mapping + Graph limitation as memory `reference_wolfgang_alias.md`.

6. **Image copy to CA153 attempted, abandoned** — CA152's images sub-table has IMG_3383 (assembly) + IMG_3492 (model label) uploaded directly via the ProShop UI. ProShop GraphQL has **zero image mutations** — images sub-table is UI-only. Tried 4 download paths (API token, session cookie, in-page fetch, top-level navigate + canvas read); all blocked by file-server's separate auth on `:8181` subdomain. Wolfgang opted to copy manually rather than spend the half-day on Selenium discovery for two photos.

**Files modified:**

- `26. SMT Post Processor Development/SMT Maintenance/SMC_AW40-04DG-A_equipment.md` — drain port confirmed one-touch (no longer "verify on disassembly"); AD48-A → AD48-6-A throughout BOM, failure modes, replacement procedure, and stock-qty TODO; barb-vs-one-touch language replaced with installed-fact statements
- `26. SMT Post Processor Development/SMT Maintenance/probe_create_equipment.py` — NEW (working introspection + create template; runs `--execute` to actually call mutation)
- `26. SMT Post Processor Development/SMT Maintenance/probe_create_m3_duplicate.py` — NEW (the actual M3 duplication call, kept as record)
- `26. SMT Post Processor Development/SMT Maintenance/probe_fix_unicode.py` — NEW (documents the unicode workaround via updateEquipment)
- `26. SMT Post Processor Development/SMT Maintenance/draft_oc_pneumatics_quote.py` — NEW (initial quote-request drafter; subsequent edits done via direct Graph PATCH and not kept as scripts)
- `26. SMT Post Processor Development/CLAUDE.md` — NEW (created at session close — first CLAUDE.md for this project)
- `1. Proshop Automations/.traxis.env` — appended `+equipment:rwdp` to PROSHOP_SCOPE on the BA16-EFAF-B154 client
- (memory) `project_proshop_equipment_api_quirks.md` — NEW
- (memory) `reference_wolfgang_alias.md` — NEW
- (memory) `MEMORY.md` — added two index entries

**ProShop side-effects (not in repo):**

- Equipment record `CA152` created (SMT M2 SMC AW40-04DG-A) — https://traxismfg.adionsystems.com/procnc/equipment/CA/CA152
- Equipment record `CA153` created (SMT M3 SMC AW40-04DG-A) — https://traxismfg.adionsystems.com/procnc/equipment/CA/CA153
- Both records have full notes (parts list, vendor, drain-fitting confirmation, install location)

**M365 side-effects:**

- `wolfgang@traxismfg.com` Exchange alias added to tom@'s mailbox via GoDaddy
- One Outlook draft created and patched repeatedly in tom@'s "Purchasing - To Review" folder; sent by Wolfgang from his alias

**Status:** Complete. Awaiting OC Pneumatics quote response — once received, update spare parts BOM with actual prices and add `ocaire.com` to `vendor_map.json` so future SMC orders auto-route.

---

### P31/P35: tool-page Buy — AJ Rod auto-routing + MFG+EDP email enrichment

**Date:** 2026-05-04

**Task:** Wolfgang clicked the new "Buy" button on tool A268 and saw nothing happen. Connect the existing Phase 1.5 quote-request email path so tool-page clicks actually draft something — and make the email vendor-readable instead of leaking internal tool numbers.

**What was done:**

1. **Diagnosis** — A268 click did reach `/api/queue-order` and queued order #4 as `pending`, but the email-draft branch was skipped because `buy-content.js`'s `scrapeVendor()` returned null on the tool page (the regex looks for an exactly-"Vendor" `<th>`, which COTS Equivalents tables have but tool pages don't). So both `unit_cost` and `vendor` came back null and the order parked silently.

2. **AJ Rod auto-routing** — encoded Wolfgang's domain rule directly in `app.py:442`: any tool-entity request with no vendor scraped now defaults to `"AJ Rodco"`. Older tool records may name a different vendor, but Traxis consolidates all tool sourcing through AJ Rod. Saved as `project_aj_rodco_tool_routing.md` in memory so future sessions don't re-introduce page-scrape heuristics for tool pages.

3. **MFG + EDP email enrichment** — added `proshop_client.get_purchasing_info()` returning the top `approvedBrands` record for a tool (manufacturer name, vendorToolId/EDP, description). `app.py:445` now consults it for tool requests and rebuilds the email subject/body around `{brand} {edp}` instead of the internal toolNumber. Vendors recognize their own catalog numbers; "A268" means nothing to them. Falls back to description if approvedBrands is empty, then to entity_id as last resort. Verified A268 → SGS 34705 with the description below in the body. Synthetic POST drafted email #6 to jaime.gomez@ajrodco.com; Wolfgang sent it.

4. **Cleanup** — orders #5 and #6 (synthetic test drafts) marked `rejected` via direct SQLite UPDATE on .71 (the reject endpoint only accepts `pending`, not `awaiting_quote`); Graph DELETE attempted on the corresponding draft messages but returned 404 (likely because Wolfgang already sent #6 and #5 may have moved). Manual sweep of "Purchasing - To Review" folder may still be needed for #5.

**Operational miscue:** killed the photo-uploader twice mid-session to pick up the AJ Rod edit, leaving a Windows-kernel zombie LISTEN socket on port 5003 each time. First reboot of .71 cleared it; second occurrence cleared on its own as the kernel aged out the half-closed sockets. Wolfgang flagged the recurring reboot pattern as unacceptable. Root cause: Werkzeug dev server `app.run()` can't be shut down cleanly — Overseer's `Popen.terminate()` hard-kills, mid-flight connections enter CLOSE_WAIT, dead PID retains the LISTEN socket. Fix added at top of P31 Next Steps (waitress + `/api/shutdown` endpoint).

**Files modified:**

- `31. Photo Upload Service/photo-uploader/app.py` — AJ Rod default for tool entities; tool quote-request email now uses MFG+EDP+description from ProShop tool library
- `31. Photo Upload Service/photo-uploader/proshop_client.py` — new `get_purchasing_info()` + `_tool_purchasing_info()` (reads top approvedBrands record per Wolfgang's convention)
- `31. Photo Upload Service/CLAUDE.md` — Next Steps reordered; waitress migration added at top
- `35. Purchasing Automation/CLAUDE.md` — Next Steps strikethrough on tool-vendor scraping (now obsolete)
- `MEMORY.md` + `project_aj_rodco_tool_routing.md` — sole-tool-vendor rule

**Status:** Complete and verified end-to-end. Service wedge fix flagged for next session — until then, avoid restart-driven deploys on this service or accept a wait/reboot.

---

## 2026-05-03

### P35: purchasing automation Phase 0/1/1.5 — bootstrap, queue, auto-quote-request

**Date:** 2026-05-03 (later, same day)

**Task:** Stand up a one-tap reordering flow. Operator clicks "Buy" on a ProShop COTS/Tool/Part page; backend either auto-approves under-threshold orders or drafts a vendor quote-request email when the page has no price.

**What was done:**

1. **Plan doc** — `35. Purchasing Automation/PLAN.md`. Architecture, file list, 4-phase build order, JSON/SQLite schemas, open risks. Picked Selenium-only (per Wolfgang: API repeatedly fails for VPO creation), folded P35 runtime into P31's Flask, JSON rules home, P27 owns cost-feedback loop downstream. Single Outlook folder ("Purchasing - To Review") for all drafts pending Send. Approval queue accessible from any LAN browser (no separate tablet UI).

2. **Vendor-map bootstrap (Phase 0)** — built `probe_sent_vpos.py` (Graph API on tom@'s Sent Items) and `probe_rene_mbox.py` (Thunderbird mbox parser for rene@'s 7.7GB archived Inbox; rene@'s M365 mailbox was purged). Found tom@ had only 11 VPOs in 3yr; rene@ had 6,223 purchasing-shaped messages from 21,437 total. Identified vendor signal (sender domain, purchasing-keyword subject), confirmed cinnamon.clark@ajrodco.com vs jaime.gomez@ — both active per Wolfgang. Hand-wrote `vendor_map.json` with 37 vendors, marked stale entries, MSC/McMaster as `online_url` portals, AJ Rodco with both reps active.

3. **Phase 1: queue + UI** — new `purchasing/` subpackage in P31 with `queue.py` (SQLite at `data/purchasing.db`), `rules.py` (item→category→default fallback), `rules.json` starter (defaults to manual review). Flask routes: `POST /api/queue-order`, `POST /api/approve/<id>`, `POST /api/reject/<id>`, `GET /approvals` page with Approve/Reject/Approve-All buttons. New P30 content script `buy-content.js` injects purple "Buy" button next to existing label buttons on COTS/Tools/Parts pages; scrapes vendor + brand + best-effort unit_cost; routes through service-worker (mixed-content workaround). Manifest bumped to 1.6.0, host_permissions added for `http://10.1.1.71:5003/*`.

4. **Phase 1.5: auto quote-request email** — new `purchasing/email_draft.py` (Microsoft Graph helper, lazy folder creation in tom@'s "Purchasing - To Review" folder) and `purchasing/vendors.py` (vendor-map lookup + first-name extraction). Wolfgang granted Mail.ReadWrite app permission in Azure for the Graph principal. When `unit_cost` is null on submit AND vendor in map AND today's quote-requests to that vendor < 3, the backend drafts an Outlook message ("Pricing request: {entity_id} qty {qty}") and sets status=`awaiting_quote`. Cap of 3 drafts per vendor per day enforced via `quote_requests_today()` in queue.py. Approvals page shows the awaiting-quote rows in a separate section with a link to the draft.

5. **End-to-end verified** — clicked Buy on a COTS page (THI-17 PEM thread inserts, qty 500, vendor "DB Roberts"), order landed in /approvals as pending with vendor + brand scraped cleanly but unit_cost null (cost-column heuristic missed for that page layout). Curl-tested full path: POST /api/queue-order with vendor=DB Roberts → quote-request drafted to lrobinson@dbroberts.com, order #3 status=awaiting_quote, draft visible in Outlook. Two MainPC reboots required to deploy (ghost-socket pattern still in play).

6. **Folder rescue** — Wolfgang accidentally moved "Purchasing - To Review" into Deleted Items while reorganizing. Walked Graph childFolders to locate it, restored to root via `mailFolders/{id}/move` with `destinationId: msgfolderroot`. Folder must stay at root because `_ensure_folder()` only searches root-level — flagged for fix.

**Files modified/created:**
- `35. Purchasing Automation/` (new project): PLAN.md, CLAUDE.md, vendor_map.json (37 vendors), probe_sent_vpos.py, probe_rene_mbox.py
- `31. Photo Upload Service/photo-uploader/purchasing/` (new): __init__.py, queue.py, rules.py, rules.json, vendors.py, email_draft.py
- `31. Photo Upload Service/photo-uploader/`: app.py (4 new routes + DB init + Graph wiring), templates/approvals.html (new), templates/base.html (Approvals nav), static/approvals.js (new), static/style.css (purple buy variant + status badges)
- `30. Material Label Extension/traxis-material-label/`: src/buy-content.js (new), background/service-worker.js (QUEUE_ORDER proxy), src/content.css (purple Buy variant), manifest.json (v1.6.0, +5003 host_permission, +Buy content script registration)
- P31 CLAUDE.md (Key Files, Interfaces, new Next Steps section)
- P30 CLAUDE.md (new Next Steps section)
- TRAXIS_ECOSYSTEM.md (P30 + P31 entries updated, new P35 entry, P35 row added to Interface table)

**Key decisions:**
- Selenium not API for VPO creation (per Wolfgang's history with the gated mutation)
- Fold runtime into P31 not standalone Flask — saves shared Selenium login + Overseer wiring
- Quote-request rate limit = 3 drafts/vendor/day, enforced in DB query (no separate counter table)
- Outlook drafts go to a single dedicated folder so they don't mix with personal drafts
- "Most recent received from" is the vendor signal (not "most recent sent to") — accepted some noise (cold sales-rep outreach) since email-archeology refinement was deemed not worth the run time

**Status:** Phase 1.5 live in production after second reboot. Buy button works end-to-end — confirmed with one real Buy (THI-17) plus one curl-driven test (deploy validation). Phase 2 (Selenium VPO creation) is the next planned step. P30 v1.6.0 is sideload-tested only; CWS resubmission pending an audit pass.

---

### P25: Garrett/Thomas onboarding doc + VS Code on .178

**Date:** 2026-05-03 (third close — short)

**Task:** Wrap the lathe program review with a Garrett/Thomas-facing doc, then walk Wolfgang through installing VS Code on .178 for editing project files.

**What was done:**

1. **Created `25. Agent Exploration/LATHE_PROGRAM_REVIEW.md`** — onboarding doc for Garrett/Thomas to fill in `lathe_programs.json`. Covers: file location, fields to edit (`part_number`, `description`, `op_number`), the two FOCAS-extracted candidates (O2004, O4256) to verify first, how to use `inspect_programs.py --o O####`, how to read the YCM CRT (`MDI > PROG > DIR`), part-number lookup guidance ("don't invent part numbers"), and a quick checklist. One page, picks up cold.

2. **VS Code install on .178** — guided Wolfgang through downloading from `code.visualstudio.com`, choosing user-install, checking "Add to PATH" + "Register as editor." Confirmed the Ready-to-Install screen via screenshot. Recommended Python extension + integrated terminal as the two productivity moves.

**Files created:**
- `25. Agent Exploration/LATHE_PROGRAM_REVIEW.md` — Garrett/Thomas onboarding (gitignored, Dropbox-synced)

**Status:** Both done. Garrett/Thomas have a self-contained entry point. Wolfgang has VS Code on .178.

---

### P25 + P12: digest shortening, lathe bootstrap, FOCAS program_directory fix

**Date:** 2026-05-03 (later, same day — followed the close-ritual session)

**Task:** Multi-thread session driven by Wolfgang's morning Telegram digest reading as a catastrophe. Trace from "shorten the digest" through "what's making it look bad" through "fix the underlying noise sources." Bonus: bootstrap p25's `lathe_programs.json` and fix the FOCAS `program_directory` polling that's been silently broken.

**What was done:**

1. **Diagnosed why the digest read as catastrophic** — three buckets: (a) overrun metrics aggregated lifetime, no time window; (b) known-noisy checks (NC program lookup false positives, all-alarm count, FOCAS stale on .178); (c) action items pulled from a Haiku-summarized index that was unreliable.

2. **Time-windowed and threshold-tightened the audit** (`25. Agent Exploration/audit_engine.py`):
   - `check_overrun_patterns`: now computes both lifetime metrics (kept for trend) AND last-90-day metrics (`recent_overrun_rate_pct`, `severe_overrun_rate_pct`, `recent_hours_over_target`, `recent_severe_overrun_count`). Severity now driven by severe-rate (>30% failure, >15% warning) on the recent window. Headline switched from "any overrun" to "severe (>20% over)" — which is the actionable signal that doesn't punish tight quoting.
   - `check_overdue_work_orders`: 3-day grace window. <3 days late counted in metric for trend but no finding emitted. New `overdue_wo_3plus` metric drives digest.
   - `check_uncertified`: window 7→3 days for digest-actionable findings. Both 3-day and 7-day counts recorded.

3. **Rewrote the digest format** (`25. Agent Exploration/alerter.py`):
   - Compact 4-6 line message vs 25-30 lines before. One headline of real signals, optional worst/action/secondary lines, summary counts.
   - Suppressed `nc_program_missing` (known false-positive engine), `alarms_7day` (mostly benign), generic `overrun_rate_pct`.
   - Replaced `_get_open_items()` to scan each project's CLAUDE.md `[NEEDS WOLFGANG]` lines directly. Single source of truth = the project Next Steps maintained by the close ritual. Drops dependency on Haiku-generated `project_index.json` action items.

4. **Bootstrapped `lathe_programs.json` from FOCAS history** — merged local Dropbox-synced data + live data (pulled via SSH from .71) into 38 distinct T2 O-numbers spanning Feb 2 → May 1, 2026. Each entry seeded with sample/date metadata in description, `part_number` left blank for Garrett/Thomas. Two entries (O2004 → suggested `10-2004`; O4256 → suggested `10042 or 10164`) auto-extracted from FOCAS `active_block_content` comments — TPM-posted programs whose headers were captured during execution.

5. **Built `inspect_programs.py`** (`25. Agent Exploration/inspect_programs.py`) — CLI that dumps every captured `(comment)` block per machine or per program. `--all`, machine-id arg, or `--o O####`. Garrett/Thomas can run it on .71 to see what FOCAS already knows about each program before keying through the YCM directory.

6. **Fixed FOCAS `program_directory` polling** (project 12 / focasmonitor) — the table was empty across all machines because `cnc_rdprogdir2(handle, 0, ref count, dir)` was failing silently (LogDebug). Replaced with two-tier strategy in `MonitoringService.ReadProgramDirectory`: primary `cnc_rdprogdir3` type=0 enumeration, fallback `cnc_rdprogdir3` type=1 for the running program from `cnc_rdprgnum`. Added `cnc_rdprogdir3` + `PRGDIR3` + `PRGDATE` to `Focas.cs`. Added PRGDIR3 insert overload + single-row helper to `Database.cs`. Bumped error logging from LogDebug → LogWarning so silent failure can't recur.

7. **Deployed to .71** — `dotnet publish -c Release` (initially failed because csproj had `SelfContained=false` and .71 has no x86 .NET 10 runtime; rebuilt with `--self-contained true` and changed csproj default to true going forward). Service stopped, 235 self-contained files copied, service restarted, RUNNING confirmed. Sunday machine-off state means no immediate verification — `program_directory` still empty because all 5 FOCAS machines show `connected=0` in samples. Fix is deployed but unverified.

8. **Built verification toolkit on .71**:
   - `verify_program_directory.bat` + `.py` — manual run, prints service status + DB state + recent warnings. ASCII-only output (Windows console encoding).
   - `report_focas_verification.py` — gathers same data, computes verdict (WORKING/PARTIAL/NOT WORKING/INCONCLUSIVE), sends to P25 Telegram bot using p25 config for credentials.
   - `run_focas_verification.bat` + `schedule_tuesday_verification.bat` — wrapper + scheduler. The schedule .bat creates a Windows scheduled task firing Tuesday 2026-05-05 at 9 AM Chicago, with `/Z` + `/ET 10:00` so the task auto-deletes after firing. Verified working via SSH; task is in place on .71 (`Next Run Time: 5/5/2026 9:00:00 AM`).

**Files modified/created:**

p25 (`25. Agent Exploration/`):
- `audit_engine.py` — time-windowed overrun + grace-windowed overdue/uncertified metrics
- `alerter.py` — compact digest + CLAUDE.md-based action item scanner
- `lathe_programs.json` — bootstrapped 38 entries with FOCAS-extracted candidates
- `inspect_programs.py` — new CLI helper
- `CLAUDE.md` — Next Steps reconciled (digest-shorten DONE; FOCAS fix added at item 7)

p12 (`12. FASData Implementation/focasmonitor/`):
- `Focas.cs` — added cnc_rdprogdir3 + PRGDIR3 + PRGDATE
- `Database.cs` — PRGDIR3 overload + InsertProgramDirectoryEntry helper
- `MonitoringService.cs` — rewrote ReadProgramDirectory with two-tier fallback + visible logging
- `FocasMonitor.csproj` — `SelfContained=true` default
- `verify_program_directory.bat` + `.py` — manual verification toolkit
- `report_focas_verification.py` — scheduled-task verifier with Telegram report
- `run_focas_verification.bat` — Task Scheduler wrapper (avoids cmd quoting hell)
- `schedule_tuesday_verification.bat` — one-shot scheduler

Deployed: focasmonitor self-contained build to `C:\FocasMonitor\` on 10.1.1.71; service restarted; running.

**Key decisions:**
- **Severe-overrun rate (>20% over) replaces any-overrun rate as digest headline** — a healthy shop with tight quotes naturally has 50%+ "any overrun." Severe rate is the real shop-health signal.
- **Suppress, don't fix, the noisy checks in the digest** — keep them in audit.db for trend analysis but stop them screaming each morning. NC missing fix and benign alarm filter are still on the backlog (p25 items 2 and 6); their digest re-enable comes after.
- **`[NEEDS WOLFGANG]` is the single source of truth for action items** — alerter scans CLAUDE.md files directly. Eliminates the unreliable Haiku-summarized intermediary.
- **FOCAS polling fix uses cnc_rdprogdir3 with type=0 + type=1 fallback** — backup code only used type=1 (per-program), but type=0 enumeration is more efficient when supported. Two-tier with both gives best chance of working across the YCM 0i-TF and the various Mill controls.
- **Self-contained .NET publish, not framework-dependent** — .71 doesn't have x86 .NET 10 runtime installed; deploying framework-dependent meant immediate service crash. Self-contained adds ~80MB but eliminates this brittleness.
- **Tuesday morning verification via scheduled Telegram report** — Sunday machines off makes today's deploy unverifiable. Tuesday gives a full Monday business day for the fix to populate `program_directory`. Auto-self-deleting task means no cleanup.

**Status:** All edits live. P25 audit + alerter changes will manifest in tomorrow morning's digest. FOCAS polling fix deployed but unverified — Tuesday 9 AM Telegram report will say WORKING / PARTIAL / NOT WORKING / INCONCLUSIVE.

**Open verification windows:**
- Tomorrow (Mon 5/4) AM: first compact digest, will show whether new metrics are populated correctly.
- Tuesday (Tue 5/5) 9 AM: scheduled FOCAS verification fires automatically to Telegram.

---

### Root: close ritual extended to reconcile to-do lists

**Date:** 2026-05-03

**Task:** Examine whether the session close ritual could also curate Wolfgang's saved to-do lists. p25 was the motivating example (its `Next Steps` section had items 4/5/6/8 marked DONE-but-still-listed, never cleaned up).

**What was done:**

1. **Mapped the to-do surfaces** — found three: hardcoded `Next Steps` sections in each project's CLAUDE.md (the main offender), `reminders` table in audit.db (Telegram-driven, 0 pending), and free-form `notes` table (scratch). Step 4 of the existing close ritual already produced an "Open items requiring Wolfgang" section but it was per-session and evaporated.

2. **Drafted a two-step extension, then collapsed it on Wolfgang's instruction** — first added step 5 "Backlog reconciliation" alongside the existing step 4 "Open items." Wolfgang flagged that two to-do-shaped outputs was one too many for him to scan. Merged into a single step 4 "To-do reconciliation": one consolidated view at beat 4, per-project blocks of proposed `Next Steps` edits, urgent items tagged `[NEEDS WOLFGANG]` and sorted to top, cross-cutting items in root CLAUDE.md's `Next Steps` (lazy-created). Step 5 became Git commit (was 6).

3. **Clarified scope** — the new ritual touches CLAUDE.md `Next Steps` sections only. It does NOT affect the daily Telegram audit digest from `alerter.py`, which is a separate system surfacing audit findings on a schedule. Wolfgang flagged the long Telegram message as a real concern; logged it as a follow-up.

**Files modified:**
- `CLAUDE.md` (root) — close ritual steps section: merged steps 4 + 5 into a single step 4 "To-do reconciliation"; renumbered Git commit; updated review-line.

**Key decisions:**
- One output for to-dos, not multiple. Single source of truth = each project's `Next Steps` section. Cross-cutting items get a root `Next Steps` section.
- Urgency preserved within the flat list via `[NEEDS WOLFGANG]` tag + top-sort, instead of a separate "Open items" surface.
- "Touched OR discussed this session" — catches to-dos surfaced in conversation about projects whose code didn't change (like p25 today).

**Status:** Ritual change live. First test is this very close. Telegram digest length is a separate, deferred ask.

---

### P31: server-side label printing + WO part-number search

**Date:** 2026-05-03

**Task:** Add label printing to the photo-uploader (so the shop tablet can do what P30's Chrome extension does on desktop), then revise the search so part-number lookups work in WO mode.

**What was done:**

1. **Server-side label rendering (`label_generator.py`, new)** — Pillow port of P30's Canvas-based generators for all five label types: material, box, equipment, tool, COTS. Auto-width 128px tall for the first four; fixed 450×128 with 2× supersample for COTS. QR via `qrcode` lib, fonts via Windows Arial fallback chain. Renderers return base64 PNG ready for the print service. Avoided porting JS to JS in Fully Kiosk — keeps label logic in one place (Python) so design tweaks don't need tablet cache busting.

2. **Per-type label data fetcher (`proshop_client.get_label_data`)** — Single dispatch method that runs an OAuth GraphQL query per entity type (`workOrder`, `equipments`, `tools`, `cotsItems`) with graceful field fallback: tries enriched fields first (`materialType`, `materialGrade`, `serialNumber`, tool `location`), retries with minimum guaranteed fields if any unknown-field error, returns at least the entity_id so a degraded label still prints.

3. **`POST /api/print-label` endpoint (`app.py`)** — Accepts `{label_type, entity_id, box_qty?, copies?}`, looks up data, renders, POSTs `{image_base64, copies, label_name}` to `http://10.1.1.242:5002/api/print-image` (same payload as P30/P9/P22). Smoke-tested: material WO 26-0120 and COTS THI-219 both printed on Brother PT-P700.

4. **Print-label bar in capture step (`home.html`, `photo.js`, `style.css`)** — Buttons appear above "Take Photo" for entities that support a label: workorder gets two (Material + Box), tool/equipment/cots each get one. Box label prompts for qty in the browser. Buttons hidden for part/fixture/ncr/claude (no P30 equivalent).

5. **WO search by part number** — Two original bugs:
   - **Frontend forced `XX-YYYY` digit-only formatting** on the WO search input, so "ABC-1234" became "12-34". Removed the auto-format. Also dropped `inputMode="numeric"` so the tablet keyboard surfaces letters by default. Placeholder updated to "Type WO number or part number...".
   - **Backend never had part-number data to match against.** `partPlainText` is free-text descriptive (e.g. "R2S1-rework 10469 Housing-DL"), so true part numbers like "10130" rarely appear. Added `part { partNumber partName }` to the bulk `workOrders` query and matched against it in `search_work_orders`.

6. **Newest-first WO sort + Complete status** — Added `Complete` to the status list `_fetch_work_orders` queries (was Active/Queued/Scheduled only — recently-finished WOs were invisible). Added `matches.sort(key=lambda m: m["id"], reverse=True)` so results come back newest-first (lexical descending on WO number works because year prefix dominates).

7. **Ghost socket dance, twice** — Each Flask restart via `taskkill /F` left port 5003 with a "ghost listener" (Windows TCP keeps the dead PID's socket bound while CLOSE_WAIT connections from other clients drain). Workaround: switch to a temporary port (5004 / 5007) for testing, reboot MainPC to clear the ghost. Went through this for the label-printing deploy and again for the search revision. After each reboot the autostarted Flask comes back clean on 5003 with the new code (Dropbox-synced from .178).

**Files modified/created (all in `31. Photo Upload Service/photo-uploader/`):**
- `label_generator.py` — new, ~210 lines, 5 renderers
- `proshop_client.py` — `get_label_data()` + per-type `_*_label_data()` helpers; bulk WO query now pulls `part {partNumber partName}`; `Complete` added to status list; `search_work_orders` matches against linked-part fields and sorts newest-first
- `app.py` — `/api/print-label` route, `requests` import, `LABEL_TYPES` map
- `static/photo.js` — print-bar handlers, `LABELS_FOR_TYPE` map, removed WO digit-only forcing, `inputMode="text"` always, broader placeholder
- `templates/home.html` — `print-label-bar` div with 5 buttons in capture step
- `static/style.css` — `.print-label-bar` + `.print-label-btn` (printed/failed states)
- `requirements.txt` — `qrcode[pil]>=7.4`
- `CLAUDE.md` — architecture/key-files/interfaces updated

**Key decisions:**
- Server-side render over porting Canvas to Fully Kiosk's Android WebView. Tradeoff: rewrite once in Python instead of dropping P30 JS in. Worth it because label logic stays in one place and tablet is a thin client.
- Use field-fallback (try enriched then minimal) on label data queries instead of probing schema first. Rationale: some ProShop field names from P30's session-cookie API may not exist in the OAuth API; degrading gracefully is cheaper than a full schema discovery.
- Stop using `taskkill /F` on Flask going forward — every kill creates the ghost socket. Better workflow is edit → save (Dropbox syncs to .71) → reboot when convenient. Acceptable for this project because shop tablet usage is intermittent.

**Status:** Flask back on 5003 after second reboot, new code live, search verified (`?q=10163` returns 4 WOs newest-first with linked part numbers visible). Print buttons not yet user-verified from the tablet — only confirmed via curl smoke tests.

---

## 2026-05-02

### P34: deployment to .71 (corrected from .178), env-path bug fix, SSH remote-control channel

**Date:** 2026-05-02 (session 2 continued after first close)

**Task:** Move P34 from .178 (where I'd installed it by mistake) to .71 (production server). Surfaced an env-path bug along the way. Established a permanent SSH channel from .178 to .71 so future cross-PC tasks don't require Wolfgang to manually run .bats.

**What was done:**

1. **Realized I was on .178, not .71** — `setup_schedule.bat` had been run on the dev workstation, not the production server. Removed the scheduled task from .178 (`schtasks /Delete`).

2. **Made `setup_schedule.bat` portable across user accounts (commit 5d2b04a)** — original hardcoded pythonw path under Superuser's profile would fail for TRAXIS user on .71. Rewrote to discover pythonw via `where` then fall back to common LOCALAPPDATA / Program Files locations.

3. **Created helper .bats for double-clickable verification on .71** — `test_run.bat` triggers the scheduled task and prints heartbeat; `diagnose.bat` runs cws_watcher with regular python.exe so errors are visible AND captures output to `diagnose_output.txt` for cross-PC visibility via Dropbox sync.

4. **Found and fixed env-path bug (commit c61af5b)** — diagnose output showed `KeyError: 'GRAPH_TENANT_ID'`. Root cause: `cws_watcher.py` hardcoded `ENV_PATHS` to `C:\Users\Superuser\Dropbox\...` which doesn't exist on .71 (TRAXIS user, D:\ drive). Fell through to `C:\Users\TRAXIS\.traxis.env` which exists but has no Graph keys. Rewrote `load_env()` to derive paths from the script's own location: `../1. Proshop Automations/.traxis.env` plus `USERPROFILE` fallbacks. Drive letter and username no longer matter. Forward-compatible with the dedicated server migration.

5. **SSH remote-control channel (commit d33f624)** — Probed .178→.71 channels; only SMB (445) was open, no SSH/WinRM/PsExec. Generated ed25519 key for Superuser@.178 (~/.ssh/id_ed25519), wrote `enable_ssh_server.bat` that self-elevates via UAC, installs Windows OpenSSH Server, opens firewall port 22, and authorizes my pubkey in both user and `administrators_authorized_keys`. Wolfgang ran it on .71. Verified end-to-end from .178: `ssh TRAXIS@10.1.1.71` works, `python cws_watcher.py --print-only` runs cleanly remote, `schtasks /Run` triggers the scheduled task and the heartbeat refreshes within ~30s.

6. **Confirmed dedicated server plan (5/7 hardware delivery)** — Read `E:\Downloads\shoestring_server_plan.md`. Plan is solid: Windows + NSSM + git deploy + Tailscale + `C:\traxis\services\` as canonical service root. Single pre-5/7 blocker visible in the plan's open-items list: project code needs to be pushed to a real git remote before the OptiPlex can clone. Repo `claude-wolfgang/TraxisAccountingIngest` mentioned in earlier remote-routine setup but not verified to exist.

**Files modified/created (all in `34. Chrome Web Store Ops Watcher/`):**
- `cws_watcher.py` — `load_env()` rewritten to use script-relative paths
- `setup_schedule.bat` — portable pythonw discovery; pauses on success/error so output is visible
- `test_run.bat` — new, double-click verification helper
- `diagnose.bat` — new, captures output to file for cross-PC debug
- `enable_ssh_server.bat` — new, one-time SSH server enable + key authorization
- `.gitignore` — added `diagnose_output.txt`

**Key decisions:**
- Own thin GraphClient pattern survives unchanged — env discovery was the only bug.
- SSH for Claude → .71 (and eventually → traxis-srv-01); Tailscale for Wolfgang's own off-LAN access. Both stay useful.
- `enable_ssh_server.bat` parked in P34 folder for now; should migrate to a general ops folder when one exists (it's shop-wide infrastructure, not P34-specific).

**Status:** P34 watcher running every 4h on .71 (next: 22:00 UTC). Heartbeat fresh. Cloud verdict-check agent unchanged (fires Tue 5 PM CDT). SSH channel permanent — future cross-PC plumbing becomes a one-liner.

---

### P34: CWS Ops Watcher — Phase 1 + Phase 2 implementation, plus cloud verdict-check routine

**Date:** 2026-05-02 (session 2 continued)

**Task:** Implement P34 from spec to scheduled production. Watcher polls the M365 mailbox via Microsoft Graph for CWS lifecycle events, classifies them, logs to SQLite, writes flag files for high-priority events. Phase 2 wires it into Windows Task Scheduler with a heartbeat file.

**What was done:**

1. **Phase 1 — watcher implementation (commit c47ad9b)**
   - `cws_watcher.py` (~210 lines): thin Microsoft Graph client (app-only OAuth, same shape as P27's), classifier with priority levels (critical / high / low / info), SQLite event log idempotent on Graph `message_id`, flag file writer for high+critical priority.
   - Architectural deviation from spec: P34 ships its own ~30-line GraphClient instead of importing from P27. Reason: P27's `accounting_ingest.py` is a 2549-line monolith that pulls `tkinter` and `anthropic` on import — would balloon P34 startup. The shared resource is `.traxis.env` credentials, not the code. Documented in P34 CLAUDE.md with the trigger condition for promoting to a `shared/graph_client.py` (third consumer appears).
   - Smoke test against `tom@traxismfg.com` over 90 days: found 4 CWS-sender events including both prior P30 rejection emails, correctly classified `high / submission_rejected`. DB seeded.

2. **Phase 2 — scheduling + heartbeat (commit 4bf0ea4)**
   - `cws_watcher.py` now writes `last_run.json` heartbeat each run: timestamp, mailbox, message counts, open flag-file counts.
   - `setup_schedule.bat` — idempotent installer for Windows Task Scheduler entry `Traxis - CWS Ops Watcher`. Runs `pythonw.exe cws_watcher.py` every 4 hours starting 06:00. No console flash (per P32 lesson — direct pythonw.exe, no .bat wrapper). No admin required.
   - End-to-end validated: `schtasks /Run` kicked off pythonw.exe silently, heartbeat refreshed within ~30s.

3. **Cloud verdict-check remote agent**
   - Created one-time scheduled remote agent (id `trig_017DycuAAU5iFZmGWbyaVTn8`) firing 2026-05-05 22:00 UTC (Tue 5 PM CDT). It will WebFetch the public CWS detail page for the P30 extension, classify the verdict by published version string (1.5.2 = approved, 1.5.1 = inconclusive, 404 = suspended), and PushNotification Wolfgang.
   - Cloud agent is independent of the local watcher — both will catch the verdict when Google reviews v1.5.2. Belt-and-suspenders.
   - New environment `Default` (id `env_016KpgnJbrqXfSzekZHLLJcN`) auto-created during routine setup since none existed.

**Files modified/created (all in `34. Chrome Web Store Ops Watcher/`):**
- `cws_watcher.py` — new, full implementation
- `requirements.txt` — new (just `requests`)
- `setup_schedule.bat` — new, Task Scheduler installer
- `CLAUDE.md` — updated to Phase 2 status, deviation documented, Phase 3 backlog added
- `.gitignore` — covers `cws_events.db`, `flags/`, `last_run.json`

**Key decisions:**
- Own thin GraphClient, not direct import of P27's. Trigger to refactor: third Graph consumer.
- Heartbeat file (`last_run.json`) instead of HTTP `/health` endpoint, since P34 is a periodic batch task not a long-running service. Phase 3 will wire Overseer to read it as a file-freshness validator.
- Cloud verdict-check agent uses public CWS detail URL — no inbox access needed, no GitHub or MCP needed.

**Status:** P34 is live. Watcher running every 4 hours on MainPC (next scheduled run today 6 PM, then 10 PM, etc.). Cloud verdict-check routine armed for Tue 5 PM CDT. Phase 3 backlog (Overseer config wiring for file-freshness validator, Telegram routing, auto-clear logic, multi-extension reporting) deferred.

---

### P30: Label Printer Extension — CWS rejection fix + P34 spec drafted

**Date:** 2026-05-02 (session 2)

**Task:** Resolve second CWS rejection of Traxis Label Printer; draft P34 spec for ongoing CWS lifecycle monitoring.

**What was done:**

1. **P30 fix** — Google rejected v1.5.1 for unused `activeTab` permission. Confirmed via grep that `activeTab` was declared in `manifest.json:11` only; no `chrome.tabs.*` or `chrome.action.*` calls anywhere. Content scripts inject via static `content_scripts` (no permission needed) and the service worker only does `fetch()` to the local print service. Removed the permission and bumped version 1.5.1 → 1.5.2. Rebuilt `deployment/traxis-label-printer.zip` (42 KB). Wolfgang submitted the new build to CWS Developer Dashboard during the session.

2. **P34 spec** — Drafted `34. Chrome Web Store Ops Watcher/CLAUDE.md`. Decision: own project (not subset of P27) because domain, stakeholders, and failure consequences differ — P27 is accounting; P34 is dev-ops for the extension fleet (P30 live, P14 + P18 upcoming). Shared piece is just Microsoft Graph client (P27 already integrates Graph for vendor email body extraction). Starts with direct import of P27's GraphClient; promote to shared module only if a third consumer appears.

**Files modified:**
- `30. Material Label Extension/traxis-material-label/manifest.json` — removed activeTab, bumped to 1.5.2
- `30. Material Label Extension/deployment/traxis-label-printer.zip` — rebuilt
- `34. Chrome Web Store Ops Watcher/CLAUDE.md` — new spec file

**Key decisions:**
- P30 fix: vestigial permission only; no code changes needed. Host permissions remain (actively used).
- P34: own project, not P27 subset. Direct import of P27 Graph client initially.
- New feedback memory saved: audit MV3 manifest permissions against actual code use before every CWS submission (second rejection in this pattern).

**Status:** P30 v1.5.2 submitted to CWS, awaiting Google review. P34 spec complete; implementation deferred to next session per Path A (clean separation of close commit from build commit).

---

### P17: COTS Crib Kiosk — Search upgrade matching photo uploader pattern

**Date:** 2026-05-02 (session crossed midnight from 2026-05-01)

**Task:** Apply the photo uploader's better search mechanism to the COTS kiosk browse page.

**What was done:**

1. **Backend rewrite** — Replaced server-side ProShop `COTSQuery` filter (which only matched the `aka` field via `contains`) with a fetch-all + cache + Python-filter pattern adapted from P31. Added 120s TTL cache, `_fetch_all_cots()` method (pageSize 1000), and rewrote `get_cots_items()` to do Python-side substring matching across 7 fields (otsId, number, aka, description, location, type, subclass) with digit-only matching for number lookups.

2. **Live debounced search** — Added 350ms debounced `input` event listener to `browse.js` so search updates as you type. Enter key still works for immediate search.

3. **Cache busting** — Added `?v=20260501-livesearch` query string to `browse.js` reference in `browse.html` so kiosk Chrome doesn't serve stale JS.

**Files modified:**
- `17. COTS - Tools Crib Kiosk/cots-kiosk/proshop_client.py` — Added `_get_cached`/`_set_cached` helpers, `_fetch_all_cots()`, rewrote `get_cots_items()` for local search
- `17. COTS - Tools Crib Kiosk/cots-kiosk/static/browse.js` — Added debounced input event listener
- `17. COTS - Tools Crib Kiosk/cots-kiosk/templates/browse.html` — Cache-bust query string on browse.js

**Key decisions:**
- Same pattern as P31 photo uploader (fetch all + Python filter), since ProShop's `StringQueryInput` only supports `exactly`, `in`, `not` — no real substring/multi-field search.
- Cache TTL of 120s matches P31; balances API load against staleness.
- Frontend pagination still works against the locally-filtered set.

**Status:** Service deployed via Dropbox sync to MainPC (.71). `__pycache__` regenerated at 15:29 confirms backend reloaded after Overseer restart. Cache-bust on `browse.html` ensures the kiosk Chrome picks up new `browse.js` on next page load. User reported the new behavior wasn't visible during testing — most likely browser cache (now addressed by cache-bust); to verify on next session.

---

## 2026-05-01

### P32: Breakeven Dashboard — Fix CMD window flash from scheduled task

**Date:** 2026-05-01 (session 3)

**Task:** Diagnose and fix a CMD window briefly popping up on the desktop from a background service.

**What was done:**

1. **Diagnosed root cause** — Audited all running Python processes, the overseer service tree, and Windows scheduled tasks. Found that "Traxis - FOCAS Runtime Aggregator" scheduled task was running `run_aggregator.bat` (which calls `python.exe`) directly every 15 minutes. Unlike the FASData tasks which use `wscript.exe` + `.vbs` wrappers, this one had no window suppression.

2. **Fixed scheduled task** — Updated the task to run `pythonw.exe focas_runtime_aggregator.py --history 4` directly instead of going through the `.bat` file. `pythonw.exe` has no console window, eliminating the flash entirely.

3. **Audit findings** — All other Python subprocess calls in the codebase (overseer, agent_scheduler, service_wrapper) correctly use `CREATE_NO_WINDOW` flags. The three FASData scheduled tasks correctly use `wscript.exe` + VBS wrappers. The `Proshop Scheduling Probe` task is a legacy one-time task from Feb 2026 (not repeating, not causing flashes).

**Files modified:**
- Windows scheduled task "Traxis - FOCAS Runtime Aggregator" — changed Task To Run from `.bat` to direct `pythonw.exe` invocation

**Key decisions:**
- Used `pythonw.exe` directly in the scheduled task rather than adding a VBS wrapper — simpler approach, no intermediary files needed
- Left `run_aggregator.bat` on disk for manual use if needed

**Status:** Fix applied. Next task execution at ~5:16 PM will verify no CMD flash.

---

### P31: Photo Upload Service — Live tablet testing, entity expansion, NCR support

**Date:** 2026-05-01 (session 2)

**Task:** Live test photo upload service on Samsung tablet in shop, fix issues found during testing, expand entity type support, add new features.

**What was done:**

1. **Flexible WO search** — Added `_normalize_wo()` method that strips dashes and leading zeros so "26120" matches "26-0120".

2. **QR scanning reliability** — Three-layer decode: BarcodeDetector (native Chrome) → jsQR (with downscaling to 1500px max) → pyzbar server-side fallback via `/api/qr-decode` endpoint. Fixed equipment QR parsing for two-segment URLs (`/equipment/GT/GT094`).

3. **All entity types wired up** — Added GraphQL queries and search for fixtures (`fixtureNumber`), equipment (`equipmentNumber` with flexible digit matching), COTS (`number` with digit-only matching), and NCRs (`ncrRefNumber`). Required adding OAuth scopes `fixtures:r`, `ots:r`, `equipment:r`, `nonconformancereports:r` to client BA16-EFAF-B154.

4. **Part operations** — Parts now show operation selection (like work orders) using the `operations` field on Part type. Upload worker routes part photos to written description pages using same URL pattern as WOs.

5. **Equipment photo upload end-to-end** — Verified GT094 (granite table) photo uploaded to ProShop successfully via Selenium (HTTP 200).

6. **Claude photo category** — New "Claude" button saves photos locally to `data/photos/claude/` (Dropbox-synced) with `local_only` status — no ProShop upload. Added global Claude Code permission to read this folder from any session.

7. **Suggestion button** — "Suggest" button on home screen saves operator feedback to `31. Photo Upload Service/suggestions.md`.

8. **Tablet kiosk setup** — Fully Kiosk Browser for Android configured as locked-down kiosk pointing to the service. PWA manifest and icons (orange/black PS + camera) created.

9. **Photo-to-print** — Read handwritten setup procedure photo via Claude vision, transcribed to formatted text, printed to Brother MFC-L2710DW via PowerShell `Out-Printer`.

10. **UI polish** — 3-column grid, larger buttons (24px padding, 100px min-height), inline QR camera button next to search, "Go" button to dismiss keyboard, all back buttons reset to home.

**Files modified:**
- `31. Photo Upload Service/photo-uploader/app.py` — Added `/api/qr-decode`, `/api/suggest`, part operations support, NCR+claude valid types
- `31. Photo Upload Service/photo-uploader/proshop_client.py` — Added fixture, equipment, COTS, NCR, part detail/ops search methods
- `31. Photo Upload Service/photo-uploader/upload_worker.py` — Extended to handle part and equipment uploads via proshop_url
- `31. Photo Upload Service/photo-uploader/static/photo.js` — Three-layer QR decode, part/NCR operation selection, Claude direct-to-capture, suggestion submit, flexible search
- `31. Photo Upload Service/photo-uploader/static/style.css` — 3-column grid, larger buttons, QR and Go button styles
- `31. Photo Upload Service/photo-uploader/templates/home.html` — NCR, Claude, Suggest buttons; suggestion step; PWA meta tags; inline QR camera
- `31. Photo Upload Service/photo-uploader/templates/base.html` — PWA manifest, external link blocker, back button disabler
- `31. Photo Upload Service/photo-uploader/static/manifest.json` — PWA manifest (new)
- `31. Photo Upload Service/photo-uploader/static/icon-192.png`, `icon-512.png` — App icons (new)
- `1. Proshop Automations/.traxis.env` — Added fixtures:r, ots:r, equipment:r, nonconformancereports:r scopes
- `~/.claude/settings.json` — Global read permission for claude photos folder

**Key decisions:**
- Port 5003 had a ghost TCP socket from prior session; ran on 5004 temporarily (will revert to 5003 on next restart)
- Claude photos are local-only (no ProShop upload) — stored in Dropbox for Claude Code access
- Parts use same written description upload pattern as work orders (same URL template)
- The Fearless Emu is developing the customer portal (P3) — F4 Labs test client in ProShop is his

**Status:** Service running on port 5004. All 9 entity types functional (work order, tool, equipment, part, fixture, COTS, NCR, Claude, QR scan). Part and equipment uploads verified end-to-end. NCR search working, upload untested. Tablet configured as kiosk via Fully Kiosk Browser.

---

### P31: BLE Proximity Worker Tracking — Multi-slot beacon fix + walk test

**Date:** 2026-05-01

**Task:** Fix proximity logger to recognize all Feasycom iBeacon broadcast slots, backfill historical data, and validate with walk test.

**What was done:**

1. **Fixed multi-slot beacon identification** — Feasycom tags broadcast 2-3 iBeacon slots simultaneously with different major numbers. Updated `proximity_logger.py` to map all slots: Tag-A (39475, 40604, 10065), Tag-B (35540, 60285, 10065). Added MAC-based disambiguation for shared major 10065.

2. **Filtered ESP32 self-detection** — Gateways detect each other as iBeacon majors 72, 116, 252. Added IGNORE_MAJORS filter to skip these, deleted 125 junk rows from DB.

3. **Backfilled 12,628 historical records** — Updated tag_name from NULL to correct tag for majors 35540 (Tag-B), 40604 (Tag-A), 60285 (Tag-B). DB now has 48,556 clean readings, zero NULLs.

4. **Walk test M8→M1→M2** — Successfully identified the correct machine visit order from RSSI data using strongest-gateway-wins analysis in 15-second windows. Feasycom tags at 2.5dB TX power show only 3-15 dB contrast between gateways — workable but marginal. MOKOSmart B2 badges expected to improve this significantly.

5. **Updated CLAUDE.md** — Documented all multi-slot major numbers per tag, gateway self-detection filtering, walk test results, and updated interfaces.

**Files modified:**
- `31. BLE Proximity Worker Tracking/proximity_logger.py` — Multi-slot beacon mapping, MAC disambiguation, IGNORE_MAJORS filter
- `31. BLE Proximity Worker Tracking/proximity.db` — Backfilled 12,628 records, deleted 125 ESP32 self-detection rows
- `31. BLE Proximity Worker Tracking/CLAUDE.md` — Updated hardware, technical notes, status, interfaces

**Key decisions:**
- "Strongest gateway wins" relative ranking is more reliable than absolute RSSI thresholds for machine assignment
- Need debounce logic (30-60s sustained lead) before switching assignments in production
- Feasycom tags are marginal for time tracking — MOKOSmart B2 badges are the real test

**Status:** Logger running as background service, all three gateways reporting, beacon identification complete. Awaiting MOKOSmart B2 badges for production-viable signal strength.

---

## 2026-04-30 (session 3)

### P25/P1: CMD Window Fix + Dedicated Server Plan

**Date:** 2026-04-30

**Task:** Diagnose and fix CMD window popping up every 15-30 minutes on collector PC (10.1.1.71). Plan dedicated server to replace workstation-hosted services.

**What was done:**

1. **Root cause found** — `agent_scheduler.py` runs `check_reminders.py` every 15 minutes via `subprocess.run()` without `CREATE_NO_WINDOW` flag, causing a visible CMD flash each time. Same issue in `run_audit.py` (60min) and `scan_projects.py` (daily).

2. **Fixed 4 subprocess calls** across 3 files:
   - `25. Agent Exploration/agent_scheduler.py` — Added `creationflags=subprocess.CREATE_NO_WINDOW` to `_run_task()`
   - `25. Agent Exploration/service_wrapper.py` — Added flag to PowerShell env-var lookup and Overseer Popen launch
   - `25. Agent Exploration/config.py` — Added flag to PowerShell env-var lookup

3. **Switched TelegramBot + AgentScheduler to pythonw.exe** — Both were the only services using `PYTHON_EXE` (console python) instead of `PYTHONW_EXE` in Overseer config. Changed `start_cmd` for both in `overseer.py`.

4. **Expanded dedicated server plan** — Updated `shoestring_server_plan.md` with services migration (Overseer + 13 services off .71), git-based deployment replacing Dropbox, phased setup sequence, and Dropbox replacement matrix.

5. **Hardware ordered** — Dell OptiPlex 7060 Micro (on hand) + Crucial BX500 2TB SSD ($189) + WD Elements SE 2TB USB ($108) + APC BE600M1 UPS ($86) + Cat6 cable ($8) = ~$401. ETA 2026-05-07.

**Files modified:**
- `25. Agent Exploration/agent_scheduler.py` — CREATE_NO_WINDOW on subprocess.run
- `25. Agent Exploration/service_wrapper.py` — CREATE_NO_WINDOW on two subprocess calls
- `25. Agent Exploration/config.py` — CREATE_NO_WINDOW on subprocess.run
- `1. Proshop Automations/Overseer/overseer.py` — TelegramBot + AgentScheduler switched to PYTHONW_EXE
- `E:\Downloads\shoestring_server_plan.md` — Expanded with migration phases, real prices, purchase list

**Key decisions:**
- Internal 2TB SSD for live services + 2TB USB portable for nightly backup (robocopy mirror)
- Git-based deployment replaces Dropbox for code; Dropbox stays for shared files (NC Programs, scans)
- Telegram `/deploy` command as initial deploy trigger, scheduled poll later
- NSSM wraps Overseer as Windows Service on new box

**Status:** Code fixes complete, syncing via Dropbox. Hardware arriving 2026-05-07. Server setup is a single afternoon once parts arrive.

---

## 2026-04-30 (session 2)

### P33: Tool Library Updater — Interactive menu + fill more ProShop fields

**Date:** 2026-04-30

**Task:** Fix double-click launching (window closes instantly) and fix tool create not populating enough fields on ProShop tool page.

**What was done:**

1. **Interactive menu** (`tool_update.py`) — Added `interactive_menu()` function triggered when no CLI arguments are passed. Presents numbered menu (Inspect, Create, Find VPO, Preview, Update, Scrape, Download Image). Collects required inputs interactively. Window stays open with "Press Enter to exit" after completion. Allows double-clicking the .py file on Windows.

2. **More ProShop fields populated** — AI search prompt (`ai_search.py`) now also requests `size` (display size: fraction, wire gauge, thread size), `fluteType` (straight/RH spiral/LH spiral), `grade` (manufacturer substrate code), `productLine` (manufacturer product line name), and `brand.cost` (unit price from distributor sites). All new fields wired through `_build_create_data` to ProShop `addTool` mutation.

3. **Brand cost** — AI now looks for pricing on distributor sites. If found, cost is included in the `approvedBrands` entry sent to ProShop.

4. **Default quantity** — `quantity` now defaults to `0` instead of being omitted, so the field isn't blank on ProShop.

5. **Grade/product line in descriptions** — AI-returned `grade` and `productLine` are injected as `_grade` and `_product_line` metadata for the description builder, producing richer descriptions (e.g., "KENNA GODRILL KC7325").

**Files modified:**
- `33. Tool Library Updater VPO Writer/tool_update.py` — Interactive menu, new field mapping, default quantity
- `33. Tool Library Updater VPO Writer/ai_search.py` — Expanded AI prompt with 5 new spec fields + brand cost
- `33. Tool Library Updater VPO Writer/CLAUDE.md` — Documented interactive menu usage

**Key decisions:**
- Interactive menu rather than .bat launcher — keeps everything in one file
- AI asked to look for pricing on distributor sites (best-effort, may return null)
- Quantity defaults to 0 rather than omitting (ProShop page shows the field populated)

**Status:** Complete.

---

## 2026-04-30

### P30: Traxis Label Printer Extension — Tool label fix + CWS privacy policy

**Date:** 2026-04-30

**Task:** Fix tool label data capture (was returning blank description/location) and resolve CWS rejection due to missing privacy policy URL.

**What was done:**

1. **Diagnosed tool label failure** — Compared working COTS/material labels against broken tool label. Root cause: tool content script relied solely on iframe `contentDocument` scraping, which fails silently when iframes are cross-origin-blocked or `data-display-name` attributes don't match expected names. No fallback existed.

2. **Rewrote tool-content.js with three-layer data cascade** (matching material label pattern):
   - Layer 1: Iframe scraping (kept, improved — widened field name matching, added input name/id scan, added cross-origin diagnostic logging)
   - Layer 2: Top-level DOM scraping (new — scans label/value pairs for Description/Location)
   - Layer 3: GraphQL API fallback (new — queries `tools(filter: { toolNumber: [...] })` using session cookie)
   - `gatherData()` merges results: iframe → DOM → API, uses first source that returns data

3. **Created privacy policy for CWS submission** — Google rejected the extension because the privacy policy URL didn't resolve. Created `claude-wolfgang/traxis-privacy` GitHub repo with privacy policy HTML page. Enabled GitHub Pages — live at `https://claude-wolfgang.github.io/traxis-privacy/`. Wolfgang resubmitted CWS listing with the new URL.

4. **Built v1.5.1 submission ZIP** — `deployment/traxis-label-printer.zip` ready to upload to CWS Developer Dashboard once review passes.

**Files modified:**
- `30. Material Label Extension/traxis-material-label/src/tool-content.js` — Three-layer data gathering (iframe + DOM + API)
- `30. Material Label Extension/traxis-material-label/manifest.json` — Version 1.5.0 → 1.5.1
- `30. Material Label Extension/deployment/traxis-label-printer.zip` — Rebuilt for v1.5.1
- `30. Material Label Extension/CLAUDE.md` — Removed "IN PROGRESS" from tool label, updated architecture notes

**External:**
- GitHub repo `claude-wolfgang/traxis-privacy` created with privacy policy page (GitHub Pages)

**Key decisions:**
- GraphQL API fallback uses the user's existing ProShop session cookie (same as material/equipment labels) — no OAuth client needed in the extension
- Privacy policy hosted on GitHub Pages rather than company domain — simpler, no infrastructure dependency

**Status:** Tool label working. CWS resubmitted with privacy policy URL, awaiting Google approval. v1.5.1 ZIP ready to upload post-approval.

---

### P33: Tool Auto-Creator — AI-powered tool creation from EDP/catalog number

**Date:** 2026-04-30

**Task:** Build a reusable CLI tool that creates new ProShop tool records from a manufacturer EDP or catalog number, using AI-powered web search to extract specs and classify tool type.

**What was done:**

1. **`ai_search.py` (NEW)** — AI-powered spec lookup using Anthropic API + `web_search_20250305` server-side tool. Claude Haiku searches distributor sites (MSC, Grainger, Penn Tool, etc.), classifies tool type (14 types supported), extracts structured JSON specs. Includes retry logic for JSON parse failures. Cost: ~$0.02/lookup.

2. **`proshop_tools.py` (MODIFIED)** — Added `add_tool()` mutation wrapper and `get_anthropic_key()` helper. Expanded `TOOL_QUERY_FIELDS` with insert-specific fields (insertInscribedCircle, insertShape, insertThickness, numberOfCuttingCorners, pitch, fullProfile, cornerRadius, quantity, location).

3. **`description_format.py` (MODIFIED)** — Added enum translation dicts (MATERIAL_MAP, INSCRIBED_CIRCLE_MAP, INSERT_SHAPE_MAP) and new description formatters (format_endmill_description, format_insert_description, format_tap_description, build_description router). Fixed drill formatter crash on None flute length. Fixed insert description to use catalog number instead of verbose AI hint.

4. **`tool_update.py` (MODIFIED)** — Added `create` subcommand with full workflow: AI search → tool group mapping → field mapping → preview → confirm → addTool. Supports `--mfg`, `--edp`, `--catalog`, `--qty`, `--location`, `--group`, `--specs-json`, `--confirm`, `--json`.

5. **`CLAUDE.md` (UPDATED)** — Documented create subcommand, AI search section, updated interfaces.

**Files modified:** ai_search.py (new), proshop_tools.py, description_format.py, tool_update.py, CLAUDE.md

**Key decisions:**
- Used Anthropic web_search server-side tool instead of direct scraping (bypasses Cloudflare, zero new dependencies)
- AI determines tool type → maps to ProShop toolGroupLetter automatically
- Catalog numbers work much better than internal webshop EDP numbers for web search
- Description always uses shop-convention formatters, never raw AI description_hint

**Bugs fixed:**
- Drill formatter TypeError on None flute_length_inch
- Description used verbose AI sentence instead of shop-convention format

**Tested:**
- ISCAR 16ERB 1.25 ISO IC908 → insert, "16ERB 1.25 ISO IC908 ISCAR"
- Kennametal B041A03455CPG → drill, "9/64" DR 2FL 13/32" F/L KENNA"
- Both produce correct ProShop enum values and AddToolInput data

**Status:** Complete. Ready for live use with `--confirm` flag.

---

### Multi-project: Git housekeeping — commit accumulated drift

**Date:** 2026-04-30

**Task:** Clean up working tree with uncommitted changes spanning multiple prior sessions.

**What was done:**

1. **P24 retirement** (`4cdbf9e`) — Moved `24. Digital Help For Rene/` to `24. Digital Help For Rene - Retired/`. Git detected as renames.
2. **P33 rename** (`637cde6`) — Moved `33. Tool Library Updater/` to `33. Tool Library Updater VPO Writer/`. Includes new `ai_search.py` and updated `tool_update.py`/`proshop_tools.py`.
3. **P32 breakeven** (`75f97ad`) — Runtime snapshot data update + new deployment docs (`DEPLOYMENT.md`, `FOCAS_SCHEMA_NOTES.md`, `config.example.json`, `config.json`, `requirements.txt`, `run_aggregator.bat`).
4. **P27 misc** (`df3dbc1`) — Reference docs (Rene reports moved to P27 docs/), tool receiving label PNGs, burst groups JSON, investigation notes (`acceptNewRecord` inquiry, QBO sync problem).
5. **Housekeeping** (`b35e74b`) — Deleted stale `All Projects Monitoring/` session logs, `Fusion_360_API_Reference.md`, `PROSHOP_API_REFERENCE.md`. Added P28 `wo_invoiced_today.md`. Updated P1 ProgrammingTimer logs.
6. **P1 gitignore** (`be1589d`) — Added `.gitignore` to `ProShopBridge/logs/` to exclude failure screenshot PNGs and log files from tracking.

**Files modified:** 24 files across 7 commits (see commit messages above)

**Key decisions:**
- ProShopBridge failure screenshots gitignored rather than tracked (diagnostic, will accumulate)
- P24 docs copied to both Retired folder and P27 docs/ (different versions — P27 has updated copies)
- P32 config.json committed (contains paths only, no secrets)

**Status:** Working tree clean. No remaining uncommitted changes.

---

## 2026-04-29

### P30: Traxis Label Printer Extension — Tool Label Support (v1.5.0, IN PROGRESS)

**Date:** 2026-04-29

**Task:** Add print label button to ProShop tool pages (`/procnc/tools/*`). The extension had content scripts for WO, COTS, equipment, box, and user pages but never supported tool pages.

**What was done:**

1. **Diagnostics** — Verified print service at 10.1.1.242:5002 is healthy (printer available, 16+ days uptime). Sent test payload through API successfully. Extension code and all existing label types are clean.

2. **New files created:**
   - `tool-content.js` — Content script for tool pages. Tool ID from URL (`/procnc/tools/GROUP/ID`). Scrapes description and location from iframe `data-display-name` fields. Orange "Print Tool Label" button at top center.
   - `tool-label-generator.js` — Canvas renderer: QR code (encodes tool page URL), tool # (bold 30px), description (20px, word-wrapped), location (14px).

3. **Updated files:**
   - `manifest.json` — v1.4.0 → v1.5.0, added content_scripts entry for `/procnc/tools/*`, added icon references
   - `content.css` — Added orange `.traxis-label-btn--tool` variant

4. **ProShop tool page DOM discovery** — Tool pages render form inputs inside iframes. Top-level `document.querySelector` cannot reach `data-display-name` attributes. The debug DOM dump confirmed: field labels (Tool #, Location, etc.) exist as `.plainheader` cells in the main document, but values are in iframe inputs. Iframes are accessible (same-origin). Final approach reads `data-display-name` fields directly from iframe contentDocument.

5. **Unresolved:** The correct `data-display-name` value for the tool description field is not yet confirmed. Current code tries Header, Description, and Tool Name. The debug logging in the current build will dump all iframe field names on next test — that will identify the correct field.

**Files modified:**
- `30. Material Label Extension/traxis-material-label/manifest.json` — v1.5.0
- `30. Material Label Extension/traxis-material-label/src/tool-content.js` — NEW
- `30. Material Label Extension/traxis-material-label/src/tool-label-generator.js` — NEW
- `30. Material Label Extension/traxis-material-label/src/content.css` — Orange tool variant

**Key decisions:**
- Tool ID always from URL (not DOM) — ProShop tool URLs are reliable (`/procnc/tools/GROUP/ID`)
- QR code encodes full ProShop tool URL (same pattern as equipment/COTS labels)
- Orange button color to distinguish from other label types
- Iframe-based scraping required — ProShop tool pages differ from other page types that use flat DOM

**Status:** IN PROGRESS. Button injects and prints. Tool # and QR correct. Description and location scraping needs one more test cycle to confirm correct iframe field names.

---

### P27: Accounting Ingest — QBO Production, Email Body Extraction, Scheduler Concept (v1.4.0)

**Date:** 2026-04-29

**Task:** Activate QBO production API, add email body extraction for non-PDF bills, fix several GUI bugs, conceptualize scheduler + procurement loop, write architecture document v1.2.

**What was done:**

1. **QBO production activation** — Switched from sandbox to production. Used Intuit OAuth2 Playground redirect URI for token exchange (Intuit rejects localhost for production). Updated .traxis.env with production Client ID, Secret, Realm ID (123146014753554), and refresh token. Smoke-tested with a real vendor query.

2. **Email body extraction** — Added `get_body()` to GraphClient, `classify_html()` (Haiku) and `extract_html()` (Sonnet) to AIExtractor. Bills from Waste Management, CIMCO, UPS, Smart Air that arrive as email text (not PDF attachments) now get classified and extracted. Changed `get_recent_emails()` to 10-day lookback window.

3. **Duplicate email fix** — accounting@traxismfg.com forwards to tom@, causing every email to be processed twice. Removed WHITELISTED_INTERNAL, now skips all @traxismfg.com senders. Added intuit.com domains to BLOCKED_DOMAINS to prevent QBO notification emails from creating circular entries.

4. **Vendor selection bug fix** — Programmatic `set()` on contact search var triggered repeated listbox rebuilds, clearing auto-selection. Fixed with 400ms debounce via `after()`, synchronous search in `_load_record()`, moved listbox bind to init.

5. **Label printing gated** — Auto-print was firing on restart (empty `_seen` set reprocessed everything). Removed auto-print, added manual "Print Labels" button to review panel.

6. **Cert PDF filing** — Added `_save_cert_for_vpo()`: copies source PDF to `Accounting Inbox/Certs/VPO-XXXXXX/` after successful packing slip upload.

7. **Architecture document v1.2** — Evaluated TRAXIS_QBO_AUTOMATION_ARCHITECTURE.md against ecosystem, added existing-system context (v1.1), then added Scheduler + Procurement Loop concept (v1.2): two-view model (Floor: 9 machines, Horizon: planning punch list), closed-loop procurement cycle, PixiJS/Phaser UI notes, 5-phase implementation sequence.

**Files modified:**
- `27. Accounting Ingest/accounting_ingest.py` — v1.3.0 → v1.4.0 (all changes above)
- `27. Accounting Ingest/qbo_auth.py` — Rewrote for production OAuth flow
- `27. Accounting Ingest/CLAUDE.md` — Updated interfaces for v1.4.0
- `1. Proshop Automations/.traxis.env` — QBO production credentials
- `TRAXIS_QBO_AUTOMATION_ARCHITECTURE.md` — v1.0 → v1.2
- `TRAXIS_ECOSYSTEM.md` — Updated P27 entry and interface map

**Key decisions:**
- QBO production uses Intuit Playground redirect URI (not localhost) — Intuit requires HTTPS for production
- Email body extraction uses Haiku for classification (fast/cheap) and Sonnet for extraction (accurate)
- Label printing is manual-only to prevent unsupervised printing on restart
- auth_010 customer PO permission is permanently blocked — won't pursue API workaround
- Scheduler reconception deferred to Web Claude brainstorming session

**Status:** v1.4.0 complete. QBO production live. Architecture doc v1.2 ready for Web Claude handoff.

---

### P31b: BLE Proximity Worker Tracking — ESP32 Gateway Deployment + Walk Test

**Date:** 2026-04-29

**Task:** Set up ESP32 gateways running ESPresense firmware for BLE-based worker tracking at CNC machines. Flash firmware, configure MQTT broker, calibrate zone thresholds via walk test, deploy gateways.

**What was done:**

1. **CP2102 driver install** — Windows couldn't find USB-serial driver. Downloaded CP210x_Universal_Windows_Driver from SiLabs, manual install via Device Manager. ESP32 appeared on COM3.

2. **ESPresense firmware flash** — Flashed 3x ESP32-WROOM-32 boards with ESPresense v4.0.6 via web flasher (web.esphome.io). Initial esptool attempts failed (wrong flash offset, missing bootloader). Web flasher includes bootloader+partition table+app in one go.

3. **Mosquitto MQTT broker** — Default config had duplicate listener entries causing bind errors. Created `mosquitto_clean.conf` (just `listener 1883` + `allow_anonymous true`). Runs in foreground via `start_mqtt_broker.bat`.

4. **Python test script** — Built `esp32_proximity_test.py`: subscribes to ESPresense MQTT, shows live RSSI/distance/zone for known beacons, logs to CSV. Fixed paho-mqtt v2 API (CallbackAPIVersion, on_connect signature), non-dict payload crash, room extraction from topic path.

5. **Beacon identification** — Original CLAUDE.md had wrong major numbers (60285, 40604). Correlated MACs via FeasyBeacon phone app to actual majors: Tag-A = 39475 (DC:0D:30:1F:90:A3), Tag-B = 10065 (DC:0D:30:48:30:3A). Configured TX power from -19.5dB to 2.5dB, interval to 1000ms.

6. **Walk test** — Systematic distance test (0, 2, 3, 6, 10, 15 ft) established zone thresholds: AT MACHINE >-45 dBm, NEARBY >-58, IN AREA >-66, FAR <-66. ESP32 gateway delivers ~50dB dynamic range over 0-15ft (vs ~4dB from the USB dongle).

7. **Gateway deployment** — M8 online at 10.1.1.38 (room=test_bench), reporting via MQTT. M1 and M2 flashed and physically deployed at machines but not yet connected to Wi-Fi — Google Fiber band steering forces ESP32 onto 5GHz which it can't use.

8. **MOKOSmart B2 badges ordered** — 10x B2 Bluetooth Smart Badge from mokosmart.com, Order #3765, $171.48 shipped ($12/badge + $51.48 express). Combined BLE iBeacon + NFC for proximity tracking and door entry.

**Files created:**
- `esp32_proximity_test.py` — Live MQTT proximity monitor + CSV logger
- `mosquitto_clean.conf` — Minimal MQTT broker config
- `start_mqtt_broker.bat` — Mosquitto foreground launcher
- `run_test.bat` — Test script wrapper
- `serial_read.py` — ESP32 serial debug monitor
- `ESP32_SETUP.md` — Step-by-step setup guide
- `proximity_log_*.csv` — Walk test data

**Files modified:**
- `CLAUDE.md` — Updated hardware, beacon IDs, zone thresholds, status, next steps

**Key decisions:**
- ESP32 + ESPresense over USB BLE dongle (50dB vs 4dB dynamic range)
- Identify beacons by iBeacon major/minor, not MAC (MACs rotate)
- Zone thresholds calibrated for tight machine layout (0-15ft useful range)
- MOKOSmart B2 for dual-purpose BLE+NFC badges (one card per worker)

**Status:** Phase 1 complete. M8 gateway proven. M1/M2 await 2.4GHz Wi-Fi SSID.

---

## 2026-04-28 / 2026-04-29

### P30: Traxis Label Printer Extension — Chrome Web Store Deployment

**Date:** 2026-04-28 → 2026-04-29

**Task:** Deploy the Traxis Label Printer Chrome extension to all shop floor computers automatically, replacing manual "Load unpacked" developer mode installs.

**What was done:**

1. **Self-hosted CRX approach (attempted, failed)** — Built a full deployment pipeline: `build.py` to pack extension as .crx via Chrome CLI, `host.py` HTTP server on 10.1.1.71:8484, `deploy_client.bat` to set Chrome `ExtensionInstallForcelist` registry policy on each shop PC. Extension ID computation from PEM had a bug (DER reconstruction mismatch) — fixed by extracting ID from CRX3 header instead. Diagnosed on shop PC via `diagnose.bat` — registry was correct and server was reachable, but Chrome refused: **"This computer is not detected as enterprise managed so policy can only automatically install extensions hosted on the Chrome Webstore."** Non-domain-joined PCs cannot force-install self-hosted extensions.

2. **Pivoted to Chrome Web Store (unlisted)** — Prepared extension for CWS submission:
   - Generated store icons (16/48/128px PNG) with Pillow
   - Added `icons` field to manifest.json
   - Bumped version 1.4.0 → 1.4.1
   - Created 1280x800 store screenshot
   - Packaged submission ZIP (`traxis-label-printer.zip`)
   - Created `deploy_client_cws.bat` — sets registry with CWS update URL, cleans up old self-hosted entries

3. **Wolfgang submitted extension to Chrome Web Store** — Registered CWS developer account ($5), filled privacy practices (single purpose, host permission justifications, activeTab justification), set publisher contact email, submitted for review. Awaiting approval.

4. **Ecosystem review** — Identified P14 (Workstation Display IPC) and P18 (ProShop Message Notifier) as two other MV3 Chrome extensions that can use the same CWS + policy deployment pipeline once P30 is proven.

**Files created:**
- `30. Material Label Extension/deployment/build.py` — CRX packer + ID extractor
- `30. Material Label Extension/deployment/host.py` — HTTP server for self-hosted approach
- `30. Material Label Extension/deployment/host.bat` — Server launcher
- `30. Material Label Extension/deployment/install_host.bat` — Server auto-start setup
- `30. Material Label Extension/deployment/deploy_client.bat` — Self-hosted registry deploy
- `30. Material Label Extension/deployment/deploy_client_cws.bat` — CWS registry deploy
- `30. Material Label Extension/deployment/remove_client.bat` — Uninstall from client
- `30. Material Label Extension/deployment/fix_client.bat` — Clean stale entries + restart Chrome
- `30. Material Label Extension/deployment/diagnose.bat` — Registry/server diagnostic
- `30. Material Label Extension/deployment/store_screenshot.png` — CWS listing image
- `30. Material Label Extension/deployment/traxis-label-printer.zip` — CWS submission package
- `30. Material Label Extension/deployment/signing_key.pem` — CRX signing key
- `30. Material Label Extension/deployment/traxis-label-printer.crx` — Packed extension
- `30. Material Label Extension/deployment/update_manifest.xml` — Self-hosted update manifest
- `30. Material Label Extension/deployment/extension_id.txt` — CRX extension ID
- `30. Material Label Extension/traxis-material-label/assets/icons/icon16.png`
- `30. Material Label Extension/traxis-material-label/assets/icons/icon48.png`
- `30. Material Label Extension/traxis-material-label/assets/icons/icon128.png`

**Files modified:**
- `30. Material Label Extension/traxis-material-label/manifest.json` (added icons, bumped to 1.4.1)

**Key decisions:**
- Self-hosted CRX requires enterprise-managed Chrome (domain-joined or cloud-managed) — not viable for standalone shop PCs
- Chrome Web Store unlisted is the right deployment model for Traxis shop floor extensions
- Same CWS + registry policy pattern will work for P14 and P18 when ready

**Status:** Extension submitted to Chrome Web Store, awaiting approval. Once approved, need extension ID to update `deploy_client_cws.bat`, then run on each shop PC.

---

## 2026-04-27

### P30: Traxis Label Printer Extension — Box Label + User Label (v1.4.0)

**Date:** 2026-04-27

**Task:** Add two new label types to the Chrome extension: Box Label (for shipping) and User Label (for employee pages). Fix form submission bug across all label buttons.

**What was done:**

1. **Box Label** — New blue button injected on WO pages in the Shipping row's "Certified To Run" cell. On click, prompts operator for box quantity ("Enter Qty of Parts in Box"), then generates and prints a label with QR code (full ProShop URL), WO#, Customer PO, Part Number, and Qty. All four text lines use uniform bold 24px font. Data sourced from DOM scraping + GraphQL API fallback (`customerPoNumber`).

2. **User Label** — New teal button injected on ProShop user pages (`/procnc/users/*`). Generates label with QR code (user page URL), Name, and User ID#. Scrapes name and ID from DOM with flexible matching (handles "Original User Id", first/last name fields, page header). Falls back to URL extraction for user ID.

3. **Form submission fix** — All five label buttons (material, COTS, equipment, box, user) now set `type="button"` to prevent ProShop's surrounding `<form>` from submitting when clicked. Previously, clicking any label button would clear the left panel/page state.

4. **Button placement iteration** — Box Label button moved through three positions: initially right-edge absolute (overlapped completion zone), then outside table (caused horizontal scrollbar), finally settled in the grey "Certified To Run" cell on the Shipping row.

**Files modified:**
- `30. Material Label Extension/traxis-material-label/src/box-content.js` (new)
- `30. Material Label Extension/traxis-material-label/src/box-label-generator.js` (new)
- `30. Material Label Extension/traxis-material-label/src/user-content.js` (new)
- `30. Material Label Extension/traxis-material-label/src/user-label-generator.js` (new)
- `30. Material Label Extension/traxis-material-label/manifest.json` (v1.3.0 → v1.4.0, two new content_scripts entries)
- `30. Material Label Extension/traxis-material-label/src/content.css` (blue box + teal user button styles)
- `30. Material Label Extension/traxis-material-label/src/content.js` (type="button" fix)
- `30. Material Label Extension/traxis-material-label/src/cots-content.js` (type="button" fix)
- `30. Material Label Extension/traxis-material-label/src/equipment-content.js` (type="button" fix)
- `30. Material Label Extension/CLAUDE.md` (updated for 5 label types)

**Key decisions:**
- Box Label QR encodes full ProShop URL (not `proshop://wo/` custom scheme) so phones can scan it
- Uniform font size on box label for readability
- User page URL pattern set to `/procnc/users/*` — needs verification if ProShop uses a different path

**Status:** Complete. Extension reloaded and Box Label tested on live WO page. User Label ready but untested (needs user page navigation).

---

## 2026-04-26

### P27: Accounting Ingest — Scan-burst-receive pipeline, tool labels, VPO receiving via API

**Date:** 2026-04-26

**Task:** Process two piles of scanned paper documents end-to-end: burst multi-page scans into individual documents, classify/extract, print tool receiving labels, and mark VPOs as received/released via API.

**What was done:**

1. **Scan→burst→classify pipeline** — Built and ran the full flow twice: scan pile to Pictures → copy to Scanned folder → Claude AI vision boundary detection (Sonnet, 108dpi) → PyMuPDF split → auto-rename with meaningful names. Pile 1: 11 pages → 6 documents. Pile 2: 6 pages → 4 documents.

2. **Manufacturing grouping rules** — Encoded domain knowledge into burst prompt: packing slips + mill certs = one group, shipping receipts belong with the packing slip they delivered (match by shipper = vendor).

3. **Tool receiving labels** — Created `tool_receiving_labels.py`: two-client API pattern (accounting reads VPO items, toolkiosk resolves tool library numbers), generates 24mm Brother PT-P700 labels (bold lib#, VPO#, order#), prints via P22 print service. Wired into `accounting_ingest.py` auto-trigger on PACKING_SLIP extraction.

4. **VPO receiving via API** — Discovered and used `updatePurchaseOrder` mutation to mark line items received+released:
   - VPO 263097 (Helical/Gorilla/Harvey tools): 3 lines received → Released
   - VPO 263091 (Hadco SS plate): 15 pcs received → Partially Released
   - VPO 263059 (R2/Dix Ti plate): releasedQty 40→100 → Complete

5. **Customer PO 208075 (Austin Pump)** — Created shell in ProShop manually (API blocked by auth_010 write permissions). Extracted all fields from scanned PO for manual fill. Confirmed updateCustomerPo is also blocked — customer POs are fully read-only via API.

6. **Pile 2 processing** — Burst into 4 docs: Shars inspection report (→TG151), Hadco packing slip #1709691 (acetal plate, VPO 263092), Austin Pump PO #206083, R2Sonic PO #PO115126. All POs created, VPO 263092 resolved.

7. **scan_relay.py** — Created relay script watching Pictures folder, moving stable PDFs to Scanned folder.

**Files created:**
- `27. Accounting Ingest/tool_receiving_labels.py`
- `27. Accounting Ingest/scan_relay.py`
- `27. Accounting Ingest/labels/` (generated label PNGs)

**Files modified:**
- `27. Accounting Ingest/accounting_ingest.py` (v1.2→v1.3: burst_pdf, _try_print_tool_labels, _process_one refactor)

**Key decisions:**
- Two-client API pattern for cross-scope data (accounting + toolkiosk)
- updatePurchaseOrder: `id` is a separate argument, not inside `data`
- Customer POs confirmed read-only via API (both create and update blocked by auth_010 permissions)
- One label per tool (copies=qty), not qty on label text

**Status:** Core pipeline working. VPO receiving automated for tools and materials. Customer POs remain manual.

**Open items:**
- auth_010 customer PO permissions — contact ProShop/Adion support
- scan_relay.py — not yet tested or set up for startup

---

### P30: Traxis Label Printer Extension — Add equipment label support

**Task:** Add a "Print Equipment Label" button to ProShop equipment pages, similar to existing WO material and COTS label buttons.

**What was done:**

1. **Created equipment label generator** (`equipment-label-generator.js`) — Renders 128px-tall auto-width label matching the material label design: QR code on left encoding the equipment page URL, 3 lines of text (Equipment # bold 36px, Tool Name 24px word-wrapped, Serial Number 14px), vertically centered.

2. **Created equipment content script** (`equipment-content.js`) — Injects red "Print Equipment Label" button on `/procnc/equipment/*` pages. Uses DOM scraping with `ownText` extraction and `[^a-z]*` icon prefix handling (matching material script pattern), plus GraphQL API fallback querying `equipments(tool: "...")`.

3. **Added red button styling** to `content.css` — `.traxis-label-btn--equipment` variant with red color scheme (#c62828) to visually distinguish from green WO/COTS buttons.

4. **Updated manifest.json** — Added equipment content script entry, bumped version to 1.3.0, updated description.

5. **Debugged DOM scraping** — Initial attempts using regex text matching and `data-display-name` attribute selectors failed due to ProShop's ⓘ icon elements polluting `textContent`. Final working approach uses `ownText` (direct text nodes only) + GraphQL API fallback, matching the proven material content script pattern.

**Files created:**
- `traxis-material-label/src/equipment-content.js`
- `traxis-material-label/src/equipment-label-generator.js`

**Files modified:**
- `traxis-material-label/manifest.json` (v1.2.1 → v1.3.0, added equipment entry)
- `traxis-material-label/src/content.css` (added red button variant)
- `30. Material Label Extension/CLAUDE.md` (updated for 3 page types)

**Key decisions:**
- Red button color for equipment to distinguish from green WO/COTS buttons
- Used same label layout as material labels (no supersample) rather than COTS layout
- GraphQL API fallback ensures labels work even if DOM scraping fails

**Status:** Complete — tested and printing correctly on equipment page TG151.

---

### P31: BLE Proximity Worker Tracking — Hardware shopping list for ESP32 gateways

**Task:** Review status of BLE proximity project and create an Amazon shopping list for the hardware needed to replace the inadequate Asus USB Bluetooth dongle.

**What was done:**

1. **Reviewed project state** — Identified that the last session (2026-04-16) concluded with the Asus USB dongle giving only ~4 dB RSSI spread across 0-50 ft, insufficient for proximity zone detection. Recommendation was to purchase dedicated BLE gateways.

2. **Created Amazon shopping list** — `AMAZON_SHOPPING_LIST.txt` with two phases:
   - Phase 1 (test kit, ~$30-50): 3x ESP32-WROOM-32 dev boards + USB cables/chargers to flash with ESPresense firmware and test against existing 2 Feasycom tags
   - Phase 2 (full deploy, ~$250-350): 12 more ESP32 boards, 10 more beacon badges, waterproof enclosures

3. **Wolfgang ordered** a 3-pack of ESP32-WROOM-32 dev boards from Amazon. Other cables/chargers already on hand.

**Files created:**
- `31. BLE Proximity Worker Tracking/AMAZON_SHOPPING_LIST.txt`

**Key decisions:**
- Going with ESP32 + ESPresense DIY route (~$280-400 total) instead of commercial gateways (~$1,200+)
- Phase 1 test with 3 boards before committing to full 14-machine deployment

**Status:** Waiting for ESP32 boards to arrive. Next session: flash ESPresense, test RSSI range with Feasycom tags.

---

### P1: Collector PC Network Fix — Bumped cable + static IP + firewall bat

**Task:** Diagnose why Overseer dashboard (port 8060) on Collector PC was unreachable from other LAN machines after a reboot.

**What was done:**

1. **Reviewed COLLECTOR_PC_FIREWALL_FIX.md** — Evaluated existing firewall fix doc for clarity, safety, and effectiveness. Identified gaps (no subnet scoping, risky full-firewall disable, incomplete port list).

2. **Rewrote open_traxis_firewall.bat** — New version opens ports 5000-8101 TCP + ICMP scoped to 10.1.1.0/24 LAN only. Creates a `TraxisFirewall` scheduled task (runs at startup as SYSTEM) to re-apply rules after GPO refresh. Supports `/apply` flag for silent scheduled task mode.

3. **Diagnosed actual root cause** — Firewall was a red herring. Disabled firewall, Overseer was running on port 8060, but ping from other machines failed. `ipconfig` showed all adapters as "Media disconnected." **Root cause: bumped ethernet cable.**

4. **Fixed DHCP drift** — After reconnecting cable, DHCP assigned .72 instead of .71. Windows Settings UI failed silently when setting static IP. Used `netsh interface ip set address "Ethernet 2" static 10.1.1.71 255.255.255.0 10.1.1.1` successfully.

5. **Updated documentation** — Rewrote COLLECTOR_PC_FIREWALL_FIX.md to reflect actual root cause and static IP config. Updated MEMORY.md with network troubleshooting lesson.

**Files modified:**
- `1. Proshop Automations/open_traxis_firewall.bat` — Complete rewrite with LAN scoping + scheduled task
- `1. Proshop Automations/COLLECTOR_PC_FIREWALL_FIX.md` — Rewritten to document actual root cause
- `MEMORY.md` — Added Collector PC Network section and physical-layer-first lesson

**Key decisions:**
- Static IP (10.1.1.71) set via netsh, not Windows Settings UI (which fails silently)
- Firewall bat uses single port range (5000-8101) instead of individual port rules
- Scheduled task survives GPO refresh by re-applying rules at startup

**Status:** Complete. Network restored, static IP set, firewall re-enabled with rules, scheduled task created.

---

## 2026-04-16

### P32: Breakeven Dashboard — Past week selector + sparkline navigation + UI polish

**Task:** Add ability to click a past week in the dashboard and see the same per-machine detail view (progress bars, expandable charts) for that week. Limit sparkline to 4 visible weeks with scroll arrows.

**What was done:**

1. **Aggregator: daily breakdown for history weeks** — `compute_daily_breakdown()` now accepts `full_week=True` parameter for completed past weeks (generates all 7 days). History loop in `--history` flag calls this for each past week, adding `"daily"` key to each history entry — making them structurally identical to the current week.

2. **Week selector via sparkline** — Clicking any sparkline bar selects that week. All dashboard components (progress bars, expandable machine charts, summary cards, pace calculations) re-render with the selected week's data. Completed weeks use full-week target (not fractional pace), show "Final" utilization, and hide live status dots.

3. **Sparkline navigation** — Limited sparkline to 4 visible bars with glass-styled left/right chevron arrows to scroll through weeks. Arrows auto-disable at boundaries.

4. **Actual hours on target card** — Added colored sub-value showing current/final weekly total on the "Target Hrs / Week" summary card.

5. **Removed cursor glow** — Disabled specular highlight on glass panels and pooling radial gradient on machine rows.

6. **T2 (YCM) data investigation** — Confirmed data collection is working correctly. T2's lower runtime (~12 hrs/wk) is real: machine was off all day Monday, and runs at 32-46% STRT vs M3's 59-72%. tool_number field is always NULL for T2 (YCM controller may not expose it via FOCAS).

**Files modified:**
- `32. Breakeven Dashboard/focas_runtime_aggregator.py` — `compute_daily_breakdown()` full_week param, history loop daily breakdown
- `32. Breakeven Dashboard/breakeven.html` — Week selection via sparkline, sparkline nav arrows, actual hours sub-value, cursor glow removal
- `32. Breakeven Dashboard/CLAUDE.md` — Created with Interfaces block

**Key decisions:**
- Week pills UI was added then removed in favor of sparkline-only selection (cleaner)
- Sparkline shows 4 weeks at a time (was showing all 5); arrows to scroll
- Past weeks use full target for % calculation (not pace-based)

**Status:** Complete. Aggregator re-run verified 4 history entries each with 7 daily entries.

---

### P15: ProShop API — Reply to Matt Carrico (Founder/Chief Architect)

**Task:** Evaluate Matt Carrico's response to our 5-item API change request, answer his questions, and draft a reply email. Matt is the founder and chief architect of ProShop ERP.

**What was done:**

1. **Parsed Matt's email** (.eml) — Identified his responses to all 5 items, extracted his specific questions and requests.

2. **Item 1 retest (read-only scope write bug)** — Re-ran the parts:r write test against the current build (April 16, 2026). Bug confirmed NOT fixed: a `parts:r` token successfully created Part `undefined-DELETE-ME-SCOPE-TEST` in production. Matt's theory (scope parameter omitted from request) ruled out — scope was explicitly included.

3. **Selenium workaround audit** — Documented the two specific ProShop pages requiring browser automation: Sequence Detail (G-Code Tool # field not writable via API, ProShop scrambles row order on API save) and Written Description (API-pushed content has display bug with legacyId="").

4. **Integration landscape inventory** — Cataloged all active integrations touching ProShop API: Fusion 360, Intuit QBO, FOCAS/CNC machines, Fusion-to-ProShop tool library sync, Make.com, Programming Timer, BLE Proximity.

5. **Drafted reply email** — Addresses all 5 items with fresh evidence for Item 1, specific Selenium workaround details for Item 2, acknowledgment of Recently Updated Records API for Item 3, concession on OAuth 2.0 point for Item 4, and agreement to share scope_permission_map.md for Item 5. Includes testing partnership offer.

**Files created:**
- `15. Proshop Replacement Research and Architecture/reply_to_matt_carrico.md` — Draft reply email with Web Claude conversion instructions
- `15. Proshop Replacement Research and Architecture/01_api_discovery/retest_item1_readonly_write.py` — Minimal retest script for read-only write bug
- `15. Proshop Replacement Research and Architecture/01_api_discovery/retest_item1_results.json` — Retest results with full payloads

**Key decisions:**
- Retested Item 1 before replying (6 weeks since original test) — confirmed still broken
- Only tested addPart (not addWorkOrder) to avoid burning another real WO number
- Offered testing partnership for API expansion — positions Traxis as collaborative, not adversarial
- Corrected tool library description: Fusion 360 ↔ ProShop sync, not standalone

**Status:** Draft ready for Wolfgang review. Needs: (1) paste via Web Claude for plain text conversion, (2) attach scope_permission_map.md, (3) delete test Part from ProShop.

---

### P19/P27: VPO Creation Workflow — Scheduler tool demand analysis + automated vendor PO creation

**Task:** Analyze WO 26-0027 tool requirements via the Shop Scheduler, create a Vendor Purchase Order to AJ Rod for low-stock tools, and update ProShop tool library pricing from the vendor order acknowledgment.

**What was done:**

1. **Scheduler tool demand analysis** — Queried P19 scheduler.db for WO 26-0027 (R2S1-AD163-001-022). Identified 19 unique tools across ops 50/60/70 (all mill-6). Found A34 (qty 1), A14 (qty 2), N124 (qty 2) as lowest stock. Five TiPD cobalt jobber drills not tracked in kiosk.

2. **VPO creation via ProShop API** — Iterated through several PO revisions (263093→263099) to establish correct field mapping:
   - `toolNumber` field links to COTS/Tool# library column (auto-fills description in UI only, not API)
   - `orderNumber` field maps to Order# column — populated with manufacturer brand + EDP (e.g., "Helical 81714")
   - `description` must be explicitly set via API (UI auto-fill doesn't work through GraphQL)
   - `shipTo` defaults to Traxis Manufacturing, 511 E St Elmo Rd, Austin TX 78745
   - `costPer`/`total` populated from vendor order acknowledgment

3. **EDP lookup from tool library** — Discovered `approvedBrands` is a paginated result (`PaginatedToolApprovedBrandResult`) requiring `{ records { vendorToolId approvedBrand cost } }` sub-selection. Always use first (top) record per Wolfgang's preference.

4. **Tool library pricing updates** — Ingested AJ Rod order ack (OrdAck1867792.pdf) and updated ProShop tool pages via `updateTool` mutation (note: `toolNumber` is a separate arg, not in the data object):
   - A34/Helical: $54.25 (was null)
   - A14/Gorilla: $26.78 (was $24.74)
   - N124/Harvey Tool: $116.20 (was null)

5. **Code update** — Modified `_build_po_items()` in accounting_ingest.py to use `toolNumber` instead of `itemNumber` for tool/COTS PO line items.

**Files modified:**
- `27. Accounting Ingest/accounting_ingest.py` — `_build_po_items()` field mapping change
- Memory files: VPO defaults, toolNumber behavior, approved brand selection, PO field mapping

**Key decisions:**
- `updatePurchaseOrder` mutation blocked by same acceptNewRecord permission gate — PO status must be set to Outstanding manually
- `updateTool` mutation works with `toolNumber` as a separate arg (not in the data input object), unlike PO mutations
- ProShop `toolNumber` auto-fill is UI-only; API must always include explicit `description`

**Status:** Complete. PO 263099 created, tool pricing updated. Manual step: set PO 263099 status to Outstanding.

---

### P33: Tool Library Updater — API tool switchover D195-D198 and reusable CLI utility

**Task:** Test ProShop API capability to update tool library entries when switching manufacturers (GARR to Kennametal GOdrill), then build a reusable CLI tool for future switchovers.

**What was done:**

1. **Manual tool updates via ProShop GraphQL API** — Updated D195, D196, D197, D198 from GARR 5xD drills to Kennametal GOdrill 3xD KC7325 drills:
   - Queried existing tool records (description, dimensions, coating, approved brands)
   - Fetched new tool specs from Kennametal product pages (diameter, OAL, flute length, shank, helix, coating)
   - Found VPO pricing in ProShop (PO 263067, 4/9/2026) — prices $46.37-$47.12/ea
   - Updated all fields: description, overallLength, lengthOfCut, shankDiameter, coating (TIALN), helixAngle (30), ansiCatalogNumber, approved brand (KENNAMETAL + new EDP + VPO cost)
   - Preserved old GARR info in purchasingNotes with PREV: prefix, without overwriting existing notes (kiosk notes on D197 preserved)
   - Downloaded Kennametal product images (API doesn't support picture uploads)

2. **Built P33: Tool Library Updater CLI** — Reusable Python utility with subcommands:
   - `inspect` — Query/display tool records (human + JSON output)
   - `find-vpo` — Search Tool-type VPOs for pricing
   - `scrape` — Fetch specs from manufacturer websites (Kennametal scraper built, extensible registry)
   - `preview` — Dry-run diff of proposed changes
   - `update` — Execute mutations with confirmation prompt
   - `download-image` — Save product images for manual upload
   - All subcommands support `--json` for Claude Code integration

**Key discoveries:**
- BA16 OAuth client accepts `purchaseorders:r` scope at token time (not pre-registered but works)
- BA16 does NOT accept `contacts:r` — supplier names on VPOs require AccountingConnector client
- ProShop API does NOT support picture uploads on tools (read-only field)
- `updateTool` mutation uses selector/data pattern for nested `approvedBrands` table updates

**Files created:**
- `33. Tool Library Updater/CLAUDE.md`
- `33. Tool Library Updater/tool_update.py` — CLI entry point
- `33. Tool Library Updater/proshop_tools.py` — ProShop API client
- `33. Tool Library Updater/description_format.py` — Description builder + PREV formatter
- `33. Tool Library Updater/mfg_scrapers.py` — Manufacturer scrapers (Kennametal)
- `Kennametal_B041A03455CPG_GOdrill.jpg` (+ 3 more product images in project root)

**ProShop records modified:**
- D195: GARR 89321 ($15.12) -> KENNAMETAL B041A03455CPG ($46.37)
- D196: GARR 89391 ($19.06) -> KENNAMETAL B041A04217CPG ($47.12)
- D197: GARR 89346 ($16.54) -> KENNAMETAL B041A03734CPG ($46.37)
- D198: GARR 89281 ($13.58) -> KENNAMETAL B041A02800CPG ($46.46)

**Status:** Complete. CLI tested and working against live ProShop data.

---

### P31: BLE Proximity Worker Tracking — Project creation and initial hardware test

**Task:** Create new project P31, move BLE proximity research from P5, and test Feasycom beacon tags with Asus USB BT dongle on 10.1.1.178.

**What was done:**

1. Created `31. BLE Proximity Worker Tracking/` as a new project, moved `BLE_Proximity_Detection_Research.md` from P5 via `git mv` (preserving history).
2. Wrote initial BLE scan test (`ble_scan_test.py`) — confirmed dongle detects both Feasycom tags.
3. Discovered beacons use **rotating random MAC addresses** — initial monitor using hardcoded MACs only got ~2 samples/5s. Rewrote to identify beacons by **iBeacon major number** instead.
4. Discovered both beacon slots on one tag share the same major but different minors (e.g., major=40604, minor=16178/16179). Grouped by major only.
5. Built live RSSI monitor (`ble_rssi_monitor.py`) with zone classification and rolling averages.
6. **Key finding:** Asus USB dongle reads -78 to -90 dBm regardless of distance (0ft vs 50ft in metal cabinet = ~4dB difference). Not enough RSSI dynamic range for proximity detection. Need a purpose-built BLE gateway.

**Files created:**
- `31. BLE Proximity Worker Tracking/CLAUDE.md`
- `31. BLE Proximity Worker Tracking/ble_scan_test.py`
- `31. BLE Proximity Worker Tracking/ble_rssi_monitor.py`
- `31. BLE Proximity Worker Tracking/ble_raw_diag.py`

**Files moved:**
- `5. Hyundai post development/BLE_Proximity_Detection_Research.md` → `31. BLE Proximity Worker Tracking/`

**Key decisions:**
- Identify beacons by iBeacon major number (not MAC, which rotates)
- Group minor variants under same major (same physical tag)
- Asus USB dongle insufficient for production — need dedicated BLE gateway (~$35-65)

**Open items:**
- Purchase a purpose-built BLE scanning gateway (Blue Charm BCG04, MOKOSmart MKGW3, or Shelly BLU Gateway)
- Label physical Feasycom tags with their major numbers (60285 and 40604)
- Consider Feasycom config app to adjust beacon advertising interval

---

### P30: COTS Label Description Fix — DOM scraper missing description text

**Task:** Fix missing description on COTS labels printed from the Chrome extension. TOO-220 printed without description text while THI-219 worked correctly.

**What was done:**

1. **Root cause identified** — The DOM scraper's header fallback regex `/[-–—]\s*(.+)/` matched the hyphen in "TOO-220", returning "220" as the description. The actual description ("TOOL, TANGLESS, M4X.7 HEX FREE-RUNNING ELECTRIC INSTALLATION") lives in a nested `.card-content` div as plain text, not in the form field labeled "Description" (which was empty).

2. **Three fixes applied to `cots-content.js`:**
   - Fixed header fallback regex to only match en-dash/em-dash (`[–—]`), not plain hyphens in COTS IDs
   - Added `extractText()` helper that reads `.value` from input/textarea/select elements (handles JS-populated form fields)
   - Replaced `.card-content` textarea-only fallback with a leaf-node text scan — skips structural containers (those with h2/h3/table/form) and grabs the first `.card-content` div with concise plain text

3. **Added "Related Label Projects" section** to P30 CLAUDE.md linking to P17 (Python CLI batch generator) and P9/P22 (shared print service).

**Files modified:**
- `30. Material Label Extension/traxis-material-label/src/cots-content.js` — scraper fixes
- `30. Material Label Extension/traxis-material-label/manifest.json` — version 1.1.0 → 1.2.1
- `30. Material Label Extension/CLAUDE.md` — added Related Label Projects section

**Key decisions:**
- P17 COTS label generator kept as-is for batch printing use case; P30 is primary for day-to-day
- ProShop COTS "Description" form field can be empty — the actual description lives in a `.card-content` div rendered separately in the page header area

**Status:** Complete. TOO-220 label now prints with full description.

---

## 2026-04-15

### P30: Material Label Extension — DOM scraper fixes and label layout update (Session 2)

**Task:** Test and fix the material label data scraping on ProShop WO pages, update label layout.

**What was done:**

1. Fixed DOM scraper not finding material — "Part Stock" label wasn't matching due to `◉` bullet prefix characters. Added `[^a-z]*` prefix to all label regexes.
2. Fixed scraper using `el.textContent` which included all descendants — switched to own-text-node extraction so "Part Stock" label matches correctly.
3. Fixed "Qty Ordered" not matching — original regex only handled "Order Qty" pattern, added "Qty Ordered" variant.
4. For WOs with multiple Part Stock entries, scraper now picks the **last** material (the current/active one, since replacements are appended).
5. Updated label layout: material font increased from 18px to 24px with word wrapping (400px max width), removed quantity line, removed separate grade line. Part number stays at 14px.

**Files modified:**
- `30. Material Label Extension/traxis-material-label/src/content.js` — DOM scraper fixes (bullet-tolerant regexes, own-text extraction, Part Stock last-child logic)
- `30. Material Label Extension/traxis-material-label/src/label-generator.js` — enlarged material font, text wrapping, removed qty/grade lines

**Key decisions:**
- When multiple materials in Part Stock, always use the last one (replacement material supersedes original)
- Full Part Stock string on label (including shape/dimensions) rather than trimmed material type only
- No material selection UI — single-button print with auto-scrape

**Status:** Working. Tested on WO 26-0140 (single material), WO 26-0002 (long text wrap), and WO 26-0071 (dual materials).

---

### P17/P30: COTS PNG Label Generator + Chrome Extension Print Button

**Task:** Replace P-touch Editor .lbx template workflow for COTS labels with programmatic PNG generation (matching P9 WO label style) and add a browser-based print button on ProShop COTS pages.

**What was done:**

1. **P17 — `generate_cots_labels.py`** (new file): Python CLI that generates COTS label PNGs using Pillow + qrcode. Layout: QR code left (ProShop URL), bold COTS ID (48pt) + wrapped description (28pt) right. Fixed 450px width (2.5" at 180 DPI), 128px height. 2x supersampled with LANCZOS downsample for crisp text. Supports `--print` (sends to PT-P700 via 10.1.1.242:5002), `--all` (batch from CSV), `--copies`, and `--api` (pulls item data from ProShop GraphQL API instead of CSV).
2. **P30 — Chrome extension expanded** to also inject a "Print COTS Label" button on ProShop COTS detail pages (`/procnc/ots/*`). Added `cots-content.js` (button injection, DOM scraping for description) and `cots-label-generator.js` (Canvas-based rendering matching the Python layout). Button is fixed-positioned top-center to avoid disrupting ProShop page layout. Extension renamed to "Traxis Label Printer" v1.1.0.
3. Test-printed THI-219 labels through multiple iterations refining font sizes, text wrapping, and resolution.

**Files created:**
- `17. COTS - Tools Crib Kiosk/generate_cots_labels.py`
- `17. COTS - Tools Crib Kiosk/labels/` (generated PNGs)
- `30. Material Label Extension/traxis-material-label/src/cots-content.js`
- `30. Material Label Extension/traxis-material-label/src/cots-label-generator.js`

**Files modified:**
- `30. Material Label Extension/traxis-material-label/manifest.json` (added COTS content script, bumped version)

**Key decisions:**
- Fixed label width at 450px (2.5") per Wolfgang's constraint
- 2x supersampling for text quality, though thermal printer dithers to 1-bit
- Description font enlarged to 28pt with word wrapping (max 2 lines) per Wolfgang's feedback
- Chrome button placed as fixed-position top-center to avoid ProShop DOM interference

**Status:** Complete. Extension needs reload in chrome://extensions to pick up changes.

---

## 2026-04-13

### ProShop API — Batch WO Status Update to Invoiced

**Task:** Update 11 work orders to "Invoiced" status in ProShop based on QBO invoices created today.

**What was done:**

1. Read `wo_invoiced_today.md` — 11 WOs matched to QBO invoices created 2026-04-13
2. Investigated ProShop GraphQL schema — found `updateWorkOrder` mutation accepts `UpdateWorkOrderInput` with a `status: WorkOrderStatus` field
3. Verified all 11 WOs were in "Shipped" status
4. Test-updated 25-0300 → Invoiced successfully
5. Batch-updated remaining 10 WOs — all succeeded, zero failures

**WOs updated:** 25-0300, 25-0302, 26-0057, 26-0059, 26-0093, 26-0094, 26-0116, 26-0122, 26-0123, 26-0124, 26-0125

**Key discovery:** First use of `updateWorkOrder` mutation for WO status changes in the codebase. Pattern: `mutation($wn: String!, $data: UpdateWorkOrderInput) { updateWorkOrder(workOrderNumber: $wn, data: $data) { workOrderNumber status } }` with `{status: "Invoiced"}`.

**Files modified:** None — all work was ad-hoc API calls, no project code changed.

**Status:** Complete.

---

### Project 29: Rollo Printer App — Full Implementation

**Task:** Implement P29 Rollo Thermal Printer system tray app from spec.

**What was done:**

1. **Built `rollo_printer_app.py`** — full system tray app using pystray, PyMuPDF, pywin32. Right-click menu: Print to Rollo, Test Printer, Open Log, Quit.
2. **Smart PDF rescaling** — auto-detects ink bounding box on the page, crops to content, auto-rotates landscape→portrait, scales up to fill 4x6 label. Solves the core UPS problem where labels print tiny on thermal paper.
3. **Created PyInstaller spec** — single .exe build (40MB), no console window.
4. **Built .exe** — `dist/rollo_printer_app.exe` compiled successfully.
5. **Created shortcuts** — Desktop shortcut + Windows Startup folder shortcut for auto-launch on boot.
6. **Discovered `.pyw` not registered** on this machine — worked around with `.bat` launcher for dev, `.exe` for production.
7. **Tested end-to-end** — printed a real UPS label (`upscarmex.pdf`) to Rollo, confirmed content fills the label correctly.

**Files created:**
- `29. Rollo Printer App/rollo_printer_app.py` — main app source
- `29. Rollo Printer App/rollo_printer_app.spec` — PyInstaller spec
- `29. Rollo Printer App/rollo_printer_app.pyw` — windowless launcher copy
- `29. Rollo Printer App/Rollo Printer.bat` — bat launcher (dev fallback)
- `29. Rollo Printer App/requirements.txt` — dependencies
- `29. Rollo Printer App/CLAUDE.md` — project docs with interfaces
- `29. Rollo Printer App/dist/rollo_printer_app.exe` — compiled executable
- Desktop shortcut: `Rollo Printer.lnk`
- Startup shortcut: `Rollo Printer.lnk`

**Key decisions:**
- Used PyMuPDF (fitz) over PyPDF2 for reliable rasterization
- Content-aware cropping (ink bounding box detection) was critical — naive page scaling produced tiny labels
- Auto-rotation handles landscape UPS PDFs on portrait 4x6 labels

**Status:** Complete. App is running, printing correctly, and will auto-start on boot.

---

### Project 28: ProShop API Usage — Batch NCR Scrap Disposition

**Task:** Investigate API control over NCR (Non-Conformance Report) module and batch-disposition all outstanding NCRs as scrap.

**What was done:**

1. **Introspected ProShop GraphQL schema for NCR types** — mapped `NonConformanceReport`, `UpdateNCRInput`, `NCRDisposition`, `UpdateNonConformanceDispositionTableInput`, `NonConformanceReportFilter`, and related types
2. **Discovered OAuth scope gating** — `nonconformancereports:rwdp` scope is enforced server-side (unlike some other modules). Existing clients (FusionConnector, ClaudeCodeResearch) did not have it enabled
3. **Created new OAuth client** — `B828-32C5-5194` (2ClaudeCodeReasearch) with full scope list including NCR access. Discovered ProShop has a character limit on scope field and scopes are locked at client creation time
4. **Queried all 277 NCRs** — found 118 Outstanding, 159 Complete. Two status values only: "Outstanding" and "Complete"
5. **Tested single NCR update** — confirmed `updateNCR` mutation with disposition array adds "Scrap" disposition row and auto-flips status to "Complete"
6. **Batch processed 108 Outstanding NCRs** (on or before March 13, 2026) — all dispositioned as Scrap with note "Batch scrap disposition - API cleanup April 2026". 101 moved to Complete, 6 stayed Outstanding (0 parts affected)
7. **Processed remaining 14 NCRs** — scrapped 10 recent ones (post-March 13), deleted 4 zero-quantity NCRs
8. **Final result: 0 Outstanding NCRs remaining**

**Key findings:**
- ProShop NCR mutations: `addNCR`, `updateNCR(ncrRefNumber, data)`, `deleteNCR(ncrRefNumber)`
- Disposition is an array of `{data: {disposition, dispositionquantity, dispositionnotes}}` within `UpdateNCRInput`
- ProShop auto-completes NCRs when disposition quantity > 0 is added
- NCR dates are in `MM/DD/YYYY; HH:MM:SS AM/PM` format, not ISO
- OAuth scope field has a character limit; scopes must be set at client creation, cannot be expanded after

**Files modified:** None (all operations were API-only, no code changes)

**New OAuth client created:**
- Client ID: B828-32C5-5194
- Name: 2ClaudeCodeReasearch
- Scope includes: nonconformancereports:rwdp + full module access

**Status:** Complete. All 277 NCRs resolved (scrapped or deleted). Zero outstanding.

---

### Project 28: ProShop API Usage — Recon & Interval Reduction

**Task:** Investigate why ProShop reported ~1,600 API calls/hour from Traxis, identify culprits, and reduce call volume.

**What was done:**

1. **Full recon across all projects** — identified every script making ProShop GraphQL API calls, catalogued auth approaches, query types, polling patterns, and estimated calls/hr per service
2. **Identified top 3 culprits:**
   - Message Notifier (P18): ~2,400–4,800 calls/hr (30s per-user polling)
   - Time Status Display (P1): ~1,320 calls/hr (30s per-user polling)
   - Shop Scheduler (P19): ~1,200–1,350 calls/hr (15-min full sync with per-WO fan-out)
3. **Reduced polling intervals:**
   - P18 Message Notifier: 30s → 30 min (config.py POLL_INTERVAL)
   - P1 Time Status Display: 30s → 15 min (POLL_INTERVAL + dashboard.html POLL_MS)
   - P19 Shop Scheduler: 15 min → 2 hr (config.py SYNC_INTERVAL)
4. **Documented ProShop's response** from Joao (via Tom) — noting unfiltered bulk queries as future optimization target
5. **Wrote RECON_REPORT.md** with full findings, per-script breakdown, and recommendations
6. **Restarted all three services** via Overseer API

**Files modified:**
- `18. ProShop Message Notifier/config.py` — POLL_INTERVAL 30 → 1800
- `18. ProShop Message Notifier/templates/notifier.html` — added Check Now button, conditional auto-poll
- `18. ProShop Message Notifier/message_notifier.py` — added _single_check method
- `1. Proshop Automations/TimeTrackerDashboard/time_status_display_v1.0.py` — POLL_INTERVAL 30 → 900
- `1. Proshop Automations/TimeTrackerDashboard/dashboard.html` — POLL_MS 15000 → 900000
- `19. Shop Scheduler/config.py` — SYNC_INTERVAL 900 → 7200
- `28. Proshop API Usage/RECON_REPORT.md` — created (recon findings + ProShop reply)

**Key decisions:** Kept writeback interval (120s) unchanged in P19 since it only fires when there are queued local changes. Kept "Check Now" / "Refresh" buttons for on-demand use between intervals.

**Estimated result:** ~5,000–6,700 calls/hr → ~284–384 calls/hr

**Follow-up work (same session):**

7. **Resolved open items:**
   - Clock Feedback Display (`clock_feedback_display_v1_0_0.py`) — confirmed not running. Not on Overseer, no process found. Non-issue.
   - FusionToolAuditor hardcoded secret — removed `PROSHOP_CLIENT_SECRET` from source code, now loads from `.traxis.env` (same pattern as ProShopBridge). Also scrubbed secret from P16 CLAUDE.md.
   - GraphQL Playground — introspected 7 key filter types (`WorkOrderFilter`, `PurchaseOrderFilter`, `UserFilter`, `WorkCellFilter`, `ToolFilter`, `ContactFilter`, `ClockPunchFilter`) from live API. Documented all available filter fields in RECON_REPORT.md with recommended filter changes table.
8. **Documented Joao's (ProShop/Adion) reply** in RECON_REPORT.md — key guidance: use filters to fetch only needed records, GraphQL Playground at `/api/graphql` has full schema.
9. **Created P28 CLAUDE.md** with interfaces section.
10. **Added P28 to TRAXIS_ECOSYSTEM.md** project list.

**Additional files modified:**
- `16. Fusion Tool Library Product ID Changer/FusionToolAuditor/FusionToolAuditor.py` — replaced hardcoded credentials with `.traxis.env` loader
- `16. Fusion Tool Library Product ID Changer/CLAUDE.md` — removed hardcoded secret, updated credentials section
- `28. Proshop API Usage/CLAUDE.md` — created (interfaces)
- `28. Proshop API Usage/RECON_REPORT.md` — added ProShop reply, filter fields reference, recommended filter changes
- `TRAXIS_ECOSYSTEM.md` — added P28 entry

**Status:** Complete. Services restarted. All open items resolved except follow-up email to Tom/Joao (Wolfgang's action).

---

### Project 22: Tool Assembly Kiosk — Push to ProShop Button + Overseer Dashboard Fixes

**Task:** Move inventory sync from an always-on Overseer service to an on-demand kiosk button. Fix Overseer dashboard links and add self-restart capability.

**What was done:**

1. **Removed InventorySync from Overseer** — deleted service config, validator, and VALIDATORS entry
2. **Added "Push to ProShop" button to kiosk** — background thread + polling pattern for the ~15min sync; button on inventory menu and summary screens
3. **Added Overseer self-restart button** — `POST /api/overseer/restart` spawns replacement process; dashboard polls until it comes back
4. **Fixed Overseer "Open" links** — replaced `localhost` with `location.hostname` for remote viewing

**Status:** Complete. Overseer HTML committed. Kiosk changes sync via Dropbox.

---

## 2026-04-12

### Project 12: TPM (Traxis Program Manager) — Startup Fix + NC Program Naming (Session 5)

**Task:** Diagnose why TPM add-in won't load in Fusion 360, then review its purpose and discuss improvements.

**What was done:**

1. **Fixed startup crash** — `ModuleNotFoundError: No module named 'tpm'`. Root cause: Fusion's add-in loader doesn't add the add-in's directory to `sys.path`, so the `tpm/` subpackage (extracted in v1.6.0 on April 2) couldn't be found. Fix: `sys.path.insert(0, _addon_dir)` before the `from tpm import ...` line. Other add-ins (ProShopBridge, FusionToolAuditor) are single-file scripts so they never hit this.

2. **Added post-completion NC Program rename** — New `_rename_nc_programs()` function runs after posting (in `PostCompletedHandler`). Catches NC Programs created during posting with default names like `NCProgram4` and renames them to `PartNumber_OPxx` format using `_naming_state`.

3. **Added diagnostic logging** — `_match_nc_to_setup()` now logs which matching strategy succeeded or why it failed, so we can debug NC Program matching issues via Fusion's Text Commands panel.

4. **Proposed Name/File name improvement (DEFERRED)** — The post dialog "File name" field shows the O-code (`0071`) instead of the descriptive name (`R2S1-10130_OP70`). Fix requires a paired change: TPM sets `job_programName` to filename stem + every .cps post processor's `getProgramNumber()` handles non-numeric names by extracting OP from `_OPxx` pattern. Deferred because .cps changes are production-critical and need careful testing. Writeup documented in session for future reference.

**Files modified:**
- `12. FASData Implementation/TraxisProgramManager/TraxisProgramManager.py` — sys.path fix (lines 48-55), `_rename_nc_programs()` function, improved `_match_nc_to_setup()` logging, TODO comment on job_programName

**Key decisions:**
- O-code numbering (O0061, O0071) is cosmetic since programs are transferred via Fanuc Transfer Tool — not worth changing independently
- .cps post processor changes need careful rollout, not a quick session fix
- Version encoding in O-codes would be lost with the proposed approach — needs consideration

**Status:** TPM loads and runs. NC Program tree naming improved. File name field improvement waiting on .cps change plan.

---

### Projects 9/22/1: Generic Print Endpoint + WO Label Printing (Session 4)

**Task:** Add a generic image print endpoint to the label print service (P22) so any project can print labels, then add WO label printing capability to Project 9.

**What was done:**

1. **Generic `/api/print-image` endpoint** — Added to print_service.py on 10.1.1.242. Accepts base64-encoded PNG, copies count, and optional label_name. Uses shared `_print_image_gdi()` helper refactored from the existing `_print_png()` code.

2. **Remote restart endpoint** — Added `/api/restart` to print_service.py. Spawns a new process and exits, enabling remote restart from the overseer dashboard. Updated overseer.py to call `restart_url` for remote services instead of logging "cannot restart."

3. **WO label printing** — Added `print_wo_label()`, `make_wo_label_image()`, and `--print` CLI flag to generate_wo_labels.py (P9). Labels include QR code (encoding `proshop://wo/{wo_number}`), bold WO number, and part number + part name from ProShop API lookup.

4. **GDI print fixes** — Fixed BMP row alignment bug (image width must be padded to multiple of 4 for DWORD-aligned rows — caused 45° skew). Sized label to 128px height matching PT-P700's actual printable area (not 170px tape height). Adjusted fonts from 48pt→36pt to fit.

5. **Printer driver config** — Discovered PT-P700 "cut tape after data" setting (was cutting at fixed 3.94" regardless of content). Disabled auto power off so printer stays in sleep mode and wakes on print jobs.

6. **ProShop scope issue** — `contacts:r` needed for customer name on labels, but FusionConnector OAuth client rejects it despite ProShop admin showing it enabled. Fell back to part number + part name. Needs investigation.

7. **Camera/tablet planning** — Discussed IP camera vs GoPro vs tablet for shop floor photo capture. Decided on Android tablet as single device for walk-around setup photos, packing station box photos, tool photos, and QR scanning. Reolink IP camera order cancelled in favor of tablet. Brother ADS-2200 scanner for multi-page docs.

**Files modified:**
- `22. Tool Assembly Management/tool-kiosk/print_service.py` — /api/print-image, /api/restart, _print_image_gdi refactor, BMP row alignment fix, DEVMODE tape length
- `9. Shop Floor Cameras/config.py` — added PRINT_SERVICE_URL
- `9. Shop Floor Cameras/generate_wo_labels.py` — print_wo_label(), make_wo_label_image(), --print flag, label dimensions/fonts
- `9. Shop Floor Cameras/proshop_client.py` — added customerName field to lookup (reverted query due to scope)
- `1. Proshop Automations/Overseer/overseer.py` — restart_url config, remote restart support
- `C:\Users\TRAXIS\.traxis.env` — scope change attempted (reverted)

**Key decisions:**
- PT-P700 printable area is 128px tall (not 170px for 24mm tape) — labels must be sized to 128px
- BMP row data must be DWORD-aligned (pad image width to multiple of 4)
- "Cut tape after data" driver setting eliminates tape waste
- Tablet replaces both GoPro and fixed IP camera for shop floor photo capture
- Part number + part name on labels (customer name blocked by OAuth scope issue)

**Status:** WO label printing fully working end-to-end. Remote restart working. Camera/tablet hardware pending order.

---

### Project 1: ProShop Bridge — Orientation Cube Visual + 180° Axis Fix (Session 3)

**Task:** Refine the "From Previous Op" section of the written description push. The text-based face mapping ("Right goes to Front, Back goes to Left") was confusing and the 180° rotation axis detection was wrong.

**What was done:**

1. **Fixed 180° rotation axis detection bug** — `_rotation_summary()` used `max(diagonal)` to find the rotation axis for 180° rotations, which fails for non-cardinal axes (e.g., (1,-1,0)/√2 was falsely reported as "X axis"). Replaced with proper `(R+I)` eigenvector method that correctly finds the rotation axis for all 180° cases.

2. **Added isometric orientation cube SVGs** — New `_render_orientation_cube_svg()` function generates transparent isometric cube with two highlighted faces (green=Top, blue=Front). Before/After cube pair shows where those faces move after the rotation. Pure inline SVG, zero dependencies, microsecond generation time.

3. **Added `_render_transition_visual()`** — Composes Before→After HTML layout with cubes, arrow, color legend, and rotation summary text caption (e.g., "flip about X axis").

4. **CKEditor SVG support** — Added `editor.filter.allow()` call in Tampermonkey script to whitelist SVG/polygon/text elements through CKEditor's Advanced Content Filter. Confirmed SVG renders in ProShop.

5. **WCS debug logging** — Added raw WCS axis vector logging for both setups during push, enabling diagnosis of WCS frame mismatches.

6. **Iterative refinements** — Removed face labels (cluttered), removed dashed lines (means hidden edges in shop drawings), tried axis spear + curved arrow (too busy), settled on clean colored cubes only.

**Files modified:** `ProShopBridge/ProShopBridge.py` (orientation cube SVG, 180° fix, WCS logging), `ProShopBridge/proshop_bridge_tampermonkey.user.js` (CKEditor SVG filter)

**Key decisions:**
- Two highlighted faces (Top + Front) disambiguate all 6 faces via right-hand rule — one face is not enough
- Solid edges only — dashed lines imply hidden internal edges to machinists
- Text caption kept alongside cubes for "flip about X axis" summary
- Axis spear and curved arrow tried but removed — cubes alone are clearer
- The WCS frames from Fusion may not correspond to a clean physical flip if the programmer also rotated XY for fixture alignment — the corrected 180° detection now honestly reports "flip 180°" instead of falsely attributing a cardinal axis

**Status:** Complete. Tested end-to-end: Part 10130 Op 80 with orientation cubes rendered in ProShop written description.

---

### Project 1: ProShop Bridge — Written Description Push Fix (Session 2)

**Task:** Continued debugging the written description push to ProShop, which had stopped working after ~2 weeks of successful operation.

**What was done:**

1. **Root cause found: URL separator `?` vs `$`** — `proshop_selenium_helper.py` used `?formName=writtenDescription` but ProShop requires `$formName=writtenDescription` for subform pages. With `?`, ProShop loaded the Part details page instead of the written description subform, so CKEditor was never found. This was introduced during the 2026-03-13 "URL fix" session which correctly changed `$`→`?` for `toolDetail` but incorrectly applied the same change to `writtenDescription`.

2. **Content prepend bug fixed** — `_set_ckeditor_content()` was combining new content with existing page content (`html + '<hr>' + existing`). When the page had leftover 250KB test data from the prior debug session, the combined 366KB payload exceeded ProShop's 256KB limit and was silently discarded. Changed to replace content entirely.

3. **Marker verification hardened** — `_save_via_fetch()` was treating a missing verification marker as success ("best-effort"). Now properly returns failure when the marker isn't found in the server response, giving accurate save feedback.

**Files modified:** `ProShopBridge/proshop_selenium_helper.py` (3 changes: URL `$`, content replace, marker verification)

**Key decisions:**
- ProShop URL scheme is inconsistent: `toolDetail` uses `?`, `writtenDescription` uses `$` as path/query separator
- The 256KB server-side limit (found in Session 1) is real but was NOT the reason the tool stopped working — kept size guards as defense-in-depth
- Composite screenshots (1280x720 q65 from Session 1) produce ~108KB payloads, well under 256KB limit
- User confirmed successful end-to-end push: Part 10130 Op 80 with composite screenshots, tool list, WCS data

**Status:** Complete. Written description push working end-to-end from Fusion 360.

---

### Project 25: Agent Exploration — Ecosystem Ritual & Constellation Implementation

**Task:** Implement the Session Close Ritual, Interface Block standard, and TRAXIS_ECOSYSTEM.md constellation file from the P25 session brief designed with Web Claude on 2026-04-11.

**What was done:**

1. **Root CLAUDE.md** (new file at project root) — Four-beat session close ritual, "sir" diagnostic tell, interface block standard definition. Auto-loaded by Claude Code for every session.

2. **P19 Shop Scheduler / CLAUDE.md** (new file) — Created with `## Interfaces` section. Produces: scheduler.db, Flask UI (port 5080), priority/tool-demand APIs, heartbeat. Consumes: ProShop GraphQL, P22 tooling.db (read-only). Contract: reads tooling.db at relative path set in config.py:35.

3. **P22 Tool Assembly Management / CLAUDE.md** (new file) — Created with `## Interfaces` section. Produces: tooling.db, Flask kiosk UI (port 5001), print-label proxy, health endpoint. Consumes: ProShop GraphQL, .traxis.env, Overseer, FocasMonitor monitoring.db, Brother printer. Contracts: P19 reads tooling.db, print_service on port 5002.

4. **scan_projects.py** (modified) — Added `parse_interface_block()` for direct text parsing of `## Interfaces` sections. Added `render_ecosystem_file()` to generate TRAXIS_ECOSYSTEM.md from project_index.json. Fixed session log path mismatch (`SESSION_LOG.md` → `main_session_log.md`).

5. **alerter.py** (modified) — Daily Telegram digest now includes "ACTION ITEMS" section with top 5 open items from project_index.json.

6. **project_index.json** (modified) — Added `interfaces` field to P19 and P22 entries.

7. **TRAXIS_ECOSYSTEM.md** (new file at project root) — Initial render with 26 projects, interface map (P19/P22), 3 critical seams, 20 open items.

**Files created:** `CLAUDE.md` (root), `TRAXIS_ECOSYSTEM.md` (root), `19. Shop Scheduler/CLAUDE.md`, `22. Tool Assembly Management/CLAUDE.md`
**Files modified:** `25. Agent Exploration/scan_projects.py`, `25. Agent Exploration/alerter.py`, `25. Agent Exploration/project_index.json`

**Key decisions:**
- Interface block parsing is pure text (no Haiku call needed) — comma-separated values under Produces/Consumes/Contracts
- Contracts field uses free-text (not structured) since cross-project assumptions are too varied for a rigid schema
- Scanner fix: `SESSION_LOG.md` → `main_session_log.md` to match the actual file name
- Ecosystem file rendered at end of every non-dry-run scan

**Status:** Complete. Ritual active, seed interfaces in place, scanner ready for nightly runs. Remaining projects need `## Interfaces` backfill incrementally.

---

## 2026-04-11

### Project 22: Tool Assembly Management — Inventory Sync Service + Live Push

**Task:** Build a service to push physical cabinet inventory counts from tooling.db to ProShop via GraphQL API, correcting systematic quantity inflation (tools rarely retired, purchases auto-add).

**What was done:**

1. **`inventory_sync.py`** (new file in `tool-kiosk/`) — Standalone sync script:
   - Reads cabinet counts from `tooling.db` (518 of 542 tools counted via kiosk sessions April 6-7)
   - Queries RTAs and work cell pockets from ProShop to get in-use tool counts
   - Ground truth: `cabinet_total + max(rta_count, wc_count)` per tool number
   - Pushes `qtyInBin` (usable = blue+green), `quantity` (total in shop), `purchasingNotes` (yellow/red condition data)
   - Notes format: `[Kiosk 2026-04-07] 2 worn, 1 replace` — replaces prior kiosk lines, preserves other notes
   - `--dry-run` and `--loop N` flags, off-hours gate (18:00-05:00 weekdays, all day weekends)
   - Sync log table in tooling.db tracks what's been pushed to avoid redundant writes
   - 0.1s throttle between API calls, per-tool error handling, timeout retry on large tool fetch

2. **Overseer integration** (`overseer.py`) — Added `InventorySync` service config:
   - Subprocess service with `--loop 3600` (hourly), auto-start enabled
   - Database health validator checks sync log freshness (2h threshold) and push counts

3. **Live run executed** — 485 tools updated, 242 condition notes written, 0 errors:
   - R66: total 4→6 (cab=5 + 1 in work cell), condition notes added
   - A1039: total 4→1 (cab=0 + 1 in work cell — correctly not zeroed)
   - A157: bin qty set, condition notes added
   - 16 tools in kiosk DB not found in ProShop (skipped)

**Key decisions:**
- Always overwrite ProShop quantities with ground truth (no "skip if ProShop higher" rule — ProShop is systematically inflated)
- Use `max(rta_count, wc_count)` per tool to avoid double-counting (RTA in a work cell appears in both queries)
- `qtyInBin` is writable but returns null via API — use `quantity` ("Total in Shop") for comparison reads
- Standalone script sharing `proshop_client.py`, `database.py`, `config.py` with kiosk app (not part of Selenium bridge)

**Status:** Complete. Live push successful. Overseer service config committed. Tool Shortages report in ProShop should show dramatically fewer false shortages.

---

### Project 19: Shop Scheduler — Fix Operation Block Sizing on Drag

**Task:** Operations visually shortened/lengthened when dragged because raw millisecond duration was preserved instead of business hours.

**What was done:**
- Added `businessHoursBetween(start, end)` function to `scheduler.js`
- Updated `handleBlockMove()` to compute business-hour duration of original position, then use `addBusinessHours()` to set the new end time
- Business hours: 5 AM - 6 PM, no weekends (matches existing BH_START/BH_END constants)

**Status:** Complete. Block sizing now consistent regardless of drag position.

---

## 2026-04-10

### Project 27: Accounting Ingest — QBO API Integration + Git Repo Setup

**Task:** Replace the QBO "drop folder" approach with real QuickBooks Online API Bill creation. Also create a git repository for the project collection under Wolfgang's GitHub account.

**What was done:**

1. **`QBOClient` class** (accounting_ingest.py) — Full QBO OAuth2 integration:
   - Token refresh using stored refresh token from `.traxis.env`; automatically saves the rotated token back to the file
   - `get_vendors()` — pulls all QBO vendors (1-hour cache)
   - `fuzzy_match_vendor(name)` — difflib-based matching, same approach as ProShop contact matching
   - `get_default_expense_account()` — finds Cost of Goods Sold or any Expense account for line item billing
   - `create_bill()` — maps extracted invoice fields to QBO Bill API format; uses line items if extracted, falls back to single total-amount line
   - `check_duplicate_bill()` — queries QBO by DocNumber before pushing
   - `_update_env_value()` helper — persists refreshed QBO tokens to `.traxis.env`

2. **Ingest flow change** — Vendor invoices no longer auto-copy to a folder. They go to the PENDING review queue like packing slips, POs, etc. Full Claude extraction happens at ingest time (not just classification).

3. **UI changes:**
   - Contact/vendor panel relabels dynamically: "QBO Vendor" for invoices, "Customer / Vendor (ProShop)" for other docs
   - Vendor search for VENDOR_INVOICE queries QBO vendor list; other doc types still search ProShop contacts
   - Approve button shows "✓ APPROVE & PUSH TO QBO" vs "✓ APPROVE & PUSH TO PROSHOP" depending on doc type
   - After QBO push: status "Uploaded to QBO ✓" + clickable link to bill in QBO sandbox
   - "Open QBO" toolbar button opens QBO bills list in browser
   - QBO duplicate check before pushing (by invoice DocNumber)

4. **Git repository initialized** — `C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects` initialized as a git repo:
   - 194 files committed across locally-synced projects
   - `.gitignore` excludes `.traxis.env`, cloud-only Dropbox folders (not synced on this machine), embedded `git-history/` folders, `.lnk` shortcuts
   - Cloud-only folders (need Dropbox sync before adding): 12 FASData, 14 Workstation Display, 15 ProShop Research, 17 COTS Kiosk, 18 Notifier, 19 Shop Scheduler, 20 Traxis Data, 21 Haas, 22 Tool Assembly, 23 Air Compressor, 25 Agent Exploration, 26 SMT, API Projects, OLD
   - Embedded .git folders in sub-projects renamed to `git-history/` (preserved, not deleted)
   - Pushed to GitHub under Wolfgang's account (repo: `traxis-automation`)

**Files modified:**
- `27. Accounting Ingest/accounting_ingest.py` — v1.1.0 → v1.2.0 (QBOClient + routing changes)
- `.gitignore` — new file (project root)
- `main_session_log.md` — this entry

**Key decisions:**
- QBO sandbox credentials (`sandbox-quickbooks.api.intuit.com`) used — production requires Intuit app review checklist completion
- Expense account selected automatically (COGS preferred); no manual account selection required in UI
- Git repo covers entire project collection, not just project 27 — cloud-only folders will be added incrementally as Dropbox syncs them to each machine

**Status:** QBO Bill creation complete and syntax-verified. Needs live test with a real vendor invoice. Git repo created and pushed.

---

## 2026-04-11

### Project 27: Accounting Ingest — QBO Test, ProShop Mutations, Intuit App Review, Live Testing

**Task:** Test QBO bill creation end-to-end, complete Intuit app assessment for production keys, fix ProShop mutations with full field mapping, and live-test the app with real emails.

**What was done:**

1. **QBO Bill creation verified** — Test bill #145 created in sandbox (Bob's Burger Joint, 2 line items, $247.50). Duplicate detection confirmed. JSON payload fix (no wrapper object).

2. **Intuit app assessment completed:**
   - Created privacy policy, terms, EULA, disconnect pages on GitHub Pages
   - Added `intuit_tid` capture, CSRF verification, `invalid_grant` handling, discovery doc fetch, token revocation, PDF attachment upload
   - Added `QBO_ENVIRONMENT` toggle (sandbox/production) in `.traxis.env`
   - Submitted questionnaire — waiting for Intuit approval

3. **ProShop mutations fixed and expanded:**
   - Fixed return field names (`id` not `purchaseOrderId`/`packingSlipId`)
   - Added line item support for Bills, Packing Slips, and Purchase Orders
   - Expanded field mapping for all doc types (PO gets confirmationNumber/date/lead time, PS gets tracking/PO ref, etc.)
   - Tested: PO #263068 and Packing Slip #260411-01 created with line items

4. **Email polling fixes:**
   - Rolling 30-day window + pagination (gets all emails, not just first 50)
   - Image attachment filtering (isInline, contentType, extensions, size)
   - Whitelisted `tom@traxismfg.com` for forwarded accounting docs

5. **UI improvements:**
   - Better classify prompt (Traxis-specific Customer PO vs Vendor PO distinction)
   - Re-extract button, UPLOAD_FAILED in Pending filter, combobox dark theme fix

6. **ProShop API permission discovery:**
   - API clients map to ProShop users (AccountingConnector = User #010)
   - Two permission layers: OAuth scope AND user module permissions
   - User 010 had read-only defaults — granted full write but `addCustomerPo` still failing — escalated to ProShop support

**Key discovery:** ProShop API has two permission layers. OAuth scope gates endpoint access. User #010 permissions gate operations. Both must be configured.

**Status:** QBO pipeline fully tested (sandbox). ProShop PO + Packing Slip working. Customer PO blocked on ProShop permissions — awaiting support. Intuit production keys pending.

---

## 2026-04-08

### Project 19/22: Shop Scheduler — Tool Demand Checker + Overseer Integration

**Task:** Cross-reference tool demand (from operation_tools in scheduler DB) against physical inventory (from tool_inventory in kiosk DB) and flag shortages on the Tools page. Also add Shop Scheduler to the Overseer for auto-start and health monitoring.

**What was done:**

1. **`/api/tool-demand` endpoint** (app.py) — Queries all tools needed by active, non-hidden, incomplete operations from `operation_tools`, aggregates by tool_number (with op count + WO list), then reads the kiosk's `tooling.db` in read-only mode (`sqlite3.connect("file:...?mode=ro", uri=True)`) to look up `qty_available` (blue + green) and `min_quantity`. Classifies each tool as `out_of_stock` (qty=0), `low_stock` (qty ≤ min), `ok`, or `not_in_inventory`. Sorts flagged items first. Gracefully handles missing/locked kiosk DB.

2. **Tool Shortages UI** (tools.html) — New collapsible section above "Work Orders Needing Tools". Color-coded rows: red (out of stock), orange (low stock), gray (not tracked in inventory). Each row shows tool number, description, status badge, qty available, op count, and WO numbers (truncated at 3). Auto-refreshes every 30s. Shows warning banner if kiosk DB is unavailable.

3. **Config: `KIOSK_DB_PATH`** (config.py) — Absolute path to kiosk's tooling.db computed relative to scheduler dir (`../22. Tool Assembly Management/tool-kiosk/data/tooling.db`).

4. **Overseer: ShopScheduler service** (overseer.py) — Added `SHOP_SCHEDULER_DIR` path, `ShopScheduler` service config (process type, port 5080, `auto_start: True`, HTTP health check at `/api/health`), `validate_shop_scheduler()` validator (checks `api_reachable`, `token_valid`, reports active WO count + uptime), registered in `VALIDATORS` dict.

**Files modified:**
- `19. Shop Scheduler/config.py` — Added `KIOSK_DB_PATH`
- `19. Shop Scheduler/app.py` — Added `import os`, `/api/tool-demand` endpoint
- `19. Shop Scheduler/templates/tools.html` — Tool Shortages section + JS
- `1. Proshop Automations/Overseer/overseer.py` — ShopScheduler service + validator

**Key decisions:**
- Read-only SQLite connection to kiosk DB avoids write locks on Dropbox-synced file
- Tools classified as `not_in_inventory` when kiosk DB is available but tool isn't found (vs `unknown` when DB is unreachable)
- Overseer will auto-start scheduler on boot; needs Overseer restart to pick up new config

**Status:** Code complete, syntax verified. Needs Overseer restart and scheduler launch to test live.

---

## 2026-04-07

### Project 22: Tool Assembly Management — Remote Printing, Touchscreen UI, Overseer Update

**Task:** Get remote label printing working from the kiosk, improve touchscreen usability (fonts too small, no keyboard hint), and update the Overseer to monitor the remote print service.

**What was done:**

1. **Remote printing fixed** — The print service on .242 (PT-P700) was never reachable remotely because Windows Firewall was blocking port 5002. Ran `open_print_service_firewall.bat` as admin on .242, started print service via `start_print_service.bat`. First successful remote print: 2x H-0026 labels from MainPC to .242's PT-P700 via b-PAC. Startup folder shortcut already existed for auto-start on boot.

2. **Font sizes increased for touchscreen** — Base font 18px→22px (all rem values scale). Form inputs height 48→56px, font 1rem→1.05rem. Form labels 0.9→1rem. Nav buttons 0.9→1rem. Scan hints 0.9→1rem. Badges 0.75→0.85rem. Table text, inventory descriptions, color tags all bumped. 600px breakpoint floor 16→19px.

3. **Keyboard hint added** — "Use keyboard to type in fields below" pill displayed at the top of all form panels (Register RTA, Install Cutter, Assign to Machine, Add Inventory Tool). Styled as subtle gray rounded bar.

4. **Overseer updated for remote print service** — Changed `LabelPrintService` config from `service_type: "process"` with localhost health check to `service_type: "remote"` pointing at `http://10.1.1.242:5002/api/health`. Removed `start_cmd`/`working_dir`, set `auto_start: False`. Added `"remote"` guards in `start_service()` and `stop_service()` dispatch so Overseer won't attempt to start/stop/restart a remote service. Updated `startup()` to monitor remote services like Windows services (just health-check, no process management).

**Architecture clarification:** Three machines — Kiosk PC (.142), MainPC (.71), Print PC (.242 w/ PT-P700). PT-D610BT is on .178 (not set up). Config already pointed to `http://10.1.1.242:5002`.

**Files modified:** `tool-kiosk/static/style.css`, `tool-kiosk/templates/kiosk.html`, `1. Proshop Automations/Overseer/overseer.py`

---

## 2026-04-06

### Project 19: Shop Scheduler — Scheduler Fixes Batch

**Task:** Three bug fixes: (1) completed WOs still showing as blocks on the board, (2) no work center mappings for MILL-X-CAT40/MILL-X-PROBE so the suggestion engine couldn't route by machine capability, (3) T2 lathe ops appearing on the "needs tools" list when tooling can't be staged for the lathe.

**What was done:**
- **Fix 1:** Added `w.status = 'active'` filter to `get_schedule_blocks()` so the API never returns blocks for completed WOs. Added cleanup in `full_sync()` to delete non-locked, non-complete blocks when WOs are marked complete.
- **Fix 2:** Added `MILL-X-CAT40` and `MILL-X-PROBE` to `work_center_map` (migration + seed). Updated suggestion engine with `CAT40_MILL_IDS` (mill-1,2,3,6,8) and `PROBE_MILL_IDS` (mill-1,2,3,8) so ops route to capable machines only.
- **Fix 3:** Added `work_center != "T2"` filter to the needs-tools list builder in `app.py`.

**Files:** `database.py`, `sync.py`, `suggest.py`, `app.py`

---

### Project 25: Agent Exploration — Overseer Watchdog + Audit Alert Redesign

**Task:** (1) Add the Overseer (Flask dashboard, port 8060) as a monitored subprocess to `service_wrapper.py` so it auto-restarts on crash — it had been down silently for a full week after March 30. (2) Redesign the Telegram audit notifications from noisy hourly "Score: X%" messages to a useful daily digest with actionable items.

**What was done:**

**1. Added Overseer watchdog to `service_wrapper.py`:**
- Added constants: `OVERSEER_PYTHON` (system Python at `Programs\Python314`), `OVERSEER_SCRIPT` (path to `1. Proshop Automations/Overseer/overseer.py`), `OVERSEER_DIR`
- Why separate Python path: Flask and requests are installed under the system interpreter, not necessarily the one running service_wrapper
- Added `start_overseer()` — launches overseer.py as subprocess, logs stdout/stderr to `logs/overseer_stdout.log`, sets cwd to Overseer directory
- Added `check_overseer()` — polls `.poll()`, restarts with exponential backoff (30-300s) if crashed, resets backoff after 5 min sustained uptime
- Added `stop_overseer()` — `.terminate()` with 10s timeout, then `.kill()`
- Integrated into all control points: `_become_leader()`, `_leader_tick()`, `stop_all()`, `get_status()` (heartbeat now includes overseer status + PID)
- Follows the exact same pattern as the existing telegram_bot management

**2. Redesigned Telegram audit alerts (`alerter.py` — full rewrite):**
- **Before:** Every audit run (hourly) could send "Score: 25.9%" with pass/warn/fail counts — not actionable, too frequent
- **After:** Two alert modes:
  - **Daily digest** (once per day, first run after 6 AM): Overdue WOs by name, overrun rate + worst offenders, readiness issues (uncertified ops, missing NC programs, outstanding material POs), machine health (stale FOCAS connections, alarm counts), summary counts
  - **Immediate alerts**: Only for genuinely new system **errors** (API down, DB unreachable) that weren't in the previous run — not for every new failure/warning
- Uses `logs/last_digest.json` state file to track when last digest was sent
- Hourly audit still runs for data collection and trending — only notification behavior changed

**3. Added `get_run_metrics()` to `audit_db.py`:**
- New method to retrieve all metrics for a given run_id as a dict `{name: (value, context)}`
- Needed by the daily digest to pull actionable metrics like `overrun_rate_pct`, `overdue_work_orders`, `outstanding_material_pos`, etc.

**Files modified:**
- `25. Agent Exploration/service_wrapper.py` — Overseer subprocess management (start/check/stop + all integration points)
- `25. Agent Exploration/alerter.py` — Full rewrite: daily digest + critical-only immediate alerts
- `25. Agent Exploration/audit_db.py` — Added `get_run_metrics(run_id)` query method

**Files NOT modified:**
- `1. Proshop Automations/Overseer/overseer.py` — untouched, just managed as a subprocess now
- `25. Agent Exploration/run_audit.py` — untouched, still calls `send_audit_alert()` with same signature
- The VBS/Startup shortcut for Overseer — left in place as fallback until wrapper approach is verified

**Key decisions:**
- Overseer uses system Python (`Programs\Python314\python.exe`) not `sys.executable`, because Flask/requests are installed there
- Daily digest fires once per day at first audit run after 6 AM — simple and predictable
- Immediate alerts restricted to severity="error" only (system health failures), not "failure" or "warning" — avoids noise from known data quality issues
- Audit still runs hourly for data trending — decoupled notification frequency from collection frequency

**Verification steps (to be done):**
1. Stop the currently-running manual Overseer instance
2. Restart the service_wrapper (or let its leader tick pick up the new code)
3. Confirm the Overseer starts and port 8060 responds
4. Kill the Overseer process manually — confirm auto-restart within 30s
5. Check `service_heartbeat.json` — confirm overseer status appears
6. Wait for next audit run — confirm no hourly Telegram message (only daily digest)

### Project 22: Tool Assembly Management — Cleanup, Inventory Import, Touchscreen

**Task:** Clean up the tool-kiosk directory, import ProShop tool library into inventory, fix touchscreen, and get Full Inventory sessions working properly.

**What was done:**

1. **Directory cleanup** — Moved 11 non-essential files (one-time scripts, debug utils, old shortcuts) to `tool-kiosk/old/`. Created `INSTRUCTIONS.txt` with start/stop/restart procedures.

2. **Touchscreen fix** — Diagnosed touch not working on Kiosk PC. Added `/touch-test` diagnostic page to Flask. Confirmed it was a Windows display-touch mapping issue (not code). Created `Fix Touchscreen.md` guide.

3. **ProShop tool import** — Fixed `get_all_tools()` in `proshop_client.py` (removed unsupported `page` arg, set `pageSize=1000`). Imported 907 tools, deleted 365 auto-generated D10xxx drill catalog entries. Added D10xxx filter to import endpoint. 542 tools now in inventory.

4. **Inventory sort order** — Changed all 3 inventory queries in `database.py` from alphabetical to numeric sort by suffix: `ORDER BY CAST(REPLACE(LTRIM(...), '-', '') AS INTEGER)`. Tools now go A1, R2, O3, O4... instead of A1, A10, A1002...

5. **Inventory session management** — `startFullInventory()` now reuses open sessions instead of creating duplicates. Added Abandon button + `POST /api/inventory/session/<id>/abandon` endpoint. Cleared 4 orphaned sessions.

6. **Browser caching disabled** — Added `@app.after_request` with `Cache-Control: no-cache` headers. Removed `?v=N` cache busters from templates.

7. **Chrome crash loop** — Identified 36+ consecutive Chrome crashes from `kiosk_launcher.log`. Fix: delete corrupted `%LOCALAPPDATA%\ToolKioskChromeProfile`.

8. **STOP KIOSK.bat** — Added fallback methods to close the launcher console window.

**Lesson learned:** Dropbox sync + Python `__pycache__` is unreliable — the Kiosk PC can run stale bytecode even when .py files are synced. Must delete `__pycache__` on the Kiosk PC after code changes.

**Files modified:** `app.py`, `database.py`, `proshop_client.py`, `kiosk.js`, `kiosk.html`, `base.html`, `STOP KIOSK.bat`. New: `INSTRUCTIONS.txt`, `Fix Touchscreen.md`, `SESSION_LOG.md` (project-level).

---

## 2026-04-02

### Project 12: FASData Implementation — TraxisProgramManager Testable Architecture

**Task:** Extract all non-Fusion logic from the 1404-line monolithic Fusion 360 add-in (TraxisProgramManager.py) into a testable `tpm/` Python package, add comprehensive pytest coverage, and wire the monolith to use the package.

**What was done:**

**1. Created `tpm/` package (5 modules, ~610 lines):**
- `tpm/config.py` — Dropbox root detection, paths, credential loading
- `tpm/proshop.py` — OAuth token caching, GraphQL client, customer PN lookup
- `tpm/naming.py` — OP numbers, versioning, header parsing
- `tpm/fileops.py` — File discovery, copy, auto-catch, folder lookup
- `tpm/wcs.py` — WCS formatting (pure string logic, zero dependencies)

**2. Created test suite (52 tests across 6 files, all passing in 0.18s):**
- `test_auto_catch.py` (8 tests) — Recent file copy, PART FILES copy, no recent files, self-copy skip, empty folders, multiple files, partial failure, ProShop down graceful degradation
- `test_naming.py` (15 tests) — OP formula (setup 1->60, 2->70, 6->110), program numbers, header parsing, version increment with has_changes flag
- `test_fileops.py` (6 tests) — Folder lookup by customer/part PN, file copy
- `test_proshop.py` (6 tests) — Token caching/refresh, missing creds, customer PN lookup
- `test_config.py` (5 tests) — Dropbox detection via info.json, credential loading
- `test_wcs.py` (9 tests) — Stock/model/selected origins, all axis combinations

**3. Rewired monolith to use tpm/ package (1404 -> 915 lines):**
- Added `from tpm import config, proshop, naming, fileops, wcs` at top
- Replaced all internal calls: `get_operation_number()` -> `naming.get_operation_number()`, etc.
- Added `_FusionLogHandler` bridge in `run()` — routes `tpm.*` logging to Fusion console
- Changed `get_next_version(setup=)` -> `get_next_version(has_changes=)` (bool instead of adsk object)
- Changed `find_part_files_folder()` to accept explicit `customer_part_number=` param
- Moved Dropbox-missing error from module-level RuntimeError to `run()` messageBox

**4. Initialized git repo and committed:**
- 3 commits on main: v1.4.0 (initial), CHANGELOG, v1.6.0 (this refactor)
- Git identity configured (Wolfgang / wolf@traxismfg.com)
- `.gitignore` updated with `.pytest_cache/`

**Key decisions:**
- `tpm/` modules use stdlib `logging` (not `adsk.core.Application.get().log()`) — testable outside Fusion
- `DROPBOX_ROOT` defaults to `None` in config (no RuntimeError) — Fusion entry point handles the error with a user-friendly messageBox
- `auto_catch_posted_files()` takes `search_folders` and `delay` params so tests can inject temp dirs and skip sleeps
- Kept all `adsk.*`-dependent code in monolith: 6 handler classes, CAM parameter helpers, WCS/tool extraction, setup naming application

**Status:** Phase 1-3 complete. Phase 4 (Fusion in-app verification) pending — need to test in Fusion: TPM dialog, post, auto-catch.

---

## 2026-04-01

### Project 9: Shop Floor Cameras — BLE Proximity Time Tracking System

**Task:** Research and design an automatic time tracking system that detects which worker is at which machine using proximity sensing, replacing tedious manual time entry in ProShop.

**What was done:**

**1. Evaluated tracking approaches:**
- Discussed camera/gait analysis (too complex for shop environment), RFID tap-based (still requires interaction), and BLE proximity (fully passive — chosen approach)

**2. Created comprehensive research document:**
- `9. Shop Floor Cameras/9.BLE-Proximity-Time-Tracking-System.md`
- Full system architecture: BLE badges on workers → USB BLE dongles on station PCs → MQTT broker → Python proximity engine → database + Grafana dashboard → ProShop integration
- Identified ProShop API blocker: `users:w` scope blocked for API clients (time tracking mutations won't work). Documented 5 workaround options ranked by feasibility
- RSSI calibration strategy for metal shop environment (multipath, shielding, per-machine thresholds)
- Integration plan with existing FOCAS monitoring (combines "who is there" with "what program is running")
- 4-phase implementation roadmap

**3. Simplified hardware approach:**
- Original plan: dedicated BLE gateways ($35/ea) + PoE switch + new cable runs (~$900)
- Discovered each machine already has a Windows PC on the network → use USB BLE dongles ($12/ea) on existing PCs instead
- Pilot cost dropped from ~$900 to ~$42

**4. Mapped full shop network:**
- Documented 9 machine station PCs (Stations A–I) with IPs on 10.1.1.x
- 3 office PCs (TRAXIS PC at 10.1.1.71, plus .242 and .178)
- 5 FOCAS CNC controllers (M2, M3, M6, M8, T2)
- Ran network scan — discovered 17 devices including NVR (surveillance cameras are on the network at 10.1.1.76), Brother printer, Polycom phone, smart thermostat
- Station PCs don't respond to ping/SMB (Windows firewall) but are online — outbound MQTT will work fine

**5. Hardware ordered (Amazon, arriving Monday April 7):**

| Item | Details | Cost | Order # |
|------|---------|------|---------|
| ASUS USB-BT500 BLE 5.0 dongle | + INLAND 10-pack USB drives | $90.75 | (arriving tomorrow) |
| XBOHJOE USB extension cable 6ft | USB 3.0 A male to female | $10.81 | 113-0450575-0218623 |
| Feasycom BLE 5.1 Beacon Cards (x2) | DA14531, IP66, iBeacon, NFC | $41.12 | 113-0264462-9415452 |

**Total pilot cost:** ~$52 (dongle + cable + 2 beacons, excluding USB drives)

**Key findings:**
- T1 (Okuma Lathe) is retired from the shop
- Metal PC cabinets will block BLE signal — USB extension cable routes dongle outside cabinet
- Badge TX power is configurable from the badge side via phone app (not the dongle)
- Feasycom FSC-BP105N chosen: credit card form factor, IP66, 6-year battery, ~$20/ea on Amazon

**Next steps:**
- [ ] Test BLE dongle + beacon at one machine (RSSI readings, range, metal interference)
- [ ] Write Python BLE scanner script using `bleak` library
- [ ] Set up Mosquitto MQTT broker on TRAXIS PC
- [ ] Probe ProShop `timeClockPunchIn`/`addTimeClockPunch` mutations (may bypass `users:w` restriction)
- [ ] Contact Adion Systems about enabling `users:w` scope for API clients

**Files created/modified:**
- `9. Shop Floor Cameras/9.BLE-Proximity-Time-Tracking-System.md` — Full research & architecture document
- `9. Shop Floor Cameras/scan_network.ps1` — PowerShell network scanner
- `9. Shop Floor Cameras/scan_network_tcp.ps1` — TCP port scanner for firewalled PCs

---

## 2026-03-30

### Project 25: Agent Exploration — Service Wrapper with Leader Election Failover

**Task:** Build a single service that runs on both home PC and collector PC (10.1.1.71), using leader election so whichever machine is on runs all services. Replaces individual Windows Task Scheduler entries with one managed wrapper.

**What was done:**

**1. Created `service_wrapper.py` — leader-elected service manager:**
- Heartbeat-based leader election via `service_heartbeat.json` (synced through Dropbox)
- Leader writes heartbeat every 60s; heartbeat considered stale after 180s
- Standby polls every 30s, promotes to leader when heartbeat goes stale
- Priority tiebreaker: `"primary"` outranks `"normal"` (hostname map + env var override)
- Leader manages 4 services:
  - `telegram_bot.py`: long-running subprocess, monitored and restarted on crash with exponential backoff (30-300s)
  - `check_reminders.py`: one-shot every 15 min (300s timeout)
  - `run_audit.py`: one-shot every 60 min (300s timeout)
  - `scan_projects.py`: one-shot daily at midnight (600s timeout)
- Graceful shutdown: catches SIGTERM/SIGINT/SIGBREAK, stops bot subprocess, clears heartbeat
- Atomic heartbeat writes via tmp file + `os.replace()`
- Main loop: 10s tick, manages election state machine (LEADER/STANDBY/SHUTDOWN)
- CLI flags: `--status` (show current heartbeat), `--once` (test one election cycle)
- Logging to `logs/service_wrapper.log` + console

**2. Created `install_service.bat` — NSSM install script:**
- Uses NSSM (Non-Sucking Service Manager) to install as Windows service `TraxisAgent`
- NSSM wraps any executable as a proper Windows service (start on boot, restart on crash, log rotation)
- Auto-detects Python path and NSSM location (`Graf\services\nssm-2.24\win64\nssm.exe`)
- Configures: auto-start, log rotation at 5MB, 10s restart delay, graceful console shutdown (15s)
- Handles existing service (stops + removes before reinstall)
- Prompts to start service after install

**3. Updated CLAUDE.md:**
- Architecture diagram: added service_wrapper.py, install_service.bat, service_heartbeat.json, logs/
- Running section: added service wrapper commands
- Scheduling section: documents wrapper internals + leader election, preserves legacy Task Scheduler entries with "remove after verified" note
- Next steps: marked item 8 (deploy telegram_bot as service) DONE
- Telegram bot section: updated from "needs deployment as service" to "managed by service_wrapper.py"

**4. Bug fixes discovered during live testing:**
- **Heartbeat thread**: One-shot tasks (audit, reminders) run via blocking `subprocess.run()`, which froze the main loop for minutes during audit. Heartbeat could go stale (>180s) and trigger false failover. Fixed by moving heartbeat writes to a background daemon thread that runs independently of the main loop.
- **Bot start order**: Heartbeat was written before bot started, so first heartbeat showed `telegram_bot: stopped`. Fixed by starting bot first, then writing heartbeat.
- **Bot output logging**: Bot subprocess stdout/stderr were sent to DEVNULL, making crash debugging impossible. Changed to append to `logs/telegram_bot.log` with `-u` (unbuffered) flag.
- **Env var pre-resolution**: Child processes (telegram_bot.py, etc.) couldn't see Windows User env vars when launched from Git Bash. Added `_resolve_env_vars()` at wrapper startup -- resolves `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` via PowerShell and sets them in `os.environ` so all children inherit them.
- **Missing package**: `python-telegram-bot` wasn't installed on home PC. Installed v22.7.

**5. Environment setup on home PC (DESKTOP-NU8H1LI):**
- Set `TELEGRAM_BOT_TOKEN` as Windows User env var (retrieved from user)
- Set `TELEGRAM_CHAT_ID` as Windows User env var (retrieved via bot API getUpdates: `8740842967`)
- Set `ANTHROPIC_API_KEY` as Windows User env var (retrieved from Project 10's `.claude/settings.local.json`)

**Testing:**
- `--status` with no heartbeat: correctly reports "No service running"
- `--once`: elected leader, started telegram_bot subprocess, stopped cleanly, cleared heartbeat
- Foreground run: leader elected, bot started (PID alive, 87MB memory), reminders ran, audit ran (exit code 1 = findings, expected)
- Heartbeat thread verified: timestamp refreshed at 60s mark while audit was still blocking main loop (audit took ~4 min)
- Bot crash/restart cycle verified: exponential backoff worked correctly (30s -> 60s -> 120s) when bot couldn't start due to missing package
- After env var fix + package install: bot stays running, heartbeat shows `status=running`

**Key design decisions:**
- NSSM chosen over native win32serviceutil (simpler, already available in Graf\services\)
- Heartbeat file approach (vs network-based) because Dropbox sync is already the shared medium
- Priority map with env var override so collector PC can be set as primary without code changes
- Exponential backoff on bot restart (30s -> 60s -> 120s -> 300s cap) to avoid thrashing
- Heartbeat in daemon thread (like P18 Message Notifier pattern) to stay fresh during blocking operations

**Next steps:**
1. ~~Run `python service_wrapper.py` foreground to verify sustained operation~~ DONE
2. Install via `install_service.bat` (run as Admin), verify `net start TraxisAgent`
3. Get collector PC hostname, add to PRIORITY_MAP as `"primary"`
4. Deploy to collector PC (set env vars, install packages, run install_service.bat)
5. Verify failover in both directions
6. Remove legacy Task Scheduler entries (TraxisAudit, TraxisReminderCheck, TraxisProjectScanner)

---

### Project 17: COTS Tools Crib Kiosk — Touchmonitor Launcher Setup

**Task:** Get the COTS kiosk running again after a break; create a one-click launcher for the touchmonitor PC (10.1.1.70).

**What was done:**

1. **Created `launch_kiosk.bat`** — all-in-one launcher that:
   - Kills any existing kiosk server process
   - Sets the ProShop API secret
   - Starts the Flask server minimized in the background
   - Polls `/api/health` until server is ready (up to 15s)
   - Opens Chrome in kiosk mode (fullscreen, no address bar) to `http://localhost:5000`
   - Located at: `cots-kiosk/launch_kiosk.bat`

2. **Touchmonitor Dropbox sync** — enabled selective sync on the touchmonitor (10.1.1.70) for the `17. COTS - Tools Crib Kiosk` folder so the launcher and all kiosk code syncs over automatically.

3. **Desktop shortcut on TRAXIS PC** — created `COTS Crib Kiosk.lnk` on `C:\Users\TRAXIS\Desktop` pointing to `run_kiosk.bat`. Touchmonitor shortcut to be created manually after Dropbox sync.

**Key decisions:**
- Used `launch_kiosk.bat` (new) vs `run_kiosk.bat` (existing) — old one kept for manual/debug use, new one is the touchmonitor launcher
- Chrome `--kiosk` mode for fullscreen touchscreen experience (Alt+F4 to exit)
- Server starts minimized so the console doesn't cover the kiosk UI

**Status:** In progress — launcher created and syncing to touchmonitor. May need adjustments after first real test on the touchscreen.

---

### Project 22: Tool Assembly Management — Print Service Fix + RTA Label

**Task:** Kiosk PC on shop floor can't print RTA stickers; also print the latest RTA label (H-0024, registered today).

**What was done:**

1. **Diagnosed print connectivity issue:**
   - Both kiosk app (port 5001) and print service (port 5002) run on MainPC (10.1.1.71)
   - Brother PT-P700 is connected and available
   - JavaScript in the kiosk browser was calling `http://10.1.1.71:5002/api/print-label` directly (cross-origin from :5001)
   - Windows Firewall had **no inbound rules** for port 5002 — requests from the shop floor kiosk PC never reached the print service
   - Print service logs confirmed: only `127.0.0.1` health checks, zero remote requests ever

2. **Added firewall rule** for port 5002 (TCP inbound) — still didn't work from kiosk browser (likely additional cross-origin/network issue)

3. **Fixed with print proxy route** — the real solution:
   - Added `/api/print-label` proxy in `app.py` (port 5001) that forwards to `localhost:5002` server-side
   - Updated `kiosk.js` to call `/api/print-label` (same origin) instead of the direct `http://10.1.1.71:5002` URL
   - Bumped JS cache version to v=12 in `kiosk.html`
   - Browser now only talks to port 5001 (already working); server proxies to print service locally — no CORS or firewall issues

4. **Printed H-0024 label** — 2 copies via b-PAC on PT-P700 (CAT40 ER25, tool O51, no RTA# yet)

**Key decisions:**
- Server-side proxy is more robust than firewall rules for cross-port browser requests
- `requests` library used for proxy (already a dependency)

**Status:** Code changes saved. Kiosk app needs restart for proxy route to take effect. Pending shop floor verification.

---

## 2026-03-28

### Project 25: Agent Exploration — Absorb Project 10, Lathe Mapping, Reminders, Telegram Bot, Nightly Scanner

**Task:** Major expansion session. Merged Project 10 (Conversational ProShop) into Project 25's agent.py so there's one NL interface for everything. Built lathe program mapping infrastructure. Added a full reminder system. Built a Claude-powered Telegram bot for phone access to all 25 projects. Created a nightly project index scanner.

**What was done:**

**1. Absorbed Project 10 into agent.py:**
- Added 5 new query methods to `proshop_client.py`: `get_work_order()`, `get_work_order_time_tracking()`, `get_work_order_profitability()`, `get_part()`, `get_part_operations()`
- Added 6 new MCP tools to `mcp_tools.py`: `get_work_order`, `get_work_order_time_tracking`, `get_work_order_profitability`, `get_part_info`, `get_part_operations`, `search_work_orders`
- `search_work_orders` uses Project 10's status mapping (open/active/complete/late/due this week/shipped)
- ProShop server now has 10 tools (was 4)
- Switched `agent.py` interactive mode from stateless `query()` to stateful `ClaudeSDKClient` -- conversation context preserved between turns
- Enriched system prompt with ProShop domain knowledge: WO number format (YY-NNNN), time units (seconds), status aliases, tool selection guide, "keep responses SHORT"
- Renamed Project 10 folder to `10. Conversational Proshop - Retired`, added `RETIRED.md`

**2. Lathe program mapping (legacy T2 programs):**
- Created `lathe_programs.json` -- mapping template for O-number -> ProShop part number
- Added `get_program_mappings()` to `config.py` -- loads and validates mapping file
- Integrated into `get_active_programs` FOCAS tool -- auto-enriches running programs with `mapped_part_number`, `mapped_description`, `mapped_op_number`
- Problem: T2 lathe programs predate TPM header system, stay resident on machine, reused across jobs

**3. Reminder system:**
- Added `reminders` table to `audit_db.py` with methods: `add_reminder()`, `get_pending_reminders()`, `get_due_reminders()`, `mark_reminder_sent()`, `cancel_reminder()`
- Added 3 MCP tools: `schedule_reminder`, `list_reminders`, `cancel_reminder` + new `create_reminders_server()`
- Created `check_reminders.py` -- polls DB every 15 min (Task Scheduler: `TraxisCheckReminders`), sends due reminders via Telegram
- Injected current datetime into agent system prompt via `_make_options()` so Claude knows what time it is

**4. Notes system:**
- Added `notes` table to `audit_db.py` with methods: `add_note()`, `get_recent_notes()`, `search_notes()`
- Used by Telegram bot for thought capture

**5. Telegram bot (`telegram_bot.py`):**
- Claude-powered (Sonnet) Telegram listener using `python-telegram-bot` + `anthropic` SDK
- System prompt dynamically loads `project_index.json` with all 25 projects, pending reminders, recent notes
- 6 Claude tools: `save_note`, `schedule_reminder`, `list_reminders`, `cancel_reminder`, `search_notes`, `get_project_status`
- Slash commands: `/status`, `/notes`, `/reminders`, `/projects`
- Only responds to authorized chat ID (Wolfgang's Telegram)
- Maintains conversation history (30 turns) within a session
- Installed `python-telegram-bot` and `anthropic` pip packages

**6. Project index (`project_index.json`):**
- Surveyed all 25 project folders (3 parallel agents reading CLAUDE.md, README.md, source files)
- Structured JSON: id, name, short description, status, affects, subprojects, waiting_on, needs_from_user
- Cross-reference map: which projects share ProShop API, FOCAS, Fusion add-ins, Overseer
- Action items for Wolfgang extracted: 6 items with effort estimates

**7. Nightly scanner (`scan_projects.py`):**
- Reads per project: CLAUDE.md, README.md, session_log.md (recursive), master SESSION_LOG.md (latest entries), Claude Code MEMORY.md, file modification timestamps
- Uses Claude Haiku (~$0.02/run) to extract status, blockers, needs_from_user
- Updates project_index.json nightly (preserves static fields, refreshes dynamic)
- Rebuilds action items list automatically
- Scheduled at midnight via Task Scheduler: `TraxisProjectScan`
- Supports `--dry-run`, `--project N` for testing
- Checks both C: and D: drives for Claude memory (collector PC uses D:)

**8. Config fix for Git Bash:**
- Added `_get_env()` helper to `config.py` -- falls back to PowerShell `[Environment]::GetEnvironmentVariable()` when Git Bash can't see Windows User env vars
- Applied to `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`
- Set `ANTHROPIC_API_KEY` as Windows User env var (was only in P11's .env file)

**Key decisions:**
- Stateful `ClaudeSDKClient` for interactive mode, stateless `query()` for one-shot (best of both)
- Reuse existing `@traxis_audit_bot` Telegram bot rather than creating a new one
- `audit.db` as single SQLite database for audit results, reminders, AND notes (no new dependencies)
- Claude Haiku for nightly scanning (cheap, handles unstructured CLAUDE.md content)
- Project index is the knowledge base -- bot reads it fresh each message, scanner updates it nightly

**Files created:**
- `lathe_programs.json` -- legacy lathe program mapping template
- `telegram_bot.py` -- Telegram bot with Claude + tools
- `check_reminders.py` -- reminder delivery polling script
- `scan_projects.py` -- nightly project index scanner
- `project_index.json` -- structured index of all 25 projects
- `10. Conversational Proshop - Retired/RETIRED.md` -- retirement notice

**Files modified:**
- `proshop_client.py` -- 5 new query methods
- `mcp_tools.py` -- 9 new MCP tools, 1 new server, status mapping, date parsing
- `agent.py` -- stateful client, enriched prompt, datetime injection, reminders server
- `audit_db.py` -- reminders + notes tables and methods
- `config.py` -- `_get_env()` PowerShell fallback, `get_program_mappings()`, lathe programs path

**Scheduled tasks created:**
- `TraxisCheckReminders` -- every 15 min, sends due reminders via Telegram
- `TraxisProjectScan` -- daily at midnight, refreshes project_index.json

**Status:** Complete. Bot tested and responding on Telegram. Scanner tested. All code syntax-verified.

---

### Project 10: Conversational ProShop — RETIRED

**Task:** Retire Project 10 after absorbing its features into Project 25.

**What was done:**
- All useful features ported: single-WO queries, time tracking, profitability, part lookups, status filtering, conversation memory, domain knowledge
- Folder renamed to `10. Conversational Proshop - Retired`
- Added `RETIRED.md` documenting what was ported and why
- `query_templates.py` preserved as GraphQL field name reference

**Status:** Retired. Absorbed into Project 25 agent.py.

---

## 2026-03-16

### Project 20: Traxis Data — Rene Data Collection Guide, Privacy Setup & Target Hours Pipeline

**Task:** Multiple tasks across two sessions: (1) Create a data collection guide for Rene to gather QuickBooks/bank/utility data for the financial model. (2) Set up data privacy controls so Claude Code can only access anonymized data. (3) Set up Rene's machine with Claude Code. (4) Move token_map.json to shared Dropbox. (5) Build a pipeline to set target hours on 152 ProShop parts missing targets, writing `minutesPerPart` back via the GraphQL API.

**What was done:**

**Rene Data Collection Guide:**
- Created `RENE_DATA_COLLECTION_GUIDE.md` with 14 items across 3 phases (QuickBooks, Bank, Utilities)
- Includes priority table showing items 1-4 unlock 80% of the financial model
- Clear 3-step workflow section: (1) Rene exports raw data to folders, (2) Rene runs `anonymize.py` from terminal, (3) Claude Code analyzes anonymized output
- FASData section deferred (still under development per Project 12)
- Created `RENE_SETUP.md` with step-by-step setup: Python, Node.js, Claude Code installation, Dropbox verification, anonymizer test

**Data Privacy Controls:**
- Created `20. Traxis Data/.claude/settings.json` with deny rules blocking Claude Code from reading `quickbooks/`, `bank/`, `utilities/`, `token_map.json`, and `.env` files
- Allow rules for `anonymized/`, `proshop/`, `*.md`, `*.py`, `*.csv`
- Bash deny rules for `*token_map*`, `*quickbooks/*`, `*bank/*`, `*utilities/*`
- Updated `CLAUDE.md` with mandatory data privacy section

**Token Map Migration:**
- Moved `token_map.json` from `C:\Users\TRAXIS\Documents\` to `20. Traxis Data/` (Dropbox-synced between machines)
- Updated 6 scripts that referenced the old path:
  - `anonymize.py`, `proshop_pull.py`, `merge_fresh.py`, `proshop_merge_and_analyze.py`, `proshop_pull_gaps.py`, `proshop_pull_invoices.py`
- All now use `SCRIPT_DIR / "token_map.json"`
- Updated `MEMORY.md`, `setup.md`, `CLAUDE.md` with new location

**Target Hours Pipeline — Discovery & Architecture:**
- Investigated where target hours live in ProShop: Part Operations → `minutesPerPart` field (not on Part or WorkOrder directly)
- WO's `hoursCurrentTarget` = sum of all operation `minutesPerPart` values (read-only via API, computed from ops)
- Discovered `updatePartOperation` mutation: takes `partNumber`, `opNumber`, `opDefinition: { minutesPerPart: String }` — arg name is `opDefinition` NOT `data`
- Discovered `updatePart` mutation: takes `partNumber`, `data: { notes: String }` — arg name IS `data`

**Target Hours Pipeline — `best_targets.py` Rewrite (critical fix):**
- **Bug caught by Wolfgang:** Original script computed targets from total WO hours without dividing by quantity. Since `minutesPerPart` is per ONE part and WOs have varying quantities (1 to 1,000), targets were completely wrong.
- Rewrote to normalize by quantity: `hrs_per_part = actual_hours / qty_ordered` for each WO
- P25+10% methodology applied to per-part values (not total WO hours)
- Output column `Best Min/Part` maps directly to ProShop's `minutesPerPart`
- Excludes CUST_018 (internal work — fixtures, jigs, tooling mods)
- Skips WOs with zero/missing quantity data (3 WOs)
- Result: 127 parts analyzed, 35 high confidence (5+ runs), 22 medium (3-4), 70 low (1-2)

**Target Hours Pipeline — `set_targets.py` (new script):**
- Three modes: `--query` (read-only), `--preview` (show mutations), `--execute` (write to ProShop)
- `--query`: Pulls all 1,014 parts with nested operations from ProShop, matches against `best_targets_list.csv` using reverse token map, outputs `proshop/part_operations_audit.csv`
- Even distribution: total minutes per part split evenly across operations (placeholder for Wolfgang to refine per-op)
- `--execute`: Runs `updatePartOperation` on each op + `updatePart` to add conspicuous note ("AUTO-SET TARGETS [...]: Per-part target: X min distributed evenly... Per-op breakdown needs manual refinement")
- Safety: requires typing "YES" to proceed, 0.5s delay between mutations, logs every result to CSV
- Result: 118 parts matched in ProShop, 7 not found (likely deleted/archived)

**Bugs Fixed:**
- `sys.stdout` buffering: background Python produced no output — fixed with `line_buffering=True` + `python -u`
- `workCenter` field is an object type, not scalar — removed from query (ProShop returned "Expected a selection on object field")
- `company` field same issue — removed
- No exit condition on persistent failures — added `if total_records is None and page_start > 200: break`
- Retry loop didn't show error messages — added extraction of `result["errors"][0]["message"]`

**Key decisions:**
- Distribute target hours evenly across operations as a starting point — Wolfgang refines per-op breakdown manually
- Add conspicuous note to each part so operators know targets are auto-set placeholders
- CUST_018 excluded from analysis — internal fixtures/jigs, not billable production work
- Privacy enforced at two layers: `.claude/settings.json` deny rules (hard) + `CLAUDE.md` instructions (soft) + anonymizer workflow (data transformation)

**Files created:**
- `20. Traxis Data/RENE_DATA_COLLECTION_GUIDE.md` — 14-item data collection guide with 3-step anonymization workflow
- `20. Traxis Data/RENE_SETUP.md` — Machine setup instructions for Rene (Python, Node, Claude Code)
- `20. Traxis Data/.claude/settings.json` — Data privacy deny/allow rules
- `20. Traxis Data/set_targets.py` — 3-phase target hours pipeline (query/preview/execute)

**Files modified:**
- `20. Traxis Data/best_targets.py` — Rewritten for per-part normalization (hrs/qty), CUST_018 exclusion
- `20. Traxis Data/anonymize.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_pull.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/merge_fresh.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_merge_and_analyze.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_pull_gaps.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/proshop_pull_invoices.py` — TOKEN_MAP_PATH → `SCRIPT_DIR / "token_map.json"`
- `20. Traxis Data/CLAUDE.md` — Added mandatory data privacy section, updated token_map location
- `20. Traxis Data/setup.md` — Updated token_map location
- `MEMORY.md` — Updated token_map location to Dropbox path

**Files generated:**
- `20. Traxis Data/best_targets_list.csv` — 127 parts with per-part suggested targets (Best Min/Part column)
- `20. Traxis Data/proshop/part_operations_audit.csv` — 118 matched parts with operation structure + proposed values

**ProShop API discoveries:**
- `minutesPerPart` on Part Operations is the correct field for setting target hours
- `updatePartOperation(partNumber, opNumber, opDefinition: { minutesPerPart })` — returns Boolean
- `updatePart(partNumber, data: { notes })` — returns Part object
- `workCenter` and `company` are object types requiring sub-selection (not scalar)
- Part `operations` supports nested pagination: `operations(pageSize: 50, pageStart: 0)`

**Status:** Pipeline ready through `--query`. Audit CSV generated with 118 parts. Next steps: (1) anonymize audit CSV, (2) Wolfgang reviews low-confidence parts (70 with only 1-2 runs), (3) run `--preview` to inspect mutations, (4) run `--execute` after approval.

---

## 2026-03-26

### Project 19: Shop Scheduler — Overlap Prevention, Board Filters, Business Hours, Material Type

**Task:** Implement no-stacking overlap prevention, rich board filters, business-hours-only scheduling, and material type filter.

**What was done:**

**Overlap Prevention (backend + frontend):**
- Added `OverlapError` exception class and `_check_overlap()` query to `database.py`
- `create_schedule_block()` and `update_schedule_block()` reject overlapping non-complete blocks on same machine (HTTP 409)
- Frontend shows toast notification when drag/drop/resize is rejected due to overlap
- No stacking allowed, period — even same-WO side 1/side 2 ops

**Rich Board Filters (collapsible filter bar):**
- Collapsible filter bar below header with toggle button
- Text search (WO#, part name, op name, customer)
- Customer dropdown (auto-populated from events)
- Status checkboxes: Scheduled, Running, Complete (defaults: Scheduled + Running)
- Urgency checkboxes: Past Due, Urgent, Normal, No Date (all checked by default)
- Material status dropdown: All / Ready / Not Ready
- Tools status dropdown: All / Ready / Not Ready
- Clear Filters button
- Filter state persisted to localStorage across page reloads
- Badge shows count of hidden events when filters active
- Client-side filtering via `allEvents` array + `applyFilters()` → `ec.setOption('events', filtered)`

**Material Type Filter (full ProShop → UI chain):**
- Added `part { materialPlainText }` to ProShop `get_work_orders()` GraphQL query
- Added `material_type TEXT` column to `work_orders` table (auto-migrated via `_migrate()`)
- Sync extracts `materialPlainText` from part data, stores in `work_orders.material_type`
- Included `w.material_type` in block and operation SQL queries
- Added `material_type` to event `extendedProps` in API response
- New "All Materials" dropdown filter populated dynamically from events (aluminum, stainless, plastic, etc.)

**Business Hours & Weekend Handling:**
- Config: `BUSINESS_HOURS_START=5` (5 AM), `BUSINESS_HOURS_END=18` (6 PM)
- EventCalendar: `slotMinTime: '05:00:00'`, `slotMaxTime: '18:00:00'`
- Created `_add_business_hours()` helper in `suggest.py` — spreads op duration across business hours only, skipping nights and weekends
- Updated `_find_next_gap()` to use business-hours-aware duration calculation

**Clear Board Button:**
- Added `POST /api/blocks/clear` endpoint — deletes all non-locked, non-complete blocks
- Button in header with confirmation dialog, shows count of deleted blocks

**Readiness Key:**
- Small legend in filter bar showing what the 4 readiness dots mean: Prog, Mat, Tools, Machine

**Version Label:**
- Added `v0.5` label in header for quick visual confirmation of which version is running

**Bug Fixes (10+):**
- `_parse_dt()` infinite recursion — was calling itself instead of `datetime.fromisoformat()` (caused /api/suggestions 500 error)
- Python 3.14 timezone-aware datetimes from "Z" suffix — `_parse_dt()` strips timezone info
- `__pycache__` with stale cpython-313 AND cpython-314 files preventing code updates
- Two-machine conflict: home computer running old scheduler on port 5080 via Dropbox sync — switched to port 5081
- EventCalendar crash from `hiddenDays: [0, 6]` — not supported in resource timeline view, removed
- `flexibleSlotTimeLimits` expanding time range beyond business hours — removed
- Weekend scheduling: ops bleeding through Saturday/Sunday due to raw `cursor + duration_td`
- Auth: tried switching to FusionConnector (403), reverted to FusionToolAuditor (BA16-EFAF-B154)
- DB locks from Dropbox syncing between two machines

**Files modified:**
- `database.py` — OverlapError, _check_overlap, _migrate(), material_type column, updated queries
- `app.py` — overlap error handling (409), /api/blocks/clear, material_type in extendedProps
- `proshop_client.py` — added `part { materialPlainText }` to WO query
- `sync.py` — extract and store material_type from ProShop part data
- `suggest.py` — _parse_dt fix, _add_business_hours, _find_next_gap business-hours-aware
- `config.py` — business hours 5AM-6PM
- `templates/scheduler.html` — filter bar, toast container, clear board, readiness key, version label, material type dropdown
- `static/scheduler.js` — allEvents tracking, full filter system with localStorage, toast notifications, clearBoard, material type filter, calendar business hours
- `static/style.css` — filter bar styles, readiness key, toast styles, version label

**Key lessons:**
- When writing helper functions, don't accidentally call the function itself (recursive bug in `_parse_dt`)
- Python 3.14 `datetime.fromisoformat("...Z")` creates tz-aware datetimes — always strip with helper
- Dropbox + two machines running same app = port conflicts, DB locks, stale code served
- `hiddenDays` and `flexibleSlotTimeLimits` crash EventCalendar in resource timeline view
- Delete `__pycache__` when switching Python versions or after code changes

**Status:** All features implemented. Material type needs verification after ProShop sync (field name `materialPlainText` may differ). Auto-schedule flow needs end-to-end test on shop-connected machine.

---

### TPM Bug Fix — Dynamic Dropbox Path Detection

**Task:** Fix `FileNotFoundError: [WinError 3] The system cannot find the path specified: 'D:\'` crash in TraxisProgramManager when running on a machine without a D: drive.

**Root cause:** `NC_PROGRAMS_ROOT` and `PART_FILES_ROOT` were hardcoded to `D:\Dropbox\...` in `TraxisProgramManager.py` (line 68-69). Machine has Dropbox on C: drive.

**What was done:**
- Added `_find_dropbox_root()` helper that reads `%LOCALAPPDATA%/Dropbox/info.json` (maintained by Dropbox on every machine) to auto-detect the Dropbox folder path
- Replaced hardcoded `D:\Dropbox\...` paths with `os.path.join(_DROPBOX, ...)` so TPM works on any machine regardless of drive letter or Dropbox location
- Raises a clear `RuntimeError` at add-in startup if Dropbox isn't installed, instead of failing deep in `makedirs`

**Files changed:**
- `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\TraxisProgramManager\TraxisProgramManager.py` — replaced constants with dynamic detection

---

## 2026-03-25

### Project 19: Shop Scheduler — Readiness Lights, Tool-Aware Scheduling, Part Drawing, Fusion ToolRenumber

**Task:** Implement 4-phase plan: readiness indicators per operation, tool-aware machine assignment, part drawing in side panel, and Fusion 360 tool renumbering add-in.

**What was done:**

**Phase 1 — Data Foundation (all complete):**
- Added 3 new DB tables: `readiness`, `machine_pockets`, `operation_tools`
- Program readiness: auto-computed per WO (checks if Programming op is complete)
- Material readiness: queries `vendorPOs` with `poType=Material`, checks `receivedDate` on `poItems`
- Machine pocket sync: pulls pocket layouts from ProShop for all 9 active machines
- Operation tool requirements: syncs `partOperation.tools` for all active WOs

**Phase 2 — Readiness UI (all complete):**
- 4 colored dots per operation: Program (green/red), Material (green/red), Tools (green/yellow), Machine (green/gray)
- Dots appear in backlog panel, Gantt blocks (bottom-right corner), and side panel (large with labels)
- Manual "Mark Tools Staged" toggle button in side panel
- API: enriched `/api/operations` and `/api/blocks` with readiness data, added `POST /api/operations/<id>/tools-ready`

**Phase 3 — Tool-Aware Scheduling (complete):**
- `_tool_overlap_score()` compares op tools vs machine pockets by tool_number AND out_of_holder (0.1" stickout tolerance)
- When multiple mills have similar load (within 2h), uses tool overlap as tiebreaker
- Suggestions include tool_match/tool_total fields, shown as "(X/Y tools)" badge on suggestion chips
- Updates `machine_ready` flag in readiness table

**Part Drawing in Side Panel (complete, untested on ProShop network):**
- `get_part_drawing(wo_number)` queries `part.partFiles.partfile` (primary drawing), falls back to `workOrderFiles`
- `/api/workorders/<wo>/drawing` endpoint returns URL + type (pdf/image)
- Side panel async-fetches drawing when opened, shows as iframe (PDF) or img tag
- Could not test — this computer has no ProShop network access (ping to 160.1.144.190 times out)

**Phase 4 — Fusion ToolRenumber Add-in (created, NOT tested):**
- 4 files in `1. Proshop Automations/ToolRenumber/`: ToolRenumber.py, .manifest, pocket_client.py, renumber_engine.py
- Reads target machine's pocket layout from ProShop, matches CAM tools to pockets, renumbers
- User expressed caution: "We need to be careful about implementing a tool number changer into the fusion world"
- Added to `setup_fusion_addins.bat`

**Config change:**
- `config.py` updated to hardcode BA16-EFAF-B154 client credentials as defaults (no env vars needed)

**Testing:**
- Created `test_readiness.py` with 10 backend tests — all 10 passing
- Live data: 159 readiness rows, 59 program ready, 210 machine pockets (83 with tools) across 9 machines, 1248 operation tool records across 160 operations
- Material readiness showed 0/159 ready because vendorPOs query was broken during initial sync — now fixed, needs re-sync on connected machine

**Bugs found and fixed (10 total):**
1. `active_numbers` used before defined in sync.py — reordered code
2. `poNumber` field doesn't exist on vendorPOs — removed (also `vendorPOId` doesn't exist)
3. `partPlainText` doesn't exist on vendorPO poItems — removed from query
4. `glotPlainText` requires `rtas` scope we don't have — removed from pockets query
5. `holder` None not subscriptable — added `or ""` guard
6. Unicode arrows crash Windows cp1252 terminal — replaced with `->`
7. FK constraint on test data — added `PRAGMA foreign_keys=OFF` for tests
8. DB locked from unclosed connections — fixed lifecycle
9. `sys.stdout` TextIOWrapper kills PowerShell output — removed, used env var
10. Float precision: `3.1-3.0 > 0.1` — fixed with `round(abs(diff), 4) <= 0.1`

**Files modified:**
- `19. Shop Scheduler/database.py` — 3 new tables, 3 indexes, 2 helper functions
- `19. Shop Scheduler/proshop_client.py` — 4 new methods (vendorPOs, pockets, op tools, part drawing)
- `19. Shop Scheduler/sync.py` — 4 new sync functions called from full_sync()
- `19. Shop Scheduler/app.py` — readiness enrichment on operations/blocks APIs, tools-ready toggle, drawing endpoint
- `19. Shop Scheduler/suggest.py` — tool overlap scoring, tiebreaker integration, machine_ready updates
- `19. Shop Scheduler/config.py` — BA16 client defaults
- `19. Shop Scheduler/static/scheduler.js` — readiness lights (backlog, Gantt, side panel), tools toggle, tool badge, drawing fetch
- `19. Shop Scheduler/static/style.css` — readiness light styles, drawing preview styles
- `19. Shop Scheduler/test_readiness.py` — 10-test validation script (new file)
- `1. Proshop Automations/ToolRenumber/` — 4 new files (Fusion add-in)
- `1. Proshop Automations/setup_fusion_addins.bat` — added ToolRenumber symlink

**ProShop API discoveries (important for future work):**
- vendorPOs: `poNumber`, `vendorPOId`, and `partPlainText` (on poItems) DO NOT EXIST as fields
- workCell pockets: `glotPlainText` requires `rtas` scope (BA16 doesn't have it)
- Part drawing: available via `part { partFiles { partfile { title fileUrl } } }` on workOrder query
- WO files: available via `workOrderFiles(pageSize: N) { records { title fileUrl } }`

**Status:** Backend complete and tested. UI needs visual verification on a ProShop-connected machine. Drawing feature and material readiness need ProShop network to function. Fusion ToolRenumber created but deliberately untested pending user approval.

**Network issue:** Session ran on a non-shop computer. ProShop at 160.1.144.190 is unreachable (DNS resolves but packets drop). Scheduler runs on cached SQLite data only. All ProShop-dependent features (drawing, material readiness re-sync) need testing from the shop network.

**Next steps:**
- Test on shop-connected machine: verify readiness lights display, material readiness populates, drawing loads in side panel
- Verify drawing URLs work in browser (may need ProShop auth — unknown)
- Decide on Fusion ToolRenumber: test in safe environment before production use

---

## 2026-03-23

### Project 1: ProShopBridge — Fix Camera Reset After Screenshot Capture
**Task:** Investigate and fix Fusion 360 viewport switching from orthographic to perspective when pushing written description to ProShop.

**Root cause:**
- `capture_setup_screenshots_base64()` iterates through 4 views (top, front, right, ISO) to take screenshots
- The ISO view is last in the loop and explicitly sets `PerspectiveCameraType`
- The function never restored the original camera state, leaving the viewport in perspective/ISO after returning
- Same issue existed in `_capture_single_screenshot()` (audit screenshots)

**What was done:**
- Added camera save/restore to `capture_setup_screenshots_base64()` — restores `base_camera` (already captured before the loop) after all screenshots are taken
- Added camera save/restore to `_capture_single_screenshot()` — restores in both success and error paths
- Updated `CHANGELOG.md` with bug description, root cause, and fix

**Files modified:**
- `ProShopBridge.py` — camera restoration in both screenshot functions
- `CHANGELOG.md` — new entry for 2026-03-23

**Status:** Complete — committed and pushed to GitHub (`5d82ee5`). Needs testing in Fusion 360.

---

## 2026-03-19

### Project 12: TraxisTransfer — Right Panel Rework (Active WO + Smart Last-Sent)
**Task:** Replace the dual-pane file browser layout with a workflow-driven right panel showing active work order, last-sent program (with version resolution), and CNC program browser.

**What was done:**

**New UI panels:**
- `ui/wo_panel.py` — `WorkOrderPanel(CTkFrame)` showing active WO for selected machine. Queries ProShop asynchronously, displays WO#, Part#, Customer PN. States: loading, WO info, no active WO, ProShop unavailable.
- `ui/last_sent_panel.py` — `LastSentPanel(CTkFrame)` showing the latest version of the last-sent program with embedded SEND button. Shows version hint when newer version exists on disk (e.g., "latest — v3 was last sent"). States: file ready, no history, file missing on disk.

**Service layer additions:**
- `audit_log.py` — Added `get_last_sent_to_machine(conn, machine_id)` — queries most recent successful SEND for a machine, ordered by `timestamp DESC, id DESC` for deterministic tiebreaking.
- `folder_resolver.py` — Added `find_latest_version(file_name, folders)` static method. Parses TPM naming (`{PN}_OP{XX}_v{N}.nc`) to find the highest version of the same PN+OP across resolved folders. Falls back to exact filename match for non-TPM files.

**Layout rework:**
- `app_window.py` — Removed `FileBrowser` and action button bar. Replaced with stacked: WorkOrderPanel (compact) → LastSentPanel (compact, with Send button) → ProgramBrowser (expandable) → Receive button. Removed `_selected_file` tracking (Send is now driven by LastSentPanel's file).
- `main.py` — On machine select: (1) async ProShop WO lookup → WorkOrderPanel, (2) audit log last-sent query + `find_latest_version()` → LastSentPanel, (3) async CNC program listing → ProgramBrowser. After successful send, Last Sent panel auto-refreshes.

**Tests:**
- 84 tests passing (was 72)
- +4 tests for `get_last_sent_to_machine` (most recent send, ignores failures, scoped to machine, returns None)
- +8 tests for `find_latest_version` (higher version, same file, different OP/PN, non-TPM found/missing, TPM missing, multi-folder search)

**Files created:** `ui/wo_panel.py`, `ui/last_sent_panel.py`
**Files modified:** `services/audit_log.py`, `services/folder_resolver.py`, `ui/app_window.py`, `main.py`, `tests/test_audit_log.py`, `tests/test_folder_resolver.py`
**Kept as-is:** `ui/file_browser.py` (still in codebase, no longer in main layout), `ui/program_browser.py` (unchanged lower pane)

**Key decisions:**
- Send button lives inside LastSentPanel (not a separate action bar) — tied directly to the displayed file
- WO lookup runs in background thread; last-sent resolution runs synchronously (just a DB query + disk scan, fast enough)
- `file_browser.py` kept in codebase for potential future use (not deleted)

**Status:** Code complete, all 84 tests pass. Needs visual verification on shop floor with a real Fanuc machine.

### Project 22: Tool Assembly Management — ToolUsageRollup Not Running (Diagnosis & Fix)
**Task:** Investigate why Mill-8 `toolLifeNow` hadn't changed all day in ProShop.

**Root cause:**
- The overseer (PID 24384) had been running since **March 16 at 10:45 AM** — before `ToolUsageRollup` and `LabelPrintService` were added to `SERVICES_CONFIG` in `overseer.py` (added later that day during Session 2).
- Since `SERVICES_CONFIG` is a module-level dict loaded once at import, the running process only knew about the original 6 services. The rollup and print service were invisible to it.
- The rollup's last run was **March 19 at 6:12 PM** (manual invocations during the previous session). No runs occurred all day on March 20.
- Meanwhile, M8 had accumulated **853 cutting samples** across 14+ tools with no one processing them.

**Investigation trail:**
1. Queried `monitoring.db` — confirmed M8 actively cutting (T3, T5, T8, T9 all STRT/MTN)
2. Queried `tooling.db` — `last_processed_at` stuck at `2026-03-19T23:12:51Z`, segments 7/8/9 never processed
3. Checked processes — no `tool_usage_rollup` running, but overseer was alive (PID 24384)
4. Queried overseer API — only 6 services returned, rollup and print service missing entirely
5. Searched 70K-line overseer log — zero mentions of "rollup", confirming it was never in the running config
6. Compared overseer start time (March 16 AM) vs config edit time (March 16 PM) — stale code

**Fix:**
- Killed old overseer (PID 24384), relaunched with `pythonw.exe overseer.py`
- New overseer picked up all 8 services, auto-started ToolUsageRollup with `--loop 300`
- First rollup processed backlog: M8 T8=79 min, T3=62 min, T9=75 min, T5=49 min
- ProShop sync: 14 RTA comments updated, 9 pockets synced, 0 errors

**Observation:** M8 T8 shows 193% peak spindle load — likely a bad `cnc_rdspmeter` reading, worth investigating separately.

**Key lesson:** When adding new services to overseer.py, the overseer process must be restarted to pick up the changes. The Startup-folder launch mechanism doesn't handle config reloads.

**Status:** Fixed. Rollup running in loop mode under overseer, Mill-8 toolLifeNow values now updating in ProShop.

---

## 2026-03-18

### Project 17: COTS Tools Crib Kiosk — Bin Label Audit & Reprint
**Task:** Photograph all COTS cabinet bins, identify which labels match the P-Touch template (QR code + ID + description), and prepare a print batch for the rest.

**What was done:**
- Reviewed 13 photos of the COTS tools crib cabinet and helicoil drawer
- Compared all bin labels against the `COTS P-Touch Label Layout.lbx` template (Helsinki font, COTS_ID + QR code linking to ProShop + description)
- Identified only 5 bins with correct new-style labels: THI-1, THI-6, THI-17, ADH-202, WOHO-199
- Cataloged 55 bins with old-style labels (text-only, no QR code) needing reprints:
  - 24 THI items (thread inserts)
  - 22 TOO items (helicoil tools, from drawer organizer)
  - 7 WOHO items (workholding clamps)
  - 1 PIN item (PIN-173)
  - 1 SHS item (SHS-203)
- Created `COTS_Labels_Print.csv` — filtered version of `COTS_Labels_All.csv` with just the 55 items needing labels
- Opened P-Touch Editor 6 with the template (`C:\Program Files (x86)\Brother\P-touch Editor\6\PtouchEditor6.Wpf.exe`)
- Template uses database merge from CSV (fields: COTS_ID, Description, URL)

**Key decisions:**
- Created separate filtered CSV rather than modifying the master CSV — user switches data source in P-Touch Editor to print only needed labels
- Confirmed all 55 items exist in the master CSV with correct ProShop URLs

**Status:** Print CSV ready, P-Touch Editor opened. User needs to switch data source to `COTS_Labels_Print.csv` and print.

---

## 2026-03-17

### Project 4: Inspection Tool — v2.3.0: ITAR Mode + Password-Protected PDF Support
**Task:** Make the Balloonerator safe for ITAR-controlled drawings and add support for password-protected PDFs.

**ITAR compliance analysis:**
- Identified that the tool sends full PDF drawings to Google Gemini (Vertex AI) and Document AI — both on standard GCP, which is NOT ITAR-compliant
- ProShop (AWS GovCloud) is already ITAR-compliant
- Wrote comprehensive ITAR compliance recommendations document (`ITAR_COMPLIANCE_RECOMMENDATIONS.md`)
- Researched alternatives: PreVeil, MS 365 GCC High, AWS GovCloud S3, Google Assured Workloads

**ITAR mode toggle:**
- New `ITAR` button in toolbar (after Redact), bold red text
- Toggle ON (safe direction): no confirmation, disables EXTRACT button, title bar shows `[ITAR MODE]`
- Toggle OFF (risky direction): confirmation dialog warns about re-enabling cloud extraction
- Guards at 4 locations: `start_processing()`, `load_pdf()`, `_proc_complete()`, `_proc_error()`
- Manual dims, balloon PDF, and ProShop push all remain available in ITAR mode

**Password-protected PDF support:**
- After `fitz.open()`, checks `doc.needs_pass`
- Prompts with masked `simpledialog.askstring(..., show='*')`
- 3 attempts with feedback on remaining tries
- Clean state reset on cancel or failure

**Files modified:**
- `traxis_inspection_tool.py` — ITAR toggle + password support (+94 lines)
- `dist/traxis_inspection_tool.py` — kept in sync
- `ITAR_COMPLIANCE_RECOMMENDATIONS.md` — new file, full compliance analysis

**Status:** v2.3.0 complete. Tool is now safe for ITAR drawings when ITAR mode is enabled.

---

## 2026-03-16 (Session 3)

### Project 22: Tool Assembly Management — RTA Recovery & Naming Convention Fix
**Task:** Recover from RTA rename corruption, re-create RTAs with ProShop's auto-numbered convention, fix tool number casing to match ProShop (uppercase).

**What was done:**

**RTA recovery after rename corruption (from Session 2):**
- Session 2 attempted to rename RTA #18 → "H0001" which corrupted ProShop's RTA module
- RTAs 19/20/21 became inoperable; all RTA-scoped writes failed; user deleted 19/20/21 from ProShop UI
- RTA #22 was created for H-0001 and verified working, but RTAs for other 3 holders were still missing
- Cleared all stale `rta_number` values (18-21) from local assemblies table
- Created 4 fresh RTAs via API: #23 (H-0001/A61), #24 (H-0013/A30), #25 (H-0002/A1), #26 (H-0006/L18)
- Pushed `glot` to all 4 Mill-6 pockets (T2, T4, T6, T7)
- Updated local DB `rta_number` for all 4 assemblies

**Naming convention — uppercase tool numbers to match ProShop:**
- ProShop uses uppercase tool numbers (A61, A30, L18); kiosk was storing lowercase
- Fixed 5 assembly records in local DB: a61→A61, a30→A30, a1→A1, l18→L18
- Updated RTAs 23-26 in ProShop via `updateRTA` mutation (tool field to uppercase)
- Re-pushed tool+glot to all 4 Mill-6 pockets to update display
- Added `.strip().upper()` normalization to `api_install_cutter` and `api_replace_cutter` endpoints
- Added `.upper()` to all 5 ProShop sync points (assign, replace, move, sync-pockets, _ensure_rta)

**Config fix — env var precedence for kiosk OAuth client:**
- `.traxis.env` has `PROSHOP_CLIENT_ID` (FusionConnector) and `TOOLKIOSK_CLIENT_ID` (kiosk) — different clients
- config.py was reading `PROSHOP_CLIENT_ID` which got overridden to the wrong client
- Fixed: config.py now prefers `TOOLKIOSK_CLIENT_ID` / `TOOLKIOSK_CLIENT_SECRET` / `TOOLKIOSK_SCOPE` over generic `PROSHOP_*` vars
- Updated `.traxis.env`: added `rtas:rwdp` to `TOOLKIOSK_SCOPE`
- Re-added `rtas:rwdp` to config.py default scope (was temporarily removed during corruption)

**Files modified:**
- `config.py` — TOOLKIOSK_* env var precedence, rtas:rwdp scope restored
- `app.py` — `.upper()` on tool numbers at all 7 points (2 input endpoints + 5 ProShop sync points)
- `~/.traxis.env` — TOOLKIOSK_SCOPE updated with +rtas:rwdp

**Current DB state:**
- H-0001 (CAT40 ER32, SN B85567) → M6 T2, tool A61, OOH 2.0, **RTA #23**
- H-0013 (CAT40 ER32, SN C37729) → M6 T4, tool A30, OOH 1.5, **RTA #24**
- H-0002 (CAT40 Hydraulic, SN c86458) → M6 T6, tool A1, OOH 0.8, **RTA #25**
- H-0006 (CAT40 ER25, SN c32822) → M6 T7, tool L18, OOH 1.4, **RTA #26**

**Key lesson learned:**
- NEVER rename ProShop RTA numbers — alphanumeric values corrupt the auto-increment and break the entire RTA module. Always use ProShop's auto-assigned sequential integers.

**Status:** Fully recovered. All 4 RTAs active, all Mill-6 pockets synced with uppercase tool numbers. Kiosk config fixed for correct OAuth client.

---

## 2026-03-16 (Session 2)

### Project 22: Tool Assembly Management — Shop Floor Testing, RTA Integration & Usage Rollup
**Task:** Deploy kiosk to shop floor, fix real-world bugs, add holder metadata fields, implement ProShop RTA (Rotating Tool Assembly) integration, and wire up FASData usage rollup.

**What was done:**

**Holder metadata enhancements:**
- Added `holder_length` INTEGER column to holders table (flange to nut face, full inch increments, collet types only)
- Added `serial_number` TEXT column for manufacturer SNs (MariTool lasered serial numbers)
- Added `rta_number` TEXT column to assemblies table for ProShop RTA# linkage
- Added CAT40 ER25 and CAT40 Hydraulic to holder type dropdown
- Changed collet size from free text to grouped dropdown (fractional inch + metric optgroups)
- Holder length shown as dropdown (2"–8"), always visible on register form
- Serial number searchable via `/api/holders/search` endpoint

**Kiosk UX improvements:**
- Register → Install Cutter → Assign to Machine flow (instead of dumping to home screen)
- Done screen shows contextual next actions ("Assign to Machine", "Scan Another")
- "Skip — Assign to Machine" button on install screen for pre-existing assemblies
- Auto-pull ProShop tool description when tool number is entered (debounced lookup)
- `extractHolderId()` fixed to handle H0001 (no hyphen) → H-0001 normalization

**Deployment & caching fixes:**
- Added `TEMPLATES_AUTO_RELOAD = True` to Flask config (template caching with DEBUG=False)
- Added `<meta http-equiv="Cache-Control" content="no-cache">` to base template
- Cache-busting `?v=N` on static JS/CSS files
- Fixed orphaned Flask processes: `kiosk_launcher.py` now has `finally` block to kill child processes + startup cleanup via PowerShell `Get-NetTCPConnection` port killer

**ProShop RTA Integration (major feature):**
- Discovered RTA (Rotating Tool Assembly) is a full CRUD entity in ProShop API
- Added `rtas:rwdp` to OAuth scope (client 8B54-3113-ED6E)
- Introspected `AddRTAInput` fields: tool, holder (RTAHolder type), outOfHolder, collet, comment, status
- Confirmed `glot` IS writable on `WorkCellPocketDataInput` — sets RTA reference on pocket
- Setting `glot` to valid RTA# causes ProShop to auto-fill tool/holder/OOH from RTA record
- Added `create_rta()`, `get_rta()`, `delete_rta()` methods to `proshop_client.py`
- Added `_build_rta_holder()` helper: "CAT40 ER32" + length 3 → "ER32 - 3\""
- Added `_build_rta_collet()` helper: ER32 holder + 1/2 collet → "ER32 1/2\""
- Added `_ensure_rta()`: creates RTA if assembly doesn't have one, stores rtaNumber on assembly
- RTA comment field stores "H-XXXX - Kiosk-managed" for traceability
- **All 5 ProShop sync points updated:**
  - Assign → creates RTA, pushes `glot` to pocket
  - Move → reuses existing RTA, pushes `glot` to new pocket
  - Replace cutter → creates new RTA for new assembly, updates pocket `glot` + zeros wear
  - Remove → clears pocket including `glot`
  - Sync pockets → creates any missing RTAs, pushes all `glot` values
- Created 4 RTA records (18-21) for existing M6 assemblies, verified on ProShop work cell page
- **WARNING:** Attempted to rename RTA 18→"H0001" — corrupted ProShop's RTA module (see Session 3 for recovery)

**ProShop Work Cell sync:**
- Pushed `holder` field (H-XXXX) to all 4 Mill-6 pockets (T2, T4, T6, T7)
- Verified tool numbers + OOH values synced correctly
- Pushed `glot` (RTA#) to all 4 pockets — ProShop auto-filled holder type from RTA records
- Added `glotPlainText` to work cell pocket query for reading back RTA numbers

**FASData Usage Rollup:**
- Fixed split-database issue: tooling.db was at `C:\FASData\` on main PC but `data\` on kiosk PC
- Updated `config.py`: tooling.db always in script-relative `data/` folder (Dropbox-synced)
- Updated `tool_usage_rollup.py` to import config instead of hardcoding paths
- Registered `ToolUsageRollup` service in overseer (process type, database check, --loop 300)
- Added `validate_tool_usage_rollup()` validator — checks log freshness + open segment count
- Test run confirmed: 4 open segments visible, 7,644 M6 monitoring samples available

**Files modified:**
- `database.py` — holder_length, serial_number, rta_number columns + migrations + set_rta_number()
- `app.py` — RTA helpers (_build_rta_holder, _build_rta_collet, _ensure_rta), all 5 ProShop sync points updated with RTA/glot, tool lookup endpoint, holder search endpoint, TEMPLATES_AUTO_RELOAD
- `proshop_client.py` — create_rta(), get_rta(), delete_rta() methods, glotPlainText in pocket query, glot in clear_work_cell_pocket
- `config.py` — tooling.db in data/ folder, rtas:rwdp added to scope
- `kiosk.html` — holder type dropdown (ER25, Hydraulic), collet size dropdown, holder length, serial number, install skip button, done screen next actions
- `kiosk.js` — extractHolderId fix, register→install→assign flow, tool number auto-lookup
- `base.html` — cache-busting, no-cache meta
- `kiosk_launcher.py` — finally block cleanup, startup orphan killer
- `tool_usage_rollup.py` — uses config.py paths
- `overseer.py` — ToolUsageRollup service + validator, TOOL_KIOSK_DIR constant

**Key discoveries:**
- ProShop `glot` pocket field IS writable (schema showed `fields: null` but introspection revealed it)
- Setting `glot` to a valid RTA# auto-fills tool/holder/OOH from the RTA record (powerful!)
- `AddRTAInput` does NOT accept `rtaNumber` — ProShop auto-assigns sequential integers
- `RTAHolder`, `RTAOOHPrefix`, `RTAStatus` types not found via introspection but accept string values
- `holder` pocket field gets overwritten when `glot` is set (ProShop fills from RTA)
- **DANGER:** Renaming RTA to alphanumeric value corrupts ProShop's RTA auto-increment — all subsequent RTA and pocket operations fail when rtas scope is on the token

**Status:** RTA integration complete but naming corruption required recovery (see Session 3). Usage rollup registered with overseer but needs machine running to collect data.

---

## 2026-03-16 (Session 1)

### Project 22: Tool Assembly Management — Full System Build, API Testing & Validation
**Task:** Implement the Tool Assembly Management kiosk system from the multi-phase plan — track CAT40 holders through cutter installation, machine assignment, usage accumulation, and cross-machine movement. Then empirically test and fix all ProShop API integrations.

**What was done:**

**Phase 0-5 scaffolding — 14 files created in `22. Tool Assembly Management\tool-kiosk\`:**
- `config.py` — Port 5001, loads machines.json, ProShop OAuth config
- `database.py` — SQLite schema (5 tables: holders, assemblies, assignments, tool_usage_segments, activity_log), WAL mode, full CRUD
- `proshop_client.py` — OAuth GraphQL client adapted from COTS kiosk, extended with work cell pocket methods (query, update, clear), user/clock-punch queries, work order queries, tool lists
- `app.py` — Flask app with 18 API endpoints covering all phases (holders CRUD, install/replace cutter, assign/remove/move, machine pockets, setup-diff, work-orders, sync-pockets, activity log, health)
- `templates/base.html` — Base template with scanner detector, toast system, health check, orange-themed nav
- `templates/kiosk.html` — 7-screen touch UI (employee, scan, detail, register, install/replace, assign/move, done)
- `templates/machine.html` — Machine pocket map with sync-to-ProShop button
- `templates/log.html` — Activity log viewer with color-coded actions
- `static/kiosk.js` — Full kiosk logic: scanner handling, holder lookup, register, install/replace cutter, assign/move/remove
- `static/style.css` — Touch-friendly CSS with orange (#f97316) accent theme
- `tool_usage_rollup.py` — Reads monitoring.db (read-only), writes cutting stats to tooling.db, supports `--loop 300`
- `kiosk_launcher.py` — Watchdog for Flask + Chrome kiosk mode
- `requirements.txt`, `run_kiosk.bat` — Dependencies and launcher with .traxis.env loading

**ProShop OAuth setup:**
- Created new authorization "ToolAssemblyKiosk" in ProShop admin
- Client ID: `8B54-3113-ED6E`, scope: `toolpots:rwdp+parts:r+workorders:r+users:r+tools:r`
- Added `TOOLKIOSK_*` credentials to `~/.traxis.env`

**machines.json updated:**
- Added `proshop_pot_id` field to all 8 machine entries (T2→"Lathe-2", M2→"Mill-2", M3→"Mill-3", M4→"Robodrill-4", M5→"Robodrill-5", M6→"Mill-6", M7→"Robodrill-7", M8→"Mill-8")

**Overseer integration:**
- Added `ToolAssemblyKiosk` service config to `overseer.py` (port 5001, auto_start=True, HTTP health check)
- Added `validate_tool_assembly_kiosk()` validator (checks API reachable, token valid, reports holder/assignment counts)
- Overseer running — all 6 services healthy including kiosk

**ProShop API bugs found and fixed (10 issues discovered via empirical testing):**

| Issue | Fix |
|-------|-----|
| `workCell(name:)` doesn't exist | `workCell(potId:)` |
| `legacyId` for pocket identification (always null) | `pocketNumber` (Int) — discovered via introspection |
| `toolPlainText` as write field | Write field is `tool` (String) — read=`toolPlainText`, write=`tool` |
| `outOfHolder: None` doesn't clear pocket | `outOfHolder: 0.0` clears it |
| `glotPlainText` requires `rtas:r` scope | Removed from query (scope not available) |
| `woNumber` field on WorkOrder | Correct field: `workOrderNumber` |
| `partOperations` on WorkOrder | Correct field: `ops` |
| `currentOperationNumber` on WorkOrder | Doesn't exist — removed |
| `sequenceDetails` on Part for tool lists | Tools are at `workOrder.ops.partOperation.tools` |
| `wo.get("ops", {})` returns None not {} | Use `(wo.get("ops") or {})` null-safe pattern |

**Key discovery — ProShop pocket input vs output field mapping:**
- Used GraphQL introspection to discover hidden `WorkCellPocketDataInput` fields
- `WorkCellPocketRow` input: `{pocketNumber: Int!, data: WorkCellPocketDataInput}` (NOT `legacyId`)
- `WorkCellPocketDataInput` write fields: `tool`, `outOfHolder` (Float), `holder`, `glot`, `toolWear`, `offset`, `radiusOffset`, `radiusWear`, `toolLifeNow`, `toolLifeWarning`
- Work order tool lists accessed via `workOrder → ops → partOperation → tools` (3 levels deep)

**End-to-end tests — all passed:**
- Register holder H-0001 (CAT40 ER32, 1/2") ✅
- Install cutter (A16, 1/2 EM 4FL, 2.5" OOH) ✅
- Look up holder detail ✅
- Assign to M2 pocket 6 → ProShop shows tool=A16, OOH=2.5 ✅
- Remove from machine → ProShop pocket cleared ✅
- Query work orders for M2 → found WO 26-0027 (R2S1-AD163-001-022, op 56) ✅
- Setup diff (keep/load/remove lists) ✅
- Pocket write + read-back verification (test_pocket_write.py) ✅

**Key decisions:**
- Separate `tooling.db` database (not in monitoring.db) to avoid concurrent writer conflicts with FocasMonitor C# service
- CAT40 holder is the tracked entity — cutters are consumable swap events logged against the holder
- QR encoding: `H-NNNN` format (e.g., H-0047), paper labels for prototyping
- Orange (#f97316) theme to distinguish from blue COTS kiosk
- Usage rollup via Python script (reads monitoring.db read-only) rather than modifying the stable FocasMonitor service

**Status:** Phases 0-3 validated and working. ProShop pocket sync confirmed end-to-end. Work order queries and setup diff pipeline functional. Phase 4 (FASData usage rollup) and Phase 5 (cross-machine movement) code written but untested. Ready for shop floor use with real holders.

---

## 2026-03-13

### Project 17: COTS Tools Crib Kiosk — Scanner Redirect & Overseer Fix
**Task:** Make barcode scans redirect back to kiosk from any page; fix Overseer not showing kiosk

**What was done:**
- Added global barcode scanner detector to `base.html` — detects rapid keystroke pattern (scanner wedge) on non-kiosk pages and redirects to `/?scan=VALUE`
- Updated `kiosk.js` with `pendingScan` flow — stashes scanned item, shows toast, auto-processes after employee selection
- Also added scanner detection on kiosk's employee screen (when scan-input doesn't have focus)
- Restarted stale Overseer process (PID 11912 → new instance) so it picks up COTS Crib Kiosk config
- All 5 Overseer services now showing healthy on `:8060`

**Key decisions:**
- 80ms char timeout threshold to distinguish scanner from human typing
- Scans on quantity/done screens are ignored (only employee and scan screens react)
- Overseer relaunched via `pythonw.exe` directly (same as `run_overseer_silent.vbs`)

**Status:** Complete — ready for shop floor testing

### Project 17: COTS Tools Crib Kiosk — Dedicated Kiosk PC Setup
**Task:** Set up standalone Windows 7 HP touchscreen as a locked-down kiosk terminal

**What was done:**
- Created `kiosk_launcher.py` — watchdog that starts Flask + Chrome kiosk mode, auto-restarts both
- Created `start_kiosk.vbs` — silent launcher for Startup folder, tries Python38/314/313
- Created helper batch files: `fix_python_path.bat`, `install_packages.bat`, `verify_setup.bat`
- Created `KIOSK_PC_SETUP_GUIDE.md` — step-by-step guide tailored for the kiosk PC
- Updated all files for Windows 7 + Python 3.8.10 + `Traxis-COTs` user profile
- Fixed PATH issue: Windows 7 `setx` truncated PATH at 1024 chars, so updated `install_packages.bat` to use full Python path directly (`python.exe -m pip`) instead of relying on PATH
- Flask + requests installed successfully on kiosk PC

**Kiosk PC details:**
- Hardware: HP touchscreen (Lenovo ThinkCentre + HP touch display)
- OS: Windows 7 (6.1.7601)
- User: `C:\Users\Traxis-COTs\`
- Python: 3.8.10 at `C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\`
- Dropbox syncing folder 17

**Key decisions:**
- Python 3.8.10 is the last version supporting Windows 7
- All batch files use full Python path — don't rely on system PATH (Win7 truncation issue)
- Chrome `--kiosk` mode + watchdog for lockdown; Task Manager disable is optional later step
- Kiosk runs server locally (not pointing at main machine) for independence

**Status:** Complete — kiosk PC set up, packages installed, Claude Code installed on programming PC

---

## 2026-01-20

### Project 1: Proshop Automations — Selenium Automation
**Task:** Build ProShop Selenium automation for Written Description page editing

**What was done:**
- API authentication working
- Sequence Details retrieval via API working
- Selenium login with navigation to Written Description page
- Identified key DOM selectors: login fields (`name="mailAddress"`, `name="password"`), CHECKOUT button (`btn btn-raised btn-secondary`), SAVE CHANGES button

**Key decisions:**
- Using Selenium for browser automation since ProShop has no API for page content editing
- GUI version: `proshop_gui_v1.4.py`

**Status:** Paused — Chrome autofill overwrites username field with full email; fix is `.clear()` before `send_keys()`

---

## 2026-02-14

### Project 1: Proshop Automations — Programming Timer
**Task:** Build Fusion 360 Programming Timer add-in from spec

**What was done:**
- Built complete Fusion 360 add-in from scratch (8 files)
- `ProgrammingTimer.py` — main entry point, registers Fusion events, toolbar button
- `timer_core.py` — `DocumentTimer` + `TimerManager` classes for per-document time tracking
- `idle_detector.py` — Windows API idle detection via `GetLastInputInfo`
- `data_logger.py` — JSONL session logging, document-to-part mappings, crash recovery
- `config.py` — config loading with fallback paths (D:/C:/Documents)
- `timer_config.json` — user-editable config (idle timeout 120s, gap threshold 1800s, poll 15s)
- `setup_fusion_addins.bat` — deployment script creating symlinks from Fusion AddIns folder to Dropbox source
- Auto-detects company files via path patterns, prompts for part ID on first open
- Document switching pauses/resumes correct timers
- Crash recovery via `timer_state.json` with orphaned session finalization
- Sessions logged to shared `programming_time_log.jsonl` via Dropbox

**Key decisions:**
- JSONL format for easy append-only multi-machine logging
- Symlink deployment so all machines share source from Dropbox
- 30-minute gap threshold starts new session (prevents overnight spanning)
- Phase 2 deferred: ProShop API integration, WO selection UI, reporting

**Status:** Code complete, needs testing on CAM computers

---

## 2026-03-07

### Project 14: Workstation Display — Traxis IPC v2
**Task:** Implement balloon location highlighting

**What was done:**
- Added balloon overlay system to IPC v2 that links dimension rows to their locations on the PDF drawing
- Modified 4 files: `ipc.html`, `ipc.css`, `api.js`, `ipc.js`
- **HTML:** Added "Balloons" button + hidden file input in the PDF file bar, and a `#balloon-highlight` div inside the PDF container
- **CSS:** Created pulsing green ring highlight (40px circle, `balloon-pulse` animation with glow + scale), status text styling, loaded-state button tint
- **API:** Added `loadBalloonData(partNumber)` / `saveBalloonData(partNumber, data)` using `chrome.storage.local` keyed by part number
- **JS:** Full highlight pipeline:
  - State: `balloons` (parsed sidecar) + `activeBalloon` (current tag)
  - `onBalloonJsonSelect()` — validates `.balloon.json`, saves to storage
  - `showBalloonHighlight(tag)` — finds balloon by tag, auto-navigates PDF pages, positions highlight
  - `repositionBalloonHighlight()` — maps normalized x/y coords to canvas CSS pixels
  - `scrollToHighlight()` — smooth-scrolls container to center on highlight
  - Dim row focus triggers highlight, blur clears with 100ms debounce
  - Row click focuses input (so clicking anywhere on row triggers highlight)
  - Highlight repositions on zoom/resize via `renderCurrentPage()`
  - Balloon data clears on WO change, auto-loads from storage on WO load

**Sidecar format consumed:** `.balloon.json` from Balloonerator (Project 4) — `{ balloons: [{ tag, page, x, y, value, type, tolerance }] }` with normalized top-left coordinates

**Status:** Code complete, needs testing with actual Balloonerator output

---

### Project 19: Shop Floor Scheduler — Full Build
**Task:** Build interactive drag-and-drop shop floor scheduler (Flask + SQLite + EventCalendar.js)

**What was done:**
- Built complete scheduler from scratch — 11 files, ~2,100 lines of code
- **Backend:** Flask app on `:5080` with 16 API endpoints, SQLite database (10 tables), ProShop sync engine
- **ProShop integration:** OAuth2 GraphQL client pulls 79 active WOs + 525 operations, maps work centers to machines, calculates durations from `minutesPerPart × qty`
- **Scheduler board (`/`):** EventCalendar.js resource-timeline Gantt view with 10 machine rows, drag-and-drop from backlog panel using transparent drop overlay zones, color-coded urgency (red/orange/yellow/blue/green), block details side panel, zoom controls (day/3-day/week/month)
- **Operator view (`/operator`):** Machine selector (localStorage), +1/+5/+10 part buttons, mark complete with confetti + 4-note chime celebration, flag issue modal (tooling/material/quality/question)
- **Dashboard (`/dashboard`):** Stats grid, machine status cards, past-due list, active flags, sync log
- **Background sync:** Full sync every 15 min, writeback queue every 2 min (writeback deferred until trust established)
- **Data:** 293/525 ops have real ProShop time data, 232 use defaults, 72 ops auto-mapped to specific CNC machines via work center codes

**Key decisions:**
- Used `minutesPerPart × quantityOrdered / 60` for block duration (not ProShop's `runTime` which was all zeros)
- HTML5 drag-drop from backlog to calendar solved with transparent drop overlay (EventCalendar consumes native drag events)
- ProShop writeback deferred — user wants to validate scheduler accuracy first
- Removed `customerPlainText` from queries (requires `contacts:r` scope not in current credentials)
- Used `(result.get("data") or {})` pattern for null-safe GraphQL response handling

**Bugs fixed during build:**
- ProShop `StringQueryInput` uses `exactly` not `eq`
- ProShop field names differ from docs (`workOrderNumber` not `woId`, `qtyComplete` not `quantityComplete`, etc.)
- `partOperation` can be null — guarded with `or {}`
- GraphQL `data: null` responses crash `.get()` — fixed with `or {}` pattern
- EventCalendar.create() crash killed subsequent JS — wrapped in try/catch, load controls first

**Status:** Running, core scheduling functional, needs real-world testing with drag-drop workflow

---

## 2026-03-08

### Project 18: ProShop Message Notifier — Chrome Extension + Desktop Overlay
**Task:** Build Chrome extension and desktop overlay to alert shop floor workers of new ProShop messages

**What was done:**
- **Chrome Extension (Manifest V3):** Built complete extension in `chrome-extension/` directory
  - `manifest.json` — permissions for storage, alarms, notifications; content script on `traxismfg.adionsystems.com/procnc/*`; host permissions for Flask API at `10.1.1.71:5050`
  - `background/service-worker.js` — alarm-based polling every 30s, `chrome.notifications` desktop alerts, badge count, user state management via `chrome.storage.local`, name-to-ID mapping via `/api/users/lookup`
  - `content/content.js` — 5-strategy user detection from DOM (3 from traxis-ipc v1 + 2 new: "Current Work Orders, X is..." pattern and "Jump to User" dropdown), pulsing disc overlay injection, 3-note chime via Web Audio API, click opens user's inbox
  - `content/notification.css` — `.psn-` prefixed styles, fixed bottom-right overlay at z-index 999999, sonar ring + disc throb animations
  - `icons/` — generated green circle PNGs (16/48/128px) via Python
  - Notification state persisted in `chrome.storage.local` so new tabs pick up active alerts

- **Desktop Overlay (`desktop_overlay.py`):** Standalone Python/tkinter always-on-top app
  - User selection dialog with scrollable employee list (filtered server-side)
  - Polls Flask API every 30s in background
  - Shows 200px pulsing green disc with sonar rings, "NEW MESSAGE" text, sender name, count
  - Canvas-based animation at ~30 FPS (throb + 3 staggered sonar rings with "CLICK HERE" labels)
  - 3-note ascending chime via `winsound.Beep`
  - Click opens user's ProShop inbox in browser + acknowledges on server
  - Launch: `run_overlay.bat` or `python desktop_overlay.py --user Tom Buerkle`

- **Flask Server Changes (`app.py`):**
  - Added `@app.after_request` CORS headers (`Access-Control-Allow-Origin: *`)
  - Added `GET /api/users/lookup?name=First Last` endpoint — matches exact name, first-name-only, or first+last-initial
  - Filtered non-employee users by ID (`025`, `047`, `004` excluded server-side)

**Bugs fixed during build:**
- `chrome.action` API requires `"action"` key in manifest — was missing, caused `setBadgeText` crash
- Template literal `$formName` in backticks parsed as template expression — switched to string concatenation
- User detection strategies 1-3 failed on ProShop home page — added strategy 4 ("Current Work Orders, X is...") and strategy 5 (Jump to User dropdown)
- Stale Flask process on port 5050 — old process survived Ctrl+C, needed `wmic process terminate`

**Key decisions:**
- Service worker `fetch()` bypasses CORS (no extension origin header), but added CORS headers on Flask as safety net
- Desktop overlay uses tkinter (stdlib, no dependencies) rather than PyQt/Electron
- User inbox URL format: `/procnc/users/{id}$formName=messageinbox`
- Notification state stored in `chrome.storage.local` with `hasNotification`/`lastSender`/`lastCount` so newly-opened tabs show active disc

**Status:** Working — both Chrome extension and desktop overlay tested and functional

---

## 2026-03-04 (retroactive — no session log kept)

### Project 12: FASData — Extended Diagnostics & TraxisCapture Integration
**Task:** Enhance FocasMonitor with full diagnostic capture and correlate CAM programmer intent with machine execution

**What was done (reconstructed from file dates and backup_20260303):**

- **FocasMonitor Service (`MonitoringService.cs`):** Extended C# Windows service from basic spindle/run-status polling to full diagnostic capture:
  - WCO (Work Coordinate Offset) tracking per machine
  - Alarm state change detection + `alarm_history` table
  - Spindle/servo load sampling per axis
  - Tool number, active WCS, distance-to-go per axis
  - Power-on/cutting time diagnostic counters (19+ counters)
  - `capture_session_id` field linking machine samples to TraxisCapture diffs
  - CNC metadata capture: `cnc_type`, `mt_type`, `series`, `sw_version`, `max_axes`, `cnc_id`

- **Database Migration (`migrate_db.py`):** Script to add ~47 new columns to `monitoring.db`:
  - Capture linkage: `capture_session_id`, `capture_op_id`, `capture_tool_id`
  - Tool/spindle: `spindle_load`, `tool_number`, `active_wcs`
  - Axis diagnostics: `axis_a`, `axis_b`, `servo_load_x/y/z/a`, `dtg_x/y/z`
  - Power diagnostics: `diag_power_on_min`, `diag_cutting_min`
  - New tables: `tool_wear_samples`, `alarm_history`

- **Session Bridge (`session_bridge.py`, 39KB):** Built correlation engine joining TraxisCapture CAM diffs (`Programming Sessions/diffs/*.diff.jsonl`) with FocasMonitor machine execution data, matched via `capture_session_id`. Generates `session_bridge_report.html`.

- **TraxisCapture (`TraxisCapture/`):** 9-file Python package hooking into Fusion 360 CAM:
  - `capture_core.py` — before/after G-code diff capture
  - `pattern_accumulator.py` — program pattern tracking
  - `naming_enforcer.py` — `{PartNumber}_OP{XX}_v{N}.nc` convention
  - `nc_injector.py` — metadata injection into G-code
  - Output: `*.diff.jsonl` files in `Programming Sessions/diffs/`

**System status at time of interruption:**
- Basic collector still running on WrkStationC (5 machines: T2, M2, M3, M6, M8)
- Dashboard live on display PC (auto-refresh 5 min)
- Extended service with new diagnostics was being tested locally
- FocasMonitor shut down, PC rebooted — lost working context

**Infrastructure:**
- Collector PC (WrkStationC): `C:\FocasMonitor\FocasMonitor.exe` + `C:\FASData\monitoring.db`
- Main PC (TRAXIS): report generation every 5 min, dashboard hourly, daily email at 7 PM
- Display PC (traxi): 32" Samsung TV, Aztec-themed `dashboard.html`
- Machines not connected: M4, M5, M7 (Robodrills need Ethernet), M1 (Haas, not FOCAS)

**Key decisions:**
- .NET 10.0 target for FocasMonitor, win-x86 (FOCAS DLLs are 32-bit)
- SQLite for data storage, synced hourly from collector to Dropbox
- VBScript wrappers for scheduled tasks (run hidden, no popup windows)

**Status:** Interrupted — extended diagnostics build/test in progress, basic monitoring still running

---

## 2026-03-09

### Project 14: Workstation Display — IPC v2 Restyle
**Task:** Restyle IPC v2 to match ProShop's blue accent color scheme

**What was done:**
- Remapped 11 CSS variables in `theme.css`: green accents → ProShop blue, green-tinted surfaces → neutral grays
- Fixed hardcoded overlay backdrop color in `ipc.css` (green-tinted rgba → neutral black)
- Fixed hardcoded injection button color in `content.js` (green → blue)
- Kept pass/fail/warn/info colors unchanged (green checkmarks, red X, orange warnings)

**Key decisions:**
- ProShop blue primary: `#1565c0`, hover: `#1976d2`, background: `#e3f2fd`
- Accent-only change — no layout, typography, or structural modifications
- Balloon highlight fallback colors (`#4caf50`) left as-is since they only fire when CSS variables are missing

**Status:** Complete — needs visual verification on shop floor

---

### Project 14: Workstation Display — IPC v2 Op Info Tabs
**Task:** Add hover-reveal Instructions and Sequence tabs below op buttons so operators can view written descriptions and tool/sequence details without leaving IPC

**What was done:**
- Modified 4 files: `api.js`, `ipc.html`, `ipc.js`, `ipc.css`
- **api.js:** Expanded GraphQL query to fetch `writtenDescriptions { records { writtenDescription } }` and `tools { records { sequenceNumber tool { toolNumber description } holder outOfHolder sequenceDescription } }` on `partOperation`
- **ipc.html:** Added `#op-info-bar` div with "Instructions" and "Sequence" tab elements and a `#info-panel` floating container, positioned between header and main content
- **ipc.js:**
  - Added `opInstructions` and `opTools` to state
  - `selectOp()` extracts written descriptions and tools from the op data, calls `renderInfoBar()`
  - `renderInfoBar()` shows/hides tabs based on data availability (hides bar entirely if op has neither)
  - `showInfoPanel(type)` renders HTML instructions or a sequence table (Seq, Tool, Holder, OOH, Description)
  - Hover delay system: `scheduleHideInfoPanel()` / `cancelHideInfoPanel()` with 150ms grace period so mouse can travel from tab to panel without it disappearing
  - `esc()` helper for safe HTML escaping in sequence table cells
- **ipc.css:** Styled `#op-info-bar` (thin flex row, `var(--s2)` background), `.info-tab` (small accent-colored labels with hover highlight), `#info-panel` (absolute-positioned dropdown with shadow, 600px max-width, 400px max-height, scrollable), `.seq-table` (compact bordered table)

**Bugs fixed during build:**
- ProShop API returned "Expected a selection on object field tool" — `tool` is a full `Tool` object type, not a string; fixed by selecting `tool { toolNumber description }` sub-fields
- Hover panel disappeared instantly when moving mouse from tab to panel — fixed with 150ms delayed hide + cancel-on-reenter pattern

**Key decisions:**
- Hover-reveal (not click-toggle) keeps it zero-footprint on screen when not needed
- Instructions tab renders raw HTML from ProShop (formatting tags only, no scripts)
- Sequence table sorted by `sequenceNumber`, shows tool description with fallback to toolNumber

**Status:** Complete and tested — working on WO 26-0070

---

## 2026-03-11

### Project 10: Conversational ProShop — Claude-Powered v2 Upgrade
**Task:** Revisit the old regex-based conversational ProShop prototype and upgrade it with Claude API capabilities

**What was done:**
- Reviewed the January 2026 regex-based prototype (68% accuracy on realistic queries)
- **Built Claude intent classifier (`claude_intent_classifier.py`):**
  - Defined all 18 query templates as Claude Haiku tools (tool-use API)
  - Claude picks the correct tool from natural language — handles typos, slang, indirect phrasing
  - Drop-in replacement for the regex `classify_intent()` function
- **Built comparison test harness (`test_classifier_comparison.py`):**
  - 25 test queries: 10 standard, 5 edge cases, 10 hard (typos, slang, no keywords)
  - Result: **Regex 68% vs Claude 100%**
  - Hard queries regex failed on: "anything running behind schedule?", "how many jobs we got going", "what's our biggest job", "pull up the ops list for 25-0001"
- **Built conversation memory (`conversation_manager.py`):**
  - Tracks last 20 user/assistant turns
  - Enables follow-up questions: "What operations does it have?" after asking about a WO
  - Tested 3-turn conversation — pronoun resolution ("it") worked perfectly
- **Built Claude response formatter (`claude_response_formatter.py`):**
  - Feeds raw ProShop JSON through Claude Haiku for natural language output
  - Proactively flags urgent items (late orders, data inconsistencies)
  - Markdown-formatted, scannable for shop floor use
- **Built integrated CLI (`cli_claude.py`, `proshop_chat_claude.py`):**
  - Wires together: Claude classification → ProShop GraphQL → Claude formatting
  - Auto-loads Anthropic API key from `../11. Proshop Mobile App/.env`
  - Supports interactive mode, single query, and debug mode
- **Fixed ProShop credentials:**
  - Old Fusion Integration (`3923-9C1C-7291`) is broken (scope corrupted)
  - Switched to `0615-12FB-C88D` ("Fusionconnector") with scope `parts:rwdp+workorders:rwdp+users:r`
- **Attempted to add `fixtures:r` scope:**
  - ProShop admin scope editor changes didn't save on `0615-12FB-C88D`
  - Discovered `BA16-EFAF-B154` ("ClaudeCodeResearch") has broader scope (`+toolpots:r+tools:r`)
  - `fixtures:r` is a separate module — not included in `tools:r`
  - Work cells (machines) and users data confirmed accessible via ClaudeCodeResearch app
- **Updated `10. PROJECT_STATUS.md`** with full v2 architecture, credentials, session log

**Performance:**
- Total query time: ~3.3s (1.3s classify + 0.4s ProShop API + 1.6s format)
- Cost per query: ~$0.002 (two Haiku calls)
- Daily cost at 100 queries: ~$0.20

**Key decisions:**
- Claude Haiku for both classification and formatting (fast + cheap)
- `tool_choice: "any"` forces Claude to always pick a tool (no free-text responses)
- Conversation history trimmed to last 6 messages for classifier (3 turns is enough for pronoun resolution)
- Kept original regex system intact for comparison/fallback

**Bugs fixed during build:**
- Windows cp1252 encoding crashes on Unicode characters from Claude (checkmarks, emojis) — fixed with `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
- `set VAR=value && python` doesn't propagate env vars reliably in sandbox — auto-load from `.env` file instead
- Box-drawing characters (`─`) fail on cp1252 — replaced with ASCII dashes in test output

**Files created:**
- `src/claude_intent_classifier.py` — Claude Haiku tool-use intent classification
- `src/claude_response_formatter.py` — Claude Haiku natural language formatting
- `src/conversation_manager.py` — Multi-turn conversation memory
- `src/cli_claude.py` — Integrated Claude-powered CLI
- `proshop_chat_claude.py` — Root launcher (v2)
- `test_classifier_comparison.py` — Side-by-side regex vs Claude test harness

**Status:** Working — Claude-powered v2 complete. Next: add machine/work cell queries (scope available), resolve fixtures scope, build web interface for shop floor.

---

### Project 12: FASData — FocasMonitor Rebuild & Dashboard v2.2
**Task:** Get the expanded FocasMonitor collector running on TRAXIS, debug all FOCAS data streams, and enhance the Shop Hub dashboard with live machine data

**What was done:**

**FocasMonitor Collector — Build & Debug:**
- Built and deployed expanded FocasMonitor C# service on TRAXIS (self-contained .NET 10.0 win-x86)
- `machine_samples` table expanded to 55 columns, 8 tables total
- Schema auto-migration in `Database.cs` — uses `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` on startup
- **Servo loads**: Switched from struct-based to raw `byte[]` buffer P/Invoke to avoid marshaling segfaults. LOADELM = 12 bytes (int data + short dec + short unit + byte name + 3 reserve). Axis identified by name byte ('X','Y','Z','A').
- **Spindle load**: Same raw buffer approach via `cnc_rdspload_raw`
- **Multiple native crash investigations**:
  - `cnc_modal` — wrong struct for this DLL version, causes 0xC0000005 segfault. Removed.
  - `cnc_rdmacro` — needs 4 params (handle, var_no, length, buf), had 3. stdcall cleanup mismatch crashes. Removed.
- **Functions confirmed NOT working** on these 0i-series controllers:
  - `cnc_rdtool` → EW_NOOPT (3) on all 5 machines — tool management option not enabled
  - `cnc_machine2` → EW_FUNC (4) on all — machine coordinates not available
  - `cnc_distance2` → -7 on all — communication error
  - `cnc_diagnoss` → EW_FUNC (4) on all — diagnosis counters not supported
- Removed `cnc_machine2` and `cnc_distance2` calls from production build
- Cleaned all diagnostic logging for stable production deployment
- Service running stable, polling 5 machines (T2, M2, M3, M6, M8) every 60s

**Data streams confirmed working:**
- Spindle speed, feed rate (mm/min), run status, mode, motion
- Axis positions (X/Y/Z via cnc_absolute, units: 1/10000 mm)
- Spindle load, servo loads (X/Y/Z/A)
- Emergency stop, alarms
- Program number, program comment
- Overrides (spindle/feed), sequence number, block count
- Parameter snapshots (575 rows captured)

**Shop Hub Dashboard v2.0 → v2.2:**
- **v2.0**: Added live data to Flask API (`fasdata_live.py`): spindle_load, servo_load_x/y/z, axis_x/y/z, emergency, sequence_number, block_count. Fixed DB_PATH from Dropbox sync path to `C:\FASData\monitoring.db`. Added E-STOP badge (flashing), alarm badge, servo load bars, DRO positions, speed/feed/program display.
- **v2.1**: Removed all messaging features per user request (per-card messages, shop-wide messages bar, SHOP MSGS button, all related CSS/JS)
- **v2.2**: Dramatic meter overhaul:
  - Spindle load: semicircle arc gauge with color-coded glow (green <50%, yellow 50-80%, red >80% with pulsing animation)
  - Servo load bars: 10px tall, gradient fills, glowing borders, pulsing red glow at >80%, numeric % readouts per axis
  - Speed/feed: large 20px bold readouts with RPM / IN/MIN / PROG labels
  - Feed rate conversion: raw mm/min from FOCAS ÷ 25.4 = inches/min
  - Idle machines: mode and program number with holding torque bars

**Key technical lessons:**
- Raw buffer P/Invoke (byte[] + BitConverter) is safer than struct marshaling for FOCAS — avoids uncatchable native segfaults
- Native crashes from wrong struct sizes or wrong param counts are NOT catchable by try-catch
- FOCAS `actf.data` returns mm/min on these controllers (unit=0). 59055 mm/min = rapid traverse, 370 mm/min = 14.6 IPM slow feed.
- `[In, Out]` attribute needed on array parameters passed to native DLLs for marshaling back
- FOCAS mode codes: 0=MDI, 1=MEM, 3=EDIT, 4=HANDLE, 5=JOG, 6=TJOG, 7=THND, 8=INC, 9=REF

**Database stats (end of session):**
- Size: 0.7 MB (service started today)
- 990 rows in machine_samples, 575 in parameter_snapshots
- Growth: ~3,900 rows/day at 60s polling (~2 MB/day, ~500 MB/year)
- No purge/retention policy needed at this scale
- Poll interval could safely drop to 10-15s (~3 GB/year at 10s)

**Files modified:**
- `12. FASData Implementation\FocasMonitor\MonitoringService.cs` — servo/spindle raw buffer polling, removed non-working calls
- `12. FASData Implementation\FocasMonitor\Focas.cs` — raw P/Invoke overloads, mode codes, [In,Out] fix
- `12. FASData Implementation\FocasMonitor\Database.cs` — auto-migration
- `1. Proshop Automations\FASDataDashboard\fasdata_live.py` — DB_PATH fix, new API fields
- `1. Proshop Automations\FASDataDashboard\fasdata_dashboard.html` — complete live data panel rewrite (v2.0→2.2)

**Status:** Running — collector stable, dashboard live at localhost:8070. M4/M5/M7 not connected (need Ethernet).

---

### Project 12: FASData — Spindle Load Fix & Dashboard v2.2 (continued session)
**Task:** Fix incorrect spindle load readings, enhance dashboard meters, convert feed rate to inches/min, investigate data querying

**What was done:**

**Spindle Load Investigation & Fix:**
- Discovered spindle load values were wrong: M2 max=32,574, M3 max=32,237, M8 values of 375-432 during cutting (impossible percentages)
- Root cause: `cnc_rdspload` struct assumption was wrong — reading `ToInt16(splBuf, 4)` from ODBSPLOAD which has the wrong layout for these controllers
- Servo loads (0-105% range) were correct because they use LOADELM via `cnc_rdsvmeter_raw`
- **Fix:** Switched spindle load to `cnc_rdspmeter` (type=0 for load), which returns LOADELM structs — same format as working servo loads
- Added `cnc_rdspmeter_raw` P/Invoke overload in `Focas.cs`
- New parsing: read LOADELM (int data + short dec + short unit + byte name), apply `data × 10^(-dec)` scaling
- Fallback: if `cnc_rdspmeter` fails, try `cnc_rdspload` as before
- **Diagnostic dump confirmed** LOADELM layout on M6 (only machine online at end of day):
  - `ret=0, count=1, data=0, dec=0, name='S1'` — correct for idle spindle
  - Other machines (T2/M2/M3/M8) were powered off, so no data to compare yet
- Needs validation tomorrow with machines under load

**Deployment Lesson:**
- Elevated PowerShell via `Start-Process -Verb RunAs -ArgumentList` with inline commands silently fails (argument quoting issue with paths containing spaces)
- **Fix:** Write a `.ps1` script file, then `Start-Process powershell -Verb RunAs -Wait -ArgumentList '-ExecutionPolicy','Bypass','-File','path\to\script.ps1'`
- Service logs go to console (nowhere for a Windows service) — used `File.AppendAllText(@"C:\FASData\diag_spindle.log")` for diagnostic output instead of `ILogger`

**M8 Data Analysis:**
- Queried DB: M8 running program O763, active block "CHAMFER DEBURR PERIMETER AND HOLES"
- Estimated cycle time from block_count resets: ~95,000 blocks per cycle
  - Cycle 1: 11:12→12:31 (~1h 19m)
  - Cycle 2: 12:31→15:23 (~2h 52m, includes operator time between parts)
- Operation sequence visible from data: Seq 80 (roughing 3820 RPM) → Seq 85 (HSM 8085 RPM) → Seq 90 (boring/reaming 1528 RPM) → Seq 95 (chamfer 4584 RPM) → Seq 100 (1819 RPM) → Seq 105 (finishing 3820 RPM)

**Dashboard v2.2 Enhancements:**
- **Dramatic spindle load gauge:** Semicircle arc meter with color-coded glow, tick marks at 50%/80%, pulsing animation at high load
- **Dramatic servo load bars:** 10px tall with gradient fills, glowing borders, pulsing red glow >80%, per-axis percentage readouts with color coding
- **Large speed/feed readouts:** 20px bold numbers with RPM / IN/MIN / PROG labels underneath
- **Feed rate in inches/min:** FOCAS returns mm/min (confirmed: 59055 = rapid, 370 = 14.6 IPM slow feed). Dashboard divides by 25.4.
- **Idle machine display:** Mode and program number with holding torque bars visible

**Sampling Rate Discussion:**
- Current: 60 seconds per poll cycle
- FOCAS poll takes ~1-3s for all 5 machines
- Can safely reduce to 10-15s without crashing
- Below 5s risks overlapping polls
- DB growth at 60s: ~3,900 rows/day, ~500 MB/year
- DB growth at 10s: ~23,400 rows/day, ~3 GB/year
- No purge/retention needed at either rate — SQLite handles it fine

**Key technical lessons (new):**
- `cnc_rdspmeter` (type=0) is the correct function for spindle load on 0i-series — returns LOADELM with data/dec/unit/name fields
- LOADELM name byte confirmed: `0x53` = 'S', suffix `0x31` = '1' (Spindle 1)
- Windows service logging: `ILogger` goes to console (invisible). Use `File.AppendAllText` for diagnostics.
- Elevated PowerShell deploy: must use a .ps1 script file, not inline commands (quoting breaks with spaces in paths)
- `program_comment` column doesn't exist in DB — the field is `active_block_content` which captures full active block G-code + comments

**Files modified:**
- `12. FASData Implementation\FocasMonitor\MonitoringService.cs` — replaced `cnc_rdspload` with `cnc_rdspmeter` for spindle load, added file-based diagnostic logging
- `12. FASData Implementation\FocasMonitor\Focas.cs` — added `cnc_rdspmeter_raw` P/Invoke overload
- `1. Proshop Automations\FASDataDashboard\fasdata_dashboard.html` — dramatic meters, IPM feed rate, spindle load arc gauge (v2.2)

**Status:** Deployed and running. Spindle load fix needs validation tomorrow with machines under load. Dashboard live at localhost:8070.

---

## 2026-03-13

### Project 16: Fusion Tool Library Product ID Changer — UX Improvements
**Task:** Improve FusionToolAuditor add-in usability

**What was done:**
- **Auto-select Document library:** Palette now automatically selects and loads the current part's tool library on open (no manual dropdown selection needed)
- **Relabeled Refresh button:** Changed "Refresh" → "Connect to Libraries" to better describe its function
- **New "Connect to ProShop Tool Data" button:** Replaced the tiny "Load" button in the stats bar with a full-sized button in the main toolbar, matching the style of "Connect to Libraries"
- **Connection status indicators:** Both "Connect to Libraries" and "Connect to ProShop Tool Data" buttons turn green when their connection succeeds
- **Close button:** Added red "Close" button to dismiss the palette, with `closePalette` handler in Python that sets `_palette.isVisible = False`

**Files modified:**
- `FusionToolAuditor/palette.html` — UI changes (auto-select, button labels, connection indicators, close button)
- `FusionToolAuditor/FusionToolAuditor.py` — Added `closePalette` action handler

**Key decisions:**
- Document library auto-selected by matching `lib.location === 'Document'` after library list populates
- Connection buttons turn green (#107c10) on success rather than using a separate indicator

**Status:** Complete — needs testing in Fusion 360

---

## 2026-04-03

### Project 23: Air Compressor Communication GUI — Build, Calibration, Remote Stop Investigation

**Task:** Build a Flask web GUI for monitoring the EMAX 20HP rotary screw compressor via Modbus TCP (PUSR DR302 gateway → Logik 26-S controller). Then investigate remote start/stop capability.

**What was done:**

**1. Built full Flask web GUI (`compressor_web.py`, ~1150 lines):**
- Live pressure bar graph with start/stop/alarm markers (120-138 PSI cycle)
- Live temperature bar graph with warning/alarm markers (~83-91°C operating)
- Status detection via HR 4244 aux register: "RUNNING (Loading)" vs "RUNNING (Unloaded)"
- Weekly schedule display + editor — reads Timer1 (Mon-Fri, HR 1800) and Timer2 (all days, HR 1920)
- Maintenance status panel with static estimates from LCD readings
- Cabinet filter manual 6-month timer tracked via `cabinet_filter.json`
- START/STOP buttons (currently schedule editors only — see below)
- Configuration panel showing pressure setpoints, temperature limits, equipment info

**2. Pressure calibration:**
- Raw hi byte showed 99 PSI when LCD read 120 — discovered linear conversion needed
- Formula: `PSI = round(hi_byte * 0.75 + 45.75)` — confirmed matching LCD in real-time

**3. Timer system discovery and bug fixes:**
- Timer1 (HR 1800): Only supports Mon-Fri (5 days × 6 regs = 30 regs). Sat/Sun = Illegal Data Address
- Timer2 (HR 1920): All 7 days (42 regs)
- Time encoding: `(minute << 8) | hour` (e.g., 7685 = 05:30)
- Fixed Timer1 overflow bug: was reading 42 regs (overflowed into unrelated data), causing Saturday ghost schedule. Fixed to read 30 regs, decode 5 days

**4. Remote start/stop investigation (BLOCKED):**
- FC01 (coils) and FC02 (discrete inputs): NOT supported by this controller
- Scanned HR 20-4600 for command registers — found serial number, config, counters, logs, but no command register
- Tried 4 timer manipulation approaches for immediate stop — all failed (controller doesn't re-evaluate mid-cycle)
- Downloaded and extracted L26-S manual PDF — Alarm 33 references separate "MODBUS protocol communication" document
- Remote start/stop IS supported but the register map is proprietary/unpublished
- Must request "Modbus Register Map" from Logika Control (info@logikacontrol.it, +39 0362/37001) or EMAX

**5. Register map documented:**
- HR 1-10: Serial number ASCII ("EC00002447")
- HR 4096-4099: Controller ID "Logik26S"
- HR 4241 hi byte: Live pressure, HR 4243 hi byte: Live temperature
- HR 1290-1292: Pressure setpoints (bar×10), HR 1312-1315: Maintenance SET values
- HR 1348-1364: Drive parameters (DR0-DA9)
- HR 1679: Load hours (~10,692)
- HR 1540-1549: Incrementing counters (possible maintenance counters — needs investigation)

**Files created/modified:**
- `23. Air Compressor communication GUI/compressor_web.py` — Main Flask GUI (port 8085)
- `23. Air Compressor communication GUI/cabinet_filter.json` — Manual filter tracking
- `23. Air Compressor communication GUI/probe_coils.py` — FC01/FC02 scanner (confirmed none exist)
- `23. Air Compressor communication GUI/scan_control.py` — Register scanner for unexplored ranges
- `23. Air Compressor communication GUI/scan_live_area.py` — Deep scan of live data areas
- `23. Air Compressor communication GUI/live_decode.py` — Diagnostic register verification tool
- `23. Air Compressor communication GUI/scan_timers.py` — Timer/counter register scanner
- `23. Air Compressor communication GUI/REGISTER_MAP.md` — Comprehensive register map document
- `23. Air Compressor communication GUI/session_log.md` — Detailed project session log

**Key decisions:**
- Pressure conversion formula derived empirically from LCD comparison (not documented anywhere)
- Timer1 limited to 5-day read (Mon-Fri only) to avoid overflow into unrelated registers
- STOP button implemented as schedule editor (changes today's OFF time) since true remote stop register is unknown
- Wt4 (unload timer) = 30 min means even schedule-based stop takes 30 min for full shutdown

**6. Pressure reading clarification:**
- HR 4241 reads **compressor outlet pressure** — shows 0 when machine is off
- Residual air in receiver tank/shop piping is NOT visible via Modbus (no system pressure sensor on controller)
- Monitoring downstream system pressure would require a standalone transducer on the receiver tank or main header

**7. Dryer activation discussion:**
- Air dryer runs at 240V, currently no automatic on/off tied to compressor
- **Recommended: pressure switch + 240V contactor** (~$50-80) — set switch at ~80 PSI, auto-powers dryer when system has pressure
- **Alternative: current-sensing relay** on compressor feed — no plumbing, but dryer shuts off immediately with compressor (no delay for residual moisture)
- Optional time-delay relay (~$20) to keep dryer running 15-30 min after compressor stops
- Need to check: dryer nameplate amps, whether dryer has built-in remote start terminal

**Status:** GUI running at http://10.1.1.71:8085. Immediate remote start/stop blocked until proprietary Modbus register map is obtained from manufacturer. Next: contact Logika Control/EMAX, investigate HR 1540 area for maintenance counters, consider reducing Wt4 from 30min, check dryer for remote start terminal and amp draw.

---

### Project 3 / 15: Automatic Ordering Research & Fearless Emu Portal Alignment

**Task:** Determine what's required to implement automatic ordering — shop floor scans low-qty items, system creates POs or online orders automatically. Remove purchasing burden from Rene. Align with Fearless Emu portal build.

**What was done:**

**1. Reviewed Project 15 purchasing & inventory architecture:**
- `08_purchasing/module_purchasing.md` — Complete PO data model, vendor integration patterns, three-way match, auto-reorder logic (1,025 lines)
- `09_inventory/module_inventory.md` — Inventory items/levels/transactions, DDMRP planning, barcode scanning (1,013 lines)
- `11_contacts/module_contacts.md` — Unified customer/vendor contact model
- `13_shop_floor/module_shop_floor.md` — Mobile scanning interfaces, kiosk designs
- `23_integrations/module_integrations.md` — Event-driven architecture, vendor integration paths (email, portal, EDI, API, punchout)
- `01_api_discovery/api_gaps.md` — Confirmed ProShop has ZERO API for purchasing or inventory
- `25_feasibility/` and `24_gap_analysis/` — Full implementation estimates and gap analysis

**2. Reviewed Fearless Emu portal current state:**
- Read `traxis-architectural-brief.pdf` — Emu's architecture: Vue/Nuxt 3, PostgreSQL as source of truth, ProShop as isolated sync module, API-first
- Read `traxis-proposal_final.docx.pdf` — 5-phase plan, 88-140 hours, $4,520-$6,600
- Read `Drawing_Revisions_Portal_Spec.docx` — Four-stage revision escalation spec (pre-quote, active quote, accepted PO, in-production). Well-designed: "portal flags, Traxis decides."
- Phase 2 done: RFQ intake, admin dashboard, file management, customer list, notifications
- Phase 3 next: Customer login, file revisions, ProShop push, quoting, PO acceptance, comment threads

**3. Determined auto-ordering fits INTO the Emu's portal, not as a separate system:**
- Same app, different roles: customer, vendor, shop floor, admin
- Same PostgreSQL database, same API layer, different views per role
- Tom's earlier Softr/Airtable/Make.com portal work acknowledged as dead end — Emu's build replaces it

**4. Sent message to Fearless Emu with four schema recommendations:**
1. Companies table with `type` field (customer, vendor, both) — not hardcoded as "customers"
2. Parts table with `item_type` field (manufactured, purchased, consumable) — unified catalog
3. File/document system generic (linked to any entity by type + ID) — not hardcoded to drawings
4. Notification system role-aware (audience parameter) — serves customer, vendor, and shop floor alerts

**5. Vendor API research:**
- McMaster-Carr: No public API, actively blocks automation. Email PO best path. OCI punchout possible long-term.
- MSC Direct: Has EDI program for business accounts. Need to call MSC rep.
- Amazon Business: Has Business API / Punchout program.
- Local vendors (DBR1, LPM1, etc.): Auto-email PO is the sweet spot. AI can parse reply emails.

**Key decisions:**
- Auto-ordering is NOT a standalone system — it's modules 8, 9, 11 from Project 15 architecture built into the Emu's portal
- Emu doesn't need to build purchasing/inventory now, but schema must accommodate it
- Emu already has access to Project 15 for full context
- Next step is Emu's response to schema recommendations + scheduling a call to walk through Phase 2

**Status:** Research complete. Awaiting Fearless Emu response. Call to be scheduled.

---

## 2026-04-11

### Project 23: Air Compressor — Timer Bypass Bug Fix, Resume Schedule Feature

**Task:** Investigate why the compressor was running on Saturday morning (7:39 AM) despite the weekly schedule having Sat/Sun OFF. Add ability to detect and resolve timer bypass condition.

**What was done:**

**1. Root cause identified:**
- `CMD_START` (0x0001) starts the compressor outside of timer control — the weekly schedule cannot turn it off afterward
- `FLAG_ON_BY_TIMER` and `FLAG_TIMER_BYPASSED` flags from HR 1034 were defined in code but never decoded or displayed in the UI
- No endpoint existed to send `CMD_STOP_BYPASS_TIMER` (0x0010) to restore timer control

**2. Backend fixes (compressor_web.py):**
- Poll loop now decodes `on_by_timer` and `timer_bypassed` booleans from HR 1034 status flags
- New endpoint: `POST /api/compressor/resume_schedule` sends `CMD_STOP_BYPASS_TIMER` (0x0010) to HR 1036

**3. UI additions (schedule panel):**
- Timer mode indicator: "ON BY SCHEDULE" (green) / "BYPASSED (manual override)" (yellow) / "OFF" (gray)
- "Resume Schedule" button — only visible when timer is bypassed, with confirmation modal

**4. Utility:** Added `restart_server.bat` as manual fallback to Overseer-managed restarts.

**Key decisions:**
- Kept existing Start/Stop buttons sending CMD_START/CMD_STOP (0x0001/0x0002) unchanged — added Resume Schedule as a separate action rather than changing Stop behavior, to avoid surprises
- Noted for future: consider whether Stop should always re-engage the timer schedule

**Status:** Code complete, pending restart of service on 10.1.1.71 via Overseer dashboard. Overseer already manages Air Compressor service with auto-start and health monitoring.

---

## 2026-04-12

### Projects 1, 25: Migrate P25 Services into Overseer
**Task:** Move Telegram bot and scheduled tasks from service_wrapper.py into Overseer-managed services, enabling remote start/stop/restart from the dashboard on port 8060.

**What was done:**

1. **telegram_bot.py** — Added stdlib HTTP health endpoint on port 8100 (daemon thread). Tracks uptime, messages handled, last message time, tools loaded, conversation length. No new dependencies.

2. **agent_scheduler.py** (NEW) — Long-running scheduler replacing service_wrapper's scheduled task logic. Runs check_reminders.py (15min), run_audit.py (60min), scan_projects.py (daily midnight). Health endpoint on port 8101 with task status and exit codes. Supports `--once` flag for testing.

3. **overseer.py** — Added `AGENT_DIR` path, two service configs (TelegramBot on :8100, AgentScheduler on :8101), and two validators (`validate_telegram_bot`, `validate_agent_scheduler`). Both use `PYTHON_EXE -u` for unbuffered output with health server threads.

4. **service_wrapper.py** — Stripped bot management (`start_bot`/`check_bot`/`stop_bot`), all scheduled task logic (`_run_oneshot`, `maybe_run_*`), and related state. Now only launches Overseer + heartbeat/leader election.

**Files modified:**
- `25. Agent Exploration/telegram_bot.py` — health endpoint added
- `25. Agent Exploration/agent_scheduler.py` — NEW file
- `1. Proshop Automations/Overseer/overseer.py` — 2 services + 2 validators added
- `25. Agent Exploration/service_wrapper.py` — bot + scheduled tasks removed

**Key decisions:**
- Used stdlib `http.server` for health endpoints (no new dependencies)
- Used `PYTHON_EXE` (not `PYTHONW_EXE`) for both P25 services since they need health server threads + unbuffered stdout
- Kept leader election and Overseer launch in service_wrapper — it's the only thing NSSM needs to start

**Status:** Code complete, all 4 files pass syntax check. Needs deployment test on 10.1.1.71 after Dropbox sync.

---

## 2026-04-14

### Project 30: Material Label Extension — Initial Build

**Task:** Build a Chrome extension (MV3) that injects a "Print Material Label" button on ProShop WO pages, generates a label PNG client-side, and sends it to the Brother PT-P700 print service.

**What was done:**

- Created full project structure at `30. Material Label Extension/traxis-material-label/`
- **manifest.json** — MV3 targeting `traxismfg.adionsystems.com/procnc/workorders/*`, host_permissions for print service at 10.1.1.242:5002
- **service-worker.js** — Proxies PRINT_LABEL and CHECK_PRINTER messages to HTTP print service (bypasses HTTPS→HTTP mixed-content block)
- **label-generator.js** — Canvas API rendering: 128px tall label matching P9 convention (QR code left encoding `proshop://wo/{woNumber}`, 4 text lines right: WO number, material, part number, quantity)
- **content.js** — WO number from URL regex, DOM scraping for material/part/qty with GraphQL API fallback via session cookie, green button injection near Part Stock row, MutationObserver with 500ms debounce for AJAX navigation
- **content.css** — Green button (#2e7d32) with printing/success/error state animations
- Downloaded `qrcode-generator` library (Kazuhiko Arase) for QR code rendering
- Iterated on button placement: moved from page top → Part Stock row area → absolute-positioned at row's right edge
- Created project CLAUDE.md with Interfaces block

**Key decisions:**

- Service worker needed as HTTPS→HTTP proxy (ProShop is HTTPS, print service is HTTP)
- Reused P9 label conventions (128px/180DPI, `proshop://wo/` QR scheme) and P22 print payload format (`{image_base64, copies, label_name}`)
- DOM scraping first with GraphQL API fallback for material data — WO number always from URL (reliable)
- XPath search for "Part Stock" text to anchor button placement (faster than full element scan)

**Files created:**

- `30. Material Label Extension/CLAUDE.md`
- `30. Material Label Extension/traxis-material-label/manifest.json`
- `30. Material Label Extension/traxis-material-label/background/service-worker.js`
- `30. Material Label Extension/traxis-material-label/src/content.js`
- `30. Material Label Extension/traxis-material-label/src/content.css`
- `30. Material Label Extension/traxis-material-label/src/label-generator.js`
- `30. Material Label Extension/traxis-material-label/lib/qrcode.min.js`

**Status:** Needs testing — button appears on WO pages, but print functionality and DOM scraping accuracy not yet verified. Button placement needs refinement once ProShop DOM structure is inspected.

---

<!-- Template for new entries:

## YYYY-MM-DD

### Project N: Project Name
**Task:** Brief description

**What was done:**
- Bullet points of changes

**Key decisions:**
- Any architectural or design choices made

**Status:** Complete / In progress / Needs testing / Blocked by X

---
-->

## 2026-04-27

### Project 31: Photo Upload Service — Phase 3 (Overseer + QR Scanning)

**Task:** Add Overseer integration for auto-start/restart and jsQR scanning support to the Photo Upload Service.

**What was done:**
- Added PhotoUploadService to Overseer (`overseer.py`): path constant, service config (port 5003, HTTP health check, auto-start), validator function (checks status, ProShop API, queue counts, worker alive), VALIDATORS dict entry
- Added jsQR 1.4.0 CDN script to `base.html` for QR code decoding on tablet
- Fixed `parseProShopUrl()` in `photo.js`: added `proshop://wo/` protocol pattern (Project 30 material labels), WO year segment support (`/workorders/2025/25-0200`), parts customer prefix handling (`/parts/R2S1/R2S1-10020`), COTS `/ots/` path fix
- Updated P31 CLAUDE.md Phase 3 status, P1 CLAUDE.md interfaces (13 services), MEMORY.md project map, TRAXIS_ECOSYSTEM.md

**Key decisions:**
- `proshop://wo/` pattern placed first (highest priority) to match Project 30 QR labels before generic URL patterns
- P31 kept in "Partial / In Progress" in MEMORY.md until on-site testing confirms it works end-to-end

**Files modified:**
- `1. Proshop Automations/Overseer/overseer.py` — PhotoUploadService config + validator
- `31. Photo Upload Service/photo-uploader/templates/base.html` — jsQR CDN
- `31. Photo Upload Service/photo-uploader/static/photo.js` — parseProShopUrl() patterns
- `31. Photo Upload Service/CLAUDE.md` — Phase 3 status
- `1. Proshop Automations/CLAUDE.md` — interfaces (13 services)
- `TRAXIS_ECOSYSTEM.md` — P31 entry + P1 interface update

**Status:** Code complete, committed as c45cfd0. Needs on-site testing: Overseer dashboard, tablet QR scan, auto-restart.

---
