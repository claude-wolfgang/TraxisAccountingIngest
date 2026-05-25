"""
Read-only dump of all QBO Bills in a date window (paid + unpaid), for
dedup against the Bills and Invoices mail folder.

Usage: python read_qbo_bills.py [since-YYYY-MM-DD]
Default window: 2026-01-01.
Writes logs/qbo_bills.json.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import accounting_ingest as ai
from accounting_ingest import QBOClient

# Read-only override to PRODUCTION. .traxis.env defaults the local client to
# sandbox; production uses separate refresh-token/realm keys, so flipping the
# in-process env touches no sandbox state and persists nothing to disk except
# a routine production refresh-token rotation (same as the GUI would do).
ai.ENV["QBO_ENVIRONMENT"] = "production"
ai.QBO_BASE_URL = ai.QBO_BASE_URLS["production"]

SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"


def main():
    qbo = QBOClient()
    print(f"QBO environment: {ai.ENV['QBO_ENVIRONMENT']}")
    sql = (f"SELECT * FROM Bill WHERE TxnDate >= '{SINCE}' "
           f"ORDERBY TxnDate DESC MAXRESULTS 500")
    data = qbo.qbo_query(sql)
    bills = data.get("QueryResponse", {}).get("Bill", [])
    print(f"Bills since {SINCE}: {len(bills)}\n")

    rows = []
    for b in bills:
        vref = b.get("VendorRef", {})
        rows.append({
            "id": b.get("Id"),
            "docnum": b.get("DocNumber"),
            "vendor": vref.get("name"),
            "vendor_id": vref.get("value"),
            "txndate": b.get("TxnDate"),
            "duedate": b.get("DueDate"),
            "total": b.get("TotalAmt"),
            "balance": b.get("Balance"),
        })

    for r in rows:
        paid = "PAID" if (r["balance"] == 0) else f"open {r['balance']}"
        print(f"{r['txndate']}  {r['vendor'] or '?':32.32}  "
              f"doc={str(r['docnum']):14.14}  ${r['total']:>10}  {paid}")

    Path("logs").mkdir(exist_ok=True)
    Path("logs/qbo_bills.json").write_text(json.dumps({
        "environment": ai.ENV["QBO_ENVIRONMENT"], "since": SINCE,
        "generated": datetime.now(timezone.utc).isoformat(),
        "count": len(rows), "bills": rows}, indent=2))
    print(f"\nWrote logs/qbo_bills.json ({len(rows)} bills).")


if __name__ == "__main__":
    main()
