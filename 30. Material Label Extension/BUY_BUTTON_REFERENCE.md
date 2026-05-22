# Buy Button — Function Map and Test Recipes

Reference card for the orange **Buy** button injected by the Traxis Label Printer extension. Spans P30 (Chrome extension, button + scrape + POST) and P31 (Flask backend, queue + auto-approve + email draft + VPO worker).

Last verified end-to-end: 2026-05-22 against extension v1.6.1 + P31 on srv-01 (10.1.1.161:5003).

---

## 1. Where it appears

Injected by `traxis-material-label/src/buy-content.js` on three ProShop page families:

| Page type | URL pattern | Entity sent to backend |
|---|---|---|
| COTS detail | `/procnc/ots/*` | `entity_type=cots`, `entity_id=<COTS code>` (e.g. `SHS-132`) |
| Tools detail | `/procnc/tools/*` | `entity_type=tool`, `entity_id=<tool #>` (e.g. `B23`) |
| Parts detail | `/procnc/parts/*` | `entity_type=part`, `entity_id=<part code>` |

Button is orange, sits near the page's Purchasing/Vendor row. Same CSS module as the other label buttons (`src/content.css`).

---

## 2. Click → data flow

```
User clicks Buy
  ↓
buy-content.js prompts for qty (browser confirm-prompt)
  ↓
buy-content.js best-effort scrapes from top-level DOM:
  - unit_cost   (heuristic on Cost column — fragile, see Known Quirks)
  - brand       (Brand column)
  - vendor      (Vendor column)
  ↓
chrome.runtime.sendMessage({action:'QUEUE_ORDER', payload:{entity_type, entity_id, qty, unit_cost?, brand?, vendor?}})
  ↓
background/service-worker.js → POST http://10.1.1.161:5003/api/queue-order
  (Was .71:5003 in v1.6.0; moved to .161 in v1.6.1 with srv-01 cutover)
  ↓
P31 photo-uploader/app.py /api/queue-order
  ↓
purchasing/rules.py decides outcome (see §3)
  ↓
Inserted into purchasing.db (orders table) with status
  ↓
JSON response → service-worker → buy-content.js → toast on page
```

---

## 3. Backend outcome branches (P31)

The order's `status` after insertion is one of:

| Status | When | What happens |
|---|---|---|
| `auto_approved` | Has `unit_cost` and (qty × unit_cost) under per-item/per-category cap in `purchasing/rules.json` | (Phase 2) `worker.py` builds a VPO via ProShop GraphQL `addPurchaseOrder`. Status flips to `vpo_created`. Today: VPO worker built but blocked on blank-VPO field mapping (see P31 Next Steps). |
| `pending` | Has `unit_cost` but over the auto-approve cap | Surfaces in `/approvals` UI for human Approve / Reject. Manual approval flips to `approved`. |
| `awaiting_quote` | No `unit_cost` AND vendor is known AND today's quote-request count to that vendor < 3 | `purchasing/email_draft.py` drafts a vendor email in tom@'s "Purchasing - To Review" Outlook folder via Microsoft Graph. Vendor name → email address from `35. Purchasing Automation/vendor_map.json`. **Tool entities default vendor to AJ Rodco** regardless of scraped vendor (memory: AJ Rodco — sole tool vendor). |
| `pending` (manual review) | No `unit_cost` and no quote-request path available (vendor unknown, or 3/3 daily quotes already sent to that vendor) | Surfaces in `/approvals` for human triage. |
| `rejected` | Reached only after manual `POST /api/reject/<id>` (with `{reason}` body) | Stays in DB for audit but excluded from active queues. |

Three pieces of state to watch:
- `/api/queue-order` — POST endpoint (extension calls this)
- `/api/approve/<id>` and `/api/reject/<id>` — POST endpoints (UI buttons + manual)
- `/approvals` — HTML page showing Pending + Awaiting Quote + Recent tables, plus per-status counts

---

