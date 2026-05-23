@echo off
REM srv-01 step 05 -- Deploy P23 Air Compressor Monitor (smoke test only).
REM Idempotent; safe to re-run.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp005_deploy_p23_compressor.ps1"
pause
