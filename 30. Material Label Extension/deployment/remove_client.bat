@echo off
REM Traxis Label Printer — Remove extension from this PC
REM Run as Administrator
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set ID_FILE=%SCRIPT_DIR%extension_id.txt

if not exist "%ID_FILE%" (
    echo ERROR: extension_id.txt not found.
    pause
    exit /b 1
)
set /p EXT_ID=<"%ID_FILE%"

set REG_PATH=HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist

echo Removing Traxis Label Printer from Chrome policies...
set FOUND=0

for /l %%i in (1,1,20) do (
    reg query "%REG_PATH%" /v %%i 2>nul | findstr /c:"!EXT_ID!" >nul
    if not errorlevel 1 (
        reg delete "%REG_PATH%" /v %%i /f >nul
        echo   Removed from slot %%i.
        set FOUND=1
    )
)

if !FOUND!==0 echo   Extension not found in Chrome policies.
echo.
echo Done. Restart Chrome to apply.
pause
