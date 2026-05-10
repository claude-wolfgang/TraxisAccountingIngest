"""
Tool Assembly Kiosk — Launcher & Watchdog
==========================================
Runs on the dedicated kiosk computer. Handles:
  1. Starting the Flask server (app.py)
  2. Launching Chrome in kiosk mode (fullscreen, no UI)
  3. Watchdog: restarts Chrome immediately if closed, restarts Flask if crashed

Setup:
  The touchscreen must be set as the PRIMARY display in Windows Display Settings.
  Chrome --kiosk opens fullscreen on the primary display, and touch input maps there.

Usage:
  Double-click START KIOSK.bat         (recommended)
  python kiosk_launcher.py             (from terminal, for debugging)
"""

import subprocess
import time
import os
import sys
import logging
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

KIOSK_URL = "http://localhost:5001"
HEALTH_URL = "http://localhost:5001/api/health"
HEALTH_TIMEOUT = 30
WATCHDOG_INTERVAL = 2
FLASK_RESTART_DELAY = 3
CHROME_RESTART_DELAY = 1
CRASH_LOOP_THRESHOLD = 5      # consecutive crashes before backoff
CRASH_LOOP_BACKOFF = 10       # seconds to wait during crash-loop backoff

# ── Load .traxis.env credentials ─────────────────────────────────────────────
_home = str(Path.home())
# Relative to this script: tool-kiosk is inside "Proshop Automation and Claude Projects"
_script_dir = Path(__file__).parent.resolve()
_projects_dir = _script_dir.parent.parent  # up from tool-kiosk → 22. Tool Assembly → Projects
_env_paths = [
    os.path.join(_home, ".traxis.env"),
    str(_projects_dir / "1. Proshop Automations" / ".traxis.env"),
    str(_projects_dir / "Keys" / ".traxis.env"),
    os.path.join(_home, "Dropbox", "MACHINE COMM Traxis", "Proshop Automation and Claude Projects", "1. Proshop Automations", ".traxis.env"),
]
for _drive in "CDEFG":
    for _sub in [
        os.path.join("MACHINE COMM Traxis", "Keys"),
        os.path.join("MACHINE COMM Traxis", "Proshop Automation and Claude Projects", "1. Proshop Automations"),
    ]:
        _env_paths.append(os.path.join(f"{_drive}:\\Dropbox", _sub, ".traxis.env"))

for _ep in _env_paths:
    if os.path.exists(_ep):
        with open(_ep) as _f:
            for _line in _f:
                _line = _line.strip()
                if "=" in _line and not _line.startswith("#"):
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())

if os.environ.get("TOOLKIOSK_CLIENT_SECRET"):
    os.environ["PROSHOP_CLIENT_ID"] = os.environ["TOOLKIOSK_CLIENT_ID"]
    os.environ["PROSHOP_CLIENT_SECRET"] = os.environ["TOOLKIOSK_CLIENT_SECRET"]
    os.environ["PROSHOP_SCOPE"] = os.environ["TOOLKIOSK_SCOPE"]

PROSHOP_CLIENT_SECRET = os.environ.get("PROSHOP_CLIENT_SECRET", "")

CHROME_KIOSK_PROFILE = os.path.join(
    os.environ.get("LOCALAPPDATA", str(_script_dir)), "ToolKioskChromeProfile"
)

CHROME_FLAGS = [
    "--kiosk",
    f"--user-data-dir={CHROME_KIOSK_PROFILE}",
    "--noerrdialogs",
    "--disable-session-crashed-bubble",
    "--disable-infobars",
    "--disable-translate",
    "--no-first-run",
    "--disable-features=TranslateUI",
    "--check-for-update-interval=604800",
    "--disable-background-networking",
    "--password-store=basic",
]

# ── Logging ──────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = SCRIPT_DIR / "kiosk_launcher.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("kiosk")

# ── Helpers ──────────────────────────────────────────────────────────────────

def find_chrome():
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def wait_for_flask(timeout=HEALTH_TIMEOUT):
    import urllib.request
    import urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.urlopen(HEALTH_URL, timeout=3)
            if req.status == 200:
                log.info("Flask server is ready")
                return True
        except Exception:
            pass
        time.sleep(1)
    log.error("Flask server did not become ready within %ds", timeout)
    return False


