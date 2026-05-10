@echo off
title Tool Assembly Kiosk
cd /d "%~dp0"
echo.
echo  =============================================
echo   Tool Assembly Kiosk
echo  =============================================
echo   Starting Flask server + Chrome kiosk mode...
echo   Close this window or run STOP KIOSK.bat to quit.
echo  =============================================
echo.
python kiosk_launcher.py
pause
