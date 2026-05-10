import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

import config
from database import (
    init_db, get_db, get_machines, get_work_orders, get_operations,
    get_schedule_blocks, create_schedule_block, update_schedule_block,
    delete_schedule_block, get_flags, get_stats, get_setting, set_setting,
    get_readiness, OverlapError, toggle_wo_hidden, get_hidden_work_orders,
    toggle_op_hidden, get_hidden_operations,
)
from proshop_client import ProShopClient, GraphQLError
from sync import SyncEngine
from suggest import get_suggestions
from priority_engine import compute_priorities, generate_bottleneck_report, format_daily_report, format_bottleneck_report

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scheduler")

# ── Startup checks ────────────────────────────────────────────────────────────
if not config.PROSHOP_CLIENT_SECRET:
    print("ERROR: PROSHOP_CLIENT_SECRET environment variable not set.")
    print("Set it before running: set PROSHOP_CLIENT_SECRET=<your secret>")
    sys.exit(1)

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
init_db()

client = ProShopClient(
    config.PROSHOP_GRAPHQL_URL,
    config.PROSHOP_TOKEN_URL,
    config.PROSHOP_CLIENT_ID,
    config.PROSHOP_CLIENT_SECRET,
    config.PROSHOP_SCOPE,
)

sync_engine = SyncEngine(client)
_start_time = time.time()


def _error_response(e):
    if isinstance(e, OverlapError):
        return jsonify({
            "error": str(e),
            "code": "OVERLAP",
            "conflict": e.conflicting_block,
        }), 409
    if isinstance(e, GraphQLError):
        return jsonify({"error": str(e), "code": "GRAPHQL_ERROR"}), 422
    if isinstance(e, ConnectionError):
        return jsonify({"error": "ProShop API is unreachable.", "code": "API_DOWN"}), 503
    return jsonify({"error": str(e), "code": "INTERNAL_ERROR"}), 500


# ── Page Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def scheduler_page():
    return render_template("scheduler.html", cache_bust=int(time.time()), proshop_base=config.PROSHOP_BASE_URL)


@app.route("/operator")
def operator_page():
    return render_template("operator.html")


@app.route("/tools")
def tools_page():
    return render_template("tools.html", proshop_base=config.PROSHOP_BASE_URL)


@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html", proshop_base=config.PROSHOP_BASE_URL)


# ── API: Machines ─────────────────────────────────────────────────────────────

@app.route("/api/machines")
def api_machines():
    return jsonify(get_machines())


# ── API: Work Orders ─────────────────────────────────────────────────────────

@app.route("/api/workorders")
def api_work_orders():
    status = request.args.get("status", "active")
    return jsonify(get_work_orders(status=status))


# ── API: Hide / Unhide Work Orders ───────────────────────────────────────────

@app.route("/api/workorders/<wo_number>/hide", methods=["POST"])
def api_toggle_wo_hidden(wo_number):
    """Toggle hidden flag on a WO. When hiding, also removes its schedule blocks."""
    try:
        conn = get_db()
        new_val = toggle_wo_hidden(conn, wo_number)
        if new_val is None:
            conn.close()
            return jsonify({"error": "Work order not found"}), 404

        removed_blocks = 0
        if new_val == 1:
            # Remove non-locked, non-complete schedule blocks for this WO's ops
            result = conn.execute(
                """DELETE FROM schedule_blocks
                   WHERE is_locked=0 AND status != 'complete'
                   AND operation_id IN (
                       SELECT id FROM operations WHERE wo_number=?
                   )""",
                (wo_number,)
            )
            removed_blocks = result.rowcount
            conn.commit()

        conn.close()
        return jsonify({"ok": True, "hidden": new_val, "removed_blocks": removed_blocks})
    except Exception as e:
        return _error_response(e)


@app.route("/api/workorders/hidden")
def api_hidden_work_orders():
    """Return list of hidden work orders."""
    conn = get_db()
    wos = get_hidden_work_orders(conn)
    conn.close()
    return jsonify(wos)


# ── API: Hide / Unhide Individual Operations ─────────────────────────────────

