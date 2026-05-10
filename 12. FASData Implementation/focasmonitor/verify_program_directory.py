"""Verify the program_directory fix is capturing data on .71.

Reads C:\\FASData\\monitoring.db read-only and prints:
  1. program_directory population per machine
  2. Sample rows showing actual captured comments
  3. Recent monitoring activity (proves service is polling)
  4. Last write timestamps so you know how fresh the data is

Pair with verify_program_directory.bat for double-click usability.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB = Path(r"C:\FASData\monitoring.db")
if not DB.exists():
    print(f"FOCAS DB not found at {DB}")
    raise SystemExit(1)

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("=" * 60)
print("PROGRAM_DIRECTORY POPULATION (the fix's output)")
print("=" * 60)
rows = conn.execute(
    """SELECT machine_id,
              COUNT(*)                    AS rows,
              COUNT(program_comment)      AS with_comment,
              COUNT(DISTINCT program_number) AS distinct_progs,
              MIN(timestamp)              AS first_ts,
              MAX(timestamp)              AS last_ts
       FROM program_directory
       GROUP BY machine_id
       ORDER BY machine_id"""
).fetchall()
if not rows:
    print("  (still empty - fix not yet capturing data)")
    print("  Likely causes if machines were running today:")
    print("    - cnc_rdprogdir3 returned non-zero - check Application event log")
    print("    - FANUC needs MEM/EDIT mode to allow directory read")
    print("    - Service hasn't fired slow-poll cycle yet")
else:
    print(f"  {'machine':<10}{'rows':>6}{'w/comment':>11}{'distinct':>10}  last_write")
    for r in rows:
        print(f"  {r['machine_id']:<10}{r['rows']:>6}{r['with_comment']:>11}"
              f"{r['distinct_progs']:>10}  {r['last_ts'][:19]}")

print()
print("=" * 60)
print("SAMPLE OF CAPTURED COMMENTS (most recent 20)")
print("=" * 60)
sample = conn.execute(
    """SELECT machine_id, program_number, program_comment, timestamp
       FROM program_directory
       ORDER BY timestamp DESC LIMIT 20"""
).fetchall()
if not sample:
    print("  (none yet)")
else:
    for r in sample:
        comment = r["program_comment"] or "<no comment>"
        print(f"  {r['timestamp'][:19]}  {r['machine_id']}  "
              f"O{r['program_number']:04d}  {comment!r}")

print()
print("=" * 60)
print("MONITORING ACTIVITY (proves service is polling)")
print("=" * 60)
cutoff = (datetime.now() - timedelta(minutes=15)).isoformat()
activity = conn.execute(
    """SELECT machine_id,
              COUNT(*)                  AS samples,
              MAX(timestamp)            AS last_sample,
              SUM(CASE WHEN connected=1 THEN 1 ELSE 0 END) AS connected_samples
       FROM machine_samples
       WHERE timestamp > ?
       GROUP BY machine_id
       ORDER BY machine_id""",
    (cutoff,),
).fetchall()
if not activity:
    print("  (no samples in last 15 min - service may not be running)")
else:
    print(f"  {'machine':<10}{'samples':>8}{'connected':>11}  last_sample")
    for r in activity:
        print(f"  {r['machine_id']:<10}{r['samples']:>8}"
              f"{r['connected_samples']:>11}  {r['last_sample'][:19]}")

print()
print("=" * 60)
print("RUNNING PROGRAMS RIGHT NOW")
print("=" * 60)
running = conn.execute(
    """SELECT machine_id, program_number, MAX(timestamp) AS ts
       FROM machine_samples
       WHERE timestamp > ? AND program_number > 0 AND connected = 1
       GROUP BY machine_id, program_number
       ORDER BY machine_id, ts DESC""",
    (cutoff,),
).fetchall()
if not running:
    print("  (nothing running on connected machines in last 15 min)")
else:
    for r in running:
        print(f"  {r['machine_id']}  O{r['program_number']:04d}  last_seen={r['ts'][:19]}")

conn.close()
