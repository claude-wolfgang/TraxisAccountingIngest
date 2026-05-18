# Register the daily WO flip job in Windows Task Scheduler.
# Run ONCE per host where you want the scheduled run (typically .71, or srv-01 post-cutover).
# Requires PowerShell as administrator.
#
# Default cadence: daily at 18:00 (end of business -- gives the Web Connector all day
# to push the day's invoices before we sweep for stuck WOs).
#
# Telegram alerting fires only when the run flips something. Silent days produce no
# noise. Requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set as SYSTEM env vars on the
# host (same convention as P1 Overseer -- not in .traxis.env).

param(
    [string]$RunTime = "18:00",
    [string]$TaskName = "Traxis - Flip WO Invoiced",
    # Default matches the P34 pattern on .71 (WindowsApps pythonw.exe proxy to user Python314).
    # Override with -PythonExe on hosts where Python lives elsewhere (e.g. srv-01 post-cutover).
    [string]$PythonExe = "C:\Users\TRAXIS\AppData\Local\Microsoft\WindowsApps\pythonw.exe",
    # Run as the interactive logged-in user (matches P34 CWS Ops Watcher). Use "SYSTEM" only
    # if the host has no persistent user session -- but SYSTEM scope env vars must then exist.
    [string]$RunAsUser = "TRAXIS"
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "flip_wo_invoiced_from_qbo.py"

if (-not (Test-Path $scriptPath)) {
    throw "Cannot find flip_wo_invoiced_from_qbo.py at $scriptPath"
}
if (-not (Test-Path $PythonExe)) {
    throw "Cannot find Python at $PythonExe -- pass -PythonExe with the correct path"
}

# Pre-flight: confirm Telegram env vars exist in the scope the task will read from.
# For RunAsUser=TRAXIS (Interactive), User-scope OR Machine-scope both work.
# For RunAsUser=SYSTEM (ServiceAccount), only Machine-scope is visible.
$botMachine = [System.Environment]::GetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "Machine")
$chatMachine = [System.Environment]::GetEnvironmentVariable("TELEGRAM_CHAT_ID",  "Machine")
$botUser    = [System.Environment]::GetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "User")
$chatUser   = [System.Environment]::GetEnvironmentVariable("TELEGRAM_CHAT_ID",   "User")
$haveTelegram = ($botMachine -and $chatMachine) -or ($botUser -and $chatUser)
if (-not $haveTelegram) {
    Write-Warning "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set at User or Machine scope."
    Write-Warning "The task will still run, but flips will not send Telegram alerts."
}

# Build the action: pythonw.exe flip_wo_invoiced_from_qbo.py --apply
$action  = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$scriptPath`" --apply" -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $RunTime
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable

# Run as the chosen user
if ($RunAsUser -eq "SYSTEM") {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Interactive -RunLevel Limited
}

# Idempotent: remove existing task with the same name first
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Removing existing task: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily sweep: detect WOs stuck on Shipped, flip to Invoiced when QBO confirms the invoice. P27 Accounting Ingest." | Out-Null

Write-Output ""
Write-Output "Registered: $TaskName"
Write-Output "  Runs daily at: $RunTime"
Write-Output "  Script:        $scriptPath"
Write-Output "  Python:        $PythonExe"
Write-Output ""
Write-Output "Manual trigger now: Start-ScheduledTask -TaskName ""$TaskName"""
Write-Output "Inspect schedule:   Get-ScheduledTaskInfo -TaskName ""$TaskName"""
Write-Output "Remove:             Unregister-ScheduledTask -TaskName ""$TaskName"" -Confirm:`$false"
