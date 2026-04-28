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

from flask import Flask, request, jsonify, render_template, send_from_directory
from PIL import Image

import config
import database
from proshop_client import ProShopClient
from upload_worker import UploadWorker

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

    valid_types = {"workorder", "tool", "equipment", "part", "fixture", "cots"}
    if entity_type not in valid_types:
        return jsonify({"error": f"Invalid entity_type. Must be one of: {', '.join(valid_types)}"}), 400

    try:
        # Read and process image
        img = Image.open(photo_file.stream)
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

        # Cache entity for future lookups
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
    """Fetch operations for a work order.

    Query params:
      - wo: work order number (e.g., 26-0019)
    """
    wo_number = request.args.get("wo", "").strip()
    if not wo_number:
        return jsonify({"ops": []})

    try:
        ops = proshop.get_work_order_ops(wo_number)
        return jsonify({"ops": ops})
    except Exception as e:
        log.error(f"Operations fetch failed: {e}", exc_info=True)
        return jsonify({"ops": [], "error": str(e)}), 500


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

if __name__ == "__main__":
    database.init_db()
    log.info(f"Photo Upload Service starting on {config.HOST}:{config.PORT}")
    log.info(f"Photos directory: {config.PHOTOS_DIR}")
    log.info(f"Database: {config.DB_PATH}")

    worker.start()

    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
