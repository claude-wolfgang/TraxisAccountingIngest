"""
Telegram alerting for Traxis Data Quality Agent.

Two alert modes:
  1. Daily digest (once per day, first run after 6 AM) -- actionable summary
     with overdue WOs, overrun stats, readiness issues, machine health.
  2. Immediate alerts -- only for critical system errors (API/DB down) that
     weren't present in the previous run.

The hourly audit continues to run for data collection and trending, but
Telegram messages are no longer sent every hour.

Setup:
  1. Message @BotFather on Telegram -> /newbot -> name it "Traxis Audit"
  2. Copy the bot token BotFather gives you
  3. Message your new bot (or add it to a group chat)
  4. Visit https://api.telegram.org/bot<TOKEN>/getUpdates -> find chat_id
  5. Set environment variables:
       TELEGRAM_BOT_TOKEN=<your token>
       TELEGRAM_CHAT_ID=<your chat id>
"""

import json
import re
import requests
from datetime import datetime
from pathlib import Path

import config

# ── Projects root for [NEEDS WOLFGANG] scan ──────────────────────────
PROJECTS_ROOT = Path(__file__).parent.parent
PROJECT_DIR_RE = re.compile(r"^(\d+)\.\s+(.+)$")
NEEDS_WOLFGANG_RE = re.compile(r"\[NEEDS WOLFGANG\]\s*(.+?)$", re.IGNORECASE)


# ── State file for tracking last digest ─────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
DIGEST_STATE_FILE = LOG_DIR / "last_digest.json"


