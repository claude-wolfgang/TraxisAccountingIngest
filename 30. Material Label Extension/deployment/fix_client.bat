@echo off
REM Traxis Label Printer — Fix: clean stale entry + restart Chrome
REM Run as Administrator

echo Removing stale registry entry...
reg delete "HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist" /v 2 /f 2>nul

echo Killing all Chrome processes...
taskkill /F /IM chrome.exe >nul 2>nul
timeout /t 3 /nobreak >nul

echo Starting Chrome to chrome://policy ...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" "chrome://policy"

echo.
echo Chrome should open to the policy page.
echo Look for ExtensionInstallForcelist in the list.
echo Then check chrome://extensions for Traxis Label Printer.
pause
