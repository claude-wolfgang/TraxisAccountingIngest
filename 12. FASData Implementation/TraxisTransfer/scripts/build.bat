@echo off
REM Build TraxisTransfer.exe using PyInstaller (32-bit Python)
REM Requires: py -3.11-32 -m pip install pyinstaller

setlocal
cd /d "%~dp0.."

py -3.11-32 -m PyInstaller ^
    --name TraxisTransfer ^
    --onefile ^
    --windowed ^
    --add-data "machines.json;." ^
    --add-data "src/traxistransfer/dlls/*.dll;traxistransfer/dlls" ^
    --hidden-import customtkinter ^
    --hidden-import paramiko ^
    --hidden-import scp ^
    --hidden-import requests ^
    --icon NONE ^
    src/traxistransfer/__main__.py

echo.
if exist "dist\TraxisTransfer.exe" (
    echo Build successful: dist\TraxisTransfer.exe
) else (
    echo Build FAILED — check output above.
)
pause
