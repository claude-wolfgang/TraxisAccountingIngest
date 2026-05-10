# Logik 26-S Modbus Register Map
## EMAX Rotary Screw Compressor — Official + Empirical

**Connection:** Modbus TCP via DR302 gateway at 10.1.1.180:502, Slave ID 1
**Serial:** 9600 baud, 8N1
**Date:** 2026-04-06
**Source:** Official LOGIK26S MODBUS PROCEDURE document + empirical verification

---

## Register Overview

| Group | Hex Range | Decimal Range | Contents | Access |
|-------|-----------|---------------|----------|--------|
| 0 | 0x0000-0x000C | HR 0-12 | System identification | R/RW |
| 1 | 0x0100-0x0108 | HR 256-264 | Passwords | RW |
| 2 | 0x0200-0x0207 | HR 512-519 | Active & unacknowledged alarms | R |
| 3 | 0x0300-0x0334 | HR 768-820 | Alarm records (20 entries) | R/RW |
| 4 | 0x0400-0x040D | HR 1024-1037 | **Controller state, sensors, commands** | R/W |
| 5 | 0x0500-0x0554 | HR 1280-1364 | Parameters & configuration | RW |
| 6 | 0x0600-0x0611 | HR 1536-1553 | **Counters & maintenance** | R/RW |
| 7 | 0x0700 | HR 1792 | Weekly clock timers | RW |
| 8 | 0x0800-0x0805 | HR 2048-2053 | System time | R/RW |
| 9 | 0x0900-0x093D | HR 2304-2365 | Maintenance records | R/RW |
| — | — | HR 1800/1920 | Timer aliases (empirically verified) | RW |
| — | — | HR 4096-4260 | Legacy live data block (hi-byte encoded) | R |

---

## Group 0: System Identification (0x0000)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0000 | HR 0-9 | char[20] | RW | Serial number, ASCII null-terminated |
| 0x000A | HR 10 | word | R | Controller model (0x02A1 = Dalgakiran) |
| 0x000B | HR 11 | char[2] | R | Firmware release (lo=minor, hi=major) |
| 0x000C | HR 12 | word | R | Modbus interface release |

---

## Group 1: Passwords (0x0100)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0100 | HR 256-258 | char[6] | RW | Level 1 password (first 2 chars, ASCII '0'-'9') |
| 0x0103 | HR 259-261 | char[6] | RW | Level 2 password (first 4 chars) |
| 0x0106 | HR 262-264 | char[6] | RW | Level 3 password (all 6 chars) |

---

## Group 2: Alarms (0x0200)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0200 | HR 512-515 | byte[8] | R | Active alarms (bitmapped, bit N = alarm N, bit 0 unused) |
| 0x0204 | HR 516-519 | byte[8] | R | Unacknowledged alarms (same bitmap layout) |

---

## Group 3: Alarm Records (0x0300)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0300 | HR 768 | byte[2] | RW | Indexes: lo=position (0-19), hi=count (0-20) |
| 0x0301 | HR 769-818 | byte[100] | R | 20 alarm records (5 bytes each: 4B time + 1B alarm code) |

---

## Group 4: Controller State & Measures (0x0400) — PRIMARY LIVE DATA

| Hex | Decimal | Type | Access | Description | Units/Notes |
|-----|---------|------|--------|-------------|-------------|
| 0x0400 | HR 1024 | word | R | Internal controller state | Enum 0-11 |
| 0x0401 | HR 1025 | word | R | **Displayed state** | Enum 0-14 (see table below) |
| 0x0402 | HR 1026 | word | R | Blocking alarm code | 0 = no alarm |
| 0x0403 | HR 1027 | word | R | Relay output | Bitmapped (RL1-RL7) |
| 0x0404 | HR 1028 | word | R | Digital input | Bitmapped (IN1-IN7, phases, PTC) |
| **0x0405** | **HR 1029** | **int** | **R** | **Screw temperature** | **Celsius * 10** |
| **0x0406** | **HR 1030** | **word** | **R** | **Working pressure** | **bar * 10** |
| **0x0407** | **HR 1031** | **word** | **R** | **Auxiliary pressure** | **bar * 10** |
| 0x0408 | HR 1032 | word | R | PTC input | Volt * 1000 |
| 0x0409 | HR 1033 | word | R | Controller supply voltage | Volt * 10 (nominal 15V) |
| **0x040A** | **HR 1034** | **word** | **R** | **Status indicators** | **Bitmapped (see table below)** |
| 0x040B | HR 1035 | word | R | Analog out frequency set | Hz |
| **0x040C** | **HR 1036** | **word** | **W** | **Fieldbus commands** | **Bitmapped (see table below)** |
| 0x040D | HR 1037 | word | W | Relative speed (VSD) | 0-1000 |

