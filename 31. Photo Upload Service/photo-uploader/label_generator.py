"""Label rendering for the photo-uploader print button.

Mirrors the P30 Chrome extension Canvas-based label generators
(label-generator.js, equipment-, tool-, cots-, box-) using Pillow.
Output spec: 128px tall PNGs at 180 DPI for the Brother PT-P700
(24mm tape). Auto-width for material/equipment/tool/box labels;
fixed 450px (2.5") for COTS labels.

All renderers return a base64-encoded PNG string (no data: prefix),
ready for `POST /api/print-image` on the print service.
"""

import base64
import io
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont

# ── Geometry ────────────────────────────────────────────────────────
DPI = 180
HEIGHT = 128
MARGIN = 6
QR_SIZE = HEIGHT - MARGIN * 2  # 116px square
MAX_TEXT_WIDTH = 400           # auto-width labels wrap text past this
COTS_WIDTH = 450               # fixed 2.5" at 180 DPI
SUPERSAMPLE = 2                # render at 2x and downsample for crisp text


# ── Fonts ───────────────────────────────────────────────────────────
def _font(size, bold=False):
    """Load Arial (Windows) with bold variant; fall back to PIL default."""
    names = ["arialbd.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "Arial.ttf"]
    win_dir = os.environ.get("WINDIR", r"C:\Windows")
    for name in names:
        for base in [os.path.join(win_dir, "Fonts"), r"C:\Windows\Fonts"]:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ── QR helpers ──────────────────────────────────────────────────────
def _qr_image(data, target_px):
    """Render a QR (error correct M) and resize to target_px square."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((target_px, target_px), Image.NEAREST)


# ── Text helpers ────────────────────────────────────────────────────
def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_text(draw, text, font, max_width):
    """Greedy word-wrap. Returns list of lines."""
    words = (text or "").split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if _text_width(draw, test, font) <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _truncate(draw, text, font, max_width):
    if _text_width(draw, text, font) <= max_width:
        return text
    while len(text) > 1:
        text = text[:-1]
        if _text_width(draw, text + "...", font) <= max_width:
            return text + "..."
    return text


def _to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(DPI, DPI))
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── Auto-width labels (material, equipment, tool, box, user) ────────
def _render_auto_width(qr_data, lines):
    """Render an auto-width 128px label with QR + stacked text lines.

    `lines` is a list of dicts: {"text": str, "font": ImageFont, "height": int}.
    Lines are vertically centered as a group to the right of the QR.
    """
    # Use a temp draw context for measurement
    measure_img = Image.new("RGB", (1, 1), "white")
    measure = ImageDraw.Draw(measure_img)

    qr_img = _qr_image(qr_data, QR_SIZE)
    text_left = MARGIN + QR_SIZE + MARGIN

    # Compute width from longest line
    max_text_w = 0
    for ln in lines:
        w = _text_width(measure, ln["text"], ln["font"])
        if w > max_text_w:
            max_text_w = w
    total_w = text_left + max_text_w + MARGIN

    canvas = Image.new("RGB", (total_w, HEIGHT), "white")
    canvas.paste(qr_img, (MARGIN, MARGIN))

    draw = ImageDraw.Draw(canvas)
    total_text_h = sum(ln["height"] for ln in lines)
    y = max(MARGIN, (HEIGHT - total_text_h) // 2)
    for ln in lines:
        draw.text((text_left, y), ln["text"], fill="black", font=ln["font"])
        y += ln["height"]

    return canvas


# ── Public renderers ────────────────────────────────────────────────
def material_label(wo_number, material, part_number=""):
    """Material label for a WO. Mirrors P30 label-generator.js."""
    font_wo = _font(36, bold=True)
    font_material = _font(24)
    font_part = _font(14)

    measure_img = Image.new("RGB", (1, 1), "white")
    measure = ImageDraw.Draw(measure_img)

    material_lines = _wrap_text(measure, material or "Unknown material", font_material, MAX_TEXT_WIDTH)

    lines = [{"text": f"WO {wo_number}", "font": font_wo, "height": 42}]
    for ml in material_lines:
        lines.append({"text": ml, "font": font_material, "height": 30})
    if part_number:
        lines.append({"text": part_number, "font": font_part, "height": 20})

    img = _render_auto_width(f"proshop://wo/{wo_number}", lines)
    return _to_base64(img)


def box_label(wo_number, customer_po, part_number, qty, url=None):
    """Box / shipping label for a WO. Mirrors P30 box-label-generator.js."""
    font_line = _font(24, bold=True)

    measure_img = Image.new("RGB", (1, 1), "white")
    measure = ImageDraw.Draw(measure_img)

    lines = [{"text": f"WO {wo_number}", "font": font_line, "height": 30}]
    if customer_po:
        po_text = f"PO: {customer_po}"
        for pl in _wrap_text(measure, po_text, font_line, MAX_TEXT_WIDTH):
            lines.append({"text": pl, "font": font_line, "height": 30})
    if part_number:
        lines.append({"text": part_number, "font": font_line, "height": 30})
    lines.append({"text": f"Qty: {qty}", "font": font_line, "height": 30})

    qr_data = url or f"proshop://wo/{wo_number}"
    img = _render_auto_width(qr_data, lines)
    return _to_base64(img)


def equipment_label(equipment_number, tool_name, serial_number, url):
    """Equipment label. Mirrors P30 equipment-label-generator.js."""
    font_eq = _font(36, bold=True)
    font_name = _font(24)
    font_serial = _font(14)

    measure_img = Image.new("RGB", (1, 1), "white")
    measure = ImageDraw.Draw(measure_img)
    name_lines = _wrap_text(measure, tool_name or "", font_name, MAX_TEXT_WIDTH)

    lines = [{"text": equipment_number or "", "font": font_eq, "height": 42}]
    for nl in name_lines:
        lines.append({"text": nl, "font": font_name, "height": 30})
    if serial_number:
        lines.append({"text": serial_number, "font": font_serial, "height": 20})

    img = _render_auto_width(url, lines)
    return _to_base64(img)


def tool_label(tool_number, description, location, url):
    """Tool label. Mirrors P30 tool-label-generator.js."""
    font_tool = _font(30, bold=True)
    font_desc = _font(20)
    font_loc = _font(14)

    measure_img = Image.new("RGB", (1, 1), "white")
    measure = ImageDraw.Draw(measure_img)
    desc_lines = _wrap_text(measure, description or "", font_desc, MAX_TEXT_WIDTH)

    lines = [{"text": tool_number or "", "font": font_tool, "height": 36}]
    for dl in desc_lines:
        lines.append({"text": dl, "font": font_desc, "height": 26})
    if location:
        lines.append({"text": location, "font": font_loc, "height": 18})

    img = _render_auto_width(url, lines)
    return _to_base64(img)


def cots_label(cots_id, description, url):
    """COTS label — fixed 450px wide, 2x supersampled for crisp text.
    Mirrors P30 cots-label-generator.js / P17 generate_cots_labels.py."""
    s = SUPERSAMPLE
    qr_img = _qr_image(url, QR_SIZE * s)

    canvas = Image.new("RGB", (COTS_WIDTH * s, HEIGHT * s), "white")
    canvas.paste(qr_img, (MARGIN * s, (HEIGHT * s - QR_SIZE * s) // 2))

    draw = ImageDraw.Draw(canvas)
    font_id = _font(48 * s, bold=True)
    font_desc = _font(28 * s)

    text_x = (MARGIN + QR_SIZE + MARGIN) * s
    text_area_w = canvas.width - text_x - MARGIN * s

    draw.text((text_x, 2 * s), cots_id or "", fill="black", font=font_id)

    desc_lines = _wrap_text(draw, description or "", font_desc, text_area_w)
    if len(desc_lines) > 2:
        desc_lines = desc_lines[:2]
        desc_lines[-1] = _truncate(draw, desc_lines[-1], font_desc, text_area_w)

    desc_y = 56 * s
    line_spacing = 32 * s
    for line in desc_lines:
        draw.text((text_x, desc_y), line, fill="black", font=font_desc)
        desc_y += line_spacing

    out = canvas.resize((COTS_WIDTH, HEIGHT), Image.LANCZOS)
    return _to_base64(out)
