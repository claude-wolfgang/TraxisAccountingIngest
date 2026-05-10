import json
import time
import threading
import logging
from datetime import datetime

import config
from database import get_db, push_schedule

log = logging.getLogger("scheduler.sync")


class SyncEngine:
    """Pulls WOs/ops from ProShop, reconciles with local DB, writes back progress."""

    def __init__(self, client):
        self.client = client
        self._sync_thread = None
        self._writeback_thread = None
        self._stop = threading.Event()

    def start_background(self):
        """Start background sync and writeback threads."""
        self._stop.clear()
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True, name="sync")
        self._writeback_thread = threading.Thread(target=self._writeback_loop, daemon=True, name="writeback")
        self._sync_thread.start()
        self._writeback_thread.start()
        log.info("Background sync started (sync=%ds, writeback=%ds)",
                 config.SYNC_INTERVAL, config.WRITEBACK_INTERVAL)

    def stop(self):
        self._stop.set()

    # ── Full Sync ─────────────────────────────────────────────────────────

    def full_sync(self):
        """Pull all active WOs + ops from ProShop, reconcile with local DB."""
        conn = get_db()
        start = time.time()
        sync_id = _log_sync(conn, "full", "started")

        try:
            # Pull work orders
            wo_result = self.client.get_work_orders(status="active", page_size=500)
            wo_records = wo_result.get("records", [])
            wo_count = len(wo_records)
            log.info("Pulled %d active WOs from ProShop", wo_count)

            # Upsert work orders
            for wo in wo_records:
                _upsert_work_order(conn, wo)

            # Pull operations for each WO
            op_count = 0
            for wo in wo_records:
                wo_num = wo.get("workOrderNumber", "")
                if not wo_num:
                    continue
                try:
                    ops = self.client.get_operations(wo_num)
                    for op in ops:
                        _upsert_operation(conn, wo_num, op)
                        op_count += 1
                    # Auto-compute program readiness per WO
                    _compute_program_readiness(conn, wo_num, ops)
                except Exception as e:
                    log.warning("Failed to pull ops for WO %s: %s", wo_num, e)

            # Mark WOs not in ProShop active list as complete
            active_numbers = {wo.get("workOrderNumber") for wo in wo_records if wo.get("workOrderNumber")}
            if active_numbers:
                placeholders = ",".join("?" * len(active_numbers))
                conn.execute(
                    f"""UPDATE work_orders SET status='complete'
                        WHERE status='active' AND wo_number NOT IN ({placeholders})""",
                    list(active_numbers)
                )
                conn.commit()

            # Clean up schedule blocks for WOs just marked complete
            result = conn.execute(
                """DELETE FROM schedule_blocks
                   WHERE is_locked=0 AND status != 'complete'
                   AND operation_id IN (
                       SELECT id FROM operations WHERE wo_number IN (
                           SELECT wo_number FROM work_orders WHERE status='complete'
                       )
                   )"""
            )
            removed_blocks = result.rowcount
            if removed_blocks:
                conn.commit()
                log.info("Removed %d schedule blocks for completed WOs", removed_blocks)

            # Compute material readiness from vendor POs + part stock data
            try:
                _compute_material_readiness(conn, self.client, active_numbers, wo_records)
            except Exception as e:
                log.warning("Material readiness sync failed: %s", e)

            # Sync machine pockets
            try:
                _sync_machine_pockets(conn, self.client)
            except Exception as e:
                log.warning("Machine pocket sync failed: %s", e)

            # Sync operation tool requirements
            try:
                _sync_operation_tools(conn, self.client, active_numbers)
            except Exception as e:
                log.warning("Operation tools sync failed: %s", e)

            duration_ms = int((time.time() - start) * 1000)
            # Push past-due incomplete blocks forward
            pushed = push_schedule(conn)

            _update_sync(conn, sync_id, "completed", wo_count, op_count, duration_ms)
            log.info("Full sync complete: %d WOs, %d ops in %dms (pushed %d blocks)",
                     wo_count, op_count, duration_ms, pushed)

            return {"wo_count": wo_count, "op_count": op_count, "duration_ms": duration_ms, "pushed": pushed}

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            _update_sync(conn, sync_id, "failed", details=str(e), duration_ms=duration_ms)
            log.error("Full sync failed: %s", e)
            raise
        finally:
            conn.close()

    # ── Writeback ─────────────────────────────────────────────────────────

    def process_writeback(self):
        """Send queued progress updates back to ProShop."""
        conn = get_db()
        try:
            pending = conn.execute(
                "SELECT * FROM writeback_queue WHERE status='pending' ORDER BY created_at LIMIT 50"
            ).fetchall()

            if not pending:
                return 0

            sent = 0
            for row in pending:
                row = dict(row)
                try:
                    op_id = row["operation_id"]
                    parts = op_id.split("-", 1)
                    wo_number = parts[0]
                    op_number = int(parts[1]) if len(parts) > 1 else 0

                    if row["field"] == "perOpQtyComplete":
                        self.client.update_operation_qty(wo_number, op_number, int(row["value"]))
                    elif row["field"] == "isOpComplete":
                        self.client.complete_operation(wo_number, op_number)

                    conn.execute(
                        "UPDATE writeback_queue SET status='sent', sent_at=datetime('now') WHERE id=?",
                        (row["id"],)
                    )
                    sent += 1
                except Exception as e:
                    attempts = row.get("attempts", 0) + 1
                    new_status = "failed" if attempts >= 3 else "pending"
                    conn.execute(
                        "UPDATE writeback_queue SET status=?, attempts=?, error=? WHERE id=?",
                        (new_status, attempts, str(e), row["id"])
                    )
                    log.warning("Writeback failed for %s: %s (attempt %d)",
                                row["operation_id"], e, attempts)

            conn.commit()
            if sent:
                log.info("Wrote back %d/%d updates to ProShop", sent, len(pending))
            return sent
        finally:
            conn.close()

    # ── Background Loops ──────────────────────────────────────────────────

    def _sync_loop(self):
        # Initial sync on startup
        try:
            self.full_sync()
        except Exception as e:
            log.error("Initial sync failed: %s", e)

        while not self._stop.wait(config.SYNC_INTERVAL):
            try:
                self.full_sync()
            except Exception as e:
                log.error("Sync loop error: %s", e)

    def _writeback_loop(self):
        while not self._stop.wait(config.WRITEBACK_INTERVAL):
            try:
                self.process_writeback()
            except Exception as e:
                log.error("Writeback loop error: %s", e)
            try:
                push_schedule()
            except Exception as e:
                log.error("Push schedule error: %s", e)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _upsert_work_order(conn, wo):
    """Insert or update a work order from ProShop data."""
    wo_number = wo.get("workOrderNumber", "")
    if not wo_number:
        return

    material_type = ""  # materialPlainText not available in this API version

    conn.execute("""
        INSERT INTO work_orders (wo_number, part_number, part_name, customer,
                                 due_date, qty_ordered, qty_complete, status, priority,
                                 material_type, proshop_data, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, datetime('now'))
        ON CONFLICT(wo_number) DO UPDATE SET
            part_number=excluded.part_number,
            part_name=excluded.part_name,
            customer=excluded.customer,
            due_date=excluded.due_date,
            qty_ordered=excluded.qty_ordered,
            qty_complete=excluded.qty_complete,
            priority=excluded.priority,
            material_type=excluded.material_type,
            proshop_data=excluded.proshop_data,
            synced_at=datetime('now')
    """, (
        wo_number,
        wo.get("partPlainText", ""),
        wo.get("partPlainText", ""),
        "",  # customer — requires contacts:r scope
        wo.get("dueDate", ""),
        _int(wo.get("quantityOrdered")),
        _int(wo.get("qtyComplete")),
        _int(wo.get("deliverypriority")),
        material_type,
        json.dumps(wo),
    ))
    conn.commit()


