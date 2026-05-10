@echo off
echo === Python version ===
python --version
echo.
echo === Checking flask install ===
python -c "import flask; print('Flask OK:', flask.__version__)"
echo.
echo === Checking requests install ===
python -c "import requests; print('Requests OK:', requests.__version__)"
echo.
echo === Checking Chrome ===
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    echo Chrome OK: C:\Program Files\Google\Chrome\Application\chrome.exe
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    echo Chrome OK: C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
) else (
    echo Chrome NOT FOUND — install Chrome before running the kiosk
)
echo.
pause
