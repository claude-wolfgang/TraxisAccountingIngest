"""
Air Compressor Monitoring GUI v2
EMAX Rotary Screw 20HP — Logik 26-S controller via DR302 Modbus TCP gateway.
Register addresses from official LOGIK26S MODBUS PROCEDURE document.
"""
from flask import Flask, jsonify, render_template_string, request
from pymodbus.client import ModbusTcpClient
import threading
import time
import datetime
import json
import os

# === CONFIG ===
GATEWAY_IP = '10.1.1.180'
GATEWAY_PORT = 502
SLAVE_ID = 1
POLL_INTERVAL = 3  # seconds
WEB_PORT = 8085
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CABINET_FILE = os.path.join(DATA_DIR, 'cabinet_filter.json')

# =============================================================================
# REGISTER ADDRESSES — Official LOGIK26S MODBUS PROCEDURE document
# Hex addresses from document are shown in comments; decimal used in code.
# =============================================================================

# --- Group 2: Alarms (0x0200) ---
REG_ACTIVE_ALARMS = 512       # 0x0200  byte[8] bitmapped, 4 regs
REG_UNACKED_ALARMS = 516      # 0x0204  byte[8] bitmapped, 4 regs

# --- Group 4: Controller State & Measures (0x0400) ---
REG_INTERNAL_STATE = 1024     # 0x0400  enum 0-11
REG_DISPLAY_STATE = 1025      # 0x0401  enum 0-14
REG_BLOCKING_ALARM = 1026     # 0x0402  alarm code or 0
REG_RELAY_OUTPUT = 1027       # 0x0403  bitmapped
REG_DIGITAL_INPUT = 1028      # 0x0404  bitmapped
REG_TEMPERATURE = 1029        # 0x0405  Celsius * 10
REG_PRESSURE = 1030           # 0x0406  bar * 10
REG_AUX_PRESSURE = 1031       # 0x0407  bar * 10
REG_STATUS_FLAGS = 1034       # 0x040A  bitmapped status indicators
REG_FIELDBUS_CMD = 1036       # 0x040C  WRITE-ONLY command register

# --- Fieldbus command bits for HR 1036 ---
CMD_START = 0x0001
CMD_STOP = 0x0002
CMD_ALARM_RESET = 0x0004
CMD_START_BYPASS_TIMER = 0x0008
CMD_STOP_BYPASS_TIMER = 0x0010
CMD_ACK_RESET_ALL = 0x0020
CMD_RESET_CAF = 0x0100        # Reset air filter maintenance counter
CMD_RESET_COF = 0x0200        # Reset oil filter maintenance counter
CMD_RESET_CSF = 0x0400        # Reset separator filter maintenance counter
CMD_RESET_OIL = 0x0800        # Reset oil maintenance counter
CMD_RESET_CHK = 0x1000        # Reset compressor check counter
CMD_RESET_BRG = 0x2000        # Reset bearing lubricate counter

# --- Status flag bits for HR 1034 ---
FLAG_COMP_ACTIVE = 0x0001
FLAG_COMP_MASTER = 0x0002
FLAG_ON_BY_TIMER = 0x0004
FLAG_TIMER_BYPASSED = 0x0008
FLAG_FAN_OUT = 0x0020
FLAG_DRAIN_OUT = 0x0040
FLAG_ALARM_OUT = 0x0080
FLAG_REMOTE_START = 0x0100    # 0=STOP
FLAG_MOTOR_STARTING = 0x0200
FLAG_COMP_IS_ACTIVE = 0x0400
FLAG_MOTOR_RUNNING = 0x0800

# --- Group 5: Parameters (0x0500) ---
REG_CONFIG_SWITCHES = 1280    # 0x0500  bitmapped config
REG_WP2_ALARM = 1290          # 0x050A  High pressure alarm (bar*10)
REG_WP3_STOP = 1291           # 0x050B  Stop pressure (bar*10)
REG_WP4_START = 1292          # 0x050C  Start pressure (bar*10)
REG_WT1_ALARM = 1296          # 0x0510  High temp alarm (C)  [CORRECTED: was 1297]
REG_WT2_WARN = 1297           # 0x0511  High temp warning (C) [CORRECTED: was 1320]
REG_CAF_SET = 1312            # 0x0520  Air filter SET interval (hrs)
REG_COF_SET = 1313            # 0x0521  Oil filter SET interval (hrs)
REG_CSF_SET = 1314            # 0x0522  Separator filter SET interval (hrs)
REG_OIL_SET = 1315            # 0x0523  Oil change SET interval (hrs)
REG_CHK_SET = 1316            # 0x0524  Compressor check SET interval (hrs)
REG_BRG_SET = 1317            # 0x0525  Bearing lubricate SET interval (hrs)

# --- Group 6: Counters (0x0600) ---
REG_TOTAL_MINUTES = 1536      # 0x0600  long (2 regs), total compressor minutes
REG_LOAD_MINUTES = 1538       # 0x0602  long (2 regs), load minutes
REG_MAINT_COUNTERS = 1540     # 0x0604  long[6] (12 regs), elapsed minutes since service
#   1540-41=CAF, 1542-43=COF, 1544-45=CSF, 1546-47=C--, 1548-49=C-h, 1550-51=C-BL
REG_LOAD_PERCENT = 1552       # 0x0610  load % in last 100hrs (100%=6000)
REG_STARTS_HOUR = 1553        # 0x0611  starts in last hour

# --- Group 7: Weekly timer (keeping empirically-verified addresses) ---
# Official doc says 0x0700=1792 but our writes at 1800/1920 are confirmed working.
TIMER1_BASE = 1800
TIMER2_BASE = 1920
REGS_PER_DAY = 6
DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

BAR10_TO_PSI = 14.504 / 10  # Convert bar*10 register value to PSI

# =============================================================================
# LOOKUP TABLES
# =============================================================================

DISPLAY_STATES = {
    0: 'OFF',
    1: 'PRESS TOO HIGH',
    2: 'REMOTE STOP',
    3: 'STOP BY TIMER',
    4: 'IDLE STOPPING',
    5: 'IDLE STOP (REMOTE)',
    6: 'IDLE STOP (TIMER)',
    7: 'STANDBY',
    8: 'WAITING TO START',
    9: 'MOTOR STARTING',
    10: 'IDLE RUNNING',
    11: 'LOAD RUNNING',
    12: 'SOFT BLOCK',
    13: 'BLOCKED',
    14: 'FACTORY TEST',
}

ALARM_CODES = {
    1: 'EMERGENCY', 2: 'MOTOR OVERHEAT', 3: 'FAN OVERHEAT',
    4: 'PHASE MISSING', 5: 'PHASE SEQ WRONG', 7: 'DOOR OPEN',
    9: 'DRIVE FAULT', 11: 'HIGH WORK PRESS', 12: 'SCREW TEMP FAULT',
    13: 'HIGH SCREW TEMP', 14: 'LOW SCREW TEMP', 15: 'SEP FILTER TRANSD',
    18: 'BLACK OUT', 20: 'PTC MOTOR', 21: 'INPUT COMMON MISSING',
    22: 'INPUT7', 25: 'SEPARATOR FILTER', 26: 'WORK PRESS FAULT',
    27: 'AUX PRESS FAULT', 28: 'LOW VOLTAGE', 29: 'SECURITY',
    30: 'SCREW TEMP WARN', 32: 'MAINT C-H BLOCK', 33: 'FIELDBUS ERR',
    35: 'EEPROM FAULT', 36: 'AIR FILTER', 37: 'MULTIUNIT FAULT',
    38: 'SEP FILTER WARN', 39: 'LOW VOLTAGE WARN', 40: 'HIGH VOLTAGE',
    41: 'TIMEKEEPER FAULT', 42: 'RS232 FAULT', 43: 'DST ADJUSTED',
    44: 'BEARING HIGH TEMP', 47: 'TOO MANY STARTS', 48: 'RESTART MANUAL',
    49: 'RESTART AUTO', 50: 'MAINT CAF', 51: 'MAINT COF',
    52: 'MAINT CSF', 53: 'MAINT C--', 54: 'MAINT C-H',
    55: 'MAINT BL', 60: 'DRIVE FAULT', 61: 'DRIVE WARNING',
    62: 'DRIVE NO COMM',
}

