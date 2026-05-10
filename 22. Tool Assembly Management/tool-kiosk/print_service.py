"""
Label Print Service — Standalone Flask app (port 5002)
======================================================
Runs on the PC with the Brother PT-P700 printer (USB).
The kiosk (on a different PC) calls this service remotely to print labels.

Uses b-PAC SDK (COM automation) to open the .lbx P-touch Editor layout
and fill fields from holder data. Falls back to PNG printing if b-PAC
is unavailable.

Usage:
    python print_service.py
"""

import os
import sys
import io
import time
import base64
import struct
import ctypes
import logging
import subprocess
import threading
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Logging ──────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_DIR = SCRIPT_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "print_service.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("print_service")

# ── Configuration ────────────────────────────────────────────────────────────

HOST = os.environ.get("PRINT_SERVICE_HOST", "0.0.0.0")
PORT = int(os.environ.get("PRINT_SERVICE_PORT", "5002"))
PRINTER_NAME_MATCH = "PT-P700"
LBX_PATH = str(SCRIPT_DIR / "labels" / "RTATOOLSLayout.lbx")
INV_LBX_PATH = str(SCRIPT_DIR / "labels" / "inventory_labels" / "Tool_Library_Label.lbx")
LABELS_DIR = str(SCRIPT_DIR / "labels")

# ── Printer Detection ───────────────────────────────────────────────────────

def find_printer():
    """Find the Brother PT-P700 printer. Returns printer name or None."""
    try:
        import win32print
        for p in win32print.EnumPrinters(2):
            if PRINTER_NAME_MATCH in p[2]:
                return p[2]
    except Exception:
        pass
    return None


# ── b-PAC Printing ──────────────────────────────────────────────────────────

def _try_bpac_print(printer_name, data, copies):
    """Try printing via b-PAC SDK. Returns True on success, False if unavailable."""
    try:
        import pythoncom
        pythoncom.CoInitialize()
        import win32com.client
        doc = win32com.client.Dispatch("bpac.Document")
        # b-PAC COM methods are misdetected as properties by pywin32 late-binding
        for m in ("Open", "Close", "SetPrinter", "GetObject",
                  "StartPrint", "PrintOut", "EndPrint"):
            doc._FlagAsMethod(m)
    except Exception as e:
        log.info("b-PAC COM not available: %s", e)
        return False

    if not os.path.exists(LBX_PATH):
        log.warning("LBX layout not found: %s", LBX_PATH)
        return False

    try:
        if not doc.Open(LBX_PATH):
            log.warning("b-PAC failed to open layout: %s", LBX_PATH)
            return False

        # Set object text fields in the layout
        # Field names match the text/barcode objects in RTATOOLSLayout.lbx:
        #   Barcode7 = holder ID,  Text2 = RTA#,  Text3 = tool#,  Text5 = holder type
        field_map = {
            "Text1": data.get("holder_id", ""),
            "Barcode7": data.get("holder_id", ""),
            "Text2": data.get("rta_number", ""),
            "Text3": data.get("proshop_tool_number", ""),
            "Text5": data.get("holder_type", ""),
        }
        for field_name, value in field_map.items():
            obj = doc.GetObject(field_name)
            if obj:
                obj.Text = str(value)

        doc.SetPrinter(printer_name, False)
        doc.StartPrint("", 0)
        doc.PrintOut(copies, 0)
        doc.EndPrint()

        doc.Close()
        log.info("b-PAC print OK: %s x%d", data.get("holder_id"), copies)
        return True

    except Exception as e:
        log.warning("b-PAC print failed: %s", e)
        try:
            doc.Close()
        except Exception:
            pass
        return False


# ── PNG Fallback Printing ────────────────────────────────────────────────────