### Displayed State Codes (HR 1025)

| Code | State |
|------|-------|
| 0 | OFF |
| 1 | Internal pressure too high — waiting |
| 2 | Remote stop active |
| 3 | Stop by timer |
| 4 | Idle stopping |
| 5 | Idle stopping by remote stop |
| 6 | Idle stopping by timer |
| 7 | Pressure in set — motor off |
| 8 | Waiting to start (security timer Wt5) |
| 9 | Motor starting |
| 10 | Idle running |
| 11 | Load running |
| 12 | Soft block delay (30 seconds) |
| 13 | Blocked |
| 14 | Factory test |

### Internal State Codes (HR 1024)

| Code | State |
|------|-------|
| 0 | RESET |
| 1 | OFF |
| 2 | Starting motor in star connection |
| 3 | Starting pause star to delta |
| 4 | Starting accelerating in delta |
| 5 | Load running |
| 6 | Idle running — pressure in range |
| 7 | Idle running — stopping |
| 8 | Inverter on |
| 9 | Inverter setup |
| 10 | Blocked by fault |
| 11 | Factory test |

### Status Indicator Bits (HR 1034)

| Bit | Hex | Description |
|-----|-----|-------------|
| 0 | 0x0001 | Compressor active (ON) |
| 1 | 0x0002 | Compressor master (master/slave) |
| 2 | 0x0004 | Compressor ON by weekly timer |
| 3 | 0x0008 | Weekly timer bypassed by user |
| 5 | 0x0020 | Fan logical out |
| 6 | 0x0040 | Drain logical out |
| 7 | 0x0080 | Alarm logical out |
| 8 | 0x0100 | Remote start/stop (0=STOP) |
| 9 | 0x0200 | Motor is starting |
| 10 | 0x0400 | Compressor is active |
| 11 | 0x0800 | Motor running |
| 12 | 0x1000 | Acting as multiunit slave |
| 13 | 0x2000 | Controlled by multiunit master |
| 14 | 0x4000 | Multiunit ON/OFF by weekly timer |
| 15 | 0x8000 | Multiunit master fault |

### Fieldbus Command Bits (HR 1036, WRITE-ONLY)

| Bit | Hex | Command |
|-----|-----|---------|
| 0 | 0x0001 | **START COMPRESSOR** |
| 1 | 0x0002 | **STOP COMPRESSOR** |
| 2 | 0x0004 | ALARM RESET |
| 3 | 0x0008 | START BYPASSING WEEKLY TIMER |
| 4 | 0x0010 | STOP BYPASSING WEEKLY TIMER |
| 5 | 0x0020 | ACK & RESET ALL ALARMS |
| 6 | 0x0040 | LOAD COMPRESSOR (requires bit 15) |
| 7 | 0x0080 | **WATCHDOG** (must re-send every 5 sec or fieldbus fault!) |
| 8 | 0x0100 | Reset air filter (CAF) counter |
| 9 | 0x0200 | Reset oil filter (COF) counter |
| 10 | 0x0400 | Reset separator filter (CSF) counter |
| 11 | 0x0800 | Reset oil (C--) counter |
| 12 | 0x1000 | Reset compressor (C-h) counter |
| 13 | 0x2000 | Reset bearing (C-BL) counter |
| 15 | 0x8000 | Enable bits 6 & 14 (valid 10 seconds) |

---

## Group 5: Parameters (0x0500) — Configuration

