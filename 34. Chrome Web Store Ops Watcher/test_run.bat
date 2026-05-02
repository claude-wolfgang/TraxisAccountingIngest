@echo off
REM ---------------------------------------------------------------------
REM  P34 watcher -- one-shot verification for users who can't type
REM  commands. Triggers the scheduled task, waits, then prints the
REM  resulting heartbeat. Safe to run anytime (read-only side effects).
REM ---------------------------------------------------------------------

setlocal

set "TASK_NAME=Traxis - CWS Ops Watcher"
set "HEARTBEAT=%~dp0last_run.json"

echo.
echo Triggering scheduled task "%TASK_NAME%"...
schtasks /Run /TN "%TASK_NAME%"
if errorlevel 1 (
    echo.
    echo ERROR: schtasks /Run failed. Is the task installed?
    echo Run setup_schedule.bat first, then re-run this.
    pause
    exit /b 1
)

echo.
echo Waiting 30 seconds for pythonw.exe to finish polling...
timeout /t 30 /nobreak >nul

echo.
echo --- last_run.json ---
if exist "%HEARTBEAT%" (
    type "%HEARTBEAT%"
) else (
    echo (file not found -- task may have failed)
)
echo.
echo ---------------------

echo.
echo If "ran_at" above shows a time within the last minute, the watcher
echo is working on this PC. Close this window when done.
echo.
pause

endlocal