def _upsert_operation(conn, wo_number, op):
    """Insert or update an operation from ProShop data."""
    op_number = op.get("operationNumber")
    if op_number is None:
        return

    op_id = f"{wo_number}-{op_number}"

    # Get cycle time per part (minutes) and qty
    minutes_per_part = _float(op.get("minutesPerPart"))
    wo_qty = _int(op.get("_woQty"))

    # Calculate total estimated hours for this operation
    total_cycle_time = _float(op.get("totalCycleTime"))  # total hours (setup + run)
    if minutes_per_part and minutes_per_part > 0 and wo_qty > 0:
        est_hours = (minutes_per_part * wo_qty) / 60.0
        is_estimated = 0
    elif total_cycle_time and total_cycle_time > 0:
        # totalCycleTime is already total hours for this op (setup + run combined)
        est_hours = total_cycle_time
        is_estimated = 0
    else:
        # Last resort: runTime from API is in seconds
        run_time = _float(op.get("runTime"))
        if run_time and run_time > 0:
            est_hours = run_time / 3600.0  # seconds to hours
            is_estimated = 1
        else:
            est_hours = None
            is_estimated = 1

    # Setup time — API returns seconds, convert to hours
    raw_setup = _float(op.get("setupTime"))
    setup_hours = raw_setup / 3600.0 if raw_setup else None

    # Operation name: prefer partOperation description, then operationDescription, then operationType
    part_op = op.get("partOperation") or {}
    op_name = (part_op.get("operationDescription")
               or op.get("operationDescription")
               or op.get("operationType")
               or "")

    # Look up machine from work center (ProShop potId like "Mill-1", "T2", "MILL-X")
    work_center_text = (op.get("workCenterPlainText") or "").strip()
    work_center_code = work_center_text
    machine_id = None
    if work_center_code:
        # Try exact match first, then case-insensitive
        row = conn.execute(
            "SELECT machine_id FROM work_center_map WHERE proshop_code=?",
            (work_center_code,)
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT machine_id FROM work_center_map WHERE LOWER(proshop_code)=LOWER(?)",
                (work_center_code,)
            ).fetchone()
        if row:
            machine_id = row[0]  # May be NULL for MILL-X (catch-all)

    conn.execute("""
        INSERT INTO operations (id, wo_number, op_number, op_name, work_center,
                                machine_id, est_hours, setup_hours,
                                qty_required, qty_complete, is_complete, is_estimated,
                                proshop_data, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            op_name=excluded.op_name,
            work_center=excluded.work_center,
            machine_id=COALESCE(operations.machine_id, excluded.machine_id),
            est_hours=excluded.est_hours,
            setup_hours=excluded.setup_hours,
            qty_required=excluded.qty_required,
            qty_complete=excluded.qty_complete,
            is_complete=excluded.is_complete,
            is_estimated=excluded.is_estimated,
            proshop_data=excluded.proshop_data,
            synced_at=datetime('now')
    """, (
        op_id,
        wo_number,
        op_number,
        op_name,
        work_center_code,
        machine_id,
        est_hours if est_hours else None,
        setup_hours,
        wo_qty or 0,
        _int(op.get("perOpQtyComplete")),
        1 if op.get("isOpComplete") else 0,
        is_estimated,
        json.dumps(op),
    ))
    conn.commit()


