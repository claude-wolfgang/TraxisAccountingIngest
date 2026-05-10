"""Fanuc FOCAS2 transfer driver — sends/receives NC programs via Fwlib32.dll.

Implements the TransferDriver ABC using the ctypes wrappers in
``traxistransfer.focas``.

CRITICAL SAFETY NOTES:
  - ``cnc_dwnend3`` and ``cnc_upend`` MUST always be called in ``finally``
    blocks.  A leaked download/upload session requires a CNC power-cycle.
  - If ``cnc_allclibhndl3`` returns EW_REJECT (5), it usually means
    FocasMonitor already holds all available handles.  The driver retries
    up to FOCAS_MAX_RETRIES times with FOCAS_RETRY_DELAY_S between attempts.
"""

from __future__ import annotations

import ctypes
import logging
import time
from pathlib import Path

from traxistransfer.constants import (
    FOCAS_CHUNK_SIZE,
    FOCAS_MAX_RETRIES,
    FOCAS_RETRY_DELAY_S,
    FOCAS_TIMEOUT_MS,
)
from traxistransfer.drivers.base import (
    ProgressCallback,
    ProgramInfo,
    TransferDriver,
    TransferError,
)
from traxistransfer.focas.errors import (
    EW_BUSY,
    EW_OK,
    EW_REJECT,
    FocasError,
    code_name,
)
from traxistransfer.focas.fwlib import get_fwlib
from traxistransfer.focas.structs import ODBST, ODBUP, PRGDIR2
from traxistransfer.models.machine import Machine

logger = logging.getLogger(__name__)

# Number of program directory entries to fetch per FOCAS call
_DIR_BATCH_SIZE = 20


