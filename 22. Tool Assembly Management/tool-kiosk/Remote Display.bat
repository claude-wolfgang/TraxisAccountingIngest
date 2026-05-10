@echo off
REM ── Open kiosk display on a REMOTE PC ─────────────────────────────────────
REM This is NOT for the kiosk PC itself. This opens Chrome on a secondary
REM machine (e.g., the tool library PC) pointing at the kiosk server.
REM
REM Edit the IP below to match your kiosk PC's address.

set KIOSK_IP=10.1.1.142
set KIOSK_PORT=5001

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --start-fullscreen ^
    --user-data-dir="%LOCALAPPDATA%\ToolKioskChromeProfile" ^
    --noerrdialogs ^
    --disable-translate ^
    --disable-infobars ^
    --disable-session-crashed-bubble ^
    --app=http://%KIOSK_IP%:%KIOSK_PORT%
