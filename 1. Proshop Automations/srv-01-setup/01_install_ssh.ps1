# =============================================================================
# srv-01 step 01 -- Install OpenSSH Server, set PowerShell as default shell,
# add Claude's pubkey for remote control. Invoked by 01_install_ssh.bat.
# =============================================================================

$ErrorActionPreference = 'Stop'

$CLAUDE_PUBKEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFf13IcMcK5EEzGZKzBBW6dbk1FETN0y/7adhg2FWnqU Superuser@.178-claude-remote-control'

Write-Host ''
Write-Host '============================================'
Write-Host '  srv-01 SSH Bootstrap'
Write-Host '============================================'
Write-Host "  Computer: $env:COMPUTERNAME"
Write-Host "  User:     $env:USERNAME"
Write-Host ''

# --- 1. Install OpenSSH Server ---------------------------------------------
Write-Host '--- Installing OpenSSH Server ---'
$cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' | Select-Object -First 1
if ($cap.State -eq 'Installed') {
    Write-Host '[OK]  Already installed'
} else {
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
    Write-Host '[NEW] OpenSSH Server installed'
}

# --- 2. Service: enable + start --------------------------------------------
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service sshd).Status -ne 'Running') { Start-Service sshd }
Write-Host '[OK]  sshd running, set to auto-start'

# --- 3. Firewall rule ------------------------------------------------------
if (-not (Get-NetFirewallRule -Name 'sshd' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'sshd' -DisplayName 'OpenSSH Server' `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow `
        -LocalPort 22 | Out-Null
    Write-Host '[NEW] Firewall rule added (TCP 22 inbound)'
} else {
    Write-Host '[OK]  Firewall rule already present'
}

# --- 4. Add Claude pubkey to authorized_keys -------------------------------
Write-Host ''
Write-Host '--- Adding Claude pubkey ---'
$isAdmin = (whoami /groups) -match 'S-1-5-32-544'

if ($isAdmin) {
    $keyfile = 'C:\ProgramData\ssh\administrators_authorized_keys'
    Write-Host "  User is in Administrators group; using $keyfile"
} else {
    $sshDir = Join-Path $env:USERPROFILE '.ssh'
    if (-not (Test-Path $sshDir)) {
        New-Item -ItemType Directory -Path $sshDir | Out-Null
    }
    $keyfile = Join-Path $sshDir 'authorized_keys'
    Write-Host "  User is non-admin; using $keyfile"
}

$existing = if (Test-Path $keyfile) { Get-Content $keyfile -ErrorAction SilentlyContinue } else { @() }
if ($existing -contains $CLAUDE_PUBKEY) {
    Write-Host '[OK]  Pubkey already present'
} else {
    Add-Content -Path $keyfile -Value $CLAUDE_PUBKEY
    Write-Host "[NEW] Pubkey appended to $keyfile"
}

# --- 5. Lock down ACLs (required by Windows OpenSSH) -----------------------
if ($isAdmin) {
    icacls $keyfile /inheritance:r | Out-Null
    icacls $keyfile /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null
} else {
    icacls $keyfile /inheritance:r | Out-Null
    icacls $keyfile /grant "${env:USERNAME}:F" /grant 'SYSTEM:F' | Out-Null
}
Write-Host '[OK]  authorized_keys ACLs locked down'

# --- 6. Set PowerShell as default shell ------------------------------------
Write-Host ''
Write-Host '--- Default shell ---'
$currentShell = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -ErrorAction SilentlyContinue).DefaultShell
$psPath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
if ($currentShell -eq $psPath) {
    Write-Host '[OK]  Default shell already PowerShell'
} else {
    New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell `
        -Value $psPath -PropertyType String -Force | Out-Null
    Write-Host "[NEW] Default shell -> PowerShell"
}

# --- 7. Restart sshd to pick up shell change -------------------------------
Restart-Service sshd
Write-Host '[OK]  sshd restarted'

# --- Summary ---------------------------------------------------------------
$ips = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -ExpandProperty IPAddress) -join ', '

Write-Host ''
Write-Host '============================================'
Write-Host '  Connection info -- share with Claude:'
Write-Host '============================================'
Write-Host "  user: $env:USERNAME"
Write-Host "  host: $env:COMPUTERNAME"
Write-Host "  IPs:  $ips"
Write-Host '============================================'
Write-Host ''
Write-Host 'Next: tell Claude the username + IP and Claude can SSH in.'
Write-Host ''
