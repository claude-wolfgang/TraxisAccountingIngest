import sys
import time
from flask import Flask, render_template, jsonify, request

import config
from proshop_client import ProShopClient, GraphQLError
from transaction_log import TransactionLog

# ── Startup checks ────────────────────────────────────────────────────────────
if not config.PROSHOP_CLIENT_SECRET:
    print("ERROR: PROSHOP_CLIENT_SECRET environment variable not set.")
    print("Set it before running: set PROSHOP_CLIENT_SECRET=<your secret>")
    sys.exit(1)

app = Flask(__name__)

client = ProShopClient(
    config.PROSHOP_GRAPHQL_URL,
    config.PROSHOP_TOKEN_URL,
    config.PROSHOP_CLIENT_ID,
    config.PROSHOP_CLIENT_SECRET,
    config.PROSHOP_SCOPE,
)

txn_log = TransactionLog(config.TRANSACTION_LOG_PATH)

_start_time = time.time()

# Cached user list
_users_cache = {"data": None, "fetched_at": 0}
USER_CACHE_TTL = 3600  # 1 hour


def _get_cached_users():
    now = time.time()
    if _users_cache["data"] and now - _users_cache["fetched_at"] < USER_CACHE_TTL:
        return _users_cache["data"]
    users = client.get_users()
    users.sort(key=lambda u: u.get("firstName", ""))
    _users_cache["data"] = users
    _users_cache["fetched_at"] = now
    return users


def _error_response(e):
    """Convert an exception to a JSON error response."""
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
                           inactivity_timeout=config.INACTIVITY_TIMEOUT_SECONDS)

@app.route("/browse")
def browse_page():
    return render_template("browse.html")

@app.route("/edit")
@app.route("/edit/<ots_id>")
def edit_page(ots_id=None):
    item = None
    if ots_id:
        try:
            item = client.get_cots_item(ots_id)
        except Exception:
            pass
    return render_template("edit.html", item=item)

@app.route("/log")
def log_page():
    return render_template("log.html")


# ── API: Users ────────────────────────────────────────────────────────────────

@app.route("/api/users")
def api_users():
    try:
        users = _get_cached_users()
        # Filter to only clocked-in employees
        try:
            clocked_in_ids = client.get_clocked_in_ids()
            if clocked_in_ids:
                users = [u for u in users if u.get("id") in clocked_in_ids]
        except Exception:
            pass  # Fall back to all active users if clock punch fails
        return jsonify(users)
    except Exception as e:
        return _error_response(e)


# ── API: COTS Read ────────────────────────────────────────────────────────────

@app.route("/api/cots")
def api_cots_list():
    try:
        q = request.args.get("q", "").strip()
        page = int(request.args.get("page", 0))
        page_size = int(request.args.get("page_size", 50))
        result = client.get_cots_items(search=q or None, page_size=page_size, page_start=page)
        return jsonify(result)
    except Exception as e:
        return _error_response(e)

@app.route("/api/cots/<ots_id>")
def api_cots_get(ots_id):
    try:
        item = client.get_cots_item(ots_id)
        if not item:
            return jsonify({"error": "Item not found", "ots_id": ots_id}), 404
        return jsonify(item)
    except Exception as e:
        return _error_response(e)


# ── API: Checkout / Checkin ───────────────────────────────────────────────────

@app.route("/api/cots/<ots_id>/checkout", methods=["POST"])
def api_checkout(ots_id):
    try:
        body = request.get_json()
        employee = body.get("employee", "Unknown")
        qty_to_take = int(body.get("quantity", 0))
        ref_type = body.get("ref_type", "")
        ref_number = body.get("ref_number", "")
        if qty_to_take <= 0:
            return jsonify({"error": "Quantity must be positive"}), 400
        if not ref_number:
            return jsonify({"error": "Work Order # is required"}), 400

        item = client.get_cots_item(ots_id)
        if not item:
            return jsonify({"error": "Item not found", "ots_id": ots_id}), 404

        inv_qty = _parse_qty(item.get("inventoryQuantity"))

        # Write to ProShop via leftoverParts (negative qty = checkout)
        updated = client.cots_checkout(ots_id, qty_to_take, ref_number, employee)
        new_inv_qty = _parse_qty(updated.get("inventoryQuantity")) if updated else inv_qty - qty_to_take

        # Log locally too
        txn_log.log(
            employee_name=employee,
            ots_id=ots_id,
            item_name=item.get("aka", ""),
            action="checkout",
            quantity=qty_to_take,
            new_quantity=new_inv_qty,
            ref_type=ref_type,
            ref_number=ref_number,
        )

        min_qty = _parse_qty(item.get("minimumQuantityOnHand"))
        below_minimum = min_qty > 0 and new_inv_qty <= min_qty

        return jsonify({
            "success": True,
            "item": item.get("aka"),
            "previous_quantity": inv_qty,
            "quantity_taken": qty_to_take,
            "new_quantity": new_inv_qty,
            "below_minimum": below_minimum,
            "minimum_quantity": min_qty,
        })
    except Exception as e:
        return _error_response(e)

