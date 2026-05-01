# P31: BLE Proximity Worker Tracking

Passive BLE-based system to track which worker is at which CNC machine.
Uses Feasycom iBeacon tags (worn by workers) and ESP32 gateways running ESPresense (at machines) to detect proximity via RSSI.

## Hardware
- 2x Feasycom iBeacon tags — on hand, TX power 2.5dB, interval 1000ms
  Each tag broadcasts multiple iBeacon slots simultaneously with different major numbers:
  - Tag-A: MAC DC:0D:30:1F:90:A3, majors 39475, 40604, 10065 (shared)
  - Tag-B: MAC DC:0D:30:48:30:3A, majors 35540, 60285, 10065 (shared)
  - Major 10065 is broadcast by BOTH tags — disambiguate via MAC address
- Asus USB Bluetooth dongle — retired, inadequate (~4 dB RSSI spread)
- 3x ESP32-WROOM-32 dev boards — ESPresense v4.0.6, CP2102 USB-serial
  - M8: IP 10.1.1.38, MAC 70:4B:CA:6D:B7:48, room=m8 — online
  - M1: IP 10.1.1.225, MAC 30:76:F5:E8:D1:FC, room=m1 — online
  - M2: IP 10.1.1.23, MAC 30:76:F5:E8:BE:74, room=m2 — online
- 10x MOKOSmart B2 Smart Badges — ordered 2026-04-29 (Order #3765, $171.48 shipped), BLE iBeacon + NFC for door entry

## Key Technical Notes
- Beacon MACs rotate randomly — must identify by iBeacon major/minor, not MAC. Exception: major 10065 requires MAC disambiguation since both tags share it
- ESP32 gateways self-detect each other as iBeacon majors 72, 116, 252 — filter these out
- ESPresense firmware (https://espresense.com/) provides Kalman-filtered RSSI + MQTT output
- Zone thresholds (walk test 2026-04-29, open air):
  - AT MACHINE >-45 dBm (~0-2ft, operator at controls)
  - NEARBY >-58 dBm (~3ft, stepping back)
  - IN AREA >-66 dBm (~6-10ft, adjacent machine)
  - FAR/GONE <-66 dBm (>10ft)
- USB dongle was useless (~4dB spread); ESP32 gateway gives ~50dB dynamic range (0-15ft)
- Feasycom tags configurable via phone app (TX power, advertising interval)
- Label physical tags with their major numbers for identification

## Gateway Configuration
ESPresense settings are stored in SPIFFS. Configuration via HTTP `/wifi` endpoint (GET to
read, POST to write). POST must include ALL parameters or omitted ones get cleared (including
WiFi credentials). The `/wifi` GET response masks the password as `***###***`.

MQTT broker: 10.1.1.108:1883 (Mosquitto on this PC, config `mosquitto_clean.conf`)

## Status
All three ESP32 gateways online and reporting via MQTT (2026-04-30). Band steering was not
an issue — ESP32s connect to Traxis-MFG on 2.4GHz channel 6 without needing a separate SSID.
Default MQTT server in ESPresense firmware is `mqtt.z13.org` — must be changed to `10.1.1.108`
on each board via the `/wifi` POST endpoint or captive portal.

Walk test (2026-04-30): M2→M1→M8 path, 30s at each machine. Feasycom tags at 2.5dB TX power
show only 3-5 dB RSSI contrast between adjacent gateways (~6ft apart) — everything reads FAR.
Expect MOKOSmart B2 badges to provide better signal for zone detection.

`proximity_logger.py` runs as background service via `start_logger.bat`, logging to `proximity.db`.

Remaining:
1. Re-test zone thresholds with steel machine backdrop (current thresholds are open-air)
2. MOKOSmart B2 badges ordered (10x, Order #3765) — configure as iBeacon when they arrive
3. Build assignment engine (strongest-gateway-wins per worker)
4. Re-run walk test with MOKOSmart badges for better RSSI contrast

## Interfaces
Produces: proximity.db (SQLite, readings table), worker-machine proximity events via MQTT
Consumes: ESPresense MQTT topics (espresense/devices/#), ProShop employee list, machine inventory
Contracts: none yet — project is in initial testing phase
