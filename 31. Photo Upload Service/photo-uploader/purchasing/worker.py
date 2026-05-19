"""Background worker: polls approved orders and creates VPOs in ProShop.

P35 Phase 2. Mirrors upload_worker.py's daemon-thread pattern.

Lifecycle: start() → _run() loop → stop().
The loop polls every POLL_INTERVAL seconds for status='approved' orders,
looks up the most recent prior VPO line (blind-copy supplier/cost), creates
the VPO via addPurchaseOrder + overwritePurchaseOrder, then marks the order
as vpo_created or failed.

A single BasicAuthSession is kept alive across iterations; it auto-refreshes
on 401 (session tokens expire after ~300s of inactivity).
"""
from __future__ import annotations
import logging
import threading
import time

from . import queue as purchasing_queue
from .proshop_basic_auth import BasicAuthSession, GraphQLError
from .proshop_vpo import P35_SCOPE, find_last_vpo_line, create_vpo

log = logging.getLogger("purchasing-worker")

POLL_INTERVAL = 30        # seconds between queue checks
BATCH_SIZE = 5            # orders per poll cycle
SESSION_IDLE_TIMEOUT = 600  # close ProShop session after 10 min idle


class PurchasingWorker:
    """Background thread that creates VPOs for approved purchasing orders."""

    def __init__(self, base_url, username, password):
        self._base_url = base_url
        self._username = username
        self._password = password
        self._thread = None
        self._stop_event = threading.Event()
        self._session = None
        self._last_activity = 0

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="purchasing-worker")
        self._thread.start()
        log.info("Purchasing worker started (Phase 2 — VPO creation)")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._close_session()

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    # ── Session management ────────────────────────────────────────────

    def _ensure_session(self):
        if self._session is None:
            self._session = BasicAuthSession(
                base_url=self._base_url,
                username=self._username,
                password=self._password,
                scope=P35_SCOPE,
            )
            log.info("Opened ProShop basic-auth session for purchasing")

    def _close_session(self):
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
            log.info("Closed ProShop purchasing session")

    # ── Main loop ─────────────────────────────────────────────────────

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._process_queue()
            except Exception as e:
                log.error(f"Purchasing worker loop error: {e}", exc_info=True)
                # If the session is broken, close it so next cycle gets a fresh one
                self._close_session()

            # Close session if idle too long to avoid stale tokens
            if (self._session is not None
                    and (time.time() - self._last_activity) > SESSION_IDLE_TIMEOUT):
                log.info("Purchasing session idle timeout — closing")
                self._close_session()

            self._stop_event.wait(POLL_INTERVAL)

    def _process_queue(self):
        orders = purchasing_queue.get_approved(limit=BATCH_SIZE)
        if not orders:
            return

        self._ensure_session()

        for order in orders:
            if self._stop_event.is_set():
                break
            self._process_order(order)

    def _process_order(self, order):
        order_id = order["id"]
        entity_id = order["entity_id"]
        entity_type = order.get("entity_type", "tool")

        log.info(f"Order #{order_id}: creating VPO for {entity_type} {entity_id} "
                 f"qty={order.get('qty')}")

        try:
            # Look up the most recent prior VPO for this entity (blind-copy
            # supplier, cost, orderNumber, description from prior purchase).
            prior = find_last_vpo_line(self._session, entity_id)
            if prior:
                log.info(f"  Prior VPO {prior['vpo_id']} from {prior['supplier']!r}")
            else:
                log.info(f"  No prior VPO found for {entity_id}")

            # Build queue_row dict matching what create_vpo expects
            queue_row = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "qty": order.get("qty", 1),
                "unit_cost": order.get("unit_cost"),
                "vendor": order.get("vendor"),
                "brand": order.get("brand"),
                "edp": order.get("edp"),
            }

            result = create_vpo(self._session, queue_row, prior)
            vpo_id = result.get("id")

            if not vpo_id:
                raise RuntimeError(f"create_vpo returned no id: {result}")

            proshop_url = result.get("proshopUrl", "")
            purchasing_queue.mark_vpo_created(order_id, str(vpo_id), proshop_url)
            self._last_activity = time.time()
            log.info(f"  VPO created: id={vpo_id} url={proshop_url}")

        except GraphQLError as e:
            error_msg = f"GraphQL error: {e}"
            purchasing_queue.mark_failed(order_id, error_msg)
            log.error(f"  Order #{order_id} failed: {error_msg}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            purchasing_queue.mark_failed(order_id, error_msg)
            log.error(f"  Order #{order_id} failed: {error_msg}", exc_info=True)
