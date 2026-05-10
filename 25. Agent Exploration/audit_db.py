"""
Local SQLite database for storing audit results over time.
Enables trending — "is data quality getting better or worse?"
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    duration_s  REAL,
    total_checks INTEGER DEFAULT 0,
    passed      INTEGER DEFAULT 0,
    warnings    INTEGER DEFAULT 0,
    failures    INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0,
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES audit_runs(id),
    timestamp   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    category    TEXT NOT NULL,
    check_name  TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK (severity IN ('pass', 'info', 'warning', 'failure', 'error')),
    subject     TEXT,
    message     TEXT NOT NULL,
    details     TEXT,
    auto_fixable INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_findings_run ON audit_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON audit_findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_category ON audit_findings(category);

CREATE TABLE IF NOT EXISTS audit_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES audit_runs(id),
    timestamp   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    context     TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON audit_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_run ON audit_metrics(run_id);

CREATE TABLE IF NOT EXISTS field_population (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES audit_runs(id),
    timestamp   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    field_name  TEXT NOT NULL,
    level       TEXT NOT NULL CHECK (level IN ('work_order', 'operation')),
    total       INTEGER NOT NULL,
    populated   INTEGER NOT NULL,
    pct         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_field_pop_run ON field_population(run_id);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message     TEXT NOT NULL,
    remind_at   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    sent_at     TEXT,
    canceled    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(remind_at, sent_at, canceled);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT NOT NULL,
    project_id  INTEGER,
    tags        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project_id);
"""


