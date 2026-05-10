"""
Generate QR label PNGs for COTS items.

Brother PT-P700, 24mm TZe tape, 180 DPI.
QR code on left (encodes ProShop URL), bold COTS ID + description on right.
Renders at 2x internally and downsamples for crisp text.

Usage:
    python generate_cots_labels.py THI-1                    # single item from CSV
    python generate_cots_labels.py THI-1 THI-10 FAS-9       # multiple items
    python generate_cots_labels.py --all                    # all 197 items from CSV
    python generate_cots_labels.py --print THI-1            # generate + send to printer
    python generate_cots_labels.py --print --all            # print all items
    python generate_cots_labels.py --print --copies 2 THI-1 # print 2 copies
    python generate_cots_labels.py --api --print THI-219     # pull from ProShop API (not CSV)
"""

import os
import sys
import io
import csv
import base64
import qrcode
from PIL import Image, ImageDraw, ImageFont

# ── Label dimensions (at output 180 DPI) ─────────────────────────────────────
DPI = 180
SUPERSAMPLE = 2                          # render at 2x, downsample for quality
LABEL_H = 128                            # PT-P700 printable height in px
MARGIN = 6
QR_SIZE = LABEL_H - MARGIN * 2           # square QR, fits printable height
MAX_LABEL_WIDTH = 450                    # 2.5" at 180 DPI

PRINT_SERVICE_URL = "http://10.1.1.242:5002"
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "COTS_Labels_All.csv")

# ProShop API config (same creds as cots-kiosk)
PROSHOP_GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
PROSHOP_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
PROSHOP_CLIENT_ID = "E88F-BE23-AC08"
PROSHOP_SCOPE = "ots:rwdp+cots:rwdp+parts:r+users:r"


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


# ── CSV loader ───────────────────────────────────────────────────────────────
def load_cots_csv():
    """Load COTS_Labels_All.csv into a dict keyed by COTS_ID."""
    items = {}
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cots_id = row["COTS_ID"].strip()
            items[cots_id] = {
                "cots_id": cots_id,
                "description": row["Description"].strip(),
                "url": row["URL"].strip(),
            }
    return items


# ── ProShop API lookup ───────────────────────────────────────────────────────
def lookup_cots_api(cots_id):
    """Fetch a COTS item from ProShop API. Returns dict or None."""
    import requests

    secret = os.environ.get("PROSHOP_CLIENT_SECRET")
    if not secret:
        print("Error: PROSHOP_CLIENT_SECRET env var not set")
        return None

    # Get OAuth token
    token_resp = requests.post(PROSHOP_TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": PROSHOP_CLIENT_ID,
        "client_secret": secret,
        "scope": PROSHOP_SCOPE,
    }, timeout=15)
    token_resp.raise_for_status()
    token = token_resp.json()["access_token"]

    # Query the item
    query = """query ($otsId: String!) {
        cotsItem(otsId: $otsId) { otsId number type description }
    }"""
    resp = requests.post(PROSHOP_GRAPHQL_URL, json={
        "query": query,
        "variables": {"otsId": cots_id},
    }, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, timeout=15)
    resp.raise_for_status()
    item = resp.json().get("data", {}).get("cotsItem")
    if not item:
        return None

    item_type = item.get("type", "")
    number = item.get("number", "")
    full_id = f"{item_type}-{number}" if item_type and number else cots_id
    url = f"https://traxismfg.adionsystems.com/procnc/ots/{item_type}/{full_id}"

    return {
        "cots_id": full_id,
        "description": item.get("description", ""),
        "url": url,
    }


# ── Label generation ─────────────────────────────────────────────────────────
def truncate_text(text, font, max_width):
    """Truncate text with ellipsis if it exceeds max_width pixels."""
    bbox = font.getbbox(text)
    if (bbox[2] - bbox[0]) <= max_width:
        return text
    while len(text) > 1:
        text = text[:-1]
        bbox = font.getbbox(text + "...")
        if (bbox[2] - bbox[0]) <= max_width:
            return text + "..."
    return text


