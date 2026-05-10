"""Tests for FolderResolver and ProShop-driven folder resolution."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from traxistransfer.constants import DriverType
from traxistransfer.models.machine import Machine
from traxistransfer.services.audit_log import init_db, get_connection
from traxistransfer.services.folder_resolver import FolderResolver


@pytest.fixture
def machine() -> Machine:
    """A test machine with a ProShop pot ID."""
    return Machine(
        id="M6",
        name="FANUC Mill 6",
        type="Mill",
        driver=DriverType.FOCAS,
        ip="10.1.1.106",
        port=8193,
        proshop_pot_id="Mill-6",
    )


@pytest.fixture
def machine_no_pot() -> Machine:
    """A test machine without a ProShop pot ID."""
    return Machine(
        id="M9",
        name="Legacy Mill",
        type="Mill",
        driver=DriverType.FOCAS,
        ip="10.1.1.109",
        port=8193,
        proshop_pot_id="",
    )


@pytest.fixture
def mock_proshop() -> MagicMock:
    """A mocked ProShopClient."""
    client = MagicMock()
    client.get_active_wo_for_workcell.return_value = {
        "woNumber": "WO-1234",
        "partNumber": "PN-5678",
    }
    client.get_customer_part_number.return_value = "CUST-9999"
    return client


@pytest.fixture
def db_conn(tmp_path: Path):
    """An in-memory SQLite connection with schema initialized."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


# -----------------------------------------------------------------------
# resolve() tests
# -----------------------------------------------------------------------


class TestResolveProShop:
    """Test resolve returns ProShop-derived folders when WO is found."""

    def test_resolve_returns_part_folder_from_proshop(
        self, tmp_path: Path, machine: Machine, mock_proshop: MagicMock
    ):
        """When ProShop returns an active WO with a part number, the
        NC Programs/{PartNumber}/ folder should be the first result."""
        part_dir = tmp_path / "PN-5678"
        part_dir.mkdir()

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            tmp_path,
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            tmp_path / "transfer",
        ):
            resolver = FolderResolver(proshop=mock_proshop)
            folders = resolver.resolve(machine)

        assert part_dir in folders
        assert folders[0] == part_dir

    def test_resolve_includes_customer_pn_folder(
        self, tmp_path: Path, machine: Machine, mock_proshop: MagicMock
    ):
        """Customer part number folder should also appear if it exists."""
        part_dir = tmp_path / "PN-5678"
        part_dir.mkdir()
        cust_dir = tmp_path / "CUST-9999"
        cust_dir.mkdir()

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            tmp_path,
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            tmp_path / "transfer",
        ):
            resolver = FolderResolver(proshop=mock_proshop)
            folders = resolver.resolve(machine)

        assert part_dir in folders
        assert cust_dir in folders
        # Part folder comes before customer folder
        assert folders.index(part_dir) < folders.index(cust_dir)

    def test_resolve_includes_wo_folder(
        self, tmp_path: Path, machine: Machine, mock_proshop: MagicMock
    ):
        """NC Files For Transfer/{WO}/ should appear when it exists."""
        transfer_root = tmp_path / "transfer"
        wo_dir = transfer_root / "WO-1234"
        wo_dir.mkdir(parents=True)

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            tmp_path / "nc_programs",
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            transfer_root,
        ):
            resolver = FolderResolver(proshop=mock_proshop)
            folders = resolver.resolve(machine)

        assert wo_dir in folders


