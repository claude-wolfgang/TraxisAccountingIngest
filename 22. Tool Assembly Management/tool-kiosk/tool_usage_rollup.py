"""
FASData Tool Usage Rollup
=========================
Reads machine_samples and tool_wear_samples from monitoring.db,
joins against active assignments in tooling.db to accumulate:
  - Cutting minutes per holder/assembly/machine
  - Average and peak spindle load
  - Wear register deltas

Runs every 5 minutes via Windows Task Scheduler or overseer.
Does NOT modify monitoring.db (read-only).

Usage:
  python tool_usage_rollup.py              (single run)
  python tool_usage_rollup.py --loop 300   (loop every 300s)
"""

import sqlite3
import time
import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPT_DIR))

# ── Load .traxis.env credentials ────────────────────────────────────────────
_projects_dir = _SCRIPT_DIR.parent.parent
_home = Path.home()
_env_paths = [
    _home / ".traxis.env",
    _projects_dir / "1. Proshop Automations" / ".traxis.env",
    _projects_dir / "Keys" / ".traxis.env",
]
for _sub in [
    os.path.join("MACHINE COMM Traxis", "Proshop Automation and Claude Projects", "1. Proshop Automations"),
    os.path.join("MACHINE COMM Traxis", "Keys"),
]:
    _env_paths.append(_home / "Dropbox" / _sub / ".traxis.env")
    for _drive in "CDEFG":
        _env_paths.append(Path(f"{_drive}:\\Dropbox") / _sub / ".traxis.env")
for _ep in _env_paths:
    if _ep.exists():
        with open(_ep) as _f:
            for _line in _f:
                _line = _line.strip()
                if "=" in _line and not _line.startswith("#"):
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
        break

import config

MONITORING_DB = config.MONITORING_DB_PATH
TOOLING_DB = config.TOOLING_DB_PATH

