"""End-to-end test of the P27 -> QBO push pipeline against the QBO sandbox.

Validates:
- Single-line and multi-line bills push at the right TotalAmt
- Layer C reconciliation gate adds a balancing line when extraction
  undercaught the stated total (BILL_RECONCILED audit)
- Reconciliation handles the reverse case (BILL_OVER_TOTAL audit)
- check_duplicate_bill catches same-vendor / same-DocNumber dups
- check_duplicate_bill with vendor scoping does NOT false-positive on
  the same DocNumber for a different vendor

Refuses to run unless QBO_ENVIRONMENT=sandbox and sandbox creds are set.

Cleanup: deletes every Bill whose DocNumber starts with TEST_PREFIX after
all scenarios complete (whether they passed or failed). Test vendors are
left in place — QBO refuses to delete vendors that have transactions in
history.
"""

import json
import os
import re
import sys
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
import accounting_ingest as ai  # noqa: E402

TEST_PREFIX = f"TEST-{datetime.now().strftime('%H%M%S')}-"
TEST_VENDOR_A = "Traxis P27 Test Vendor A"
TEST_VENDOR_B = "Traxis P27 Test Vendor B"


# ─── helpers ───────────────────────────────────────────────────────────────

def must_be_sandbox():
    env = ai.ENV.get("QBO_ENVIRONMENT", "")
    if env != "sandbox":
        print(f"ABORT: QBO_ENVIRONMENT is {env!r}; set it to 'sandbox' in .traxis.env first.")
        print("  Production credentials are not used by this test, but the safety check is mandatory.")
        sys.exit(2)
    for k in ("QBO_SANDBOX_REFRESH_TOKEN", "QBO_SANDBOX_REALM_ID"):
        if not ai.ENV.get(k):
            print(f"ABORT: {k} missing from .traxis.env — run qbo_auth_sandbox.py first.")
            sys.exit(2)


def get_or_create_vendor(qbo, display_name):
    """Find a Vendor by DisplayName, or create one. Returns (id, name)."""
    safe = display_name.replace("'", "\\'")
    data = qbo.qbo_query(
        f"SELECT Id, DisplayName FROM Vendor WHERE DisplayName = '{safe}' MAXRESULTS 1"
    )
    rows = data.get("QueryResponse", {}).get("Vendor", [])
    if rows:
        return rows[0]["Id"], rows[0]["DisplayName"]
    r = requests.post(
        qbo._url("vendor"),
        headers=qbo._headers(),
        params={"minorversion": "65"},
        json={"DisplayName": display_name},
    )
    if not r.ok:
        qbo._raise_qbo_error(r)
    v = r.json().get("Vendor", {})
    return v.get("Id"), v.get("DisplayName")


def get_bill(qbo, bill_id):
    data = qbo.qbo_query(f"SELECT * FROM Bill WHERE Id = '{bill_id}' MAXRESULTS 1")
    bills = data.get("QueryResponse", {}).get("Bill", []) or []
    return bills[0] if bills else None


def delete_bill(qbo, bill_id, sync_token="0"):
    r = requests.post(
        qbo._url("bill"),
        headers=qbo._headers(),
        params={"operation": "delete", "minorversion": "65"},
        json={"Id": bill_id, "SyncToken": str(sync_token)},
    )
    return r.ok, r.text[:200]


def cleanup_test_bills(qbo, log):
    """Delete every Bill whose DocNumber starts with TEST_PREFIX."""
    safe = TEST_PREFIX.replace("'", "\\'")
    data = qbo.qbo_query(f"SELECT Id, DocNumber, SyncToken FROM Bill WHERE DocNumber LIKE '{safe}%' MAXRESULTS 50")
    bills = data.get("QueryResponse", {}).get("Bill", []) or []
    if not bills:
        log(f"Cleanup: no test bills to delete (prefix {TEST_PREFIX!r})")
        return
    for b in bills:
        ok, body = delete_bill(qbo, b["Id"], b.get("SyncToken", "0"))
        log(f"Cleanup: delete Bill #{b['Id']} ({b.get('DocNumber')}) -> {'OK' if ok else 'FAIL '+body}")


def read_audit_since(start_pos):
    """Return audit-log lines written since byte offset start_pos. Returns []
    if the log doesn't exist yet."""
    if not ai.QBO_AUDIT_LOG.exists():
        return []
    with ai.QBO_AUDIT_LOG.open("r", encoding="utf-8") as f:
        f.seek(start_pos)
        return f.readlines()


def audit_log_size():
    if not ai.QBO_AUDIT_LOG.exists():
        return 0
    return ai.QBO_AUDIT_LOG.stat().st_size


def audit_events_for(doc_number, lines):
    """Filter audit log lines to only those mentioning this doc_number.
    Returns list of (event, fields_dict)."""
    out = []
    for ln in lines:
        if f"doc_number={doc_number}" not in ln:
            continue
        parts = ln.rstrip("\n").split("\t")
        if len(parts) < 2:
            continue
        event = parts[1]
        fields = {}
        for p in parts[2:]:
            if "=" in p:
                k, v = p.split("=", 1)
                fields[k] = v
        out.append((event, fields))
    return out


