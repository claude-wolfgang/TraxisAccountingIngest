@echo off
rem Registers a Windows Task Scheduler entry that starts the Tool Assembly
rem Kiosk silently on every logon of the current user. Idempotent — re-run
rem to update; uninstall with the schtasks /Delete command printed at the end.

setlocal

set "TASKNAME=TraxisToolKiosk"
set "WRAPPER=%~dp0run_kiosk_silent.bat"

if not exist "%WRAPPER%" (
    echo ERROR: run_kiosk_silent.bat not found next to this script.
    echo Expected at: %WRAPPER%
    pause
    exit /b 1
)

echo.
echo  =============================================
echo   Tool Assembly Kiosk - Autostart Installer
echo  =============================================
echo   Task name: %TASKNAME%
echo   Target:    %WRAPPER%
echo  =============================================
echo.

rem Wipe any prior version so this is idempotent.
schtasks /Delete /TN "%TASKNAME%" /F >nul 2>&1

schtasks /Create /TN "%TASKNAME%" /TR "%WRAPPER%" /SC ONLOGON /RL LIMITED /F
if errorlevel 1 (
    echo.
    echo Task creation FAILED.
    pause
    exit /b 1
)

echo.
echo Done. The kiosk will start automatically on every logon of this user.
echo.
echo Useful commands:
echo   Start it now:        schtasks /Run    /TN "%TASKNAME%"
echo   Check task status:   schtasks /Query  /TN "%TASKNAME%" /V /FO LIST
echo   Remove autostart:    schtasks /Delete /TN "%TASKNAME%" /F
echo.
pause
