"""Phase 2: take the dump from reconcile_folders.py, derive a reference
number per thread, query QBO Bills and ProShop POs/customerPOs/bills, and
report what's NOT already present.

Strategy:
- Dedupe by Graph `conversationId` (FW: pairs collapse into one thread)
- Extract reference numbers via regex from subject + attachment filenames
- Bills and Invoices → query QBO `SELECT * FROM Bill WHERE DocNumber = ?`
  (mirrors check_duplicate_bill); also query ProShop `bills.referenceNumber`
- Orders → query ProShop `customerPOs.clientPONumber` and
  `purchaseOrders.confirmationNumber` (vendor POs)
- For threads where no identifier is found, list as "needs human look"
"""

from pathlib import Path
import json
import re
import sys
import time
import base64
import requests
from datetime import datetime, timezone, timedelta

import reconcile_folders as rf  # reuse env + graph helpers

ENV = rf.ENV
LOOKBACK_DAYS = rf.LOOKBACK_DAYS

# ─── ProShop OAuth (read-only — uses ACCOUNTING_CLIENT_ID) ─────────────────

PROSHOP_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
PROSHOP_GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"

_ps_cache = {"tok": None, "exp": 0}

def proshop_token():
    if _ps_cache["tok"] and time.time() < _ps_cache["exp"] - 60:
        return _ps_cache["tok"]
    r = requests.post(PROSHOP_TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": ENV["ACCOUNTING_CLIENT_ID"],
        "client_secret": ENV["ACCOUNTING_CLIENT_SECRET"],
        "scope": ENV["ACCOUNTING_SCOPE"],
    })
    r.raise_for_status()
    data = r.json()
    _ps_cache["tok"] = data["access_token"]
    _ps_cache["exp"] = time.time() + data.get("expires_in", 3600)
    return _ps_cache["tok"]

def proshop_query(gql):
    r = requests.post(
        PROSHOP_GRAPHQL_URL,
        headers={
            "Authorization": f"Bearer {proshop_token()}",
            "Content-Type": "application/json",
        },
        json={"query": gql},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body and not body.get("data"):
        raise RuntimeError(f"ProShop errors: {body['errors']}")
    return body.get("data", {})

# ─── QBO OAuth ─────────────────────────────────────────────────────────────

QBO_BASE_URLS = {
    "sandbox":    "https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}",
    "production": "https://quickbooks.api.intuit.com/v3/company/{realm_id}",
}
QBO_APP_URLS = {
    "sandbox":    "https://app.sandbox.qbo.intuit.com/app/bill?txnId={bill_id}",
    "production": "https://app.qbo.intuit.com/app/bill?txnId={bill_id}",
}

_qbo_cache = {"tok": None, "exp": 0}

def qbo_token():
    if _qbo_cache["tok"] and time.time() < _qbo_cache["exp"] - 60:
        return _qbo_cache["tok"]
    # Re-read env from disk in case the running ingest service rotated the
    # refresh token since we last loaded it.
    fresh = rf.load_env()
    creds = base64.b64encode(
        f"{fresh['QBO_CLIENT_ID']}:{fresh['QBO_CLIENT_SECRET']}".encode()
    ).decode()
    r = requests.post(
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": fresh["QBO_REFRESH_TOKEN"],
        },
    )
    if not r.ok:
        try:
            print(f"  [qbo refresh failed body]: {r.text[:300]}", file=sys.stderr)
        except Exception:
            pass
    r.raise_for_status()
    data = r.json()
    _qbo_cache["tok"] = data["access_token"]
    _qbo_cache["exp"] = time.time() + data.get("expires_in", 3600)
    # If QBO rotated the refresh token, persist it back so the running
    # service doesn't end up with a stale one.
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != fresh.get("QBO_REFRESH_TOKEN"):
        for p in rf.ENV_PATHS:
            if p.exists():
                lines = p.read_text().splitlines()
                lines = [f"QBO_REFRESH_TOKEN={new_refresh}" if ln.startswith("QBO_REFRESH_TOKEN=") else ln
                         for ln in lines]
                p.write_text("\n".join(lines) + "\n")
                break
    return _qbo_cache["tok"]