# Map filter names to fieldbus reset command bits
FILTER_RESET_CMDS = {
    'caf': CMD_RESET_CAF,
    'cof': CMD_RESET_COF,
    'csf': CMD_RESET_CSF,
    'oil': CMD_RESET_OIL,
    'chk': CMD_RESET_CHK,
    'brg': CMD_RESET_BRG,
}

FILTER_LABELS = {
    'caf': 'Air Filter (CAF)',
    'cof': 'Oil Filter (COF)',
    'csf': 'Separator Filter (CSF)',
    'oil': 'Oil Change (C--)',
    'chk': 'Compressor Check (C-h)',
    'brg': 'Bearing Lubricate (C-BL)',
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def encode_time(hour, minute):
    """Encode hour:minute to Logik timer register value."""
    return (minute << 8) | hour


def decode_time(value):
    """Decode Logik timer register value to (hour, minute)."""
    return value & 0xFF, (value >> 8) & 0xFF


def read_long32(regs, offset=0):
    """Read 32-bit unsigned long from two consecutive registers (big-endian)."""
    if offset + 1 >= len(regs):
        return 0
    return (regs[offset] << 16) | regs[offset + 1]


def signed16(val):
    """Interpret a 16-bit register value as signed."""
    return val - 65536 if val > 32767 else val


def decode_alarms(regs):
    """Decode 4 alarm registers (HR 512-515) into list of active alarm codes.
    Bit mapping: bit N of the 64-bit field = alarm N (bit 0 unused)."""
    active = []
    if len(regs) < 4:
        return active
    for reg_idx, reg_val in enumerate(regs):
        hi = (reg_val >> 8) & 0xFF
        lo = reg_val & 0xFF
        for bit in range(8):
            alarm_num = reg_idx * 16 + bit
            if alarm_num > 0 and (hi & (1 << bit)):
                active.append(alarm_num)
        for bit in range(8):
            alarm_num = reg_idx * 16 + 8 + bit
            if lo & (1 << bit):
                active.append(alarm_num)
    return active


def decode_schedule_block(regs, base, count=7):
    """Decode a timer block into a list of day schedules."""
    schedule = []
    for day in range(count):
        offset = day * REGS_PER_DAY
        if offset + REGS_PER_DAY > len(regs):
            schedule.append({'on': None, 'off': None, 'enabled': False})
            continue
        slots = regs[offset:offset + REGS_PER_DAY]
        on_time = None
        off_time = None
        for s in range(3):
            on_val = slots[s * 2]
            off_val = slots[s * 2 + 1]
            if on_val != off_val and on_val != 0:
                on_h, on_m = decode_time(on_val)
                off_h, off_m = decode_time(off_val)
                if 0 <= on_h <= 23 and 0 <= on_m <= 59:
                    on_time = f"{on_h:02d}:{on_m:02d}"
                    off_time = f"{off_h:02d}:{off_m:02d}"
                    break
        schedule.append({
            'on': on_time,
            'off': off_time,
            'enabled': on_time is not None,
        })
    return schedule


# === CABINET FILTER (manual tracking - not in PLC) ===
def load_cabinet_filter():
    if os.path.exists(CABINET_FILE):
        with open(CABINET_FILE, 'r') as f:
            return json.load(f)
    return {
        'last_changed': None,
        'interval_hours': 2730,
        'notes': 'Not tracked by PLC. 6-month cycle based on 5AM-8PM operation.'
    }


def save_cabinet_filter(data):
    with open(CABINET_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# =============================================================================
# SHARED STATE
# =============================================================================
data_lock = threading.Lock()
modbus_client_lock = threading.Lock()
modbus_client = None

current_data = {
    'pressure_psi': 0,
    'pressure_bar': 0.0,
    'temperature_c': 0.0,
    'temperature_f': 32,
    'aux_psi': 0,
    'aux_bar': 0.0,
    'wp2_alarm_psi': 0,
    'wp3_stop_psi': 0,
    'wp4_start_psi': 0,
    'wt1_alarm': 105,
    'wt2_warn': 100,
    'display_state': 0,
    'display_state_text': 'UNKNOWN',
    'internal_state': 0,
    'blocking_alarm': 0,
    'blocking_alarm_text': '',
    'active_alarms': [],
    'active_alarm_texts': [],
    'status_flags': 0,
    'motor_running': False,
    'compressor_active': False,
    'on_by_timer': False,
    'timer_bypassed': False,
    'relay_output': 0,
    'digital_input': 0,
    'total_hours': 0,
    'load_hours': 0,
    'load_percent': 0.0,
    'starts_hour': 0,
    # Maintenance: set intervals and remaining hours
    'caf_set': 0, 'caf_remain': 0,
    'cof_set': 0, 'cof_remain': 0,
    'csf_set': 0, 'csf_remain': 0,
    'oil_set': 0, 'oil_remain': 0,
    'chk_set': 0, 'chk_remain': 0,
    'brg_set': 0, 'brg_remain': 0,
    'connected': False,
    'last_update': '',
    'status': 'UNKNOWN',
    'schedule': [],
}


def read_regs(client, start, count):
    """Read holding registers, return list of values or empty list on error."""
    try:
        with modbus_client_lock:
            result = client.read_holding_registers(start, count=count, device_id=SLAVE_ID)
        if not result.isError():
            return list(result.registers)
    except Exception:
        pass
    return []


def write_cmd(client, register, value):
    """Write a single register. Returns True on success."""
    try:
        with modbus_client_lock:
            result = client.write_register(register, value, device_id=SLAVE_ID)
        return not result.isError()
    except Exception:
        return False


# =============================================================================
# BACKGROUND POLLER
# =============================================================================

def poll_compressor():
    """Background thread: poll compressor registers using official addresses."""
    global modbus_client
    client = ModbusTcpClient(GATEWAY_IP, port=GATEWAY_PORT, timeout=3)
    with modbus_client_lock:
        modbus_client = client
    while True:
        try:
            if not client.connected:
                client.connect()
            if not client.connected:
                with data_lock:
                    current_data['connected'] = False
                    current_data['status'] = 'OFFLINE'
                time.sleep(POLL_INTERVAL)
                continue

            # --- Read Group 2: Active alarms (HR 512-515, 4 regs) ---
            alarm_regs = read_regs(client, REG_ACTIVE_ALARMS, 4)
            time.sleep(0.03)

            # --- Read Group 4: State & sensors (HR 1024-1035, 12 regs) ---
            state_regs = read_regs(client, REG_INTERNAL_STATE, 12)
            time.sleep(0.03)

            # --- Read Group 5: Pressure config (HR 1290-1292, 3 regs) ---
            press_cfg = read_regs(client, REG_WP2_ALARM, 3)
            time.sleep(0.03)

            # --- Read Group 5: Temp config (HR 1296-1297, 2 regs) ---
            temp_cfg = read_regs(client, REG_WT1_ALARM, 2)
            time.sleep(0.03)

            # --- Read Group 5: Maintenance SET values (HR 1312-1317, 6 regs) ---
            maint_set = read_regs(client, REG_CAF_SET, 6)
            time.sleep(0.03)

            # --- Read Group 6: Counters (HR 1536-1553, 18 regs) ---
            counters = read_regs(client, REG_TOTAL_MINUTES, 18)
            time.sleep(0.03)

            # --- Read timer schedule (keep existing working approach) ---
            t1_regs = read_regs(client, TIMER1_BASE, 30)
            t2_regs = read_regs(client, TIMER2_BASE, 42)
            sched1 = decode_schedule_block(t1_regs, TIMER1_BASE, count=5) if t1_regs else []
            sched2 = decode_schedule_block(t2_regs, TIMER2_BASE) if t2_regs else []

            schedule = []
            for i in range(7):
                s1 = sched1[i] if i < len(sched1) else {'enabled': False}
                s2 = sched2[i] if i < len(sched2) else {'enabled': False}
                if s1.get('enabled'):
                    schedule.append({**s1, 'day': DAY_NAMES[i], 'source': 'T1'})
                elif s2.get('enabled'):
                    schedule.append({**s2, 'day': DAY_NAMES[i], 'source': 'T2'})
                else:
                    schedule.append({'day': DAY_NAMES[i], 'on': None, 'off': None,
                                     'enabled': False, 'source': None})

            # === Decode live data from Group 4 ===
            if len(state_regs) >= 12:
                internal_state = state_regs[0]   # HR 1024
                display_state = state_regs[1]    # HR 1025
                blocking_alarm = state_regs[2]   # HR 1026
                relay_output = state_regs[3]     # HR 1027
                digital_input = state_regs[4]    # HR 1028
                temp_c10 = signed16(state_regs[5])  # HR 1029, Celsius*10
                pressure_bar10 = state_regs[6]   # HR 1030, bar*10
                aux_bar10 = state_regs[7]        # HR 1031, bar*10
                status_flags = state_regs[10]    # HR 1034
            else:
                internal_state = display_state = blocking_alarm = 0
                relay_output = digital_input = 0
                temp_c10 = pressure_bar10 = aux_bar10 = 0
                status_flags = 0

            temp_c = temp_c10 / 10.0
            temp_f = round(temp_c * 9 / 5 + 32)
            pressure_psi = round(pressure_bar10 * BAR10_TO_PSI)
            aux_psi = round(aux_bar10 * BAR10_TO_PSI)

            # Pressure config
            wp2_psi = round(press_cfg[0] * BAR10_TO_PSI) if len(press_cfg) >= 1 else 0
            wp3_psi = round(press_cfg[1] * BAR10_TO_PSI) if len(press_cfg) >= 2 else 0
            wp4_psi = round(press_cfg[2] * BAR10_TO_PSI) if len(press_cfg) >= 3 else 0

            # Temp config
            wt1_alarm = temp_cfg[0] if len(temp_cfg) >= 1 else 105
            wt2_warn = temp_cfg[1] if len(temp_cfg) >= 2 else 100

            # Status text
            display_text = DISPLAY_STATES.get(display_state, f'STATE {display_state}')
            blocking_text = ALARM_CODES.get(blocking_alarm, '') if blocking_alarm else ''

            # Active alarms
            active_alarm_nums = decode_alarms(alarm_regs) if alarm_regs else []
            active_alarm_texts = [
                f"A{n:02d}-{ALARM_CODES.get(n, '?')}" for n in active_alarm_nums
            ]

            # Status flags
            motor_running = bool(status_flags & FLAG_MOTOR_RUNNING)
            compressor_active = bool(status_flags & FLAG_COMP_IS_ACTIVE)
            on_by_timer = bool(status_flags & FLAG_ON_BY_TIMER)
            timer_bypassed = bool(status_flags & FLAG_TIMER_BYPASSED)

            # === Decode Group 6: Counters ===
            if len(counters) >= 18:
                total_minutes = read_long32(counters, 0)   # HR 1536-37
                load_minutes = read_long32(counters, 2)    # HR 1538-39
                # Maintenance elapsed minutes (long[6] at offset 4)
                caf_elapsed_min = read_long32(counters, 4)   # HR 1540-41
                cof_elapsed_min = read_long32(counters, 6)   # HR 1542-43
                csf_elapsed_min = read_long32(counters, 8)   # HR 1544-45
                oil_elapsed_min = read_long32(counters, 10)  # HR 1546-47
                chk_elapsed_min = read_long32(counters, 12)  # HR 1548-49
                brg_elapsed_min = read_long32(counters, 14)  # HR 1550-51
                load_pct_raw = counters[16]                  # HR 1552
                starts_hour = counters[17]                   # HR 1553
            else:
                total_minutes = load_minutes = 0
                caf_elapsed_min = cof_elapsed_min = csf_elapsed_min = 0
                oil_elapsed_min = chk_elapsed_min = brg_elapsed_min = 0
                load_pct_raw = starts_hour = 0

            total_hours = round(total_minutes / 60)
            load_hours = round(load_minutes / 60)
            load_percent = round(load_pct_raw / 60, 1)  # 6000 = 100%

            # Maintenance remaining hours
            caf_set = maint_set[0] if len(maint_set) >= 1 else 0
            cof_set = maint_set[1] if len(maint_set) >= 2 else 0
            csf_set = maint_set[2] if len(maint_set) >= 3 else 0
            oil_set = maint_set[3] if len(maint_set) >= 4 else 0
            chk_set = maint_set[4] if len(maint_set) >= 5 else 0
            brg_set = maint_set[5] if len(maint_set) >= 6 else 0

            caf_remain = caf_set - round(caf_elapsed_min / 60)
            cof_remain = cof_set - round(cof_elapsed_min / 60)
            csf_remain = csf_set - round(csf_elapsed_min / 60)
            oil_remain = oil_set - round(oil_elapsed_min / 60)
            chk_remain = chk_set - round(chk_elapsed_min / 60)
            brg_remain = brg_set - round(brg_elapsed_min / 60)

            with data_lock:
                current_data['pressure_psi'] = pressure_psi
                current_data['pressure_bar'] = round(pressure_bar10 / 10, 1)
                current_data['temperature_c'] = round(temp_c, 1)
                current_data['temperature_f'] = temp_f
                current_data['aux_psi'] = aux_psi
                current_data['aux_bar'] = round(aux_bar10 / 10, 1)
                current_data['wp2_alarm_psi'] = wp2_psi
                current_data['wp3_stop_psi'] = wp3_psi
                current_data['wp4_start_psi'] = wp4_psi
                current_data['wt1_alarm'] = wt1_alarm
                current_data['wt2_warn'] = wt2_warn
                current_data['display_state'] = display_state
                current_data['display_state_text'] = display_text
                current_data['internal_state'] = internal_state
                current_data['blocking_alarm'] = blocking_alarm
                current_data['blocking_alarm_text'] = blocking_text
                current_data['active_alarms'] = active_alarm_nums
                current_data['active_alarm_texts'] = active_alarm_texts
                current_data['status_flags'] = status_flags
                current_data['motor_running'] = motor_running
                current_data['compressor_active'] = compressor_active
                current_data['on_by_timer'] = on_by_timer
                current_data['timer_bypassed'] = timer_bypassed
                current_data['relay_output'] = relay_output
                current_data['digital_input'] = digital_input
                current_data['total_hours'] = total_hours
                current_data['load_hours'] = load_hours
                current_data['load_percent'] = load_percent
                current_data['starts_hour'] = starts_hour
                current_data['caf_set'] = caf_set
                current_data['caf_remain'] = caf_remain
                current_data['cof_set'] = cof_set
                current_data['cof_remain'] = cof_remain
                current_data['csf_set'] = csf_set
                current_data['csf_remain'] = csf_remain
                current_data['oil_set'] = oil_set
                current_data['oil_remain'] = oil_remain
                current_data['chk_set'] = chk_set
                current_data['chk_remain'] = chk_remain
                current_data['brg_set'] = brg_set
                current_data['brg_remain'] = brg_remain
                current_data['connected'] = True
                current_data['status'] = display_text
                current_data['last_update'] = datetime.datetime.now().strftime('%H:%M:%S')
                current_data['schedule'] = schedule

        except Exception as e:
            with data_lock:
                current_data['connected'] = False
                current_data['status'] = f'ERROR: {e}'

        time.sleep(POLL_INTERVAL)


# =============================================================================
# FLASK APP
# =============================================================================
app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html>
<head>
<title>Air Compressor Monitor</title>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: Consolas, 'Courier New', monospace;
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 20px;
  }
  h1 { text-align: center; color: #e0e0e0; margin-bottom: 5px; font-size: 22px; }
  .subtitle { text-align: center; color: #888; font-size: 12px; margin-bottom: 20px; }
  .status-bar {
    display: flex; justify-content: space-between; align-items: center;
    background: #16213e; padding: 8px 15px; border-radius: 6px;
    margin-bottom: 10px; font-size: 13px;
  }
  .status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 8px; }
  .dot-green { background: #4ecca3; }
  .dot-red { background: #e74c3c; }
  .dot-yellow { background: #fdd835; }
  .alarm-banner {
    display: none; background: #b71c1c; color: #fff; padding: 8px 15px;
    border-radius: 6px; margin-bottom: 10px; font-size: 13px;
    align-items: center; justify-content: space-between;
  }
  .alarm-banner.active { display: flex; }
  .alarm-banner .alarm-list { flex: 1; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }
  .panel { background: #16213e; border-radius: 8px; padding: 15px; }
  .panel h2 { font-size: 14px; color: #aaa; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  .bar-container { margin-bottom: 10px; }
  .bar-label { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 3px; }
  .bar-value { font-weight: bold; color: #fff; }
  .bar-track { background: #0f3460; border-radius: 4px; height: 22px; position: relative; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; min-width: 2px; }
  .bar-marker { position: absolute; top: 0; height: 100%; width: 2px; background: rgba(255,255,255,0.5); }
  .fill-blue { background: linear-gradient(90deg, #1a73e8, #4fc3f7); }
  .fill-green { background: linear-gradient(90deg, #2e7d32, #4ecca3); }
  .fill-orange { background: linear-gradient(90deg, #e65100, #ff9800); }
  .fill-red { background: linear-gradient(90deg, #b71c1c, #e74c3c); }
  .fill-yellow { background: linear-gradient(90deg, #f57f17, #fdd835); }
  .fill-teal { background: linear-gradient(90deg, #00695c, #26a69a); }
  .fill-purple { background: linear-gradient(90deg, #4a148c, #9c27b0); }
  .big-value { font-size: 42px; font-weight: bold; text-align: center; margin: 5px 0; }
  .big-unit { font-size: 16px; color: #888; }
  .info-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; border-bottom: 1px solid #0f3460; }
  .info-row:last-child { border-bottom: none; }
  .full-width { grid-column: 1 / -1; }
  .btn {
    background: #0f3460; color: #e0e0e0; border: 1px solid #1a73e8;
    border-radius: 4px; padding: 3px 10px; cursor: pointer;
    font-family: inherit; font-size: 11px;
  }
  .btn:hover { background: #1a73e8; }
  .btn-danger { border-color: #e74c3c; }
  .btn-danger:hover { background: #e74c3c; }
  .btn-warn { border-color: #ff9800; color: #ff9800; }
  .btn-warn:hover { background: #ff9800; color: #fff; }
  .btn-start {
    background: #1b5e20; border: 1px solid #4caf50; color: #fff;
    border-radius: 4px; padding: 5px 16px; cursor: pointer;
    font-family: inherit; font-size: 12px; font-weight: bold;
  }
  .btn-start:hover { background: #2e7d32; }
  .btn-stop {
    background: #b71c1c; border: 1px solid #e74c3c; color: #fff;
    border-radius: 4px; padding: 5px 16px; cursor: pointer;
    font-family: inherit; font-size: 12px; font-weight: bold;
  }
  .btn-stop:hover { background: #c62828; }
  .btn-start:disabled, .btn-stop:disabled { opacity: 0.5; cursor: not-allowed; }
  .pending-status { color: #fdd835; animation: blink 1s infinite; }
  @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  .maint-overdue { color: #e74c3c; font-weight: bold; }
  .maint-warn { color: #ff9800; font-weight: bold; }
  .maint-ok { color: #4ecca3; }
  .note { font-size: 11px; color: #666; font-style: italic; }
  .reset-row { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; }
  .sched-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-bottom: 15px; }
  .sched-day { padding: 8px 4px; border-radius: 4px; text-align: center; font-size: 12px; }
  .sched-day.active { background: #0f3460; }
  .sched-day.inactive { background: #111; opacity: 0.5; }
  .sched-day .day-name { font-weight: bold; margin-bottom: 4px; }
  .sched-day .day-time { font-size: 11px; color: #4ecca3; }
  .sched-day.inactive .day-time { color: #555; }
  .sched-form {
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    padding: 10px; background: #0f3460; border-radius: 6px;
  }
  .sched-form label { font-size: 12px; color: #aaa; }
  .sched-form select, .sched-form input[type="time"] {
    background: #1a1a2e; color: #e0e0e0; border: 1px solid #1a73e8;
    border-radius: 3px; padding: 4px 6px; font-family: inherit; font-size: 12px;
  }
  .sched-form input[type="checkbox"] { margin-right: 4px; }
  .modal-overlay {
    display: none; position: fixed; top: 0; left: 0;
    width: 100%; height: 100%; background: rgba(0,0,0,0.7);
    z-index: 100; justify-content: center; align-items: center;
  }
  .modal-overlay.active { display: flex; }
  .modal {
    background: #16213e; border: 1px solid #1a73e8; border-radius: 8px;
    padding: 25px; max-width: 420px; text-align: center;
  }
  .modal h3 { margin-bottom: 15px; color: #e74c3c; }
  .modal p { margin-bottom: 20px; font-size: 14px; }
  .modal .btn { margin: 0 8px; padding: 8px 20px; font-size: 13px; }
  .flag-row { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 6px; }
  .flag-item { font-size: 11px; padding: 2px 8px; border-radius: 3px; }
  .flag-on { background: #1b5e20; color: #4ecca3; }
  .flag-off { background: #333; color: #666; }
</style>
</head>
<body>

<h1>EMAX Air Compressor</h1>
<p class="subtitle">20HP Rotary Screw &mdash; Logik 26-S &mdash; 10.1.1.180:502</p>

<div class="status-bar">
  <div>
    <span class="status-dot" id="conn-dot"></span>
    <span id="conn-text">Connecting...</span>
  </div>
  <div>State: <strong id="comp-status">---</strong></div>
  <div>
    <button class="btn-start" id="btn-start" onclick="confirmStart()">&#9654; START</button>
    <button class="btn-stop" id="btn-stop" onclick="confirmStop()">&#9632; STOP</button>
  </div>
  <div>Updated: <span id="last-update">---</span></div>
</div>

<!-- ALARM BANNER -->
<div class="alarm-banner" id="alarm-banner">
  <span class="alarm-list" id="alarm-text">No alarms</span>
  <button class="btn btn-warn" onclick="confirmAlarmReset()">RESET ALARMS</button>
</div>

<div class="grid">
  <!-- PRESSURE -->
  <div class="panel">
    <h2>Working Pressure</h2>
    <div class="big-value" id="pressure-big">--- <span class="big-unit">PSI</span></div>
    <div class="bar-container">
      <div class="bar-track" style="height:28px;">
        <div class="bar-fill fill-blue" id="pressure-bar" style="width:0%"></div>
        <div class="bar-marker" id="press-start-marker" title="Start pressure"></div>
        <div class="bar-marker" id="press-stop-marker" title="Stop pressure" style="background:rgba(255,200,0,0.7)"></div>
        <div class="bar-marker" id="press-alarm-marker" title="Alarm" style="background:rgba(255,0,0,0.7)"></div>
      </div>
    </div>
    <div class="bar-label" style="font-size:11px; color:#888;">
      <span>0</span>
      <span>Start / Stop / Alarm</span>
      <span>175 PSI</span>
    </div>
  </div>

  <!-- TEMPERATURE -->
  <div class="panel">
    <h2>Air End Temperature</h2>
    <div class="big-value" id="temp-big">--- <span class="big-unit">&deg;F</span></div>
    <div class="bar-container">
      <div class="bar-track" style="height:28px;">
        <div class="bar-fill fill-green" id="temp-bar" style="width:0%"></div>
        <div class="bar-marker" id="temp-warn-marker" title="Warning" style="background:rgba(255,200,0,0.7)"></div>
        <div class="bar-marker" id="temp-alarm-marker" title="Alarm" style="background:rgba(255,0,0,0.7)"></div>
      </div>
    </div>
    <div class="bar-label" style="font-size:11px; color:#888;">
      <span>32&deg;F</span>
      <span>Warning / Alarm</span>
      <span>260&deg;F</span>
    </div>
  </div>

  <!-- SCHEDULE -->
  <div class="panel full-width">
    <h2>Weekly Schedule</h2>
    <div class="sched-grid" id="schedule-display">
      <div class="sched-day inactive"><div class="day-name">---</div></div>
    </div>
    <div id="timer-mode-row" style="margin:10px 0; padding:8px 12px; border-radius:6px; font-size:14px; display:flex; align-items:center; gap:12px;">
      <span id="timer-mode-text" style="font-weight:600;">Timer mode: ---</span>
      <button class="btn" id="btn-resume-schedule" onclick="confirmResumeSchedule()" style="display:none; background:#0f3460; color:#4fc3f7; border:1px solid #4fc3f7; padding:4px 12px; font-size:13px; cursor:pointer; border-radius:4px;">&#8635; Resume Schedule</button>
    </div>
    <div class="sched-form">
      <div>
        <label>Day</label><br>
        <select id="sched-day">
          <option value="0">Monday</option><option value="1">Tuesday</option>
          <option value="2">Wednesday</option><option value="3">Thursday</option>
          <option value="4">Friday</option><option value="5">Saturday</option>
          <option value="6">Sunday</option><option value="weekdays">Mon-Fri</option>
          <option value="all">Every Day</option>
        </select>
      </div>
      <div><label>ON Time</label><br><input type="time" id="sched-on" value="05:00"></div>
      <div><label>OFF Time</label><br><input type="time" id="sched-off" value="20:00"></div>
      <div><label><input type="checkbox" id="sched-enable" checked> Enabled</label></div>
      <div><button class="btn" onclick="confirmSchedule()">Apply</button></div>
    </div>
  </div>

  <!-- MAINTENANCE -->
  <div class="panel full-width">
    <h2>Maintenance Status</h2>
    <div id="maint-section"></div>

    <!-- Cabinet filter (manual, not PLC) -->
    <div class="bar-container" style="margin-top:15px; border-top:1px solid #0f3460; padding-top:10px;">
      <div class="bar-label">
        <span>Cabinet Intake Filter(s)</span>
        <span class="bar-value" id="cab-val">---</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill fill-purple" id="cab-bar" style="width:0%"></div>
      </div>
      <div class="reset-row">
        <span class="note">Not tracked by PLC &mdash; manual 6-month timer.</span>
        <button class="btn btn-danger" onclick="confirmReset('cabinet','Cabinet Filter')">Reset Timer</button>
      </div>
    </div>
  </div>

  <!-- CONFIGURATION & STATS -->
  <div class="panel full-width">
    <h2>Configuration &amp; Statistics</h2>
    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px;">
      <div>
        <div class="info-row"><span>Pressure Alarm (WP2)</span><span id="wp2-val">---</span></div>
        <div class="info-row"><span>Stop Pressure (WP3)</span><span id="wp3-val">---</span></div>
        <div class="info-row"><span>Start Pressure (WP4)</span><span id="wp4-val">---</span></div>
        <div class="info-row"><span>Temp Alarm (WT1)</span><span id="wt1-val">---</span></div>
        <div class="info-row"><span>Temp Warning (WT2)</span><span id="wt2-val">---</span></div>
      </div>
      <div>
        <div class="info-row"><span>Total Hours</span><span id="total-hrs">---</span></div>
        <div class="info-row"><span>Load Hours</span><span id="load-hrs">---</span></div>
        <div class="info-row"><span>Load %</span><span id="load-pct">---</span></div>
        <div class="info-row"><span>Starts/Hour</span><span id="starts-hr">---</span></div>
        <div class="info-row"><span>Aux Pressure</span><span id="aux-val">---</span></div>
      </div>
      <div>
        <div class="info-row"><span>Motor</span><span>20 HP / 208-230V</span></div>
        <div class="info-row"><span>Serial</span><span>EC00002447</span></div>
        <div class="info-row"><span>Software</span><span>L26SD V1.87</span></div>
        <div class="info-row"><span>Controller State</span><span id="int-state">---</span></div>
        <div id="status-flags-row" class="flag-row"></div>
      </div>
    </div>
  </div>
</div>

<!-- CONFIRM MODAL -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <h3 id="modal-title">Confirm</h3>
    <p id="modal-msg">---</p>
    <button class="btn" onclick="closeModal()">Cancel</button>
    <button class="btn btn-danger" id="modal-confirm">Confirm</button>
  </div>
</div>

<script>
const PRESS_MAX = 175;
let commandPending = null;
let commandTimeout = null;

function confirmStart() {
  document.getElementById('modal-title').textContent = 'Confirm Start';
  document.getElementById('modal-msg').textContent =
    'Start the compressor? This sends a fieldbus START command directly to the controller.';
  document.getElementById('modal').classList.add('active');
  document.getElementById('modal-confirm').onclick = function() {
    closeModal(); sendCommand('start');
  };
}

function confirmStop() {
  document.getElementById('modal-title').textContent = 'Confirm Stop';
  document.getElementById('modal-msg').textContent =
    'Stop the compressor? This sends a fieldbus STOP command directly to the controller.';
  document.getElementById('modal').classList.add('active');
  document.getElementById('modal-confirm').onclick = function() {
    closeModal(); sendCommand('stop');
  };
}

function confirmAlarmReset() {
  document.getElementById('modal-title').textContent = 'Confirm Alarm Reset';
  document.getElementById('modal-msg').textContent =
    'Acknowledge and reset all alarms? The alarm cause must be resolved first.';
  document.getElementById('modal').classList.add('active');
  document.getElementById('modal-confirm').onclick = function() {
    closeModal();
    fetch('/api/compressor/alarm_reset', {method:'POST', headers:{'Content-Type':'application/json'}})
    .then(r => r.json()).then(d => { if (d.error) alert('Error: '+d.error); })
    .catch(e => alert('Failed: '+e));
  };
}

function confirmResumeSchedule() {
  document.getElementById('modal-title').textContent = 'Resume Schedule';
  document.getElementById('modal-msg').textContent =
    'Return compressor to weekly timer control? The compressor will follow its programmed schedule.';
  document.getElementById('modal').classList.add('active');
  document.getElementById('modal-confirm').onclick = function() {
    closeModal();
    fetch('/api/compressor/resume_schedule', {method:'POST', headers:{'Content-Type':'application/json'}})
    .then(r => r.json()).then(d => { if (d.error) alert('Error: '+d.error); })
    .catch(e => alert('Failed: '+e));
  };
}

function sendCommand(action) {
  const btnStart = document.getElementById('btn-start');
  const btnStop = document.getElementById('btn-stop');
  btnStart.disabled = true;
  btnStop.disabled = true;
  commandPending = action === 'start' ? 'starting' : 'stopping';
  document.getElementById('comp-status').innerHTML =
    '<span class="pending-status">' + commandPending.toUpperCase() + '...</span>';

  fetch('/api/compressor/' + action, {method:'POST', headers:{'Content-Type':'application/json'}})
  .then(r => r.json())
  .then(d => {
    if (d.error) {
      alert('Error: ' + d.error);
      commandPending = null; btnStart.disabled = false; btnStop.disabled = false;
      return;
    }
    if (commandTimeout) clearTimeout(commandTimeout);
    commandTimeout = setTimeout(function() {
      if (commandPending) {
        commandPending = null; btnStart.disabled = false; btnStop.disabled = false;
      }
    }, 30000);
  })
  .catch(e => {
    alert('Failed to send command: ' + e);
    commandPending = null; btnStart.disabled = false; btnStop.disabled = false;
  });
}

function confirmReset(filter, label) {
  document.getElementById('modal-title').textContent = 'Confirm Reset';
  document.getElementById('modal-msg').textContent =
    'Reset ' + label + ' maintenance counter? Only do this after performing the service.';
  document.getElementById('modal').classList.add('active');
  document.getElementById('modal-confirm').onclick = function() {
    fetch('/api/reset_filter', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({filter: filter})
    })
    .then(r => r.json())
    .then(d => { if (d.error) alert('Error: '+d.error); else alert(d.message); closeModal(); update(); })
    .catch(e => { alert('Failed: '+e); closeModal(); });
  };
}

function confirmSchedule() {
  const daySel = document.getElementById('sched-day').value;
  const onTime = document.getElementById('sched-on').value;
  const offTime = document.getElementById('sched-off').value;
  const enabled = document.getElementById('sched-enable').checked;
  let dayLabel;
  if (daySel === 'weekdays') dayLabel = 'Mon-Fri';
  else if (daySel === 'all') dayLabel = 'Every Day';
  else dayLabel = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][parseInt(daySel)];
  const action = enabled ? (onTime + ' - ' + offTime) : 'DISABLED';
  document.getElementById('modal-title').textContent = 'Confirm Schedule Change';
  document.getElementById('modal-msg').textContent =
    'Set ' + dayLabel + ' to ' + action + '? This writes to the compressor controller.';
  document.getElementById('modal').classList.add('active');
  document.getElementById('modal-confirm').onclick = function() {
    let days;
    if (daySel === 'weekdays') days = [0,1,2,3,4];
    else if (daySel === 'all') days = [0,1,2,3,4,5,6];
    else days = [parseInt(daySel)];
    const [onH, onM] = onTime.split(':').map(Number);
    const [offH, offM] = offTime.split(':').map(Number);
    fetch('/api/schedule', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({days:days, on_hour:onH, on_minute:onM, off_hour:offH, off_minute:offM, enabled:enabled})
    })
    .then(r => r.json())
    .then(d => { if (d.error) alert('Error: '+d.error); else alert(d.message); closeModal(); update(); })
    .catch(e => { alert('Failed: '+e); closeModal(); });
  };
}

function closeModal() { document.getElementById('modal').classList.remove('active'); }

function update() {
  fetch('/api/data')
    .then(r => r.json())
    .then(d => {
      // Connection
      const dot = document.getElementById('conn-dot');
      const txt = document.getElementById('conn-text');
      if (d.connected) { dot.className = 'status-dot dot-green'; txt.textContent = 'Connected'; }
      else { dot.className = 'status-dot dot-red'; txt.textContent = 'Disconnected'; }
      document.getElementById('last-update').textContent = d.last_update;

      // Command pending state - detect state change from controller
      if (commandPending === 'stopping' && (d.display_state === 0 || d.display_state === 3 || d.display_state === 7)) {
        commandPending = null;
        if (commandTimeout) clearTimeout(commandTimeout);
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-stop').disabled = false;
      } else if (commandPending === 'starting' && (d.display_state >= 9 && d.display_state <= 11)) {
        commandPending = null;
        if (commandTimeout) clearTimeout(commandTimeout);
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-stop').disabled = false;
      }
      if (commandPending) {
        document.getElementById('comp-status').innerHTML =
          '<span class="pending-status">' + commandPending.toUpperCase() + '...</span>';
      } else {
        const statusEl = document.getElementById('comp-status');
        statusEl.textContent = d.display_state_text;
        if (d.display_state === 11) statusEl.style.color = '#4ecca3';
        else if (d.display_state === 10) statusEl.style.color = '#4fc3f7';
        else if (d.display_state === 13) statusEl.style.color = '#e74c3c';
        else if (d.display_state === 0 || d.display_state === 3) statusEl.style.color = '#888';
        else statusEl.style.color = '#fdd835';
      }

      // Alarm banner
      const banner = document.getElementById('alarm-banner');
      if (d.active_alarm_texts && d.active_alarm_texts.length > 0) {
        banner.classList.add('active');
        document.getElementById('alarm-text').textContent = d.active_alarm_texts.join(' | ');
      } else {
        banner.classList.remove('active');
      }

      // Pressure
      const psi = d.pressure_psi;
      const psiPct = Math.min(100, (psi / PRESS_MAX) * 100);
      document.getElementById('pressure-big').innerHTML =
        psi + ' <span class="big-unit">PSI</span> <span style="font-size:16px;color:#888">(' + d.pressure_bar + ' bar)</span>';
      const pressBar = document.getElementById('pressure-bar');
      pressBar.style.width = psiPct + '%';
      if (psi >= d.wp2_alarm_psi && d.wp2_alarm_psi > 0) pressBar.className = 'bar-fill fill-red';
      else if (psi >= d.wp3_stop_psi && d.wp3_stop_psi > 0) pressBar.className = 'bar-fill fill-yellow';
      else pressBar.className = 'bar-fill fill-blue';
      if (d.wp4_start_psi > 0) document.getElementById('press-start-marker').style.left = ((d.wp4_start_psi/PRESS_MAX)*100)+'%';
      if (d.wp3_stop_psi > 0) document.getElementById('press-stop-marker').style.left = ((d.wp3_stop_psi/PRESS_MAX)*100)+'%';
      if (d.wp2_alarm_psi > 0) document.getElementById('press-alarm-marker').style.left = ((d.wp2_alarm_psi/PRESS_MAX)*100)+'%';

      // Temperature
      const tempF = d.temperature_f;
      const tempC = d.temperature_c;
      const tempPct = Math.min(100, ((tempF-32)/(260-32))*100);
      document.getElementById('temp-big').innerHTML =
        tempF+' <span class="big-unit">&deg;F</span> <span style="font-size:18px;color:#888">('+tempC+'&deg;C)</span>';
      const tempBar = document.getElementById('temp-bar');
      tempBar.style.width = tempPct + '%';
      const wt1F = d.wt1_alarm*9/5+32;
      const wt2F = d.wt2_warn*9/5+32;
      if (tempC >= d.wt1_alarm) tempBar.className = 'bar-fill fill-red';
      else if (tempC >= d.wt2_warn) tempBar.className = 'bar-fill fill-orange';
      else tempBar.className = 'bar-fill fill-green';
      if (d.wt2_warn > 0) document.getElementById('temp-warn-marker').style.left = ((wt2F-32)/(260-32)*100)+'%';
      if (d.wt1_alarm > 0) document.getElementById('temp-alarm-marker').style.left = ((wt1F-32)/(260-32)*100)+'%';

      // Schedule
      if (d.schedule && d.schedule.length === 7) {
        let html = '';
        d.schedule.forEach(function(entry) {
          const cls = entry.enabled ? 'active' : 'inactive';
          const timeStr = entry.enabled ? (entry.on + '<br>' + entry.off) : 'OFF';
          html += '<div class="sched-day '+cls+'"><div class="day-name">'+entry.day+'</div><div class="day-time">'+timeStr+'</div></div>';
        });
        document.getElementById('schedule-display').innerHTML = html;
      }

      // Timer mode indicator
      const modeEl = document.getElementById('timer-mode-text');
      const modeRow = document.getElementById('timer-mode-row');
      const resumeBtn = document.getElementById('btn-resume-schedule');
      if (d.on_by_timer) {
        modeEl.textContent = 'Timer mode: ON BY SCHEDULE';
        modeRow.style.background = 'rgba(78, 204, 163, 0.15)';
        modeEl.style.color = '#4ecca3';
        resumeBtn.style.display = 'none';
      } else if (d.timer_bypassed) {
        modeEl.textContent = 'Timer mode: BYPASSED (manual override)';
        modeRow.style.background = 'rgba(253, 216, 53, 0.15)';
        modeEl.style.color = '#fdd835';
        resumeBtn.style.display = 'inline-block';
      } else {
        modeEl.textContent = 'Timer mode: OFF';
        modeRow.style.background = 'rgba(136, 136, 136, 0.1)';
        modeEl.style.color = '#888';
        resumeBtn.style.display = 'none';
      }

      // Maintenance (dynamic from PLC counters)
      const maintItems = [
        {id:'caf', label:'Air Filter (CAF)', set:d.caf_set, remain:d.caf_remain},
        {id:'cof', label:'Oil Filter (COF)', set:d.cof_set, remain:d.cof_remain},
        {id:'csf', label:'Separator Filter (CSF)', set:d.csf_set, remain:d.csf_remain},
        {id:'oil', label:'Oil Change (C--)', set:d.oil_set, remain:d.oil_remain},
        {id:'chk', label:'Compressor Check (C-h)', set:d.chk_set, remain:d.chk_remain},
        {id:'brg', label:'Bearing Lubricate (C-BL)', set:d.brg_set, remain:d.brg_remain},
      ];
      let mHtml = '';
      maintItems.forEach(function(item) {
        if (item.set <= 0) return;
        const overdue = item.remain < 0;
        const pct = Math.min(100, Math.max(0, (item.remain / item.set) * 100));
        let valText, valClass, fillClass;
        if (overdue) {
          valText = Math.abs(item.remain) + ' hrs OVERDUE';
          valClass = 'maint-overdue';
          fillClass = 'fill-red';
        } else if (pct < 15) {
          valText = item.remain + ' hrs remaining';
          valClass = 'maint-warn';
          fillClass = 'fill-orange';
        } else {
          valText = item.remain + ' hrs remaining';
          valClass = 'maint-ok';
          fillClass = 'fill-teal';
        }
        mHtml += '<div class="bar-container">' +
          '<div class="bar-label"><span>' + item.label + ' &mdash; ' + item.set.toLocaleString() + ' hr interval</span>' +
          '<span class="bar-value ' + valClass + '">' + valText + '</span></div>' +
          '<div class="bar-track"><div class="bar-fill ' + fillClass + '" style="width:' + (overdue ? 100 : (100-pct)) + '%"></div></div>' +
          '<div class="reset-row"><span></span>' +
          '<button class="btn btn-danger" onclick="confirmReset(\'' + item.id + '\',\'' + item.label + '\')">Reset Counter</button>' +
          '</div></div>';
      });
      document.getElementById('maint-section').innerHTML = mHtml;

      // Cabinet filter (manual tracking)
      if (d.cabinet_remain !== undefined && d.cabinet_interval !== undefined) {
        const cabPct = d.cabinet_interval > 0 ?
          Math.min(100, Math.max(0, (d.cabinet_remain/d.cabinet_interval)*100)) : 0;
        let cabText = d.cabinet_remain + ' / ' + d.cabinet_interval + ' hrs';
        if (d.cabinet_last_changed) cabText += ' (changed: ' + d.cabinet_last_changed + ')';
        document.getElementById('cab-val').textContent = cabText;
        const cabBar = document.getElementById('cab-bar');
        cabBar.style.width = cabPct + '%';
        if (cabPct < 10) cabBar.className = 'bar-fill fill-red';
        else if (cabPct < 25) cabBar.className = 'bar-fill fill-orange';
        else cabBar.className = 'bar-fill fill-purple';
      }

      // Config values
      document.getElementById('wp2-val').textContent = d.wp2_alarm_psi + ' PSI';
      document.getElementById('wp3-val').textContent = d.wp3_stop_psi + ' PSI';
      document.getElementById('wp4-val').textContent = d.wp4_start_psi + ' PSI';
      document.getElementById('wt1-val').textContent = d.wt1_alarm+' C ('+Math.round(d.wt1_alarm*9/5+32)+' F)';
      document.getElementById('wt2-val').textContent = d.wt2_warn+' C ('+Math.round(d.wt2_warn*9/5+32)+' F)';

      // Statistics
      document.getElementById('total-hrs').textContent = d.total_hours.toLocaleString() + ' hrs';
      document.getElementById('load-hrs').textContent = d.load_hours.toLocaleString() + ' hrs';
      document.getElementById('load-pct').textContent = d.load_percent + '%';
      document.getElementById('starts-hr').textContent = d.starts_hour;
      document.getElementById('aux-val').textContent = d.aux_psi + ' PSI (' + d.aux_bar + ' bar)';
      document.getElementById('int-state').textContent = d.internal_state;

      // Status flags
      const flags = d.status_flags || 0;
      let fHtml = '';
      const flagDefs = [
        [0x0800, 'MOTOR'], [0x0400, 'ACTIVE'], [0x0004, 'TIMER'],
        [0x0008, 'BYPASS'], [0x0020, 'FAN'], [0x0040, 'DRAIN'], [0x0080, 'ALARM']
      ];
      flagDefs.forEach(function(f) {
        const on = (flags & f[0]) !== 0;
        fHtml += '<span class="flag-item '+(on?'flag-on':'flag-off')+'">'+f[1]+'</span>';
      });
      document.getElementById('status-flags-row').innerHTML = fHtml;
    })
    .catch(e => {
      document.getElementById('conn-dot').className = 'status-dot dot-red';
      document.getElementById('conn-text').textContent = 'Web error';
    });
}

setInterval(update, 3000);
update();
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/status')
def api_status():
    """Health endpoint for Overseer integration."""
    with data_lock:
        connected = current_data['connected']
        pressure_psi = current_data['pressure_psi']
        temperature_f = current_data['temperature_f']
        display_state_text = current_data['display_state_text']
        last_update = current_data['last_update']
        active_alarms = list(current_data['active_alarm_texts'])
    return jsonify({
        'status': 'ok' if connected else 'error',
        'connected': connected,
        'pressure_psi': pressure_psi,
        'temperature_f': temperature_f,
        'compressor_state': display_state_text,
        'last_update': last_update,
        'active_alarms': active_alarms,
        'error': None if connected else 'Not connected to compressor',
    })


@app.route('/api/data')
def api_data():
    with data_lock:
        result = dict(current_data)

    # Add cabinet filter info
    cab = load_cabinet_filter()
    result['cabinet_interval'] = cab.get('interval_hours', 2730)
    result['cabinet_last_changed'] = cab.get('last_changed', 'Never')
    if cab.get('last_changed'):
        try:
            changed = datetime.datetime.strptime(cab['last_changed'], '%Y-%m-%d')
            days_ago = (datetime.datetime.now() - changed).days
            est_hours = days_ago * 15
            result['cabinet_remain'] = max(0, cab['interval_hours'] - est_hours)
        except (ValueError, TypeError):
            result['cabinet_remain'] = cab['interval_hours']
    else:
        result['cabinet_remain'] = 0

    return jsonify(result)


@app.route('/api/compressor/start', methods=['POST'])
def compressor_start():
    """Start the compressor via fieldbus command register (HR 1036)."""
    try:
        with modbus_client_lock:
            if not (modbus_client and modbus_client.connected):
                return jsonify({'error': 'Not connected to compressor'}), 503
            result = modbus_client.write_register(
                REG_FIELDBUS_CMD, CMD_START, device_id=SLAVE_ID)
            if result.isError():
                return jsonify({'error': f'Modbus write failed: {result}'}), 500
    except Exception as e:
        return jsonify({'error': f'Write error: {e}'}), 500

    return jsonify({'message': 'START command sent via fieldbus (HR 1036, bit 0x0001).'})


@app.route('/api/compressor/stop', methods=['POST'])
def compressor_stop():
    """Stop the compressor via fieldbus command register (HR 1036)."""
    try:
        with modbus_client_lock:
            if not (modbus_client and modbus_client.connected):
                return jsonify({'error': 'Not connected to compressor'}), 503
            result = modbus_client.write_register(
                REG_FIELDBUS_CMD, CMD_STOP, device_id=SLAVE_ID)
            if result.isError():
                return jsonify({'error': f'Modbus write failed: {result}'}), 500
    except Exception as e:
        return jsonify({'error': f'Write error: {e}'}), 500

    return jsonify({'message': 'STOP command sent via fieldbus (HR 1036, bit 0x0002).'})


@app.route('/api/compressor/resume_schedule', methods=['POST'])
def compressor_resume_schedule():
    """Stop bypass and return compressor to weekly timer control (HR 1036)."""
    try:
        with modbus_client_lock:
            if not (modbus_client and modbus_client.connected):
                return jsonify({'error': 'Not connected to compressor'}), 503
            result = modbus_client.write_register(
                REG_FIELDBUS_CMD, CMD_STOP_BYPASS_TIMER, device_id=SLAVE_ID)
            if result.isError():
                return jsonify({'error': f'Modbus write failed: {result}'}), 500
    except Exception as e:
        return jsonify({'error': f'Write error: {e}'}), 500

    return jsonify({'message': 'RESUME SCHEDULE command sent (HR 1036, bit 0x0010). Timer control restored.'})


@app.route('/api/compressor/alarm_reset', methods=['POST'])
def compressor_alarm_reset():
    """Acknowledge and reset all alarms via fieldbus command register."""
    try:
        with modbus_client_lock:
            if not (modbus_client and modbus_client.connected):
                return jsonify({'error': 'Not connected to compressor'}), 503
            result = modbus_client.write_register(
                REG_FIELDBUS_CMD, CMD_ACK_RESET_ALL, device_id=SLAVE_ID)
            if result.isError():
                return jsonify({'error': f'Modbus write failed: {result}'}), 500
    except Exception as e:
        return jsonify({'error': f'Write error: {e}'}), 500

    return jsonify({'message': 'Alarm reset command sent (HR 1036, bit 0x0020).'})


@app.route('/api/reset_filter', methods=['POST'])
def reset_filter():
    """Reset a maintenance counter via fieldbus command or manual cabinet tracking."""
    data = request.get_json()
    filter_name = data.get('filter', '')

    if filter_name == 'cabinet':
        cab = load_cabinet_filter()
        cab['last_changed'] = datetime.datetime.now().strftime('%Y-%m-%d')
        save_cabinet_filter(cab)
        return jsonify({'message': 'Cabinet filter timer reset. Last changed: today.'})

    if filter_name in FILTER_RESET_CMDS:
        cmd = FILTER_RESET_CMDS[filter_name]
        label = FILTER_LABELS.get(filter_name, filter_name)
        try:
            with modbus_client_lock:
                if not (modbus_client and modbus_client.connected):
                    return jsonify({'error': 'Not connected to compressor'}), 503
                result = modbus_client.write_register(
                    REG_FIELDBUS_CMD, cmd, device_id=SLAVE_ID)
                if result.isError():
                    return jsonify({'error': f'Modbus write failed: {result}'}), 500
        except Exception as e:
            return jsonify({'error': f'Write error: {e}'}), 500
        return jsonify({'message': f'{label} counter reset via fieldbus (HR 1036, cmd 0x{cmd:04X}).'})

    return jsonify({'error': f'Unknown filter: {filter_name}'}), 400


@app.route('/api/schedule', methods=['POST'])
def set_schedule():
    data = request.get_json()
    days = data.get('days', [])
    on_hour = data.get('on_hour', 5)
    on_minute = data.get('on_minute', 0)
    off_hour = data.get('off_hour', 20)
    off_minute = data.get('off_minute', 0)
    enabled = data.get('enabled', True)

    if not days:
        return jsonify({'error': 'No days specified'}), 400

    on_val = encode_time(on_hour, on_minute)
    off_val = encode_time(off_hour, off_minute)

    written = []
    for day in days:
        if not 0 <= day <= 6:
            continue
        if enabled:
            values = [on_val, off_val, off_val, off_val, off_val, off_val]
        else:
            values = [0, 0, 0, 0, 0, 0]

        try:
            with modbus_client_lock:
                if not (modbus_client and modbus_client.connected):
                    return jsonify({'error': 'Not connected to compressor'}), 503
                timers = [TIMER1_BASE, TIMER2_BASE] if day <= 4 else [TIMER2_BASE]
                for timer_base in timers:
                    base_reg = timer_base + day * REGS_PER_DAY
                    result = modbus_client.write_registers(
                        base_reg, values, device_id=SLAVE_ID)
                    if result.isError():
                        return jsonify({
                            'error': f'Modbus write failed for {DAY_NAMES[day]}: {result}'
                        }), 500
                    time.sleep(0.05)
                written.append(DAY_NAMES[day])
        except Exception as e:
            return jsonify({'error': f'Write error: {e}'}), 500

    if not written:
        return jsonify({'error': 'No valid days to write'}), 400

    day_list = ', '.join(written)
    if enabled:
        return jsonify({
            'message': f'Schedule set for {day_list}: '
                       f'ON {on_hour:02d}:{on_minute:02d}, OFF {off_hour:02d}:{off_minute:02d}'
        })
    else:
        return jsonify({'message': f'Schedule disabled for {day_list}'})


def _serve_with_shutdown(app, host, port, channel_timeout=30):
    """Run app under waitress with a /api/shutdown route for graceful stop."""
    from waitress import create_server

    shutdown_event = threading.Event()

    @app.route("/api/shutdown", methods=["POST"])
    def _api_shutdown():
        shutdown_event.set()
        return ("shutting down", 200)

    server = create_server(app, host=host, port=port, channel_timeout=channel_timeout)

    def _waiter():
        shutdown_event.wait()
        server.close()

    threading.Thread(target=_waiter, daemon=True).start()
    print(f"Serving on http://{host}:{port} (waitress)", flush=True)
    server.run()


if __name__ == '__main__':
    print(f"Starting compressor monitor v2...")
    print(f"  Gateway: {GATEWAY_IP}:{GATEWAY_PORT}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print(f"  Web UI: http://localhost:{WEB_PORT}")
    print(f"  Register source: Official LOGIK26S MODBUS PROCEDURE")
    print()

    poller = threading.Thread(target=poll_compressor, daemon=True)
    poller.start()

    _serve_with_shutdown(app, '0.0.0.0', WEB_PORT)
