"""Autonomous priority engine for Traxis shop scheduling.

Computes urgency ratios, diagnoses bottlenecks per-job,
and generates daily action plans + aggregate bottleneck reports.
"""

from datetime import datetime, timedelta
from collections import defaultdict
import json
import logging

from database import get_db, get_readiness

log = logging.getLogger("scheduler.priority")

# Business hours
BH_START = 5   # 5 AM
BH_END = 18    # 6 PM
BH_PER_DAY = BH_END - BH_START  # 13 hours

# Urgency ratio thresholds
RATIO_RED_ALERT = 1.0     # Cannot finish on time
RATIO_CRITICAL = 0.8      # No room for error
RATIO_START_SOON = 0.5    # Needs attention this week
RATIO_QUEUED = 0.2        # On the radar
# Below 0.2 = BACKLOG

# Blocker categories
BLOCKER_NONE = None
BLOCKER_PROGRAMMING = "PROGRAMMING"
BLOCKER_MATERIAL = "MATERIAL"
BLOCKER_TOOLING = "TOOLING/PERSONNEL"
BLOCKER_SCHEDULING = "SCHEDULING/MANAGEMENT"
BLOCKER_CAPACITY = "CAPACITY"


def compute_priorities(conn=None, today=None):
    """Main entry point. Compute priorities for all active work orders.

    Returns:
        {
            "generated_at": ISO timestamp,
            "action_list": [...],    # ready jobs, ranked by urgency
            "alert_list": [...],     # urgent but blocked, with diagnosis
            "queue_list": [...],     # ready, moderate urgency
            "backlog_list": [...],   # low urgency
            "bottleneck_summary": {category: count, ...},
            "machine_outlook": [{machine_id, name, scheduled_hours_3d, pct}, ...]
        }
    """
    close = conn is None
    if close:
        conn = get_db()

    if today is None:
        today = datetime.now()

    # 1. Get all active WOs with their incomplete ops
    wo_ops = _get_wo_operations(conn)

    # 2. Get readiness data for all ops
    all_readiness = get_readiness(conn)

    # 3. Check which part numbers have prior completed WOs
    prior_parts = _get_prior_completed_parts(conn)

    # 4. Get current machine occupancy
    machine_blocks = _get_machine_blocks(conn, today)

    # 5. Get machine info
    machines = {r["id"]: r["name"] for r in conn.execute(
        "SELECT id, name FROM machines WHERE is_active=1"
    ).fetchall()}

    # 6. Score each WO
    scored_wos = []
    for wo_number, wo_data in wo_ops.items():
        score = _score_work_order(wo_data, today)
        scored_wos.append({**wo_data, **score})

    # 7. For each WO's next runnable op, diagnose blockers
    results = []
    for wo in scored_wos:
        next_op = _get_next_op(wo["ops"])
        if not next_op:
            continue

        op_id = next_op["id"]
        readiness = all_readiness.get(op_id, {})
        has_prior_run = wo["part_number"] in prior_parts

        # Is this op currently scheduled/running?
        is_scheduled = _is_op_scheduled(conn, op_id)

        blocker = _diagnose_blocker(
            next_op, readiness, has_prior_run,
            is_scheduled, machine_blocks, machines
        )

        # Back-calculate unblock deadline if blocked
        unblock_by = None
        if blocker and wo["urgency_ratio"] is not None:
            unblock_by = _calc_unblock_deadline(wo, next_op, today)

        results.append({
            "wo_number": wo["wo_number"],
            "part_number": wo["part_number"],
            "part_name": wo["part_name"],
            "customer": wo["customer"],
            "due_date": wo["due_date"],
            "urgency_ratio": wo["urgency_ratio"],
            "urgency_label": wo["urgency_label"],
            "total_remaining_hours": wo["total_remaining_hours"],
            "remaining_ops": wo["remaining_ops"],
            "next_op_id": op_id,
            "next_op_number": next_op["op_number"],
            "next_op_name": next_op["op_name"],
            "next_op_hours": next_op.get("override_hours") or next_op.get("est_hours") or 1.0,
            "next_op_work_center": next_op.get("work_center"),
            "next_op_machine": next_op.get("machine_id"),
            "is_repeat_part": has_prior_run,
            "readiness": {
                "program": bool(readiness.get("program_ready", 0)),
                "material": bool(readiness.get("material_ready", 0)),
                "tools": bool(readiness.get("tools_ready", 0)),
                "machine": bool(readiness.get("machine_ready", 0)),
            },
            "blocker": blocker,
            "blocker_detail": _blocker_detail(blocker, readiness, has_prior_run, wo),
            "unblock_by": unblock_by.strftime("%Y-%m-%d") if unblock_by else None,
            "is_scheduled": is_scheduled,
            "reason": _build_reason(wo, blocker, has_prior_run),
        })

    # 8. Split into tracks
    # "Input blockers" are things that prevent starting: programming, material, tooling.
    # SCHEDULING and CAPACITY are diagnostic labels for the bottleneck report,
    # not blockers for the action/alert split. A job with all inputs ready
    # goes on the ACTION list even if it's not yet scheduled — that's the whole point.
    INPUT_BLOCKERS = {BLOCKER_PROGRAMMING, BLOCKER_MATERIAL, BLOCKER_TOOLING}

    action_list = []   # ready (or scheduled), high urgency
    alert_list = []    # input-blocked, high urgency
    queue_list = []    # ready, moderate urgency
    backlog_list = []  # low urgency

    for r in results:
        ratio = r["urgency_ratio"]
        has_input_blocker = r["blocker"] in INPUT_BLOCKERS

        if ratio is None:
            backlog_list.append(r)
        elif ratio >= RATIO_START_SOON:
            if has_input_blocker and not r["is_scheduled"]:
                alert_list.append(r)
            else:
                action_list.append(r)
        elif ratio >= RATIO_QUEUED:
            if has_input_blocker:
                alert_list.append(r)
            else:
                queue_list.append(r)
        else:
            backlog_list.append(r)

    # Sort by urgency ratio descending (most urgent first)
    action_list.sort(key=lambda x: -(x["urgency_ratio"] or 0))
    alert_list.sort(key=lambda x: -(x["urgency_ratio"] or 0))
    queue_list.sort(key=lambda x: -(x["urgency_ratio"] or 0))

    # 9. Bottleneck summary across at-risk jobs
    bottleneck_summary = defaultdict(int)
    for r in alert_list:
        if r["blocker"]:
            bottleneck_summary[r["blocker"]] += 1
    # Also count blockers in action list (jobs that are scheduled despite blockers)
    for r in action_list:
        if r["blocker"]:
            bottleneck_summary[r["blocker"]] += 1

    # 10. Machine outlook (next 3 business days)
    outlook_end = _add_business_days(today, 3)
    machine_outlook = []
    for mid, mname in sorted(machines.items(), key=lambda x: x[1]):
        hours = _machine_scheduled_hours(conn, mid, today, outlook_end)
        available = 3 * BH_PER_DAY
        machine_outlook.append({
            "machine_id": mid,
            "name": mname,
            "scheduled_hours_3d": round(hours, 1),
            "available_hours_3d": available,
            "utilization_pct": round(hours / available * 100) if available else 0,
        })

    if close:
        conn.close()

    return {
        "generated_at": datetime.now().isoformat(),
        "action_list": action_list,
        "alert_list": alert_list,
        "queue_list": queue_list,
        "backlog_list": backlog_list,
        "bottleneck_summary": dict(bottleneck_summary),
        "machine_outlook": machine_outlook,
    }


