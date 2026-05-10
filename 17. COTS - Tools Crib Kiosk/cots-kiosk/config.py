import os

# ProShop API
PROSHOP_GRAPHQL_URL = os.environ.get("PROSHOP_GRAPHQL_URL", "https://traxismfg.adionsystems.com/api/graphql")
PROSHOP_TOKEN_URL = os.environ.get("PROSHOP_TOKEN_URL", "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken")
PROSHOP_CLIENT_ID = os.environ.get("PROSHOP_CLIENT_ID", "E88F-BE23-AC08")
PROSHOP_CLIENT_SECRET = os.environ.get("PROSHOP_CLIENT_SECRET")
PROSHOP_SCOPE = os.environ.get("PROSHOP_SCOPE", "ots:rwdp+cots:rwdp+parts:r+users:r")

# Token refresh buffer (seconds before expiry)
TOKEN_REFRESH_BUFFER = 300

# Flask
HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
PORT = int(os.environ.get("FLASK_PORT", "5000"))
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Transaction log
TRANSACTION_LOG_PATH = os.environ.get("TRANSACTION_LOG_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "transactions.csv"))

# Kiosk behavior
AUTO_RETURN_SECONDS = 5
INACTIVITY_TIMEOUT_SECONDS = 120
