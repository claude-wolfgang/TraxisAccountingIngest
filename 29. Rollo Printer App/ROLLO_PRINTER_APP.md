# Rollo Thermal Printer System Tray App

## Overview
Windows system tray application for printing UPS shipping labels (or any PDFs) directly to Rollo 4x6 thermal printer without browser dialogs or UPS software interference.

## Problem Statement
UPS web interface and thermal printer drivers don't communicate correctly. This app bypasses that entirely by:
1. Accepting PDFs via drag-drop or file browser
2. Rescaling to 4x6 thermal label dimensions
3. Sending directly to Rollo printer
4. Running silently in system tray

## Requirements

### Functional
- System tray icon (minimize to tray, not taskbar)
- Right-click context menu with "Print to Rollo" option
- File dialog to select PDF
- Auto-rescale PDF to 4x6 inches at 203 DPI (Rollo native resolution)
- Send directly to "Rollo Printer" (Windows printer name)
- Log all print jobs with timestamp to `rollo_print.log` in same folder
- No dialog boxes or terminal windows during printing
- Single .exe deliverable (PyInstaller)

### Non-Functional
- Silent operation (no popups unless error)
- Lightweight (should not noticeably impact system resources)
- Windows 7+ compatible
- Can be added to Windows startup if needed

## Technical Specification

### Stack
- **Language:** Python 3.8+
- **GUI/Tray:** pystray (or PyQt5 if needed)
- **PDF Processing:** PyPDF2 or pypdf for rescaling
- **Printer Communication:** win32print or pywin32 for direct printer access
- **Packaging:** PyInstaller to create single .exe

### PDF Rescaling Logic
- Detect PDF dimensions
- Scale to 4x6 inches (1212 x 1824 pixels at 203 DPI for Rollo)
- Maintain aspect ratio (center on label if needed)
- Apply scaling during PDF-to-print conversion

### Printer Detection
- Query Windows for printer named "Rollo Printer"
- Fail gracefully if not found (log error, notify user)
- Test print job to ensure connectivity

### Logging
- File: `rollo_print.log` (same directory as .exe)
- Format: `[YYYY-MM-DD HH:MM:SS] Printed: {filename} | Pages: {count} | Status: {success/fail}`
- Keep last 100 entries (rotate file)

## Deliverables

### Files to Produce
1. `rollo_printer_app.py` - Main application source
2. `rollo_printer_app.spec` - PyInstaller spec file
3. `rollo_printer_app.exe` - Compiled executable
4. `README.md` - Setup and usage instructions

### Dropbox Location
```
MACHINE COMM Traxis/Proshop Automation and Claude Projects/18. Rollo Printer System Tray App/
├── rollo_printer_app.exe
├── rollo_printer_app.spec
├── rollo_printer_app.py
├── README.md
└── rollo_print.log (created on first run)
```

## Usage

### Installation
1. Download `rollo_printer_app.exe` from Dropbox
2. Place anywhere on local drive (recommend Program Files or Desktop)
3. Run once to initialize
4. (Optional) Add to Windows startup folder for auto-launch

### Operation
1. App runs silently in system tray (yellow/gold Rollo icon)
2. Right-click tray icon → "Print to Rollo"
3. Select PDF file from dialog
4. App rescales and sends to printer
5. Brief notification (or log entry) confirms success

### Logs
- Check `rollo_print.log` in same folder as .exe for history
- Useful for troubleshooting or auditing print jobs

## Error Handling
- Rollo printer not found → Log error + brief tray notification
- Invalid PDF → Log error + notification
- Print job failed → Log reason + notification
- Network/permissions issues → Graceful failure with actionable message

## Future Enhancements (Not in MVP)
- Drag-and-drop PDF onto tray icon
- Print queue visualization
- Multiple printer support
- UPS API integration (skip PDF step entirely)
- Schedule print jobs

## Success Criteria
✅ App runs silently in tray  
✅ Right-click context menu works  
✅ PDF rescales to 4x6 correctly  
✅ Prints to Rollo without browser/dialog interference  
✅ Logs all activity  
✅ Single .exe (no dependencies to install)  
✅ Ready to use in <1 minute after download  
