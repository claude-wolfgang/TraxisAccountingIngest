@echo off
REM Traxis Service Overseer v1.0
REM =============================
REM Launches the overseer which manages and monitors all Traxis services.
REM Open http://localhost:8060 in your browser after running.

echo ============================================
echo  Traxis Service Overseer v1.0
echo ============================================
echo.
echo Starting overseer at http://localhost:8060
echo Press Ctrl+C to stop.
echo.

"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe" "%~dp0overseer.py"

pause
