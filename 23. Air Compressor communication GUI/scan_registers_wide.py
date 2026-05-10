from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
connected = client.connect()
print(f"Connected: {connected}")

if not connected:
    print("Could not connect.")
    exit(1)

# Scan holding registers (FC03) 0-999
print("\n========== HOLDING REGISTERS (FC03) 0-999 ==========")
for start in range(0, 1000, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            has_data = any(v != 0 for v in result.registers)
            if has_data:
                for i, val in enumerate(result.registers):
                    addr = start + i
                    if val != 0:
                        hi = (val >> 8) & 0xFF
                        lo = val & 0xFF
                        ascii_str = ""
                        if 32 <= hi < 127 and 32 <= lo < 127:
                            ascii_str = f'  "{chr(hi)}{chr(lo)}"'
                        print(f"  HR {addr:4d}: {val:6d}  (0x{val:04X}){ascii_str}")
    except:
        pass
    time.sleep(0.05)

# Also try coils (FC01) 0-199
print("\n========== COILS (FC01) 0-199 ==========")
for start in range(0, 200, 20):
    try:
        result = client.read_coils(start, count=20, device_id=1)
        if not result.isError():
            has_data = any(v != 0 for v in result.bits[:20])
            if has_data:
                for i, val in enumerate(result.bits[:20]):
                    addr = start + i
                    if val:
                        print(f"  Coil {addr:4d}: {val}")
    except:
        pass
    time.sleep(0.05)

# Also try discrete inputs (FC02) 0-199
print("\n========== DISCRETE INPUTS (FC02) 0-199 ==========")
for start in range(0, 200, 20):
    try:
        result = client.read_discrete_inputs(start, count=20, device_id=1)
        if not result.isError():
            has_data = any(v != 0 for v in result.bits[:20])
            if has_data:
                for i, val in enumerate(result.bits[:20]):
                    addr = start + i
                    if val:
                        print(f"  DI {addr:4d}: {val}")
    except:
        pass
    time.sleep(0.05)

client.close()
print("\nScan complete.")
