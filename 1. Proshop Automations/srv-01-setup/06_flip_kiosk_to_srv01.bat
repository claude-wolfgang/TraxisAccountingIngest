@echo off
REM =============================================================================
REM srv-01 step 06 -- Flip the .141 tool kiosk PC's backend URL from .71 to .161.
REM
REM Run on the kiosk PC (10.1.1.141). Double-click.
REM
REM What it does:
REM   1. Edits %USERPROFILE%\.traxis.env to add/update
REM      TOOLKIOSK_BACKEND_URL=http://10.1.1.161:5001
REM   2. Tries to enable RDP (needs admin -- skips with a warning if not).
REM   3. Asks whether to reboot now so kiosk_launcher picks up the new URL.
REM
REM Safe to re-run. Idempotent. No network changes other than RDP firewall rule.
REM =============================================================================

setlocal

echo.
echo ============================================
echo  Traxis Tool Kiosk: flip backend to srv-01
echo ============================================
echo.
echo This script will:
echo   1. Set TOOLKIOSK_BACKEND_URL=http://10.1.1.161:5001 in %%USERPROFILE%%\.traxis.env
echo   2. Try to enable Remote Desktop (RDP) so future changes can be remote.
echo   3. Offer to reboot so the kiosk launcher picks up the new URL.
echo.
pause

echo.
echo --- Step 1: Update .traxis.env ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$f = \"$env:USERPROFILE\.traxis.env\";" ^
  "if (-not (Test-Path $f)) { New-Item -ItemType File -Path $f | Out-Null; Write-Host '  Created new .traxis.env' }" ^
  "else { Write-Host \"  Found existing $f\" };" ^
  "$content = Get-Content $f -Raw -ErrorAction SilentlyContinue;" ^
  "if (-not $content) { $content = '' };" ^
  "$newline = 'TOOLKIOSK_BACKEND_URL=http://10.1.1.161:5001';" ^
  "if ($content -match '(?m)^TOOLKIOSK_BACKEND_URL=.*$') {" ^
  "  $content = $content -replace '(?m)^TOOLKIOSK_BACKEND_URL=.*$', $newline;" ^
  "  Write-Host '  Updated existing TOOLKIOSK_BACKEND_URL line'" ^
  "} else {" ^
  "  if ($content -and -not $content.EndsWith([Environment]::NewLine)) { $content += [Environment]::NewLine };" ^
  "  $content += $newline + [Environment]::NewLine;" ^
  "  Write-Host '  Appended new TOOLKIOSK_BACKEND_URL line'" ^
  "};" ^
  "Set-Content -Path $f -Value $content -NoNewline;" ^
  "Write-Host '';" ^
  "Write-Host '  Current contents:';" ^
  "Get-Content $f | ForEach-Object { Write-Host \"    $_\" }"

if errorlevel 1 (
    echo.
    echo [ERROR] PowerShell failed during step 1. See output above.
    pause
    exit /b 1
)

echo.
echo --- Step 2: Try to enable Remote Desktop ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   [SKIP] Not running as administrator. RDP NOT enabled.
    echo          Right-click this .bat and "Run as administrator" to enable RDP
    echo          on a future run, or do it manually:
    echo            Settings -^> System -^> Remote Desktop -^> Enable
) else (
    echo   Running as administrator. Enabling RDP...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0;" ^
      "Enable-NetFirewallRule -DisplayGroup 'Remote Desktop';" ^
      "Write-Host '  RDP enabled. Test from another PC with: mstsc /v:10.1.1.141'"
)

echo.
echo --- Step 3: Restart the kiosk to pick up the new URL ---
echo.
echo The kiosk_launcher reads .traxis.env at startup. Easiest is a reboot.
echo Alternatives:
echo   * Reboot now             (recommended -- cleanest)
echo   * Skip and reboot later  (kiosk will keep pointing at .71 until then)
echo   * Run scheduled task     (only if TraxisToolKiosk is registered)
echo.
choice /c RSL /n /m "Reboot (R), Skip (S), or run scheduled task (L)? "
if errorlevel 3 (
    echo.
    echo Running scheduled task...
    schtasks /Run /TN TraxisToolKiosk
    if errorlevel 1 (
        echo   [WARN] schtasks /Run failed. Reboot or run kiosk_launcher.py manually.
    )
    echo Done. Verify the kiosk URL bar shows 10.1.1.161 once Chrome loads.
    pause
    exit /b 0
)
if errorlevel 2 (
    echo.
    echo Skipped. Remember to reboot to activate the new URL.
    pause
    exit /b 0
)
if errorlevel 1 (
    echo.
    echo Rebooting in 10 seconds. Press Ctrl+C in this window to cancel.
    timeout /t 10
    shutdown /r /t 0
)

endlocal
