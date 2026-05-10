"""Paths, defaults, and enums used across TraxisTransfer."""

from pathlib import Path
import json
import os
from enum import Enum


def _find_dropbox_root():
    """Auto-detect Dropbox root via info.json, falling back to common locations."""
    info_path = Path(os.environ.get("LOCALAPPDATA", ""), "Dropbox", "info.json")
    if info_path.exists():
        try:
            data = json.loads(info_path.read_text())
            for acct in ("personal", "business"):
                if acct in data and "path" in data[acct]:
                    return Path(data[acct]["path"])
        except (json.JSONDecodeError, KeyError):
            pass
    for drive in ("D:", "C:"):
        p = Path(drive, "Dropbox")
        if p.exists():
            return p
    return Path(r"D:\Dropbox")


_DROPBOX = _find_dropbox_root()

# --- File system paths ---
NC_PROGRAMS_ROOT = _DROPBOX / "NC Programs"
NC_FILES_FOR_TRANSFER = _DROPBOX / "NC Files For Transfer"
FASDATA_DIR = Path(r"C:\FASData")
DB_PATH = FASDATA_DIR / "traxistransfer.db"
FALLBACK_DB_PATH = Path(__file__).resolve().parent.parent.parent / "transfer_log.db"

# --- FOCAS defaults ---
DEFAULT_FOCAS_PORT = 8193
FOCAS_TIMEOUT_MS = 10_000
FOCAS_CHUNK_SIZE = 1024
FOCAS_MAX_RETRIES = 3
FOCAS_RETRY_DELAY_S = 5

# --- Haas SSH defaults ---
HAAS_PI_IP = "10.1.1.149"
HAAS_PI_USER = "haasmill1"
HAAS_PI_PORT = 22
HAAS_USB_SHARE_PATH = "/mnt/usb_share"
HAAS_PRE_COPY_SCRIPT = "/home/haasmill1/pre-copy.sh"
HAAS_POST_COPY_SCRIPT = "/home/haasmill1/post-copy.sh"
HAAS_SSH_MAX_RETRIES = 3
HAAS_SSH_RETRY_DELAY_S = 5

# --- Status checker ---
STATUS_CHECK_INTERVAL_S = 30

# --- Env var names ---
ENV_CLIENT_ID = "TRAXISTRANSFER_CLIENT_ID"
ENV_CLIENT_SECRET = "TRAXISTRANSFER_CLIENT_SECRET"
ENV_PROSHOP_URL = "PROSHOP_URL"
FALLBACK_CLIENT_ID = "PROSHOP_CLIENT_ID"
FALLBACK_CLIENT_SECRET = "PROSHOP_CLIENT_SECRET"
TRAXIS_ENV_FILE = Path.home() / ".traxis.env"


class DriverType(str, Enum):
    """Supported transfer driver types."""
    FOCAS = "focas"
    HAAS_CHC = "haas_chc"
    HAAS_NGC = "haas_ngc"
    SERIAL = "serial"


class TransferDirection(str, Enum):
    """Transfer direction."""
    SEND = "send"
    RECEIVE = "receive"
