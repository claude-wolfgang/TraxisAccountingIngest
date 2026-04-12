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

4. **Open items** — Output a section titled "Open items requiring Wolfgang" listing: decisions deferred, things blocked on external input, anything needing human action before the next session.

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