| Hex | Decimal | Parameter | Description | Units |
|-----|---------|-----------|-------------|-------|
| 0x0500 | HR 1280 | Config switches | Bitmapped (C01, C03-C06, C11, units, DST, T01, C17, C07.3-4) | — |
| 0x0501 | HR 1281 | Config sel 1/2 | C13 RL2 mode, C14 RL5 mode, C15 RL6 mode, C16 RL7 mode | — |
| 0x0502 | HR 1282 | Config sel 2/2 | C19, C07 multiunit, C18 analog out, C12 IN7, C21 inverter | — |
| 0x0503 | HR 1283 | Language | 0=Italian, 1=English | — |
| 0x0504 | HR 1284 | PW1 | Level 1 password (BCD) | — |
| 0x0505 | HR 1285 | PW2 | Level 2 password (BCD) | — |
| 0x0506 | HR 1286 | PW3 hi | Level 3 password (BCD, first 4 digits) | — |
| 0x0507 | HR 1287 | PW3 lo | Level 3 password (BCD, last 2 digits) | — |
| 0x0508 | HR 1288 | LCD contrast | 200-380 (default 250) | — |
| 0x0509 | HR 1289 | WP1 | Pressure range top | bar |
| **0x050A** | **HR 1290** | **WP2** | **High pressure alarm** | **bar*10** |
| **0x050B** | **HR 1291** | **WP3** | **Stop pressure** | **bar*10** |
| **0x050C** | **HR 1292** | **WP4** | **Start pressure** | **bar*10** |
| 0x050D | HR 1293 | WP5 | Slave start | bar*10 |
| 0x050E | HR 1294 | WP6 | Offset | bar*10 |
| 0x050F | HR 1295 | WT0 | Temp sensor type (0=off, 1=KTY, 2=NTC) | — |
| **0x0510** | **HR 1296** | **WT1** | **High temp alarm** | **C** |
| **0x0511** | **HR 1297** | **WT2** | **High temp warning** | **C** |
| 0x0512 | HR 1298 | WT3 | — | C |
| 0x0513 | HR 1299 | WT4 | — | C |
| 0x0514 | HR 1300 | WT5 | — | C |
| 0x0515 | HR 1301 | WT6 | — | C |
| 0x0516 | HR 1302 | WT7 | — | C |
| 0x0517 | HR 1303 | Wt1 | Star timer | sec |
| 0x0518 | HR 1304 | Wt2 | Star/Delta changeover | msec |
| 0x0519 | HR 1305 | Wt3 | Delta timer | sec |
| 0x051A | HR 1306 | Wt4 | Unload timer | min |
| 0x051B | HR 1307 | Wt5 | Safety timer | sec |
| 0x051C | HR 1308 | Wt6 | RL6 On timer | sec |
| 0x051D | HR 1309 | Wt7 | RL6 Off timer | min |
| 0x051E | HR 1310 | C07.1 | Master/Slave timer | hour |
| 0x051F | HR 1311 | C07.2 | Slave timer | min |
| **0x0520** | **HR 1312** | **CAF SET** | **Air filter service interval** | **hour** |
| **0x0521** | **HR 1313** | **COF SET** | **Oil filter service interval** | **hour** |
| **0x0522** | **HR 1314** | **CSF SET** | **Separator filter service interval** | **hour** |
| **0x0523** | **HR 1315** | **C-- SET** | **Oil change service interval** | **hour** |
| **0x0524** | **HR 1316** | **C-h SET** | **Compressor check interval** | **hour** |
| **0x0525** | **HR 1317** | **C-BL SET** | **Bearing lubricate interval** | **hour** |
| 0x0526 | HR 1318 | C08 | Modbus address / compressor number | — |
| 0x0527 | HR 1319 | C02 | Max starts per hour | — |
| 0x0528 | HR 1320 | C10 | Air delivery | L/min*0.1 |
| 0x0529 | HR 1321 | AP1 | Sep filter alarm | bar*10 |
| 0x052A | HR 1322 | AP2 | Sep filter warning | bar*10 |
| 0x052B | HR 1323 | AP3 | — | bar*10 |
| 0x052C | HR 1324 | C19.1 | Alarm delay | sec |
| 0x052D | HR 1325 | AP4 | Max aux pressure | bar*10 |
| 0x0544 | HR 1348 | DR0 | Drive model (0=disabled, 1=Danfoss FC) | — |
| 0x0545-0x0554 | HR 1349-1364 | DR1-DA9 | Drive parameters | various |

---

## Group 6: Counters (0x0600)

| Hex | Decimal | Type | Access | Description | Units |
|-----|---------|------|--------|-------------|-------|
| **0x0600** | **HR 1536-1537** | **long** | **RW** | **Total compressor hours** | **minutes** |
| **0x0602** | **HR 1538-1539** | **long** | **RW** | **Load hours** | **minutes** |
| **0x0604** | **HR 1540-1551** | **long[6]** | **RW** | **Maintenance counters (elapsed since service)** | **minutes** |
| | HR 1540-1541 | long | | — Index 0: Air Filter (CAF) | minutes |
| | HR 1542-1543 | long | | — Index 1: Oil Filter (COF) | minutes |
| | HR 1544-1545 | long | | — Index 2: Separator Filter (CSF) | minutes |
| | HR 1546-1547 | long | | — Index 3: Oil (C--) | minutes |
| | HR 1548-1549 | long | | — Index 4: Compressor Check (C-h) | minutes |
| | HR 1550-1551 | long | | — Index 5: Bearing Lubricate (C-BL) | minutes |
| 0x0610 | HR 1552 | word | R | Load % in last 100 hours (6000=100%) | — |
| 0x0611 | HR 1553 | word | R | Motor starts in last hour | — |

---

