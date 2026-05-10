"""Auto-scheduling suggestion engine.

Analyzes unscheduled ops and current machine load to produce
per-operation suggestions: best machine + time slot with reasoning.
"""

from datetime import datetime, timedelta

import config
from database import get_db, get_operations, get_machines, get_readiness


def _parse_dt(s):
    """Parse ISO datetime string to naive datetime (strip timezone if present)."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00") if s.endswith("Z") else s)
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# Machine IDs for mills (used when distributing MILL-X ops)
MILL_IDS = [f"mill-{i}" for i in range(1, 9)]
LATHE_ID = "t2"
URGENT_DAYS = 3  # ops due within this many days get priority scheduling
MAX_OP_HOURS = 80  # sanity cap — flag ops claiming more than this

# Robodrills are BT30 with limited milling capability — never auto-assign
# ops to these unless they have historical evidence of running on one.
ROBODRILL_IDS = {"mill-4", "mill-5", "mill-7"}
# Full-size mills safe for general auto-assignment
FULL_SIZE_MILL_IDS = [m for m in MILL_IDS if m not in ROBODRILL_IDS]
# CAT40 taper mills (all full-size mills)
CAT40_MILL_IDS = {"mill-1", "mill-2", "mill-3", "mill-6", "mill-8"}
# Probe-capable mills (subset of CAT40)
PROBE_MILL_IDS = {"mill-1", "mill-2", "mill-3", "mill-8"}
# SET1 parts default to Mill-7 (5-axis Robodrill)
SET1_DEFAULT_MACHINE = "mill-7"


def get_suggestions(conn=None):
    """Return a list of scheduling suggestions for all unscheduled schedulable ops.

    Each suggestion: {op_id, machine_id, machine_name, start_time, end_time,
                      duration_hours, reasons, urgency}
    """
    close = conn is None
    if close:
        conn = get_db()

    ops = get_operations(conn=conn, unscheduled_only=True, schedulable_only=True)
    machines_list = get_machines(conn=conn)
    machine_names = {m["id"]: m["name"] for m in machines_list}

    bh_start = int(conn.execute(
        "SELECT value FROM settings WHERE key='business_hours_start'"
    ).fetchone()[0])
    bh_end = int(conn.execute(
        "SELECT value FROM settings WHERE key='business_hours_end'"
    ).fetchone()[0])

    now = datetime.now()

    # Pre-compute machine loads for the next 5 business days
    search_end = _add_business_days(now, 5, bh_start, bh_end)
    mill_loads = {
        mid: _machine_load(conn, mid, now, search_end)
        for mid in MILL_IDS
    }

    suggestions = []
    skipped = []  # ops that can't be auto-scheduled, with reasons
    # Track tentative assignments so suggestions don't overlap each other
    tentative_blocks = []  # [(machine_id, start, end), ...]

    # Sort ops: urgent first (past-due, then due within URGENT_DAYS), then by due date
    ops.sort(key=lambda o: (_urgency_sort_key(o.get("due_date")), o.get("due_date") or "9999"))

    for op in ops:
        duration_hours = op.get("override_hours") or op.get("est_hours") or (
            config.DEFAULT_OP_DURATION_MIN / 60
        )
        due_date = op.get("due_date")
        urgency = _urgency_label(due_date)
        reasons = []

        # Sanity check: flag absurd durations
        if duration_hours > MAX_OP_HOURS:
            skipped.append({
                "op_id": op["id"],
                "reason": f"Duration too large ({duration_hours:,.0f}h) — likely bad data from ProShop",
            })
            continue

        # Determine candidate machine(s)
        assigned_machine = op.get("machine_id")
        is_urgent = urgency in ("past-due", "urgent")

        part_number = op.get("part_number") or ""
        is_set1 = part_number.upper().startswith("SET1")

        if assigned_machine:
            candidates = [assigned_machine]
            reasons.append("Assigned per ProShop")
        elif is_set1:
            # SET1 parts default to Mill-7 (5-axis Robodrill)
            candidates = [SET1_DEFAULT_MACHINE]
            reasons.append("SET1 part — defaults to Mill-7 (5-axis)")
        else:
            # No work cell assigned — check if this part/op was run before
            hist_machine = _find_historical_machine(
                conn, part_number, op.get("op_name")
            )

            # Narrow candidate pool by work center capability
            work_center = (op.get("work_center") or "").upper()
            if work_center == "MILL-X-PROBE":
                pool = list(PROBE_MILL_IDS)
                reasons.append("Probe-capable mills only")
            elif work_center == "MILL-X-CAT40":
                pool = list(CAT40_MILL_IDS)
                reasons.append("CAT40 mills only")
            else:
                pool = list(FULL_SIZE_MILL_IDS)

            if is_urgent and not hist_machine:
                # Urgent + no history: search pool for earliest slot
                candidates = pool
                reasons.append("Earliest available — " + ("past due" if urgency == "past-due" else "due soon"))
            elif hist_machine:
                candidates = [hist_machine]
                reasons.append(f"Previously run on {machine_names.get(hist_machine, hist_machine)}")
                if is_urgent:
                    # Also check other safe mills in case the historical one is packed
                    if hist_machine in ROBODRILL_IDS:
                        # History is on a robodrill — only fall back to other robodrills or pool
                        candidates = [hist_machine] + pool
                    else:
                        candidates = [hist_machine] + [m for m in pool if m != hist_machine]
            else:
                # No history, not urgent → pick lightest-loaded mill from pool
                # Use tool overlap as tiebreaker among similarly-loaded mills
                sorted_mills = sorted(pool, key=lambda mid: mill_loads.get(mid, 0))
                lightest_load = mill_loads.get(sorted_mills[0], 0)
                # Mills within 2h of lightest are considered "similar load"
                similar = [m for m in sorted_mills if mill_loads.get(m, 0) <= lightest_load + 2]
                if len(similar) > 1:
                    # Tiebreak by tool overlap
                    best_tool_mill = max(similar, key=lambda mid: _tool_overlap_score(conn, op["id"], mid)[2])
                    score = _tool_overlap_score(conn, op["id"], best_tool_mill)
                    candidates = [best_tool_mill]
                    if score[1] > 0:
                        reasons.append(f"Best tool match ({score[0]}/{score[1]} tools) on {machine_names.get(best_tool_mill, best_tool_mill)}")
                    else:
                        reasons.append(f"Lightest load among mills ({machine_names.get(best_tool_mill, best_tool_mill)})")
                else:
                    lightest = sorted_mills[0]
                    candidates = [lightest]
                    reasons.append(f"Lightest load among mills ({machine_names.get(lightest, lightest)})")

        # Find best slot across candidates
        best = None
        for mid in candidates:
            slot = _find_next_gap(
                conn, mid, duration_hours, now, bh_start, bh_end, tentative_blocks
            )
            if slot and (best is None or slot[0] < best[1]):
                best = (mid, slot[0], slot[1])

        if not best:
            # Mark machine_ready=0 for skipped ops
            conn.execute("""
                INSERT INTO readiness (operation_id, machine_ready, updated_at)
                VALUES (?, 0, datetime('now'))
                ON CONFLICT(operation_id) DO UPDATE SET
                    machine_ready=0, updated_at=datetime('now')
            """, (op["id"],))
            skipped.append({
                "op_id": op["id"],
                "reason": f"No open slot within 30 days ({duration_hours:.1f}h needed)",
            })
            continue

        machine_id, start, end = best
        reasons.append("Next available slot")

        # Update machine_ready in readiness table
        conn.execute("""
            INSERT INTO readiness (operation_id, machine_ready, updated_at)
            VALUES (?, 1, datetime('now'))
            ON CONFLICT(operation_id) DO UPDATE SET
                machine_ready=1, updated_at=datetime('now')
        """, (op["id"],))

        # Track this tentative assignment for gap-finding
        tentative_blocks.append((machine_id, start, end))
        # Update load tracking
        added_hours = (end - start).total_seconds() / 3600
        if machine_id in mill_loads:
            mill_loads[machine_id] += added_hours

        # Compute tool overlap for the chosen machine
        tool_score = _tool_overlap_score(conn, op["id"], machine_id)

        suggestions.append({
            "op_id": op["id"],
            "machine_id": machine_id,
            "machine_name": machine_names.get(machine_id, machine_id),
            "start_time": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_hours": round(duration_hours, 2),
            "reasons": reasons,
            "urgency": urgency,
            "tool_match": tool_score[0],
            "tool_total": tool_score[1],
        })

    conn.commit()

    if close:
        conn.close()

    return {"suggestions": suggestions, "skipped": skipped}


def _find_historical_machine(conn, part_number, op_name):
    """Check if this part+op combo was previously run on a machine.

    Looks at completed schedule blocks for operations with the same
    part_number and op_name. Returns the most recently used machine_id,
    or None.
    """
    if not part_number or not op_name:
        return None

    row = conn.execute(
        """SELECT sb.machine_id, MAX(sb.start_time) as last_run
           FROM schedule_blocks sb
           JOIN operations o ON sb.operation_id = o.id
           JOIN work_orders w ON o.wo_number = w.wo_number
           WHERE w.part_number = ? AND o.op_name = ?
             AND sb.status IN ('complete', 'running')
           GROUP BY sb.machine_id
           ORDER BY last_run DESC
           LIMIT 1""",
        (part_number, op_name)
    ).fetchone()

    return row["machine_id"] if row else None


def _machine_load(conn, machine_id, start, end):
    """Total scheduled hours on a machine between start and end."""
    rows = conn.execute(
        """SELECT start_time, end_time FROM schedule_blocks
           WHERE machine_id = ? AND status != 'complete'
           AND end_time > ? AND start_time < ?""",
        (machine_id, start.isoformat(), end.isoformat())
    ).fetchall()

    total = 0.0
    for r in rows:
        s = max(_parse_dt(r["start_time"]), start)
        e = min(_parse_dt(r["end_time"]), end)
        if e > s:
            total += (e - s).total_seconds() / 3600
    return total


def _find_next_gap(conn, machine_id, duration_hours, search_from, bh_start, bh_end, tentative_blocks=None):
    """Find the next contiguous gap >= duration_hours on a machine.

    Respects business hours. Returns (start, end) or None.
    """
    if duration_hours <= 0:
        duration_hours = config.DEFAULT_OP_DURATION_MIN / 60

    duration_td = timedelta(hours=duration_hours)
    horizon = search_from + timedelta(days=30)  # search up to 30 days out

    # Get existing blocks on this machine, sorted by start
    rows = conn.execute(
        """SELECT start_time, end_time FROM schedule_blocks
           WHERE machine_id = ? AND status != 'complete'
           AND end_time > ? AND start_time < ?
           ORDER BY start_time""",
        (machine_id, search_from.isoformat(), horizon.isoformat())
    ).fetchall()

    blocks = [(_parse_dt(r["start_time"]), _parse_dt(r["end_time"])) for r in rows]

    # Add tentative blocks for this machine
    if tentative_blocks:
        for mid, ts, te in tentative_blocks:
            if mid == machine_id:
                blocks.append((ts, te))
        blocks.sort(key=lambda b: b[0])

    # Start searching from the next valid business hour
    cursor = _next_business_hour(search_from, bh_start, bh_end)

    for _ in range(5000):  # safety limit
        if cursor >= horizon:
            return None

        # Ensure cursor is within business hours
        cursor = _next_business_hour(cursor, bh_start, bh_end)

        # Calculate end using business hours only (skips nights and weekends)
        slot_end = _add_business_hours(cursor, duration_hours, bh_start, bh_end)

        # Check for overlap with any existing block
        conflict = False
        for bs, be in blocks:
            if cursor < be and slot_end > bs:
                # Overlap — advance cursor past this block
                cursor = be
                conflict = True
                break

        if not conflict:
            return (cursor, slot_end)

    return None


def _next_business_hour(dt, bh_start, bh_end):
    """Advance dt to the next valid business hour if it's outside hours or on weekend."""
    # Skip weekends
    while dt.weekday() >= 5:  # Saturday=5, Sunday=6
        dt = (dt + timedelta(days=1)).replace(hour=bh_start, minute=0, second=0, microsecond=0)

    if dt.hour < bh_start:
        dt = dt.replace(hour=bh_start, minute=0, second=0, microsecond=0)
    elif dt.hour >= bh_end:
        dt = (dt + timedelta(days=1)).replace(hour=bh_start, minute=0, second=0, microsecond=0)
        # Skip weekends again
        while dt.weekday() >= 5:
            dt = (dt + timedelta(days=1)).replace(hour=bh_start, minute=0, second=0, microsecond=0)

    return dt


