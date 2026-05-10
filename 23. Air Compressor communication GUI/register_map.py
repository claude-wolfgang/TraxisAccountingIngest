"""
Systematic register mapping by reading all config registers and matching
against known parameter defaults from the L26-S manual.
"""
from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('10.1.1.180', port=502, timeout=3)
connected = client.connect()
print(f"Connected: {connected}")
if not connected:
    exit(1)

# Read the full config block HR 1280-1500
print("\n===== FULL CONFIG BLOCK HR 1280-1500 =====")
all_regs = {}
for start in range(1280, 1500, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, val in enumerate(result.registers):
                all_regs[start + i] = val
    except:
        pass
    time.sleep(0.05)

# Print all registers with annotations for known matches
# Known defaults from manual:
known_defaults = {
    # Passwords
    'PW1': 0x0022,  # 22 decimal stored as hex
    'PW2': 0x4444,  # 4444
    'PW3a': 0x6666, # first part of 666666
    'PW3b': 0x0066, # second part
    # Compressor Setup C01-C23
    'C02 Starts/hour': 6,
    'C03 Wt4 fixed': 1,  # YES
    'C04 Control phases': 1,  # YES
    'C05 Safety': 0,  # NO
    'C06 Low voltage': 1,  # YES
    'C07 Multiunit': 0,
    'C07.1 Timer M/S': 100,
    'C07.2 Timer slave': 5,
    'C08 Compressor Nr': 1,
    'C10 Flow': 1000,
    # Pressures (stored as bar * 10)
    'WP1 Top range': 150,  # 15.0 bar
    'WP2 High press alarm': 110,  # 11.0 bar default
    'WP3 Stop press': 88,  # 8.8 bar default
    'WP4 Start press': 73,  # 7.3 bar default
    'WP5 Slave start': 65,  # 6.5 bar default
    'WP6 Offset': 0,
    'AP1 Sep filter alarm': 17,  # 1.7 bar
    'AP2 Sep filter warn': 12,  # 1.2 bar
    'AP3 Offset': 0,
    'AP4 Max aux press': 20,  # 2.0 bar
    # Temperatures (°C)
    'WT1 High T alarm': 105,
    'WT2 High T warning': 100,
    'WT3 Start fan': 85,
    'WT4 dT fan stop': 10,
    'WT5 Low T alarm': 0,
    'WT6 Offset': 0,
    'WT7 PID Enable': 0,
    # Timers
    'Wt1 Star': 5,
    'Wt2 Star/Delta': 35,
    'Wt3 Delta': 2,
    'Wt4 Unload': 3,
    'Wt5 Safety': 30,
    'Wt6 RL6 On': 2,
    'Wt7 RL6 Off': 3,
    # Inverter RS485 defaults
    'DR0 Drive Model': 0,
    'DR1 Min freq': 30,
    'DR2 Max freq': 85,
    'DR3 Accel': 400,  # 40.0s * 10
    'DR4 Decel': 40,   # 4.0s * 10
    'DR5 PID prop': 440, # 4.40 * 100
    'DR6 PID int': 200,  # 2.00s * 100
    'DA0 Motor Power': 576, # 57.6 * 10
    'DA1 Motor Voltage': 415,
    'DA2 Motor Freq': 87,
    'DA3 Motor Current': 1060, # 106.0A * 10
    'DA4 Motor Speed': 2575,
    'DA5 Current Limit': 1000, # 100.0% * 10
    'DA6 PID Diff': 0,
    'DA7 Reset Energy': 0,
    'DA8 Jog Ramp': 200, # 20.0s * 10
    'DA9 PID int mult': 100, # 1.00 * 100
    # Maintenance timers
    'CAF Air filter': 2000,
    'COF Oil filter': 2000,
    'CSF Sep filter': 4000,
    'C-- Oil change': 8000,
    'C--h Check comp': 500,
    'C-BL Bearings': 29999,
}

# Print all non-zero registers with any matching defaults
for addr in sorted(all_regs.keys()):
    val = all_regs[addr]
    if val == 0:
        continue
    # Check if value matches any known default
    matches = [name for name, default in known_defaults.items() if default == val]
    match_str = f"  *** MATCHES: {', '.join(matches)}" if matches else ""

    hi = (val >> 8) & 0xFF
    lo = val & 0xFF
    ascii_str = ""
    if 32 <= hi < 127 and 32 <= lo < 127:
        ascii_str = f' "{chr(hi)}{chr(lo)}"'

    print(f"  HR {addr:5d}: {val:6d}  (0x{val:04X}){ascii_str}{match_str}")

# Also read live data block
print("\n===== LIVE DATA HR 4100-4260 =====")
for start in range(4100, 4260, 10):
    try:
        result = client.read_holding_registers(start, count=10, device_id=1)
        if not result.isError():
            for i, val in enumerate(result.registers):
                addr = start + i
                if val != 0:
                    hi = (val >> 8) & 0xFF
                    lo = val & 0xFF
                    ascii_str = ""
                    if 32 <= hi < 127 and 32 <= lo < 127:
                        ascii_str = f' "{chr(hi)}{chr(lo)}"'
                    print(f"  HR {addr:5d}: {val:6d}  (0x{val:04X})  hi={hi:3d} lo={lo:3d}{ascii_str}")
    except:
        pass
    time.sleep(0.05)

# Read INFO block HR 0-20
print("\n===== INFO HR 0-20 =====")
try:
    result = client.read_holding_registers(0, count=20, device_id=1)
    if not result.isError():
        for i, val in enumerate(result.registers):
            if val != 0:
                hi = (val >> 8) & 0xFF
                lo = val & 0xFF
                ascii_str = ""
                if 32 <= hi < 127 and 32 <= lo < 127:
                    ascii_str = f' "{chr(hi)}{chr(lo)}"'
                print(f"  HR {i:5d}: {val:6d}  (0x{val:04X}){ascii_str}")
except:
    pass

client.close()
print("\nDone.")