@app.route("/api/operations/<path:op_id>/hide", methods=["POST"])
def api_toggle_op_hidden(op_id):
    """Toggle hidden flag on a single operation. When hiding, removes its schedule blocks."""
    conn = get_db()
    try:
        new_val = toggle_op_hidden(conn, op_id)
        if new_val is None:
            return jsonify({"error": "Operation not found"}), 404

        removed_blocks = 0
        if new_val == 1:
            result = conn.execute(
                """DELETE FROM schedule_blocks
                   WHERE is_locked=0 AND status != 'complete'
                   AND operation_id=?""",
                (op_id,)
            )
            removed_blocks = result.rowcount
            conn.commit()

        return jsonify({"ok": True, "hidden": new_val, "removed_blocks": removed_blocks})
    except Exception as e:
        return _error_response(e)
    finally:
        conn.close()


@app.route("/api/operations/hidden")
def api_hidden_operations():
    """Return list of individually hidden operations."""
    conn = get_db()
    try:
        ops = get_hidden_operations(conn)
        return jsonify(ops)
    finally:
        conn.close()


# ── API: Operations (Backlog) ─────────────────────────────────────────────────

@app.route("/api/operations")
def api_operations():
    wo = request.args.get("wo")
    unscheduled = request.args.get("unscheduled", "false").lower() == "true"
    schedulable = request.args.get("schedulable", "false").lower() == "true"
    conn = get_db()
    ops = get_operations(conn=conn, wo_number=wo, unscheduled_only=unscheduled, schedulable_only=schedulable)
    # Enrich with readiness data
    op_ids = {o["id"] for o in ops}
    readiness_map = get_readiness(conn, op_ids) if op_ids else {}
    conn.close()
    for op in ops:
        r = readiness_map.get(op["id"])
        op["readiness"] = {
            "program_ready": r["program_ready"] if r else 0,
            "material_ready": r["material_ready"] if r else 0,
            "tools_ready": r["tools_ready"] if r else 0,
            "machine_ready": r["machine_ready"] if r else 0,
        }
    return jsonify(ops)


# ── API: Readiness Toggle ────────────────────────────────────────────────────

@app.route("/api/workorders/<wo>/tools-ready", methods=["POST"])
def api_wo_tools_ready(wo):
    """Mark all ops for a WO as tools-ready."""
    try:
        conn = get_db()
        ops = conn.execute(
            "SELECT id FROM operations WHERE wo_number=? AND is_complete=0", (wo,)
        ).fetchall()
        for op in ops:
            conn.execute("""
                INSERT INTO readiness (operation_id, tools_ready, updated_at)
                VALUES (?, 1, datetime('now'))
                ON CONFLICT(operation_id) DO UPDATE SET
                    tools_ready=1, updated_at=datetime('now')
            """, (op["id"],))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "wo_number": wo, "ops_updated": len(ops)})
    except Exception as e:
        return _error_response(e)


@app.route("/api/operations/<path:op_id>/tools-ready", methods=["POST"])
def api_toggle_tools_ready(op_id):
    """Toggle the tools_ready flag for an operation."""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT tools_ready FROM readiness WHERE operation_id=?", (op_id,)
        ).fetchone()
        new_val = 0 if (row and row["tools_ready"]) else 1
        conn.execute("""
            INSERT INTO readiness (operation_id, tools_ready, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(operation_id) DO UPDATE SET
                tools_ready=excluded.tools_ready,
                updated_at=datetime('now')
        """, (op_id, new_val))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "tools_ready": new_val})
    except Exception as e:
        return _error_response(e)


# ── API: Part Drawing ────────────────────────────────────────────────────────

@app.route("/api/workorders/<wo>/drawing")
def api_wo_drawing(wo):
    """Fetch part drawing URL from ProShop for the side panel preview."""
    try:
        drawing = client.get_part_drawing(wo)
        if drawing:
            file_url = drawing.get("fileUrl", "")
            # Make absolute URL if relative
            if file_url and not file_url.startswith("http"):
                base = config.PROSHOP_GRAPHQL_URL.rsplit("/api/", 1)[0]
                file_url = base + (file_url if file_url.startswith("/") else "/" + file_url)
            ext = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""
            file_type = "pdf" if ext == "pdf" else "image"
            return jsonify({
                "title": drawing.get("title", ""),
                "url": file_url,
                "type": file_type,
            })
        return jsonify({"url": None})
    except Exception as e:
        return jsonify({"url": None, "error": str(e)})


