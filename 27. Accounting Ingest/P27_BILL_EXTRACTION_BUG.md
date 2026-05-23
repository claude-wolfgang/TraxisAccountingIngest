# P27 Bill Extraction Bug — Multi-Line Consolidated Bills

**Discovered:** May 13, 2026
**Status:** Open / needs fix
**Severity:** Medium — produces wrong-amount staging entries on consolidated vendor bills
**Source of finding:** Wolfgang, during QBO AP reconciliation session

---

## The Bug

P27's bill extraction logic grabs the **first line item** of a multi-line vendor bill and reports that value as the bill total in QBO's staging area. The actual bill total is much larger and isn't captured. If a user trusts the staging amount and clicks "Create bill," they end up with a phantom bill at the wrong (low) amount, while the real bill is either missing from QBO entirely or has to be reconciled later against a vendor statement.

---

## Test Case (reproducible)

**Vendor:** Hadco Metal Trading Co., LLC
**Bill #:** 2134269
**Bill date:** 04/07/2026
**PDF location:** P27 ingest record from ~4/07/2026 (find by bill no.)

**Staging entry produced:** `$960.00` (Materials & Supplies, first line item only)
**Actual bill total:** `$4,987.41` (9 line items)

Line-item breakdown from the actual PDF:

| # | Description | Amount |
|---|-------------|--------|
| 1 | ST ST HEX 316/316L bar (Pick Ticket 1703784) | $960.00 |
| 2 | 4.5" Plastic Plate Acetal Black (PT 1707289) | $480.00 |
| 3 | 4.5" Plastic Plate Acetal Black (PT 1707289) | $1,440.00 |
| 4 | 4.5" Plastic Plate Acetal Black (PT 1707289) | $720.00 |
| 5 | Total Misc | $12.47 |
| 6 | (blank line item) | $675.00 |
| 7 | Total Misc | $12.47 |
| 8 | (blank line item) | $675.00 |
| 9 | Total Misc | $12.47 |
| | **Total** | **$4,987.41** |

Confirmed via comparison with the actual full bill in QBO (entered separately) and Hadco's vendor statement dated 5/13/2026 showing bill 2134269 paid in full via the 5/7 Bill_Pay.

---

## Impact

Every consolidated vendor bill is at risk. Known affected (or likely-affected) vendors based on observed Hadco statement pattern:

- **Hadco Metal Trading** — bundles multiple pick tickets per bill, high frequency
- **AJ Rod Company** — likely consolidated monthly batches
- **McMaster-Carr** — possibly, depending on bill structure
- Any other vendor that itemizes multiple deliveries on one invoice

Operational consequence: AP balances per vendor are understated until manual reconciliation. The 5/13/2026 Hadco statement reconciliation revealed 4 bills that should have been in QBO but weren't, totaling $7,445.38 — at least some of which may have been lost to this bug.

---

## The Fix

Bill total should be extracted from one of (in order of preference):

1. **The PDF's "Total," "Amount Due," "Balance Due," or "Invoice Total" field** (most reliable — vendors place this in a consistent location on the bill summary, typically bottom-right or in a summary table)
2. **Sum of all detected line items** (fallback if no total field is found)
3. **Cross-validate**: if both available, log a warning when they disagree

**Avoid** using the first line item's amount as the bill total — that's effectively the current bug.

---

## Implementation Sketch

When ingesting a vendor bill PDF:

1. Detect line item rows (existing logic, presumably works)
2. Look for a labeled total field — regex against common labels: `Total`, `Amount Due`, `Balance Due`, `Invoice Total`, `Grand Total`
3. If found, use that as the bill amount; validate it equals sum of line items (within rounding tolerance)
4. If not found, sum all line item amounts
5. Either way: preserve line item detail for the QBO Bill (per-line categories, descriptions, pick ticket refs)
6. Log the extraction method (total-field vs. sum) for auditability

---

## Verification

After fix, re-run extraction against the 2134269 PDF and confirm:

- Staging amount: **$4,987.41** (not $960)
- All 9 line items present in the staging detail

Also test against:

- **Hadco 2138696** PDF — should produce $2,652.47 (verified correct manually 5/13/2026; previous extraction was also correct, suggesting the bug may be intermittent or specific to certain layouts)
- **Hadco 2139793** PDF — should produce $687.47 (also verified)
- **Single-line bill** (e.g., Lumen Utility 1839, $45.10) — should still extract correctly; this bug shouldn't regress simple bills

---

## Related Notes

- QBO staging "Source" column shows "File upload" for P27-ingested bills (vs. "QuickBooks vendor" for QBO native portal-pushed bills) — useful for filtering to find P27-origin entries
- Until fixed, **do not trust** staging amounts on multi-line vendor bills; always compare against PDF total or vendor statement before clicking "Create bill"
- Manual workaround: delete the bad staging entry and create the bill manually with the correct total
- Connection to broader architecture: this bug sits in the AP ingest pipeline that maps to the proposed "Vendor Bills" email folder in the P25/P27 triage system. Fixing it upstream means downstream consumers (QBO, ProShop) get correct data without further reconciliation.

---

## Followup Questions Worth Answering

- Is the bug **layout-specific**? Hadco 2138696 and 2139793 extracted correctly while 2134269 didn't — suggests something about 2134269's PDF structure trips the extractor. Worth comparing layouts.
- Are AJ Rod staging bills (1875661 $165, 1875672 $224.48) **also partial extractions**? Need to verify by opening their PDFs.
- Does the bug exist in **single-line bills** with unusual layouts (e.g., totals appearing in a different position)?
