import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta

import config


class OverlapError(Exception):
    """Raised when a schedule block would overlap an existing block on the same machine."""
    def __init__(self, conflicting_block):
        self.conflicting_block = conflicting_block
        super().__init__(
            f"Overlaps with block #{conflicting_block['id']} "
            f"(WO{conflicting_block['wo_number']} Op{conflicting_block['op_number']}) "
            f"on {conflicting_block['machine_id']}"
        )


def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    conn.executescript(SCHEMA)
    _seed_defaults(conn)
    _migrate(conn)
    conn.close()


def _migrate(conn):
    """Run lightweight migrations for columns added after initial schema."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(work_orders)").fetchall()]
    # Add material_type to work_orders if missing
    if "material_type" not in cols:
        conn.execute("ALTER TABLE work_orders ADD COLUMN material_type TEXT DEFAULT ''")
        conn.commit()
    # Add hidden flag to work_orders if missing
    if "hidden" not in cols:
        conn.execute("ALTER TABLE work_orders ADD COLUMN hidden INTEGER DEFAULT 0")
        conn.commit()

    # Add hidden flag to operations if missing
    op_cols = [r[1] for r in conn.execute("PRAGMA table_info(operations)").fetchall()]
    if "hidden" not in op_cols:
        conn.execute("ALTER TABLE operations ADD COLUMN hidden INTEGER DEFAULT 0")
        conn.commit()

    # Add MILL-X-CAT40 and MILL-X-PROBE work center mappings if missing
    for code, desc in [
        ("MILL-X-CAT40", "CAT40 mill catch-all (full-size mills)"),
        ("MILL-X-PROBE", "Probe-capable mill catch-all"),
    ]:
        exists = conn.execute(
            "SELECT 1 FROM work_center_map WHERE proshop_code=?", (code,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO work_center_map (proshop_code, machine_id, description) VALUES (?, NULL, ?)",
                (code, desc)
            )
    conn.commit()


SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'mill',   -- mill, lathe, other
    proshop_id  TEXT,                            -- ProShop work cell ID
    sort_order  INTEGER DEFAULT 0,
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS work_orders (
    wo_number   TEXT PRIMARY KEY,
    part_number TEXT,
    part_name   TEXT,
    customer    TEXT,
    due_date    TEXT,
    qty_ordered INTEGER DEFAULT 0,
    qty_complete INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'active',          -- active, complete, cancelled
    priority    INTEGER DEFAULT 0,
    proshop_data TEXT,                           -- Full JSON from ProShop
    synced_at   TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operations (
    id              TEXT PRIMARY KEY,            -- "{wo_number}-{op_number}"
    wo_number       TEXT NOT NULL REFERENCES work_orders(wo_number),
    op_number       INTEGER NOT NULL,
    op_name         TEXT,
    work_center     TEXT,                       -- ProShop work center code
    machine_id      TEXT REFERENCES machines(id),
    est_hours       REAL,                       -- ProShop estimated hours
    override_hours  REAL,                       -- Manual override
    setup_hours     REAL DEFAULT 0,
    qty_required    INTEGER DEFAULT 0,
    qty_complete    INTEGER DEFAULT 0,
    is_complete     INTEGER DEFAULT 0,
    is_estimated    INTEGER DEFAULT 1,          -- 1 if using default time
    proshop_data    TEXT,                        -- Full JSON from ProShop
    synced_at       TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL REFERENCES operations(id),
    machine_id  TEXT NOT NULL REFERENCES machines(id),
    start_time  TEXT NOT NULL,                  -- ISO datetime
    end_time    TEXT NOT NULL,                  -- ISO datetime
    status      TEXT DEFAULT 'scheduled',       -- scheduled, running, complete, paused
    is_locked   INTEGER DEFAULT 0,
    color       TEXT,                           -- Override color
    notes       TEXT,
    created_by  TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operator_updates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id    INTEGER REFERENCES schedule_blocks(id),
    operation_id TEXT REFERENCES operations(id),
    update_type TEXT NOT NULL,                  -- qty_update, status_change, note
    qty_added   INTEGER DEFAULT 0,
    old_status  TEXT,
    new_status  TEXT,
    note        TEXT,
    operator    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS flags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id    INTEGER REFERENCES schedule_blocks(id),
    operation_id TEXT REFERENCES operations(id),
    machine_id  TEXT REFERENCES machines(id),
    category    TEXT NOT NULL,                  -- tooling, material, quality, question
    description TEXT NOT NULL,
    status      TEXT DEFAULT 'open',            -- open, acknowledged, resolved
    flagged_by  TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS work_center_map (
    proshop_code TEXT PRIMARY KEY,
    machine_id   TEXT REFERENCES machines(id),
    description  TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type   TEXT NOT NULL,                  -- full, writeback, partial
    status      TEXT NOT NULL,                  -- started, completed, failed
    details     TEXT,
    wo_count    INTEGER DEFAULT 0,
    op_count    INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS writeback_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL,
    field       TEXT NOT NULL,                  -- perOpQtyComplete, isOpComplete
    value       TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',         -- pending, sent, failed
    attempts    INTEGER DEFAULT 0,
    error       TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    sent_at     TEXT
);

CREATE TABLE IF NOT EXISTS readiness (
    operation_id TEXT PRIMARY KEY REFERENCES operations(id),
    program_ready  INTEGER DEFAULT 0,   -- 1=programming complete for this WO
    material_ready INTEGER DEFAULT 0,   -- 1=all material received
    tools_ready    INTEGER DEFAULT 0,   -- 1=tools staged (manual toggle)
    machine_ready  INTEGER DEFAULT 0,   -- 1=viable machine slot found
    material_detail TEXT,               -- JSON: {status, outstanding_pos: [...]}
    updated_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS machine_pockets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id      TEXT NOT NULL REFERENCES machines(id),
    pocket_number   INTEGER NOT NULL,
    tool_number     TEXT,               -- ProShop toolPlainText (tool ID)
    out_of_holder   REAL,               -- stickout distance
    holder          TEXT,               -- holder description
    synced_at       TEXT DEFAULT (datetime('now')),
    UNIQUE(machine_id, pocket_number)
);

CREATE TABLE IF NOT EXISTS operation_tools (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id    TEXT NOT NULL REFERENCES operations(id),
    tool_number     TEXT,               -- ProShop tool number / ID
    tool_description TEXT,
    holder          TEXT,
    out_of_holder   REAL,
    sequence_number INTEGER,
    synced_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_blocks_machine ON schedule_blocks(machine_id);
CREATE INDEX IF NOT EXISTS idx_blocks_operation ON schedule_blocks(operation_id);
CREATE INDEX IF NOT EXISTS idx_blocks_time ON schedule_blocks(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_ops_wo ON operations(wo_number);
CREATE INDEX IF NOT EXISTS idx_ops_machine ON operations(machine_id);
CREATE INDEX IF NOT EXISTS idx_flags_status ON flags(status);
CREATE INDEX IF NOT EXISTS idx_writeback_status ON writeback_queue(status);
CREATE INDEX IF NOT EXISTS idx_readiness_op ON readiness(operation_id);
CREATE INDEX IF NOT EXISTS idx_machine_pockets_machine ON machine_pockets(machine_id);
CREATE INDEX IF NOT EXISTS idx_op_tools_op ON operation_tools(operation_id);
"""


