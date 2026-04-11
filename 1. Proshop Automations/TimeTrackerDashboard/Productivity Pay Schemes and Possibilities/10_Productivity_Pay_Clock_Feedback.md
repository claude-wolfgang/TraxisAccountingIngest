# Productivity Pay & Clock Feedback Display

**Date:** January 23, 2026  
**Project Status:** ✅ Phase 1 Complete  
**Related Files:** `clock_feedback_display_v1_0_0.py`, `proshop_time_tracking_test_v1_0_1.py`

---

## Overview

This project implements an employee feedback system tied to a productivity-based pay incentive scheme. The goal is to provide real-time feedback to employees at clock-in/out to reinforce productive behaviors and create a direct connection between effort and reward.

---

## Productivity Pay Scheme Options

Three alternative schemes were evaluated:

### Option 1: Efficiency Bonus (Beat the Estimate)

Compare actual vs. quoted hours per job; share savings when jobs complete under budget.

| Aspect | Detail |
|--------|--------|
| Structure | Hours saved × $/hr rate → split among contributors |
| Example | Job quoted 8 hrs, done in 6 → $50 pool at $25/hr saved |
| Guardrails | Quality gate (no bonus if rework), minimum job size threshold |
| Pros | Direct effort-reward link, encourages process improvement |
| Cons | Risk of gaming estimates, admin overhead per job |

### Option 2: Team Scorecard Bonus (Balanced Metrics)

Monthly bonus pool based on weighted team performance across multiple metrics.

| Metric | Weight | Target |
|--------|--------|--------|
| Revenue shipped | 40% | $X/month |
| First-pass yield | 30% | 95%+ |
| On-time delivery | 20% | 90%+ |
| Safety/housekeeping | 10% | Discretionary |

| Aspect | Detail |
|--------|--------|
| Structure | Weighted average score × base pool → divide by headcount |
| Pros | Balances speed/quality/delivery, hard to game |
| Cons | Weak individual incentive, delayed monthly feedback |

### Option 3: Gain Sharing (Profit Participation)

Share percentage of gross profit above baseline threshold.

| Aspect | Detail |
|--------|--------|
| Structure | (Profit − baseline) × share % → divide among employees |
| Example | $55k profit − $40k baseline = $15k × 20% = $3k pool |
| Pros | Aligns with business health, simple to administer |
| Cons | Abstract connection to individual effort |

### Recommended Approach

Given the planned machine utilization monitoring system, a **utilization-based bonus** was selected:

- **Metric:** Shop-wide average spindle utilization
- **Baseline:** ~35% (calibrate after initial data collection)
- **Bonus:** $X per percentage point above baseline, per employee
- **Quality Gate:** First-pass yield must be ≥ 90%
- **Payout:** Monthly

**Logic:** If all jobs are profitable (even slightly), then maximizing spindle time = maximizing profit. Machine monitoring provides objective, automated data.

---

## Psychology Principles for Incentive Effectiveness

### 1. Immediacy (Temporal Proximity)
- Shorter gap between action and reward = stronger reinforcement
- Real-time display on shop floor is highest impact
- Daily/shift feedback, monthly payout

### 2. Perceived Control (Agency)
- Exclude factors outside employee control (machine downtime, material delays)
- Employees must understand what actions move the number

### 3. Visibility and Salience
- Big, visible dashboard showing live utilization
- What gets measured and displayed gets attention

### 4. Goal Setting
- Specific, challenging-but-achievable targets
- "50% utilization this month" beats "do better"

### 5. Loss Aversion (Framing)
- Frame as protecting existing bonus rather than earning new one
- "On track for $340" creates something to defend

### 6. Fairness and Transparency
- Show exactly how number is calculated
- Equal split or clear agreed weighting
- No black boxes

### 7. Team Dynamics
- Team-based incentives suit small shops
- Reinforces collaboration over competition

### 8. Progress Visibility (Small Wins)
- Show week-over-week improvement
- Celebrate milestones and records

---

## Clock-In/Out Feedback Display

### Concept

When employees clock in/out via ProShop, a dedicated display shows:

**Clock In:**
```
Good morning, Chris                         Thu Jan 23

YESTERDAY:  8.2 hrs    THIS WEEK:  32.5 hrs    DAYS: 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Let's have a great day!
```

**Clock Out:**
```
Nice work, Chris                            Thu Jan 23

TODAY:  9.1 hrs    THIS WEEK:  41.6 hrs    DAYS: 5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

See you tomorrow!
```

### Implementation

- **Language:** Python with tkinter GUI
- **Data Source:** ProShop API (clock punches, time tracking)
- **Polling:** Every 30 seconds for new clock events
- **Display Duration:** 15 seconds per message, then idle screen
- **Local Storage:** `clock_feedback_data.json` tracks daily metrics

---

## ProShop API Findings

### Authentication

```
POST https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
client_id=3923-9C1C-7291
client_secret=[SECRET]
scope=parts:rwdp+workorders:rwdp+users:r+toolpots:r
```

### Required Scopes

