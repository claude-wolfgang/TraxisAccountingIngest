import os

# ProShop API
PROSHOP_GRAPHQL_URL = os.environ.get("PROSHOP_GRAPHQL_URL", "https://traxismfg.adionsystems.com/api/graphql")
PROSHOP_TOKEN_URL = os.environ.get("PROSHOP_TOKEN_URL", "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken")
PROSHOP_CLIENT_ID = os.environ.get("PROSHOP_CLIENT_ID", "BA16-EFAF-B154")
PROSHOP_CLIENT_SECRET = os.environ.get("PROSHOP_CLIENT_SECRET", "2F64968E4E77FDE1CB6B587D9F92340CC3B4C82A414D77798F359A85CD4976D1")
PROSHOP_SCOPE = os.environ.get("PROSHOP_SCOPE", "parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r+purchaseOrders:r")

# ProShop web UI base (derived from API URL)
PROSHOP_BASE_URL = PROSHOP_GRAPHQL_URL.rsplit("/api/", 1)[0]

# Flask
HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
PORT = int(os.environ.get("FLASK_PORT", "5080"))
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Database
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.db")

# Sync intervals (seconds)
SYNC_INTERVAL = 7200      # 2 hr — was 15 min, reduced to cut API load. Use POST /api/sync for manual refresh.
WRITEBACK_INTERVAL = 120   # 2 min progress writeback to ProShop

# Scheduling defaults
DEFAULT_OP_DURATION_MIN = 60  # Default duration when ProShop has no time data
BUSINESS_HOURS_START = 5      # 5 AM
BUSINESS_HOURS_END = 18       # 6 PM

# Heartbeat file (Overseer checks this)
HEARTBEAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heartbeat.json")

# Kiosk tooling DB (read-only, Dropbox-synced from project 22)
_BASE = os.path.dirname(os.path.abspath(__file__))
KIOSK_DB_PATH = os.path.join(_BASE, "..", "22. Tool Assembly Management", "tool-kiosk", "data", "tooling.db")
