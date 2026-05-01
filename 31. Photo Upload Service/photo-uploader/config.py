"""Photo Upload Service — Configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECTS_DIR = _SCRIPT_DIR.parent.parent  # up from photo-uploader → 31. → Projects

# Load .traxis.env
_env_path = _PROJECTS_DIR / "1. Proshop Automations" / ".traxis.env"
if _env_path.exists():
    load_dotenv(_env_path)

# ProShop API — use FusionToolAuditor client (broadest scope)
PROSHOP_GRAPHQL_URL = os.environ.get(
    "PROSHOP_GRAPHQL_URL",
    "https://traxismfg.adionsystems.com/api/graphql",
)
PROSHOP_TOKEN_URL = os.environ.get(
    "PROSHOP_TOKEN_URL",
    "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken",
)
PROSHOP_BASE_URL = os.environ.get(
    "PROSHOP_BASE_URL",
    "https://traxismfg.adionsystems.com/procnc",
)
PROSHOP_CLIENT_ID = os.environ.get("PROSHOP_CLIENT_ID", "BA16-EFAF-B154")
PROSHOP_CLIENT_SECRET = os.environ.get("PROSHOP_CLIENT_SECRET")
PROSHOP_SCOPE = os.environ.get(
    "PROSHOP_SCOPE",
    "parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r+fixtures:r",
)

# Selenium login (for Phase 2 upload worker)
PROSHOP_USERNAME = os.environ.get("PROSHOP_USERNAME")
PROSHOP_PASSWORD = os.environ.get("PROSHOP_PASSWORD")

# Flask
HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
PORT = int(os.environ.get("FLASK_PORT", "5003"))
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Data paths
DATA_DIR = _SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
PHOTOS_DIR = DATA_DIR / "photos"
PHOTOS_DIR.mkdir(exist_ok=True)
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
DB_PATH = os.environ.get("PHOTO_DB_PATH", str(DATA_DIR / "photos.db"))

# Photo processing
MAX_PHOTO_DIMENSION = 2000  # pixels (longest side)
JPEG_QUALITY = 85
MAX_UPLOAD_SIZE_MB = 20  # reject uploads larger than this

# Upload worker (Phase 2)
UPLOAD_CHECK_INTERVAL = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAYS = [60, 300, 900]  # seconds: 1min, 5min, 15min
