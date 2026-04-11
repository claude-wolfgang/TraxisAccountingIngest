"""
ProShop GraphQL Client with OAuth 2.0 authentication.
Thread-safe with in-memory caching for use in FastAPI.
"""

import requests
import time
import hashlib
import json
import threading
import logging
from typing import Optional, Dict, Any

from config import (
    PROSHOP_BASE_URL, PROSHOP_CLIENT_ID, PROSHOP_CLIENT_SECRET,
    PROSHOP_SCOPES, CACHE_TTL_SECONDS
)

logger = logging.getLogger(__name__)


class ProShopClient:
    """GraphQL client for ProShop ERP with OAuth 2.0 authentication."""

    def __init__(self):
        self.base_url = PROSHOP_BASE_URL
        self.client_id = PROSHOP_CLIENT_ID
        self.client_secret = PROSHOP_CLIENT_SECRET
        self.scopes = PROSHOP_SCOPES
        self.cache_ttl = CACHE_TTL_SECONDS

        self.graphql_url = f"{self.base_url}/api/graphql"
        self.token_url = f"{self.base_url}/home/member/oauth/accesstoken"

        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0
        self.session = requests.Session()

        # Thread-safe in-memory cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        self._token_lock = threading.Lock()

    def authenticate(self) -> bool:
        """Authenticate with ProShop using OAuth 2.0 Client Credentials flow."""
        with self._token_lock:
            # Double-check after acquiring lock
            if self.access_token and time.time() < self.token_expires_at:
                return True

            try:
                response = self.session.post(
                    self.token_url,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "scope": self.scopes,
                    },
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                    return False

                data = response.json()
                self.access_token = data.get("access_token")
                expires_in = data.get("expires_in", 86400)
                self.token_expires_at = time.time() + expires_in - 60

                logger.info("ProShop authentication successful")
                return True

            except Exception as e:
                logger.error(f"Authentication error: {e}")
                return False

    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token, refreshing if needed."""
        if self.access_token and time.time() < self.token_expires_at:
            return True
        return self.authenticate()

    def _make_cache_key(self, query: str, variables: Dict[str, Any] = None) -> str:
        key_data = query.strip() + json.dumps(variables or {}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    def execute(self, query: str, variables: Dict[str, Any] = None, use_cache: bool = True) -> Dict[str, Any]:
        """
        Execute a GraphQL query.

        Returns the 'data' portion of the response.
        Raises Exception on authentication failure or GraphQL errors.
        """
        # Check cache
        cache_key = None
        if use_cache and self.cache_ttl > 0:
            cache_key = self._make_cache_key(query, variables)
            with self._cache_lock:
                cached = self._cache.get(cache_key)
                if cached and cached["expires_at"] > time.time():
                    return cached["data"]

        if not self.ensure_authenticated():
            raise Exception("Failed to authenticate with ProShop")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self.session.post(self.graphql_url, headers=headers, json=payload, timeout=60)

        if response.status_code != 200:
            raise Exception(f"GraphQL request failed: {response.status_code} - {response.text}")

        result = response.json()

        if "errors" in result and result["errors"]:
            error_msgs = [e.get("message", str(e)) for e in result["errors"]]
            raise Exception(f"GraphQL errors: {'; '.join(error_msgs)}")

        data = result.get("data", {})

        # Store in cache
        if cache_key:
            with self._cache_lock:
                self._cache[cache_key] = {
                    "data": data,
                    "expires_at": time.time() + self.cache_ttl,
                }

        return data

    def clear_cache(self):
        """Clear all cached responses."""
        with self._cache_lock:
            self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            now = time.time()
            valid = sum(1 for v in self._cache.values() if v["expires_at"] > now)
            expired = len(self._cache) - valid
            return {"total": len(self._cache), "valid": valid, "expired": expired}

    def is_connected(self) -> bool:
        """Check if we can reach ProShop."""
        try:
            return self.ensure_authenticated()
        except Exception:
            return False


# Singleton client instance
_client: Optional[ProShopClient] = None
_client_lock = threading.Lock()


def get_client() -> ProShopClient:
    """Get the shared ProShop client instance."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ProShopClient()
                _client.authenticate()
    return _client
