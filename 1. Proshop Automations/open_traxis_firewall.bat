@echo off
:: Opens Windows Firewall ports for Traxis services on Collector PC (10.1.1.71)
:: Also creates a scheduled task to re-apply rules after GPO refresh / reboot
:: Must be run as Administrator
::
:: Usage:
::   open_traxis_firewall.bat          — Add rules + create scheduled task (interactive)
::   open_traxis_firewall.bat /apply   — Add rules only, no output (used by scheduled task)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click and select "Run as administrator".
    pause
    exit /b 1
)

set "SILENT=0"
if /i "%~1"=="/apply" set "SILENT=1"

if "%SILENT%"=="0" echo ============================================
if "%SILENT%"=="0" echo  Traxis Firewall Setup — Collector PC
if "%SILENT%"=="0" echo ============================================
if "%SILENT%"=="0" echo.

:: ── Step 1: Ensure firewall is ON ──
if "%SILENT%"=="0" echo Ensuring firewall is enabled...
netsh advfirewall set allprofiles state on >nul 2>&1

:: ── Step 2: Remove old rules (clean slate) ──
if "%SILENT%"=="0" echo Removing old Traxis firewall rules...
netsh advfirewall firewall delete rule name="Traxis Time Tracker (8050)" >nul 2>&1
netsh advfirewall firewall delete rule name="Traxis Overseer (8060)" >nul 2>&1
netsh advfirewall firewall delete rule name="Traxis FASData Dashboard (8070)" >nul 2>&1
netsh advfirewall firewall delete rule name="Traxis Services (TCP)" >nul 2>&1
netsh advfirewall firewall delete rule name="Traxis Services (Ping)" >nul 2>&1

:: ── Step 3: Add firewall rules scoped to LAN ──
if "%SILENT%"=="0" echo Adding firewall rules for ports 5000-8101 (LAN only)...

netsh advfirewall firewall add rule ^
    name="Traxis Services (TCP)" ^
    dir=in action=allow protocol=TCP ^
    localport=5000-8101 ^
    remoteip=10.1.1.0/24 ^
    description="Traxis Overseer, Bridge, dashboards, Telegram, Agent Scheduler"

netsh advfirewall firewall add rule ^
    name="Traxis Services (Ping)" ^
    dir=in action=allow protocol=ICMPv4 ^
    remoteip=10.1.1.0/24 ^
    description="Allow ping from LAN"

if "%SILENT%"=="0" echo Firewall rules applied.
if "%SILENT%"=="0" echo.

:: ── Step 4: Create scheduled task to survive GPO refresh ──
if "%SILENT%"=="1" goto :done

echo Creating scheduled task "TraxisFirewall" to re-apply on boot...

:: Get the full path to this script
set "SCRIPT_PATH=%~f0"

:: Delete existing task if present
schtasks /delete /tn "TraxisFirewall" /f >nul 2>&1

:: Create task: runs at system startup as SYSTEM with highest privileges
schtasks /create ^
    /tn "TraxisFirewall" ^
    /tr "\"%SCRIPT_PATH%\" /apply" ^
    /sc onstart ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if %errorlevel% equ 0 (
    echo Scheduled task created successfully.
) else (
    echo WARNING: Could not create scheduled task. Rules will work until next GPO refresh.
)

echo.
echo ============================================
echo  Summary
echo ============================================
echo  Firewall:      ON (all profiles)
echo  Ports opened:  5000-8101 TCP (LAN only)
echo  Ping:          Allowed from 10.1.1.0/24
echo  Scheduled:     Re-applied on every reboot
echo  Scope:         10.1.1.0/24 only
echo ============================================
echo.

:: ── Verify ──
echo Current Traxis firewall rules:
netsh advfirewall firewall show rule name="Traxis Services (TCP)" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Traxis Services (TCP) — ports 5000-8101
) else (
    echo   [FAIL] TCP rule not found
)
netsh advfirewall firewall show rule name="Traxis Services (Ping)" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Traxis Services (Ping) — ICMPv4
) else (
    echo   [FAIL] Ping rule not found
)

echo.
echo Test from another machine with:
echo   curl http://10.1.1.71:8060/
echo.
pause

:done
