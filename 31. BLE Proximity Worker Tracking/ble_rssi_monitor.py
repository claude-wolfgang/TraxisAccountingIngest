"""
BLE RSSI Live Monitor — P31 Proximity Worker Tracking
Identifies Feasycom beacons by iBeacon UUID (not MAC, which rotates).
Press Ctrl+C to stop.
"""

import asyncio
import os
import struct
import time
from bleak import BleakScanner

# iBeacon manufacturer ID (Apple)
IBEACON_COMPANY = 0x004C
IBEACON_PREFIX = bytes([0x02, 0x15])  # iBeacon type + length

# RSSI history per beacon, keyed by major only (minor rotates on some Feasycom tags)
# {major: [(timestamp, rssi, mac, minor), ...]}
history = {}
beacon_names = {}  # {major: "Tag-N"}
WINDOW = 5  # rolling average window (seconds)

# Enable ANSI escapes on Windows
if os.name == "nt":
    os.system("")


def parse_ibeacon(manufacturer_data):
    """Extract UUID, major, minor, tx_power from iBeacon advertisement."""
    if IBEACON_COMPANY not in manufacturer_data:
        return None
    data = manufacturer_data[IBEACON_COMPANY]
    if len(data) < 23 or data[:2] != IBEACON_PREFIX:
        return None
    uuid = data[2:18].hex()
    uuid_str = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:32]}"
    major = struct.unpack(">H", data[18:20])[0]
    minor = struct.unpack(">H", data[20:22])[0]
    tx_power = struct.unpack("b", data[22:23])[0]
    return uuid_str, major, minor, tx_power


def rssi_bar(rssi):
    clamped = max(-100, min(-30, rssi))
    length = int((clamped + 100) / 70 * 30)
    return "#" * length + "-" * (30 - length)


def zone_label(rssi):
    if rssi > -82:
        return "AT MACHINE"
    elif rssi > -88:
        return "NEARBY    "
    elif rssi > -94:
        return "IN AREA   "
    else:
        return "FAR / LOST"


def detection_callback(device, adv):
    result = parse_ibeacon(adv.manufacturer_data)
    if result is None:
        return
    uuid_str, major, minor, tx_power = result
    key = major  # group by major only — minor varies per slot
    now = time.time()

    if key not in history:
        history[key] = []
        tag_num = len(beacon_names) + 1
        beacon_names[key] = f"Tag-{tag_num} (major={major})"
        print(f"  * Discovered {beacon_names[key]}: minor={minor} mac={device.address}")

    history[key].append((now, adv.rssi, device.address, minor))
    history[key] = [(t, r, m, mi) for t, r, m, mi in history[key] if now - t <= WINDOW]


def render():
    now = time.time()
    lines = []
    lines.append("=" * 64)
    lines.append("   BLE PROXIMITY MONITOR  --  Feasycom Beacon Tags")
    lines.append("   Identifying by iBeacon major/minor (MAC rotates)")
    lines.append("   Ctrl+C to stop")
    lines.append("=" * 64)
    lines.append("")

    if not beacon_names:
        lines.append("  Waiting for iBeacon advertisements...")
        lines.append("")
    else:
        for key, label in beacon_names.items():
            readings = [(t, r, m, mi) for t, r, m, mi in history.get(key, []) if now - t <= WINDOW]
            if readings:
                latest_rssi = readings[-1][1]
                latest_mac = readings[-1][2]
                avg = sum(r for _, r, _, _ in readings) / len(readings)
                bar = rssi_bar(latest_rssi)
                zone = zone_label(avg)
                lines.append(f"  {label}")
                lines.append(f"    Latest: {latest_rssi:>4} dBm   Avg: {avg:>6.1f} dBm   ({len(readings)} samples)")
                lines.append(f"    [{bar}]  {zone}")
            else:
                lines.append(f"  {label}")
                lines.append(f"    -- no recent signal --")
                lines.append(f"    [{'-' * 30}]  NO SIGNAL")
            lines.append("")

    lines.append("-" * 64)
    lines.append("  Zones:  > -82 AT MACHINE | > -88 NEARBY")
    lines.append("          > -94 IN AREA    | else FAR / LOST")
    lines.append("=" * 64)

    # Pad to fixed height to prevent flicker
    while len(lines) < 25:
        lines.append("")

    output = "\033[H" + "\n".join(line.ljust(64) for line in lines) + "\n"
    print(output, end="", flush=True)


async def main():
    os.system("cls" if os.name == "nt" else "clear")
    print("Starting BLE monitor... waiting for iBeacon advertisements...\n")

    scanner = BleakScanner(
        detection_callback=detection_callback,
        scanning_mode="active",
    )
    await scanner.start()

    try:
        while True:
            render()
            await asyncio.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        await scanner.stop()

    print("\n" * 3)
    print("Session summary:")
    for key, label in beacon_names.items():
        readings = history.get(key, [])
        if readings:
            rssis = [r for _, r, _, _ in readings]
            print(f"  {label}: {len(readings)} readings, "
                  f"min={min(rssis)} dBm, max={max(rssis)} dBm, "
                  f"avg={sum(rssis)/len(rssis):.1f} dBm")
        else:
            print(f"  {label}: no readings")


if __name__ == "__main__":
    asyncio.run(main())
