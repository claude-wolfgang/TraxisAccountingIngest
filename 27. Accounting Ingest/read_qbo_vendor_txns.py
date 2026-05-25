"""
Read-only dump of all QBO transactions for a vendor (Bills, BillPayments,
and credit-card/cash Purchases), to reconcile what was billed vs paid.

Usage: python read_qbo_vendor_txns.py "Hillary"
Production, read-only. Writes logs/qbo_vendor_txns.json.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import accounting_ingest as ai
from accounting_ingest import QBOClient

ai.ENV["QBO_ENVIRONMENT"] = "production"
ai.QBO_BASE_URL = ai.QBO_BASE_URLS["production"]

NAME = sys.argv[1] if len(sys.argv) > 1 else "Hillary"


def main():
    qbo = QBOClient()
    safe = NAME.replace("'", "\\'")
    vdata = qbo.qbo_query(
        f"SELECT * FROM Vendor WHERE DisplayName LIKE '%{safe}%' MAXRESULTS 10")
    vendors = vdata.get("QueryResponse", {}).get("Vendor", [])
    if not vendors:
        print(f"No vendor matching '{NAME}'.")
        return
    for v in vendors:
        vid = v["Id"]
        print(f"\n=== Vendor: {v.get('DisplayName')} (id {vid})  "
              f"Balance={v.get('Balance')} ===")

        bills = qbo.qbo_query(
            f"SELECT * FROM Bill WHERE VendorRef = '{vid}' "
            f"ORDERBY TxnDate DESC MAXRESULTS 50"
        ).get("QueryResponse", {}).get("Bill", [])
        print(f"\n  BILLS ({len(bills)}):")
        for b in bills:
            linked = []
            for ln in b.get("LinkedTxn", []):
                linked.append(f"{ln.get('TxnType')}:{ln.get('TxnId')}")
            print(f"    {b.get('TxnDate')}  doc={str(b.get('DocNumber')):12.12}  "
                  f"total=${b.get('TotalAmt'):>9}  bal=${b.get('Balance'):>9}  "
                  f"linked={linked or '-'}")

        pays = qbo.qbo_query(
            f"SELECT * FROM BillPayment WHERE VendorRef = '{vid}' "
            f"ORDERBY TxnDate DESC MAXRESULTS 50"
        ).get("QueryResponse", {}).get("BillPayment", [])
        print(f"\n  BILL PAYMENTS ({len(pays)}):")
        for p in pays:
            linked = [f"{ln.get('TxnType')}:{ln.get('TxnId')}"
                      for ln in p.get("Line", []) for ln in ln.get("LinkedTxn", [])]
            print(f"    {p.get('TxnDate')}  ${p.get('TotalAmt'):>9}  "
                  f"type={p.get('PayType')}  paysBills={linked or '-'}")

        # Credit-card / cash / check expenses booked directly (not via Bill).
        # Purchase isn't filterable by EntityRef, so pull 2026 and filter here.
        allp = qbo.qbo_query(
            "SELECT * FROM Purchase WHERE TxnDate >= '2025-12-01' "
            "ORDERBY TxnDate DESC MAXRESULTS 1000"
        ).get("QueryResponse", {}).get("Purchase", [])
        purch = [p for p in allp
                 if NAME.lower() in json.dumps(p.get("EntityRef", {})).lower()
                 or NAME.lower() in json.dumps(p).lower()]
        print(f"\n  DIRECT PURCHASES / CC CHARGES mentioning '{NAME}' "
              f"since 2025-12 ({len(purch)} of {len(allp)} scanned):")
        for p in purch:
            ent = (p.get("EntityRef") or {}).get("name")
            print(f"    {p.get('TxnDate')}  ${p.get('TotalAmt'):>9}  "
                  f"paymentType={p.get('PaymentType')}  acct={(p.get('AccountRef') or {}).get('name')}  "
                  f"entity={ent}  doc={p.get('DocNumber')}")

    Path("logs").mkdir(exist_ok=True)
    Path("logs/qbo_vendor_txns.json").write_text(json.dumps({
        "name": NAME, "generated": datetime.now(timezone.utc).isoformat(),
        "vendors": vendors}, indent=2, default=str))
    print("\nWrote logs/qbo_vendor_txns.json")


if __name__ == "__main__":
    main()
