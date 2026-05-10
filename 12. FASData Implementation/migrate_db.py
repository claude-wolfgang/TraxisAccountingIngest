#!/usr/bin/env python3
"""
Database Migration — FocasMonitor schema upgrade
Traxis Manufacturing

Adds missing columns to machine_samples and creates new tables
(tool_wear_samples, alarm_history, etc.) to support CAPTURE tag
parsing and extended monitoring.

Preserves all existing data. New columns will be NULL for old rows.

Usage:
  python migrate_db.py                        # migrate C:\FASData\monitoring.db
  python migrate_db.py --db path/to/db        # migrate specific database
  python migrate_db.py --dry-run              # show what would change
"""

import sqlite3
import os
import shutil
import argparse
from datetime import datetime

DEFAULT_DB = r"C:\FASData\monitoring.db"


def get_existing_columns(conn, table):
    """Get set of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def get_existing_tables(conn):
    """Get set of table names."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def get_existing_indexes(conn):
    """Get set of index names."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")
    return {row[0] for row in cursor.fetchall()}


# Columns to add to machine_samples (name, type)
NEW_COLUMNS = [
    ("connected", "INTEGER"),
    ("cnc_type", "TEXT"),
    ("mt_type", "TEXT"),
    ("series", "TEXT"),
    ("sw_version", "TEXT"),
    ("max_axes", "INTEGER"),
    ("cnc_id", "TEXT"),
    ("edit_status", "INTEGER"),
    ("warning", "INTEGER"),
    ("sequence_number", "INTEGER"),
    ("block_count", "INTEGER"),
    ("active_block_content", "TEXT"),
    ("capture_session_id", "TEXT"),
    ("capture_op_id", "TEXT"),
    ("capture_tool_id", "TEXT"),
    ("spindle_load", "INTEGER"),
    ("tool_number", "INTEGER"),
    ("active_wcs", "INTEGER"),
    ("axis_a", "INTEGER"),
    ("axis_b", "INTEGER"),
    ("mach_x", "INTEGER"),
    ("mach_y", "INTEGER"),
    ("mach_z", "INTEGER"),
    ("dtg_x", "INTEGER"),
    ("dtg_y", "INTEGER"),
    ("dtg_z", "INTEGER"),
    ("servo_load_x", "INTEGER"),
    ("servo_load_y", "INTEGER"),
    ("servo_load_z", "INTEGER"),
    ("servo_load_a", "INTEGER"),
    ("diag_power_on_min", "INTEGER"),
    ("diag_cutting_min", "INTEGER"),
    ("diag_cycle_min", "INTEGER"),
    ("tool_life_enabled", "INTEGER"),
    ("tool_life_type", "TEXT"),
]

# New tables to create
NEW_TABLES = {
    "tool_wear_samples": """
        CREATE TABLE IF NOT EXISTS tool_wear_samples (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               TEXT NOT NULL,
            machine_id              TEXT NOT NULL,
            capture_session_id      TEXT,
            capture_op_id           TEXT,
            tool_number             INTEGER,
            offset_number           INTEGER,
            length_wear             INTEGER,
            diameter_wear           INTEGER,
            length_geometry         INTEGER,
            diameter_geometry       INTEGER
        )""",
    "tool_life_samples": """
        CREATE TABLE IF NOT EXISTS tool_life_samples (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               TEXT NOT NULL,
            machine_id              TEXT NOT NULL,
            group_number            INTEGER,
            tool_number             INTEGER,
            h_offset                INTEGER,
            d_offset                INTEGER,
            life_limit              INTEGER,
            life_used               INTEGER,
            life_remaining_pct      REAL,
            life_type               TEXT,
            status                  TEXT
        )""",
    "wco_samples": """
        CREATE TABLE IF NOT EXISTS wco_samples (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               TEXT NOT NULL,
            machine_id              TEXT NOT NULL,
            wcs_number              INTEGER,
            wcs_name                TEXT,
            offset_x                INTEGER,
            offset_y                INTEGER,
            offset_z                INTEGER,
            offset_a                INTEGER,
            changed                 INTEGER
        )""",
    "parameter_snapshots": """
        CREATE TABLE IF NOT EXISTS parameter_snapshots (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               TEXT NOT NULL,
            machine_id              TEXT NOT NULL,
            param_number            INTEGER,
            axis                    INTEGER,
            value                   INTEGER,
            description             TEXT
        )""",
    "alarm_history": """
        CREATE TABLE IF NOT EXISTS alarm_history (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               TEXT NOT NULL,
            machine_id              TEXT NOT NULL,
            alarm_number            INTEGER,
            alarm_type              INTEGER,
            alarm_axis              INTEGER,
            alarm_message           TEXT,
            capture_session_id      TEXT,
            capture_op_id           TEXT,
            program_number          INTEGER
        )""",
    "program_directory": """
        CREATE TABLE IF NOT EXISTS program_directory (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               TEXT NOT NULL,
            machine_id              TEXT NOT NULL,
            program_number          INTEGER,
            program_size_bytes      INTEGER,
            program_comment         TEXT
        )""",
}

# Indexes to create
NEW_INDEXES = [
    # machine_samples
    ("idx_ms_timestamp",  "CREATE INDEX IF NOT EXISTS idx_ms_timestamp ON machine_samples(timestamp)"),
    ("idx_ms_machine",    "CREATE INDEX IF NOT EXISTS idx_ms_machine ON machine_samples(machine_id)"),
    ("idx_ms_mach_time",  "CREATE INDEX IF NOT EXISTS idx_ms_mach_time ON machine_samples(machine_id, timestamp)"),
    ("idx_ms_session",    "CREATE INDEX IF NOT EXISTS idx_ms_session ON machine_samples(capture_session_id) WHERE capture_session_id IS NOT NULL"),
    ("idx_ms_program",    "CREATE INDEX IF NOT EXISTS idx_ms_program ON machine_samples(machine_id, program_number) WHERE program_number IS NOT NULL"),
    # tool_wear_samples
    ("idx_tw_machine",    "CREATE INDEX IF NOT EXISTS idx_tw_machine ON tool_wear_samples(machine_id)"),
    ("idx_tw_timestamp",  "CREATE INDEX IF NOT EXISTS idx_tw_timestamp ON tool_wear_samples(timestamp)"),
    ("idx_tw_session",    "CREATE INDEX IF NOT EXISTS idx_tw_session ON tool_wear_samples(capture_session_id) WHERE capture_session_id IS NOT NULL"),
    ("idx_tw_tool",       "CREATE INDEX IF NOT EXISTS idx_tw_tool ON tool_wear_samples(machine_id, tool_number)"),
    # tool_life_samples
    ("idx_tl_machine",    "CREATE INDEX IF NOT EXISTS idx_tl_machine ON tool_life_samples(machine_id)"),
    ("idx_tl_timestamp",  "CREATE INDEX IF NOT EXISTS idx_tl_timestamp ON tool_life_samples(timestamp)"),
    ("idx_tl_tool",       "CREATE INDEX IF NOT EXISTS idx_tl_tool ON tool_life_samples(machine_id, tool_number)"),
    # wco_samples
    ("idx_wco_machine",   "CREATE INDEX IF NOT EXISTS idx_wco_machine ON wco_samples(machine_id)"),
    ("idx_wco_timestamp", "CREATE INDEX IF NOT EXISTS idx_wco_timestamp ON wco_samples(timestamp)"),
    # parameter_snapshots
    ("idx_ps_machine",    "CREATE INDEX IF NOT EXISTS idx_ps_machine ON parameter_snapshots(machine_id)"),
    ("idx_ps_param",      "CREATE INDEX IF NOT EXISTS idx_ps_param ON parameter_snapshots(machine_id, param_number)"),
    # alarm_history
    ("idx_ah_machine",    "CREATE INDEX IF NOT EXISTS idx_ah_machine ON alarm_history(machine_id)"),
    ("idx_ah_timestamp",  "CREATE INDEX IF NOT EXISTS idx_ah_timestamp ON alarm_history(timestamp)"),
    ("idx_ah_session",    "CREATE INDEX IF NOT EXISTS idx_ah_session ON alarm_history(capture_session_id) WHERE capture_session_id IS NOT NULL"),
    # program_directory
    ("idx_pd_machine",    "CREATE INDEX IF NOT EXISTS idx_pd_machine ON program_directory(machine_id)"),
    ("idx_pd_program",    "CREATE INDEX IF NOT EXISTS idx_pd_program ON program_directory(machine_id, program_number)"),
]


def migrate(db_path, dry_run=False):
    """Run the migration."""
    if not os.path.isfile(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return False

    # Backup
    if not dry_run:
        backup = db_path.replace(
            ".db", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        print(f"Backing up to: {backup}")
        shutil.copy2(db_path, backup)
        print(f"Backup created ({os.path.getsize(backup):,} bytes)")

    conn = sqlite3.connect(db_path)
    existing_tables = get_existing_tables(conn)
    existing_indexes = get_existing_indexes(conn)

    print(f"\nExisting tables: {sorted(existing_tables)}")

    changes = 0

    # 1. Add missing columns to machine_samples
    if "machine_samples" in existing_tables:
        existing_cols = get_existing_columns(conn, "machine_samples")
        print(f"Existing machine_samples columns: {len(existing_cols)}")

        for col_name, col_type in NEW_COLUMNS:
            if col_name not in existing_cols:
                sql = (f"ALTER TABLE machine_samples "
                       f"ADD COLUMN {col_name} {col_type}")
                print(f"  ADD COLUMN: {col_name} {col_type}")
                if not dry_run:
                    conn.execute(sql)
                changes += 1

        # Handle 'connected' column — old schema has it
        # but check if we need a default for old rows
        if "connected" not in existing_cols:
            print("  Note: 'connected' column added — old rows will be NULL")

    # 2. Create missing tables
    for table_name, create_sql in NEW_TABLES.items():
        if table_name not in existing_tables:
            print(f"  CREATE TABLE: {table_name}")
            if not dry_run:
                conn.execute(create_sql)
            changes += 1
        else:
            print(f"  [OK] {table_name} already exists")

    # 3. Create missing indexes
    for idx_name, create_sql in NEW_INDEXES:
        if idx_name not in existing_indexes:
            print(f"  CREATE INDEX: {idx_name}")
            if not dry_run:
                conn.execute(create_sql)
            changes += 1
        else:
            print(f"  [OK] {idx_name} already exists")

    if not dry_run:
        conn.commit()

    conn.close()

    # Verify
    if not dry_run and changes > 0:
        print(f"\nVerifying migration...")
        conn = sqlite3.connect(db_path)
        new_tables = get_existing_tables(conn)
        new_cols = get_existing_columns(conn, "machine_samples")
        new_indexes = get_existing_indexes(conn)
        conn.close()
        print(f"  Tables: {len(new_tables)}")
        print(f"  machine_samples columns: {len(new_cols)}")
        print(f"  Indexes: {len(new_indexes)}")
        has_capture = "capture_session_id" in new_cols
        print(f"  capture_session_id present: {has_capture}")
        if has_capture:
            print("\nMigration successful!")
        else:
            print("\nERROR: capture_session_id not found after migration!")
            return False

    if changes == 0:
        print("\nDatabase already up to date — no changes needed.")
    elif dry_run:
        print(f"\nDry run: {changes} changes would be made.")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate FocasMonitor database schema")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="Path to monitoring.db")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying")
    args = parser.parse_args()

    print("=" * 50)
    print("  FocasMonitor Database Migration")
    print("  Traxis Manufacturing")
    print("=" * 50)
    print(f"\nDatabase: {args.db}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)\n")
    else:
        print()

    migrate(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