def start_flask():
    env = os.environ.copy()
    if PROSHOP_CLIENT_SECRET:
        env["PROSHOP_CLIENT_SECRET"] = PROSHOP_CLIENT_SECRET

    python_exe = sys.executable
    if "pythonw" in python_exe.lower():
        python_exe = python_exe.replace("pythonw", "python").replace("PYTHONW", "python")
    if not Path(python_exe).exists():
        python_exe = str(Path(sys.executable).parent / "python.exe")

    app_py = str(SCRIPT_DIR / "app.py")
    log.info("Starting Flask: %s %s", python_exe, app_py)

    proc = subprocess.Popen(
        [python_exe, app_py],
        cwd=str(SCRIPT_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.info("Flask started (PID %d)", proc.pid)
    return proc


def start_chrome(chrome_path):
    cmd = [chrome_path] + CHROME_FLAGS + [KIOSK_URL]
    log.info("Launching Chrome kiosk: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.info("Chrome started (PID %d)", proc.pid)
    return proc


def clean_chrome_profile_locks():
    """Delete Chrome profile lock files that prevent new instances from starting."""
    profile = Path(CHROME_KIOSK_PROFILE)
    for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        lock_file = profile / lock_name
        try:
            if lock_file.exists():
                lock_file.unlink()
                log.info("Removed stale lock: %s", lock_file)
        except Exception as e:
            log.warning("Could not remove %s: %s", lock_file, e)


def kill_kiosk_chrome():
    """Kill only Chrome instances using the kiosk profile, not normal Chrome."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
             "Where-Object { $_.CommandLine -and $_.CommandLine.Contains('ToolKioskChromeProfile') } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(1)
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("Tool Assembly Kiosk Launcher starting")
    log.info("=" * 50)

    chrome_path = find_chrome()
    if not chrome_path:
        log.error("Chrome not found! Install Chrome and try again.")
        return

    log.info("Chrome found: %s", chrome_path)
    log.info("Kiosk profile: %s", CHROME_KIOSK_PROFILE)

    flask_proc = start_flask()
    if not wait_for_flask():
        log.error("Continuing anyway — Chrome will show an error page until Flask is ready")

    kill_kiosk_chrome()
    clean_chrome_profile_locks()
    time.sleep(1)

    chrome_proc = start_chrome(chrome_path)

    log.info("Watchdog running (checking every %ds)", WATCHDOG_INTERVAL)
    chrome_crash_count = 0

    try:
        while True:
            time.sleep(WATCHDOG_INTERVAL)

            if flask_proc.poll() is not None:
                log.warning("Flask died (exit code %s) — restarting in %ds",
                            flask_proc.returncode, FLASK_RESTART_DELAY)
                time.sleep(FLASK_RESTART_DELAY)
                flask_proc = start_flask()
                wait_for_flask()

            if chrome_proc.poll() is not None:
                chrome_crash_count += 1
                clean_chrome_profile_locks()
                if chrome_crash_count >= CRASH_LOOP_THRESHOLD:
                    log.warning("Chrome crash loop detected (%d crashes) — waiting %ds",
                                chrome_crash_count, CRASH_LOOP_BACKOFF)
                    time.sleep(CRASH_LOOP_BACKOFF)
                    clean_chrome_profile_locks()
                else:
                    log.warning("Chrome closed (%d) — relaunching in %ds",
                                chrome_crash_count, CHROME_RESTART_DELAY)
                    time.sleep(CHROME_RESTART_DELAY)
                chrome_proc = start_chrome(chrome_path)
            else:
                chrome_crash_count = 0

    except KeyboardInterrupt:
        log.info("Shutting down (Ctrl+C)")
    finally:
        log.info("Cleaning up child processes...")
        for proc, name in [(chrome_proc, "Chrome"), (flask_proc, "Flask")]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    log.info("%s terminated", name)
                except Exception:
                    proc.kill()
                    log.info("%s killed", name)


if __name__ == "__main__":
    # Also kill Flask on port 5001 if left over from a previous run
    try:
        subprocess.run(
            ["powershell", "-Command",
             "Get-NetTCPConnection -LocalPort 5001 -ErrorAction SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass
    main()
