# ProShop API Usage — Recon Report

**Date:** 2026-04-13
**Complaint:** ProShop reports Traxis averaging ~1,600 API calls/hour
**Scope:** All numbered project folders under `Proshop Automation and Claude Projects`

---

## ProShop's Response (2026-04-13)

From Joao at ProShop (Adion Systems), relayed through Tom, in response to our inquiry:

> That sounds good Tom, thank you for investigating on your side. From what I can see, it seems like your team is querying for POs of different status - this seems to be happening every 15 minutes or so, retrieving every record in the system. In addition, it looks like a few queries related to work orders, time tracking and cots items are being run to retrieve every record in the system as well, which could prove to be very heavy depending on how many records you have on your ProShop site.
>
> In terms of documentation, I completely agree with you, it is lacking. We are working on improving this as we speak. However, if you add /api/graphql after .com on your ProShop site, you will be taken to your own GraphQL Playground. There you can find the complete schema, along with every available field and sub-field for both queries and mutations.
>
> It may not be as detailed of a documentation as one would hope for, but it can help your team to understand the fields they could filter by to obtain only the records truly needed

**Key takeaways for future optimization:**
- PO queries were pulling every record every 15 min (Shop Scheduler `vendorPOs`) — now every 2 hr
- Work orders, time tracking, and COTS queries also pull full table dumps — should add status/date filters to fetch only active/recent records
- GraphQL Playground available at `https://traxismfg.adionsystems.com/api/graphql` — full schema with all filterable fields
- ProShop is working on improving API documentation

**Action taken (2026-04-13):**
- Message Notifier: 30s → 30 min
- Time Status Display: 30s → 15 min
- Shop Scheduler: 15 min → 2 hr
- Estimated reduction: ~5,000–6,700 calls/hr → ~284–384 calls/hr

**Future pass (not yet done):** Add query filters so bulk queries only fetch active/open records instead of entire tables.

---

## Summary Table

| Script | Folder | Query Types | Call Pattern | Est. Calls/Hr |
|--------|--------|-------------|-------------|---------------|
| message_notifier.py | 18 | user.messages, users | 30s poll per user | **2,400–4,800** |
| time_status_display_v1.0.py | 1/TimeTrackerDashboard | user (timeClock, timeTracking), users | 30s poll per user | **~1,320** |
| sync.py | 19 | workOrders, ops, workCells, vendorPOs, pockets | 15min full sync + 2min writeback | **~1,200–1,350** |
| clock_feedback_display_v1_0_0.py | 1/TimeTracker/Productivity | latestClockPunches | 30s poll | **~120** |
| proshop_client.py (FASData) | 1/FASDataDashboard | workOrders | 5min poll | ~12 |
| accounting_ingest.py | 27 | addBill, addPackingSlip, addCustomerPo, contacts | 5min email poll + on-demand | ~5–12 |
| app.py (COTS Kiosk) | 17 | cotsItems, users, clockPunch | On-demand (user touch) | ~10–20 |
| app.py (Tool Kiosk) | 22 | workCell, tools, RTAs, pockets | On-demand (user touch) | ~15–30 |
| ProShopBridge.py | 1/ProShopBridge | workOrders, workOrder, updatePart | On-demand (Fusion palette) | ~0–20 |
| pocket_client.py | 1/ToolRenumber | workCell, workCells | On-demand (Fusion palette) | ~0–10 |
| client.py + queries.py (Mobile) | 11 | 17 query templates (WOs, parts, etc.) | On-demand + cache + rate limit | ~5–50 |
| FusionToolAuditor.py | 16 | tools (pageSize: 1000) | Manual button click | ~0–2 |

**Retired (P10 — Conversational ProShop):** 6 files with API code; project is marked retired. Not counted unless still running.

**Test/diagnostic scripts (P27):** `proshop_check_permissions.py` (×3 variants) — one-shot debugging tools, 0 calls/hr.

---

## Per-Script Detail

### 1. Message Notifier — `18. ProShop Message Notifier/`

