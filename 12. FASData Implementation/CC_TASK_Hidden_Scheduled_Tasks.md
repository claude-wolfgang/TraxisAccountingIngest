# Claude Code Task: Hide Scheduled Task Console Windows

## Problem

The FASData scheduled tasks open visible console windows when they run, which is distracting.

## Solution

Create VBScript wrappers that launch the scripts with hidden windows, then update the scheduled tasks to use the wrappers.

## Files to Create

Create these in the project folder:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\
```

### 1. `run_daily_report_hidden.vbs`

```vbs
' Runs send_daily_report.py with no visible window
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe"" ""D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\send_daily_report.py"" --no-email", 0, False
```

### 2. `run_dashboard_hidden.vbs`

```vbs
' Runs generate_dashboard.py with no visible window
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe"" ""D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\generate_dashboard.py""", 0, False
```

## Update Scheduled Tasks

After creating the VBS files, update the scheduled tasks to use them:

### Daily Report Task (7 PM)

Delete and recreate:
```cmd
schtasks /delete /tn "FASData Daily Report" /f
schtasks /create /tn "FASData Daily Report" /tr "wscript.exe \"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\run_daily_report_hidden.vbs\"" /sc daily /st 19:00
```

### Dashboard Task (if it exists as a separate task)

If there's a scheduled task for the dashboard generator, update it similarly:
```cmd
schtasks /delete /tn "FASData Dashboard" /f
schtasks /create /tn "FASData Dashboard" /tr "wscript.exe \"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\run_dashboard_hidden.vbs\"" /sc hourly /st 00:00
```

## Verify

After updating, you can test by running manually:
```cmd
schtasks /run /tn "FASData Daily Report"
```

No console window should appear, but the report should still generate.

## Update Documentation

Add this to `FASData System Reference.md`:

### Hidden Task Wrappers (2026-02-05)

VBScript wrappers prevent scheduled tasks from showing console windows:

| Task | Wrapper | Schedule |
|------|---------|----------|
| Daily Report | `run_daily_report_hidden.vbs` | Daily 7 PM |
| Dashboard | `run_dashboard_hidden.vbs` | Hourly |

The `0` parameter in `WshShell.Run` means "hidden window."
