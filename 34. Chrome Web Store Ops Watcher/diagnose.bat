@echo off
REM ---------------------------------------------------------------------
REM  P34 watcher -- diagnostic. Captures all output to diagnose_output.txt
REM  (which Dropbox syncs back) AND prints to the console. Read-only --
REM  uses --print-only so no DB or heartbeat writes happen.
REM ---------------------------------------------------------------------

setlocal

set "SCRIPT=%~dp0cws_watcher.py"
set "LOG=%~dp0diagnose_output.txt"

REM Find python.exe (NOT pythonw -- we want stdout/stderr visible)
set "PYTHON="
for /f "delims=" %%P in ('where python.exe 2^>nul') do (
    if not defined PYTHON set "PYTHON=%%P"
)
if not defined PYTHON (
    for %%C in (
        "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "C:\Program Files\Python314\python.exe"
        "C:\Program Files\Python313\python.exe"
        "C:\Program Files\Python312\python.exe"
    ) do (
        if not defined PYTHON if exist %%C set "PYTHON=%%~C"
    )
)

(
    echo === P34 Diagnostic Report ===
    echo Run at: %DATE% %TIME%
    echo Hostname:   %COMPUTERNAME%
    echo User:       %USERNAME%
    echo Python:     %PYTHON%
    echo Script:     %SCRIPT%
    echo.
    echo === Scheduled task status ===
    schtasks /Query /TN "Traxis - CWS Ops Watcher" /V /FO LIST 2>&1
    echo.
    echo === Running cws_watcher.py --print-only -v ===
    if defined PYTHON (
        "%PYTHON%" "%SCRIPT%" --print-only -v
    ) else (
        echo ERROR: python.exe not found
    )
    echo.
    echo === End ===
) > "%LOG%" 2>&1

echo.
echo Output saved to:  %LOG%
echo.
type "%LOG%"
echo.
pause

endlocal
