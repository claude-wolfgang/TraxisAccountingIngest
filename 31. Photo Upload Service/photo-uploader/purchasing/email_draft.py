"""Microsoft Graph helper: create email drafts in a dedicated folder.

Uses app-only OAuth with the same .traxis.env credentials P27/P34 use.
Drafts are written to a "Purchasing - To Review" folder under tom@traxismfg.com
so Wolfgang can find/Send them without them mixing with personal drafts.

Required Graph permission: Mail.ReadWrite (application). If only Mail.Read is
granted we'll get 403 on first draft creation — surfaced in logs.
"""

import os
import threading
import time
from pathlib import Path

import requests

# Reuse the same .traxis.env discovery pattern P31 already uses
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATHS = [
    PROJECT_ROOT / "1. Proshop Automations" / ".traxis.env",
    Path(os.environ.get("USERPROFILE", "")) / ".traxis.env",
]

DRAFT_MAILBOX = "tom@traxismfg.com"
DRAFT_FOLDER_NAME = "Purchasing - To Review"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


_state = {
    "token": None,
    "expires_at": 0,
    "folder_id": None,
    "env": None,
}
_lock = threading.Lock()


def _load_env():
    if _state["env"]:
        return _state["env"]
    for p in ENV_PATHS:
        if p.exists():
            env = {}
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            _state["env"] = env
            return env
    raise RuntimeError(".traxis.env not found in known paths")


def _token():
    with _lock:
        now = time.time()
        if _state["token"] and now < _state["expires_at"] - 60:
            return _state["token"]
        env = _load_env()
        url = f"https://login.microsoftonline.com/{env['GRAPH_TENANT_ID']}/oauth2/v2.0/token"
        r = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": env["GRAPH_CLIENT_ID"],
            "client_secret": env["GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
        _state["token"] = data["access_token"]
        _state["expires_at"] = now + data.get("expires_in", 3600)
        return _state["token"]


def _headers():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _ensure_folder():
    """Look up (or create) the 'Purchasing - To Review' folder ID. Cached."""
    with _lock:
        if _state["folder_id"]:
            return _state["folder_id"]

    # Search existing folders
    r = requests.get(
        f"{GRAPH_BASE}/users/{DRAFT_MAILBOX}/mailFolders",
        headers=_headers(),
        params={"$filter": f"displayName eq '{DRAFT_FOLDER_NAME}'"},
        timeout=15,
    )
    r.raise_for_status()
    found = r.json().get("value", [])
    if found:
        with _lock:
            _state["folder_id"] = found[0]["id"]
        return _state["folder_id"]

    # Create it
    r = requests.post(
        f"{GRAPH_BASE}/users/{DRAFT_MAILBOX}/mailFolders",
        headers=_headers(),
        json={"displayName": DRAFT_FOLDER_NAME},
        timeout=15,
    )
    r.raise_for_status()
    folder_id = r.json()["id"]
    with _lock:
        _state["folder_id"] = folder_id
    return folder_id


def create_draft(to_email, subject, body, body_type="Text"):
    """Create a draft message in the Purchasing folder. Returns the draft message ID.

    Raises requests.HTTPError on failure. Caller should catch + degrade gracefully
    (e.g. status='pending' if drafting fails so the order isn't lost).
    """
    folder_id = _ensure_folder()
    payload = {
        "subject": subject,
        "body": {"contentType": body_type, "content": body},
        "toRecipients": [{"emailAddress": {"address": to_email}}],
    }
    r = requests.post(
        f"{GRAPH_BASE}/users/{DRAFT_MAILBOX}/mailFolders/{folder_id}/messages",
        headers=_headers(),
        json=payload,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["id"]


def draft_web_url(message_id):
    """Public Outlook web link to a draft (operator clicks to review/Send)."""
    return f"https://outlook.office.com/mail/inbox/id/{message_id}"
