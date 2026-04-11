"""
Universal search endpoint.
Searches across work orders and parts.
"""

import time
import re
from fastapi import APIRouter, HTTPException, Query

from graphql.client import get_client
from graphql.queries import execute_template
from models.schemas import StandardResponse

router = APIRouter(prefix="/api/search", tags=["Search"])

# Patterns for identifying search input type
WO_PATTERN = re.compile(r'^\d{2}-\d{4}$')
PART_PATTERN = re.compile(r'^[A-Z]{2,4}\d*-[A-Z0-9]+', re.IGNORECASE)


@router.get("", response_model=StandardResponse)
async def search(q: str = Query(..., description="Search query — WO number, part number, or keyword")):
    """
    Universal search. Automatically detects whether the query is a work order number,
    part number, or general text and routes accordingly.
    """
    start = time.time()
    client = get_client()
    q = q.strip()

    results = {"work_orders": [], "parts": []}

    try:
        # If it looks like a WO number, search work orders
        if WO_PATTERN.match(q):
            wo = execute_template(client, "work_order_status", {"woNumber": q})
            if wo:
                results["work_orders"].append(wo)

        # If it looks like a part number, search parts
        elif PART_PATTERN.match(q):
            parts = execute_template(client, "part_info", {"partNumber": [q.upper()]})
            if parts:
                results["parts"] = parts

        else:
            # Try both — search WOs and parts
            # Try as WO number first (in case it's partial)
            wo_match = re.search(r'(\d{2}-\d{4})', q)
            if wo_match:
                wo = execute_template(client, "work_order_status", {"woNumber": wo_match.group(1)})
                if wo:
                    results["work_orders"].append(wo)

            # Try as part number
            part_match = re.search(r'([A-Z]{2,4}\d*-[A-Z0-9]+)', q, re.IGNORECASE)
            if part_match:
                parts = execute_template(client, "part_info", {"partNumber": [part_match.group(1).upper()]})
                if parts:
                    results["parts"] = parts

        meta = {
            "query_time_ms": round((time.time() - start) * 1000),
            "query": q,
            "result_counts": {
                "work_orders": len(results["work_orders"]),
                "parts": len(results["parts"]),
            },
        }

        return StandardResponse(data=results, meta=meta)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
