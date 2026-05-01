@echo off
cd /d "%~dp0"
echo Starting BLE proximity logger...
echo Logging to proximity.db
echo Press Ctrl+C to stop
echo.
"C:\Users\Superuser\AppData\Local\Programs\Python\Python314\python.exe" -u proximity_logger.py 10.1.1.108
pause
