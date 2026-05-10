"""
Deep dump of all live-data registers and nearby areas
to find a command/control register for start/stop.
"""
from pymodbus.client import ModbusTcpClient
import time

GATEWAY_IP = '10.1.1.180'
GATEWAY_PORT = 502
SLAVE_ID = 1

client = ModbusTcpClient(GATEWAY_IP, port=GATEWAY_PORT, timeout=3)
client.connect()
if not client.connected:
    print("FAILED to connect!")
    exit(1)

print(f"Connected to {GATEWAY_IP}:{GATEWAY_PORT}")

def dump_range(label, start, count):
    """Read and print all registers in a range."""
    print(f"\n{'='*60}")
    print(f"{label}: HR {start}-{start+count-1}")
    print(f"{'='*60}")
    for addr in range(start, start + count, 10):
        n = min(10, start + count - addr)
        try:
            result = client.read_holding_registers(addr, count=n, device_id=SLAVE_ID)
            if not result.isError():
                for i, val in enumerate(result.registers):
                    r = addr + i
                    hi = (val >> 8) & 0xFF
                    lo = val & 0xFF
                    flag = ""
                    if r == 4241: flag = " <-- PRESSURE"
                    elif r == 4243: flag = " <-- TEMPERATURE"
                    elif r == 4244: flag = " <-- AUX (loading indicator)"
                    elif 0 < val <= 10: flag = " <-- SMALL VALUE"
                    elif val == 0: flag = ""
                    print(f"  HR {r:5d} = {val:6d}  (0x{val:04X})  hi={hi:3d} lo={lo:3d}{flag}")
            else:
                print(f"  HR {addr}-{addr+n-1}: error - {result}")
        except Exception as e:
            print(f"  HR {addr}-{addr+n-1}: exception - {e}")
        time.sleep(0.03)

# Full dump of live data area
dump_range("LIVE BLOCK 1 (sensors/status)", 4100, 60)
dump_range("LIVE BLOCK 2 (pressure/temp)", 4230, 60)

# Check areas just before/after live blocks
dump_range("PRE-LIVE BLOCK (possible control area)", 4080, 20)
dump_range("POST-LIVE BLOCK 2", 4290, 30)

# Check commonly-used control register addresses
dump_range("Low control area (HR 1-20)", 1, 20)
dump_range("HR 4096 area (common Modbus base)", 4096, 10)

# Dump the full config block more carefully
dump_range("Config block detail (HR 1280-1320)", 1280, 40)

# Check near the timer area for a "timer enable" register
dump_range("Pre-timer area (HR 1780-1800)", 1780, 20)

# Maintenance counter area (the 1540 hits from previous scan)
dump_range("Maintenance counters? (HR 1530-1560)", 1530, 30)

# Read registers 1670-1680 (includes the mystery HR 1678=3)
dump_range("Load hours area (HR 1660-1690)", 1660, 30)

client.close()
print("\nDone.")
