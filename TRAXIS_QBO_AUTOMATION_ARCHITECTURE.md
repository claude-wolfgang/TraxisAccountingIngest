# Traxis Manufacturing — QBO Automation Architecture
**Complete system for bill ingest → categorization → reconciliation → compliance**

**Version:** 1.2 — 2026-04-29
**Changelog:**
- v1.0 — Initial architecture proposal (Web Claude)
- v1.1 — Added ecosystem context section: what's already built in P27, actual tech stack corrections, integration points, prioritized build list, suggestions (Claude Code)
- v1.2 — QBO production activated. Added Scheduler + Procurement Loop concept. P27 v1.4.0: email body extraction, deduplication fixes, gated label printing, cert filing by VPO (Claude Code)

---

## SYSTEM OVERVIEW

**Goal:** Eliminate manual data entry. Automate vendor bill ingestion, categorization, posting to QBO, reconciliation, and compliance documentation.

**Coverage:**
- Vendor invoices (email → QBO)
- Bank transactions (auto-matched)
- Bill categorization (via Claude rules)
- Monthly reconciliation (automated + flagged exceptions)
- Audit trail generation (ISO 9001/AS9100 compliant)

---

## ARCHITECTURE LAYERS

### LAYER 1: DATA INGEST (Email → Structured Data)

**Tool:** Microsoft Graph API + Azure Function + Claude API

**Flow:**
```
1. Vendors email invoices to: bills@traxismfg.com
2. Azure Function triggered on new emails
3. Microsoft Graph API fetches:
   - Sender (vendor name)
   - Subject
   - PDF attachment
4. Claude extracts via vision API:
   - Vendor name (canonical match to QBO vendor list)
   - Invoice number
   - Invoice date
   - Amount
   - Due date
   - Line items (description + amount)
   - Account category (based on item description + vendor type)
5. Output: JSON structured data
6. Store in: Azure Blob Storage + database
```

**Error Handling:**
- Ambiguous vendor → flag for manual review
- Amount > $5,000 → flag for approval (business rule)
- Missing due date → extract from payment terms table
- PDF unreadable → alert Rene/Garrett to resend

---

### LAYER 2: QBO API POSTING (Structured Data → Bill Records)

**Tool:** Intuit QBO API (once approved) + Node.js microservice

**Flow:**
```
1. Incoming JSON from Layer 1
2. Validation:
   - Vendor exists in QBO? If not → create
   - Account code exists? If not → flag
   - Amount format correct? Currency validation
   - Due date in future? (catch stale invoices)
3. QBO API Call:
   - Create Bill (Expenses > Accounts Payable)
   - Fields: VendorRef, DueDate, TxnDate, LineItems[{Description, Amount, AccountRef}]
   - Attachments: Upload original PDF via QBO Document API
4. Store QBO Document ID for audit trail
5. Record in database: bill_id, qbo_doc_id, timestamp, status
```

**Business Rules (Configurable):**
```
If vendor = "Hadco Metal Trading":
  → Account: "Materials - Raw Stock"
  
If vendor = "McMaster Carr":
  → Account: "Supplies & Tools"
  
If vendor = "LP Machine":
  → Account: "Subcontracting - Machining"
  
If amount > $5,000:
  → Set status: "Pending Approval"
  → Email Garrett for review
  → Don't post until approved
```

**Approval Workflow:**
```
Garrett receives email with bill details
Clicks "Approve" or "Reject" in email or web dashboard
If approved → API posts to QBO
If rejected → Bill marked "Rejected", reason logged
```

---

### LAYER 3: BANK RECONCILIATION AUTOMATION

**Tool:** QBO Bank Feeds + Claude API for exception flagging