@app.route("/api/cots/<ots_id>/checkin", methods=["POST"])
def api_checkin(ots_id):
    try:
        body = request.get_json()
        employee = body.get("employee", "Unknown")
        qty_to_return = int(body.get("quantity", 0))
        ref_type = body.get("ref_type", "")
        ref_number = body.get("ref_number", "")
        if qty_to_return <= 0:
            return jsonify({"error": "Quantity must be positive"}), 400
        if not ref_number:
            return jsonify({"error": "WO or PO # is required"}), 400

        item = client.get_cots_item(ots_id)
        if not item:
            return jsonify({"error": "Item not found", "ots_id": ots_id}), 404

        inv_qty = _parse_qty(item.get("inventoryQuantity"))

        # Write to ProShop via leftoverParts (positive qty = return)
        updated = client.cots_checkin(ots_id, qty_to_return, ref_type, ref_number, employee)
        new_inv_qty = _parse_qty(updated.get("inventoryQuantity")) if updated else inv_qty + qty_to_return

        # Log locally too
        txn_log.log(
            employee_name=employee,
            ots_id=ots_id,
            item_name=item.get("aka", ""),
            action="checkin",
            quantity=qty_to_return,
            new_quantity=new_inv_qty,
            ref_type=ref_type,
            ref_number=ref_number,
        )

        return jsonify({
            "success": True,
            "item": item.get("aka"),
            "previous_quantity": inv_qty,
            "quantity_returned": qty_to_return,
            "new_quantity": new_inv_qty,
        })
    except Exception as e:
        return _error_response(e)


# ── API: COTS Create / Update / Delete ────────────────────────────────────────

@app.route("/api/cots", methods=["POST"])
def api_cots_create():
    try:
        data = request.get_json()
        if not data.get("aka"):
            return jsonify({"error": "Item name (aka) is required"}), 400
        if not data.get("type"):
            return jsonify({"error": "Item type is required"}), 400
        result = client.add_cots(data)
        return jsonify(result), 201
    except Exception as e:
        return _error_response(e)

@app.route("/api/cots/<ots_id>", methods=["PUT"])
def api_cots_update(ots_id):
    try:
        data = request.get_json()
        result = client.update_cots(ots_id, data)
        return jsonify(result)
    except Exception as e:
        return _error_response(e)

@app.route("/api/cots/<ots_id>", methods=["DELETE"])
def api_cots_delete(ots_id):
    try:
        client.delete_cots(ots_id)
        return jsonify({"success": True, "deleted": ots_id})
    except Exception as e:
        return _error_response(e)


# ── API: Transactions & Health ────────────────────────────────────────────────

@app.route("/api/transactions")
def api_transactions():
    n = int(request.args.get("n", 50))
    return jsonify(txn_log.get_recent(n))

@app.route("/api/health")
def api_health():
    health = client.check_health()
    health["uptime_seconds"] = int(time.time() - _start_time)
    return jsonify(health)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_qty(value):
    """Parse a quantity value that might be None, str, int, or float."""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0


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
    print(f"COTS Crib Kiosk starting on http://{config.HOST}:{config.PORT}")
    print(f"ProShop API: {config.PROSHOP_GRAPHQL_URL}")
    health = client.check_health()
    if health.get("api_reachable"):
        print(f"API OK — {health.get('total_cots_items', '?')} COTS items")
    else:
        print(f"WARNING: API unreachable — {health.get('error', 'unknown')}")
    _serve_with_shutdown(app, config.HOST, config.PORT)