def _read_digest_state():
    """Read last digest timestamp. Returns datetime or None."""
    try:
        if DIGEST_STATE_FILE.exists():
            data = json.loads(DIGEST_STATE_FILE.read_text())
            return datetime.fromisoformat(data["last_digest"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        pass
    return None


def _write_digest_state():
    """Record that a digest was just sent."""
    LOG_DIR.mkdir(exist_ok=True)
    try:
        DIGEST_STATE_FILE.write_text(json.dumps({
            "last_digest": datetime.now().isoformat(timespec="seconds"),
        }))
    except OSError:
        pass


# ── Telegram sender ──────────────────────────────────────────────────────

def _send_telegram(text):
    """Post a message to the configured Telegram chat. Returns True on success."""
    if not config.TELEGRAM_ENABLED:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=15)
        if resp.status_code != 200:
            print(f"  [WARN] Telegram send failed: {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"  [WARN] Telegram send error: {e}")
        return False


# ── Diff engine ──────────────────────────────────────────────────────────

def _get_previous_run(audit_db, current_run_id):
    """Get the run immediately before the current one."""
    conn = audit_db._connect()
    row = conn.execute("""
        SELECT * FROM audit_runs
        WHERE id < ? AND total_checks > 0
        ORDER BY id DESC LIMIT 1
    """, (current_run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _finding_key(f):
    """Unique key for a finding to compare across runs."""
    return (f["category"], f["check_name"], f["severity"], f.get("subject", ""))


def _compute_new_errors(audit_db, current_run_id, current_findings):
    """Find genuinely new system errors (severity='error') compared to previous run.

    Returns list of new error findings (not warnings or failures -- just errors).
    """
    prev_run = _get_previous_run(audit_db, current_run_id)
    curr_errors = [f for f in current_findings if f["severity"] == "error"]

    if prev_run is None:
        return curr_errors  # First run: all errors are new

    prev_findings = audit_db.get_run_findings(prev_run["id"])
    prev_error_keys = {_finding_key(f) for f in prev_findings if f["severity"] == "error"}
    return [f for f in curr_errors if _finding_key(f) not in prev_error_keys]


# ── Daily digest formatting ──────────────────────────────────────────────

def _format_digest(current_run, metrics, findings):
    """Build a compact one-screen daily digest.

    Headline metrics use the recent (last 90 days) overrun window and the
    3-day-grace overdue count — see audit_engine.check_overrun_patterns and
    check_overdue_work_orders. Suppresses nc_program_missing (known false
    positive engine, see p25 CLAUDE.md) and machine alarm count (mostly
    benign E-stops/door interlocks). Action items come from [NEEDS WOLFGANG]
    lines in each project's CLAUDE.md.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    failures = [f for f in findings if f["severity"] in ("failure", "error")]

    overdue_3plus = metrics.get("overdue_wo_3plus", (None, None))[0]
    severe_rate = metrics.get("severe_overrun_rate_pct", (None, None))[0]
    recent_hours_over = metrics.get("recent_hours_over_target", (None, None))[0]
    recent_total = metrics.get("recent_completed_wos", (None, None))[0]
    uncertified_3day = metrics.get("uncertified_starting_3day", (None, None))[0]
    mat_po = metrics.get("outstanding_material_pos", (None, None))[0]
    stale_machines = metrics.get("focas_machines_stale", (None, None))[0]

    n_err = current_run.get("errors", 0) or 0
    open_items = _get_open_items()

    lines = [f"<b>TRAXIS DIGEST</b> · {now}"]

    # ── Headline (one line — counts of real signals only) ──
    headline = []
    if overdue_3plus is not None and overdue_3plus > 0:
        headline.append(f"{int(overdue_3plus)} overdue (>3d)")
    if severe_rate is not None and severe_rate > 0:
        headline.append(f"{severe_rate:.0f}% severe overrun (90d)")
    if uncertified_3day is not None and uncertified_3day > 0:
        headline.append(f"{int(uncertified_3day)} uncertified ops (3d)")
    if n_err > 0:
        headline.append(f"<b>{n_err} ERRORS</b>")
    if open_items:
        headline.append(f"{len(open_items)} actions")
    lines.append(" · ".join(headline) if headline else "All clear")

    # ── Worst recent overrun (one line, only if any).
    # worst_overrun is emitted at severity "info" by audit_engine, so pull
    # from all findings, not just failures. Show only if it's actually severe.
    worst_findings = [f for f in findings if f["check_name"] == "worst_overrun"]
    if worst_findings and severe_rate is not None and severe_rate > 0:
        msg = worst_findings[0].get("message", "")
        if len(msg) > 100:
            msg = msg[:97] + "..."
        lines.append(f"Worst: {msg}")

    # ── Top action item (one line, only if any) ──
    if open_items:
        top = open_items[0]
        pid = top.get("project", "?")
        action = top.get("action", "")
        if len(action) > 90:
            action = action[:87] + "..."
        lines.append(f"Top action: P{pid} {action}")

    # ── Compact secondary roll-up (one line, only if anything) ──
    secondary = []
    if recent_hours_over is not None and recent_hours_over > 0:
        secondary.append(f"{recent_hours_over:.0f}h over target (90d)")
    if mat_po is not None and mat_po > 0:
        secondary.append(f"{int(mat_po)} mat POs")
    if stale_machines is not None and stale_machines > 0:
        secondary.append(f"{int(stale_machines)} stale machines")
    if secondary:
        lines.append(" · ".join(secondary))

    # ── Summary counts (always last) ──
    total = current_run.get("total_checks", 0) or 0
    n_pass = current_run.get("passed", 0) or 0
    n_warn = current_run.get("warnings", 0) or 0
    n_fail = current_run.get("failures", 0) or 0
    lines.append(f"{total} checks: {n_pass}p {n_warn}w {n_fail}f {n_err}e")

    return "\n".join(lines)


def _get_open_items():
    """Scan each project's CLAUDE.md for `[NEEDS WOLFGANG]` lines.

    Returns list of {project, action, file} dicts, ordered by project number.
    Source of truth is the project Next Steps section maintained by the close
    ritual — no longer relies on the Haiku-summarized project_index.json.
    """
    items = []
    try:
        for entry in sorted(PROJECTS_ROOT.iterdir()):
            if not entry.is_dir():
                continue
            m = PROJECT_DIR_RE.match(entry.name)
            if not m:
                continue
            project_id = m.group(1)
            claude_md = entry / "CLAUDE.md"
            if not claude_md.exists():
                continue
            try:
                text = claude_md.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                m2 = NEEDS_WOLFGANG_RE.search(line)
                if m2:
                    action = m2.group(1).strip().rstrip(".")
                    items.append({
                        "project": project_id,
                        "action": action,
                        "file": str(claude_md),
                    })
    except OSError:
        pass
    return items


# ── Immediate critical alert formatting ──────────────────────────────────

def _format_critical_alert(new_errors):
    """Format an immediate alert for new system errors."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"<b>TRAXIS ALERT</b> -- {now}"]
    lines.append("")
    lines.append(f"<b>{len(new_errors)} NEW ERROR(S):</b>")
    for f in new_errors[:5]:
        cat = f.get("category", "?")
        msg = f.get("message", "")
        if len(msg) > 120:
            msg = msg[:117] + "..."
        lines.append(f"!! [{cat}] {msg}")
    if len(new_errors) > 5:
        lines.append(f"  ... +{len(new_errors) - 5} more")
    return "\n".join(lines)


# ── Public API ───────────────────────────────────────────────────────────

def send_audit_alert(audit_db, run_id, findings):
    """Decide whether to send an alert and format the right type.

    Two modes:
      - Daily digest: sent once per day (first run after 6 AM)
      - Immediate: sent only for new system errors (severity='error')

    Args:
        audit_db: AuditDB instance
        run_id: Current run ID
        findings: List of Finding objects from the audit engine

    Returns True if an alert was sent, False otherwise.
    """
    if not config.TELEGRAM_ENABLED:
        return False

    # Get current run metadata
    conn = audit_db._connect()
    row = conn.execute("SELECT * FROM audit_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not row:
        return False
    current_run = dict(row)

    # Convert Finding objects to dicts
    current_findings = []
    for f in findings:
        current_findings.append({
            "category": f.category,
            "check_name": f.check_name,
            "severity": f.severity,
            "message": f.message,
            "subject": f.subject,
        })

    sent = False

    # ── Check for new critical errors (immediate alert) ──
    new_errors = _compute_new_errors(audit_db, run_id, current_findings)
    if new_errors:
        text = _format_critical_alert(new_errors)
        if _send_telegram(text):
            print("  [INFO] Telegram critical alert sent")
            sent = True

    # ── Check if daily digest is due ──
    now = datetime.now()
    last_digest = _read_digest_state()
    send_digest = False

    if last_digest is None:
        # First ever run -- send digest
        send_digest = True
    elif now.hour >= 6:
        # After 6 AM: send if last digest was before today's 6 AM
        today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if last_digest < today_6am:
            send_digest = True

    if send_digest:
        metrics = audit_db.get_run_metrics(run_id)
        all_findings = audit_db.get_run_findings(run_id)
        text = _format_digest(current_run, metrics, all_findings)
        if _send_telegram(text):
            _write_digest_state()
            print("  [INFO] Telegram daily digest sent")
            sent = True

    if not sent:
        print("  [INFO] Telegram: no alert needed")

    return sent
