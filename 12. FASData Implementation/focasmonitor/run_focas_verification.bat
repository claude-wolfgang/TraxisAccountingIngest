@echo off
REM Wrapper invoked by Task Scheduler. %~dp0 resolves to this folder, so the
REM script path doesn't need to be quoted in schtasks /TR.
python "%~dp0report_focas_verification.py"
