"""Live monitor of suspected pressure/temperature registers."""
from pymodbus.client import ModbusTcpClient
import time, datetime

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
connected = client.connect()
print(f"Connected: {connected}")
if not connected:
    exit(1)

print("Monitoring live registers (Ctrl+C to stop)...\n")
print(f"{'Time':>12}  {'HR4241':>8} {'Hi4241':>7}  {'HR4243':>8} {'Hi4243':>7}  {'HR4244':>8} {'Hi4244':>7}  {'HR4100':>8} {'Hi4100':>7}")
print("-" * 95)

try:
    while True:
        now = datetime.datetime.now().strftime("%H:%M:%S")
        vals = {}
        for start in [4100, 4240]:
            try:
                result = client.read_holding_registers(start, count=10, device_id=1)
                if not result.isError():
                    for i, v in enumerate(result.registers):
                        vals[start + i] = v
            except:
                pass

        def hi(addr):
            return (vals.get(addr, 0) >> 8) & 0xFF

        def lo(addr):
            return vals.get(addr, 0) & 0xFF

        print(f"{now:>12}  "
              f"{vals.get(4241, 0):>8} {hi(4241):>5}hi  "
              f"{vals.get(4243, 0):>8} {hi(4243):>5}hi  "
              f"{vals.get(4244, 0):>8} {hi(4244):>5}hi  "
              f"{vals.get(4100, 0):>8} {hi(4100):>5}hi")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    client.close()
