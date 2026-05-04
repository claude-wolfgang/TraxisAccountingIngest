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
Consumes: Windows printer subsystem (printer named "Rollo Printer"), user-supplied PDF files (UPS and FedEx Ship Manager 8.5×11 layouts both handled)
Contracts: Expects a Windows printer with "rollo" (case-insensitive) in its name to be installed

## Next Steps
- **Rebuild `dist/rollo_printer_app.exe` via PyInstaller** to deploy the 2026-05-04 FedEx label fix. Source `rollo_printer_app.py` has the multi-block + upside-down-detection logic but the bundled exe is stale. `pyinstaller rollo_printer_app.spec`.
- Smoke-test UPS path with a real UPS PDF after the rebuild — multi-block detection is no-op for single-block content but worth confirming once.
