"""Tests for auto-catch feature (tpm.fileops.auto_catch_posted_files)."""

import os
import time

import pytest

from tpm import fileops


class TestAutoCatch:
    def test_copies_recent_nc(self, mock_dropbox, mock_proshop, tmp_path):
        """Recent .nc in search folder -> copied to NC Programs/{part}/."""
        search = tmp_path / "search"
        search.mkdir()
        nc = search / "test_program.nc"
        nc.write_text("G90 G54\n")

        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[str(search)],
        )

        dest = os.path.join(
            str(mock_dropbox), "NC Programs", "NP000674", "test_program.nc",
        )
        assert os.path.isfile(dest)

    def test_copies_to_part_files(self, mock_dropbox, mock_proshop, tmp_path):
        """Recent .nc -> also copied to PART FILES (if folder exists)."""
        search = tmp_path / "search"
        search.mkdir()
        nc = search / "test.nc"
        nc.write_text("G90\n")

        # Create part files folder matching ProShop PN fallback
        pf_root = os.path.join(str(mock_dropbox), "PART FILES Traxis")
        pf = os.path.join(pf_root, "Cust", "NP000674")
        os.makedirs(pf)

        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[str(search)],
        )

        assert os.path.isfile(os.path.join(pf, "test.nc"))

    def test_no_recent_files(self, mock_dropbox, tmp_path):
        """No recent files -> returns cleanly without copying."""
        search = tmp_path / "search"
        search.mkdir()
        nc = search / "old.nc"
        nc.write_text("G90\n")
        old_time = time.time() - 120  # 2 minutes old
        os.utime(str(nc), (old_time, old_time))

        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[str(search)],
        )

        dest = os.path.join(
            str(mock_dropbox), "NC Programs", "NP000674", "old.nc",
        )
        assert not os.path.exists(dest)

    def test_skips_self_copy(self, mock_dropbox):
        """File already at destination -> skipped (no overwrite loop)."""
        nc_dir = os.path.join(str(mock_dropbox), "NC Programs", "NP000674")
        os.makedirs(nc_dir)
        nc = os.path.join(nc_dir, "test.nc")
        with open(nc, "w") as f:
            f.write("G90\n")

        # Search in the destination folder itself
        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[nc_dir],
        )

        # File should still exist but not be doubled
        assert os.path.isfile(nc)

    def test_no_search_folders(self, mock_dropbox):
        """No search folders exist -> returns gracefully."""
        fileops.auto_catch_posted_files(
            "NP000674", delay=0,
            search_folders=[],
        )

    def test_multiple_nc_files(self, mock_dropbox, mock_proshop, tmp_path):
        """Multiple recent .nc files -> all copied."""
        search = tmp_path / "search"
        search.mkdir()
        (search / "prog1.nc").write_text("G90\n")
        (search / "prog2.nc").write_text("G91\n")

        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[str(search)],
        )

        nc_dir = os.path.join(str(mock_dropbox), "NC Programs", "NP000674")
        assert os.path.isfile(os.path.join(nc_dir, "prog1.nc"))
        assert os.path.isfile(os.path.join(nc_dir, "prog2.nc"))

    def test_one_copy_fails_others_succeed(
        self, mock_dropbox, mock_proshop, tmp_path, monkeypatch,
    ):
        """One copy fails -> others still succeed."""
        search = tmp_path / "search"
        search.mkdir()
        (search / "good.nc").write_text("G90\n")
        (search / "bad.nc").write_text("G91\n")

        import shutil

        original_copy2 = shutil.copy2

        def flaky_copy2(src, dst):
            if "bad.nc" in str(src):
                raise OSError("Disk full")
            return original_copy2(src, dst)

        monkeypatch.setattr(shutil, "copy2", flaky_copy2)

        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[str(search)],
        )

        nc_dir = os.path.join(str(mock_dropbox), "NC Programs", "NP000674")
        assert os.path.isfile(os.path.join(nc_dir, "good.nc"))

    def test_proshop_down_nc_still_copies(
        self, mock_dropbox, tmp_path, monkeypatch,
    ):
        """ProShop down -> NC Programs copy works, PART FILES skipped."""
        import tpm.proshop

        monkeypatch.setattr(tpm.proshop, "get_token", lambda: None)

        search = tmp_path / "search"
        search.mkdir()
        (search / "test.nc").write_text("G90\n")

        fileops.auto_catch_posted_files(
            "NP000674", delay=0, max_age=60,
            search_folders=[str(search)],
        )

        nc_dir = os.path.join(str(mock_dropbox), "NC Programs", "NP000674")
        assert os.path.isfile(os.path.join(nc_dir, "test.nc"))
