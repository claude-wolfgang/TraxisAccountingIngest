"""
Raw BLE advertisement logger — logs every callback with precise timing.
Shows whether low sample count is beacon interval or Windows filtering.
Run for 30 seconds with tags nearby. Ctrl+C to stop early.
"""

import asyncio
import time
from bleak import BleakScanner

start = time.time()
counts = {}


def callback(device, adv):
    now = time.time() - start
    addr = device.address
    rssi = adv.rssi
    name = device.name or ""
    counts[addr] = counts.get(addr, 0) + 1
    # Only print known beacons + any iBeacon (mfr 0x004C)
    is_ibeacon = 0x004C in adv.manufacturer_data
    if is_ibeacon or "RAD" in name or "Feasy" in name.lower():
        print(f"  {now:6.2f}s  {rssi:>4} dBm  {addr}  {name}  #{counts[addr]}")


async def main():
    print("Raw BLE advertisement log (30s) — put tags near dongle")
    print(f"{'Time':>8}  {'RSSI':>4}       {'Address':<20} {'Name'}")
    print("-" * 65)

    scanner = BleakScanner(detection_callback=callback, scanning_mode="active")
    await scanner.start()
    await asyncio.sleep(30)
    await scanner.stop()

    print("-" * 65)
    print(f"\nAll devices seen ({len(counts)} total):")
    for addr, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {addr}  {count:>4} advertisements")


if __name__ == "__main__":
    asyncio.run(main())