**Files:** `app.py`, `message_notifier.py`, `config.py`

**Auth:** OAuth client_credentials, token cached with 300s refresh buffer, thread-safe lock.

**Queries:**
- `users(pageSize: 200)` — cached 1 hour
- `user(id: $userId) { messages(filter, pageSize, pageStart) }` — per-user inbox poll

**Pattern:** Background thread polls every **30 seconds** (`POLL_INTERVAL = 30` in config.py). Each cycle queries messages for every monitored user. With the count-then-fetch pattern, each user may trigger 2 queries per cycle.

**Estimated load:** 10 active users × 2 queries × 120 cycles/hr = **2,400 calls/hr**. At 20 users: **4,800 calls/hr**.

**Verdict:** **PRIMARY SUSPECT.** This single service likely accounts for the entire 1,600 complaint and more.

---

### 2. Time Status Display — `1. Proshop Automations/TimeTrackerDashboard/time_status_display_v1.0.py`

**Auth:** OAuth client_credentials, own `ProShopAPI` class, token cached with 60s refresh buffer.

**Queries:**
- `users(pageSize: 50)` — initial load
- `user(id: $userId) { timeClock(pageSize: 5), timeTracking(pageSize: 50) }` — per employee

**Pattern:** Daemon thread with `POLL_INTERVAL = 30` seconds. Each cycle queries every active employee individually.

**Estimated load:** 1 user-list + 10 per-user queries per 30s = 11 × 120 = **~1,320 calls/hr**.

**Verdict:** **SECOND SUSPECT.** Per-user polling at 30s with no batching is extremely expensive.

---

### 3. Shop Scheduler — `19. Shop Scheduler/`

**Files:** `sync.py`, `proshop_client.py`, `config.py`

**Auth:** OAuth client_credentials, token cached with 300s buffer.

**Queries:**
- `workOrders` — all active WOs
- `workOrder.ops` — per-WO operations (N queries where N = active WO count)
- `vendorPOs` — material readiness
- `workCells` — machine configuration
- `workCell.pockets` — per-machine pockets (M queries)

**Pattern:** Two background loops:
- Full sync every **900 seconds** (15 min): ~300 queries per cycle (1 WO list + N per-WO ops + 1 workCells + M per-machine pockets)
- Writeback every **120 seconds** (2 min): 1–5 mutations per cycle

**Estimated load:** 4 syncs/hr × 300 + 30 writebacks/hr × 3 = **~1,200–1,350 calls/hr**.

**Verdict:** **THIRD SUSPECT.** The per-WO and per-machine fan-out in each sync cycle is expensive.

---

### 4. Clock Feedback Display — `1. Proshop Automations/TimeTrackerDashboard/Productivity Pay Schemes and Possibilities/clock_feedback_display_v1_0_0.py`

**Auth:** OAuth client_credentials, own `ProShopAPI` class, token expires after 50 min.

**Queries:**
- `clockPunch.latestClockPunches(pageSize: 50)` — single efficient query

**Pattern:** Background poll every **30 seconds**.

**Estimated load:** 1 query × 120 cycles/hr = **~120 calls/hr**.

**Verdict:** Moderate. Efficient single-query design (contrast with time_status_display which queries per-user).

---

### 5. FASData Dashboard — `1. Proshop Automations/FASDataDashboard/`

**Files:** `proshop_client.py`, `fasdata_live.py`

**Auth:** OAuth client_credentials, token cached with 60s buffer. `fasdata_live.py` uses shared `ProShopClient` instance.

**Queries:**
- `workOrders(filter: { year }, pageSize: 500)` — WO list cache

**Pattern:** Background thread with `time.sleep(300)` — **5-minute** refresh. `fasdata_live.py` uses cache for part lookups, doesn't add API calls.

**Estimated load:** **~12 calls/hr**.

**Verdict:** Low. Well-designed caching.

---

### 6. Accounting Ingest — `27. Accounting Ingest/accounting_ingest.py`

