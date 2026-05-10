"""
Tool Assembly Management Kiosk — Flask Application

Tracks CAT40 holders through their lifecycle: cutter installation,
machine assignment, usage accumulation, cutter replacement, and
cross-machine movement.
"""

import sys
import os
import time
import logging
import threading
from pathlib import Path
import requests as _requests
from flask import Flask, render_template, jsonify, request

import config
import database as db
from proshop_client import ProShopClient, GraphQLError

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("tool_kiosk")

# ── Startup checks ────────────────────────────────────────────────────────────
if not config.PROSHOP_CLIENT_SECRET:
    log.error("PROSHOP_CLIENT_SECRET environment variable not set.")
    log.error("Set it before running: set PROSHOP_CLIENT_SECRET=<your secret>")
    sys.exit(1)

log.info("=" * 60)
log.info("Tool Assembly Management Kiosk starting...")
log.info(f"ProShop API: {config.PROSHOP_GRAPHQL_URL}")
log.info(f"Client ID: {config.PROSHOP_CLIENT_ID}")
log.info(f"Database: {config.TOOLING_DB_PATH}")
log.info("=" * 60)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Route Flask's own logger (app.logger) to the same file handler
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                              datefmt="%Y-%m-%d %H:%M:%S"))
app.logger.addHandler(_file_handler)

client = ProShopClient(
    config.PROSHOP_GRAPHQL_URL,
    config.PROSHOP_TOKEN_URL,
    config.PROSHOP_CLIENT_ID,
    config.PROSHOP_CLIENT_SECRET,
    config.PROSHOP_SCOPE,
)

# Initialize tooling database
db.init_db(config.TOOLING_DB_PATH)

_start_time = time.time()

# Cached user list
_users_cache = {"data": None, "fetched_at": 0}
USER_CACHE_TTL = 3600


def _get_db():
    """Get a database connection for the current request."""
    return db.get_connection(config.TOOLING_DB_PATH)


def _get_cached_users():
    now = time.time()
    if _users_cache["data"] and now - _users_cache["fetched_at"] < USER_CACHE_TTL:
        return _users_cache["data"]
    users = client.get_users()
    users.sort(key=lambda u: u.get("firstName", ""))
    _users_cache["data"] = users
    _users_cache["fetched_at"] = now
    return users


def _build_rta_holder(holder):
    """Build RTA holder string from kiosk holder data.

    E.g., CAT40 ER32 with length 3 → 'ER32 - 3"'
          CAT40 Shrink Fit → 'Shrink Fit'
    """
    ht = (holder.get("holder_type") or "").replace("CAT40 ", "").strip()
    length = holder.get("holder_length")
    if length and ht.startswith("ER"):
        return f'{ht} - {length}"'
    return ht or ""


def _build_rta_collet(holder):
    """Build RTA collet string from kiosk holder data.

    E.g., ER32 holder with 1/2 collet → 'ER32 1/2"'
    """
    ht = (holder.get("holder_type") or "").replace("CAT40 ", "").strip()
    cs = (holder.get("collet_size") or "").strip()
    if not cs:
        return ""
    # For ER collet types, prefix with collet type
    if ht.startswith("ER"):
        collet_type = ht.split()[0]  # "ER32", "ER25", "ER16"
        return f'{collet_type} {cs}'
    return cs


def _ensure_rta(conn, holder_id, assembly):
    """Ensure a permanent ProShop RTA exists for this holder.

    - If the holder already has an RTA: update it with current tool/OOH.
    - If no RTA yet: create one and store the number on the holder permanently.
    - Also stamps the RTA number on the assembly row for history.

    Returns the rta_number (string) or None on failure.
    """
    holder = db.get_holder(conn, holder_id)
    if not holder or not assembly.get("proshop_tool_number"):
        return None

    tool_num = (assembly.get("proshop_tool_number") or "").upper()
    rta_holder = _build_rta_holder(holder)
    ooh = str(assembly["ooh_inches"]) if assembly.get("ooh_inches") else ""
    collet = _build_rta_collet(holder)
    comment = f'{holder_id} - Kiosk-managed'

    existing_rta = holder.get("rta_number")

    try:
        if existing_rta:
            # Update existing RTA with current tool/OOH
            _rta, new_num = client.update_or_recreate_rta(
                existing_rta, tool_num,
                holder_type=rta_holder, ooh=ooh,
                collet=collet, comment=comment,
            )
            # If the number changed (recreate path), update the holder
            if new_num != existing_rta:
                db.set_holder_rta_number(conn, holder_id, new_num)
            # Stamp on assembly for history
            db.set_rta_number(conn, assembly["assembly_id"], new_num)
            return new_num
        else:
            # Create new RTA and store permanently on holder
            rta = client.create_rta(
                tool_number=tool_num,
                holder_type=rta_holder, ooh=ooh,
                collet=collet, comment=comment,
            )
            if rta and rta.get("rtaNumber"):
                rta_num = rta["rtaNumber"]
                db.set_holder_rta_number(conn, holder_id, rta_num)
                db.set_rta_number(conn, assembly["assembly_id"], rta_num)
                log.info(f"RTA #{rta_num} created/updated for {holder_id}")
                return rta_num
            else:
                log.warning(f"RTA creation returned unexpected result for {holder_id}: {rta}")
    except Exception as e:
        log.error(f"RTA creation/update failed for {holder_id}: {e}", exc_info=True)
    return None


def _error_response(e):
    if isinstance(e, GraphQLError):
        return jsonify({"error": str(e), "code": "GRAPHQL_ERROR"}), 422
    if isinstance(e, ConnectionError):
        return jsonify({"error": "ProShop API is unreachable.", "code": "API_DOWN"}), 503
    if isinstance(e, TimeoutError):
        return jsonify({"error": "Request timed out.", "code": "API_TIMEOUT"}), 504
    return jsonify({"error": str(e), "code": "INTERNAL_ERROR"}), 500