def _seed_defaults(conn):
    """Seed default machines and settings if tables are empty."""
    count = conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0]
    if count > 0:
        return

    # Traxis machines — 8 mills + 1 lathe (matching ProShop work cells)
    machines = [
        ("mill-1", "Haas VF5",             "mill",  "Mill-1", 1),
        ("mill-2", "Smec #1",              "mill",  "Mill-2", 2),
        ("mill-3", "Smec #2",              "mill",  "Mill-3", 3),
        ("mill-4", "Black Robodrill",      "mill",  "Mill-4", 4),
        ("mill-5", "White Robodrill",      "mill",  "Mill-5", 5),
        ("mill-6", "Chevalier",            "mill",  "Mill-6", 6),
        ("mill-7", "5-axis Robodrill",     "mill",  "Mill-7", 7),
        ("mill-8", "Hyundai-Wia KF5600II", "mill", "Mill-8", 8),
        ("t2",     "YCM NTC1600LY",       "lathe", "T2",     9),
    ]
    conn.executemany(
        "INSERT INTO machines (id, name, type, proshop_id, sort_order) VALUES (?, ?, ?, ?, ?)",
        machines
    )

    # Work center mappings: ProShop potId / work center code → machine
    # MILL-X is catch-all — maps to NULL (scheduler distributes to mills 1-8)
    mappings = [
        ("Mill-1",  "mill-1", "Haas VF5"),
        ("Mill-2",  "mill-2", "Smec #1"),
        ("Mill-3",  "mill-3", "Smec #2"),
        ("Mill-4",  "mill-4", "Black Robodrill"),
        ("Mill-5",  "mill-5", "White Robodrill"),
        ("Mill-6",  "mill-6", "Chevalier"),
        ("Mill-7",  "mill-7", "5-axis Robodrill"),
        ("Mill-8",  "mill-8", "Hyundai-Wia KF5600II"),
        ("T2",      "t2",     "YCM NTC1600LY"),
        ("MILL-X",  None,     "Mill catch-all (distribute to any mill)"),
        ("MILL-X-CAT40", None, "CAT40 mill catch-all (full-size mills)"),
        ("MILL-X-PROBE", None, "Probe-capable mill catch-all"),
    ]
    conn.executemany(
        "INSERT INTO work_center_map (proshop_code, machine_id, description) VALUES (?, ?, ?)",
        mappings
    )

    # Default settings
    defaults = [
        ("default_duration_min", str(config.DEFAULT_OP_DURATION_MIN)),
        ("sync_interval", str(config.SYNC_INTERVAL)),
        ("writeback_interval", str(config.WRITEBACK_INTERVAL)),
        ("business_hours_start", str(config.BUSINESS_HOURS_START)),
        ("business_hours_end", str(config.BUSINESS_HOURS_END)),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        defaults
    )

    conn.commit()


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_machines(conn=None):
    close = conn is None
    if close:
        conn = get_db()
    rows = conn.execute(
        "SELECT * FROM machines WHERE is_active=1 ORDER BY sort_order"
    ).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]


