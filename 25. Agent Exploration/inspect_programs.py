"""Dump every program comment FOCAS has captured for a machine.

Garrett/Thomas use this before sitting at the lathe to see what the data
collector already knows about each O-number — saves keying through programs
on the YCM CRT to read headers manually.

Comments come from `active_block_content` samples where the block starts with
`(` (Fanuc executes comment-only blocks as no-ops; the sampler logs the text).

Usage:
    python inspect_programs.py             # T2 (default lathe)
    python inspect_programs.py M3          # specific machine
    python inspect_programs.py --all       # every machine
    python inspect_programs.py --o O2004   # one specific program (any machine)
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import config


def _connect():
    db = config.get_focas_db_path()
    if not db or not Path(db).exists():
        print(f"FOCAS DB not found (looked at {config.FOCAS_DB_PRIMARY} and fallback).")
        return None
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt_block(text, width=120):
    """Collapse newlines, trim, truncate."""
    s = (text or "").replace("\n", " ").strip()
    return s if len(s) <= width else s[: width - 3] + "..."


def inspect_machine(conn, machine_id):
    rows = conn.execute(
        """
        SELECT program_number,
               active_block_content,
               COUNT(*)   AS occurrences,
               MIN(timestamp) AS first_seen,
               MAX(timestamp) AS last_seen
        FROM machine_samples
        WHERE machine_id = ?
          AND program_number > 0
          AND active_block_content LIKE '(%'
        GROUP BY program_number, active_block_content
        ORDER BY program_number, occurrences DESC
        """,
        (machine_id,),
    ).fetchall()

    if not rows:
        print(f"[{machine_id}] No comment-style blocks captured.")
        return

    distinct = sorted({r["program_number"] for r in rows})
    print(f"[{machine_id}] {len(distinct)} programs with captured comments, "
          f"{len(rows)} distinct (program, comment) tuples")
    print()

    current = None
    for r in rows:
        if r["program_number"] != current:
            current = r["program_number"]
            print(f"  --- O{current:04d} ---")
        print(f"      ({r['occurrences']:>3}x)  {_fmt_block(r['active_block_content'])}")
    print()


def inspect_program(conn, o_number):
    """Single program across all machines (handy for shared-program lookups)."""
    onum = o_number.lstrip("Oo").lstrip("0") or "0"
    try:
        prog_int = int(onum)
    except ValueError:
        print(f"Bad O-number: {o_number}")
        return

    rows = conn.execute(
        """
        SELECT machine_id,
               active_block_content,
               COUNT(*)   AS occurrences,
               MIN(timestamp) AS first_seen,
               MAX(timestamp) AS last_seen
        FROM machine_samples
        WHERE program_number = ?
          AND active_block_content LIKE '(%'
        GROUP BY machine_id, active_block_content
        ORDER BY machine_id, occurrences DESC
        """,
        (prog_int,),
    ).fetchall()

    if not rows:
        print(f"O{prog_int:04d}: no captured comments on any machine.")
        return

    print(f"O{prog_int:04d}: {len(rows)} (machine, comment) tuples")
    print()
    current = None
    for r in rows:
        if r["machine_id"] != current:
            current = r["machine_id"]
            print(f"  --- {current} ---")
        print(f"      ({r['occurrences']:>3}x)  {_fmt_block(r['active_block_content'])}")
    print()


def inspect_all(conn):
    machines = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT machine_id FROM machine_samples ORDER BY machine_id"
        ).fetchall()
    ]
    for mid in machines:
        inspect_machine(conn, mid)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("machine_id", nargs="?", default="T2",
                   help="Machine to inspect (default T2)")
    p.add_argument("--all", action="store_true", help="Every machine in the DB")
    p.add_argument("--o", "--program", dest="program",
                   help="One specific O-number, e.g. O2004 or 2004 (across all machines)")
    args = p.parse_args()

    conn = _connect()
    if conn is None:
        return 1
    try:
        if args.program:
            inspect_program(conn, args.program)
        elif args.all:
            inspect_all(conn)
        else:
            inspect_machine(conn, args.machine_id)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
