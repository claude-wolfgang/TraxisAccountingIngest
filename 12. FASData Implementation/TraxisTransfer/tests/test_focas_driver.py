"""Tests for the Fanuc FOCAS2 transfer driver.

All FOCAS DLL calls are mocked — no real CNC or Fwlib32.dll required.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from traxistransfer.constants import (
    FOCAS_CHUNK_SIZE,
    FOCAS_MAX_RETRIES,
    FOCAS_RETRY_DELAY_S,
    DriverType,
)
from traxistransfer.drivers.base import TransferError
from traxistransfer.drivers.fanuc_focas import FanucFocasDriver
from traxistransfer.focas.errors import EW_BUSY, EW_OK, EW_REJECT, EW_SOCKET
from traxistransfer.models.machine import Machine


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def machine() -> Machine:
    return Machine(
        id="M6",
        name="FANUC Mill 6",
        type="Mill",
        driver=DriverType.FOCAS,
        ip="10.1.1.106",
        port=8193,
    )


@pytest.fixture
def mock_fwlib():
    """Provide a mock FOCAS DLL where all calls return EW_OK by default."""
    fwlib = MagicMock()
    fwlib.cnc_allclibhndl3.return_value = EW_OK
    fwlib.cnc_freelibhndl.return_value = EW_OK
    fwlib.cnc_statinfo.return_value = EW_OK
    fwlib.cnc_dwnstart3.return_value = EW_OK
    fwlib.cnc_download3.return_value = EW_OK
    fwlib.cnc_dwnend3.return_value = EW_OK
    fwlib.cnc_upstart.return_value = EW_OK
    fwlib.cnc_upload.return_value = EW_OK
    fwlib.cnc_upend.return_value = EW_OK
    fwlib.cnc_rdprogdir2.return_value = EW_OK

    # Make cnc_allclibhndl3 populate the handle via byref
    def set_handle(*args):
        # args[3] is the ctypes.byref(handle) — but in mock land
        # we need the driver to work, so we set handle.value via side_effect
        return EW_OK

    fwlib.cnc_allclibhndl3.side_effect = set_handle

    with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
        yield fwlib


@pytest.fixture
def driver(machine, mock_fwlib) -> FanucFocasDriver:
    return FanucFocasDriver(machine)


# ── Connection lifecycle ────────────────────────────────────────────

class TestConnectDisconnect:
    """Test connection and disconnection."""

    def test_connect_calls_allclibhndl3(self, driver, mock_fwlib):
        driver._connect()
        mock_fwlib.cnc_allclibhndl3.assert_called_once()

    def test_disconnect_calls_freelibhndl(self, driver, mock_fwlib):
        driver._connect()
        driver._disconnect()
        mock_fwlib.cnc_freelibhndl.assert_called_once()

    def test_disconnect_when_not_connected_is_noop(self, driver, mock_fwlib):
        driver._disconnect()
        mock_fwlib.cnc_freelibhndl.assert_not_called()

    def test_disconnect_clears_handle(self, driver, mock_fwlib):
        driver._connect()
        assert driver._handle is not None
        driver._disconnect()
        assert driver._handle is None

    def test_connect_failure_raises_transfer_error(self, machine):
        fwlib = MagicMock()
        fwlib.cnc_allclibhndl3.return_value = EW_SOCKET
        with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
            d = FanucFocasDriver(machine)
            with pytest.raises(TransferError, match="EW_SOCKET"):
                d._connect()


# ── EW_REJECT retry logic ──────────────────────────────────────────

class TestRejectRetry:
    """Test that EW_REJECT triggers retries with delays."""

    @patch("traxistransfer.drivers.fanuc_focas.time.sleep")
    def test_retries_on_reject_then_succeeds(self, mock_sleep, machine):
        fwlib = MagicMock()
        # Reject twice, then succeed
        fwlib.cnc_allclibhndl3.side_effect = [EW_REJECT, EW_REJECT, EW_OK]
        with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
            d = FanucFocasDriver(machine)
            d._connect()

        assert fwlib.cnc_allclibhndl3.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(FOCAS_RETRY_DELAY_S)

    @patch("traxistransfer.drivers.fanuc_focas.time.sleep")
    def test_retries_exhausted_raises_error(self, mock_sleep, machine):
        fwlib = MagicMock()
        fwlib.cnc_allclibhndl3.return_value = EW_REJECT
        with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
            d = FanucFocasDriver(machine)
            with pytest.raises(TransferError, match="EW_REJECT"):
                d._connect()

        assert fwlib.cnc_allclibhndl3.call_count == FOCAS_MAX_RETRIES
        # Sleeps happen between retries (not after the last one)
        assert mock_sleep.call_count == FOCAS_MAX_RETRIES - 1

    @patch("traxistransfer.drivers.fanuc_focas.time.sleep")
    def test_non_reject_error_does_not_retry(self, mock_sleep, machine):
        fwlib = MagicMock()
        fwlib.cnc_allclibhndl3.return_value = EW_SOCKET
        with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
            d = FanucFocasDriver(machine)
            with pytest.raises(TransferError):
                d._connect()

        # Should fail immediately without retrying
        assert fwlib.cnc_allclibhndl3.call_count == 1
        mock_sleep.assert_not_called()


# ── send_program ────────────────────────────────────────────────────

class TestSendProgram:
    """Test the send_program (download to CNC) flow."""

    def test_send_calls_in_correct_order(self, driver, mock_fwlib, tmp_path):
        """dwnstart3 -> download3 (loop) -> dwnend3."""
        nc_file = tmp_path / "O1234.nc"
        nc_file.write_text("O1234\nG90 G0 X0 Y0\nM30\n%\n")

        # Make download3 accept all bytes each call
        def accept_all(handle, length_ptr, data):
            return EW_OK

        mock_fwlib.cnc_download3.side_effect = accept_all

        driver.send_program(nc_file)

        mock_fwlib.cnc_dwnstart3.assert_called_once()
        assert mock_fwlib.cnc_download3.call_count >= 1
        mock_fwlib.cnc_dwnend3.assert_called_once()

    def test_dwnend3_called_on_download_error(self, driver, mock_fwlib, tmp_path):
        """CRITICAL: dwnend3 MUST be called even when download3 fails."""
        nc_file = tmp_path / "O1234.nc"
        nc_file.write_text("O1234\nG90\nM30\n%\n")

        mock_fwlib.cnc_download3.return_value = EW_SOCKET  # simulate error

        with pytest.raises(TransferError):
            driver.send_program(nc_file)

        # dwnend3 must still be called
        mock_fwlib.cnc_dwnend3.assert_called_once()

    def test_dwnend3_called_on_dwnstart3_failure(self, driver, mock_fwlib, tmp_path):
        """If dwnstart3 fails, dwnend3 should NOT be called (session never opened)."""
        nc_file = tmp_path / "O1234.nc"
        nc_file.write_text("O1234\nG90\nM30\n%\n")

        mock_fwlib.cnc_dwnstart3.return_value = EW_BUSY

        with pytest.raises(TransferError):
            driver.send_program(nc_file)

        # dwnend3 should NOT be called — session was never started
        mock_fwlib.cnc_dwnend3.assert_not_called()

    def test_disconnect_always_called(self, driver, mock_fwlib, tmp_path):
        """Disconnect must happen even on error."""
        nc_file = tmp_path / "O1234.nc"
        nc_file.write_text("O1234\nG90\nM30\n%\n")

        mock_fwlib.cnc_download3.return_value = EW_SOCKET

        with pytest.raises(TransferError):
            driver.send_program(nc_file)

        mock_fwlib.cnc_freelibhndl.assert_called_once()

    def test_file_not_found_raises_transfer_error(self, driver, mock_fwlib, tmp_path):
        missing = tmp_path / "nonexistent.nc"
        with pytest.raises(TransferError, match="File not found"):
            driver.send_program(missing)

    def test_empty_file_raises_transfer_error(self, driver, mock_fwlib, tmp_path):
        empty = tmp_path / "empty.nc"
        empty.write_text("")
        with pytest.raises(TransferError, match="empty"):
            driver.send_program(empty)

    def test_progress_callback_is_called(self, driver, mock_fwlib, tmp_path):
        nc_file = tmp_path / "O1234.nc"
        nc_file.write_text("O1234\nG90 G0 X0 Y0\nM30\n%\n")

        progress_calls = []

        def accept_all(handle, length_ptr, data):
            return EW_OK

        mock_fwlib.cnc_download3.side_effect = accept_all

        driver.send_program(nc_file, progress_cb=lambda sent, total: progress_calls.append((sent, total)))

        assert len(progress_calls) >= 1
        # Final call should have sent == total
        last_sent, total = progress_calls[-1]
        assert last_sent == total


# ── receive_program ─────────────────────────────────────────────────

class TestReceiveProgram:
    """Test the receive_program (upload from CNC) flow."""

    def test_upend_called_on_upload_error(self, driver, mock_fwlib, tmp_path):
        """CRITICAL: upend MUST be called even when upload fails."""
        dest = tmp_path / "received.nc"

        mock_fwlib.cnc_upload.return_value = EW_SOCKET

        with pytest.raises(TransferError):
            driver.receive_program("O1234", dest)

        mock_fwlib.cnc_upend.assert_called_once()

    def test_upend_not_called_if_upstart_fails(self, driver, mock_fwlib, tmp_path):
        """If upstart fails, upend should NOT be called."""
        dest = tmp_path / "received.nc"

        mock_fwlib.cnc_upstart.return_value = EW_BUSY

        with pytest.raises(TransferError):
            driver.receive_program("O1234", dest)

        mock_fwlib.cnc_upend.assert_not_called()

    def test_disconnect_always_called_on_error(self, driver, mock_fwlib, tmp_path):
        dest = tmp_path / "received.nc"

        mock_fwlib.cnc_upload.return_value = EW_SOCKET

        with pytest.raises(TransferError):
            driver.receive_program("O1234", dest)

        mock_fwlib.cnc_freelibhndl.assert_called_once()


# ── is_reachable ────────────────────────────────────────────────────

class TestIsReachable:
    """Test the is_reachable quick connectivity check."""

    def test_reachable_returns_true(self, driver, mock_fwlib):
        assert driver.is_reachable() is True
        mock_fwlib.cnc_statinfo.assert_called_once()

    def test_unreachable_returns_false(self, machine):
        fwlib = MagicMock()
        fwlib.cnc_allclibhndl3.return_value = EW_SOCKET
        with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
            d = FanucFocasDriver(machine)
            assert d.is_reachable() is False

    def test_disconnect_called_on_reachable(self, driver, mock_fwlib):
        driver.is_reachable()
        mock_fwlib.cnc_freelibhndl.assert_called_once()

    def test_disconnect_called_on_unreachable(self, machine):
        fwlib = MagicMock()
        fwlib.cnc_allclibhndl3.return_value = EW_SOCKET
        with patch("traxistransfer.drivers.fanuc_focas.get_fwlib", return_value=fwlib):
            d = FanucFocasDriver(machine)
            d.is_reachable()
        # freelibhndl should NOT be called — we never got a handle
        fwlib.cnc_freelibhndl.assert_not_called()
