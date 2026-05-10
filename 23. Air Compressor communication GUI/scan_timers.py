"""Quick scan of timer registers and search for maintenance counter registers."""
from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
if not client.connect():
    print("FAILED TO CONNECT")
    exit(1)

print("=== TIMER REGISTERS (HR 1800-1950) ===")
for start in range(1800, 1960, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, v in enumerate(result.registers):
                addr = start + i
                if v != 0:
                    hi = (v >> 8) & 0xFF
                    lo = v & 0xFF
                    print(f"  HR {addr}: {v:6d} (0x{v:04X})  hi={hi:3d} lo={lo:3d}")
        time.sleep(0.02)
    except Exception as e:
        print(f"  Error at HR {start}: {e}")

print("\n=== SEARCHING FOR MAINTENANCE COUNTER VALUES ===")
print("Looking for values near 612 (CAF/CSF remaining) and negative values (COF/C-- overdue)...")

# Search extended config (HR 1540-1680)
print("\n--- HR 1540-1680 ---")
for start in range(1540, 1680, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, v in enumerate(result.registers):
                addr = start + i
                signed = v if v < 32768 else v - 65536
                if v != 0:
                    print(f"  HR {addr}: {v:6d} (signed={signed:6d}) (0x{v:04X})")
        time.sleep(0.02)
    except Exception as e:
        print(f"  Error at HR {start}: {e}")

# Live data block - full scan
print("\n--- HR 4100-4260 (all non-zero) ---")
for start in range(4100, 4260, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, v in enumerate(result.registers):
                addr = start + i
                signed = v if v < 32768 else v - 65536
                if v != 0:
                    hi = (v >> 8) & 0xFF
                    lo = v & 0xFF
                    print(f"  HR {addr}: {v:6d} (signed={signed:6d}) (0x{v:04X}) hi={hi:3d} lo={lo:3d}")
        time.sleep(0.02)
    except Exception as e:
        print(f"  Error at HR {start}: {e}")

# Check info block for working hours (32-bit?)
print("\n--- HR 0-20 (info block) ---")
try:
    result = client.read_holding_registers(0, count=20, device_id=1)
    if not result.isError():
        for i, v in enumerate(result.registers):
            signed = v if v < 32768 else v - 65536
            hi = (v >> 8) & 0xFF
            lo = v & 0xFF
            print(f"  HR {i}: {v:6d} (signed={signed:6d}) (0x{v:04X}) hi={hi:3d} lo={lo:3d}")
except Exception as e:
    print(f"  Error: {e}")

# Check areas around known config for counter registers
# Maybe counters are right after SET values (HR 1316-1330?)
print("\n--- HR 1312-1350 (maintenance area detail) ---")
try:
    result = client.read_holding_registers(1312, count=40, device_id=1)
    if not result.isError():
        for i, v in enumerate(result.registers):
            addr = 1312 + i
            signed = v if v < 32768 else v - 65536
            print(f"  HR {addr}: {v:6d} (signed={signed:6d}) (0x{v:04X})")
except Exception as e:
    print(f"  Error: {e}")

# Maybe counters are in a separate block - try HR 1680-1800
print("\n--- HR 1680-1800 ---")
for start in range(1680, 1800, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, v in enumerate(result.registers):
                addr = start + i
                signed = v if v < 32768 else v - 65536
                if v != 0:
                    print(f"  HR {addr}: {v:6d} (signed={signed:6d}) (0x{v:04X})")
        time.sleep(0.02)
    except Exception as e:
        print(f"  Error at HR {start}: {e}")

# Try HR 2000-2310
print("\n--- HR 2000-2310 ---")
for start in range(2000, 2310, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, v in enumerate(result.registers):
                addr = start + i
                signed = v if v < 32768 else v - 65536
                if v != 0:
                    print(f"  HR {addr}: {v:6d} (signed={signed:6d}) (0x{v:04X})")
        time.sleep(0.02)
    except Exception as e:
        print(f"  Error at HR {start}: {e}")

client.close()
print("\n=== SCAN COMPLETE ===")