_log_dir = _SCRIPT_DIR / "data" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
LOG_FILE = str(_log_dir / "tool_usage_rollup.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("rollup")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_monitoring_conn():
    """Read-only connection to FocasMonitor's monitoring.db."""
    if not os.path.exists(MONITORING_DB):
        log.error("monitoring.db not found at %s", MONITORING_DB)
        return None
    conn = sqlite3.connect(f"file:{MONITORING_DB}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_tooling_conn():
    conn = sqlite3.connect(TOOLING_DB, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def rollup():
    """Process new machine_samples since each segment's last_processed_at."""
    tooling = get_tooling_conn()
    monitoring = get_monitoring_conn()

    if not monitoring:
        tooling.close()
        return

    try:
        # Get all open usage segments (segment_end IS NULL)
        segments = tooling.execute("""
            SELECT s.*, a.pocket_number
            FROM tool_usage_segments s
            JOIN assignments a ON a.holder_id = s.holder_id
                AND a.machine_id = s.machine_id
                AND a.removed_at IS NULL
            WHERE s.segment_end IS NULL
        """).fetchall()

        if not segments:
            log.info("No open usage segments to process")
            monitoring.close()
            tooling.close()
            return

        log.info("Processing %d open usage segments", len(segments))
        now = _now()

        for seg in segments:
            segment_id = seg["segment_id"]
            machine_id = seg["machine_id"]
            pocket = seg["pocket_number"]
            since = seg["last_processed_at"] or seg["segment_start"]

            # Query machine_samples for this machine since last processed,
            # where tool_number matches the pocket and machine is cutting.
            # NOTE: datetime() normalises both sides to UTC — monitoring.db
            # stores local-with-offset (e.g. "…-05:00") while last_processed_at
            # is stored as UTC ("…Z").  Plain string comparison skips samples
            # whose local hour is numerically < the UTC hour.
            samples = monitoring.execute("""
                SELECT timestamp, spindle_speed, spindle_load,
                       tool_number, run_status, motion
                FROM machine_samples
                WHERE machine_id = ?
                  AND datetime(timestamp) > datetime(?)
                  AND tool_number = ?
                  AND connected = 1
                ORDER BY timestamp ASC
            """, (machine_id, since, pocket)).fetchall()

            if not samples:
                continue

            # Count cutting samples (run_status='STRT' or 'MSTR' and motion='MTN')
            cutting_samples = 0
            total_load = 0
            peak_load = seg["peak_spindle_load"] or 0

            for s in samples:
                rs = (s["run_status"] or "").upper()
                mo = (s["motion"] or "").upper()
                load = s["spindle_load"] or 0

                if rs in ("STRT", "MSTR") and mo == "MTN":
                    cutting_samples += 1
                    total_load += load
                    if load > peak_load:
                        peak_load = load

            # Each sample is ~60 seconds apart (pollIntervalSeconds)
            cutting_minutes = cutting_samples * 1.0  # 1 min per sample at 60s interval

            # Get wear data for this tool pocket (same datetime() fix)
            wear_rows = monitoring.execute("""
                SELECT length_wear, diameter_wear
                FROM tool_wear_samples
                WHERE machine_id = ?
                  AND datetime(timestamp) > datetime(?)
                  AND offset_number = ?
                ORDER BY timestamp ASC
            """, (machine_id, since, pocket)).fetchall()

            length_wear_end = seg["length_wear_end"]
            radius_wear_end = seg["radius_wear_end"]
            if wear_rows:
                # First wear reading becomes start if we don't have one
                if seg["length_wear_start"] is None:
                    tooling.execute(
                        """UPDATE tool_usage_segments
                           SET length_wear_start = ?, radius_wear_start = ?
                           WHERE segment_id = ?""",
                        (wear_rows[0]["length_wear"], wear_rows[0]["diameter_wear"],
                         segment_id),
                    )
                # Last wear reading is the current end
                length_wear_end = wear_rows[-1]["length_wear"]
                radius_wear_end = wear_rows[-1]["diameter_wear"]

            # Update the segment
            prev_cutting = seg["cutting_minutes"] or 0
            prev_samples = seg["sample_count"] or 0
            prev_avg = seg["avg_spindle_load"] or 0

            new_total_cutting = prev_cutting + cutting_minutes
            new_total_samples = prev_samples + cutting_samples
            if new_total_samples > 0:
                new_avg = ((prev_avg * prev_samples) + total_load) / new_total_samples
            else:
                new_avg = prev_avg

            tooling.execute("""
                UPDATE tool_usage_segments SET
                    cutting_minutes = ?,
                    sample_count = ?,
                    avg_spindle_load = ?,
                    peak_spindle_load = ?,
                    length_wear_end = ?,
                    radius_wear_end = ?,
                    last_processed_at = ?
                WHERE segment_id = ?
            """, (new_total_cutting, new_total_samples,
                  round(new_avg, 1), peak_load,
                  length_wear_end, radius_wear_end,
                  now, segment_id))

            log.info("Segment %d (%s/%s T%d): +%.1f min cutting, %d samples, peak %d%%",
                     segment_id, seg["holder_id"], machine_id, pocket,
                     cutting_minutes, cutting_samples, peak_load)

        tooling.commit()
        log.info("Rollup complete")

    except Exception as e:
        log.error("Rollup failed: %s", e, exc_info=True)
    finally:
        monitoring.close()
        tooling.close()


# ── ProShop Sync (RTA comments + toolLifeNow) ────────────────────────────────

# Track last-synced values to avoid unnecessary API calls
_last_synced = {}  # keyed by holder_id → comment string
_last_sync_time = 0
SYNC_INTERVAL = 3600  # seconds between syncs (1 hour)


def _build_rta_comment(holder_id, cutting_minutes, peak_load):
    """Build the standardized RTA comment string."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    peak_str = f" | Peak {peak_load}%" if peak_load else ""
    return f"{holder_id} | {cutting_minutes:.1f} min cutting{peak_str} | {today}"


def sync_to_proshop(force=False):
    """Push cutting time data to ProShop: RTA comments + pocket toolLifeNow.

    Only runs once per SYNC_INTERVAL (1 hour) unless force=True.
    """
    global _last_sync_time
    now = time.time()
    if not force and (now - _last_sync_time) < SYNC_INTERVAL:
        return

    if not config.PROSHOP_CLIENT_SECRET:
        log.warning("ProShop sync skipped: PROSHOP_CLIENT_SECRET not set")
        return

    from proshop_client import ProShopClient, GraphQLError
    import database as db

    tooling = get_tooling_conn()
    try:
        holders = db.get_holders_with_rta_usage(tooling)
    finally:
        tooling.close()

    if not holders:
        log.info("ProShop sync: no holders with RTAs to update")
        return

    client = ProShopClient(
        config.PROSHOP_GRAPHQL_URL,
        config.PROSHOP_TOKEN_URL,
        config.PROSHOP_CLIENT_ID,
        config.PROSHOP_CLIENT_SECRET,
        config.PROSHOP_SCOPE,
    )

    machines = config.MACHINES
    rta_updated = 0
    pocket_updated = 0
    skipped = 0
    errors = 0

    for h in holders:
        rta_num = h["rta_number"]
        cutting_min = h["total_cutting_minutes"]
        comment = _build_rta_comment(
            h["holder_id"], cutting_min, h["peak_spindle_load"],
        )

        # Skip if nothing changed since last sync
        if _last_synced.get(h["holder_id"]) == comment:
            skipped += 1
            continue

        # 1) Update RTA comment
        try:
            client.update_rta_comment(rta_num, comment)
            rta_updated += 1
            log.info("RTA %s updated: %s", rta_num, comment)
        except GraphQLError as e:
            errors += 1
            log.warning("RTA %s comment update failed: %s", rta_num, e)
        except Exception as e:
            errors += 1
            log.error("RTA %s comment error: %s", rta_num, e, exc_info=True)

        # 2) Update pocket toolLifeNow if holder is assigned to a machine
        machine_id = h.get("machine_id")
        pocket_number = h.get("pocket_number")
        if machine_id and pocket_number is not None:
            pot_id = machines.get(machine_id, {}).get("proshop_pot_id")
            if pot_id:
                life_str = f"{cutting_min:.1f} min"
                try:
                    client.update_work_cell_pocket(
                        pot_id, pocket_number, {"toolLifeNow": life_str})
                    pocket_updated += 1
                    log.info("Pocket %s T%d toolLifeNow: %s",
                             pot_id, pocket_number, life_str)
                except Exception as e:
                    errors += 1
                    log.warning("Pocket %s T%d update failed: %s",
                                pot_id, pocket_number, e)

        _last_synced[h["holder_id"]] = comment

    _last_sync_time = time.time()
    log.info("ProShop sync complete: %d RTA comments, %d pockets, %d skipped, %d errors",
             rta_updated, pocket_updated, skipped, errors)


def main():
    log.info("Tooling DB: %s", TOOLING_DB)
    log.info("Monitoring DB: %s", MONITORING_DB)
    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 300
        log.info("Running in loop mode, interval=%ds", interval)
        while True:
            rollup()
            sync_to_proshop()
            time.sleep(interval)
    else:
        rollup()
        sync_to_proshop(force=True)


if __name__ == "__main__":
    main()
