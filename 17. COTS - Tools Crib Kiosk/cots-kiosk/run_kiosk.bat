@echo off
title COTS Crib Kiosk Server

:: Set API credentials
set PROSHOP_CLIENT_SECRET=E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110

:: Start Flask server
cd /d "%~dp0"
echo Starting COTS Crib Kiosk...
echo Open http://localhost:5000 in your browser
echo.
python app.py

:: If python exits, pause so errors are visible
echo.
echo Server stopped.
pause
