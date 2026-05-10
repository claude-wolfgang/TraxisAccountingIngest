"""ctypes Structure definitions for FOCAS2 program transfer.

Translated from the C# Focas.cs reference. All structs use _pack_ = 4
to match the DLL's expected alignment.
"""

import ctypes


class ODBST(ctypes.Structure):
    """CNC status information — cnc_statinfo().

    9 x c_short = 18 bytes.
    """
    _pack_ = 4
    _fields_ = [
        ("hdck", ctypes.c_short),       # Handwheel retrace
        ("tmmode", ctypes.c_short),      # T/M mode selection
        ("aut", ctypes.c_short),         # AUTO/MANUAL mode
        ("run", ctypes.c_short),         # Run status (0=STOP, 1=HOLD, 2=START, 3=MSTR, 4=RESTART)
        ("motion", ctypes.c_short),      # Axis motion
        ("mstb", ctypes.c_short),        # M/S/T/B status
        ("emergency", ctypes.c_short),   # Emergency stop
        ("alarm", ctypes.c_short),       # Alarm state
        ("edit", ctypes.c_short),        # Edit mode
    ]


class PRGDIR2(ctypes.Structure):
    """Program directory entry — cnc_rdprogdir2().

    Fields: number (int), length (int), comment (char[51]).
    With _pack_=4: 4 + 4 + 51 = 59 -> padded to 60 bytes.
    """
    _pack_ = 4
    _fields_ = [
        ("number", ctypes.c_int),        # O-number
        ("length", ctypes.c_int),        # Program size in characters
        ("comment", ctypes.c_char * 51), # Program comment (null-terminated)
    ]


class ODBUP(ctypes.Structure):
    """Upload data buffer — cnc_upload().

    Fields: dummy (short), type (short), data (byte[256]).
    Total: 2 + 2 + 256 = 260 bytes.
    """
    _pack_ = 4
    _fields_ = [
        ("dummy", ctypes.c_short),       # Padding / unused
        ("type", ctypes.c_short),        # Data type (0=NC program)
        ("data", ctypes.c_char * 256),   # Upload data block
    ]


class IODBPSD(ctypes.Structure):
    """Parameter read/write structure — cnc_rdparam() / cnc_wrparam().

    Simplified to integer data only (rdata union omitted).
    """
    _pack_ = 4
    _fields_ = [
        ("datano", ctypes.c_short),      # Parameter number
        ("type", ctypes.c_short),        # Axis/type info
        ("axis", ctypes.c_short),        # Axis number
        ("dummy", ctypes.c_short),       # Padding
        ("idata", ctypes.c_int),         # Integer parameter value
    ]


class ODBSYS(ctypes.Structure):
    """System info — cnc_sysinfo().

    Contains CNC type, machine type, series, version, and axis info.
    """
    _pack_ = 4
    _fields_ = [
        ("addinfo", ctypes.c_short),     # Additional info
        ("max_axis", ctypes.c_short),    # Maximum controlled axes
        ("cnc_type", ctypes.c_char * 2), # CNC type string (e.g. "15", "16", "30")
        ("mt_type", ctypes.c_char * 2),  # Machine type ("M"=mill, "T"=lathe)
        ("series", ctypes.c_char * 4),   # Series number
        ("version", ctypes.c_char * 4),  # Version number
        ("axes", ctypes.c_char * 2),     # Axis count string
    ]
