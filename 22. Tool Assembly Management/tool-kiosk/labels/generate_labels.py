"""
Generate QR label images for CAT40 tool holders.

Brother PT-P700, 24mm TZe tape, 180 DPI.
QR code on left, bold ID + description on right, tight fit.

Usage:
    python generate_labels.py              # H-0001 through H-0020
    python generate_labels.py 1 50         # H-0001 through H-0050
    python generate_labels.py 5 5          # Just H-0005
"""

import os
import sys
import qrcode
from PIL import Image, ImageDraw, ImageFont

# ── Label dimensions ─────────────────────────────────────────────────────────
DPI = 180
TAPE_HEIGHT_MM = 24
TAPE_HEIGHT_IN = TAPE_HEIGHT_MM / 25.4
LABEL_H = int(TAPE_HEIGHT_IN * DPI)   # 170 px

MARGIN = 4
QR_SIZE = LABEL_H - MARGIN * 2        # square, fits tape height

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


def make_label(holder_id, description="CAT40 Holder", rta_number=None, output_dir="."):
    """Generate a single label PNG — auto-sized width to content."""
    # QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(holder_id)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.NEAREST)

    # Build description line with RTA if available
    if rta_number:
        desc_line = f"RTA {rta_number} \u00b7 {description}"
    else:
        desc_line = description

    # Measure text to auto-size width
    font_id = get_font(48, bold=True)
    font_desc = get_font(22, bold=False)
    id_bbox = font_id.getbbox(holder_id)
    desc_bbox = font_desc.getbbox(desc_line)
    text_w = max(id_bbox[2] - id_bbox[0], desc_bbox[2] - desc_bbox[0])

    # Total label width: QR + gap + text + margin
    label_w = MARGIN + QR_SIZE + MARGIN + text_w + MARGIN

    # Label canvas
    label = Image.new("RGB", (label_w, LABEL_H), "white")
    draw = ImageDraw.Draw(label)

    # QR on left
    qr_x = MARGIN
    qr_y = (LABEL_H - QR_SIZE) // 2
    label.paste(qr_img, (qr_x, qr_y))

    # Text after QR
    text_x = qr_x + QR_SIZE + MARGIN

    # Holder ID — large bold, vertically centered top half
    draw.text((text_x, MARGIN + 8), holder_id, fill="black", font=font_id)

    # Description + RTA — smaller, below ID
    draw.text((text_x, MARGIN + 62), desc_line, fill="black", font=font_desc)

    # Save
    out_path = os.path.join(output_dir, f"{holder_id}.png")
    label.save(out_path, dpi=(DPI, DPI))
    return out_path


def get_holders_from_db():
    """Read holders with their RTA numbers and holder types from tooling.db."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "..", "data", "tooling.db")
    if not os.path.exists(db_path):
        print(f"ERROR: tooling.db not found at {db_path}")
        return []
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT holder_id, holder_type, rta_number
        FROM holders WHERE status = 'active'
        ORDER BY holder_id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    if "--from-db" in sys.argv:
        holders = get_holders_from_db()
        if not holders:
            print("No active holders found in tooling.db")
            return
        print(f"Generating labels for {len(holders)} holders from tooling.db...")
        for h in holders:
            hid = h["holder_id"]
            desc = h["holder_type"] or "CAT40 Holder"
            rta = h["rta_number"]
            path = make_label(hid, description=desc, rta_number=rta, output_dir=out_dir)
            rta_str = f" (RTA {rta})" if rta else ""
            print(f"  {hid}{rta_str} -> {os.path.basename(path)}")
        print(f"\nDone! {len(holders)} labels generated.")
        return

    start = 1
    end = 20
    if len(sys.argv) >= 3:
        start = int(sys.argv[1])
        end = int(sys.argv[2])
    elif len(sys.argv) == 2:
        end = int(sys.argv[1])

    print(f"Generating labels H-{start:04d} through H-{end:04d}...")

    for i in range(start, end + 1):
        holder_id = f"H-{i:04d}"
        path = make_label(holder_id, output_dir=out_dir)
        print(f"  {holder_id} -> {os.path.basename(path)}")

    print(f"\nDone! {end - start + 1} labels generated.")


if __name__ == "__main__":
    main()
