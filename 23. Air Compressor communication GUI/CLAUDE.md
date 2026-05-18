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

## Next Steps

- **Monitor watchdog effectiveness** — first real test will be the next power blip or Monday morning after a weekend. Check `watchdog_interventions` counter and `/api/clock` endpoint.
- **[Optional] Add clock-sync feature** — if the controller's RTC drifts, add a `/api/clock/set` endpoint that writes correct time to HR 2048-2051. Not urgent since clock was accurate this session.
- **[Optional] Add alarm history endpoint** — decode HR 768-818 alarm records (20 entries, 5 bytes each: 4B timestamp + 1B alarm code) and expose via `/api/alarm_history`. Would help diagnose why the compressor didn't start without SSH access.

## Interfaces

Produces: Web GUI on port 8085 (`/`, `/api/status`, `/api/data`, `/api/clock`); Modbus TCP commands to Logik 26-S controller (fieldbus start/stop/alarm-reset/schedule-write/timer-resume via HR 1036); timer watchdog auto-recovery actions (logged to stdout, visible in Overseer).

Consumes: EMAX compressor Logik 26-S via DR302 Modbus TCP gateway at `10.1.1.180:502` (Slave ID 1); Overseer health monitoring on port 8085 (`/api/status`).

Contracts: Modbus register addresses per `REGISTER_MAP.md` — Group 4 live data at HR 1024-1037, Group 6 counters at HR 1536-1553, Group 7 timers at HR 1800/1920 (empirical, not official HR 1792), Group 8 system time at HR 2048-2051. Timer watchdog only auto-resets alarms in `SAFE_AUTO_RESET_ALARMS = {18, 43, 48, 49}` — all other alarms require manual panel intervention.
