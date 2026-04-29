@echo off
REM Traxis Label Printer — Deployment Diagnostic
REM Run as Administrator on the problem PC

echo ============================================
echo  Traxis Extension Diagnostic - %COMPUTERNAME%
echo ============================================
echo.
echo [1] HKLM Chrome policy:
reg query "HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist" 2>nul
if errorlevel 1 echo   NOT SET
echo.
echo [2] Host server test:
curl -s -o nul -w "HTTP %%{http_code}" "http://10.1.1.71:8484/update_manifest.xml" 2>nul
if errorlevel 1 echo   UNREACHABLE
echo.
echo.
echo [3] Chrome version:
reg query "HKLM\SOFTWARE\Google\Chrome\BLBeacon" /v version 2>nul
echo.
echo [4] Admin check:
net session >nul 2>nul
if errorlevel 1 (echo   NOT ADMIN - rerun as Administrator) else (echo   OK - running as admin)
echo.
echo ============================================
pause
