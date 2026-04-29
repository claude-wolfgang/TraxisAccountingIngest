@echo off
cd /d "%~dp0"
python esp32_proximity_test.py
echo.
echo Script exited. Press any key to close.
pause >nul
