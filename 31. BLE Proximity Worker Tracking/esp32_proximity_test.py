"""
ESP32 Gateway Proximity Test — P31 BLE Worker Tracking

Subscribes to ESPresense MQTT output from ESP32 gateways and displays
live beacon RSSI / distance with zone classification.

Logs all readings to CSV for post-test analysis of dynamic range.

Prerequisites:
  pip install paho-mqtt

Usage:
  python esp32_proximity_test.py                    # localhost broker
  python esp32_proximity_test.py 192.168.1.50       # remote broker
"""

import csv
import json
import os
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER = sys.argv[1] if len(sys.argv) > 1 else "localhost"
PORT = 1883

KNOWN_BEACONS = {39475: "Tag-A", 10065: "Tag-B"}
WINDOW = 10  # rolling average window in seconds

# {beacon_key: [(timestamp, rssi, distance, room), ...]}
history = {}
rooms_seen = set()

LOG_FILE = f"proximity_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
csv_file = None
csv_writer = None

if os.name == "nt":
    os.system("")


def zone_label(rssi):
    if rssi > -45:
        return "\033[92mAT MACHINE\033[0m"
    elif rssi > -58:
        return "\033[93mNEARBY    \033[0m"
    elif rssi > -66:
        return "\033[33mIN AREA   \033[0m"
    else:
        return "\033[91mFAR / GONE\033[0m"


def rssi_bar(rssi):
    clamped = max(-100, min(-30, rssi))
    length = int((clamped + 100) / 70 * 40)
    return "\033[92m" + "#" * length + "\033[0m" + "-" * (40 - length)


def extract_major(device_id):
    """Extract iBeacon major number from ESPresense device ID.
    Format: iBeacon:<uuid>-<major>-<minor>
    """
    if not device_id.startswith("iBeacon:"):
        return None
    parts = device_id.split("-")
    if len(parts) < 2:
        return None
    try:
        return int(parts[-2])
    except ValueError:
        return None


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"  Connected to MQTT broker at {BROKER}:{PORT}")
        client.subscribe("espresense/rooms/#")
        client.subscribe("espresense/devices/#")
        print("  Subscribed to espresense/rooms/# and espresense/devices/#")
    else:
        print(f"  MQTT connection failed (rc={reason_code})")


def on_message(client, userdata, msg):
    global csv_file, csv_writer

    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(payload, dict):
        return

    device_id = payload.get("id", "")
    rssi = payload.get("rssi")
    distance = payload.get("distance")
    raw_distance = payload.get("raw")
    mac = payload.get("mac", "")

    if rssi is None:
        return

    major = extract_major(device_id)

    # Extract room from topic: espresense/devices/<device_id>/<room> or espresense/rooms/<room>/<device_id>
    topic_parts = msg.topic.split("/")
    if len(topic_parts) >= 4 and topic_parts[1] == "devices":
        room = topic_parts[3]
    elif len(topic_parts) >= 4 and topic_parts[1] == "rooms":
        room = topic_parts[2]
    else:
        room = "unknown"
    rooms_seen.add(room)

    now = time.time()
    key = major if major in KNOWN_BEACONS else device_id

    if key not in history:
        label = KNOWN_BEACONS.get(major, device_id[:40])
        history[key] = {"label": label, "readings": [], "known": major in KNOWN_BEACONS}
        if major in KNOWN_BEACONS:
            print(f"  * Discovered known beacon: {label} (major={major}) via {room}")
        elif len(history) <= 20:
            print(f"  * Discovered device: {device_id[:50]} via {room}")

    history[key]["readings"].append((now, rssi, distance or 0, room))
    history[key]["readings"] = [
        r for r in history[key]["readings"] if now - r[0] <= WINDOW
    ]

    if csv_writer and major in KNOWN_BEACONS:
        csv_writer.writerow([
            datetime.now().isoformat(),
            KNOWN_BEACONS[major],
            major,
            room,
            rssi,
            distance or "",
            raw_distance or "",
            mac,
        ])
        csv_file.flush()


