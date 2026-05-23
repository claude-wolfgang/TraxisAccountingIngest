"""Watch MQTT for any Traxis B2 badge broadcast (our assigned UUID).
Prints per-gateway RSSI in real time so you can walk-test proximity.

Usage:
  python b2_watch.py            # watch all 10 badges
  python b2_watch.py 3          # watch only B2-03 (minor=3)
  Ctrl-C to stop.
"""
import json
import sys
import time
import paho.mqtt.client as mqtt

BROKER = "10.1.1.178"

# Our assigned Traxis B2 batch UUID (lower-case form ESPresense emits)
TRAXIS_UUID = "23fd6bbb-8a96-4c0e-8ab4-0158e9a3d1ef"

# Optional minor filter
TARGET_MINOR = int(sys.argv[1]) if len(sys.argv) > 1 else None

# Track last-seen per (minor, gateway) so we only print on meaningful change
last_seen = {}

# Also count gateway telemetry so we can report which gateways are alive
gateway_seen = set()


def on_connect(client, userdata, flags, rc, properties):
    target = f"B2-{TARGET_MINOR:02d}" if TARGET_MINOR else "all 10 Traxis B2 badges"
    print(f"[{time.strftime('%H:%M:%S')}] connected to {BROKER}:1883 — watching for {target}", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] UUID filter: {TRAXIS_UUID}", flush=True)
    client.subscribe("espresense/devices/#")
    client.subscribe("espresense/rooms/+/status")


def on_message(client, userdata, msg):
    # Gateway telemetry
    if msg.topic.startswith("espresense/rooms/") and msg.topic.endswith("/status"):
        gw = msg.topic.split("/")[2]
        if gw not in gateway_seen:
            gateway_seen.add(gw)
            payload = msg.payload.decode(errors="replace")
            print(f"[{time.strftime('%H:%M:%S')}] gateway alive: {gw} ({payload})", flush=True)
        return

    # Device readings
    if not msg.topic.startswith("espresense/devices/"):
        return

    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict):
        return

    device_id = payload.get("id", "")
    if not device_id.startswith("iBeacon:"):
        return

    # iBeacon:{uuid}-{major}-{minor}
    suffix = device_id[len("iBeacon:"):]
    if not suffix.lower().startswith(TRAXIS_UUID):
        return  # not one of ours

    # Parse major/minor (last two dash-separated tokens)
    parts = suffix.rsplit("-", 2)
    if len(parts) != 3:
        return
    _, major, minor = parts
    try:
        major = int(major)
        minor = int(minor)
    except ValueError:
        return

    if TARGET_MINOR is not None and minor != TARGET_MINOR:
        return

    # Extract gateway from topic: espresense/devices/{id}/{gateway}
    gw = msg.topic.rsplit("/", 1)[-1]
    rssi = payload.get("rssi")
    distance = payload.get("distance")

    key = (minor, gw)
    now = time.time()
    last = last_seen.get(key, (0, None))
    # Print on first sight, or if RSSI changed by >2 dB, or every 5s
    if last[1] is None or abs((rssi or 0) - (last[1] or 0)) >= 2 or (now - last[0]) > 5:
        print(f"[{time.strftime('%H:%M:%S')}]  B2-{minor:02d}  gw={gw:3s}  rssi={rssi!s:>7s}  dist={distance!s:>6s}m", flush=True)
        last_seen[key] = (now, rssi)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883, 60)
try:
    client.loop_forever()
except KeyboardInterrupt:
    print(f"\n[{time.strftime('%H:%M:%S')}] stopped. gateways seen: {sorted(gateway_seen) or 'none'}")
