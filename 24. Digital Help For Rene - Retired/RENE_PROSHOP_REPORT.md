# Rene Maldonado - ProShop Activity Report
**Generated: 2026-03-26**
**User ID: 011 | Email: rene@traxismfg.com | Status: Active**

---

## Executive Summary

Rene is **the single largest ProShop user at Traxis** by volume. He touches every major module: work orders, vendor POs, packing slips, contacts, invoices, and shop floor work. He is effectively operating as a one-man office AND part-time machinist.

---

## Complete ProShop Footprint

### 1. Work Orders — Rene creates ~88% of ALL work orders

| Year | Rene Created | Total WOs | Rene's Share |
|------|-------------|-----------|-------------|
| 2025 | 342 | 385 | **89%** |
| 2026 YTD | 112 | 128 | **87%** |

- **2026 Monthly Rate:** ~37 WOs/month (Jan: 34, Feb: 39, Mar: 39)
- Last-modified **237 of 385 WOs** in 2025 (62%)
- Each WO creation involves: part info, customer PO ref, quantities, due dates, operations, routing

### 2. Packing Slips — Rene creates ~81% of all packing slips

| Metric | Value |
|--------|-------|
| Total in system | 1,590 |
| Rene created | 406 of first 500 (**81%**) |
| Rene last-modified | 400 (**80%**) |
| Monthly rate (when active) | ~22/month |

He is the primary shipper. Each packing slip involves: selecting WO, line items, quantities, packaging method, carrier info.

### 3. Vendor POs — Rene is the #1 creator

| Metric | Value |
|--------|-------|
| Total in system | 1,518+ |
| Rene created | 308+ of first 500 (**62%**) |
| Monthly rate (when active) | ~30/month |

Each vendor PO involves: supplier selection, line items, costs, quantities, delivery dates, shipping terms.

### 4. Contacts — Rene manages 44% of supplier/customer records

| Metric | Value |
|--------|-------|
| Total contacts | 137 |
| Rene created | 39 (**28%**) |
| Rene last-modified | 61 (**44%**) |

### 5. Invoices — Secondary role

| Metric | Value |
|--------|-------|
| Total in system | 1,321 |
| Rene created | 49 of 500 (**9%**) |
| Primary creator | User 001 (448, **90%**) |

Rene handles invoices occasionally but it's not his main function.

### 6. Quotes — Minimal involvement

| Metric | Value |
|--------|-------|
| Total | 920 |
| Rene created | 10 of 500 (**2%**) |

### 7. NCRs (Non-Conformance Reports) — Occasional

| Metric | Value |
|--------|-------|
| Total | 266 |
| Rene created | 12 (**4%**) |

### 8. Shop Floor Time Tracking — 133 entries, ~285 hours

| Category | Count | Hours |
|----------|-------|-------|
| Running (R) | 125 | 269.8 |
| Setup (SU) | 2 | 6.4 |
| Maintenance (M) | 1 | 7.2 |
| Shipping (SH) | 1 | 1.1 |
| Inspection (1st) | 1 | 0.6 |
| Mfg Planning (MP) | 2 | 0.2 |

**Recent monthly shop hours:**
- Mar 2026: 9.1h | Feb: 19.8h | Jan: 27.1h | Dec: 25.0h | Nov: 16.1h | Oct: 12.6h

**Common hands-on tasks:** running parts, deburring, installing inserts (M4, Ti, helicoils), packaging, bending hooks, testing

### 9. Clock Punches
- **2,508 total** (full attendance history)

---

## The Big Picture: Where Rene Spends His Time

| Activity | Volume | Rene's Share | Automatable? |
|----------|--------|-------------|-------------|
| **Work Order creation** | ~37/mo | **87-89%** | HIGH - template from customer PO |
| **Packing Slip creation** | ~22/mo | **81%** | HIGH - generate from completed WO ops |
| **Vendor PO creation** | ~30/mo | **62%+** | HIGH - auto-gen from BOM/material needs |
| **Contact management** | ongoing | **44%** | MEDIUM - import from vendor/customer data |
| **WO status updates** | constant | **62%** | HIGH - auto from time tracking clock-outs |
| **Shop floor work** | 10-27 hrs/mo | 100% (his tasks) | LOW - physical work |
| **Invoice creation** | occasional | 9% | LOW - not his primary role |

---

## Automation Opportunities (Ranked)

### 1. Work Order Auto-Creation (HIGHEST IMPACT)
- **Current:** Rene manually creates ~37 WOs/month, entering part info, customer PO, quantities, dates, operations
- **Automation:** When a customer PO arrives, auto-generate WO from part history (operations, routing, targets all exist from prior runs)
- **API support:** `addWorkOrder` mutation works. Part templates with operations already exist.
- **Estimated time saved:** 15-20 hrs/month

### 2. Packing Slip Auto-Generation (HIGH IMPACT)
- **Current:** Rene manually creates ~22 packing slips/month
- **Automation:** When final op completes on WO, auto-generate packing slip with correct line items
- **API support:** `addPackingSlip` mutation available
- **Estimated time saved:** 5-8 hrs/month

### 3. Vendor PO Auto-Generation (HIGH IMPACT)
- **Current:** ~30 vendor POs/month, selecting supplier, entering line items
- **Automation:** When WO is created, auto-generate vendor POs from BOM (bill of materials)
- **API support:** Vendor PO mutations available
- **Estimated time saved:** 10-15 hrs/month

### 4. WO Status Auto-Updates (MEDIUM IMPACT)
- **Current:** Rene manually updates op completion status
- **Automation:** When operator clocks out of an op, auto-mark complete if qty matches
- **API support:** `updateWorkOrderOperation` with `isOpComplete`, `percentComplete`
- **Estimated time saved:** 3-5 hrs/month

### 5. Contact Auto-Import (LOWER IMPACT)
- **Current:** Rene creates/updates supplier and customer contacts
- **Automation:** Sync from accounting system or import from vendor onboarding forms
- **Estimated time saved:** 1-2 hrs/month

---

## Data Notes

- **API returns oldest-first, max 500 records, no pagination** — monthly rates for packing slips/vendor POs are based on historical data (2022-2023 window) not recent months
- **Purchase Orders (`purchaseorders` scope)** not available on any current OAuth client — would need to be added in ProShop admin to see Rene's full PO workload
- **Edit logs** require a separate scope not currently enabled — would show exact field-level changes Rene makes
- **Tasks** (`taskstable` scope) not enabled on the available client — would show tasks assigned to Rene
- **ClaudeCodeResearch client** (E88F-BE23-AC08) provides broadest access; scopes confirmed working: contacts, invoices, packingslips, messages, estimates, quotes, NCRs, equipment, training, vendorPOs, OTS/COTS

---

## Recommended Next Steps

1. **Add `purchaseorders:rwdp` + `taskstable:rwdp` scopes** to ClaudeCodeResearch client in ProShop admin — unlocks full purchasing visibility
2. **Build WO auto-creation** prototype — biggest time saver (~15-20 hrs/month)
3. **Build packing slip auto-gen** — straightforward once WO ops are tracked
4. **Consider browser activity tracker** on Rene's workstation for precise time-on-task data
