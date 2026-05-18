"""Back-feed WorkOrder Shipped -> Invoiced when QBO confirms the invoice landed.

The forward mechanism for the documented one-way Web Connector gap
(proshop_qbo_sync_problem.md). ProShop creates invoices and pushes to QBO,
but doesn't always flip the source WO from Shipped -> Invoiced. This script
detects the gap and closes it, only when QBO confirms the invoice is real.

Algorithm:
  1. Pull all WOs with status="Shipped"
  2. Pull all PackingSlips with itemsShipped.workOrderPlainText + invoicePlainText
  3. Build map: workOrderNumber -> set of invoicePlainText values from its slips
  4. Pull all QBO Invoice.DocNumber values (within --qbo-window-days)
  5. For each stuck WO:
       - If no slip linkage -> skip (WO might not be ready for invoicing yet)
       - If linked slips have blank invoicePlainText -> skip (no ProShop invoice exists)
       - If linked invoices not in QBO -> skip (Web Connector hasn't pushed yet)
       - Else: candidate for flip
  6. In --apply mode, mutate WorkOrder.status to "Invoiced" via updateWorkOrder
     under basic auth. Audit each event to logs/proshop_wo_flip.log.

Dry-run by default. Use --apply to actually write.

CLI:
  python flip_wo_invoiced_from_qbo.py                    # dry-run, all customers
  python flip_wo_invoiced_from_qbo.py --apply            # actually flip
  python flip_wo_invoiced_from_qbo.py --customer R2S1    # restrict to one customer
  python flip_wo_invoiced_from_qbo.py --qbo-window-days 730  # widen QBO lookback
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import requests

# Telegram alerting — same env var convention as P1 Overseer (set as system env vars on the host)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(text):
    """Best-effort Telegram alert. Silent if creds missing."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        return True
    except Exception as e:
        print(f"  (Telegram send failed: {e})", file=sys.stderr)
        return False

# Derive ENV_PATH from script location so this works on .178 (Superuser), .71 (TRAXIS, D:\Dropbox),
# and srv-01 post-cutover. The .traxis.env always lives at <projects>/1. Proshop Automations/.traxis.env
# regardless of which Dropbox root the host uses.
ENV_PATH = Path(__file__).resolve().parent.parent / "1. Proshop Automations" / ".traxis.env"
AUDIT_LOG = Path(__file__).parent / "logs" / "proshop_wo_flip.log"

PROSHOP_BASE = "https://traxismfg.adionsystems.com"
PROSHOP_BEGIN = f"{PROSHOP_BASE}/api/beginsession"
PROSHOP_GQL = f"{PROSHOP_BASE}/api/graphql"

QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_API_BASE = "https://quickbooks.api.intuit.com/v3/company"
QBO_REFRESH_KEY = "QBO_REFRESH_TOKEN"
QBO_REALM_KEY = "QBO_REALM_ID"

PAGE_SIZE = 200


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def norm_inv_no(s):
    if s is None:
        return ""
    return re.sub(r"\s+", "", str(s)).strip().upper()


# ---------- ProShop ----------

def proshop_session(env):
    user = env["PROSHOP_USERNAME"]
    if "@" not in user:
        user = f"{user}@traxismfg.com"
    scope = env["ACCOUNTING_SCOPE"].replace("+", " ")
    if "workorders" not in scope:
        raise RuntimeError("ACCOUNTING_SCOPE missing 'workorders' permission — add 'workorders:rwdp' to .traxis.env")
    r = requests.post(
        PROSHOP_BEGIN,
        headers={"Content-Type": "application/json"},
        json={"username": user, "password": env["PROSHOP_PASSWORD"], "scope": scope},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["authorizationResult"]["token"]


def fetch_stuck_wos(token):
    """Return list of WOs with status='Shipped'."""
    gql = """
    query StuckWOs($pageSize: Int!, $pageStart: Int!) {
      workOrders(filter: {status: ["Shipped"]}, pageSize: $pageSize, pageStart: $pageStart) {
        totalRecords
        records { status partPlainText proshopUrl dateShipped }
      }
    }
    """
    out = []
    start = 0
    while True:
        r = requests.post(PROSHOP_GQL, params={"token": token},
                          json={"query": gql, "variables": {"pageSize": PAGE_SIZE, "pageStart": start}},
                          timeout=60)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"ProShop errors: {body['errors']}")
        recs = body["data"]["workOrders"]["records"] or []
        out.extend(recs)
        if len(recs) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    # workOrderNumber isn't a directly readable field; extract from proshopUrl
    for rec in out:
        url = rec.get("proshopUrl") or ""
        rec["workOrderNumber"] = url.rstrip("/").rsplit("/", 1)[-1] if url else None
    return out