def _next_business_day(dt, bh_start):
    """Advance to the start of the next business day."""
    dt = (dt + timedelta(days=1)).replace(hour=bh_start, minute=0, second=0, microsecond=0)
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt


def _add_business_hours(start, hours, bh_start, bh_end):
    """Add hours of business time to a start datetime, skipping nights and weekends."""
    remaining = hours
    cursor = start
    bh_per_day = bh_end - bh_start

    for _ in range(500):  # safety limit
        if remaining <= 0:
            break

        # Make sure we're in business hours
        cursor = _next_business_hour(cursor, bh_start, bh_end)

        # Hours left in the current business day
        day_end = cursor.replace(hour=bh_end, minute=0, second=0, microsecond=0)
        available = (day_end - cursor).total_seconds() / 3600

        if remaining <= available:
            cursor += timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= available
            cursor = _next_business_day(cursor, bh_start)

    return cursor


def _add_business_days(dt, days, bh_start, bh_end):
    """Add N business days to a datetime."""
    result = dt
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result.replace(hour=bh_end, minute=0, second=0, microsecond=0)


def _urgency_sort_key(due_date_str):
    """Return a sort key: 0=past-due, 1=urgent, 2=normal, 3=no date."""
    if not due_date_str:
        return 3
    try:
        due = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
        days = (due - datetime.now()).days
        if days < 0:
            return 0
        if days < URGENT_DAYS:
            return 1
        return 2
    except (ValueError, TypeError):
        return 3


