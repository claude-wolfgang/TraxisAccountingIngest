# Shop Scheduler — Session Log

## Session 4: 2026-04-06 — Scheduler Fixes Batch

### Changes Made

**Fix 1: Clean up completed WO blocks** (database.py, sync.py)
- WOs marked "Manufacturing Complete" (or any non-active status) in ProShop were still showing as scheduled blocks on the board (e.g., WO 25-0300, 23-0449)
- `get_schedule_blocks()` now filters with `WHERE w.status = 'active'` so the API never returns blocks for completed WOs
- `full_sync()` now deletes non-locked, non-complete schedule blocks for WOs just marked complete, matching the pattern from the hide-WO cleanup in `app.py`

**Fix 2: MILL-X-CAT40 and MILL-X-PROBE work center mappings** (database.py, suggest.py)
- Added two new `work_center_map` entries (NULL machine_id = catch-all): `MILL-X-CAT40` and `MILL-X-PROBE`
- Migration in `_migrate()` inserts them on existing DBs (idempotent); also added to `_seed_defaults()` for fresh installs
- Suggestion engine now routes by work center capability:
  - `MILL-X-PROBE` → mill-1, 2, 3, 8 (probe-capable)
  - `MILL-X-CAT40` → mill-1, 2, 3, 6, 8 (CAT40 taper)
  - `MILL-X` / None → all full-size mills (existing behavior)
- The narrowed pool is used consistently in all fallback paths (urgent, historical, lightest-load)

**Fix 3: Exclude T2 from needs-tools list** (app.py)
- Lathe (T2) ops were appearing on the Dashboard "Needs Tools" list, but tooling can't be staged for the lathe
- Added `and op.get("work_center", "").upper() != "T2"` filter to the needs-tools builder

### Files Modified
| File | Summary |
|------|---------|
| database.py | `get_schedule_blocks()` active-only filter; `_migrate()` + `_seed_defaults()` for MILL-X-CAT40/PROBE |
| sync.py | `full_sync()` deletes schedule blocks for newly-completed WOs |
| suggest.py | `CAT40_MILL_IDS`, `PROBE_MILL_IDS` constants; work-center-aware candidate pool |
| app.py | T2 exclusion from needs-tools list |

---

## Session 3: 2026-04-03 — v0.6 Features

### Changes Made

**Edge-Scroll on Drag** (scheduler.js)
- When dragging a scheduled block near the left/right edge of the calendar, the timeline auto-scrolls
- 60px trigger zone from each edge, 1200ms delay between scroll steps
- Only active for block-to-block drags (NOT backlog drops, which would break overlay positioning)
- Functions: `startEdgeScrollCheck()`, `edgeScrollStep()`, `stopEdgeScroll()`

**Readiness Dot Key in Header** (all templates + style.css)
- Added a visual key in the header bar showing what the 4 readiness dots mean: Prog, Mat, Tools, Machine
- Displayed on all 4 pages: Board, Operator, Dashboard, Tools
- Styled as a compact pill with colored dots

**Check Runtimes Tab** (dashboard.html, dashboard.js, app.py)
- New "Check Runtimes" tab on the Dashboard showing operations with est_hours > 80h
- These may be bad data from ProShop (e.g., 335h Final Inspection) or legitimate high-volume runs
- Shows hours, qty, estimated flag in red for review
- Deep-linkable: `/dashboard?tab=runtimes`

**ProShop Links from Detail Panel** (scheduler.js, scheduler.html, app.py)
- Clicking a WO number in the block detail panel opens the WO in ProShop
- "ProShop" button in panel actions for quick access
- URL pattern: `{PROSHOP_BASE}/procnc/workorders/20YY/YY-XXXX$`
- `window.PROSHOP_BASE` injected via template

**Schedule Push — Automatic** (database.py, sync.py)
- Past-due incomplete blocks automatically slide forward to current business hours
- Cascading: subsequent blocks on the same machine push forward to avoid overlaps
- Locked blocks don't move but constrain the cascade cursor
- Runs after every full sync (~15 min) and every writeback cycle (~2 min)
- Business-hours aware: blocks snap to 5 AM-6 PM weekdays
- Functions: `push_schedule()`, `_snap_to_business()`, `_add_bh()`, `_parse_dt()`, `_fmt_dt()`

**Tools Queue Page** (templates/tools.html, app.py, style.css)
- Dedicated `/tools` page for the tooling person
- Shows WOs sorted by urgency with tool requirements
- "Done" button marks tools-ready in the readiness table

**Material Readiness 3-State** (sync.py, dashboard.js)
- Material status derived from Part Stock data (not VPO linkage)
- Three states: not_ordered / ordered (with PO# and order status) / received
- Displayed on Dashboard "Material" needs tab with PO details

**Dashboard Needs Lists** (dashboard.html, dashboard.js, app.py)
- Tabs for Program / Material / Tools / Check Runtimes needs
- Counts shown on each tab badge
- WO numbers link directly to ProShop
- Print support for each tab
- Deep-link: `/dashboard?tab=program|material|tools|runtimes`

### Files Modified
| File | Lines Changed | Summary |
|------|--------------|---------|
| app.py | +276 -53 | Tools page route, needs API with runtimes, proshop_base injection |
| config.py | +5 -3 | Minor config updates |
| database.py | +158 -0 | push_schedule system with business-hours helpers |
| proshop_client.py | +6 -0 | Minor client additions |
| static/dashboard.js | +130 -15 | Runtimes tab, material detail rendering, deep-link support |
| static/scheduler.js | +1151 -254 | Edge-scroll, ProShop links, swap, zoom, filters, hidden items |
| static/style.css | +375 -12 | Readiness key, tools page, dashboard tabs, filter bar |
| suggest.py | (unchanged) | MAX_OP_HOURS = 80 (kept for flagging) |
| sync.py | +100 -47 | push_schedule integration, material readiness from Part Stock |
| templates/dashboard.html | +20 -0 | Runtimes tab button |
| templates/operator.html | +8 -0 | Readiness key in header |
| templates/scheduler.html | +49 -11 | Readiness key, PROSHOP_BASE script, hidden items dropdown |
| templates/tools.html | (new) | Full tools queue page |

### Known Issues
- WOs 26-0095 through 26-0104 fail to sync ops (`'NoneType' object has no attribute 'get'`) — likely new/empty WOs in ProShop
- `/api/suggestions` returns 500 on first load (one-time, self-resolves after full sync completes)
- "database is locked" can occur when push_schedule in writeback loop collides with full sync — transient, auto-retries

---

## Session 2: 2026-03-30 — v0.5 Major Improvements

### Changes Made
- Op hiding (per-WO and per-operation)
- Business hours enforcement (5 AM - 6 PM weekdays)
- Drag-drop fixes and swap detection
- Bottom detail panel for block info
- Backlog panel with search
- Filter bar with collapsible controls
- Zoom controls (Day/3-Day/Week/Month)
- Overlap prevention (backend 409 + frontend toast)
- Clear Board button
- Auto-Schedule suggestion engine
- Undo support

---

## Session 1: 2026-03-28 — Initial Commit

### Changes Made
- Flask + SQLite architecture
- ProShop OAuth2 integration
- EventCalendar (resourceTimelineDay) Gantt board
- Readiness lights (program, material, tools, machine)
- Tool-aware scheduling with pocket comparison
- Part drawing viewer
- Operator touch view
- Dashboard stats view