**Flow:**
```
**Daily (Automated):**
1. QBO downloads transactions from Chase (automatic)
2. QBO auto-matches obvious transactions:
   - Checks (already in QBO, matched by check number)
   - Deposits matching invoices
   - ACH transfers with memo match
3. Remaining "unmatched" transactions:
   - Move to "For Review" category
   - Run through Claude categorization:
     - Is this a vendor payment? → match to bill
     - Is this a bank fee? → code as "Bank Charges"
     - Is this a transfer? → code as "Transfers"
     - Is this a business expense not in bill form? → code automatically

**Monthly (Automated with Human Review):**
1. Get Chase bank statement ending balance
2. Run three-way reconciliation:
   a) Bank statement balance
   b) QBO account balance
   c) Check/deposit status
3. Reconcile in QBO:
   - Mark all matched items as "Reconciled"
   - Flag exceptions:
     - Amount discrepancy > $50
     - Timing issue > 7 days
     - Missing documentation
4. Claude flags high-priority issues:
   - Duplicate transactions detected
   - Unusual amount (3x average for vendor)
   - Round-dollar amount (possible manual entry error)
5. Email summary: "Reconciliation complete. 2 exceptions flagged for review."
```

**Exception Report:**
```
Reconciliation Date: 2026-04-30
Status: Complete with exceptions
Matched Transactions: 47
Unmatched: 3
Discrepancies: 1

EXCEPTION #1: Duplicate check?
  Check #2341 posted twice (04/15, 04/16)
  Amount: $1,200.00
  Vendor: Hadco Metal Trading
  Action: Investigate clearing status, possible pendulum transaction

EXCEPTION #2: Round dollar amount
  Deposit: $5,000.00
  Date: 04/18
  Memo: "Payment from customer"
  Description: No invoice number
  Action: Follow up with Garrett on customer identity
```

---

### LAYER 4: CATEGORIZATION & EXPENSE RULES

**Tool:** Claude API with business rule engine

**Flow:**
```
For every transaction (bill or bank):
1. Claude reads:
   - Vendor/payee name
   - Amount
   - Memo/description
   - Invoice number (if available)
   - ProShop work order (if linked)
2. Categorizes using rules:
   - Direct materials → "Materials & Supplies"
   - Subcontracting → "Subcontracting - [Service Type]"
   - Utilities → "Utilities"
   - Tool/equipment < $500 → "Supplies & Tools"
   - Tool/equipment > $500 → "Equipment & Machinery"
3. Flags for human review:
   - Novel vendor → confirm category
   - Amount anomaly → confirm category
   - Mixed line items → may need split posting
4. Stores categorization with confidence score:
   - > 95% confidence: Post automatically
   - 70-95% confidence: Post + flag for review
   - < 70% confidence: Hold for manual review
```

---

### LAYER 5: PROSHOW INTEGRATION (Optional Post-Phase)

**Tool:** ProShop GraphQL API

**Flow:**
```
When bill posted to QBO:
1. Check if invoice mentions ProShop work order
2. If work order found:
   - Update WO status: "Materials Ordered" or "Subcontracted"
   - Link QBO bill_id to ProShop for traceability
   - Update Material/Subcontracting actual costs
3. If bill is for job materials:
   - Extract line item costs
   - Post to ProShop job costing
   - Compare to estimated vs actual
4. Generate report: "WO Status + Cost Variance"
```

---

### LAYER 6: MONTHLY COMPLIANCE & REPORTING

**Tool:** Claude + QBO API + Markdown/PDF generation

**Flow:**
```
**End of Month Automated Report:**
1. Pull data from QBO:
   - P&L (income vs expenses by category)
   - AP aging (what's unpaid, what's due soon)
   - AR aging (if you track it)
   - Bank balances
   - Reconciliation status
2. Claude generates:
   - Compliance checklist:
     ✓ Bank reconciliation completed
     ✓ All bills categorized
     ✓ Exceptions resolved
     ✓ Audit trail complete
   - Exception summary (see Layer 3)
   - Cash position summary
   - Due payment list (next 30 days)
3. Output: HTML report + PDF download
4. Email to: Wolfgang, accountant, Garrett
5. Store in: Traxis shared drive (audit trail)
```

