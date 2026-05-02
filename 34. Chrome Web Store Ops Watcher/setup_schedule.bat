@echo off
REM ---------------------------------------------------------------------
REM  P34 Chrome Web Store Ops Watcher -- Task Scheduler installer
REM
REM  Creates "Traxis - CWS Ops Watcher" running every 4 hours via
REM  pythonw.exe (no console flash, per P32 lesson). Idempotent --
REM  safe to re-run; existing task is replaced.
REM
REM  No admin elevation required (task runs as the current user).
REM ---------------------------------------------------------------------

setlocal

set "TASK_NAME=Traxis - CWS Ops Watcher"
set "PYTHONW=C:\Users\Superuser\AppData\Local\Programs\Python\Python314\pythonw.exe"
set "SCRIPT=%~dp0cws_watcher.py"

if not exist "%PYTHONW%" (
    echo ERROR: pythonw.exe not found at %PYTHONW%
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo ERROR: cws_watcher.py not found at %SCRIPT%
    exit /b 1
)

echo Creating scheduled task "%TASK_NAME%"
echo   Runs:    every 4 hours
echo   Command: "%PYTHONW%" "%SCRIPT%"
echo.

schtasks /Create /F ^
  /SC HOURLY /MO 4 ^
  /TN "%TASK_NAME%" ^
  /TR "\"%PYTHONW%\" \"%SCRIPT%\"" ^
  /RL LIMITED ^
  /ST 06:00

if errorlevel 1 (
    echo.
    echo ERROR: schtasks /Create failed.
    exit /b 1
)

echo.
echo Task created. Verify with:
echo   schtasks /Query /TN "%TASK_NAME%"
echo.
echo Run once now to confirm:
echo   schtasks /Run /TN "%TASK_NAME%"
echo.
echo Remove later with:
echo   schtasks /Delete /TN "%TASK_NAME%" /F

endlocal
