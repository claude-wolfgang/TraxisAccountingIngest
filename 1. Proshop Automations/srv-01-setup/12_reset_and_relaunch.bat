@echo off
REM Kills any running kiosk launcher + chrome, verifies the synced launcher
REM has the .traxis.env-first fix, then relaunches with debug output.
REM Run on .141. Double-click.

set "OUT=%USERPROFILE%\Dropbox\temp\kiosk_reset_report.txt"
if not exist "%USERPROFILE%\Dropbox\temp" mkdir "%USERPROFILE%\Dropbox\temp"

set "LAUNCHER=%USERPROFILE%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\22. Tool Assembly Management\tool-kiosk\kiosk_launcher.py"
set "PY=%LOCALAPPDATA%\Python\bin\python.exe"

(
  echo === reset and relaunch at %DATE% %TIME% ===
  echo.
  echo --- killing existing chrome.exe + python*.exe ---
) > "%OUT%"

taskkill /F /IM chrome.exe >> "%OUT%" 2>&1
taskkill /F /IM python.exe >> "%OUT%" 2>&1
taskkill /F /IM pythonw.exe >> "%OUT%" 2>&1

(
  echo.
  echo --- launcher file mtime ---
) >> "%OUT%"

powershell -NoProfile -Command "(Get-Item '%LAUNCHER%').LastWriteTime" >> "%OUT%" 2>&1

(
  echo.
  echo --- verifying fix is synced: line 39 region of kiosk_launcher.py ---
) >> "%OUT%"

powershell -NoProfile -Command "Get-Content '%LAUNCHER%' | Select-Object -Skip 36 -First 8" >> "%OUT%" 2>&1

(
  echo.
  echo --- relaunching kiosk_launcher.py for 12 seconds ---
) >> "%OUT%"

cd /d "%USERPROFILE%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\22. Tool Assembly Management\tool-kiosk"
start /B "" "%PY%" kiosk_launcher.py >> "%OUT%" 2>&1
timeout /t 12 /nobreak >nul

(
  echo.
  echo --- killing launcher after 12s capture window ---
) >> "%OUT%"
taskkill /F /IM chrome.exe >> "%OUT%" 2>&1
taskkill /F /IM python.exe >> "%OUT%" 2>&1
taskkill /F /IM pythonw.exe >> "%OUT%" 2>&1

(
  echo.
  echo === END ===
) >> "%OUT%"

echo.
echo Done. Report at %OUT%
pause
