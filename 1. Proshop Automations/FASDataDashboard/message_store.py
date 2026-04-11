"""
Message storage for Shop Hub messaging system.
Uses a separate SQLite database at C:\\FASData\\shophub.db.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ShopHub.Messages")

SHOPHUB_DB = r"C:\FASData\shophub.db"


class MessageStore:
    """SQLite-backed message storage with machine and shop-wide channels."""

    def __init__(self, db_path: str = SHOPHUB_DB):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    author TEXT NOT NULL,
                    machine_id TEXT,
                    work_order TEXT,
                    message TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_timestamp
                ON messages(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_machine
                ON messages(machine_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def add_message(self, author: str, message: str,
                    machine_id: str | None = None,
                    work_order: str | None = None) -> dict:
        """Insert a new message. Returns the created message dict."""
        ts = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO messages (timestamp, author, machine_id, work_order, message)
                   VALUES (?, ?, ?, ?, ?)""",
                (ts, author, machine_id, work_order, message),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "timestamp": ts,
                "author": author,
                "machine_id": machine_id,
                "work_order": work_order,
                "message": message,
            }
        finally:
            conn.close()

    def get_messages(self, machine_id: str | None = None, limit: int = 20) -> list[dict]:
        """Get recent messages for a machine or shop-wide (machine_id=None)."""
        conn = self._get_conn()
        try:
            if machine_id:
                rows = conn.execute(
                    """SELECT * FROM messages
                       WHERE machine_id = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (machine_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM messages
                       WHERE machine_id IS NULL
                       ORDER BY timestamp DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            # Return in chronological order (oldest first)
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def get_all_recent(self, limit: int = 50) -> list[dict]:
        """Get all recent messages across all channels."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM messages
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()
