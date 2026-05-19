"""
Tool Assembly Kiosk — Launcher & Watchdog
==========================================
Runs on the dedicated kiosk computer. Handles:
  1. (Optionally) Starting the Flask server (app.py) — only if KIOSK_URL is local.
     The canonical Flask backend lives on the Overseer host (.71, later .161).
  2. Detecting which monitor is the touchscreen via the Win32 Pointer Device API
     and launching Chrome --kiosk pinned to that monitor's bounds.
  3. Watchdog: restarts Chrome immediately if closed.
  4. Heartbeat thread: POSTs to /api/kiosk-heartbeat on the backend every 60s so
     Overseer can flag the kiosk degraded when the touchscreen goes dark even
     if Flask itself stays healthy.

Setup:
  Touchscreen does NOT need to be the primary display — detection picks it
  by digitizer presence. Calibrate touch input via Tablet PC Settings → Setup
  so finger input maps to the touchscreen's monitor.

Usage:
  Double-click START KIOSK.bat         (recommended)
  python kiosk_launcher.py             (from terminal, for debugging)
"""

import ctypes
from ctypes import wintypes
import subprocess
import threading
import time
import os
import sys
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

KIOSK_URL = os.environ.get("TOOLKIOSK_BACKEND_URL", "http://10.1.1.71:5001")
HEALTH_URL = KIOSK_URL.rstrip("/") + "/api/health"
HEARTBEAT_URL = KIOSK_URL.rstrip("/") + "/api/kiosk-heartbeat"
HEARTBEAT_INTERVAL = 60
HEALTH_TIMEOUT = 30
WATCHDOG_INTERVAL = 2
FLASK_RESTART_DELAY = 3
CHROME_RESTART_DELAY = 1
CRASH_LOOP_THRESHOLD = 5      # consecutive crashes before backoff
CRASH_LOOP_BACKOFF = 10       # seconds to wait during crash-loop backoff

_backend_host = urllib.parse.urlparse(KIOSK_URL).hostname or ""
IS_LOCAL_BACKEND = _backend_host in ("localhost", "127.0.0.1", "::1", "")

# Touchscreen monitor coordinates are detected at runtime via the Win32
# Pointer Device API. Fallback when no touchscreen is found:
FALLBACK_MONITOR_RECT = (0, 0, 1920, 1080)  # x, y, w, h

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

