"""Lazy-loaded FOCAS2 DLL wrapper with typed function prototypes.

The DLL is NOT loaded at import time. Call ``get_fwlib()`` to get the
loaded+typed library handle (loaded once, then cached).

DLL search order:
  1. ``<package>/dlls/Fwlib32.dll``  (bundled with TraxisTransfer)
  2. System PATH / working directory  (fallback)
"""

from __future__ import annotations

import ctypes
import os
from typing import Any

from traxistransfer.focas.structs import ODBST, ODBSYS, ODBUP, PRGDIR2

# Module-level cache
_fwlib: Any | None = None


def _load_dll() -> ctypes.WinDLL:
    """Locate and load Fwlib32.dll."""
    dll_dir = os.path.join(os.path.dirname(__file__), "..", "dlls")
    dll_path = os.path.join(dll_dir, "Fwlib32.dll")

    if os.path.isfile(dll_path):
        return ctypes.windll.LoadLibrary(dll_path)

    # Fallback: let Windows search PATH / cwd
    return ctypes.windll.LoadLibrary("Fwlib32.dll")


def _set_prototypes(lib: ctypes.WinDLL) -> None:
    """Declare argtypes and restype for every FOCAS function we use."""

    # ── Connection ──────────────────────────────────────────────────
    # short cnc_allclibhndl3(const char* ip, unsigned short port,
    #                         int timeout, unsigned short* handle)
    lib.cnc_allclibhndl3.argtypes = [
        ctypes.c_char_p,
        ctypes.c_ushort,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_ushort),
    ]
    lib.cnc_allclibhndl3.restype = ctypes.c_short

    # short cnc_freelibhndl(unsigned short handle)
    lib.cnc_freelibhndl.argtypes = [ctypes.c_ushort]
    lib.cnc_freelibhndl.restype = ctypes.c_short

    # ── Status ──────────────────────────────────────────────────────
    # short cnc_statinfo(unsigned short handle, ODBST* statinfo)
    lib.cnc_statinfo.argtypes = [
        ctypes.c_ushort,
        ctypes.POINTER(ODBST),
    ]
    lib.cnc_statinfo.restype = ctypes.c_short

    # ── Program directory ───────────────────────────────────────────
    # short cnc_rdprogdir2(unsigned short handle, short type,
    #                       short* num, PRGDIR2* buf)
    lib.cnc_rdprogdir2.argtypes = [
        ctypes.c_ushort,
        ctypes.c_short,
        ctypes.POINTER(ctypes.c_short),
        ctypes.POINTER(PRGDIR2),
    ]
    lib.cnc_rdprogdir2.restype = ctypes.c_short

    # ── Download (send TO CNC) ──────────────────────────────────────
    # short cnc_dwnstart3(unsigned short handle, short type)
    lib.cnc_dwnstart3.argtypes = [ctypes.c_ushort, ctypes.c_short]
    lib.cnc_dwnstart3.restype = ctypes.c_short

    # short cnc_download3(unsigned short handle, int* length, char* data)
    lib.cnc_download3.argtypes = [
        ctypes.c_ushort,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_char_p,
    ]
    lib.cnc_download3.restype = ctypes.c_short

    # short cnc_dwnend3(unsigned short handle)
    lib.cnc_dwnend3.argtypes = [ctypes.c_ushort]
    lib.cnc_dwnend3.restype = ctypes.c_short

    # ── Upload (receive FROM CNC) ───────────────────────────────────
    # short cnc_upstart(unsigned short handle, short type, int prog_no)
    lib.cnc_upstart.argtypes = [
        ctypes.c_ushort,
        ctypes.c_short,
        ctypes.c_int,
    ]
    lib.cnc_upstart.restype = ctypes.c_short

    # short cnc_upload(unsigned short handle, ODBUP* buf,
    #                   unsigned short* length)
    lib.cnc_upload.argtypes = [
        ctypes.c_ushort,
        ctypes.POINTER(ODBUP),
        ctypes.POINTER(ctypes.c_ushort),
    ]
    lib.cnc_upload.restype = ctypes.c_short

    # short cnc_upend(unsigned short handle)
    lib.cnc_upend.argtypes = [ctypes.c_ushort]
    lib.cnc_upend.restype = ctypes.c_short

    # ── System info ─────────────────────────────────────────────────
    # short cnc_sysinfo(unsigned short handle, ODBSYS* sysinfo)
    lib.cnc_sysinfo.argtypes = [
        ctypes.c_ushort,
        ctypes.POINTER(ODBSYS),
    ]
    lib.cnc_sysinfo.restype = ctypes.c_short


def get_fwlib() -> ctypes.WinDLL:
    """Return the loaded and typed FOCAS library (lazy singleton).

    Raises:
        OSError: If Fwlib32.dll cannot be found or loaded.
    """
    global _fwlib
    if _fwlib is None:
        lib = _load_dll()
        _set_prototypes(lib)
        _fwlib = lib
    return _fwlib


def reset_fwlib() -> None:
    """Clear the cached DLL handle (useful for testing)."""
    global _fwlib
    _fwlib = None