**Auth:** OAuth client_credentials for ProShop + Microsoft Graph for email polling.

**Queries:**
- `contacts(pageSize: 500)` — cached 1 hour
- Mutations: `addBill`, `addPackingSlip`, `addCustomerPo`, `addPurchaseOrder`, `addQuote`

**Pattern:** Email poller thread at **300-second** (5 min) intervals checks Microsoft Graph. ProShop mutations only fire when a human approves a document in the UI.

**Estimated load:** ~1–2 ProShop queries/hr (contacts cache) + ~4–10 mutations/hr (document approvals). **~5–12 calls/hr**.

**Verdict:** Low. Email polling hits Microsoft Graph, not ProShop.

---

### 7. COTS Kiosk — `17. COTS - Tools Crib Kiosk/cots-kiosk/`

**Auth:** OAuth client_credentials.

**Queries:** `cotsItems`, `cotsItem`, `users`, `clockPunch.latestClockPunches`, plus CRUD mutations.

**Pattern:** Event-driven (touchscreen interactions). No background polling.

**Estimated load:** **~10–20 calls/hr** during shop hours.

---

### 8. Tool Assembly Kiosk — `22. Tool Assembly Management/tool-kiosk/`

**Auth:** OAuth client_credentials.

**Queries:** `workCell`, `workCell.pockets`, `tools`, `RTAs`, `users`, `workOrder`.

**Pattern:** Event-driven. `inventory_sync.py` runs on manual trigger only (50–100 queries per sync).

**Estimated load:** **~15–30 calls/hr** during shop hours, spikes to ~100+ during manual sync.

---

### 9. ProShop Bridge — `1. Proshop Automations/ProShopBridge/ProShopBridge.py`

**Auth:** OAuth client_credentials, inline, token cached in module globals.

**Queries:**
- `workOrders(filter: { year }, pageSize: 500)` — fetch by year
- `workOrder(workOrderNumber)` — single WO with operations
- `updatePart` mutation — **called once per tool** (not batched; 10 tools = 10 mutations)

**Pattern:** Event-driven (Fusion 360 palette interactions). No background polling.

**Estimated load:** **~0–20 calls/hr** (interactive), spiking to ~100+ during active parts export.

---

### 10. Tool Renumber / Pocket Client — `1. Proshop Automations/ToolRenumber/pocket_client.py`

**Auth:** OAuth client_credentials, inline, token cached 23 hours.

**Queries:**
- `workCell(potId)` with `pockets(pageSize: 100)`
- `workCells(pageSize: 50)`

**Pattern:** On-demand (called from Fusion 360 add-in).

**Estimated load:** **~0–10 calls/hr**.

---

### 11. Mobile App Backend — `11. Proshop Mobile App/proshop-mobile-backend/graphql/`

**Auth:** OAuth client_credentials, singleton client with thread-safe token lock.

**Queries:** 17 named query templates covering work orders, parts, operations, profitability.

**Pattern:** On-demand (mobile app requests). **In-memory cache with configurable TTL** + **rate limiting** (`RATE_LIMIT_SECONDS` between queries).

**Estimated load:** **~5–50 calls/hr** depending on mobile usage.

---

### 12. Fusion Tool Auditor — `16. Fusion Tool Library Product ID Changer/FusionToolAuditor/FusionToolAuditor.py`

**Auth:** OAuth client_credentials, inline, **hardcoded client secret in source** (security concern).

**Queries:**
- `tools(pageSize: 1000)` — all tools with approved brands

**Pattern:** Manual trigger (user clicks "Fetch ProShop Tools" in Fusion add-in).

**Estimated load:** **~0–2 calls/day**. Negligible.

**Note:** Client secret `2F64968E4E77...` is hardcoded at line ~342. Should be moved to `.traxis.env`.

---

### 13. Overseer — `1. Proshop Automations/Overseer/overseer.py`

**Auth:** None (does not call ProShop API directly).

