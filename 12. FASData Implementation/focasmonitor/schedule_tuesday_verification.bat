@echo off
REM ============================================================================
REM  Schedule a one-shot FOCAS program_directory verification for Tuesday 9 AM
REM  ----------------------------------------------------------------------------
REM  Run this on .71 once. It creates a Windows Scheduled Task that:
REM    - Fires once at Tuesday 2026-05-05 09:00 (local Chicago time)
REM    - Runs report_focas_verification.py
REM    - Sends a verdict + per-machine summary to the P25 Telegram bot
REM    - Auto-deletes itself after running (/Z flag)
REM
REM  Re-run this .bat to re-schedule (uses /F to overwrite). Won't change the
REM  scheduled task once it has fired.
REM ============================================================================

setlocal

set "TASK_NAME=FocasProgDirVerifyTue"
set "WRAPPER_PATH=%~dp0run_focas_verification.bat"
set "SCHEDULE_DATE=05/05/2026"
set "SCHEDULE_TIME=09:00"
set "SCHEDULE_END_TIME=10:00"

echo.
echo Scheduling one-shot FOCAS verification:
echo   Task name:  %TASK_NAME%
echo   Wrapper:    %WRAPPER_PATH%
echo   When:       %SCHEDULE_DATE% %SCHEDULE_TIME% (local time)
echo.

REM /TR value is just the wrapper .bat path. The wrapper handles invoking
REM Python with the right script — avoids cmd's nested-quoting hell.
REM
REM /ET (end time) supplies the EndBoundary that newer Windows schtasks
REM requires when combined with /Z (auto-delete after run). End time is set
REM to 1 hour past start; the actual run completes in seconds, so /ET just
REM bounds the trigger window.
schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "%WRAPPER_PATH%" ^
    /SC ONCE ^
    /SD %SCHEDULE_DATE% ^
    /ST %SCHEDULE_TIME% ^
    /ET %SCHEDULE_END_TIME% ^
    /Z ^
    /F

if errorlevel 1 (
    echo.
    echo ERROR: schtasks /Create failed. See output above.
    echo Common causes:
    echo   - Need to run this Command Prompt as the user who owns C:\FASData
    echo   - Date format wrong: schtasks expects locale format ^(US: MM/DD/YYYY^)
    echo   - Task name conflict with existing task
    echo.
    pause
    exit /b 1
)

echo.
echo SUCCESS. To inspect or remove the task:
echo   schtasks /Query /TN "%TASK_NAME%" /V /FO LIST
echo   schtasks /Delete /TN "%TASK_NAME%" /F
echo.
echo To run it NOW (smoke test) without waiting until Tuesday:
echo   schtasks /Run /TN "%TASK_NAME%"
echo.
pause
