@echo off
REM Fires the TraxisToolKiosk scheduled task right now (no logoff/reboot).
REM Run on .141. Double-click.

echo Starting TraxisToolKiosk scheduled task...
schtasks /Run /TN TraxisToolKiosk
if errorlevel 1 (
    echo.
    echo FAILED. Check that install_autostart.bat has been run on this PC.
    pause
    exit /b 1
)
echo.
echo Task fired. Chrome should appear on the touchscreen in a few seconds.
echo Heartbeat will start POSTing to srv-01 within ~60s.
pause
