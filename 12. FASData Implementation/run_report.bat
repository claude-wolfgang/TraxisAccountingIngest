@echo off
:: ──────────────────────────────────────────────────────
:: FASData Utilization Report — One Click
:: Traxis Manufacturing
::
:: Double-click to generate and open the report.
:: Saves HTML to Dropbox for anyone to view.
:: ──────────────────────────────────────────────────────

echo.
echo   FASData Utilization Report
echo   ──────────────────────────
echo.

:: Analyze data, generate charts + HTML report
echo   Analyzing machine data...
"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe" "%~dp0generate_report.py" %*
if errorlevel 1 (
    echo.
    echo   ERROR: Report generation failed.
    echo   Check that monitoring.db is accessible in Dropbox.
    pause
    exit /b 1
)

:: Open the HTML report
echo.
echo   Opening report...
start "" "%~dp0utilization_report.html"
