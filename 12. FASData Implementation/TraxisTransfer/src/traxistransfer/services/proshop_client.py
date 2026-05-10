"""Lightweight ProShop GraphQL client for TraxisTransfer."""

from __future__ import annotations

import threading
import time
import requests

from traxistransfer.config import get_proshop_url, get_client_credentials


class GraphQLError(Exception):
    """Raised on GraphQL query failure."""


class ProShopClient:
    """Thread-safe ProShop GraphQL client with OAuth token caching."""

    GRAPHQL_PATH = "/api/graphql"
    TOKEN_PATH = "/home/member/oauth/accesstoken"
    SCOPE = "parts:r+workorders:r"

    def __init__(self):
        self._base_url = get_proshop_url()
        self._client_id, self._client_secret = get_client_credentials()
        self._token: str | None = None
        self._token_expiry: float = 0
        self._lock = threading.Lock()

    @property
    def _graphql_url(self) -> str:
        return self._base_url.rstrip("/") + self.GRAPHQL_PATH

    @property
    def _token_url(self) -> str:
        return self._base_url.rstrip("/") + self.TOKEN_PATH

    def _refresh_token(self) -> str:
        """Get a fresh OAuth token."""
        if not self._client_id or not self._client_secret:
            raise GraphQLError("ProShop credentials not configured")

        resp = requests.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self.SCOPE,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        # Refresh 5 minutes before expiry
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in - 300
        return self._token

    def _get_token(self) -> str:
        """Get a valid token, refreshing if needed. Thread-safe."""
        with self._lock:
            if self._token and time.time() < self._token_expiry:
                return self._token
            return self._refresh_token()

    def query(self, graphql_query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query. Retries once on 401."""
        token = self._get_token()
        for attempt in range(2):
            resp = requests.post(
                self._graphql_url,
                json={"query": graphql_query, "variables": variables or {}},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if resp.status_code == 401 and attempt == 0:
                with self._lock:
                    self._token = None
                    self._token_expiry = 0
                token = self._get_token()
                continue
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                raise GraphQLError(f"GraphQL errors: {result['errors']}")
            return result.get("data", {})
        raise GraphQLError("Query failed after retry")

    def get_active_wo_for_workcell(self, pot_id: str) -> dict | None:
        """Get active work order for a work cell.

        Returns dict with 'woNumber' and 'partNumber' or None.
        """
        gql = """
        query($potId: String!) {
            workCell(potId: $potId) {
                activeWorkOrder {
                    woNumber
                    partNumber
                }
            }
        }
        """
        try:
            data = self.query(gql, {"potId": pot_id})
            wc = data.get("workCell")
            if wc and wc.get("activeWorkOrder"):
                return wc["activeWorkOrder"]
        except Exception:
            pass
        return None

    def get_customer_part_number(self, part_number: str) -> str | None:
        """Look up the customer part number for a ProShop part number.

        Returns the customer PN string or None.
        """
        gql = """
        query($partNumber: String!) {
            part(partNumber: $partNumber) {
                customerPartNumber
            }
        }
        """
        try:
            data = self.query(gql, {"partNumber": part_number})
            part = data.get("part")
            if part and part.get("customerPartNumber"):
                return part["customerPartNumber"]
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        """Quick health check -- can we reach ProShop?"""
        try:
            self._get_token()
            return True
        except Exception:
            return False