def build_chrome_flags(monitor_rect):
    x, y, w, h = monitor_rect
    return [
        "--kiosk",
        f"--user-data-dir={CHROME_KIOSK_PROFILE}",
        f"--window-position={x},{y}",
        f"--window-size={w},{h}",
        "--start-fullscreen",
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


def detect_touch_monitor():
    """Find the touchscreen via Win32 Pointer Device API. Returns
    (x, y, width, height) of its bounds in virtual-desktop coordinates,
    or None if no touchscreen is detected.

    Works regardless of which monitor is set as primary — picks by
    digitizer presence, not by display ordering."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        POINTER_DEVICE_TYPE_TOUCH = 3
        POINTER_DEVICE_PRODUCT_STRING_MAX = 520
        CCHDEVICENAME = 32

        class POINTER_DEVICE_INFO(ctypes.Structure):
            _fields_ = [
                ("displayOrientation", wintypes.DWORD),
                ("device", wintypes.HANDLE),
                ("pointerDeviceType", wintypes.DWORD),
                ("monitor", wintypes.HANDLE),
                ("startingCursorId", wintypes.ULONG),
                ("maxActiveContacts", wintypes.USHORT),
                ("productString", wintypes.WCHAR * POINTER_DEVICE_PRODUCT_STRING_MAX),
            ]

        class MONITORINFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * CCHDEVICENAME),
            ]

        GetPointerDevices = user32.GetPointerDevices
        GetPointerDevices.argtypes = [
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(POINTER_DEVICE_INFO),
        ]
        GetPointerDevices.restype = wintypes.BOOL

        GetMonitorInfoW = user32.GetMonitorInfoW
        GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEX)]
        GetMonitorInfoW.restype = wintypes.BOOL

        count = ctypes.c_uint32(0)
        if not GetPointerDevices(ctypes.byref(count), None):
            log.warning("GetPointerDevices(count) failed (err %d)", ctypes.get_last_error())
            return None
        if count.value == 0:
            log.info("No pointer devices reported")
            return None

        devices = (POINTER_DEVICE_INFO * count.value)()
        if not GetPointerDevices(ctypes.byref(count), devices):
            log.warning("GetPointerDevices(fetch) failed (err %d)", ctypes.get_last_error())
            return None

        for d in devices:
            if d.pointerDeviceType != POINTER_DEVICE_TYPE_TOUCH:
                continue
            if not d.monitor:
                continue
            mi = MONITORINFOEX()
            mi.cbSize = ctypes.sizeof(MONITORINFOEX)
            if not GetMonitorInfoW(d.monitor, ctypes.byref(mi)):
                continue
            r = mi.rcMonitor
            w = r.right - r.left
            h = r.bottom - r.top
            log.info(
                "Touchscreen detected: '%s' on %s at (%d,%d) %dx%d",
                d.productString, mi.szDevice, r.left, r.top, w, h,
            )
            return (r.left, r.top, w, h)

        log.info("No touch-type pointer device found among %d devices", count.value)
        return None
    except Exception as e:
        log.warning("Touch monitor detection failed: %s", e)
        return None


def wait_for_backend(timeout=HEALTH_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.urlopen(HEALTH_URL, timeout=3)
            if req.status == 200:
                log.info("Backend is ready at %s", HEALTH_URL)
                return True
        except Exception:
            pass
        time.sleep(1)
    log.error("Backend %s did not respond within %ds", HEALTH_URL, timeout)
    return False


def heartbeat_loop():
    """POST to /api/kiosk-heartbeat every HEARTBEAT_INTERVAL seconds so
    Overseer can detect a dark touchscreen via the backend's /api/health."""
    while True:
        try:
            req = urllib.request.Request(HEARTBEAT_URL, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            log.debug("Heartbeat post failed: %s", e)
        time.sleep(HEARTBEAT_INTERVAL)


def start_heartbeat_thread():
    t = threading.Thread(target=heartbeat_loop, daemon=True, name="kiosk-heartbeat")
    t.start()
    log.info("Heartbeat thread started -> %s (every %ds)", HEARTBEAT_URL, HEARTBEAT_INTERVAL)


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


def start_chrome(chrome_path, chrome_flags):
    cmd = [chrome_path] + chrome_flags + [KIOSK_URL]
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
    log.info("Backend: %s (local=%s)", KIOSK_URL, IS_LOCAL_BACKEND)
    log.info("=" * 50)

    chrome_path = find_chrome()
    if not chrome_path:
        log.error("Chrome not found! Install Chrome and try again.")
        return

    log.info("Chrome found: %s", chrome_path)
    log.info("Kiosk profile: %s", CHROME_KIOSK_PROFILE)

    monitor_rect = detect_touch_monitor()
    if monitor_rect is None:
        monitor_rect = FALLBACK_MONITOR_RECT
        log.warning("No touchscreen detected — falling back to %s", FALLBACK_MONITOR_RECT)
    chrome_flags = build_chrome_flags(monitor_rect)

    flask_proc = None
    if IS_LOCAL_BACKEND:
        flask_proc = start_flask()
        if not wait_for_backend():
            log.error("Continuing anyway — Chrome will show an error page until Flask is ready")
    else:
        log.info("Remote backend — not spawning local Flask")
        if not wait_for_backend(timeout=10):
            log.warning("Remote backend unreachable; Chrome will show an error page until it recovers")

    kill_kiosk_chrome()
    clean_chrome_profile_locks()
    time.sleep(1)

    chrome_proc = start_chrome(chrome_path, chrome_flags)
    start_heartbeat_thread()

    log.info("Watchdog running (checking every %ds)", WATCHDOG_INTERVAL)
    chrome_crash_count = 0

    try:
        while True:
            time.sleep(WATCHDOG_INTERVAL)

            if flask_proc is not None and flask_proc.poll() is not None:
                log.warning("Flask died (exit code %s) — restarting in %ds",
                            flask_proc.returncode, FLASK_RESTART_DELAY)
                time.sleep(FLASK_RESTART_DELAY)
                flask_proc = start_flask()
                wait_for_backend()

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
                chrome_proc = start_chrome(chrome_path, chrome_flags)
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
    # Only clean up local Flask if we're meant to run one (local backend mode).
    # On a touchscreen pointed at a remote backend, nothing of ours owns 5001.
    if IS_LOCAL_BACKEND:
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
