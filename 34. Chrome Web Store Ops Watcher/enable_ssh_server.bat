@echo off
REM ---------------------------------------------------------------------
REM  Enable OpenSSH Server on this Windows machine and authorize the
REM  Superuser@.178 control key so Claude can drive it remotely.
REM
REM  Self-elevates to admin via UAC. Idempotent -- safe to re-run.
REM
REM  Public key fingerprint (verify): SHA256:Pl/io87NDFvXXNL2Tk6NoKNyxj1hDefae7TVV4t84P4
REM ---------------------------------------------------------------------

REM Self-elevate if not running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting admin elevation -- click Yes on the UAC prompt...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

setlocal

set "PUBKEY=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFf13IcMcK5EEzGZKzBBW6dbk1FETN0y/7adhg2FWnqU Superuser@.178-claude-remote-control"
set "USER_SSH_DIR=%USERPROFILE%\.ssh"
set "USER_KEYS=%USER_SSH_DIR%\authorized_keys"
set "ADMIN_KEYS=%PROGRAMDATA%\ssh\administrators_authorized_keys"

echo.
echo === Step 1: Install OpenSSH Server (may take 30-60 sec) ===
powershell -NoProfile -Command "if ((Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0').State -ne 'Installed') { Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 } else { Write-Host '  Already installed.' }"

echo.
echo === Step 2: Start and enable sshd service ===
sc config sshd start= auto >nul
net start sshd 2>nul
if %errorlevel% equ 0 (
    echo   sshd started.
) else (
    echo   sshd already running ^(or just started by Add-WindowsCapability^).
)

echo.
echo === Step 3: Open firewall port 22 ===
netsh advfirewall firewall show rule name="OpenSSH-Server-In-TCP" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="OpenSSH-Server-In-TCP" dir=in action=allow protocol=TCP localport=22 >nul
    echo   Rule added.
) else (
    echo   Rule already exists.
)

echo.
echo === Step 4: Authorize Superuser@.178 public key ===

REM User authorized_keys (works for non-admin users)
if not exist "%USER_SSH_DIR%" mkdir "%USER_SSH_DIR%"
findstr /C:"%PUBKEY%" "%USER_KEYS%" >nul 2>&1
if errorlevel 1 (
    echo %PUBKEY%>>"%USER_KEYS%"
    icacls "%USER_KEYS%" /inheritance:r /grant "%USERNAME%:F" >nul
    echo   Added to %USER_KEYS%
) else (
    echo   Already in %USER_KEYS%
)

REM administrators_authorized_keys (required for admin users on default sshd_config)
if not exist "%PROGRAMDATA%\ssh" mkdir "%PROGRAMDATA%\ssh"
findstr /C:"%PUBKEY%" "%ADMIN_KEYS%" >nul 2>&1
if errorlevel 1 (
    echo %PUBKEY%>>"%ADMIN_KEYS%"
    icacls "%ADMIN_KEYS%" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" >nul
    echo   Added to %ADMIN_KEYS%
) else (
    echo   Already in %ADMIN_KEYS%
)

echo.
echo === Done ===
echo From .178 I can now run:
echo   ssh TRAXIS@10.1.1.71 hostname
echo.
pause

endlocal
