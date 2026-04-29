@echo off
REM Traxis Label Printer — Deploy extension to this PC via Chrome policy
REM Run as Administrator on each shop computer.
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set HOST_URL=http://10.1.1.71:8484
set ID_FILE=%SCRIPT_DIR%extension_id.txt

if not exist "%ID_FILE%" (
    echo ERROR: extension_id.txt not found. Run build.py first.
    pause
    exit /b 1
)
set /p EXT_ID=<"%ID_FILE%"

set REG_PATH=HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist
set VALUE=%EXT_ID%;%HOST_URL%/update_manifest.xml

echo Deploying Traxis Label Printer...
echo   ID: %EXT_ID%

REM Ensure registry key exists
reg add "%REG_PATH%" /f >nul 2>nul

REM Check if already registered
reg query "%REG_PATH%" 2>nul | findstr /c:"%EXT_ID%" >nul
if not errorlevel 1 (
    echo Already deployed on this PC.
    pause
    exit /b 0
)

REM Find next available slot
set SLOT=1
:findslot
reg query "%REG_PATH%" /v !SLOT! >nul 2>nul
if not errorlevel 1 (
    set /a SLOT+=1
    if !SLOT! leq 20 goto findslot
    echo ERROR: No available registry slot.
    pause
    exit /b 1
)

reg add "%REG_PATH%" /v !SLOT! /t REG_SZ /d "%VALUE%" /f

if !errorlevel!==0 (
    echo.
    echo SUCCESS: Extension deployed in slot !SLOT!.
    echo Restart Chrome on this PC to install.
) else (
    echo ERROR: Failed to write registry. Run as Administrator.
)

pause
