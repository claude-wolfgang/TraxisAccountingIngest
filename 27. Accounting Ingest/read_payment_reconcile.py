"""Reconcile QBO payment reality against ProShop's view of who has paid.

Closes the documented visibility gap (proshop_qbo_sync_problem.md): ProShop's
QBO sync is one-way (ProShop → QBO), so when a customer pays a QBO invoice,
ProShop has no idea. Invoices stay marked "Outstanding" in ProShop forever
even after the customer paid weeks ago.

This script flags:
  - QBO says PAID but ProShop says OUTSTANDING — "stop chasing this one"
  - QBO says OWED but ProShop says PAID — unusual; investigate
  - QBO partial payment but ProShop binary status — partials noted

Read-only.

Default window: 180 days (Net 30 customers typically lag 30-60 days; the value
is in finding OLD paid-but-not-flipped invoices, so we go back wider than the
Stage 2 reconciliation).

Output:
  - Console: collections punch list ("QBO paid, ProShop says outstanding") + anomalies
  - logs/payment_reconcile_180d.json — full data
"""

import base64
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

ENV_PATH = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")
LOG_PATH = Path(__file__).parent / "logs" / "payment_reconcile_180d.json"

PROSHOP_BASE = "https://traxismfg.adionsystems.com"
PROSHOP_BEGIN = f"{PROSHOP_BASE}/api/beginsession"
PROSHOP_GQL = f"{PROSHOP_BASE}/api/graphql"

QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_API_BASE = "https://quickbooks.api.intuit.com/v3/company"
QBO_REFRESH_KEY = "QBO_REFRESH_TOKEN"
QBO_REALM_KEY = "QBO_REALM_ID"

WINDOW_DAYS = 180
CUTOFF_DATE = date.today() - timedelta(days=WINDOW_DAYS)

# ProShop invoice status values that mean "still owed"
UNPAID_STATUSES = {"outstanding", "open", "unpaid", "partial"}
# Status values that mean "paid"
PAID_STATUSES = {"paid", "closed", "complete"}

AMOUNT_TOLERANCE = Decimal("0.01")
PAGE_SIZE = 200


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s[:len(fmt)+2], fmt).date()
        except ValueError:
            continue
    return None


def to_decimal(x):
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return None


def norm_invoice_no(s):
    if s is None:
        return ""
    return re.sub(r"\s+", "", str(s)).strip().upper()


