@echo off
title COTS Crib Kiosk Launcher

:: Set API credentials
set PROSHOP_CLIENT_SECRET=E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110

:: Change to script directory
cd /d "%~dp0"

:: Kill any existing kiosk server
taskkill /f /fi "WINDOWTITLE eq COTS Crib Kiosk Server" >nul 2>&1

:: Start the server minimized in the background
start "COTS Crib Kiosk Server" /min python app.py

:: Wait for the server to be ready
echo Starting COTS Crib Kiosk server...
set RETRIES=0
:wait_loop
timeout /t 1 /nobreak >nul
powershell -Command "(Invoke-WebRequest -Uri http://localhost:5000/api/health -UseBasicParsing -TimeoutSec 2).StatusCode" >nul 2>&1
if %errorlevel%==0 goto server_ready
set /a RETRIES+=1
if %RETRIES% GEQ 15 (
    echo Server failed to start. Check the server window for errors.
    pause
    exit /b 1
)
goto wait_loop

:server_ready
echo Server is running!

:: Open Chrome in kiosk mode
echo Launching Chrome...
start "" "chrome.exe" --kiosk http://localhost:5000