# ─── scenarios ─────────────────────────────────────────────────────────────

def fab(doc_number, vendor_name, total, line_amounts):
    """Fabricate an extracted-dict shaped like AIExtractor output."""
    return {
        "vendor_name": vendor_name,
        "invoice_number": doc_number,
        "invoice_date": datetime.now().strftime("%Y-%m-%d"),
        "total_amount": f"{total:.2f}",
        "subtotal": f"{total:.2f}",
        "line_items": [
            {"description": f"line {i+1}", "quantity": "1",
             "unit_price": f"{a:.2f}", "extended_price": f"{a:.2f}"}
            for i, a in enumerate(line_amounts)
        ],
        "notes": "P27 sandbox test bill",
        "confidence": 1.0,
    }


def run_scenarios(qbo, vendor_a_id, vendor_a_name, vendor_b_id, vendor_b_name, log):
    results = []
    audit_pos = audit_log_size()

    def assert_(label, cond, detail=""):
        results.append({"name": label, "pass": bool(cond), "detail": detail})
        log(f"  {'PASS' if cond else 'FAIL'}  {label}  {detail}")

    def docno(n):
        return f"{TEST_PREFIX}{n:03d}"

    # ── Scenario 1: single line, clean push ──────────────────────────────
    log("\n[1] Single-line clean push")
    dn = docno(1)
    extracted = fab(dn, vendor_a_name, total=100.00, line_amounts=[100.00])
    bid, url = qbo.create_bill(extracted, vendor_a_id, vendor_a_name)
    b = get_bill(qbo, bid)
    assert_("S1: bill created", b is not None, f"id={bid}")
    assert_("S1: TotalAmt == $100", b and abs(b.get("TotalAmt", 0) - 100.0) < 0.01,
            f"got ${b.get('TotalAmt') if b else '?'}")
    assert_("S1: 1 Line", b and len(b.get("Line", [])) == 1,
            f"got {len(b.get('Line', [])) if b else 0} lines")
    events = audit_events_for(dn, read_audit_since(audit_pos))
    assert_("S1: BILL_CREATED audited", any(e[0] == "BILL_CREATED" for e in events),
            f"events={[e[0] for e in events]}")
    assert_("S1: no BILL_RECONCILED", not any(e[0] == "BILL_RECONCILED" for e in events))

    # ── Scenario 2: multi-line clean push ─────────────────────────────────
    log("\n[2] Multi-line clean push")
    dn = docno(2)
    extracted = fab(dn, vendor_a_name, total=300.00, line_amounts=[100, 100, 100])
    bid, url = qbo.create_bill(extracted, vendor_a_id, vendor_a_name)
    b = get_bill(qbo, bid)
    assert_("S2: TotalAmt == $300", b and abs(b.get("TotalAmt", 0) - 300.0) < 0.01,
            f"got ${b.get('TotalAmt') if b else '?'}")
    assert_("S2: 3 Lines", b and len(b.get("Line", [])) == 3,
            f"got {len(b.get('Line', [])) if b else 0}")
    events = audit_events_for(dn, read_audit_since(audit_pos))
    assert_("S2: no BILL_RECONCILED", not any(e[0] == "BILL_RECONCILED" for e in events))

    # ── Scenario 3: extraction undercount -> Layer C reconciles ──────────
    log("\n[3] Multi-line UNDERcaught -> Layer C reconciliation expected")
    dn = docno(3)
    extracted = fab(dn, vendor_a_name, total=400.00, line_amounts=[100, 100])  # only $200 in lines
    bid, url = qbo.create_bill(extracted, vendor_a_id, vendor_a_name)
    b = get_bill(qbo, bid)
    assert_("S3: TotalAmt == $400 (was $200 without fix)",
            b and abs(b.get("TotalAmt", 0) - 400.0) < 0.01,
            f"got ${b.get('TotalAmt') if b else '?'}")
    assert_("S3: 3 lines (2 + balancing)", b and len(b.get("Line", [])) == 3,
            f"got {len(b.get('Line', [])) if b else 0}")
    if b:
        bal_line = next((l for l in b.get("Line", [])
                         if "Unitemized balance" in (l.get("Description") or "")), None)
        assert_("S3: balancing line present", bal_line is not None,
                detail=(bal_line or {}).get("Description", "")[:80] if bal_line else "")
        assert_("S3: balancing line == $200",
                bal_line and abs(bal_line.get("Amount", 0) - 200.0) < 0.01,
                f"got ${(bal_line or {}).get('Amount')}")
    events = audit_events_for(dn, read_audit_since(audit_pos))
    assert_("S3: BILL_RECONCILED audited", any(e[0] == "BILL_RECONCILED" for e in events),
            f"events={[e[0] for e in events]}")

    # ── Scenario 4: extraction OVERcount -> BILL_OVER_TOTAL log ──────────
    log("\n[4] Line sum exceeds stated -> BILL_OVER_TOTAL audit expected")
    dn = docno(4)
    extracted = fab(dn, vendor_a_name, total=100.00, line_amounts=[80, 80])  # lines=$160, stated=$100
    bid, url = qbo.create_bill(extracted, vendor_a_id, vendor_a_name)
    b = get_bill(qbo, bid)
    assert_("S4: TotalAmt == $160 (line sum)",
            b and abs(b.get("TotalAmt", 0) - 160.0) < 0.01,
            f"got ${b.get('TotalAmt') if b else '?'}")
    events = audit_events_for(dn, read_audit_since(audit_pos))
    assert_("S4: BILL_OVER_TOTAL audited",
            any(e[0] == "BILL_OVER_TOTAL" for e in events),
            f"events={[e[0] for e in events]}")

    # ── Scenario 5: dup check fires on exact same-vendor/DocNumber ───────
    log("\n[5] check_duplicate_bill catches exact dup (same vendor)")
    dn = docno(1)  # already exists from S1
    dup_url = qbo.check_duplicate_bill(dn, vendor_id=vendor_a_id)
    assert_("S5: dup detected with vendor scoping", dup_url is not None,
            f"got {dup_url}")
    dup_url_unscoped = qbo.check_duplicate_bill(dn)
    assert_("S5: dup also detected vendor-unscoped", dup_url_unscoped is not None,
            f"got {dup_url_unscoped}")

    # ── Scenario 6: vendor-scoped check does NOT false-positive ──────────
    log("\n[6] same DocNumber, different vendor: scoped check returns None")
    dn = docno(1)  # exists for vendor A
    # Try scoping to vendor B (no bill with that doc# under B)
    scoped_b = qbo.check_duplicate_bill(dn, vendor_id=vendor_b_id)
    assert_("S6: scoped check returns None for different vendor",
            scoped_b is None, f"got {scoped_b}")
    # Sanity: unscoped check would falsely match
    unscoped = qbo.check_duplicate_bill(dn)
    assert_("S6: unscoped check false-positives (proves the fix matters)",
            unscoped is not None, f"got {unscoped}")
    # Push the legitimate non-dup bill under vendor B
    extracted = fab(dn, vendor_b_name, total=50.00, line_amounts=[50.00])
    bid_b, _ = qbo.create_bill(extracted, vendor_b_id, vendor_b_name)
    b_b = get_bill(qbo, bid_b)
    assert_("S6: vendor B bill posts cleanly", b_b is not None,
            f"id={bid_b}")

    # ── Scenario 7: real Hadco-shape $12.47 pattern ──────────────────────
    log("\n[7] Hadco $12.47 'Total Misc' shape - reconciliation expected")
    dn = docno(7)
    extracted = fab(dn, vendor_a_name, total=1362.47, line_amounts=[1350.00])
    bid, url = qbo.create_bill(extracted, vendor_a_id, vendor_a_name)
    b = get_bill(qbo, bid)
    assert_("S7: TotalAmt == $1362.47",
            b and abs(b.get("TotalAmt", 0) - 1362.47) < 0.01,
            f"got ${b.get('TotalAmt') if b else '?'}")
    assert_("S7: 2 lines (1 real + 1 balancing)",
            b and len(b.get("Line", [])) == 2,
            f"got {len(b.get('Line', [])) if b else 0}")
    if b:
        bal = next((l for l in b.get("Line", [])
                    if "Unitemized balance" in (l.get("Description") or "")), None)
        assert_("S7: balancing line == $12.47",
                bal and abs(bal.get("Amount", 0) - 12.47) < 0.01,
                f"got ${(bal or {}).get('Amount')}")

    return results


