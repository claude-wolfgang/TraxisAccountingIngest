@echo off
REM ============================================================================
REM  srv-01 step 02 -- Baseline server tweaks
REM  ============================================================================
REM  Run AFTER 01_install_ssh.bat (no dependency, but order is the convention).
REM  Right-click -> "Run as administrator"
REM
REM  Reversible. Sets server-appropriate defaults: power, long paths, time,
REM  Defender exclusions, no auto-restart on Windows Update, etc.
REM ============================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Run as administrator.
    echo  Right-click this .bat -^> "Run as administrator"
    echo.
    pause
    exit /b 1
)

set "PS1=%~dp002_baseline.ps1"
if not exist "%PS1%" (
    echo  ERROR: Cannot find paired script:
    echo    %PS1%
    echo  Make sure 02_baseline.ps1 is in the same folder as this .bat.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

echo.
pause