**Pattern:** Health-check loop every **60 seconds** hitting local Flask `/api/health` endpoints for each of 12 managed services. These are local HTTP GETs, **not ProShop API calls**.

**Estimated load:** **0 ProShop API calls/hr**. (720 local health checks/hr.)

---

## Most Likely Culprits for High Call Volume

Assuming all services are running concurrently during shop hours:

| Rank | Service | Est. Calls/Hr | % of Total |
|------|---------|---------------|------------|
| 1 | **Message Notifier (P18)** | 2,400–4,800 | 45–60% |
| 2 | **Time Status Display (P1)** | ~1,320 | 20–25% |
| 3 | **Shop Scheduler (P19)** | ~1,200–1,350 | 20–25% |
| 4 | Clock Feedback Display (P1) | ~120 | 2% |
| 5 | All others combined | ~50–150 | 2–3% |
| | **TOTAL** | **~5,100–6,700** | |

The reported 1,600 calls/hr is **lower than the theoretical maximum**, which suggests either:
- Not all three top services run simultaneously
- The Message Notifier monitors fewer than 10 users
- The Shop Scheduler has fewer active WOs than estimated
- Some services were offline during measurement

**The three services that matter are P18, the TimeTracker dashboard, and P19.** Everything else is noise.

---

## Recommended Path to Shared Client

### Current State
Every project implements its own OAuth + GraphQL client. There are at least **8 independent implementations** of the same `client_credentials` → `Bearer token` → `POST /api/graphql` pattern. Token caching strategies vary (60s buffer to 23-hour TTL). No request counting, no rate limiting (except P11 mobile), no centralized logging.

### Effort Estimate per Script

| Script | Effort | Notes |
|--------|--------|-------|
| proshop_client.py (FASData) | **Low** — 1-line import swap | Already a clean client class; replace internals |
| pocket_client.py (ToolRenumber) | **Low** — 1-line import swap | Clean client class, urllib-based |
| ProShopBridge.py | **Medium** — extract inline auth | Auth + query functions are inline; need to extract |
| FusionToolAuditor.py | **Medium** — extract inline auth + remove hardcoded secret | Inline auth with hardcoded credentials |
| accounting_ingest.py | **Medium** — extract ProShop client class | Has its own inline ProShopClient; swap to shared |
| message_notifier / app.py (P18) | **Medium** — extract inline auth with thread lock | Token logic interleaved with notification logic |
| sync.py / proshop_client.py (P19) | **Low** — already a clean client | Similar pattern to FASData client |
| client.py (P11 Mobile) | **Low** — already well-structured | Has caching + rate limiting; may want to preserve |
| COTS Kiosk (P17) | **Low** — has own proshop_client.py | Swap import |
| Tool Kiosk (P22) | **Low-Medium** | Depends on internal structure |

### Recommended Architecture

1. **Create `shared/proshop_api.py`** — single OAuth client with:
   - Token caching + thread-safe refresh
   - Request counter + rate limiter (configurable per-service)
   - Logging of all queries with timestamps (for future auditing)
   - Configurable cache layer (TTL per query type)

2. **Batch API pattern** — For per-entity fan-out (the real problem):
   - Message Notifier: Replace N per-user `user(id)` queries with a single `users` query that includes message counts, if ProShop supports it
   - Time Status Display: Same — batch user time data into fewer queries
   - Shop Scheduler: Fetch all WO ops in one paginated query instead of per-WO

3. **Priority order:**
   - **Week 1:** Shared client + swap P18 Message Notifier (biggest win)
   - **Week 2:** Swap P1 TimeTracker + P19 Scheduler
   - **Week 3:** Remaining services (low-volume, low urgency)

### Quick Wins (No Shared Client Needed)

- **Increase poll intervals:** Message Notifier 30s → 120s cuts load by 75%. TimeTracker 30s → 60s cuts load by 50%.
- **Add request counting:** Drop a simple counter into each service's query method to get real numbers instead of estimates.
- **Kill clock_feedback_display if it's a prototype:** ~120 calls/hr for a possibly unused tkinter window.