def proshop_begin_session(env):
    user = env["PROSHOP_USERNAME"]
    if "@" not in user:
        user = f"{user}@traxismfg.com"
    scope = env["ACCOUNTING_SCOPE"].replace("+", " ")
    r = requests.post(
        PROSHOP_BEGIN,
        headers={"Content-Type": "application/json"},
        json={"username": user, "password": env["PROSHOP_PASSWORD"], "scope": scope},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["authorizationResult"]["token"]


def proshop_fetch_invoices(token):
    gql = """
    query Invoices($pageSize: Int!, $pageStart: Int!) {
      invoices(pageSize: $pageSize, pageStart: $pageStart) {
        totalRecords
        records {
          invoiceId
          invoiceDate
          invoicedDollars
          status
          paymentTerms
          soldToPlainText
          shippedToPlainText
          customerPOPlainText
          proshopUrl
        }
      }
    }
    """
    out = []
    page_start = 0
    while True:
        r = requests.post(
            PROSHOP_GQL,
            params={"token": token},
            headers={"Content-Type": "application/json"},
            json={"query": gql, "variables": {"pageSize": PAGE_SIZE, "pageStart": page_start}},
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"ProShop GraphQL errors: {body['errors']}")
        result = body["data"]["invoices"]
        records = result.get("records") or []
        out.extend(records)
        total = result.get("totalRecords") or 0
        print(f"  ProShop page {page_start}-{page_start+len(records)} of {total}")
        if len(records) < PAGE_SIZE or len(out) >= total:
            break
        page_start += PAGE_SIZE
    return out


def qbo_refresh(env):
    creds = base64.b64encode(
        f"{env['QBO_CLIENT_ID']}:{env['QBO_CLIENT_SECRET']}".encode()
    ).decode()
    r = requests.post(
        QBO_TOKEN_URL,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={"grant_type": "refresh_token", "refresh_token": env[QBO_REFRESH_KEY]},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(
            f"QBO refresh failed {r.status_code}: {r.text[:400]}\n"
            f"  If 'invalid_grant', re-run qbo_auth.py."
        )
    data = r.json()
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != env[QBO_REFRESH_KEY]:
        text = ENV_PATH.read_text()
        text = re.sub(
            rf"^{QBO_REFRESH_KEY}=.*$",
            f"{QBO_REFRESH_KEY}={new_refresh}",
            text,
            flags=re.MULTILINE,
        )
        ENV_PATH.write_text(text)
        env[QBO_REFRESH_KEY] = new_refresh
        print(f"  (rotated {QBO_REFRESH_KEY} in .traxis.env)")
    return data["access_token"]


def qbo_fetch_invoices(env, access_token):
    realm = env[QBO_REALM_KEY]
    url = f"{QBO_API_BASE}/{realm}/query"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    out = []
    start = 1
    chunk = 1000
    cutoff = CUTOFF_DATE.isoformat()
    while True:
        sql = (
            f"SELECT Id, DocNumber, TxnDate, TotalAmt, Balance, CustomerRef, DueDate "
            f"FROM Invoice "
            f"WHERE TxnDate >= '{cutoff}' "
            f"STARTPOSITION {start} MAXRESULTS {chunk}"
        )
        r = requests.get(url, headers=headers, params={"query": sql, "minorversion": "65"}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"QBO error {r.status_code}: {r.text[:400]}")
        qr = r.json().get("QueryResponse", {})
        batch = qr.get("Invoice", []) or []
        out.extend(batch)
        print(f"  QBO page {start}-{start+len(batch)-1} (got {len(batch)})")
        if len(batch) < chunk:
            break
        start += chunk
    return out


def classify_payment_state(ps_status, qbo_balance, qbo_total):
    """Return (drift_type, label).

    drift_type ∈ {STOP_CHASING, UNEXPECTED_OWED, PARTIAL, AGREED, UNKNOWN_STATUS}
    """
    s = (ps_status or "").strip().lower()
    if qbo_balance is None or qbo_total is None:
        return ("UNKNOWN_STATUS", f"ProShop={ps_status!r}, QBO missing balance")
    qbo_paid = qbo_balance <= AMOUNT_TOLERANCE
    qbo_partial = qbo_balance > AMOUNT_TOLERANCE and qbo_balance < qbo_total - AMOUNT_TOLERANCE

    if s in UNPAID_STATUSES:
        if qbo_paid:
            return ("STOP_CHASING", "QBO paid, ProShop says outstanding")
        if qbo_partial:
            return ("PARTIAL", f"QBO partially paid (${qbo_total - qbo_balance}/${qbo_total}); ProShop binary status")
        return ("AGREED", "Both say owed")
    if s in PAID_STATUSES:
        if qbo_paid:
            return ("AGREED", "Both say paid")
        return ("UNEXPECTED_OWED", "ProShop says paid, QBO shows balance owed")
    return ("UNKNOWN_STATUS", f"ProShop status={ps_status!r}; QBO balance=${qbo_balance}")


def reconcile(ps_invoices, qbo_invoices):
    qbo_by_num = {}
    for inv in qbo_invoices:
        num = norm_invoice_no(inv.get("DocNumber"))
        if num:
            qbo_by_num.setdefault(num, []).append(inv)

    results = {"STOP_CHASING": [], "UNEXPECTED_OWED": [], "PARTIAL": [], "AGREED": [], "UNKNOWN_STATUS": [], "NOT_IN_QBO": []}

    for ps in ps_invoices:
        num = norm_invoice_no(ps.get("invoiceId"))
        if not num:
            continue
        qbo_list = qbo_by_num.get(num)
        ps_total = to_decimal(ps.get("invoicedDollars")) or Decimal(0)
        ps_status = ps.get("status") or ""
        inv_date = parse_date(ps.get("invoiceDate"))
        days_old = (date.today() - inv_date).days if inv_date else None
        customer = ps.get("soldToPlainText") or ps.get("shippedToPlainText") or "(blank)"

        if not qbo_list:
            results["NOT_IN_QBO"].append({
                "number": num, "customer": customer, "ps_total": str(ps_total),
                "ps_status": ps_status, "days_old": days_old, "ps_url": ps.get("proshopUrl"),
            })
            continue

        # Take first match (DocNumbers should be unique per realm)
        q = qbo_list[0]
        qbo_total = to_decimal(q.get("TotalAmt"))
        qbo_balance = to_decimal(q.get("Balance"))
        drift, label = classify_payment_state(ps_status, qbo_balance, qbo_total)
        row = {
            "number": num,
            "customer": customer,
            "ps_total": str(ps_total),
            "ps_status": ps_status,
            "qbo_total": str(qbo_total) if qbo_total is not None else None,
            "qbo_balance": str(qbo_balance) if qbo_balance is not None else None,
            "qbo_due_date": q.get("DueDate"),
            "days_old": days_old,
            "label": label,
            "ps_url": ps.get("proshopUrl"),
        }
        results[drift].append(row)

    return results


def print_table(title, rows, columns, sort_key=None):
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print("  (none)")
        return
    if sort_key:
        rows = sorted(rows, key=sort_key)
    widths = [max(len(str(c)), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in columns]
    header = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    print(header)
    print("-" * len(header))
    for r in rows[:200]:
        print(" | ".join(str(r.get(c, "")).ljust(w) for c, w in zip(columns, widths)))
    if len(rows) > 200:
        print(f"  ... ({len(rows) - 200} more — see {LOG_PATH.name})")


def main():
    env = load_env()
    print(f"Window: invoices dated >= {CUTOFF_DATE.isoformat()} (last {WINDOW_DAYS} days)")

    print("\nProShop: begin session...")
    ps_token = proshop_begin_session(env)
    print("ProShop: fetching all invoices...")
    t0 = time.time()
    ps_all = proshop_fetch_invoices(ps_token)
    ps_invoices = [inv for inv in ps_all if (d := parse_date(inv.get("invoiceDate"))) and d >= CUTOFF_DATE]
    print(f"  -> {len(ps_all)} fetched, {len(ps_invoices)} in window ({time.time()-t0:.1f}s)")

    print("\nQBO: refresh token...")
    qbo_token = qbo_refresh(env)
    print(f"QBO: fetching invoices from realm {env[QBO_REALM_KEY]}...")
    t0 = time.time()
    qbo_invoices = qbo_fetch_invoices(env, qbo_token)
    print(f"  -> {len(qbo_invoices)} invoices in {time.time()-t0:.1f}s")

    print("\nReconciling payment status...")
    result = reconcile(ps_invoices, qbo_invoices)

    print("\n" + "=" * 70)
    print(f"PAYMENT RECONCILE — last {WINDOW_DAYS} days (since {CUTOFF_DATE.isoformat()})")
    print("=" * 70)
    print(f"  ProShop invoices in window:   {len(ps_invoices)}")
    print(f"  QBO invoices in window:       {len(qbo_invoices)}")
    print(f"  Agreed (no drift):            {len(result['AGREED'])}")
    print(f"  STOP CHASING (paid in QBO):   {len(result['STOP_CHASING'])}")
    print(f"  Partial in QBO:               {len(result['PARTIAL'])}")
    print(f"  Unexpected owed in QBO:       {len(result['UNEXPECTED_OWED'])}")
    print(f"  Not in QBO (gap):             {len(result['NOT_IN_QBO'])}")
    print(f"  Unknown ProShop status:       {len(result['UNKNOWN_STATUS'])}")

    cols = ["number", "customer", "ps_status", "qbo_balance", "ps_total", "days_old", "ps_url"]
    print_table(
        "STOP CHASING — QBO says paid, ProShop says outstanding",
        result["STOP_CHASING"], cols, sort_key=lambda r: -(r["days_old"] or 0),
    )
    print_table(
        "PARTIAL — QBO partially paid",
        result["PARTIAL"], cols, sort_key=lambda r: -(r["days_old"] or 0),
    )
    print_table(
        "UNEXPECTED OWED — ProShop says paid, QBO shows balance",
        result["UNEXPECTED_OWED"], cols,
    )
    print_table(
        "UNKNOWN ProShop status",
        result["UNKNOWN_STATUS"], cols,
    )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps({
        "window": {"days": WINDOW_DAYS, "cutoff": CUTOFF_DATE.isoformat()},
        "counts": {k: len(v) for k, v in result.items()},
        "results": result,
    }, indent=2, default=str))
    print(f"\nFull results written to: {LOG_PATH}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        body = e.response.text[:600] if e.response else ""
        print(f"HTTP error: {e}\n{body}", file=sys.stderr)
        sys.exit(1)
