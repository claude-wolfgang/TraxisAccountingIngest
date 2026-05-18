---
description: Run the ProShop ↔ QBO bookkeeping reconciliation (30-day window)
---

Run the two P27 reconciliation scripts and report findings as a punch list.

Execute in parallel (independent):

```bash
cd "27. Accounting Ingest" && python read_proshop_unbilled_shipments.py 2>&1 | tail -50
```

```bash
cd "27. Accounting Ingest" && python read_proshop_invoices.py 2>&1 | tail -50
```

Report in this shape:

**Stage 1 — Shipped but not invoiced in ProShop**
Markdown table with columns: Customer, Slip, Shipped, Cust PO, ProShop link. One row per unbilled slip. If zero, say "Nothing pending."

**Stage 2 — Invoiced in ProShop but not in QBO**
Markdown table with columns: Invoice #, $ Total, ProShop link. One row per ProShop-only invoice. If zero, say "All invoices reached QBO."

**Stage 2 — Amount mismatches**
Markdown table with columns: Invoice #, ProShop $, QBO $, Diff. Flag Setcom (SET1) rows as "known SET1 pattern" per the [[project-proshop-qbo-zero-dollar-set1]] memory — Wolfgang fixes those manually one side or the other.

**Other anomalies** (only if present):
- QBO-only invoices (would be unusual — invoices in QBO with no ProShop counterpart)
- Blank invoice numbers on either side
- ProShop slips dated today (likely just queued for next Web Connector cycle — not a real problem yet)

For any Stage 2 sync gap on a customer where you don't already know the QBO DisplayName from [[project-customer-code-mapping]], offer to look it up via the QBO Customer API (one query, ~1 second).

For Stage 1 slips, the dollar value is intentionally absent — `pricePer` is null on un-invoiced slips per the schema. Don't try to add it back; see [[project-proshop-invoice-schema-gotchas]].

End-of-output: a one-line "OK to close" if everything is matched, or "N items need attention" with the count.
