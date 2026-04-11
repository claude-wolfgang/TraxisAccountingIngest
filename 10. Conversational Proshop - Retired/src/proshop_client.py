"""
ProShop GraphQL Client with OAuth 2.0 authentication.
Provides a simple interface for executing GraphQL queries against ProShop ERP.
"""

import requests
import time
import hashlib
import json
import os
from typing import Optional, Dict, Any


# =============================================================================
# Cache Configuration
# =============================================================================

# Default cache TTL in seconds (5 minutes)
DEFAULT_CACHE_TTL = 300

# File-based cache location
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".proshop_cache.json")


def _load_cache() -> Dict[str, Dict[str, Any]]:
    """Load cache from file."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_cache(cache: Dict[str, Dict[str, Any]]):
    """Save cache to file."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except IOError:
        pass  # Fail silently on write errors


def _make_cache_key(query: str, variables: Dict[str, Any] = None) -> str:
    """Generate a cache key from query and variables."""
    key_data = query.strip() + json.dumps(variables or {}, sort_keys=True)
    return hashlib.md5(key_data.encode()).hexdigest()


def clear_cache():
    """Clear all cached responses."""
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except IOError:
        pass


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    cache = _load_cache()
    now = time.time()
    valid = sum(1 for v in cache.values() if v["expires_at"] > now)
    expired = len(cache) - valid
    return {"total": len(cache), "valid": valid, "expired": expired}


class ProShopClient:
    """GraphQL client for ProShop ERP with OAuth 2.0 authentication."""

    # Default configuration
    DEFAULT_BASE_URL = "https://traxismfg.adionsystems.com"
    DEFAULT_CLIENT_ID = "0615-12FB-C88D"
    DEFAULT_CLIENT_SECRET = "1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32"
    DEFAULT_SCOPES = "parts:rwdp+workorders:rwdp+users:r"

    def __init__(
        self,
        base_url: str = None,
        client_id: str = None,
        client_secret: str = None,
        scopes: str = None,
        cache_ttl: int = None
    ):
        """
        Initialize the ProShop client.

        Args:
            base_url: ProShop base URL (defaults to Traxis instance)
            client_id: OAuth client ID
            client_secret: OAuth client secret
            scopes: OAuth scopes to request
            cache_ttl: Cache time-to-live in seconds (default 300 = 5 min)
        """
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.client_id = client_id or self.DEFAULT_CLIENT_ID
        self.client_secret = client_secret or self.DEFAULT_CLIENT_SECRET
        self.scopes = scopes or self.DEFAULT_SCOPES
        self.cache_ttl = cache_ttl if cache_ttl is not None else DEFAULT_CACHE_TTL

        self.graphql_url = f"{self.base_url}/api/graphql"
        self.token_url = f"{self.base_url}/home/member/oauth/accesstoken"

        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0
        self.session = requests.Session()

    def authenticate(self) -> bool:
        """
        Authenticate with ProShop using OAuth 2.0 Client Credentials flow.

        Returns:
            True if authentication succeeded, False otherwise.
        """
        try:
            response = self.session.post(
                self.token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.scopes
                }
            )

            if response.status_code != 200:
                print(f"Authentication failed: {response.status_code}")
                print(response.text)
                return False

            data = response.json()
            self.access_token = data.get("access_token")
            expires_in = data.get("expires_in", 86400)
            self.token_expires_at = time.time() + expires_in - 60  # 1 minute buffer

            return True

        except Exception as e:
            print(f"Authentication error: {e}")
            return False

    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token, refreshing if needed."""
        if self.access_token and time.time() < self.token_expires_at:
            return True
        return self.authenticate()

    def execute(self, query: str, variables: Dict[str, Any] = None, use_cache: bool = True) -> Dict[str, Any]:
        """
        Execute a GraphQL query.

        Args:
            query: The GraphQL query string
            variables: Optional variables for the query
            use_cache: Whether to use caching (default True)

        Returns:
            The 'data' portion of the response, or raises an exception on error.

        Raises:
            Exception: If authentication fails or query returns errors.
        """
        # Check cache first
        cache_key = None
        cache = None
        if use_cache and self.cache_ttl > 0:
            cache_key = _make_cache_key(query, variables)
            cache = _load_cache()
            cached = cache.get(cache_key)
            if cached and cached["expires_at"] > time.time():
                return cached["data"]

        if not self.ensure_authenticated():
            raise Exception("Failed to authenticate with ProShop")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self.session.post(self.graphql_url, headers=headers, json=payload)

        if response.status_code != 200:
            raise Exception(f"GraphQL request failed: {response.status_code} - {response.text}")

        result = response.json()

        if "errors" in result and result["errors"]:
            error_msgs = [e.get("message", str(e)) for e in result["errors"]]
            raise Exception(f"GraphQL errors: {'; '.join(error_msgs)}")

        data = result.get("data", {})

        # Store in cache
        if cache_key:
            if cache is None:
                cache = _load_cache()
            cache[cache_key] = {
                "data": data,
                "expires_at": time.time() + self.cache_ttl
            }
            _save_cache(cache)

        return data

    def execute_raw(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query and return the full response (including errors).
        Useful for debugging.
        """
        if not self.ensure_authenticated():
            raise Exception("Failed to authenticate with ProShop")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self.session.post(self.graphql_url, headers=headers, json=payload)

        return {
            "status_code": response.status_code,
            "response": response.json() if response.status_code == 200 else response.text
        }


# Convenience function for quick testing
def get_client() -> ProShopClient:
    """Get an authenticated ProShop client."""
    client = ProShopClient()
    if not client.authenticate():
        raise Exception("Failed to authenticate with ProShop")
    return client


if __name__ == "__main__":
    # Quick test
    client = get_client()
    print("Authentication successful!")

    # Test query
    result = client.execute("""
        query {
            workOrders(pageSize: 3) {
                totalRecords
                records {
                    workOrderNumber
                    status
                }
            }
        }
    """)

    print(f"Total work orders: {result['workOrders']['totalRecords']}")
    for wo in result['workOrders']['records']:
        print(f"  {wo['workOrderNumber']}: {wo['status']}")
