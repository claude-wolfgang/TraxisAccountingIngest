"""Photo Upload Service — SQLite database layer."""

import sqlite3
from datetime import datetime, timezone

import config


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS photos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type     TEXT NOT NULL,
            entity_id       TEXT NOT NULL,
            entity_name     TEXT DEFAULT '',
            operation_number TEXT DEFAULT '',
            operation_desc  TEXT DEFAULT '',
            file_path       TEXT NOT NULL,
            note            TEXT DEFAULT '',
            status          TEXT DEFAULT 'pending',
            error_message   TEXT,
            retry_count     INTEGER DEFAULT 0,
            proshop_url     TEXT,
            created_at      TEXT NOT NULL,
            uploaded_at     TEXT,
            updated_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(status);
        CREATE INDEX IF NOT EXISTS idx_photos_entity ON photos(entity_type, entity_id);

        CREATE TABLE IF NOT EXISTS entity_cache (
            entity_type  TEXT NOT NULL,
            entity_id    TEXT NOT NULL,
            entity_name  TEXT DEFAULT '',
            proshop_url  TEXT DEFAULT '',
            cached_at    TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        );
    """)
    conn.close()


# ── Photo CRUD ────────────────────────────────────────────────────────────

def insert_photo(entity_type, entity_id, entity_name, file_path,
                  note="", proshop_url="", operation_number="", operation_desc=""):
    now = _now()
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO photos
           (entity_type, entity_id, entity_name, operation_number, operation_desc,
            file_path, note, proshop_url, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_id, entity_name, operation_number, operation_desc,
         file_path, note, proshop_url, now, now),
    )
    photo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return photo_id


def get_photo(photo_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_photos(limit=10):
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM photos
           WHERE status IN ('pending', 'failed')
           AND retry_count < ?
           ORDER BY created_at ASC LIMIT ?""",
        (config.MAX_RETRIES, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_photos(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM photos ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_photo_status(photo_id, status, error_message=None):
    now = _now()
    conn = get_connection()
    if status == "uploaded":
        conn.execute(
            "UPDATE photos SET status=?, uploaded_at=?, updated_at=?, error_message=NULL WHERE id=?",
            (status, now, now, photo_id),
        )
    else:
        conn.execute(
            "UPDATE photos SET status=?, error_message=?, updated_at=? WHERE id=?",
            (status, error_message, now, photo_id),
        )
    conn.commit()
    conn.close()


def increment_retry(photo_id):
    now = _now()
    conn = get_connection()
    conn.execute(
        "UPDATE photos SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
        (now, photo_id),
    )
    conn.commit()
    conn.close()


def get_queue_stats():
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM photos GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


# ── Entity Cache ──────────────────────────────────────────────────────────

def cache_entity(entity_type, entity_id, entity_name="", proshop_url=""):
    now = _now()
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO entity_cache
           (entity_type, entity_id, entity_name, proshop_url, cached_at)
           VALUES (?, ?, ?, ?, ?)""",
        (entity_type, entity_id, entity_name, proshop_url, now),
    )
    conn.commit()
    conn.close()


def get_cached_entity(entity_type, entity_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM entity_cache WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
