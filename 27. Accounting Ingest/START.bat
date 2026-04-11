@echo off
cd /d "%~dp0"
echo Starting Traxis Accounting Ingest Tool...
python accounting_ingest.py
pause
