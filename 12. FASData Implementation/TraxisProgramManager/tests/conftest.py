"""Shared fixtures for TPM test suite."""

import os

import pytest


@pytest.fixture
def mock_dropbox(tmp_path, monkeypatch):
    """Create fake Dropbox structure and patch config paths."""
    nc_root = tmp_path / "NC Programs"
    nc_root.mkdir()
    pf_root = tmp_path / "PART FILES Traxis"
    pf_root.mkdir()

    import tpm.config

    monkeypatch.setattr(tpm.config, "DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(tpm.config, "NC_PROGRAMS_ROOT", str(nc_root))
    monkeypatch.setattr(tpm.config, "PART_FILES_ROOT", str(pf_root))

    return tmp_path


@pytest.fixture
def mock_proshop(monkeypatch):
    """Patch ProShop API calls to avoid real HTTP."""
    import tpm.proshop

    monkeypatch.setattr(tpm.proshop, "get_token", lambda: "fake-token")
    monkeypatch.setattr(
        tpm.proshop, "graphql_query", lambda q, v=None: {"data": {}},
    )


@pytest.fixture
def sample_nc_file(tmp_path):
    """Create a realistic NC file with TPM header."""

    def _create(name="NP000674_OP60.nc", version=1, content=None):
        if content is None:
            content = (
                "%\n"
                "(PART: NP000674)\n"
                "(OP: 60)\n"
                f"(VERSION: {version})\n"
                "(WCS: G54 - X: Center, Y: Center, Z: Top of Stock)\n"
                "(POSTED: 2026-04-02 10:00)\n"
                "G90 G54\n"
                "T1 M6\n"
                "G0 X0 Y0\n"
                "%\n"
            )
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _create


@pytest.fixture(autouse=True)
def reset_proshop_token():
    """Reset ProShop token cache before each test."""
    import tpm.proshop

    tpm.proshop.reset_token()
