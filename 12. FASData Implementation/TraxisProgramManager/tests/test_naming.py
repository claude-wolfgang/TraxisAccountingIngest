"""Tests for tpm.naming."""

from tpm import naming


class TestGetOperationNumber:
    def test_setup_1(self):
        assert naming.get_operation_number(1) == 60

    def test_setup_2(self):
        assert naming.get_operation_number(2) == 70

    def test_setup_6(self):
        assert naming.get_operation_number(6) == 110


class TestGetProgramNumber:
    def test_op60_v1(self):
        assert naming.get_program_number(60, 1) == "0061"

    def test_op60_v2(self):
        assert naming.get_program_number(60, 2) == "0062"

    def test_op70_v1(self):
        assert naming.get_program_number(70, 1) == "0071"

    def test_op110_v3(self):
        assert naming.get_program_number(110, 3) == "0113"


class TestReadVersionFromHeader:
    def test_reads_version(self, tmp_path):
        nc = tmp_path / "test.nc"
        nc.write_text("%\n(PART: NP000674)\n(VERSION: 3)\nG90\n")
        assert naming.read_version_from_header(str(nc)) == 3

    def test_returns_zero_if_missing(self, tmp_path):
        nc = tmp_path / "test.nc"
        nc.write_text("%\nG90 G54\nT1 M6\n")
        assert naming.read_version_from_header(str(nc)) == 0

    def test_returns_zero_for_nonexistent(self, tmp_path):
        assert naming.read_version_from_header(str(tmp_path / "nope.nc")) == 0

    def test_only_scans_first_20_lines(self, tmp_path):
        nc = tmp_path / "test.nc"
        lines = ["G0 X0\n"] * 25 + ["(VERSION: 5)\n"]
        nc.write_text("".join(lines))
        assert naming.read_version_from_header(str(nc)) == 0


class TestGetCurrentVersion:
    def test_no_files(self, tmp_path):
        assert naming.get_current_version(str(tmp_path), "NP000674", 60) == 0

    def test_from_header(self, tmp_path):
        nc = tmp_path / "NP000674_OP60.nc"
        nc.write_text("%\n(VERSION: 2)\nG90\n")
        assert naming.get_current_version(str(tmp_path), "NP000674", 60) == 2

    def test_from_legacy_filenames(self, tmp_path):
        (tmp_path / "NP000674_OP60_v1.nc").write_text("v1")
        (tmp_path / "NP000674_OP60_v3.nc").write_text("v3")
        assert naming.get_current_version(str(tmp_path), "NP000674", 60) == 3


class TestGetNextVersion:
    def test_first_post(self, tmp_path):
        assert naming.get_next_version(str(tmp_path), "NP000674", 60) == 1

    def test_no_changes_reuses(self, tmp_path):
        nc = tmp_path / "NP000674_OP60.nc"
        nc.write_text("%\n(VERSION: 2)\nG90\n")
        assert naming.get_next_version(
            str(tmp_path), "NP000674", 60, has_changes=False,
        ) == 2

    def test_changes_increments(self, tmp_path):
        nc = tmp_path / "NP000674_OP60.nc"
        nc.write_text("%\n(VERSION: 2)\nG90\n")
        assert naming.get_next_version(
            str(tmp_path), "NP000674", 60, has_changes=True,
        ) == 3

    def test_unknown_changes_increments(self, tmp_path):
        nc = tmp_path / "NP000674_OP60.nc"
        nc.write_text("%\n(VERSION: 2)\nG90\n")
        assert naming.get_next_version(
            str(tmp_path), "NP000674", 60, has_changes=None,
        ) == 3