def build_wo_to_invoices_map(token):
    """Scan all packing slips. Returns {workOrderNumber: set(invoicePlainText)}."""
    gql = """
    query Slips($pageSize: Int!, $pageStart: Int!) {
      packingSlips(pageSize: $pageSize, pageStart: $pageStart) {
        totalRecords
        records {
          id
          invoicePlainText
          itemsShipped(pageSize: 100, pageStart: 0) {
            records { workOrderPlainText }
          }
        }
      }
    }
    """
    mapping = {}
    start = 0
    total = None
    while True:
        r = requests.post(PROSHOP_GQL, params={"token": token},
                          json={"query": gql, "variables": {"pageSize": PAGE_SIZE, "pageStart": start}},
                          timeout=60)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"ProShop errors: {body['errors']}")
        result = body["data"]["packingSlips"]
        recs = result.get("records") or []
        total = result.get("totalRecords") or 0
        inv_no = ""
        for slip in recs:
            inv_no = (slip.get("invoicePlainText") or "").strip()
            items = (slip.get("itemsShipped") or {}).get("records") or []
            for it in items:
                wo = (it.get("workOrderPlainText") or "").strip()
                if wo:
                    mapping.setdefault(wo, set()).add(inv_no)
        print(f"  Slips {start}-{start+len(recs)} of {total}")
        if len(recs) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return mapping


def flip_wo(token, wo_num):
    """Mutate WorkOrder.status to 'Invoiced'. Returns new status or raises."""
    m = 'mutation { updateWorkOrder(workOrderNumber: "' + wo_num + '", data: {status: "Invoiced"}) { status } }'
    r = requests.post(PROSHOP_GQL, params={"token": token}, json={"query": m}, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"updateWorkOrder errors: {body['errors']}")
    return body.get("data", {}).get("updateWorkOrder", {}).get("status")


# ---------- QBO ----------

def qbo_refresh(env):
    creds = base64.b64encode(f"{env['QBO_CLIENT_ID']}:{env['QBO_CLIENT_SECRET']}".encode()).decode()
    r = requests.post(QBO_TOKEN_URL, headers={
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }, data={"grant_type": "refresh_token", "refresh_token": env[QBO_REFRESH_KEY]}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"QBO refresh failed {r.status_code}: {r.text[:400]}\nRe-run qbo_auth.py if 'invalid_grant'.")
    data = r.json()
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != env[QBO_REFRESH_KEY]:
        text = ENV_PATH.read_text()
        text = re.sub(rf"^{QBO_REFRESH_KEY}=.*$", f"{QBO_REFRESH_KEY}={new_refresh}", text, flags=re.MULTILINE)
        ENV_PATH.write_text(text)
        env[QBO_REFRESH_KEY] = new_refresh
        print(f"  (rotated {QBO_REFRESH_KEY} in .traxis.env)")
    return data["access_token"]


