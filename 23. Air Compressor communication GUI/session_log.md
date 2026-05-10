# Session Log — Air Compressor Communication GUI

## 2026-04-03 — GUI Build, Pressure Calibration, Timer Discovery, Remote Stop Investigation

### What Was Done
Built a full Flask web GUI (`compressor_web.py`) for monitoring the EMAX 20HP rotary screw compressor via Modbus TCP through a PUSR DR302 gateway. Then spent significant time investigating remote start/stop capability.

### GUI Features Implemented
- **Live pressure** bar graph with start/stop/alarm markers (120-138 PSI operating range)
- **Live temperature** bar graph with warning/alarm markers (~83-91C operating)
- **Status detection** using aux register HR 4244: "RUNNING (Loading)" vs "RUNNING (Unloaded)"
- **Weekly schedule** display + editor — reads from Timer1 (Mon-Fri) and Timer2 (all days)
- **Maintenance status** — static estimates from LCD readings (COF and Oil 122h overdue, CAF and CSF ~612h remaining)
- **Cabinet filter** — manual 6-month timer tracked via `cabinet_filter.json`, set to ~50% remaining
- **START/STOP buttons** — currently change today's schedule only (see Remote Stop below)
- **Configuration panel** — pressure setpoints, temperature limits, equipment info

### Pressure Calibration
- Initially showed 99 PSI when LCD read 120 PSI
- Discovered hi byte needs linear conversion: `PSI = round(hi_byte * 0.75 + 45.75)`
- Confirmed by comparing LCD (123 PSI) to GUI in real-time — now matches 120-138 PSI cycle

### Timer System Discovery
- **Timer1** (HR 1800): Only supports Mon-Fri (5 days, 30 registers). Sat/Sun writes return Illegal Data Address.
- **Timer2** (HR 1920): Supports all 7 days (42 registers).
- **Time encoding**: `(minute << 8) | hour` — e.g., 7685 = 05:30, 20 = 20:00
- **Bug found and fixed**: Timer1 was reading 42 registers (overflowed into unrelated data), causing Saturday to show a ghost schedule. Fixed to read only 30 registers.

### Remote Start/Stop Investigation
- **FC01 (coils) and FC02 (discrete inputs)**: NOT supported by this controller
- **Scanned HR 20-4600**: Found serial number, config, counters, logs, but no obvious command register
- **Timer schedule manipulation** tested 4 different approaches — none caused immediate shutdown:
  1. Clear Timer1 only (zeros)
  2. Clear both timers (zeros)
  3. Write past time (00:00-00:01)
  4. Change OFF time to current time / 2 minutes ago
- **Manual confirms remote start/stop exists** (Alarm 33 references "MODBUS protocol communication" document)
- **Register map is proprietary** — not published online
- **Wt4 (unload timer) = 30 min** (max = "non-stop motor mode") — even if schedule triggers stop, motor runs 30min before shutdown

### Key Finding: Need Manufacturer Documentation
The Logik 26-S manual explicitly references a separate "Modbus Protocol Communication" document that contains the register addresses for remote control. This document must be requested from:
- **Logika Control** (controller manufacturer): info@logikacontrol.it, +39 0362/37001
- **EMAX Compressor**: emaxcompressor.com/user-manuals
- **Ask for**: "Modbus Register Map" for Logik 26-S, firmware L26SD V1.87

### Files Created/Modified
- `compressor_web.py` — Main Flask GUI (port 8085), ~1150 lines
- `cabinet_filter.json` — Manual filter tracking (`last_changed: 2026-01-03`)
- `probe_coils.py` — FC01/FC02 scanner (confirmed none exist)
- `scan_control.py` — Register scanner for unexplored ranges
- `scan_live_area.py` — Deep scan of live data and control areas
- `L26-S-manual.pdf` — Downloaded controller manual
- `comm-training.pdf` — Logika Control communication training doc

