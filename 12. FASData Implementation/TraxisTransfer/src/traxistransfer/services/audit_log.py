"""SQLite audit log for transfer history, folder memory, and preferences."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from traxistransfer.constants import DB_PATH, FALLBACK_DB_PATH, FASDATA_DIR


def get_db_path() -> Path:
    """Return the database path, preferring C:\\FASData."""
    if FASDATA_DIR.exists():
        return DB_PATH
    return FALLBACK_DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with WAL mode and busy timeout."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            machine_id TEXT NOT NULL,
            machine_name TEXT NOT NULL,
            driver TEXT NOT NULL,
            direction TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            program_number TEXT,
            file_size_bytes INTEGER,
            duration_seconds REAL,
            operator TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            error_message TEXT,
            work_order TEXT,
            part_number TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_transfers_timestamp ON transfers(timestamp);
        CREATE INDEX IF NOT EXISTS idx_transfers_machine ON transfers(machine_id);

        CREATE TABLE IF NOT EXISTS folder_memory (
            machine_id TEXT PRIMARY KEY,
            last_folder TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()


def log_transfer(
    conn: sqlite3.Connection,
    machine_id: str,
    machine_name: str,
    driver: str,
    direction: str,
    file_path: str,
    file_name: str,
    program_number: str = "",
    file_size_bytes: int = 0,
    duration_seconds: float = 0.0,
    success: bool = True,
    error_message: str = "",
    work_order: str = "",
    part_number: str = "",
) -> int:
    """Log a transfer and return the row ID."""
    operator = ""
    try:
        operator = os.getlogin()
    except OSError:
        pass

    cursor = conn.execute(
        """INSERT INTO transfers
           (machine_id, machine_name, driver, direction, file_path, file_name,
            program_number, file_size_bytes, duration_seconds, operator,
            success, error_message, work_order, part_number)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (machine_id, machine_name, driver, direction, file_path, file_name,
         program_number, file_size_bytes, duration_seconds, operator,
         1 if success else 0, error_message, work_order, part_number),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_transfers(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Return the most recent transfers."""
    rows = conn.execute(
        "SELECT * FROM transfers ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_folder_memory(conn: sqlite3.Connection, machine_id: str, folder: str) -> None:
    """Save the last-used folder for a machine."""
    conn.execute(
        """INSERT INTO folder_memory (machine_id, last_folder, updated_at)
           VALUES (?, ?, datetime('now', 'localtime'))
           ON CONFLICT(machine_id) DO UPDATE SET
             last_folder = excluded.last_folder,
             updated_at = excluded.updated_at""",
        (machine_id, folder),
    )
    conn.commit()


def get_folder_memory(conn: sqlite3.Connection, machine_id: str) -> str | None:
    """Get the remembered folder for a machine."""
    row = conn.execute(
        "SELECT last_folder FROM folder_memory WHERE machine_id = ?",
        (machine_id,),
    ).fetchone()
    return row["last_folder"] if row else None


def save_preference(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Save a preference value."""
    conn.execute(
        """INSERT INTO preferences (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, value),
    )
    conn.commit()


def get_preference(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    """Get a preference value."""
    row = conn.execute(
        "SELECT value FROM preferences WHERE key = ?",
        (key,),
    ).fetchone()
    return row["value"] if row else default


def get_last_sent_to_machine(conn: sqlite3.Connection, machine_id: str) -> dict | None:
    """Return the most recent successful SEND to a machine, or None."""
    row = conn.execute(
        """SELECT * FROM transfers
           WHERE machine_id = ? AND direction = 'send' AND success = 1
           ORDER BY timestamp DESC, id DESC LIMIT 1""",
        (machine_id,),
    ).fetchone()
    return dict(row) if row else None
