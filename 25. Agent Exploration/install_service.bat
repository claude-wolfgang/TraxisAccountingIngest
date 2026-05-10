@echo off
REM ============================================================================
REM  Install TraxisAgent as a Windows Service using NSSM
REM  Run as Administrator: right-click -> "Run as administrator"
REM ============================================================================

setlocal enabledelayedexpansion

set SERVICE_NAME=TraxisAgent
set SCRIPT_DIR=%~dp0
set WRAPPER_SCRIPT=%SCRIPT_DIR%service_wrapper.py
set LOG_DIR=%SCRIPT_DIR%logs

REM -- Find NSSM --
set NSSM_PATH=
for %%P in (
    "D:\Dropbox\MACHINE COMM Traxis\Graf\services\nssm-2.24\win64\nssm.exe"
    "%~dp0..\..\Graf\services\nssm-2.24\win64\nssm.exe"
) do (
    if exist %%P (
        set "NSSM_PATH=%%~P"
        goto :found_nssm
    )
)

echo ERROR: nssm.exe not found. Checked:
echo   D:\Dropbox\MACHINE COMM Traxis\Graf\services\nssm-2.24\win64\nssm.exe
echo   %~dp0..\..\Graf\services\nssm-2.24\win64\nssm.exe
echo.
echo Download from https://nssm.cc/download and update this script.
pause
exit /b 1

:found_nssm
echo Found NSSM: %NSSM_PATH%

REM -- Find Python --
set PYTHON_PATH=
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where python') do (
        set "PYTHON_PATH=%%i"
        goto :found_python
    )
)
echo ERROR: Python not found on PATH.
pause
exit /b 1

:found_python
echo Found Python: %PYTHON_PATH%

REM -- Check wrapper script exists --
if not exist "%WRAPPER_SCRIPT%" (
    echo ERROR: service_wrapper.py not found at %WRAPPER_SCRIPT%
    pause
    exit /b 1
)

REM -- Create logs directory --
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM -- Check if service already exists --
"%NSSM_PATH%" status %SERVICE_NAME% >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo Service %SERVICE_NAME% already exists. Removing first...
    "%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
    timeout /t 3 /nobreak >nul
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm
    timeout /t 2 /nobreak >nul
)

REM -- Install service --
echo.
echo Installing %SERVICE_NAME% ...

"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%"
"%NSSM_PATH%" set %SERVICE_NAME% AppParameters "\"%WRAPPER_SCRIPT%\""
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "Traxis Agent Service"
"%NSSM_PATH%" set %SERVICE_NAME% Description "Leader-elected service wrapper for Traxis audit, Telegram bot, reminders, and project scanner."
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START

REM -- Logging (stdout + stderr to log file) --
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%LOG_DIR%\service_wrapper.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%LOG_DIR%\service_wrapper.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdoutCreationDisposition 4
"%NSSM_PATH%" set %SERVICE_NAME% AppStderrCreationDisposition 4
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 5242880

REM -- Restart on crash (10s delay) --
"%NSSM_PATH%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 10000

REM -- Graceful shutdown (send Ctrl+C, wait 15s before kill) --
"%NSSM_PATH%" set %SERVICE_NAME% AppStopMethodSkip 0
"%NSSM_PATH%" set %SERVICE_NAME% AppStopMethodConsole 15000
"%NSSM_PATH%" set %SERVICE_NAME% AppStopMethodWindow 5000
"%NSSM_PATH%" set %SERVICE_NAME% AppStopMethodThreads 5000

echo.
echo ============================================================================
echo  Service installed successfully!
echo.
echo  To start:    net start %SERVICE_NAME%
echo  To stop:     net stop %SERVICE_NAME%
echo  To remove:   "%NSSM_PATH%" remove %SERVICE_NAME% confirm
echo  To edit:     "%NSSM_PATH%" edit %SERVICE_NAME%
echo  Status:      python "%WRAPPER_SCRIPT%" --status
echo  Logs:        %LOG_DIR%\service_wrapper.log
echo ============================================================================
echo.

set /p START_NOW="Start the service now? (Y/N): "
if /i "%START_NOW%"=="Y" (
    echo Starting %SERVICE_NAME% ...
    net start %SERVICE_NAME%
    if %errorlevel% equ 0 (
        echo Service started successfully.
        timeout /t 5 /nobreak >nul
        echo.
        echo Current status:
        python "%WRAPPER_SCRIPT%" --status
    ) else (
        echo Failed to start. Check logs at: %LOG_DIR%\service_wrapper.log
    )
)

pause
