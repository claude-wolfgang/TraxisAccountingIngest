# Project 25: Agent Exploration — Data Quality Agent

## What This Is
Always-running data quality agent for Traxis Manufacturing. Audits ProShop ERP,
FOCAS machine monitoring, and the NC program filesystem to find and report data
quality issues. Stores results for trending over time.

## Status: BUILT AND WORKING (2026-03-27), EXPANDED (2026-03-28)
First real run: 122 checks, Score 25.9% CRITICAL.
68 active WOs, 489 operations, 64.4% overrun rate, 1139.7h over target.
All results stored in audit.db for trending.

2026-03-28: Absorbed Project 10 (Conversational ProShop), added Telegram bot,
reminder system, notes capture, nightly project scanner, and legacy lathe
program mapping. Project is now a full personal assistant for 25 projects.

## Architecture
```
service_wrapper.py    Leader-elected service wrapper (runs all services below, incl. Overseer)
install_service.bat   NSSM install script (run as Admin to create Windows service)
run_audit.py          Audit entry point (CLI with --quick, --trend, --json flags)
agent.py              Claude Agent SDK entry point (NL queries via MCP tools)
mcp_tools.py          MCP tool definitions (21 tools across 4 servers)
telegram_bot.py       Claude-powered Telegram bot (phone assistant)
scan_projects.py      Nightly project index scanner (Haiku-powered)
check_reminders.py    Reminder polling daemon (every 15 min via wrapper)
├── config.py         Credentials, paths, machine mappings, env var helper
├── proshop_client.py ProShop GraphQL client (OAuth 2.0, 9 query methods)
├── focas_reader.py   FOCAS SQLite reader (read-only)
├── audit_engine.py   All audit checks (45+ checks across 8 categories)
├── audit_db.py       Local SQLite for audit + reminders + notes
├── report.py         Console + markdown report generation
├── project_index.json Structured index of all 25 projects (auto-updated nightly)
├── lathe_programs.json Legacy T2 O-number -> part number mappings
├── audit.db          Local SQLite database (auto-created)
├── service_heartbeat.json  Leader election heartbeat (auto-created, Dropbox-synced)
├── alerter.py       Telegram alerts: daily digest + critical-only immediate
├── logs/             Service wrapper logs (auto-created)
│   ├── service_wrapper.log
│   ├── overseer_stdout.log
│   └── last_digest.json
└── reports/          Generated audit reports
    ├── latest.md     Always-current latest report
    └── audit_YYYYMMDD_HHMMSS.md  Timestamped reports
```

## Running
```bash
# Service Wrapper (leader-elected, runs all services)
python service_wrapper.py            # Normal run (as service or foreground)
python service_wrapper.py --status   # Show current heartbeat and exit
python service_wrapper.py --once     # One election cycle and exit (testing)
install_service.bat                  # Install as Windows service (run as Admin)

# Data Quality Audit
python run_audit.py              # Full audit -> console + reports/latest.md
python run_audit.py --quick      # System health only
python run_audit.py --trend      # Historical trend analysis (needs 2+ runs)
python run_audit.py --json       # Machine-readable output
python run_audit.py --no-save    # Console only, no file output
python run_audit.py --days 90    # Trend report over 90 days instead of 30

# Claude Agent (natural language queries via MCP tools)
python agent.py "which jobs are overrunning?"   # One-shot query
python agent.py                                  # Interactive mode (stateful)

# Telegram Bot (long-running, phone access to all 25 projects)
python telegram_bot.py           # Run the bot
python telegram_bot.py --test    # Send test message and exit

# Nightly Scanner (auto-updates project_index.json)
python scan_projects.py              # Full scan
python scan_projects.py --dry-run    # Scan without writing
python scan_projects.py --project 12 # Scan one project only

# Reminders
python check_reminders.py        # Send due reminders via Telegram
python check_reminders.py --list # Show pending reminders
```

