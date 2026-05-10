@echo off
echo =====================================================
echo  FocasMonitor Update Deployment
echo  Traxis Manufacturing - %DATE%
echo =====================================================
echo.

:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges.
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
set "PUBLISH=%SCRIPT_DIR%focasmonitor\publish"
set "DEPLOY=C:\FocasMonitor"
set "DB=C:\FASData\monitoring.db"

:: Verify publish folder exists
if not exist "%PUBLISH%\FocasMonitor.exe" (
    echo ERROR: Build not found at %PUBLISH%
    echo Run 'dotnet publish' first.
    pause
    exit /b 1
)

:: Step 1: Stop service
echo [1/4] Stopping FocasMonitor service...
sc stop FocasMonitor >nul 2>&1
timeout /t 3 /nobreak >nul
sc query FocasMonitor | find "STOPPED" >nul
if %errorLevel% neq 0 (
    echo   Waiting for service to stop...
    timeout /t 5 /nobreak >nul
)
echo   Service stopped.
echo.

:: Step 2: Migrate database
echo [2/4] Migrating database...
python "%SCRIPT_DIR%migrate_db.py" --db "%DB%"
if %errorLevel% neq 0 (
    echo ERROR: Migration failed!
    echo Starting old service back up...
    sc start FocasMonitor
    pause
    exit /b 1
)
echo.

:: Step 3: Deploy new build
echo [3/4] Deploying new build to %DEPLOY%...
xcopy /E /Y "%PUBLISH%\*" "%DEPLOY%\" >nul
echo   Files copied.
echo.

:: Step 4: Start service
echo [4/4] Starting FocasMonitor service...
sc start FocasMonitor >nul 2>&1
timeout /t 3 /nobreak >nul
sc query FocasMonitor | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo   Service started successfully!
) else (
    echo   WARNING: Service may not have started. Check with:
    echo     sc query FocasMonitor
)

echo.
echo =====================================================
echo  Deployment Complete!
echo =====================================================
echo.
echo  Next: Wait 60 seconds, then verify new data with:
echo    python session_bridge.py
echo.
pause
