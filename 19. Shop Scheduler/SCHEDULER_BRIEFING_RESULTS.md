# Scheduler Briefing Results — 2026-03-25

---

## Task 1 — Project Inventory

### Summary Table

| # | Project | Purpose | Systems | Status |
|---|---------|---------|---------|--------|
| 1 | ProShop Automations | Multi-tool ERP automation suite (ProShopBridge, ProShopConnector, Overseer, ProgrammingTimer, FASDataDashboard) | ProShop, Fusion 360, FOCAS, SQLite, Windows | **Working** |
| 2 | YCM Post Processor | Lathe post for YCM NTC1600LY with ProShop metadata blocks | Fusion 360, YCM Lathe, ProShop | **Working** (v1.7.005) |
| 3 | Customer Portal | E-commerce portal — RFQ, order tracking, document delivery | Softr, Airtable, Make.com, ProShop, Dropbox | **Working/Partial** |
| 4 | Inspection Print | PDF dimension extraction via Document AI → ProShop upload | Google Cloud AI, ProShop | **Working** (v1.4.0) |
| 5 | Hyundai Post | G/M-code reference for Hyundai KF5600ii | Hyundai CNC | **Stalled** (docs only) |
| 6 | Chevalier Post | VMC post for Chevalier EM2040L with ProShop tool summary | Fusion 360, Chevalier VMC, ProShop | **Working** (v1.3.8) |
| 7 | Customer Outreach | Business development strategy (Saronic Technologies target) | None | **Pending** |
| 8 | Catastrophe Planning | Risk assessment and business continuity | None | **Stalled** |
| 9 | Shop Floor Cameras | Photo documentation system per WO via QR + UploadCam | Dropbox, Airtable, Make.com, Softr, ProShop | **Partial** (hardware pending) |
| 10 | Conversational ProShop | Natural language query interface for ProShop (Claude-powered v2) | ProShop API, Claude API | **Working** (v2) |
| 11 | ProShop Mobile App | FastAPI backend + planned PWA frontend for shop floor access | ProShop API, Claude API | **Partial** (backend scaffold only) |
| 12 | FASData Implementation | NC program traceability: Fusion → CNC → machine data logging | Fusion 360, FOCAS, ProShop, SQLite, Dropbox | **Partial** (TPM working, Capture blocked) |
| 13 | Preventive Maintenance | Label templates for battery replacement | Brother P-touch | **Unknown** (labels only) |
| 14 | Workstation Display | Chrome extension for In-Process Check measurements on shop floor | ProShop, Chrome, PDF.js | **Partial** (spec complete, build pending) |
| 15 | ProShop Replacement | Architectural research for ground-up ERP replacement | ProShop schema, all systems | **Research phase** |
| 16 | Fusion Tool Library | Fusion 360 add-in to correct Product ID → ProShop tool IDs | Fusion 360, ProShop | **Working** (v1.0, not symlinked) |
| 17 | COTS Crib Kiosk | Touch-screen tool crib inventory checkout kiosk | ProShop COTS API | **Planning** (Phase 0) |
| 18 | ProShop Message Notifier | Desktop overlay for new ProShop message alerts | ProShop API, LAN | **Working** (service, heartbeat active) |
| 19 | Shop Scheduler | Web-based scheduling UI for CNC work orders across machines | ProShop, SQLite | **Working** (service, heartbeat active) |
| 20 | Traxis Data | Financial analysis: ProShop labor vs actuals vs QuickBooks | ProShop, FASData, QuickBooks, Bank CSVs | **Working** (analytics) |
| 21 | Haas Communications | Raspberry Pi RS-232 bridge for Haas VF-5/40 program transfer | Haas CNC, Raspberry Pi, SSH/SCP | **Implementation** (hardware phase) |
| 22 | Tool Assembly Management | Tool usage pattern mining from ProShop data | ProShop | **Working** (analysis phase) |
| 23 | Air Compressor GUI | MODBUS TCP monitoring dashboard for EMAX compressor | EMAX compressor, PUSR gateway, Modbus | **Planning** (gateway on order) |
| — | API Projects | Mirror/archive of selected project API code | Various | **Stale** |
| — | All Projects Monitoring | Centralized project inventory and health dashboard | All projects | **Active** |

---

## Task 2 — Scheduler Contribution Mapping

### Projects That Directly Feed the Scheduler

