@echo off
title Compressor Web Server
echo ============================================
echo   Air Compressor Web Server - Restart
echo ============================================
echo.

REM Kill any existing instance
echo Stopping any running compressor_web.py...
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /fo list 2^>nul ^| findstr "PID"') do (
    wmic process where "ProcessId=%%a" get CommandLine 2>nul | findstr /i "compressor_web" >nul && (
        echo   Killing PID %%a
        taskkill /pid %%a /f >nul 2>&1
    )
)
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python3.exe" /fo list 2^>nul ^| findstr "PID"') do (
    wmic process where "ProcessId=%%a" get CommandLine 2>nul | findstr /i "compressor_web" >nul && (
        echo   Killing PID %%a
        taskkill /pid %%a /f >nul 2>&1
    )
)
echo Done.
echo.

REM Change to the script directory
cd /d "%~dp0"

REM Find Python
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
) else (
    where python3 >nul 2>&1
    if %errorlevel%==0 (
        set PYTHON=python3
    ) else (
        echo ERROR: Python not found in PATH!
        echo Install Python or add it to your PATH.
        pause
        exit /b 1
    )
)

echo Using: %PYTHON%
%PYTHON% --version
echo.

REM Check dependencies
%PYTHON% -c "import flask, pymodbus" 2>nul
if %errorlevel% neq 0 (
    echo Missing dependencies. Installing flask and pymodbus...
    %PYTHON% -m pip install flask pymodbus
    echo.
)

echo Starting compressor_web.py on port 8085...
echo Press Ctrl+C to stop.
echo ============================================
echo.
%PYTHON% compressor_web.py
pause
