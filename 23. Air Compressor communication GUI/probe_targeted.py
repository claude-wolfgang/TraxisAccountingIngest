"""Probe the exact registers compressor_web.py reads — see what controller actually returns."""
from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
if not client.connect():
    print("CONNECT FAILED")
    exit(1)

# Targeted reads at addresses compressor_web.py expects
targets = [
    ("Group 2 Active Alarms",    512,  4),
    ("Group 2 Unacked Alarms",   516,  4),
    ("Group 4 Live Data",       1024, 14),   # state, temp, pressure, status_flags
    ("Group 6 Counters",        1536, 18),   # total/load minutes + maint
    ("Group 6 Load%/Starts",    1552,  2),
    ("Group 8 System Time/RTC", 2048,  4),
    ("Group 7 Timer1 (read)",   1800, 30),
    ("Group 7 Timer2 (read)",   1920, 42),
]

def show(label, addr, count, result):
    print(f"\n--- {label} (HR {addr}, count={count}) ---")
    if result is None:
        print("  EXCEPTION RAISED")
        return
    if result.isError():
        print(f"  MODBUS ERROR: {result}")
        return
    print(f"  {len(result.registers)} regs returned")
    for i, val in enumerate(result.registers):
        marker = "" if val == 0 else "  <-- NON-ZERO"
        if i < 8 or val != 0:
            print(f"    HR {addr+i:5d}: {val:6d}  (0x{val:04X}){marker}")
    nonzero = sum(1 for v in result.registers if v != 0)
    print(f"  Summary: {nonzero}/{len(result.registers)} non-zero")

# Take two snapshots to see what changes
print("=" * 60)
print("SNAPSHOT 1")
print("=" * 60)
snap1 = {}
for label, addr, count in targets:
    try:
        r = client.read_holding_registers(addr, count=count, device_id=1)
        snap1[label] = r
        show(label, addr, count, r)
    except Exception as e:
        print(f"\n--- {label} ---  EXCEPTION: {e}")
        snap1[label] = None
    time.sleep(0.1)

print("\nWaiting 5 seconds for live values to change...\n")
time.sleep(5)

print("=" * 60)
print("SNAPSHOT 2 — CHANGED VALUES ONLY")
print("=" * 60)
for label, addr, count in targets:
    try:
        r2 = client.read_holding_registers(addr, count=count, device_id=1)
        r1 = snap1.get(label)
        if r1 is None or r1.isError() or r2.isError():
            continue
        changes = [(addr+i, r1.registers[i], r2.registers[i])
                   for i in range(len(r2.registers))
                   if r1.registers[i] != r2.registers[i]]
        if changes:
            print(f"\n{label}:")
            for a, v1, v2 in changes:
                print(f"  HR {a:5d}: {v1:6d} -> {v2:6d}")
    except Exception as e:
        print(f"\n{label} EXCEPTION: {e}")
    time.sleep(0.1)

client.close()
print("\nDone.")