# ── API: Schedule Blocks (CRUD) ──────────────────────────────────────────────

@app.route("/api/blocks")
def api_blocks():
    machine_id = request.args.get("machine")
    start = request.args.get("start")
    end = request.args.get("end")
    conn = get_db()
    blocks = get_schedule_blocks(conn=conn, machine_id=machine_id, start=start, end=end)
    # Gather readiness for all block operations
    block_op_ids = {b["operation_id"] for b in blocks}
    readiness_map = get_readiness(conn, block_op_ids) if block_op_ids else {}
    conn.close()

    # Convert to EventCalendar format
    events = []
    for b in blocks:
        due = b.get("due_date", "")
        urgency = _urgency_color(due, b.get("status", "scheduled"))
        progress = 0
        if b["qty_required"] and b["qty_required"] > 0:
            progress = min(100, int((b["qty_complete"] or 0) / b["qty_required"] * 100))

        events.append({
            "id": b["id"],
            "resourceId": b["machine_id"],
            "start": b["start_time"],
            "end": b["end_time"],
            "title": f"WO{b['wo_number']} Op{b['op_number']}",
            "subtitle": b.get("part_name", "") or b.get("op_name", ""),
            "backgroundColor": b.get("color") or urgency["bg"],
            "borderColor": urgency["border"],
            "textColor": urgency["text"],
            "extendedProps": {
                "block_id": b["id"],
                "operation_id": b["operation_id"],
                "machine_id": b["machine_id"],
                "wo_number": b["wo_number"],
                "op_number": b["op_number"],
                "op_name": b.get("op_name", ""),
                "part_number": b.get("part_number", ""),
                "part_name": b.get("part_name", ""),
                "customer": b.get("customer", ""),
                "due_date": due,
                "qty_required": b["qty_required"],
                "qty_complete": b["qty_complete"],
                "progress": progress,
                "status": b["status"],
                "is_locked": b.get("is_locked", 0),
                "is_estimated": b.get("is_estimated", 0),
                "machine_name": b.get("machine_name", ""),
                "material_type": b.get("material_type", ""),
                "est_hours": b.get("est_hours"),
                "override_hours": b.get("override_hours"),
                "readiness": {
                    "program_ready": readiness_map.get(b["operation_id"], {}).get("program_ready", 0),
                    "material_ready": readiness_map.get(b["operation_id"], {}).get("material_ready", 0),
                    "tools_ready": readiness_map.get(b["operation_id"], {}).get("tools_ready", 0),
                    "machine_ready": readiness_map.get(b["operation_id"], {}).get("machine_ready", 0),
                },
            },
        })
    return jsonify(events)


@app.route("/api/blocks", methods=["POST"])
def api_create_block():
    import sqlite3 as _sqlite3
    data = request.get_json()
    # Prevent duplicate blocks for the same operation
    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM schedule_blocks WHERE operation_id = ? AND status != 'complete'",
            (data["operation_id"],),
        ).fetchone()
        conn.close()
        if existing:
            return jsonify({"error": f"Operation {data['operation_id']} is already scheduled (block #{existing[0]})"}), 409
    except Exception:
        pass
    last_err = None
    for attempt in range(3):
        try:
            conn = get_db()
            block_id = create_schedule_block(
                conn,
                operation_id=data["operation_id"],
                machine_id=data["machine_id"],
                start_time=data["start_time"],
                end_time=data["end_time"],
                created_by=data.get("created_by"),
            )
            conn.close()
            return jsonify({"id": block_id}), 201
        except OverlapError as e:
            log.warning("Overlap rejected: %s", e)
            return _error_response(e)
        except _sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower() and attempt < 2:
                log.warning("DB locked on create_block attempt %d, retrying...", attempt + 1)
                try:
                    conn.close()
                except Exception:
                    pass
                time.sleep(0.3 * (attempt + 1))
                continue
            return _error_response(e)
        except Exception as e:
            return _error_response(e)
    return _error_response(last_err or Exception("Failed after retries"))


