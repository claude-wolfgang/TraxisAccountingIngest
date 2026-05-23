"""Re-extract a vendor bill PDF and show what would happen — no DB writes.

Use to verify fixes for the P27 bill extraction bug
(see P27_BILL_EXTRACTION_BUG.md). Takes either a PDF path or a queue_id;
re-runs AIExtractor.extract() with the currently configured caps, then
simulates the reconciliation gate from QBOClient.create_bill so you can see
the would-be QBO Bill before pushing.

Usage:
    python reextract_bill.py --pdf "<path to PDF>"
    python reextract_bill.py --queue-id 405

Output: before/after JSON (if queue_id supplied; before only exists in DB)
and a reconciliation summary block showing stated_total vs line_sum and
whether a balancing line would be inserted.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Import the existing extractor + ENV-loading code rather than duplicating it.
sys.path.insert(0, str(Path(__file__).parent))
import accounting_ingest as ai  # noqa: E402

DB_PATH = ai.DB_PATH


def _to_float(v):
    if v is None:
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return 0.0


def simulate_reconciliation(extracted):
    """Mirror the QBOClient.create_bill reconciliation logic without
    writing anything. Returns dict describing what would happen.
    """
    lines = []
    for item in extracted.get("line_items", []) or []:
        amt = _to_float(item.get("extended_price") or item.get("unit_price"))
        if amt > 0:
            lines.append({"amount": round(amt, 2),
                          "description": item.get("description", "")})

    fallback_used = False
    if not lines:
        total = _to_float(extracted.get("total_amount") or extracted.get("subtotal"))
        lines.append({"amount": round(total, 2),
                      "description": f"Invoice {extracted.get('invoice_number','')}"})
        fallback_used = True

    line_sum = round(sum(ln["amount"] for ln in lines), 2)
    stated_total = _to_float(extracted.get("total_amount"))
    delta = round(stated_total - line_sum, 2)

    action = "ok"
    reconcile_amount = 0.0
    if stated_total > 0 and delta > 0.50:
        action = "RECONCILED"
        reconcile_amount = delta
    elif stated_total > 0 and delta < -0.50:
        action = "OVER_TOTAL"  # logged, but not auto-fixed

    return {
        "lines": lines,
        "line_sum": line_sum,
        "stated_total": stated_total,
        "delta": delta,
        "fallback_used": fallback_used,
        "action": action,
        "reconcile_amount": reconcile_amount,
        "final_total": round(line_sum + reconcile_amount, 2) if action == "RECONCILED" else line_sum,
    }


def load_queue_row(queue_id):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT id, doc_type, status, pdf_path, extracted_json, edited_json "
        "FROM queue WHERE id = ?",
        (queue_id,),
    ).fetchone()
    con.close()
    return row


def print_recon(label, recon):
    print(f"\n--- {label} ---")
    print(f"  lines extracted   : {len(recon['lines'])}")
    print(f"  line_sum          : ${recon['line_sum']:.2f}")
    print(f"  stated_total      : ${recon['stated_total']:.2f}")
    print(f"  delta             : ${recon['delta']:.2f}")
    print(f"  fallback_used     : {recon['fallback_used']}")
    print(f"  action            : {recon['action']}")
    if recon["action"] == "RECONCILED":
        print(f"  reconcile_amount  : ${recon['reconcile_amount']:.2f}  (added as balancing line)")
    print(f"  final QBO total   : ${recon['final_total']:.2f}")
    if recon["lines"]:
        print(f"  line breakdown:")
        for ln in recon["lines"]:
            d = (ln["description"] or "")[:55]
            print(f"    ${ln['amount']:>10.2f}  {d}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", help="Path to PDF to re-extract")
    g.add_argument("--queue-id", type=int, help="Queue row id to re-extract")
    ap.add_argument("--show-raw", action="store_true",
                    help="Print full new extracted JSON")
    args = ap.parse_args()

    pdf_path = None
    before_extracted = None

    if args.queue_id is not None:
        row = load_queue_row(args.queue_id)
        if not row:
            print(f"Queue id {args.queue_id} not found")
            sys.exit(1)
        if row["doc_type"] != "VENDOR_INVOICE":
            print(f"Queue id {args.queue_id} is {row['doc_type']!r}, not VENDOR_INVOICE")
            sys.exit(1)
        pdf_path = row["pdf_path"]
        if not pdf_path or not Path(pdf_path).exists():
            print(f"Queue id {args.queue_id} has no PDF on disk (pdf_path={pdf_path!r})")
            sys.exit(1)
        edited = row["edited_json"] or row["extracted_json"]
        if edited:
            try:
                before_extracted = json.loads(edited)
            except json.JSONDecodeError:
                before_extracted = None
        print(f"Queue id {args.queue_id}: status={row['status']}, pdf={pdf_path}")
    else:
        pdf_path = args.pdf
        if not Path(pdf_path).exists():
            print(f"PDF not found: {pdf_path}")
            sys.exit(1)

    if before_extracted is not None:
        before_recon = simulate_reconciliation(before_extracted)
        print_recon("BEFORE (stored extraction)", before_recon)

    print("\nRe-extracting (max_pages=12, max_tokens=8000)...")
    extractor = ai.AIExtractor()
    after_extracted = extractor.extract(pdf_path, "VENDOR_INVOICE")
    if "error" in after_extracted:
        print(f"Extraction error: {after_extracted}")
        sys.exit(2)

    after_recon = simulate_reconciliation(after_extracted)
    print_recon("AFTER  (re-extracted)", after_recon)

    # Self-check claims from Claude
    print(f"\nClaude self-check fields:")
    for k in ("line_items_sum_computed", "total_match", "pages_seen", "confidence"):
        v = after_extracted.get(k)
        if v is not None:
            print(f"  {k}: {v}")

    if args.show_raw:
        print("\n--- full extracted JSON ---")
        print(json.dumps(after_extracted, indent=2))

    if before_extracted is not None:
        before_n = len(before_extracted.get("line_items", []) or [])
        after_n = len(after_extracted.get("line_items", []) or [])
        print(f"\nLine-item count: {before_n} -> {after_n}")
        if before_recon["final_total"] != after_recon["final_total"]:
            print(f"QBO total would change: ${before_recon['final_total']:.2f}"
                  f" -> ${after_recon['final_total']:.2f}")


if __name__ == "__main__":
    main()
