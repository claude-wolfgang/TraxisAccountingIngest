@echo off
REM Fires the kiosk task, captures the exit code + output, waits 8s,
REM then re-queries to see if Last Run Time advanced.
REM Run on .141. Double-click.

set "OUT=%USERPROFILE%\Dropbox\temp\kiosk_fire_report.txt"
if not exist "%USERPROFILE%\Dropbox\temp" mkdir "%USERPROFILE%\Dropbox\temp"

echo Firing TraxisToolKiosk and capturing result...

(
  echo === fire attempt at %DATE% %TIME% ===
  echo.
  echo --- schtasks /Run output ---
  schtasks /Run /TN TraxisToolKiosk
  echo schtasks /Run exit code: %errorlevel%
  echo.
  echo --- waiting 8 seconds ---
) > "%OUT%"

timeout /t 8 /nobreak > nul

(
  echo.
  echo --- post-fire task status ---
  schtasks /Query /TN TraxisToolKiosk /V /FO LIST
  echo.
  echo --- pythonw processes now ---
  tasklist /FI "IMAGENAME eq pythonw.exe"
  echo.
  echo --- chrome processes now ---
  tasklist /FI "IMAGENAME eq chrome.exe"
  echo.
  echo === END ===
) >> "%OUT%"

echo.
echo Done. Report at %OUT%
pause