@app.route("/api/blocks/<int:block_id>", methods=["PUT"])
def api_update_block(block_id):
    import sqlite3 as _sqlite3
    data = request.get_json()
    last_err = None
    for attempt in range(3):
        try:
            conn = get_db()

            # Check if locked
            row = conn.execute("SELECT is_locked FROM schedule_blocks WHERE id=?", (block_id,)).fetchone()
            if row and row[0] and not data.get("force"):
                conn.close()
                return jsonify({"error": "Block is locked"}), 409

            update_schedule_block(conn, block_id, **data)
            conn.close()
            return jsonify({"ok": True})
        except _sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower() and attempt < 2:
                log.warning("DB locked on update_block attempt %d, retrying...", attempt + 1)
                try:
                    conn.close()
                except Exception:
                    pass
                time.sleep(0.3 * (attempt + 1))
                continue
            return _error_response(e)
        except Exception as e:
            return _error_response(e)
    return _error_response(last_err or Exception("Failed after retries"))


@app.route("/api/blocks/clear", methods=["POST"])
def api_clear_blocks():
    """Remove all non-locked, non-complete schedule blocks."""
    try:
        conn = get_db()
        result = conn.execute(
            "DELETE FROM schedule_blocks WHERE is_locked=0 AND status != 'complete'"
        )
        count = result.rowcount
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "deleted": count})
    except Exception as e:
        return _error_response(e)


@app.route("/api/blocks/<int:block_id>", methods=["DELETE"])
def api_delete_block(block_id):
    try:
        conn = get_db()
        delete_schedule_block(conn, block_id)
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return _error_response(e)