## Dependencies
- Python 3.10+
- `requests` (pip install requests)
- `claude-agent-sdk` (pip install claude-agent-sdk) -- for agent.py / MCP tools
- `python-telegram-bot` (pip install python-telegram-bot) -- for telegram_bot.py
- `anthropic` (pip install anthropic) -- for telegram_bot.py, scan_projects.py
- Uses stdlib sqlite3, pathlib, json

## Environment Variables (Windows User env vars)
- `ANTHROPIC_API_KEY` -- required for agent.py, telegram_bot.py, scan_projects.py
- `TELEGRAM_BOT_TOKEN` -- required for telegram_bot.py, check_reminders.py
- `TELEGRAM_CHAT_ID` -- required for telegram_bot.py, check_reminders.py
- Note: Git Bash can't read Windows User env vars. config.py has `_get_env()` PowerShell fallback.

## Data Sources
- **ProShop API:** `https://traxismfg.adionsystems.com/api/graphql`
  - Client: BA16-EFAF-B154 (ClaudeCodeResearch)
  - Secret: 2F64968E4E77FDE1CB6B587D9F92340CC3B4C82A414D77798F359A85CD4976D1
  - Scope: parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r
  - Token URL: /home/member/oauth/accesstoken
  - 120s timeout, auto-retry on 401
- **FOCAS DB:** `C:\FASData\monitoring.db` (primary) or Dropbox sync copy (fallback)
  - Read-only connection (file: URI with mode=ro)
  - No WAL pragma (causes write error on RO connection)
  - 5 machines in DB: M2, M3, M6, M8, T2
- **Filesystem:** Dropbox NC Programs + Part Files (auto-detected from %LOCALAPPDATA%/Dropbox/info.json)

## Audit Categories (8 total, 45+ checks)
1. **System** -- API health, database health, filesystem access
2. **ProShop Population** -- Field fill rates for WOs and operations
3. **Consistency** -- Logical checks (qty, status, hours mismatches)
4. **Schedule** -- Overdue WOs, unscheduled ops due soon
5. **Readiness** -- Tool certifications, NC programs, material status
6. **Cross-reference** -- ProShop <-> FOCAS <-> filesystem alignment
7. **FOCAS** -- Collection gaps, schema, alarms, utilization
8. **Financial** -- Overrun rate, worst jobs, family patterns

## Key Files From Other Projects
- `19. Shop Scheduler/proshop_client.py` -- Original client pattern (source of correct OAuth secret)
- `19. Shop Scheduler/config.py` -- Correct ProShop credentials
- `10. Conversational Proshop - Retired/src/query_templates.py` -- Query templates (ABSORBED into P25 on 2026-03-28)
- `20. Traxis Data/proshop_pull.py` -- Data pull + overrun analysis
- `12. FASData Implementation/focasmonitor/Database.cs` -- FOCAS schema
- `12. FASData Implementation/TraxisTransfer/src/traxistransfer/services/folder_resolver.py` -- NC folder resolution (uses customerPartNumber)
- `1. Proshop Automations/FASDataDashboard/fasdata_live.py` -- Dashboard queries
- `15. Proshop Replacement Research and Architecture/01_api_discovery/proshop_actual_schema.md` -- Full ProShop schema (74 Part fields, verified 2026-03-04)

## Known API Gotchas
- Part number lookups are case-sensitive
- No server-side filtering -- must fetch all, filter client-side
- `operationNumber` (query) vs `opNumber` (mutation) -- different names, same field
- Pagination broken beyond page 1 -- use pageSize up to 500
- Written descriptions via API are BROKEN (legacyId bug)
- Editing OAuth client scopes can corrupt the client -- always create new
- `outsideProcessing` is an object field but has no useful subfields via current scope -- do not query it
- `billOfMaterials` and `tools` on partOperation cause timeouts when fetched in bulk -- use per-WO targeted queries only
- Active WO query works with page_size=100, timeout=120s. Larger sizes risk timeout.

