# Air Compressor Communication GUI — Project Plan

## Overview

Build a network-connected monitoring and control GUI for the EMAX rotary screw air compressor
(the yellow machine in the shelter behind the building). The compressor's Logik 26-S PLC controller
supports MODBUS RTU over RS485. A small Ethernet gateway in the shelter converts this to
MODBUS TCP, making the compressor accessible from any PC on the LAN.

---

## Equipment

### Compressor
- **Make/Model:** EMAX Rotary Screw, Model ERS0200003
- **Motor:** 20HP, 3-phase, 208/230V, 57.5/55.2 amps
- **Output:** 85 SCFM @ 100 PSI
- **Max PSI:** 145 / Min PSI: 90
- **Control Type:** Standard Drive (Y-Delta start)
- **Controller:** Logik 26-S by Logika Control (Italy), Revision 1, 04.12.2015
- **Serial:** EC00002447-H / Job: 60284

### Gateway (Ordered)
- **Device:** PUSR DR302 DIN Rail Modbus Gateway
- **Function:** Modbus RTU (RS485) to Modbus TCP (Ethernet) converter
- **Power:** 5-36V DC (will be powered from controller's +15Vdc supply)
- **Network:** 10/100 Mbps Ethernet, RJ45
- **Amazon:** ~$39, Prime delivery

---

## Physical Installation

### What You Need
1. PUSR DR302 gateway (ordered)
2. Short run of 4-conductor cable (a few feet, from controller to gateway)
   - Shielded twisted pair preferred, 22 AWG
   - Can also use standard 4-conductor thermostat wire in a pinch for a short run
3. Ethernet cable from the shelter to the nearest network switch/router
4. Small screwdriver for terminal blocks

### Wiring: Controller to Gateway

All connections are on **Terminal M2** on the back of the Logik 26-S controller.
The terminal block has 4 poles in a row with screw terminals.

```
Logik 26-S Terminal M2          PUSR DR302 Green Terminal Block
────────────────────            ─────────────────────────────────
Pole 1  (0 / GND)  ──────────  GND
Pole 2  (D-)       ──────────  A (also labeled D- or T/R-)
Pole 3  (D+)       ──────────  B (also labeled D+ or T/R+)
Pole 4  (+15Vdc)   ──────────  V+ (power input, 5-36V DC)
```

**IMPORTANT wiring notes from the manual:**
- Do NOT reverse D+ and D- — wrong wiring can damage both the controller and the gateway.
- Keep RS485 cable separated from power cables (separate cable tray/conduit).
- Keep RS485 cable at least 2 meters from motors, inverters, and distribution cabinets.
- Connect cable shield to ground at ONE end only (gateway end).
- For this short run (a few feet inside the cabinet), a 120-ohm termination resistor
  between D+ and D- is optional but recommended. The DR302 may have a built-in
  termination jumper — check the manual that comes with it.

### Wiring: Gateway to Network

- Plug a standard Ethernet cable (Cat5e or Cat6) into the DR302's RJ45 "LAN" port.
- Run the cable from the shelter to the nearest network switch, router, or Ethernet wall jack.
- The DR302 supports DHCP by default, so it will get an IP automatically from your router.
  You should later assign it a static IP (see Gateway Configuration below).

### Physical Mounting

- The DR302 is DIN-rail mountable. If the compressor's electrical panel has a DIN rail,
  snap the gateway onto it.
- If no DIN rail is available, use double-sided tape, zip ties, or a small DIN rail section
  screwed to the inside of the cabinet.
- Keep the gateway away from heat sources and contactors if possible.

### Safety

- **TURN OFF THE COMPRESSOR AND DISCONNECT POWER** before working inside the
  electrical cabinet. This is a 208/230V 3-phase system — lethal voltage.
- The M2 terminal carries only low voltage (15VDC and RS485 signal levels), but other
  terminals and wiring inside the cabinet are at line voltage.
- After wiring, close the cabinet door before powering up — the controller has an alarm
  (IN7, code 07) for cabinet door open if that input is wired.

---

## Gateway Configuration (DR302)

After the DR302 is powered and connected to the network:

### Step 1: Find It on the Network

- Default IP is typically 192.168.0.7 (check the DR302 manual/label).
- If using DHCP, check your router's DHCP client list for the new device.
- PUSR also provides a free "USR-VCOM" Windows utility that scans the network for their devices.
  Download from: https://www.pusr.com/support/downloads

### Step 2: Access the Web Configuration

- Open a browser and go to the gateway's IP address (e.g., http://192.168.0.7).
- Default login is usually admin / admin (check manual).

### Step 3: Configure for Modbus Gateway Mode

Set the following in the web interface:

| Setting | Value |
|---------|-------|
| Work Mode | Modbus TCP <-> Modbus RTU Gateway |
| Serial Baud Rate | 9600 (most common for Logik controllers — may need to try 19200) |
| Data Bits | 8 |
| Stop Bits | 1 |
| Parity | None (may need to try Even — match the controller) |
| Modbus TCP Port | 502 (standard Modbus TCP port) |
| Local IP | Set a static IP on your LAN, e.g., 192.168.1.100 |

**Confirmed serial parameters (from official MODBUS PROCEDURE document):**
Baud rate 9600, Data bits 8, Stop bits 1, Parity None. These are **fixed** and cannot
be changed on the Logik 26-S. The DR302 factory default is 115200 — it must be changed
to 9600 in the DR302 web interface.

### Step 4: Set the Controller's MODBUS Address

On the Logik 26-S front panel:
1. Enter the menu (press Enter for 3 seconds to get to password entry).
2. Select Password Level 2 or 3.
3. Enter password (factory defaults: Level 2 = 4444, Level 3 = 666666).
4. Go to Menu 04 — Compressor Setup.
5. Find parameter **C08 (Compressor Nr)** — this is the MODBUS slave address.
6. Default is 1, which is correct for a single compressor. Confirm it is set to 1.

---

## MODBUS Register Map — OBTAINED

~~The manuals describe what parameters exist but do NOT publish the actual MODBUS register addresses.~~

**RESOLVED 2026-04-06:** Official **LOGIK26S MODBUS PROCEDURE** document (13 pages) received.
File: `LOGIK26S MODBUS PROCEDURE.pdf` in project folder.
Complete decoded register map: `REGISTER_MAP.md` in project folder.

The document covers 10 register groups (0x0000-0x0900), including:
- System ID, passwords, alarms, controller state, live sensors
- Fieldbus command register (start/stop/alarm reset/maintenance counter reset)
- All parameters (pressure, temperature, timers, drive, PID)
- Counters (total hours, load hours, maintenance elapsed, load %, starts/hr)
- Clock timers, system time, maintenance records

Both Option A (contacted manufacturer) and Option B (empirical probing on 2026-04-03) were
executed. The official document confirmed most empirical findings and corrected several
register assignments (WT1/WT2 off by 1, load hours location, live data block).

---

## Software Architecture

### Stack
- **Language:** Python 3.14 (already installed on the Traxis PC)
- **MODBUS library:** pymodbus (pip install pymodbus)
- **GUI:** Web-based dashboard using Flask or FastAPI + HTML/JS
- **Database:** SQLite for logging (same pattern as FocasMonitor)
- **Service management:** Managed by the existing Traxis Overseer

### Architecture Diagram

```
[Logik 26-S Controller]
        |
    RS485 (4 wires, short run)
        |
[PUSR DR302 Gateway]  ---- in the compressor shelter
        |
    Ethernet (Cat5/6)
        |
[LAN / Network Switch]
        |
[Traxis PC]
    |
    +-- compressor_monitor.py (background service)
    |       - Polls compressor via Modbus TCP every few seconds
    |       - Logs data to SQLite database
    |       - Detects alarms and can send notifications
    |
    +-- compressor_web.py (web dashboard)
    |       - Serves web GUI on e.g. http://localhost:8085
    |       - Shows live pressure, temperature, status
    |       - Shows alarm history and maintenance counters
    |       - Provides start/stop buttons (with confirmation)
    |
    +-- compressor.db (SQLite database)
            - Time-series data: pressure, temperature, status
            - Alarm log
            - Maintenance counter snapshots
```

### What the Dashboard Will Show

**Live Status Panel:**
- Current working pressure (PSI) with gauge visualization
- Air end temperature (F) with gauge visualization
- Compressor state: OFF / LOADING / UNLOADING / STANDBY / ALARM
- Motor status (running/stopped)
- Fan status (on/off)
- Load solenoid valve status (open/closed)

**Pressure Settings:**
- WP1: Top range transducer
- WP2: High pressure alarm threshold
- WP3: Stop pressure
- WP4: Start pressure

**Maintenance Panel:**
- Air filter hours remaining (CAF counter)
- Oil filter hours remaining (COF counter)
- Separator filter hours remaining (CSF counter)
- Oil change hours remaining (C-- counter)
- Compressor check hours remaining (C--h counter)
- Bearings lubrication hours remaining (C-BL counter)

**Alarm Panel:**
- Active alarms with code, description, and timestamp
- Alarm history (last 20, mirroring the controller's alarm list)
- Color-coded: red = shut-off alarm, yellow = warning, blue = maintenance

**Working Hours:**
- Total working hours
- Load hours
- Load % (updated every 5 hours by controller)
- Starts per hour

**Controls (with confirmation dialogs):**
- Start compressor (remote start via MODBUS)
- Stop compressor (remote stop via MODBUS)
- Alarm reset

**Historical Charts:**
- Pressure over time (24hr, 7day, 30day views)
- Temperature over time
- Load % trend
- Run hours per day

---

## Alarm Reference (from Logik 26-S Manual)

### Immediate Shut-Off Alarms
| Code | Description | Cause |
|------|-------------|-------|
| 01 | EMERGENCY STOP | Emergency stop button open (IN1) |
| 02 | MOTOR OVERLOAD | Thermal motor open (IN2) |
| 03 | THERMAL FAN | Thermal fan open (IN3) |
| 04 | NO PHASE | Phase lost >300ms |
| 05 | WRONG PHASE | Phases inverted |
| 07 | DOOR OPEN | IN7 open (cabinet door) |
| 09 | DRIVE FAULT | VFD fault relay (if enabled) |
| 11 | HIGH PRESSURE | Pressure > WP2 |
| 12 | T. PROBE FAILURE | Temperature probe failure |
| 13 | HIGH TEMP | Temperature > WT1 |
| 14 | LOW TEMP | Temperature < WT5 |
| 18 | POWER OFF | Power off + manual restart mode |
| 20 | PTC MOTOR | PTC input open |
| 21 | INPUT POWER FAULT | All digital inputs lost power |
| 22 | INPUT IN7 | Generic alarm (if C12=3) |
| 25 | SEPARATOR FILTER | Separator differential switch open (IN6) |

### Delayed Shut-Off Alarms (30 sec unload first)
| Code | Description | Cause |
|------|-------------|-------|
| 26 | PRESS. TRANSD. FAILURE | Pressure transducer failure |
| 27 | AUX. TRANSD. FAILURE | Aux pressure transducer failure |
| 28 | LOW VOLTAGE | Controller supply < 9.5Vac |
| 29 | SAFETY | Timer CAF elapsed (if Safety=YES) |
| 30 | HIGH TEMP WARNING | Temperature > WT2 |
| 32 | CHECK COMPRESSOR | Timer C--h elapsed |
| 33 | RS485 FAILURE | MODBUS watchdog timeout |
| 60 | INVERTER FAILURE | VFD shut-off via RS485 |
| 62 | COMM. INVERTER | No RS485 communication to VFD |

### Warnings (Visual Only)
| Code | Description | Cause |
|------|-------------|-------|
| 35 | DATA LOST | Default data loaded |
| 36 | AIR FILTER | Air filter pressure switch closed (IN5) |
| 37 | MULTIUNIT FAILURE | No communication to master |
| 39 | LOW VOLTAGE | Controller supply < 11.6Vac |
| 40 | HIGH VOLTAGE | Controller supply > 14.5Vac |
| 41 | CLOCK FAILURE | RTC failure |
| 42 | RS485 FAILURE | Master/slave communication lost |
| 47 | STARTS/HOUR | Max starts/hour exceeded |

### Maintenance Messages
| Code | Description | Counter |
|------|-------------|---------|
| 50 | CHANGE AIR FILTER | CAF timer elapsed |
| 51 | CHANGE OIL FILTER | COF timer elapsed |
| 52 | CHANGE SEP. FILTER | CSF timer elapsed |
| 53 | CHANGE OIL | C-- timer elapsed |
| 54 | CHECK COMPRESSOR | C--h timer elapsed |
| 55 | CHECK BEARINGS | C-BL timer elapsed |

---

## Maintenance Parts Reference

| Part | SKU |
|------|-----|
| Air Filter | FILTER007 |
| Oil Filter | FILTER070 |
| Separator | FILTER009 |
| Oil | OIL003 (1.6 gal, do NOT overfill) |
| Service Kit | SKIT003 |
| Belts | BELT016 (qty 3) |

---

## Controller Passwords (Factory Defaults)

| Level | Code | Access |
|-------|------|--------|
| Level 1 (Service 1) | 22 | Basic settings, timers, weekly schedule |
| Level 2 (Service 2) | 4444 | Pressures, temperatures, maintenance counters |
| Level 3 (Factory) | 666666 | Full access: relay config, VFD, analog output, PID, reset |

**Password reset procedure:** Power off controller, restore power, hold both arrow
buttons for >5 seconds until "Reset Password" appears, release when it says "Password reset."

---

## Project Steps / Checklist

### Phase 1: Hardware (You) — COMPLETE
- [x] Order PUSR DR302 gateway
- [x] Plan Ethernet cable route from shelter to nearest network point
- [x] Run Ethernet cable to shelter
- [x] Power down compressor and disconnect electrical power
- [x] Open electrical cabinet, locate Terminal M2 on Logik 26-S controller
- [x] Wire 4 conductors from M2 (poles 1-4) to DR302 terminal block
- [x] Mount DR302 inside cabinet (DIN rail or secured with zip ties)
- [x] Plug Ethernet cable into DR302
- [x] Close cabinet, restore power
- [x] Verify DR302 powers up (PWR LED on) and gets network link (LAN LED on)

### Phase 2: Gateway Configuration (Together) — COMPLETE
- [x] Find DR302 on the network (DHCP lease or default IP)
- [x] Access DR302 web interface and configure Modbus gateway mode
- [x] Assign static IP to DR302 → **10.1.1.180**, port 502
- [x] Verify basic Modbus TCP connectivity from this PC (pymodbus)
- [x] Confirm baud rate and parity settings → **9600, 8N1** (serial params are fixed on Logik 26-S)

### Phase 3: Get Register Map — COMPLETE
- [x] Contact Logika Control and/or EMAX for MODBUS register map
- [x] ~~If no response, probe registers using QModMaster~~ Probed empirically first (2026-04-03)
- [x] **Received official LOGIK26S MODBUS PROCEDURE document** (13 pages, 2026-04-06)
- [x] Document all registers → `REGISTER_MAP.md` (official + empirical, comprehensive)

### Phase 4: Software (Claude) — MOSTLY COMPLETE
- [x] Install pymodbus: `pip install pymodbus` (v3.12.1)
- [ ] Build compressor monitoring service (polling, logging to SQLite) — *polling done, SQLite logging pending*
- [x] Build web dashboard (Flask, live status, alarms, maintenance)
- [ ] Add alarm notifications (email, desktop notification, or integration with Overseer)
- [ ] Add historical data charts
- [x] Add remote start/stop controls with safety confirmations — **Fieldbus commands via HR 1036**
- [ ] Register with Overseer for auto-start and health monitoring
- [x] Test end-to-end — **Verified all official registers reading correctly 2026-04-06**

### Current Status Summary (2026-04-06)
**Web GUI v2 running at http://10.1.1.71:8085** with:
- Live pressure/temperature from official registers (exact scaling, no approximation)
- Official controller state display (14 state codes)
- Active alarm monitoring with alarm reset button
- Real-time maintenance counters from PLC (6 items, all reading correctly)
- Remote START/STOP via fieldbus command register (instant, no more timer hacking)
- Maintenance counter reset from web GUI
- Total hours, load hours, load %, starts/hour
- Status flag indicators (motor, fan, drain, alarm, timer states)
- Weekly schedule editor (unchanged, working)
- Cabinet filter manual tracking (unchanged)

---

## Contact Info

**Logika Control s.r.l.** (controller manufacturer)
- Via Garibaldi, 83/a, 20054 Nova Milanese (MI), Italy
- Phone: +39 0362 37001
- Fax: +39 0362 370030
- Web: www.logikacontrol.it

**EMAX Compressors** (compressor manufacturer)
- Sales/Parts/Tech Support: (866) 294-4153
- VSD Support: (877) 283-7614
- Web: www.emaxcompressor.com
- Manual/warranty: www.emaxcompressor.com

---

*Document created: 2026-03-23*
*Source manuals: L25-S_0.3a_eng, L26-S Rev 1, EMAX Rotary Screw Manual, Maintenance Details*
