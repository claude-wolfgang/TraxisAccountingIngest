"""
Scan unexplored Modbus register ranges on the Logik 26-S to find
a remote start/stop control register.

Known registers are skipped. We're looking for:
- Small values (0/1/2) that might be command/mode registers
- Registers in typical "control" address ranges
"""
from pymodbus.client import ModbusTcpClient
import time

GATEWAY_IP = '10.1.1.180'
GATEWAY_PORT = 502
SLAVE_ID = 1

# Ranges to scan (start, end) - skipping known areas
SCAN_RANGES = [
    (20, 100),       # Low addresses (HR 0-20 confirmed dead)
    (100, 300),      # Before config block
    (300, 1280),     # Large gap before config
    (1370, 1410),    # Between config blocks
    (1500, 1680),    # Between config and load hours
    (1680, 1800),    # Between load hours and timer1
    (1830, 1920),    # Between timer1 and timer2
    (1962, 2100),    # After timer2
    (2100, 2500),    # Unexplored mid-range
    (2500, 3000),    # Unexplored mid-range
    (3000, 3500),    # Unexplored
    (3500, 4000),    # Unexplored
    (4000, 4100),    # Just before live data
    (4260, 4400),    # After live data
    (4400, 4600),    # Extended live area
]

client = ModbusTcpClient(GATEWAY_IP, port=GATEWAY_PORT, timeout=3)
client.connect()

if not client.connected:
    print("FAILED to connect!")
    exit(1)

print(f"Connected to {GATEWAY_IP}:{GATEWAY_PORT}")
print("Scanning for control/command registers...")
print("=" * 70)

found = []
errors = 0
CHUNK = 10

for range_start, range_end in SCAN_RANGES:
    print(f"\n--- Scanning HR {range_start}-{range_end} ---")
    for addr in range(range_start, range_end, CHUNK):
        count = min(CHUNK, range_end - addr)
        try:
            result = client.read_holding_registers(addr, count=count, device_id=SLAVE_ID)
            if not result.isError():
                for i, val in enumerate(result.registers):
                    reg_addr = addr + i
                    if val != 0:  # Only show non-zero values
                        hi = (val >> 8) & 0xFF
                        lo = val & 0xFF
                        found.append((reg_addr, val, hi, lo))
                        # Flag potential control registers (small values 1-10)
                        flag = " <-- POSSIBLE CONTROL?" if 0 < val <= 10 else ""
                        print(f"  HR {reg_addr:5d} = {val:6d}  (0x{val:04X})  hi={hi:3d} lo={lo:3d}{flag}")
            else:
                # Don't spam for illegal address errors
                errors += 1
        except Exception as e:
            errors += 1
        time.sleep(0.03)

print("\n" + "=" * 70)
print(f"SUMMARY: {len(found)} non-zero registers found, {errors} read errors")
print("\nAll non-zero registers:")
for addr, val, hi, lo in found:
    flag = ""
    if 0 < val <= 10:
        flag = " *** POSSIBLE CONTROL/MODE"
    elif val in [0xFF, 0xFFFF, 0x00FF, 0xFF00]:
        flag = " (max/flag value)"
    print(f"  HR {addr:5d} = {val:6d}  (0x{val:04X}){flag}")

client.close()
print("\nDone.")
