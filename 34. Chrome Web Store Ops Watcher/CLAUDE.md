# Project 34: Chrome Web Store Ops Watcher

Status: **Phase 2 implemented — scheduled task running every 4h with heartbeat file.**

Polls a Microsoft 365 mailbox via Microsoft Graph API for CWS lifecycle event emails (submissions, policy notices, suspensions, deprecations), classifies them, and logs to SQLite with flag files for high/critical events. Monitors the Traxis Chrome extension fleet — currently P30 (Label Printer), with P14 (Workstation Display) and P18 (Message Notifier) coming.

## Why this exists

Three Chrome extensions deploy via CWS unlisted + ExtensionInstallForcelist registry policy on shop PCs. Failure modes that would otherwise be discovered late:

- Submission rejected (blocks rollout)
- Extension suspended (silently breaks shop floor on next Chrome update)
- Policy deadline missed (manifest/permission changes, annual privacy re-attestation)
- API deprecation announcement (months ahead of breakage)
- Update-published confirmations (audit trail of which version is live on shop PCs)

P30 has already hit two CWS rejections in a row; without a watcher, each rejection email is found by manual inbox check.

## Files

| File | Purpose |
|------|---------|
| `cws_watcher.py` | Main poller. Thin Graph client + classifier + SQLite logger + flag writer + heartbeat. ~240 lines, single file. |
| `setup_schedule.bat` | Idempotent installer for the Windows Task Scheduler entry (4-hour cadence, runs as current user, no admin required). |
| `requirements.txt` | Just `requests`. |
| `cws_events.db` (gitignored) | SQLite event log. Idempotent on Graph `message_id`. |
| `flags/*.flag` (gitignored) | Per-event text files for Overseer pickup; only written for `high` / `critical` priority. |
| `last_run.json` (gitignored) | Heartbeat written every successful run: timestamp + mailbox + message counts + open flag counts. Polled by Overseer (Phase 3). |

## Architecture

```
.traxis.env (GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET)
        │
        ▼
GraphClient (thin, app-only OAuth — same shape as P27)
        │  list_messages(mailbox, since) → [msg]
        │  get_body(mailbox, msg_id)     → (html, type)
        ▼
classify(subject, body) → (priority, kind)
        │
        ▼
INSERT OR IGNORE INTO cws_events  +  flags/cws_<date>_<priority>_<id>.flag
```

### Classification rules

Order-sensitive — first match wins. Priority levels: `critical` > `high` > `low` > `info`.

| Priority | Kind | Pattern (subject or body, lowercase) |
|----------|------|--------------------------------------|
| critical | suspension | `suspend|takedown|removed from` |
| high | submission_rejected | `reject` |
| high | deprecation | `deprecat|discontinued|no longer support` |
| high | policy_notice | `policy|deadline|required by|action required|must update` |
| low | submission_approved | `approv|published|now live` |
| low | install_report | `usage report|install report|monthly summary` |
| info | other | (fallback) |

Flag files are written only for `high` / `critical` events.

### Architectural deviation from initial spec

Spec said "direct import of P27's GraphClient." In practice that requires loading the entire 2549-line `accounting_ingest.py` monolith including `tkinter` and `anthropic`, which would balloon P34's startup time and create a cross-domain dependency. Instead, P34 has its own thin GraphClient class (~30 lines) using the same OAuth flow and the same `.traxis.env` credentials. The shared resource is the env file, not the code. Drift risk is minimal — the Graph token endpoint and message listing API are stable.

If a third Graph consumer appears later, extracting a `shared/graph_client.py` becomes worthwhile. Until then, two ~30-line copies are cheaper than the refactor.

## Usage

### Manual

```bash
# Smoke test — see what would be classified, no DB writes
python cws_watcher.py --since 2026-01-01 --print-only -v

# Real run — log to DB, write flag files for high-priority events
python cws_watcher.py

# Backfill from a specific date (idempotent — safe to re-run)
python cws_watcher.py --since 2026-01-01

# Override mailbox (defaults to tom@traxismfg.com)
python cws_watcher.py --mailbox someone@traxismfg.com
```

Default lookback is 90 days; pass `--since` for backfill.

### Scheduled

```cmd
REM Install the scheduled task (one-time)
setup_schedule.bat

REM Verify
schtasks /Query /TN "Traxis - CWS Ops Watcher"

REM Trigger an immediate run (useful for testing)
schtasks /Run /TN "Traxis - CWS Ops Watcher"

REM Remove
schtasks /Delete /TN "Traxis - CWS Ops Watcher" /F
```