class TestResolveFallbacks:
    """Test resolve falls back correctly when ProShop is unavailable."""

    def test_resolve_falls_back_to_remembered_folder(
        self,
        tmp_path: Path,
        machine: Machine,
        db_conn,
    ):
        """When ProShop is not available, the remembered folder is used."""
        remembered = tmp_path / "remembered_folder"
        remembered.mkdir()

        # Save a remembered folder
        from traxistransfer.services import audit_log

        audit_log.save_folder_memory(db_conn, machine.id, str(remembered))

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            tmp_path / "nc_missing",
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            tmp_path / "transfer_missing",
        ):
            resolver = FolderResolver(proshop=None, db_conn=db_conn)
            folders = resolver.resolve(machine)

        assert remembered in folders
        assert folders[0] == remembered

    def test_resolve_returns_defaults_when_nothing_matches(
        self, tmp_path: Path, machine: Machine
    ):
        """When ProShop is down and no remembered folder, defaults are used."""
        transfer_root = tmp_path / "transfer"
        transfer_root.mkdir()
        nc_root = tmp_path / "nc_programs"
        nc_root.mkdir()

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            nc_root,
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            transfer_root,
        ):
            resolver = FolderResolver(proshop=None, db_conn=None)
            folders = resolver.resolve(machine)

        assert transfer_root in folders
        assert nc_root in folders

    def test_resolve_no_proshop_pot_id_skips_lookup(
        self, tmp_path: Path, machine_no_pot: Machine, mock_proshop: MagicMock
    ):
        """Machines without proshop_pot_id should skip the API call."""
        transfer_root = tmp_path / "transfer"
        transfer_root.mkdir()

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            tmp_path / "nc_missing",
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            transfer_root,
        ):
            resolver = FolderResolver(proshop=mock_proshop)
            resolver.resolve(machine_no_pot)

        mock_proshop.get_active_wo_for_workcell.assert_not_called()

    def test_resolve_proshop_exception_falls_through(
        self, tmp_path: Path, machine: Machine, mock_proshop: MagicMock
    ):
        """If ProShop raises an exception, resolve still returns defaults."""
        mock_proshop.get_active_wo_for_workcell.side_effect = Exception(
            "Connection refused"
        )
        transfer_root = tmp_path / "transfer"
        transfer_root.mkdir()

        with patch(
            "traxistransfer.services.folder_resolver.NC_PROGRAMS_ROOT",
            tmp_path / "nc_missing",
        ), patch(
            "traxistransfer.services.folder_resolver.NC_FILES_FOR_TRANSFER",
            transfer_root,
        ):
            resolver = FolderResolver(proshop=mock_proshop)
            folders = resolver.resolve(machine)

        # Should not raise, just return the fallback
        assert transfer_root in folders


# -----------------------------------------------------------------------
# save_choice() tests
# -----------------------------------------------------------------------


class TestSaveChoice:
    """Test save_choice persists to audit_log."""

    def test_save_choice_persists(
        self, tmp_path: Path, machine: Machine, db_conn
    ):
        """save_choice should write the folder to folder_memory."""
        folder = tmp_path / "my_choice"
        folder.mkdir()

        resolver = FolderResolver(db_conn=db_conn)
        resolver.save_choice(machine, folder)

        from traxistransfer.services import audit_log

        remembered = audit_log.get_folder_memory(db_conn, machine.id)
        assert remembered == str(folder)

    def test_save_choice_updates_existing(
        self, tmp_path: Path, machine: Machine, db_conn
    ):
        """save_choice should overwrite a previous memory for the same machine."""
        folder1 = tmp_path / "first"
        folder1.mkdir()
        folder2 = tmp_path / "second"
        folder2.mkdir()

        resolver = FolderResolver(db_conn=db_conn)
        resolver.save_choice(machine, folder1)
        resolver.save_choice(machine, folder2)

        from traxistransfer.services import audit_log

        remembered = audit_log.get_folder_memory(db_conn, machine.id)
        assert remembered == str(folder2)

    def test_save_choice_no_db_is_noop(
        self, tmp_path: Path, machine: Machine
    ):
        """save_choice without a db_conn should not raise."""
        folder = tmp_path / "noop"
        folder.mkdir()

        resolver = FolderResolver(db_conn=None)
        resolver.save_choice(machine, folder)  # Should not raise


# -----------------------------------------------------------------------
# list_nc_files() tests
# -----------------------------------------------------------------------


