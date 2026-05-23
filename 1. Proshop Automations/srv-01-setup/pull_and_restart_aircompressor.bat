@echo off
REM ===========================================================================
REM Run on srv-01: pull latest git + restart AirCompressor + verify.
REM Double-click, or paste path into PowerShell to invoke.
REM ===========================================================================
setlocal
set "PS1=%~dp0pull_and_restart_aircompressor.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
echo.
echo --- Done. Press any key to close. ---
pause >nul
