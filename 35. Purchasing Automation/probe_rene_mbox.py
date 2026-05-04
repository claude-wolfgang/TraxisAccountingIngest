"""
Probe Rene's archived Inbox mbox for vendor email signatures.

Sample-mode (default): scans first 5000 messages, fast.
Full-mode (--full):    scans every message in the file (~50-100k+, slow).

Vendor signal heuristic:
  - From: address is NOT @traxismfg.com
  - AND Subject matches purchasing keywords (PO, quote, RFQ, order, invoice,
    shipment, tracking, confirmation) OR has obvious PDF-attached marker

Aggregates by sender domain → most-recent address, hit count, last-seen date.
"""

import argparse
import mailbox
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

MBOX_PATH = Path(
    r"C:\Users\Superuser\Dropbox\OPERATIONS Traxis\EMPLOYEES"
    r"\Rene Maldonado Email Files\rene@traxismfg.com"
    r"\rene@traxismfg.com.sbd\Inbox"
)

PURCHASING_KEYWORDS = re.compile(
    r"\b(PO|P\.?O\.?|purchase\s*order|quote|RFQ|order|shipment|tracking|"
    r"invoice|confirmation|acknowledg|ship\s*notice|packing\s*list)\b",
    re.IGNORECASE,
)

# Things that scream "not a vendor"
EXCLUDE_DOMAINS = {
    "traxismfg.com",         # internal
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "aol.com", "icloud.com", "msn.com",  # personal mail providers
    "google.com",            # noreply / notifications
    "amazon.com",            # AWS / shopping noise (we'll add back if there's signal)
    "linkedin.com", "facebook.com", "twitter.com",
    "ups.com", "fedex.com", "usps.com",  # shipping notifications, not vendors
    "intuit.com", "quickbooks.com", "notification.intuit.com",  # QBO noise
    "microsoft.com", "office365.com", "onmicrosoft.com",
    "adobe.com", "dropbox.com", "github.com",
    "zoom.us", "calendly.com",
    "anthropic.com", "openai.com",
    "freightquote.com",      # shipping booking noise
    # Known Traxis customers (Traxis is the vendor for these)
    "tesla.com", "r2sonic.com",
    "arlut.utexas.edu", "engr.utexas.edu", "utexas.edu",
    "infineon.com", "brightmachines.com", "aiworldwide.com",
    "varian.com", "cellingbiosciences.com", "lyndallbrakes.com",
    "nikotrack.com", "crippensheetmetal.com", "eos-na.com",
    "livesoda.com", "vitech-us.com", "warbach.com",
    # Ambiguous, treating as non-vendor for bootstrap (Wolfgang can promote later)
    "escobedogroup.com", "fractalems.com", "moonlitmfg.com",
    "noveon.co", "austinpump.com", "atonometrics.com",
    "centerline-inc.com", "komico.com",
}

# Patterns that suggest no-reply or system address
NOREPLY_RE = re.compile(r"(no.?reply|do.?not.?reply|notifications?@|alerts?@|mailer-daemon)", re.I)


def domain_of(addr):
    addr = (addr or "").lower().strip()
    if "@" not in addr:
        return ""
    return addr.split("@", 1)[1].rstrip(">")


def parse_date(raw):
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    # Normalize to naive UTC so all dates are comparable
    if d.tzinfo is not None:
        d = d.astimezone(tz=None).replace(tzinfo=None)
    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="scan entire mbox")
    parser.add_argument("--sample", type=int, default=5000, help="sample size (default 5000)")
    args = parser.parse_args()

    if not MBOX_PATH.exists():
        sys.exit(f"ERROR: mbox not found at {MBOX_PATH}")

    print(f"Opening mbox: {MBOX_PATH}")
    print(f"  size: {MBOX_PATH.stat().st_size / 1e9:.2f} GB")
    print(f"  mode: {'FULL SCAN' if args.full else f'SAMPLE first {args.sample}'}\n")

    mb = mailbox.mbox(str(MBOX_PATH), create=False)

    total = 0
    purchasing_hits = 0
    no_from = 0
    excluded = 0
    by_domain = defaultdict(lambda: {
        "count": 0,
        "addresses": Counter(),
        "latest_date": None,
        "latest_addr": "",
        "subjects": []
    })

    limit = None if args.full else args.sample

    for key, msg in mb.iteritems():
        total += 1
        if limit and total > limit:
            break
        if total % 1000 == 0:
            print(f"  scanned {total} messages, {purchasing_hits} purchasing-shaped...")

        from_raw = msg.get("From", "")
        if not from_raw:
            no_from += 1
            continue
        addrs = getaddresses([from_raw])
        if not addrs:
            no_from += 1
            continue
        sender = addrs[0][1].lower()
        domain = domain_of(sender)
        if not domain:
            no_from += 1
            continue
        if domain in EXCLUDE_DOMAINS or NOREPLY_RE.search(sender):
            excluded += 1
            continue

        subject = msg.get("Subject", "") or ""
        if not PURCHASING_KEYWORDS.search(subject):
            continue

        purchasing_hits += 1
        date = parse_date(msg.get("Date"))

        d = by_domain[domain]
        d["count"] += 1
        d["addresses"][sender] += 1
        if date and (d["latest_date"] is None or date > d["latest_date"]):
            d["latest_date"] = date
            d["latest_addr"] = sender
        if len(d["subjects"]) < 3:
            d["subjects"].append((date, subject[:80]))

    print(f"\nDone. scanned={total}, purchasing-shaped={purchasing_hits}, "
          f"excluded={excluded}, no-from={no_from}\n")

    print("=" * 100)
    print(f"TOP VENDOR DOMAINS (sorted by hit count, top 50):")
    print("=" * 100)
    print(f"\n{'count':>5}  {'last seen':<12}  {'most-recent addr':<45}  sample subject")
    print("-" * 100)
    for domain, d in sorted(by_domain.items(), key=lambda kv: -kv[1]["count"])[:50]:
        last = d["latest_date"].strftime("%Y-%m-%d") if d["latest_date"] else "?"
        sample_subj = d["subjects"][0][1] if d["subjects"] else ""
        print(f"{d['count']:5d}  {last:<12}  {d['latest_addr']:<45}  {sample_subj}")


if __name__ == "__main__":
    main()
