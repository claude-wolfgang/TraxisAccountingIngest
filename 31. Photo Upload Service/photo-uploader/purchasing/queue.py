"""SQLite queue for the P35 purchasing workflow.

Schema follows PLAN.md — same shape that Phase 2 (Selenium VPO creation)
and Phase 3 (Graph email draft) will populate later. Phase 1 only writes
the early columns (created_at, status=pending|approved, approved_*).
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "purchasing.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    qty             REAL NOT NULL,
    unit_cost       REAL,
    vendor          TEXT,
    brand           TEXT,
    edp             TEXT,
    status          TEXT NOT NULL,
    vpo_number      TEXT,
    pdf_path        TEXT,
    email_draft_id  TEXT,
    created_at      TEXT NOT NULL,
    approved_at     TEXT,
    approved_by     TEXT,
    completed_at    TEXT,
    error           TEXT,
    rule_reason     TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, created_at);
"""


def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _lock, _conn() as c:
        c.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_order(entity_type, entity_id, qty, unit_cost=None, vendor=None,
                 brand=None, edp=None, status="pending",
                 approved_by=None, rule_reason=None):
    """Insert a queued order. status=pending|approved|... per PLAN."""
    now = _now()
    approved_at = now if status == "approved" else None
    with _lock, _conn() as c:
        cur = c.execute(
            """INSERT INTO orders
               (entity_type, entity_id, qty, unit_cost, vendor, brand, edp,
                status, created_at, approved_at, approved_by, rule_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity_type, entity_id, qty, unit_cost, vendor, brand, edp,
             status, now, approved_at, approved_by, rule_reason),
        )
        return cur.lastrowid


def get(order_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


def get_pending(limit=50):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM orders WHERE status = 'pending' "
            "ORDER BY created_at ASC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent(limit=50):
    """Recent orders regardless of status — for the bottom of the approvals page."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def approve(order_id, approver):
    """Flip pending → approved. Returns True if state change happened."""
    with _lock, _conn() as c:
        cur = c.execute(
            """UPDATE orders SET status = 'approved', approved_at = ?, approved_by = ?
               WHERE id = ? AND status = 'pending'""",
            (_now(), approver, order_id),
        )
        return cur.rowcount > 0


def reject(order_id, approver, reason=None):
    """Flip pending → rejected."""
    with _lock, _conn() as c:
        cur = c.execute(
            """UPDATE orders SET status = 'rejected', approved_at = ?,
                                 approved_by = ?, error = ?
               WHERE id = ? AND status = 'pending'""",
            (_now(), approver, reason, order_id),
        )
        return cur.rowcount > 0


def stats():
    """Counts by status — for badges and headers."""
    with _conn() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) AS n FROM orders GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


def quote_requests_today(vendor):
    """Count quote-request emails drafted to a vendor since UTC midnight today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _conn() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n FROM orders
               WHERE vendor = ? AND status = 'awaiting_quote'
                 AND created_at LIKE ?""",
            (vendor, f"{today}%"),
        ).fetchone()
        return row["n"] if row else 0


def attach_draft(order_id, draft_id):
    """Store the Graph draft message ID on an order row."""
    with _lock, _conn() as c:
        c.execute(
            "UPDATE orders SET email_draft_id = ? WHERE id = ?",
            (draft_id, order_id),
        )


def get_approved(limit=10):
    """Fetch orders ready for VPO creation (status='approved'), oldest first."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM orders WHERE status = 'approved' "
            "ORDER BY created_at ASC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_vpo_created(order_id, vpo_number, proshop_url=None):
    """Flip approved → vpo_created with VPO number and completion timestamp."""
    with _lock, _conn() as c:
        cur = c.execute(
            """UPDATE orders SET status = 'vpo_created', vpo_number = ?,
                                 completed_at = ?, error = NULL
               WHERE id = ? AND status = 'approved'""",
            (vpo_number, _now(), order_id),
        )
        return cur.rowcount > 0


def mark_failed(order_id, error_msg):
    """Flip to 'failed' with error detail."""
    with _lock, _conn() as c:
        cur = c.execute(
            """UPDATE orders SET status = 'failed', error = ?,
                                 completed_at = ?
               WHERE id = ?""",
            (error_msg, _now(), order_id),
        )
        return cur.rowcount > 0
