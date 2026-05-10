@echo off
echo =====================================================
echo  FOCAS Machine Monitor - Service Installation
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

:: Build the project first
echo Building the project...
cd /d "%~dp0"
dotnet publish -c Release -r win-x86 --self-contained false -o "%~dp0publish"
if %errorLevel% neq 0 (
    echo Build failed!
    pause
    exit /b 1
)

:: Copy FOCAS DLLs to publish folder
echo.
echo Copying FOCAS DLLs...
copy /Y "%~dp0*.dll" "%~dp0publish\" 2>nul

:: Create the data directories
echo.
echo Creating data directories...
mkdir "C:\FASData" 2>nul
mkdir "C:\FASData\logs" 2>nul

:: Copy config file
copy /Y "%~dp0machines.json" "%~dp0publish\"

:: Install the service
echo.
echo Installing Windows Service...
sc create "FocasMonitor" binPath= "%~dp0publish\FocasMonitor.exe" start= auto DisplayName= "FOCAS Machine Monitor"
sc description "FocasMonitor" "Monitors FANUC CNC machines via FOCAS protocol for Traxis Manufacturing"

:: Start the service
echo.
echo Starting service...
sc start "FocasMonitor"

echo.
echo =====================================================
echo  Installation Complete!
echo =====================================================
echo.
echo Service Name: FocasMonitor
echo Data Location: C:\FASData\
echo Config File: %~dp0publish\machines.json
echo.
echo To view status: sc query FocasMonitor
echo To stop:        sc stop FocasMonitor
echo To start:       sc start FocasMonitor
echo To uninstall:   Run Uninstall-Service.bat
echo.
pause
