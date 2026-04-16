# BLE Proximity Detection for CNC Machine Shop: Hardware & Software Research

**Use Case:** Automatically track which worker is at which machine via passive BLE proximity (no tapping/scanning). ~14 machines, ~10 workers, industrial CNC environment.

**Date:** March 31, 2026

---

## Table of Contents
1. [How RSSI-Based Proximity Works (and Challenges in a Metal Shop)](#1-rssi-based-proximity-in-a-metal-shop)
2. [Worker Wearable Tags (BLE Beacons)](#2-worker-wearable-tags-ble-beacons)
3. [Machine-Mounted Gateways/Receivers](#3-machine-mounted-gatewaysreceivers)
4. [DIY / Budget Gateway Option (ESP32)](#4-diy--budget-gateway-option-esp32)
5. [Central Software & Open-Source Stack](#5-central-software--open-source-stack)
6. [Turnkey Systems](#6-turnkey-systems)
7. [Budget Estimates](#7-budget-estimates)
8. [Recommended Architecture](#8-recommended-architecture)

---

## 1. RSSI-Based Proximity in a Metal Shop

### How It Works

Each worker carries a BLE beacon (tag) that continuously broadcasts a signal containing a unique identifier (UUID/Major/Minor for iBeacon, or Namespace/Instance for Eddystone). A gateway/receiver mounted at each machine continuously scans for these broadcasts. The receiver measures the **RSSI (Received Signal Strength Indicator)** of each detected beacon -- a stronger signal means the worker is closer.

**Core logic:** If `beacon X` is detected by `gateway at Machine 5` with an RSSI above a configured threshold (e.g., -65 dBm), then `Worker X is at Machine 5`. When RSSI drops below threshold for a configured timeout (e.g., 30-120 seconds), the worker is considered to have left.

### Challenges in a CNC Machine Shop

Metal-heavy environments are among the **hardest** for BLE/RF signals:

| Challenge | Impact | Mitigation |
|-----------|--------|------------|
| **Metal reflections (multipath)** | Large steel machine bodies bounce signals unpredictably, causing RSSI spikes and nulls | Mount gateways on the operator side of the machine (not behind metal); use RSSI averaging/filtering |
| **Signal absorption by coolant** | Water-based coolants absorb 2.4 GHz energy | Keep beacons/gateways away from coolant spray zones; mount gateways above splash level |
| **EMI from VFDs and spindles** | Variable frequency drives and servo motors emit broadband EMI | Use beacons/gateways with good RF filtering; keep antennas away from motor cables |
| **Metal chips/debris** | Conductive metal particles on devices can detune antennas | Use IP65/IP66 enclosures; mount gateways in protected locations |
| **Vibration** | Constant machine vibration can loosen connections and fatigue hardware | Use industrial-rated mounting; secure cable connections |
| **Worker body shadowing** | The human body attenuates 2.4 GHz by ~3-10 dB | Badge worn on chest facing the machine is ideal; pocket carry reduces reliability |

### Critical Design Principles for This Environment

1. **Use proximity (zone detection), NOT trilateration.** Trilateration (calculating exact X,Y position from multiple gateways) is unreliable in metal environments. Instead, use a simple model: one gateway per machine, detect "near" vs "far."

2. **RSSI threshold tuning is essential.** You will need to calibrate each machine's gateway individually because metal reflections vary by location. Plan for a 1-2 day calibration phase.

3. **Use aggressive RSSI filtering.** Raw RSSI is noisy (+-10 dBm variance). Apply a rolling average, median filter, or Kalman filter. A 5-10 sample rolling average over 5-10 seconds works well.

4. **Reduce beacon TX power** to limit detection range to ~2-3 meters. This prevents a gateway at Machine 5 from detecting a worker at adjacent Machine 6. Most beacons support TX power adjustment from +4 dBm down to -20 dBm.

5. **Mount gateways at operator-station height** (~1.2-1.5m), facing the operator position, NOT behind the machine body.

6. **Use a "strongest signal wins" algorithm.** If a worker's beacon is detected by multiple gateways, assign them to the gateway with the strongest RSSI.

---

## 2. Worker Wearable Tags (BLE Beacons)

### OPTION A: MOKOSmart H3 Card Beacon (Best Value)
**Recommended for budget-conscious deployments**

| Spec | Detail |
|------|--------|
| Form factor | Credit card size badge (fits in lanyard holder) |
| BLE version | 5.0 |
| Protocols | iBeacon, Eddystone (UID, URL, TLM) |
| Battery life | Up to 5 years |
| IP rating | IP66 (dust-tight, water jets) |
| TX power | Configurable |
| Extra features | Motion sensor, NFC optional |
| **Price** | **~$9.00-$9.50 per unit** |
| Where to buy | [MOKOSmart Store](https://store.mokosmart.com/product-category/bluetooth-beacon/) |

### OPTION B: Minew C10 Card Beacon (Mid-Range)
**Well-established brand with excellent documentation**

| Spec | Detail |
|------|--------|
| Form factor | Card-shaped badge, 18.5g with lanyard hole |
| BLE version | 5.0 |
| Protocols | iBeacon, Eddystone (UID, URL, TLM) simultaneously |
| Battery life | 2-3 years (800mAh Li-MnO2) |
| IP rating | IP65 |
| TX power | Configurable (up to 100m range) |
| Extra features | Hidden panic button, 3-axis accelerometer, optional RFID/NFC |
| **Price** | **~$12.00 per unit** |
| Where to buy | [Minew Store](https://www.minewstore.com/product/c10-card-beacon), [Tindie](https://www.tindie.com/products/minew/c10-card-beacon/), Alibaba (bulk) |

### OPTION C: MOKOSmart B2 Smart Badge (Premium)
**Best feature set for industrial use**

| Spec | Detail |
|------|--------|
| Form factor | Badge with CR80 ID card slot, 98x65x8.5mm, 35g |
| BLE version | 5.0 |
| Protocols | iBeacon, Eddystone |
| Battery life | Up to 5 years (800mAh) |
| IP rating | IP66 |
| Transmission range | 150m (open area) |
| TX power | Configurable |
| Extra features | SOS panic button, RFID/NFC, accelerometer, buzzer, LED |
| **Price** | **~$12.00-$13.00 per unit** (B2R replaceable-battery variant: ~$13.00) |
| Where to buy | [MOKOSmart Store](https://store.mokosmart.com/product/b2-bluetooth-smart-badge/) |

### OPTION D: Lansitec B006 Badge Beacon
**Good for custom orders at volume**

| Spec | Detail |
|------|--------|
| Form factor | Badge, 97x62x7mm, ABS housing |
| BLE version | 5.0 |
| Protocols | iBeacon |
| Battery | Rechargeable 600mAh or non-rechargeable 2xCR2032 |
| Battery life | ~1 year at 0 dBm / 1s interval |
| TX power | +4 dBm to -20 dBm in 4 dBm steps |
| Extra features | Optional temperature sensor, buzzer |
| **Price** | **Contact for quote** (high-volume manufacturer, >300k/month capacity) |
| Where to buy | [Lansitec](https://www.lansitec.com/products/badge-bluetooth-beacon/) (direct) |

### OPTION E: MOKOSmart H1 Keychain Beacon (Pocket Fob)
**Smallest and cheapest option**

| Spec | Detail |
|------|--------|
| Form factor | Compact keychain fob |
| BLE version | 5.0 |
| Protocols | iBeacon, Eddystone |
| Extra features | Motion sensor, one-click SOS |
| **Price** | **~$8.00 per unit** |
| Where to buy | [MOKOSmart Store](https://store.mokosmart.com/) |

### Tag Recommendation for Your Shop

**Primary pick: MOKOSmart H3 Card Beacon at ~$9/unit** or **MOKOSmart B2 Smart Badge at ~$12/unit.** The H3 is thinner and lighter for pure tracking; the B2 adds an SOS button and ID card slot which may be useful for shop safety. Both have IP66 rating suitable for a CNC environment. Buy 12-15 units (10 workers + spares). Total: **$108-$180 for all tags.**

---

## 3. Machine-Mounted Gateways/Receivers

### OPTION A: MOKOSmart MKGW3 Indoor PoE Gateway (Best Value)
**Recommended: Best price/performance for this use case**

| Spec | Detail |
|------|--------|
| Connectivity | WiFi + Ethernet + PoE (cascade up to 5 gateways) |
| BLE version | 5.0 |
| Protocols supported | MQTT, HTTP, TCP, UDP |
| Cloud compatibility | AWS IoT, Azure, Google Cloud |
| Scan capacity | High throughput |
| Bi-directional | Yes (can also send commands to beacons) |
| Configuration | Web interface |
| **Price** | **~$35.00 per unit** |
| Where to buy | [MOKOSmart Store](https://store.mokosmart.com/product-category/bluetooth-to-wifi-ethernet-gateway/) |

### OPTION B: April Brother AB BLE Gateway V4 (Budget + Flexible)
**Great for developers; strong HTTP/MQTT/WebSocket support**

| Spec | Detail |
|------|--------|
| Connectivity | WiFi (802.11 b/g/n) + Ethernet (10/100, PoE capable) |
| BLE chipset | NRF52832 on ESP32 base |
| Scan capacity | 210 ads/sec (Ethernet), 150 ads/sec (WiFi) |
| Protocols | MQTT, HTTP, WebSocket |
| Beacon support | iBeacon, Eddystone, custom BLE |
| Configuration | HTTP API |
| Range | 30m (PCB antenna) |
| Size | 72x74x20mm |
| **Price** | **~$38.50 per unit** (was $42) |
| Where to buy | [April Brother Store](https://store.aprbrother.com/product/abblegateway4), Alibaba (bulk) |

### OPTION C: Minew G1 IoT Gateway (Premium / Enterprise)
**Highest scan throughput; best for dense beacon environments**

| Spec | Detail |
|------|--------|
| Connectivity | WiFi (802.11 b/g/n, 300 Mbps) + Ethernet |
| BLE version | 5.0 (300m range, -108 dBm sensitivity) |
| Scan capacity | ~400 broadcast packets/second |
| Protocols | HTTP(SSL/TLS), MQTT(SSL/TLS & Proxy), TCP |
| Cloud | AWS, Azure, Google Cloud |
| Operating temp | -40C to 85C (industrial grade) |
| Data features | Pre-parsing, duplicate filtering, bulk configuration |
| Security | EN 18031 certified |
| **Price** | **~$65.00 per unit** |
| Where to buy | [Minew Store](https://www.minewstore.com/product/g1-iot-bluetooth-gateway), [DigiKey](https://www.digikey.com/en/products/detail/minew/G1/26776367), [BeaconZone](https://www.beaconzone.co.uk/G1) |

### OPTION D: MOKOSmart MKGW1-BG Pro (High Throughput)

| Spec | Detail |
|------|--------|
| Connectivity | WiFi + Ethernet |
| Scan capacity | Up to 300 Bluetooth devices scanned/second |
| Protocols | MQTT, HTTP, TCP, UDP |
| **Price** | **~$62.00 per unit** |
| Where to buy | [MOKOSmart Store](https://store.mokosmart.com/product-category/bluetooth-to-wifi-ethernet-gateway/) |

### OPTION E: Fanstel BWG840F (Open Source / Industrial)

| Spec | Detail |
|------|--------|
| Connectivity | WiFi (ESP32-based) |
| BLE | Bluetooth 5, 1800m range at 125 Kbps (long range mode) |
| Open source | Yes (firmware is open source) |
| Size | 60x60x22mm with wall mount bracket |
| **Price** | **~$47/unit (1pc), ~$39/unit (10pc), ~$36/unit (100pc)** |
| Where to buy | [Fanstel](https://www.fanstel.com/wifi-ble-5-iot-gateway) (direct) |

### Gateway Recommendation for Your Shop

**Primary pick: MOKOSmart MKGW3 at ~$35/unit.** It has PoE support (simplifies wiring -- just run one Ethernet cable to each machine area), MQTT support, and adequate scan performance for your density (10 beacons is trivial). Buy 14-16 units (one per machine + spares). Total: **$490-$560 for all gateways.**

If you want better scan performance and pre-parsing: **Minew G1 at ~$65/unit** (total ~$910-$1040 for 14-16 units).

---

## 4. DIY / Budget Gateway Option (ESP32)

For the absolute lowest cost, you can build your own gateways using ESP32 dev boards running open-source firmware.

### Hardware

| Component | Cost | Source |
|-----------|------|--------|
| ESP32 dev board (e.g., ESP32-WROOM-32) | ~$5-8 | Amazon, AliExpress |
| Olimex ESP32-GATEWAY (with Ethernet) | ~$25 | [Olimex](https://www.olimex.com/Products/IoT/ESP32/), DigiKey |
| USB power supply (5V/1A) | ~$3-5 | Amazon |
| Waterproof enclosure (IP65 ABS box) | ~$3-8 | Amazon, AliExpress |
| **Total per gateway** | **~$11-40** | |

### Firmware Options

1. **ESPresense** (https://espresense.com/) -- Purpose-built for room/zone presence detection. Uses RSSI with Kalman filtering. Reports to MQTT. Supports iBeacon, Eddystone, and MAC-based tracking. Web-based configuration. OTA updates. **Best choice for this use case.**

2. **OpenMQTTGateway / Theengs** (https://docs.openmqttgateway.com/) -- More general-purpose BLE-to-MQTT gateway. Decodes many BLE device types. Configurable RSSI minimum threshold. Presence detection with configurable away timer (default 120 seconds).

### Pros and Cons of DIY

| Pros | Cons |
|------|------|
| Lowest cost (~$11-15 per node with bare ESP32) | Requires firmware flashing and configuration |
| Full control over filtering and thresholds | No commercial support |
| Huge community (ESPresense, OpenMQTTGateway) | Less reliable than commercial gateways |
| Can add external antenna for better range | WiFi only (no Ethernet on basic boards) |
| OTA firmware updates | Need to build/source enclosures |

### DIY Cost for 14 Machines

| Approach | Per Unit | Total (14 units) |
|----------|----------|-------------------|
| Bare ESP32 + USB power + enclosure | ~$15 | ~$210 |
| Olimex ESP32-GATEWAY (Ethernet + enclosure) | ~$35 | ~$490 |

---

## 5. Central Software & Open-Source Stack

### Recommended Open-Source Architecture

```
[BLE Beacons on Workers]
        |  (BLE advertisement)
        v
[Gateways at Machines]  -- one per machine
        |  (WiFi/Ethernet)
        v
[MQTT Broker]  -- Mosquitto (open source)
        |
        v
[Processing Layer]  -- Node-RED or custom Python
        |
        v
[Database + API]  -- PostgreSQL/InfluxDB + custom API
        |
        v
[Your ProShop/MES Integration]
```

### Component Details

#### MQTT Broker: Eclipse Mosquitto
- **What:** Lightweight MQTT message broker
- **Why:** All recommended gateways support MQTT natively. Mosquitto is the industry standard.
- **Cost:** Free, open source
- **Install:** Docker container, Windows service, or Linux package
- **URL:** https://mosquitto.org/

#### Processing: Node-RED
- **What:** Visual flow-based programming tool for IoT
- **Why:** Can subscribe to MQTT topics from each gateway, apply RSSI threshold logic, determine which worker is at which machine, and push results to your application via HTTP/webhook
- **Cost:** Free, open source
- **Key flows needed:**
  - Subscribe to `gateway/machine-N/beacons` MQTT topic
  - Filter by RSSI threshold (e.g., > -65 dBm)
  - Apply rolling average to smooth RSSI
  - Determine "strongest gateway" for each beacon
  - Publish worker-machine assignments to output topic or HTTP endpoint
  - Handle "worker departed" events (beacon RSSI below threshold for N seconds)
- **URL:** https://nodered.org/

#### Alternative Processing: Custom Python Script
- Subscribe to MQTT using `paho-mqtt` library
- Maintain a dict of `{beacon_id: {gateway_id: rssi_avg, last_seen: timestamp}}`
- Every N seconds, for each beacon, pick the gateway with the strongest RSSI
- Publish assignments via MQTT, HTTP webhook, or write directly to database

#### Database: InfluxDB or PostgreSQL
- **InfluxDB** for time-series data (who was where, when, for how long)
- **PostgreSQL** for relational data (current assignments, worker profiles, machine info)
- Both are free and open source

#### Visualization / Dashboard: Grafana
- Connect to InfluxDB or PostgreSQL
- Build dashboards showing current worker-machine assignments
- Historical charts of time spent at each machine
- Free, open source
- **URL:** https://grafana.com/

### Pre-Built Open-Source Software

| Software | Purpose | URL |
|----------|---------|-----|
| **ESPresense** | ESP32 firmware for BLE presence detection | https://espresense.com/ |
| **OpenMQTTGateway** | ESP32 firmware for BLE-to-MQTT bridging | https://github.com/theengs/OpenMQTTGateway |
| **Theengs Gateway** | Python BLE-to-MQTT bridge (runs on Raspberry Pi, PC) | https://github.com/theengs/gateway |
| **Mosquitto** | MQTT broker | https://mosquitto.org/ |
| **Node-RED** | Flow-based IoT processing | https://nodered.org/ |
| **Grafana** | Dashboards and visualization | https://grafana.com/ |
| **Home Assistant** | Home/building automation with mqtt_room integration | https://www.home-assistant.io/ |

---

## 6. Turnkey / Near-Turnkey Systems

If you want to avoid DIY integration, these vendors offer more complete solutions:

### BeaconTrax Focus Detection RTLS
- **What:** Purpose-built system for proximity monitoring of personnel at workstations
- **How it works:** Gateways with 2-5 meter read range installed at each machine. ID badge beacons on workers. Reports time spent at each location.
- **Includes:** Hardware (gateways + badges) + cloud software + analytics
- **Best for:** If you want a vendor to handle everything
- **Pricing:** Contact for quote (expect $$$$ -- enterprise pricing)
- **URL:** https://www.beacontrax.com/people-locating-system/

### GAO RFID BLE People Tracking System
- **What:** Full BLE personnel tracking designed for manufacturing
- **Features:** IP67 beacons with up to 10-year battery, gateways with PoE/battery/solar power, up to 300m indoor range
- **Experience:** 30+ years, 11,000+ deployed systems
- **Pricing:** Contact for quote
- **URL:** https://gaorfid.com/ble-based-people-tracking-system-for-manufacturing-facilities/

### Kontakt.io (Enterprise / Healthcare Focus)
- **What:** Smart Badge + Gateway + Cloud Location Engine
- **How it works:** Smart Badge beacons on workers, gateways detect them, cloud software provides analytics (arrival/departure, time at location, movement patterns)
- **Best for:** Larger deployments with budget for SaaS
- **Pricing:** Smart Badges ~$30-50 each (estimated), gateways ~$100-200 each (estimated), plus monthly SaaS fee
- **Note:** Kontakt.io has shifted focus to healthcare RTLS; may be overkill for a 14-machine shop
- **URL:** https://kontakt.io/products/

### Sewio RTLS (Bluetooth + UWB)
- **What:** Full RTLS platform for manufacturing
- **Best for:** If you later need precise positioning (sub-meter with UWB)
- **URL:** https://www.sewio.net/bluetooth-ble-asset-visibility/

---

## 7. Budget Estimates

### Option 1: Full DIY (Lowest Cost)
| Item | Qty | Unit Cost | Total |
|------|-----|-----------|-------|
| MOKOSmart H3 Card Beacons | 12 | $9.50 | $114 |
| ESP32 dev boards + enclosures | 15 | $15 | $225 |
| Raspberry Pi 4 (MQTT broker + Node-RED server) | 1 | $60 | $60 |
| PoE switch (if using Olimex ESP32-GATEWAY) | 1 | $80 | $80 |
| Cabling, mounts, misc | 1 | $100 | $100 |
| **TOTAL** | | | **~$579** |

### Option 2: Commercial Gateways + Open-Source Software (Recommended)
| Item | Qty | Unit Cost | Total |
|------|-----|-----------|-------|
| MOKOSmart B2 Smart Badge Beacons | 12 | $12 | $144 |
| MOKOSmart MKGW3 PoE Gateways | 15 | $35 | $525 |
| Small server/PC (MQTT + Node-RED + database) | 1 | $200 | $200 |
| PoE switch (16-port) | 1 | $120 | $120 |
| Ethernet cabling + mounting hardware | 1 | $200 | $200 |
| **TOTAL** | | | **~$1,189** |

### Option 3: Premium Commercial (Best Reliability)
| Item | Qty | Unit Cost | Total |
|------|-----|-----------|-------|
| Minew C10 Card Beacons | 12 | $12 | $144 |
| Minew G1 IoT Gateways | 15 | $65 | $975 |
| Small server/PC | 1 | $200 | $200 |
| PoE switch + cabling + mounting | 1 | $350 | $350 |
| **TOTAL** | | | **~$1,669** |

### Option 4: Turnkey Vendor
| Item | Estimated Cost |
|------|---------------|
| BeaconTrax or GAO RFID full system | $5,000 - $15,000+ |
| Includes: hardware, software, installation support, cloud platform | |

---

## 8. Recommended Architecture

For a 14-machine CNC shop with 10 workers, here is the recommended approach:

### Hardware
- **Beacons:** 12x MOKOSmart B2 Smart Badge (~$12 each) -- IP66, 5-year battery, iBeacon/Eddystone, SOS button, ID card slot
- **Gateways:** 15x MOKOSmart MKGW3 PoE Gateway (~$35 each) -- one per machine + one spare. PoE simplifies installation (single Ethernet cable per machine area)
- **Network:** 1x 16-port PoE switch (~$120), Ethernet runs to each machine area
- **Server:** 1x small PC or Raspberry Pi running Mosquitto + Node-RED + PostgreSQL

### Software Stack (All Free/Open Source)
1. **Gateways** configured to publish beacon scan data to MQTT broker
2. **Mosquitto** MQTT broker on central server
3. **Node-RED** subscribes to gateway topics, applies:
   - RSSI threshold filter (discard signals weaker than -70 dBm, tunable per machine)
   - Rolling average (5-sample window)
   - "Strongest gateway wins" assignment logic
   - Departure timeout (beacon not seen for 120 seconds = worker left)
4. **Node-RED** publishes worker-machine assignments to:
   - MQTT topic for real-time consumers
   - HTTP webhook to ProShop/MES system
   - PostgreSQL for historical logging
5. **Grafana** dashboard for real-time visibility and historical reporting

### Installation Approach
1. Mount gateways at operator station height (~1.2m) on the operator side of each machine
2. Use plastic or non-metallic mounting brackets (avoid metal near antenna)
3. Run Ethernet from PoE switch to each gateway
4. Configure each gateway with a unique machine identifier
5. Issue each worker a badge beacon with a unique ID mapped to their name
6. Spend 1-2 days calibrating RSSI thresholds per machine (have a worker stand at the machine and observe RSSI readings, then set threshold ~5 dB below the observed average)

### Data Flow
```
Worker Badge (BLE broadcast every 1-2 sec)
    --> Gateway at Machine (scans continuously, reports via MQTT)
        --> MQTT Broker (Mosquitto)
            --> Node-RED (RSSI filter + assignment logic)
                --> ProShop API (HTTP webhook: "Worker A arrived at Machine 5")
                --> PostgreSQL (log: worker, machine, timestamp, duration)
                --> Grafana Dashboard (real-time shop floor view)
```

---

## Key Vendor Links

### Beacons (Worker Tags)
- MOKOSmart Store: https://store.mokosmart.com/product-category/bluetooth-beacon/
- Minew Store: https://www.minewstore.com/product/c10-card-beacon
- Lansitec: https://www.lansitec.com/products/badge-bluetooth-beacon/

### Gateways (Machine Receivers)
- MOKOSmart Store: https://store.mokosmart.com/product-category/bluetooth-to-wifi-ethernet-gateway/
- April Brother Store: https://store.aprbrother.com/product/abblegateway4
- Minew Store: https://www.minewstore.com/product/g1-iot-bluetooth-gateway
- Fanstel: https://www.fanstel.com/wifi-ble-5-iot-gateway

### Open-Source Software
- ESPresense: https://espresense.com/
- OpenMQTTGateway: https://github.com/theengs/OpenMQTTGateway
- Theengs Gateway: https://github.com/theengs/gateway
- Mosquitto MQTT: https://mosquitto.org/
- Node-RED: https://nodered.org/
- Grafana: https://grafana.com/

### Turnkey Systems
- BeaconTrax: https://www.beacontrax.com/people-locating-system/
- GAO RFID: https://gaorfid.com/ble-based-people-tracking-system-for-manufacturing-facilities/
- Kontakt.io: https://kontakt.io/products/
