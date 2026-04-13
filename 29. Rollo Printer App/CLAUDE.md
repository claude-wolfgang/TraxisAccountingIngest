# P29 — Rollo Thermal Printer System Tray App

Windows system tray app that prints PDFs to Rollo 4x6 thermal printer with auto-rescaling.

## Stack
- Python 3.8+ / pystray / PyMuPDF / pywin32
- PyInstaller for single-exe packaging

## Key files
- `rollo_printer_app.py` — main application
- `rollo_printer_app.spec` — PyInstaller build spec
- `ROLLO_PRINTER_APP.md` — full spec/requirements doc

## Build
```bash
pip install -r requirements.txt
pyinstaller rollo_printer_app.spec
```
Output: `dist/rollo_printer_app.exe`

## Interfaces
Produces: `rollo_print.log` (print job history, last 100 entries), `rollo_printer_app.exe` (standalone executable)
Consumes: Windows printer subsystem (printer named "Rollo Printer"), user-supplied PDF files
Contracts: Expects a Windows printer with "rollo" (case-insensitive) in its name to be installed
