# P31: BLE Proximity Worker Tracking

Passive BLE-based system to track which worker is at which CNC machine.
Uses Feasycom iBeacon tags (worn by workers) and ESP32 gateways running ESPresense (at machines) to detect proximity via RSSI.

## Hardware
- 2x Feasycom iBeacon tags (major 60285, 40604) — on hand
- Asus USB Bluetooth dongle — on hand, but inadequate (~4 dB RSSI spread)
- 3x ESP32-WROOM-32 dev boards — ordered 2026-04-26, pending arrival

## Key Technical Notes
- Beacon MACs rotate randomly — must identify by iBeacon major/minor, not MAC
- ESPresense firmware (https://espresense.com/) provides Kalman-filtered RSSI + MQTT output
- Zone thresholds from ble_rssi_monitor.py: AT MACHINE >-82, NEARBY >-88, IN AREA >-94
- Feasycom tags configurable via phone app (TX power, advertising interval)
- Label physical tags with their major numbers for identification

## Status
Phase 1 test kit ordered. Next: flash ESPresense onto ESP32 boards, test RSSI dynamic range vs. Asus dongle.

## Interfaces
Produces: worker-machine proximity events (RSSI readings, presence/absence via MQTT)
Consumes: ProShop employee list, machine inventory
Contracts: none yet — project is in initial testing phase