## 4. Tool-entity special case

For `entity_type=tool` (only), the server **discards scraped brand and vendor** and overrides them from the ProShop tool library via GraphQL:

- `vendor` → `"AJ Rodco"` (hardcoded — see memory: AJ Rodco — sole tool vendor)
- `brand` → `tools.approvedBrands[0].brandPlainText` (top approved brand)
- `vendorToolId` (EDP) → `tools.approvedBrands[0].vendorToolId`
- Email subject becomes `"{brand} {edp}"` e.g. `"YG-1 43584TF"`, falling back to description, then entity_id

Reason for discard: ProShop tool pages render the Purchasing table inside an iframe, so `buy-content.js`'s top-level-DOM scrape sometimes leaks the Vendor cell into the brand slot (produced "Aj Rod 43584TF" subjects in 2026-05-20 incident). Server-side override is now authoritative. See `project_proshop_tool_brand_vs_vendor.md` in memory and P31 commit `52ee3b2`.

---

## 5. Hosts the extension talks to (manifest)

Declared in `traxis-material-label/manifest.json` host_permissions:

| Host | Purpose | Code site |
|---|---|---|
| `https://traxismfg.adionsystems.com/*` | Read page DOM, GraphQL fallback | Every `*-content.js` |
| `http://10.1.1.242:5002/*` | Brother PT-P700 print service | `service-worker.js` `PRINT_SERVICE` |
| `http://10.1.1.161:5003/*` | P31 purchasing-queue + label-print proxy | `service-worker.js` `PHOTO_SERVICE` |

CWS reviewer checks the live privacy policy at https://claude-wolfgang.github.io/traxis-privacy/ matches this list exactly. Mismatch = rejection.

---

## 6. Known quirks

- **Cost-column scrape is fragile.** Heuristic in `buy-content.js scrapeUnitCost()` worked for LUB-116 but missed for THI-17 and FIL-157 (Amazon vendor rows). When unit_cost is missing, the order falls into `awaiting_quote` or `pending` even if ProShop has a visible price. See P30 Next Steps.
- **Tool pages render the Purchasing table inside an iframe** — `scrapeBrand`/`scrapeVendor`/`scrapeUnitCost` only see the top-level DOM, so they scrape garbage on tools. Server-side override (§4) papers over this for tools; COTS and Parts are still on the top-level-DOM path.
- **Daily per-vendor quote cap = 3.** After 3 quote-requests to the same vendor in one calendar day, additional no-unit-cost orders for that vendor fall to manual `pending` instead of drafting a 4th email.
- **The Buy button silently no-ops if `PHOTO_SERVICE` host is unreachable** — toast says success because service-worker doesn't always surface fetch errors to the content script. Server-side absence is the only reliable detection.

---

## 7. Test recipes

### 7a. Smoke test after extension code change (load-unpacked)

Use when patching `buy-content.js`, `service-worker.js`, or `manifest.json` host_permissions. Run from any PC that can reach `.161:5003`.

1. `chrome://extensions` → Developer mode ON → **Load unpacked** → select `30. Material Label Extension/traxis-material-label/`
2. Confirm version shown matches `manifest.json` and **disable** any CWS-installed instance (avoid double-button injection)
3. Open service-worker DevTools: click **service worker** on the extension card → Network tab
4. Open a known COTS or Tool page (e.g. `https://traxismfg.adionsystems.com/procnc/ots/SHS/SHS-132` or `/procnc/tools/CMD/CMD-2`)
5. Click orange **Buy** → qty `1` → confirm
6. Network tab should show `POST /api/queue-order` → **200**
7. Confirm order appears at `http://10.1.1.161:5003/approvals` with the right entity_id/qty/vendor
8. Reject the test order: `Invoke-WebRequest -Uri "http://10.1.1.161:5003/api/reject/<ID>" -Method POST -ContentType "application/json" -Body '{"reason":"test"}'`
9. **Remove the unpacked card from `chrome://extensions` when done** to avoid conflict with the CWS install

