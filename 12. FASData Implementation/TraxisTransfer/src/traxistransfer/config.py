"""Load machines.json, .traxis.env, and preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path

from traxistransfer.constants import (
    ENV_CLIENT_ID, ENV_CLIENT_SECRET,
    ENV_PROSHOP_URL, FALLBACK_CLIENT_ID, FALLBACK_CLIENT_SECRET,
    TRAXIS_ENV_FILE,
)
from traxistransfer.models.machine import Machine


def load_env_file(path: Path | None = None) -> None:
    """Load key=value pairs from .traxis.env into os.environ (no override)."""
    env_path = path or TRAXIS_ENV_FILE
    if not env_path.exists():
        # Try Dropbox fallback
        alt = Path(r"D:\Dropbox\MACHINE COMM Traxis\Keys\.traxis.env")
        if alt.exists():
            env_path = alt
        else:
            return

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def get_proshop_url() -> str:
    """Return the ProShop API base URL."""
    return os.environ.get(ENV_PROSHOP_URL, "https://traxis.proshopweb.com")


def get_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) for ProShop OAuth.

    Prefers TRAXISTRANSFER_* env vars, falls back to PROSHOP_*.
    """
    client_id = os.environ.get(ENV_CLIENT_ID) or os.environ.get(FALLBACK_CLIENT_ID, "")
    client_secret = os.environ.get(ENV_CLIENT_SECRET) or os.environ.get(FALLBACK_CLIENT_SECRET, "")
    return client_id, client_secret


def load_machines(config_path: Path | None = None) -> list[Machine]:
    """Load machine definitions from machines.json."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "machines.json"

    with open(config_path, "r") as f:
        data = json.load(f)

    machines = []
    for entry in data.get("machines", []):
        machines.append(Machine.from_dict(entry))
    return machines