def _urgency_label(due_date_str):
    """Return urgency label: past-due, urgent, normal, or none."""
    if not due_date_str:
        return "none"
    try:
        due = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
        days = (due - datetime.now()).days
        if days < 0:
            return "past-due"
        if days < URGENT_DAYS:
            return "urgent"
        return "normal"
    except (ValueError, TypeError):
        return "none"


def _tool_overlap_score(conn, operation_id, machine_id):
    """Compare operation_tools vs machine_pockets by tool_number AND out_of_holder.

    Returns (matched, total, ratio) where:
    - matched = number of op tools already in machine pockets
    - total = total tools needed by the operation
    - ratio = matched/total (0.0 if no tools)
    """
    op_tools = conn.execute(
        "SELECT tool_number, out_of_holder FROM operation_tools WHERE operation_id=?",
        (operation_id,)
    ).fetchall()

    if not op_tools:
        return (0, 0, 0.0)

    machine_pockets = conn.execute(
        "SELECT tool_number, out_of_holder FROM machine_pockets WHERE machine_id=? AND tool_number IS NOT NULL",
        (machine_id,)
    ).fetchall()

    # Build set of (tool_number, out_of_holder) in machine — stickout tolerance of 0.1"
    pocket_set = [(p["tool_number"], p["out_of_holder"]) for p in machine_pockets]

    total = len(op_tools)
    matched = 0
    for ot in op_tools:
        ot_num = ot["tool_number"]
        ot_stickout = ot["out_of_holder"]
        for pt_num, pt_stickout in pocket_set:
            if pt_num == ot_num:
                # Tool number matches — check stickout compatibility
                if ot_stickout is None or pt_stickout is None:
                    # No stickout data — count as match on tool number alone
                    matched += 1
                    break
                elif round(abs(ot_stickout - pt_stickout), 4) <= 0.1:
                    matched += 1
                    break

    ratio = matched / total if total > 0 else 0.0
    return (matched, total, ratio)
