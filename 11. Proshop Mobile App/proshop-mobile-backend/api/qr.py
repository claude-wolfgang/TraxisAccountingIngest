"""
QR Code generation endpoints.
"""

import io
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import qrcode

router = APIRouter(prefix="/api/qr", tags=["QR Codes"])


def _generate_qr(data: str) -> io.BytesIO:
    """Generate a QR code PNG image."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@router.get("/wo/{wo_number}")
async def qr_work_order(wo_number: str):
    """Generate a QR code for a work order."""
    buf = _generate_qr(f"proshop://wo/{wo_number}")
    return StreamingResponse(buf, media_type="image/png")


@router.get("/part/{part_number}")
async def qr_part(part_number: str):
    """Generate a QR code for a part."""
    buf = _generate_qr(f"proshop://part/{part_number}")
    return StreamingResponse(buf, media_type="image/png")


@router.get("/op/{wo_number}/{op_number}")
async def qr_operation(wo_number: str, op_number: str):
    """Generate a QR code for a specific operation."""
    buf = _generate_qr(f"proshop://op/{wo_number}/{op_number}")
    return StreamingResponse(buf, media_type="image/png")
