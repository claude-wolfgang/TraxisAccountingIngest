"""
Configuration for Traxis Data Quality Agent.
Credentials and paths for ProShop, FOCAS, and filesystem checks.
"""
import os
from pathlib import Path


def _get_env(name):
    """Get env var, falling back to Windows User env vars (Git Bash can't see them)."""
    val = os.environ.get(name)
    if val:
        return val
    if os.name == "nt":
        import subprocess
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"[Environment]::GetEnvironmentVariable('{name}', 'User')"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            val = result.stdout.strip()
            if val:
                os.environ[name] = val  # Cache for subsequent reads
                return val
        except Exception:
            pass
    return None


# ── ProShop API ──────────────────────────────────────────────────────────
# Using ClaudeCodeResearch client (broadest scope).
# Credentials read from env vars; literal fallbacks preserve current
# behavior on .71 until env vars are set. Strip the fallbacks once the
# server migration is verified.
PROSHOP_INSTANCE = "traxismfg"
PROSHOP_BASE_URL = f"https://{PROSHOP_INSTANCE}.adionsystems.com"
PROSHOP_GRAPHQL_URL = f"{PROSHOP_BASE_URL}/api/graphql"
PROSHOP_TOKEN_URL = f"{PROSHOP_BASE_URL}/home/member/oauth/accesstoken"
PROSHOP_CLIENT_ID = _get_env("PROSHOP_CLIENT_ID") or "BA16-EFAF-B154"
PROSHOP_CLIENT_SECRET = (
    _get_env("PROSHOP_CLIENT_SECRET")
    or "2F64968E4E77FDE1CB6B587D9F92340CC3B4C82A414D77798F359A85CD4976D1"
)
PROSHOP_SCOPE = "parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r"

# ── Anthropic API ───────────────────────────────────────────────────────
ANTHROPIC_API_KEY = _get_env("ANTHROPIC_API_KEY")

# ── FOCAS Database ───────────────────────────────────────────────────────
# Primary: collector PC local path (overridable via TRAXIS_FOCAS_DB).
# Fallback: Dropbox sync copy.
FOCAS_DB_PRIMARY = Path(_get_env("TRAXIS_FOCAS_DB") or r"C:\FASData\monitoring.db")
FOCAS_DB_FALLBACK = Path(
    os.path.expanduser("~"),
    "Dropbox", "MACHINE COMM Traxis", "FASData", "monitoring.db"
)

def get_focas_db_path():
    """Return the best available FOCAS database path."""
    if FOCAS_DB_PRIMARY.exists():
        return FOCAS_DB_PRIMARY
    if FOCAS_DB_FALLBACK.exists():
        return FOCAS_DB_FALLBACK
    return None

# ── NC Programs Filesystem ───────────────────────────────────────────────
# Auto-detect Dropbox root from Dropbox's info.json
def _find_dropbox_root():
    info_path = Path(os.environ.get("LOCALAPPDATA", ""), "Dropbox", "info.json")
    if info_path.exists():
        import json
        with open(info_path) as f:
            info = json.load(f)
        personal = info.get("personal", {}).get("path")
        if personal:
            return Path(personal)
    # Fallback: check common locations
    for drive in ["D:", "C:"]:
        p = Path(drive, "Dropbox")
        if p.exists():
            return p
    return None

_dropbox = _find_dropbox_root()
NC_PROGRAMS_ROOT = Path(_dropbox, "NC Programs") if _dropbox else None
PART_FILES_ROOT = Path(_dropbox, "PART FILES Traxis") if _dropbox else None

# ── Audit Database ───────────────────────────────────────────────────────
AUDIT_DB_PATH = Path(__file__).parent / "audit.db"

# ── Machine ID Mapping ───────────────────────────────────────────────────
# Maps ProShop work cell names to FOCAS machine IDs
PROSHOP_TO_FOCAS = {
    "Mill-1": None,       # Haas VF-5 — no FOCAS
    "Mill-2": "M2",       # FANUC Mill 2
    "Mill-3": "M3",       # FANUC Mill 3 (intermittent)
    "Mill-4": "M4",       # Robodrill 4 (no ethernet)
    "Mill-5": "M5",       # Robodrill 5 (no ethernet)
    "Mill-6": "M6",       # FANUC Mill 6
    "Mill-7": "M7",       # Robodrill 7 (no ethernet)
    "Mill-8": "M8",       # Hyundai-Wia KF5600II
    "Lathe-1": None,      # Unknown
    "Lathe-2": "T2",      # YCM NTC1600LY
}

FOCAS_MACHINES = {v: k for k, v in PROSHOP_TO_FOCAS.items() if v}

# ── Legacy Program Mappings ──────────────────────────────────────────────
# Maps CNC O-numbers to ProShop parts for machines with resident programs
# that predate the TraxisPostProcessor header system.
LATHE_PROGRAMS_PATH = Path(__file__).parent / "lathe_programs.json"

def get_program_mappings():
    """Load legacy program mappings. Returns dict of o_number -> entry."""
    if not LATHE_PROGRAMS_PATH.exists():
        return {}
    import json
    with open(LATHE_PROGRAMS_PATH) as f:
        data = json.load(f)
    mappings = {}
    for prog in data.get("programs", []):
        o_num = prog.get("o_number", "").upper()
        if o_num and prog.get("part_number") != "EXAMPLE-PART":
            mappings[o_num] = prog
    return mappings

# ── Telegram Alerts ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ── Report Output ────────────────────────────────────────────────────────
REPORT_DIR = Path(__file__).parent / "reports"
