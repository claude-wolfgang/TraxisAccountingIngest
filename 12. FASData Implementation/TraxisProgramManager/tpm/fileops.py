"""TPM file operations: discovery, copy, auto-catch, folder lookup."""

import glob
import logging
import os
import shutil
import time
from datetime import datetime

from . import config, proshop

logger = logging.getLogger("tpm.fileops")

# Default folders where Fusion writes NC files (patchable in tests)
DEFAULT_SEARCH_FOLDERS = [
    r"D:\Users\MainPC\Documents\NC Files For Transfer",
    os.path.expanduser(r"~\Documents\NC Files For Transfer"),
    os.path.expanduser(r"~\Documents\Fusion 360\NC Programs"),
    os.path.expanduser(r"~\Documents"),
]


def find_part_files_folder(part_number, customer_part_number=None):
    """Search PART FILES Traxis for a folder containing this part.

    Lookup order:
    1. Use provided customer_part_number
    2. Query ProShop API for customerPartNumber
    3. Fall back to searching with the ProShop part number
    """
    part_files_root = config.PART_FILES_ROOT
    if not part_files_root or not os.path.isdir(part_files_root):
        return None

    # Try customer part number first (from caller or API)
    cust_pn = customer_part_number
    if not cust_pn:
        cust_pn = proshop.lookup_customer_part_number(part_number)

    if cust_pn:
        search = os.path.join(part_files_root, '*', cust_pn)
        matches = glob.glob(search)
        if matches:
            logger.info(
                "Found part folder (customer PN %s): %s", cust_pn, matches[0],
            )
            return matches[0]
        logger.debug("No folder found for customer PN '%s'", cust_pn)

    # Fall back to ProShop part number (original behavior)
    search = os.path.join(part_files_root, '*', part_number)
    matches = glob.glob(search)
    if matches:
        logger.info("Found part folder: %s", matches[0])
        return matches[0]
    return None


def copy_to_part_folder(nc_file_path, part_files_folder):
    """Copy an NC file into a part folder. Returns dest path or None."""
    try:
        dest = os.path.join(part_files_folder, os.path.basename(nc_file_path))
        shutil.copy2(nc_file_path, dest)
        logger.info("Copied to part folder: %s", dest)
        return dest
    except Exception as e:
        logger.error("Could not copy to part folder: %s", e)
        return None


def get_output_folders(info):
    """Return all folders where Fusion might have placed the NC file."""
    folders = [info['output_folder']]
    for candidate in DEFAULT_SEARCH_FOLDERS:
        if os.path.isdir(candidate) and candidate not in folders:
            folders.append(candidate)
    return folders


def find_posted_nc(fusion_name, info, max_age=300, retries=4):
    """Find the NC file Fusion just posted by exact filename.

    Args:
        fusion_name: Expected filename (e.g. "0061.nc")
        info: Dict with 'output_folder' key
        max_age: Max file age in seconds (default 300)
        retries: Number of retry attempts (default 4)
    """
    folders = get_output_folders(info)
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(1.0)

        for folder in folders:
            if not os.path.isdir(folder):
                continue
            try:
                listing = os.listdir(folder)
            except Exception:
                continue

            # Case-insensitive match for Windows
            for f in listing:
                if f.lower() == fusion_name.lower():
                    candidate = os.path.join(folder, f)
                    try:
                        age = datetime.now().timestamp() - \
                            os.path.getmtime(candidate)
                    except Exception:
                        age = 0
                    if age < max_age:
                        logger.info(
                            "Found: %s (%.0fs old)", candidate, age,
                        )
                        return candidate
                    break

    return None


def process_posted_files(naming_state, delay=2.0):
    """Process posted NC files -- find and copy to NC Programs and PART FILES.

    Args:
        naming_state: Dict of {setup_name: info_dict}
        delay: Seconds to wait before scanning (default 2.0 for Fusion flush)
    """
    try:
        if delay > 0:
            time.sleep(delay)
        logger.info("Processing %d setup(s)", len(naming_state))

        for setup_name, info in naming_state.items():
            desired_name = info['filename']
            fusion_name = info.get('fusion_filename', desired_name)

            nc_path = find_posted_nc(fusion_name, info)
            if not nc_path and desired_name != fusion_name:
                nc_path = find_posted_nc(desired_name, info)

            if nc_path:
                logger.info("Found: %s", nc_path)

                # Copy to Dropbox NC Programs folder
                dropbox_folder = info['output_folder']
                dropbox_path = os.path.join(dropbox_folder, desired_name)
                if nc_path != dropbox_path:
                    os.makedirs(dropbox_folder, exist_ok=True)
                    try:
                        shutil.copy2(nc_path, dropbox_path)
                        logger.info("Copied to: %s", dropbox_path)
                    except Exception as e:
                        logger.error("Copy to Dropbox failed: %s", e)

                # Copy to PART FILES folder
                pf = info.get('part_files_folder')
                if pf and os.path.isdir(pf):
                    copy_to_part_folder(nc_path, pf)
            else:
                logger.debug(
                    "'%s' not found -- setup not posted", fusion_name,
                )

        logger.info("Post processing complete")

    except Exception as e:
        logger.error("Error: %s", e)


def auto_catch_posted_files(part_number, delay=2.0, max_age=60,
                            search_folders=None):
    """Auto-catch: find recently posted NC files and copy to Dropbox.

    Runs when programmer posts without TPM dialog. Scans for .nc files
    modified within max_age seconds, copies to NC Programs/{part_number}/.

    Args:
        part_number: ProShop part number
        delay: Seconds to wait before scanning
        max_age: Max file age in seconds to consider "recent"
        search_folders: Override DEFAULT_SEARCH_FOLDERS (for testing)
    """
    try:
        if delay > 0:
            time.sleep(delay)
        logger.info("Scanning for recent NC files (part: %s)", part_number)

        if search_folders is not None:
            folders = search_folders
        else:
            folders = [f for f in DEFAULT_SEARCH_FOLDERS if os.path.isdir(f)]

        if not folders:
            logger.info("No search folders found")
            return

        now = datetime.now().timestamp()
        found = []
        for folder in folders:
            try:
                for f in os.listdir(folder):
                    if not f.lower().endswith('.nc'):
                        continue
                    fpath = os.path.join(folder, f)
                    try:
                        age = now - os.path.getmtime(fpath)
                    except Exception:
                        continue
                    if age < max_age:
                        found.append(fpath)
                        logger.info("Found: %s (%.0fs old)", fpath, age)
            except Exception:
                continue

        if not found:
            logger.info("No recent NC files found")
            return

        nc_root = config.NC_PROGRAMS_ROOT
        if not nc_root:
            logger.error("NC_PROGRAMS_ROOT not configured")
            return

        dest_folder = os.path.join(nc_root, part_number)
        os.makedirs(dest_folder, exist_ok=True)

        for nc_path in found:
            dest = os.path.join(dest_folder, os.path.basename(nc_path))
            if nc_path == dest:
                continue
            try:
                shutil.copy2(nc_path, dest)
                logger.info("Copied to: %s", dest)
            except Exception as e:
                logger.error("Copy failed: %s", e)

        # Also copy to PART FILES if we can find the folder
        try:
            pf = find_part_files_folder(part_number)
            if pf and os.path.isdir(pf):
                for nc_path in found:
                    copy_to_part_folder(nc_path, pf)
        except Exception as e:
            logger.error("PART FILES copy failed: %s", e)

        logger.info("Auto-catch complete")

    except Exception as e:
        logger.error("Error: %s", e)