@app.route("/api/blocks/swap", methods=["POST"])
def api_swap_blocks():
    """Swap time slots (and optionally machines) of two blocks."""
    data = request.get_json()
    block_a = data.get("block_a")
    block_b = data.get("block_b")
    if not block_a or not block_b:
        return jsonify({"error": "block_a and block_b are required"}), 400
    log.info("Swap request: block_a=%s (%s), block_b=%s (%s)", block_a, type(block_a).__name__, block_b, type(block_b).__name__)
    try:
        conn = get_db()
        a = conn.execute(
            "SELECT id, machine_id, start_time, end_time, is_locked FROM schedule_blocks WHERE id=?",
            (block_a,),
        ).fetchone()
        b = conn.execute(
            "SELECT id, machine_id, start_time, end_time, is_locked FROM schedule_blocks WHERE id=?",
            (block_b,),
        ).fetchone()
        if not a or not b:
            log.warning("Swap: block not found — a=%s, b=%s", a is not None, b is not None)
            conn.close()
            return jsonify({"error": f"Block not found (a={block_a} exists={a is not None}, b={block_b} exists={b is not None})"}), 404
        if a["is_locked"] or b["is_locked"]:
            conn.close()
            return jsonify({"error": "Cannot swap locked blocks"}), 409
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE schedule_blocks SET machine_id=?, start_time=?, end_time=?, updated_at=? WHERE id=?",
            (b["machine_id"], b["start_time"], b["end_time"], now, block_a),
        )
        conn.execute(
            "UPDATE schedule_blocks SET machine_id=?, start_time=?, end_time=?, updated_at=? WHERE id=?",
            (a["machine_id"], a["start_time"], a["end_time"], now, block_b),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return _error_response(e)


# ── API: Operator Actions ─────────────────────────────────────────────────────

@app.route("/api/blocks/<int:block_id>/progress", methods=["POST"])
def api_update_progress(block_id):
    """Operator adds parts completed."""
    try:
        data = request.get_json()
        qty_add = int(data.get("qty", 0))
        operator = data.get("operator", "")
        conn = get_db()

        # Get block + operation
        block = conn.execute(
            "SELECT * FROM schedule_blocks WHERE id=?", (block_id,)
        ).fetchone()
        if not block:
            conn.close()
            return jsonify({"error": "Block not found"}), 404

        op = conn.execute(
            "SELECT * FROM operations WHERE id=?", (block["operation_id"],)
        ).fetchone()
        if not op:
            conn.close()
            return jsonify({"error": "Operation not found"}), 404

        new_qty = (op["qty_complete"] or 0) + qty_add

        # Update local operation
        conn.execute(
            "UPDATE operations SET qty_complete=? WHERE id=?",
            (new_qty, op["id"])
        )

        # Set block to running if scheduled
        if block["status"] == "scheduled":
            conn.execute(
                "UPDATE schedule_blocks SET status='running', updated_at=datetime('now') WHERE id=?",
                (block_id,)
            )

        # Log operator update
        conn.execute(
            """INSERT INTO operator_updates (block_id, operation_id, update_type, qty_added, operator)
               VALUES (?, ?, 'qty_update', ?, ?)""",
            (block_id, op["id"], qty_add, operator)
        )

        # Queue writeback to ProShop
        conn.execute(
            """INSERT INTO writeback_queue (operation_id, field, value)
               VALUES (?, 'perOpQtyComplete', ?)""",
            (op["id"], str(new_qty))
        )

        conn.commit()
        conn.close()

        return jsonify({
            "qty_complete": new_qty,
            "qty_required": op["qty_required"],
            "progress": min(100, int(new_qty / max(1, op["qty_required"]) * 100)),
        })
    except Exception as e:
        return _error_response(e)


@app.route("/api/blocks/<int:block_id>/complete", methods=["POST"])
def api_complete_block(block_id):
    """Operator marks a block complete."""
    try:
        data = request.get_json() or {}
        operator = data.get("operator", "")
        conn = get_db()

        block = conn.execute(
            "SELECT * FROM schedule_blocks WHERE id=?", (block_id,)
        ).fetchone()
        if not block:
            conn.close()
            return jsonify({"error": "Block not found"}), 404

        old_status = block["status"]

        # Update block
        conn.execute(
            "UPDATE schedule_blocks SET status='complete', updated_at=datetime('now') WHERE id=?",
            (block_id,)
        )

        # Update operation
        conn.execute(
            "UPDATE operations SET is_complete=1 WHERE id=?",
            (block["operation_id"],)
        )

        # Log
        conn.execute(
            """INSERT INTO operator_updates
               (block_id, operation_id, update_type, old_status, new_status, operator)
               VALUES (?, ?, 'status_change', ?, 'complete', ?)""",
            (block_id, block["operation_id"], old_status, operator)
        )

        # Queue writeback
        conn.execute(
            """INSERT INTO writeback_queue (operation_id, field, value)
               VALUES (?, 'isOpComplete', 'true')""",
            (block["operation_id"],)
        )

        conn.commit()

        # Count today's completions
        completed_today = conn.execute(
            """SELECT COUNT(*) FROM operator_updates
               WHERE update_type='status_change' AND new_status='complete'
               AND date(created_at)=date('now')"""
        ).fetchone()[0]

        conn.close()

        return jsonify({
            "ok": True,
            "completed_today": completed_today,
        })
    except Exception as e:
        return _error_response(e)


# ── API: Flags ────────────────────────────────────────────────────────────────

@app.route("/api/flags", methods=["GET"])
def api_flags():
    status = request.args.get("status", "open")
    return jsonify(get_flags(status=status))


@app.route("/api/flags", methods=["POST"])
def api_create_flag():
    try:
        data = request.get_json()
        conn = get_db()
        conn.execute(
            """INSERT INTO flags (block_id, operation_id, machine_id, category, description, flagged_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (data.get("block_id"), data.get("operation_id"), data.get("machine_id"),
             data["category"], data["description"], data.get("flagged_by", ""))
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True}), 201
    except Exception as e:
        return _error_response(e)


@app.route("/api/flags/<int:flag_id>/resolve", methods=["POST"])
def api_resolve_flag(flag_id):
    try:
        data = request.get_json() or {}
        conn = get_db()
        conn.execute(
            """UPDATE flags SET status='resolved', resolved_by=?, resolved_at=datetime('now')
               WHERE id=?""",
            (data.get("resolved_by", ""), flag_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return _error_response(e)


# ── API: Suggestions ─────────────────────────────────────────────────────────

@app.route("/api/suggestions")
def api_suggestions():
    try:
        conn = get_db()
        suggestions = get_suggestions(conn)
        conn.close()
        return jsonify(suggestions)
    except Exception as e:
        return _error_response(e)


# ── API: Priorities & Bottleneck ──────────────────────────────────────────────

@app.route("/api/priorities")
def api_priorities():
    """Daily priority report: ranked action list + alerts + bottleneck summary."""
    try:
        conn = get_db()
        priorities = compute_priorities(conn)
        conn.close()
        return jsonify(priorities)
    except Exception as e:
        return _error_response(e)


@app.route("/api/priorities/report")
def api_priorities_report():
    """Text-formatted daily priority report (for display or email)."""
    try:
        conn = get_db()
        priorities = compute_priorities(conn)
        conn.close()
        return format_daily_report(priorities), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as e:
        return _error_response(e)


@app.route("/api/bottleneck")
def api_bottleneck():
    """Aggregate bottleneck analysis: what category is slowing the shop most."""
    try:
        conn = get_db()
        report = generate_bottleneck_report(conn)
        conn.close()
        return jsonify(report)
    except Exception as e:
        return _error_response(e)


@app.route("/api/bottleneck/report")
def api_bottleneck_report():
    """Text-formatted bottleneck report."""
    try:
        conn = get_db()
        report = generate_bottleneck_report(conn)
        conn.close()
        return format_bottleneck_report(report), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as e:
        return _error_response(e)


# ── API: Needs Lists ─────────────────────────────────────────────────────────

@app.route("/api/needs")
def api_needs():
    """Return all incomplete ops grouped by what they need (program, material, tools)."""
    try:
        conn = get_db()
        ops = get_operations(conn, schedulable_only=True)
        op_ids = {o["id"] for o in ops}
        readiness_map = get_readiness(conn, op_ids) if op_ids else {}

        # Also get tool lists for ops that need tools (deduplicated, no blanks)
        tool_map = {}
        for op_id in op_ids:
            tools = conn.execute(
                "SELECT tool_number, tool_description FROM operation_tools WHERE operation_id = ?",
                (op_id,),
            ).fetchall()
            if tools:
                seen = set()
                clean = []
                for t in tools:
                    num = (t["tool_number"] or "").strip()
                    desc = (t["tool_description"] or "").strip()
                    if not num and not desc:
                        continue
                    key = (num, desc)
                    if key not in seen:
                        seen.add(key)
                        clean.append({"tool_number": num, "tool_description": desc})
                if clean:
                    tool_map[op_id] = clean

        conn.close()

        needs_program = []
        needs_material = []
        needs_tools = []
        check_runtimes = []

        RUNTIME_CAP = 80  # hours — flag ops above this for review

        for op in ops:
            r = readiness_map.get(op["id"], {})
            item = {
                "wo_number": op["wo_number"],
                "op_number": op["op_number"],
                "op_name": op.get("op_name", ""),
                "part_number": op.get("part_number", ""),
                "part_name": op.get("part_name", ""),
                "customer": op.get("customer", ""),
                "due_date": op.get("due_date", ""),
                "material_type": op.get("material_type", ""),
                "work_center": op.get("work_center", ""),
                "est_hours": op.get("override_hours") or op.get("est_hours", 0),
            }
            if not r.get("program_ready", False):
                needs_program.append(item)
            if not r.get("material_ready", False):
                mat_item = dict(item)
                raw_detail = r.get("material_detail") or "{}"
                try:
                    detail_obj = json.loads(raw_detail) if isinstance(raw_detail, str) else raw_detail
                except (json.JSONDecodeError, TypeError):
                    detail_obj = {}
                mat_item["material_status"] = detail_obj.get("status", "unknown")
                mat_item["material_po"] = detail_obj.get("po", "")
                mat_item["material_order_status"] = detail_obj.get("order_status", "")
                needs_material.append(mat_item)
            if (not r.get("tools_ready", False)
                    and r.get("program_ready", False)
                    and op.get("work_center", "").upper() != "T2"):
                tools_item = dict(item)
                tools_item["op_id"] = op["id"]
                tools_item["tools"] = tool_map.get(op["id"], [])
                needs_tools.append(tools_item)

            # Flag ops with suspiciously high runtimes
            hours = op.get("override_hours") or op.get("est_hours") or 0
            is_est = op.get("is_estimated", 0)
            if hours > RUNTIME_CAP:
                rt_item = dict(item)
                rt_item["est_hours"] = hours
                rt_item["is_estimated"] = is_est
                rt_item["qty_required"] = op.get("qty_required", 0)
                check_runtimes.append(rt_item)

        return jsonify({
            "needs_program": needs_program,
            "needs_material": needs_material,
            "needs_tools": needs_tools,
            "check_runtimes": check_runtimes,
            "counts": {
                "program": len(needs_program),
                "material": len(needs_material),
                "tools": len(needs_tools),
                "runtimes": len(check_runtimes),
            },
        })
    except Exception as e:
        return _error_response(e)


# ── API: Tool Demand ─────────────────────────────────────────────────────────

@app.route("/api/tool-demand")
def api_tool_demand():
    """Cross-reference tools needed by open ops against kiosk inventory."""
    import sqlite3
    try:
        conn = get_db()

        # Get all unique tools demanded by active, non-hidden, incomplete ops
        rows = conn.execute("""
            SELECT ot.tool_number, ot.tool_description,
                   o.id AS op_id, o.wo_number
            FROM operation_tools ot
            JOIN operations o ON ot.operation_id = o.id
            JOIN work_orders w ON o.wo_number = w.wo_number
            WHERE w.status = 'active'
              AND o.is_complete = 0
              AND COALESCE(w.hidden, 0) = 0
              AND COALESCE(o.hidden, 0) = 0
              AND TRIM(COALESCE(ot.tool_number, '')) != ''
        """).fetchall()
        conn.close()

        # Aggregate by tool_number
        demand = {}  # tool_number -> {description, op_ids set, wo_numbers set}
        for r in rows:
            tn = r["tool_number"].strip()
            if tn not in demand:
                demand[tn] = {
                    "description": (r["tool_description"] or "").strip(),
                    "op_ids": set(),
                    "wo_numbers": set(),
                }
            demand[tn]["op_ids"].add(r["op_id"])
            demand[tn]["wo_numbers"].add(r["wo_number"])

        # Read kiosk inventory (read-only)
        kiosk_available = False
        inventory = {}
        try:
            kiosk_path = config.KIOSK_DB_PATH
            if os.path.exists(kiosk_path):
                kiosk_conn = sqlite3.connect(f"file:{kiosk_path}?mode=ro", uri=True)
                kiosk_conn.row_factory = sqlite3.Row
                inv_rows = kiosk_conn.execute(
                    "SELECT tool_number, tool_description, qty_blue, qty_green, "
                    "min_quantity, last_counted_at FROM tool_inventory"
                ).fetchall()
                kiosk_conn.close()
                for ir in inv_rows:
                    inventory[ir["tool_number"]] = {
                        "qty_available": (ir["qty_blue"] or 0) + (ir["qty_green"] or 0),
                        "min_quantity": ir["min_quantity"],
                        "last_counted_at": ir["last_counted_at"],
                        "inv_description": (ir["tool_description"] or "").strip(),
                    }
                kiosk_available = True
        except Exception as e:
            log.warning("Could not read kiosk DB: %s", e)

        # Build result list
        result = []
        for tn, d in demand.items():
            inv = inventory.get(tn)
            if inv:
                qty = inv["qty_available"]
                min_q = inv["min_quantity"]
                if qty == 0:
                    status = "out_of_stock"
                elif min_q is not None and qty <= min_q:
                    status = "low_stock"
                else:
                    status = "ok"
                result.append({
                    "tool_number": tn,
                    "description": inv["inv_description"] or d["description"],
                    "op_count": len(d["op_ids"]),
                    "wo_numbers": sorted(d["wo_numbers"]),
                    "qty_available": qty,
                    "min_quantity": min_q,
                    "last_counted_at": inv["last_counted_at"],
                    "status": status,
                })
            else:
                result.append({
                    "tool_number": tn,
                    "description": d["description"],
                    "op_count": len(d["op_ids"]),
                    "wo_numbers": sorted(d["wo_numbers"]),
                    "qty_available": None,
                    "min_quantity": None,
                    "last_counted_at": None,
                    "status": "not_in_inventory" if kiosk_available else "unknown",
                })

        # Sort: out_of_stock first, then low_stock, not_in_inventory, unknown, ok last
        priority = {"out_of_stock": 0, "low_stock": 1, "not_in_inventory": 2, "unknown": 3, "ok": 4}
        result.sort(key=lambda x: (priority.get(x["status"], 9), x["tool_number"]))

        return jsonify({
            "tools": result,
            "kiosk_available": kiosk_available,
            "shortage_count": sum(1 for t in result if t["status"] in ("out_of_stock", "low_stock", "not_in_inventory")),
        })
    except Exception as e:
        return _error_response(e)


# ── API: Stats & Sync ────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/sync", methods=["POST"])
def api_trigger_sync():
    try:
        result = sync_engine.full_sync()
        return jsonify(result)
    except Exception as e:
        return _error_response(e)


@app.route("/api/sync/log")
def api_sync_log():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sync_log ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── API: Health ───────────────────────────────────────────────────────────────

@app.route("/api/health")
def api_health():
    health = client.check_health()
    health["uptime_seconds"] = int(time.time() - _start_time)
    health["service"] = "shop-scheduler"
    health["port"] = config.PORT

    # Write heartbeat
    try:
        import os
        heartbeat = {
            "service": "shop-scheduler",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": health["uptime_seconds"],
            "healthy": health.get("api_reachable", False),
        }
        with open(config.HEARTBEAT_PATH, "w") as f:
            json.dump(heartbeat, f)
    except Exception:
        pass

    return jsonify(health)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _urgency_color(due_date_str, status):
    """Return color scheme based on due date urgency."""
    if status == "complete":
        return {"bg": "#166534", "border": "#22c55e", "text": "#dcfce7"}

    if not due_date_str:
        return {"bg": "#1e3a5f", "border": "#3b82f6", "text": "#dbeafe"}

    try:
        due = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
        now = datetime.now()
        days = (due - now).days

        if days < 0:
            return {"bg": "#7f1d1d", "border": "#ef4444", "text": "#fecaca"}  # Past due
        elif days < 3:
            return {"bg": "#7c2d12", "border": "#f97316", "text": "#fed7aa"}  # Due <3 days
        elif days < 7:
            return {"bg": "#713f12", "border": "#eab308", "text": "#fef9c3"}  # Due <7 days
        else:
            return {"bg": "#1e3a5f", "border": "#3b82f6", "text": "#dbeafe"}  # Normal
    except (ValueError, TypeError):
        return {"bg": "#1e3a5f", "border": "#3b82f6", "text": "#dbeafe"}


# ── Main ──────────────────────────────────────────────────────────────────────

def _serve_with_shutdown(app, host, port, channel_timeout=30):
    """Run app under waitress with a /api/shutdown route for graceful stop."""
    import threading
    from waitress import create_server

    shutdown_event = threading.Event()

    @app.route("/api/shutdown", methods=["POST"])
    def _api_shutdown():
        shutdown_event.set()
        return ("shutting down", 200)

    server = create_server(app, host=host, port=port, channel_timeout=channel_timeout)

    def _waiter():
        shutdown_event.wait()
        server.close()

    threading.Thread(target=_waiter, daemon=True).start()
    print(f"Serving on http://{host}:{port} (waitress)", flush=True)
    server.run()


if __name__ == "__main__":
    print(f"Shop Scheduler starting on http://{config.HOST}:{config.PORT}")
    print(f"ProShop API: {config.PROSHOP_GRAPHQL_URL}")

    health = client.check_health()
    if health.get("api_reachable"):
        print(f"API OK - {health.get('active_work_orders', '?')} active WOs")
    else:
        print(f"WARNING: API unreachable - {health.get('error', 'unknown')}")

    # Start background sync
    sync_engine.start_background()

    _serve_with_shutdown(app, config.HOST, config.PORT)
