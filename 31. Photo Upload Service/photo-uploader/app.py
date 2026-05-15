"""Photo Upload Service — Flask application.

Receives photos from shop floor tablet, stores locally, queues for
ProShop upload via Selenium (Phase 2).

Port: 5003
"""

import os
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, request, jsonify, render_template, send_from_directory
from PIL import Image, ImageOps

import config
import database
import label_generator
from proshop_client import ProShopClient
from upload_worker import UploadWorker
from purchasing import queue as purchasing_queue
from purchasing import rules as purchasing_rules
from purchasing import vendors as purchasing_vendors
from purchasing import email_draft as purchasing_email

QUOTE_REQUEST_DAILY_CAP = 3  # max drafts per vendor per day

PRINT_SERVICE_URL = "http://10.1.1.242:5002"

# ── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOGS_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("photo-uploader")

# ── App Setup ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024

proshop = ProShopClient()
worker = UploadWorker()


# ── Pages ─────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/queue")
def queue_page():
    photos = database.get_recent_photos(limit=100)
    stats = database.get_queue_stats()
    return render_template("queue.html", photos=photos, stats=stats)


@app.route("/photo/<int:photo_id>")
def photo_edit_page(photo_id):
    photo = database.get_photo(photo_id)
    if not photo:
        return render_template("photo_edit.html", photo=None), 404
    return render_template("photo_edit.html", photo=photo)


@app.route("/api/photos/<int:photo_id>/update", methods=["POST"])
def update_photo(photo_id):
    photo = database.get_photo(photo_id)
    if not photo:
        return jsonify({"error": "photo not found"}), 404
    data = request.get_json(silent=True) or {}
    fields = {}
    for k in ("entity_id", "entity_name", "operation_number", "operation_desc", "note"):
        if k in data:
            fields[k] = (data.get(k) or "").strip()
    fields["reset_status"] = bool(data.get("retry"))
    database.update_photo_fields(photo_id, **fields)
    log.info(f"Photo #{photo_id} edited: {fields}")
    return jsonify({"success": True})


@app.route("/api/photos/<int:photo_id>/delete", methods=["POST"])
def delete_photo(photo_id):
    rel_path = database.delete_photo(photo_id)
    if rel_path is None:
        return jsonify({"error": "photo not found"}), 404
    try:
        full_path = config.DATA_DIR / rel_path
        if full_path.exists():
            full_path.unlink()
    except Exception as e:
        log.warning(f"Photo #{photo_id}: row deleted but file unlink failed: {e}")
    log.info(f"Photo #{photo_id} deleted")
    return jsonify({"success": True})


# ── API: Photo Upload ────────────────────────────────────────────────────

@app.route("/api/photos", methods=["POST"])
def upload_photo():
    """Accept a photo upload with entity metadata.

    Expects multipart form data:
      - photo: JPEG/PNG file
      - entity_type: workorder|tool|equipment|part|cots
      - entity_id: WO number, tool number, etc.
      - entity_name: (optional) display name
      - proshop_url: (optional) URL for Selenium navigation
      - note: (optional) operator note
    """
    if "photo" not in request.files:
        return jsonify({"error": "No photo file provided"}), 400

    photo_file = request.files["photo"]
    if not photo_file.filename:
        return jsonify({"error": "Empty filename"}), 400

    entity_type = request.form.get("entity_type", "").strip().lower()
    entity_id = request.form.get("entity_id", "").strip()
    entity_name = request.form.get("entity_name", "").strip()
    proshop_url = request.form.get("proshop_url", "").strip()
    note = request.form.get("note", "").strip()
    operation_number = request.form.get("operation_number", "").strip()
    operation_desc = request.form.get("operation_desc", "").strip()

    if not entity_type or not entity_id:
        return jsonify({"error": "entity_type and entity_id are required"}), 400

    valid_types = {"workorder", "tool", "equipment", "part", "fixture", "cots", "ncr", "claude"}
    if entity_type not in valid_types:
        return jsonify({"error": f"Invalid entity_type. Must be one of: {', '.join(valid_types)}"}), 400

    try:
        # Read and process image
        img = Image.open(photo_file.stream)
        # Apply EXIF orientation so saved pixels are upright regardless of
        # how the tablet was held when the shot was taken. Pillow doesn't
        # do this automatically and we strip EXIF on save, so without this
        # the worker would later upload a sideways JPEG.
        img = ImageOps.exif_transpose(img)
        img = _resize_image(img)

        # Ensure RGB (strip alpha from PNGs)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Save to filesystem — WOs include operation subfolder
        safe_id = _sanitize_filename(entity_id)
        if entity_type == "workorder" and operation_number:
            safe_op = _sanitize_filename(operation_number)
            photo_dir = config.PHOTOS_DIR / entity_type / safe_id / f"op{safe_op}"
        else:
            photo_dir = config.PHOTOS_DIR / entity_type / safe_id
        photo_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.jpg"
        file_path = photo_dir / filename

        img.save(str(file_path), "JPEG", quality=config.JPEG_QUALITY)
        log.info(f"Photo saved: {file_path} ({os.path.getsize(file_path)} bytes)")

        # Store relative path in DB
        rel_path = str(file_path.relative_to(config.DATA_DIR))

        # Insert into database
        photo_id = database.insert_photo(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            file_path=rel_path,
            note=note,
            proshop_url=proshop_url,
            operation_number=operation_number,
            operation_desc=operation_desc,
        )

        # Claude photos are local-only — mark immediately so worker skips them
        if entity_type == "claude":
            database.update_photo_status(photo_id, "local_only")
        else:
            database.cache_entity(entity_type, entity_id, entity_name, proshop_url)

        return jsonify({
            "success": True,
            "photo_id": photo_id,
            "file_path": rel_path,
            "message": "Photo saved successfully",
        }), 201

    except Exception as e:
        log.error(f"Photo upload failed: {e}", exc_info=True)
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


