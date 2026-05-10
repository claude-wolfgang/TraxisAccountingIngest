from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient('10.1.1.180', port=502, timeout=5)
connected = client.connect()
print(f"Connected: {connected}")

if not connected:
    print("Could not connect.")
    exit(1)

# Scan holding registers (FC03) in blocks of 10
print("\n========== HOLDING REGISTERS (FC03) ==========")
for start in range(0, 200, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            has_data = any(v != 0 for v in result.registers)
            if has_data:
                for i, val in enumerate(result.registers):
                    addr = start + i
                    # Try to decode as ASCII pair
                    hi = (val >> 8) & 0xFF
                    lo = val & 0xFF
                    ascii_str = ""
                    if 32 <= hi < 127 and 32 <= lo < 127:
                        ascii_str = f'  "{chr(hi)}{chr(lo)}"'
                    print(f"  HR {addr:4d}: {val:6d}  (0x{val:04X}){ascii_str}")
    except Exception as e:
        pass

# Scan input registers (FC04) in blocks of 10
print("\n========== INPUT REGISTERS (FC04) ==========")
for start in range(0, 200, 10):
    try:
        result = client.read_input_registers(start, count=10, device_id=1)
        if not result.isError():
            has_data = any(v != 0 for v in result.registers)
            if has_data:
                for i, val in enumerate(result.registers):
                    addr = start + i
                    hi = (val >> 8) & 0xFF
                    lo = val & 0xFF
                    ascii_str = ""
                    if 32 <= hi < 127 and 32 <= lo < 127:
                        ascii_str = f'  "{chr(hi)}{chr(lo)}"'
                    print(f"  IR {addr:4d}: {val:6d}  (0x{val:04X}){ascii_str}")
    except Exception as e:
        pass

client.close()
print("\nScan complete.")
