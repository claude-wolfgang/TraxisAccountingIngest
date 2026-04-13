# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Rollo Printer System Tray App
# Build with: pyinstaller rollo_printer_app.spec

a = Analysis(
    ['rollo_printer_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'win32print',
        'win32ui',
        'fitz',
        'tkinter',
        'tkinter.filedialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='rollo_printer_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # Could add a .ico later
)