**ISO 9001/AS9100 Compliance Document:**
```
---
TRAXIS MANUFACTURING LLC
MONTHLY ACCOUNTING RECONCILIATION REPORT
Month: April 2026

Compliance Status: COMPLIANT ✓

Bank Reconciliation:
  Completed: 04/29/2026
  Status: Complete (0 exceptions)
  By: [Automated System]
  Reviewed by: [Manual human review if needed]

Bill Processing:
  Bills received: 12
  Bills posted to QBO: 12
  Average posting time: 2 hours
  Exceptions: 1 (resolved)

Categorization Accuracy:
  Auto-categorized (>95% confidence): 11 of 12
  Manual review required: 1 of 12
  All resolved: YES

Audit Trail:
  All transactions logged with timestamp, source, categorization
  PDF attachments stored: 12 of 12
  QBO document IDs recorded: 12 of 12

Next Review Date: 05/29/2026
---
```

---

## TECHNOLOGY STACK

| Function | Tool | Cost | Status |
|----------|------|------|--------|
| Email monitoring | Microsoft Graph API | $0 (M365) | Ready |
| PDF extraction | Claude Vision API | $0.003/page | Ready |
| Data transformation | Azure Functions | ~$10/mo | Ready |
| Data storage | Azure SQL Database | ~$15/mo | Ready |
| QBO integration | Intuit QBO API | Free (approved needed) | **WAITING** |
| Automation engine | Node.js + Claude | $50-100/mo | Ready |
| Reporting | Claude + Markdown | Included | Ready |
| Audit logging | Custom database | Included | Ready |

**Total Monthly Cost:** ~$75-150 (vs manual entry: ~$500+/mo in labor)

---

## MONTHLY WORKFLOW

### **First of Month (Automated)**
```
00:00 - System checks for any unmatched June transactions
06:00 - Bank reconciliation runs automatically
07:00 - Exception report generated
08:00 - Email sent to Wolfgang + Garrett: "Reconciliation complete, 0 exceptions"
```

### **Mid-Month (Ongoing)**
```
Vendors email bills throughout month
Each bill:
  - Ingested within 1 hour
  - Extracted by Claude
  - Posted to QBO (if no exceptions)
  - PDF attached in QBO
  - Logged in audit trail
```

### **End of Month (Manual Review)**
```
Wolfgang receives report (automated)
Review checklist:
  [ ] Bank reconciliation complete
  [ ] All bills posted
  [ ] Exception report reviewed
  [ ] Due payments identified
Garrett reviews high-value bills (> $5,000) if flagged
Accountant gets report for tax prep
File report in compliance folder
```

---

## EXCEPTION HANDLING & ESCALATION

**Level 1: Automatic Handling**
- Duplicate transaction detected → flag, don't post twice
- Vendor not in QBO → create automatically
- Missing due date → extract from standard payment terms

**Level 2: Garrett Review (within 24 hours)**
- Amount > $5,000
- Novel vendor
- Categorization confidence < 70%
- Unusual payment terms

**Level 3: Wolfgang Review (within 2 days)**
- Amount > $10,000
- Potential duplicate invoice
- Discrepancy between PO and invoice

**Level 4: Escalation (if no action)**
- Auto-alert after 3 days
- Hold bill from posting until resolved
- Log as open issue in compliance report

---

## AUDIT TRAIL (ISO 9001/AS9100 Compliance)

