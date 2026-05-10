"""FOCAS2 ctypes wrapper for Fanuc CNC communication."""

from traxistransfer.focas.errors import EW_OK, FocasError
from traxistransfer.focas.fwlib import get_fwlib, reset_fwlib
from traxistransfer.focas.structs import ODBST, ODBSYS, ODBUP, PRGDIR2

__all__ = [
    "EW_OK",
    "FocasError",
    "get_fwlib",
    "reset_fwlib",
    "ODBST",
    "ODBSYS",
    "ODBUP",
    "PRGDIR2",
]
