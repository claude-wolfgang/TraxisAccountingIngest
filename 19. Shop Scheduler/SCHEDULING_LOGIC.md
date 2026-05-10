# Traxis Autonomous Scheduling Logic — v0.1

**Goal:** Replace human decision-making for job prioritization with a scoring engine
that ranks jobs and presents a daily action plan. Human approves or overrides.
When overriding, the system asks WHY to learn and refine.

---

## Core Metric: Urgency Ratio

```
urgency_ratio = total_remaining_hours / hours_available_before_due
```

- `total_remaining_hours` = sum of `hoursTarget` across ALL remaining ops on the WO
  (not just the next op — the whole chain matters)
- `hours_available_before_due` = business_days_until_due × 8 (single shift)
- Uses `mustLeaveBy` date (100% populated) as the deadline

### Interpretation:
| Ratio    | Meaning                                    | Action          |
|----------|--------------------------------------------|-----------------|
| > 1.0    | Mathematically cannot finish on time       | RED ALERT       |
| 0.8–1.0  | Cutting it close, no room for error        | CRITICAL        |
| 0.5–0.8  | Needs to start this week                   | START SOON      |
| 0.2–0.5  | Comfortable but on the radar               | QUEUED          |
| < 0.2    | Plenty of time                             | BACKLOG         |

---

## Readiness: Two Tracks, Not a Gate

Readiness is NOT a hard filter. Instead, jobs split into two output streams:

### Track A: ACTION LIST (ready or nearly ready)
Jobs where the next op can physically start. Ranked by urgency ratio.
These are what the operator should run.

### Track B: ALERT LIST (urgent but blocked)
Jobs with high urgency ratio but blocked by readiness issues.
Each alert includes:
- WHAT is blocking (material? program? tools?)
- WHEN does it need to be resolved (back-calculated from due date)
- WHO needs to act (programmer? purchasing? operator?)

**The key insight:** A job with urgency ratio 0.9 that's blocked on material
is MORE important to act on than a ready job with ratio 0.3 — it just needs
a DIFFERENT action (chase the material, not start cutting).

---

## Daily Priority Output

The system generates this every morning (and on-demand):

```
═══ TRAXIS DAILY PRIORITIES — [DATE] ═══

▸ START NOW (ready, high urgency):
  1. WO-XXXX Op 30 [Mill] — Due Apr 8 | 12h left across 3 ops | ratio: 0.94
     → Run on: Mill-3 (suggested, 7/10 tool match)
     Reason: Tightest ratio of all ready jobs. Must start today.

  2. WO-YYYY Op 20 [Lathe] — Due Apr 10 | 6h left across 2 ops | ratio: 0.75
     → Run on: T2-YCM
     Reason: Only lathe job approaching critical. Straightforward.

▸ UNBLOCK NOW (urgent but not ready):
  3. WO-ZZZZ Op 40 [Mill] — Due Apr 9 | 8h left | ratio: 0.87
     ✗ BLOCKED: Program not complete
     → Deadline to unblock: Apr 7 (or job will be late)
     Action: Finish programming WO-ZZZZ today.

  4. WO-AAAA Op 10 [Mill] — Due Apr 11 | 14h left | ratio: 0.70
     ✗ BLOCKED: Material PO outstanding
     → Deadline to unblock: Apr 8
     Action: Check material ETA with supplier.

▸ QUEUE (ready, moderate urgency):
  5. WO-BBBB Op 20 [Mill] — Due Apr 18 | 4h left | ratio: 0.25
  6. WO-CCCC Op 30 [Lathe] — Due Apr 20 | 3h left | ratio: 0.19
  ...

▸ ON TRACK (no action needed today):
  [remaining jobs with low ratios, collapsed]

═══ MACHINE UTILIZATION OUTLOOK ═══
  Mill-1: 14h scheduled next 3 days (58%)
  Mill-3: 22h scheduled next 3 days (92%) ← near capacity
  T2-YCM: 6h scheduled next 3 days (25%) ← available
  ...
```

---

## Feedback Loop

When the user overrides a recommendation:
1. System logs: [timestamp, job, recommended_action, actual_action]
2. System asks: "You moved WO-XXXX ahead of WO-YYYY. Why?"
3. Options presented:
   - Customer called / external pressure
   - I know something the data doesn't (explain)
   - The readiness data is wrong
   - Setup efficiency — I'm already set up for this
   - Other (free text)
4. Over time, patterns in overrides reveal missing factors in the model.

---

## Bottleneck Diagnosis: "What's Slowing Us Down?"

For every job that's behind schedule or stalled, the system diagnoses the root cause
by process of elimination. This works at two levels: per-job and aggregate.

### Per-Job Diagnosis (elimination logic)

For each WO where urgency_ratio > threshold and job is not actively running:

```
1. PROGRAM: Has this part/rev been completed on a previous WO in ProShop?
   YES → Program exists. Not the blocker.
   NO  → Is the Programming op complete on THIS WO?
         YES → Program exists. Not the blocker.
         NO  → ⚑ BLOCKED: PROGRAMMING
              ("New part, program not yet complete")

2. MATERIAL: Has material been received? (receivedDate on all PO items)
   YES → Material on hand. Not the blocker.
   NO POs exist → Assume stock on hand. Not the blocker.
   PO exists, not received → ⚑ BLOCKED: MATERIAL
              ("Material PO outstanding, need by [back-calc date]")

3. TOOLS: Are tools staged for the next op? (tools_ready flag)
   YES → Tools ready. Not the blocker.
   NO  → ⚑ BLOCKED: TOOLING/PERSONNEL
              ("Program and material ready. Tools not staged.
               This is a personnel or staging efficiency gap.")

4. MACHINE CAPACITY: Is a machine available?
   YES, idle → ⚑ BLOCKED: SCHEDULING/MANAGEMENT
              ("Everything ready. Machine available. Job not started.
               This is a scheduling or decision-making gap.")
   NO, all occupied → ⚑ BLOCKED: CAPACITY
              ("Everything ready but all qualified machines occupied.
               Bottleneck is machine hours.")
```

