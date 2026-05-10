@echo off
echo =====================================================
echo  FocasMonitor CLEAN Update - Traxis Manufacturing
echo  %DATE% %TIME%
echo =====================================================
echo.

:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Right-click this file and select
    echo        "Run as administrator"
    echo.
    pause
    exit /b 1
)

:: Stop the service
echo [1/5] Stopping FocasMonitor service...
sc stop FocasMonitor >nul 2>&1
timeout /t 5 /nobreak >nul
taskkill /F /IM FocasMonitor.exe >nul 2>&1
timeout /t 3 /nobreak >nul
echo       Done.
echo.

:: Clean old install
echo [2/5] Cleaning old install at C:\FocasMonitor...
if exist "C:\FocasMonitor" (
    rmdir /S /Q "C:\FocasMonitor"
    timeout /t 2 /nobreak >nul
)
mkdir "C:\FocasMonitor"
echo       Done.
echo.

:: Create data directories
echo [3/5] Creating data directories...
if not exist "C:\FASData" mkdir "C:\FASData"
if not exist "C:\FASData\logs" mkdir "C:\FASData\logs"
echo       Done.
echo.

:: Copy fresh build
echo [4/5] Copying new files to C:\FocasMonitor...
xcopy /E /Y "%~dp0*" "C:\FocasMonitor\" >nul
if %errorLevel% neq 0 (
    echo       ERROR: Copy failed!
    pause
    exit /b 1
)
echo       Done.
echo.

:: Register and start service
echo [5/5] Starting FocasMonitor service...
sc query FocasMonitor >nul 2>&1
if %errorLevel% neq 0 (
    echo       Service not found, creating...
    sc create "FocasMonitor" binPath= "C:\FocasMonitor\FocasMonitor.exe" start= auto DisplayName= "FOCAS Machine Monitor"
    sc description "FocasMonitor" "Monitors FANUC CNC machines via FOCAS protocol"
    timeout /t 2 /nobreak >nul
)
sc start FocasMonitor >nul 2>&1
timeout /t 5 /nobreak >nul

:: Verify
sc query FocasMonitor | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo.
    echo =====================================================
    echo  SUCCESS! Service is running.
    echo =====================================================
) else (
    echo.
    echo  Service did not start. Trying to run manually...
    echo  Close this window to stop it.
    echo.
    "C:\FocasMonitor\FocasMonitor.exe"
)

echo.
pause
