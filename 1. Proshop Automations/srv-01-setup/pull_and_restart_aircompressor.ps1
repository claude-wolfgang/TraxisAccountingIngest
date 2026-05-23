# =============================================================================
# Pull latest from git + restart AirCompressor on srv-01, with verification.
#
# Diagnoses the common "PID changed but old code still running" case (pull
# blocked by local commit / dirty file / divergence).
#
# Run via pull_and_restart_aircompressor.bat OR directly:
#   powershell -ExecutionPolicy Bypass -File pull_and_restart_aircompressor.ps1
#
# Idempotent. Safe to re-run.
# =============================================================================

$ErrorActionPreference = 'Continue'
function _hdr($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }
function _ok($m)  { Write-Host "[OK]   $m" -ForegroundColor Green }
function _warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function _err($m) { Write-Host "[ERR]  $m" -ForegroundColor Red }

$DeployRoot   = 'T:\traxis\services'
$P23File      = Join-Path $DeployRoot '23. Air Compressor communication GUI\compressor_web.py'
$OverseerBase = 'http://localhost:8060'
$AirSvcURL    = 'http://localhost:8085'
$ExpectedMarker = '/api/gateway/reboot'   # what the new code must contain

if (-not (Test-Path $DeployRoot)) { _err "Deploy root $DeployRoot not found"; exit 1 }
Set-Location $DeployRoot

# --- 1. Current git state -------------------------------------------------
_hdr 'git state BEFORE'
$beforeHead = (git log -1 --oneline)
Write-Host "  HEAD: $beforeHead"
git fetch origin main 2>&1 | Out-Null
$behind = (git rev-list --count HEAD..origin/main) -as [int]
$ahead  = (git rev-list --count origin/main..HEAD) -as [int]
Write-Host "  vs origin/main: $behind behind, $ahead ahead"
$dirty = (git status --porcelain)
if ($dirty) { _warn "Working tree dirty:"; $dirty | ForEach-Object { Write-Host "    $_" } }
else        { _ok  "Working tree clean" }

# --- 2. Pull (auto-stash if dirty, then pop) ------------------------------
_hdr 'git pull'
if ($behind -eq 0 -and $ahead -eq 0 -and -not $dirty) {
    _ok 'Already at origin/main -- nothing to pull'
} elseif ($ahead -gt 0) {
    _err "srv-01 is $ahead commit(s) AHEAD of origin -- ff-only pull will refuse."
    Write-Host "  Local-only commits:"
    git log --oneline "origin/main..HEAD"
    Write-Host "  Resolve manually (push, reset, or rebase) then re-run."
    exit 1
} else {
    $stashed = $false
    if ($dirty) {
        $stashLabel = "auto-stash by pull_and_restart_aircompressor $(Get-Date -Format yyyy-MM-ddTHH:mm:ss)"
        Write-Host "  Stashing dirty files (label: $stashLabel)..."
        git stash push -u -m $stashLabel | Out-Host
        if ($LASTEXITCODE -ne 0) { _err 'git stash failed -- aborting'; exit 1 }
        $stashed = $true
        _ok 'Stashed'
    }
    if ($behind -gt 0) {
        git pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            _err 'git pull failed'
            if ($stashed) { Write-Host "  Reverting stash..."; git stash pop | Out-Host }
            exit 1
        }
        _ok 'Pulled'
    } else {
        _ok 'No commits to pull (was only dirty, not behind)'
    }
    if ($stashed) {
        Write-Host "  Popping stash..."
        git stash pop | Out-Host
        if ($LASTEXITCODE -ne 0) {
            _warn 'Stash pop produced conflicts -- your local changes are in git stash list, resolve manually'
        } else {
            _ok 'Stash popped cleanly'
        }
    }
}
$afterHead = (git log -1 --oneline)
Write-Host "  HEAD now: $afterHead"

# --- 3. Verify file on disk has the new code ------------------------------
_hdr 'verify file content'
if (-not (Test-Path $P23File)) { _err "$P23File missing"; exit 1 }
$hit = Select-String -Path $P23File -Pattern $ExpectedMarker -SimpleMatch
if ($hit) {
    _ok "Marker '$ExpectedMarker' found in compressor_web.py (line $($hit[0].LineNumber))"
} else {
    _err "Marker '$ExpectedMarker' NOT in compressor_web.py -- pull didn't bring the change."
    Write-Host "  Likely cause: srv-01 checkout points at a different remote/branch."
    Write-Host "  Diagnose with:  git remote -v ; git branch --show-current"
    exit 1
}

# --- 4. Restart via Overseer ---------------------------------------------
_hdr 'restart AirCompressor via Overseer'
try {
    $old = (Invoke-RestMethod "$OverseerBase/api/status").services |
        Where-Object name -eq AirCompressor | Select-Object -ExpandProperty pid
    Write-Host "  Old PID: $old"
    Invoke-RestMethod -Method Post "$OverseerBase/api/services/AirCompressor/restart" | Out-Null
    Start-Sleep -Seconds 4
    $new = (Invoke-RestMethod "$OverseerBase/api/status").services |
        Where-Object name -eq AirCompressor | Select-Object -ExpandProperty pid
    Write-Host "  New PID: $new"
    if ($new -and $new -ne $old) { _ok 'Service restarted (PID changed)' }
    else                         { _err 'PID unchanged -- restart may have failed'; exit 1 }
} catch {
    _err "Overseer restart call failed: $($_.Exception.Message)"; exit 1
}

# --- 5. Verify the new endpoint is live -----------------------------------
_hdr 'verify new endpoint'
try {
    # GET on a POST-only route should return 405 if registered, 404 if not.
    Invoke-WebRequest -Uri "$AirSvcURL/api/gateway/reboot" -Method Get -UseBasicParsing -TimeoutSec 5 | Out-Null
    _warn 'Endpoint responded 200 to GET -- unexpected, but route is alive'
} catch {
    $code = [int]$_.Exception.Response.StatusCode
    if ($code -eq 405)   { _ok '/api/gateway/reboot is live (405 = POST-only, route exists)' }
    elseif ($code -eq 404){ _err '/api/gateway/reboot returned 404 -- new code did NOT load. Check service logs.'; exit 1 }
    else                 { _warn "/api/gateway/reboot returned HTTP $code" }
}

try {
    $html = (Invoke-WebRequest -Uri "$AirSvcURL/" -UseBasicParsing -TimeoutSec 5).Content
    if ($html -match 'Reboot Gateway' -and $html -match 'confirmRebootGateway') {
        _ok 'Reboot Gateway button + JS handler present in UI'
    } else {
        _warn 'UI page served but Reboot Gateway button/JS missing -- inspect manually'
    }
} catch {
    _warn "Could not fetch UI page: $($_.Exception.Message)"
}

Write-Host ''
_ok 'Deploy complete.'
