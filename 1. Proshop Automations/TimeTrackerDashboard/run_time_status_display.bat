@echo off
REM Traxis Time Tracking Status Display v1.0
REM ==========================================
REM Launches the time tracking dashboard server.
REM Open http://localhost:8050 in your browser after running.
REM
REM SETUP:
REM   1. Set your ProShop client secret below (or as env var)
REM   2. pip install flask requests
REM   3. Run this batch file

REM === SET YOUR SECRET HERE ===
REM set PROSHOP_CLIENT_SECRET=your_secret_here

echo ============================================
echo  Traxis Time Tracking Status Display v1.0
echo ============================================
echo.

REM Check if secret is set
if "%PROSHOP_CLIENT_SECRET%"=="" (
    echo WARNING: PROSHOP_CLIENT_SECRET not set!
    echo Edit this .bat file or set the environment variable.
    echo.
)

echo Starting server at http://localhost:8050
echo Press Ctrl+C to stop.
echo.

"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe" "%~dp0time_status_display_v1.0.py"

pause
