# Project 23: Air Compressor Communication

Web GUI for monitoring and controlling the EMAX 20HP Rotary Screw air compressor (Serial EC00002447) via Modbus TCP through a PUSR DR302 gateway.

## Architecture

- **Controller:** Logik 26-S PLC (Logika Control, Italy)
- **Gateway:** PUSR DR302 Modbus TCP at `10.1.1.180:502`, Slave ID 1
- **Web service:** Flask on port 8085, polled by Overseer health check
- **Register map:** `REGISTER_MAP.md` (official + empirical)

## Key Features

- Live pressure, temperature, status, maintenance counters
- Weekly timer schedule read/write (HR 1800/1920 empirical bases)
- Fieldbus START/STOP/ALARM_RESET via HR 1036
- Controller RTC clock display (HR 2048-2051)
- **Timer watchdog** — auto-recovers from missed scheduled starts caused by safe alarms (A18-BLACK OUT, A43-DST, A48/A49-RESTART) and re-engages timer after panel bypasses. Critical/safety alarms always require manual panel intervention.

## Timer Watchdog

The watchdog runs every poll cycle (3s) and checks four conditions in priority order:
1. Alarm just cleared last cycle → send START
2. Blocked by safe alarm during scheduled ON window → clear alarm (start next cycle)
3. Timer bypassed by panel → resume schedule
4. Compressor OFF during scheduled window, no alarm → send START

Safe alarm set: `{18, 43, 48, 49}`. 60-second cooldown between actions.

## Gateway Recovery (SLAVE_SILENT)

**Symptom:** GUI shows "Connected" green dot BUT `Controller Clock: ---`, temperature stuck at `32°F` (raw 0°C), pressure `0 PSI`, all weekdays show `OFF`, and writes (START / schedule edits) fail with **"connection forcibly closed"** (WSAECONNRESET / 10054). This is the DR302 gateway in a hung half-state — TCP socket alive, Modbus-RTU passthrough to the Logik 26-S dead. Reads return zeros; writes get RST'd. Watchdog cannot recover from this because its own writes fail too (look for a climbing `Interventions:` count with no effect).

**Fix, easiest first:**

1. **Click "↻ Reboot Gateway" in the compressor GUI** (fixes ~90% of cases, no compressor disruption). The button lives in the second status bar (next to `Interventions:`). Triggers `POST /api/gateway/reboot` which calls the DR302 web admin on the user's behalf — no need to remember the URL or credentials. 60-second cooldown to prevent double-clicks. Gateway is back in ~10-15s; next poll cycle (3s) repopulates the GUI.

2. **Manual reboot via the DR302 web UI** (fallback if the button is broken or you're debugging it):
   - URL: **http://10.1.1.180**
   - Credentials: **`admin` / `admin`** (HTTP Basic, realm `USR-DR302` — factory default, never rotated, confirmed 2026-05-23)
   - Manage page → **Restart Module** button
   - **Diagnostic while you're in there:** on the Serial/Port page, if Send count is climbing but Recv count is frozen, the RS-485 link or the controller is the problem, not the gateway.

3. **Main-power-cycle the compressor** (cycles controller + gateway together since DR302 draws from controller's +15Vdc rail — see `PROJECT-PLAN.md:53`):
   - Panel OFF → throw main disconnect → wait ~30s → power back on → controller boots in ~10-20s

4. **DO NOT open the cabinet to pull the gateway V+ wire** — 208/230V 3-phase terminals are inches away. Options 1-3 do the same thing without the risk.

**Implementation note for option 1:** the `POST /api/gateway/reboot` handler issues `GET http://{GATEWAY_IP}/login.cgi` with Basic auth and `Referer: /manage.shtml` — that's what the DR302's `manage.shtml` form does when "Restart Module" is clicked. If a future firmware breaks this, the documented fallback in the device's JS is `GET /misc.cgi?restart`. Mid-call `ConnectionResetError` / `URLError` is treated as success (the gateway kills its own socket while restarting).

## Next Steps

- **First real-world test of the Reboot Gateway button** — next SLAVE_SILENT incident will be the proof. Implementation is verified-deployed (PID changed, endpoint returns 405, button in DOM as of 2026-05-23) but the actual reboot path (`POST /api/gateway/reboot` → `GET /login.cgi` w/ Referer → gateway restart) wasn't exercised live because the gateway had just been hand-rebooted. If the first click fails to reboot the device, swap `'/login.cgi'` for `'/misc.cgi?restart'` in `gateway_reboot()` — one-line change, documented fallback.
- **Fix the flaky PID-changed check in `srv-01-setup/pull_and_restart_aircompressor.ps1`** — 4s sleep is too short for Overseer's async restart; on 2026-05-23 deploy the script reported "PID unchanged restart may have failed" when the restart had in fact succeeded (verified by `/api/gateway/reboot` returning 405 from .178). Better signal: have the script verify the new endpoint shape directly (configurable marker URL + expected status code) instead of, or in addition to, the PID compare.
- **Monitor watchdog effectiveness** — first real test will be the next power blip or Monday morning after a weekend. Check `watchdog_interventions` counter and `/api/clock` endpoint.
- **[Optional] Add clock-sync feature** — if the controller's RTC drifts, add a `/api/clock/set` endpoint that writes correct time to HR 2048-2051. Not urgent since clock was accurate this session.
- **[Optional] Add alarm history endpoint** — decode HR 768-818 alarm records (20 entries, 5 bytes each: 4B timestamp + 1B alarm code) and expose via `/api/alarm_history`. Would help diagnose why the compressor didn't start without SSH access.

## Interfaces

Produces: Web GUI on port 8085 (`/`, `/api/status`, `/api/data`, `/api/clock`, `/api/gateway/reboot`); Modbus TCP commands to Logik 26-S controller (fieldbus start/stop/alarm-reset/schedule-write/timer-resume via HR 1036); HTTP soft-reboot of DR302 gateway via `GET http://10.1.1.180/login.cgi` with Basic auth (admin/admin); timer watchdog auto-recovery actions (logged to stdout, visible in Overseer).

Consumes: EMAX compressor Logik 26-S via DR302 Modbus TCP gateway at `10.1.1.180:502` (Slave ID 1); DR302 web admin at `http://10.1.1.180` (Basic auth, admin/admin) for soft-reboot; Overseer health monitoring on port 8085 (`/api/status`).

Contracts: Modbus register addresses per `REGISTER_MAP.md` — Group 4 live data at HR 1024-1037, Group 6 counters at HR 1536-1553, Group 7 timers at HR 1800/1920 (empirical, not official HR 1792), Group 8 system time at HR 2048-2051. Timer watchdog only auto-resets alarms in `SAFE_AUTO_RESET_ALARMS = {18, 43, 48, 49}` — all other alarms require manual panel intervention. **DR302 reboot endpoint** (`POST /api/gateway/reboot`) has a 60s server-side cooldown; mid-call `ConnectionResetError` from the gateway is treated as the success signal (gateway kills its own socket while restarting). If PUSR ships a firmware that breaks `/login.cgi`, the documented fallback URL is `/misc.cgi?restart`.