class AuditDB:
    """Persistent storage for audit results with trending queries."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    # ── Write ────────────────────────────────────────────────────────────

    def start_run(self):
        """Create a new audit run and return its ID."""
        conn = self._connect()
        cursor = conn.execute("INSERT INTO audit_runs DEFAULT VALUES")
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def finish_run(self, run_id, duration_s, total_checks, passed, warnings, failures, errors, summary=""):
        """Finalize an audit run with counts."""
        conn = self._connect()
        conn.execute("""
            UPDATE audit_runs
            SET duration_s = ?, total_checks = ?, passed = ?,
                warnings = ?, failures = ?, errors = ?, summary = ?
            WHERE id = ?
        """, (duration_s, total_checks, passed, warnings, failures, errors, summary, run_id))
        conn.commit()
        conn.close()

    def add_finding(self, run_id, category, check_name, severity, message,
                    subject=None, details=None, auto_fixable=False):
        """Record a single audit finding."""
        conn = self._connect()
        conn.execute("""
            INSERT INTO audit_findings
                (run_id, category, check_name, severity, subject, message, details, auto_fixable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, category, check_name, severity, subject, message,
              json.dumps(details) if details else None, 1 if auto_fixable else 0))
        conn.commit()
        conn.close()

    def add_metric(self, run_id, metric_name, metric_value, context=None):
        """Record a numeric metric for trending."""
        conn = self._connect()
        conn.execute("""
            INSERT INTO audit_metrics (run_id, metric_name, metric_value, context)
            VALUES (?, ?, ?, ?)
        """, (run_id, metric_name, metric_value, context))
        conn.commit()
        conn.close()

    def add_field_population(self, run_id, field_name, level, total, populated):
        """Record field population rate for trending."""
        pct = round(100.0 * populated / total, 1) if total > 0 else 0
        conn = self._connect()
        conn.execute("""
            INSERT INTO field_population (run_id, field_name, level, total, populated, pct)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (run_id, field_name, level, total, populated, pct))
        conn.commit()
        conn.close()

    # ── Read / Trending ──────────────────────────────────────────────────

    def get_latest_run(self):
        """Get the most recent completed audit run."""
        conn = self._connect()
        row = conn.execute("""
            SELECT * FROM audit_runs
            WHERE total_checks > 0
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_run_findings(self, run_id, severity=None):
        """Get all findings for a run, optionally filtered by severity."""
        conn = self._connect()
        if severity:
            rows = conn.execute("""
                SELECT * FROM audit_findings
                WHERE run_id = ? AND severity = ?
                ORDER BY category, check_name
            """, (run_id, severity)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM audit_findings
                WHERE run_id = ?
                ORDER BY severity DESC, category, check_name
            """, (run_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_run_metrics(self, run_id):
        """Get all metrics for a specific run as a dict {name: (value, context)}."""
        conn = self._connect()
        rows = conn.execute("""
            SELECT metric_name, metric_value, context
            FROM audit_metrics
            WHERE run_id = ?
        """, (run_id,)).fetchall()
        conn.close()
        return {r["metric_name"]: (r["metric_value"], r["context"]) for r in rows}

    def get_metric_trend(self, metric_name, days=30):
        """Get a metric's values over time for trend analysis."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT am.timestamp, am.metric_value, am.context
            FROM audit_metrics am
            JOIN audit_runs ar ON am.run_id = ar.id
            WHERE am.metric_name = ?
              AND ar.timestamp > ?
            ORDER BY ar.timestamp
        """, (metric_name, cutoff)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_field_population_trend(self, field_name, days=30):
        """Get population rate trend for a specific field."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT fp.timestamp, fp.pct, fp.total, fp.populated
            FROM field_population fp
            JOIN audit_runs ar ON fp.run_id = ar.id
            WHERE fp.field_name = ?
              AND ar.timestamp > ?
            ORDER BY ar.timestamp
        """, (field_name, cutoff)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_run_history(self, days=30):
        """Get audit run history for overall trend."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT * FROM audit_runs
            WHERE timestamp > ?
              AND total_checks > 0
            ORDER BY timestamp
        """, (cutoff,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Reminders ──────────────────────────────────────────────────────

    def add_reminder(self, message, remind_at):
        """Schedule a reminder. remind_at is an ISO datetime string."""
        conn = self._connect()
        cursor = conn.execute(
            "INSERT INTO reminders (message, remind_at) VALUES (?, ?)",
            (message, remind_at),
        )
        rid = cursor.lastrowid
        conn.commit()
        conn.close()
        return rid

    def get_pending_reminders(self):
        """Get all unsent, uncanceled reminders."""
        conn = self._connect()
        rows = conn.execute("""
            SELECT * FROM reminders
            WHERE sent_at IS NULL AND canceled = 0
            ORDER BY remind_at
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_due_reminders(self):
        """Get reminders that are due now (remind_at <= now, not yet sent)."""
        conn = self._connect()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute("""
            SELECT * FROM reminders
            WHERE remind_at <= ? AND sent_at IS NULL AND canceled = 0
            ORDER BY remind_at
        """, (now,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_reminder_sent(self, reminder_id):
        """Mark a reminder as sent."""
        conn = self._connect()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE reminders SET sent_at = ? WHERE id = ?",
            (now, reminder_id),
        )
        conn.commit()
        conn.close()

    def cancel_reminder(self, reminder_id):
        """Cancel a pending reminder. Returns True if found and canceled."""
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE reminders SET canceled = 1 WHERE id = ? AND sent_at IS NULL",
            (reminder_id,),
        )
        conn.commit()
        changed = cursor.rowcount > 0
        conn.close()
        return changed

    # ── Notes ─────────────────────────────────────────────────────────

    def add_note(self, text, project_id=None, tags=None):
        """Save a note/thought. Returns note ID."""
        conn = self._connect()
        cursor = conn.execute(
            "INSERT INTO notes (text, project_id, tags) VALUES (?, ?, ?)",
            (text, project_id, tags),
        )
        nid = cursor.lastrowid
        conn.commit()
        conn.close()
        return nid

    def get_recent_notes(self, limit=20, project_id=None):
        """Get recent notes, optionally filtered by project."""
        conn = self._connect()
        if project_id is not None:
            rows = conn.execute(
                "SELECT * FROM notes WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_notes(self, query):
        """Search notes by text content."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM notes WHERE text LIKE ? ORDER BY created_at DESC LIMIT 20",
            (f"%{query}%",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_severity_trend(self, days=30):
        """Get pass/warn/fail counts over time."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT timestamp, passed, warnings, failures, errors, total_checks
            FROM audit_runs
            WHERE timestamp > ?
              AND total_checks > 0
            ORDER BY timestamp
        """, (cutoff,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
