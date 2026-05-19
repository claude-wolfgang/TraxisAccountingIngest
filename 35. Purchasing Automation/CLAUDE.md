# Project 35 — Purchasing Automation

One-tap reordering of COTS / Tools / Parts items from any browser on the LAN. Operator clicks "Buy" on a ProShop item page; the request enters a per-rule auto-approve gate; on approval (Phase 2+), Selenium creates the VPO in ProShop, downloads the PDF, and drafts a vendor email with the PDF attached.

**Implementation home:** folded into P31's Flask app on port 5003 (see P31 CLAUDE.md). This folder holds the plan doc, bootstrap scripts, vendor map, and discovery scripts.

## Phase Status

- **Phase 0** (done): vendor-map bootstrap from M365 — scanned tom@'s Sent Items + rene@'s 7.7GB archived Inbox mbox; 37-vendor `vendor_map.json` produced.
- **Phase 1** (done): SQLite queue + `/approvals` web UI + P30 extension "Buy" button on COTS/Tools/Parts pages. Without unit_cost, falls through to manual review.
- **Phase 1.5** (done): auto quote-request email drafted via Microsoft Graph when unit_cost is missing on the page; capped at 3 drafts per vendor per day; lands in tom@traxismfg.com's "Purchasing - To Review" Outlook folder for human Send.
- **Phase 2** (in progress): API-driven VPO creation via `addPurchaseOrder` + `overwritePurchaseOrder` under basic auth. Field mapping validated 2026-05-18 (test VPOs 263116, 263119). poType=General, two-step for Outstanding status. Pending: worker thread + queue integration.
- **Phase 2b** (planned): Amazon Business cart-add URL routing for Amazon-sourced items. `method_history` table + extension tab-open.
- **Phase 3** (planned): Microsoft Graph email-draft for the actual VPO PDF (extends Phase 1.5's drafter).
- **Phase 4** (planned): polish — Overseer dashboard badge, batch-approve, sort/filter, optional rule-edit UI, method_history admin UI on `/approvals`.

P27 owns the cost-feedback loop (parsing vendor reply emails to update ProShop unit_cost when actual price differs from quoted). P35 only needs to publish `vpo_number → entity_id` in `orders.db` for P27 to read.

## Files in this folder

| File | Purpose |
|------|---------|
| `PLAN.md` | Full architecture + phases + open risks |
| `vendor_map.json` | Bootstrap output; hand-edited 37-vendor map (domain → name + active reps + default email) |
| `probe_sent_vpos.py` | One-shot Graph diagnostic: scans tom@'s Sent Items for VPO emails, prints recipient domain summary |
| `probe_rene_mbox.py` | One-shot Thunderbird mbox parser: scans rene@'s archived Inbox for vendor email signal (sample mode default; --full for entire 7.7GB) |

The Flask code, queue DB, rules, vendor lookup, and email-draft helper all live in `31. Photo Upload Service/photo-uploader/purchasing/`.

## Next Steps

- **[NEEDS WOLFGANG] Delete test VPOs 263106 + 263119** from ProShop UI. 263106: created 2026-05-06, `remarks = "API-PROBE-2026-05-06 — DELETE ME"`. 263119: created 2026-05-18 with correct poType=General + orderStatus=Outstanding. Wolfgang already deleted 263116.
- **[NEEDS WOLFGANG] Inspect test VPO 263119** — `https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263119`. Should show poType=General, orderStatus=Outstanding, supplier=Dixie Tool Crib, LUB-116 linked, remarks="P35 auto-generated". Confirm it matches manually-created VPOs, then delete.
- **[NEEDS WOLFGANG] Service-restart fragility** — see P31 Next Steps. Until the dev-server zombie-socket pattern is fixed, deploys that require a Flask restart can wedge port 5003 and force a reboot of .71. Scoped to P31 because all P35 runtime lives there.
- **Phase 2 VPO worker (next build step)** — field mapping validated 2026-05-18. Remaining:
  1. **Build `purchasing/worker.py`** — PurchasingWorker background thread polling `orders.db` for `status='approved'` → `find_last_vpo_line` → `create_vpo` → `mark_vpo_created`.
  2. **Add `get_approved()`, `mark_vpo_created()`, `mark_failed()` to `purchasing/queue.py`.**
  3. **Wire worker startup into `app.py`** alongside existing `upload_worker`.
- **Phase 2b: Amazon Business cart-add routing** — Traxis has an Amazon Business account. Plan:
  1. Add `method_history` table to `purchasing.db` (entity_id → method/asin_or_url).
  2. In `/api/queue-order`, check method_history: if amazon + ASIN → build `amazon.com/gp/aws/cart/add.html?ASIN.1=...&Quantity.1=...` URL, return `{action: "open_url"}`.
  3. Extension handles `open_url` response → `chrome.tabs.create()` opens Amazon cart.
  4. Admin UI on `/approvals` page for managing method_history entries (add/edit/delete ASIN per item).
  5. ASINs entered one-by-one as items come up. FIL-157 is the first Amazon item (no VPO history, vendor scraped as "AMAZON").
- **MFG+EDP enrichment for COTS and parts** — tool-page Buy clicks now use approvedBrands data in the quote-request email; mirror the same in COTS and parts paths.
- **Cost-scrape brittleness** — the COTS-page Cost-column heuristic in P30's `buy-content.js` worked for LUB-116 but missed for THI-17 AND FIL-157. Inspect FIL-157 / THI-17 page DOM and tighten the column-finder.
- **CWS approval cycle** — P30 v1.6.0 (with the new Buy button) submitted for review 2026-05-14. Google flagged in-depth review due to host permissions. Shop PCs auto-update via ExtensionInstallForcelist after approval; until then only the sideloaded dev installs have the Buy button.
- **Fix folder lookup** — `email_draft._ensure_folder()` only searches root-level mail folders.
- **Email name-extraction** — optional: add `first_name` to `vendor_map.json` entries.
- **Proactive reorder sweep (v2)** — scheduled job scanning COTS for low-inventory items.
- **McMaster price scraper (v2)** — short-circuit the email-quote loop for the highest-volume catalog vendor.
- **Add `ocaire.com` to `vendor_map.json`** once OC Pneumatics replies.

**Done 2026-05-04:** AJ Rod auto-routing; MFG+EDP+description enrichment in tool quote-request emails.

**Done 2026-05-06:** API probe of `addPurchaseOrder` under basic auth; live mutation confirmed (test VPO 263106); Phase 2 reframed from Selenium → API; foundation modules built and dry-run-validated.

**Done 2026-05-18:** VPO field mapping validated via live test VPOs (263116, 263119). Fixed `proshop_vpo.py`: poType="General" (was "Standard"), two-step create flow for Outstanding status (add + overwritePurchaseOrder), error handling for silent GraphQL failures. Introspected all PO enums + 44 line-item fields. Planned two-track purchasing (VPO + Amazon Business cart-add URL). FIL-157 classified as Amazon item.

## Interfaces

Produces: `vendor_map.json` (consumed by P31 purchasing.vendors module), `PLAN.md` (canonical design doc), one-shot probe scripts. All operational code (queue, rules, draft, Flask routes) lives in P31; P35 produces no runtime services on its own.

Consumes: Microsoft Graph API for bootstrap probes (Mail.Read on tom@traxismfg.com Sent Items); local Thunderbird mbox at `C:\Users\Superuser\Dropbox\OPERATIONS Traxis\EMPLOYEES\Rene Maldonado Email Files\rene@traxismfg.com\rene@traxismfg.com.sbd\Inbox` for the rene@ archive scan.

Contracts: `vendor_map.json` schema (per-domain entry with `name`, `active_reps[]`, `default` email) is consumed by P31's `purchasing.vendors.find()`. Hand-edits in `vendor_map.json` are expected — script changes must keep schema stable. Phase 4 cost-feedback in P27 will read `purchasing.db` (managed by P31) for `vpo_number → entity_id` lookup.