def render():
    now = time.time()
    lines = []
    lines.append("=" * 72)
    lines.append("   ESP32 GATEWAY PROXIMITY TEST — ESPresense + MQTT")
    lines.append(f"   Broker: {BROKER}:{PORT}   Rooms: {', '.join(sorted(rooms_seen)) or '(none yet)'}")
    lines.append(f"   Logging to: {LOG_FILE}")
    lines.append("   Ctrl+C to stop")
    lines.append("=" * 72)
    lines.append("")

    known_entries = {k: v for k, v in history.items() if v["known"]}
    other_count = sum(1 for v in history.values() if not v["known"])

    if not known_entries:
        lines.append("  Waiting for known Feasycom beacons (major 60285, 40604)...")
        lines.append(f"  Other BLE devices seen: {other_count}")
        lines.append("")
    else:
        for key, entry in known_entries.items():
            readings = [r for r in entry["readings"] if now - r[0] <= WINDOW]
            label = entry["label"]

            if readings:
                latest_rssi = readings[-1][1]
                latest_dist = readings[-1][2]
                latest_room = readings[-1][3]
                avg_rssi = sum(r[1] for r in readings) / len(readings)
                min_rssi = min(r[1] for r in readings)
                max_rssi = max(r[1] for r in readings)
                spread = max_rssi - min_rssi
                avg_dist = sum(r[2] for r in readings) / len(readings)

                bar = rssi_bar(avg_rssi)
                zone = zone_label(avg_rssi)

                lines.append(f"  {label} (major={key})  via [{latest_room}]")
                lines.append(f"    RSSI:  now={latest_rssi:>4} dBm  avg={avg_rssi:>6.1f}  "
                             f"min={min_rssi:>4}  max={max_rssi:>4}  spread={spread:>2} dB")
                lines.append(f"    Dist:  now={latest_dist:>5.2f}m   avg={avg_dist:>5.2f}m   "
                             f"({len(readings)} samples / {WINDOW}s)")
                lines.append(f"    [{bar}]  {zone}")
            else:
                lines.append(f"  {label} (major={key})")
                lines.append(f"    -- no recent signal --")
                lines.append(f"    [{'-' * 40}]  \033[91mNO SIGNAL\033[0m")
            lines.append("")

    lines.append(f"  Other BLE devices in range: {other_count}")
    lines.append("-" * 72)
    lines.append("  Zones:  > -45 AT MACHINE | > -58 NEARBY | > -66 IN AREA | else FAR")
    lines.append("=" * 72)

    while len(lines) < 28:
        lines.append("")

    output = "\033[H" + "\n".join(line.ljust(72) for line in lines) + "\n"
    print(output, end="", flush=True)


def main():
    global csv_file, csv_writer

    csv_file = open(LOG_FILE, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["timestamp", "tag", "major", "room", "rssi", "distance", "raw_distance", "mac"])

    os.system("cls" if os.name == "nt" else "clear")
    print(f"Connecting to MQTT broker at {BROKER}:{PORT}...")
    print(f"Logging CSV to {LOG_FILE}\n")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
    except ConnectionRefusedError:
        print(f"\n  ERROR: Cannot connect to MQTT broker at {BROKER}:{PORT}")
        print("  Make sure Mosquitto is running:")
        print('    net start mosquitto')
        print("  Or install it: https://mosquitto.org/download/")
        return
    except OSError as e:
        print(f"\n  ERROR: {e}")
        print(f"  Check that {BROKER} is reachable and Mosquitto is running.")
        return

    client.loop_start()

    try:
        while True:
            render()
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        csv_file.close()

    print("\n" * 3)
    print("=" * 72)
    print("  TEST SESSION SUMMARY")
    print("=" * 72)
    known = {k: v for k, v in history.items() if v["known"]}
    for key, entry in known.items():
        readings = entry["readings"]
        if readings:
            rssis = [r[1] for r in readings]
            dists = [r[2] for r in readings]
            print(f"\n  {entry['label']} (major={key}):")
            print(f"    Readings:  {len(readings)}")
            print(f"    RSSI:      min={min(rssis)} max={max(rssis)} avg={sum(rssis)/len(rssis):.1f} "
                  f"spread={max(rssis)-min(rssis)} dB")
            print(f"    Distance:  min={min(dists):.2f}m max={max(dists):.2f}m avg={sum(dists)/len(dists):.2f}m")
    print(f"\n  CSV log saved to: {LOG_FILE}")
    print("=" * 72)


if __name__ == "__main__":
    main()
