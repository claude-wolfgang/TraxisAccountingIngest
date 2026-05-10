"""
Traxis COTS Crib — Kiosk Launcher & Watchdog
=============================================
Runs on the dedicated kiosk computer. Handles:
  1. Starting the Flask server (app.py)
  2. Launching Chrome in kiosk mode (fullscreen, no UI)
  3. Watchdog: restarts Chrome immediately if closed, restarts Flask if crashed

Usage:
  pythonw.exe kiosk_launcher.py        (silent, no console window)
  python.exe  kiosk_launcher.py        (visible, for debugging)

Put start_kiosk.vbs in the Windows Startup folder for auto-start on boot.
"""

import subprocess
import time
import os
import sys
import signal
import logging
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

KIOSK_URL = "http://localhost:5000"
HEALTH_URL = "http://localhost:5000/api/health"
HEALTH_TIMEOUT = 30          # seconds to wait for Flask to be ready
WATCHDOG_INTERVAL = 2        # seconds between Chrome alive checks
FLASK_RESTART_DELAY = 3      # seconds to wait before restarting Flask
CHROME_RESTART_DELAY = 1     # seconds before relaunching Chrome

PROSHOP_CLIENT_SECRET = "E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110"

# Chrome flags for kiosk mode
CHROME_FLAGS = [
    "--kiosk",                              # fullscreen, no browser UI
    "--noerrdialogs",                       # suppress error dialogs
    "--disable-session-crashed-bubble",     # no "Chrome didn't shut down correctly"
    "--disable-infobars",                   # no info bars
    "--disable-translate",                  # no translate prompts
    "--no-first-run",                       # skip first-run wizard
    "--disable-features=TranslateUI",       # really no translate
    "--check-for-update-interval=604800",   # check updates weekly, not on launch
    "--disable-background-networking",      # reduce background activity
    "--password-store=basic",               # don't prompt for keyring
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
    """Find Chrome executable on this Windows machine."""
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
    """Poll the health endpoint until Flask is ready."""
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
    """Start app.py as a subprocess."""
    env = os.environ.copy()
    env["PROSHOP_CLIENT_SECRET"] = PROSHOP_CLIENT_SECRET

    python_exe = sys.executable
    # If we're running under pythonw, use python.exe for the Flask subprocess
    # so it gets proper stdio (pythonw has no console)
    if "pythonw" in python_exe.lower():
        python_exe = python_exe.replace("pythonw", "python").replace("PYTHONW", "python")
    # Ensure we have the real path (not a relative or broken one)
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
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log.info("Flask started (PID %d)", proc.pid)
    return proc


def start_chrome(chrome_path):
    """Launch Chrome in kiosk mode."""
    cmd = [chrome_path] + CHROME_FLAGS + [KIOSK_URL]
    log.info("Launching Chrome kiosk: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.info("Chrome started (PID %d)", proc.pid)
    return proc


def kill_existing_chrome():
    """Kill any existing Chrome instances so --kiosk launches clean."""
    try:
        subprocess.run(
            ["taskkill", "/IM", "chrome.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(1)
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("Traxis COTS Crib Kiosk Launcher starting")
    log.info("=" * 50)

    # Find Chrome
    chrome_path = find_chrome()
    if not chrome_path:
        log.error("Chrome not found! Install Chrome and try again.")
        return

    log.info("Chrome found: %s", chrome_path)

    # Start Flask server
    flask_proc = start_flask()
    if not wait_for_flask():
        log.error("Continuing anyway — Chrome will show an error page until Flask is ready")

    # Kill any stale Chrome so kiosk mode works cleanly
    kill_existing_chrome()
    time.sleep(1)

    # Launch Chrome in kiosk mode
    chrome_proc = start_chrome(chrome_path)

    # ── Watchdog loop ────────────────────────────────────────────────────
    log.info("Watchdog running (checking every %ds)", WATCHDOG_INTERVAL)

    try:
        while True:
            time.sleep(WATCHDOG_INTERVAL)

            # Check Flask
            if flask_proc.poll() is not None:
                log.warning("Flask died (exit code %s) — restarting in %ds",
                            flask_proc.returncode, FLASK_RESTART_DELAY)
                time.sleep(FLASK_RESTART_DELAY)
                flask_proc = start_flask()
                wait_for_flask()

            # Check Chrome
            if chrome_proc.poll() is not None:
                log.warning("Chrome closed — relaunching in %ds", CHROME_RESTART_DELAY)
                time.sleep(CHROME_RESTART_DELAY)
                chrome_proc = start_chrome(chrome_path)

    except KeyboardInterrupt:
        log.info("Shutting down (Ctrl+C)")
        chrome_proc.terminate()
        flask_proc.terminate()


if __name__ == "__main__":
    main()