Last passed: 2026-05-22 on v1.6.1 unpacked, COTS SHS-132, order #7 landed, rejected cleanly.

### 7b. Server-side acceptance test (no Chrome required)

Use when patching `purchasing/rules.py`, `vendor_map.json`, or `app.py /api/queue-order`. Synthetic order via curl/Invoke-WebRequest.

```powershell
Invoke-WebRequest -Uri "http://10.1.1.161:5003/api/queue-order" -Method POST `
  -ContentType "application/json" `
  -Body '{"entity_type":"cots","entity_id":"PROBE-DELETE-ME","qty":1,"unit_cost":0.01,"vendor":"Amazon"}'
```

Expected: 200, JSON with `order_id` and `status`. Verify on `/approvals`. Reject afterward.

### 7c. Tool-entity API-authoritative override test

Use when patching tool-vendor or tool-brand resolution server-side.

1. POST a tool order with deliberately-wrong scraped brand/vendor:
   ```powershell
   Invoke-WebRequest -Uri "http://10.1.1.161:5003/api/queue-order" -Method POST `
     -ContentType "application/json" `
     -Body '{"entity_type":"tool","entity_id":"B23","qty":1,"brand":"WRONG_BRAND","vendor":"WRONG_VENDOR"}'
   ```
2. Check `/approvals` Awaiting Vendor Quote row for B23 — vendor must be "AJ Rodco" (not "WRONG_VENDOR")
3. Open the drafted email in Outlook (link on `/approvals`) — subject must be `"YG-1 43584TF"` (or current top-approved brand + EDP), not `"WRONG_BRAND ..."`
4. Reject the test order

### 7d. CWS-installed end-to-end (post-walk)

Use after running `deploy_client_cws.bat` on a shop PC, to confirm the CWS push landed and works for an operator.

1. On the shop PC: `chrome://extensions` shows "Traxis Label Printer 1.6.x" with **"Installed by enterprise policy"** badge (cannot be disabled by user)
2. Open any tool page → Buy button visible (orange)
3. Click Buy → qty `1` → confirm
4. Toast appears on page
5. From your desk: `http://10.1.1.161:5003/approvals` shows the order from the shop PC (you can see the entity_id and timestamp)
6. Reject the test order

---

## 8. Where the code lives

| Layer | File | Function |
|---|---|---|
| Extension UI | `traxis-material-label/src/buy-content.js` | Button injection, qty prompt, DOM scrape, sendMessage |
| Extension transport | `traxis-material-label/background/service-worker.js` | `queueOrder()` — fetch POST to PHOTO_SERVICE |
| Extension manifest | `traxis-material-label/manifest.json` | host_permissions, content_scripts.matches |
| Backend endpoint | `31. Photo Upload Service/photo-uploader/app.py` | `@app.route('/api/queue-order')`, `/api/approve/<id>`, `/api/reject/<id>`, `/approvals` |
| Backend rules | `31. Photo Upload Service/photo-uploader/purchasing/rules.py` | auto-approve evaluator |
| Backend rules data | `31. Photo Upload Service/photo-uploader/purchasing/rules.json` | per-item/per-category caps |
| Backend queue | `31. Photo Upload Service/photo-uploader/purchasing/queue.py` | SQLite CRUD on `orders` table |
| Backend vendors | `31. Photo Upload Service/photo-uploader/purchasing/vendors.py` | vendor_map.json lookup + first-name extraction |
| Backend email | `31. Photo Upload Service/photo-uploader/purchasing/email_draft.py` | Microsoft Graph draft into "Purchasing - To Review" folder |
| Vendor map | `35. Purchasing Automation/vendor_map.json` | vendor name → email + optional contact metadata |
| Tool API override | `31. Photo Upload Service/photo-uploader/proshop_client.py` `get_purchasing_info()` | Pulls top approvedBrand + vendorToolId for tools |
