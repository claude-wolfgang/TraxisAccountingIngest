"""
Generate QR label images for cabinet tool inventory bins.

Brother PT-P700, 24mm TZe tape, 180 DPI.
QR code (left) encoding tool number, bold tool # + description on right.

Usage:
    python generate_inventory_labels.py                     # from Cabinet_Tools.csv
    python generate_inventory_labels.py --from-db           # from tool_inventory table
    python generate_inventory_labels.py --tool A61          # single tool
"""

import os
import sys
import csv
import qrcode
from PIL import Image, ImageDraw, ImageFont

# ── Label dimensions ─────────────────────────────────────────────────────────
DPI = 180
TAPE_HEIGHT_MM = 24
TAPE_HEIGHT_IN = TAPE_HEIGHT_MM / 25.4
LABEL_H = int(TAPE_HEIGHT_IN * DPI)   # 170 px

MARGIN = 4
QR_SIZE = LABEL_H - MARGIN * 2


# ── Fonts ────────────────────────────────────────────────────────────────────
def get_font(size, bold=False):
    names = ["arialbd.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "Arial.ttf"]
    for name in names:
        for base in [
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            r"C:\Windows\Fonts",
        ]:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_text(text, font, max_width, draw):
    """Word-wrap text to fit within max_width pixels. Returns list of lines."""
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def make_inventory_label(tool_number, description="", output_dir="."):
    """Generate a single inventory label PNG — fixed ~2.25" width for 24mm tape."""
    # Target width: ~2.25 inches at 180 DPI = 405 px
    TARGET_W = 400

    # QR code encodes the tool number
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(tool_number)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.NEAREST)

    font_id = get_font(48, bold=True)
    font_desc = get_font(18, bold=False)

    # Text area width = total - QR - margins
    text_area_w = TARGET_W - MARGIN - QR_SIZE - MARGIN - MARGIN

    # Wrap description to fit text area
    _tmp = Image.new("RGB", (1, 1))
    _tmp_draw = ImageDraw.Draw(_tmp)
    desc_lines = wrap_text(description or "", font_desc, text_area_w, _tmp_draw)

    # Label canvas
    label = Image.new("RGB", (TARGET_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)

    # QR on left
    qr_x = MARGIN
    qr_y = (LABEL_H - QR_SIZE) // 2
    label.paste(qr_img, (qr_x, qr_y))

    # Text after QR
    text_x = qr_x + QR_SIZE + MARGIN

    # Tool number — large bold, top of text area
    id_bbox = font_id.getbbox(tool_number)
    id_h = id_bbox[3] - id_bbox[1]
    draw.text((text_x, MARGIN + 2), tool_number, fill="black", font=font_id)

    # Description — wrapped lines below tool number
    desc_y = MARGIN + 2 + id_h + 4
    line_h = 20  # line spacing for 18pt
    for line in desc_lines:
        if desc_y + line_h > LABEL_H - MARGIN:
            break
        draw.text((text_x, desc_y), line, fill="black", font=font_desc)
        desc_y += line_h

    # Save
    safe_name = tool_number.replace("/", "-").replace("\\", "-")
    out_path = os.path.join(output_dir, f"INV-{safe_name}.png")
    label.save(out_path, dpi=(DPI, DPI))
    return out_path


def load_from_csv(csv_path):
    """Load tool list from CSV file."""
    items = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tn = (row.get("tool_number") or "").strip()
            if tn:
                items.append({
                    "tool_number": tn,
                    "description": (row.get("description") or "").strip(),
                    "cabinet_location": (row.get("cabinet_location") or "").strip(),
                })
    return items


def load_from_db():
    """Load tool list from tool_inventory table."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "..", "data", "tooling.db")
    if not os.path.exists(db_path):
        print(f"ERROR: tooling.db not found at {db_path}")
        return []
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT tool_number, tool_description, cabinet_location FROM tool_inventory ORDER BY tool_number"
    ).fetchall()
    conn.close()
    return [{"tool_number": r["tool_number"],
             "description": r["tool_description"],
             "cabinet_location": r["cabinet_location"]} for r in rows]


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "inventory_labels")
    os.makedirs(out_dir, exist_ok=True)

    if "--tool" in sys.argv:
        idx = sys.argv.index("--tool")
        if idx + 1 < len(sys.argv):
            tn = sys.argv[idx + 1].strip().upper()
            path = make_inventory_label(tn, output_dir=out_dir)
            print(f"  {tn} -> {os.path.basename(path)}")
            return

    if "--from-db" in sys.argv:
        items = load_from_db()
        source = "tooling.db"
    else:
        csv_path = os.path.join(script_dir, "Cabinet_Tools.csv")
        if not os.path.exists(csv_path):
            print(f"ERROR: {csv_path} not found")
            return
        items = load_from_csv(csv_path)
        source = "Cabinet_Tools.csv"

    if not items:
        print(f"No tools found in {source}")
        return

    print(f"Generating {len(items)} inventory labels from {source}...")
    for item in items:
        path = make_inventory_label(
            item["tool_number"],
            description=item["description"],
            output_dir=out_dir,
        )
        print(f"  {item['tool_number']} -> {os.path.basename(path)}")

    print(f"\nDone! {len(items)} labels saved to {out_dir}")


if __name__ == "__main__":
    main()
