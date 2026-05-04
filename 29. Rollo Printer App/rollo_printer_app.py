"""
Rollo Thermal Printer System Tray App
Prints PDFs directly to Rollo 4x6 thermal printer with auto-rescaling.
Runs silently in the Windows system tray.
"""

import io
import logging
import os
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import fitz  # PyMuPDF
import pystray
import win32print
import win32ui
from PIL import Image, ImageDraw
from pystray import MenuItem as item

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRINTER_NAME = "Rollo Printer"
LABEL_WIDTH_IN = 4.0
LABEL_HEIGHT_IN = 6.0
ROLLO_DPI = 203
LABEL_WIDTH_PX = int(LABEL_WIDTH_IN * ROLLO_DPI)   # 812
LABEL_HEIGHT_PX = int(LABEL_HEIGHT_IN * ROLLO_DPI)  # 1218

APP_NAME = "Rollo Printer"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log_dir() -> Path:
    """Return the directory that contains the running exe (or script)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def setup_logging() -> logging.Logger:
    log_path = _log_dir() / "rollo_print.log"
    logger = logging.getLogger("rollo")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_path, maxBytes=0, backupCount=0,
    )
    # We manage rotation manually: keep last 100 lines
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def trim_log(max_lines: int = 100) -> None:
    """Keep only the last *max_lines* entries in the log file."""
    log_path = _log_dir() / "rollo_print.log"
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            log_path.write_text(
                "\n".join(lines[-max_lines:]) + "\n", encoding="utf-8"
            )
    except FileNotFoundError:
        pass


logger = setup_logging()

# ---------------------------------------------------------------------------
# Printer helpers
# ---------------------------------------------------------------------------

def find_rollo_printer() -> str | None:
    """Return the exact Windows printer name if Rollo is installed."""
    printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
    for name in printers:
        if "rollo" in name.lower():
            return name
    return None


def _split_axis(
    bw: Image.Image,
    bbox: tuple[int, int, int, int],
    axis: str,
    min_gap_pct: float,
) -> list[tuple[int, int, int, int]]:
    """Split bbox of a threshold image into sub-bboxes wherever a strip of
    full-axis whitespace at least min_gap_pct of the axis length appears.
    Returns [bbox] unchanged if no qualifying split is found.
    """
    left, top, _right, _bottom = bbox
    region = bw.crop(bbox)
    rw, rh = region.size
    if rw == 0 or rh == 0:
        return [bbox]

    # Transpose so columns become rows for fast bytes-comparison scanning.
    scan_img = region.transpose(Image.TRANSPOSE) if axis == "cols" else region
    sw, sh = scan_img.size
    data = scan_img.tobytes()
    zero_row = b"\x00" * sw
    has_content = [
        data[y * sw:(y + 1) * sw] != zero_row for y in range(sh)
    ]

    min_gap = max(int(sh * min_gap_pct), 10)

    runs: list[tuple[int, int]] = []
    run_start = -1
    last_content = -1
    for i, has in enumerate(has_content):
        if has:
            if run_start < 0:
                run_start = i
            last_content = i
        elif run_start >= 0 and (i - last_content) >= min_gap:
            runs.append((run_start, last_content))
            run_start = -1
    if run_start >= 0 and last_content >= run_start:
        runs.append((run_start, last_content))

    if len(runs) <= 1:
        return [bbox]

    out: list[tuple[int, int, int, int]] = []
    for s, e in runs:
        crop = (0, s, rw, e + 1) if axis == "rows" else (s, 0, e + 1, rh)
        sub = region.crop(crop)
        sb = sub.getbbox()
        if not sb:
            continue
        sl, st, sr, sbot = sb
        if axis == "rows":
            out.append((left + sl, top + s + st, left + sr, top + s + sbot))
        else:
            out.append((left + s + sl, top + st, left + s + sr, top + sbot))
    return out or [bbox]


def _find_label_region(
    bw: Image.Image,
    outer_bbox: tuple[int, int, int, int],
    min_gap_pct: float = 0.04,
) -> tuple[int, int, int, int] | None:
    """Detect distinct content regions inside outer_bbox separated by full-axis
    whitespace strips on either axis (handles UPS small-label-on-letter,
    FedEx label+doc-tab stacked, and FedEx label+instructions side-by-side).
    Returns the bbox of the largest region by area, or None if content is one
    contiguous block.
    """
    row_blocks = _split_axis(bw, outer_bbox, "rows", min_gap_pct)
    leaves: list[tuple[int, int, int, int]] = []
    for rb in row_blocks:
        leaves.extend(_split_axis(bw, rb, "cols", min_gap_pct))

    if len(leaves) <= 1:
        return None

    return max(leaves, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))


def _region_is_upside_down(
    page: "fitz.Page",
    region_bbox_px: tuple[int, int, int, int],
    dpi: int,
) -> bool:
    """True if text inside region_bbox_px is predominantly rotated 180°.
    FedEx ship-manager labels are rendered upside-down on the page so a user
    can fold and tuck for laser printing — for thermal we flip them back.
    """
    scale = 72.0 / dpi
    x0, y0, x1, y1 = region_bbox_px
    pdf_rect = fitz.Rect(x0 * scale, y0 * scale, x1 * scale, y1 * scale)
    try:
        text_dict = page.get_text("dict")
    except Exception:
        return False
    upright = upside_down = 0
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        bbox = block.get("bbox")
        if not bbox or not pdf_rect.intersects(fitz.Rect(*bbox)):
            continue
        for line in block.get("lines", []):
            cos_t = line.get("dir", (1.0, 0.0))[0]
            if cos_t > 0.9:
                upright += 1
            elif cos_t < -0.9:
                upside_down += 1
    return upside_down > upright


def render_pdf_to_images(pdf_path: str) -> list[Image.Image]:
    """Render each page of *pdf_path* to a PIL Image scaled for the Rollo label.

    Crops to the actual ink area so an 8.5x11 carrier PDF (UPS, FedEx) fills
    the 4x6. When content is split by whitespace (FedEx page-header + label,
    or label + doc tab), picks the largest block as the label and corrects
    upside-down orientation via PyMuPDF text direction.
    """
    doc = fitz.open(pdf_path)
    images: list[Image.Image] = []
    preview_dpi = 300
    for page in doc:
        # FedEx ship-manager PDFs are authored with page.rotation set so the
        # label sits sideways/upside-down on a fold-and-tuck laser sheet.
        # Render in PDF-native space so the label is upright and text-direction
        # checks below match the rendered pixmap's coordinate frame.
        if page.rotation:
            page.set_rotation(0)
        mat = fitz.Matrix(preview_dpi / 72.0, preview_dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        gray = img.convert("L")
        bw = gray.point(lambda x: 255 if x < 250 else 0)
        bbox = bw.getbbox()

        if bbox is None:
            continue

        label_bbox = _find_label_region(bw, bbox) or bbox

        margin_x = int((label_bbox[2] - label_bbox[0]) * 0.03)
        margin_y = int((label_bbox[3] - label_bbox[1]) * 0.03)
        crop_box = (
            max(label_bbox[0] - margin_x, 0),
            max(label_bbox[1] - margin_y, 0),
            min(label_bbox[2] + margin_x, img.width),
            min(label_bbox[3] + margin_y, img.height),
        )
        cropped = img.crop(crop_box)

        if _region_is_upside_down(page, crop_box, preview_dpi):
            cropped = cropped.rotate(180, expand=True)

        crop_w, crop_h = cropped.size
        if crop_w > crop_h:
            cropped = cropped.rotate(90, expand=True)
            crop_w, crop_h = cropped.size

        scale_x = LABEL_WIDTH_PX / crop_w
        scale_y = LABEL_HEIGHT_PX / crop_h
        scale = min(scale_x, scale_y)

        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)
        resized = cropped.resize((new_w, new_h), Image.LANCZOS)

        label = Image.new("RGB", (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), (255, 255, 255))
        offset_x = (LABEL_WIDTH_PX - new_w) // 2
        offset_y = (LABEL_HEIGHT_PX - new_h) // 2
        label.paste(resized, (offset_x, offset_y))
        images.append(label)
    doc.close()
    return images


def print_images(images: list[Image.Image], printer_name: str) -> None:
    """Send a list of PIL images to the named Windows printer."""
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    hdc.StartDoc("Rollo Label")
    for img in images:
        hdc.StartPage()
        dib = img.tobytes("raw", "BGR")
        # Use StretchDIBits for direct bitmap printing
        import struct
        import ctypes

        bmi_header = struct.pack(
            "<IiiHHIIiiII",
            40,               # biSize
            img.width,        # biWidth
            -img.height,      # biHeight (negative = top-down)
            1,                # biPlanes
            24,               # biBitCount
            0,                # biCompression (BI_RGB)
            0,                # biSizeImage
            ROLLO_DPI,        # biXPelsPerMeter (approximate)
            ROLLO_DPI,        # biYPelsPerMeter
            0,                # biClrUsed
            0,                # biClrImportant
        )
        bmi = bmi_header  # BITMAPINFO with no color table for 24-bit

        # Row stride must be DWORD-aligned
        row_stride = ((img.width * 3) + 3) & ~3
        padded = bytearray()
        raw = img.tobytes("raw", "BGR")
        src_stride = img.width * 3
        for y in range(img.height):
            row = raw[y * src_stride : (y + 1) * src_stride]
            padded.extend(row)
            padded.extend(b"\x00" * (row_stride - src_stride))

        hdc_handle = hdc.GetSafeHdc()
        gdi32 = ctypes.windll.gdi32
        gdi32.StretchDIBits(
            hdc_handle,
            0, 0, img.width, img.height,  # dest
            0, 0, img.width, img.height,  # src
            bytes(padded),
            bmi,
            0,  # DIB_RGB_COLORS
            0x00CC0020,  # SRCCOPY
        )
        hdc.EndPage()
    hdc.EndDoc()
    hdc.DeleteDC()


# ---------------------------------------------------------------------------
# Print workflow
# ---------------------------------------------------------------------------

def print_pdf(pdf_path: str, notify_fn=None) -> None:
    """Full pipeline: validate → render → print → log."""
    filename = os.path.basename(pdf_path)
    try:
        printer = find_rollo_printer()
        if printer is None:
            msg = f"Printed: {filename} | Status: FAIL — Rollo printer not found"
            logger.info(msg)
            if notify_fn:
                notify_fn("Printer not found", "Could not find Rollo printer. Is it connected?")
            return

        images = render_pdf_to_images(pdf_path)
        if not images:
            msg = f"Printed: {filename} | Pages: 0 | Status: FAIL — no pages rendered"
            logger.info(msg)
            if notify_fn:
                notify_fn("PDF Error", f"No pages could be rendered from {filename}")
            return

        print_images(images, printer)
        msg = f"Printed: {filename} | Pages: {len(images)} | Status: SUCCESS"
        logger.info(msg)
        trim_log()
        if notify_fn:
            notify_fn("Printed", f"{filename} ({len(images)} page(s)) sent to {printer}")

    except Exception as e:
        msg = f"Printed: {filename} | Status: FAIL — {e}"
        logger.info(msg)
        if notify_fn:
            notify_fn("Print Error", str(e))


# ---------------------------------------------------------------------------
# System tray app
# ---------------------------------------------------------------------------

def create_icon_image() -> Image.Image:
    """Generate a simple gold/yellow printer icon for the tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Gold rectangle body
    draw.rounded_rectangle([8, 20, 56, 48], radius=4, fill=(218, 165, 32), outline=(0, 0, 0))
    # Paper slot top
    draw.rectangle([16, 8, 48, 24], fill=(255, 255, 255), outline=(0, 0, 0))
    # Paper output bottom
    draw.rectangle([16, 44, 48, 58], fill=(255, 255, 255), outline=(0, 0, 0))
    # Small indicator dot
    draw.ellipse([42, 30, 50, 38], fill=(0, 180, 0))
    return img