def generate_bottleneck_report(conn=None, today=None):
    """Generate aggregate bottleneck analysis across all at-risk jobs.

    Returns breakdown by blocker category plus identification of #1 constraint.
    """
    close = conn is None
    if close:
        conn = get_db()

    priorities = compute_priorities(conn, today)

    # All jobs above the "queued" threshold
    at_risk = priorities["action_list"] + priorities["alert_list"] + priorities["queue_list"]
    at_risk = [r for r in at_risk if (r["urgency_ratio"] or 0) >= RATIO_QUEUED]

    total = len(at_risk)
    breakdown = defaultdict(lambda: {"count": 0, "wos": [], "est_hours_blocked": 0})

    for r in at_risk:
        cat = r["blocker"] or "ON_TRACK"
        breakdown[cat]["count"] += 1
        breakdown[cat]["wos"].append(r["wo_number"])
        if r["blocker"]:
            breakdown[cat]["est_hours_blocked"] += r.get("next_op_hours", 0)

    # Find #1 bottleneck (excluding ON_TRACK)
    blockers_only = {k: v for k, v in breakdown.items() if k != "ON_TRACK"}
    top_bottleneck = None
    if blockers_only:
        top_bottleneck = max(blockers_only.items(), key=lambda x: x[1]["count"])

    if close:
        conn.close()

    return {
        "generated_at": datetime.now().isoformat(),
        "jobs_at_risk": total,
        "breakdown": {
            k: {
                "count": v["count"],
                "pct": round(v["count"] / total * 100) if total else 0,
                "work_orders": v["wos"],
                "est_hours_blocked": round(v["est_hours_blocked"], 1),
            }
            for k, v in sorted(breakdown.items(), key=lambda x: -x[1]["count"])
        },
        "top_bottleneck": {
            "category": top_bottleneck[0],
            "count": top_bottleneck[1]["count"],
            "pct": round(top_bottleneck[1]["count"] / total * 100) if total else 0,
            "work_orders": top_bottleneck[1]["wos"],
            "recommendation": _bottleneck_recommendation(top_bottleneck[0]),
        } if top_bottleneck else None,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_wo_operations(conn):
    """Get all active WOs with their incomplete manufacturing ops."""
    rows = conn.execute("""
        SELECT o.id, o.wo_number, o.op_number, o.op_name, o.work_center,
               o.machine_id, o.est_hours, o.override_hours, o.is_complete,
               o.qty_required, o.qty_complete,
               w.part_number, w.part_name, w.customer, w.due_date,
               w.qty_ordered, w.material_type, w.status as wo_status,
               o.proshop_data as op_proshop_data
        FROM operations o
        JOIN work_orders w ON o.wo_number = w.wo_number
        WHERE w.status = 'active'
          AND COALESCE(w.hidden, 0) = 0
          AND COALESCE(o.hidden, 0) = 0
        ORDER BY o.wo_number, o.op_number
    """).fetchall()

    wo_map = {}
    for r in rows:
        r = dict(r)
        wn = r["wo_number"]
        if wn not in wo_map:
            wo_map[wn] = {
                "wo_number": wn,
                "part_number": r["part_number"],
                "part_name": r["part_name"],
                "customer": r["customer"],
                "due_date": r["due_date"],
                "qty_ordered": r["qty_ordered"],
                "material_type": r["material_type"],
                "ops": [],
            }
        wo_map[wn]["ops"].append(r)

    return wo_map


def _get_prior_completed_parts(conn):
    """Get set of part_numbers that have at least one completed WO."""
    rows = conn.execute("""
        SELECT DISTINCT part_number FROM work_orders
        WHERE status = 'complete' AND part_number IS NOT NULL AND part_number != ''
    """).fetchall()
    return {r["part_number"] for r in rows}


def _get_machine_blocks(conn, now):
    """Get current non-complete blocks per machine for capacity check."""
    rows = conn.execute("""
        SELECT machine_id, COUNT(*) as block_count,
               SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) as running
        FROM schedule_blocks
        WHERE status != 'complete'
          AND end_time > ?
        GROUP BY machine_id
    """, (now.isoformat(),)).fetchall()
    return {r["machine_id"]: dict(r) for r in rows}


def _score_work_order(wo_data, today):
    """Compute urgency ratio for a work order.

    urgency_ratio = total_remaining_hours / business_hours_until_due
    """
    ops = wo_data["ops"]

    # Sum remaining hours across all incomplete ops
    total_remaining = 0
    remaining_count = 0
    for op in ops:
        if op["is_complete"]:
            continue
        hours = op.get("override_hours") or op.get("est_hours") or 1.0
        total_remaining += hours
        remaining_count += 1

    # Business hours until due
    due_str = wo_data.get("due_date")
    if not due_str:
        return {
            "urgency_ratio": None,
            "urgency_label": "no-date",
            "total_remaining_hours": round(total_remaining, 1),
            "remaining_ops": remaining_count,
        }

    try:
        due = datetime.strptime(due_str[:10], "%Y-%m-%d")
        # Due date is end of that day
        due = due.replace(hour=BH_END, minute=0)
    except (ValueError, TypeError):
        return {
            "urgency_ratio": None,
            "urgency_label": "no-date",
            "total_remaining_hours": round(total_remaining, 1),
            "remaining_ops": remaining_count,
        }

    hours_available = _business_hours_between(today, due)

    if hours_available <= 0:
        ratio = float('inf') if total_remaining > 0 else 0
    else:
        ratio = total_remaining / hours_available if total_remaining > 0 else 0

    # Label
    if ratio == float('inf') or ratio > RATIO_RED_ALERT:
        label = "RED ALERT"
    elif ratio >= RATIO_CRITICAL:
        label = "CRITICAL"
    elif ratio >= RATIO_START_SOON:
        label = "START SOON"
    elif ratio >= RATIO_QUEUED:
        label = "QUEUED"
    else:
        label = "BACKLOG"

    return {
        "urgency_ratio": round(ratio, 3) if ratio != float('inf') else 999.0,
        "urgency_label": label,
        "total_remaining_hours": round(total_remaining, 1),
        "remaining_ops": remaining_count,
        "hours_available": round(hours_available, 1),
    }


def _get_next_op(ops):
    """Get the next incomplete, non-programming operation to run."""
    incomplete = [
        o for o in ops
        if not o["is_complete"]
    ]
    if not incomplete:
        return None

    # Filter to manufacturing ops (have a work_center) — skip programming, inspection, etc.
    mfg = [o for o in incomplete if o.get("work_center")]
    if mfg:
        # Return lowest op_number
        return min(mfg, key=lambda o: o["op_number"])

    # Fall back to any incomplete op
    return min(incomplete, key=lambda o: o["op_number"])


def _is_op_scheduled(conn, op_id):
    """Check if an operation has a non-complete schedule block."""
    row = conn.execute(
        "SELECT 1 FROM schedule_blocks WHERE operation_id=? AND status != 'complete' LIMIT 1",
        (op_id,)
    ).fetchone()
    return row is not None


def _diagnose_blocker(op, readiness, has_prior_run, is_scheduled, machine_blocks, machines):
    """Run the elimination chain to find primary blocker.

    Order: Program → Material → Tooling → Scheduling → Capacity
    Returns blocker category string or None if ready.
    """
    # Gate 1: Program
    program_ready = readiness.get("program_ready", 0)
    if not program_ready and not has_prior_run:
        return BLOCKER_PROGRAMMING

    # Gate 2: Material
    material_ready = readiness.get("material_ready", 0)
    if not material_ready:
        # Check material_detail for more info
        detail = readiness.get("material_detail")
        if detail:
            try:
                md = json.loads(detail) if isinstance(detail, str) else detail
                # If status is explicitly "not ready", it's a blocker
                if md.get("status") in ("not_ordered", "ordered", "outstanding"):
                    return BLOCKER_MATERIAL
            except (json.JSONDecodeError, TypeError):
                pass
        # If material_ready is 0 but no detail, assume it's a real blocker
        # (the sync sets it based on PO data)
        return BLOCKER_MATERIAL

    # Gate 3: Tooling
    tools_ready = readiness.get("tools_ready", 0)
    if not tools_ready:
        return BLOCKER_TOOLING

    # Gate 4: Everything ready — is it running?
    if is_scheduled:
        return BLOCKER_NONE  # Job is scheduled/running, no blocker

    # Not scheduled despite being ready
    # Check if a machine is available
    work_center = (op.get("work_center") or "").upper()
    assigned_machine = op.get("machine_id")

    if assigned_machine:
        # Has a specific machine — is it occupied?
        mb = machine_blocks.get(assigned_machine, {})
        if mb.get("running", 0) > 0:
            return BLOCKER_CAPACITY
        return BLOCKER_SCHEDULING
    else:
        # No specific machine — check if any compatible machine has capacity
        # For simplicity, check if all mills are occupied
        mill_running = sum(
            1 for mid, mb in machine_blocks.items()
            if mid.startswith("mill") and mb.get("running", 0) > 0
        )
        total_mills = sum(1 for mid in machines if mid.startswith("mill"))

        if work_center and "LATHE" in work_center.upper():
            # Lathe job
            t2 = machine_blocks.get("t2", {})
            if t2.get("running", 0) > 0:
                return BLOCKER_CAPACITY
            return BLOCKER_SCHEDULING
        else:
            # Mill job
            if mill_running >= total_mills:
                return BLOCKER_CAPACITY
            return BLOCKER_SCHEDULING

    return BLOCKER_NONE


def _blocker_detail(blocker, readiness, has_prior_run, wo):
    """Generate human-readable detail for a blocker."""
    if not blocker:
        return None

    if blocker == BLOCKER_PROGRAMMING:
        return "New part — program not yet complete. No prior completed WO found for this part number."

    if blocker == BLOCKER_MATERIAL:
        detail = readiness.get("material_detail")
        if detail:
            try:
                md = json.loads(detail) if isinstance(detail, str) else detail
                status = md.get("status", "unknown")
                return f"Material status: {status}. PO outstanding or not yet ordered."
            except (json.JSONDecodeError, TypeError):
                pass
        return "Material not confirmed received."

    if blocker == BLOCKER_TOOLING:
        return "Program and material ready. Tools not staged — personnel or staging efficiency gap."

    if blocker == BLOCKER_SCHEDULING:
        return "All inputs ready. Machine available. Job not started — scheduling or decision-making gap."

    if blocker == BLOCKER_CAPACITY:
        return "All inputs ready. All qualified machines currently occupied."

    return None


def _calc_unblock_deadline(wo, next_op, today):
    """Back-calculate when a blocker must be resolved to avoid being late.

    Logic: due_date minus remaining business hours = latest start.
    The blocker must be resolved before that.
    """
    due_str = wo.get("due_date")
    if not due_str:
        return None

    try:
        due = datetime.strptime(due_str[:10], "%Y-%m-%d").replace(hour=BH_END)
    except (ValueError, TypeError):
        return None

    remaining_hours = wo.get("total_remaining_hours", 0)
    if not remaining_hours:
        remaining_hours = next_op.get("override_hours") or next_op.get("est_hours") or 1.0

    # Subtract remaining hours from due date to get latest start
    latest_start = _subtract_business_hours(due, remaining_hours)

    # The blocker should be resolved at least 1 business day before latest start
    # to allow for staging/setup
    unblock_by = _subtract_business_hours(latest_start, BH_PER_DAY)

    # Don't return dates in the past — if we're already past the deadline, return today
    if unblock_by < today:
        return today

    return unblock_by


def _build_reason(wo, blocker, has_prior_run):
    """Build a one-line reason string for the priority ranking."""
    ratio = wo.get("urgency_ratio")
    label = wo.get("urgency_label", "")
    remaining = wo.get("total_remaining_hours", 0)
    remaining_ops = wo.get("remaining_ops", 0)

    parts = []

    if label == "RED ALERT":
        parts.append("Cannot finish on time at current pace.")
    elif label == "CRITICAL":
        parts.append("No room for error.")
    elif label == "START SOON":
        parts.append("Needs to start this week.")

    parts.append(f"{remaining}h across {remaining_ops} op{'s' if remaining_ops != 1 else ''}.")

    if has_prior_run:
        parts.append("Repeat part.")

    if blocker:
        parts.append(f"Blocked: {blocker}.")

    return " ".join(parts)


def _bottleneck_recommendation(category):
    """Return actionable recommendation for a bottleneck category."""
    recs = {
        BLOCKER_PROGRAMMING: "CAM capacity is the constraint. Consider: dedicated programming time blocks, outsourcing programming, or prioritizing repeat parts.",
        BLOCKER_MATERIAL: "Material procurement is the constraint. Review supplier lead times, PO follow-up process, and safety stock levels.",
        BLOCKER_TOOLING: "Tool staging is the constraint. Consider: dedicated tool staging time, pre-kitting tools for upcoming jobs, or a tool room schedule.",
        BLOCKER_SCHEDULING: "Decision-making itself is the constraint. The priority engine should fix this — jobs are ready but not being started.",
        BLOCKER_CAPACITY: "Machine hours are the constraint. Consider: overtime, outsourcing operations, or evaluating a new machine.",
    }
    return recs.get(category, "Review jobs in this category for common patterns.")


# ── Date/time utilities ───────────────────────────────────────────────────────

def _business_hours_between(start, end):
    """Count business hours between two datetimes."""
    if end <= start:
        return 0

    total = 0
    cursor = _snap_to_bh(start)

    for _ in range(500):  # safety limit
        if cursor >= end:
            break

        day_end = cursor.replace(hour=BH_END, minute=0, second=0, microsecond=0)
        effective_end = min(day_end, end)

        if effective_end > cursor:
            total += (effective_end - cursor).total_seconds() / 3600

        # Move to next business day
        cursor = (cursor + timedelta(days=1)).replace(
            hour=BH_START, minute=0, second=0, microsecond=0
        )
        # Skip weekends
        while cursor.weekday() >= 5:
            cursor += timedelta(days=1)

    return total


def _subtract_business_hours(dt, hours):
    """Subtract business hours from a datetime, skipping nights and weekends."""
    remaining = hours
    cursor = dt

    for _ in range(500):
        if remaining <= 0:
            break

        # Snap to business hours (backwards)
        cursor = _snap_to_bh_back(cursor)

        # Hours available from start of this business day to cursor
        day_start = cursor.replace(hour=BH_START, minute=0, second=0, microsecond=0)
        available = (cursor - day_start).total_seconds() / 3600

        if available <= 0:
            # Move to end of previous business day
            cursor = (cursor - timedelta(days=1)).replace(
                hour=BH_END, minute=0, second=0, microsecond=0
            )
            while cursor.weekday() >= 5:
                cursor -= timedelta(days=1)
            continue

        if remaining <= available:
            cursor -= timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= available
            # Move to end of previous business day
            cursor = (cursor - timedelta(days=1)).replace(
                hour=BH_END, minute=0, second=0, microsecond=0
            )
            while cursor.weekday() >= 5:
                cursor -= timedelta(days=1)

    return cursor


def _snap_to_bh(dt):
    """Snap datetime forward to business hours."""
    while dt.weekday() >= 5:
        dt = (dt + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
    if dt.hour < BH_START:
        dt = dt.replace(hour=BH_START, minute=0, second=0, microsecond=0)
    elif dt.hour >= BH_END:
        dt = (dt + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
        while dt.weekday() >= 5:
            dt = (dt + timedelta(days=1)).replace(hour=BH_START, minute=0, second=0, microsecond=0)
    return dt


def _snap_to_bh_back(dt):
    """Snap datetime backward to business hours."""
    while dt.weekday() >= 5:
        dt = (dt - timedelta(days=1)).replace(hour=BH_END, minute=0, second=0, microsecond=0)
    if dt.hour >= BH_END:
        dt = dt.replace(hour=BH_END, minute=0, second=0, microsecond=0)
    elif dt.hour < BH_START:
        dt = (dt - timedelta(days=1)).replace(hour=BH_END, minute=0, second=0, microsecond=0)
        while dt.weekday() >= 5:
            dt = (dt - timedelta(days=1)).replace(hour=BH_END, minute=0, second=0, microsecond=0)
    return dt


def _add_business_days(dt, days):
    """Add N business days to a datetime."""
    result = dt
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result.replace(hour=BH_END, minute=0, second=0, microsecond=0)


def _machine_scheduled_hours(conn, machine_id, start, end):
    """Total scheduled hours on a machine between start and end."""
    rows = conn.execute("""
        SELECT start_time, end_time FROM schedule_blocks
        WHERE machine_id = ? AND status != 'complete'
          AND end_time > ? AND start_time < ?
    """, (machine_id, start.isoformat(), end.isoformat())).fetchall()

    total = 0.0
    for r in rows:
        s = datetime.fromisoformat(r["start_time"])
        e = datetime.fromisoformat(r["end_time"])
        s = max(s, start)
        e = min(e, end)
        if e > s:
            total += (e - s).total_seconds() / 3600
    return total


# ── Text report formatter ─────────────────────────────────────────────────────

def format_daily_report(priorities):
    """Format priorities dict into a readable text report."""
    lines = []
    gen = priorities["generated_at"][:16].replace("T", " ")
    lines.append(f"=== TRAXIS DAILY PRIORITIES -- {gen} ===")
    lines.append("")

    # Action list
    if priorities["action_list"]:
        lines.append(">> START NOW (ready, high urgency):")
        for i, r in enumerate(priorities["action_list"], 1):
            ratio_str = f"{r['urgency_ratio']:.2f}" if r['urgency_ratio'] else "?"
            lines.append(
                f"  {i}. {r['wo_number']} Op {r['next_op_number']} [{r['next_op_work_center'] or '?'}] "
                f"-- Due {r['due_date'][:10] if r['due_date'] else '?'} | "
                f"{r['total_remaining_hours']}h left | ratio: {ratio_str}"
            )
            if r.get("next_op_machine"):
                lines.append(f"     -> Machine: {r['next_op_machine']}")
            lines.append(f"     {r['reason']}")
            lines.append("")
    else:
        lines.append(">> START NOW: (none)")
        lines.append("")

    # Alert list
    if priorities["alert_list"]:
        lines.append(">> UNBLOCK NOW (urgent but blocked):")
        for i, r in enumerate(priorities["alert_list"], 1):
            ratio_str = f"{r['urgency_ratio']:.2f}" if r['urgency_ratio'] else "?"
            lines.append(
                f"  {i}. {r['wo_number']} Op {r['next_op_number']} [{r['next_op_work_center'] or '?'}] "
                f"-- Due {r['due_date'][:10] if r['due_date'] else '?'} | "
                f"{r['total_remaining_hours']}h left | ratio: {ratio_str}"
            )
            lines.append(f"     X BLOCKED: {r['blocker']}")
            if r.get("blocker_detail"):
                lines.append(f"     {r['blocker_detail']}")
            if r.get("unblock_by"):
                lines.append(f"     -> Must unblock by: {r['unblock_by']}")
            lines.append("")
    else:
        lines.append(">> UNBLOCK NOW: (none)")
        lines.append("")

    # Queue
    if priorities["queue_list"]:
        lines.append(f">> QUEUE ({len(priorities['queue_list'])} jobs, moderate urgency):")
        for r in priorities["queue_list"][:5]:
            ratio_str = f"{r['urgency_ratio']:.2f}" if r['urgency_ratio'] else "?"
            status = "BLOCKED" if r["blocker"] else "READY"
            lines.append(
                f"  {r['wo_number']} Op {r['next_op_number']} -- "
                f"Due {r['due_date'][:10] if r['due_date'] else '?'} | "
                f"ratio: {ratio_str} | {status}"
            )
        if len(priorities["queue_list"]) > 5:
            lines.append(f"  ... and {len(priorities['queue_list']) - 5} more")
        lines.append("")

    # Backlog
    lines.append(f">> BACKLOG: {len(priorities['backlog_list'])} jobs on track")
    lines.append("")

    # Bottleneck summary
    if priorities["bottleneck_summary"]:
        lines.append("=== BOTTLENECK SUMMARY ===")
        total = sum(priorities["bottleneck_summary"].values())
        for cat, count in sorted(priorities["bottleneck_summary"].items(), key=lambda x: -x[1]):
            pct = round(count / total * 100) if total else 0
            bar = "#" * (pct // 5)
            lines.append(f"  {cat:25s} {count:2d} jobs ({pct:2d}%) {bar}")
        lines.append("")

    # Machine outlook
    lines.append("=== MACHINE OUTLOOK (next 3 days) ===")
    for m in priorities["machine_outlook"]:
        bar = "#" * (m["utilization_pct"] // 5)
        flag = " <- available" if m["utilization_pct"] < 30 else (
            " <- near capacity" if m["utilization_pct"] > 80 else ""
        )
        lines.append(
            f"  {m['name']:25s} {m['scheduled_hours_3d']:5.1f}h / {m['available_hours_3d']}h "
            f"({m['utilization_pct']:2d}%) {bar}{flag}"
        )

    return "\n".join(lines)


def format_bottleneck_report(report):
    """Format bottleneck report dict into readable text."""
    lines = []
    gen = report["generated_at"][:16].replace("T", " ")
    lines.append(f"=== SHOP BOTTLENECK REPORT -- {gen} ===")
    lines.append(f"Jobs at risk: {report['jobs_at_risk']}")
    lines.append("")

    lines.append("Breakdown by primary blocker:")
    for cat, data in report["breakdown"].items():
        bar = "#" * (data["pct"] // 5)
        lines.append(
            f"  {cat:25s} {data['count']:2d} jobs ({data['pct']:2d}%) {bar}"
        )
        if data.get("est_hours_blocked"):
            lines.append(f"  {'':25s} ~{data['est_hours_blocked']}h blocked")
    lines.append("")

    if report["top_bottleneck"]:
        tb = report["top_bottleneck"]
        lines.append(f">> #1 BOTTLENECK: {tb['category']}")
        lines.append(f"   {tb['count']} jobs ({tb['pct']}%) blocked")
        lines.append(f"   Affected: {', '.join(tb['work_orders'][:10])}")
        if len(tb["work_orders"]) > 10:
            lines.append(f"   ... and {len(tb['work_orders']) - 10} more")
        lines.append(f"   Recommendation: {tb['recommendation']}")

    return "\n".join(lines)