| Project | Data It Provides | Connection Point | Modification Needed |
|---------|-----------------|-----------------|-------------------|
| **19. Shop Scheduler** | Core scheduling engine — machine assignments, gap-finding, urgency sorting, ProShop sync | **IS the scheduler** — extend it | Add readiness assessment layer, daily briefing output |
| **1. ProShop Automations (FASDataDashboard)** | Real-time machine utilization, idle time, current job on each Fanuc machine | SQLite DB at `FocasMonitor/focas_data.db` | Query DB for machine availability projections — when will current job finish? |
| **12. FASData (FocasMonitor)** | FOCAS machine samples with cycle times, program IDs, capture session data | SQLite DB polled by C# service | Use actual cycle times to improve "hours remaining" estimates vs ProShop targets |
| **20. Traxis Data** | Historical job overrun rates (68% of jobs overrun by +19.4%) | Analysis output files | Feed overrun multiplier into scheduler time estimates |
| **10. Conversational ProShop** | Proven ProShop GraphQL client with caching | Python module `proshop_client.py` | Reuse client code; could be the natural language interface to the daily briefing |
| **22. Tool Assembly Management** | Tool frequency data — which tools are used most, common setups | `tool_frequency_data.json` (263KB) | Cross-reference tool availability with upcoming job requirements |

### Projects With Indirect/Future Contributions

| Project | Potential Contribution | Gap |
|---------|----------------------|-----|
| **2. YCM Post / 6. Chevalier Post** | ProShop metadata blocks in NC programs identify which operation is running | Read-only; no scheduler changes needed |
| **16. Fusion Tool Library** | Correct Fusion→ProShop tool ID mapping for tool readiness checks | Not currently symlinked; needs activation |
| **21. Haas Communications** | Would bring Haas VF-5/40 into real-time monitoring (currently blind) | Hardware not assembled yet |
| **18. Message Notifier** | Could push "daily briefing ready" alerts | Needs notification trigger integration |
| **14. Workstation Display** | Operator-side confirmation that job setup is complete | Spec complete but not built |

### Gap Analysis — What No Existing Tool Provides

| Scheduler Need | Gap | How to Fill |
|---------------|-----|------------|
| **Material order status with ETAs** | ProShop has `partStockStatuses` with `psETA`/`psActualETA` but current scope lacks `contacts:r` and `purchaseOrders:r` to read supplier/PO data | Add `contacts:r+purchaseOrders:r` to OAuth client scope |
| **"Is this job ready to run?" composite flag** | No tool combines material + tooling + program + first article into a single readiness signal | Build readiness assessment logic in scheduler |
| **Programming queue for Garrett** | ProShop has `programmingPercentComplete` (12% populated) and Programming work center ops, but no queue prioritized by machine opening dates | Cross-reference unprogrammed ops with projected machine openings |
| **Purchasing alerts for Rene** | Lead time data exists in ProShop (`partStockStatuses`, `opMustBeBackOnDate`) but not surfaced in any tool | Build purchasing alert module that compares lead times to projected run dates |
| **Machine opening projections** | FocasMonitor has real cycle time data for Fanuc machines; Haas is blind; ProShop scheduler has scheduled dates | Combine FOCAS actuals + ProShop scheduled hours to project when each machine opens |
| **Daily briefing output format** | No tool generates a morning summary report | New module: pull all data → generate markdown/HTML briefing |

---

## Task 3 — ProShop Data Reality Check

### Data Source: 67 Active Work Orders, 478 Operations (186 Manufacturing)

### WO-Level Fields

| Field | Populated | Rate | Verdict |
|-------|-----------|------|---------|
| `dueDate` | 67/67 | 100% | **Usable** — every WO has a due date |
| `mustLeaveBy` | 67/67 | 100% | **Usable** — shipping deadline |
| `scheduledStartDate` | 55/67 | 82% | **Usable** — ProShop's own scheduling dates |
| `hoursCurrentTarget` | 67/67 | 100% | **Usable** — planned hours for the WO |
| `hoursTotalSpent` | 67/67 | 100% | **Usable** — actual hours consumed |
| `plannerPlainText` | 59/67 | 88% | **Usable** — who plans this job |
| `personInChargePlainText` | 59/67 | 88% | **Usable** — PIC assignment |
| `partStockStatuses` | 57/67 | 85% | **Partially usable** — see material deep-dive below |
| `preProcessingChecklist` | 57/67 | 85% | **Exists but unused** — see checklist deep-dive below |
| `planningPercentComplete` | 16/67 | 24% | **Sparse** — only tracked on some WOs |
| `programmingPercentComplete` | 8/67 | 12% | **Sparse** — rarely filled in |
| `planningLevel` | 13/67 | 19% | **Sparse** |
| `scheduledEndDate` | 0/67 | 0% | **Empty** — never populated at WO level |
| `qtyComplete` | 0/67 | 0% | **Empty** — always null at WO level |
| `deliverypriority` | 0/67 | 0% | **Empty** — never used |
| `earlyAsPossible` | 0/67 | 0% | **Empty** |

