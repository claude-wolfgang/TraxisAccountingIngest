"""
Configuration loading for Programming Timer add-in.
"""

import json
import os
import socket

# Default configuration
DEFAULTS = {
    "company_file_patterns": ["hub://Traxis", "D:/Dropbox/MACHINE COMM Traxis"],
    "idle_timeout_seconds": 120,
    "gap_threshold_seconds": 1800,
    "log_folder": "",
    "programmer_name": "",
    "poll_interval_seconds": 15
}

_config = None
_config_path = None


def get_addin_folder():
    """Return the folder containing this add-in."""
    return os.path.dirname(os.path.abspath(__file__))


def get_config_path():
    """Return path to the configuration file."""
    return os.path.join(get_addin_folder(), "timer_config.json")


def load_config():
    """Load configuration from timer_config.json, then overlay timer_config.local.json."""
    global _config, _config_path

    _config_path = get_config_path()
    _config = DEFAULTS.copy()

    # Load shared config (syncs via Dropbox)
    if os.path.exists(_config_path):
        try:
            with open(_config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                _config.update(user_config)
        except Exception as e:
            print("[Timer] Warning: Could not load config: {}".format(e))

    # Load local override (per-machine, stored outside Dropbox)
    appdata = os.environ.get("APPDATA", "")
    local_dir = os.path.join(appdata, "Traxis", "ProgrammingTimer")
    _try_create_folder(local_dir)
    local_path = os.path.join(local_dir, "timer_config.local.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                local_config = json.load(f)
                _config.update(local_config)
                print("[Timer] Loaded local config override: {}".format(local_path))
        except Exception as e:
            print("[Timer] Warning: Could not load local config: {}".format(e))

    return _config


def get_config():
    """Return the current configuration, loading if necessary."""
    global _config
    if _config is None:
        load_config()
    return _config


def get_log_folder():
    """Determine the log folder, trying configured path, D drive, C drive, then Documents."""
    config = get_config()

    # Try configured folder first
    if config.get("log_folder"):
        folder = config["log_folder"]
        if os.path.exists(folder) or _try_create_folder(folder):
            return folder

    # Try D: drive Dropbox
    d_path = os.path.join(
        "D:", os.sep, "Dropbox", "MACHINE COMM Traxis",
        "Proshop Automation and Claude Projects",
        "1. Proshop Automations", "ProgrammingTimer"
    )
    if os.path.exists(d_path) or _try_create_folder(d_path):
        return d_path

    # Try C: drive user Dropbox
    username = os.environ.get("USERNAME", "")
    c_path = os.path.join(
        "C:", os.sep, "Users", username, "Dropbox",
        "MACHINE COMM Traxis", "Proshop Automation and Claude Projects",
        "1. Proshop Automations", "ProgrammingTimer"
    )
    if os.path.exists(c_path) or _try_create_folder(c_path):
        return c_path

    # Last resort: Documents folder
    docs_path = os.path.join(
        "C:", os.sep, "Users", username, "Documents", "ProgrammingTimer"
    )
    _try_create_folder(docs_path)
    return docs_path


def _try_create_folder(path):
    """Try to create a folder, return True if successful or already exists."""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def get_programmer_name():
    """Return the programmer name (configured or Windows username)."""
    config = get_config()
    name = config.get("programmer_name", "")
    if not name:
        name = os.environ.get("USERNAME", "Unknown")
    return name


def get_seat_name():
    """Return the computer/seat name."""
    return socket.gethostname()


def is_company_file(document_path):
    """Check if a document path matches any company file pattern."""
    if not document_path:
        return False

    config = get_config()
    patterns = config.get("company_file_patterns", [])

    normalized_path = document_path.replace("/", os.sep).lower()

    for pattern in patterns:
        normalized_pattern = pattern.replace("/", os.sep).lower()
        if normalized_pattern in normalized_path:
            return True

    return False


def get_idle_timeout():
    """Return idle timeout in seconds."""
    return get_config().get("idle_timeout_seconds", 120)


def get_gap_threshold():
    """Return gap threshold in seconds."""
    return get_config().get("gap_threshold_seconds", 1800)


def get_poll_interval():
    """Return polling interval in seconds."""
    return get_config().get("poll_interval_seconds", 15)
