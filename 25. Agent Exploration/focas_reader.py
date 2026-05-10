"""
FOCAS machine monitoring database reader for the Data Quality Agent.
Read-only access to monitoring.db (SQLite) collected by FocasMonitor.

Database location:
  Primary:  C:\\FASData\\monitoring.db (collector PC)
  Fallback: ~/Dropbox/MACHINE COMM Traxis/FASData/monitoring.db (sync copy)
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


# Spindle speed values >= this are FOCAS error/flag codes, not real RPM
SPINDLE_SPEED_MAX_VALID = 100_000


class FocasReader:
    """Read-only interface to the FOCAS monitoring SQLite database."""

    def __init__(self, db_path):
        if not db_path or not Path(db_path).exists():
            raise FileNotFoundError(f"FOCAS database not found: {db_path}")
        self.db_path = str(db_path)

    def _connect(self):
        """Open a read-only connection."""
        conn = sqlite3.connect(
            f"file:{self.db_path}?mode=ro",
            uri=True,
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        # Note: WAL pragma omitted because connection is read-only.
        # busy_timeout is fine on read-only connections.
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # ── Database Health ──────────────────────────────────────────────────

    def check_health(self):
        """Verify database is accessible and has recent data."""
        try:
            conn = self._connect()
            # Check latest sample timestamp per machine
            rows = conn.execute("""
                SELECT machine_id,
                       MAX(timestamp) as last_sample,
                       COUNT(*) as total_samples
                FROM machine_samples
                GROUP BY machine_id
                ORDER BY machine_id
            """).fetchall()
            conn.close()

            now = datetime.now()
            machines = {}
            for row in rows:
                last = datetime.fromisoformat(row["last_sample"])
                # Strip timezone info if present for consistent comparison
                if last.tzinfo is not None:
                    last = last.replace(tzinfo=None)
                age_minutes = (now - last).total_seconds() / 60
                machines[row["machine_id"]] = {
                    "last_sample": row["last_sample"],
                    "total_samples": row["total_samples"],
                    "age_minutes": round(age_minutes, 1),
                    "stale": age_minutes > 5,  # >5 min = problem
                }

            return {"healthy": True, "machines": machines}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    # ── Schema Verification ──────────────────────────────────────────────

    def get_schema_info(self):
        """Return table names and column counts for schema drift detection."""
        conn = self._connect()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        schema = {}
        for t in tables:
            name = t["name"]
            cols = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
            schema[name] = {
                "column_count": len(cols),
                "columns": [c["name"] for c in cols],
            }

        conn.close()
        return schema

    # ── Machine Status ───────────────────────────────────────────────────

    def get_latest_status(self):
        """Get the most recent sample for each machine."""
        conn = self._connect()
        rows = conn.execute("""
            SELECT ms.*
            FROM machine_samples ms
            INNER JOIN (
                SELECT machine_id, MAX(timestamp) as max_ts
                FROM machine_samples
                GROUP BY machine_id
            ) latest ON ms.machine_id = latest.machine_id
                     AND ms.timestamp = latest.max_ts
            ORDER BY ms.machine_id
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_machine_status_at(self, machine_id, timestamp):
        """Get the sample closest to a given timestamp for a machine."""
        conn = self._connect()
        row = conn.execute("""
            SELECT * FROM machine_samples
            WHERE machine_id = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (machine_id, timestamp)).fetchone()
        conn.close()
        return dict(row) if row else None

    # ── Utilization ──────────────────────────────────────────────────────

    def get_utilization_today(self):
        """Calculate today's utilization per machine (6 AM - 7 PM shift)."""
        conn = self._connect()
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT
                machine_id,
                COUNT(*) as total_samples,
                SUM(CASE
                    WHEN connected = 1
                    AND (run_status IN ('STRT','MSTR')
                         OR (spindle_speed > 0 AND spindle_speed < ?))
                    THEN 1 ELSE 0
                END) as running_samples,
                SUM(CASE
                    WHEN connected = 1
                    AND (run_status IN ('STRT','MSTR')
                         OR (spindle_speed > 0 AND spindle_speed < ?))
                    AND (motion IN ('MTN','DWL','MOTION')
                         OR feed_rate > 0)
                    THEN 1 ELSE 0
                END) as cutting_samples,
                SUM(CASE WHEN connected = 1 THEN 1 ELSE 0 END) as connected_samples
            FROM machine_samples
            WHERE date(timestamp, 'localtime') = ?
              AND CAST(strftime('%H', timestamp, 'localtime') AS INTEGER) BETWEEN 6 AND 18
            GROUP BY machine_id
            ORDER BY machine_id
        """, (SPINDLE_SPEED_MAX_VALID, SPINDLE_SPEED_MAX_VALID, today)).fetchall()
        conn.close()

        results = {}
        for row in rows:
            total = row["total_samples"]
            running = row["running_samples"]
            cutting = row["cutting_samples"]
            connected = row["connected_samples"]
            results[row["machine_id"]] = {
                "total_samples": total,
                "running_samples": running,
                "cutting_samples": cutting,
                "connected_samples": connected,
                "utilization_pct": round(100.0 * running / total, 1) if total > 0 else 0,
                "cutting_pct": round(100.0 * cutting / total, 1) if total > 0 else 0,
                "connection_pct": round(100.0 * connected / total, 1) if total > 0 else 0,
            }
        return results

    def get_utilization_range(self, days=7):
        """Get daily utilization per machine over a date range."""
        conn = self._connect()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT
                machine_id,
                date(timestamp, 'localtime') as sample_date,
                COUNT(*) as total_samples,
                SUM(CASE
                    WHEN connected = 1
                    AND (run_status IN ('STRT','MSTR')
                         OR (spindle_speed > 0 AND spindle_speed < ?))
                    THEN 1 ELSE 0
                END) as running_samples
            FROM machine_samples
            WHERE date(timestamp, 'localtime') >= ?
              AND CAST(strftime('%H', timestamp, 'localtime') AS INTEGER) BETWEEN 6 AND 18
            GROUP BY machine_id, sample_date
            ORDER BY machine_id, sample_date
        """, (SPINDLE_SPEED_MAX_VALID, start_date)).fetchall()
        conn.close()

        results = {}
        for row in rows:
            mid = row["machine_id"]
            if mid not in results:
                results[mid] = []
            total = row["total_samples"]
            results[mid].append({
                "date": row["sample_date"],
                "utilization_pct": round(100.0 * row["running_samples"] / total, 1) if total > 0 else 0,
                "samples": total,
            })
        return results

    # ── Program Detection ────────────────────────────────────────────────

    def get_active_programs(self, hours_back=4):
        """Identify programs that have been running recently."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        rows = conn.execute("""
            SELECT
                machine_id,
                program_number,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                COUNT(*) as sample_count,
                AVG(spindle_speed) as avg_spindle,
                AVG(feed_rate) as avg_feed
            FROM machine_samples
            WHERE timestamp > ?
              AND connected = 1
              AND program_number IS NOT NULL
              AND program_number > 0
              AND spindle_speed > 0
              AND spindle_speed < ?
            GROUP BY machine_id, program_number
            ORDER BY machine_id, sample_count DESC
        """, (cutoff, SPINDLE_SPEED_MAX_VALID)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Alarm History ────────────────────────────────────────────────────

    def get_recent_alarms(self, days=7):
        """Get alarms from the last N days."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                timestamp,
                machine_id,
                alarm_number,
                alarm_message,
                program_number,
                capture_session_id
            FROM alarm_history
            WHERE timestamp > ?
            ORDER BY timestamp DESC
        """, (cutoff,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_alarm_counts(self, days=7):
        """Get alarm frequency per machine over N days."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                machine_id,
                COUNT(*) as alarm_count,
                COUNT(DISTINCT alarm_number) as unique_alarms
            FROM alarm_history
            WHERE timestamp > ?
            GROUP BY machine_id
            ORDER BY alarm_count DESC
        """, (cutoff,)).fetchall()
        conn.close()
        return {row["machine_id"]: dict(row) for row in rows}

    # ── Data Collection Gaps ─────────────────────────────────────────────

    def find_collection_gaps(self, machine_id, days=3, gap_threshold_minutes=10):
        """Find gaps in data collection > threshold for a machine."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT timestamp
            FROM machine_samples
            WHERE machine_id = ?
              AND timestamp > ?
            ORDER BY timestamp
        """, (machine_id, cutoff)).fetchall()
        conn.close()

        gaps = []
        prev = None
        for row in rows:
            ts = datetime.fromisoformat(row["timestamp"])
            if prev:
                delta_min = (ts - prev).total_seconds() / 60
                if delta_min > gap_threshold_minutes:
                    gaps.append({
                        "start": prev.isoformat(),
                        "end": ts.isoformat(),
                        "gap_minutes": round(delta_min, 1),
                    })
            prev = ts
        return gaps

    # ── Tool Wear ────────────────────────────────────────────────────────

    def get_tool_wear_latest(self, machine_id=None):
        """Get latest tool wear readings per tool per machine."""
        conn = self._connect()
        where = "WHERE machine_id = ?" if machine_id else ""
        params = (machine_id,) if machine_id else ()
        rows = conn.execute(f"""
            SELECT tw.*
            FROM tool_wear_samples tw
            INNER JOIN (
                SELECT machine_id, tool_number, MAX(timestamp) as max_ts
                FROM tool_wear_samples
                {where}
                GROUP BY machine_id, tool_number
            ) latest ON tw.machine_id = latest.machine_id
                     AND tw.tool_number = latest.tool_number
                     AND tw.timestamp = latest.max_ts
            ORDER BY tw.machine_id, tw.tool_number
        """, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Tool Life ────────────────────────────────────────────────────────

    def get_tool_life_status(self, machine_id=None):
        """Get latest tool life remaining data."""
        conn = self._connect()
        where = "WHERE machine_id = ?" if machine_id else ""
        params = (machine_id,) if machine_id else ()
        rows = conn.execute(f"""
            SELECT tl.*
            FROM tool_life_samples tl
            INNER JOIN (
                SELECT machine_id, group_number, tool_number, MAX(timestamp) as max_ts
                FROM tool_life_samples
                {where}
                GROUP BY machine_id, group_number, tool_number
            ) latest ON tl.machine_id = latest.machine_id
                     AND tl.group_number = latest.group_number
                     AND tl.tool_number = latest.tool_number
                     AND tl.timestamp = latest.max_ts
            ORDER BY tl.machine_id, tl.group_number, tl.tool_number
        """, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Capture Traceability ─────────────────────────────────────────────

    def get_capture_sessions(self, days=30):
        """Get all unique capture sessions with sample counts."""
        conn = self._connect()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                capture_session_id,
                machine_id,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                COUNT(*) as sample_count,
                COUNT(DISTINCT capture_op_id) as unique_ops,
                COUNT(DISTINCT capture_tool_id) as unique_tools
            FROM machine_samples
            WHERE capture_session_id IS NOT NULL
              AND capture_session_id != ''
              AND timestamp > ?
            GROUP BY capture_session_id, machine_id
            ORDER BY first_seen DESC
        """, (cutoff,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Raw Query (for custom checks) ────────────────────────────────────

    def query(self, sql, params=()):
        """Execute an arbitrary read-only SQL query."""
        conn = self._connect()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
