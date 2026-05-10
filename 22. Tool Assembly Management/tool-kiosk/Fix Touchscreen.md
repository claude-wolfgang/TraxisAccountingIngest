# Fix Touchscreen — Kiosk PC (Windows 11)

Touch works with mouse but not finger. Windows lost track of which display is the touchscreen.

---

## Step 1: Check Device Manager

1. Press **Win+X** > **Device Manager**
2. Expand **Human Interface Devices**
3. Find **HID-compliant touch screen**

| What you see | What to do |
|---|---|
| Down arrow (disabled) | Right-click > **Enable device** |
| Yellow warning icon | Right-click > **Uninstall device**, then Action menu > **Scan for hardware changes** |
| Not listed at all | Unplug/replug the touchscreen USB cable, then Action > **Scan for hardware changes** |
| Listed normally | Good — move to Step 2 |

After this, try tapping the screen. If touch works now, skip to Step 4.

---

## Step 2: Open Tablet PC Settings

Windows 11 hides this. Two ways to get there:

**Option A (fastest):**
- Press **Win+R**, type `tabletpc.cpl`, press Enter

**Option B:**
- Open **Control Panel**
- Top-right corner: change **View by** from "Category" to **Large icons**
- Find and click **Tablet PC Settings**

If "Tablet PC Settings" doesn't appear at all, it means Windows doesn't detect a touchscreen — go back to Step 1.

---

## Step 3: Map Touch to Correct Display

1. In Tablet PC Settings, click **Setup**
2. Select **Touch input**
3. A white screen appears: **"Touch this screen to identify it as the touchscreen"**
4. **Tap the 10" touchscreen** with your finger
5. Press **Enter** to confirm

---

## Step 4: Calibrate

1. Still in Tablet PC Settings, click **Calibrate**
2. Select **Touch input**
3. Tap the crosshairs as they appear on screen
4. Save calibration

---

## Step 5: Verify

Open Chrome on the touchscreen and go to:

```
http://localhost:5001/touch-test
```

Tap the orange box. You should see **TOUCH** events in the log.

If it works, restart the kiosk:
1. Run **STOP KIOSK.bat**
2. Run **START KIOSK.bat**

---

## Notes

- This can happen after Windows updates even if you didn't change anything
- The kiosk has two monitors — Windows needs to know which one accepts touch input
- If this keeps happening, check for Windows Update and consider pausing updates