---

## GraphQL Filter Fields Reference (Introspected 2026-04-13)

Per Joao's advice, these are the available filter fields for our highest-volume queries. Use these to fetch only active/relevant records instead of full table dumps.

**GraphQL Playground:** `https://traxismfg.adionsystems.com/api/graphql`

### WorkOrderFilter

Key fields for reducing payload:
- `status: String` — filter by "Active", "Complete", etc.
- `year: String` — already used
- `customer: String`
- `type: String`
- `part: String`
- `workOrderNumber: String`
- `lastModifiedTime: DateFilterInput` — only fetch recently changed WOs
- `personInCharge: String`
- `planningLevel: String`

Full list: activeInventoryFlag, asAdditionalChanges, asAssemblyFAI, asBaselinePartNumber, asDetailFAI, asDrawingNumber, asDrawingRevLevel, asFAINotComplete, asFullFAI, asPartialFAI, assemblyClass, asSerialNumber, bagSize, boxSize, buildToInventory, bulkImportId, certificationNumber, class, contact, countAsOnTime, createdBy, customer, customerPONumber, defaultRouting, drawingNumber, drawingRev, earlyAsPossible, editLog, faiCustomerApproval, faiCustomerApprovalBy, faiReviewedBy, faiReviewedByBy, faiSignature, fauxGrossProfitMargin, firstArticleRequired, includeNewRevTargets, installGroup, isTemplate, lastModifiedTime, part, partRev, personInCharge, planner, plannerDoesRunning, plannerDoesSetup, planningLevel, projectCode, qtyInWIP, standardizedLaborClass, status, templateGroup, type, wipIndirectOverhead, workOrderNumber, year

### PurchaseOrderFilter

Key fields:
- `orderStatus: String` — filter by open/closed/received
- `year: String`
- `supplier: String`
- `date: DateFilterInput`
- `lastModifiedTime: DateFilterInput`
- `received: String`
- `poType: String`

Full list: billingInformation, bulkImportId, confirmationNumber, createdBy, date, dueDateCannotBeMetMessage, editLog, freightOnBoard, id, initials, installGroup, isTemplate, lastModifiedTime, opTimeCritical, orderStatus, poRevision, poType, received, rootSupplier, shipTo, shipToAddressee, shipToAddressNickname, shipToCity, shipToCountry, shipToPhoneNumber, shipToState, shipToZipCode, shipVia, supplier, supplierAddressee, supplierCity, supplierCountry, supplierPhoneNumber, supplierState, supplierZipCode, taxable, templateGroup, templateId, year

### UserFilter

Key fields:
- `isActive: Boolean` — only fetch active employees
- `isScheduledResource: Boolean`
- `firstName: String`, `lastName: String`
- `id: String`

### WorkCellFilter

Key fields:
- `isScheduledResource: Boolean` — only scheduled machines
- `potId: String`
- `department: String`
- `commonName: String`

### ToolFilter

Key fields:
- `status: String`
- `toolNumber: String`
- `toolGroupLetter: String`
- `location: String`
- `lastModifiedTime: DateFilterInput`

### ClockPunchFilter

Key fields:
- `punchDate: DateFilterInput` — already used by TimeTracker
- `inOrOut: String`

### Recommended Filter Changes (future optimization)

| Query | Current | Recommended Filter |
|-------|---------|-------------------|
| Shop Scheduler `workOrders` | `pageSize: 500`, year only | Add `status: "Active"` |
| Shop Scheduler `vendorPOs` | All POs | Add `orderStatus: "Open"` |
| FASData `workOrders` | `pageSize: 500`, year only | Add `status: "Active"` |
| Message Notifier `users` | `pageSize: 200`, all users | Add `isActive: true` |
| Time Status Display `users` | `pageSize: 50`, all users | Already filters active in code — could push to API filter |
| Shop Scheduler `workCells` | All machines | Add `isScheduledResource: true` |
