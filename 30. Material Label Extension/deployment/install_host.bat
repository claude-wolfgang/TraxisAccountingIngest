@echo off
REM Traxis Label Printer — Install extension host as startup service
REM Run as Administrator on the host machine (10.1.1.71)

set SCRIPT_DIR=%~dp0
set TASK_NAME=TraxisExtensionHost

where pythonw >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: pythonw not found in PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('where pythonw') do set PYTHONW=%%i

REM Open firewall port
netsh advfirewall firewall add rule name="Traxis Extension Host" dir=in action=allow protocol=tcp localport=8484 >nul 2>nul

REM Create scheduled task to run at startup
schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHONW%\" \"%SCRIPT_DIR%host.py\"" /sc onstart /ru SYSTEM /f

if %errorlevel%==0 (
    echo Scheduled task created — server will auto-start on boot.
    echo Starting server now...
    cd /d "%SCRIPT_DIR%"
    start "" "%PYTHONW%" host.py
    echo.
    echo Host is running on port 8484.
) else (
    echo ERROR: Failed to create scheduled task. Run as Administrator.
)

pause
