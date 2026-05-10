"""Transfer service — orchestrates driver selection, execution, and logging."""

from __future__ import annotations

import os
import time
from pathlib import Path

from traxistransfer.constants import DriverType, TransferDirection
from traxistransfer.drivers.base import TransferDriver, TransferError, ProgressCallback
from traxistransfer.drivers.fanuc_focas import FanucFocasDriver
from traxistransfer.drivers.haas_chc_ssh import HaasChcSshDriver
from traxistransfer.drivers.haas_ngc_smb import HaasNgcSmbDriver
from traxistransfer.drivers.serial_dnc import SerialDncDriver
from traxistransfer.models.machine import Machine
from traxistransfer.models.transfer import TransferResult
from traxistransfer.services import audit_log


_DRIVER_MAP = {
    DriverType.FOCAS: FanucFocasDriver,
    DriverType.HAAS_CHC: HaasChcSshDriver,
    DriverType.HAAS_NGC: HaasNgcSmbDriver,
    DriverType.SERIAL: SerialDncDriver,
}


def get_driver(machine: Machine) -> TransferDriver:
    """Create the appropriate driver for a machine."""
    cls = _DRIVER_MAP.get(machine.driver)
    if cls is None:
        raise TransferError(f"Unknown driver type: {machine.driver}")
    return cls(machine)


def send_program(
    machine: Machine,
    file_path: Path,
    program_number: str | None = None,
    progress_cb: ProgressCallback | None = None,
    db_conn=None,
    work_order: str = "",
    part_number: str = "",
) -> TransferResult:
    """Send a program to a machine and log the result."""
    driver = get_driver(machine)
    start = time.monotonic()
    error_msg = ""
    success = True

    try:
        driver.send_program(file_path, program_number, progress_cb)
    except (TransferError, Exception) as e:
        success = False
        error_msg = str(e)

    duration = time.monotonic() - start
    file_size = file_path.stat().st_size if file_path.exists() else 0

    result = TransferResult(
        machine_id=machine.id,
        machine_name=machine.name,
        driver=machine.driver.value,
        direction=TransferDirection.SEND,
        file_path=str(file_path),
        file_name=file_path.name,
        program_number=program_number or "",
        file_size_bytes=file_size,
        duration_seconds=round(duration, 2),
        success=success,
        error_message=error_msg,
        work_order=work_order,
        part_number=part_number,
    )

    if db_conn:
        try:
            audit_log.log_transfer(
                db_conn,
                machine_id=result.machine_id,
                machine_name=result.machine_name,
                driver=result.driver,
                direction=result.direction.value,
                file_path=result.file_path,
                file_name=result.file_name,
                program_number=result.program_number,
                file_size_bytes=result.file_size_bytes,
                duration_seconds=result.duration_seconds,
                success=result.success,
                error_message=result.error_message,
                work_order=result.work_order,
                part_number=result.part_number,
            )
        except Exception:
            pass  # Don't fail the transfer because of logging

    return result


def receive_program(
    machine: Machine,
    program_number: str,
    dest_path: Path,
    progress_cb: ProgressCallback | None = None,
    db_conn=None,
) -> TransferResult:
    """Receive a program from a machine and log the result."""
    driver = get_driver(machine)
    start = time.monotonic()
    error_msg = ""
    success = True

    try:
        driver.receive_program(program_number, dest_path, progress_cb)
    except (TransferError, Exception) as e:
        success = False
        error_msg = str(e)

    duration = time.monotonic() - start
    file_size = dest_path.stat().st_size if dest_path.exists() else 0

    result = TransferResult(
        machine_id=machine.id,
        machine_name=machine.name,
        driver=machine.driver.value,
        direction=TransferDirection.RECEIVE,
        file_path=str(dest_path),
        file_name=dest_path.name,
        program_number=program_number,
        file_size_bytes=file_size,
        duration_seconds=round(duration, 2),
        success=success,
        error_message=error_msg,
    )

    if db_conn:
        try:
            audit_log.log_transfer(
                db_conn,
                machine_id=result.machine_id,
                machine_name=result.machine_name,
                driver=result.driver,
                direction=result.direction.value,
                file_path=result.file_path,
                file_name=result.file_name,
                program_number=result.program_number,
                file_size_bytes=result.file_size_bytes,
                duration_seconds=result.duration_seconds,
                success=result.success,
                error_message=result.error_message,
            )
        except Exception:
            pass

    return result
