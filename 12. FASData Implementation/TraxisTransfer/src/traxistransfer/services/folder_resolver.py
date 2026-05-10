"""Smart folder resolution for NC program files."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from traxistransfer.constants import NC_PROGRAMS_ROOT, NC_FILES_FOR_TRANSFER
from traxistransfer.models.machine import Machine
from traxistransfer.services.proshop_client import ProShopClient
from traxistransfer.services import audit_log


class FolderResolver:
    """Resolves the best folder to show for a given machine."""

    def __init__(
        self,
        proshop: ProShopClient | None = None,
        db_conn: sqlite3.Connection | None = None,
    ):
        self._proshop = proshop
        self._db = db_conn

    def resolve(self, machine: Machine) -> list[Path]:
        """Return ordered list of folders to search for NC programs.

        Resolution chain:
        1. ProShop: active WO -> part number -> NC Programs/{PartNumber}/
        2. Remembered: last folder operator used for this machine
        3. Default: NC Files For Transfer root
        """
        folders: list[Path] = []

        # 1. Try ProShop lookup
        if self._proshop and machine.proshop_pot_id:
            try:
                wo = self._proshop.get_active_wo_for_workcell(
                    machine.proshop_pot_id
                )
                if wo:
                    part_number = wo.get("partNumber", "")
                    wo_number = wo.get("woNumber", "")

                    # Check NC Programs/{PartNumber}/ (TPM output)
                    if part_number:
                        part_folder = NC_PROGRAMS_ROOT / part_number
                        if part_folder.is_dir():
                            folders.append(part_folder)

                        # Also try customer part number
                        customer_pn = self._proshop.get_customer_part_number(
                            part_number
                        )
                        if customer_pn:
                            cust_folder = NC_PROGRAMS_ROOT / customer_pn
                            if (
                                cust_folder.is_dir()
                                and cust_folder not in folders
                            ):
                                folders.append(cust_folder)

                    # Check NC Files For Transfer/{WO}/
                    if wo_number:
                        wo_folder = NC_FILES_FOR_TRANSFER / wo_number
                        if wo_folder.is_dir():
                            folders.append(wo_folder)
            except Exception:
                pass  # Silently fall back if ProShop unreachable

        # 2. Try remembered folder
        if self._db:
            try:
                remembered = audit_log.get_folder_memory(
                    self._db, machine.id
                )
                if remembered:
                    remembered_path = Path(remembered)
                    if (
                        remembered_path.is_dir()
                        and remembered_path not in folders
                    ):
                        folders.append(remembered_path)
            except Exception:
                pass

        # 3. Default fallback
        if NC_FILES_FOR_TRANSFER.is_dir() and NC_FILES_FOR_TRANSFER not in folders:
            folders.append(NC_FILES_FOR_TRANSFER)
        if NC_PROGRAMS_ROOT.is_dir() and NC_PROGRAMS_ROOT not in folders:
            folders.append(NC_PROGRAMS_ROOT)

        return folders

    def save_choice(self, machine: Machine, folder: Path) -> None:
        """Persist the operator's folder choice for this machine."""
        if self._db:
            audit_log.save_folder_memory(self._db, machine.id, str(folder))

    @staticmethod
    def list_nc_files(folders: list[Path]) -> list[dict]:
        """List .nc files from all resolved folders, merged and deduplicated.

        Returns list of dicts: {path, name, size, modified, folder, version, op_number}
        Parses TPM naming: {PartNumber}_OP{XX}_v{N}.nc
        """
        seen: set[str] = set()
        files: list[dict] = []
        tpm_pattern = re.compile(
            r"^(.+)_OP(\d+)_v(\d+)\.nc$", re.IGNORECASE
        )

        for folder in folders:
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                if f.suffix.lower() == ".nc" and f.name not in seen:
                    seen.add(f.name)
                    stat = f.stat()
                    entry: dict = {
                        "path": f,
                        "name": f.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "folder": str(folder),
                        "version": None,
                        "op_number": None,
                        "part_number": None,
                    }
                    m = tpm_pattern.match(f.name)
                    if m:
                        entry["part_number"] = m.group(1)
                        entry["op_number"] = int(m.group(2))
                        entry["version"] = int(m.group(3))
                    files.append(entry)

        # Sort: most recently modified first
        files.sort(key=lambda x: x["modified"], reverse=True)
        return files

    @staticmethod
    def find_latest_version(file_name: str, folders: list[Path]) -> dict | None:
        """Find the latest version of a file on disk.

        Given a filename like ``67890_OP60_v3.nc``, parse out the PN+OP, scan
        *folders* for all versions of that PN+OP, and return the file dict for
        the highest version number.  If the file doesn't match TPM naming,
        return it as-is if it still exists on disk.
        """
        tpm_pattern = re.compile(
            r"^(.+)_OP(\d+)_v(\d+)\.nc$", re.IGNORECASE
        )
        m = tpm_pattern.match(file_name)

        if not m:
            # Non-TPM file — look for exact match on disk
            for folder in folders:
                candidate = folder / file_name
                if candidate.is_file():
                    stat = candidate.stat()
                    return {
                        "path": candidate,
                        "name": candidate.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "folder": str(folder),
                        "version": None,
                        "op_number": None,
                        "part_number": None,
                    }
            return None

        # TPM file — find all versions with same PN+OP
        target_pn = m.group(1)
        target_op = m.group(2)
        best: dict | None = None
        best_version = -1

        for folder in folders:
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                if f.suffix.lower() != ".nc":
                    continue
                fm = tpm_pattern.match(f.name)
                if not fm:
                    continue
                if fm.group(1) == target_pn and fm.group(2) == target_op:
                    ver = int(fm.group(3))
                    if ver > best_version:
                        best_version = ver
                        stat = f.stat()
                        best = {
                            "path": f,
                            "name": f.name,
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "folder": str(folder),
                            "version": ver,
                            "op_number": int(fm.group(2)),
                            "part_number": fm.group(1),
                        }

        return best
