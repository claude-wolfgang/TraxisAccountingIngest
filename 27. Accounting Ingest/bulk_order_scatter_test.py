"""Empirically characterize the addCustomerPo bulk-insert scatter.

Pushes 5 fresh CPOs against client 3DS1 via the OLD bulk-add path (single
addCustomerPo mutation with partsOrdered as a 20-item array). Reads back
originalSortPosition + itemNumber for each line and prints a comparison
matrix so we can tell whether the scatter is:

  (a) identical every run  -> content-driven (e.g., alphabetic insert order,
      index-update timing) and theoretically compensable
  (b) varies between runs  -> commit-order noise from the persistence layer
      (DB parallelism, lock contention) and not compensable

Test clientPONumber prefix: BULK-ORDER-TEST-<timestamp>-<run>
Test client: 3DS1 (same one used for BASIC-AUTH-TEST 2026-05-06)

Read-only output, but it creates 5 real CPOs in ProShop — DELETE them after
inspection. Each row's clientPartNumber is "TEST-LINE-NN" so they're easy
to spot in cleanup.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounting_ingest as ai


NUM_RUNS = 5
NUM_LINES = 20
TEST_CLIENT = "3DS1"

ADD_CPO = """
mutation($data: AddCustomerPoInput!) {
  addCustomerPo(data: $data) { poId proshopUrl }
}
"""

READ_CPO = """
query($poId: String!) {
  customerPOs(filter: {poId: [$poId]}, pageSize: 1) {
    records {
      poId
      clientPONumber
      partsOrdered(pageSize: 50) {
        records {
          itemNumber
          clientPartNumber
        }
      }
    }
  }
}
"""


def build_lines(n: int, zero_pad: bool = False) -> list[dict]:
    """Build n identifiable line items. Each line carries:
      - clientPartNumber = TEST-LINE-01 .. TEST-LINE-NN (unique, sortable)
      - itemNumber = "1" .. "N" (raw) or "01".."NN" (zero-padded)
      - quantityOrdered = (n - i + 1)  (decreasing)
      - pricePer = i * 1.0 (increasing)
    """
    width = max(2, len(str(n))) if zero_pad else 0
    out = []
    for i in range(1, n + 1):
        item_num = str(i).zfill(width) if zero_pad else str(i)
        out.append({
            "itemNumber": item_num,
            "clientPartNumber": f"TEST-LINE-{i:02d}",
            "quantityOrdered": (n - i + 1),
            "pricePer": float(i),
            "lineItemNotes": f"input position {i}",
        })
    return out


def push_one(proshop, run_idx: int, batch_id: str, log,
             zero_pad: bool = False) -> tuple[str, str]:
    """Push a fresh CPO with NUM_LINES lines via bulk addCustomerPo. Returns
    (poId, clientPONumber)."""
    suffix = "PAD" if zero_pad else "RAW"
    client_po_number = f"BULK-ORDER-TEST-{batch_id}-{suffix}-{run_idx}"
    lines = build_lines(NUM_LINES, zero_pad=zero_pad)
    payload = {
        "client": TEST_CLIENT,
        "clientPONumber": client_po_number,
        "dateEntered": datetime.now().strftime("%Y-%m-%d"),
        "notes": "[bulk_order_scatter_test] DELETE ME AFTER REVIEW",
        "year": str(datetime.now().year),
        "partsOrdered": lines,
    }
    sess = proshop._get_basic_session()
    result = sess.execute(ADD_CPO, {"data": payload})
    rec = (result or {}).get("addCustomerPo") or {}
    po_id = rec.get("poId") or ""
    log(f"run {run_idx}: created {po_id}  (clientPONumber={client_po_number})")
    return po_id, client_po_number


def read_back(proshop, po_id: str) -> list[dict]:
    sess = proshop._get_basic_session()
    data = sess.execute(READ_CPO, {"poId": po_id})
    recs = (data.get("customerPOs") or {}).get("records") or []
    if not recs:
        return []
    return (recs[0].get("partsOrdered") or {}).get("records") or []


def input_pos_from_clientpn(pn: str) -> int | None:
    """Recover the input position 1..N from clientPartNumber 'TEST-LINE-NN'."""
    if not pn or not pn.startswith("TEST-LINE-"):
        return None
    try:
        return int(pn.split("-")[-1])
    except ValueError:
        return None


def main() -> int:
    zero_pad = "--pad" in sys.argv
    proshop = ai.ProShopClient()
    batch_id = datetime.now().strftime("%H%M%S")
    log = print

    print(f"=== bulk_order_scatter_test ({NUM_RUNS} runs × {NUM_LINES} lines, "
          f"itemNumber={'zero-padded' if zero_pad else 'raw'}) ===")
    print(f"batch_id={batch_id}  client={TEST_CLIENT}")
    print()

    runs: list[tuple[str, list[dict]]] = []  # (po_id, partsOrdered records as read back)
    for run in range(1, NUM_RUNS + 1):
        po_id, _ = push_one(proshop, run, batch_id, log, zero_pad=zero_pad)
        # Give ProShop a moment to settle the writes before we read.
        time.sleep(1.0)
        lines = read_back(proshop, po_id)
        runs.append((po_id, lines))
        log(f"run {run}: read back {len(lines)} lines from {po_id}")
        print()

    # ── Analysis ────────────────────────────────────────────────────────────
    # For each run, map input_position -> read-back rank (the position in the
    # records[] list as ProShop returned it). If ProShop preserved order,
    # rank == input_position.
    print()
    print(f"{'INPUT POS':>10}  ", end="")
    for run in range(1, NUM_RUNS + 1):
        print(f"  run{run:>2}_rank  run{run:>2}_itemNum", end="")
    print()
    print("-" * (10 + NUM_RUNS * 24))

    for input_pos in range(1, NUM_LINES + 1):
        row = [f"{input_pos:>10}"]
        for _, lines in runs:
            rank = None
            item_num = None
            for idx, ln in enumerate(lines, 1):
                if input_pos_from_clientpn(ln.get("clientPartNumber") or "") == input_pos:
                    rank = idx
                    item_num = ln.get("itemNumber")
                    break
            row.append(f"  {str(rank or '—'):>10}")
            row.append(f"  {str(item_num or '—'):>10}")
        print("".join(row))

    print()
    # Cross-run consistency: is the scatter identical?
    rank_signatures = []
    for _, lines in runs:
        sig = []
        for ln in lines:
            sig.append(input_pos_from_clientpn(ln.get("clientPartNumber") or ""))
        rank_signatures.append(tuple(sig))
    distinct = set(rank_signatures)
    print(f"Distinct ordering signatures across {NUM_RUNS} runs: {len(distinct)}")
    if len(distinct) == 1:
        print("  -> deterministic scatter (content-driven, theoretically compensable)")
    else:
        print("  -> non-deterministic scatter (commit-order noise)")
    print()
    print("Created CPOs (DELETE AFTER REVIEW):")
    for po_id, _ in runs:
        print(f"  {po_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
