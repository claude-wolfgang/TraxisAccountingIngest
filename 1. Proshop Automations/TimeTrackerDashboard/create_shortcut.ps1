$WshShell = New-Object -ComObject WScript.Shell
$StartupPath = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup\TimeTrackerDashboard.lnk")
$Shortcut = $WshShell.CreateShortcut($StartupPath)
$Shortcut.TargetPath = "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\TimeTrackerDashboard\run_silent.vbs"
$Shortcut.WorkingDirectory = "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\TimeTrackerDashboard"
$Shortcut.Description = "Traxis Time Tracking Dashboard"
$Shortcut.Save()
Write-Host "Shortcut created at: $StartupPath"
