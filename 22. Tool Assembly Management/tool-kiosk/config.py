import os
import json
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECTS_DIR = _SCRIPT_DIR.parent.parent  # up from tool-kiosk → 22. → Projects

# ProShop API
PROSHOP_GRAPHQL_URL = os.environ.get("PROSHOP_GRAPHQL_URL", "https://traxismfg.adionsystems.com/api/graphql")
PROSHOP_TOKEN_URL = os.environ.get("PROSHOP_TOKEN_URL", "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken")
PROSHOP_CLIENT_ID = os.environ.get("TOOLKIOSK_CLIENT_ID",
                    os.environ.get("PROSHOP_CLIENT_ID", "8B54-3113-ED6E"))
PROSHOP_CLIENT_SECRET = os.environ.get("TOOLKIOSK_CLIENT_SECRET",
                        os.environ.get("PROSHOP_CLIENT_SECRET"))
PROSHOP_SCOPE = os.environ.get("TOOLKIOSK_SCOPE",
                os.environ.get("PROSHOP_SCOPE",
                "toolpots:rwdp+parts:r+workorders:r+users:r+tools:r+rtas:rwdp"))

# Flask
HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
PORT = int(os.environ.get("FLASK_PORT", "5001"))
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Database
# tooling.db — always in local data\ folder (Dropbox-synced, shared with kiosk PC)
_data_dir = _SCRIPT_DIR / "data"
_data_dir.mkdir(exist_ok=True)
TOOLING_DB_PATH = os.environ.get("TOOLING_DB_PATH", str(_data_dir / "tooling.db"))
# monitoring.db — C:\FASData (written by FocasMonitor), read-only by rollup
_fasdata = Path(r"C:\FASData")
MONITORING_DB_PATH = os.environ.get("MONITORING_DB_PATH", str(_fasdata / "monitoring.db"))

# Machine config — find machines.json relative to this script or by env var
_machines_default = str(_PROJECTS_DIR / "12. FASData Implementation" / "focasmonitor" / "machines.json")
MACHINES_JSON_PATH = os.environ.get("MACHINES_JSON_PATH", _machines_default)

def load_machines():
    """Load machine config from FocasMonitor's machines.json."""
    with open(MACHINES_JSON_PATH, "r") as f:
        data = json.load(f)
    machines = {}
    for m in data.get("machines", []):
        machines[m["id"]] = {
            "name": m["name"],
            "type": m["type"],
            "enabled": m.get("enabled", False),
            "proshop_pot_id": m.get("proshop_pot_id", ""),
        }
    return machines

MACHINES = load_machines()

# Label Print Service (standalone on print server PC)
PRINT_SERVICE_URL = os.environ.get("PRINT_SERVICE_URL", "http://10.1.1.242:5002")

# Kiosk behavior
AUTO_RETURN_SECONDS = 5
INACTIVITY_TIMEOUT_SECONDS = 120
