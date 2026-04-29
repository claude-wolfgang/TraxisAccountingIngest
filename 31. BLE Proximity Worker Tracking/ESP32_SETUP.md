# ESP32 Gateway Setup — ESPresense Firmware

## Step 1: Install CP2102 USB Driver

The ESP32-WROOM-32 boards use a CP2102 USB-to-serial chip.
If no COM port appears in Device Manager when plugged in:

1. Download driver: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers
2. Install, reboot
3. Plug in ESP32 — should appear as "Silicon Labs CP210x" on a COM port

Verify in Device Manager → Ports (COM & LPT) → should show COM3 or similar.

## Step 2: Flash ESPresense via Web Flasher

1. Open Chrome or Edge (must be Chromium-based for Web Serial)
2. Go to: https://espresense.com/firmware
3. Select flavor: **esp32** (for WROOM-32)
4. Click "Connect" → select the COM port for your ESP32
5. Click "Install" → wait ~60 seconds for flash to complete
6. ESP32 reboots into ESPresense

## Step 3: Configure ESPresense Wi-Fi + MQTT

After flashing, the ESP32 creates a Wi-Fi hotspot:

1. Connect phone/laptop to Wi-Fi network: **ESPresense-XXXXXX**
2. A captive portal opens (or browse to 192.168.4.1)
3. Configure:
   - **Wi-Fi SSID/password**: your shop network
   - **MQTT broker**: IP of the PC running Mosquitto (see below)
   - **MQTT port**: 1883
   - **Room name**: machine identifier (e.g., `haas-vf2`, `mazak-1`, or `test-bench` for testing)
4. Save and reboot

## Step 4: Install Mosquitto MQTT Broker (on this PC)

### Option A: Windows installer
1. Download: https://mosquitto.org/download/
2. Run installer (use defaults)
3. Edit config to allow local network connections:
   - Open `C:\Program Files\mosquitto\mosquitto.conf`
   - Add these lines:
     ```
     listener 1883
     allow_anonymous true
     ```
4. Restart service: `net stop mosquitto && net start mosquitto`

### Option B: Quick test with Python
```
pip install amqtt
amqtt  # runs a broker on port 1883
```

## Step 5: Verify MQTT Messages

After ESP32 connects to Wi-Fi and MQTT:
```
mosquitto_sub -h localhost -t "espresense/#" -v
```

You should see messages like:
```
espresense/rooms/test-bench/iBeacon:xxxxxxxx-xxxx-...-60285-nnn  {"id":"iBeacon:...","rssi":-65,"distance":1.2,...}
```

## Step 6: Run Proximity Test

```
python esp32_proximity_test.py
```

This script subscribes to ESPresense MQTT output and displays live beacon
proximity with zone detection, logging all readings to CSV for analysis.

## Hardware Checklist
- [ ] ESP32-WROOM-32 board plugged in via USB
- [ ] CP2102 driver installed (COM port visible)
- [ ] ESPresense firmware flashed
- [ ] Wi-Fi configured on ESP32
- [ ] Mosquitto running on this PC
- [ ] Both Feasycom beacon tags powered on (major 60285, 40604)