Every transaction stores:
```json
{
  "bill_id": "BIL-2026-0001",
  "qbo_doc_id": "123456789",
  "vendor": "Hadco Metal Trading",
  "amount": 1500.00,
  "due_date": "2026-05-15",
  "created_timestamp": "2026-04-15T14:32:00Z",
  "created_by": "automated",
  "categorized_by": "claude-api",
  "categorization_confidence": 0.98,
  "category": "Materials & Supplies",
  "posted_to_qbo_timestamp": "2026-04-15T14:33:15Z",
  "posted_by": "qbo-api",
  "status": "posted",
  "pdf_attachment_qbo_id": "ATT-987654321",
  "exceptions": [],
  "reviewed_by": null,
  "approval_timestamp": null,
  "notes": ""
}
```

Stored in database + QBO, queryable for audits.

---

## SUCCESS METRICS

**Efficiency:**
- Bills ingested: < 2 hours from email
- Monthly reconciliation: 100% automated + flagged exceptions only
- Manual touchpoints: < 5% of transactions
- Time saved: ~20 hours/month

**Accuracy:**
- Categorization accuracy: > 95%
- Reconciliation exceptions: < 1% of transactions
- Duplicate detection: 100%
- Audit trail completeness: 100%

**Compliance:**
- ISO 9001/AS9100 documentation complete
- Monthly report generation: automated
- Retention period compliance: auto-enforced
- Exception resolution time: < 2 days

---

## IMPLEMENTATION ROADMAP

### **Phase 1: Foundation (2-3 weeks)**
- [ ] Set up bills@traxismfg.com mailbox
- [ ] Deploy Microsoft Graph API monitoring
- [ ] Build Claude extraction pipeline
- [ ] Test on 10 sample invoices from vendors
- [ ] Validate extracted data against QBO vendor list

### **Phase 2: QBO Integration (1-2 weeks after Intuit approval)**
- [ ] Receive Intuit API app approval
- [ ] Build QBO API posting logic
- [ ] Set up business rule engine
- [ ] Deploy with approval workflow (for >$5,000 bills)
- [ ] Test end-to-end: email → extraction → QBO posting

### **Phase 3: Reconciliation Automation (1-2 weeks)**
- [ ] Configure bank feed auto-matching rules
- [ ] Build exception detection (Claude + heuristics)
- [ ] Implement monthly reconciliation script
- [ ] Test with April-June 2026 data
- [ ] Generate compliance reports

### **Phase 4: ProShop Integration (Optional, 2-3 weeks)**
- [ ] Map ProShop work orders to QBO categories
- [ ] Build bidirectional sync
- [ ] Test cost variance reporting
- [ ] Document integration in procedures

### **Phase 5: Compliance & Handoff (1 week)**
- [ ] Create operations manual (procedures)
- [ ] Train Garrett on exception handling
- [ ] Document audit trail process
- [ ] Set up monthly review cadence
- [ ] Go live

---

## NEXT STEPS

1. **Confirm Intuit API Status** — Check developer.intuit.com for app approval
2. **Set Up Email Ingest** — Create bills@traxismfg.com, test mailbox
3. **Build Phase 1** — Deploy Claude extraction pipeline
4. **Test with Hadco** — Ingest 5 Hadco invoices, validate extraction
5. **Once API approved** — Move to Phase 2 (QBO posting)

---

## QUESTIONS / DECISION POINTS

- **Approval threshold:** Is >$5,000 the right approval limit, or different?
- **Vendor list:** Should we auto-create new vendors or require pre-approval?
- **ProShop linkage:** Do bills reference work orders in memo? (needed for Phase 4)
- **Categorization:** Are there industry-specific categories beyond what's listed?
- **Retention:** Are 7 years okay for record retention, or do customers require longer?

---

## ECOSYSTEM CONTEXT — WHAT ALREADY EXISTS (Added 2026-04-27)

> **This section was added by Claude Code after reviewing this document against the live Traxis codebase. The architecture above was written as a greenfield proposal, but significant infrastructure already exists. Any implementation plan should build on what's running, not replace it.**

### Already Built (Project 27: Accounting Ingest)

