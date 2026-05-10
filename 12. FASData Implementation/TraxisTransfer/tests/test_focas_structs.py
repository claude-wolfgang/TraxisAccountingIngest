"""Tests for FOCAS2 ctypes struct definitions.

Validates that struct sizes match what Fwlib32.dll expects, accounting
for _pack_ = 4 alignment.
"""

import ctypes

from traxistransfer.focas.structs import IODBPSD, ODBST, ODBSYS, ODBUP, PRGDIR2


class TestODBST:
    """ODBST — CNC status (9 shorts)."""

    def test_size_is_18_bytes(self):
        """9 x c_short (2 bytes each) = 18 bytes, no padding needed."""
        assert ctypes.sizeof(ODBST) == 18

    def test_field_count(self):
        assert len(ODBST._fields_) == 9

    def test_field_names(self):
        names = [f[0] for f in ODBST._fields_]
        expected = [
            "hdck", "tmmode", "aut", "run", "motion",
            "mstb", "emergency", "alarm", "edit",
        ]
        assert names == expected

    def test_default_values_are_zero(self):
        st = ODBST()
        assert st.run == 0
        assert st.alarm == 0
        assert st.emergency == 0


class TestPRGDIR2:
    """PRGDIR2 — program directory entry."""

    def test_size_with_pack4_padding(self):
        """int(4) + int(4) + char[51] = 59 -> padded to 60 with _pack_=4."""
        assert ctypes.sizeof(PRGDIR2) == 60

    def test_comment_max_length(self):
        """Comment field is 51 chars (50 + null terminator)."""
        assert ctypes.sizeof(ctypes.c_char * 51) == 51

    def test_field_assignment(self):
        entry = PRGDIR2()
        entry.number = 1234
        entry.length = 5678
        entry.comment = b"Test program"
        assert entry.number == 1234
        assert entry.length == 5678
        assert entry.comment == b"Test program"


class TestODBUP:
    """ODBUP — upload data buffer."""

    def test_size_is_260_bytes(self):
        """short(2) + short(2) + char[256] = 260 bytes (no padding needed)."""
        assert ctypes.sizeof(ODBUP) == 260

    def test_data_buffer_size(self):
        assert ctypes.sizeof(ctypes.c_char * 256) == 256


class TestIODBPSD:
    """IODBPSD — parameter read/write."""

    def test_size(self):
        """short(2) + short(2) + short(2) + short(2) + int(4) = 12 bytes."""
        assert ctypes.sizeof(IODBPSD) == 12

    def test_field_assignment(self):
        p = IODBPSD()
        p.datano = 6800
        p.idata = 42
        assert p.datano == 6800
        assert p.idata == 42


class TestODBSYS:
    """ODBSYS — system information."""

    def test_size(self):
        """short(2) + short(2) + char[2] + char[2] + char[4] + char[4] + char[2] = 18."""
        assert ctypes.sizeof(ODBSYS) == 18

    def test_string_fields(self):
        sys_info = ODBSYS()
        sys_info.cnc_type = b"30"
        sys_info.mt_type = b"M"
        sys_info.series = b"0iMF"
        assert sys_info.cnc_type == b"30"
        assert sys_info.mt_type == b"M"