class RolloTrayApp:
    def __init__(self):
        self.icon: pystray.Icon | None = None

    def notify(self, title: str, message: str) -> None:
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass  # Notification not supported on all platforms

    def on_print(self, icon, menu_item) -> None:
        """Open file dialog and print selected PDF."""
        # Run in thread so we don't block the tray
        def _do():
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            pdf_path = filedialog.askopenfilename(
                title="Select PDF to print on Rollo",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
            root.destroy()

            if pdf_path:
                print_pdf(pdf_path, notify_fn=self.notify)

        threading.Thread(target=_do, daemon=True).start()

    def on_test(self, icon, menu_item) -> None:
        """Quick connectivity test."""
        def _do():
            printer = find_rollo_printer()
            if printer:
                self.notify("Rollo Found", f"Printer detected: {printer}")
                logger.info(f"Test: Rollo printer found as '{printer}'")
            else:
                self.notify("Rollo Not Found", "No Rollo printer detected")
                logger.info("Test: Rollo printer NOT found")

        threading.Thread(target=_do, daemon=True).start()

    def on_open_log(self, icon, menu_item) -> None:
        """Open the log file in the default text editor."""
        log_path = _log_dir() / "rollo_print.log"
        if log_path.exists():
            os.startfile(str(log_path))
        else:
            self.notify("No Log", "No print log exists yet.")

    def on_quit(self, icon, menu_item) -> None:
        icon.stop()

    def run(self) -> None:
        menu = pystray.Menu(
            item("Print to Rollo", self.on_print, default=True),
            item("Test Printer", self.on_test),
            item("Open Log", self.on_open_log),
            pystray.Menu.SEPARATOR,
            item("Quit", self.on_quit),
        )
        self.icon = pystray.Icon(
            APP_NAME,
            icon=create_icon_image(),
            title=APP_NAME,
            menu=menu,
        )
        logger.info("App started")
        self.icon.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        app = RolloTrayApp()
        app.run()
    except Exception:
        import traceback
        crash_path = _log_dir() / "rollo_crash.log"
        crash_path.write_text(traceback.format_exc(), encoding="utf-8")


if __name__ == "__main__":
    main()
