# =============================================================================
# srv-01 step 04 -- Direct-download tooling installs (winget bypass)
#
# Installs Python 3.14, Git for Windows, NSSM, GitHub CLI directly from
# vendor sites. VS Code skipped (UI app, install manually if needed).
# =============================================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'  # speeds up Invoke-WebRequest

$DL = "$env:TEMP\traxis-tooling"
New-Item -ItemType Directory -Force -Path $DL | Out-Null

function _hdr($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }
function _ok($m) { Write-Host "[OK]  $m" }
function _err($m) { Write-Host "[ERR] $m" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# Python 3.14
# ---------------------------------------------------------------------------
_hdr 'Python 3.14'
if (Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' }) {
    _ok "Python already installed: $((Get-Command python).Source)"
} else {
    $pyVer = '3.14.0'
    $pyUrl = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-amd64.exe"
    $pyExe = "$DL\python-$pyVer-amd64.exe"
    Write-Host "  Downloading $pyUrl ..."
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyExe -UseBasicParsing
    _ok "Downloaded ($([math]::Round((Get-Item $pyExe).Length/1MB,1)) MB)"
    Write-Host '  Installing silently (per-user, PATH, pip, launcher) ...'
    & $pyExe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=1 | Out-Null
    Start-Sleep -Seconds 3
    $pyPath = "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
    if (Test-Path $pyPath) {
        $env:Path = "$env:LOCALAPPDATA\Programs\Python\Python314;$env:LOCALAPPDATA\Programs\Python\Python314\Scripts;$env:Path"
        _ok "Python installed at $pyPath"
        & $pyPath --version
    } else {
        _err "Python install failed (expected at $pyPath)"
    }
}

# ---------------------------------------------------------------------------
# Git for Windows
# ---------------------------------------------------------------------------
_hdr 'Git for Windows'
if (Get-Command git -ErrorAction SilentlyContinue) {
    _ok "Git already installed: $((Get-Command git).Source)"
} else {
    Write-Host '  Querying GitHub for latest git-for-windows release ...'
    $gitRel = Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest' -UseBasicParsing
    $asset = $gitRel.assets | Where-Object { $_.name -like '*-64-bit.exe' -and $_.name -notlike '*portable*' -and $_.name -notlike '*MinGit*' } | Select-Object -First 1
    $gitUrl = $asset.browser_download_url
    $gitExe = "$DL\$($asset.name)"
    Write-Host "  Downloading $($asset.name) ..."
    Invoke-WebRequest -Uri $gitUrl -OutFile $gitExe -UseBasicParsing
    _ok "Downloaded ($([math]::Round((Get-Item $gitExe).Length/1MB,1)) MB)"
    Write-Host '  Installing silently ...'
    & $gitExe /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS="ext,ext\shellhere,ext\guihere,gitlfs,assoc,assoc_sh,scalar" | Out-Null
    Start-Sleep -Seconds 3
    $env:Path = 'C:\Program Files\Git\cmd;' + $env:Path
    if (Get-Command git -ErrorAction SilentlyContinue) {
        _ok "Git installed: $((git --version))"
    } else {
        _err 'Git install failed'
    }
}

# ---------------------------------------------------------------------------
# NSSM 2.24
# ---------------------------------------------------------------------------
_hdr 'NSSM'
$nssmTarget = 'C:\Program Files\nssm\nssm.exe'
if (Test-Path $nssmTarget) {
    _ok "NSSM already installed at $nssmTarget"
} else {
    $nssmZip = "$DL\nssm-2.24.zip"
    Write-Host '  Downloading nssm-2.24.zip ...'
    Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile $nssmZip -UseBasicParsing
    _ok "Downloaded ($([math]::Round((Get-Item $nssmZip).Length/1KB,1)) KB)"
    Expand-Archive -Path $nssmZip -DestinationPath $DL -Force
    New-Item -ItemType Directory -Force -Path 'C:\Program Files\nssm' | Out-Null
    Copy-Item "$DL\nssm-2.24\win64\nssm.exe" -Destination $nssmTarget -Force
    $env:Path = 'C:\Program Files\nssm;' + $env:Path
    # Add to system PATH so services pick it up
    $sysPath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    if ($sysPath -notlike '*nssm*') {
        [Environment]::SetEnvironmentVariable('Path', "$sysPath;C:\Program Files\nssm", 'Machine')
    }
    if (Test-Path $nssmTarget) {
        _ok "NSSM installed at $nssmTarget"
    } else {
        _err 'NSSM install failed'
    }
}

# ---------------------------------------------------------------------------
# GitHub CLI
# ---------------------------------------------------------------------------
_hdr 'GitHub CLI'
if (Get-Command gh -ErrorAction SilentlyContinue) {
    _ok "gh already installed: $((Get-Command gh).Source)"
} else {
    Write-Host '  Querying GitHub for latest cli release ...'
    $ghRel = Invoke-RestMethod 'https://api.github.com/repos/cli/cli/releases/latest' -UseBasicParsing
    $asset = $ghRel.assets | Where-Object { $_.name -like '*_windows_amd64.msi' } | Select-Object -First 1
    $ghUrl = $asset.browser_download_url
    $ghMsi = "$DL\$($asset.name)"
    Write-Host "  Downloading $($asset.name) ..."
    Invoke-WebRequest -Uri $ghUrl -OutFile $ghMsi -UseBasicParsing
    _ok "Downloaded ($([math]::Round((Get-Item $ghMsi).Length/1MB,1)) MB)"
    Write-Host '  Installing silently ...'
    Start-Process msiexec.exe -ArgumentList '/i', $ghMsi, '/quiet', '/norestart' -Wait
    Start-Sleep -Seconds 3
    $env:Path = 'C:\Program Files\GitHub CLI;' + $env:Path
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        _ok "gh installed: $((gh --version | Select-Object -First 1))"
    } else {
        _err 'gh install failed'
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '============================================'
Write-Host '  Tooling install complete'
Write-Host '============================================'
foreach ($t in @('python','git','gh')) {
    $cmd = Get-Command $t -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1
    if ($cmd) {
        Write-Host ("  {0,-8} {1}" -f $t, $cmd.Source)
    } else {
        Write-Host ("  {0,-8} MISSING" -f $t)
    }
}
if (Test-Path 'C:\Program Files\nssm\nssm.exe') {
    Write-Host "  nssm     C:\Program Files\nssm\nssm.exe"
} else {
    Write-Host "  nssm     MISSING"
}
Write-Host ''
Write-Host 'Note: PATH changes require a new shell session to be visible.'
Write-Host 'When you SSH in next, all four commands should resolve.'
