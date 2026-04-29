# P31: BLE Proximity Worker Tracking

Passive BLE-based system to track which worker is at which CNC machine.
Uses Feasycom iBeacon tags (worn by workers) and ESP32 gateways running ESPresense (at machines) to detect proximity via RSSI.

## Hardware
- 2x Feasycom iBeacon tags — on hand, TX power 2.5dB, interval 1000ms
  - Tag-A: MAC DC:0D:30:1F:90:A3, major 39475
  - Tag-B: MAC DC:0D:30:48:30:3A, major 10065
- Asus USB Bluetooth dongle — retired, inadequate (~4 dB RSSI spread)
- 3x ESP32-WROOM-32 dev boards — ESPresense v4.0.6, CP2102 USB-serial
  - M8: IP 10.1.1.38, MAC 70:4B:CA:6D:B7:48, room=test_bench — online
  - M1: flashed, deployed, pending Wi-Fi connection (Google Fiber band steering issue)
  - M2: flashed, deployed, pending Wi-Fi connection
- 10x MOKOSmart B2 Smart Badges — ordered 2026-04-29 (Order #3765, $171.48 shipped), BLE iBeacon + NFC for door entry

## Key Technical Notes
- Beacon MACs rotate randomly — must identify by iBeacon major/minor, not MAC
- ESPresense firmware (https://espresense.com/) provides Kalman-filtered RSSI + MQTT output
- Zone thresholds (walk test 2026-04-29, open air):
  - AT MACHINE >-45 dBm (~0-2ft, operator at controls)
  - NEARBY >-58 dBm (~3ft, stepping back)
  - IN AREA >-66 dBm (~6-10ft, adjacent machine)
  - FAR/GONE <-66 dBm (>10ft)
- USB dongle was useless (~4dB spread); ESP32 gateway gives ~50dB dynamic range (0-15ft)
- Feasycom tags configurable via phone app (TX power, advertising interval)
- Label physical tags with their major numbers for identification

## Status
Phase 1 complete: walk test validated ESP32 gateway RSSI dynamic range (~50dB over 0-15ft).
M8 gateway online and reporting via MQTT. M1 and M2 flashed and physically deployed but
not yet on Wi-Fi (Google Fiber band steering forces 5GHz; ESP32 needs 2.4GHz-only SSID).

Next steps:
1. Get M1/M2 on Wi-Fi — create 2.4GHz-only SSID on Google Fiber router, or use ESPresense AP mode to configure
2. Configure M1/M2 MQTT (server 10.1.1.108, port 1883, rooms m1/m2)
3. Run multi-gateway "strongest wins" test walking between M8, M1, M2
4. Re-test zone thresholds with steel machine backdrop (current thresholds are open-air)
5. MOKOSmart B2 badges ordered (10x, Order #3765) — configure as iBeacon when they arrive
6. Build assignment engine (strongest-gateway-wins per worker)

## Interfaces
Produces: worker-machine proximity events (RSSI readings, presence/absence via MQTT)
Consumes: ProShop employee list, machine inventory
Contracts: none yet — project is in initial testing phase
