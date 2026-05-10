"""TPM configuration: paths, credentials, environment."""

import json
import logging
import os

logger = logging.getLogger("tpm.config")


def find_dropbox_root():
    """Locate Dropbox folder via info.json (works on any machine)."""
    for base in (os.environ.get("LOCALAPPDATA", ""),
                 os.environ.get("APPDATA", ""),
                 os.path.expanduser("~")):
        info = os.path.join(base, "Dropbox", "info.json")
        if os.path.isfile(info):
            try:
                with open(info, "r") as f:
                    data = json.load(f)
                for acct in ("personal", "business"):
                    if acct in data and "path" in data[acct]:
                        return data[acct]["path"]
            except Exception:
                pass
    return None


# Paths — DROPBOX_ROOT is None when Dropbox isn't installed.
# The Fusion entry point raises RuntimeError; tests patch these.
DROPBOX_ROOT = find_dropbox_root()
NC_PROGRAMS_ROOT = os.path.join(DROPBOX_ROOT, "NC Programs") if DROPBOX_ROOT else None
PART_FILES_ROOT = (
    os.path.join(DROPBOX_ROOT, "PART FILES Traxis") if DROPBOX_ROOT else None
)

# ProShop connection
PROSHOP_HOST = "traxismfg.adionsystems.com"
TOKEN_URL = f"https://{PROSHOP_HOST}/home/member/oauth/accesstoken"
GRAPHQL_URL = f"https://{PROSHOP_HOST}/api/graphql"
ENV_FILE = os.path.join(os.path.expanduser("~"), ".traxis.env")


def load_credentials():
    """Read key=value pairs from ENV_FILE or shared Dropbox path."""
    creds = {}
    env_path = ENV_FILE
    if not os.path.exists(env_path):
        # Try shared Dropbox path
        env_path = os.path.join(
            os.path.expanduser("~"), "Dropbox",
            "MACHINE COMM Traxis", "Keys", ".traxis.env",
        )
    if not os.path.exists(env_path):
        return creds
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    creds[key.strip()] = val.strip()
    except Exception as e:
        logger.error("Error reading %s: %s", env_path, e)
    return creds