def get_work_orders(conn=None, status="active"):
    close = conn is None
    if close:
        conn = get_db()
    rows = conn.execute(
        "SELECT * FROM work_orders WHERE status=? ORDER BY due_date",
        (status,)
    ).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]


def get_operations(conn=None, wo_number=None, unscheduled_only=False, schedulable_only=False, include_hidden=False):
    close = conn is None
    if close:
        conn = get_db()

    query = """
        SELECT o.*, w.part_number, w.part_name, w.due_date, w.customer,
               w.qty_ordered, w.material_type, w.status as wo_status
        FROM operations o
        JOIN work_orders w ON o.wo_number = w.wo_number
        WHERE w.status = 'active' AND o.is_complete = 0
    """
    if not include_hidden:
        query += " AND COALESCE(w.hidden, 0) = 0 AND COALESCE(o.hidden, 0) = 0"
    params = []

    if wo_number:
        query += " AND o.wo_number = ?"
        params.append(wo_number)

    if schedulable_only:
        # Only ops that belong to a known work center (mills, lathe, catch-all)
        query += """ AND o.work_center IN (
            SELECT proshop_code FROM work_center_map
        )"""

    if unscheduled_only:
        query += " AND o.id NOT IN (SELECT operation_id FROM schedule_blocks WHERE status != 'complete')"

    query += " ORDER BY w.due_date, o.wo_number, o.op_number"

    rows = conn.execute(query, params).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]


