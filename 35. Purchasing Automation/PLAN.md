# Project 35 — Purchasing Automation

One-tap reordering of COTS / Tools / Parts items from any browser on the LAN. Operator clicks "Buy" on a ProShop item page; the request enters a per-rule auto-approve gate; on approval, Selenium creates the VPO in ProShop, downloads the PDF, and drafts a vendor email with the PDF attached.

## Goals (v1)

- Browser-button purchase trigger on ProShop COTS, Tools, and Parts pages (P30 extension territory)
- Two-condition auto-approve gate: `qty × unit_cost ≤ amount_threshold` **AND** `last_ordered > min_interval`
- Single-screen approval queue at `http://10.1.1.71:5003/approvals` (or a new P35 service — see "Hosting decision")
- Selenium-driven VPO creation (no API; acceptNewRecord gate is unsolved)
- Draft (not auto-send) vendor email via Microsoft Graph with VPO PDF attached
- Bootstrap a vendor → email map by scraping Sent Items in M365
- Hand off the cost-drift feedback loop to P27 — P35 publishes `vpo_number → entity_id` in `orders.db` so P27's parser can update ProShop unit_cost when vendor replies arrive

## Non-goals (v1)

- No Equipment "buy" button (durable items don't reorder)
- No equipment → COTS-consumables linking (v2)
- No vendor web-portal automation — for online vendors we surface the URL and mark "pending web order"
- No automatic price discovery (we read what ProShop already has)
- No multi-currency, no tax handling beyond what ProShop renders

## Architecture

```
ProShop COTS/Tools/Parts page
   │   (P30 extension button: "Buy")
   ▼
P35 Flask  (port TBD, e.g. 5008 — or fold into P31:5003)
   ├── POST /api/queue-order  ← extension posts {entity_type, entity_id, qty?}
   ├── Rules engine           ← reads rules.json, scrapes ProShop for last_ordered
   ├── SQLite queue           ← orders.db (pending / approved / sent / failed)
   ├── GET  /approvals        ← approval inbox (any LAN browser)
   ├── POST /api/approve/{id} ← approves a queued order
   └── Worker thread          ← pops "approved" → Selenium VPO + PDF + Graph draft
        │
        ├── Selenium → ProShop "New VPO" form (reuses upload_worker.py login)
        ├── PDF download via ProShop's "Print VPO" action
        └── Microsoft Graph → drafts email in Sent Items folder w/ PDF attached
```

## Hosting decision

Two clean options:

- **Fold into P31** — share the existing Flask + Selenium login + Overseer wiring. New routes: `/approvals`, `/api/queue-order`, `/api/approve/*`. New worker thread alongside `upload_worker.py`. Smallest infra footprint.
- **Standalone P35 Flask** — separates concerns; failure in purchasing doesn't take down photo upload. New port 5008, new Overseer entry.

**Recommendation:** fold into P31 for v1. The shared Selenium login alone saves a non-trivial amount of code; if it grows past ~500 lines, split it out as P35-standalone in a v2 refactor.

## Files (assuming fold-into-P31)

In `31. Photo Upload Service/photo-uploader/`:

| File | Purpose |
|------|---------|
| `purchasing/__init__.py` | new subpackage namespace |
| `purchasing/rules.json` | per-item / per-category rules (amount + interval) |
| `purchasing/rules.py` | loads rules.json, evaluates `should_auto_approve(item, qty, unit_cost)` |
| `purchasing/queue.py` | SQLite schema + CRUD for the order queue |
| `purchasing/proshop_scrape.py` | Selenium routines: scrape last-ordered date for an item, create VPO, download PDF |
| `purchasing/email_draft.py` | Microsoft Graph helper: draft message in Sent Items with PDF attachment |
| `purchasing/worker.py` | background thread: pops approved orders, runs the Selenium → email pipeline |
| `purchasing/vendor_map.json` | vendor → email-address map (bootstrap output, hand-edited after) |
| `purchasing/bootstrap_vendor_map.py` | one-shot: scrapes Sent Items via Graph for past VPOs, writes vendor_map.json |
| `app.py` | new routes: `/approvals`, `/api/queue-order`, `/api/approve/<id>`, `/api/reject/<id>` |
| `templates/approvals.html` | approval inbox page (rows: item / qty / vendor / $total / Approve / Hold) |
| `static/approvals.js` | approve/reject button handlers |

In `30. Material Label Extension/traxis-material-label/src/`:

| File | Purpose |
|------|---------|
| `buy-content.js` | injects "Buy" button on COTS / Tools / Parts pages (mirrors `cots-content.js` button-injection pattern) |

## Data shapes

### `rules.json`

```json
{
  "defaults": {
    "amount_threshold": 100,
    "min_interval_days": 30
  },
  "categories": {
    "lubricant":    { "amount_threshold": 250, "min_interval_days": 60 },
    "consumable":   { "amount_threshold": 150, "min_interval_days": 30 },
    "tool_insert":  { "amount_threshold": 500, "min_interval_days": 14 }
  },
  "items": {
    "LUB-116": { "category": "lubricant", "min_interval_days": 90, "notes": "55-gal coolant drum" },
    "THI-219": { "category": "consumable" }
  }
}
```

Resolution order: per-item override → category default → global default. Item rule takes precedence on each field individually so you can just say `"min_interval_days": 90` without re-declaring threshold.

### `vendor_map.json`

```json
{
  "MSC Industrial":  { "email": "orders@mscdirect.com",   "last_used": "2026-04-12", "use_count": 47 },
  "McMaster-Carr":   { "email": "online_only",            "online_url": "https://mcmaster.com/...", "last_used": "2026-04-30", "use_count": 12 },
  "Master Chemical": { "email": "sales@masterchem.com",   "last_used": "2026-03-20", "use_count": 5 }
}
```

`"email": "online_only"` flags vendors that don't take emailed POs; the worker opens `online_url` in a new tab and marks the queue entry `pending_web_order` for the operator to confirm.

### `orders.db` (SQLite)

```sql
CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  entity_type TEXT,           -- cots / tool / part
  entity_id TEXT,             -- LUB-116, etc.
  qty REAL,
  unit_cost REAL,
  vendor TEXT,
  brand TEXT,
  edp TEXT,
  status TEXT,                -- pending / approved / vpo_created / emailed / pending_web_order / done / failed
  vpo_number TEXT,            -- filled after Selenium creates the VPO; also read by P27 to map replies → entity_id
  pdf_path TEXT,              -- local path to downloaded VPO PDF
  email_draft_id TEXT,        -- Graph message ID once draft is created
  created_at TIMESTAMP,
  approved_at TIMESTAMP,
  approved_by TEXT,           -- "auto" or operator name
  completed_at TIMESTAMP,
  error TEXT
);
```

## Build order (phased)

### Phase 0 — bootstrap vendor map (one-shot, runnable before the rest)
- `bootstrap_vendor_map.py`: query `me/mailFolders/SentItems/messages` filtered to `hasAttachments=true` and subject containing `VPO`, parse To addresses, group by vendor (best-effort from subject/attachment name), write `vendor_map.json` for hand review

### Phase 1 — queue + approvals UI (no Selenium yet)
- SQLite schema, `queue.py`, `rules.py`
- `/api/queue-order` endpoint accepts a queue request and applies rules
- `/approvals` page renders pending orders + approve/reject buttons
- P30 extension `buy-content.js` button → POST to queue endpoint
- Stops short of actually creating VPOs — approval just marks the row `approved` and that's it
- **Milestone:** you can click "Buy" on a COTS page and see it land in the approval inbox

### Phase 2 — Selenium VPO creation
- `proshop_scrape.py`: log into ProShop (reuse P31's `upload_worker.py` login), navigate to "New VPO", fill line items, save, capture VPO number
- `worker.py` background thread: pops `approved` orders, runs the create-VPO routine, updates row to `vpo_created`
- Download the VPO PDF (Selenium "Print" → save dialog → known download path)
- **Milestone:** approval triggers a real VPO in ProShop with PDF on disk

### Phase 3 — email draft
- `email_draft.py`: Graph `me/messages` create-draft with PDF attachment, To from vendor_map
- For `online_only` vendors, skip email and open the URL instead (extension can do this if the worker posts back a "needs_browser_action" signal)
- Status flips to `emailed` or `pending_web_order`
- **Milestone:** approved orders end up as drafts in your Outlook ready to send

### Phase 4 — polish
- Overseer dashboard badge: count of `status=pending` rows
- Approval inbox sort/filter (by vendor, by category, by age)
- "Approve all" batch button (with confirmation)
- Rule-edit page (web UI for `rules.json`) — optional, can edit the file directly for now
- Cost-drift report: items whose vendor price has shifted >5% over last 6 months (good for renegotiation conversations)

## Cost-feedback loop (lives in P27, not P35)

When a vendor reply lands, P27 already parses the doc for line items and totals. The new behavior P27 needs:
1. Detect that a reply references a known VPO (regex VPO number from subject / body / attached PDF)
2. Look up `vpo_number → entity_id` in P35's `orders.db` (read-only access)
3. Compare parsed unit price vs. ProShop's current `unit_cost`; if drift > threshold, Selenium-update ProShop
4. Drift threshold default: ignore changes < 1% or < $0.50, lives in P27's config

P35's only obligation here is keeping `orders.db` populated with VPO ↔ entity_id. Everything downstream is P27's domain.

## v2 / future

- Equipment → COTS consumables link (so equipment page shows "Reorder coolant" instead of just docs)
- Telegram push via P25 when something hits the queue
- Auto-send (skip draft) for trusted vendors
- Spend dashboards from `orders.db` join with ProShop cost data (P32 territory)
- **Proactive reorder sweep:** scheduled job that reads ProShop's existing open VPOs, scans COTS items for low-inventory / reorder-due conditions, and for any item that needs ordering AND isn't already on an open VPO, drafts a quote-request email automatically (same flow as the operator-triggered Buy button). Removes the "I forgot to reorder X" failure mode.
- McMaster price scraper (or PunchOut catalog setup) to short-circuit the email-quote loop for the highest-volume catalog vendor

## Open risks

- **Selenium "New VPO" form discovery** — same hidden-CKEditor surprise we hit on P31's photo upload. May need a `inspect_vpo_form.py` discovery script first (the way P31 has `inspect_upload.py`)
- **VPO PDF download path** — ProShop may stream the PDF inline rather than offering a download. Fallback: print-to-PDF via Chrome devtools protocol
- **Vendor email parse** — sales-rep addresses cycle out, generic `orders@` isn't always present. Manual prune required after bootstrap; script flags low-confidence matches
- **Browser button on Tools page must work in iframe** — P30's tool-content.js already handles this (three-layer cascade); buy-content.js can copy that pattern

## Interfaces (preview for CLAUDE.md when v1 lands)

Produces: `/api/queue-order`, `/api/approve/{id}`, `/api/reject/{id}`, `/approvals` page, orders.db, drafted Outlook messages with VPO PDF attachments, ProShop VPO records (via Selenium)

Consumes: ProShop web UI via headless Selenium (reuses P31 login), Microsoft Graph API (Mail.Read for bootstrap, Mail.ReadWrite for draft creation), `.traxis.env`, `rules.json`, `vendor_map.json`

Contracts: P30 extension button posts `{entity_type, entity_id, qty?}` to `/api/queue-order`. VPO record matches manual-flow conventions (shipTo Traxis MFG, orderNumber = brand+EDP, top approvedBrand) per existing memory rules.
