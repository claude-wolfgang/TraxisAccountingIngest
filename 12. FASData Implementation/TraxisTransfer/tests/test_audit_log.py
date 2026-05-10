"""Tests for audit_log service using in-memory SQLite."""

from __future__ import annotations

import sqlite3
import time

import pytest

from traxistransfer.services.audit_log import (
    get_folder_memory,
    get_last_sent_to_machine,
    get_preference,
    get_recent_transfers,
    init_db,
    log_transfer,
    save_folder_memory,
    save_preference,
)


@pytest.fixture()
def conn():
    """Provide an in-memory database connection with tables created."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_db(db)
    yield db
    db.close()


# -- init_db ------------------------------------------------------------------

def test_init_db_creates_all_tables(conn: sqlite3.Connection):
    """init_db should create transfers, folder_memory, and preferences tables."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = sorted(r["name"] for r in rows)
    assert "folder_memory" in table_names
    assert "preferences" in table_names
    assert "transfers" in table_names


# -- log_transfer / get_recent_transfers --------------------------------------

def test_log_transfer_inserts_and_returns_id(conn: sqlite3.Connection):
    """log_transfer should insert a row and return a positive integer ID."""
    row_id = log_transfer(
        conn,
        machine_id="VF2",
        machine_name="Haas VF-2",
        driver="cncnetv2",
        direction="send",
        file_path=r"D:\NC Programs\1234\1234_OP60_v1.nc",
        file_name="1234_OP60_v1.nc",
        program_number="O1234",
        file_size_bytes=4096,
        duration_seconds=1.5,
        success=True,
    )
    assert isinstance(row_id, int)
    assert row_id > 0

    # Verify the row exists
    row = conn.execute("SELECT * FROM transfers WHERE id = ?", (row_id,)).fetchone()
    assert row["machine_id"] == "VF2"
    assert row["direction"] == "send"
    assert row["success"] == 1


def test_get_recent_transfers_descending_order(conn: sqlite3.Connection):
    """get_recent_transfers should return records newest-first."""
    # Insert three records with explicit timestamps to guarantee order
    for i, ts in enumerate(["2025-01-01 10:00:00", "2025-01-02 10:00:00", "2025-01-03 10:00:00"]):
        conn.execute(
            """INSERT INTO transfers
               (timestamp, machine_id, machine_name, driver, direction,
                file_path, file_name, success)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, f"M{i}", f"Machine {i}", "network", "send",
             f"/path/file{i}.nc", f"file{i}.nc", 1),
        )
    conn.commit()

    results = get_recent_transfers(conn, limit=10)
    assert len(results) == 3
    # Newest first
    assert results[0]["machine_id"] == "M2"
    assert results[1]["machine_id"] == "M1"
    assert results[2]["machine_id"] == "M0"


# -- folder_memory ------------------------------------------------------------

def test_folder_memory_round_trip(conn: sqlite3.Connection):
    """save_folder_memory then get_folder_memory should return the saved folder."""
    save_folder_memory(conn, "VF2", r"D:\NC Programs\1234")
    result = get_folder_memory(conn, "VF2")
    assert result == r"D:\NC Programs\1234"


def test_folder_memory_overwrites_on_same_machine(conn: sqlite3.Connection):
    """Saving folder memory twice for the same machine should keep only the latest."""
    save_folder_memory(conn, "VF2", r"D:\NC Programs\1234")
    save_folder_memory(conn, "VF2", r"D:\NC Programs\5678")
    result = get_folder_memory(conn, "VF2")
    assert result == r"D:\NC Programs\5678"

    # Confirm only one row for VF2
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM folder_memory WHERE machine_id = ?", ("VF2",)
    ).fetchone()["cnt"]
    assert count == 1


def test_get_folder_memory_returns_none_when_missing(conn: sqlite3.Connection):
    """get_folder_memory should return None for an unknown machine."""
    result = get_folder_memory(conn, "NONEXISTENT")
    assert result is None


# -- preferences --------------------------------------------------------------

def test_preference_round_trip(conn: sqlite3.Connection):
    """save_preference then get_preference should return the saved value."""
    save_preference(conn, "theme", "dark")
    result = get_preference(conn, "theme")
    assert result == "dark"


def test_get_preference_returns_default_when_missing(conn: sqlite3.Connection):
    """get_preference should return the default for an unknown key."""
    result = get_preference(conn, "nonexistent_key", default="fallback")
    assert result == "fallback"


# -- get_last_sent_to_machine -------------------------------------------------

def test_get_last_sent_returns_most_recent_successful_send(conn: sqlite3.Connection):
    """Should return the most recent successful send for the given machine."""
    # Insert two sends and one receive
    log_transfer(conn, machine_id="VF2", machine_name="Haas VF-2",
                 driver="focas", direction="send",
                 file_path="/p/old.nc", file_name="old.nc", success=True)
    log_transfer(conn, machine_id="VF2", machine_name="Haas VF-2",
                 driver="focas", direction="receive",
                 file_path="/p/recv.nc", file_name="recv.nc", success=True)
    log_transfer(conn, machine_id="VF2", machine_name="Haas VF-2",
                 driver="focas", direction="send",
                 file_path="/p/new.nc", file_name="new.nc", success=True)

    result = get_last_sent_to_machine(conn, "VF2")
    assert result is not None
    assert result["file_name"] == "new.nc"
    assert result["direction"] == "send"


def test_get_last_sent_ignores_failed_sends(conn: sqlite3.Connection):
    """Failed sends should not be returned."""
    log_transfer(conn, machine_id="VF2", machine_name="Haas VF-2",
                 driver="focas", direction="send",
                 file_path="/p/good.nc", file_name="good.nc", success=True)
    log_transfer(conn, machine_id="VF2", machine_name="Haas VF-2",
                 driver="focas", direction="send",
                 file_path="/p/fail.nc", file_name="fail.nc", success=False,
                 error_message="timeout")

    result = get_last_sent_to_machine(conn, "VF2")
    assert result is not None
    assert result["file_name"] == "good.nc"


def test_get_last_sent_returns_none_when_no_sends(conn: sqlite3.Connection):
    """Should return None when the machine has no send history."""
    result = get_last_sent_to_machine(conn, "NONEXISTENT")
    assert result is None


def test_get_last_sent_scoped_to_machine(conn: sqlite3.Connection):
    """Should only return sends for the requested machine, not others."""
    log_transfer(conn, machine_id="M1", machine_name="Machine 1",
                 driver="focas", direction="send",
                 file_path="/p/m1.nc", file_name="m1.nc", success=True)
    log_transfer(conn, machine_id="M2", machine_name="Machine 2",
                 driver="focas", direction="send",
                 file_path="/p/m2.nc", file_name="m2.nc", success=True)

    result = get_last_sent_to_machine(conn, "M1")
    assert result is not None
    assert result["file_name"] == "m1.nc"