The task runs `pythonw.exe cws_watcher.py` every 4 hours starting 06:00 daily. No console window flash (per P32 lesson — direct `pythonw.exe`, no `.bat` wrapper). Runs as the current user with `LIMITED` privileges; no admin elevation needed for setup or execution.

`last_run.json` updates on every run; downstream services (Overseer, future Phase 3 work) can read it to detect staleness or surface counts.

## Interfaces

Produces: `cws_events.db` (SQLite event log), flag files in `flags/` for Overseer pickup, `last_run.json` heartbeat (timestamp + counts) for staleness detection, scheduled task `Traxis - CWS Ops Watcher` (Windows Task Scheduler, 4h cadence)
Consumes: Microsoft Graph API (app-only OAuth, `Mail.Read` application permission), `.traxis.env` (`GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` shared with P27), `tom@traxismfg.com` mailbox by default (override via `--mailbox` or `CWS_WATCHER_MAILBOX` env var)
Contracts: Idempotent on Graph `message_id` — re-running won't double-log. Flag file naming: `flags/cws_<YYYY-MM-DD>_<priority>_<msg_id_prefix>.flag`. SQLite schema columns: `message_id, received_at, sender, subject, body_excerpt, classification, priority, raw_json, processed_at`. `raw_json` preserves the full Graph message envelope for re-classification later if rules change. `last_run.json` keys: `ran_at` (ISO UTC), `mailbox`, `since`, `total_messages_seen`, `cws_messages_seen`, `new_events`, `high_priority_count`, `critical_priority_count`. Scheduled task name `Traxis - CWS Ops Watcher` is the documented identifier — Phase 3 Overseer integration will reference it.

## Initial run validation (2026-05-02)

First execution against `tom@traxismfg.com` over 90 days returned 4 CWS-sender events:

- 2026-05-02 — submission_rejected (P30 v1.5.1, activeTab violation) — high
- 2026-04-30 — submission_rejected (P30 first rejection) — high
- 2026-04-29 — Confirm contact email — info
- 2026-04-29 — Publisher invitation — info

Two flag files written. No false positives in the classifier on this sample.

## Phase 2 — done

- ✓ **Scheduling.** Windows Task Scheduler entry `Traxis - CWS Ops Watcher` runs `pythonw.exe cws_watcher.py` every 4 hours, starting 06:00 daily. No console flash (per P32 lesson). Created via `setup_schedule.bat` — idempotent, no admin required.
- ✓ **Heartbeat file.** Each run writes `last_run.json` with timestamp + message/event counts. Future Overseer integration polls this file for staleness (no HTTP endpoint needed since the watcher is a periodic batch task, not a long-running service).

## Phase 3 — pending

- **Overseer config wiring.** Add a `SERVICES_CONFIG` entry in `1. Proshop Automations/Overseer/overseer.py` that treats P34 as a "scheduled task" service — validator reads `last_run.json` and flags as degraded if `ran_at` is older than ~6 hours (1.5× the polling interval). This needs new logic in Overseer to handle file-freshness validators, alongside the existing HTTP-health and DB-freshness validators.
- **Optional Telegram routing.** P25 AgentScheduler can forward `critical` events to your phone for off-hours suspension alerts. Trigger on flag file creation or new DB row with `priority='critical'`.
- **Approved-event auto-clear.** When a `submission_approved` event arrives, auto-delete any earlier `submission_rejected` flag files for the same `Item ID` mentioned in the body (parse "Item ID:" pattern from the rejection body to bind events to extensions).
- **Multi-extension reporting.** As P14 and P18 ship, parse the extension name from each event subject and surface per-extension status in the heartbeat / Overseer view.

## Related projects

- **P27 (`27. Accounting Ingest`)** — Source of the Graph OAuth pattern this project mirrors. Same `.traxis.env` credentials.
- **P30 (`30. Material Label Extension`)** — First extension monitored. CWS item ID `ackaimnnhgfijphpnjdpajflndpggdcg`.
- **P14 (`14. Workstation Display`)** — Slated for CWS deployment, will be second monitored extension.
- **P18 (`18. ProShop Message Notifier`)** — Slated for CWS deployment, will be third monitored extension.
- **P1 (`1. Proshop Automations`)** — Overseer service host that will surface flag files.
