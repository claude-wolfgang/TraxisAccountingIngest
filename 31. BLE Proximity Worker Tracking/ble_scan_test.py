"""
BLE Scanner Test — P31 Proximity Worker Tracking
Scans for BLE advertisements and prints device name, MAC, RSSI.
Look for the Feasycom beacon in the output.
"""

import asyncio
from bleak import BleakScanner


def detection_callback(device, advertisement_data):
    name = device.name or "(unknown)"
    rssi = advertisement_data.rssi
    # Show manufacturer data if present (helps identify Feasycom)
    mfr = ""
    if advertisement_data.manufacturer_data:
        for company_id, data in advertisement_data.manufacturer_data.items():
            mfr = f"  mfr=0x{company_id:04X} data={data.hex()}"
    print(f"  {rssi:>4} dBm  {device.address:<20}  {name}{mfr}")


async def main():
    print("Scanning for BLE devices (10 seconds)...")
    print(f"{'RSSI':>6}  {'Address':<20}  Name")
    print("-" * 70)

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    await asyncio.sleep(10)
    await scanner.stop()

    print("-" * 70)
    print("Scan complete.")


if __name__ == "__main__":
    asyncio.run(main())
