"""TPM naming logic: OP numbers, versioning, header parsing."""

import glob
import logging
import os
import re

logger = logging.getLogger("tpm.naming")


def get_operation_number(setup_number):
    """Setup 1 -> OP60, Setup 2 -> OP70, etc."""
    return 60 + (setup_number - 1) * 10


def get_current_version(output_folder, part_number, op_number):
    """Return the current version number, or 0 if no prior version exists.

    Reads the (VERSION: N) header from the existing NC file first,
    then falls back to scanning for versioned filenames.
    """
    # Check non-versioned filename (current naming convention)
    nc_path = os.path.join(output_folder, f"{part_number}_OP{op_number}.nc")
    if os.path.isfile(nc_path):
        ver = read_version_from_header(nc_path)
        if ver > 0:
            return ver

    # Fall back to versioned filenames (legacy)
    pattern = os.path.join(output_folder, f"{part_number}_OP{op_number}_v*.nc")
    existing = glob.glob(pattern)
    if not existing:
        return 0
    versions = []
    for f in existing:
        match = re.search(r'_v(\d+)\.nc$', os.path.basename(f))
        if match:
            versions.append(int(match.group(1)))
    return max(versions) if versions else 0


def read_version_from_header(nc_path):
    """Read version number from (VERSION: N) header comment in NC file."""
    try:
        with open(nc_path, 'r', encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f):
                if i > 20:
                    break
                match = re.search(r'\(VERSION:\s*(\d+)\)', line)
                if match:
                    return int(match.group(1))
    except Exception:
        pass
    return 0


def get_program_number(op_number, version):
    """Generate 4-digit program number from OP and version.

    OP60 v1 -> 0061, OP60 v2 -> 0062, OP70 v1 -> 0071, etc.
    The last digit indicates the version/revision.
    """
    return str(op_number + version).zfill(4)


def get_next_version(output_folder, part_number, op_number, has_changes=None):
    """Determine the version number for this post.

    Args:
        output_folder: Path to NC Programs/{part_number}/
        part_number: ProShop part number
        op_number: Operation number (60, 70, etc.)
        has_changes: None (unknown), True (toolpaths changed), or False
            (no changes). When False, reuses the current version.
            When True or None, increments.
    """
    current = get_current_version(output_folder, part_number, op_number)

    if current == 0:
        return 1  # First post

    if has_changes is False:
        logger.debug("No toolpath changes -- reusing v%d", current)
        return current  # Same version, program unchanged

    return current + 1  # Changed or unknown -> new version