# ── API: Entity Search ───────────────────────────────────────────────────

@app.route("/api/search")
def search_entities():
    """Search ProShop for entities matching a query.

    Query params:
      - type: workorder|tool|equipment|part|cots
      - q: search text (min 2 chars)
    """
    entity_type = request.args.get("type", "").strip().lower()
    query_text = request.args.get("q", "").strip()

    if not entity_type or not query_text:
        return jsonify({"results": []})

    if len(query_text) < 2:
        return jsonify({"results": []})

    try:
        results = proshop.search_entity(entity_type, query_text)
        return jsonify({"results": results})
    except Exception as e:
        log.error(f"Search failed: {e}", exc_info=True)
        return jsonify({"results": [], "error": str(e)}), 500


# ── API: Work Order Operations ────────────────────────────────────────────

@app.route("/api/operations")
def get_operations():
    """Fetch operations for a work order or part.

    Query params:
      - wo: work order number (e.g., 26-0019)
      - part: part number (e.g., R3V1-10852)
    """
    wo_number = request.args.get("wo", "").strip()
    part_number = request.args.get("part", "").strip()

    if not wo_number and not part_number:
        return jsonify({"ops": []})

    try:
        if wo_number:
            ops = proshop.get_work_order_ops(wo_number)
        else:
            ops = proshop.get_part_ops(part_number)
        return jsonify({"ops": ops})
    except Exception as e:
        log.error(f"Operations fetch failed: {e}", exc_info=True)
        return jsonify({"ops": [], "error": str(e)}), 500


@app.route("/api/part-workorders")
def get_part_workorders():
    """Fetch work orders (current and past) for a part number."""
    part_number = request.args.get("part", "").strip()
    if not part_number:
        return jsonify({"workorders": []})
    try:
        wos = proshop.get_work_orders_for_part(part_number)
        return jsonify({"workorders": wos})
    except Exception as e:
        log.error(f"Part work-order fetch failed: {e}", exc_info=True)
        return jsonify({"workorders": [], "error": str(e)}), 500


# ── API: QR Decode ──────────────────────────────────────────────────────

