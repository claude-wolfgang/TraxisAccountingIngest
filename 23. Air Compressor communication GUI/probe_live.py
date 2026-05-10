"""Read interesting register ranges twice with a delay to find changing values."""
from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
connected = client.connect()
print(f"Connected: {connected}")
if not connected:
    exit(1)

# Ranges that had data
ranges = [
    (0, 20), (130, 150),
    (1280, 1370),
    (1540, 1560), (1670, 1690),
    (1800, 1830), (1920, 1950),
    (4100, 4140), (4230, 4260),
]

def read_all(label):
    data = {}
    for start, end in ranges:
        count = end - start
        try:
            result = client.read_holding_registers(start, count=count, device_id=1)
            if not result.isError():
                for i, val in enumerate(result.registers):
                    data[start + i] = val
        except:
            pass
        time.sleep(0.05)
    print(f"\n--- {label} ---")
    return data

snap1 = read_all("Snapshot 1")
print(f"Read {len(snap1)} registers")

print("\nWaiting 10 seconds...")
time.sleep(10)

snap2 = read_all("Snapshot 2")
print(f"Read {len(snap2)} registers")

print("\n========== CHANGED REGISTERS ==========")
changed = False
for addr in sorted(snap1.keys()):
    if addr in snap2 and snap1[addr] != snap2[addr]:
        changed = True
        print(f"  HR {addr:5d}: {snap1[addr]:6d} -> {snap2[addr]:6d}")

if not changed:
    print("  No changes detected")

print("\n========== ALL NON-ZERO VALUES (Snapshot 2) ==========")
for addr in sorted(snap2.keys()):
    if snap2[addr] != 0:
        val = snap2[addr]
        hi = (val >> 8) & 0xFF
        lo = val & 0xFF
        ascii_str = ""
        if 32 <= hi < 127 and 32 <= lo < 127:
            ascii_str = f'  "{chr(hi)}{chr(lo)}"'
        print(f"  HR {addr:5d}: {val:6d}  (0x{val:04X}){ascii_str}")

client.close()
