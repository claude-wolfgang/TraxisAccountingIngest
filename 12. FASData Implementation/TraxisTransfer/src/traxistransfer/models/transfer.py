"""Transfer result data model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from traxistransfer.constants import TransferDirection


@dataclass
class TransferResult:
    """Outcome of a program transfer operation."""

    machine_id: str
    machine_name: str
    driver: str
    direction: TransferDirection
    file_path: str
    file_name: str
    program_number: str
    file_size_bytes: int
    duration_seconds: float
    success: bool
    error_message: str = ""
    work_order: str = ""
    part_number: str = ""
    operator: str = ""
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
