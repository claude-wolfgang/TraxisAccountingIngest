@echo off
REM ============================================================================
REM  srv-01 step 01 -- Install OpenSSH Server + add Claude's pubkey
REM  ============================================================================
REM  Right-click -> "Run as administrator"
REM
REM  Copy BOTH 01_install_ssh.bat and 01_install_ssh.ps1 to srv-01 first
REM  (RDP clipboard, USB stick, or \\<main-pc>\<share> -- your pick).
REM  Run this .bat from the folder where both files live.
REM ============================================================================

REM --- Detect admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Run as administrator.
    echo  Right-click this .bat -^> "Run as administrator"
    echo.
    pause
    exit /b 1
)

REM --- Run the paired PS1 ---
set "PS1=%~dp001_install_ssh.ps1"
if not exist "%PS1%" (
    echo  ERROR: Cannot find paired script:
    echo    %PS1%
    echo  Make sure 01_install_ssh.ps1 is in the same folder as this .bat.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

echo.
pause
