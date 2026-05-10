@echo off
echo =====================================================
echo  FOCAS Machine Monitor - Service Uninstallation
echo  Traxis Manufacturing
echo =====================================================
echo.

:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges.
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

:: Stop the service
echo Stopping service...
sc stop "FocasMonitor" 2>nul

:: Wait a moment
timeout /t 2 /nobreak >nul

:: Delete the service
echo Removing service...
sc delete "FocasMonitor"

echo.
echo =====================================================
echo  Service Uninstalled
echo =====================================================
echo.
echo Note: Data files in C:\FASData\ have been preserved.
echo Delete manually if no longer needed.
echo.
pause
