"""
ProShop Message Notifier — Web Server
======================================
Flask app that serves a notification page for all LAN users.
Each user selects their name, then the page polls for new
human-sent ProShop messages and shows a pulsing green disc.
"""

import sys
import time
import json
import threading

from flask import Flask, render_template, jsonify, request
import requests as http_requests

import config

# ── Startup checks ──────────────────────────────────────────────────────────

if not config.CLIENT_SECRET:
    print("ERROR: PROSHOP_CLIENT_SECRET environment variable not set.")
    print("Set it before running: set PROSHOP_CLIENT_SECRET=<your secret>")
    sys.exit(1)

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ── ProShop API Client ──────────────────────────────────────────────────────

_token = None
_token_obtained_at = 0
_token_expires_in = 86400
_token_lock = threading.Lock()


def _ensure_token():
    global _token, _token_obtained_at, _token_expires_in
    now = time.time()
    if _token and now < (_token_obtained_at + _token_expires_in - 300):
        return
    with _token_lock:
        now = time.time()
        if _token and now < (_token_obtained_at + _token_expires_in - 300):
            return
        resp = http_requests.post(config.TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": config.CLIENT_ID,
            "client_secret": config.CLIENT_SECRET,
            "scope": config.SCOPE,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _token = data["access_token"]
        _token_obtained_at = time.time()
        _token_expires_in = data.get("expires_in", 86400)


def _graphql(query, variables=None):
    global _token
    _ensure_token()
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = http_requests.post(config.GRAPHQL_URL, json=payload, headers={
        "Authorization": f"Bearer {_token}",
        "Content-Type": "application/json",
    }, timeout=30)
    if resp.status_code == 401:
        _token = None
        _ensure_token()
        resp = http_requests.post(config.GRAPHQL_URL, json=payload, headers={
            "Authorization": f"Bearer {_token}",
            "Content-Type": "application/json",
        }, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body and not body.get("data"):
        msgs = [e.get("message", str(e)) for e in body["errors"]]
        raise Exception("; ".join(msgs))
    return body


# ── Users ───────────────────────────────────────────────────────────────────

_users_cache = {"data": None, "fetched_at": 0}
USER_CACHE_TTL = 3600


def _get_users():
    now = time.time()
    if _users_cache["data"] and now - _users_cache["fetched_at"] < USER_CACHE_TTL:
        return _users_cache["data"]
    result = _graphql("""
        { users(pageSize: 200) { records { id firstName lastName isActive } } }
    """)
    records = result.get("data", {}).get("users", {}).get("records", [])
    excluded_names = {"system user", "system agent", "system", "api"}
    excluded_ids = {"025", "047", "004"}  # Sam Price, Tim Roddick, Zach Clarke
    users = [
        u for u in records
        if u.get("isActive")
        and u.get("id") not in excluded_ids
        and u.get("firstName", "").lower() not in excluded_names
        and u.get("lastName", "").lower() not in excluded_names
    ]
    users.sort(key=lambda u: u.get("firstName", ""))
    _users_cache["data"] = users
    _users_cache["fetched_at"] = now
    return users


# ── Message Checking ────────────────────────────────────────────────────────

_user_states = {}  # user_id -> {"baseline": int, "last_check": float}

INBOX_QUERY = """
    query ($userId: String!, $filter: UserInboxFilter, $size: Int, $start: Int) {
        user(id: $userId) {
            messages(filter: $filter, pageSize: $size, pageStart: $start) {
                totalRecords
                records {
                    id subject postDate isSystemSent
                    fromPlainText
                    from { firstName lastName }
                }
            }
        }
    }
"""


def _get_inbox(user_id, page_size=1, page_start=0):
    result = _graphql(INBOX_QUERY, {
        "userId": user_id,
        "filter": {"boxType": "INBOX", "showOnlyUnread": True},
        "size": page_size,
        "start": page_start,
    })
    msgs = result.get("data", {}).get("user", {}).get("messages", {})
    return msgs.get("totalRecords", 0), msgs.get("records", [])


def _check_for_new(user_id):
    """Returns (has_new, count, sender, messages_list)."""
    total, _ = _get_inbox(user_id, page_size=1)

    if user_id not in _user_states:
        _user_states[user_id] = {"baseline": total, "last_check": time.time()}
        return False, 0, "", []

    state = _user_states[user_id]
    state["last_check"] = time.time()

    if total > state["baseline"]:
        diff = total - state["baseline"]
        fetch_count = min(diff + 5, 50)
        start = max(0, total - fetch_count)
        _, records = _get_inbox(user_id, page_size=fetch_count, page_start=start)

        human = [m for m in records if not m.get("isSystemSent")]
        if human:
            frm = human[0].get("from") or {}
            first = frm.get("firstName", "")
            last = frm.get("lastName", "")
            sender = f"{first} {last[0]}." if last else first
            simple = [{
                "subject": m.get("subject", ""),
                "from": f"{m.get('from', {}).get('firstName', '')} {m.get('from', {}).get('lastName', '')}".strip(),
            } for m in human]
            return True, len(human), sender, simple

    state["baseline"] = total
    return False, 0, "", []


# ── Heartbeat ───────────────────────────────────────────────────────────────

_start_time = time.time()


def _write_heartbeat(status="ok", error=""):
    try:
        active_users = [
            uid for uid, s in _user_states.items()
            if time.time() - s["last_check"] < 120
        ]
        with open(config.HEARTBEAT_PATH, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "status": status,
                "error": error,
                "active_users": len(active_users),
                "uptime_seconds": int(time.time() - _start_time),
            }, f)
    except Exception:
        pass


def _heartbeat_loop():
    while True:
        _write_heartbeat()
        time.sleep(30)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("notifier.html",
                           poll_interval=config.POLL_INTERVAL,
                           messages_url=config.MESSAGES_URL)


@app.route("/api/users")
def api_users():
    try:
        return jsonify(_get_users())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/lookup")
def api_users_lookup():
    """Look up a user by name (for Chrome extension user detection)."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name parameter required"}), 400
    try:
        users = _get_users()
        # Try exact "FirstName LastName" match first
        parts = name.split(None, 1)
        for u in users:
            full = f"{u['firstName']} {u['lastName']}"
            if full.lower() == name.lower():
                return jsonify(u)
        # Try first-name-only match if only one word given
        if len(parts) == 1:
            matches = [u for u in users if u["firstName"].lower() == name.lower()]
            if len(matches) == 1:
                return jsonify(matches[0])
        # Try partial match (first name + last initial)
        if len(parts) == 2:
            first, rest = parts
            for u in users:
                if (u["firstName"].lower() == first.lower() and
                        u["lastName"].lower().startswith(rest.rstrip(".").lower())):
                    return jsonify(u)
        return jsonify({"error": f"User not found: {name}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/messages/<user_id>/check")
def api_check(user_id):
    try:
        has_new, count, sender, messages = _check_for_new(user_id)
        return jsonify({
            "has_new": has_new,
            "count": count,
            "sender": sender,
            "messages": messages,
        })
    except Exception as e:
        return jsonify({"error": str(e), "has_new": False, "count": 0}), 500


@app.route("/api/messages/<user_id>/acknowledge", methods=["POST"])
def api_acknowledge(user_id):
    try:
        total, _ = _get_inbox(user_id, page_size=1)
        _user_states[user_id] = {"baseline": total, "last_check": time.time()}
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def api_health():
    try:
        _ensure_token()
        active = [
            uid for uid, s in _user_states.items()
            if time.time() - s["last_check"] < 120
        ]
        return jsonify({
            "status": "ok",
            "token_valid": _token is not None,
            "active_users": len(active),
            "uptime_seconds": int(time.time() - _start_time),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ── Main ────────────────────────────────────────────────────────────────────

def _serve_with_shutdown(app, host, port, channel_timeout=30):
    """Run app under waitress with a /api/shutdown route for graceful stop."""
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
    print(f"ProShop Message Notifier starting on http://{config.HOST}:{config.PORT}")

    # Start heartbeat thread
    hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb_thread.start()

    # Verify API connection
    try:
        _ensure_token()
        print("ProShop API: connected")
    except Exception as e:
        print(f"WARNING: ProShop API error: {e}")

    _serve_with_shutdown(app, config.HOST, config.PORT)