# ─── main ──────────────────────────────────────────────────────────────────

def main():
    must_be_sandbox()
    print(f"QBO_ENVIRONMENT={ai.QBO_ENVIRONMENT}  realm={ai.ENV['QBO_SANDBOX_REALM_ID']}")
    print(f"Audit log: {ai.QBO_AUDIT_LOG}")
    print(f"Test DocNumber prefix: {TEST_PREFIX}")

    qbo = ai.QBOClient()

    def log(m):
        print(m, flush=True)

    log("\nGet-or-create test vendors...")
    a_id, a_name = get_or_create_vendor(qbo, TEST_VENDOR_A)
    b_id, b_name = get_or_create_vendor(qbo, TEST_VENDOR_B)
    log(f"  vendor A: id={a_id} name={a_name!r}")
    log(f"  vendor B: id={b_id} name={b_name!r}")

    results = []
    try:
        results = run_scenarios(qbo, a_id, a_name, b_id, b_name, log)
    finally:
        log("\nCleaning up test bills...")
        try:
            cleanup_test_bills(qbo, log)
        except Exception as e:
            log(f"  cleanup error (manual cleanup may be required): {e}")

    log("\n" + "=" * 60)
    passed = sum(1 for r in results if r["pass"])
    failed = sum(1 for r in results if not r["pass"])
    log(f"SUMMARY: {passed} passed, {failed} failed, {len(results)} total")
    log("=" * 60)
    for r in results:
        tag = " OK " if r["pass"] else "FAIL"
        log(f"  [{tag}] {r['name']}  {r.get('detail','')}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
