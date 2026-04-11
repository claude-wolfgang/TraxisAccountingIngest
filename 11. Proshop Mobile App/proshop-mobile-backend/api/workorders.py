"""
Work Order API endpoints.
"""

import time
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from graphql.client import get_client
from graphql.queries import execute_template
from models.schemas import StandardResponse

router = APIRouter(prefix="/api/workorders", tags=["Work Orders"])


def _make_meta(start: float, cached: bool = False):
    return {
        "query_time_ms": round((time.time() - start) * 1000),
        "cached": cached,
    }


@router.get("", response_model=StandardResponse)
async def list_work_orders(status: Optional[str] = Query(None, description="Filter by status: open, active, complete, shipped, etc.")):
    """List work orders (last 12 months). Optionally filter by status."""
    start = time.time()
    client = get_client()
    try:
        if status:
            result = execute_template(client, "list_work_orders_by_status", {"status": status})
        else:
            result = execute_template(client, "list_work_orders")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/due-this-week", response_model=StandardResponse)
async def work_orders_due_this_week():
    """Get work orders due this week."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "work_orders_due_this_week")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/late", response_model=StandardResponse)
async def late_work_orders():
    """Get work orders that are past due."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "late_work_orders")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/count", response_model=StandardResponse)
async def open_work_order_count():
    """Get count of open work orders."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "open_work_order_count")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/largest", response_model=StandardResponse)
async def largest_active_order():
    """Get the largest active work order by quantity."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "largest_active_order")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profitability", response_model=StandardResponse)
async def work_order_profitability():
    """Get profitability data for recent work orders."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "work_order_profitability")
        return StandardResponse(data=result, meta=_make_meta(start))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{wo_number}", response_model=StandardResponse)
async def get_work_order(wo_number: str):
    """Get details for a specific work order."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "work_order_status", {"woNumber": wo_number})
        if not result:
            raise HTTPException(status_code=404, detail=f"Work order {wo_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{wo_number}/ops", response_model=StandardResponse)
async def get_work_order_operations(wo_number: str):
    """Get operations for a specific work order."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "work_order_operations", {"woNumber": wo_number})
        if not result:
            raise HTTPException(status_code=404, detail=f"Work order {wo_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{wo_number}/current-op", response_model=StandardResponse)
async def get_current_operation(wo_number: str):
    """Get the current (incomplete) operation for a work order."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "work_order_current_op", {"woNumber": wo_number})
        if not result:
            raise HTTPException(status_code=404, detail=f"Work order {wo_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{wo_number}/time", response_model=StandardResponse)
async def get_time_tracking(wo_number: str):
    """Get time tracking data for a work order."""
    start = time.time()
    client = get_client()
    try:
        result = execute_template(client, "work_order_time_tracking", {"woNumber": wo_number})
        if not result:
            raise HTTPException(status_code=404, detail=f"Work order {wo_number} not found")
        return StandardResponse(data=result, meta=_make_meta(start))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
