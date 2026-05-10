"""Background status checker — polls machine reachability."""

from __future__ import annotations

import threading
import time

from traxistransfer.constants import STATUS_CHECK_INTERVAL_S
from traxistransfer.models.machine import Machine
from traxistransfer.services.transfer_service import get_driver


class StatusChecker:
    """Daemon thread that polls machine reachability at regular intervals."""

    def __init__(self, machines: list[Machine], callback=None, interval: int = STATUS_CHECK_INTERVAL_S):
        self._machines = [m for m in machines if m.enabled]
        self._callback = callback  # callback(machine_id: str, reachable: bool)
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        """Start the background status checker."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="StatusChecker")
        self._thread.start()

    def stop(self):
        """Stop the background status checker."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        """Main loop: check each machine, sleep, repeat."""
        while not self._stop_event.is_set():
            for machine in self._machines:
                if self._stop_event.is_set():
                    break
                try:
                    driver = get_driver(machine)
                    reachable = driver.is_reachable()
                except Exception:
                    reachable = False

                machine.reachable = reachable
                if self._callback:
                    self._callback(machine.id, reachable)

            self._stop_event.wait(self._interval)

    def check_now(self, machine: Machine) -> bool:
        """Synchronously check a single machine (called from main thread)."""
        try:
            driver = get_driver(machine)
            reachable = driver.is_reachable()
            machine.reachable = reachable
            return reachable
        except Exception:
            machine.reachable = False
            return False
