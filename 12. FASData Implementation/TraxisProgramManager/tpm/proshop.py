"""TPM ProShop API client: OAuth tokens and GraphQL queries."""

import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

logger = logging.getLogger("tpm.proshop")

_token = None
_token_expiry = 0


def reset_token():
    """Clear cached token (for tests)."""
    global _token, _token_expiry
    _token = None
    _token_expiry = 0


def get_token():
    """Get OAuth token via client_credentials flow, with caching."""
    global _token, _token_expiry
    if _token and time.time() < _token_expiry:
        return _token
    creds = config.load_credentials()
    client_id = creds.get("PROSHOP_CLIENT_ID", "")
    client_secret = creds.get("PROSHOP_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("Missing PROSHOP_CLIENT_ID or PROSHOP_CLIENT_SECRET")
        return None
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "parts:r",
    }).encode("utf-8")
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(config.TOKEN_URL, data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })
        with urllib.request.urlopen(req, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            _token = result.get("access_token")
            expires_in = result.get("expires_in", 86400)
            _token_expiry = time.time() + expires_in - 300
            logger.info("OAuth token acquired")
            return _token
    except Exception as e:
        logger.error("Token error: %s", e)
        return None


def graphql_query(query, variables=None):
    """POST a GraphQL query to ProShop with Bearer auth."""
    token = get_token()
    if not token:
        return {"errors": [{"message": "No auth token"}]}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode("utf-8")
    ctx = ssl.create_default_context()
    req = urllib.request.Request(config.GRAPHQL_URL, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("GraphQL HTTP %d: %s", e.code, body[:300])
        return {"errors": [{"message": f"HTTP {e.code}"}]}
    except Exception as e:
        logger.error("GraphQL error: %s", e)
        return {"errors": [{"message": str(e)}]}


def lookup_customer_part_number(part_number):
    """Query ProShop for the customer's part number.

    Returns the customerPartNumber string, or None on failure.
    """
    try:
        query = """
        query($pn: String!) {
          part(partNumber: $pn) {
            customerPartNumber
          }
        }
        """
        result = graphql_query(query, {"pn": part_number})
        if "errors" in result:
            logger.warning("Customer PN lookup failed: %s", result["errors"])
            return None
        cust_pn = (
            result.get("data", {}).get("part", {}).get("customerPartNumber")
        )
        if cust_pn:
            logger.info("Customer PN for %s: %s", part_number, cust_pn)
            return cust_pn
        logger.debug("No customerPartNumber found for %s", part_number)
        return None
    except Exception as e:
        logger.error("Customer PN lookup error: %s", e)
        return None