| Scope | Unlocks |
|-------|---------|
| `parts:rwdp` | Part data |
| `workorders:rwdp` | Work orders, profitability, time tracking per WO |
| `users:r` | User list, clock punches, time tracking per user |
| `toolpots:r` | Work cells (machines) |

**Note:** Scopes must be enabled in ProShop Admin → Manage Authorizations for the API client.

### Key Queries

**Latest Clock Punches:**
```graphql
query {
  clockPunch {
    latestClockPunches(pageSize: 50) {
      records {
        clockPunchId
        punchDate
        inOrOut
        operator
      }
    }
  }
}
```

**Users:**
```graphql
query {
  users(pageSize: 50) {
    records {
      id
      firstName
      lastName
      isActive
    }
  }
}
```

**User Time Data:**
```graphql
query($userId: String!) {
  user(id: $userId) {
    firstName
    lastName
    timeClock(pageSize: 50) {
      records { punchDate, inOrOut }
    }
    timeTracking(pageSize: 100) {
      records { 
        timeIn, timeOut, status, 
        workOrderPlainText, operationNumber 
      }
    }
  }
}
```

**Work Cells:**
```graphql
query {
  workCells(pageSize: 50) {
    records {
      potId
      shortName
      description
      department
      isScheduledResource
      isLathe
    }
  }
}
```

### Active Employees (from API)

| ID | Name | Role |
|----|------|------|
| 001 | Tom Buerkle | Owner/Programmer (Wolfgang) |
| 004 | Zach Clarke | — |
| 007 | Jose Molina | Operator |
| 011 | Rene Maldonado | Purchasing/Operations |

### Work Cells (from API)

| ID | Name | Department |
|----|------|------------|
| Mill-1 through Mill-5 | Production mills | Production Milling |
| Mill-6, Mill-7 | Prototype mills | Prototype |
| Mill-8 | Hyundai | Production Milling |
| T1, T2 | Lathes | — |
| INSPECT-01 | Inspection | Inspection |
| + Assembly, External, Manual equipment |

---

## Files Created

| File | Version | Purpose |
|------|---------|---------|
| `clock_feedback_display_v1_0_0.py` | 1.0.0 | Main feedback display application |
| `clock_feedback_display_v1_0_0.bat` | — | Windows launcher |
| `proshop_time_tracking_test_v1_0_1.py` | 1.0.1 | API test/discovery script |
| `proshop_time_tracking_test_v1_0_1.bat` | — | Windows launcher |
| `proshop_scope_tester.py` | — | Utility to test scope combinations |
| `proshop_api_discovery.py` | — | Schema introspection tool |
| `clock_feedback_data.json` | — | Local metrics storage (auto-created) |

---

## Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Employee       │     │  ProShop ERP    │     │  Feedback       │
│  clocks in/out  │────▶│  records punch  │────▶│  Display polls  │
└─────────────────┘     └─────────────────┘     │  & shows msg    │
                                                 └─────────────────┘
                                                         │
                                                         ▼
                                                 ┌─────────────────┐
                                                 │  Local JSON     │
                                                 │  tracks metrics │
                                                 └─────────────────┘
```

---

## Next Steps

### Phase 2: Machine Utilization Integration

1. **FOCAS Connection** — Connect to Fanuc controls via FOCAS2 library
2. **Utilization Calculation** — Spindle time ÷ scheduled time
3. **Display Update** — Add utilization % and projected bonus to feedback
4. **Dashboard** — Shop floor display showing live utilization

### Phase 3: Bonus Calculation

1. **Define baseline** — Run data collection for 1-2 months
2. **Set targets** — Realistic but challenging utilization goals
3. **Calculate payouts** — Integrate with payroll or manual distribution
4. **Refine** — Adjust based on feedback and results

### Technical Tasks

- [ ] Install FOCAS libraries on shop PC
- [ ] Network connectivity to machine controls (port 8193)
- [ ] Database for time-series utilization data (SQLite or InfluxDB)
- [ ] Grafana or web dashboard for historical trends
- [ ] Raspberry Pi + monitor for shop floor display

---

## Configuration Reference

### Display Settings (in script)

```python
POLL_INTERVAL = 30          # Seconds between API polls
MESSAGE_DISPLAY_TIME = 15   # Seconds to show feedback
DATA_FILE = "clock_feedback_data.json"
```

### Running the Display

```powershell
# Option 1: Double-click the .bat file
clock_feedback_display_v1_0_0.bat

# Option 2: Command line
python clock_feedback_display_v1_0_0.py

# Option 3: Environment variable for secret
set PROSHOP_CLIENT_SECRET=your_secret_here
python clock_feedback_display_v1_0_0.py
```

### Fullscreen Mode

- Press **F11** or **Escape** to toggle fullscreen
- Recommended for kiosk/shop floor deployment

---

## Notes

- ProShop API has a bug where `Written Description` data written via API doesn't display in UI (use Selenium workaround)
- Work cell query uses `shortName`/`description` not `cellDescription`
- Scope must include `users:r` and `toolpots:r` for full functionality
- Display only catches clock events that occur while it's running
- Historical clock data is available via API but not currently used for backfill
