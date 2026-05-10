"""
Probe coils (FC01) and discrete inputs (FC02) on the Logik 26-S controller
to discover start/stop control and running feedback signals.
"""
from pymodbus.client import ModbusTcpClient
import time

GATEWAY_IP = '10.1.1.180'
GATEWAY_PORT = 502
SLAVE_ID = 1

client = ModbusTcpClient(GATEWAY_IP, port=GATEWAY_PORT, timeout=3)
client.connect()

if not client.connected:
    print("FAILED to connect to gateway!")
    exit(1)

print(f"Connected to {GATEWAY_IP}:{GATEWAY_PORT}")
print("=" * 60)

# --- FC01: Read Coils (output coils) ---
print("\n=== COILS (FC01) - addresses 0-255 ===")
found_coils = []
for start in range(0, 256, 16):
    try:
        result = client.read_coils(start, count=16, device_id=SLAVE_ID)
        if not result.isError():
            for i, val in enumerate(result.bits[:16]):
                addr = start + i
                if val:
                    found_coils.append(addr)
                    print(f"  Coil {addr:4d} = ON")
        else:
            print(f"  Coils {start}-{start+15}: error - {result}")
    except Exception as e:
        print(f"  Coils {start}-{start+15}: exception - {e}")
    time.sleep(0.05)

if not found_coils:
    print("  No active coils found in 0-255")

# --- FC02: Read Discrete Inputs ---
print("\n=== DISCRETE INPUTS (FC02) - addresses 0-255 ===")
found_inputs = []
for start in range(0, 256, 16):
    try:
        result = client.read_discrete_inputs(start, count=16, device_id=SLAVE_ID)
        if not result.isError():
            for i, val in enumerate(result.bits[:16]):
                addr = start + i
                if val:
                    found_inputs.append(addr)
                    print(f"  Input {addr:4d} = ON")
        else:
            print(f"  Inputs {start}-{start+15}: error - {result}")
    except Exception as e:
        print(f"  Inputs {start}-{start+15}: exception - {e}")
    time.sleep(0.05)

if not found_inputs:
    print("  No active discrete inputs found in 0-255")

# --- Also try FC05: write single coil to test if writable ---
# Don't actually write anything - just report what we found
print("\n" + "=" * 60)
print(f"SUMMARY: {len(found_coils)} active coils, {len(found_inputs)} active inputs")
if found_coils:
    print(f"  Active coils: {found_coils}")
if found_inputs:
    print(f"  Active inputs: {found_inputs}")

# --- Try reading coils in higher ranges (some controllers use 1000+) ---
print("\n=== COILS (FC01) - addresses 1000-1100 ===")
for start in range(1000, 1100, 16):
    try:
        result = client.read_coils(start, count=16, device_id=SLAVE_ID)
        if not result.isError():
            for i, val in enumerate(result.bits[:16]):
                addr = start + i
                if val:
                    print(f"  Coil {addr:4d} = ON")
                    found_coils.append(addr)
    except Exception:
        pass
    time.sleep(0.05)

print("\n=== DISCRETE INPUTS (FC02) - addresses 1000-1100 ===")
for start in range(1000, 1100, 16):
    try:
        result = client.read_discrete_inputs(start, count=16, device_id=SLAVE_ID)
        if not result.isError():
            for i, val in enumerate(result.bits[:16]):
                addr = start + i
                if val:
                    print(f"  Input {addr:4d} = ON")
                    found_inputs.append(addr)
    except Exception:
        pass
    time.sleep(0.05)

print("\nFINAL: " + str(len(found_coils)) + " coils, " + str(len(found_inputs)) + " inputs total")
client.close()
