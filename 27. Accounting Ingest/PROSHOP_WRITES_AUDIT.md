# ProShop Writes — Full Audit (P27 Accounting Ingest)

Every push from `accounting_ingest.py` into ProShop, drawn from `ingest_queue.db`.

Use this to review / rework / delete each ProShop record.


## Summary
- **15 writes actually landed in ProShop** (`status=UPLOADED` + http proshop_url).
- **3 write attempts failed** — no ProShop record created, but worth knowing.
- **2 rows are mis-statused** — status=UPLOADED but the path is a local Dropbox folder (PAYMENT_VOUCHER routed-as-VENDOR_INVOICE). These did not touch ProShop.

---

## Triage Findings (2026-05-18)

Each of the 15 records was queried via basic auth (OAuth client `ACCOUNTING_CLIENT_ID` is dead since `auth_010` was deleted 2026-05-06 — returns 403 on token).

**Current state in ProShop:**
- **4 records still live.** 3 of them have problems that need action; 1 looks legitimate.
- **11 records have already been deleted by Wolfgang.** Reading them by exact `id` / `poId` filter returns 0 rows.

### Action required (4 still in ProShop)

| ID | Type | Current state | Recommendation | Why |
|---|---|---|---|---|
| **260410001** | Bill (LP Machine $10,650, ref 260092) | Header fields correct (`supplierPlainText=LPM1`, `referenceNumber=260092`, `dateIssued=2026-04-07`). Body broken (line items null). **More importantly: Traxis doesn't use ProShop's bills module** — bills go to QBO only. | **DELETE.** The record is in a module that isn't part of the Traxis workflow; reworking it serves no purpose. Going forward, the ingest should not push bills to ProShop at all — `_upload_bill` and the `VENDOR_INVOICE → ProShop` dispatch branch should be removed (the QBO path is the only correct destination for vendor invoices). | Wolfgang 2026-05-18: "we don't use proshops bills module." |
| **263085** | VPO 263085 (aluminum from Water Cut Inc., $5,468) | Date + confirmation# + remarks + 2 poItems (2× 48"×96" plates, 1× 48"×24" plate) all populated. `costPer` values correct ($2,430, $608). **But `supplierPlainText` is null** — no contact code attached. (No `WAT1` contact exists; "Water Cut" never matched the contact picker.) | **REWORK in ProShop UI** — attach the correct supplier contact (likely needs the Water Cut Inc. contact created first), or DELETE and re-enter manually. Line-item data is mostly recoverable; supplier is the gap. | Contact picker accepted "no match" instead of forcing a selection. |
| **263104** | VPO 263104 (`confirmationNumber=PO115126`, supplier=TRA1, "Mod Side Plate Thread" $203.19) | **This is a customer PO from R2Sonic that got mis-classified as a vendor PO and pushed.** PO115126 is R2Sonic's PO number; queue ID [122] failed under `auth_010` first (`acceptNewRecord` permission block), then the same source PDF was reclassified as VENDOR_PO and pushed. `supplierPlainText=TRA1` — Traxis is set as its own supplier, which is wrong. | **DELETE.** Then re-push the same source PDF as a customer PO via the (now-restored) basic-auth path. | The dropdown bug we just fixed today is exactly the symptom: doc reclassification didn't switch the upload route. |
| **263089** | VPO 263089 (`confirmationNumber=394205`, supplier=BAY1, aluminum plate $3,100/ea × 2 = $6,200) | Real Bayou Metal Supply vendor quote/order. Header + 1 real poItem (the other is null). Supplier=BAY1 is correct (Bayou Metal Supply LLC). **Mis-classified at extraction-time as `CUSTOMER_QUOTE`** (because Traxis appears as the customer on a vendor's quote form), but the upload still landed in `/purchaseorders/` so this row is actually OK in shape — just labeled wrong in our queue. | **KEEP** (verify against source PDF). The poItem is real; the empty second slot is just our upload code padding. If Wolfgang confirms the price + quantity match the source, leave it. | Confusion was in our queue's `doc_type` label, not in the ProShop record. |

### Already deleted by Wolfgang (11 records)

These return 0 rows on direct-ID lookup. No action needed — they're gone.

- **R2S1-PO115245** (CPO) — first live CPO push (5/13 session). Deleted.
- **R2S1-PO115244** (CPO) — second live CPO push. Deleted.
- **263110** (VPO) — Helical Solutions, source PDF was actually a packing slip; got pushed as a new VPO routed to `AJR1`. Deleted.
- **263111** (VPO) — Harvey Tool, same pattern (PS → new VPO → AJR1). Deleted.
- **263086** (VPO) — was extracted as `CUSTOMER_QUOTE` `395866` from Traxis Mfg (extraction confusion); landed in `/purchaseorders/`. Deleted.
- **260414.01** (Quote) — `clientPlainText=TRA1`. Extraction set Traxis as its own client. Wolfgang likely deleted; verify it's actually gone (one of the few `/quotes/` writes — easy to overlook).
- **260511-02 / -03 / -04 / -05 / -06** (5 packing slips, 2026-05-11 burst) — Hadco/Gorilla Mill/Helical/Harvey vendor slips. All deleted. `260511-04` and `-06` were the same source PDF (duplicate push of Helical PS `5536692`).

### Failure pattern — root causes

Three independent bugs combined to produce the "universally wrong" pattern:

1. **Customer/vendor confusion at extraction.** When Traxis appears anywhere on a document (as the buyer on a vendor quote, the seller on a customer quote, the supplier on a customer's PO), the prompt frequently picked Traxis as the wrong-side party. Affected: all 3 CUSTOMER_QUOTE rows, VPO 263104, the failed CPO [122]. The `KEY RULE` in the prompt was meant to handle this but doesn't catch it reliably.

2. **Doc-type-change-without-upload-route-change.** Reclassifying a row in the GUI changed the displayed type but kept the original upload routing — so a doc reclassified to CUSTOMER_QUOTE could still land in `/purchaseorders/`. **Fixed today** (dropdown `<<ComboboxSelected>>` binding); confirmed root cause for at least 263086 and 263089.

3. **Field-shape mismatches on the API call.** `addBill` items were sent with field names that ProShop accepted silently but stored as null. Same shape gap on CPO `partsOrdered` until today (zero line items sent before 2026-05-18). Symptom: a record exists with correct header but empty body.

4. **Contact picker accepts "no match."** 7 of the 15 pushed records had `contact_name=None` in the queue. The picker should hard-refuse upload when no contact is selected; today it silently uploads with a null supplier/client/soldTo, and ProShop accepts the orphan record.

### Recommended pause

Until those four fixes land, the ingest's ProShop write privilege is unsafe to use. The dropdown fix today is one of four. The other three (extraction prompt re-anchor, addBill field-shape, contact-picker hard-required) are open work — should go to top of P27 Next Steps as `[NEEDS WOLFGANG]` gates before any more pushes happen.

---

## CUSTOMER_PO — 2 write(s)

### [472] [R2S1-PO115245](https://traxismfg.adionsystems.com/procnc/customerpo/2026/R2S1-PO115245)
- **Pushed:** 2026-05-11
- **Doc:** quote `PO115245`  —  **Traxis Manufacturing LLC**
- **Contact code in ProShop:** `R2S1`
- **Total:** $898.55  |  **Line items sent:** 4  |  **Extraction confidence:** 0.97
- **Source PDF:** `20260509_124709_Purchase_Order_PO115245_1778273527715.pdf`

### [469] [R2S1-PO115244](https://traxismfg.adionsystems.com/procnc/customerpo/2026/R2S1-PO115244)
- **Pushed:** 2026-05-11
- **Doc:** po `PO115244`  —  **R2Sonic LLC**
- **Contact code in ProShop:** `R2S1`
- **Total:** $2833.20  |  **Line items sent:** 2  |  **Extraction confidence:** 0.97
- **Source PDF:** `20260509_124658_Purchase_Order_PO115244_1778272680964.pdf`


## VENDOR_PO — 4 write(s)

### [159] [263085](https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263085)
- **Pushed:** 2026-04-14
- **Doc:** quote `396181`  —  **WATER CUT INC.**
- **Contact code in ProShop:** `_(no contact code)_`
- **Total:** $5468.00  |  **Line items sent:** 2  |  **Extraction confidence:** 0.97
- **Source PDF:** `20260414_143447_Image_20260414_0002.pdf`

### [378] [263104](https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263104)
- **Pushed:** 2026-04-30
- **Doc:** quote `PO115126`  —  **Traxis Manufacturing LLC**
- **Contact code in ProShop:** `TRA1`
- **Total:** $406.38  |  **Line items sent:** 1  |  **Extraction confidence:** 0.92
- **Source PDF:** `U64871E1X118934_04262026_152340_002383_doc4.pdf`

### [621] [263110](https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263110)
- **Pushed:** 2026-05-11
- **Doc:** quote `5393862`  —  **Helical Solutions LLC**
- **Contact code in ProShop:** `AJR1`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.85
- **Source PDF:** `U64871E1X118934_04262026_115237_002362_doc5.pdf`

### [612] [263111](https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263111)
- **Pushed:** 2026-05-11
- **Doc:** quote `5393759`  —  **Harvey Tool Company, LLC**
- **Contact code in ProShop:** `AJR1`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.92
- **Source PDF:** `U64871E1X118934_04262026_115237_002362_doc4.pdf`


## PACKING_SLIP — 5 write(s)

### [556] [260511-02](https://traxismfg.adionsystems.com/procnc/packingslips/2026/260511-02)
- **Pushed:** 2026-05-11
- **Doc:** packing `1709691`  —  **Hadco Metal Trading Co., LLC (OK)**
- **Contact code in ProShop:** `HAD1`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.92
- **Source PDF:** `U64871E1X118934_04262026_152340_002383_doc2.pdf`

### [554] [260511-03](https://traxismfg.adionsystems.com/procnc/packingslips/2026/260511-03)
- **Pushed:** 2026-05-11
- **Doc:** packing `640846`  —  **Carbide Grinding Co., Inc. DBA Gorilla Mill**
- **Contact code in ProShop:** `_(no contact code)_`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.97
- **Source PDF:** `U64871E1X118934_04262026_115237_002362_doc6.pdf`

### [553] [260511-04](https://traxismfg.adionsystems.com/procnc/packingslips/2026/260511-04)
- **Pushed:** 2026-05-11
- **Doc:** packing `5536692`  —  **Helical Solutions LLC**
- **Contact code in ProShop:** `_(no contact code)_`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.98
- **Source PDF:** `U64871E1X118934_04262026_115237_002362_doc5.pdf`

### [552] [260511-05](https://traxismfg.adionsystems.com/procnc/packingslips/2026/260511-05)
- **Pushed:** 2026-05-11
- **Doc:** packing `5536607`  —  **Harvey Tool Company, LLC**
- **Contact code in ProShop:** `_(no contact code)_`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.97
- **Source PDF:** `U64871E1X118934_04262026_115237_002362_doc4.pdf`

### [584] [260511-06](https://traxismfg.adionsystems.com/procnc/packingslips/2026/260511-06)
- **Pushed:** 2026-05-11
- **Doc:** packing `5536692`  —  **Helical Solutions LLC**
- **Contact code in ProShop:** `_(no contact code)_`
- **Total:** $—  |  **Line items sent:** 1  |  **Extraction confidence:** 0.98
- **Source PDF:** `U64871E1X118934_04262026_115237_002362_doc5.pdf`


## CUSTOMER_QUOTE — 3 write(s)

### [136] [260414.01](https://traxismfg.adionsystems.com/procnc/quotes/2026/260414.01)
- **Pushed:** 2026-04-14
- **Doc:** quote `2421582`  —  **TRAXIS MFG**
- **Contact code in ProShop:** `TRA1`
- **Total:** $687.47  |  **Line items sent:** 1  |  **Extraction confidence:** 0.97
- **Source PDF:** `20260414_115015_QT_Q0242158201BB02_.pdf`

### [132] [263086](https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263086)
- **Pushed:** 2026-04-14
- **Doc:** quote `395866`  —  **TRAXIS MFG**
- **Contact code in ProShop:** `_(no contact code)_`
- **Total:** $2650.00  |  **Line items sent:** 1  |  **Extraction confidence:** 0.97
- **Source PDF:** `20260414_114929_QuoteForm395866.PDF`

### [131] [263089](https://traxismfg.adionsystems.com/procnc/purchaseorders/2026/263089)
- **Pushed:** 2026-04-14
- **Doc:** quote `394205`  —  **TRAXIS MFG**
- **Contact code in ProShop:** `BAY1`
- **Total:** $6200.00  |  **Line items sent:** 1  |  **Extraction confidence:** 0.97
- **Source PDF:** `20260414_114918_QuoteForm394205.PDF`


## VENDOR_INVOICE — 1 write(s)

### [2] [260410001](https://traxismfg.adionsystems.com/procnc/bills/2026/260410001)
- **Pushed:** 2026-04-10
- **Doc:** invoice `260092`  —  **LP Machine & Program LLC.**
- **Contact code in ProShop:** `LPM1`
- **Total:** $10650.00  |  **Line items sent:** 3  |  **Extraction confidence:** 0.97
- **Source PDF:** `Invoice- Traxis MFG 10163 263011 #260092.pdf`


## Failed Attempts (no ProShop record created)

### [1] VENDOR_INVOICE — failed 2026-04-10
- **Error:** `Argument totalDollars does not exist on AddBillInput`
- **Doc:** `260092`  —  LP Machine & Program LLC.
- **Source PDF:** `Invoice- Traxis MFG 10163 263011 #260092.pdf`

### [122] CUSTOMER_PO — failed 2026-04-11
- **Error:** `The user auth_010 attempted to edit record CustomerPo:acceptNewRecord that they don't have write permission for.`
- **Doc:** `PO115126`  —  R2Sonic LLC
- **Source PDF:** `20260411_105005_Purchase_Order_PO115126_1775833074637.pdf`

### [126] VENDOR_PO — failed 2026-04-13
- **Error:** `An internal error occurred. Please check application logs for more details.`
- **Doc:** `2419996`  —  Hadco Metal Trading Co., LLC (HOU)
- **Source PDF:** `20260413_083323_2419996.pdf`

## Mis-statused (status=UPLOADED but written to local folder, not ProShop)

### [139] VENDOR_INVOICE
- **Local path written to:** `C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\Filed\PAYMENT_VOUCHER\20260414_120106_Bill_Payment_0000016316_1776185839480.pdf`
- **Source PDF:** `20260414_120106_Bill_Payment_0000016316_1776185839480.pdf`

### [120] VENDOR_INVOICE
- **Local path written to:** `C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\Filed\PAYMENT_VOUCHER\20260411_104950_Bill_Payment_Traxis_04.08.2026_ACH.pdf`
- **Source PDF:** `20260411_104950_Bill_Payment_Traxis_04.08.2026_ACH.pdf`
