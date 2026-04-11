"""
Count Parts endpoint — sends camera frame to Claude Vision for part counting.
"""

import time
import logging
from fastapi import APIRouter

from models.schemas import CountPartsRequest, CountPartsResponse
from services.vision_counter import count_parts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Vision"])


@router.post("/count-parts", response_model=CountPartsResponse)
async def count_parts_endpoint(request: CountPartsRequest):
    """
    Count parts in a camera image using Claude Vision.

    Accepts a base64-encoded JPEG image and optional context string.
    Returns count, confidence level, and description.
    """
    start = time.time()

    result = count_parts(
        image_base64=request.image_base64,
        context=request.context or "",
    )

    elapsed = round((time.time() - start) * 1000)
    logger.info(f"Count parts: {result['count']} ({result['confidence']}) in {elapsed}ms")

    return CountPartsResponse(
        success=result["error"] is None,
        count=result["count"],
        confidence=result["confidence"],
        description=result["description"],
        error=result["error"],
    )