def _log_sync(conn, sync_type, status, details=None):
    cur = conn.execute(
        "INSERT INTO sync_log (sync_type, status, details) VALUES (?, ?, ?)",
        (sync_type, status, details)
    )
    conn.commit()
    return cur.lastrowid


def _update_sync(conn, sync_id, status, wo_count=0, op_count=0, duration_ms=0, details=None):
    conn.execute(
        """UPDATE sync_log SET status=?, wo_count=?, op_count=?, duration_ms=?, details=?
           WHERE id=?""",
        (status, wo_count, op_count, duration_ms, details, sync_id)
    )
    conn.commit()


def _int(val, default=0):
    if val is None:
        return default
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return default


def _float(val):
    if val is None:
        return None
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return None


# ── Readiness Helpers ────────────────────────────────────────────────────────

def _compute_program_readiness(conn, wo_number, ops):
    """WO-level check: if the Programming op is complete (or absent), all mfg ops are program_ready."""
    programming_op = None
    mfg_op_ids = []

    for op in ops:
        op_type = (op.get("operationType") or "").strip()
        op_num = op.get("operationNumber")
        if op_num is None:
            continue
        op_id = f"{wo_number}-{op_num}"

        if op_type == "Programming":
            programming_op = op
        # Mfg ops have work centers that map to machines (Mill-*, T2, MILL-X)
        wc = (op.get("workCenterPlainText") or "").strip()
        if wc:
            row = conn.execute(
                "SELECT proshop_code FROM work_center_map WHERE proshop_code=?", (wc,)
            ).fetchone()
            if row:
                mfg_op_ids.append(op_id)

    # Programming complete if: no programming op exists, or it's marked complete
    prog_ready = 1
    if programming_op and not programming_op.get("isOpComplete"):
        prog_ready = 0

    for op_id in mfg_op_ids:
        conn.execute("""
            INSERT INTO readiness (operation_id, program_ready, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(operation_id) DO UPDATE SET
                program_ready=excluded.program_ready,
                updated_at=datetime('now')
        """, (op_id, prog_ready))
    conn.commit()


