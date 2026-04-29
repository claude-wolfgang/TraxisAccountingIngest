@echo off
REM Traxis Label Printer — Start extension host server (background)
cd /d "%~dp0"
start "" pythonw host.py
echo Extension host started on port 8484
