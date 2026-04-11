"""
Configuration for ProShop Mobile Backend.
Loads settings from environment variables with sensible defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ProShop API
PROSHOP_BASE_URL = os.getenv("PROSHOP_BASE_URL", "https://traxismfg.adionsystems.com")
PROSHOP_CLIENT_ID = os.getenv("PROSHOP_CLIENT_ID", "")
PROSHOP_CLIENT_SECRET = os.getenv("PROSHOP_CLIENT_SECRET", "")
PROSHOP_SCOPES = os.getenv("PROSHOP_SCOPES", "parts:rwdp+workorders:rwdp")

# Claude AI Chat (optional — falls back to pattern matching without it)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# App Auth
API_KEY = os.getenv("API_KEY", "proshop-mobile-dev-key")

# Cache
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "1800"))  # 30 minutes — ProShop data changes slowly

# Query limits
MAX_RESULTS_PER_QUERY = 500
MAX_DISPLAY_RESULTS = 50
RATE_LIMIT_SECONDS = 0.0  # Disabled — cache handles API protection
DEFAULT_LOOKBACK_MONTHS = 12
