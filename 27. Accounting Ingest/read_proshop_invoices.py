"""Read invoices from ProShop and QuickBooks Online, cross-check by number + total.

ProShop = source of truth for what we billed customers. QBO = what got posted.
Mismatches typically mean: (a) entered manually in QBO with different total, (b)
posted in one system but not the other, (c) typo in invoice number on either side.

Reads only — no writes to either system.

Outputs:
  - Console summary + tables for each mismatch category
  - logs/proshop_qbo_invoice_reconcile.json — full data for follow-up
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
LOG_PATH = Path(__file__).parent / "logs" / "proshop_qbo_invoice_reconcile_30d.json"

PROSHOP_BASE = "https://traxismfg.adionsystems.com"
PROSHOP_BEGIN = f"{PROSHOP_BASE}/api/beginsession"
PROSHOP_GQL = f"{PROSHOP_BASE}/api/graphql"

QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_API_BASE = "https://quickbooks.api.intuit.com/v3/company"  # production only — sandbox would be sandbox-quickbooks.api.intuit.com
QBO_REFRESH_KEY = "QBO_REFRESH_TOKEN"   # production token
QBO_REALM_KEY = "QBO_REALM_ID"          # production realm

WINDOW_DAYS = 30
CUTOFF_DATE = date.today() - timedelta(days=WINDOW_DAYS)  # inclusive lower bound

AMOUNT_TOLERANCE = Decimal("0.01")
PAGE_SIZE = 200


def parse_date(s):
    """Parse YYYY-MM-DD or M/D/YYYY; return None on failure."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s[:len(fmt)+2], fmt).date()
        except ValueError:
            continue
    return None


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


# ---------- ProShop ----------

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
    token = r.json()["authorizationResult"]["token"]
    return token