class TestListNcFiles:
    """Test list_nc_files parsing, deduplication, and sorting."""

    def test_parses_tpm_naming(self, tmp_path: Path):
        """TPM-named files should have part_number, op_number, version parsed."""
        folder = tmp_path / "parts"
        folder.mkdir()
        (folder / "PN-5678_OP60_v1.nc").write_text("G0 X0 Y0")
        (folder / "PN-5678_OP70_v2.nc").write_text("G0 X1 Y1")

        files = FolderResolver.list_nc_files([folder])

        assert len(files) == 2
        names = {f["name"] for f in files}
        assert "PN-5678_OP60_v1.nc" in names
        assert "PN-5678_OP70_v2.nc" in names

        for f in files:
            if f["name"] == "PN-5678_OP60_v1.nc":
                assert f["part_number"] == "PN-5678"
                assert f["op_number"] == 60
                assert f["version"] == 1
            elif f["name"] == "PN-5678_OP70_v2.nc":
                assert f["part_number"] == "PN-5678"
                assert f["op_number"] == 70
                assert f["version"] == 2

    def test_non_tpm_files_have_none_fields(self, tmp_path: Path):
        """Non-TPM files should have None for part_number, op_number, version."""
        folder = tmp_path / "legacy"
        folder.mkdir()
        (folder / "O1234.nc").write_text("G0")

        files = FolderResolver.list_nc_files([folder])
        assert len(files) == 1
        assert files[0]["part_number"] is None
        assert files[0]["op_number"] is None
        assert files[0]["version"] is None

    def test_deduplicates_across_folders(self, tmp_path: Path):
        """Same filename in two folders should appear only once (first wins)."""
        folder_a = tmp_path / "a"
        folder_a.mkdir()
        folder_b = tmp_path / "b"
        folder_b.mkdir()

        (folder_a / "program.nc").write_text("G0 X0")
        (folder_b / "program.nc").write_text("G0 X1")

        files = FolderResolver.list_nc_files([folder_a, folder_b])
        assert len(files) == 1
        assert files[0]["folder"] == str(folder_a)

    def test_sorts_by_modified_descending(self, tmp_path: Path):
        """Files should be sorted most-recently-modified first."""
        folder = tmp_path / "sorted"
        folder.mkdir()

        # Create files with different modification times
        old_file = folder / "old.nc"
        old_file.write_text("G0")

        # Force a different mtime by sleeping briefly and creating a new file
        import os

        new_file = folder / "new.nc"
        new_file.write_text("G1")

        # Set explicit modification times to guarantee order
        os.utime(old_file, (1000.0, 1000.0))
        os.utime(new_file, (2000.0, 2000.0))

        files = FolderResolver.list_nc_files([folder])
        assert len(files) == 2
        assert files[0]["name"] == "new.nc"
        assert files[1]["name"] == "old.nc"

    def test_ignores_non_nc_files(self, tmp_path: Path):
        """Only .nc files should be listed."""
        folder = tmp_path / "mixed"
        folder.mkdir()
        (folder / "program.nc").write_text("G0")
        (folder / "readme.txt").write_text("notes")
        (folder / "setup.pdf").write_bytes(b"%PDF")
        (folder / "backup.NC").write_text("G1")  # uppercase extension

        files = FolderResolver.list_nc_files([folder])
        names = {f["name"] for f in files}
        assert "program.nc" in names
        assert "backup.NC" in names  # .NC uppercase should match
        assert "readme.txt" not in names
        assert "setup.pdf" not in names

    def test_skips_missing_folders(self, tmp_path: Path):
        """Non-existent folders in the list should be silently skipped."""
        real_folder = tmp_path / "real"
        real_folder.mkdir()
        (real_folder / "test.nc").write_text("G0")
        fake_folder = tmp_path / "nonexistent"

        files = FolderResolver.list_nc_files([real_folder, fake_folder])
        assert len(files) == 1

    def test_empty_folders_return_empty_list(self, tmp_path: Path):
        """Empty folders should return an empty list."""
        folder = tmp_path / "empty"
        folder.mkdir()

        files = FolderResolver.list_nc_files([folder])
        assert files == []

    def test_file_entry_contains_expected_keys(self, tmp_path: Path):
        """Each file entry dict should have all expected keys."""
        folder = tmp_path / "check"
        folder.mkdir()
        (folder / "test.nc").write_text("G0 X0 Y0 Z0")

        files = FolderResolver.list_nc_files([folder])
        assert len(files) == 1
        entry = files[0]
        assert "path" in entry
        assert "name" in entry
        assert "size" in entry
        assert "modified" in entry
        assert "folder" in entry
        assert "version" in entry
        assert "op_number" in entry
        assert "part_number" in entry
        assert entry["name"] == "test.nc"
        assert entry["size"] > 0
        assert entry["folder"] == str(folder)
        assert isinstance(entry["path"], Path)