### Operation-Level Fields

| Field | Populated | Rate | Verdict |
|-------|-----------|------|---------|
| `scheduledStartDate` | 263/478 | 55% | **Usable** — over half of ops have ProShop-generated schedule dates |
| `scheduledEndDate` | 263/478 | 55% | **Usable** — matches start date population |
| `totalCycleTime` | 252/478 | 53% | **Usable** — best timing field overall |
| `setupTime` | 191/478 | 40% | **Partially usable** — non-zero on 40% of ops |
| `toolMaster` (tool assignments) | 170/478 | 36% | **Usable** — tool lists on 36% of ops (mostly mfg ops) |
| `minutesPerPart` | 129/478 | 27% | **Partially usable** — key for cycle time calculation |
| `runTime` | 124/478 | 26% | **Partially usable** — total run time estimate |
| `certifiedToRun` (set) | 133/478 | 28% | **Partially usable** — only on mfg/inspection ops |
| `certifiedToRun` (true) | 11/478 | 2% | **Critical finding** — almost nothing is certified |
| `firstArticleComplete` (set) | 136/478 | 28% | **Partially usable** |
| `firstArticleComplete` (true) | 16/478 | 3% | **Critical finding** — very few FAIs done |
| `breakdownComplete` (set) | 100/478 | 21% | Present on some ops |
| `breakdownComplete` (true) | 0/478 | 0% | **Empty** — never marked true |
| `billOfMaterials` | 26/478 | 5% | **Sparse** — BOM only on 26 ops |
| `runTimeSpent` | 20/478 | 4% | **Sparse** — actual time rarely recorded |
| `setupTimeSpent` | 7/478 | 1% | **Sparse** |
| `outsideProcessing` | 5/478 | 1% | **Sparse** — 5 ops have outside processing |
| `preProcessingCheckComplete` | 0/478 | 0% | **Empty** — never marked true |
| `percentComplete` | 0/478 | 0% | **Empty** |
| `operationDescription` | 0/478 | 0% | **Empty** — always null |

### Material Data Deep-Dive (`partStockStatuses`)

85% of WOs have material records. What's actually in them:

| Field | Status | Notes |
|-------|--------|-------|
| `material` | **Populated** | e.g., "Titanium", "Plastic", "Aluminum" |
| `materialGrade` | **Populated** | e.g., "Grade 2", "Delrin/ Acetal", "6061-T6" |
| `partStockType` | **Mostly empty** | "Round Bar", "Plate" when set, often null |
| `roughStockLength/Width/Height` | **Partially populated** | Stock dimensions when entered |
| `psETA` | **Empty** | Expected delivery date — never filled |
| `psActualETA` | **Empty** | Actual delivery date — never filled |
| `psQuantityQrdered` | **Empty** | Quantity ordered — never filled |
| `psPONumberPlainText` | **Blocked** | Requires `purchaseOrders:r` scope |
| `psSupplierPlainText` | **Blocked** | Requires `contacts:r` scope |

**Verdict:** Material *type* is known. Material *order status* (ETA, PO, supplier) is not being tracked in ProShop, and even if it were, the current OAuth scope can't read it.

### Pre-Processing Checklist Deep-Dive

85% of WOs have ~20 checklist items. Template questions include:
- Requirement Distillation Process (RDP) Complete
- Verify Customer Requirements
- Verify Rev
- Review Time Tracking
- Review Part Process Development
- Review All OP operations "Must be Back On Date", Lead Time, Vendor, Price
- Program verified / Program Checked
- First Article Complete

