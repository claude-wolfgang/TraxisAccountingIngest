@echo off
:: FASData Shop Floor Dashboard - Kiosk Launcher
:: Place this in the Windows Startup folder for auto-launch on boot:
::   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
::
:: Display PC user: traxi
:: Dashboard synced via Dropbox

set DASHBOARD="C:\Users\traxi\Dropbox\MACHINE COMM Traxis\FASData\reports\dashboard.html"

:: Try Chrome first
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --disable-pinch --overscroll-history-navigation=0 --disable-infobars --noerrdialogs %DASHBOARD%
    goto :eof
)

:: Fall back to Edge
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk --disable-pinch --overscroll-history-navigation=0 --disable-infobars --noerrdialogs %DASHBOARD%
    goto :eof
)

:: Edge might also be here
if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files\Microsoft\Edge\Application\msedge.exe" --kiosk --disable-pinch --overscroll-history-navigation=0 --disable-infobars --noerrdialogs %DASHBOARD%
    goto :eof
)

echo ERROR: Neither Chrome nor Edge found.
pause