# -----------------------------------------------------------------------
# find_latest_version() tests
# -----------------------------------------------------------------------


class TestFindLatestVersion:
    """Test find_latest_version picks the highest version of a PN+OP."""

    def test_finds_higher_version(self, tmp_path: Path):
        """Given v1 was sent, should find v3 if it exists."""
        folder = tmp_path / "parts"
        folder.mkdir()
        (folder / "PN-5678_OP60_v1.nc").write_text("G0 X0")
        (folder / "PN-5678_OP60_v2.nc").write_text("G0 X1")
        (folder / "PN-5678_OP60_v3.nc").write_text("G0 X2")

        result = FolderResolver.find_latest_version(
            "PN-5678_OP60_v1.nc", [folder]
        )
        assert result is not None
        assert result["name"] == "PN-5678_OP60_v3.nc"
        assert result["version"] == 3

    def test_returns_same_file_if_no_newer(self, tmp_path: Path):
        """If the sent file IS the latest, return it."""
        folder = tmp_path / "parts"
        folder.mkdir()
        (folder / "PN-5678_OP60_v2.nc").write_text("G0 X0")

        result = FolderResolver.find_latest_version(
            "PN-5678_OP60_v2.nc", [folder]
        )
        assert result is not None
        assert result["name"] == "PN-5678_OP60_v2.nc"
        assert result["version"] == 2

    def test_ignores_different_op(self, tmp_path: Path):
        """Versions of a different OP should not be returned."""
        folder = tmp_path / "parts"
        folder.mkdir()
        (folder / "PN-5678_OP60_v1.nc").write_text("G0 X0")
        (folder / "PN-5678_OP70_v5.nc").write_text("G0 X1")

        result = FolderResolver.find_latest_version(
            "PN-5678_OP60_v1.nc", [folder]
        )
        assert result is not None
        assert result["name"] == "PN-5678_OP60_v1.nc"

    def test_ignores_different_pn(self, tmp_path: Path):
        """Versions of a different part number should not be returned."""
        folder = tmp_path / "parts"
        folder.mkdir()
        (folder / "PN-5678_OP60_v1.nc").write_text("G0")
        (folder / "PN-9999_OP60_v9.nc").write_text("G0")

        result = FolderResolver.find_latest_version(
            "PN-5678_OP60_v1.nc", [folder]
        )
        assert result is not None
        assert result["name"] == "PN-5678_OP60_v1.nc"

    def test_non_tpm_file_found_on_disk(self, tmp_path: Path):
        """Non-TPM files should be found if they exist on disk."""
        folder = tmp_path / "legacy"
        folder.mkdir()
        (folder / "O1234.nc").write_text("G0 X0 Y0")

        result = FolderResolver.find_latest_version(
            "O1234.nc", [folder]
        )
        assert result is not None
        assert result["name"] == "O1234.nc"
        assert result["version"] is None

    def test_non_tpm_file_missing_returns_none(self, tmp_path: Path):
        """Non-TPM file that's gone should return None."""
        folder = tmp_path / "empty"
        folder.mkdir()

        result = FolderResolver.find_latest_version(
            "O1234.nc", [folder]
        )
        assert result is None

    def test_tpm_file_missing_returns_none(self, tmp_path: Path):
        """If no versions of the PN+OP exist, return None."""
        folder = tmp_path / "empty"
        folder.mkdir()

        result = FolderResolver.find_latest_version(
            "PN-5678_OP60_v1.nc", [folder]
        )
        assert result is None

    def test_searches_across_multiple_folders(self, tmp_path: Path):
        """Should find the highest version across multiple folders."""
        folder_a = tmp_path / "a"
        folder_a.mkdir()
        folder_b = tmp_path / "b"
        folder_b.mkdir()
        (folder_a / "PN-5678_OP60_v1.nc").write_text("G0")
        (folder_b / "PN-5678_OP60_v4.nc").write_text("G0 X1")

        result = FolderResolver.find_latest_version(
            "PN-5678_OP60_v1.nc", [folder_a, folder_b]
        )
        assert result is not None
        assert result["name"] == "PN-5678_OP60_v4.nc"
        assert result["version"] == 4
        assert result["folder"] == str(folder_b)
