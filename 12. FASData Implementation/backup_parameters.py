"""
FOCAS Parameter Backup Script

Connects to each machine via FOCAS (Fwlib32.dll), reads critical parameters,
and saves them to a timestamped JSON backup file. Must be run on a machine
with FOCAS DLLs and network access to the CNC controllers.

IMPORTANT: Run this BEFORE enabling Tool Life Management (TLM).

Key parameters backed up:
  - P6800: TLM enable bits
  - P6801: Tool life alarm output
  - P6813: Max tool groups
  - Axis parameters, feed rate limits, etc.

Usage:
  python backup_parameters.py
  python backup_parameters.py --machines-json path/to/machines.json
  python backup_parameters.py --output-dir C:\FASData\backups
"""

import ctypes
import json
import os
import sys
from datetime import datetime


# Default paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MACHINES_JSON = os.path.join(SCRIPT_DIR, "focasmonitor", "machines.json")
DEFAULT_OUTPUT_DIR = r"C:\FASData\backups"

# FOCAS DLL — must be in script dir or system PATH
FWLIB_NAME = "Fwlib32.dll"

# Parameters to back up (number, description)
PARAMS_TO_READ = [
    (6800, "Tool Life Management config bits"),
    (6801, "Tool life alarm output"),
    (6813, "Max tool groups (0i-MF)"),
    (1000, "Axis name characters"),
    (1001, "Axis name characters (ext)"),
    (1401, "Feedrate clamp per axis"),
    (1410, "Rapid traverse rate per axis"),
    (1420, "Rapid traverse rate (2nd) per axis"),
    (1320, "Servo loop gain per axis"),
    (1421, "Servo parameter"),
    (1423, "Servo parameter"),
    (1825, "Reference position per axis"),
    (3131, "Alarm history settings"),
]


def load_fwlib():
    """Load the FOCAS DLL."""
    # Search in script dir first, then focasmonitor dir, then system
    search_paths = [
        os.path.join(SCRIPT_DIR, FWLIB_NAME),
        os.path.join(SCRIPT_DIR, "focasmonitor", FWLIB_NAME),
    ]
    for path in search_paths:
        if os.path.isfile(path):
            return ctypes.windll.LoadLibrary(path)

    # Try system path
    return ctypes.windll.LoadLibrary(FWLIB_NAME)


def connect(fwlib, ip, port, timeout=10):
    """Connect to a CNC controller via FOCAS.

    Returns handle (ushort) or None on failure.
    """
    handle = ctypes.c_ushort(0)
    ret = fwlib.cnc_allclibhndl3(
        ip.encode('ascii'),
        ctypes.c_ushort(port),
        ctypes.c_int(timeout),
        ctypes.byref(handle),
    )
    if ret != 0:
        return None
    return handle.value


def disconnect(fwlib, handle):
    """Disconnect from a CNC controller."""
    fwlib.cnc_freelibhndl(ctypes.c_ushort(handle))


class IODBPSD(ctypes.Structure):
    """FOCAS parameter read structure (type 0 — word)."""
    _fields_ = [
        ("datano", ctypes.c_short),
        ("type", ctypes.c_short),
        ("data", ctypes.c_int),
    ]


def read_parameter(fwlib, handle, param_num, axis=0):
    """Read a single parameter value from the controller.

    Args:
        fwlib: Loaded FOCAS DLL
        handle: Connection handle
        param_num: Parameter number
        axis: Axis number (0 for non-axis params)

    Returns:
        int value or None on error
    """
    buf = IODBPSD()
    buf_len = ctypes.c_short(ctypes.sizeof(IODBPSD))

    ret = fwlib.cnc_rdparam(
        ctypes.c_ushort(handle),
        ctypes.c_short(param_num),
        ctypes.c_short(axis),
        buf_len,
        ctypes.byref(buf),
    )
    if ret != 0:
        return None
    return buf.data


def backup_machine(fwlib, machine_config):
    """Read all parameters from a single machine.

    Returns dict with parameter values and metadata.
    """
    machine_id = machine_config["id"]
    ip = machine_config["ip"]
    port = machine_config.get("port", 8193)
    name = machine_config.get("name", machine_id)

    print(f"  Connecting to {name} ({machine_id}) at {ip}:{port}...")

    handle = connect(fwlib, ip, port)
    if handle is None:
        print(f"  ERROR: Could not connect to {name}")
        return {
            "machine_id": machine_id,
            "machine_name": name,
            "ip": ip,
            "status": "connection_failed",
            "parameters": {},
        }

    try:
        parameters = {}
        for param_num, description in PARAMS_TO_READ:
            # Read non-axis value first
            value = read_parameter(fwlib, handle, param_num, axis=0)

            # For axis-specific params, also read per-axis
            axis_values = {}
            if param_num in (1401, 1410, 1420, 1320, 1421, 1423, 1825):
                for axis in range(1, 9):  # Up to 8 axes
                    av = read_parameter(fwlib, handle, param_num, axis=axis)
                    if av is not None:
                        axis_values[f"axis_{axis}"] = av

            parameters[str(param_num)] = {
                "number": param_num,
                "description": description,
                "value": value,
                "axis_values": axis_values if axis_values else None,
            }

        print(f"  OK: Read {len(parameters)} parameters from {name}")

        return {
            "machine_id": machine_id,
            "machine_name": name,
            "ip": ip,
            "status": "success",
            "parameters": parameters,
        }

    finally:
        disconnect(fwlib, handle)


def main():
    """Main entry point — backup parameters from all enabled machines."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Backup FOCAS parameters from CNC controllers")
    parser.add_argument(
        "--machines-json", default=DEFAULT_MACHINES_JSON,
        help=f"Path to machines.json (default: {DEFAULT_MACHINES_JSON})")
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    args = parser.parse_args()

    # Load machines config
    print(f"Loading machines from: {args.machines_json}")
    with open(args.machines_json, 'r', encoding='utf-8') as f:
        config = json.load(f)

    machines = [
        m for m in config.get("machines", [])
        if m.get("enabled") and m.get("ip")
    ]

    if not machines:
        print("ERROR: No enabled machines with IPs found")
        sys.exit(1)

    print(f"Found {len(machines)} enabled machine(s)")

    # Load FOCAS DLL
    print(f"Loading FOCAS library ({FWLIB_NAME})...")
    try:
        fwlib = load_fwlib()
    except OSError as e:
        print(f"ERROR: Could not load {FWLIB_NAME}: {e}")
        print("Ensure Fwlib32.dll is in the script directory or system PATH")
        sys.exit(1)

    # Backup each machine
    results = {}
    for machine in machines:
        result = backup_machine(fwlib, machine)
        results[machine["id"]] = result

    # Write backup file
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"parameter_backup_{timestamp}.json"
    filepath = os.path.join(args.output_dir, filename)

    backup = {
        "backup_timestamp": datetime.now().isoformat(timespec="seconds"),
        "source_config": args.machines_json,
        "machines": results,
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(backup, f, indent=2, default=str)

    print(f"\nBackup written to: {filepath}")

    # Summary
    success = sum(1 for r in results.values() if r["status"] == "success")
    failed = len(results) - success
    print(f"Results: {success} succeeded, {failed} failed")

    if failed > 0:
        print("\nFailed machines:")
        for mid, r in results.items():
            if r["status"] != "success":
                print(f"  {mid}: {r['machine_name']} — {r['status']}")


if __name__ == "__main__":
    main()
