"""
Configuration loader for TraxisCapture.

Reads capture_config.json from the add-in directory.
Falls back to sensible defaults if the file is missing.
"""

import os
import json
import re

ADDIN_FOLDER = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(ADDIN_FOLDER, "capture_config.json")

_config = None


def load_config():
    """Load configuration from capture_config.json."""
    global _config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _config = json.load(f)
    except Exception:
        _config = {}
    return _config


def get_config():
    """Return loaded config, loading if needed."""
    if _config is None:
        load_config()
    return _config


def get_output_dir():
    """Return the full path to the diffs output directory."""
    cfg = get_config()
    dropbox = cfg.get("dropbox_root", r"D:\Dropbox\MACHINE COMM Traxis")
    rel = cfg.get("output_dir", "Programming Sessions/diffs")
    path = os.path.join(dropbox, rel)
    os.makedirs(path, exist_ok=True)
    return path


def get_naming_pattern():
    """Return compiled regex for setup naming convention."""
    cfg = get_config()
    return re.compile(cfg.get("naming_pattern", r"^[A-Z0-9_-]+:\d+$"))


def get_nc_programs_root():
    """Return NC programs root directory."""
    cfg = get_config()
    return cfg.get("nc_programs_root", r"D:\Dropbox\NC Programs")


def get_skip_keywords():
    """Return list of keywords for fixture/non-part setups."""
    cfg = get_config()
    return cfg.get("skip_keywords", [
        "fixture", "soft jaw", "softjaw", "jaws", "workholding", "vise"])


def get_part_number_patterns():
    """Return compiled regex list for part number detection."""
    cfg = get_config()
    raw = cfg.get("part_number_patterns", [
        r"^(\d{2,5}-\d{3,5})",
        r"^(\d{4,5}-[A-Z])",
        r"^(SA\d{4,8})",
        r"^(\d{4,6})",
    ])
    return [re.compile(p, re.IGNORECASE) for p in raw]


def get_op_start():
    """Return starting OP number (default 60)."""
    cfg = get_config()
    return cfg.get("op_start_number", 60)


def get_op_increment():
    """Return OP number increment (default 10)."""
    cfg = get_config()
    return cfg.get("op_increment", 10)
