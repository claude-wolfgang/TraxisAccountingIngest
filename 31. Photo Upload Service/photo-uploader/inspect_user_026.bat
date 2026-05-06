@echo off
REM Launcher for inspect_user_page.py against user 026.
REM Keeps the window open so you can read the output.

cd /d "%~dp0"
python inspect_user_page.py --user 026 --keep-open
echo.
echo --- script finished ---
pause
