"""Generate and print small labels for tools received against a VPO.

Label format (Brother PT-P700, 24mm tape):
  ┌──────────────────────┐
  │   A34     VPO 263097 │
  │   Helical 81714  ×3  │
  └──────────────────────┘

Uses two ProShop API clients:
  - Accounting client: reads VPO line items (descriptions, quantities, order numbers)
  - Toolkiosk client: resolves tool library numbers by description match

Prints via P22 print service at PRINT_SERVICE_URL /api/print-image.
"""

import sys
import os
import base64
import io
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from accounting_ingest import load_env

ENV = load_env()

PROSHOP_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
PROSHOP_GQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
PRINT_SERVICE_URL = "http://10.1.1.242:5002"

DPI = 180
TAPE_HEIGHT_MM = 24
LABEL_H = int((TAPE_HEIGHT_MM / 25.4) * DPI)  # ~170 px


def get_font(size, bold=False):
    names = ["arialbd.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "Arial.ttf"]
    for name in names:
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _get_token(client_id, client_secret, scope):
    r = requests.post(PROSHOP_TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    })
    r.raise_for_status()
    return r.json()["access_token"]


def _gql(token, query, variables=None):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(PROSHOP_GQL_URL, headers=headers, json=payload)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"][0]["message"])
    return data["data"]


def get_vpo_tool_items(vpo_number):
    """Read VPO line items and resolve tool library numbers. Returns list of dicts."""
    acct_token = _get_token(ENV["ACCOUNTING_CLIENT_ID"], ENV["ACCOUNTING_CLIENT_SECRET"], ENV["ACCOUNTING_SCOPE"])
    tool_token = _get_token(ENV["TOOLKIOSK_CLIENT_ID"], ENV["TOOLKIOSK_CLIENT_SECRET"], ENV["TOOLKIOSK_SCOPE"])

    vpo_data = _gql(acct_token, """query {
        vendorPO(id: "%s") {
            supplierPlainText
            poItems { records { description orderNumber quantity receivedQty } }
        }
    }""" % vpo_number)

    items = vpo_data["vendorPO"]["poItems"]["records"]
    vendor = vpo_data["vendorPO"]["supplierPlainText"]
    results = []

    for item in items:
        desc = item.get("description")
        if not desc:
            continue
        qty = item.get("quantity")
        order_num = item.get("orderNumber") or ""

        # Resolve tool library number by description match
        lib_number = None
        try:
            tool_data = _gql(tool_token,
                'query($d: [String]) { tools(filter: { description: $d }, pageSize: 1) { records { toolNumber } } }',
                {"d": [desc]})
            recs = tool_data["tools"]["records"]
            if recs:
                lib_number = recs[0]["toolNumber"]
        except Exception:
            pass

        results.append({
            "vpo": vpo_number,
            "vendor": vendor,
            "lib_number": lib_number,
            "order_number": order_num,
            "description": desc,
            "quantity": qty,
        })

    return results


def make_label_image(lib_number, vpo_number, order_number, quantity=None):
    """Generate a compact 24mm tape label PNG with 3 lines. Returns PIL Image."""
    font_lib = get_font(22, bold=True)
    font_sm = get_font(14, bold=False)

    line1 = lib_number
    line2 = f"VPO {vpo_number}"
    line3 = order_number or ""

    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    l1_w = d.textbbox((0, 0), line1, font=font_lib)[2]
    l2_w = d.textbbox((0, 0), line2, font=font_sm)[2]
    l3_w = d.textbbox((0, 0), line3, font=font_sm)[2] if line3 else 0

    label_w = max(l1_w, l2_w, l3_w) + 16

    img = Image.new("RGB", (label_w, LABEL_H), "white")
    draw = ImageDraw.Draw(img)

    draw.text((8, 2), line1, font=font_lib, fill="black")
    draw.text((8, 28), line2, font=font_sm, fill="black")
    if line3:
        draw.text((8, 46), line3, font=font_sm, fill="black")

    return img


def print_label(image, label_name="tool_receiving", copies=1):
    """Send label PNG to the P22 print service."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    r = requests.post(f"{PRINT_SERVICE_URL}/api/print-image", json={
        "image_base64": b64,
        "label_name": label_name,
        "copies": copies,
    }, timeout=10)
    r.raise_for_status()
    return r.json()


def receive_and_label(vpo_number, dry_run=False):
    """Main entry: read VPO tool items, generate labels, print them."""
    items = get_vpo_tool_items(vpo_number)
    print(f"VPO {vpo_number}: {len(items)} tool line items")

    labels_dir = Path(__file__).parent / "labels"
    labels_dir.mkdir(exist_ok=True)

    for item in items:
        lib = item["lib_number"] or "???"
        qty = int(item["quantity"] or 1)
        order = item["order_number"]
        print(f"  {lib:6s} | {order:30s} | qty {qty} | {item['description'][:40]}")

        img = make_label_image(lib, vpo_number, order)
        label_path = labels_dir / f"{lib}_{vpo_number}.png"
        img.save(str(label_path))

        if dry_run:
            print(f"    -> saved {label_path.name} x{qty} (dry run, not printing)")
        else:
            try:
                result = print_label(img, label_name=f"{lib}_{vpo_number}", copies=qty)
                print(f"    -> printed x{qty}: {result}")
            except Exception as e:
                print(f"    -> print failed: {e}, saved to {label_path.name}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Print tool receiving labels for a VPO")
    parser.add_argument("vpo", help="VPO number (e.g. 263097)")
    parser.add_argument("--dry-run", action="store_true", help="Generate labels but don't print")
    args = parser.parse_args()
    receive_and_label(args.vpo, dry_run=args.dry_run)