# ── Page Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def kiosk_page():
    return render_template("kiosk.html",
                           auto_return=config.AUTO_RETURN_SECONDS,
                           inactivity_timeout=config.INACTIVITY_TIMEOUT_SECONDS,
                           machines=config.MACHINES,
                           print_service_url=config.PRINT_SERVICE_URL)

@app.route("/machine/<machine_id>")
def machine_page(machine_id):
    return render_template("machine.html",
                           machine_id=machine_id,
                           machines=config.MACHINES)

@app.route("/touch-test")
def touch_test_page():
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Touch Test</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }
  h1 { text-align: center; }
  #log { font-size: 1.2rem; padding: 16px; max-height: 60vh; overflow-y: auto; background: #fff; border-radius: 12px; border: 2px solid #e2e8f0; }
  .entry { padding: 6px 0; border-bottom: 1px solid #f1f5f9; }
  .touch { color: #16a34a; font-weight: 700; }
  .mouse { color: #2563eb; font-weight: 700; }
  .click { color: #7c3aed; font-weight: 700; }
  #target { text-align: center; margin: 20px auto; padding: 40px; font-size: 1.5rem; font-weight: 700;
    background: #fff7ed; border: 3px solid #f97316; border-radius: 16px; max-width: 500px; cursor: pointer;
    user-select: none; }
  #summary { text-align: center; margin: 16px 0; font-size: 1.3rem; }
</style></head><body>
<h1>Touch Diagnostic</h1>
<div id="summary">Tap or click the orange box below</div>
<div id="target">TAP HERE</div>
<div id="log"></div>
<script>
var log = document.getElementById('log');
var counts = { touch: 0, mouse: 0, click: 0 };
function addEntry(type, detail) {
  counts[type]++;
  var d = document.createElement('div');
  d.className = 'entry';
  d.innerHTML = '<span class="' + type + '">' + type.toUpperCase() + '</span> ' + detail;
  log.insertBefore(d, log.firstChild);
  document.getElementById('summary').innerHTML =
    '<span class="touch">Touch: ' + counts.touch + '</span> &nbsp; ' +
    '<span class="mouse">Mouse: ' + counts.mouse + '</span> &nbsp; ' +
    '<span class="click">Click: ' + counts.click + '</span>';
}
var target = document.getElementById('target');
target.addEventListener('touchstart', function(e) {
  var t = e.touches[0];
  addEntry('touch', 'touchstart @ (' + Math.round(t.clientX) + ',' + Math.round(t.clientY) + ')');
});
target.addEventListener('touchend', function(e) {
  addEntry('touch', 'touchend');
});
target.addEventListener('mousedown', function(e) {
  addEntry('mouse', 'mousedown @ (' + e.clientX + ',' + e.clientY + ')');
});
target.addEventListener('click', function(e) {
  addEntry('click', 'click @ (' + e.clientX + ',' + e.clientY + ')');
});
// Also listen on document for any touch anywhere
document.addEventListener('touchstart', function(e) {
  if (e.target !== target) {
    var t = e.touches[0];
    addEntry('touch', 'touchstart (outside box) @ (' + Math.round(t.clientX) + ',' + Math.round(t.clientY) + ')');
  }
}, true);
</script></body></html>"""

@app.route("/log")
def log_page():
    return render_template("log.html")


# ── API: Users ────────────────────────────────────────────────────────────────

@app.route("/api/users")
def api_users():
    try:
        users = _get_cached_users()
        try:
            clocked_in_ids = client.get_clocked_in_ids()
            if clocked_in_ids:
                users = [u for u in users if u.get("id") in clocked_in_ids]
            else:
                app.logger.warning("get_clocked_in_ids returned empty — showing all users")
        except Exception as e:
            app.logger.warning("Clock-in filter failed: %s — showing all users", e)
        return jsonify(users)
    except Exception as e:
        return _error_response(e)


# ── API: Machines ─────────────────────────────────────────────────────────────

@app.route("/api/machines")
def api_machines():
    """List all machines with their config."""
    machines = []
    for mid, info in config.MACHINES.items():
        machines.append({
            "id": mid,
            "name": info["name"],
            "type": info["type"],
            "enabled": info["enabled"],
            "proshop_pot_id": info["proshop_pot_id"],
        })
    return jsonify(machines)


# ── API: Holders ──────────────────────────────────────────────────────────────

@app.route("/api/holders")
def api_list_holders():
    """List all active holders."""
    conn = _get_db()
    try:
        status = request.args.get("status", "active")
        holders = db.list_holders(conn, status=status)
        return jsonify(holders)
    finally:
        conn.close()


@app.route("/api/holders/<holder_id>")
def api_get_holder(holder_id):
    """Get full holder detail including assembly, assignment, usage."""
    conn = _get_db()
    try:
        detail = db.get_holder_detail(conn, holder_id)
        if not detail:
            return jsonify({"error": "Holder not found", "holder_id": holder_id}), 404
        return jsonify(detail)
    finally:
        conn.close()


@app.route("/api/holders", methods=["POST"])
def api_register_holder():
    """Register a new holder."""
    conn = _get_db()
    try:
        body = request.get_json()
        holder_id = body.get("holder_id", "").strip().upper()
        if not holder_id:
            return jsonify({"error": "holder_id is required"}), 400

        existing = db.get_holder(conn, holder_id)
        if existing:
            return jsonify({"error": f"Holder {holder_id} already exists"}), 409

        holder_length = body.get("holder_length")
        if holder_length is not None:
            try:
                holder_length = int(holder_length)
            except (ValueError, TypeError):
                holder_length = None

        holder = db.register_holder(
            conn,
            holder_id=holder_id,
            holder_type=body.get("holder_type", ""),
            collet_size=body.get("collet_size", ""),
            holder_length=holder_length,
            serial_number=body.get("serial_number", "").strip(),
            default_tool=body.get("default_tool"),
            notes=body.get("notes", ""),
            employee=body.get("employee", ""),
        )
        return jsonify(holder), 201
    finally:
        conn.close()


# ── API: Combined Register RTA ────────────────────────────────────────────────

@app.route("/api/register-rta", methods=["POST"])
def api_register_rta():
    """Register a new holder + install cutter + create ProShop RTA in one step.

    Auto-assigns the next H# and RTA#.  Returns holder_id, rta_number, assembly.
    """
    conn = _get_db()
    try:
        body = request.get_json()
        employee = body.get("employee", "")

        # 1. Auto-assign next holder ID
        holder_id = db.next_holder_id(conn)

        # 2. Register holder
        holder_length = body.get("holder_length")
        if holder_length is not None:
            try:
                holder_length = int(holder_length)
            except (ValueError, TypeError):
                holder_length = None

        db.register_holder(
            conn,
            holder_id=holder_id,
            holder_type=body.get("holder_type", ""),
            collet_size=body.get("collet_size", ""),
            holder_length=holder_length,
            serial_number=body.get("serial_number", "").strip(),
            notes=body.get("notes", ""),
            employee=employee,
        )

        # 3. Install cutter
        tool_num = body.get("proshop_tool_number", "").strip().upper()
        tool_desc = body.get("tool_description", "")
        ooh = body.get("ooh_inches")
        if ooh is not None:
            try:
                ooh = float(ooh)
            except (ValueError, TypeError):
                ooh = None

        assembly = db.install_cutter(
            conn,
            holder_id=holder_id,
            proshop_tool_number=tool_num,
            tool_description=tool_desc,
            ooh_inches=ooh,
            employee=employee,
        )

        # 4. Create RTA in ProShop
        holder = db.get_holder(conn, holder_id)
        rta_number = None
        if tool_num:
            rta_holder = _build_rta_holder(holder)
            rta_collet = _build_rta_collet(holder)
            ooh_str = str(ooh) if ooh else ""
            comment = f"{holder_id} - Kiosk-managed"
            try:
                rta = client.create_rta(
                    tool_number=tool_num,
                    holder_type=rta_holder,
                    ooh=ooh_str,
                    collet=rta_collet,
                    comment=comment,
                )
                if rta and rta.get("rtaNumber"):
                    rta_number = rta["rtaNumber"]
                    log.info(f"RTA #{rta_number} created for {holder_id}")
                else:
                    log.warning(f"RTA creation returned unexpected result for {holder_id}: {rta}")
            except Exception as e:
                log.error(f"RTA creation failed for {holder_id}: {e}", exc_info=True)

        # 5. Store RTA# on holder and assembly
        if rta_number:
            db.set_holder_rta_number(conn, holder_id, rta_number)
            db.set_rta_number(conn, assembly["assembly_id"], rta_number)

        return jsonify({
            "holder_id": holder_id,
            "rta_number": rta_number,
            "assembly": assembly,
            "holder": db.get_holder(conn, holder_id),
        }), 201
    except Exception as e:
        return _error_response(e)
    finally:
        conn.close()


# ── API: Holder Search ───────────────────────────────────────────────────────

@app.route("/api/holders/search")
def api_search_holders():
    """Search holders by serial number or holder ID substring."""
    conn = _get_db()
    try:
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify([])
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT * FROM holders
               WHERE status = 'active'
                 AND (holder_id LIKE ? OR serial_number LIKE ? OR rta_number LIKE ?)
               ORDER BY holder_id LIMIT 20""",
            (like, like, like),
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


# ── API: Tool Lookup ─────────────────────────────────────────────────────────

@app.route("/api/tools/<tool_number>")
def api_tool_lookup(tool_number):
    """Look up a ProShop tool by tool number."""
    try:
        tool = client.get_tool_by_number(tool_number.strip().upper())
        if not tool:
            return jsonify({"error": "Tool not found"}), 404
        return jsonify(tool)
    except Exception as e:
        return _error_response(e)


# ── API: Assemblies (cutter install/replace) ──────────────────────────────────

@app.route("/api/holders/<holder_id>/install", methods=["POST"])
def api_install_cutter(holder_id):
    """Install a cutter into a holder. Retires the current cutter if one exists."""
    conn = _get_db()
    try:
        holder = db.get_holder(conn, holder_id)
        if not holder:
            return jsonify({"error": "Holder not found"}), 404

        body = request.get_json()
        employee = body.get("employee", "")

        # Retire existing cutter if one is active
        current = db.get_active_assembly(conn, holder_id)
        if current:
            reason = body.get("retire_reason", "replaced")
            db.retire_cutter(conn, current["assembly_id"], reason=reason,
                             employee=employee)

        assembly = db.install_cutter(
            conn,
            holder_id=holder_id,
            proshop_tool_number=body.get("proshop_tool_number", "").strip().upper(),
            tool_description=body.get("tool_description", ""),
            ooh_inches=body.get("ooh_inches"),
            employee=employee,
        )
        return jsonify(assembly), 201
    finally:
        conn.close()


@app.route("/api/holders/<holder_id>/replace", methods=["POST"])
def api_replace_cutter(holder_id):
    """Replace cutter: retire old, install new, zero ProShop wear if assigned."""
    conn = _get_db()
    try:
        holder = db.get_holder(conn, holder_id)
        if not holder:
            return jsonify({"error": "Holder not found"}), 404

        body = request.get_json()
        employee = body.get("employee", "")
        reason = body.get("retire_reason", "worn")

        # Retire current cutter
        current = db.get_active_assembly(conn, holder_id)
        old_assembly = None
        if current:
            old_assembly = db.retire_cutter(conn, current["assembly_id"],
                                            reason=reason, employee=employee)
            # Retire 1 unit from ProShop tool inventory
            old_tool_num = (current.get("proshop_tool_number") or "").strip().upper()
            if old_tool_num:
                try:
                    client.retire_tool_qty(old_tool_num, qty=1)
                except Exception as e:
                    print(f"[WARN] Could not retire tool {old_tool_num} from ProShop inventory: {e}")

        # Install new cutter
        tool_num = body.get("proshop_tool_number",
                            current["proshop_tool_number"] if current else "")
        new_assembly = db.install_cutter(
            conn,
            holder_id=holder_id,
            proshop_tool_number=tool_num.strip().upper() if tool_num else "",
            tool_description=body.get("tool_description",
                                      current["tool_description"] if current else ""),
            ooh_inches=body.get("ooh_inches",
                                current["ooh_inches"] if current else None),
            employee=employee,
        )

        # Create new RTA and update ProShop pocket if holder is assigned
        proshop_synced = False
        rta_number = None
        assignment = db.get_active_assignment(conn, holder_id)
        if assignment:
            machine_info = config.MACHINES.get(assignment["machine_id"], {})
            pot_id = machine_info.get("proshop_pot_id")
            if pot_id:
                rta_number = _ensure_rta(conn, holder_id, new_assembly)
                try:
                    tool_num = (new_assembly.get("proshop_tool_number") or "").upper()
                    pocket_data = {
                        "tool": tool_num,
                        "toolWear": "0",
                        "toolLifeNow": "0",
                    }
                    if new_assembly.get("ooh_inches"):
                        pocket_data["outOfHolder"] = new_assembly["ooh_inches"]
                    if rta_number:
                        pocket_data["glot"] = rta_number
                    else:
                        pocket_data["holder"] = holder_id
                    client.update_work_cell_pocket(pot_id,
                                                   assignment["pocket_number"],
                                                   pocket_data)
                    proshop_synced = True
                except Exception:
                    pass

        return jsonify({
            "old_assembly": old_assembly,
            "new_assembly": new_assembly,
            "proshop_synced": proshop_synced,
            "rta_number": rta_number,
        }), 201
    finally:
        conn.close()


@app.route("/api/holders/<holder_id>/history")
def api_holder_history(holder_id):
    """Get assembly and assignment history for a holder."""
    conn = _get_db()
    try:
        return jsonify({
            "assemblies": db.get_assembly_history(conn, holder_id),
            "assignments": db.get_assignment_history(conn, holder_id),
        })
    finally:
        conn.close()


# ── API: Machine Assignments ──────────────────────────────────────────────────

@app.route("/api/machines/<machine_id>/pockets")
def api_machine_pockets(machine_id):
    """Get all active pocket assignments for a machine."""
    conn = _get_db()
    try:
        pockets = db.get_machine_pockets(conn, machine_id)
        return jsonify(pockets)
    finally:
        conn.close()


@app.route("/api/holders/<holder_id>/assign", methods=["POST"])
def api_assign_holder(holder_id):
    """Assign a holder to a machine pocket, optionally syncing to ProShop."""
    conn = _get_db()
    try:
        holder = db.get_holder(conn, holder_id)
        if not holder:
            return jsonify({"error": "Holder not found"}), 404

        body = request.get_json()
        machine_id = body.get("machine_id", "")
        pocket_number = body.get("pocket_number")
        employee = body.get("employee", "")
        work_order = body.get("work_order")

        if not machine_id or pocket_number is None:
            return jsonify({"error": "machine_id and pocket_number required"}), 400

        # Close any existing assignment for this holder
        current = db.get_active_assignment(conn, holder_id)
        if current:
            db.remove_from_machine(conn, current["assignment_id"], employee=employee)
            # Close usage segment on old machine
            seg = db.get_open_segment(conn, holder_id, current["machine_id"])
            if seg:
                db.close_usage_segment(conn, seg["segment_id"])

        # Create new assignment
        assignment = db.assign_to_machine(
            conn, holder_id, machine_id, pocket_number,
            work_order=work_order, employee=employee,
        )

        # Open usage segment
        assembly = db.get_active_assembly(conn, holder_id)
        assembly_id = assembly["assembly_id"] if assembly else None
        db.open_usage_segment(conn, holder_id, assembly_id, machine_id,
                              work_order=work_order)

        # Create RTA and sync to ProShop
        proshop_synced = False
        rta_number = None
        machine_info = config.MACHINES.get(machine_id, {})
        pot_id = machine_info.get("proshop_pot_id")
        if pot_id and assembly:
            rta_number = _ensure_rta(conn, holder_id, assembly)
            try:
                tool_num = (assembly.get("proshop_tool_number") or "").upper()
                pocket_data = {"tool": tool_num}
                if assembly.get("ooh_inches"):
                    pocket_data["outOfHolder"] = assembly["ooh_inches"]
                if rta_number:
                    pocket_data["glot"] = rta_number
                else:
                    pocket_data["holder"] = holder_id
                client.update_work_cell_pocket(pot_id, pocket_number, pocket_data)
                proshop_synced = True
            except Exception:
                pass

        return jsonify({
            "assignment": assignment,
            "proshop_synced": proshop_synced,
            "rta_number": rta_number,
        }), 201
    finally:
        conn.close()


@app.route("/api/holders/<holder_id>/remove", methods=["POST"])
def api_remove_holder(holder_id):
    """Remove a holder from its current machine pocket."""
    conn = _get_db()
    try:
        body = request.get_json()
        employee = body.get("employee", "")

        assignment = db.get_active_assignment(conn, holder_id)
        if not assignment:
            return jsonify({"error": "Holder is not assigned to any machine"}), 400

        db.remove_from_machine(conn, assignment["assignment_id"], employee=employee)

        # Close usage segment
        seg = db.get_open_segment(conn, holder_id, assignment["machine_id"])
        if seg:
            db.close_usage_segment(conn, seg["segment_id"])

        # Clear ProShop pocket
        proshop_synced = False
        machine_info = config.MACHINES.get(assignment["machine_id"], {})
        pot_id = machine_info.get("proshop_pot_id")
        if pot_id:
            try:
                client.clear_work_cell_pocket(pot_id, assignment["pocket_number"])
                proshop_synced = True
            except Exception:
                pass

        return jsonify({
            "removed": True,
            "assignment": db.get_assignment(conn, assignment["assignment_id"]),
            "proshop_synced": proshop_synced,
        })
    finally:
        conn.close()


@app.route("/api/holders/<holder_id>/move", methods=["POST"])
def api_move_holder(holder_id):
    """Move a holder from current machine to a new machine+pocket."""
    conn = _get_db()
    try:
        holder = db.get_holder(conn, holder_id)
        if not holder:
            return jsonify({"error": "Holder not found"}), 404

        body = request.get_json()
        new_machine_id = body.get("machine_id", "")
        new_pocket = body.get("pocket_number")
        employee = body.get("employee", "")
        work_order = body.get("work_order")

        if not new_machine_id or new_pocket is None:
            return jsonify({"error": "machine_id and pocket_number required"}), 400

        old_assignment = db.get_active_assignment(conn, holder_id)
        assembly = db.get_active_assembly(conn, holder_id)

        # Close old assignment + usage segment
        old_proshop_synced = False
        if old_assignment:
            db.remove_from_machine(conn, old_assignment["assignment_id"],
                                   employee=employee)
            seg = db.get_open_segment(conn, holder_id, old_assignment["machine_id"])
            if seg:
                db.close_usage_segment(conn, seg["segment_id"])
            # Clear old ProShop pocket
            old_info = config.MACHINES.get(old_assignment["machine_id"], {})
            old_pot = old_info.get("proshop_pot_id")
            if old_pot:
                try:
                    client.clear_work_cell_pocket(old_pot,
                                                  old_assignment["pocket_number"])
                    old_proshop_synced = True
                except Exception:
                    pass

        # Create new assignment + usage segment
        new_assignment = db.assign_to_machine(
            conn, holder_id, new_machine_id, new_pocket,
            work_order=work_order, employee=employee,
        )
        assembly_id = assembly["assembly_id"] if assembly else None
        db.open_usage_segment(conn, holder_id, assembly_id, new_machine_id,
                              work_order=work_order)

        # Sync new ProShop pocket (reuse existing RTA)
        new_proshop_synced = False
        rta_number = None
        new_info = config.MACHINES.get(new_machine_id, {})
        new_pot = new_info.get("proshop_pot_id")
        if new_pot and assembly:
            rta_number = _ensure_rta(conn, holder_id, assembly)
            try:
                tool_num = (assembly.get("proshop_tool_number") or "").upper()
                pocket_data = {"tool": tool_num}
                if assembly.get("ooh_inches"):
                    pocket_data["outOfHolder"] = assembly["ooh_inches"]
                if rta_number:
                    pocket_data["glot"] = rta_number
                else:
                    pocket_data["holder"] = holder_id
                client.update_work_cell_pocket(new_pot, new_pocket, pocket_data)
                new_proshop_synced = True
            except Exception:
                pass

        db.log_activity(conn, "move_holder", holder_id=holder_id,
                        machine_id=new_machine_id, pocket_number=new_pocket,
                        employee=employee,
                        details={
                            "from_machine": old_assignment["machine_id"] if old_assignment else None,
                            "from_pocket": old_assignment["pocket_number"] if old_assignment else None,
                            "to_machine": new_machine_id,
                            "to_pocket": new_pocket,
                        })
        conn.commit()

        return jsonify({
            "old_assignment": db.get_assignment(conn, old_assignment["assignment_id"]) if old_assignment else None,
            "new_assignment": new_assignment,
            "old_proshop_synced": old_proshop_synced,
            "new_proshop_synced": new_proshop_synced,
        }), 201
    finally:
        conn.close()


# ── API: Job Setup Diff ───────────────────────────────────────────────────────

@app.route("/api/machines/<machine_id>/setup-diff")
def api_setup_diff(machine_id):
    """Compare current pocket assignments vs. required tools for a work order.

    Query params: wo_number, operation_number
    Returns: keep[], load[], remove[] lists
    """
    conn = _get_db()
    try:
        wo_number = request.args.get("wo_number", "")
        op_number = request.args.get("operation_number", "")
        if not wo_number or not op_number:
            return jsonify({"error": "wo_number and operation_number required"}), 400

        # Get required tools from ProShop work order operation
        try:
            required_tools = client.get_sequence_detail_tools(wo_number, op_number)
        except Exception as e:
            return _error_response(e)

        # Get current pocket assignments
        current_pockets = db.get_machine_pockets(conn, machine_id)

        # Build lookup of current tools by ProShop tool number
        current_by_tool = {}
        for p in current_pockets:
            tn = p.get("proshop_tool_number", "")
            if tn:
                current_by_tool[tn.upper()] = p

        # Deduplicate required tools (same physical tool used in multiple sequences)
        seen_tools = {}
        for tool in required_tools:
            tn = (tool.get("toolNumber") or "").strip().upper()
            desc = tool.get("toolDescription", "")
            ooh = tool.get("toolOOH", "")
            seq_desc = tool.get("sequenceDescription", "")
            # For tools without a ProShop number, use OOH as dedup key
            dedup_key = tn if tn else f"_ooh_{ooh}"
            if dedup_key not in seen_tools:
                seen_tools[dedup_key] = {
                    "tool_number": tn,
                    "tool_description": desc or seq_desc,
                    "tool_ooh": ooh,
                    "sequences": [seq_desc] if seq_desc else [],
                }
            else:
                if seq_desc and seq_desc not in seen_tools[dedup_key]["sequences"]:
                    seen_tools[dedup_key]["sequences"].append(seq_desc)

        # Diff
        keep = []
        load = []
        required_tool_numbers = set()

        for dedup_key, tool in seen_tools.items():
            tn = tool["tool_number"]
            required_tool_numbers.add(tn)
            if tn and tn in current_by_tool:
                keep.append({
                    "tool_number": tn,
                    "tool_description": tool["tool_description"],
                    "tool_ooh": tool["tool_ooh"],
                    "current_pocket": current_by_tool[tn]["pocket_number"],
                    "holder_id": current_by_tool[tn]["holder_id"],
                })
            else:
                load.append({
                    "tool_number": tn,
                    "tool_description": tool["tool_description"],
                    "tool_ooh": tool["tool_ooh"],
                })

        remove = []
        for p in current_pockets:
            tn = (p.get("proshop_tool_number") or "").upper()
            if tn and tn not in required_tool_numbers:
                remove.append({
                    "tool_number": tn,
                    "tool_description": p.get("tool_description", ""),
                    "pocket_number": p["pocket_number"],
                    "holder_id": p["holder_id"],
                })

        return jsonify({
            "machine_id": machine_id,
            "wo_number": wo_number,
            "operation_number": op_number,
            "keep": keep,
            "load": load,
            "remove": remove,
            "total_required": len(seen_tools),
            "total_current": len(current_pockets),
        })
    finally:
        conn.close()


@app.route("/api/machines/<machine_id>/work-orders")
def api_machine_work_orders(machine_id):
    """Get work orders scheduled/queued for a machine."""
    machine_info = config.MACHINES.get(machine_id, {})
    pot_id = machine_info.get("proshop_pot_id", "")
    if not pot_id:
        return jsonify({"error": f"No ProShop work cell mapped for {machine_id}"}), 404
    try:
        wos = client.get_work_orders_for_machine(pot_id)
        return jsonify(wos)
    except Exception as e:
        return _error_response(e)


# ── API: ProShop Pocket Sync ─────────────────────────────────────────────────

@app.route("/api/machines/<machine_id>/sync-pockets", methods=["POST"])
def api_sync_pockets(machine_id):
    """Push all current local pocket assignments to ProShop for a machine."""
    conn = _get_db()
    try:
        machine_info = config.MACHINES.get(machine_id, {})
        pot_id = machine_info.get("proshop_pot_id")
        if not pot_id:
            return jsonify({"error": f"No ProShop work cell for {machine_id}"}), 404

        pockets = db.get_machine_pockets(conn, machine_id)
        results = []
        for p in pockets:
            holder_id = p.get("holder_id", "")
            assembly = db.get_active_assembly(conn, holder_id) if holder_id else None
            rta_number = None
            if assembly:
                rta_number = _ensure_rta(conn, holder_id, assembly)

            tool_num = (p.get("proshop_tool_number") or "").upper()
            pocket_data = {"tool": tool_num}
            if p.get("ooh_inches"):
                pocket_data["outOfHolder"] = p["ooh_inches"]
            if rta_number:
                pocket_data["glot"] = rta_number
            else:
                pocket_data["holder"] = holder_id
            try:
                client.update_work_cell_pocket(pot_id, p["pocket_number"],
                                               pocket_data)
                results.append({"pocket": p["pocket_number"], "synced": True,
                                "rta_number": rta_number})
            except Exception as e:
                results.append({"pocket": p["pocket_number"], "synced": False,
                                "error": str(e)})

        return jsonify({"machine_id": machine_id, "results": results})
    finally:
        conn.close()


# ── API: Activity Log ─────────────────────────────────────────────────────────

@app.route("/api/activity")
def api_activity():
    conn = _get_db()
    try:
        limit = int(request.args.get("n", 50))
        holder_id = request.args.get("holder_id")
        entries = db.get_recent_activity(conn, limit=limit, holder_id=holder_id)
        return jsonify(entries)
    finally:
        conn.close()


# ── API: Health ───────────────────────────────────────────────────────────────

@app.route("/api/health")
def api_health():
    health = client.check_health()
    health["uptime_seconds"] = int(time.time() - _start_time)
    # Add holder/assignment counts for overseer dashboard
    try:
        conn = _get_db()
        holders = conn.execute(
            "SELECT COUNT(*) FROM holders WHERE status = 'active'").fetchone()[0]
        assignments = conn.execute(
            "SELECT COUNT(*) FROM assignments WHERE removed_at IS NULL").fetchone()[0]
        conn.close()
        health["active_holders"] = holders
        health["active_assignments"] = assignments
    except Exception:
        pass
    return jsonify(health)


# ── API: Print Proxy ─────────────────────────────────────────────────────────
# Proxies print requests from the kiosk browser through the main app (port 5001)
# to the local print service (port 5002), avoiding cross-origin / firewall issues.

# ── API: Tool Inventory ──────────────────────────────────────────────────────

@app.route("/api/inventory")
def api_list_inventory():
    """List all inventory items with current counts."""
    conn = _get_db()
    try:
        items = db.list_inventory(conn)
        return jsonify(items)
    finally:
        conn.close()


@app.route("/api/inventory/<tool_number>")
def api_get_inventory_item(tool_number):
    """Get a single inventory item + count history."""
    conn = _get_db()
    try:
        import re
        tn = tool_number.strip().upper()
        item = db.get_inventory_item(conn, tn)

        # If not found, extract numeric part and try matching
        if not item:
            m = re.match(r'^([A-Z]*)(\d+)$', tn)
            if m:
                numeric = m.group(2)
                row = conn.execute(
                    """SELECT tool_number FROM tool_inventory
                       WHERE LTRIM(tool_number, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') = ?
                       ORDER BY tool_number LIMIT 1""",
                    (numeric,),
                ).fetchone()
                if row:
                    actual = row[0]
                    if m.group(1) and m.group(1) != actual[:len(actual) - len(numeric)]:
                        # Wrong prefix — suggest the correct one
                        return jsonify({
                            "error": "did_you_mean",
                            "tool_number": tn,
                            "suggestion": actual,
                        }), 404
                    # Number-only input — auto-resolve
                    tn = actual
                    item = db.get_inventory_item(conn, tn)

        if not item:
            return jsonify({"error": "Tool not found in inventory",
                            "tool_number": tool_number}), 404
        item["history"] = db.get_count_history(conn, tn)
        return jsonify(item)
    finally:
        conn.close()


@app.route("/api/inventory/count", methods=["POST"])
def api_record_count():
    """Record an inventory count (quick mode or within session)."""
    conn = _get_db()
    try:
        body = request.get_json()
        tool_number = (body.get("tool_number") or "").strip().upper()
        if not tool_number:
            return jsonify({"error": "tool_number is required"}), 400

        item = db.get_inventory_item(conn, tool_number)
        if not item:
            return jsonify({"error": f"Tool {tool_number} not in inventory"}), 404

        result = db.record_count(
            conn, tool_number,
            blue=int(body.get("qty_blue", 0)),
            green=int(body.get("qty_green", 0)),
            yellow=int(body.get("qty_yellow", 0)),
            red=int(body.get("qty_red", 0)),
            employee=body.get("employee", ""),
            session_id=body.get("session_id"),
        )
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/inventory/items", methods=["POST"])
def api_add_inventory_item():
    """Add a new inventory item."""
    conn = _get_db()
    try:
        body = request.get_json()
        tool_number = (body.get("tool_number") or "").strip().upper()
        if not tool_number:
            return jsonify({"error": "tool_number is required"}), 400

        existing = db.get_inventory_item(conn, tool_number)
        if existing:
            return jsonify({"error": f"Tool {tool_number} already exists"}), 409

        min_qty = body.get("min_quantity")
        if min_qty is not None:
            try:
                min_qty = int(min_qty)
            except (ValueError, TypeError):
                min_qty = None

        item = db.add_inventory_item(
            conn, tool_number,
            description=body.get("tool_description", ""),
            cabinet_location=body.get("cabinet_location", ""),
            min_quantity=min_qty,
            notes=body.get("notes", ""),
        )
        return jsonify(item), 201
    finally:
        conn.close()


@app.route("/api/inventory/session", methods=["POST"])
def api_start_inventory_session():
    """Start a full inventory session."""
    conn = _get_db()
    try:
        body = request.get_json()
        result = db.start_inventory_session(conn, employee=body.get("employee", ""))
        return jsonify(result), 201
    finally:
        conn.close()


@app.route("/api/inventory/session/<session_id>")
def api_get_session_progress(session_id):
    """Get session progress (counted vs remaining)."""
    conn = _get_db()
    try:
        progress = db.get_session_progress(conn, session_id)
        if not progress:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(progress)
    finally:
        conn.close()


@app.route("/api/inventory/session/<session_id>/next")
def api_get_session_next(session_id):
    """Get the next uncounted item in a session."""
    conn = _get_db()
    try:
        item = db.get_session_next_item(conn, session_id)
        if not item:
            return jsonify({"done": True, "message": "All items counted"})
        return jsonify(item)
    finally:
        conn.close()


@app.route("/api/inventory/session/<session_id>/complete", methods=["POST"])
def api_complete_session(session_id):
    """Complete an inventory session."""
    conn = _get_db()
    try:
        db.complete_session(conn, session_id)
        progress = db.get_session_progress(conn, session_id)
        return jsonify(progress)
    finally:
        conn.close()


@app.route("/api/inventory/session/<session_id>/abandon", methods=["POST"])
def api_abandon_session(session_id):
    """Abandon an inventory session — marks it completed and deletes its counts."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE inventory_sessions SET completed_at = datetime('now') WHERE session_id = ?",
            (session_id,))
        conn.execute(
            "DELETE FROM inventory_counts WHERE session_id = ?",
            (session_id,))
        conn.commit()
        return jsonify({"ok": True, "session_id": session_id})
    finally:
        conn.close()


@app.route("/api/inventory/session/open")
def api_get_open_session():
    """Get the most recent unfinished inventory session, if any."""
    conn = _get_db()
    try:
        row = conn.execute(
            """SELECT * FROM inventory_sessions
               WHERE completed_at IS NULL
               ORDER BY started_at DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return jsonify(None)
        session = dict(row)
        # Count how many have been counted so far
        counted = conn.execute(
            "SELECT COUNT(DISTINCT tool_number) FROM inventory_counts WHERE session_id = ?",
            (session["session_id"],)
        ).fetchone()[0]
        session["counted_items"] = counted
        return jsonify(session)
    finally:
        conn.close()


@app.route("/api/inventory/import-from-proshop", methods=["POST"])
def api_import_tools_from_proshop():
    """Fetch all tools from ProShop and import them into tool_inventory.

    Skips tools that already exist. Returns count of imported/skipped.
    """
    conn = _get_db()
    try:
        tools = client.get_all_tools()
        imported = 0
        skipped = 0
        for t in tools:
            tn = (t.get("toolNumber") or "").strip().upper()
            if not tn:
                continue
            # Skip ProShop auto-generated drill catalog (D10001–D10999)
            if tn.startswith("D10") and len(tn) == 6 and tn[1:].isdigit():
                skipped += 1
                continue
            existing = db.get_inventory_item(conn, tn)
            if existing:
                skipped += 1
                continue
            desc = t.get("description") or ""
            db.add_inventory_item(conn, tn, description=desc)
            imported += 1
        return jsonify({
            "imported": imported,
            "skipped": skipped,
            "total_proshop": len(tools),
        })
    except Exception as e:
        return _error_response(e)
    finally:
        conn.close()


_sync_state = {"running": False, "result": None}


def _run_inventory_sync():
    """Background worker for inventory sync."""
    try:
        import inventory_sync
        inventory_sync.DRY_RUN = False
        # Bypass off-hours gate for manual push
        orig = inventory_sync._is_off_hours
        inventory_sync._is_off_hours = lambda: True
        try:
            inventory_sync.sync_inventory()
        finally:
            inventory_sync._is_off_hours = orig

        conn = db.get_connection(config.TOOLING_DB_PATH)
        try:
            synced = conn.execute("SELECT COUNT(*) FROM inventory_sync_log").fetchone()[0]
            last_push = conn.execute("SELECT MAX(pushed_at) FROM inventory_sync_log").fetchone()[0] or "never"
        finally:
            conn.close()
        _sync_state["result"] = {"status": "ok", "synced_tools": synced, "last_push": last_push}
    except Exception as e:
        _sync_state["result"] = {"status": "error", "error": str(e)}
    finally:
        _sync_state["running"] = False


@app.route("/api/inventory/push-to-proshop", methods=["POST"])
def api_push_inventory_to_proshop():
    """Start inventory sync to push cabinet counts to ProShop.

    Runs in a background thread. Poll /api/inventory/sync-status for results.
    """
    if _sync_state["running"]:
        return jsonify({"status": "already_running"})
    _sync_state["running"] = True
    _sync_state["result"] = None
    threading.Thread(target=_run_inventory_sync, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/inventory/sync-status")
def api_sync_status():
    """Check status of inventory sync push."""
    if _sync_state["running"]:
        return jsonify({"status": "running"})
    if _sync_state["result"]:
        return jsonify(_sync_state["result"])
    return jsonify({"status": "idle"})


@app.route("/api/inventory/export-csv")
def api_export_inventory_csv():
    """Export tool_inventory to CSV for label generation."""
    conn = _get_db()
    try:
        items = db.list_inventory(conn)
        import io
        output = io.StringIO()
        output.write("tool_number,description,cabinet_location\n")
        for item in items:
            tn = item["tool_number"].replace('"', '""')
            desc = (item["tool_description"] or "").replace('"', '""')
            loc = (item["cabinet_location"] or "").replace('"', '""')
            output.write(f'"{tn}","{desc}","{loc}"\n')
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=Cabinet_Tools.csv"},
        )
    finally:
        conn.close()


@app.route("/api/proshop-tools-csv")
def api_proshop_tools_csv():
    """Fetch all tools from ProShop and return as CSV.

    Columns: tool_number, description, proshop_url
    """
    try:
        tools = client.get_all_tools()
        base_url = config.PROSHOP_GRAPHQL_URL.rsplit("/api/", 1)[0]
        import io
        output = io.StringIO()
        output.write("TOOL_ID,Description,URL\n")
        for t in tools:
            tn = (t.get("toolNumber") or "").replace('"', '""')
            desc = (t.get("description") or "").replace('"', '""')
            category = tn[0] if tn else ""
            url = f"{base_url}/procnc/tools/{category}/{tn}"
            output.write(f'"{tn}","{desc}","{url}"\n')
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=ProShop_Tools.csv"},
        )
    except Exception as e:
        return _error_response(e)


@app.route("/api/inventory/search")
def api_search_inventory():
    """Search inventory by tool number or description."""
    conn = _get_db()
    try:
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify([])
        items = db.search_inventory(conn, q)
        return jsonify(items)
    finally:
        conn.close()


@app.route("/api/print-inventory-label", methods=["POST"])
def api_print_inventory_label_proxy():
    """Print an inventory label via the print service."""
    try:
        resp = _requests.post(
            config.PRINT_SERVICE_URL + "/api/print-inventory-label",
            json=request.get_json(),
            timeout=10,
        )
        return jsonify(resp.json()), resp.status_code
    except _requests.ConnectionError:
        return jsonify({"error": "Print service unreachable",
                        "code": "PRINT_OFFLINE"}), 503
    except Exception as e:
        return jsonify({"error": str(e), "code": "PRINT_PROXY_ERROR"}), 500


@app.route("/api/print-label", methods=["POST"])
def api_print_label_proxy():
    try:
        resp = _requests.post(
            config.PRINT_SERVICE_URL + "/api/print-label",
            json=request.get_json(),
            timeout=10,
        )
        return jsonify(resp.json()), resp.status_code
    except _requests.ConnectionError:
        return jsonify({"error": "Print service unreachable", "code": "PRINT_OFFLINE"}), 503
    except Exception as e:
        return jsonify({"error": str(e), "code": "PRINT_PROXY_ERROR"}), 500


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
    print(f"Tool Assembly Kiosk starting on http://{config.HOST}:{config.PORT}")
    print(f"ProShop API: {config.PROSHOP_GRAPHQL_URL}")
    print(f"Tooling DB: {config.TOOLING_DB_PATH}")
    health = client.check_health()
    if health.get("api_reachable"):
        print(f"API OK — work cell found: {health.get('work_cell_found')}")
    else:
        print(f"WARNING: API unreachable — {health.get('error', 'unknown')}")
    _serve_with_shutdown(app, config.HOST, config.PORT)