def fetch_qbo_doc_numbers(env, token, window_days):
    """Return set of normalized DocNumber strings within window."""
    realm = env[QBO_REALM_KEY]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    out = set()
    start = 1
    chunk = 1000
    while True:
        sql = (f"SELECT Id, DocNumber FROM Invoice "
               f"WHERE TxnDate >= '{cutoff}' "
               f"STARTPOSITION {start} MAXRESULTS {chunk}")
        r = requests.get(f"{QBO_API_BASE}/{realm}/query", headers=headers,
                         params={"query": sql, "minorversion": "65"}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"QBO error {r.status_code}: {r.text[:400]}")
        batch = r.json().get("QueryResponse", {}).get("Invoice", []) or []
        for inv in batch:
            n = norm_inv_no(inv.get("DocNumber"))
            if n:
                out.add(n)
        print(f"  QBO invoices {start}-{start+len(batch)-1}")
        if len(batch) < chunk:
            break
        start += chunk
    return out


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="Actually mutate ProShop (default: dry-run)")
    ap.add_argument("--customer", metavar="CODE",
                    help="Restrict to one customer (matches part prefix, e.g. R2S1)")
    ap.add_argument("--qbo-window-days", type=int, default=365,
                    help="How far back to fetch QBO invoices (default: 365)")
    ap.add_argument("--test-telegram", action="store_true",
                    help="Send a test Telegram message and exit (verifies the alert channel)")
    args = ap.parse_args()

    if args.test_telegram:
        import socket
        msg = f"[P27 WO Flip] test message from {socket.gethostname()} at {datetime.now().isoformat(timespec='seconds')}"
        if send_telegram(msg):
            print(f"OK: sent test message: {msg}")
            return
        print("FAIL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment, or request failed.")
        sys.exit(1)

    env = load_env()
    mode = "APPLY (will mutate)" if args.apply else "DRY-RUN (read only)"
    cust_filter = f"customer={args.customer}" if args.customer else "all customers"
    print(f"Mode: {mode}  |  Filter: {cust_filter}  |  QBO window: {args.qbo_window_days}d")

    print("\nProShop: begin session...")
    ps_token = proshop_session(env)

    print("ProShop: pulling WOs with status=Shipped...")
    stuck = fetch_stuck_wos(ps_token)
    print(f"  -> {len(stuck)} stuck WOs")

    if args.customer:
        stuck = [w for w in stuck if (w.get("partPlainText") or "").startswith(args.customer)]
        print(f"  -> {len(stuck)} after --customer={args.customer} filter")

    if not stuck:
        print("Nothing stuck. Exiting.")
        return

    print("\nProShop: scanning all PackingSlips for WO -> invoice links...")
    wo_to_invs = build_wo_to_invoices_map(ps_token)
    print(f"  -> {len(wo_to_invs)} WOs found in packing slips")

    print("\nQBO: refresh token + fetch DocNumbers...")
    qbo_token = qbo_refresh(env)
    qbo_doc_nums = fetch_qbo_doc_numbers(env, qbo_token, args.qbo_window_days)
    print(f"  -> {len(qbo_doc_nums)} QBO invoices in window")

    print("\n" + "=" * 72)
    print(f"DECISIONS  (n={len(stuck)} stuck WOs)")
    print("=" * 72)

    flip, skip_no_slip, skip_no_invoice, skip_not_in_qbo = [], [], [], []
    for wo in stuck:
        wn = wo["workOrderNumber"]
        part = wo.get("partPlainText") or "?"
        invs = wo_to_invs.get(wn, set())
        ps_invs = {norm_inv_no(i) for i in invs if i}
        if not invs:
            skip_no_slip.append(wo)
            print(f"  SKIP  {wn:10s} {part:30s} no packing slip references this WO")
            continue
        if not ps_invs:
            skip_no_invoice.append(wo)
            print(f"  SKIP  {wn:10s} {part:30s} slip exists but invoicePlainText blank (not invoiced in ProShop)")
            continue
        in_qbo = ps_invs & qbo_doc_nums
        if not in_qbo:
            skip_not_in_qbo.append((wo, ps_invs))
            print(f"  SKIP  {wn:10s} {part:30s} ProShop inv {sorted(ps_invs)} but not in QBO yet")
            continue
        flip.append((wo, in_qbo))
        print(f"  FLIP  {wn:10s} {part:30s} -> QBO inv {sorted(in_qbo)}")

    print("\n" + "=" * 72)
    print(f"SUMMARY  flip={len(flip)}  skip-no-slip={len(skip_no_slip)}  skip-no-invoice={len(skip_no_invoice)}  skip-not-in-qbo={len(skip_not_in_qbo)}")
    print("=" * 72)

    if not flip:
        print("\nNothing to flip. Done.")
        return

    if not args.apply:
        print(f"\nDRY-RUN: {len(flip)} WOs would be flipped. Re-run with --apply to mutate.")
        return

    print(f"\nAPPLYING {len(flip)} flips...")
    AUDIT_LOG.parent.mkdir(exist_ok=True)
    succ, fail = [], []
    for wo, qbo_invs in flip:
        wn = wo["workOrderNumber"]
        part = wo.get("partPlainText") or ""
        try:
            new_status = flip_wo(ps_token, wn)
            if new_status != "Invoiced":
                fail.append((wn, f"unexpected status: {new_status}"))
                print(f"  FAIL  {wn}: status={new_status}")
                continue
            succ.append(wn)
            print(f"  OK    {wn}: Shipped -> Invoiced  (matched QBO inv {sorted(qbo_invs)})")
            with AUDIT_LOG.open("a", encoding="utf-8") as f:
                ts = datetime.now(timezone.utc).isoformat()
                f.write(f"{ts}\tWO_STATUS_FLIP_AUTO\t{wn}\t{part}\tShipped\tInvoiced\tqbo_invs={','.join(sorted(qbo_invs))}\n")
            time.sleep(0.2)
        except Exception as e:
            fail.append((wn, str(e)[:120]))
            print(f"  FAIL  {wn}: {e}")

    print(f"\nApply complete: {len(succ)} flipped, {len(fail)} failed")
    if fail:
        for wn, reason in fail:
            print(f"  FAIL {wn}: {reason}")

    # Telegram alert — only ping when something actually changed
    if succ or fail:
        lines = [f"[P27 WO Flip] {len(succ)} WOs Shipped->Invoiced"]
        for wn in succ:
            lines.append(f"  ok  {wn}")
        for wn, reason in fail:
            lines.append(f"  FAIL {wn}: {reason[:80]}")
        if send_telegram("\n".join(lines)):
            print("  (Telegram alert sent)")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        body = e.response.text[:600] if e.response else ""
        print(f"HTTP error: {e}\n{body}", file=sys.stderr)
        sys.exit(1)
