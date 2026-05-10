"""
Tooling database module — C:\\FASData\\tooling.db

Manages holders, assemblies, assignments, usage segments, and activity log.
Uses WAL mode and busy_timeout=5000 to avoid locking issues with concurrent readers.
"""

import sqlite3
import json
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_connection(db_path):
    """Open a connection with WAL mode and busy timeout."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path):
    """Create all tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS holders (
            holder_id       TEXT PRIMARY KEY,
            holder_type     TEXT NOT NULL DEFAULT '',
            collet_size     TEXT NOT NULL DEFAULT '',
            holder_length   INTEGER,
            serial_number   TEXT NOT NULL DEFAULT '',
            default_tool    TEXT,
            notes           TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'active',
            created_at      TEXT NOT NULL,
            retired_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS assemblies (
            assembly_id             INTEGER PRIMARY KEY AUTOINCREMENT,
            holder_id               TEXT NOT NULL REFERENCES holders(holder_id),
            proshop_tool_number     TEXT NOT NULL DEFAULT '',
            tool_description        TEXT NOT NULL DEFAULT '',
            ooh_inches              REAL,
            rta_number              TEXT,
            measured_length         REAL,
            measured_diameter       REAL,
            measured_at             TEXT,
            installed_at            TEXT NOT NULL,
            retired_at              TEXT,
            retire_reason           TEXT,
            installed_by            TEXT NOT NULL DEFAULT '',
            retired_by              TEXT
        );

        CREATE TABLE IF NOT EXISTS assignments (
            assignment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            holder_id       TEXT NOT NULL REFERENCES holders(holder_id),
            machine_id      TEXT NOT NULL,
            pocket_number   INTEGER NOT NULL,
            work_order      TEXT,
            assigned_at     TEXT NOT NULL,
            removed_at      TEXT,
            assigned_by     TEXT NOT NULL DEFAULT '',
            removed_by      TEXT
        );

        CREATE TABLE IF NOT EXISTS tool_usage_segments (
            segment_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            holder_id           TEXT NOT NULL REFERENCES holders(holder_id),
            assembly_id         INTEGER REFERENCES assemblies(assembly_id),
            machine_id          TEXT NOT NULL,
            work_order          TEXT,
            cutting_minutes     REAL NOT NULL DEFAULT 0,
            sample_count        INTEGER NOT NULL DEFAULT 0,
            avg_spindle_load    REAL,
            peak_spindle_load   INTEGER,
            length_wear_start   INTEGER,
            length_wear_end     INTEGER,
            radius_wear_start   INTEGER,
            radius_wear_end     INTEGER,
            segment_start       TEXT NOT NULL,
            segment_end         TEXT,
            last_processed_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            action          TEXT NOT NULL,
            holder_id       TEXT,
            machine_id      TEXT,
            pocket_number   INTEGER,
            employee        TEXT,
            details         TEXT
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_assemblies_holder
            ON assemblies(holder_id);
        CREATE INDEX IF NOT EXISTS idx_assemblies_active
            ON assemblies(holder_id, retired_at)
            WHERE retired_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_assignments_holder
            ON assignments(holder_id);
        CREATE INDEX IF NOT EXISTS idx_assignments_active
            ON assignments(holder_id, removed_at)
            WHERE removed_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_assignments_machine
            ON assignments(machine_id, removed_at)
            WHERE removed_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_usage_holder
            ON tool_usage_segments(holder_id);
        CREATE INDEX IF NOT EXISTS idx_usage_assembly
            ON tool_usage_segments(assembly_id);
        CREATE INDEX IF NOT EXISTS idx_activity_holder
            ON activity_log(holder_id);
        CREATE INDEX IF NOT EXISTS idx_activity_time
            ON activity_log(timestamp);
        CREATE TABLE IF NOT EXISTS tool_inventory (
            tool_number       TEXT PRIMARY KEY,
            tool_description  TEXT NOT NULL DEFAULT '',
            cabinet_location  TEXT NOT NULL DEFAULT '',
            qty_blue          INTEGER NOT NULL DEFAULT 0,
            qty_green         INTEGER NOT NULL DEFAULT 0,
            qty_yellow        INTEGER NOT NULL DEFAULT 0,
            qty_red           INTEGER NOT NULL DEFAULT 0,
            min_quantity      INTEGER,
            last_counted_at   TEXT,
            last_counted_by   TEXT,
            created_at        TEXT NOT NULL,
            notes             TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS inventory_counts (
            count_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_number   TEXT NOT NULL REFERENCES tool_inventory(tool_number),
            session_id    TEXT,
            qty_blue      INTEGER NOT NULL DEFAULT 0,
            qty_green     INTEGER NOT NULL DEFAULT 0,
            qty_yellow    INTEGER NOT NULL DEFAULT 0,
            qty_red       INTEGER NOT NULL DEFAULT 0,
            counted_at    TEXT NOT NULL,
            counted_by    TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS inventory_sessions (
            session_id     TEXT PRIMARY KEY,
            started_at     TEXT NOT NULL,
            completed_at   TEXT,
            started_by     TEXT NOT NULL DEFAULT '',
            total_items    INTEGER NOT NULL DEFAULT 0,
            counted_items  INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_inventory_counts_tool
            ON inventory_counts(tool_number);
        CREATE INDEX IF NOT EXISTS idx_inventory_counts_session
            ON inventory_counts(session_id);
    """)
    conn.commit()

    # Migrations for existing databases
    cols = {r[1] for r in conn.execute("PRAGMA table_info(holders)").fetchall()}
    if "holder_length" not in cols:
        conn.execute("ALTER TABLE holders ADD COLUMN holder_length INTEGER")
        conn.commit()
    if "serial_number" not in cols:
        conn.execute("ALTER TABLE holders ADD COLUMN serial_number TEXT NOT NULL DEFAULT ''")
        conn.commit()

    asm_cols = {r[1] for r in conn.execute("PRAGMA table_info(assemblies)").fetchall()}
    if "rta_number" not in asm_cols:
        conn.execute("ALTER TABLE assemblies ADD COLUMN rta_number TEXT")
        conn.commit()

    # Add rta_number to holders (permanent RTA per holder)
    if "rta_number" not in cols:
        conn.execute("ALTER TABLE holders ADD COLUMN rta_number TEXT")
        conn.commit()
        # Migrate: copy RTA from active assembly to holder
        conn.execute("""
            UPDATE holders
            SET rta_number = (
                SELECT a.rta_number FROM assemblies a
                WHERE a.holder_id = holders.holder_id
                  AND a.retired_at IS NULL
                  AND a.rta_number IS NOT NULL
                ORDER BY a.installed_at DESC LIMIT 1
            )
        """)
        conn.commit()

    conn.close()


def log_activity(conn, action, holder_id=None, machine_id=None,
                 pocket_number=None, employee=None, details=None):
    """Insert an activity log entry."""
    detail_json = json.dumps(details) if details else None
    conn.execute(
        """INSERT INTO activity_log
           (timestamp, action, holder_id, machine_id, pocket_number, employee, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (_now(), action, holder_id, machine_id, pocket_number, employee, detail_json),
    )


# ── Holders ──────────────────────────────────────────────────────────────────

def next_holder_id(conn):
    """Return the next available holder ID (e.g., H-0048).

    Finds the highest numeric suffix among existing H-XXXX IDs and returns
    the next one, zero-padded to 4 digits.  Starts at H-0001 if no holders exist.
    """
    rows = conn.execute(
        "SELECT holder_id FROM holders ORDER BY holder_id DESC"
    ).fetchall()
    max_num = 0
    for row in rows:
        hid = row["holder_id"] or ""
        # Match H-XXXX pattern and extract the number
        if hid.startswith("H-"):
            try:
                num = int(hid[2:])
                if num > max_num:
                    max_num = num
            except ValueError:
                continue
    return f"H-{max_num + 1:04d}"


def register_holder(conn, holder_id, holder_type="", collet_size="",
                    holder_length=None, serial_number="", default_tool=None,
                    notes="", employee=""):
    """Register a new holder. Returns the holder row."""
    now = _now()
    conn.execute(
        """INSERT INTO holders
           (holder_id, holder_type, collet_size, holder_length, serial_number,
            default_tool, notes, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (holder_id, holder_type, collet_size, holder_length, serial_number,
         default_tool, notes, now),
    )
    log_activity(conn, "register_holder", holder_id=holder_id, employee=employee,
                 details={"holder_type": holder_type, "collet_size": collet_size,
                          "holder_length": holder_length,
                          "serial_number": serial_number})
    conn.commit()
    return get_holder(conn, holder_id)


def get_holder(conn, holder_id):
    """Get a single holder by ID, or None."""
    row = conn.execute("SELECT * FROM holders WHERE holder_id = ?", (holder_id,)).fetchone()
    return dict(row) if row else None


def list_holders(conn, status="active"):
    """List all holders with given status."""
    rows = conn.execute(
        "SELECT * FROM holders WHERE status = ? ORDER BY holder_id", (status,)
    ).fetchall()
    return [dict(r) for r in rows]


def retire_holder(conn, holder_id, employee=""):
    """Retire a holder (status='retired')."""
    now = _now()
    conn.execute(
        "UPDATE holders SET status = 'retired', retired_at = ? WHERE holder_id = ?",
        (now, holder_id),
    )
    log_activity(conn, "retire_holder", holder_id=holder_id, employee=employee)
    conn.commit()


# ── Assemblies ───────────────────────────────────────────────────────────────

def install_cutter(conn, holder_id, proshop_tool_number="", tool_description="",
                   ooh_inches=None, employee=""):
    """Install a cutter into a holder. Returns the new assembly row."""
    now = _now()
    cur = conn.execute(
        """INSERT INTO assemblies
           (holder_id, proshop_tool_number, tool_description, ooh_inches,
            installed_at, installed_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (holder_id, proshop_tool_number, tool_description, ooh_inches, now, employee),
    )
    assembly_id = cur.lastrowid
    log_activity(conn, "install_cutter", holder_id=holder_id, employee=employee,
                 details={"assembly_id": assembly_id,
                          "proshop_tool_number": proshop_tool_number,
                          "tool_description": tool_description,
                          "ooh_inches": ooh_inches})
    conn.commit()
    return get_assembly(conn, assembly_id)


def retire_cutter(conn, assembly_id, reason="worn", employee=""):
    """Retire the current cutter assembly."""
    now = _now()
    conn.execute(
        """UPDATE assemblies
           SET retired_at = ?, retire_reason = ?, retired_by = ?
           WHERE assembly_id = ?""",
        (now, reason, employee, assembly_id),
    )
    row = get_assembly(conn, assembly_id)
    if row:
        log_activity(conn, "retire_cutter", holder_id=row["holder_id"],
                     employee=employee,
                     details={"assembly_id": assembly_id, "reason": reason})
    conn.commit()
    return row


def get_assembly(conn, assembly_id):
    """Get a single assembly by ID."""
    row = conn.execute("SELECT * FROM assemblies WHERE assembly_id = ?",
                       (assembly_id,)).fetchone()
    return dict(row) if row else None


def get_active_assembly(conn, holder_id):
    """Get the current (non-retired) assembly for a holder, or None."""
    row = conn.execute(
        """SELECT * FROM assemblies
           WHERE holder_id = ? AND retired_at IS NULL
           ORDER BY installed_at DESC LIMIT 1""",
        (holder_id,),
    ).fetchone()
    return dict(row) if row else None


def set_rta_number(conn, assembly_id, rta_number):
    """Set the ProShop RTA number on an assembly."""
    conn.execute(
        "UPDATE assemblies SET rta_number = ? WHERE assembly_id = ?",
        (rta_number, assembly_id),
    )
    conn.commit()


def set_holder_rta_number(conn, holder_id, rta_number):
    """Set the permanent ProShop RTA number on a holder."""
    conn.execute(
        "UPDATE holders SET rta_number = ? WHERE holder_id = ?",
        (rta_number, holder_id),
    )
    conn.commit()


def get_assembly_history(conn, holder_id):
    """Get all assemblies for a holder, newest first."""
    rows = conn.execute(
        "SELECT * FROM assemblies WHERE holder_id = ? ORDER BY installed_at DESC",
        (holder_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Assignments ──────────────────────────────────────────────────────────────

def assign_to_machine(conn, holder_id, machine_id, pocket_number,
                      work_order=None, employee=""):
    """Assign a holder to a machine pocket. Returns the new assignment row."""
    now = _now()
    cur = conn.execute(
        """INSERT INTO assignments
           (holder_id, machine_id, pocket_number, work_order, assigned_at, assigned_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (holder_id, machine_id, pocket_number, work_order, now, employee),
    )
    assignment_id = cur.lastrowid
    log_activity(conn, "assign_to_machine", holder_id=holder_id,
                 machine_id=machine_id, pocket_number=pocket_number,
                 employee=employee,
                 details={"assignment_id": assignment_id, "work_order": work_order})
    conn.commit()
    return get_assignment(conn, assignment_id)


def remove_from_machine(conn, assignment_id, employee=""):
    """Remove a holder from its machine pocket."""
    now = _now()
    conn.execute(
        "UPDATE assignments SET removed_at = ?, removed_by = ? WHERE assignment_id = ?",
        (now, employee, assignment_id),
    )
    row = get_assignment(conn, assignment_id)
    if row:
        log_activity(conn, "remove_from_machine", holder_id=row["holder_id"],
                     machine_id=row["machine_id"],
                     pocket_number=row["pocket_number"],
                     employee=employee,
                     details={"assignment_id": assignment_id})
    conn.commit()
    return row


def get_assignment(conn, assignment_id):
    """Get a single assignment by ID."""
    row = conn.execute("SELECT * FROM assignments WHERE assignment_id = ?",
                       (assignment_id,)).fetchone()
    return dict(row) if row else None


def get_active_assignment(conn, holder_id):
    """Get the current (non-removed) assignment for a holder, or None."""
    row = conn.execute(
        """SELECT * FROM assignments
           WHERE holder_id = ? AND removed_at IS NULL
           ORDER BY assigned_at DESC LIMIT 1""",
        (holder_id,),
    ).fetchone()
    return dict(row) if row else None


def get_machine_pockets(conn, machine_id):
    """Get all active assignments for a machine, ordered by pocket number."""
    rows = conn.execute(
        """SELECT a.*, asm.proshop_tool_number, asm.tool_description,
                  asm.ooh_inches, h.rta_number
           FROM assignments a
           LEFT JOIN assemblies asm
             ON asm.holder_id = a.holder_id AND asm.retired_at IS NULL
           LEFT JOIN holders h
             ON h.holder_id = a.holder_id
           WHERE a.machine_id = ? AND a.removed_at IS NULL
           ORDER BY a.pocket_number""",
        (machine_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_assignment_history(conn, holder_id):
    """Get all assignments for a holder, newest first."""
    rows = conn.execute(
        "SELECT * FROM assignments WHERE holder_id = ? ORDER BY assigned_at DESC",
        (holder_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Usage Segments ───────────────────────────────────────────────────────────

def open_usage_segment(conn, holder_id, assembly_id, machine_id, work_order=None):
    """Open a new usage tracking segment."""
    now = _now()
    cur = conn.execute(
        """INSERT INTO tool_usage_segments
           (holder_id, assembly_id, machine_id, work_order, segment_start)
           VALUES (?, ?, ?, ?, ?)""",
        (holder_id, assembly_id, machine_id, work_order, now),
    )
    conn.commit()
    return cur.lastrowid


def close_usage_segment(conn, segment_id):
    """Close an open usage segment."""
    now = _now()
    conn.execute(
        "UPDATE tool_usage_segments SET segment_end = ? WHERE segment_id = ?",
        (now, segment_id),
    )
    conn.commit()


def get_open_segment(conn, holder_id, machine_id):
    """Get the open (no segment_end) usage segment for a holder on a machine."""
    row = conn.execute(
        """SELECT * FROM tool_usage_segments
           WHERE holder_id = ? AND machine_id = ? AND segment_end IS NULL
           ORDER BY segment_start DESC LIMIT 1""",
        (holder_id, machine_id),
    ).fetchone()
    return dict(row) if row else None


def get_usage_summary(conn, holder_id):
    """Get total usage stats for a holder across all segments."""
    row = conn.execute(
        """SELECT
             COALESCE(SUM(cutting_minutes), 0) as total_cutting_minutes,
             COALESCE(SUM(sample_count), 0) as total_samples,
             MAX(peak_spindle_load) as overall_peak_spindle_load,
             COUNT(*) as segment_count
           FROM tool_usage_segments
           WHERE holder_id = ?""",
        (holder_id,),
    ).fetchone()
    return dict(row) if row else {}


def get_usage_summary_for_assembly(conn, assembly_id):
    """Get total usage stats for a specific assembly."""
    row = conn.execute(
        """SELECT
             COALESCE(SUM(cutting_minutes), 0) as total_cutting_minutes,
             COALESCE(SUM(sample_count), 0) as total_samples,
             MAX(peak_spindle_load) as overall_peak_spindle_load,
             COUNT(*) as segment_count
           FROM tool_usage_segments
           WHERE assembly_id = ?""",
        (assembly_id,),
    ).fetchone()
    return dict(row) if row else {}


def get_holders_with_rta_usage(conn):
    """Get usage stats for all active holders with an RTA and active assembly.

    Returns list of dicts: holder_id, rta_number, total_cutting_minutes,
    peak_spindle_load, machine_id, pocket_number.
    """
    rows = conn.execute("""
        SELECT
            h.holder_id,
            h.rta_number,
            COALESCE(SUM(s.cutting_minutes), 0) AS total_cutting_minutes,
            MAX(s.peak_spindle_load) AS peak_spindle_load,
            asn.machine_id,
            asn.pocket_number
        FROM holders h
        JOIN assemblies a
          ON a.holder_id = h.holder_id AND a.retired_at IS NULL
        LEFT JOIN assignments asn
          ON asn.holder_id = h.holder_id AND asn.removed_at IS NULL
        LEFT JOIN tool_usage_segments s
          ON s.holder_id = h.holder_id
        WHERE h.rta_number IS NOT NULL
          AND h.status = 'active'
        GROUP BY h.holder_id, h.rta_number, asn.machine_id, asn.pocket_number
    """).fetchall()
    return [dict(r) for r in rows]


# ── Activity Log ─────────────────────────────────────────────────────────────

def get_recent_activity(conn, limit=50, holder_id=None):
    """Get recent activity log entries."""
    if holder_id:
        rows = conn.execute(
            """SELECT * FROM activity_log
               WHERE holder_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (holder_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Holder Detail (composite) ────────────────────────────────────────────────

def get_holder_detail(conn, holder_id):
    """Get full holder info: holder + active assembly + active assignment + usage."""
    holder = get_holder(conn, holder_id)
    if not holder:
        return None
    holder["active_assembly"] = get_active_assembly(conn, holder_id)
    holder["active_assignment"] = get_active_assignment(conn, holder_id)
    holder["usage_summary"] = get_usage_summary(conn, holder_id)
    if holder["active_assembly"]:
        holder["assembly_usage"] = get_usage_summary_for_assembly(
            conn, holder["active_assembly"]["assembly_id"])
    else:
        holder["assembly_usage"] = {}
    return holder


# ── Tool Inventory ──────────────────────────────────────────────────────────

def add_inventory_item(conn, tool_number, description="", cabinet_location="",
                       min_quantity=None, notes=""):
    """Add a new item to the tool inventory."""
    now = _now()
    conn.execute(
        """INSERT INTO tool_inventory
           (tool_number, tool_description, cabinet_location, min_quantity, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tool_number, description, cabinet_location, min_quantity, notes, now),
    )
    log_activity(conn, "add_inventory_item",
                 details={"tool_number": tool_number, "description": description})
    conn.commit()
    return get_inventory_item(conn, tool_number)


def get_inventory_item(conn, tool_number):
    """Get a single inventory item with computed fields."""
    row = conn.execute(
        "SELECT * FROM tool_inventory WHERE tool_number = ?", (tool_number,)
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["qty_available"] = item["qty_green"] + item["qty_blue"]
    item["qty_total"] = (item["qty_blue"] + item["qty_green"] +
                         item["qty_yellow"] + item["qty_red"])
    return item


def list_inventory(conn):
    """List all inventory items sorted by tool_number."""
    rows = conn.execute(
        "SELECT * FROM tool_inventory ORDER BY CAST(REPLACE(LTRIM(tool_number, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '-', '') AS INTEGER), tool_number"
    ).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        item["qty_available"] = item["qty_green"] + item["qty_blue"]
        item["qty_total"] = (item["qty_blue"] + item["qty_green"] +
                             item["qty_yellow"] + item["qty_red"])
        items.append(item)
    return items


def search_inventory(conn, query):
    """Search inventory by tool_number or description."""
    like = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM tool_inventory
           WHERE tool_number LIKE ? OR tool_description LIKE ?
           ORDER BY CAST(REPLACE(LTRIM(tool_number, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '-', '') AS INTEGER), tool_number LIMIT 20""",
        (like, like),
    ).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        item["qty_available"] = item["qty_green"] + item["qty_blue"]
        item["qty_total"] = (item["qty_blue"] + item["qty_green"] +
                             item["qty_yellow"] + item["qty_red"])
        items.append(item)
    return items


def record_count(conn, tool_number, blue=0, green=0, yellow=0, red=0,
                 employee="", session_id=None):
    """Record a count: updates current quantities and inserts history row."""
    now = _now()
    # Update current quantities
    conn.execute(
        """UPDATE tool_inventory
           SET qty_blue = ?, qty_green = ?, qty_yellow = ?, qty_red = ?,
               last_counted_at = ?, last_counted_by = ?
           WHERE tool_number = ?""",
        (blue, green, yellow, red, now, employee, tool_number),
    )
    # Insert history row
    conn.execute(
        """INSERT INTO inventory_counts
           (tool_number, session_id, qty_blue, qty_green, qty_yellow, qty_red,
            counted_at, counted_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tool_number, session_id, blue, green, yellow, red, now, employee),
    )
    # Update session progress if applicable
    if session_id:
        conn.execute(
            """UPDATE inventory_sessions
               SET counted_items = counted_items + 1
               WHERE session_id = ?""",
            (session_id,),
        )
    log_activity(conn, "inventory_count",
                 details={"tool_number": tool_number,
                          "blue": blue, "green": green,
                          "yellow": yellow, "red": red,
                          "session_id": session_id},
                 employee=employee)
    conn.commit()
    return get_inventory_item(conn, tool_number)


def get_count_history(conn, tool_number, limit=20):
    """Get recent count history for one item."""
    rows = conn.execute(
        """SELECT * FROM inventory_counts
           WHERE tool_number = ?
           ORDER BY counted_at DESC LIMIT ?""",
        (tool_number, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def start_inventory_session(conn, employee=""):
    """Create an inventory session. Returns session_id + item list."""
    import uuid
    session_id = str(uuid.uuid4())[:8]
    now = _now()
    total = conn.execute("SELECT COUNT(*) FROM tool_inventory").fetchone()[0]
    conn.execute(
        """INSERT INTO inventory_sessions
           (session_id, started_at, started_by, total_items, counted_items)
           VALUES (?, ?, ?, ?, 0)""",
        (session_id, now, employee, total),
    )
    log_activity(conn, "start_inventory_session",
                 details={"session_id": session_id, "total_items": total},
                 employee=employee)
    conn.commit()
    return {"session_id": session_id, "total_items": total}


def get_session_progress(conn, session_id):
    """Get session info + which items still need counting."""
    session = conn.execute(
        "SELECT * FROM inventory_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        return None
    session = dict(session)

    # Items already counted in this session
    counted = conn.execute(
        "SELECT DISTINCT tool_number FROM inventory_counts WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    counted_set = {r[0] for r in counted}

    # All inventory items
    all_items = list_inventory(conn)
    remaining = [i for i in all_items if i["tool_number"] not in counted_set]
    counted_items = [i for i in all_items if i["tool_number"] in counted_set]

    session["remaining"] = remaining
    session["counted_list"] = counted_items
    return session


def get_session_next_item(conn, session_id):
    """Get the next uncounted item in a session."""
    counted = conn.execute(
        "SELECT DISTINCT tool_number FROM inventory_counts WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    counted_set = {r[0] for r in counted}

    all_items = conn.execute(
        "SELECT * FROM tool_inventory ORDER BY CAST(REPLACE(LTRIM(tool_number, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '-', '') AS INTEGER), tool_number"
    ).fetchall()
    for r in all_items:
        if r["tool_number"] not in counted_set:
            item = dict(r)
            item["qty_available"] = item["qty_green"] + item["qty_blue"]
            item["qty_total"] = (item["qty_blue"] + item["qty_green"] +
                                 item["qty_yellow"] + item["qty_red"])
            return item
    return None


def complete_session(conn, session_id):
    """Mark an inventory session as completed."""
    now = _now()
    conn.execute(
        "UPDATE inventory_sessions SET completed_at = ? WHERE session_id = ?",
        (now, session_id),
    )
    log_activity(conn, "complete_inventory_session",
                 details={"session_id": session_id})
    conn.commit()
