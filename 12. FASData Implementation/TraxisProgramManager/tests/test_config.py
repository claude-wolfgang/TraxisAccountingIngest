"""Tests for tpm.config."""

import json
import os

import pytest

from tpm import config


def test_find_dropbox_root_with_info_json(tmp_path, monkeypatch):
    """find_dropbox_root returns path from info.json."""
    dropbox_dir = tmp_path / "Dropbox"
    dropbox_dir.mkdir()
    info = dropbox_dir / "info.json"
    info.write_text(
        json.dumps({"personal": {"path": str(tmp_path / "MyDropbox")}}),
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.find_dropbox_root() == str(tmp_path / "MyDropbox")


def test_find_dropbox_root_missing(tmp_path, monkeypatch):
    """find_dropbox_root returns None when no info.json exists."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda _p: str(tmp_path))
    assert config.find_dropbox_root() is None


def test_load_credentials_from_file(tmp_path, monkeypatch):
    """load_credentials reads key=value pairs."""
    env_file = tmp_path / ".traxis.env"
    env_file.write_text(
        "PROSHOP_CLIENT_ID=abc123\nPROSHOP_CLIENT_SECRET=secret456\n",
    )
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))
    creds = config.load_credentials()
    assert creds["PROSHOP_CLIENT_ID"] == "abc123"
    assert creds["PROSHOP_CLIENT_SECRET"] == "secret456"


def test_load_credentials_missing_file(tmp_path, monkeypatch):
    """load_credentials returns empty dict when file missing."""
    monkeypatch.setattr(config, "ENV_FILE", str(tmp_path / "nonexistent"))
    monkeypatch.setattr(os.path, "expanduser", lambda _p: str(tmp_path / "x"))
    creds = config.load_credentials()
    assert creds == {}


def test_load_credentials_skips_comments(tmp_path, monkeypatch):
    """load_credentials ignores comment lines."""
    env_file = tmp_path / ".traxis.env"
    env_file.write_text("# Comment\nKEY=value\n")
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))
    creds = config.load_credentials()
    assert creds["KEY"] == "value"
