# Digital Rene — Master Report
## Automating Rene Maldonado's ProShop Workload at Traxis Manufacturing

**Date:** 2026-03-27
**Prepared by:** Claude Code (Project 24)
**Data source:** ProShop GraphQL API, live queries against production

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Who Is Rene in the System](#2-who-is-rene-in-the-system)
3. [ProShop Activity by Module](#3-proshop-activity-by-module)
4. [BOM & Materials Problem](#4-bom--materials-problem)
5. [BOM Gap Analysis Detail](#5-bom-gap-analysis-detail)
6. [COTS Inventory State](#6-cots-inventory-state)
7. [The Full Workflow Rene Does Today](#7-the-full-workflow-rene-does-today)
8. [Automation Opportunities](#8-automation-opportunities)
9. [API Access & Technical Notes](#9-api-access--technical-notes)
10. [Files & Artifacts](#10-files--artifacts)
11. [Next Steps](#11-next-steps)

---

## 1. Purpose

Rene Maldonado is the most active ProShop user at Traxis by a wide margin. He is the primary person creating work orders, vendor POs, packing slips, and managing contacts — while also doing hands-on shop floor work (running parts, deburring, installing inserts). This report documents everything discovered about his ProShop activity so we can identify what a "Digital Rene" agent could take over.

---

## 2. Who Is Rene in the System

| Field | Value |
|-------|-------|
| User ID | `011` |
| Name | Rene Maldonado |
| Email | rene@traxismfg.com |
| Status | Active |
| Clock Punches (all time) | 2,508 |
| Time Tracking Entries | 133 (285 hours) |
| ProShop URL | `https://traxismfg.adionsystems.com/procnc` |

For context, User `001` is Tom Buerkle (owner). In most modules, it's just Rene and Tom doing the work — Rene handles the bulk.

---

## 3. ProShop Activity by Module

### 3.1 Work Orders — 87-89% of all WOs are Rene's

| Year | Rene Created | Total | Share | Other Creators |
|------|-------------|-------|-------|----------------|
| 2025 | 342 | 385 | **89%** | 001: 41, 018: 2 |
| 2026 YTD | 112 | 128 | **87%** | 001: 16 |

**2026 monthly rate:** Jan: 34, Feb: 39, Mar: 39 (~37/month)

Rene also last-modified 237 of 385 WOs in 2025 (62%), meaning he's updating statuses, completing operations, and managing the lifecycle on most jobs even when someone else creates them.

**What WO creation involves:**
- Look up part (or create new)
- Enter customer PO reference, quantities, due date
- Set up operations (often copied from part template)
- Assign routing / work centers
- Trigger material ordering (manually, via vendor POs)

### 3.2 Vendor POs — #1 Creator

| Metric | Value |
|--------|-------|
| Total in system | 1,518+ |
| Rene created (of first 500) | 308 (**62%**) |
| Next highest creator | User 001: 127 |
| Monthly rate (active period) | ~30/month |

**Note:** The API only returns the first 500 records (oldest first, no pagination). Rene's share of recent vendor POs is likely higher since he's been the primary purchaser in 2025-2026.

### 3.3 Packing Slips — 81% Created by Rene

| Metric | Value |
|--------|-------|
| Total in system | 1,590 |
| Rene created (of first 500) | 406 (**81%**) |
| Rene last-modified | 400 (80%) |
| Monthly rate | ~22/month |

Rene is the primary shipper. Each packing slip involves selecting the WO, entering line items, quantities, packaging method, and carrier information.

### 3.4 Contacts — 44% Modified by Rene

| Metric | Value |
|--------|-------|
| Total contacts | 137 |
| Rene created | 39 (28%) |
| Rene last-modified | 61 (44%) |
| User 001 created | 67 (49%) |

Rene is the #2 contact manager but modifies more records than he creates — he's maintaining supplier and customer data.

### 3.5 COTS/OTS Items — 51% Created by Rene

| Metric | Value |
|--------|-------|
| Total COTS items | 201 |
| Rene created | 102 (51%) |
| Rene last-modified | 95 (47%) |

These are the off-the-shelf items in inventory: helicoils, inserts, fasteners, adhesives, cleaning supplies, filters, packaging materials.

### 3.6 Invoices — Secondary Role

| Metric | Value |
|--------|-------|
| Total | 1,321 |
| Rene created | 49 of 500 (9%) |
| Primary creator | User 001: 448 (90%) |

Rene creates invoices occasionally (likely when Tom is unavailable) but it's not his main function.

### 3.7 Quotes — Minimal

| Total | Rene Created |
|-------|-------------|
| 920 | 10 of 500 (2%) |

### 3.8 NCRs — Occasional

| Total | Rene Created |
|-------|-------------|
| 266 | 12 (4%) |

### 3.9 Time Tracking (Shop Floor Work)

| Category | Code | Entries | Hours |
|----------|------|---------|-------|
| Running | R | 125 | 269.8 |
| Maintenance | M | 1 | 7.2 |
| Setup | SU | 2 | 6.4 |
| Shipping Prep | SH | 1 | 1.1 |
| First Article Inspection | 1st | 1 | 0.6 |
| Manufacturing Planning | MP | 2 | 0.2 |
| Troubleshooting | TR | 1 | 0.1 |
| **TOTAL** | | **133** | **~285** |

**Recent monthly shop hours:**

| Month | Hours | Key Activities |
|-------|-------|----------------|
| Mar 2026 | 9.1 | Running, installing helicoils |
| Feb 2026 | 19.8 | Running, installing inserts, packaging |
| Jan 2026 | 27.1 | Running, installing inserts, packaging |
| Dec 2025 | 25.0 | Running, testing |
| Nov 2025 | 16.1 | Deburring (large batch — 4 entries on WO 25-0335) |
| Oct 2025 | 12.6 | Running, bending hooks, installing caps |

**Common hands-on tasks observed:**
- Running parts on machines (Bridgeport, etc.)
- Deburring (scotch-brite, hand tools)
- Installing helicoils (M3, M4, M5, M6, 2-56, 8-32)
- Installing PEM press-fit nuts (NFPC-M4)
- Installing titanium inserts (2TNC-06C-0207)
- Packaging finished parts
- Bending hooks, installing caps
- Cleaning, testing

### 3.10 Summary Table

| Module | Total Records | Rene's Share | Volume |
|--------|--------------|-------------|--------|
| Work Orders | 2,400+ | **87-89% creator** | ~37/mo |
| Packing Slips | 1,590 | **81% creator** | ~22/mo |
| Vendor POs | 1,518 | **62%+ creator** | ~30/mo |
| COTS Items | 201 | **51% creator** | ongoing |
| Contacts | 137 | **44% modifier** | ongoing |
| WO Modifications | all | **62% of changes** | constant |
| Shop Floor | 285 hrs | 100% (his tasks) | 10-27 hrs/mo |
| Invoices | 1,321 | 9% | occasional |
| Quotes | 920 | 2% | rare |
| NCRs | 266 | 4% | occasional |

---

## 4. BOM & Materials Problem

### The Core Issue

When a customer orders a part that needs BOM items (helicoils, inserts, raw material), Rene manually:
1. Remembers which items the part needs
2. Checks if they're in stock (physically walks to the shelf)
3. Creates a vendor PO if needed (~30/month)
4. Tracks delivery
5. Installs the items during the assembly/insert operation

**ProShop has the data structures for this** — every part operation can have a `billOfMaterials` table, and there's a full COTS inventory system with reorder points. But the data is incomplete, so the automation chain is broken.

### BOM Data Quality

| Metric | Value |
|--------|-------|
| Total parts in system | 1,016 |
| Parts with BOM data | 70 (14%) |
| Parts without BOM data | 946 (86%) |
| Total BOM line items | 172 |
| Complete items (have all fields) | 50 (29%) |
| Incomplete items | 122 (71%) |

### Gap Breakdown

| Missing Data | Count | % of all BOM items |
|-------------|-------|-------------------|
| **NO COST** | 108 | 62% |
| **NO SUPPLIER** | 51 | 29% |
| **NO PART NUMBER & NO DESCRIPTION** | 46 | 26% |
| **NO QTY** | 33 | 19% |
| **NO DESCRIPTION** (has PN) | 28 | 16% |
| **NO PART NUMBER** (has desc) | 26 | 15% |

### COTS Inventory Data Quality

| Metric | Value |
|--------|-------|
| Total COTS items | 201 |
| Items with reorder points set | **7** (3.5%) |
| Items with min qty on hand set | **7** (3.5%) |

Only 7 of 201 inventory items have any reorder trigger configured. The COTS system is essentially operating as a catalog, not an inventory management system.

### What This Means

The automation chain should be:
```
Customer PO arrives
  -> WO created (from part template)
    -> BOM read from operations
      -> COTS inventory checked
        -> Vendor PO auto-generated if below reorder point
```

But today:
```
Customer PO arrives
  -> Rene manually creates WO
    -> Rene remembers what the part needs from experience
      -> Rene physically checks the shelf
        -> Rene manually creates vendor PO
```

---

## 5. BOM Gap Analysis Detail

### By Supplier — Items Needing Cost

The most efficient way to fill cost data is to batch-request pricing from each supplier.

#### DBR1 — 21 items (likely a helicoil/insert distributor)

These are mostly the same 3 part numbers repeated across multiple assemblies:

| BOM Part Number | Description | Used On | Qty/Part |
|----------------|-------------|---------|----------|
| 2TNC-06C-0207 | Titanium insert | R2S1-10016, -10016(Ti), -10016-OLD, -10020, -10130, -10163 | 18-36 |
| HELICOIL 1084-4CN60 | M4 helicoil | R2S1-10016, -10016(Ti), -10016-OLD, -10020, -10163 | 4 |
| PEM P/N: NFPC-M4 | Press-fit nut | R2S1-10016, -10016(Ti), -10016-OLD, -10020 | 4 |
| 1084-4CN040 | Helicoil variant | R2S1-10130 | 2 |
| R2S1-10243 | Insert (self-ref) | R2S1-10243 | 4 |
| R2S1-10312 | Insert (self-ref) | R2S1-10312, -10312(Ti) | 2 |
| R2S1-10701 | Insert (self-ref) | R2S1-10701 | 4 |
| ??? (unlabeled) | Unknown | R2S1-10051 | 8 |

**Action:** One call to DBR1 requesting unit prices for 2TNC-06C-0207, 1084-4CN60, 1084-4CN040, NFPC-M4 covers 18 of the 21 items.

#### TRA1 — 25 items (Traxis internal / sub-assemblies)

| Category | Items | Examples |
|----------|-------|---------|
| Sub-assemblies (SSI parts) | 9 | ssi-9301-60556, ssi-9303-62649, ssi-9303-62654 |
| Raw material (aluminum) | 7 | Aluminum Channel, Tube, Plate, Bar, Flange |
| Assembly components (CEL) | 5 | CEL1-013-0011-1, CEL1-013-0044 items 1-3 |
| Other | 4 | MAT-45, R2S1-10151, 1084-5cn050 helicoil |

**Action:** These are mostly internal costs that Tom/Rene can price from historical vendor POs or material invoices.

#### MCM1 — 4 items (likely McMaster-Carr)

| BOM Part Number | Used On |
|----------------|---------|
| ssi-1300-12943 | ALM1-ssi-9303-25142 |
| 97395A414 (pin) | DEP1-DT0498 |
| 91585A345 (screw) | R2S1-10451 |
| ??? (unlabeled) | LYN1-BH-A-E |

**Action:** McMaster part numbers are directly searchable on mcmaster.com for pricing.

#### NO SUPPLIER — 47 items

These are the worst: no supplier AND usually no part number or description. Many are shipping/packaging placeholders ("PACKAGE IN EVEN AMOUNTS!") or completely blank entries. These need manual identification — Rene would need to look at each part's drawing/operation and fill in what's actually needed.

### Fully Complete BOM Items (50 items — the good data)

These items have all fields populated and represent what the data should look like:

| Supplier | Count | Examples |
|----------|-------|---------|
| MCM1 (McMaster) | 21 | Screws, brackets, adhesive, magnets — all with costs |
| AUS3 | 7 | Sub-assemblies with costs ($7.50-$100+ each) |
| TRA1 | 3 | Internal parts with costs |
| Digikey | 1 | WAKEFIELD-VETTE heat sink, $88.47 |
| Various | 18 | Helicoils, magnets, brackets with costs |

---

## 6. COTS Inventory State

### Item Types

| Type Code | Description | Count |
|-----------|-------------|-------|
| THI | Threaded inserts (helicoils, PEMs) | 39 |
| TOO | Tooling consumables | 39 |
| MAT | Raw materials | 32 |
| WOHO | Work holding | 16 |
| PAC | Packaging materials | 15 |
| SHS | Shop supplies (hand tools, etc.) | 11 |
| CLN | Cleaning supplies | 7 |
| FAS | Fasteners | 7 |
| FIL | Filters (air compressor, water) | 7 |
| PIN | Pins / dowels | 7 |
| ABS | Abrasives (scotch-brite, cut-off wheels) | 5 |
| ADH | Adhesives (E6000, VHB tape, Nitto) | 3 |
| Other | Various | 13 |

### Items With Reorder Points (only 7)

| # | Description | Inventory | Min Qty | Reorder Pt |
|---|-------------|-----------|---------|------------|
| 1 | M5x0.8 Helicoil 1084-5CN050 | 464 | 50 | 0 |
| 5 | 2-56 helicoil x .086 lg, locking | 164 | 30 | 50 |
| 8 | M3x0.5 Helicoil 1XD SS | 31 | 0 | 0 |
| 11 | 8-32 Helicoil 1.5XD | 200 | 30 | 0 |
| 96 | M2.5x0.45 Helicoil 1XD SS | 14 | 0 | 0 |
| 104 | M6x1 Helicoil Tanged Free Running | 456 | 0 | 0 |
| 450 | 3M 5958FR VHB Tape 1" | 0 | 0 | 0 |

**Key observation:** Even the 7 items with reorder settings mostly have reorder point = 0, which means no auto-reorder would trigger. Only item #5 (2-56 helicoil) has a meaningful reorder point of 50.

### Items at Zero Inventory (potential stockout risk)

Multiple items show `inventoryQuantity: 0.0` — these include adhesives, abrasives, filters, and some raw materials. Without reorder points, nobody gets alerted when these run out.

---

## 7. The Full Workflow Rene Does Today

Based on the data, here is Rene's reconstructed workflow across a typical job:

### Phase 1: Order Intake
1. Customer PO arrives (email/portal)
2. Rene opens ProShop, creates a new Work Order (~37/month)
3. Enters part number, customer PO reference, quantity, due date
4. Sets up operations (usually copied from part template if repeat job)
5. Reviews BOM — mentally checks what materials/inserts are needed

### Phase 2: Purchasing
6. Rene checks if raw material is needed → creates vendor PO to material supplier
7. Checks if helicoils/inserts are in stock → physically checks shelf
8. If not in stock → creates vendor PO to DBR1, MCM1, etc. (~30 POs/month)
9. Tracks delivery — updates vendor PO status when materials arrive

### Phase 3: Production Support
10. Rene sometimes runs parts himself (Bridgeport, manual ops) — 10-27 hrs/month
11. Deburring, helicoil installation, insert pressing, packaging
12. Updates WO operation status as ops complete

### Phase 4: Shipping
13. When all ops complete, Rene creates packing slip (~22/month)
14. Selects WO, enters line items, quantities, packaging method
15. Arranges carrier, ships parts

### Phase 5: Administrative
16. Updates contact records when supplier info changes (44% of contacts)
17. Occasionally creates invoices (9%)
18. Occasionally files NCRs (4%)
19. Manages COTS inventory catalog (51% created by him)

### Additional Workflow Identified (user input)
20. **RFQ scanning** — incoming RFQs need to be read, dimensions extracted
21. **Toolpath estimating** — run time estimates entered for quoting
22. **ProShop estimate entry** — estimate data entered into ProShop for quotes

---

## 8. Automation Opportunities

### Tier 1: Highest Impact (30-40 hrs/month saved)

#### 1A. Work Order Auto-Creation from Customer POs
- **Problem:** 37 WOs/month created manually
- **Solution:** When customer PO arrives, match to existing part, auto-create WO with operations from part template
- **API:** `addWorkOrder` mutation works. Part templates with operations already exist.
- **Prerequisite:** Customer PO intake mechanism (email parsing, portal API, or manual trigger)
- **Estimated savings:** 15-20 hrs/month

#### 1B. BOM-Triggered Vendor PO Auto-Generation
- **Problem:** 30 vendor POs/month created manually from memory
- **Solution:** When WO is created, read BOM from part operations, check COTS inventory, auto-generate vendor PO if below reorder point
- **API:** Vendor PO mutations available. BOM data readable per operation.
- **Prerequisite:** BOM data cleanup (see Section 5 — 122 items need data)
- **Prerequisite:** COTS reorder points set (currently only 7 of 201 items)
- **Estimated savings:** 10-15 hrs/month

#### 1C. Packing Slip Auto-Generation
- **Problem:** 22 packing slips/month created manually
- **Solution:** When final operation on WO completes, auto-generate packing slip
- **API:** `addPackingSlip` mutation available
- **Prerequisite:** Reliable op-completion tracking (see 2A below)
- **Estimated savings:** 5-8 hrs/month

### Tier 2: Medium Impact (5-10 hrs/month saved)

#### 2A. WO Operation Auto-Complete
- **Problem:** Rene manually updates op completion status
- **Solution:** When operator clocks out and qty matches target, auto-mark op complete
- **API:** `updateWorkOrderOperation` with `isOpComplete`, `percentComplete`
- **Blocker:** Time tracking mutations require `users:rw` scope (currently only `users:r`)
- **Estimated savings:** 3-5 hrs/month

#### 2B. RFQ → Estimate Pipeline
- **Problem:** RFQs arrive, Rene manually reads them, enters data into toolpath estimator, then into ProShop estimates
- **Solution:** PDF/email parsing → dimension extraction → runtime estimation → ProShop estimate API
- **API:** `addEstimate` mutation available (needs `estimates:rwdp` scope, confirmed working)
- **Existing work:** Project 4 (Balloon Dimension Tool) already extracts dimensions from PDFs
- **Estimated savings:** 3-5 hrs/month

#### 2C. COTS Inventory Auto-Alerts
- **Problem:** Rene physically checks shelves; items run out without warning
- **Solution:** Set reorder points on all 201 COTS items; daily inventory check script alerts when below threshold
- **API:** `cotsItems` query returns `inventoryQuantity`, `minimumQuantityOnHand`, `minReorderPoint`
- **Estimated savings:** 2-3 hrs/month + eliminates stockout delays

### Tier 3: Foundational (enables Tier 1)

#### 3A. BOM Data Cleanup
- **What:** Fill in missing costs, part numbers, descriptions, and suppliers on 122 BOM items
- **Quick wins:**
  - 1 call to DBR1 prices 21 items
  - McMaster part numbers (97395A414, 91585A345) can be looked up online
  - TRA1 items are internal — price from historical vendor POs
- **Artifact:** `BOM_GAPS.csv` has every item with its current data and what's missing
- **Effort:** ~4-8 hours of Rene's time with supplier calls

#### 3B. COTS Reorder Point Setup
- **What:** Set `minimumQuantityOnHand` and `minReorderPoint` on all 201 COTS items
- **Currently:** Only 7 items have any settings, and most of those have reorder = 0
- **API:** Can be updated via mutations if `ots:rwdp` scope is used
- **Effort:** ~2-4 hours to set reasonable values based on usage patterns

#### 3C. ProShop OAuth Scope Expansion
- **What:** Add missing scopes to ClaudeCodeResearch client (E88F-BE23-AC08)
- **Missing scopes that need adding:**
  - `purchaseorders:rwdp` — see full PO data and create POs via API
  - `taskstable:rwdp` — see/manage tasks assigned to Rene
  - `customerpos:rwdp` — upgrade from read-only to full access
  - `users:rw` — enable time tracking mutations
- **Effort:** 5 minutes in ProShop admin (but see warning about scope corruption in API reference)

---

## 9. API Access & Technical Notes

### OAuth Clients Available

| Client | ID | Working Scopes | Notes |
|--------|-----|---------------|-------|
| **ClaudeCodeResearch** | E88F-BE23-AC08 | 25+ modules (broadest) | Missing: purchaseorders, taskstable, customerpos write |
| FusionToolAuditor | BA16-EFAF-B154 | parts, workorders, users, tools, toolpots | Narrow scope, no expansion tested |
| FusionConnector | 0615-12FB-C88D | parts, workorders, users | Legacy, narrow |
| Dimension Extraction | 99EB-27E6-8915 | parts, workorders, users | Same as FusionConnector |

### ClaudeCodeResearch — Confirmed Working Scope String

```
parts:rwdp+workorders:rwdp+users:r+toolpots:r+tools:rwdp+contacts:rwdp+
estimates:rwdp+quotes:rwdp+invoices:rwdp+bills:rwdp+packingslips:rwdp+
messages:rwdp+equipment:rwdp+training:rwdp+vendorpos:rwdp+ots:rwdp+
qualityprocedures:rwdp+nonconformancereports:rwdp+correctiveactionrequests:rwdp+
rtas:rwdp+companypositions:rwdp+formats:rwdp+standards:rwdp+
estimatesarchive:r+fixtures:rwdp+securityadmin
```

### Scope Gotchas (from Project 15 research)

| Issue | Detail |
|-------|--------|
| `tasks:rwdp` is WRONG | Correct scope name: `taskstable:rwdp` |
| `cots:rwdp` is WRONG | Correct scope name: `ots:rwdp` |
| Invalid scopes silently accepted | Token request succeeds but grants no access to that module |
| Read-only allows writes | `:r` scope does NOT enforce read-only — API only checks module-level access |
| Editing scopes in admin can corrupt client | The 3923 client was permanently broken after scope edits |
| `purchaseorders` is separate from `vendorpos` | Both must be added independently |
| `vendorPOs` query always accessible | Works with any valid token regardless of scope |

### Key API Patterns

| Operation | Query/Mutation | Key Fields |
|-----------|---------------|------------|
| Read part BOM | `part(partNumber) > operations > billOfMaterials` | customerPartNumber, quantity, unit, cost, supplierPlainText |
| Read COTS inventory | `cotsItems` | inventoryQuantity, minimumQuantityOnHand, minReorderPoint |
| Create work order | `addWorkOrder` | partNumber, qty, dueDate, etc. |
| Create packing slip | `addPackingSlip` | (needs field discovery) |
| Update WO operation | `updateWorkOrderOperation` | opNumber, isOpComplete, percentComplete |
| Create vendor PO | needs `purchaseorders:rwdp` | blocked on current clients |

### API Limitations

- **No pagination** — max 500 records per query, oldest first, no offset/cursor
- **No bulk operations** — one mutation per request
- **Rate limiting** — unknown, use 0.3s delay between requests (from Project 15)
- **Token validity** — 24 hours (86,400 seconds)
- **Part filter is broken** — use `part(partNumber:)` singular query instead of `parts(filter:)`

---

## 10. Files & Artifacts

| File | Description |
|------|-------------|
| `DIGITAL_RENE_MASTER_REPORT.md` | This report |
| `RENE_PROSHOP_REPORT.md` | Earlier activity report (superseded by this document) |
| `BOM_GAPS.csv` | Every BOM line item with current data and what's missing — 172 rows |

### Related Project Files

| Project | Path | Relevance |
|---------|------|-----------|
| 15. ProShop Replacement | `.env` | ClaudeCodeResearch credentials (broadest scope) |
| 15. ProShop Replacement | `01_api_discovery/scope_permission_map.md` | Full scope documentation |
| 15. ProShop Replacement | `01_api_discovery/api_discovery_report.md` | Complete API reference |
| 1. ProShop Automations | `.traxis.env` | All OAuth client credentials |
| 4. Inspection/Dimension | `Dimension Extraction Automation/` | PDF dimension extraction (reusable for RFQ scanning) |
| 10. Conversational ProShop | `src/proshop_client.py` | Python ProShop API client with caching |
| 20. Traxis Data | Various | Financial analysis scripts, crosswalk reports |
| Root | `PROSHOP_API_REFERENCE.md` | Master API reference document |

---

## 11. Next Steps

### Immediate (Rene can do this week)

1. **Price the DBR1 items** — one phone call covers 21 BOM items (helicoils, PEM nuts, Ti inserts)
2. **Look up McMaster prices** — 4 items with direct part numbers (97395A414, 91585A345, etc.)
3. **Set COTS reorder points** — start with the 39 threaded inserts (THI type) since those are used most in BOMs

### Short Term (this month)

4. **Add `purchaseorders:rwdp` and `taskstable:rwdp`** scopes to ClaudeCodeResearch client in ProShop admin
5. **Build BOM-triggered ordering prototype** — script that reads a WO's part BOM, checks COTS inventory, and drafts vendor POs for review
6. **Fill remaining BOM gaps** — work through BOM_GAPS.csv, focus on items with suppliers first (61 items)

### Medium Term (next 1-2 months)

7. **Build WO auto-creation** — template-based WO generation from customer PO intake
8. **Build packing slip auto-gen** — trigger when final op completes
9. **Build RFQ → estimate pipeline** — leverage Project 4's dimension extraction
10. **Set up COTS inventory monitoring** — daily check + alert when below reorder point

### Long Term (2-3 months)

11. **Full "Digital Rene" agent** — unified system that handles:
    - Customer PO intake → WO creation
    - BOM check → vendor PO generation
    - Op completion tracking → packing slip generation
    - Inventory monitoring → reorder alerts
    - RFQ processing → estimate generation
12. **Browser activity tracker** on Rene's workstation to measure time saved and identify remaining manual tasks

---

*Report generated from live ProShop API queries on 2026-03-27. Data reflects production state at time of query. BOM gap data exported to BOM_GAPS.csv for actionable follow-up.*
