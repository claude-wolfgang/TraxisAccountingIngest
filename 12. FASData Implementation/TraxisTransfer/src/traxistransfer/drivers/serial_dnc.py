"""RS-232 DNC serial driver — stub for future implementation."""

from __future__ import annotations

from pathlib import Path

from traxistransfer.drivers.base import TransferDriver, TransferError, ProgramInfo, ProgressCallback
from traxistransfer.models.machine import Machine


class SerialDncDriver(TransferDriver):
    """RS-232 serial DNC transfer (not yet implemented)."""

    def __init__(self, machine: Machine):
        super().__init__(machine)

    def send_program(self, file_path: Path, program_number: str | None = None,
                     progress_cb: ProgressCallback | None = None) -> None:
        raise NotImplementedError("Serial DNC driver not yet implemented")

    def receive_program(self, program_number: str, dest_path: Path,
                        progress_cb: ProgressCallback | None = None) -> None:
        raise NotImplementedError("Serial DNC driver not yet implemented")

    def list_programs(self) -> list[ProgramInfo]:
        raise NotImplementedError("Serial DNC driver not yet implemented")

    def is_reachable(self) -> bool:
        return False