## Group 7: Clock Timers (0x0700)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0700 | HR 1792 | byte[84] | RW | 7 days x 3 timers x 4 bytes |

Timer encoding per slot (2 registers):
- Register N: `(start_minute << 8) | start_hour`
- Register N+1: `(stop_minute << 8) | stop_hour`

Example: 05:30 = `(30 << 8) | 5` = 7685 = 0x1E05

**Note:** Empirically verified timer writes work at HR 1800 (Timer1, Mon-Fri) and HR 1920 (Timer2, all 7 days). The official base 0x0700=HR 1792 may be a header or different layout.

---

## Group 8: System Time (0x0800)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0800 | HR 2048-2051 | byte[8] | RW | System time: sec, min, hr, DOW(1=Mon), day, month, year(0=2000) |
| 0x0804 | HR 2052 | word | R | Timekeeper error flags |
| 0x0805 | HR 2053 | word | R | DST adjustment (-1=legal, 0=solar) |

---

## Group 9: Maintenance Records (0x0900)

| Hex | Decimal | Type | Access | Description |
|-----|---------|------|--------|-------------|
| 0x0900 | HR 2304 | byte[2] | RW | Indexes (circular, lo=position, hi=count) |
| 0x0901 | HR 2305-2364 | byte[120] | RW | 20 records (6 bytes: 4B time + 1B counter index + 2B countdown value) |

---

## Alarm Code Table

| Code | Alarm | Code | Alarm |
|------|-------|------|-------|
| 1 | A01-EMERGENCY | 32 | A32-MAINT C-H BLK |
| 2 | A02-MOTOR OVERHEAT | 33 | A33-FIELDBUS ERR |
| 3 | A03-FAN OVERHEAT | 35 | A35-EEPROM FAULT |
| 4 | A04-AC PHASE MISSING | 36 | A36-AIR FILTER |
| 5 | A05-AC PHASE SEQ WRONG | 37 | A37-MU FAULT |
| 7 | A07-DOOR OPEN | 38 | A38-SEP FILTER WARN |
| 9 | A09-DRIVE FAULT | 39 | A39-LOW VOLTAGE WARN |
| 11 | A11-HIGH WORK PRESS | 40 | A40-HIGH VOLTAGE |
| 12 | A12-SCREW TEMP FAULT | 41 | A41-TIMEKEEPER FAULT |
| 13 | A13-HIGH SCREW TEMP | 42 | A42-RS232 FAULT |
| 14 | A14-LOW SCREW TEMP | 43 | A43-DST ADJUSTED |
| 15 | A15-SEP FILTER TRANSD | 44 | A44-BEARING HIGH TEMP |
| 18 | A18-BLACK OUT | 47 | A47-TOO MANY STARTS |
| 20 | A20-PTC MOTOR | 48 | A48-RESTART MANUAL |
| 21 | A21-INPUT COMMON MISSING | 49 | A49-RESTART AUTO |
| 22 | A22-INPUT7 | 50 | A50-MAINT CAF |
| 25 | A25-SEPARATOR FILTER | 51 | A51-MAINT COF |
| 26 | A26-WORK PRESS FAULT | 52 | A52-MAINT CSF |
| 27 | A27-AUX PRESS FAULT | 53 | A53-MAINT C-- |
| 28 | A28-LOW VOLTAGE | 54 | A54-MAINT C-H |
| 29 | A29-SECURITY | 55 | A55-MAINT BL |
| 30 | A30-SCREW TEMP WARN | 60 | A60-DRIVE FAULT |
| | | 61 | A61-DRIVE WARNING |
| | | 62 | A62-DRIVE NO COMM |

---

## Notes

1. **All hex addresses from the official document.** Decimal addresses = hex converted.
2. **Pressure:** Controller stores as bar*10 internally. Convert: PSI = value * 1.4504
3. **Temperature:** HR 1029 = Celsius * 10 (signed). Divide by 10 for actual temp.
4. **Long values:** 32-bit big-endian (high word at lower address). Value in minutes.
5. **Maintenance remaining:** `remaining_hrs = SET_hrs - (elapsed_minutes / 60)`
6. **Watchdog (HR 1036 bit 7):** Do NOT set unless implementing a 5-second keepalive thread. Failure to re-send causes fieldbus fault alarm (A33) requiring manual reset.
7. **Timer base discrepancy:** Official doc says 0x0700=HR 1792 but empirically verified writes work at HR 1800/1920. Keeping empirical addresses for timer operations.
8. **FC01/FC02 (coils/discrete inputs):** NOT SUPPORTED — returns Illegal Function.
9. **pymodbus 3.12.1:** Use `device_id=` parameter (NOT `slave=` or `unit=`).
