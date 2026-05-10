import os

# ProShop API
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
CLIENT_ID = "E88F-BE23-AC08"
CLIENT_SECRET = os.environ.get("PROSHOP_CLIENT_SECRET")
SCOPE = "ots:r+cots:r+parts:r+users:r+messages:r"

# Flask server
HOST = "0.0.0.0"
PORT = 5050

# Polling
POLL_INTERVAL = 1800  # 30 min — was 30s, reduced to cut API load

# ProShop messages page (opened on click)
MESSAGES_URL = "https://traxismfg.adionsystems.com/procnc/messages"

# Heartbeat file (overseer checks this)
HEARTBEAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heartbeat.json")
