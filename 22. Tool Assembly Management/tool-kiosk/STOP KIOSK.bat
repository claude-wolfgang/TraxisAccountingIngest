@echo off
echo Stopping Tool Assembly Kiosk...
echo.

:: Kill Flask on port 5001
echo  - Stopping Flask server...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 5001 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

:: Kill any app.py / kiosk_launcher.py python processes
echo  - Stopping Python processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -and ($_.CommandLine.Contains('kiosk_launcher') -or $_.CommandLine.Contains('app.py')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

:: Kill kiosk Chrome (only the kiosk profile, not your normal Chrome)
echo  - Stopping kiosk Chrome...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('ToolKioskChromeProfile') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

:: Close the START KIOSK.bat console window
echo  - Closing launcher window...
taskkill /fi "WINDOWTITLE eq Tool Assembly Kiosk" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Tool Assembly Kiosk*" /f >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('KIOSK') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo Done. Everything stopped.
timeout /t 2 >nul
