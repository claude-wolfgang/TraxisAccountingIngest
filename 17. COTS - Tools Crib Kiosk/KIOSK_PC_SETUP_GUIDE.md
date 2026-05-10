# COTS Crib Kiosk — Dedicated PC Setup Guide

This guide walks through setting up the kiosk PC (Windows 7 HP touchscreen) as a locked-down COTS Crib terminal. The kiosk runs a local Flask server and Chrome in fullscreen kiosk mode with a watchdog that auto-restarts everything.

---

## Machine Details

- **Hardware:** HP touchscreen all-in-one (Lenovo ThinkCentre + HP touch display)
- **OS:** Windows 7 (Version 6.1.7601)
- **User profile:** `C:\Users\Traxis-COTs\`
- **Python:** 3.8.10 (last version supporting Windows 7)
- **Python path:** `C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\`

---

## What the kiosk PC will do when set up

- Run the Flask web server locally on port 5000
- Open Chrome in fullscreen kiosk mode — no address bar, no tabs, no browser UI
- Watchdog restarts Chrome immediately if someone closes it
- Watchdog restarts Flask if it crashes
- Starts automatically on boot with no user interaction

---

## Setup Steps (in order)

### Step 1: Fix Python PATH

Python is installed but not on PATH. On the kiosk PC, open the `cots-kiosk` folder and double-click:

```
fix_python_path.bat
```

Then **close and reopen** Command Prompt and verify:

```
python --version
```

Should say: `Python 3.8.10`

If `fix_python_path.bat` says "Python not found", Python may be in a different folder. Check what's in `C:\Users\Traxis-COTs\AppData\Local\Programs\Python\` and update the bat file.

---

### Step 2: Install Python packages

Double-click:

```
install_packages.bat
```

Or manually in Command Prompt:

```
pip install flask requests
```

---

### Step 3: Set up Dropbox Selective Sync

Dropbox is logged in but syncing everything. To only sync the kiosk files:

1. Click the Dropbox icon in the system tray (bottom-right)
2. Click the gear icon → **Preferences**
3. Go to **Sync** tab → **Selective Sync** → **Change Settings**
4. Uncheck everything EXCEPT:
   - `MACHINE COMM Traxis` → `Proshop Automation and Claude Projects` → `17. COTS - Tools Crib Kiosk`
5. Click **Update**, then **OK**

Wait for sync to complete. The kiosk files will be at:

```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\17. COTS - Tools Crib Kiosk\cots-kiosk\
```

(If Dropbox puts files on `C:\` instead of `D:\`, adjust paths accordingly.)

---

### Step 4: Verify everything is ready

Double-click:

```
verify_setup.bat
```

You should see:
```
Python 3.8.10
Flask OK: (some version)
Requests OK: (some version)
Chrome OK: (path to chrome.exe)
```

If anything says NOT FOUND, fix that before continuing.

---

### Step 5: Test Flask server manually

Open Command Prompt and run:

```
cd "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\17. COTS - Tools Crib Kiosk\cots-kiosk"
set PROSHOP_CLIENT_SECRET=E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110
python app.py
```

Open Chrome and go to `http://localhost:5000`. You should see the kiosk interface. Press Ctrl+C in Command Prompt to stop.

---

### Step 6: Test the kiosk launcher

Double-click `start_kiosk.vbs` in the cots-kiosk folder. It should:

1. Start Flask in the background (no console window)
2. After a few seconds, Chrome opens in fullscreen kiosk mode
3. If you Alt+F4 Chrome, it relaunches within ~2 seconds

If Chrome doesn't appear, check `kiosk_launcher.log` in the cots-kiosk folder for errors.

To stop the kiosk for now: Ctrl+Alt+Del → Task Manager → end `pythonw.exe` → then close Chrome.

---

### Step 7: Set up auto-start on boot

1. Press **Win+R**, type `shell:startup`, press Enter
2. Right-click in the folder → **New** → **Shortcut**
3. For the location, browse to:
   ```
   D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\17. COTS - Tools Crib Kiosk\cots-kiosk\start_kiosk.vbs
   ```
4. Name it `COTS Crib Kiosk`
5. Click Finish

Reboot the PC to verify it starts automatically.

---

### Step 8 (Optional): Auto-login on boot

Skip the Windows login screen so the kiosk starts unattended:

1. Press **Win+R**, type `netplwiz`, press Enter
2. Uncheck **"Users must enter a user name and password to use this computer"**
3. Click Apply, enter the password twice, click OK

---

### Step 9 (Optional): Disable Task Manager

Prevents shop floor users from exiting via Ctrl+Alt+Del → Task Manager.

**Windows 7 Pro/Enterprise only** (won't work on Home edition):

1. Press **Win+R**, type `gpedit.msc`, press Enter
2. Navigate to: **User Configuration** → **Administrative Templates** → **System** → **Ctrl+Alt+Del Options**
3. Double-click **Remove Task Manager**, set to **Enabled**, click OK

To undo later: set back to **Not Configured**.

**Windows 7 Home** alternative (registry):

1. Press **Win+R**, type `regedit`, press Enter
2. Navigate to: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Policies\System`
   - If the `System` key doesn't exist, right-click `Policies` → New → Key → name it `System`
3. Right-click → New → DWORD (32-bit) → name it `DisableTaskMgr` → set value to `1`

To undo: delete the `DisableTaskMgr` value or set it to `0`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Chrome shows "can't reach this page" | Flask hasn't started. Check `kiosk_launcher.log` for errors. |
| Chrome doesn't open at all | Check `kiosk_launcher.log` — it will say "Chrome not found" if it can't locate chrome.exe. |
| `start_kiosk.vbs` says "Cannot find pythonw.exe" | Python not installed or in unexpected location. Check path in error message. |
| SSL errors in the log | Windows 7 may have outdated root certificates. Run Windows Update or install the certs manually. |
| Need to exit kiosk for maintenance | Ctrl+Alt+Del → Task Manager → End `pythonw.exe` → Close Chrome. |

### Log file

All launcher activity (starts, restarts, errors) is logged to:

```
cots-kiosk\kiosk_launcher.log
```

---

## Files in cots-kiosk folder

| File | Purpose |
|------|---------|
| `start_kiosk.vbs` | Silent launcher — double-click or put in Startup folder |
| `kiosk_launcher.py` | Watchdog — starts Flask + Chrome, keeps both alive |
| `kiosk_launcher.log` | Log file (created on first run) |
| `fix_python_path.bat` | One-time fix: adds Python to system PATH |
| `install_packages.bat` | One-time: installs flask + requests via pip |
| `verify_setup.bat` | Checks Python, Flask, requests, Chrome are all present |
| `run_kiosk.bat` | Manual server start (for debugging, no kiosk mode) |
| `app.py` | Flask web server |

---

## Network requirements

- **Outbound HTTPS (port 443):** `https://traxismfg.adionsystems.com` (ProShop API)
- **Local only (port 5000):** `http://localhost:5000` (kiosk web UI — no inbound access needed)

---

## Quick reference

| Action | How |
|--------|-----|
| Start kiosk manually | Double-click `start_kiosk.vbs` |
| Stop kiosk | Ctrl+Alt+Del → Task Manager → End `pythonw.exe` → Close Chrome |
| Check server health | From another PC: `http://<kiosk-ip>:5000/api/health` |
| View logs | Open `kiosk_launcher.log` in Notepad |
| Run server only (debug) | Run `run_kiosk.bat` |