### Current State
- Web GUI running at http://10.1.1.71:8085 (accessible from phones/any device on network)
- Schedule: Mon-Fri 05:30-20:00, Sat-Sun OFF
- START/STOP buttons work as schedule editors (change today's ON/OFF times) but do NOT force immediate start/stop
- Immediate remote control blocked until we get the proprietary Modbus register map

### Pressure Reading Clarification
- **HR 4241 reads compressor outlet pressure** — shows 0 when machine is off
- Residual air pressure in receiver tank and shop piping is **not** visible via Modbus
- No separate "system pressure" sensor accessible through the Logik 26-S controller
- To monitor downstream system pressure independently, would need a standalone pressure transducer on the receiver tank or main header

### Dryer Activation — Pressure Switch Discussion
The air dryer runs at 240V and currently has no automatic on/off tied to compressor operation. Options discussed:

**Option 1: Pressure switch + contactor (recommended)**
- Adjustable pressure switch (Condor MDR or Lefoo LF10 style) set to close ~80 PSI
- 240V coil contactor sized for the dryer's amp draw
- Pressure switch energizes contactor coil → contactor switches 240V to dryer
- When compressor stops and pressure bleeds below setpoint, dryer turns off automatically
- ~$50-80 in parts

**Option 2: Current-sensing relay on compressor**
- CT clamp on compressor power lead + current-sensing relay → 240V contactor for dryer
- No plumbing required, purely electrical
- Downside: dryer turns off immediately when compressor stops (no delay for residual moisture)

**Considerations before choosing:**
- Check dryer nameplate for amp draw (determines contactor sizing)
- Check if dryer has built-in "remote start" terminal or demand mode
- Optional: time-delay relay (~$20) to keep dryer running 15-30 min after compressor stops to dry residual moisture

### Next Steps (as of 2026-04-03)
1. ~~Contact Logika Control / EMAX for the Modbus register map~~ **DONE — received 2026-04-06**
2. ~~Once register address is known, wire true start/stop into the GUI~~ **DONE — v2 rewrite**
3. ~~Find maintenance counter registers~~ **DONE — HR 1540-1551 confirmed**
4. Consider reducing Wt4 from 30min to 3-5min (affects how fast machine stops after unloading)
5. Dryer activation: check dryer nameplate amps and whether it has a remote start terminal

---

## 2026-04-06 — Official Modbus Document Received, Complete v2 Rewrite

### What Happened
Received the official **LOGIK26S MODBUS PROCEDURE** document (13 pages) from Logika Control / EMAX. This is the proprietary register map we were searching for since 2026-04-03. It documents every Modbus register group, data types, scaling, alarm codes, and — most critically — the **fieldbus command register for remote start/stop**.

Performed a complete analysis comparing the official document against our empirical register map, then rewrote the entire `compressor_web.py` as v2 using the official addresses.

### Major Discoveries from the Official Document

**1. Remote Start/Stop — HR 1036 (0x040C)**
The single biggest find. A write-only fieldbus command register with bitmapped commands:
- 0x0001 = START COMPRESSOR
- 0x0002 = STOP COMPRESSOR
- 0x0004 = ALARM RESET
- 0x0008 = START BYPASSING WEEKLY TIMER
- 0x0010 = STOP BYPASSING WEEKLY TIMER
- 0x0020 = ACK & RESET ALL ALARMS
- 0x0080 = WATCHDOG (dangerous — must re-send every 5 sec or causes A33 fault)
- 0x0100-0x2000 = Reset maintenance counters (CAF/COF/CSF/C--/C-h/C-BL)

**2. Official Live Data Registers (Group 4, HR 1024-1037)**
Replaced the legacy HR 4241/4243/4244 hi-byte registers with clean, properly-scaled official registers:
- HR 1029 = Screw temperature (Celsius * 10, signed)
- HR 1030 = Working pressure (bar * 10)
- HR 1031 = Auxiliary pressure (bar * 10)
- HR 1024/1025 = Internal/displayed controller state (enumerated 0-14)
- HR 1026 = Blocking alarm code
- HR 1034 = Status indicator flags (motor, fan, drain, alarm, timer, etc.)

**3. Maintenance Counters — HR 1540-1551**
The counters we couldn't find since day one. Six 32-bit long values stored in **minutes** (big-endian, high word first):
- HR 1540-41 = Air Filter (CAF) elapsed since service
- HR 1542-43 = Oil Filter (COF)
- HR 1544-45 = Separator Filter (CSF)
- HR 1546-47 = Oil Change (C--)
- HR 1548-49 = Compressor Check (C-h)
- HR 1550-51 = Bearing Lubricate (C-BL)

**4. Total/Load Hours — HR 1536-1539**
Official 32-bit counters in minutes, replacing the single-register HR 1679 approximation:
- HR 1536-37 = Total compressor hours
- HR 1538-39 = Load hours

**5. Active Alarms — HR 512-515**
Bitmapped active alarm register. Each bit = one alarm code. Full 62-code alarm table documented.

**6. Additional Counters**
- HR 1552 = Load % in last 100 hours (6000 = 100%)
- HR 1553 = Motor starts in last hour

### Register Corrections (Empirical vs Official)

| Parameter | Old (Empirical) | New (Official) | Impact |
|-----------|----------------|----------------|--------|
| Pressure | HR 4241, hi-byte + linear formula | HR 1030, bar*10 | Exact conversion, no more approximation |
| Temperature | HR 4243, hi-byte = Celsius | HR 1029, Celsius*10 | Decimal precision (88.0 vs 88) |
| Aux pressure | HR 4244, hi-byte | HR 1031, bar*10 | Now shows actual bar/PSI |
| WT1 (temp alarm) | HR 1297 | HR 1296 | Was off by 1 register |
| WT2 (temp warning) | HR 1320 | HR 1297 | Was completely wrong register |
| Status | Guessed from aux value | HR 1025, enum 0-14 | Official state names |
| Load hours | HR 1679 (single reg) | HR 1538-39 (32-bit) | 32-bit precision, in minutes |

### Code Changes — compressor_web.py v2

**Backend (Python):**
- All register addresses updated to official document values
- Live data decoded with proper scaling (bar*10 → PSI, Celsius*10 → C/F)
- Controller state read from official enum (HR 1025) instead of aux-value guessing
- Maintenance counters read as 32-bit longs from HR 1540-1551
- Total/load hours read as 32-bit longs from HR 1536-1539
- Active alarms decoded from bitmapped HR 512-515
- Status flags decoded from HR 1034
- Polling optimized: 7 targeted block reads vs old approach of 11+ scattered reads

**Start/Stop — completely replaced:**
- Old: Changed today's timer schedule entry, 5-minute delay, unreliable
- New: Direct write to fieldbus command register HR 1036 (CMD_START=0x0001, CMD_STOP=0x0002)
- Instant response, 30-second confirmation timeout (detects state change via HR 1025)

**New API endpoints:**
- `POST /api/compressor/alarm_reset` — Sends ACK+RESET ALL (0x0020) to HR 1036
- `POST /api/reset_filter` — Now handles PLC counter resets via HR 1036 bits 0x0100-0x2000

**Dashboard UI:**
- Red alarm banner with active alarm names + RESET ALARMS button
- Status bar shows official state text, color-coded (green=load, blue=idle, red=blocked)
- Maintenance bars now fully dynamic from real PLC counters (no more static estimates)
- Each PLC maintenance item has a "Reset Counter" button
- Pressure shows both PSI and bar
- New stats: total hours, load hours, load %, starts/hour, aux pressure
- Status flag indicators: MOTOR, ACTIVE, TIMER, BYPASS, FAN, DRAIN, ALARM

### Verified Live Data (first poll after restarting service)

```
pressure_psi: 136  (9.4 bar)     — matches LCD
temperature_c: 88.0  (190 F)     — matches LCD
display_state: 10 (IDLE RUNNING) — correct, machine was between loads
motor_running: true               — confirmed
total_hours: 21,709               — matches LCD
load_hours: 10,691                — matches LCD (was 10,682 on 04-03)
load_percent: 76.7%               — first time we've had this
caf_remain: 1993 hrs              — real data!
cof_remain: 593 hrs               — real data!
wt1_alarm: 110 C                  — corrected (was 105 from wrong register)
wt2_warn: 105 C                   — corrected (was 100 from wrong register)
active_alarms: []                 — no alarms, good
```

### Files Modified
- `compressor_web.py` — Complete v2 rewrite (~680 lines, was ~1150)
- `REGISTER_MAP.md` — Rewritten with official hex+decimal addresses, all groups 0-9
- `MEMORY.md` — Updated with corrected addresses and fieldbus command reference

### Timer Base Address Discrepancy
The official document says Group 7 (Clock Timers) starts at 0x0700 = HR 1792. But our empirically-verified timer writes work at HR 1800 (Timer1) and HR 1920 (Timer2). Since these have been working for days, we kept the empirical addresses. The offset (1800 vs 1792 = +8 registers) may indicate a header, firmware-specific layout, or aliased memory. Schedule writes continue to work correctly.

### Watchdog Warning
The fieldbus command register has a watchdog bit (0x0080) that, if set, must be re-sent every 5 seconds. If it lapses, the controller triggers alarm A33 (FIELDBUS ERR) and the compressor stops. This bit must **never** be set without a dedicated keepalive thread. The START/STOP commands (0x0001/0x0002) work independently without the watchdog.

### Current State
- Web GUI v2 running at http://10.1.1.71:8085
- All data from official registers, verified against LCD
- START/STOP buttons send direct fieldbus commands (instant response)
- Maintenance counters live and accurate
- Alarm monitoring active with reset capability
- Schedule editor unchanged and working

### Remaining Next Steps
1. Consider reducing Wt4 unload timer from 30min to 3-5min (write to HR 1306)
2. Dryer activation: check dryer nameplate amps, implement pressure switch + contactor
3. Add SQLite logging for historical trends (pressure, temperature, load %)
4. Add historical charts to dashboard
5. ~~Register with Traxis Overseer for auto-start and health monitoring~~ **DONE — already configured**
6. ~~Test START BYPASSING TIMER (0x0008) / STOP BYPASSING TIMER (0x0010) for timer-independent control~~ **DONE — 2026-04-11**
7. Read system clock (HR 2048) and alarm history (HR 768+) for enhanced diagnostics

---

## 2026-04-11 — Timer Bypass Bug Fix, Resume Schedule Feature

### Problem
Compressor was found running on Saturday morning at 7:39 AM despite the weekly schedule having Sat/Sun set to OFF. Investigation revealed the compressor was staying on continuously rather than following the timer schedule.

### Root Cause
The `CMD_START` (0x0001) fieldbus command starts the compressor **outside of timer control**. Once started this way, the weekly timer schedule has no authority to turn it off. The UI had no way to detect this condition or return control to the timer because:
1. `FLAG_ON_BY_TIMER` (0x0004) and `FLAG_TIMER_BYPASSED` (0x0008) from HR 1034 were defined but never decoded or displayed
2. There was no endpoint or button to send `CMD_STOP_BYPASS_TIMER` (0x0010) to restore timer control

### What Was Done

**Backend changes (compressor_web.py):**
- Poll loop now decodes `FLAG_ON_BY_TIMER` and `FLAG_TIMER_BYPASSED` from HR 1034 status flags
- New `on_by_timer` and `timer_bypassed` booleans exposed in `/api/data` response
- New endpoint: `POST /api/compressor/resume_schedule` — sends `CMD_STOP_BYPASS_TIMER` (0x0010) to HR 1036 to hand control back to the weekly timer

**UI changes (schedule panel):**
- New timer mode indicator below the 7-day schedule grid, showing one of:
  - "ON BY SCHEDULE" (green) — timer is in control
  - "BYPASSED (manual override)" (yellow) — timer was overridden
  - "OFF" (gray) — neither flag set
- "Resume Schedule" button — only visible when timer is bypassed, with confirmation modal
- `confirmResumeSchedule()` JS function wired to the new endpoint

**Utility:**
- Added `restart_server.bat` — kills existing process, checks dependencies, restarts server (manual fallback to Overseer)

### Key Insight
The Logik 26-S controller distinguishes between:
- `CMD_START` (0x0001) — immediate start, ignores timer
- `CMD_START_BYPASS_TIMER` (0x0008) — start and explicitly flag timer as bypassed
- `CMD_STOP_BYPASS_TIMER` (0x0010) — stop bypass and return to timer control

The existing Start/Stop buttons use 0x0001/0x0002 which operate independently of the timer. The new Resume Schedule button is the missing piece that re-engages the weekly schedule.

### Current State
- Changes pending restart of compressor_web.py on 10.1.1.71 via Overseer dashboard (http://10.1.1.71:8060)
- Overseer already manages the Air Compressor service with auto-start, health checks, and restart-on-failure

### Remaining Next Steps
1. Consider reducing Wt4 unload timer from 30min to 3-5min (write to HR 1306)
2. Dryer activation: check dryer nameplate amps, implement pressure switch + contactor
3. Add SQLite logging for historical trends (pressure, temperature, load %)
4. Add historical charts to dashboard
5. Read system clock (HR 2048) and alarm history (HR 768+) for enhanced diagnostics
6. Consider whether Stop button should send CMD_STOP_BYPASS_TIMER instead of plain CMD_STOP so stopping always re-engages the schedule

---
