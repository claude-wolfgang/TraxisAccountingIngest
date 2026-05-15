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

- **[Optional] Document the Flask template-cache restart rule** (surfaced 2026-05-15 on P31). Jinja2 caches compiled templates per-process in production mode (no `TEMPLATES_AUTO_RELOAD`), so editing any `templates/*.html` in any of the 9 Overseer-managed Flask services requires a service restart to take effect — `static/*.js`/`static/*.css` reload fine without restart. Worth either (a) one-line note in this root CLAUDE.md so Claude doesn't have to rediscover it next time, or (b) enabling `app.config["TEMPLATES_AUTO_RELOAD"] = True` across the fleet (small perf cost on every request, but a friendlier deploy story). Caught on P31 today when a template+JS change appeared half-broken until Overseer restart cleared the template cache.
- **[NEEDS WOLFGANG] srv-01 cutover** — srv-01 is upstairs, headless, at static IP `10.1.1.161`, `TRAXIS-SRV-01`. TraxisOverseer NSSM service installed but **stopped, Start mode = SERVICE_DEMAND_START**. To cut over from .71: (1) stop .71's Overseer + service_wrapper. (2) Copy state DBs to `T:\traxis\data\` on srv-01: `C:\FASData\monitoring.db` + `shophub.db`, `22/tool-kiosk/data/tooling.db`, `25/audit.db`, `31/photo-uploader/data/` tree, `lathe_programs.json`, `document_mappings.json`. (3) Set `TRAXIS_FOCAS_DB` env var to the copied path. (4) Update kiosk PC bookmarks (10.1.1.142, etc.) from `10.1.1.71:port` → `10.1.1.161:port`. (5) On srv-01: `nssm set TraxisOverseer Start SERVICE_AUTO_START; nssm start TraxisOverseer`. (6) Soak 48-72hr. (7) Delete `TraxisOverseer.lnk` from .71's Startup folder to decommission .71's services role.
- **srv-01 install FocasMonitor (C# Windows service)** — copy `C:\FocasMonitor\` self-contained build from .71 to srv-01, register via `sc create` or the bundled installer. Verify TCP/8193 reachable from srv-01 to each CNC (M2, M3, M6, M8, T2). Best done as part of state migration so monitoring.db can be copied with FocasMonitor stopped.
- **[Optional] Rotate leaked .pem keys** — `11. Proshop Mobile App/proshop-mobile-backend/certs/key.pem` and `30. Material Label Extension/deployment/signing_key.pem` are in the GitHub repo's commit history. `.gitignore` rewrite on 2026-05-10 stops them from re-entering new commits but history still exposes them. Regenerate the keys, replace use sites, commit; consider whether the existing history matters (repo is private; access has always been just `claude-wolfgang`).
- **[Optional] Centralize logs to `TRAXIS_LOGS`** — services currently log to per-service paths. Standardize on `<TRAXIS_LOGS>/<service-name>/` for one-place greppability. Touches each service's logging setup; nice polish but not load-bearing.
- **Phase A literal-fallback cleanup** — `overseer.py` and `25. Agent Exploration/config.py` retain literal-secret + literal-path fallbacks in code so .71 keeps working without env vars set. Once srv-01 has been the sole production host for 1-2 weeks, strip those literal fallbacks so secrets only exist in env vars / `.traxis.env`, not in committed code.
- **Audit Phase A waitress dep on all service hosts** — `.242` (LabelPrintService) was missed in the 5/9 Phase A `pip install` sweep; service was dead from 5/9 until 5/13. Any other Phase A service host not yet pip-installed? Quick check: each `requirements.txt` lists `waitress>=2.1`; the `start_*.bat` should print "Serving on http://... (waitress)". Run the `install_print_service_deps.bat` pattern on any missed host.
- **Enable Windows LocalDumps for pythonw.exe on .71 (and srv-01)** — `HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe` with `DumpFolder`, `DumpCount`, `DumpType=2`. Cheap; next mystery Overseer death will leave a `.dmp` we can actually analyze. Justified by the 5/11 silent kill (no traceback, no event, no dump).
- **[Optional] Watchdog-of-the-watchdog on .71** — scheduled task curling `http://localhost:8060/api/status` every 5 min, relaunch via `Win32_Process.Create` if down. Cheap belt-and-suspenders during the srv-01 soak. Skip if cutover is imminent — NSSM on srv-01 makes this moot.
