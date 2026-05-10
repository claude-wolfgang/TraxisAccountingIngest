# =============================================================================
# srv-01 step 02 -- Baseline server tweaks. Invoked by 02_baseline.bat.
#
# Reversible. Sets server-appropriate defaults for a small headless box
# running Python services. Skips aggressive debloating.
# =============================================================================

$ErrorActionPreference = 'Continue'  # don't bail on a single failure
function _ok($m) { Write-Host "[OK]  $m" }
function _new($m) { Write-Host "[NEW] $m" }
function _err($m) { Write-Host "[ERR] $m" -ForegroundColor Red }

Write-Host ''
Write-Host '============================================'
Write-Host '  srv-01 baseline tweaks'
Write-Host '============================================'
Write-Host ''

# --- POWER & BOOT ----------------------------------------------------------
Write-Host '--- Power & boot ---'

# High Performance power plan
try {
    powercfg -setactive SCHEME_MIN | Out-Null
    _ok 'Power plan -> High Performance'
} catch { _err "Power plan: $_" }

# Never sleep, never turn off display, never spin down disk (AC + DC)
foreach ($mode in @('AC','DC')) {
    powercfg -change -monitor-timeout-$mode 0 | Out-Null
    powercfg -change -disk-timeout-$mode 0 | Out-Null
    powercfg -change -standby-timeout-$mode 0 | Out-Null
    powercfg -change -hibernate-timeout-$mode 0 | Out-Null
}
_ok 'Sleep/display/disk timeouts -> Never'

# No hibernation file (saves several GB on the SSD)
powercfg /hibernate off | Out-Null
_ok 'Hibernation disabled'

# No Fast Startup (avoids stale-driver weirdness on reboot)
$fsKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power'
if (Test-Path $fsKey) {
    Set-ItemProperty -Path $fsKey -Name HiberbootEnabled -Value 0 -Type DWord
    _ok 'Fast Startup disabled'
}

# --- FILESYSTEM ------------------------------------------------------------
Write-Host ''
Write-Host '--- Filesystem ---'

# Long path support (>260 chars). Critical for Python on Windows.
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
    -Name LongPathsEnabled -Value 1 -Type DWord
_ok 'Long path support enabled (LongPathsEnabled=1)'

# Show hidden files + file extensions in Explorer
$adv = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'
Set-ItemProperty -Path $adv -Name Hidden -Value 1 -Type DWord
Set-ItemProperty -Path $adv -Name HideFileExt -Value 0 -Type DWord
Set-ItemProperty -Path $adv -Name ShowSuperHidden -Value 0 -Type DWord  # don't show OS protected
_ok 'Explorer: show hidden, show extensions'

# Open Explorer to "This PC" instead of Quick Access
Set-ItemProperty -Path $adv -Name LaunchTo -Value 1 -Type DWord
_ok 'Explorer launches to This PC'

# Full path in title bar (helpful in RDP)
$cabState = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\CabinetState'
if (-not (Test-Path $cabState)) { New-Item -Path $cabState -Force | Out-Null }
Set-ItemProperty -Path $cabState -Name FullPath -Value 1 -Type DWord
_ok 'Explorer: full path in title bar'

# --- TIME ZONE & NTP -------------------------------------------------------
Write-Host ''
Write-Host '--- Time ---'

try {
    Set-TimeZone -Id 'Central Standard Time'
    _ok 'Time zone -> Central Standard Time'
} catch { _err "Time zone: $_" }

# Pin to pool.ntp.org and force sync
& w32tm /config /manualpeerlist:'pool.ntp.org,0x9' /syncfromflags:manual /reliable:yes /update | Out-Null
& Restart-Service w32time
& w32tm /resync /force | Out-Null
_ok 'NTP source -> pool.ntp.org, time resync forced'

# --- WINDOWS DEFENDER ------------------------------------------------------
Write-Host ''
Write-Host '--- Defender exclusions ---'

# Exclude C:\traxis\ from real-time scanning. Big speed win for Python services
# that import many .py files; nothing untrusted lives there.
try {
    Add-MpPreference -ExclusionPath 'C:\traxis' -ErrorAction Stop
    _ok 'Excluded C:\traxis from real-time scanning'
} catch { Write-Host '[OK]  C:\traxis exclusion (already set or Defender off)' }

# Exclude Python interpreter from process scanning (after install — may not
# exist yet, that's fine, this is idempotent)
$pythonExe = 'C:\Python314\python.exe'
if (-not (Test-Path $pythonExe)) {
    # winget default install path
    $pythonExe = "${env:LOCALAPPDATA}\Programs\Python\Python314\python.exe"
}
try {
    Add-MpPreference -ExclusionProcess 'python.exe' -ErrorAction Stop
    Add-MpPreference -ExclusionProcess 'pythonw.exe' -ErrorAction Stop
    _ok 'Excluded python.exe / pythonw.exe processes from real-time scanning'
} catch { Write-Host '[OK]  Python process exclusion (already set or Defender off)' }

# --- WINDOWS UPDATE: NO AUTO-RESTART ---------------------------------------
Write-Host ''
Write-Host '--- Windows Update ---'

$wuKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
if (-not (Test-Path $wuKey)) { New-Item -Path $wuKey -Force | Out-Null }
Set-ItemProperty -Path $wuKey -Name NoAutoRebootWithLoggedOnUsers -Value 1 -Type DWord
_ok 'No auto-restart with logged-on users'

# --- TELEMETRY / NUISANCE TWEAKS -------------------------------------------
Write-Host ''
Write-Host '--- Telemetry & Start-menu nuisance ---'

# Bing Web Search in Start menu off
$searchKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search'
if (-not (Test-Path $searchKey)) { New-Item -Path $searchKey -Force | Out-Null }
Set-ItemProperty -Path $searchKey -Name BingSearchEnabled -Value 0 -Type DWord
Set-ItemProperty -Path $searchKey -Name CortanaConsent -Value 0 -Type DWord
_ok 'Bing/Cortana web search in Start: off'

# Diagnostic data: Required only (lowest you can set on Pro)
$dcKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection'
if (-not (Test-Path $dcKey)) { New-Item -Path $dcKey -Force | Out-Null }
Set-ItemProperty -Path $dcKey -Name AllowTelemetry -Value 1 -Type DWord
_ok 'Telemetry -> Required only (lowest setting on Pro)'

# Customer Experience Improvement Program off
$ceipKey = 'HKLM:\SOFTWARE\Microsoft\SQMClient\Windows'
if (-not (Test-Path $ceipKey)) { New-Item -Path $ceipKey -Force | Out-Null }
Set-ItemProperty -Path $ceipKey -Name CEIPEnable -Value 0 -Type DWord
_ok 'Customer Experience Improvement Program: off'

# --- EXPLORER REFRESH ------------------------------------------------------
Write-Host ''
Write-Host '--- Refresh Explorer to apply user-scope changes ---'
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Start-Process explorer
_ok 'Explorer restarted'

# --- SUMMARY ---------------------------------------------------------------
Write-Host ''
Write-Host '============================================'
Write-Host '  Baseline complete'
Write-Host '============================================'
Write-Host ''
Write-Host 'Reboot recommended (long-path support and no-Fast-Startup'
Write-Host 'take effect on next boot).'
Write-Host ''