class FanucFocasDriver(TransferDriver):
    """Transfer driver for Fanuc CNCs via FOCAS2 / Fwlib32.dll."""

    def __init__(self, machine: Machine):
        super().__init__(machine)
        self._handle: int | None = None

    # ── Connection helpers ──────────────────────────────────────────

    def _connect(self) -> None:
        """Open a FOCAS handle to the CNC.

        Retries up to FOCAS_MAX_RETRIES times on EW_REJECT (handle limit
        reached — typically because FocasMonitor holds a connection).

        Raises:
            TransferError: If the connection cannot be established.
        """
        fwlib = get_fwlib()
        handle = ctypes.c_ushort(0)

        last_code: int = 0
        for attempt in range(1, FOCAS_MAX_RETRIES + 1):
            last_code = fwlib.cnc_allclibhndl3(
                self.machine.ip.encode("ascii"),
                ctypes.c_ushort(self.machine.port),
                ctypes.c_int(FOCAS_TIMEOUT_MS),
                ctypes.byref(handle),
            )

            if last_code == EW_OK:
                self._handle = handle.value
                logger.debug(
                    "Connected to %s — handle %d",
                    self.machine.display_name,
                    self._handle,
                )
                return

            if last_code == EW_REJECT and attempt < FOCAS_MAX_RETRIES:
                logger.warning(
                    "Connection rejected by %s (attempt %d/%d) — "
                    "retrying in %ds (FocasMonitor conflict?)",
                    self.machine.display_name,
                    attempt,
                    FOCAS_MAX_RETRIES,
                    FOCAS_RETRY_DELAY_S,
                )
                time.sleep(FOCAS_RETRY_DELAY_S)
                continue

            # Non-retryable error, or final retry exhausted
            break

        raise TransferError(
            f"Cannot connect to {self.machine.display_name} "
            f"({self.machine.ip}:{self.machine.port}): "
            f"{code_name(last_code)} (code {last_code})"
        )

    def _disconnect(self) -> None:
        """Release the FOCAS handle (safe to call even if not connected)."""
        if self._handle is not None:
            try:
                fwlib = get_fwlib()
                fwlib.cnc_freelibhndl(ctypes.c_ushort(self._handle))
                logger.debug(
                    "Disconnected from %s — handle %d",
                    self.machine.display_name,
                    self._handle,
                )
            except Exception:
                logger.exception("Error releasing handle %d", self._handle)
            finally:
                self._handle = None

    # ── Public API ──────────────────────────────────────────────────

    def send_program(
        self,
        file_path: Path,
        program_number: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Send an NC program file to the CNC via FOCAS download.

        The file content is sent as-is. The CNC parses the O-number from
        the first line of the data (e.g. ``O1234``).  If *program_number*
        is provided and the file does not start with an O-number line, the
        driver prepends one.

        Args:
            file_path: Path to the ``.nc`` file on disk.
            program_number: Optional O-number override (e.g. ``"O1234"``).
            progress_cb: Optional ``(bytes_sent, total_bytes)`` callback.

        Raises:
            TransferError: On any FOCAS or I/O error.
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            raise TransferError(f"File not found: {file_path}")

        data = file_path.read_bytes()
        total = len(data)

        if total == 0:
            raise TransferError(f"File is empty: {file_path}")

        # Prepend O-number if provided and not already present
        if program_number is not None:
            o_num = program_number.upper()
            if not o_num.startswith("O"):
                o_num = f"O{o_num}"
            # If file doesn't start with an O-number, prepend one
            first_line = data.split(b"\n", 1)[0].strip()
            if not first_line.upper().startswith(b"O"):
                data = f"{o_num}\n".encode("ascii") + data
                total = len(data)

        self._connect()
        fwlib = get_fwlib()
        handle = ctypes.c_ushort(self._handle)
        download_started = False

        try:
            # Start download session
            ret = fwlib.cnc_dwnstart3(handle, ctypes.c_short(0))
            if ret != EW_OK:
                raise FocasError("cnc_dwnstart3", ret)
            download_started = True

            # Send data in chunks
            offset = 0
            while offset < total:
                chunk = data[offset : offset + FOCAS_CHUNK_SIZE]
                length = ctypes.c_int(len(chunk))

                ret = fwlib.cnc_download3(
                    handle,
                    ctypes.byref(length),
                    chunk,
                )
                if ret == EW_BUSY:
                    # CNC buffer full — brief pause and retry this chunk
                    time.sleep(0.05)
                    continue
                if ret != EW_OK:
                    raise FocasError("cnc_download3", ret)

                # length.value tells us how many bytes the CNC actually accepted
                offset += length.value

                if progress_cb is not None:
                    progress_cb(offset, total)

            logger.info(
                "Sent %s (%d bytes) to %s",
                file_path.name,
                total,
                self.machine.display_name,
            )

        except FocasError as exc:
            raise TransferError(str(exc)) from exc

        finally:
            # CRITICAL: always end the download session
            if download_started:
                try:
                    fwlib.cnc_dwnend3(handle)
                except Exception:
                    logger.exception("cnc_dwnend3 failed during cleanup")
            self._disconnect()

    def receive_program(
        self,
        program_number: str,
        dest_path: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Download an NC program from the CNC to a local file.

        Args:
            program_number: O-number to download (e.g. ``"O1234"`` or ``"1234"``).
            dest_path: Local file path to write.
            progress_cb: Optional ``(bytes_received, total_bytes)`` callback.
                         *total_bytes* is 0 (unknown) until upload completes.

        Raises:
            TransferError: On any FOCAS or I/O error.
        """
        # Parse numeric O-number
        num_str = program_number.upper().lstrip("O")
        try:
            prog_no = int(num_str)
        except ValueError:
            raise TransferError(
                f"Invalid program number: {program_number!r} "
                f"(expected numeric O-number like 'O1234' or '1234')"
            )

        self._connect()
        fwlib = get_fwlib()
        handle = ctypes.c_ushort(self._handle)
        upload_started = False
        received_data = bytearray()

        try:
            # Start upload session
            ret = fwlib.cnc_upstart(
                handle,
                ctypes.c_short(0),  # type 0 = NC program
                ctypes.c_int(prog_no),
            )
            if ret != EW_OK:
                raise FocasError("cnc_upstart", ret)
            upload_started = True

            # Read data blocks until end-of-program
            while True:
                buf = ODBUP()
                length = ctypes.c_ushort(256 + 4)  # sizeof data + header

                ret = fwlib.cnc_upload(
                    handle,
                    ctypes.byref(buf),
                    ctypes.byref(length),
                )
                if ret == EW_BUSY:
                    time.sleep(0.05)
                    continue
                if ret != EW_OK:
                    raise FocasError("cnc_upload", ret)

                # Extract actual data bytes (length includes the 4-byte header)
                data_len = length.value - 4
                if data_len <= 0:
                    break

                chunk = buf.data[:data_len]
                received_data.extend(chunk)

                if progress_cb is not None:
                    progress_cb(len(received_data), 0)

                # Check for program-end marker (% on its own line)
                if b"%" in chunk:
                    break

        except FocasError as exc:
            raise TransferError(str(exc)) from exc

        finally:
            # CRITICAL: always end the upload session
            if upload_started:
                try:
                    fwlib.cnc_upend(handle)
                except Exception:
                    logger.exception("cnc_upend failed during cleanup")
            self._disconnect()

        # Write received data to file
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(bytes(received_data))

        logger.info(
            "Received O%04d (%d bytes) from %s -> %s",
            prog_no,
            len(received_data),
            self.machine.display_name,
            dest_path,
        )

    def list_programs(self) -> list[ProgramInfo]:
        """List programs stored on the CNC.

        Reads the program directory in batches of 20 via ``cnc_rdprogdir2``.

        Returns:
            List of ProgramInfo with number, size, and comment.

        Raises:
            TransferError: On FOCAS error.
        """
        self._connect()
        fwlib = get_fwlib()
        handle = ctypes.c_ushort(self._handle)

        try:
            programs: list[ProgramInfo] = []
            top_prog = 0  # Start scanning from O0000

            while True:
                num = ctypes.c_short(_DIR_BATCH_SIZE)
                buf = (PRGDIR2 * _DIR_BATCH_SIZE)()

                ret = fwlib.cnc_rdprogdir2(
                    handle,
                    ctypes.c_short(0),  # type 0 = all programs
                    ctypes.byref(num),
                    ctypes.cast(buf, ctypes.POINTER(PRGDIR2)),
                )
                if ret != EW_OK:
                    raise FocasError("cnc_rdprogdir2", ret)

                count = num.value
                if count <= 0:
                    break

                for i in range(count):
                    entry = buf[i]
                    comment = entry.comment.decode("ascii", errors="replace").rstrip("\x00")
                    programs.append(
                        ProgramInfo(
                            number=f"O{entry.number:04d}",
                            name=f"O{entry.number:04d}",
                            size=entry.length,
                            comment=comment,
                        )
                    )
                    top_prog = entry.number

                # If we got fewer than requested, we've reached the end
                if count < _DIR_BATCH_SIZE:
                    break

                # Move past the last program we read
                top_prog += 1

            logger.info(
                "Listed %d programs on %s",
                len(programs),
                self.machine.display_name,
            )
            return programs

        except FocasError as exc:
            raise TransferError(str(exc)) from exc

        finally:
            self._disconnect()

    def is_reachable(self) -> bool:
        """Quick connectivity test — connect and read status.

        Returns True if the CNC responds, False otherwise.
        Never raises.
        """
        try:
            self._connect()
            fwlib = get_fwlib()
            status = ODBST()
            ret = fwlib.cnc_statinfo(
                ctypes.c_ushort(self._handle),
                ctypes.byref(status),
            )
            return ret == EW_OK
        except Exception:
            return False
        finally:
            self._disconnect()
