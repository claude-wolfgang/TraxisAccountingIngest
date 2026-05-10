"""Tests for tpm.proshop."""

import json
import time
import urllib.request

import pytest

from tpm import config, proshop


def test_token_caching():
    """Token is reused when still valid."""
    proshop._token = "cached-token"
    proshop._token_expiry = time.time() + 3600
    assert proshop.get_token() == "cached-token"


def test_token_refresh_when_expired(monkeypatch):
    """Token is refreshed when expired."""
    proshop._token = "old-token"
    proshop._token_expiry = time.time() - 100  # expired

    monkeypatch.setattr(config, "load_credentials", lambda: {
        "PROSHOP_CLIENT_ID": "test-id",
        "PROSHOP_CLIENT_SECRET": "test-secret",
    })

    class FakeResp:
        def read(self):
            return json.dumps({
                "access_token": "new-token",
                "expires_in": 86400,
            }).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

    token = proshop.get_token()
    assert token == "new-token"


def test_no_credentials_returns_none(monkeypatch):
    """Returns None when credentials file is missing."""
    monkeypatch.setattr(config, "load_credentials", lambda: {})
    assert proshop.get_token() is None


def test_lookup_customer_part_number_success(monkeypatch):
    """Returns customerPartNumber from GraphQL response."""
    monkeypatch.setattr(proshop, "graphql_query", lambda q, v=None: {
        "data": {"part": {"customerPartNumber": "55200029"}},
    })
    assert proshop.lookup_customer_part_number("NP000674") == "55200029"


def test_lookup_customer_part_number_not_found(monkeypatch):
    """Returns None when part has no customerPartNumber."""
    monkeypatch.setattr(proshop, "graphql_query", lambda q, v=None: {
        "data": {"part": {"customerPartNumber": None}},
    })
    assert proshop.lookup_customer_part_number("NP000674") is None


def test_lookup_customer_part_number_error(monkeypatch):
    """Returns None on API error."""
    monkeypatch.setattr(proshop, "graphql_query", lambda q, v=None: {
        "errors": [{"message": "timeout"}],
    })
    assert proshop.lookup_customer_part_number("NP000674") is None