def wrap_text(text, font, max_width):
    """Word-wrap text to fit within max_width pixels. Returns list of lines."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            # If single word exceeds width, truncate it
            bbox = font.getbbox(word)
            if (bbox[2] - bbox[0]) > max_width:
                current = truncate_text(word, font, max_width)
            else:
                current = word
    if current:
        lines.append(current)
    return lines


def make_cots_label_image(cots_id, description, url):
    """Generate a COTS label as a PIL Image (in memory).
    Renders at 2x resolution and downsamples for crisp text."""
    S = SUPERSAMPLE

    # QR code encodes the full ProShop URL
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6 * S,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((QR_SIZE * S, QR_SIZE * S), Image.NEAREST)

    # Text — fixed label width, wrap descriptions to fit
    font_id = get_font(48 * S, bold=True)
    font_desc = get_font(28 * S, bold=False)

    label_w = MAX_LABEL_WIDTH * S
    text_area_w = label_w - (MARGIN + QR_SIZE + MARGIN + MARGIN) * S

    id_line = cots_id
    desc_lines = wrap_text(description, font_desc, text_area_w) if description else []
    # Limit to 2 lines max to fit vertically
    if len(desc_lines) > 2:
        desc_lines = desc_lines[:2]
        desc_lines[-1] = truncate_text(desc_lines[-1], font_desc, text_area_w)

    # Canvas at supersample resolution
    label_hi = Image.new("RGB", (label_w, LABEL_H * S), "white")
    draw = ImageDraw.Draw(label_hi)

    # QR on left, vertically centered
    qr_x = MARGIN * S
    qr_y = (LABEL_H * S - QR_SIZE * S) // 2
    label_hi.paste(qr_img, (qr_x, qr_y))

    # Text after QR
    text_x = qr_x + QR_SIZE * S + MARGIN * S

    # COTS ID — large bold, top
    draw.text((text_x, 2 * S), id_line, fill="black", font=font_id)

    # Description — wrapped lines below ID
    desc_y = 56 * S
    line_spacing = 32 * S
    for line in desc_lines:
        draw.text((text_x, desc_y), line, fill="black", font=font_desc)
        desc_y += line_spacing

    # Downsample to output resolution with LANCZOS for smooth edges
    label = label_hi.resize((MAX_LABEL_WIDTH, LABEL_H), Image.LANCZOS)
    return label


def make_cots_label(cots_id, description, url, output_dir="."):
    """Generate a single COTS label PNG and save to disk."""
    img = make_cots_label_image(cots_id, description, url)
    safe_name = cots_id.replace("/", "-")
    out_path = os.path.join(output_dir, f"COTS_{safe_name}.png")
    img.save(out_path, dpi=(DPI, DPI))
    return out_path


def print_cots_label(cots_id, description, url, copies=1):
    """Generate a COTS label and send it to the print service."""
    import requests

    img = make_cots_label_image(cots_id, description, url)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(DPI, DPI))
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    api_url = f"{PRINT_SERVICE_URL}/api/print-image"
    payload = {
        "image_base64": image_b64,
        "copies": copies,
        "label_name": f"COTS {cots_id}",
    }
    resp = requests.post(api_url, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    print(f"  Printed {cots_id} x{copies} on {result.get('printer', '?')}")
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]

    do_print = "--print" in args
    if do_print:
        args = [a for a in args if a != "--print"]

    do_all = "--all" in args
    if do_all:
        args = [a for a in args if a != "--all"]

    use_api = "--api" in args
    if use_api:
        args = [a for a in args if a != "--api"]

    copies = 1
    if "--copies" in args:
        idx = args.index("--copies")
        copies = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    # Determine which items to process
    if use_api:
        # Pull each item from ProShop API
        if not args:
            print("Error: --api requires COTS_ID(s)")
            sys.exit(1)
        targets = []
        for cots_id in args:
            print(f"  Looking up {cots_id} from ProShop API...")
            item = lookup_cots_api(cots_id)
            if item:
                targets.append(item)
            else:
                print(f"  Warning: {cots_id} not found in ProShop API, skipping")
    else:
        # Load from CSV
        items = load_cots_csv()
        if do_all:
            targets = list(items.values())
        else:
            if not args:
                print("Error: provide COTS_ID(s) or --all")
                sys.exit(1)
            targets = []
            for cots_id in args:
                cots_id_upper = cots_id.upper()
                if cots_id_upper in items:
                    targets.append(items[cots_id_upper])
                elif cots_id in items:
                    targets.append(items[cots_id])
                else:
                    print(f"  Warning: {cots_id} not found in CSV, skipping")

    if not targets:
        print("No items to process.")
        sys.exit(1)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labels")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Generating {len(targets)} COTS label(s)...")
    for item in targets:
        path = make_cots_label(item["cots_id"], item["description"], item["url"], output_dir=out_dir)
        print(f"  {item['cots_id']} -> {path}")
        if do_print:
            print_cots_label(item["cots_id"], item["description"], item["url"], copies=copies)

    print(f"\nLabels saved to {out_dir}")
    if do_print:
        print("Labels sent to printer.")


if __name__ == "__main__":
    main()
