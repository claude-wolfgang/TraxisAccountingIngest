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
set "SCRIPT=%~dp0cws_watcher.py"

REM Discover pythonw.exe on this machine (where.exe returns the first match in PATH).
REM Falls back to common install locations if not in PATH.
set "PYTHONW="
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do (
    if not defined PYTHONW set "PYTHONW=%%P"
)
if not defined PYTHONW (
    for %%C in (
        "%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
        "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
        "C:\Program Files\Python314\pythonw.exe"
        "C:\Program Files\Python313\pythonw.exe"
        "C:\Program Files\Python312\pythonw.exe"
    ) do (
        if not defined PYTHONW if exist %%C set "PYTHONW=%%~C"
    )
)

if not defined PYTHONW (
    echo ERROR: pythonw.exe not found. Install Python 3.12+ or add it to PATH.
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo ERROR: cws_watcher.py not found at %SCRIPT%
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
