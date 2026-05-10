"""
Traxis Agent Service Wrapper -- Overseer Launcher

Runs Overseer as a long-running subprocess. Restarts on crash with
exponential backoff (30s, doubling, capped at 300s; resets to 30s after
5 minutes of sustained uptime).

Designed to be wrapped by NSSM as the TraxisAgent Windows service.
On srv-01 you may also wrap overseer.py directly with NSSM and skip this
script entirely.

Usage:
    python service_wrapper.py            # Normal run (as service)
    python service_wrapper.py --status   # Print where to look for status and exit
    python service_wrapper.py --once     # Start overseer once and exit (testing)
"""

import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---- Paths ------------------------------------------------------------------


def _env(name, default):
    """Return env var if set and non-empty, else default."""
    val = os.environ.get(name, "").strip()
    return val if val else default


PROJECT_ROOT = Path(__file__).parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Overseer uses the system Python (Flask/requests installed there, not necessarily here).
# Defaults match the .71 (TRAXIS user) install. On srv-01, set TRAXIS_PYTHON
# and TRAXIS_BASE_DIR -- same env vars consumed by overseer.py itself.
OVERSEER_PYTHON = _env(
    "TRAXIS_PYTHON",
    r"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe",
)
_PROSHOP_AUTOMATIONS = Path(_env(
    "TRAXIS_BASE_DIR",
    r"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations",
))
OVERSEER_SCRIPT = _PROSHOP_AUTOMATIONS / "Overseer" / "overseer.py"
OVERSEER_DIR = OVERSEER_SCRIPT.parent

# ---- Environment Pre-resolution --------------------------------------------
# Ensure critical env vars are in os.environ so child processes inherit them.
# Git Bash can't see Windows User env vars; resolve them once via PowerShell.

_REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]


def _resolve_env_vars():
    """Pre-resolve Windows User env vars into os.environ for child processes."""
    if os.name != "nt":
        return
    for name in _REQUIRED_ENV_VARS:
        if os.environ.get(name):
            continue
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"[Environment]::GetEnvironmentVariable('{name}', 'User')"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            val = result.stdout.strip()
            if val:
                os.environ[name] = val
        except Exception:
            pass


_resolve_env_vars()

# ---- Logging ----------------------------------------------------------------

log = logging.getLogger("traxis_service")


def _setup_logging():
    log.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    fh = logging.FileHandler(LOG_DIR / "service_wrapper.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    log.addHandler(fh)


# ---- Constants --------------------------------------------------------------

TICK_S = 10  # Main loop tick

# ---- Subprocess Manager -----------------------------------------------------


class ServiceManager:
    """Runs Overseer as a long-running subprocess. Restarts on crash."""

    def __init__(self):
        self.overseer_proc = None
        self.overseer_backoff = 30
        self.overseer_max_backoff = 300
        self.overseer_last_restart = 0

    def start_overseer(self):
        """Start overseer.py as a subprocess."""
        if self.overseer_proc and self.overseer_proc.poll() is None:
            return  # Already running

        now = time.time()
        elapsed = now - self.overseer_last_restart
        if elapsed < self.overseer_backoff:
            return  # Still in backoff window

        script = str(OVERSEER_SCRIPT)
        overseer_log = open(LOG_DIR / "overseer_stdout.log", "a", encoding="utf-8")
        log.info("Starting overseer.py ...")
        try:
            self.overseer_proc = subprocess.Popen(
                [OVERSEER_PYTHON, "-u", script],
                cwd=str(OVERSEER_DIR),
                stdout=overseer_log,
                stderr=overseer_log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.overseer_last_restart = now
            log.info("overseer.py started (PID %d).", self.overseer_proc.pid)
        except Exception as e:
            log.error("Failed to start overseer.py: %s", e)

    def check_overseer(self):
        """Check if overseer is running, restart with backoff if crashed."""
        if not self.overseer_proc:
            self.start_overseer()
            return

        rc = self.overseer_proc.poll()
        if rc is None:
            # Still running -- reset backoff on sustained uptime (5 min)
            if time.time() - self.overseer_last_restart > 300:
                self.overseer_backoff = 30
            return

        log.warning("overseer.py exited with code %s. Restarting (backoff %ds)...",
                    rc, self.overseer_backoff)
        self.overseer_proc = None
        self.start_overseer()

        # Exponential backoff (capped)
        self.overseer_backoff = min(self.overseer_backoff * 2, self.overseer_max_backoff)

    def stop_overseer(self):
        """Gracefully stop the overseer."""
        if not self.overseer_proc or self.overseer_proc.poll() is not None:
            self.overseer_proc = None
            return

        log.info("Stopping overseer.py (PID %d)...", self.overseer_proc.pid)
        self.overseer_proc.terminate()
        try:
            self.overseer_proc.wait(timeout=10)
            log.info("overseer.py stopped gracefully.")
        except subprocess.TimeoutExpired:
            log.warning("overseer.py did not stop in 10s, killing.")
            self.overseer_proc.kill()
            self.overseer_proc.wait(timeout=5)
        self.overseer_proc = None


# ---- Main loop --------------------------------------------------------------


class ServiceWrapper:
    """Runs and monitors Overseer."""

    def __init__(self, run_once=False):
        self.pid = os.getpid()
        self.started_at = datetime.now()
        self.run_once = run_once
        self.running = True
        self.mgr = ServiceManager()
        log.info("Service wrapper starting (pid=%d)", self.pid)

    def run(self):
        """Main loop."""
        self.mgr.start_overseer()

        if self.run_once:
            log.info("--once flag: exiting after initial start.")
            return

        while self.running:
            try:
                self.mgr.check_overseer()
                time.sleep(TICK_S)
            except Exception as e:
                log.error("Main loop error: %s", e, exc_info=True)
                time.sleep(TICK_S)

        log.info("Shutting down...")
        self.mgr.stop_overseer()
        log.info("Service wrapper stopped.")

    def shutdown(self):
        log.info("Shutdown signal received.")
        self.running = False


# ---- CLI --------------------------------------------------------------------


def show_status():
    """Print where to look for status and exit.

    Leader election was removed; there's no shared heartbeat file to inspect.
    """
    print("service_wrapper has no shared status file (leader election removed).")
    print("  NSSM service:     nssm status TraxisAgent")
    print("  Overseer dashboard: http://localhost:8060")


def main():
    if "--status" in sys.argv:
        show_status()
        return

    _setup_logging()
    run_once = "--once" in sys.argv

    wrapper = ServiceWrapper(run_once=run_once)

    def _signal_handler(signum, frame):
        wrapper.shutdown()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _signal_handler)

    wrapper.run()


if __name__ == "__main__":
    main()
