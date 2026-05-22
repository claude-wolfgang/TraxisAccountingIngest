@echo off
REM =============================================================================
REM srv-01 step 07 (kiosk-side diag) -- Find Python on the kiosk PC.
REM
REM Run on .141. Double-click.
REM Writes a report to:
REM   %USERPROFILE%\Dropbox\temp\kiosk_python_check.txt
REM ...which I can read remotely.
REM =============================================================================

setlocal

set "OUT=%USERPROFILE%\Dropbox\temp\kiosk_python_check.txt"
if not exist "%USERPROFILE%\Dropbox\temp" mkdir "%USERPROFILE%\Dropbox\temp"

echo Writing report to %OUT% ...

(
  echo === kiosk python check on %COMPUTERNAME% by %USERNAME% at %DATE% %TIME% ===
  echo.
  echo --- where pythonw ---
  where pythonw 2^>^&1
  echo.
  echo --- where python ---
  where python 2^>^&1
  echo.
  echo --- LOCALAPPDATA Python dirs ---
  if exist "%LOCALAPPDATA%\Programs\Python" (
    dir /b "%LOCALAPPDATA%\Programs\Python"
  ) else (
    echo NOT FOUND: %LOCALAPPDATA%\Programs\Python
  )
  echo.
  echo --- Program Files Python dirs ---
  if exist "C:\Program Files\Python313" echo FOUND: C:\Program Files\Python313
  if exist "C:\Program Files\Python314" echo FOUND: C:\Program Files\Python314
  if not exist "C:\Program Files\Python313" if not exist "C:\Program Files\Python314" echo NOT FOUND: any C:\Program Files\Python3xx
  echo.
  echo --- TraxisToolKiosk task last result ---
  schtasks /Query /TN TraxisToolKiosk /V /FO LIST 2^>^&1 ^| findstr /I "Last Result Last Run Status Task To"
  echo.
  echo --- TOOLKIOSK_BACKEND_URL env ---
  if defined TOOLKIOSK_BACKEND_URL (
    echo TOOLKIOSK_BACKEND_URL=%TOOLKIOSK_BACKEND_URL%
  ) else (
    echo TOOLKIOSK_BACKEND_URL not set in this shell
  )
  echo.
  echo --- .traxis.env contents ---
  if exist "%USERPROFILE%\.traxis.env" (
    type "%USERPROFILE%\.traxis.env"
  ) else (
    echo NOT FOUND: %USERPROFILE%\.traxis.env
  )
  echo.
  echo === END OF REPORT ===
) > "%OUT%" 2>&1

echo.
echo Done. Report saved to %OUT%
echo Tell the chat you ran it -- output will sync to Dropbox in a moment.
pause