def _compute_material_readiness(conn, client, active_wo_numbers, wo_records=None):
    """Determine material readiness per WO from Part Stock data.

    Three states:
      - not_ordered:      Material defined but no PO linked
      - ordered:          PO exists (Outstanding / Released / Partially Released)
      - received:         PO received field is set
      - on_hand:          PO text is "In Stock" / similar, or no material needed
    """
    # Build WO → material status from partStockStatuses
    wo_mat_status = {}
    for wo in (wo_records or []):
        wo_num = wo.get("workOrderNumber", "")
        stocks = (wo.get("partStockStatuses") or {}).get("records", [])
        has_mat = any(s.get("material") for s in stocks)

        if not has_mat:
            wo_mat_status[wo_num] = (1, {"status": "no_material_needed"})
            continue

        # Check Part Stock PO linkage
        po_text = None
        po_received = None
        po_order_status = None
        for s in stocks:
            pt = (s.get("psPONumberPlainText") or "").strip()
            if pt:
                po_text = pt
                po_obj = s.get("psPONumber") or {}
                po_received = po_obj.get("received")
                po_order_status = po_obj.get("orderStatus")
                break

        if not po_text:
            # Material defined but no PO
            wo_mat_status[wo_num] = (0, {"status": "not_ordered"})
        elif po_text.lower() in ("in stock", "on hand", "customer supplied", "stock"):
            wo_mat_status[wo_num] = (1, {"status": "on_hand", "note": po_text})
        elif po_received:
            wo_mat_status[wo_num] = (1, {"status": "received", "po": po_text,
                                          "received_date": po_received})
        else:
            wo_mat_status[wo_num] = (0, {"status": "ordered", "po": po_text,
                                          "order_status": po_order_status or ""})

    # For any active WO not in wo_records, default to unknown
    for wo_num in active_wo_numbers:
        if wo_num not in wo_mat_status:
            wo_mat_status[wo_num] = (1, {"status": "unknown"})

    # Write to DB
    for wo_num, (mat_ready, detail_obj) in wo_mat_status.items():
        detail = json.dumps(detail_obj)
        mfg_ops = conn.execute(
            """SELECT o.id FROM operations o
               JOIN work_center_map wcm ON o.work_center = wcm.proshop_code
               WHERE o.wo_number=? AND o.is_complete=0""",
            (wo_num,)
        ).fetchall()
        for row in mfg_ops:
            conn.execute("""
                INSERT INTO readiness (operation_id, material_ready, material_detail, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(operation_id) DO UPDATE SET
                    material_ready=excluded.material_ready,
                    material_detail=excluded.material_detail,
                    updated_at=datetime('now')
            """, (row["id"], mat_ready, detail))
    conn.commit()


def _sync_machine_pockets(conn, client):
    """Sync pocket layouts for all active machines from ProShop."""
    machines = conn.execute(
        "SELECT id, proshop_id FROM machines WHERE is_active=1 AND proshop_id IS NOT NULL"
    ).fetchall()

    for machine in machines:
        pot_id = machine["proshop_id"]
        machine_id = machine["id"]
        try:
            wc_data = client.get_work_cell_pockets(pot_id)
            if not wc_data:
                continue
            pockets = (wc_data.get("pockets") or {}).get("records", [])

            # Clear old pockets for this machine, then insert fresh
            conn.execute("DELETE FROM machine_pockets WHERE machine_id=?", (machine_id,))
            for i, p in enumerate(pockets):
                tool_text = (p.get("toolPlainText") or "").strip()
                conn.execute("""
                    INSERT INTO machine_pockets (machine_id, pocket_number, tool_number,
                                                  out_of_holder, holder, synced_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (
                    machine_id,
                    p.get("legacyId") or (i + 1),
                    tool_text if tool_text else None,
                    _float(p.get("outOfHolder")),
                    (p.get("holder") or "").strip() or None,
                ))
            log.info("Synced %d pockets for %s", len(pockets), pot_id)
        except Exception as e:
            log.warning("Failed to sync pockets for %s: %s", pot_id, e)

    conn.commit()


def _sync_operation_tools(conn, client, active_wo_numbers):
    """Sync tool requirements for operations from ProShop partOperation.tools."""
    for wo_num in active_wo_numbers:
        try:
            tools_data = client.get_operation_tools(wo_num)
            if not tools_data:
                continue
            for op_num, tools in tools_data.items():
                op_id = f"{wo_num}-{op_num}"
                # Check op exists
                if not conn.execute("SELECT 1 FROM operations WHERE id=?", (op_id,)).fetchone():
                    continue
                # Clear old tools for this op
                conn.execute("DELETE FROM operation_tools WHERE operation_id=?", (op_id,))
                for t in tools:
                    tool_info = t.get("tool") or {}
                    conn.execute("""
                        INSERT INTO operation_tools (operation_id, tool_number, tool_description,
                                                     holder, out_of_holder, sequence_number, synced_at)
                        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """, (
                        op_id,
                        tool_info.get("toolNumber") or tool_info.get("description", ""),
                        tool_info.get("description", ""),
                        (t.get("holder") or "").strip() or None,
                        _float(t.get("outOfHolder")),
                        _int(t.get("sequenceNumber")),
                    ))
        except Exception as e:
            log.warning("Failed to sync tools for WO %s: %s", wo_num, e)
    conn.commit()