@app.route("/api/qr-decode", methods=["POST"])
def qr_decode():
    """Decode QR code from an uploaded image, server-side fallback."""
    if "photo" not in request.files:
        return jsonify({"error": "No photo"}), 400

    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        img = Image.open(request.files["photo"].stream)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # Try at multiple scales for small QR codes
        results = []
        for max_dim in [img.size[0], 2000, 1200, 800]:
            w, h = img.size
            if w > max_dim or h > max_dim:
                if w > h:
                    new_w, new_h = max_dim, int(h * max_dim / w)
                else:
                    new_h, new_w = max_dim, int(w * max_dim / h)
                scaled = img.resize((new_w, new_h), Image.LANCZOS)
            else:
                scaled = img
            results = pyzbar_decode(scaled)
            if results:
                break

        if not results:
            return jsonify({"found": False})

        data = results[0].data.decode("utf-8")
        return jsonify({"found": True, "data": data})
    except ImportError:
        return jsonify({"error": "pyzbar not installed"}), 500
    except Exception as e:
        log.error(f"QR decode error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── API: Suggestions ────────────────────────────────────────────────────

SUGGESTIONS_FILE = Path(__file__).parent.parent / "suggestions.md"

@app.route("/api/suggest", methods=["POST"])
def submit_suggestion():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No suggestion text"}), 400

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- [{timestamp}] {text}\n"

    is_new = not SUGGESTIONS_FILE.exists() or SUGGESTIONS_FILE.stat().st_size == 0
    with open(SUGGESTIONS_FILE, "a", encoding="utf-8") as f:
        if is_new:
            f.write("# Photo Upload App — Suggestions\n\n")
        f.write(entry)

    log.info(f"Suggestion saved: {text[:80]}")
    return jsonify({"success": True})


# ── API: Print Label ─────────────────────────────────────────────────────

LABEL_TYPES = {
    "material": "workorder",
    "box": "workorder",
    "tool": "tool",
    "equipment": "equipment",
    "cots": "cots",
}


@app.route("/api/print-label", methods=["POST"])
def print_label():
    """Render a label for an entity and POST it to the Brother print service.

    Body (JSON):
      label_type: material | box | tool | equipment | cots
      entity_id: WO number, tool number, etc.
      box_qty:   (box labels only) operator-entered quantity
      copies:    (optional) defaults to 1
    """
    data = request.get_json(silent=True) or {}
    label_type = (data.get("label_type") or "").strip().lower()
    entity_id = (data.get("entity_id") or "").strip()
    box_qty = (data.get("box_qty") or "").strip()
    copies = int(data.get("copies") or 1)

    if label_type not in LABEL_TYPES:
        return jsonify({"error": f"Unknown label_type '{label_type}'"}), 400
    if not entity_id:
        return jsonify({"error": "entity_id required"}), 400

    entity_type = LABEL_TYPES[label_type]

    try:
        info = proshop.get_label_data(entity_type, entity_id)
    except Exception as e:
        log.error(f"Label data lookup failed: {e}", exc_info=True)
        return jsonify({"error": f"ProShop lookup failed: {e}"}), 502

    try:
        if label_type == "material":
            image_b64 = label_generator.material_label(
                info.get("wo_number") or entity_id,
                info.get("material") or "",
                info.get("part_number") or "",
            )
            label_name = f"Material WO {entity_id}"
        elif label_type == "box":
            if not box_qty:
                return jsonify({"error": "box_qty required for box labels"}), 400
            image_b64 = label_generator.box_label(
                info.get("wo_number") or entity_id,
                info.get("customer_po") or "",
                info.get("part_number") or "",
                box_qty,
                url=f"{config.PROSHOP_BASE_URL}/workorders/{entity_id}",
            )
            label_name = f"Box WO {entity_id}"
        elif label_type == "tool":
            image_b64 = label_generator.tool_label(
                info.get("tool_number") or entity_id,
                info.get("description") or "",
                info.get("location") or "",
                info.get("url") or f"{config.PROSHOP_BASE_URL}/tools/{entity_id}",
            )
            label_name = f"Tool {entity_id}"
        elif label_type == "equipment":
            image_b64 = label_generator.equipment_label(
                info.get("equipment_number") or entity_id,
                info.get("tool_name") or "",
                info.get("serial_number") or "",
                info.get("url") or f"{config.PROSHOP_BASE_URL}/equipment/{entity_id}",
            )
            label_name = f"Equipment {entity_id}"
        elif label_type == "cots":
            image_b64 = label_generator.cots_label(
                info.get("cots_id") or entity_id,
                info.get("description") or "",
                info.get("url") or f"{config.PROSHOP_BASE_URL}/ots/{entity_id}",
            )
            label_name = f"COTS {entity_id}"
    except Exception as e:
        log.error(f"Label render failed: {e}", exc_info=True)
        return jsonify({"error": f"Render failed: {e}"}), 500

    try:
        resp = requests.post(
            f"{PRINT_SERVICE_URL}/api/print-image",
            json={"image_base64": image_b64, "copies": copies, "label_name": label_name},
            timeout=15,
        )
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    except requests.RequestException as e:
        log.error(f"Print service request failed: {e}")
        return jsonify({"error": f"Print service unreachable: {e}"}), 502

    if not resp.ok:
        return jsonify({"error": body.get("error") or f"HTTP {resp.status_code}"}), 502

    log.info(f"Printed {label_name} ({label_type}) — copies={copies}")
    return jsonify({"success": True, "label_name": label_name, **body})


# ── Pages: Approvals ─────────────────────────────────────────────────────

@app.route("/approvals")
def approvals_page():
    pending = purchasing_queue.get_pending(limit=100)
    recent = purchasing_queue.get_recent(limit=30)
    stats = purchasing_queue.stats()
    return render_template("approvals.html",
                           pending=pending, recent=recent, stats=stats)


# ── API: Purchasing Queue ────────────────────────────────────────────────

PURCHASING_ENTITY_TYPES = {"cots", "tool", "part"}


@app.route("/api/queue-order", methods=["POST"])
def queue_order():
    """Receive a Buy-button POST from the P30 extension.

    Body (JSON):
      entity_type: cots | tool | part
      entity_id:   e.g. LUB-116
      qty:         numeric
      unit_cost:   numeric (best-effort scrape; null if not visible)
      vendor:      optional pre-selected vendor name
      brand:       optional brand
      edp:         optional EDP code
    """
    data = request.get_json(silent=True) or {}
    entity_type = (data.get("entity_type") or "").strip().lower()
    entity_id = (data.get("entity_id") or "").strip()
    qty_raw = data.get("qty")
    unit_cost_raw = data.get("unit_cost")

    if entity_type not in PURCHASING_ENTITY_TYPES:
        return jsonify({"error": f"entity_type must be one of {sorted(PURCHASING_ENTITY_TYPES)}"}), 400
    if not entity_id:
        return jsonify({"error": "entity_id required"}), 400
    try:
        qty = float(qty_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "qty must be numeric"}), 400
    unit_cost = None
    if unit_cost_raw not in (None, ""):
        try:
            unit_cost = float(unit_cost_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "unit_cost must be numeric or omitted"}), 400

    vendor = (data.get("vendor") or None)
    brand = (data.get("brand") or None)
    edp = (data.get("edp") or None)

    # All tool requests route through AJ Rodco regardless of what the
    # tool page lists — older tool records may name another vendor but
    # we consolidate sourcing through them.
    if entity_type == "tool" and not vendor:
        vendor = "AJ Rodco"

    # Enrich with MFG + EDP from ProShop tool library — vendors don't
    # recognize internal tool numbers (A268, etc.); they need their own
    # brand + part number to look up the item.
    description = ""
    if entity_type == "tool":
        # Skip approvedBrands entries that are actually the recipient vendor —
        # tool records sometimes have AJ Rodco stored as approvedBrand which
        # produces "Aj Rod 314965" emails to AJ Rodco; we want the actual
        # manufacturer (e.g. "Iscar 314965") or fall through to description.
        info = proshop.get_purchasing_info(entity_type, entity_id, skip_vendor=vendor)
        description = info.get("description") or ""
        if not brand:
            brand = info.get("brand")
        if not edp:
            edp = info.get("edp")

    auto, reason = purchasing_rules.should_auto_approve(entity_id, qty, unit_cost)
    status = "approved" if auto else "pending"
    approver = "auto" if auto else None
    draft_id = None

    # No unit cost? Try to drop a quote-request draft into Outlook for the
    # operator to review/Send. Cap to QUOTE_REQUEST_DAILY_CAP per vendor.
    if not auto and unit_cost is None and vendor:
        ventry, vdomain = purchasing_vendors.find(vendor)
        vendor_email = purchasing_vendors.default_email(ventry)
        if vendor_email:
            todays = purchasing_queue.quote_requests_today(vendor)
            if todays >= QUOTE_REQUEST_DAILY_CAP:
                reason = (f"no unit_cost — daily quote-request cap reached "
                          f"({todays}/{QUOTE_REQUEST_DAILY_CAP} to {vendor})")
            else:
                first_name = purchasing_vendors.first_name_of(vendor_email)
                greeting = f"Hi {first_name}," if first_name else "Hello,"
                # Vendor-facing identifier: prefer MFG + EDP, fall back to
                # description, last resort the internal tool number.
                if brand and edp:
                    ident = f"{brand} {edp}"
                elif description:
                    ident = description
                else:
                    ident = entity_id
                desc_line = (f"\nDescription: {description}\n"
                             if description and brand and edp else "")
                subject = f"Pricing request: {ident} qty {qty:g}"
                body = (f"{greeting}\n\n"
                        f"Could you send current pricing and lead time for "
                        f"{ident}, quantity {qty:g}?\n"
                        f"{desc_line}\n"
                        f"Thanks,\nTom\nTraxis Manufacturing")
                try:
                    draft_id = purchasing_email.create_draft(vendor_email, subject, body)
                    status = "awaiting_quote"
                    reason = (f"quote-request drafted to {vendor_email} "
                              f"(#{todays + 1}/{QUOTE_REQUEST_DAILY_CAP} today to {vendor})")
                except Exception as e:
                    log.error(f"Quote-request draft failed for {vendor}: {e}", exc_info=True)
                    reason = f"no unit_cost; draft attempt failed: {e}"

    order_id = purchasing_queue.insert_order(
        entity_type=entity_type,
        entity_id=entity_id,
        qty=qty,
        unit_cost=unit_cost,
        vendor=vendor,
        brand=brand,
        edp=edp,
        status=status,
        approved_by=approver,
        rule_reason=reason,
    )
    if draft_id:
        purchasing_queue.attach_draft(order_id, draft_id)

    log.info(f"Queued order #{order_id}: {entity_type} {entity_id} qty={qty} "
             f"cost={unit_cost} vendor={vendor} status={status} reason={reason}")
    return jsonify({
        "success": True,
        "order_id": order_id,
        "status": status,
        "auto_approved": auto,
        "draft_id": draft_id,
        "reason": reason,
    }), 201