Each job gets tagged with its PRIMARY blocker — the first failing gate in the chain.

### Aggregate Analysis: "The Major Slowing Contributor"

Across all jobs that are behind or at risk (urgency_ratio > 0.5):

```
═══ SHOP BOTTLENECK REPORT — Week of [DATE] ═══

Jobs at risk: 12

Breakdown by primary blocker:
  PROGRAMMING:          2 jobs  (17%)  ░░
  MATERIAL:             1 job   ( 8%)  ░
  TOOLING/PERSONNEL:    5 jobs  (42%)  ░░░░░
  SCHEDULING/MGMT:      3 jobs  (25%)  ░░░
  MACHINE CAPACITY:     1 job   ( 8%)  ░

► #1 BOTTLENECK THIS WEEK: TOOLING/PERSONNEL
  5 jobs had programs and material but sat waiting for tool staging.
  Estimated hours lost: ~18h
  Affected WOs: WO-1234, WO-2345, WO-3456, WO-4567, WO-5678

► TREND (last 4 weeks):
  Week 1: Programming (45%)
  Week 2: Programming (38%)
  Week 3: Tooling (40%)
  Week 4: Tooling (42%)  ← this week
  → Programming improving. Tooling emerging as new constraint.
```

### What This Tells Management

This is the Theory of Constraints made automatic:
- **If PROGRAMMING dominates:** Need more CAM capacity (your time, or outsource)
- **If MATERIAL dominates:** Purchasing/supplier management needs attention
- **If TOOLING/PERSONNEL dominates:** Tool staging process needs a system, or
  need dedicated tool room time/person
- **If SCHEDULING/MGMT dominates:** The decision-making itself is the bottleneck.
  This is what the priority engine fixes.
- **If CAPACITY dominates:** Machines are actually full. Time to look at overtime,
  outsourcing, or a new machine.

The diagnosis shifts over time as you fix constraints. Fix the #1, and #2 becomes
the new #1. That's progress.

### Data Required for Diagnosis

| Check               | Data source                        | Available? |
|---------------------|------------------------------------|-----------|
| Prior WO same part  | ProShop: completed WOs by part/rev | Need to query — part number on WO + historical search |
| Programming op done | ProShop: isOpComplete on Prog op   | ✓ Already in sync |
| Material received   | ProShop: vendorPO receivedDate     | ✓ Partial (material readiness sync) |
| Tools staged        | Scheduler: tools_ready flag        | ✓ Manual toggle |
| Machine available   | Scheduler: Gantt block data        | ✓ Can compute from blocks |

**Gap: "Prior WO same part/rev"** — We need to query ProShop for historical WOs
with the same part number to determine if this is a repeat job. This is the key
new data point needed.

---

## What We Already Have (in the Scheduler)

| Data point              | Available? | Source           |
|-------------------------|-----------|------------------|
| Due date / mustLeaveBy  | ✓ 100%   | ProShop sync     |
| Hours target per op     | ✓ 100%   | ProShop sync     |
| Operation sequence      | ✓        | ProShop sync     |
| Op completion status    | ✓        | ProShop sync     |
| Program readiness       | ✓        | Computed in sync |
| Material readiness      | ~partial | vendorPOs query  |
| Tool readiness          | ✓        | Manual toggle    |
| Machine readiness       | ✓        | Tool overlap     |
| Machine assignments     | ✓        | Scheduler blocks |
| Actual cycle times      | ✗        | Need FOCAS data  |

---

## What Needs to Be Built

1. **`priority_engine.py`** — Computes urgency ratios, splits into action/alert tracks,
   generates the ranked output. Pure logic, no UI.

2. **`/api/priorities` endpoint** — Serves the daily priority view as JSON.

3. **Priority Panel in UI** — New panel in scheduler showing the ranked list.
   Click a job to see it on the Gantt. Override buttons with feedback capture.

4. **Alert system** — Surface "unblock by" deadlines. Could tie into Message Notifier
   (Project 18) for push notifications.

5. **Feedback logging** — SQLite table recording overrides and reasons.
   Review periodically to refine the model.

---

## Future: Autonomous Mode

Once the scoring model is validated through weeks of use + feedback:
- System auto-assigns jobs to machines based on urgency + tool overlap
- System auto-sequences the day's work
- Human reviews and approves the plan each morning (or gets notified of exceptions)
- Eventually: system just runs, human intervenes only on red alerts

---

## Design Principles

1. **Show your work.** Every recommendation includes a one-line "Reason:" so the
   human can evaluate the logic, not just the output.
2. **Two tracks, not one list.** Ready-to-run and needs-action are different workflows.
   Don't mix them.
3. **Back-calculate deadlines.** Don't just say "material is missing." Say "material
   must arrive by Tuesday or WO-XXXX will be late."
4. **Learn from overrides.** Every human correction is training data.
5. **Degrade gracefully.** Missing data (no hours estimate, no readiness) = flag it,
   don't crash. Show what you know, be honest about what you don't.