def _print_image_gdi(printer_name, pil_image, copies, doc_name="Label"):
    """Print a PIL Image via win32print/GDI. Shared by all label endpoints."""
    import win32ui
    import win32print
    from PIL import Image

    # Pad image width to multiple of 4 — BMP rows must be DWORD-aligned
    pad_w = (pil_image.width + 3) & ~3
    if pad_w != pil_image.width:
        padded = Image.new("RGB", (pad_w, pil_image.height), "white")
        padded.paste(pil_image, (0, 0))
        pil_image = padded

    # Set tape cut length to match content + small margin
    content_mm = (pil_image.width / 180.0) * 25.4
    label_length_mm = content_mm + 6  # 3mm margin each side
    try:
        hprinter = win32print.OpenPrinter(printer_name)
        devmode = win32print.GetPrinter(hprinter, 2)['pDevMode']
        win32print.ClosePrinter(hprinter)
        devmode.PaperSize = 256              # DMPAPER_USER (custom)
        devmode.PaperLength = int(label_length_mm * 10)  # tenths of mm
        devmode.PaperWidth = 240             # 24mm tape
        devmode.Fields |= 0x8 | 0x10        # DM_PAPERLENGTH | DM_PAPERWIDTH
        log.info("Set tape length: %.1fmm (content %.1fmm)", label_length_mm, content_mm)
    except Exception as e:
        devmode = None
        log.warning("Could not set DEVMODE: %s", e)

    for _ in range(copies):
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        if devmode:
            try:
                hdc.ResetDC(devmode)
            except Exception as e:
                log.warning("ResetDC failed: %s", e)
        hdc.StartDoc(doc_name)
        hdc.StartPage()

        dpi_x = hdc.GetDeviceCaps(88)   # LOGPIXELSX
        dpi_y = hdc.GetDeviceCaps(90)   # LOGPIXELSY
        log.info("Printer DPI: %dx%d, image: %dx%d px",
                 dpi_x, dpi_y, pil_image.width, pil_image.height)

        # Scale to match printer DPI (labels designed at 180 DPI)
        scale_x = dpi_x / 180.0
        scale_y = dpi_y / 180.0
        w = int(pil_image.width * scale_x)
        h = int(pil_image.height * scale_y)

        dib = pil_image.convert("RGB").tobytes("raw", "BGR")
        bmi = struct.pack('<IiiHHIIiiII',
                          40,                            # biSize
                          pil_image.width, -pil_image.height,  # negative = top-down
                          1, 24, 0,                      # planes, bpp, compression
                          0, dpi_x, dpi_y, 0, 0)

        gdi32 = ctypes.windll.gdi32
        gdi32.StretchDIBits(
            hdc.GetSafeHdc(),
            0, 0, w, h,                                 # dest
            0, 0, pil_image.width, pil_image.height,     # src
            dib, bmi, 0, 0x00CC0020)                     # SRCCOPY

        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()


def _print_png(printer_name, data, copies):
    """Generate a PNG label and print via win32print/GDI."""
    # Import label generator
    sys.path.insert(0, LABELS_DIR)
    from generate_labels import make_label

    holder_id = data.get("holder_id", "UNKNOWN")
    holder_type = data.get("holder_type", "CAT40 Holder")
    rta_number = data.get("rta_number")

    png_path = make_label(holder_id, description=holder_type,
                          rta_number=rta_number, output_dir=LABELS_DIR)

    from PIL import Image
    img = Image.open(png_path)

    _print_image_gdi(printer_name, img, copies, doc_name=f"Label {holder_id}")
    log.info("PNG print OK: %s x%d on %s", holder_id, copies, printer_name)


# ── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

_start_time = time.time()


@app.route("/api/health")
def api_health():
    """Check if PT-P700 is available, return printer status."""
    printer = find_printer()
    return jsonify({
        "status": "ok" if printer else "printer_offline",
        "printer": printer,
        "printer_available": printer is not None,
        "uptime_seconds": int(time.time() - _start_time),
    })


@app.route("/api/restart", methods=["POST"])
def api_restart():
    """Restart the print service process (for remote management)."""
    log.info("Restart requested via API")

    def _do_restart():
        time.sleep(1.5)  # let the HTTP response return
        subprocess.Popen(
            [sys.executable] + sys.argv,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        os._exit(0)

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"status": "restarting"})


@app.route("/api/print-label", methods=["POST"])
def api_print_label():
    """Print a label for a holder on the Brother PT-P700.

    Request body:
        holder_id:            e.g., "H-0001"
        rta_number:           e.g., "23"
        proshop_tool_number:  e.g., "A61"
        holder_type:          e.g., "CAT40 ER32"
        copies:               default 2
    """
    printer_name = find_printer()
    if not printer_name:
        return jsonify({
            "error": "Brother PT-P700 not found. Is the printer turned on?",
            "code": "PRINTER_OFFLINE",
        }), 503

    body = request.get_json() or {}
    data = {
        "holder_id": body.get("holder_id", "").strip(),
        "rta_number": body.get("rta_number", ""),
        "proshop_tool_number": body.get("proshop_tool_number", ""),
        "holder_type": body.get("holder_type", "CAT40 Holder"),
    }
    copies = int(body.get("copies", 2))

    if not data["holder_id"]:
        return jsonify({"error": "holder_id is required"}), 400

    # Try b-PAC first, fall back to PNG
    method = "bpac"
    try:
        ok = _try_bpac_print(printer_name, data, copies)
    except Exception as e:
        log.warning("b-PAC exception: %s", e)
        ok = False

    if not ok:
        method = "png"
        try:
            _print_png(printer_name, data, copies)
        except Exception as e:
            log.error("PNG print failed: %s", e)
            return jsonify({"error": str(e), "code": "PRINT_FAILED"}), 500

    return jsonify({
        "printed": True,
        "printer": printer_name,
        "copies": copies,
        "holder_id": data["holder_id"],
        "rta_number": data["rta_number"],
        "method": method,
    })


# ── Generic Image Printing ───────────────────────────────────────────────────