**Every single checklist item across all 67 WOs is unchecked (`all: false`).** The checklist template exists but nobody is using it. This is a significant process gap — the checklist was designed for exactly the readiness assessment the scheduler needs, but it's not being maintained.

### Work Cell Data (Machines)

23 work cells, 15 scheduled resources:

| Machine | Name | Type | Bottleneck | Tie-In Status | Department |
|---------|------|------|------------|---------------|------------|
| Mill-1 | Haas VF5 | Mill | No | — | Production Milling |
| Mill-2 | Smec #1 | Mill | No | Setup | Production Milling |
| Mill-3 | Smec #2 | Mill | No | — | Production Milling |
| Mill-4 | Black Robodrill | Mill | No | — | Production Milling |
| Mill-5 | White Robodrill | Mill | No | — | Production Milling |
| Mill-6 | Chevalier | Mill | No | — | Prototype |
| Mill-7 | 5-axis Robodrill | Mill | No | — | Prototype |
| Mill-8 | Hyundai-Wia KF5600II | Mill | No | Running | Production Milling |
| T2 | YCM NTC1600LY | Lathe | **Yes** | Running | Production Lathe |
| MILL-X | Mill Catch-All | Virtual | No | — | — |
| Program | Programming | Virtual | **Yes** | — | Programming |
| SAW-01 | Horizontal Bandsaw | Saw | No | — | Material Prep |
| INSPECT-01 | Final Inspection | Station | No | — | Inspection |
| Deburr/Clean | Final Deburr | Station | No | — | Cell System |
| SG | Surface Grinder | Mill | No | — | Prototype |

Bottlenecks flagged: **T2 (lathe)** and **Programming**. Tie-in status shows Mill-8 and T2 currently running.

### What's Missing Entirely

1. **Material order tracking** — ETA fields exist but are never populated. No way to know if material has been ordered or when it arrives.
2. **Tooling readiness** — `toolMaster` shows what tools are *assigned* to an op (36%), but there's no "tools are physically in the machine" flag.
3. **Program completion status** — `programmingPercentComplete` only populated on 12% of WOs. No reliable way to know if the NC program is done.
4. **Checklist compliance** — The pre-processing checklist is a dead feature. 0% completion across 67 WOs.
5. **Actual vs. planned actuals** — `runTimeSpent`/`setupTimeSpent` populated on <5% of ops. Must use FOCAS data or time tracking for actuals.
6. **Machine real-time status** — ProShop's `tieInStatus` is stale (some dates from 2017). FOCAS is the real source for Fanuc machines; Haas is blind.

### Scope Limitations (Fixable)

Current OAuth client (`BA16-EFAF-B154`) has: `parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r`

**Missing scopes needed for full scheduler:**
- `contacts:r` — customer names, supplier names on material orders
- `purchaseOrders:r` — PO numbers, PO status, delivery dates for materials
- `vendorPOs:r` — vendor purchase order details (currently returns null — may need different scope name)

**Warning:** Editing OAuth client scope in ProShop admin has previously corrupted a client (the 3923 client). Create a new OAuth client rather than modifying existing ones.

---

## Scheduler Architecture Recommendation

Based on this analysis, the daily job readiness scheduler should:

1. **Extend Project 19 (Shop Scheduler)** — it already has ProShop sync, machine model, gap-finding, and an active SQLite database
2. **Add a readiness assessment layer** that combines:
   - ProShop `certifiedToRun` + `firstArticleComplete` + `breakdownComplete` flags
   - Material availability from `partStockStatuses` (type known; order status needs new scope)
   - Programming status from `programmingPercentComplete` or op-level checks
   - FOCAS machine utilization data for real finish time projections
3. **Generate a daily briefing** answering the 4 original questions:
   - **Machine openings:** FOCAS actuals + ProShop `scheduledEndDate` on current ops → projected free times
   - **Ready-to-run jobs:** Composite of material + tooling + program + FAI flags
   - **Garrett's programming queue:** Ops where `operationType="Programming"` and `isOpComplete=false`, sorted by machine opening date
   - **Rene's purchasing list:** Jobs approaching machine openings where `psETA` is empty and material isn't on hand
4. **Create a new OAuth client** with `contacts:r+purchaseOrders:r` added to unlock material supplier/PO data
5. **Accept the checklist gap** — don't depend on `preProcessingChecklist` being filled; derive readiness from other signals instead
