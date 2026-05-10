@echo off
REM Deploy TraxisTransfer to workstation
setlocal

set INSTALL_DIR=C:\FASData\TraxisTransfer
set SOURCE_DIR=%~dp0..

echo Installing TraxisTransfer to %INSTALL_DIR%...

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy executable
if exist "%SOURCE_DIR%\dist\TraxisTransfer.exe" (
    copy /Y "%SOURCE_DIR%\dist\TraxisTransfer.exe" "%INSTALL_DIR%\"
) else (
    echo ERROR: dist\TraxisTransfer.exe not found. Run build.bat first.
    pause
    exit /b 1
)

REM Copy config
copy /Y "%SOURCE_DIR%\machines.json" "%INSTALL_DIR%\"

echo.
echo Installation complete.
echo Location: %INSTALL_DIR%\TraxisTransfer.exe
pause