@app.route("/api/approve/<int:order_id>", methods=["POST"])
def approve_order(order_id):
    data = request.get_json(silent=True) or {}
    approver = (data.get("approver") or "wolfgang").strip()
    if not purchasing_queue.approve(order_id, approver):
        order = purchasing_queue.get(order_id)
        if not order:
            return jsonify({"error": "order not found"}), 404
        return jsonify({"error": f"order is {order['status']}, cannot approve"}), 409
    log.info(f"Order #{order_id} approved by {approver}")
    return jsonify({"success": True, "order_id": order_id})


@app.route("/api/reject/<int:order_id>", methods=["POST"])
def reject_order(order_id):
    data = request.get_json(silent=True) or {}
    approver = (data.get("approver") or "wolfgang").strip()
    reason = (data.get("reason") or "").strip() or None
    if not purchasing_queue.reject(order_id, approver, reason):
        order = purchasing_queue.get(order_id)
        if not order:
            return jsonify({"error": "order not found"}), 404
        return jsonify({"error": f"order is {order['status']}, cannot reject"}), 409
    log.info(f"Order #{order_id} rejected by {approver} ({reason or 'no reason'})")
    return jsonify({"success": True, "order_id": order_id})


# ── API: Health ──────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    """Health check endpoint for Overseer monitoring."""
    stats = database.get_queue_stats()
    api_health = proshop.check_health()
    return jsonify({
        "service": "photo-uploader",
        "status": "ok",
        "queue": stats,
        "worker_alive": worker.is_alive(),
        "proshop_api": api_health,
    })


# ── API: Serve Photos ────────────────────────────────────────────────────

@app.route("/data/photos/<path:filename>")
def serve_photo(filename):
    """Serve stored photos for the queue page thumbnails."""
    return send_from_directory(str(config.PHOTOS_DIR), filename)


# ── Helpers ──────────────────────────────────────────────────────────────

def _resize_image(img):
    """Resize image so longest side is at most MAX_PHOTO_DIMENSION."""
    max_dim = config.MAX_PHOTO_DIMENSION
    w, h = img.size
    if w <= max_dim and h <= max_dim:
        return img
    if w > h:
        new_w = max_dim
        new_h = int(h * max_dim / w)
    else:
        new_h = max_dim
        new_w = int(w * max_dim / h)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _sanitize_filename(name):
    """Make entity ID safe for filesystem use."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


# ── Main ─────────────────────────────────────────────────────────────────

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
    database.init_db()
    purchasing_queue.init_db()
    log.info(f"Photo Upload Service starting on {config.HOST}:{config.PORT}")
    log.info(f"Photos directory: {config.PHOTOS_DIR}")
    log.info(f"Database: {config.DB_PATH}")

    worker.start()

    _serve_with_shutdown(app, config.HOST, config.PORT)
