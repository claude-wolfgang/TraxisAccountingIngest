"""
Probe Sent Items in M365 to discover VPO email patterns.

One-shot diagnostic: scans the last 365 days of Sent Items for messages
that look like outgoing VPOs (has attachments, subject mentions VPO/PO,
or attachment named like a VPO PDF). Prints what it finds so we can
design the bootstrap script's actual filter.

Run from anywhere on a PC with .traxis.env reachable.
"""

import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
USERPROFILE = Path(os.environ.get("USERPROFILE", ""))

ENV_PATHS = [
    PROJECT_ROOT / "1. Proshop Automations" / ".traxis.env",
    USERPROFILE / ".traxis.env",
    USERPROFILE / "Dropbox" / "MACHINE COMM Traxis" / "Keys" / ".traxis.env",
]

MAILBOX = "rene@traxismfg.com"
DAYS_BACK = 1095  # 3 years

# Reliable VPO marker: ProShop names PO PDFs `{6digits}_ Purchase Order.pdf`
VPO_PDF_RE = re.compile(r"^(\d{4,7})_?\s*Purchase Order\.pdf$", re.I)

# Excluded recipients (not re-order vendors)
EXCLUDE_DOMAINS = {"traxismfg.com"}                     # internal forwards
EXCLUDE_ADDRESSES = {"flaggerp512@gmail.com"}           # Sam (P3 contractor)
EXCLUDE_SUBJECT_RE = re.compile(r"\bTesla\b", re.I)     # forwarded customer POs
SENT_FOLDER_URL = (
    "https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/SentItems/messages"
)


def load_env():
    for p in ENV_PATHS:
        if p.exists():
            env = {}
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            return env
    sys.exit("ERROR: .traxis.env not found at known paths")


def get_token(env):
    url = f"https://login.microsoftonline.com/{env['GRAPH_TENANT_ID']}/oauth2/v2.0/token"
    r = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": env["GRAPH_CLIENT_ID"],
        "client_secret": env["GRAPH_CLIENT_SECRET"],
        "scope": "https://graph.microsoft.com/.default",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def list_sent_with_attachments(token, mailbox, since_iso):
    url = SENT_FOLDER_URL.format(mailbox=mailbox)
    params = {
        "$filter": f"sentDateTime ge {since_iso} and hasAttachments eq true",
        "$select": "id,subject,toRecipients,sentDateTime,bodyPreview",
        "$top": "100",
        "$orderby": "sentDateTime desc",
    }
    headers = {"Authorization": f"Bearer {token}"}
    out = []
    while url:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None
    return out


def list_attachments(token, mailbox, msg_id):
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{msg_id}/attachments"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     params={"$select": "name,contentType,size"})
    r.raise_for_status()
    return r.json().get("value", [])


def main():
    env = load_env()
    token = get_token(env)
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).isoformat().replace("+00:00", "Z")

    print(f"Scanning {MAILBOX} Sent Items since {since}...")
    msgs = list_sent_with_attachments(token, MAILBOX, since)
    print(f"  found {len(msgs)} sent messages with attachments\n")

    # Filter by attachment-name match (definitive ProShop VPO signature)
    matches = []   # (msg, vpo_number, vpo_attachment_name)
    skipped_excluded = 0
    skipped_no_vpo = 0
    for m in msgs:
        atts = list_attachments(token, MAILBOX, m["id"])
        vpo_hit = None
        for a in atts:
            mres = VPO_PDF_RE.match(a.get("name", "").strip())
            if mres:
                vpo_hit = (mres.group(1), a["name"])
                break
        if not vpo_hit:
            skipped_no_vpo += 1
            continue
        subj = m.get("subject") or ""
        if EXCLUDE_SUBJECT_RE.search(subj):
            skipped_excluded += 1
            continue
        tos = [r.get("emailAddress", {}).get("address", "").lower()
               for r in m.get("toRecipients", []) if r.get("emailAddress", {}).get("address")]
        # If every recipient is excluded, skip
        kept_tos = []
        for t in tos:
            domain = t.split("@", 1)[1] if "@" in t else ""
            if t in EXCLUDE_ADDRESSES or domain in EXCLUDE_DOMAINS:
                continue
            kept_tos.append(t)
        if not kept_tos:
            skipped_excluded += 1
            continue
        matches.append((m, vpo_hit[0], vpo_hit[1], kept_tos))

    print(f"Filter results:")
    print(f"  matched VPO-PDF naming pattern: {len(matches) + skipped_excluded}")
    print(f"  excluded (Tesla / @traxismfg / Sam):   {skipped_excluded}")
    print(f"  kept as real vendor VPOs:              {len(matches)}")
    print(f"  no VPO PDF attached:                   {skipped_no_vpo}\n")

    # Sample print
    print("=" * 80)
    print(f"SAMPLE (first 25 of {len(matches)} kept matches, newest first):")
    print("=" * 80)
    for m, vpo_num, vpo_name, tos in matches[:25]:
        sent = m.get("sentDateTime", "")[:10]
        subj = m.get("subject") or "(no subject)"
        print(f"\n[{sent}] PO {vpo_num} -> {', '.join(tos)}")
        print(f"  subj: {subj[:80]}")

    # Vendor map preview: domain -> most-recent address + count
    print("\n" + "=" * 80)
    print("VENDOR MAP PREVIEW (grouped by domain):")
    print("=" * 80)
    domain_data = defaultdict(lambda: {"count": 0, "addresses": Counter(), "latest_date": "", "latest_addr": ""})
    for m, vpo_num, vpo_name, tos in matches:
        sent = m.get("sentDateTime", "")[:10]
        for t in tos:
            domain = t.split("@", 1)[1] if "@" in t else "(no-domain)"
            d = domain_data[domain]
            d["count"] += 1
            d["addresses"][t] += 1
            if sent > d["latest_date"]:
                d["latest_date"] = sent
                d["latest_addr"] = t

    print(f"\n{'count':>5} {'last sent':<12} {'most-recent addr':<40} other addresses")
    print("-" * 100)
    for domain, d in sorted(domain_data.items(), key=lambda kv: -kv[1]["count"]):
        others = [f"{a}({n})" for a, n in d["addresses"].most_common() if a != d["latest_addr"]]
        others_str = ", ".join(others) if others else ""
        print(f"{d['count']:5d} {d['latest_date']:<12} {d['latest_addr']:<40} {others_str}")


if __name__ == "__main__":
    main()
