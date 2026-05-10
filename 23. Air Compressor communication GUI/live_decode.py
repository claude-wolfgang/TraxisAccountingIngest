"""
Live data decoder - reads compressor registers and displays decoded values.
Compare these with the compressor LCD to verify register assignments.
"""
from pymodbus.client import ModbusTcpClient
import time, datetime

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
connected = client.connect()
print(f"Connected: {connected}")
if not connected:
    exit(1)

def read_range(start, count):
    """Read a block of holding registers, return dict {addr: value}."""
    vals = {}
    try:
        result = client.read_holding_registers(start, count=count, device_id=1)
        if not result.isError():
            for i, v in enumerate(result.registers):
                vals[start + i] = v
    except Exception as e:
        print(f"  Error reading HR {start}-{start+count}: {e}")
    return vals

print("\nReading compressor data...\n")

# Read live data block
live = {}
for start in [4100, 4230]:
    live.update(read_range(start, 30))

# Read config block for reference
config = {}
for start in range(1280, 1370, 10):
    config.update(read_range(start, 10))
    time.sleep(0.05)

# Read info block
info = read_range(0, 20)

# === DECODE INFO ===
print("=" * 60)
print("INFO BLOCK")
print("=" * 60)
serial = ""
for addr in range(0, 5):
    val = info.get(addr, 0)
    hi = (val >> 8) & 0xFF
    lo = val & 0xFF
    if 32 <= hi < 127:
        serial += chr(hi)
    if 32 <= lo < 127:
        serial += chr(lo)
print(f"  Serial Number: {serial}")
print(f"  HR 8 (working hours?): {info.get(8, 'N/A')}")
print(f"  HR 9 (load hours?):    {info.get(9, 'N/A')}")

# === DECODE CONFIG ===
print(f"\n{'=' * 60}")
print("CONFIGURATION (HR 1280+)")
print("=" * 60)
print(f"  PW1 (Level 1 password): {config.get(1284, 'N/A')}")
print(f"  PW2 (Level 2 password): {config.get(1285, 'N/A')}")

# Pressure setpoints - try bar*10 interpretation
print(f"\n  --- Pressure Setpoints (bar * 10) ---")
for addr, label in [
    (1288, "HR1288"), (1289, "HR1289"), (1290, "HR1290"),
    (1291, "HR1291"), (1292, "HR1292"), (1293, "HR1293"),
    (1296, "HR1296"), (1340, "HR1340"),
]:
    val = config.get(addr, 0)
    bar = val / 10.0
    psi = bar * 14.504
    print(f"  {label}: {val:5d} = {bar:.1f} bar = {psi:.0f} PSI")

print(f"\n  --- Temperature Setpoints (C) ---")
print(f"  WT1 High T alarm (HR1297):   {config.get(1297, 'N/A')} C")
print(f"  WT2 High T warning (HR1320): {config.get(1320, 'N/A')} C")
print(f"  HR1298:                       {config.get(1298, 'N/A')} C")

print(f"\n  --- Timers ---")
print(f"  C02 Starts/hour (HR1303): {config.get(1303, 'N/A')}")
print(f"  Wt1 Star (HR1306):        {config.get(1306, 'N/A')} sec")
print(f"  Wt2 Star/Delta (HR1304):  {config.get(1304, 'N/A')} ms")
print(f"  Wt3 Delta (HR1305):       {config.get(1305, 'N/A')} sec")
print(f"  Wt5 Safety (HR1307):      {config.get(1307, 'N/A')} sec")

print(f"\n  --- Maintenance ---")
print(f"  CAF Air filter:  {config.get(1312, 'N/A')} hr interval, {config.get(1313, 'N/A')} hr remaining")
print(f"  COF Oil filter:  {config.get(1314, 'N/A')} hr interval, {config.get(1315, 'N/A')} hr remaining")
print(f"  CSF Sep filter:  {config.get(1316, 'N/A')} hr interval, {config.get(1317, 'N/A')} hr remaining(?)")

print(f"\n  --- Drive/Motor ---")
print(f"  Motor Power (HR1355):   {config.get(1355, 0)/10:.1f} kW")
print(f"  Motor Voltage (HR1356): {config.get(1356, 'N/A')} V")
print(f"  Motor Freq (HR1357):    {config.get(1357, 'N/A')} Hz")
print(f"  Motor Current (HR1358): {config.get(1358, 0)/10:.1f} A")
print(f"  Motor Speed (HR1359):   {config.get(1359, 'N/A')} RPM")

# === DECODE LIVE DATA ===
print(f"\n{'=' * 60}")
print("LIVE DATA (HR 4100+)")
print("=" * 60)
print(f"  Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Key changing registers with multiple interpretations
for addr, label in [(4241, "HR4241 (Pressure?)"), (4243, "HR4243 (Temperature?)"), (4244, "HR4244 (Aux?)")]:
    val = live.get(addr, 0)
    hi = (val >> 8) & 0xFF
    lo = val & 0xFF
    bar_hi = hi / 10.0
    psi_hi = bar_hi * 14.504
    print(f"\n  {label}:")
    print(f"    Raw: {val} (0x{val:04X})")
    print(f"    Hi byte: {hi}  Lo byte: {lo}")
    print(f"    If hi=bar*10:  {bar_hi:.1f} bar = {psi_hi:.0f} PSI")
    print(f"    If hi=PSI:     {hi} PSI = {hi/14.504:.1f} bar")
    print(f"    If hi=tempC:   {hi} C = {hi*9/5+32:.0f} F")
    print(f"    If full=bar*10: {val/10:.1f} bar")

# Also show HR 4100 area
print(f"\n  --- Status Area ---")
print(f"  HR4100: {live.get(4100, 'N/A')} (state code?)")

# Decode ASCII from 4101-4103
state_str = ""
for addr in [4101, 4102, 4103]:
    val = live.get(addr, 0)
    hi = (val >> 8) & 0xFF
    lo = val & 0xFF
    if 32 <= hi < 127:
        state_str += chr(hi)
    if 32 <= lo < 127:
        state_str += chr(lo)
print(f"  HR4101-4103 ASCII: \"{state_str}\"")
print(f"  HR4104: {live.get(4104, 'N/A')}")
print(f"  HR4106: {live.get(4106, 'N/A')} (0x{live.get(4106, 0):04X})")

# Show all non-zero live registers
print(f"\n  --- All Non-Zero Live Registers ---")
for addr in sorted(live.keys()):
    val = live.get(addr, 0)
    if val != 0:
        hi = (val >> 8) & 0xFF
        lo = val & 0xFF
        print(f"    HR{addr}: {val:6d} (0x{val:04X})  hi={hi:3d} lo={lo:3d}")

client.close()
print(f"\n{'=' * 60}")
print("DONE - Compare values above with compressor LCD!")
print("=" * 60)