def qbo_query(sql):
    env = ENV.get("QBO_ENVIRONMENT", "production")
    base = QBO_BASE_URLS[env].format(realm_id=ENV["QBO_REALM_ID"])
    r = requests.get(
        f"{base}/query",
        headers={
            "Authorization": f"Bearer {qbo_token()}",
            "Accept": "application/json",
        },
        params={"query": sql, "minorversion": "65"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def qbo_bill_url(bid):
    env = ENV.get("QBO_ENVIRONMENT", "production")
    return QBO_APP_URLS[env].format(bill_id=bid)

# ─── Local P27 queue DB ────────────────────────────────────────────────────

import sqlite3 as _sqlite3
DB_PATH = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\ingest_queue.db")

_queue_cache = None

def _load_queue():
    """Load all queue rows once. Returns list of (id, doc_type, status, refs_set, vendor)."""
    global _queue_cache
    if _queue_cache is not None:
        return _queue_cache
    con = _sqlite3.connect(DB_PATH)
    con.row_factory = _sqlite3.Row
    out = []
    for r in con.execute("SELECT id, doc_type, status, extracted_json, proshop_url FROM queue"):
        ej = {}
        try:
            ej = json.loads(r["extracted_json"] or "{}")
        except Exception:
            pass
        refs = set()
        for k in ("invoice_number", "po_number", "packing_slip_number",
                  "quote_number", "reference_number"):
            v = ej.get(k)
            if v:
                refs.add(str(v).strip())
                refs.add(normalize_ref(str(v)))
                # ref may itself be "MULTIPLE: 2125689, 2125690, ..." — split
                if "MULTIPLE" in str(v).upper() or "," in str(v):
                    for piece in re.split(r"[,\s;]+", str(v)):
                        piece = piece.strip().strip(":")
                        if piece and piece.isdigit():
                            refs.add(piece)
        out.append({
            "id": r["id"],
            "doc_type": r["doc_type"],
            "status": r["status"],
            "refs": refs,
            "vendor": ej.get("vendor_name") or ej.get("customer_name") or "",
            "proshop_url": r["proshop_url"],
        })
    con.close()
    _queue_cache = out
    return out

def find_in_local_queue(ref):
    """Return matching local-queue rows by ref number.

    Permissive match — also accepts queue refs that contain the search
    digits as a prefix or substring (e.g. queue has "224142_362" for
    email ref "224142", which is an extraction-artifact suffix)."""
    if not ref:
        return []
    candidates = {ref, normalize_ref(ref), ref.lstrip("0")}
    candidates = {c for c in candidates if c}
    # Strip non-digits for permissive matching
    digits_ref = re.sub(r"\D", "", ref)
    out = []
    for row in _load_queue():
        if row["refs"] & candidates:
            out.append({**row, "refs": sorted(row["refs"])})
            continue
        if digits_ref and len(digits_ref) >= 5:
            # Substring match against each queue ref (drop \D from each)
            for qref in row["refs"]:
                qdigits = re.sub(r"\D", "", qref)
                if qdigits and (digits_ref == qdigits or
                                qdigits.startswith(digits_ref) or
                                digits_ref.startswith(qdigits) and len(qdigits) >= 5):
                    out.append({**row, "refs": sorted(row["refs"])})
                    break
    return out

# ─── Identifier extraction ─────────────────────────────────────────────────

# Order folder: look for customer PO numbers
ORDERS_PATTERNS = [
    # R2Sonic: "PO115244" / "PO115245" / "PO115267"
    re.compile(r"\bPO\s*(\d{5,7})\b", re.I),
    # Setcom: "WO 352950" / "WO352949"
    re.compile(r"\bWO\s*(\d{5,7})\b", re.I),
    # OPmobility / generic: "Order - 4516803284" / "Order # 12345"
    re.compile(r"\bOrder\b[^A-Za-z0-9]+(\d{6,12})", re.I),
    # Numeric attachment IDs like "1778704054705" in netsuite filenames — too noisy, skip
]

# Bills folder: invoice / statement / bill / packing-slip numbers
BILLS_PATTERNS = [
    # "Invoice 00042125", "Invoice# 1878933", "Sales Invoice - 2143747"
    re.compile(r"\bInvoice\s*#?\s*[-:]?\s*(\d{4,10})\b", re.I),
    # "Inv1878933.pdf" / "Inv_153025_from_Hillary" — _ is a word char so use lookbehind
    re.compile(r"(?<![A-Za-z0-9])Inv[_\-]?(\d{4,10})(?![A-Za-z0-9])", re.I),
    # "Statement of Account 666536"
    re.compile(r"Statement of Account\s*#?\s*(\d{4,10})", re.I),
    # Vendor PO inside subject: "your PO number 263108"
    re.compile(r"\bPO\s*number\s*(\d{5,7})\b", re.I),
    # Sentry-style: "FW: 2521075        FW: Bill Question" — digits early in subject
    re.compile(r"FW:\s*(\d{6,8})\s", re.I),
    # "Order receipt for order 1275847" / "Invoice-Number-1275847.pdf"
    re.compile(r"Invoice[-_\s]?Number[-_\s]?(\d{4,10})", re.I),
    # "Statement of Account #" + Hadco STMT-style attachments
    re.compile(r"STMT(\d{6,10})", re.I),
]

def extract_identifiers(subjects, attachments, folder):
    """Pull all probable reference numbers from subjects + attachment names."""
    hay = " | ".join(subjects)
    for att in attachments:
        if att.get("name"):
            hay += " | " + att["name"]
    patterns = ORDERS_PATTERNS if folder == "Orders" else BILLS_PATTERNS
    found = []
    for pat in patterns:
        for m in pat.finditer(hay):
            ref = m.group(1)
            # Capture the pattern label so we know what kind it is
            kind = pat.pattern[:30]
            if (ref, pat) not in [(r, p) for r, p, _ in found]:
                found.append((ref, pat, kind))
    return found

# ─── ProShop / QBO dup-check ───────────────────────────────────────────────

def normalize_ref(s):
    s = str(s or "").strip()
    return re.sub(r'^(p\s*[/\.]?\s*o\s*[#:\-]?\s*|inv(?:oice)?\s*[#:\-]?\s*)',
                  '', s, flags=re.I).strip()

def find_in_proshop_customer_po(ref):
    """Return list of {url, date, clientPONumber} for matches."""
    candidates = [ref, normalize_ref(ref), f"PO{ref}"]
    seen = set()
    out = []
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        safe = cand.replace('"', '\\"')
        gql = (
            '{ customerPOs(filter: {clientPONumber: ["' + safe + '"]}, pageSize: 5) '
            '{ records { proshopUrl clientPONumber dateEntered } } }'
        )
        try:
            data = proshop_query(gql)
        except Exception as e:
            print(f"  [proshop CPO query failed for {cand!r}]: {e}", file=sys.stderr)
            continue
        for rec in data.get("customerPOs", {}).get("records", []) or []:
            out.append({
                "url": rec.get("proshopUrl"),
                "date": rec.get("dateEntered"),
                "clientPONumber": rec.get("clientPONumber"),
                "matched_as": cand,
            })
    return out

def find_in_proshop_purchase_order(ref):
    """Vendor POs — confirmationNumber field."""
    candidates = [ref, normalize_ref(ref)]
    seen = set()
    out = []
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        safe = cand.replace('"', '\\"')
        gql = (
            '{ purchaseOrders(filter: {confirmationNumber: ["' + safe + '"]}, pageSize: 5) '
            '{ records { proshopUrl confirmationNumber date } } }'
        )
        try:
            data = proshop_query(gql)
        except Exception as e:
            print(f"  [proshop VPO query failed for {cand!r}]: {e}", file=sys.stderr)
            continue
        for rec in data.get("purchaseOrders", {}).get("records", []) or []:
            out.append({
                "url": rec.get("proshopUrl"),
                "date": rec.get("date"),
                "confirmationNumber": rec.get("confirmationNumber"),
                "matched_as": cand,
            })
    return out

def find_in_proshop_bill(ref):
    candidates = [ref, normalize_ref(ref)]
    seen = set()
    out = []
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        safe = cand.replace('"', '\\"')
        gql = (
            '{ bills(filter: {referenceNumber: ["' + safe + '"]}, pageSize: 5) '
            '{ records { proshopUrl referenceNumber dateIssued } } }'
        )
        try:
            data = proshop_query(gql)
        except Exception as e:
            print(f"  [proshop bill query failed for {cand!r}]: {e}", file=sys.stderr)
            continue
        for rec in data.get("bills", {}).get("records", []) or []:
            out.append({
                "url": rec.get("proshopUrl"),
                "date": rec.get("dateIssued"),
                "referenceNumber": rec.get("referenceNumber"),
                "matched_as": cand,
            })
    return out

def find_in_qbo_bill(ref):
    candidates = [ref, normalize_ref(ref)]
    seen = set()
    out = []
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        safe = cand.replace("'", "\\'")
        try:
            data = qbo_query(f"SELECT * FROM Bill WHERE DocNumber = '{safe}' MAXRESULTS 5")
        except Exception as e:
            print(f"  [qbo query failed for {cand!r}]: {e}", file=sys.stderr)
            continue
        for b in data.get("QueryResponse", {}).get("Bill", []) or []:
            out.append({
                "url": qbo_bill_url(b.get("Id")),
                "DocNumber": b.get("DocNumber"),
                "TxnDate": b.get("TxnDate"),
                "TotalAmt": b.get("TotalAmt"),
                "Vendor": b.get("VendorRef", {}).get("name"),
                "matched_as": cand,
            })
    return out

# ─── Thread dedup ──────────────────────────────────────────────────────────

def thread_key(msg):
    """Collapse FW: pairs. Strip leading RE:/FW: and whitespace from subject."""
    subj = msg.get("subject", "")
    cleaned = re.sub(r"^(?:(?:re|fw|fwd):\s*)+", "", subj, flags=re.I).strip()
    return cleaned.lower()

def group_threads(messages):
    """Group messages by cleaned subject. Returns list of {subjects, attachments, msgs, received}."""
    by_key = {}
    for m in messages:
        k = thread_key(m)
        by_key.setdefault(k, []).append(m)
    threads = []
    for k, msgs in by_key.items():
        msgs.sort(key=lambda x: x.get("received") or "")
        atts = []
        seen_names = set()
        for m in msgs:
            for a in m.get("attachments") or []:
                n = a.get("name")
                if n and n not in seen_names:
                    seen_names.add(n)
                    atts.append(a)
        threads.append({
            "thread_key": k,
            "first_subject": msgs[0].get("subject", ""),
            "received_first": msgs[0].get("received"),
            "received_last": msgs[-1].get("received"),
            "from_addrs": sorted({m.get("from") for m in msgs if m.get("from")}),
            "msg_count": len(msgs),
            "attachments": atts,
            "subjects": [m.get("subject", "") for m in msgs],
        })
    threads.sort(key=lambda t: t["received_last"] or "", reverse=True)
    return threads

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    phase1_path = Path(__file__).parent / "logs" / "reconcile_folders_phase1.json"
    if not phase1_path.exists():
        print("Run reconcile_folders.py first to produce phase1 JSON")
        sys.exit(1)
    data = json.loads(phase1_path.read_text())

    report = {}
    for folder, msgs in data.items():
        print(f"\n{'=' * 70}")
        print(f"FOLDER: {folder}  ({len(msgs)} messages)")
        print('=' * 70)
        threads = group_threads(msgs)
        print(f"{len(threads)} unique threads after FW:/RE: collapse\n")

        folder_report = []
        for t in threads:
            ids = extract_identifiers(t["subjects"], t["attachments"], folder)
            row = {
                "subject": t["first_subject"][:90],
                "from_external": [a for a in t["from_addrs"] if a and "traxismfg" not in a.lower()],
                "received": t["received_last"],
                "msg_count": t["msg_count"],
                "attachments": [a.get("name") for a in t["attachments"] if a.get("name")],
                "extracted_ids": [r for r, _, _ in ids],
                "matches": {},
                "verdict": None,
            }

            if folder.lower() == "orders":
                for ref, pat, _ in ids:
                    cpo = find_in_proshop_customer_po(ref)
                    if cpo:
                        row["matches"].setdefault(ref, {})["customer_po"] = cpo
                    vpo = find_in_proshop_purchase_order(ref)
                    if vpo:
                        row["matches"].setdefault(ref, {})["vendor_po"] = vpo
                    lq = find_in_local_queue(ref)
                    if lq:
                        row["matches"].setdefault(ref, {})["p27_queue"] = lq
            else:  # Bills and Invoices
                for ref, pat, _ in ids:
                    qb = find_in_qbo_bill(ref)
                    if qb:
                        row["matches"].setdefault(ref, {})["qbo_bill"] = qb
                    psb = find_in_proshop_bill(ref)
                    if psb:
                        row["matches"].setdefault(ref, {})["proshop_bill"] = psb
                    lq = find_in_local_queue(ref)
                    if lq:
                        row["matches"].setdefault(ref, {})["p27_queue"] = lq

            # Classify match strength:
            #   STRONG = already in ProShop / QBO (true duplicate)
            #   QUEUED = in the local P27 ingest queue (already picked up,
            #            just not yet pushed — usually still actionable, but
            #            we shouldn't double-process it)
            has_strong = False
            has_queued = False
            for mset in row["matches"].values():
                for kind in mset:
                    if kind == "p27_queue":
                        has_queued = True
                    else:
                        has_strong = True

            if not ids:
                row["verdict"] = "NO_ID_FOUND"
            elif has_strong:
                row["verdict"] = "DUPLICATE"
            elif has_queued:
                row["verdict"] = "IN_QUEUE"
            else:
                row["verdict"] = "NEW"

            folder_report.append(row)

            tag = {"DUPLICATE": "[DUP]", "NEW": "[NEW]",
                   "IN_QUEUE": "[QUE]", "NO_ID_FOUND": "[??]"}[row["verdict"]]
            ext = ",".join(row["from_external"]) or "(internal only)"
            ids_str = ",".join(row["extracted_ids"]) or "—"
            print(f"  {tag}  {row['received']}  {ext[:35]:<35}  ids=[{ids_str}]  {row['subject']}")
            for ref, mset in row["matches"].items():
                for kind, hits in mset.items():
                    for h in hits:
                        url = h.get("url") or ""
                        date = h.get("date") or h.get("TxnDate") or ""
                        print(f"        match: {kind} ref={ref} date={date} -> {url}")
        report[folder] = folder_report

    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    out = logs_dir / "reconcile_check_results.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote results -> {out}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for folder, rows in report.items():
        new_rows    = [r for r in rows if r["verdict"] == "NEW"]
        in_queue    = [r for r in rows if r["verdict"] == "IN_QUEUE"]
        unknown     = [r for r in rows if r["verdict"] == "NO_ID_FOUND"]
        duplicates  = [r for r in rows if r["verdict"] == "DUPLICATE"]
        print(f"\n{folder}:  {len(rows)} threads  ({len(duplicates)} DUP, "
              f"{len(in_queue)} already in P27 queue, "
              f"{len(new_rows)} NEW, {len(unknown)} no-ID)")

        if new_rows:
            print(f"\n  >>> NEW — not in ProShop/QBO and not yet in P27 queue:")
            for r in new_rows:
                ext = ",".join(r["from_external"]) or "(internal only)"
                print(f"     - {r['received']}  from {ext[:40]:<40}  ids={r['extracted_ids']}")
                print(f"        subject: {r['subject']}")
        if in_queue:
            print(f"\n  --- IN_QUEUE — already picked up by P27 (pending review/upload):")
            for r in in_queue:
                ext = ",".join(r["from_external"]) or "(internal only)"
                qrows = []
                for ref, mset in r["matches"].items():
                    for q in mset.get("p27_queue", []):
                        qrows.append(f"#{q['id']}({q['status']}/{q['doc_type']})")
                print(f"     - {r['received']}  from {ext[:40]:<40}  ids={r['extracted_ids']}  queue=[{', '.join(qrows)}]")
                print(f"        subject: {r['subject']}")
        if unknown:
            print(f"\n  ??? NO_IDENTIFIER — need human review:")
            for r in unknown:
                ext = ",".join(r["from_external"]) or "(internal only)"
                print(f"     - {r['received']}  from {ext[:40]:<40}")
                print(f"        subject: {r['subject']}")
                if r['attachments']:
                    print(f"        atts: {r['attachments']}")

if __name__ == "__main__":
    main()
