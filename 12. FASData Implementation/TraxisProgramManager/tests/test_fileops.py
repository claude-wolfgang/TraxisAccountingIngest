"""Tests for tpm.fileops."""

import os

import pytest

from tpm import fileops


class TestFindPartFilesFolder:
    def test_finds_by_customer_pn(self, mock_dropbox):
        """Finds folder when customer PN matches."""
        pf_root = os.path.join(str(mock_dropbox), "PART FILES Traxis")
        cust_folder = os.path.join(pf_root, "CustomerA", "55200029")
        os.makedirs(cust_folder)

        result = fileops.find_part_files_folder(
            "NP000674", customer_part_number="55200029",
        )
        assert result == cust_folder

    def test_falls_back_to_part_pn(self, mock_dropbox, mock_proshop):
        """Falls back to ProShop PN when customer PN not found."""
        pf_root = os.path.join(str(mock_dropbox), "PART FILES Traxis")
        pn_folder = os.path.join(pf_root, "CustomerB", "NP000674")
        os.makedirs(pn_folder)

        result = fileops.find_part_files_folder(
            "NP000674", customer_part_number="NOMATCH",
        )
        assert result == pn_folder

    def test_returns_none_when_not_found(self, mock_dropbox, mock_proshop):
        """Returns None when no matching folder exists."""
        result = fileops.find_part_files_folder(
            "NP999999", customer_part_number="NOPE",
        )
        assert result is None

    def test_returns_none_when_root_missing(self, monkeypatch):
        """Returns None when PART_FILES_ROOT doesn't exist."""
        import tpm.config

        monkeypatch.setattr(tpm.config, "PART_FILES_ROOT", "/nonexistent")
        assert fileops.find_part_files_folder("NP000674") is None


class TestCopyToPartFolder:
    def test_copies_file(self, tmp_path):
        src = tmp_path / "source" / "test.nc"
        src.parent.mkdir()
        src.write_text("G90\n")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        result = fileops.copy_to_part_folder(str(src), str(dest_dir))
        assert result is not None
        assert os.path.isfile(result)
        assert open(result).read() == "G90\n"

    def test_returns_none_on_failure(self, tmp_path):
        result = fileops.copy_to_part_folder(
            "/nonexistent/file.nc", str(tmp_path),
        )
        assert result is None
