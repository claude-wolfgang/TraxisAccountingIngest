"""Run reextract_bill against a list of queue_ids in parallel and produce
a single-row-per-bill summary table.

Usage:
    python reextract_batch.py 405 323 218 294 644 413 633 467 424 401 253
"""

import argparse
import concurrent.futures as cf
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import accounting_ingest as ai  # noqa
from reextract_bill import simulate_reconciliation, load_queue_row, _to_float  # noqa


def reextract_one(queue_id):
    """Return summary dict for a single queue id."""
    row = load_queue_row(queue_id)
    if not row:
        return {"id": queue_id, "error": "row not found"}
    if row["doc_type"] != "VENDOR_INVOICE":
        return {"id": queue_id, "error": f"doc_type={row['doc_type']}"}
    if not row["pdf_path"] or not Path(row["pdf_path"]).exists():
        return {"id": queue_id, "error": "no pdf on disk"}

    before_json = row["edited_json"] or row["extracted_json"]
    try:
        before = json.loads(before_json) if before_json else {}
    except json.JSONDecodeError:
        before = {}

    before_recon = simulate_reconciliation(before)

    try:
        extractor = ai.AIExtractor()
        after = extractor.extract(row["pdf_path"], "VENDOR_INVOICE")
    except Exception as e:
        return {"id": queue_id, "error": f"extract failed: {e}"}
    if "error" in after:
        return {"id": queue_id, "error": after.get("error", "extract returned error")}

    after_recon = simulate_reconciliation(after)

    vendor = (before.get("vendor_name") or after.get("vendor_name") or "?")[:24]
    inv_no = before.get("invoice_number") or after.get("invoice_number") or "?"

    return {
        "id": queue_id,
        "vendor": vendor,
        "invoice": inv_no,
        "before_lines": len(before.get("line_items", []) or []),
        "before_line_sum": before_recon["line_sum"],
        "before_stated": before_recon["stated_total"],
        "before_final": before_recon["final_total"],
        "before_action": before_recon["action"],
        "after_lines": len(after.get("line_items", []) or []),
        "after_line_sum": after_recon["line_sum"],
        "after_stated": after_recon["stated_total"],
        "after_final": after_recon["final_total"],
        "after_action": after_recon["action"],
        "after_delta": after_recon["delta"],
        "claude_match": after.get("total_match"),
        "claude_pages": after.get("pages_seen"),
        "claude_lines_sum": after.get("line_items_sum_computed"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+", type=int)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(reextract_one, args.ids):
            results.append(r)
            print(f"  done #{r.get('id')}: {r.get('vendor', r.get('error'))}", flush=True)

    print()
    print(
        f"{'id':<5} {'vendor':<24} {'inv':<14} "
        f"{'bL':<3} {'b_sum':>9} {'b_stated':>9} {'b_final':>9} {'b_act':<11} "
        f"{'aL':<3} {'a_sum':>9} {'a_stated':>9} {'a_final':>9} {'a_act':<11} "
        f"{'a_delta':>8} {'match':<10} {'pgs':<3}"
    )
    print("-" * 180)
    for r in results:
        if "error" in r:
            print(f"{r['id']:<5} ERROR: {r['error']}")
            continue
        print(
            f"{r['id']:<5} {r['vendor']:<24} {str(r['invoice'])[:14]:<14} "
            f"{r['before_lines']:<3} {r['before_line_sum']:>9.2f} "
            f"{r['before_stated']:>9.2f} {r['before_final']:>9.2f} "
            f"{r['before_action']:<11} "
            f"{r['after_lines']:<3} {r['after_line_sum']:>9.2f} "
            f"{r['after_stated']:>9.2f} {r['after_final']:>9.2f} "
            f"{r['after_action']:<11} "
            f"{r['after_delta']:>8.2f} "
            f"{str(r['claude_match'] or '-')[:10]:<10} "
            f"{str(r['claude_pages'] or '-')[:3]:<3}"
        )

    # Highlight the ones where final_total changes (real fixes), and
    # the ones where after_action is RECONCILED (Layer C catching things)
    print()
    print("Bills where Layer A+C would change the QBO total vs. status quo:")
    any_change = False
    for r in results:
        if "error" in r:
            continue
        # Status quo (pre-fix) would have produced just line_sum, NOT final_total
        status_quo = r["before_line_sum"]
        new_final = r["after_final"]
        if abs(status_quo - new_final) >= 0.50:
            any_change = True
            print(
                f"  #{r['id']:<4} {r['vendor']:<24} "
                f"would have pushed ${status_quo:.2f}, "
                f"now pushes ${new_final:.2f} "
                f"(delta ${new_final - status_quo:+.2f})"
            )
    if not any_change:
        print("  (none — every bill already extracted to the correct total)")


if __name__ == "__main__":
    main()
