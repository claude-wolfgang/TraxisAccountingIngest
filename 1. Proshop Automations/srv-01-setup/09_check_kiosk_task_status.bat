@echo off
REM Captures full TraxisToolKiosk task status to Dropbox for remote review.
REM Run on .141. Double-click.

set "OUT=%USERPROFILE%\Dropbox\temp\kiosk_task_status.txt"
if not exist "%USERPROFILE%\Dropbox\temp" mkdir "%USERPROFILE%\Dropbox\temp"

echo Writing task status to %OUT% ...
schtasks /Query /TN TraxisToolKiosk /V /FO LIST > "%OUT%"

echo --- type "%~dp0..\..\22. Tool Assembly Management\tool-kiosk\run_kiosk_silent.bat" --- >> "%OUT%"
type "%~dp0..\..\22. Tool Assembly Management\tool-kiosk\run_kiosk_silent.bat" >> "%OUT%"

echo. >> "%OUT%"
echo --- chrome processes --- >> "%OUT%"
tasklist /FI "IMAGENAME eq chrome.exe" /FO TABLE >> "%OUT%"

echo. >> "%OUT%"
echo --- pythonw processes --- >> "%OUT%"
tasklist /FI "IMAGENAME eq pythonw.exe" /FO TABLE >> "%OUT%"

echo.
echo Done. Tell the chat.
pause
