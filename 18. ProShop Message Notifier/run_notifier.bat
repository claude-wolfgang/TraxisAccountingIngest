@echo off
title ProShop Message Notifier

:: Set API credentials
set PROSHOP_CLIENT_SECRET=E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110

:: Start web-based notifier (Flask on port 5050)
cd /d "%~dp0"
echo Starting ProShop Message Notifier (web)...
python app.py

:: If python exits, pause so errors are visible
echo.
echo Notifier stopped.
pause
