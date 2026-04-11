"""
Simple API key authentication for the mobile app.
"""

from fastapi import Header, HTTPException

from config import API_KEY


async def verify_api_key(x_api_key: str = Header(default=None)):
    """Verify the API key from request header. Skip if no key configured."""
    if API_KEY and API_KEY != "proshop-mobile-dev-key":
        if x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