def get_schedule_blocks(conn=None, machine_id=None, start=None, end=None):
    close = conn is None
    if close:
        conn = get_db()

    query = """
        SELECT sb.*, o.op_name, o.wo_number, o.op_number, o.qty_required,
               o.qty_complete, o.is_estimated, o.est_hours, o.override_hours,
               w.part_number, w.part_name, w.due_date, w.customer, w.qty_ordered,
               w.material_type, m.name as machine_name
        FROM schedule_blocks sb
        JOIN operations o ON sb.operation_id = o.id
        JOIN work_orders w ON o.wo_number = w.wo_number
        JOIN machines m ON sb.machine_id = m.id
        WHERE w.status = 'active'
    """
    params = []

    if machine_id:
        query += " AND sb.machine_id = ?"
        params.append(machine_id)
    if start:
        query += " AND sb.end_time >= ?"
        params.append(start)
    if end:
        query += " AND sb.start_time <= ?"
        params.append(end)

    query += " ORDER BY sb.start_time"

    rows = conn.execute(query, params).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]


def _check_overlap(conn, machine_id, start_time, end_time, exclude_block_id=None):
    """Check for overlapping non-complete blocks on the same machine.
    Returns the conflicting block row or None."""
    query = """
        SELECT sb.id, sb.operation_id, sb.machine_id, sb.start_time, sb.end_time,
               sb.status, o.wo_number, o.op_number
        FROM schedule_blocks sb
        JOIN operations o ON sb.operation_id = o.id
        WHERE sb.machine_id = ?
          AND sb.status != 'complete'
          AND sb.start_time < ?
          AND sb.end_time > ?
    """
    params = [machine_id, end_time, start_time]
    if exclude_block_id is not None:
        query += " AND sb.id != ?"
        params.append(exclude_block_id)
    query += " LIMIT 1"
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def create_schedule_block(conn, operation_id, machine_id, start_time, end_time, created_by=None):
    conflict = _check_overlap(conn, machine_id, start_time, end_time)
    if conflict:
        raise OverlapError(conflict)

    cur = conn.execute(
        """INSERT INTO schedule_blocks (operation_id, machine_id, start_time, end_time, created_by)
           VALUES (?, ?, ?, ?, ?)""",
        (operation_id, machine_id, start_time, end_time, created_by)
    )
    conn.commit()
    return cur.lastrowid


def update_schedule_block(conn, block_id, **kwargs):
    allowed = {"machine_id", "start_time", "end_time", "status", "is_locked", "color", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    # If changing machine, start, or end — check for overlaps
    if updates.keys() & {"machine_id", "start_time", "end_time"}:
        current = conn.execute(
            "SELECT machine_id, start_time, end_time FROM schedule_blocks WHERE id=?",
            (block_id,)
        ).fetchone()
        if current:
            machine = updates.get("machine_id", current["machine_id"])
            start = updates.get("start_time", current["start_time"])
            end = updates.get("end_time", current["end_time"])
            conflict = _check_overlap(conn, machine, start, end, exclude_block_id=block_id)
            if conflict:
                raise OverlapError(conflict)

    updates["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [block_id]
    conn.execute(f"UPDATE schedule_blocks SET {set_clause} WHERE id=?", values)
    conn.commit()


def delete_schedule_block(conn, block_id):
    conn.execute("DELETE FROM schedule_blocks WHERE id=? AND is_locked=0", (block_id,))
    conn.commit()


def get_flags(conn=None, status="open"):
    close = conn is None
    if close:
        conn = get_db()
    rows = conn.execute(
        """SELECT f.*, o.wo_number, o.op_number, o.op_name, m.name as machine_name
           FROM flags f
           LEFT JOIN operations o ON f.operation_id = o.id
           LEFT JOIN machines m ON f.machine_id = m.id
           WHERE f.status = ?
           ORDER BY f.created_at DESC""",
        (status,)
    ).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]


def get_stats(conn=None):
    close = conn is None
    if close:
        conn = get_db()

    stats = {}
    stats["active_wos"] = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE status='active'"
    ).fetchone()[0]

    stats["past_due"] = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE status='active' AND due_date < date('now')"
    ).fetchone()[0]

    stats["total_ops"] = conn.execute(
        "SELECT COUNT(*) FROM operations o JOIN work_orders w ON o.wo_number=w.wo_number WHERE w.status='active'"
    ).fetchone()[0]

    stats["unscheduled_ops"] = conn.execute(
        """SELECT COUNT(*) FROM operations o
           JOIN work_orders w ON o.wo_number=w.wo_number
           WHERE w.status='active' AND o.is_complete=0
           AND o.id NOT IN (SELECT operation_id FROM schedule_blocks WHERE status != 'complete')"""
    ).fetchone()[0]

    row = conn.execute(
        """SELECT COALESCE(SUM(COALESCE(o.override_hours, o.est_hours, 1.0)), 0) as total_hours
           FROM operations o
           JOIN work_orders w ON o.wo_number=w.wo_number
           WHERE w.status='active' AND o.is_complete=0"""
    ).fetchone()
    stats["backlog_hours"] = round(row[0], 1)

    stats["machines_running"] = conn.execute(
        "SELECT COUNT(DISTINCT machine_id) FROM schedule_blocks WHERE status='running'"
    ).fetchone()[0]

    stats["open_flags"] = conn.execute(
        "SELECT COUNT(*) FROM flags WHERE status='open'"
    ).fetchone()[0]

    stats["completed_today"] = conn.execute(
        """SELECT COUNT(*) FROM operator_updates
           WHERE update_type='status_change' AND new_status='complete'
           AND date(created_at)=date('now')"""
    ).fetchone()[0]

    if close:
        conn.close()
    return stats


