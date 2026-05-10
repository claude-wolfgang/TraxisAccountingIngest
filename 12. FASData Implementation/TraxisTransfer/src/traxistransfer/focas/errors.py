"""FOCAS2 error codes and exception class."""

# ── Return codes from Fwlib32.dll ──────────────────────────────────────
EW_OK = 0            # Normal completion
EW_SOCKET = -16      # Socket error / no connection
EW_PROTOCOL = -17    # Protocol error
EW_NODLL = -15       # DLL not found
EW_HANDLE = -8       # Invalid handle
EW_VERSION = -7      # CNC/PMC version mismatch
EW_UNEXP = -6        # Unexpected error
EW_PARAM = -4        # Invalid parameter
EW_BUFFER = -3       # Buffer shortage
EW_FUNC = -1         # Command not supported
EW_DATA = 1          # Data error (wrong value / range)
EW_NOOPT = 2         # Option not enabled on CNC
EW_BUSY = 3          # CNC is busy (e.g. editing)
EW_ATTRIB = 4        # Data attribute error
EW_REJECT = 5        # Execution rejected (e.g. handle limit — FocasMonitor conflict)
EW_ALARM = 6         # Alarm state
EW_STOP = 7          # CNC is stopped
EW_PASSWD = 8        # Password error

# Human-readable descriptions for common codes
_CODE_NAMES = {
    EW_OK: "EW_OK",
    EW_SOCKET: "EW_SOCKET",
    EW_PROTOCOL: "EW_PROTOCOL",
    EW_NODLL: "EW_NODLL",
    EW_HANDLE: "EW_HANDLE",
    EW_VERSION: "EW_VERSION",
    EW_UNEXP: "EW_UNEXP",
    EW_PARAM: "EW_PARAM",
    EW_BUFFER: "EW_BUFFER",
    EW_FUNC: "EW_FUNC",
    EW_DATA: "EW_DATA",
    EW_NOOPT: "EW_NOOPT",
    EW_BUSY: "EW_BUSY",
    EW_ATTRIB: "EW_ATTRIB",
    EW_REJECT: "EW_REJECT",
    EW_ALARM: "EW_ALARM",
    EW_STOP: "EW_STOP",
    EW_PASSWD: "EW_PASSWD",
}


def code_name(code: int) -> str:
    """Return human-readable name for a FOCAS return code."""
    return _CODE_NAMES.get(code, f"UNKNOWN({code})")


class FocasError(Exception):
    """Raised when a FOCAS API call returns a non-zero error code."""

    def __init__(self, function: str, code: int, detail: str = ""):
        self.function = function
        self.code = code
        name = code_name(code)
        msg = f"{function} failed: {name} (code {code})"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)
