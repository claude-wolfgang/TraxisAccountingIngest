# Traxis Manufacturing — Project Ecosystem

This root CLAUDE.md covers all 27+ projects under `Proshop Automation and Claude Projects`.
Claude Code loads it automatically at session start.

## Quick Context

- **Owner:** Wolfgang
- **ERP:** ProShop (GraphQL API, OAuth 2.0)
- **CAM:** Fusion 360
- **Collector PC:** 10.1.1.71 (MainPC) — runs Overseer, dashboards, services
- **Kiosk PC:** 10.1.1.141 — tool kiosk touchscreen (Chrome `--kiosk`; backend on .71)
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

- **[NEEDS WOLFGANG] Kiosk PC .141 follow-ups — autologon + primary monitor swap** (surfaced 2026-05-22). After today's cutover, the kiosk auto-starts on logon via the registered `TraxisToolKiosk` scheduled task, BUT requires a human to log in first (no autologon). Two on-site improvements bundled: (1) configure Windows autologon for the `traxi` user (registry: `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon` → `AutoAdminLogon=1`, `DefaultUserName`, `DefaultPassword`); (2) swap primary monitor from the touchscreen (currently DISPLAY1) to the regular monitor for keyboard-side UX — Settings → System → Display → "Make this my main display". Launcher already auto-detects touchscreen via Win32 Pointer Device API, so monitor swap won't break kiosk targeting. Optional bonus while there: enable RDP (`fDenyTSConnections=0` + firewall rule) so future kiosk config changes don't require physical access.
- **[NEEDS WOLFGANG] Compressor controller's PSI display sometimes shows 32°F / 0 PSI on dashboard while panel runs fine** — diagnosed 2026-05-22 as duplicate-process bug (two `compressor_web.py` on .71 contending for the Modbus connection) which is RESOLVED on srv-01 (single process). But the SLAVE_SILENT failure mode (TCP up to gateway, no real data from controller) IS a real possibility for future field failures (gateway hang, RS-485 break, controller fault). Designed but not built: state-machine UI in `compressor_web.py` that detects HEALTHY / SLAVE_SILENT / GATEWAY_UNREACHABLE / PANEL_BYPASS / SCHEDULE_EMPTY via RTC+serial sentinel reads + value-jitter checks, renders actionable banners per state, persists last-known-good schedule to disk for auto-restore after panel wipes. Filed because today's `[NEEDS WOLFGANG]` panel-bypass behavior on physical ON is a known weakness — operator presses ON, controller flips to manual-bypass mode, schedule registers go blank, app can't recover. Estimate: ~one focused session.
- **[NEEDS WOLFGANG] Overseer adoption logic permits duplicates** — found 2026-05-22 during cutover: .71 had TWO running TraxisOverseer processes (PIDs 1424 + 9640) and TWO `compressor_web.py` (PIDs 21088 + 12108), plus duplicates of every other service after Overseer's "adopt existing process" logic latched onto whichever PID it saw first while orphaned siblings kept polling. Causes silent service contention bugs (the compressor zero-fill we chased today). Overseer's `_adopt_or_start` should reject adoption when more than one matching process exists, and either pick one + kill the rest, or refuse to start the service and surface a duplicate-detected alert.
- **AgentScheduler: bump audit stderr from log.debug to log.warning** (surfaced 2026-05-22). The `audit_ok = ok and rc in (0, 1)` tolerance landed today (commit `8d1fbac`), so the "audit failing" false-alarm is resolved. But the original observability concern is still real: when `run_audit.py` truly fails (timeout, exception, or actual `failure`/`error` severity findings as opposed to mere `warning` findings), `_run_task` logs stderr at `log.debug` truncated to 500 chars, and the file handler is at INFO level. So real audit failures silently disappear. Bump to `log.warning` and uncap the truncation (or raise to 8KB).
- **Soak srv-01 for 1-2 weeks before Phase A literal-fallback cleanup** — `overseer.py` and `25. Agent Exploration/config.py` still carry literal-secret + literal-path fallbacks in code from when .71 needed to work without env vars set. Once srv-01 has been sole production host for 1-2 weeks, strip those fallbacks so secrets only exist in `.traxis.env` / Machine env vars, not committed code.
- **Enable Windows LocalDumps for pythonw.exe on srv-01** — `HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\pythonw.exe` with `DumpFolder`, `DumpCount`, `DumpType=2`. Cheap; next mystery service death will leave a `.dmp` we can actually analyze. Originally scoped for .71 (5/11 silent kill) but .71 is decommissioned — the rule still applies to srv-01.
- **[Optional] Document the Flask template-cache restart rule** (surfaced 2026-05-15 on P31). Jinja2 caches compiled templates per-process in production mode (no `TEMPLATES_AUTO_RELOAD`), so editing any `templates/*.html` in any of the 9 Overseer-managed Flask services requires a service restart to take effect — `static/*.js`/`static/*.css` reload fine without restart. Worth either (a) one-line note in this root CLAUDE.md so Claude doesn't have to rediscover it next time, or (b) enabling `app.config["TEMPLATES_AUTO_RELOAD"] = True` across the fleet (small perf cost on every request, but a friendlier deploy story).
- **[Optional] Rotate leaked .pem keys** — `11. Proshop Mobile App/proshop-mobile-backend/certs/key.pem` and `30. Material Label Extension/deployment/signing_key.pem` are in the GitHub repo's commit history. `.gitignore` rewrite on 2026-05-10 stops them from re-entering new commits but history still exposes them. Regenerate the keys, replace use sites, commit; consider whether the existing history matters (repo is private; access has always been just `claude-wolfgang`).
- **[Optional] Centralize logs to `TRAXIS_LOGS`** — services currently log to per-service paths. Standardize on `<TRAXIS_LOGS>/<service-name>/` for one-place greppability. Touches each service's logging setup; nice polish but not load-bearing.
- **[Optional] Sweep CLAUDE.md files for `10.1.1.71` references and update to `10.1.1.161` where applicable** — interfaces, examples, hardcoded hostnames in docs. Mostly text-only; the code itself reads env vars. Project 1, 22, 25 CLAUDE.mds touched today already updated; project 12, 17, 19, 31 and others probably still say "MainPC (10.1.1.71)".
