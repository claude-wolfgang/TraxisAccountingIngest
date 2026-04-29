@echo off
REM Traxis Label Printer — Deploy via Chrome Web Store policy
REM Run as Administrator on each shop computer.
REM
REM After publishing, paste the Chrome Web Store extension ID below:
setlocal enabledelayedexpansion

set CWS_EXT_ID=PASTE_EXTENSION_ID_HERE
set CWS_UPDATE=https://clients2.google.com/service/update2/crx

if "%CWS_EXT_ID%"=="PASTE_EXTENSION_ID_HERE" (
    echo ERROR: Edit this file and replace PASTE_EXTENSION_ID_HERE
    echo with the extension ID from Chrome Web Store.
    pause
    exit /b 1
)

set REG_PATH=HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist
set VALUE=%CWS_EXT_ID%;%CWS_UPDATE%

echo Deploying Traxis Label Printer (Chrome Web Store)...
echo   ID: %CWS_EXT_ID%

reg add "%REG_PATH%" /f >nul 2>nul

REM Remove any old self-hosted entries
for /l %%i in (1,1,20) do (
    reg query "%REG_PATH%" /v %%i 2>nul | findstr /c:"10.1.1.71" >nul
    if not errorlevel 1 (
        reg delete "%REG_PATH%" /v %%i /f >nul
        echo   Removed old self-hosted entry from slot %%i
    )
)

REM Check if already registered
reg query "%REG_PATH%" 2>nul | findstr /c:"%CWS_EXT_ID%" >nul
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
    echo SUCCESS: Deployed in slot !SLOT!.
    echo Restart Chrome to install.
) else (
    echo ERROR: Run as Administrator.
)

pause
