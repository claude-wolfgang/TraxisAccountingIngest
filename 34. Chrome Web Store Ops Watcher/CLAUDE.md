# Project 34: Chrome Web Store Ops Watcher

Status: **Spec / not yet implemented**

Monitors Chrome Web Store lifecycle events for the Traxis extension fleet — currently P30 (Label Printer), with P14 (Workstation Display) and P18 (Message Notifier) coming. Polls the M365 mailbox via Microsoft Graph for emails from CWS senders, classifies each event, and surfaces high-priority items to Overseer.

## Why this exists

Three Chrome extensions deploy via CWS unlisted + ExtensionInstallForcelist registry policy on shop PCs. Failure modes that would otherwise be discovered late:

- Submission rejected (blocks rollout)
- Extension suspended (silently breaks shop floor on next Chrome update)
- Policy deadline missed (manifest/permission changes, annual privacy re-attestation)
- API deprecation announcement (months ahead of breakage)
- Update-published confirmations (audit trail of which version is live on shop PCs)

P30 has already hit two CWS rejections in a row; without a watcher, each rejection email is found by manual inbox check.

## Planned architecture

```
cws_watcher.py        →  imports GraphClient from P27 (`27. Accounting Ingest`)
                       →  polls every 4h for messages from CWS senders
classifier.py         →  classifies each message: submission_decision /
                          policy_notice / suspension / quota / deprecation /
                          install_report / other
cws_events.db         →  SQLite log of every event (idempotent on message_id)
flags/                →  flag files Overseer dashboard picks up for high-priority events
```

## Planned files

| File | Purpose |
|------|---------|
| `cws_watcher.py` | Main poller. Fetches messages, dedupes, classifies, writes DB + flags. |
| `classifier.py` | Subject + body keyword classifier with priority levels. |
| `cws_events.db` | SQLite event log: message_id, received_at, sender, subject, body_excerpt, classification, priority, raw_json, processed_at. |
| `flags/` | Per-event flag files for Overseer dashboard (high/critical priority only). |
| `requirements.txt` | Pinned deps (msal/requests for Graph if not inherited from P27). |

## Interfaces

Produces: `cws_events.db` (SQLite event log), flag files in `flags/` for Overseer pickup, optional one-line summary log entries to `main_session_log.md` at root
Consumes: Microsoft Graph API (via P27's GraphClient — direct import for now), `.traxis.env` (Graph OAuth credentials shared with P27), Overseer (P1) as managed service host
Contracts: One-way coupling P34 → P27 (P34 imports from P27, P27 has no knowledge of P34). Polling cadence 4h. Filters mailbox by sender match `chromewebstore-noreply@google.com` and `chrome-store-policy@google.com`. Flag file naming: `flags/cws_<event_id>_<priority>.flag` containing one-line summary. Idempotent on message_id — re-running the watcher won't double-log.

## Open questions for first implementation

- **Graph client extraction**: import P27's GraphClient as-is, or refactor to a thin `fetch_messages(filter, since)` helper first? Decide after reading P27 code.
- **Notification path**: Overseer flag file only, or also Telegram via P25 (AgentScheduler)? Telegram adds value for off-hours suspension alerts.
- **Polling cadence**: 4h is conservative; could go to 12h since CWS deadlines are typically weeks. Start at 4h, tune down if quiet.
- **Service shape**: Overseer-managed long-running service (continuous loop with sleep), or Windows Task Scheduler firing pythonw.exe every N hours? Task Scheduler is simpler for the MVP.
- **Backfill**: one-shot run with `--since 2026-01-01` to load historical CWS events (including the two prior P30 rejections) for audit trail.

## Trigger to start implementation

Either:
- P30 v1.5.2 approval clears and we want to log it as the first event under P34, or
- P14 or P18 nears its first CWS submission

Whichever comes first.

## Related projects

- **P27 (`27. Accounting Ingest`)** — Source of the Microsoft Graph client this project will import.
- **P30 (`30. Material Label Extension`)** — First extension monitored. Live on CWS as item `ackaimnnhgfijphpnjdpajflndpggdcg`.
- **P14 (`14. Workstation Display`)** — Slated for CWS deployment, will be second monitored extension.
- **P18 (`18. ProShop Message Notifier`)** — Slated for CWS deployment, will be third monitored extension.
- **P1 (`1. Proshop Automations`)** — Overseer service host that will surface flag files.