def proshop_fetch_invoices(token):
    """Page through every invoice. Returns list of dicts."""
    gql = """
    query Invoices($pageSize: Int!, $pageStart: Int!) {
      invoices(pageSize: $pageSize, pageStart: $pageStart) {
        totalRecords
        records {
          invoiceId
          legacyId
          invoicedDollars
          invoiceDate
          invoiceDueDate
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


# ---------- QBO ----------

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
            f"  Using {QBO_REFRESH_KEY}={env.get(QBO_REFRESH_KEY,'')[:12]}...\n"
            f"  If 'invalid_grant', the production refresh token has expired — re-run qbo_auth.py."
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
    chunk = 1000  # QBO max
    cutoff = CUTOFF_DATE.isoformat()
    while True:
        sql = (
            f"SELECT Id, DocNumber, TxnDate, TotalAmt, CustomerRef "
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


# ---------- Reconcile ----------

def norm_invoice_no(s):
    if s is None:
        return ""
    return re.sub(r"\s+", "", str(s)).strip().upper()


def to_decimal(x):
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return None


def reconcile(proshop_invoices, qbo_invoices):
    ps_by_num = {}
    ps_no_num = []
    for inv in proshop_invoices:
        num = norm_invoice_no(inv.get("invoiceId"))
        if not num:
            ps_no_num.append(inv)
            continue
        ps_by_num.setdefault(num, []).append(inv)

    qbo_by_num = {}
    qbo_no_num = []
    for inv in qbo_invoices:
        num = norm_invoice_no(inv.get("DocNumber"))
        if not num:
            qbo_no_num.append(inv)
            continue
        qbo_by_num.setdefault(num, []).append(inv)

    matched_ok, amount_mismatch, proshop_only, qbo_only = [], [], [], []

    for num, ps_list in ps_by_num.items():
        qbo_list = qbo_by_num.get(num)
        ps_total = sum((to_decimal(p.get("invoicedDollars")) or Decimal(0)) for p in ps_list)
        if not qbo_list:
            proshop_only.append({"number": num, "proshop": ps_list, "proshop_total": str(ps_total)})
            continue
        qbo_total = sum((to_decimal(q.get("TotalAmt")) or Decimal(0)) for q in qbo_list)
        diff = (ps_total - qbo_total).copy_abs()
        row = {
            "number": num,
            "proshop": ps_list,
            "qbo": qbo_list,
            "proshop_total": str(ps_total),
            "qbo_total": str(qbo_total),
            "diff": str(diff),
        }
        if diff <= AMOUNT_TOLERANCE:
            matched_ok.append(row)
        else:
            amount_mismatch.append(row)

    for num, qbo_list in qbo_by_num.items():
        if num not in ps_by_num:
            qbo_total = sum((to_decimal(q.get("TotalAmt")) or Decimal(0)) for q in qbo_list)
            qbo_only.append({"number": num, "qbo": qbo_list, "qbo_total": str(qbo_total)})

    return {
        "matched_ok": matched_ok,
        "amount_mismatch": amount_mismatch,
        "proshop_only": proshop_only,
        "qbo_only": qbo_only,
        "proshop_no_number": ps_no_num,
        "qbo_no_number": qbo_no_num,
    }


def print_table(title, rows, columns):
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print("  (none)")
        return
    widths = [max(len(str(c)), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in columns]
    header = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    print(header)
    print("-" * len(header))
    for r in rows[:200]:  # cap console output
        print(" | ".join(str(r.get(c, "")).ljust(w) for c, w in zip(columns, widths)))
    if len(rows) > 200:
        print(f"  ... ({len(rows) - 200} more — see {LOG_PATH.name})")


def main():
    env = load_env()

    print(f"Window: invoices dated >= {CUTOFF_DATE.isoformat()} (last {WINDOW_DAYS} days)")

    print("\nProShop: begin session...")
    ps_token = proshop_begin_session(env)
    print("ProShop: fetching all invoices (filtered client-side — no native date range)...")
    t0 = time.time()
    ps_all = proshop_fetch_invoices(ps_token)
    ps_invoices = [inv for inv in ps_all if (d := parse_date(inv.get("invoiceDate"))) and d >= CUTOFF_DATE]
    print(f"  -> {len(ps_all)} fetched, {len(ps_invoices)} in window ({time.time()-t0:.1f}s)")

    print("\nQBO: refresh token...")
    qbo_token = qbo_refresh(env)
    print(f"QBO: fetching invoices from realm {env[QBO_REALM_KEY]} (server-side WHERE TxnDate >= ...)...")
    t0 = time.time()
    qbo_invoices = qbo_fetch_invoices(env, qbo_token)
    print(f"  -> {len(qbo_invoices)} invoices in {time.time()-t0:.1f}s")

    print("\nReconciling by invoice number + total...")
    result = reconcile(ps_invoices, qbo_invoices)

    print("\n" + "=" * 60)
    print(f"SUMMARY (last {WINDOW_DAYS} days, since {CUTOFF_DATE.isoformat()})")
    print("=" * 60)
    print(f"  ProShop invoices:        {len(ps_invoices)}")
    print(f"  QBO invoices:            {len(qbo_invoices)}")
    print(f"  Matched (number+total):  {len(result['matched_ok'])}")
    print(f"  Amount mismatches:       {len(result['amount_mismatch'])}")
    print(f"  ProShop only:            {len(result['proshop_only'])}")
    print(f"  QBO only:                {len(result['qbo_only'])}")
    print(f"  ProShop blank number:    {len(result['proshop_no_number'])}")
    print(f"  QBO blank number:        {len(result['qbo_no_number'])}")

    print_table("AMOUNT MISMATCHES", result["amount_mismatch"],
                ["number", "proshop_total", "qbo_total", "diff"])
    print_table("PROSHOP ONLY (not in QBO)", result["proshop_only"],
                ["number", "proshop_total"])
    print_table("QBO ONLY (not in ProShop)", result["qbo_only"],
                ["number", "qbo_total"])

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps({
        "window": {"days": WINDOW_DAYS, "cutoff": CUTOFF_DATE.isoformat()},
        "counts": {
            "proshop": len(ps_invoices),
            "qbo": len(qbo_invoices),
            "matched_ok": len(result["matched_ok"]),
            "amount_mismatch": len(result["amount_mismatch"]),
            "proshop_only": len(result["proshop_only"]),
            "qbo_only": len(result["qbo_only"]),
        },
        **result,
    }, indent=2, default=str))
    print(f"\nFull results written to: {LOG_PATH}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP error: {e}\n{e.response.text[:600] if e.response else ''}", file=sys.stderr)
        sys.exit(1)