**Layer 1 — Email + Scan Ingest: OPERATIONAL**
- Microsoft Graph API polls `accounting@traxismfg.com` (OAuth 2.0, 30-day lookback)
- `scan_relay.py` watches the scanner output folder, moves stable PDFs to `Scanned/`
- PyMuPDF burst splits multi-page PDFs into single pages in `Scanned/burst/`
- Claude Vision (Sonnet) classifies each page: VENDOR_INVOICE, PACKING_SLIP, CUSTOMER_PO, VENDOR_PO, CUSTOMER_QUOTE, PAYMENT_VOUCHER
- Extracts vendor, amount, date, line items, PO#, confidence score
- Tkinter GUI with manual review queue (edit extracted JSON before posting)
- SQLite database (`ingest_queue.db`) tracks all documents with status lifecycle

**Layer 2 — QBO Posting: SANDBOX COMPLETE, BLOCKED ON INTUIT APPROVAL**
- Bill creation via QBO REST API works in sandbox
- Vendor auto-create if not found in QBO
- PDF attachment upload via QBO Document API
- Environment toggle: `QBO_ENVIRONMENT` in `.traxis.env` (currently `"sandbox"`)
- QBO credentials (client ID, realm, refresh token) already provisioned

**Layer 5 — ProShop Integration: LIVE (not optional)**
- `updatePurchaseOrder` mutation marks VPO items received (receivedQty, releasedQty, dates)
- Packing slip detection triggers auto-print of tool receiving labels (Brother PT-P700 via P22 print service)
- Contact fuzzy matching for vendor→ProShop contact linkage
- Uses dedicated OAuth client (AccountingConnector, scope: invoices/bills/estimates/quotes/customerpos/packingslips/purchaseorders/contacts/parts)

### Actual Technology Stack (vs. proposed)

| Function | Proposed in Doc | Actual in P27 | Notes |
|----------|----------------|---------------|-------|
| Email monitoring | Microsoft Graph API | Microsoft Graph API | ✓ Same |
| PDF extraction | Claude Vision API | Claude Vision (Sonnet) | ✓ Same |
| Orchestration | Azure Functions | Local Python + Tkinter GUI | GUI provides manual review queue — important for confidence < 95% docs |
| Data storage | Azure SQL Database | SQLite (`ingest_queue.db`) | Synced via Dropbox. Adequate for current volume (~50-100 docs/month) |
| QBO integration | Intuit QBO API + Node.js | Intuit QBO REST API + Python | Python, not Node.js — consistent with rest of ecosystem |
| Automation engine | Node.js + Claude | Python + Claude API | All Traxis automation is Python-based |
| Reporting | Claude + Markdown | Not yet built | This is a real gap — Layer 6 is the main unbuilt piece |

**Key takeaway: Don't propose Azure/Node.js. The entire Traxis ecosystem is Python + SQLite + Dropbox + local services. Moving to Azure would create operational complexity with no proportional benefit at current scale (~12 vendors, ~50 bills/month).**

### Ecosystem Integration Points the Doc Should Reference

1. **Print Service (P22):** All label printing goes through `http://10.1.1.242:5002/api/print-image` — Brother PT-P700, 128px height, 180 DPI, base64 PNG payload. Tool receiving labels from P27 already use this.

2. **ProShop API Auth Model:** Three-layer permission gate — OAuth scope + User #010 moduleAccess + unsolved `acceptNewRecord` requirement. P27 already navigates this with the AccountingConnector OAuth client. Customer PO mutations are blocked by `auth_010` permissions (read-only via API).

3. **Agent Exploration (P25):** The Telegram bot + audit engine can surface QBO posting failures or stale bills. Consider wiring P27 exceptions into P25's alert channel rather than building a separate notification system.

4. **Breakeven Dashboard (P32):** Reads FOCAS data for machine runtime. If Layer 5 links bills to work orders, P32 could show cost-per-hour alongside runtime — a natural extension.

5. **Shared credentials:** All API keys live in `.traxis.env` (ProShop OAuth ×6, Microsoft Graph, QBO, Anthropic, Telegram). P27 already loads from this file.

