@echo off
REM Manually invokes the kiosk launcher with verbose output captured.
REM Bypasses Task Scheduler so we see the actual Python error.
REM Run on .141. Double-click. Doesn't matter if Chrome opens — Ctrl+C closes the window.

set "OUT=%USERPROFILE%\Dropbox\temp\kiosk_launch_debug.txt"
if not exist "%USERPROFILE%\Dropbox\temp" mkdir "%USERPROFILE%\Dropbox\temp"

set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
set "LAUNCHER=%USERPROFILE%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\22. Tool Assembly Management\tool-kiosk\kiosk_launcher.py"

(
  echo === manual kiosk launch at %DATE% %TIME% ===
  echo.
  echo Python: %PY%
  if exist "%PY%" ( echo   exists: YES ) else ( echo   exists: NO )
  echo.
  echo Launcher: %LAUNCHER%
  if exist "%LAUNCHER%" ( echo   exists: YES ) else ( echo   exists: NO )
  echo.
  echo --- running launcher ---
) > "%OUT%"

cd /d "%USERPROFILE%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\22. Tool Assembly Management\tool-kiosk"
"%PY%" kiosk_launcher.py >> "%OUT%" 2>&1
set RC=%errorlevel%

(
  echo.
  echo --- launcher exited with code %RC% ---
  echo === END ===
) >> "%OUT%"

echo.
echo Done. Report at %OUT%
echo Exit code: %RC%
pause