@app.route("/api/print-image", methods=["POST"])
def api_print_image():
    """Print a caller-supplied PNG image on the Brother PT-P700.

    Request body:
        image_base64:  base64-encoded PNG data (required)
        copies:        number of copies (default 1)
        label_name:    optional name for logging (e.g. "WO 26-0120")
    """
    printer_name = find_printer()
    if not printer_name:
        return jsonify({
            "error": "Brother PT-P700 not found. Is the printer turned on?",
            "code": "PRINTER_OFFLINE",
        }), 503

    body = request.get_json() or {}
    image_b64 = body.get("image_base64", "")
    copies = int(body.get("copies", 1))
    label_name = body.get("label_name", "generic")

    if not image_b64:
        return jsonify({"error": "image_base64 is required"}), 400

    try:
        from PIL import Image
        raw = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(raw))
    except Exception as e:
        return jsonify({"error": f"Invalid image data: {e}",
                        "code": "BAD_IMAGE"}), 400

    try:
        _print_image_gdi(printer_name, img, copies,
                         doc_name=f"Label {label_name}")
        log.info("Image print OK: %s x%d on %s", label_name, copies, printer_name)
    except Exception as e:
        log.error("Image print failed: %s", e)
        return jsonify({"error": str(e), "code": "PRINT_FAILED"}), 500

    return jsonify({
        "printed": True,
        "printer": printer_name,
        "copies": copies,
        "label_name": label_name,
    })


# ── Inventory Label Printing ─────────────────────────────────────────────────

def _try_bpac_inventory_print(printer_name, data, copies):
    """Print inventory label via b-PAC using Tool_Library_Label.lbx layout."""
    try:
        import pythoncom
        pythoncom.CoInitialize()
        import win32com.client
        doc = win32com.client.Dispatch("bpac.Document")
        for m in ("Open", "Close", "SetPrinter", "GetObject",
                  "StartPrint", "PrintOut", "EndPrint"):
            doc._FlagAsMethod(m)
    except Exception as e:
        log.info("b-PAC COM not available: %s", e)
        return False

    if not os.path.exists(INV_LBX_PATH):
        log.warning("Inventory LBX layout not found: %s", INV_LBX_PATH)
        return False

    try:
        if not doc.Open(INV_LBX_PATH):
            log.warning("b-PAC failed to open inventory layout: %s", INV_LBX_PATH)
            return False

        # Map data to label fields (layout uses COTS field names)
        field_map = {
            "COTS_ID": data.get("tool_number", ""),
            "Description": data.get("description", ""),
            "URL": data.get("proshop_url", ""),
        }
        for field_name, value in field_map.items():
            obj = doc.GetObject(field_name)
            if obj:
                obj.Text = str(value)

        doc.SetPrinter(printer_name, False)
        doc.StartPrint("", 0)
        doc.PrintOut(copies, 0)
        doc.EndPrint()
        doc.Close()
        log.info("b-PAC inventory print OK: %s x%d", data.get("tool_number"), copies)
        return True

    except Exception as e:
        log.warning("b-PAC inventory print failed: %s", e)
        try:
            doc.Close()
        except Exception:
            pass
        return False


@app.route("/api/print-inventory-label", methods=["POST"])
def api_print_inventory_label():
    """Print a drawer/bin label for a cabinet tool.

    Request body:
        tool_number:  e.g., "A61"
        description:  e.g., "1/2 4-Flute End Mill"
        copies:       default 1
    """
    printer_name = find_printer()
    if not printer_name:
        return jsonify({
            "error": "Brother PT-P700 not found. Is the printer turned on?",
            "code": "PRINTER_OFFLINE",
        }), 503

    body = request.get_json() or {}
    tool_number = (body.get("tool_number") or "").strip().upper()
    data = {
        "tool_number": tool_number,
        "description": body.get("description", ""),
        "proshop_url": body.get("proshop_url", ""),
    }
    copies = int(body.get("copies", 1))

    if not tool_number:
        return jsonify({"error": "tool_number is required"}), 400

    # Build ProShop URL if not provided
    if not data["proshop_url"] and tool_number:
        category = tool_number[0]
        data["proshop_url"] = f"https://traxismfg.adionsystems.com/procnc/tools/{category}/{tool_number}"

    try:
        ok = _try_bpac_inventory_print(printer_name, data, copies)
    except Exception as e:
        log.warning("b-PAC inventory exception: %s", e)
        ok = False

    if not ok:
        return jsonify({"error": "b-PAC print failed. Check layout file and printer.",
                        "code": "PRINT_FAILED"}), 500

    return jsonify({
        "printed": True,
        "printer": printer_name,
        "copies": copies,
        "tool_number": tool_number,
    })


# ── Main ─────────────────────────────────────────────────────────────────────

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
    printer = find_printer()
    if printer:
        log.info("Printer found: %s", printer)
    else:
        log.warning("PT-P700 not found — label printing will fail until printer is connected")

    log.info("Label Print Service starting on http://%s:%d", HOST, PORT)
    _serve_with_shutdown(app, HOST, PORT)
