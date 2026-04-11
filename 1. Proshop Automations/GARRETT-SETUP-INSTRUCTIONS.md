# Garrett's Inspection Room Computer — Setup Instructions

## Issues to Fix
1. Old add-in icons showing in Fusion (ProShopConnector, TraxisPostProcessor)
2. Written Description push not working (needs Tampermonkey)
3. TPM setup renaming not working (needs credentials + proper install)

---

## Step 1: Close Fusion 360
Make sure Fusion is fully closed before proceeding.

## Step 2: Run the Installer (as Admin)
1. Right-click `setup_fusion_addins.bat` and choose **Run as administrator**
2. It will auto-detect the Dropbox path
3. If `.traxis.env` doesn't exist on this machine, it will copy credentials automatically
4. If ProgrammingTimer asks for a name, enter **Garrett**
5. Confirm output shows `[NEW]` for each add-in and `[DEL]` for old ones:
   - `[DEL] TraxisPostProcessor -- removed`
   - `[DEL] ProShopConnector -- removed`
   - `[NEW] ProgrammingTimer -- linked`
   - `[NEW] ProShopBridge -- linked`
   - `[NEW] TraxisProgramManager -- linked`
   - `[NEW] TraxisCapture -- linked`
   - `[NEW] FusionToolAuditor -- linked`

## Step 3: Enable Add-ins in Fusion
1. Open Fusion 360
2. Press **Shift+S** to open Scripts and Add-Ins
3. Go to the **Add-Ins** tab
4. If ProShopConnector or TraxisPostProcessor still appear, select and **remove/disable** them
5. Enable these add-ins (check "Run on Startup" for each):
   - **ProShopBridge**
   - **TraxisProgramManager**
   - **ProgrammingTimer**
   - **TraxisCapture**
6. FusionToolAuditor is on-demand only — enable when needed

## Step 4: Set Up Tampermonkey (for Written Description Push)
The Written Description push copies HTML to clipboard and opens a ProShop page.
A Tampermonkey userscript auto-pastes it. Without this, sequence details work but written descriptions won't.

1. Open **Chrome** on this machine
2. Install the **Tampermonkey** extension from the Chrome Web Store
3. Click the Tampermonkey icon in Chrome toolbar → **Create a new script**
4. Delete the template code
5. Open this file and copy its entire contents:
   ```
   ProShopBridge\proshop_bridge_tampermonkey.user.js
   ```
   (Located in the same Dropbox folder as this instructions file)
6. Paste into Tampermonkey and click **File → Save** (Ctrl+S)
7. Verify the script shows as **enabled** in Tampermonkey's dashboard

## Step 5: Verify Everything Works
1. In Fusion, open a CAM document with setups
2. Click **TPM** button in Utilities tab — enter a part number, check setups, click OK
   - Setups should rename to `PartNumber:OpNumber` format
   - Check Fusion's **Text Commands** panel (bottom of screen) for any errors
3. Click **PROSHOP** button — should open the ProShop Bridge palette
   - Try a push with both checkboxes checked
   - Sequence details should push via API
   - Written description should open Chrome and auto-paste via Tampermonkey

## Troubleshooting
- **TPM errors**: Check Text Commands panel for `[TPM]` log lines
- **Missing credentials**: Verify `C:\Users\{username}\.traxis.env` exists
- **Written desc fails silently**: Confirm Tampermonkey is enabled and the script is active
- **Old icons persist**: Shift+S → Add-Ins → manually delete any stale entries