### What's Actually Left to Build

| Priority | Item | Effort | Blocked By |
|----------|------|--------|------------|
| **P0** | QBO production switch | 1 hour (flip env var + test) | Intuit approval |
| **P1** | Vendor→account categorization rule engine | 1-2 days | Nothing — can start now |
| **P1** | Approval workflow for bills > $5,000 | 2-3 days | Nothing — Garrett email or Telegram alert |
| **P2** | Bank reconciliation automation (Layer 3) | 1-2 weeks | QBO production access + Chase bank feed setup |
| **P2** | Monthly compliance report (Layer 6) | 3-5 days | QBO production access (needs real data) |
| **P3** | Bill→work order linkage | 1 week | Needs business rule: how do bills reference WOs? (memo? PO line item?) |
| **P3** | Cost variance reporting (estimated vs actual) | 1 week | Depends on bill→WO linkage |

### Suggestions for Web Claude

1. **Don't redesign the pipeline.** Layers 1, 2, and 5 are built. Focus implementation effort on Layers 3 (bank reconciliation), 4 (categorization rule engine), and 6 (compliance reporting).

2. **The approval workflow could be Telegram-based** instead of email. P25's Telegram bot is already running and Claude-powered — adding an "Approve/Reject bill" command is ~1 day of work vs. building a separate email approval system.

3. **The categorization rule engine (Layer 4) should be a JSON config file, not code.** P27 already uses Claude for classification — the rule engine just needs a `vendor_rules.json` mapping vendor names to QBO account codes, with Claude as fallback for unknown vendors.

4. **Layer 3 (bank reconciliation) is the highest-value unbuilt piece.** But it requires QBO production access and Chase bank feed configuration. Don't plan this until Intuit approves.

5. **The ISO 9001/AS9100 compliance report (Layer 6) can be a Claude-generated markdown report** pulled from the existing SQLite audit trail. No new infrastructure needed — just a scheduled script that queries `ingest_queue.db` and generates the report monthly.

---

## SCHEDULER + PROCUREMENT LOOP (Added 2026-04-29)

> **This section captures a concept discussed between Wolfgang and Claude Code. It connects the shop scheduler (P19), tool inventory (P22), tool library (P33), and accounting ingest (P27) into a closed-loop system that predicts procurement needs and automates the order cycle.**

### The Problem

Traxis has ~50 open work orders at any time, each with multiple operations requiring specific tooling. It is beyond human capacity to track which tools are needed, when each job will reach the op that needs them, whether the tools are in stock, and whether they've been ordered. Dropped orders and late material/tool procurement are the highest-impact failures — they directly affect customers.

### Core Insight: Manage 9 Machines, Not 50 Jobs

The scheduler should not present 50 jobs to manage. It should present **9 machines** to feed. Each machine needs one thing: its next ready piece. The 50 jobs exist behind that view — the engine manages them, the human manages the machines.

### Two Views of the Same Data

**View 1: The Floor (Minute-to-Minute)**
- 9 machine slots, one per CNC
- Each shows: what's running now, what's next, queue depth
- A machine with an empty ready queue is the problem — that's where you focus
- Cards are uniform size, color-coded by urgency pressure (remaining work ÷ remaining time)
- Cool blue = fine. Amber = tightening. Red = critical. Dark = already late
- Blocker dots on each card: program, material, tools, first article
- No timeline axis, no duration encoding — pressure is the only visual dimension

**View 2: The Horizon (Weekly Planning)**
- All open jobs sorted by due date
- Engine projects forward: walks each WO's remaining ops in sequence
- Estimates when each op will start based on current machine load and ops ahead
- Checks tool availability for future ops against P22 inventory (tooling.db)
- Checks whether a VPO is already open for anything missing
- Compares tool lead times against projected op start dates
- Surfaces: **"Order these 3 things this week or these jobs slip"**
- Output is a punch list, not a dashboard — actions, not information

