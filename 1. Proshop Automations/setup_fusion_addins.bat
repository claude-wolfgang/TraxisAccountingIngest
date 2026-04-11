@echo off
REM ============================================================================
REM  Traxis Fusion 360 Add-in & Script Installer
REM  ============================================================================
REM  Creates symlinks from Dropbox source folders into Fusion 360's local
REM  AddIns and Scripts directories. Run on each programmer's machine.
REM
REM  MUST be run as Administrator (symlinks require elevated privileges).
REM  Close Fusion 360 before running.
REM
REM  Machines:
REM    TRAXIS     - Dropbox at D:\Dropbox\MACHINE COMM Traxis\
REM    Traxis MFG - Dropbox at C:\Users\Traxis MFG\Dropbox\MACHINE COMM Traxis\
REM
REM  Last updated: 2026-03-02
REM ============================================================================

echo.
echo  ============================================
echo   Traxis Fusion 360 Add-in Installer
echo  ============================================
echo.

REM --- Check for admin rights ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: This script must be run as Administrator.
    echo  Right-click the .bat file and choose "Run as administrator"
    echo.
    pause
    exit /b 1
)

REM --- Check Fusion is not running ---
tasklist /FI "IMAGENAME eq Fusion360.exe" 2>NUL | find /I "Fusion360.exe" >NUL
if %errorlevel% equ 0 (
    echo  ERROR: Fusion 360 is running. Please close it first.
    echo.
    pause
    exit /b 1
)

REM --- Auto-detect Dropbox path ---
set "DROPBOX="

if exist "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects" (
    set "DROPBOX=D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects"
    goto :found_dropbox
)
if exist "C:\Users\%USERNAME%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects" (
    set "DROPBOX=C:\Users\%USERNAME%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects"
    goto :found_dropbox
)
if exist "%USERPROFILE%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects" (
    set "DROPBOX=%USERPROFILE%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects"
    goto :found_dropbox
)

echo  ERROR: Could not find Dropbox project folder.
echo  Checked:
echo    D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects
echo    C:\Users\%USERNAME%\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects
echo.
pause
exit /b 1

:found_dropbox
echo  Dropbox:  %DROPBOX%

set "ADDINS=%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns"
set "SCRIPTS=%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts"

REM --- Verify Fusion folders exist ---
if not exist "%ADDINS%" (
    echo  ERROR: Fusion AddIns folder not found at:
    echo    %ADDINS%
    echo  Is Fusion 360 installed? Run Fusion once first, then retry.
    echo.
    pause
    exit /b 1
)
if not exist "%SCRIPTS%" mkdir "%SCRIPTS%"

echo  AddIns:  %ADDINS%
echo  Scripts: %SCRIPTS%
echo.

REM --- Setup credentials file ---
echo  --- Credentials ---
set "CREDS_SRC=%DROPBOX%\1. Proshop Automations\.traxis.env"
set "CREDS_DST=C:\Users\%USERNAME%\.traxis.env"
if exist "%CREDS_DST%" (
    echo  [OK]   .traxis.env already exists at %CREDS_DST%
) else if exist "%CREDS_SRC%" (
    copy "%CREDS_SRC%" "%CREDS_DST%" >nul
    echo  [NEW]  .traxis.env copied to %CREDS_DST%
) else (
    echo  [SKIP] No .traxis.env found in source folder
)
echo.

REM --- Setup ProgrammingTimer programmer name ---
echo  --- Programmer Name ---
set "TIMER_LOCAL_DIR=%APPDATA%\Traxis\ProgrammingTimer"
set "TIMER_LOCAL_CFG=%TIMER_LOCAL_DIR%\timer_config.local.json"
if not exist "%TIMER_LOCAL_DIR%" mkdir "%TIMER_LOCAL_DIR%"
if exist "%TIMER_LOCAL_CFG%" (
    echo  [OK]   Programmer name already configured
) else (
    echo  This machine: %COMPUTERNAME% (%USERNAME%)
    echo  ProgrammingTimer needs your name to tag time logs.
    set /p PROG_NAME="  Enter your name: "
    echo {"programmer_name": "%PROG_NAME%"} > "%TIMER_LOCAL_CFG%"
    echo  [NEW]  Set programmer name to "%PROG_NAME%"
)
echo.

echo  ============================================
echo   Creating symlinks...
echo  ============================================
echo.

set ERRORS=0
set CREATED=0
set SKIPPED=0

REM === ADD-INS ================================================================

call :link "%ADDINS%" "ProgrammingTimer"      "%DROPBOX%\1. Proshop Automations\ProgrammingTimer"
call :link "%ADDINS%" "ProShopBridge"          "%DROPBOX%\1. Proshop Automations\ProShopBridge"
call :link "%ADDINS%" "FusionToolAuditor"      "%DROPBOX%\16. Fusion Tool Library Product ID Changer\FusionToolAuditor"
call :link "%ADDINS%" "ToolRenumber"            "%DROPBOX%\1. Proshop Automations\ToolRenumber"
REM Remove old TraxisPostProcessor symlink (renamed to TraxisProgramManager)
if exist "%ADDINS%\TraxisPostProcessor" (
    rmdir "%ADDINS%\TraxisPostProcessor" 2>NUL
    echo  [DEL]  TraxisPostProcessor -- removed (renamed to TraxisProgramManager)
)
REM Remove old ProShopConnector symlink (replaced by ProShopBridge)
if exist "%ADDINS%\ProShopConnector" (
    rmdir "%ADDINS%\ProShopConnector" 2>NUL
    echo  [DEL]  ProShopConnector -- removed (replaced by ProShopBridge)
)
call :link "%ADDINS%" "TraxisProgramManager"    "%DROPBOX%\12. FASData Implementation\TraxisProgramManager"
call :link "%ADDINS%" "TraxisCapture"          "%DROPBOX%\12. FASData Implementation\TraxisCapture"

REM === SCRIPTS ================================================================

call :link "%SCRIPTS%" "ExportToolLibrary"     "%DROPBOX%\16. Fusion Tool Library Product ID Changer\ExportToolLibrary"

echo.
echo  ============================================
echo   Done!  Created: %CREATED%  Skipped: %SKIPPED%  Errors: %ERRORS%
echo  ============================================
echo.
echo  Next steps:
echo   1. Open Fusion 360
echo   2. Press Shift+S to open Scripts and Add-Ins
echo   3. Enable the add-ins you want to use
echo.
pause
exit /b 0

REM ============================================================================
:link
REM  %~1 = parent dir (AddIns or Scripts)
REM  %~2 = link name
REM  %~3 = source path in Dropbox
REM ============================================================================
set "LINK=%~1\%~2"
set "TARGET=%~3"

if not exist "%TARGET%" (
    echo  [SKIP] %~2 -- source not found
    set /a SKIPPED+=1
    goto :eof
)

if exist "%LINK%" (
    REM Remove existing (symlink or local copy) and recreate
    rmdir "%LINK%" 2>NUL
    rmdir /s /q "%LINK%" 2>NUL
)

mklink /D "%LINK%" "%TARGET%" >NUL 2>&1
if %errorlevel% equ 0 (
    echo  [NEW]  %~2 -- linked
    set /a CREATED+=1
) else (
    echo  [ERR]  %~2 -- mklink failed
    set /a ERRORS+=1
)
goto :eof
