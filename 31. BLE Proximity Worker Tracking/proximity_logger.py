"""
Persistent BLE proximity logger — P31 BLE Worker Tracking

Subscribes to all ESPresense gateways via MQTT and logs iBeacon
proximity readings to SQLite. Runs continuously as a background service.

Usage:
  python proximity_logger.py                  # default broker localhost
  python proximity_logger.py 10.1.1.108       # specify broker
"""

import json
import os
import sqlite3
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER = sys.argv[1] if len(sys.argv) > 1 else "10.1.1.108"
PORT = 1883
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proximity.db")

KNOWN_BEACONS = {39475: "Tag-A", 35540: "Tag-B", 40604: "Tag-A", 60285: "Tag-B"}
# Major 10065 is ambiguous — both tags broadcast it. Disambiguate by MAC.
AMBIGUOUS_MAJORS = {10065: {"dc0d3048303a": "Tag-B", "dc0d301f90a3": "Tag-A"}}
KNOWN_MACS = {"dc0d301f90a3": "Tag-A", "dc0d3048303a": "Tag-B"}
# Majors from ESP32 gateway self-detection (not beacons)
IGNORE_MAJORS = {72, 116, 252}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            tag_name TEXT,
            major INTEGER,
            minor INTEGER,
            room TEXT NOT NULL,
            rssi REAL NOT NULL,
            distance REAL,
            mac TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_room ON readings(room)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_major ON readings(major)
    """)
    conn.commit()
    return conn


def extract_ibeacon_parts(device_id):
    if not device_id.startswith("iBeacon:"):
        return None, None
    parts = device_id.split("-")
    if len(parts) < 2:
        return None, None
    try:
        major = int(parts[-2])
        minor = int(parts[-1])
        return major, minor
    except ValueError:
        return None, None


def make_on_connect(db_conn):
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[{datetime.now():%H:%M:%S}] Connected to MQTT broker at {BROKER}:{PORT}")
            client.subscribe("espresense/devices/#")
            print(f"[{datetime.now():%H:%M:%S}] Subscribed to espresense/devices/#")
        else:
            print(f"[{datetime.now():%H:%M:%S}] MQTT connection failed (rc={reason_code})")
    return on_connect


def make_on_message(db_conn):
    insert_count = [0]
    last_flush = [time.time()]

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if not isinstance(payload, dict):
            return

        device_id = payload.get("id", "")
        rssi = payload.get("rssi")
        distance = payload.get("distance")
        mac = payload.get("mac", "")

        if rssi is None:
            return

        major, minor = extract_ibeacon_parts(device_id)
        if major is None:
            return

        if major in IGNORE_MAJORS:
            return

        topic_parts = msg.topic.split("/")
        room = topic_parts[3] if len(topic_parts) >= 4 else "unknown"

        mac_clean = mac.replace(":", "").lower()
        if major in AMBIGUOUS_MAJORS:
            tag_name = AMBIGUOUS_MAJORS[major].get(mac_clean)
        else:
            tag_name = KNOWN_BEACONS.get(major)
        if tag_name is None and mac_clean in KNOWN_MACS:
            tag_name = KNOWN_MACS[mac_clean]
        now = datetime.now().isoformat()

        try:
            db_conn.execute(
                "INSERT INTO readings (timestamp, device_id, tag_name, major, minor, room, rssi, distance, mac) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, device_id, tag_name, major, minor, room, rssi, distance, mac),
            )
            insert_count[0] += 1

            if time.time() - last_flush[0] >= 5:
                db_conn.commit()
                last_flush[0] = time.time()
        except sqlite3.Error as e:
            print(f"[{datetime.now():%H:%M:%S}] DB error: {e}")

    return on_message


def make_on_disconnect():
    def on_disconnect(client, userdata, flags, reason_code, properties):
        print(f"[{datetime.now():%H:%M:%S}] Disconnected (rc={reason_code}), reconnecting...")
    return on_disconnect


def main():
    db_conn = init_db()
    row_count = db_conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    print(f"Proximity logger starting — DB: {DB_PATH} ({row_count} existing readings)")
    print(f"Broker: {BROKER}:{PORT}")
    print(f"Known beacons: {KNOWN_BEACONS}")
    print()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = make_on_connect(db_conn)
    client.on_message = make_on_message(db_conn)
    client.on_disconnect = make_on_disconnect()
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect(BROKER, PORT, 60)
    except (ConnectionRefusedError, OSError) as e:
        print(f"ERROR: Cannot connect to {BROKER}:{PORT} — {e}")
        return

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now():%H:%M:%S}] Shutting down...")
    finally:
        db_conn.commit()
        db_conn.close()
        client.disconnect()
        print("Logger stopped.")


if __name__ == "__main__":
    main()
