@echo off
REM ============================================================================
REM  Verify FOCAS program_directory fix is capturing data
REM  ----------------------------------------------------------------------------
REM  Run this on .71 (or anywhere with read access to C:\FASData\monitoring.db).
REM  Reads everything read-only — safe to run any time.
REM
REM  Background: 2026-05-03 we replaced the broken cnc_rdprogdir2 call in
REM  MonitoringService.cs with cnc_rdprogdir3 (type=0 enumeration + type=1
REM  per-program fallback). This script checks whether the fix is actually
REM  populating the program_directory table and gives diagnostic context if not.
REM ============================================================================

echo.
echo ============================================================
echo   FOCAS Program Directory Verification
echo ============================================================
echo.

REM --- 1. Service status ---
echo [1/3] FocasMonitor service status
echo ----------------------------------------------------------------
sc query FocasMonitor 2>nul | findstr /I "STATE SERVICE_NAME"
echo.

REM --- 2. Database state via Python helper ---
echo [2/3] Database state
echo ----------------------------------------------------------------
python "%~dp0verify_program_directory.py"
echo.

REM --- 3. Recent FocasMonitor warnings/errors from the Application event log ---
echo [3/3] Recent FocasMonitor warnings/errors (last 24h)
echo ----------------------------------------------------------------
powershell -NoProfile -Command "Get-WinEvent -ProviderName FocasMonitor -MaxEvents 50 -ErrorAction SilentlyContinue | Where-Object { $_.TimeCreated -gt (Get-Date).AddHours(-24) -and $_.LevelDisplayName -ne 'Information' } | Select-Object -First 10 | Format-List TimeCreated, LevelDisplayName, Message"
echo.

echo ============================================================
echo   Done. If program_directory rows = 0 after machines have
echo   run programs today, check the warnings section above for
echo   cnc_rdprogdir3 return codes.
echo ============================================================
echo.
pause
