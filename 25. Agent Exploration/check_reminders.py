"""
Check for due reminders and send them via Telegram.
Designed to run on Windows Task Scheduler every 15 minutes.

Usage:
    python check_reminders.py          # Check and send due reminders
    python check_reminders.py --list   # Show all pending reminders
"""

import sys

import config
from audit_db import AuditDB


def send_telegram(text):
    """Send a message via the configured Telegram bot."""
    if not config.TELEGRAM_ENABLED:
        print(f"[SKIP] Telegram not configured. Message: {text}")
        return False
    import requests
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return False


def check_and_send():
    """Check for due reminders and send them."""
    db = AuditDB(config.AUDIT_DB_PATH)
    due = db.get_due_reminders()

    if not due:
        return 0

    sent = 0
    for r in due:
        text = f"REMINDER: {r['message']}"
        if send_telegram(text):
            db.mark_reminder_sent(r["id"])
            sent += 1
            print(f"  [SENT] #{r['id']}: {r['message']}")
        else:
            print(f"  [FAIL] #{r['id']}: {r['message']}")

    return sent


def list_pending():
    """List all pending reminders."""
    db = AuditDB(config.AUDIT_DB_PATH)
    pending = db.get_pending_reminders()

    if not pending:
        print("No pending reminders.")
        return

    print(f"{len(pending)} pending reminder(s):")
    for r in pending:
        print(f"  #{r['id']}  {r['remind_at']}  {r['message']}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_pending()
    else:
        sent = check_and_send()
        if sent:
            print(f"Sent {sent} reminder(s).")
