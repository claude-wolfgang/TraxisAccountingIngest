"""Tests for priority_engine.py — runs against synthetic data, no ProShop needed."""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

# Ensure we can import from the scheduler directory
sys.path.insert(0, os.path.dirname(__file__))

# Set dummy env var so config doesn't fail
os.environ.setdefault("PROSHOP_CLIENT_SECRET", "test")

from priority_engine import (
    compute_priorities, generate_bottleneck_report,
    format_daily_report, format_bottleneck_report,
    _business_hours_between, _subtract_business_hours,
    _score_work_order, _diagnose_blocker, _snap_to_bh,
    BH_START, BH_END, BH_PER_DAY,
    BLOCKER_PROGRAMMING, BLOCKER_MATERIAL, BLOCKER_TOOLING,
    BLOCKER_SCHEDULING, BLOCKER_CAPACITY,
)
from database import SCHEMA


def _make_db():
    """Create in-memory DB with schema and test data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")  # Allow test data without full FK chain
    conn.executescript(SCHEMA)
    # Run lightweight migrations that production uses
    try:
        conn.execute("ALTER TABLE work_orders ADD COLUMN material_type TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE work_orders ADD COLUMN hidden INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE operations ADD COLUMN hidden INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # Seed machines
    machines = [
        ("mill-1", "Haas VF5", "mill", 1),
        ("mill-2", "Smec #1", "mill", 2),
        ("mill-3", "Smec #2", "mill", 3),
        ("t2", "YCM NTC1600LY", "lathe", 9),
    ]
    conn.executemany(
        "INSERT INTO machines (id, name, type, sort_order, is_active) VALUES (?, ?, ?, ?, 1)",
        machines,
    )

    # Settings
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        [("business_hours_start", "5"), ("business_hours_end", "18")],
    )

    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)
    two_weeks = today + timedelta(days=14)

    # WO-001: Urgent, ready to run (repeat part)
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("001", "PART-A", "Widget A", "Acme Corp", tomorrow.strftime("%Y-%m-%d"), "active"),
    )
    conn.execute(
        "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("001-10", "001", 10, "Mill Op 1", "Mill-1", 8.0, 0),
    )
    conn.execute(
        "INSERT INTO readiness (operation_id, program_ready, material_ready, tools_ready, machine_ready) "
        "VALUES (?, 1, 1, 1, 1)",
        ("001-10",),
    )

    # WO-002: Urgent, blocked on material
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("002", "PART-B", "Bracket B", "Boeing", tomorrow.strftime("%Y-%m-%d"), "active"),
    )
    conn.execute(
        "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("002-10", "002", 10, "Mill Op 1", "Mill-2", 6.0, 0),
    )
    conn.execute(
        "INSERT INTO readiness (operation_id, program_ready, material_ready, tools_ready, machine_ready, material_detail) "
        "VALUES (?, 1, 0, 0, 1, ?)",
        ("002-10", '{"status": "ordered"}'),
    )

    # WO-003: Moderate urgency, blocked on programming (new part)
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("003", "PART-C-NEW", "New Part C", "SpaceX", next_week.strftime("%Y-%m-%d"), "active"),
    )
    conn.execute(
        "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("003-5", "003", 5, "Programming", "PROG", None, 0),
    )
    conn.execute(
        "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("003-10", "003", 10, "Mill Op 1", "Mill-3", 12.0, 0),
    )
    conn.execute(
        "INSERT INTO readiness (operation_id, program_ready, material_ready, tools_ready, machine_ready) "
        "VALUES (?, 0, 1, 0, 1)",
        ("003-10",),
    )

    # WO-004: Low urgency, all ready
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("004", "PART-D", "Spacer D", "NASA", two_weeks.strftime("%Y-%m-%d"), "active"),
    )
    conn.execute(
        "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("004-10", "004", 10, "Mill Op 1", "Mill-1", 3.0, 0),
    )
    conn.execute(
        "INSERT INTO readiness (operation_id, program_ready, material_ready, tools_ready, machine_ready) "
        "VALUES (?, 1, 1, 1, 1)",
        ("004-10",),
    )

    # WO-005: Urgent, tools not staged (program + material ready)
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("005", "PART-A", "Widget A Rev2", "Acme Corp",
         (today + timedelta(days=2)).strftime("%Y-%m-%d"), "active"),
    )
    conn.execute(
        "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("005-10", "005", 10, "Mill Op 1", "Mill-1", 10.0, 0),
    )
    conn.execute(
        "INSERT INTO readiness (operation_id, program_ready, material_ready, tools_ready, machine_ready) "
        "VALUES (?, 1, 1, 0, 1)",
        ("005-10",),
    )

    # A completed WO for PART-A (repeat part detection)
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("OLD-001", "PART-A", "Widget A", "Acme Corp", "2025-01-01", "complete"),
    )

    # WO-006: Multi-op job, partially complete
    conn.execute(
        "INSERT INTO work_orders (wo_number, part_number, part_name, customer, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("006", "PART-E", "Housing E", "Lockheed",
         (today + timedelta(days=5)).strftime("%Y-%m-%d"), "active"),
    )
    for op_num, hours, complete in [(10, 4.0, 1), (20, 6.0, 0), (30, 3.0, 0)]:
        conn.execute(
            "INSERT INTO operations (id, wo_number, op_number, op_name, work_center, est_hours, is_complete) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"006-{op_num}", "006", op_num, f"Mill Op {op_num//10}", "Mill-1", hours, complete),
        )
    conn.execute(
        "INSERT INTO readiness (operation_id, program_ready, material_ready, tools_ready, machine_ready) "
        "VALUES (?, 1, 1, 1, 1)",
        ("006-20",),
    )

    conn.commit()
    return conn


passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")


print("=" * 60)
print("PRIORITY ENGINE TESTS")
print("=" * 60)

# ── Test 1: Business hours calculation ───────────────────────────────────────
print("\n--- Test 1: Business hours calculation ---")

# Same day, within BH
start = datetime(2026, 4, 7, 8, 0)  # Tuesday 8 AM
end = datetime(2026, 4, 7, 16, 0)   # Tuesday 4 PM
hours = _business_hours_between(start, end)
check("Same day 8AM-4PM = 8h", abs(hours - 8.0) < 0.01, f"got {hours}")

# Overnight
start = datetime(2026, 4, 7, 16, 0)  # Tuesday 4 PM
end = datetime(2026, 4, 8, 10, 0)    # Wednesday 10 AM
hours = _business_hours_between(start, end)
# Tue 4PM-6PM = 2h, Wed 5AM-10AM = 5h = 7h
check("Overnight Tue 4PM - Wed 10AM = 7h", abs(hours - 7.0) < 0.01, f"got {hours}")

# Over weekend
start = datetime(2026, 4, 10, 12, 0)  # Friday noon
end = datetime(2026, 4, 13, 12, 0)    # Monday noon
hours = _business_hours_between(start, end)
# Fri noon-6PM = 6h, Mon 5AM-noon = 7h = 13h
check("Weekend Fri noon - Mon noon = 13h", abs(hours - 13.0) < 0.01, f"got {hours}")

# ── Test 2: Urgency ratio scoring ────────────────────────────────────────────
print("\n--- Test 2: Urgency ratio scoring ---")

conn = _make_db()
priorities = compute_priorities(conn, today=datetime.now())

# WO-001 should be actionable (all lights green) — either action or queue depending on time-of-day
action_wos = [r["wo_number"] for r in priorities["action_list"]]
alert_wos = [r["wo_number"] for r in priorities["alert_list"]]
queue_wos = [r["wo_number"] for r in priorities["queue_list"]]
backlog_wos = [r["wo_number"] for r in priorities["backlog_list"]]

# WO-001 is ready — should be in action or queue, NOT alerts (it has no input blocker)
check("WO-001 actionable (not in alerts)", "001" not in alert_wos,
      f"alerts: {alert_wos}")
check("WO-001 in action or queue", "001" in action_wos or "001" in queue_wos,
      f"action: {action_wos}, queue: {queue_wos}")

# WO-002 is blocked on material — should be in alerts (if urgent enough) or queue with blocker
check("WO-002 has material blocker",
      any(r["wo_number"] == "002" and r["blocker"] == BLOCKER_MATERIAL
          for r in priorities["alert_list"] + priorities["queue_list"]),
      f"alerts: {alert_wos}, queue: {queue_wos}")

# WO-004 should be in queue or backlog (low urgency, 2 weeks out)
check("WO-004 in queue or backlog", "004" in queue_wos or "004" in backlog_wos,
      f"queue: {queue_wos}, backlog: {backlog_wos}")

# ── Test 3: Blocker diagnosis ────────────────────────────────────────────────
print("\n--- Test 3: Blocker diagnosis ---")

# Gather all results for lookup
all_results = priorities["action_list"] + priorities["alert_list"] + priorities["queue_list"] + priorities["backlog_list"]

# WO-001: ready, no input blocker (may have SCHEDULING diagnostic label)
wo001 = next((r for r in all_results if r["wo_number"] == "001"), None)
check("WO-001 no input blocker",
      wo001 and wo001["blocker"] not in (BLOCKER_PROGRAMMING, BLOCKER_MATERIAL, BLOCKER_TOOLING),
      f"blocker: {wo001['blocker'] if wo001 else 'NOT FOUND'}")

# WO-002: blocked on material
wo002 = next((r for r in all_results if r["wo_number"] == "002"), None)
check("WO-002 blocked on MATERIAL", wo002 and wo002["blocker"] == BLOCKER_MATERIAL,
      f"blocker: {wo002['blocker'] if wo002 else 'NOT FOUND'}")

# WO-005: blocked on tooling (program + material ready, tools not)
wo005 = next((r for r in all_results if r["wo_number"] == "005"), None)
check("WO-005 blocked on TOOLING", wo005 and wo005["blocker"] == BLOCKER_TOOLING,
      f"blocker: {wo005['blocker'] if wo005 else 'NOT FOUND'}")

# WO-003: blocked on programming (new part)
wo003 = next((r for r in all_results if r["wo_number"] == "003"), None)
check("WO-003 blocked on PROGRAMMING", wo003 and wo003["blocker"] == BLOCKER_PROGRAMMING,
      f"blocker: {wo003['blocker'] if wo003 else 'NOT FOUND'}")

# ── Test 4: Repeat part detection ────────────────────────────────────────────
print("\n--- Test 4: Repeat part detection ---")

# PART-A has a completed WO (OLD-001)
check("WO-001 detected as repeat part", wo001 and wo001["is_repeat_part"] is True,
      f"is_repeat: {wo001.get('is_repeat_part') if wo001 else 'NOT FOUND'}")

# WO-003 (PART-C-NEW) has no prior WO
check("WO-003 detected as new part", wo003 and wo003["is_repeat_part"] is False,
      f"is_repeat: {wo003.get('is_repeat_part') if wo003 else 'NOT FOUND'}")

# ── Test 5: Multi-op remaining hours ─────────────────────────────────────────
print("\n--- Test 5: Multi-op chain (WO-006) ---")

wo006 = next((r for r in all_results if r["wo_number"] == "006"), None)
check("WO-006 found", wo006 is not None)
if wo006:
    # Op 10 is complete (4h), Op 20 (6h) + Op 30 (3h) remain = 9h
    check("WO-006 remaining hours = 9.0",
          abs(wo006["total_remaining_hours"] - 9.0) < 0.1,
          f"got {wo006['total_remaining_hours']}")
    check("WO-006 remaining ops = 2", wo006["remaining_ops"] == 2,
          f"got {wo006['remaining_ops']}")
    check("WO-006 next op is Op 20", wo006["next_op_number"] == 20,
          f"got {wo006['next_op_number']}")

# ── Test 6: Unblock deadlines ────────────────────────────────────────────────
print("\n--- Test 6: Unblock-by deadlines ---")

if wo002:
    check("WO-002 has unblock_by date", wo002.get("unblock_by") is not None,
          f"unblock_by: {wo002.get('unblock_by')}")

# ── Test 7: Bottleneck report ────────────────────────────────────────────────
print("\n--- Test 7: Bottleneck report ---")

report = generate_bottleneck_report(conn, today=datetime.now())
check("Bottleneck report generated", report is not None)
check("Has jobs_at_risk count", report["jobs_at_risk"] > 0,
      f"got {report['jobs_at_risk']}")
check("Has breakdown", len(report["breakdown"]) > 0,
      f"categories: {list(report['breakdown'].keys())}")

if report["top_bottleneck"]:
    check("Top bottleneck identified",
          report["top_bottleneck"]["category"] in (
              BLOCKER_PROGRAMMING, BLOCKER_MATERIAL, BLOCKER_TOOLING,
              BLOCKER_SCHEDULING, BLOCKER_CAPACITY),
          f"category: {report['top_bottleneck']['category']}")
    check("Has recommendation", len(report["top_bottleneck"]["recommendation"]) > 0)

# ── Test 8: Text report formatting ───────────────────────────────────────────
print("\n--- Test 8: Text report formatting ---")

text = format_daily_report(priorities)
check("Daily report not empty", len(text) > 100, f"length: {len(text)}")
check("Contains START NOW section", "START NOW" in text)
check("Contains UNBLOCK NOW section", "UNBLOCK NOW" in text)
check("Contains MACHINE OUTLOOK", "MACHINE OUTLOOK" in text)

bottleneck_text = format_bottleneck_report(report)
check("Bottleneck report not empty", len(bottleneck_text) > 50)
check("Contains BOTTLENECK", "BOTTLENECK" in bottleneck_text)

# ── Test 9: Machine outlook ─────────────────────────────────────────────────
print("\n--- Test 9: Machine outlook ---")

check("Machine outlook populated", len(priorities["machine_outlook"]) > 0,
      f"count: {len(priorities['machine_outlook'])}")
for m in priorities["machine_outlook"]:
    check(f"  {m['name']}: utilization is a number",
          isinstance(m["utilization_pct"], (int, float)),
          f"got {m['utilization_pct']}")

# ── Test 10: Action list is ranked ───────────────────────────────────────────
print("\n--- Test 10: Action list ranking ---")

# Action + queue combined should have ready items
ready_items = [r for r in priorities["action_list"] + priorities["queue_list"]
               if r["blocker"] not in (BLOCKER_PROGRAMMING, BLOCKER_MATERIAL, BLOCKER_TOOLING)]
check("Ready items exist in action/queue", len(ready_items) >= 1,
      f"count: {len(ready_items)}")
# If multiple action items, check ordering
if len(priorities["action_list"]) >= 2:
    ratios = [r["urgency_ratio"] for r in priorities["action_list"]]
    check("Action list sorted by urgency (highest first)",
          all(ratios[i] >= ratios[i+1] for i in range(len(ratios)-1)),
          f"ratios: {ratios}")

conn.close()

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
print("=" * 60)

# Print sample report for visual inspection
print("\n\nSAMPLE DAILY REPORT:")
print("-" * 60)
conn = _make_db()
priorities = compute_priorities(conn, today=datetime.now())
print(format_daily_report(priorities))
print("\n\nSAMPLE BOTTLENECK REPORT:")
print("-" * 60)
report = generate_bottleneck_report(conn, today=datetime.now())
print(format_bottleneck_report(report))
conn.close()

sys.exit(1 if failed > 0 else 0)
