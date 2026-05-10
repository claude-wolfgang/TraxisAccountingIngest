@echo off
title Shop Scheduler

:: Set API credentials
set PROSHOP_CLIENT_ID=BA16-EFAF-B154
set PROSHOP_CLIENT_SECRET=2F64968E4E77FDE1CB6B587D9F92340CC3B4C82A414D77798F359A85CD4976D1

:: Start Flask server
cd /d "%~dp0"
echo Starting Shop Scheduler...
echo Open http://localhost:5080 in your browser
echo.
python app.py

:: If python exits, pause so errors are visible
echo.
echo Server stopped.
pause