def get_readiness(conn, operation_ids=None):
    """Get readiness data for operations. Returns dict keyed by operation_id."""
    if operation_ids:
        placeholders = ",".join("?" * len(operation_ids))
        rows = conn.execute(
            f"SELECT * FROM readiness WHERE operation_id IN ({placeholders})",
            list(operation_ids)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM readiness").fetchall()
    return {r["operation_id"]: dict(r) for r in rows}


def get_readiness_for_op(conn, operation_id):
    """Get readiness for a single operation, or defaults if not yet computed."""
    row = conn.execute(
        "SELECT * FROM readiness WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if row:
        return dict(row)
    return {
        "operation_id": operation_id,
        "program_ready": 0, "material_ready": 0,
        "tools_ready": 0, "machine_ready": 0,
        "material_detail": None,
    }


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (key, str(value))
    )
    conn.commit()


def toggle_wo_hidden(conn, wo_number):
    """Toggle the hidden flag on a work order. Returns new hidden value."""
    row = conn.execute(
        "SELECT hidden FROM work_orders WHERE wo_number=?", (wo_number,)
    ).fetchone()
    if not row:
        return None
    new_val = 0 if row["hidden"] else 1
    conn.execute(
        "UPDATE work_orders SET hidden=? WHERE wo_number=?", (new_val, wo_number)
    )
    conn.commit()
    return new_val


def get_hidden_work_orders(conn):
    """Return all hidden work orders."""
    rows = conn.execute(
        "SELECT wo_number, part_number, part_name, customer, due_date "
        "FROM work_orders WHERE hidden = 1 ORDER BY wo_number"
    ).fetchall()
    return [dict(r) for r in rows]


def toggle_op_hidden(conn, op_id):
    """Toggle the hidden flag on a single operation. Returns new hidden value."""
    row = conn.execute(
        "SELECT hidden FROM operations WHERE id=?", (op_id,)
    ).fetchone()
    if not row:
        return None
    new_val = 0 if row["hidden"] else 1
    conn.execute(
        "UPDATE operations SET hidden=? WHERE id=?", (new_val, op_id)
    )
    conn.commit()
    return new_val


def get_hidden_operations(conn):
    """Return all individually hidden operations with WO context."""
    rows = conn.execute(
        "SELECT o.id, o.wo_number, o.op_number, o.op_name, o.est_hours, o.override_hours, "
        "w.part_number, w.part_name, w.customer "
        "FROM operations o "
        "JOIN work_orders w ON o.wo_number = w.wo_number "
        "WHERE COALESCE(o.hidden, 0) = 1 "
        "ORDER BY o.wo_number, o.op_number"
    ).fetchall()
    return [dict(r) for r in rows]


# ── Schedule Push (slide past-due incomplete blocks forward) ─────────────────

_push_log = logging.getLogger("scheduler.push")

BH_START = 5   # Business hours start (5 AM)
BH_END = 18    # Business hours end (6 PM)


def _snap_to_business(dt):
    """Advance dt to the next valid business hour if outside hours or on weekend."""
    while dt.weekday() >= 5:
        dt = (dt + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
    if dt.hour < BH_START:
        dt = dt.replace(hour=BH_START, minute=0, second=0, microsecond=0)
    elif dt.hour >= BH_END:
        dt = (dt + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
        while dt.weekday() >= 5:
            dt = (dt + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
    return dt


def _add_bh(start, hours):
    """Add business hours to a datetime, skipping nights and weekends."""
    remaining = hours
    cursor = _snap_to_business(start)
    for _ in range(500):
        if remaining <= 0:
            break
        day_end = cursor.replace(hour=BH_END, minute=0, second=0, microsecond=0)
        available = (day_end - cursor).total_seconds() / 3600
        if remaining <= available:
            cursor += timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= available
            cursor = (cursor + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
            while cursor.weekday() >= 5:
                cursor = (cursor + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
    return cursor


def _parse_dt(s):
    """Parse ISO datetime string to naive datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00") if s.endswith("Z") else s)
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _fmt_dt(dt):
    """Format datetime as ISO string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def push_schedule(conn=None):
    """Slide past-due incomplete blocks forward to now, pushing subsequent blocks.

    For each machine:
    1. Find blocks where end_time < now AND status != 'complete' AND not locked
    2. Slide that block so it starts at now (snapped to business hours)
    3. Push any subsequent blocks on the same machine forward to avoid overlaps

    Returns count of blocks moved.
    """
    close = conn is None
    if close:
        conn = get_db()

    now = datetime.now()
    now_bh = _snap_to_business(now)
    moved = 0

    # Get all machines that have scheduled blocks
    machine_rows = conn.execute(
        "SELECT DISTINCT machine_id FROM schedule_blocks WHERE status != 'complete'"
    ).fetchall()

    for mrow in machine_rows:
        mid = mrow["machine_id"]

        # Get all non-complete blocks on this machine, sorted by start_time
        blocks = conn.execute(
            "SELECT sb.id, sb.start_time, sb.end_time, sb.status, sb.is_locked, "
            "       o.est_hours, o.override_hours "
            "FROM schedule_blocks sb "
            "JOIN operations o ON sb.operation_id = o.id "
            "WHERE sb.machine_id = ? AND sb.status != 'complete' "
            "ORDER BY sb.start_time",
            (mid,),
        ).fetchall()

        if not blocks:
            continue

        # Track the earliest available cursor for this machine
        cursor = None

        for b in blocks:
            block_id = b["id"]
            start = _parse_dt(b["start_time"])
            end = _parse_dt(b["end_time"])
            is_locked = b["is_locked"]

            # Calculate duration in business hours from the block's actual span
            hours = b["override_hours"] or b["est_hours"] or 0
            if hours <= 0:
                # Fall back to raw time difference
                hours = (end - start).total_seconds() / 3600

            if is_locked:
                # Locked blocks don't move, but they constrain the cursor
                cursor = max(cursor, end) if cursor else end
                continue

            # Does this block need pushing?
            needs_push = end <= now  # block is entirely in the past
            if cursor and start < cursor:
                needs_push = True  # block overlaps with a previously pushed block

            if not needs_push:
                # This block is in the future and not overlapping — update cursor and skip
                cursor = max(cursor, end) if cursor else end
                continue

            # Calculate new start: max of now_bh and cursor (to chain after previous)
            new_start = now_bh
            if cursor and cursor > new_start:
                new_start = _snap_to_business(cursor)

            new_end = _add_bh(new_start, hours)

            # Only update if actually different
            if abs((new_start - start).total_seconds()) < 60:
                cursor = max(cursor, new_end) if cursor else new_end
                continue

            conn.execute(
                "UPDATE schedule_blocks SET start_time=?, end_time=? WHERE id=?",
                (_fmt_dt(new_start), _fmt_dt(new_end), block_id),
            )
            moved += 1
            cursor = new_end

    if moved > 0:
        conn.commit()
        _push_log.info("Pushed %d blocks forward", moved)

    if close:
        conn.close()

    return moved
