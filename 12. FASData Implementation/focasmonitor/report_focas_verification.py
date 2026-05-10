"""One-shot verification + Telegram report for the program_directory fix.

Designed to be invoked by Windows Task Scheduler on .71. Reads monitoring.db
read-only, computes a verdict (WORKING / NOT WORKING / INCONCLUSIVE), and
posts to the P25 Telegram bot using credentials from p25's config module.

Always exits 0 — even on failure we want the scheduled task to look successful
in the Task Scheduler UI; the Telegram message carries the actual verdict.
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Pull p25 config (Telegram credentials, env-var loader)
P25 = Path(__file__).resolve().parent.parent.parent / "25. Agent Exploration"
sys.path.insert(0, str(P25))
import config  # noqa: E402

import requests  # noqa: E402


def build_report():
    db = Path(r"C:\FASData\monitoring.db")
    if not db.exists():
        return "FOCAS VERIFY ERROR: monitoring.db not found at C:\\FASData\\monitoring.db"

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    pd_rows = conn.execute(
        """SELECT machine_id,
                  COUNT(*)                       AS rows,
                  COUNT(program_comment)         AS with_comment,
                  COUNT(DISTINCT program_number) AS distinct_progs,
                  MAX(timestamp)                 AS last_ts
           FROM program_directory
           GROUP BY machine_id"""
    ).fetchall()

    cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
    activity = conn.execute(
        """SELECT machine_id,
                  COUNT(*) AS samples,
                  SUM(CASE WHEN connected = 1 THEN 1 ELSE 0 END) AS connected
           FROM machine_samples
           WHERE timestamp > ?
           GROUP BY machine_id
           ORDER BY machine_id""",
        (cutoff,),
    ).fetchall()

    sample_comments = conn.execute(
        """SELECT machine_id, program_number, program_comment
           FROM program_directory
           WHERE program_comment IS NOT NULL AND program_comment != ''
           GROUP BY machine_id, program_number
           ORDER BY MAX(timestamp) DESC
           LIMIT 5"""
    ).fetchall()

    conn.close()

    total_pd = sum(r["rows"] for r in pd_rows)
    total_with_comment = sum(r["with_comment"] for r in pd_rows)
    connected_now = sum((r["connected"] or 0) for r in activity)

    lines = [f"<b>FOCAS PROGDIR VERIFY</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

    if total_pd > 0:
        verdict = "WORKING" if total_with_comment > 0 else "PARTIAL"
        lines.append(f"VERDICT: {verdict} - {total_pd} rows ({total_with_comment} w/comment)")
        lines.append("")
        lines.append("Per-machine:")
        for r in pd_rows:
            lines.append(
                f"  {r['machine_id']}: {r['rows']}r {r['with_comment']}c "
                f"{r['distinct_progs']}p  last={r['last_ts'][:19]}"
            )
        if sample_comments:
            lines.append("")
            lines.append("Sample comments captured:")
            for r in sample_comments:
                c = (r["program_comment"] or "")[:60]
                lines.append(f"  {r['machine_id']} O{r['program_number']:04d}: {c}")
    else:
        if connected_now == 0:
            lines.append("VERDICT: INCONCLUSIVE - no machines connected in last 30 min")
            lines.append("(machines may not have been powered on yet)")
        else:
            lines.append(f"VERDICT: NOT WORKING - {connected_now} connected samples")
            lines.append("but program_directory still empty.")
            lines.append("Check .71 Application event log for cnc_rdprogdir3 errors.")

    if activity:
        lines.append("")
        lines.append("Polling activity (last 30 min):")
        for r in activity:
            lines.append(
                f"  {r['machine_id']}: {r['samples']} samples, "
                f"{r['connected'] or 0} connected"
            )

    return "\n".join(lines)


def send_telegram(text):
    if not config.TELEGRAM_ENABLED:
        print("Telegram not configured. Would send:\n" + text)
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"Telegram send error: {e}")
        return False


if __name__ == "__main__":
    text = build_report()
    print(text)
    send_telegram(text)
    sys.exit(0)
