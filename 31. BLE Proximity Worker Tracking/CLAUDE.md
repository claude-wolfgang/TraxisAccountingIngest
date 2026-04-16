# P31: BLE Proximity Worker Tracking

Passive BLE-based system to track which worker is at which CNC machine.
Uses Feasycom long-range beacon tags (worn by workers) and Asus USB BT dongles (at machines) to detect proximity via RSSI.

## Hardware (on hand)
- Asus USB Bluetooth dongle (receiver/gateway)
- Feasycom long-range BLE beacon tag (worker wearable)

## Interfaces
Produces: worker-machine proximity events (RSSI readings, presence/absence)
Consumes: ProShop employee list, machine inventory
Contracts: none yet — project is in initial testing phase
