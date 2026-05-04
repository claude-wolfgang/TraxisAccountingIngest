# Project 35 — Purchasing Automation

One-tap reordering of COTS / Tools / Parts items from any browser on the LAN. Operator clicks "Buy" on a ProShop item page; the request enters a per-rule auto-approve gate; on approval (Phase 2+), Selenium creates the VPO in ProShop, downloads the PDF, and drafts a vendor email with the PDF attached.

**Implementation home:** folded into P31's Flask app on port 5003 (see P31 CLAUDE.md). This folder holds the plan doc, bootstrap scripts, vendor map, and discovery scripts.

## Phase Status

- **Phase 0** (done): vendor-map bootstrap from M365 — scanned tom@'s Sent Items + rene@'s 7.7GB archived Inbox mbox; 37-vendor `vendor_map.json` produced.
- **Phase 1** (done): SQLite queue + `/approvals` web UI + P30 extension "Buy" button on COTS/Tools/Parts pages. Without unit_cost, falls through to manual review.
- **Phase 1.5** (done): auto quote-request email drafted via Microsoft Graph when unit_cost is missing on the page; capped at 3 drafts per vendor per day; lands in tom@traxismfg.com's "Purchasing - To Review" Outlook folder for human Send.
- **Phase 2** (planned): Selenium VPO creation. Needs an `inspect_vpo_form.py` discovery script first (mirror of P31's `inspect_upload.py` pattern).
- **Phase 3** (planned): Microsoft Graph email-draft for the actual VPO PDF (extends Phase 1.5's drafter).
- **Phase 4** (planned): polish — Overseer dashboard badge, batch-approve, sort/filter, optional rule-edit UI.

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

- **[NEEDS WOLFGANG] Service-restart fragility** — see P31 Next Steps. Until the dev-server zombie-socket pattern is fixed, deploys that require a Flask restart can wedge port 5003 and force a reboot of .71. Scoped to P31 because all P35 runtime lives there.
- **Phase 2: Selenium VPO creation** — write `inspect_vpo_form.py` first (visible-mode driver of ProShop's "New VPO" form) to discover selectors before building the VPO worker.
- **MFG+EDP enrichment for COTS and parts** — tool-page Buy clicks now use approvedBrands data in the quote-request email; mirror the same in COTS and parts paths. (See P31 Next Steps for the implementation pointer.)
- **Fix folder lookup** — `email_draft._ensure_folder()` only searches root-level mail folders; if the "Purchasing - To Review" folder gets nested under another folder (Wolfgang's organizational impulse), Flask will create a duplicate at root on next restart. Either walk childFolders recursively or persist the folder ID across restarts.
- **Cost-scrape brittleness** — the COTS-page Cost-column heuristic in P30's `buy-content.js` worked for LUB-116 but missed for THI-17. Inspect the THI-17 page DOM and tighten the column-finder.
- **Email name-extraction** — `vendors.first_name_of()` only confidently extracts a first name when the local part has a dot (e.g. jaime.gomez). For `briannab@`-style addresses we fall back to "Hello," — losing real name info. Optional: add a `first_name` field to `vendor_map.json` entries and prefer that.
- **CWS approval cycle** — P30 v1.6.0 (with the new Buy button) needs to be re-published to Chrome Web Store. Sideload-tested only.
- **Proactive reorder sweep (v2)** — see PLAN.md v2/future. Scheduled job that scans ProShop COTS for low-inventory items not already on an open VPO and drafts quote requests automatically.
- **McMaster price scraper (v2)** — short-circuit the email-quote loop for the highest-volume catalog vendor.
- **Add `ocaire.com` to `vendor_map.json`** once OC Pneumatics replies to the SMC AW40-04DG-A quote request (drafted 2026-05-04 from P26, sent by Wolfgang). Reply will confirm preferred contact; this is also the first SMC/pneumatic vendor in the map, so future spare orders for SMC parts (drains, filters, regulators across the floor) auto-route there.

**Done this session (2026-05-04):** AJ Rod auto-routing for tool requests (server-side default); MFG+EDP+description enrichment in tool quote-request emails (replaces internal tool numbers).

## Interfaces

Produces: `vendor_map.json` (consumed by P31 purchasing.vendors module), `PLAN.md` (canonical design doc), one-shot probe scripts. All operational code (queue, rules, draft, Flask routes) lives in P31; P35 produces no runtime services on its own.

Consumes: Microsoft Graph API for bootstrap probes (Mail.Read on tom@traxismfg.com Sent Items); local Thunderbird mbox at `C:\Users\Superuser\Dropbox\OPERATIONS Traxis\EMPLOYEES\Rene Maldonado Email Files\rene@traxismfg.com\rene@traxismfg.com.sbd\Inbox` for the rene@ archive scan.

Contracts: `vendor_map.json` schema (per-domain entry with `name`, `active_reps[]`, `default` email) is consumed by P31's `purchasing.vendors.find()`. Hand-edits in `vendor_map.json` are expected — script changes must keep schema stable. Phase 4 cost-feedback in P27 will read `purchasing.db` (managed by P31) for `vpo_number → entity_id` lookup.
