@echo off
echo Linking TraxisCapture add-in...

set "LINK=%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\TraxisCapture"
set "TARGET=%~dp0TraxisCapture"

if exist "%LINK%" (
    rmdir "%LINK%" 2>NUL
    echo Removed old link.
)

mklink /D "%LINK%" "%TARGET%"
if %errorlevel% equ 0 (
    echo SUCCESS: Symlink created.
    echo.
    dir "%LINK%"
) else (
    echo FAILED: mklink requires admin. Right-click this .bat and Run as administrator.
)
echo.
pause
