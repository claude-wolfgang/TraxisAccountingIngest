# TraxisTransfer

CNC program transfer tool for Traxis Manufacturing. Replaces the Fanuc PTT and manual SSH/SCP workflows with a unified GUI application.

## Features

- **FOCAS2 driver** — Send/receive NC programs to Fanuc CNCs via ctypes
- **SSH/SCP driver** — Transfer to Haas CHC machines via Pi Zero bridge
- **Smart folder resolution** — Auto-suggests the right folder based on ProShop active work order
- **Audit logging** — SQLite transfer history with operator tracking
- **ISA-101 dark UI** — Large buttons, touch-friendly for shop floor use

## Requirements

- Python 3.11 (32-bit) — required for FOCAS DLL compatibility
- Windows 10/11

## Quick Start

```bash
# Create venv with 32-bit Python
py -3.11-32 -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python -m traxistransfer
```

## Build

```bash
scripts\build.bat
```

Produces `dist\TraxisTransfer.exe`.

## Configuration

- `machines.json` — Machine definitions (IP, port, driver type)
- `~/.traxis.env` — ProShop OAuth credentials

## Project Structure

```
src/traxistransfer/
  focas/        — FOCAS2 ctypes wrapper (DLL, structs, errors)
  drivers/      — Transfer drivers (Fanuc, Haas SSH, stubs)
  services/     — Business logic (folder resolver, ProShop client, audit log)
  ui/           — CustomTkinter GUI components
  models/       — Data classes
  dlls/         — FOCAS DLL files (32-bit)
```
