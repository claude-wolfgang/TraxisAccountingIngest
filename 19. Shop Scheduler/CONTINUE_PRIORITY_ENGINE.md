# Priority Engine — Continuation Guide

## What Was Built (April 6, 2026)

### Files Created/Modified
- `priority_engine.py` — Core scoring engine (35/35 tests passing)
- `test_priority_engine.py` — Full test suite with synthetic data
- `SCHEDULING_LOGIC.md` — Complete logic spec (user-approved)
- `app.py` — 4 new endpoints added

### How It Works
1. **Urgency ratio** = total_remaining_hours / business_hours_until_due
   - Computed at WO level across ALL remaining ops (whole chain)
   - 8h/day, mustLeaveBy date, skips weekends
2. **Bottleneck diagnosis** — elimination chain per job:
   - Program? (check prior completed WO with same part_number, or programming op complete)
   - Material? (vendorPO receivedDate)
   - Tooling? (tools_ready manual flag)
   - If all clear + not running → SCHEDULING/MANAGEMENT or CAPACITY
3. **Two output tracks**:
   - ACTION list: inputs ready, ranked by urgency → operator marching orders
   - ALERT list: input-blocked, with back-calculated "unblock by" deadlines
4. **Aggregate bottleneck report**: counts blockers across all at-risk jobs, identifies #1 constraint

### API Endpoints
- `GET /api/priorities` — JSON: action_list, alert_list, queue_list, backlog_list, bottleneck_summary, machine_outlook
- `GET /api/priorities/report` — Plain text daily report (human-readable)
- `GET /api/bottleneck` — JSON: breakdown by blocker category, top_bottleneck with recommendation
- `GET /api/bottleneck/report` — Plain text bottleneck report

---

## What's Next (pick up here)

### Immediate: Test on Live Data
- Start the scheduler and hit `http://localhost:5080/api/priorities/report`
- Review the output against your actual shop knowledge
- Note any jobs that seem mis-ranked or mis-diagnosed — that's calibration data

### Phase 2: UI Panel
- Add a "Priorities" tab/panel in the scheduler frontend
- Show the ranked action list and alert list
- Click a job to highlight it on the Gantt
- Color-code by urgency tier (red/orange/yellow/green)

### Phase 3: Feedback Loop
- New DB table: `priority_overrides` (timestamp, wo, recommended_rank, actual_rank, reason)
- When user reorders or overrides, capture WHY (dropdown + free text)
- Weekly review of override patterns → refine scoring weights

### Phase 4: Bottleneck Trends
- Store weekly bottleneck snapshots in DB
- Show 4-week trend: "Programming was 45% of delays, now down to 20%"
- Track improvement over time

### Phase 5: Autonomous Mode
- System proposes full daily schedule (machine assignments + sequence)
- User approves or tweaks each morning
- Eventually: auto-apply with exception alerts only

---

## Paste This to Start a New Session

```
I'm working on the Shop Scheduler (Project 19). Last session we built the
priority engine — urgency scoring, bottleneck diagnosis, daily action/alert
reports. 35/35 tests passing.

Read these files to get up to speed:
- 19. Shop Scheduler/SCHEDULING_LOGIC.md (the logic spec)
- 19. Shop Scheduler/CONTINUE_PRIORITY_ENGINE.md (this file)
- 19. Shop Scheduler/priority_engine.py (the engine)

[Then tell me what you want to work on next, e.g.:]
- "I tested /api/priorities/report and here's what I saw: ..."
- "Let's build the UI panel"
- "Let's add the feedback logging"
```
