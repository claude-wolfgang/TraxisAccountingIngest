"""
Chrome Web Store Ops Watcher (P34)

Polls a Microsoft 365 mailbox via Graph API for CWS lifecycle event emails
(submissions, policy notices, suspensions, deprecations), classifies them,
and logs to SQLite with flag files for high-priority events.

Monitors the Traxis Chrome extension fleet:
  - P30 Label Printer (live)
  - P14 Workstation Display (upcoming)
  - P18 Message Notifier (upcoming)

Usage:
  python cws_watcher.py [--mailbox tom@traxismfg.com] [--since 2026-01-01]
                        [--print-only] [-v]
"""

import argparse
import html
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "cws_events.db"
FLAGS_DIR = SCRIPT_DIR / "flags"
HEARTBEAT_PATH = SCRIPT_DIR / "last_run.json"

ENV_PATHS = [
    Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env"),
    Path(r"C:\Users\TRAXIS\.traxis.env"),
]

CWS_SENDERS = [
    "chromewebstore-noreply@google.com",
    "chrome-store-policy@google.com",
]

GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/users/{mailbox}/messages"


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


# ── Graph client (thin, app-only auth — same shape as P27) ────────────────

class GraphClient:
    def __init__(self, env):
        self.env = env
        self.token = None
        self.expires_at = 0

    def _token(self):
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        url = GRAPH_TOKEN_URL.format(tenant_id=self.env["GRAPH_TENANT_ID"])
        r = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": self.env["GRAPH_CLIENT_ID"],
            "client_secret": self.env["GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        })
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data.get("expires_in", 3600)
        return self.token

    def _headers(self):
        return {"Authorization": f"Bearer {self._token()}"}

    def list_messages(self, mailbox, since_iso):
        url = GRAPH_MESSAGES_URL.format(mailbox=mailbox)
        params = {
            "$filter": f"receivedDateTime ge {since_iso}",
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
            "$top": "100",
            "$orderby": "receivedDateTime desc",
        }
        all_msgs = []
        while url:
            r = requests.get(url, headers=self._headers(), params=params)
            r.raise_for_status()
            data = r.json()
            all_msgs.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = None
        return all_msgs

    def get_body(self, mailbox, msg_id):
        url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{msg_id}"
        r = requests.get(url, headers=self._headers(), params={"$select": "body"})
        r.raise_for_status()
        body = r.json().get("body", {})
        return body.get("content", ""), body.get("contentType", "text")


# ── Classifier ────────────────────────────────────────────────────────────

# Order matters — first match wins. Priority: critical > high > low > info.
CLASSIFICATION_RULES = [
    ("critical", "suspension",            r"suspend|takedown|removed from"),
    ("high",     "submission_rejected",   r"reject"),
    ("high",     "deprecation",           r"deprecat|discontinued|no longer support"),
    ("high",     "policy_notice",         r"policy|deadline|required by|action required|must update"),
    ("low",      "submission_approved",   r"approv|published|now live"),
    ("low",      "install_report",        r"usage report|install report|monthly summary"),
]


def classify(subject, body_excerpt):
    s = (subject or "").lower()
    b = (body_excerpt or "").lower()
    for priority, kind, pattern in CLASSIFICATION_RULES:
        if re.search(pattern, s) or re.search(pattern, b):
            return priority, kind
    return "info", "other"


# ── DB ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS cws_events (
    message_id     TEXT PRIMARY KEY,
    received_at    TEXT NOT NULL,
    sender         TEXT NOT NULL,
    subject        TEXT,
    body_excerpt   TEXT,
    classification TEXT NOT NULL,
    priority       TEXT NOT NULL,
    raw_json       TEXT,
    processed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cws_priority ON cws_events(priority, received_at);
"""


def db_open():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    return con


def db_insert_event(con, ev):
    before = con.total_changes
    con.execute(
        "INSERT OR IGNORE INTO cws_events "
        "(message_id, received_at, sender, subject, body_excerpt, classification, priority, raw_json, processed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (ev["message_id"], ev["received_at"], ev["sender"], ev["subject"],
         ev["body_excerpt"], ev["classification"], ev["priority"],
         json.dumps(ev["raw"]), datetime.now(timezone.utc).isoformat())
    )
    return con.total_changes > before


# ── Flag files (Overseer pickup) ──────────────────────────────────────────

def write_heartbeat(stats):
    """Write last_run.json so Overseer (P1) can read freshness + counts."""
    payload = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        **stats,
    }
    HEARTBEAT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_flag(ev):
    if ev["priority"] not in ("high", "critical"):
        return
    FLAGS_DIR.mkdir(exist_ok=True)
    fname = f"cws_{ev['received_at'][:10]}_{ev['priority']}_{ev['message_id'][:8]}.flag"
    summary = (
        f"[{ev['priority'].upper()}] {ev['classification']}\n"
        f"From: {ev['sender']}\n"
        f"Received: {ev['received_at']}\n"
        f"Subject: {ev['subject']}\n\n"
        f"{ev['body_excerpt'][:300]}\n"
    )
    (FLAGS_DIR / fname).write_text(summary, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────

def is_cws_sender(addr):
    return addr.lower() in [s.lower() for s in CWS_SENDERS]


def html_to_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mailbox", default=None, help="M365 mailbox to query (default tom@traxismfg.com)")
    ap.add_argument("--since", default=None, help="ISO date or datetime; default 90 days ago")
    ap.add_argument("--print-only", action="store_true", help="Don't write DB or flags; print results")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    env = load_env()
    mailbox = args.mailbox or env.get("CWS_WATCHER_MAILBOX") or "tom@traxismfg.com"
    since_iso = args.since or (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
    if "T" not in since_iso:
        since_iso = since_iso + "T00:00:00Z"

    print(f"CWS Watcher — mailbox={mailbox}  since={since_iso}  print_only={args.print_only}")

    gc = GraphClient(env)
    msgs = gc.list_messages(mailbox, since_iso)
    cws_msgs = [m for m in msgs
                if is_cws_sender(m.get("from", {}).get("emailAddress", {}).get("address", ""))]
    print(f"  fetched {len(msgs)} total, {len(cws_msgs)} from CWS senders")

    stats = {
        "mailbox": mailbox,
        "since": since_iso,
        "total_messages_seen": len(msgs),
        "cws_messages_seen": len(cws_msgs),
        "new_events": 0,
        "high_priority_count": 0,
        "critical_priority_count": 0,
    }

    if not cws_msgs:
        if not args.print_only:
            write_heartbeat(stats)
        return 0

    con = None if args.print_only else db_open()
    new_count = 0
    for m in cws_msgs:
        full_body, _ = gc.get_body(mailbox, m["id"])
        body_text = html_to_text(full_body)[:2000]
        priority, kind = classify(m.get("subject", ""), body_text)
        ev = {
            "message_id": m["id"],
            "received_at": m["receivedDateTime"],
            "sender": m["from"]["emailAddress"]["address"],
            "subject": m.get("subject", ""),
            "body_excerpt": body_text[:500],
            "classification": kind,
            "priority": priority,
            "raw": m,
        }
        if args.print_only:
            print(f"  [{priority}] {kind}  {ev['received_at']}  {ev['subject'][:80]}")
            if args.verbose:
                print(f"      body: {body_text[:300]}\n")
        else:
            inserted = db_insert_event(con, ev)
            tag = "NEW " if inserted else "dup "
            print(f"  {tag}[{priority}] {kind}  {ev['received_at']}  {ev['subject'][:80]}")
            if inserted:
                new_count += 1
                write_flag(ev)

    if con:
        con.commit()
        con.close()
        print(f"\n  {new_count} new event(s) logged to {DB_PATH.name}")

    if not args.print_only:
        # Count current open high/critical flag files (post-run state)
        if FLAGS_DIR.exists():
            stats["high_priority_count"] = len(list(FLAGS_DIR.glob("*_high_*.flag")))
            stats["critical_priority_count"] = len(list(FLAGS_DIR.glob("*_critical_*.flag")))
        stats["new_events"] = new_count
        write_heartbeat(stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())
