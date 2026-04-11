"""
Parts API endpoints.
"""

import time
from fastapi import APIRouter, HTTPException
from typing import Optional

from graphql.client import get_client
from graphql.queries import execute_template
from models.schemas import StandardResponse

router = APIRouter(prefix="/api/parts", tags=["Parts"])


def _make_meta(start: float):
    return {"query_time_ms": round((time.time() - start) * 1000)}


@router.get("", response_model=StandardResponse)
async def list_parts():
    """List all parts."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "list_parts")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{part_number}", response_model=StandardResponse)
async def get_part(part_number: str):
    """Get details for a specific part."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "part_info", {"partNumber": [part_number.upper()]})
        if not result:
            raise HTTPException(status_code=404, detail=f"Part {part_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{part_number}/ops", response_model=StandardResponse)
async def get_part_operations(part_number: str):
    """Get operations for a specific part."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "part_operations", {"partNumber": [part_number.upper()]})
        if not result:
            raise HTTPException(status_code=404, detail=f"Part {part_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{part_number}/ops/{op_number}", response_model=StandardResponse)
async def get_part_operation_detail(part_number: str, op_number: str):
    """Get detailed info for a specific operation on a part, including tools and written descriptions."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(
            client, "part_operation_details",
            {"partNumber": [part_number.upper()], "opNumber": op_number},
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Part {part_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