### The Closed Loop

```
1. HORIZON ENGINE projects: "WO 12345 hits Op 30 in ~2 weeks,
   needs endmill X, not in stock, lead time 5 days → order by Friday"

2. P33 TOOL LIBRARY looks up the tool: vendor, EDP, pricing, approved brand

3. P27 INGEST creates the VPO in ProShop via API (addPurchaseOrder mutation),
   pre-filled with vendor, toolNumber, EDP, shipTo, pricing

4. EMAIL goes out to vendor (Microsoft Graph API can send, not just read)

5. VENDOR CONFIRMS — reply email ingested by P27, classified, matched to VPO

6. TOOL SHIPS — packing slip arrives (email or scan), P27 classifies it,
   user clicks Print Labels for receiving

7. TOOL RECEIVED — updatePurchaseOrder mutation sets receivedQty/releasedQty,
   cert PDF auto-filed to Certs/VPO-XXXXXX/ folder,
   P22 inventory updated

8. HORIZON ENGINE sees tool now in stock, clears the blocker

9. FLOOR VIEW picks up the job as "next" for that machine
```

### What Exists vs. What's Needed

| Component | Status | Project |
|-----------|--------|---------|
| Urgency scoring + blocker diagnosis | Built | P19 priority_engine.py |
| Tool readiness check vs P22 inventory | Built | P19 reads tooling.db |
| ProShop WO/ops/tools sync | Built | P19 sync.py |
| Tool catalog with vendor/EDP/pricing | Built | P33 Tool Library |
| VPO creation via API | Built | P27 addPurchaseOrder |
| Packing slip classification + receiving | Built | P27 + tool_receiving_labels.py |
| Cert PDF filing by VPO | Built (v1.4.0) | P27 _save_cert_for_vpo |
| Email send (order to vendor) | Not built | Microsoft Graph API (available) |
| **Horizon projection engine** | **Not built** | Would extend P19 |
| **Automated tool procurement trigger** | **Not built** | Would connect P19 → P33 → P27 |
| **Floor view UI (9 machines)** | **Not built** | Replaces current P19 web UI |
| **Horizon view UI (punch list)** | **Not built** | New view in P19 |

### UI Concept Notes

- Current P19 web UI has layout precision problems (cards shift/resize based on position). Needs rebuild.
- Candidate tech: PixiJS (WebGL 2D renderer, pixel-perfect positioning, 60fps animations) or Electron for native feel
- Cards must be uniform size — urgency encoded as color/temperature, not card dimensions
- No timeline/Gantt approach — large jobs (200+ hours) break the scale and hide urgent small jobs
- The board should feel like a tool, not a dashboard. CAM-software-level precision is the bar.
- Two audiences: Wolfgang (planning, procurement decisions) and floor operators (what to run next)

### Implementation Sequence

1. **Horizon projection engine** — extend P19 to walk future ops and flag tool gaps. This is the highest-value piece and requires no UI.
2. **Morning Telegram alert** — wire the horizon output into P25's bot. "3 tools need ordering this week" with the list. Zero UI needed.
3. **Floor view rebuild** — 9-machine board with pressure-coded cards. Replace current P19 web UI.
4. **Automated VPO creation** — horizon engine triggers P33 lookup → P27 VPO creation with one-click approval.
5. **Vendor email send** — close the loop with outbound email via Graph API.

### Questions / Decisions

- **Lead time data:** Where do tool lead times live? P33 tool library? Vendor-specific? Need a default (5 days?) and overrides.
- **Approval gate:** Should automated VPO creation require approval (Telegram confirm) or just do it for items under a threshold?
- **Machine assignment:** Does the engine assign jobs to machines, or just rank-order what's ready and let the floor decide?
- **First article status:** How is first article tracked in ProShop? Is it queryable via API or manual?

