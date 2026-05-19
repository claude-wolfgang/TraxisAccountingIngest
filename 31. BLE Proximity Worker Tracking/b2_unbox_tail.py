"""
B2 unbox tail — watch MQTT for new beacons appearing on the network.

Snapshots the set of device IDs currently broadcasting, then prints any
NEW device ID, MAC, or advertising format that shows up afterwards.
This isolates B2 badges from the already-broadcasting Feasycom tags and
self-discovered ESP32 gateways.

Usage:  python b2_unbox_tail.py
        (Ctrl-C to stop. Run this, then power on one B2 at a time.)
"""

import json
import sys
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER = "10.1.1.108"
PORT = 1883
BASELINE_SECONDS = 8  # observe existing traffic first, then flag anything new

seen_baseline = {}   # device_id -> first-seen-ts
device_macs = {}     # device_id -> mac
new_devices = set()
start_ts = time.time()
baseline_locked = threading.Event()
msg_count_baseline = [0]
msg_count_total = [0]


def lock_baseline_timer():
    time.sleep(BASELINE_SECONDS)
    baseline_locked.set()
    print()
    print("=" * 70)
    if len(seen_baseline) == 0:
        print(f"BASELINE LOCKED — no devices broadcasting right now ({msg_count_baseline[0]} msgs total).")
        print("  Gateways may be quiet (no beacons in range). Any new device that")
        print("  appears now will be flagged.")
    else:
        print(f"BASELINE LOCKED — {len(seen_baseline)} unique devices already broadcasting:")
        for did in sorted(seen_baseline):
            print(f"  {did}   mac={device_macs.get(did, '?')}")
    print("=" * 70)
    print()
    print(f"[{datetime.now():%H:%M:%S}] Now watching for NEW devices. Power on a B2 badge.")
    print(flush=True)


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[{datetime.now():%H:%M:%S}] Connected to MQTT {BROKER}:{PORT}", flush=True)
    client.subscribe("espresense/devices/#")
    print(f"[{datetime.now():%H:%M:%S}] Baseline scan: {BASELINE_SECONDS}s — cataloging what's already broadcasting...", flush=True)
    threading.Thread(target=lock_baseline_timer, daemon=True).start()


def on_message(client, userdata, msg):
    msg_count_total[0] += 1
    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict):
        return

    device_id = payload.get("id", "")
    mac = payload.get("mac", "").lower()
    rssi = payload.get("rssi")
    name = payload.get("name", "")
    distance = payload.get("distance")
    tx = payload.get("tx")
    topic_parts = msg.topic.split("/")
    room = topic_parts[3] if len(topic_parts) >= 4 else "?"

    if not baseline_locked.is_set():
        msg_count_baseline[0] += 1
        if device_id and device_id not in seen_baseline:
            seen_baseline[device_id] = time.time() - start_ts
            device_macs[device_id] = mac
        return

    # Post-baseline: print anything we haven't seen before
    if device_id and device_id not in seen_baseline and device_id not in new_devices:
        new_devices.add(device_id)
        print()
        print(">>> NEW DEVICE <<<")
        print(f"  time:     {datetime.now():%H:%M:%S}")
        print(f"  id:       {device_id}")
        print(f"  mac:      {mac}")
        print(f"  name:     {name!r}")
        print(f"  tx_power: {tx}")
        print(f"  rssi:     {rssi} dBm  (gateway: {room})")
        print(f"  distance: {distance} m")
        print(f"  raw:      {payload}")
        print(flush=True)
    elif device_id in new_devices:
        print(f"  [{room}] {device_id}  rssi={rssi}  dist={distance}", flush=True)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT, 60)
    except (ConnectionRefusedError, OSError) as e:
        print(f"ERROR: Cannot connect to {BROKER}:{PORT} — {e}")
        sys.exit(1)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now():%H:%M:%S}] Stopped. New devices seen: {len(new_devices)}")


if __name__ == "__main__":
    main()
