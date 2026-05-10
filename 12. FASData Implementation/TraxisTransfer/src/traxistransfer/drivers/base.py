"""Abstract base class for transfer drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from traxistransfer.models.machine import Machine


class ProgramInfo:
    """Metadata for a program stored on the CNC."""

    def __init__(self, number: str, name: str = "", size: int = 0, comment: str = ""):
        self.number = number
        self.name = name
        self.size = size
        self.comment = comment

    def __repr__(self) -> str:
        return f"ProgramInfo({self.number!r}, size={self.size})"


# Progress callback: (bytes_transferred, total_bytes) -> None
ProgressCallback = Callable[[int, int], None]


class TransferDriver(ABC):
    """Abstract interface for sending/receiving NC programs to a CNC machine."""

    def __init__(self, machine: Machine):
        self.machine = machine

    @abstractmethod
    def send_program(
        self,
        file_path: Path,
        program_number: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Send an NC program file to the CNC.

        Args:
            file_path: Local .nc file to send.
            program_number: O-number override (e.g. "O1234"). If None, parsed from file.
            progress_cb: Optional callback for progress updates.

        Raises:
            TransferError: On failure.
        """

    @abstractmethod
    def receive_program(
        self,
        program_number: str,
        dest_path: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Download an NC program from the CNC to a local file.

        Args:
            program_number: O-number to download (e.g. "O1234").
            dest_path: Local path to write the file.
            progress_cb: Optional callback for progress updates.

        Raises:
            TransferError: On failure.
        """

    @abstractmethod
    def list_programs(self) -> list[ProgramInfo]:
        """List programs stored on the CNC.

        Returns:
            List of ProgramInfo with number, size, comment.

        Raises:
            TransferError: On failure.
        """

    @abstractmethod
    def is_reachable(self) -> bool:
        """Check if the machine is reachable (quick connectivity test)."""


class TransferError(Exception):
    """Raised when a transfer operation fails."""
