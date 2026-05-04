# Traxis Manufacturing — Project Ecosystem

This root CLAUDE.md covers all 27+ projects under `Proshop Automation and Claude Projects`.
Claude Code loads it automatically at session start.

## Quick Context

- **Owner:** Wolfgang
- **ERP:** ProShop (GraphQL API, OAuth 2.0)
- **CAM:** Fusion 360
- **Collector PC:** 10.1.1.71 (MainPC) — runs Overseer, dashboards, services
- **Kiosk PC:** 10.1.1.142 — tool kiosk touchscreen
- **Project index:** `25. Agent Exploration/project_index.json`
- **Ecosystem map:** `TRAXIS_ECOSYSTEM.md` (generated — do not hand-edit)
- **Session log:** `main_session_log.md`

## Session Close Ritual

When Wolfgang says **"prepare to close"**, follow this four-beat protocol exactly.

| Beat | Who | Says | Purpose |
|------|-----|------|---------|
| 1 | Wolfgang | `prepare to close` | Trigger (may be accidental) |
| 2 | Claude Code | `Prepare to close session?` | Confirmation — safety catch |
| 3 | Wolfgang | `yes` | Confirms intent |
| 4 | Claude Code | *(does all close work, then)* `Ready to authorize close, sir` | Presents for review |
| 5 | Wolfgang | `authorized` | Commits everything |

Nothing is written until beat 4. Nothing is irreversible until "authorized" at beat 5.

**Diagnostic tell:** The word **"sir"** in beat 4 is deliberate. If you ever see "Ready to authorize close" without "sir", this root CLAUDE.md is not loaded — fix before ending the session.

### Close Steps (execute after "yes" at beat 3)

In this order — each step informs the next:

1. **Session log** — Write or update the entry in `main_session_log.md` for this session. Include: date, project number and name, task summary, files modified, key decisions, status.

2. **Interface block** — Review and update the `## Interfaces` section in this project's CLAUDE.md with any changes to what it produces, consumes, or contracts with other projects. If the project has no CLAUDE.md, create one with the Interfaces section.

3. **Constellation file** — Propagate any interface changes to `TRAXIS_ECOSYSTEM.md` at this root. Update the relevant project entry. If no interface changes, skip.

4. **To-do reconciliation** — This is the **only** to-do-shaped output Wolfgang sees at close. There is no separate "Open items" section. For each project touched or discussed this session, sweep its CLAUDE.md `Next Steps` (or equivalent backlog) section against actual session work and `git diff`, then propose inline edits in one pass:
   - **Strike or remove** items now DONE.
   - **Drop** items that became OBSOLETE.
   - **Reorder** if priorities shifted.
   - **Add** new items surfaced this session — including decisions deferred, blockers, and anything needing Wolfgang's human action. Tag urgent ones `[NEEDS WOLFGANG]` and sort to the top of the section so urgency is not lost in a flat list.
   - **Cross-cutting items** that don't belong to a single project go in the root CLAUDE.md's `Next Steps` section (create it if absent).
   - If a touched project has no `Next Steps` section, add one.

   Be conservative on done-judgment: when unsure an item is fully complete, leave it and flag at beat 4. The presentation at beat 4 is one consolidated to-do view — per-project blocks of proposed `Next Steps` edits — not a separate open-items list plus a separate backlog sweep.

5. **Git commit** — After "authorized" at beat 5, stage and commit all session changes to the repo. Use a concise commit message summarizing the session's work.

Present all of the above (steps 1-4) for review, then say: `Ready to authorize close, sir`

### Lightweight Variant

If context is low or the session was short, acceptable minimum is session log update plus one line: "Interfaces unchanged" or "Interfaces changed — see session log." Still requires the four-beat ritual.

## Interface Block Standard

Every project's CLAUDE.md should have a `## Interfaces` section with exactly three fields:

```
## Interfaces
Produces: <files, databases, API endpoints, services this project writes or exposes>
Consumes: <files, databases, APIs, services this project reads or depends on>
Contracts: <cross-project assumptions — paths, formats, schemas — that another project would break if changed>
```

These are parsed by the nightly scanner (`25. Agent Exploration/scan_projects.py`) and aggregated into `TRAXIS_ECOSYSTEM.md`.

## Next Steps

- **Cross-cutting: roll all Flask services off Werkzeug onto waitress** — every service Overseer manages via `pythonw app.py` (P17 COTS, P31 Photo, P5/Tool Kiosk, P34 Shop Scheduler, etc.) shares the same restart-fragility surfaced 2026-05-04: Werkzeug's dev server has no graceful shutdown, so `Popen.terminate()` leaves zombie LISTEN sockets when there are pending CLOSE_WAITs. A standard pattern: `from waitress import serve; serve(app, host=..., port=..., channel_timeout=30)` plus a shared `POST /api/shutdown` route. Worth doing as a single sweep across all of them rather than per-service. Overseer's `_stop_process` should call `/api/shutdown` first (5s budget) before `terminate()`. P31 Next Steps has the detailed fix plan.