## Known Limitations (as of first run)
1. **NC program lookup at 0.9%** -- Uses partNumber but folders use customerPartNumber. Fix researched, not yet implemented. Add `customerPartNumber` to part query.
2. **FOCAS stale on this PC** -- Reads Dropbox sync copy, not live collector at 10.1.1.71. Expected.
3. **Tool/BOM bulk checks removed** -- Caused timeouts. Replaced with certifiedToRun check.
4. **Op 3000 false positives** -- Common non-machining op flagged for missing NC programs.
5. **Utilization shows 0%** -- Dropbox sync has no same-day data. Correct on collector PC.

## Windows Console Encoding
All output uses ASCII only. No Unicode box-drawing characters, no emoji.
This avoids cp1252 encoding errors on Windows terminals.

## Scheduling
The service wrapper (`service_wrapper.py`) replaces all individual Task Scheduler entries.
It runs as a Windows service (`TraxisAgent`) via NSSM and handles internal scheduling:
- **telegram_bot.py**: Continuous subprocess, auto-restarted on crash (exponential backoff 30-300s)
- **overseer.py**: Continuous subprocess, auto-restarted on crash (exponential backoff 30-300s). Uses system Python (`Programs\Python314`) since Flask/requests are installed there. CWD set to Overseer directory.
- **check_reminders.py**: Every 15 minutes
- **run_audit.py**: Every 60 minutes (Telegram alerts: daily digest at first run after 6 AM + immediate alerts for system errors only)
- **scan_projects.py**: Daily at midnight (00:00-00:15 window)

