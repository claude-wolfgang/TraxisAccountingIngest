"""
Dashboard endpoint — single fast endpoint that returns all dashboard stats.
Fetches work orders ONCE and computes all stats from that dataset.
"""

import time
from datetime import datetime, timedelta
from fastapi import APIRouter

from graphql.client import get_client
from graphql.queries import parse_date, is_within_lookback
from models.schemas import StandardResponse

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# The single query that fetches everything we need
DASHBOARD_QUERY = """
    query DashboardData($pageSize: Int) {
        workOrders(pageSize: $pageSize) {
            totalRecords
            records {
                workOrderNumber
                status
                dueDate
                quantityOrdered
                qtyComplete
            }
        }
    }
"""


@router.get("", response_model=StandardResponse)
async def dashboard():
    """
    Single endpoint for all dashboard data. Fetches work orders once
    and computes: open count, due this week, late, and recent WO list.
    """
    start = time.time()
    client = get_client()

    try:
        data = client.execute(DASHBOARD_QUERY, {"pageSize": 2500})
        all_records = data.get("workOrders", {}).get("records", [])
        total_in_system = data.get("workOrders", {}).get("totalRecords", 0)

        # Filter to recent (last 12 months)
        recent = [wo for wo in all_records if is_within_lookback(wo)]

        today = datetime.now().date()
        week_end = today + timedelta(days=(6 - today.weekday()))
        complete_statuses = ["Complete", "Invoiced", "Shipped", "Canceled"]
        open_statuses = ["Active", "Manufacturing Complete"]

        # Compute all stats from the single dataset
        open_wos = [wo for wo in recent if wo.get("status") in open_statuses]
        late_wos = []
        due_this_week = []

        for wo in recent:
            due_date = parse_date(wo.get("dueDate"))
            if not due_date:
                continue

            # Late: past due and not complete
            if due_date < today and wo.get("status") not in complete_statuses:
                late_wos.append(wo)

            # Due this week
            if today <= due_date <= week_end:
                due_this_week.append(wo)

        return StandardResponse(
            data={
                "open_count": len(open_wos),
                "late_count": len(late_wos),
                "due_this_week_count": len(due_this_week),
                "total_recent": len(recent),
                "total_in_system": total_in_system,
                "late_work_orders": late_wos,
                "due_this_week": due_this_week,
            },
            meta={"query_time_ms": round((time.time() - start) * 1000)},
        )

    except Exception as e:
        return StandardResponse(
            success=False,
            data={"error": str(e)},
            meta={"query_time_ms": round((time.time() - start) * 1000)},
        )
