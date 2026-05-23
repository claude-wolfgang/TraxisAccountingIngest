# =============================================================================
# srv-01 step 05 -- Deploy P23 Air Compressor Monitor as a standalone service.
#
# Run-of-show:
#   1. git pull in the deploy tree
#   2. pip install flask + pymodbus + waitress for Python 3.14
#   3. Open inbound firewall for TCP 8085
#   4. Smoke-test compressor_web.py for ~10s, then stop and report findings
#
# Persistence (NSSM register) is a SEPARATE step (06) so Wolfgang can decide
# between standalone NSSM vs. Overseer-managed before committing.
#
# Idempotent. Safe to re-run.
# =============================================================================

$ErrorActionPreference = 'Continue'
function _ok($m)  { Write-Host "[OK]  $m" }
function _new($m) { Write-Host "[NEW] $m" }
function _err($m) { Write-Host "[ERR] $m" -ForegroundColor Red }
function _hdr($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }

$DeployRoot = if (Test-Path 'T:\traxis\services') { 'T:\traxis\services' } else { 'C:\traxis\services' }
$P23Dir = Join-Path $DeployRoot '23. Air Compressor communication GUI'
$Script = Join-Path $P23Dir 'compressor_web.py'
$Python = "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"

# --- 1. git pull -----------------------------------------------------------
_hdr 'git pull'
if (-not (Test-Path (Join-Path $DeployRoot '.git'))) {
    _err "$DeployRoot is not a git checkout. Aborting."
    exit 1
}
Push-Location $DeployRoot
& git pull --ff-only
if ($LASTEXITCODE -ne 0) { _err 'git pull failed' } else { _ok 'pulled' }
Pop-Location

if (-not (Test-Path $Script)) {
    _err "compressor_web.py not found at $Script"
    exit 1
}
_ok "Script at $Script"

# --- 2. pip install deps ---------------------------------------------------
_hdr 'Python deps'
if (-not (Test-Path $Python)) {
    _err "Python 3.14 not found at $Python"
    exit 1
}
& $Python -m pip install --quiet --upgrade pip
foreach ($pkg in @('flask', 'pymodbus', 'waitress')) {
    & $Python -m pip install --quiet $pkg
    if ($LASTEXITCODE -eq 0) { _ok "$pkg installed/up-to-date" } else { _err "pip install $pkg failed" }
}

# --- 3. Firewall rule ------------------------------------------------------
_hdr 'Firewall TCP 8085'
$ruleName = 'Traxis Compressor Monitor (8085)'
if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
    _ok 'Firewall rule already present'
} else {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound `
        -Protocol TCP -LocalPort 8085 -Action Allow -Profile Any | Out-Null
    _new 'Firewall rule added (TCP 8085 inbound)'
}

# --- 4. Smoke test ---------------------------------------------------------
_hdr 'Smoke test'
Write-Host '  Launching compressor_web.py (background, 15s window) ...'
$logFile = Join-Path $env:TEMP 'compressor_smoke.log'
Remove-Item $logFile -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $Python `
    -ArgumentList "`"$Script`"" `
    -WorkingDirectory $P23Dir `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError "$logFile.err" `
    -NoNewWindow -PassThru

Start-Sleep -Seconds 10

# Hit /api/status from localhost to confirm Flask is up.
try {
    $resp = Invoke-RestMethod -Uri 'http://localhost:8085/api/status' -TimeoutSec 5
    Write-Host ''
    _ok 'Web server responded to /api/status:'
    $resp | ConvertTo-Json -Depth 4 | ForEach-Object { "    $_" } | Write-Host
} catch {
    _err "Smoke test FAILED: $_"
    Write-Host '  --- log ---'
    if (Test-Path $logFile)        { Get-Content $logFile        | Select-Object -Last 30 }
    if (Test-Path "$logFile.err")  { Get-Content "$logFile.err"  | Select-Object -Last 30 }
}

# Tear down the smoke-test process.
if (-not $proc.HasExited) {
    # Prefer graceful shutdown via the Phase A /api/shutdown convention.
    try { Invoke-RestMethod -Uri 'http://localhost:8085/api/shutdown' -Method Post -TimeoutSec 2 | Out-Null } catch {}
    Start-Sleep -Seconds 2
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
}
_ok 'Smoke-test process stopped'

# --- Summary ---------------------------------------------------------------
Write-Host ''
Write-Host '============================================'
Write-Host '  P23 deploy step 05 complete'
Write-Host '============================================'
Write-Host "  Script:   $Script"
Write-Host "  Python:   $Python"
Write-Host "  Web port: 8085"
Write-Host "  Modbus:   10.1.1.180:502 (DR302 gateway -> compressor slave 1)"
Write-Host ''
Write-Host 'Next: register as a service. Two options ->'
Write-Host '  A) NSSM standalone (run 06_register_p23_nssm.ps1)'
Write-Host '  B) Wait for Overseer-on-srv-01 cutover and let Overseer manage it'
Write-Host ''