Install via `install_service.bat` (run as Admin). Uses NSSM from `Graf\services\nssm-2.24\`.

### Leader Election (Multi-Machine Failover)
Uses `service_heartbeat.json` (synced via Dropbox) for leader election between machines.
- Leader writes heartbeat every 60s; stale after 180s
- Standby polls every 30s, promotes when heartbeat goes stale
- Priority tiebreaker: `"primary"` outranks `"normal"` (set via PRIORITY_MAP or env var)
- Graceful yield: leader steps down if higher-priority machine comes online

### Legacy Task Scheduler (remove after wrapper verified)
Old individual Task Scheduler entries (kept for rollback):
```
Program: python
Arguments: run_audit.py / check_reminders.py / scan_projects.py
Trigger: Hourly / 15-min / Midnight
```
Exit code 1 = failures or errors found (useful for monitoring).

## Next Steps (Priority Order)
1. `lathe_programs.json` — 63 programs total, **45 cross-ref-ready** (part_number + op_number both filled), 46 with part_number, 46 with op_number. Major session 2026-05-09:
   - All 30 op#s filled from Wolfgang's checklist.
   - All 38 existing part_numbers canonicalized to ProShop customer-prefix form (R2S1-, ICO1-, AUS1-, MON2-, AME1-, UTA1-, 3DS1-, ART1-) — verified via `parts(filter:{partNumber:})` lookups. Several were previously unmatchable (e.g. `BARB-FITTING` → `AUS1-Barb Fitting`, `10-2004` → `ICO1-10-02004`, `AD0208-300-007` → `R2S1-A0208-300-007` — note D→A typo correction in NC headers).
   - O7001 → R2S1-10036 (master for O3213, by elimination — O7002 is already 10037).
   - O4282 → R2S1-10042 (shared with R2S1-10164, dual-use OP80 like O4280).
   - 4 FOCAS orphans resolved via `PART FILES Traxis/` NC file content search: O2006 → ICO1-10-02002 OP4; O2009 → ICO1-10-02004 (Bore Collet Fixture); O1491 → ART1-149 OP1; O1492 → ART1-149 OP2. Pattern discovered: Artivion items use O14XY where X=item suffix, Y=op (so O1421/22 = Item 142, O1431/32 = Item 143, O1490-93 = Item 149).
   - O1489 → LYN1-BH-A-E op 60 (single WO time-tracking match on 2026-03-19).
   - **Still open (18 entries):**
     - **5 Feb-2026 FOCAS orphans with no Dropbox NC trail and no WO time-tracking match** — likely typed at YCM and never archived: O0121 (Feb 8-9), O0819/O0820/O0821 (Feb 10-11), O2049 (Feb 27, 475 samples). Only YCM-side `MDI > PROG > DIR` inspection can resolve.
     - **3 March-cluster orphans with candidates but no part_number set** — O1481 + O1482 likely ART1-148 Top Collar OP1/OP2 by O14XY pattern (Item 148 NC files not archived in PART FILES Traxis); O1499 not matched anywhere, possibly test/one-off.
     - **O2010** has two NC-file candidates (3DS1-7301K32 vs ST3315 obsolete) — needs YCM disambiguation.
     - **O2000** SPACER_10 (generic spacer) — Wolfgang skipped on checklist; left empty as default.
     - **O0061** REWORK OP61 (op 61, no part) — generic rework, intended to stay empty.
     - **7 utility/macro entries** intentionally empty per O8000–O8999/O9000–O9999 reserved-range rule: O8000, O8100, O9000, TAP1, plus O0003 / O1000 (generic impeller programs).
2. Fix NC program lookup (add customerPartNumber to query) — currently suppressed from digest as known-noisy. Re-enable in digest after fix.
3. Filter non-machining ops (op 3000 etc.) from NC check.
4. Deploy to collector PC (10.1.1.71) for live FOCAS data — partly addressed by service wrapper + leader election; verify FOCAS reads live DB on .71.
5. Build subagents (data-auditor, reconciler, reporter).
6. Filter benign FANUC alarm codes (E-stop, door interlocks) so `alarms_7day` becomes a real-fault metric instead of activity count. Currently dropped from digest entirely.
7. Verify FOCAS `program_directory` fix worked. Deployed 2026-05-03 (cnc_rdprogdir3 type=0 + type=1 fallback in `MonitoringService.cs`, self-contained build at `C:\FocasMonitor\` on .71). Sunday machines-off prevented same-day verification. Scheduled task `FocasProgDirVerifyTue` fires Tue 2026-05-05 09:00 on .71, sends verdict to Telegram, self-deletes. After Tuesday: if WORKING, remove this item; if NOT WORKING / PARTIAL, debug from Application event log (cnc_rdprogdir3 return codes now visible at LogWarning).

## Claude Agent SDK Integration (IMPLEMENTED 2026-03-28)
Platform decision: Claude Agent SDK (NOT OpenClaw -- security concerns, ClawHavoc attack).

**mcp_tools.py** defines 21 MCP tools across 4 in-process servers:
- **proshop** (10 tools): check_proshop_health, get_active_work_orders, get_completed_work_orders, get_work_cells, get_work_order, get_work_order_time_tracking, get_work_order_profitability, get_part_info, get_part_operations, search_work_orders
- **focas** (4 tools): check_focas_health, get_machine_utilization, get_recent_alarms, get_active_programs
- **audit** (4 tools): run_full_audit, get_latest_audit, get_audit_history, get_metric_trend
- **reminders** (3 tools): schedule_reminder, list_reminders, cancel_reminder

**agent.py** creates a Claude agent (Sonnet) with enriched ProShop domain knowledge.
- One-shot mode: `query()` (stateless)
- Interactive mode: `ClaudeSDKClient` (stateful, preserves conversation context)
- Injects current datetime into system prompt
- Status mapping from P10: open->Active, late->Active+past due, etc.

**telegram_bot.py** is a separate Claude-powered Telegram bot (@traxis_audit_bot):
- Uses Anthropic Python SDK directly (not Agent SDK)
- 6 tools: save_note, schedule_reminder, list_reminders, cancel_reminder, search_notes, get_project_status
- Loads project_index.json for context on all 25 projects
- Conversation history (30 turns)
- Slash commands: /status, /notes, /reminders, /projects

**scan_projects.py** nightly scanner (midnight via Task Scheduler):
- Reads CLAUDE.md, README.md, session_log.md, master SESSION_LOG.md, Claude Code MEMORY.md
- Uses Haiku to extract structured status per project (~$0.02/run)
- Updates project_index.json (preserves static fields, updates dynamic)

**check_reminders.py** polls every 15 min via Task Scheduler:
- Checks audit.db for due reminders
- Sends via Telegram API
- Marks as sent

Future subagents:
- data-auditor (Haiku) -> runs checks, flags issues
- reconciler (Sonnet) -> cross-references, root cause analysis
- reporter (Haiku) -> generates summaries, sends alerts

Orchestrator (Sonnet/Opus) decides what to investigate and routes tasks.
Integration with existing Overseer service on 10.1.1.71 (ports 8050-8070).

## Scheduled Tasks
### Current: TraxisAgent Service (service_wrapper.py)
| Service | How | Interval | Timeout |
|---------|-----|----------|---------|
| telegram_bot.py | Long-running subprocess | Continuous | Auto-restart (30-300s backoff) |
| overseer.py | Long-running subprocess | Continuous | Auto-restart (30-300s backoff) |
| check_reminders.py | One-shot subprocess | Every 15 min | 300s |
| run_audit.py | One-shot subprocess | Every 60 min | 300s |
| scan_projects.py | One-shot subprocess | Daily at midnight | 600s |

### Legacy Task Scheduler (remove after service verified)
| Task Name | Script | Schedule | Notes |
|-----------|--------|----------|-------|
| TraxisAudit | run_audit.py | Hourly | Exits 1 on failures |
| TraxisProjectScanner | scan_projects.py | Daily at 12:00 AM | Updates project_index.json |
| TraxisReminderCheck | check_reminders.py | Every 15 min | Sends due reminders via Telegram |

## Telegram Bot (@traxis_audit_bot)
- Bot name: "Traxis Audit"
- Only responds to TELEGRAM_CHAT_ID (Wolfgang's chat)
- Managed by service_wrapper.py (auto-started, monitored, restarted on crash)
- Handles: thought capture, project queries, reminders, status overviews

## Legacy Lathe Program Mapping
T2 lathe has resident programs (O-numbers) that predate the TraxisPostProcessor header system.
These stay on the machine and aren't loaded per job. `lathe_programs.json` maps O-numbers to
ProShop part numbers so FOCAS active_programs can be cross-referenced.
Template created -- needs real data from Garrett/Thomas.

## Machine ID Mapping
| ProShop | FOCAS | Machine | FOCAS Connected |
|---------|-------|---------|-----------------|
| Mill-1 | -- | Haas VF-5 | No |
| Mill-2 | M2 | FANUC Mill 2 | Yes |
| Mill-3 | M3 | FANUC Mill 3 | Yes (intermittent) |
| Mill-4 | M4 | Robodrill 4 | No ethernet |
| Mill-5 | M5 | Robodrill 5 | No ethernet |
| Mill-6 | M6 | FANUC Mill 6 | Yes |
| Mill-7 | M7 | Robodrill 7 | No ethernet |
| Mill-8 | M8 | Hyundai-Wia KF5600II | Yes |
| Lathe-1 | -- | Unknown | No |
| Lathe-2 | T2 | YCM NTC1600LY | Yes |

## Interfaces
Produces: audit.db (SQLite), reports/latest.md, project_index.json, service_heartbeat.json, Telegram bot responses, /api/health on ports 8100 (TelegramBot) and 8101 (AgentScheduler)
Consumes: ProShop GraphQL API, FOCAS monitoring.db (read-only), NC Programs filesystem, Anthropic API, Telegram Bot API, Overseer (managed service on ports 8100/8101)
Contracts: service_wrapper.py launches Overseer which manages TelegramBot + AgentScheduler. Health endpoints must respond JSON with `"status": "ok"` for Overseer validation. agent_scheduler.py runs check_reminders.py/run_audit.py/scan_projects.py as subprocesses from PROJECT_ROOT.
