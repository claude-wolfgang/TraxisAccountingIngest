# ProShop Writes — Full Audit (P27 Accounting Ingest)

Every push from `accounting_ingest.py` into ProShop, drawn from `ingest_queue.db`.

Use this to review / rework / delete each ProShop record.


## Summary
- **15 writes actually landed in ProShop** (`status=UPLOADED` + http proshop_url).
- **3 write attempts failed** — no ProShop record created, but worth knowing.
- **2 rows are mis-statused** — status=UPLOADED but the path is a local Dropbox folder (PAYMENT_VOUCHER routed-as-VENDOR_INVOICE). These did not touch ProShop.

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
