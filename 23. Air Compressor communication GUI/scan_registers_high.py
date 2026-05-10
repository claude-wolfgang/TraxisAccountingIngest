from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
connected = client.connect()
print(f"Connected: {connected}")

if not connected:
    exit(1)

# Scan holding registers 1000-5000
print("========== HOLDING REGISTERS (FC03) 1000-5000 ==========")
for start in range(1000, 5000, 10):
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
                        # Also show signed interpretation
                        signed = val if val < 32768 else val - 65536
                        extra = f"  signed={signed}" if signed < 0 else ""
                        print(f"  HR {addr:5d}: {val:6d}  (0x{val:04X}){ascii_str}{extra}")
    except:
        pass
    time.sleep(0.05)

# Also try some very high ranges common in some controllers
for range_start, range_end in [(8000, 9000), (9000, 10000), (30000, 30200), (40000, 40200)]:
    print(f"\n--- Checking HR {range_start}-{range_end} ---")
    for start in range(range_start, range_end, 10):
        try:
            result = client.read_holding_registers(start, count=10, device_id=1)
            if not result.isError():
                has_data = any(v != 0 for v in result.registers)
                if has_data:
                    for i, val in enumerate(result.registers):
                        addr = start + i
                        if val != 0:
                            print(f"  HR {addr:5d}: {val:6d}  (0x{val:04X})")
        except:
            pass
        time.sleep(0.05)

client.close()
print("\nScan complete.")
