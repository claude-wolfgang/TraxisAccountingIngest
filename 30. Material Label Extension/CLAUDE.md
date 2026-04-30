# Project 30 — Traxis Label Printer Extension

Chrome extension (MV3) that injects print-label buttons on ProShop pages. Supports six page types:

- **WO pages** (`/procnc/workorders/*`) — "Print Material Label" button (green, Part Stock row)
- **WO pages** (`/procnc/workorders/*`) — "Print Box Label" button (blue, Shipping row) — prompts for box qty
- **COTS pages** (`/procnc/ots/*`) — "Print COTS Label" button (green)
- **Equipment pages** (`/procnc/equipment/*`) — "Print Equipment Label" button (red)
- **User pages** (`/procnc/users/*`) — "Print User Label" button (teal)
- **Tool pages** (`/procnc/tools/*`) — "Print Tool Label" button (orange) — IN PROGRESS

## Architecture

```
content.js            →  scrapes WO/material data from DOM + API fallback
                       →  LabelGenerator renders label PNG via Canvas API
box-content.js        →  scrapes Customer PO + Part# from DOM + API, prompts for box qty
                       →  BoxLabelGenerator renders label PNG via Canvas API
cots-content.js       →  scrapes COTS ID + description from DOM
                       →  COTSLabelGenerator renders label PNG via Canvas API
equipment-content.js  →  scrapes equipment data from DOM + API fallback
                       →  EquipmentLabelGenerator renders label PNG via Canvas API
user-content.js       →  scrapes user name + ID from DOM
                       →  UserLabelGenerator renders label PNG via Canvas API
tool-content.js       →  tool ID from URL, description/location from iframe fields
                       →  ToolLabelGenerator renders label PNG via Canvas API
All                   →  chrome.runtime.sendMessage → service-worker.js
service-worker.js     →  POSTs base64 PNG to http://10.1.1.242:5002/api/print-image
```

**Note:** ProShop tool pages render form inputs inside iframes (unlike other page types). The tool content script accesses iframe `contentDocument` directly to read `data-display-name` fields.

Service worker is needed to bypass HTTPS→HTTP mixed-content block.

## Label Specs

**Material labels** (WO pages):
- 128px tall, auto-width, 180 DPI
- QR code left (encodes `proshop://wo/{woNumber}`)
- Text: WO number (bold 36px), material (24px, word-wrapped at 400px), part number (14px)

**COTS labels** (COTS pages):
- 128px tall, 450px wide (2.5"), 180 DPI, 2x supersampled
- QR code left (encodes full ProShop COTS URL)
- Text: COTS ID (bold 48px), description (28px, word-wrapped up to 2 lines)

**Equipment labels** (Equipment pages):
- 128px tall, auto-width, 180 DPI
- QR code left (encodes full ProShop equipment URL)
- Text: Equipment # (bold 36px), Tool Name (24px, word-wrapped at 400px), Serial Number (14px)

**Box labels** (WO pages — Shipping row):
- 128px tall, auto-width, 180 DPI
- QR code left (encodes `proshop://wo/{woNumber}`)
- Text: WO # (bold 30px), Customer PO (20px), Part Number (16px), Qty (bold 26px)
- Operator prompted for box quantity on click

**User labels** (User pages):
- 128px tall, auto-width, 180 DPI
- QR code left (encodes full ProShop user URL)
- Text: Name (bold 36px), User ID (24px)

**Tool labels** (Tool pages — IN PROGRESS):
- 128px tall, auto-width, 180 DPI
- QR code left (encodes full ProShop tool URL)
- Text: Tool # (bold 30px), description (20px, word-wrapped), location (14px)

## Key Files

| File | Purpose |
|------|---------|
| `traxis-material-label/manifest.json` | MV3 manifest, matches WO + COTS + equipment pages |
| `traxis-material-label/background/service-worker.js` | Print service proxy |
| `traxis-material-label/src/content.js` | WO button injection, DOM scraping, API fallback |
| `traxis-material-label/src/label-generator.js` | WO material label renderer (Canvas) |
| `traxis-material-label/src/cots-content.js` | COTS button injection, DOM scraping |
| `traxis-material-label/src/cots-label-generator.js` | COTS label renderer (Canvas, 2x supersample) |
| `traxis-material-label/src/equipment-content.js` | Equipment button injection, DOM scraping, API fallback |
| `traxis-material-label/src/equipment-label-generator.js` | Equipment label renderer (Canvas) |
| `traxis-material-label/src/box-content.js` | Box label button injection, DOM scraping, qty prompt |
| `traxis-material-label/src/box-label-generator.js` | Box label renderer (Canvas) |
| `traxis-material-label/src/user-content.js` | User label button injection, DOM scraping |
| `traxis-material-label/src/user-label-generator.js` | User label renderer (Canvas) |
| `traxis-material-label/src/tool-content.js` | Tool button injection, iframe scraping |
| `traxis-material-label/src/tool-label-generator.js` | Tool label renderer (Canvas) |
| `traxis-material-label/src/content.css` | Button styling — green (WO/COTS), red (equipment), blue (box), teal (user), orange (tool) |
| `traxis-material-label/lib/qrcode.min.js` | QR code generation library (shared) |

## Related Label Projects

- **P17 (`17. COTS - Tools Crib Kiosk/generate_cots_labels.py`)** — Original Python CLI COTS label generator. Uses CSV master list or ProShop GraphQL API. Supports batch printing (`--all`) and multi-copy (`--copies`). P30 supersedes P17 for day-to-day COTS label printing (no CSV dependency), but P17 remains available for batch operations.
- **P9 / P22** — Share the same print service endpoint and payload format at `http://10.1.1.242:5002/api/print-image`.

## Installation

### Production (Chrome Web Store — all shop PCs)

Extension is published as **unlisted** on Chrome Web Store. Deployed via Chrome enterprise policy:

1. Get extension ID from CWS Developer Dashboard
2. Edit `deployment/deploy_client_cws.bat` — replace `PASTE_EXTENSION_ID_HERE` with CWS extension ID
3. Run `deploy_client_cws.bat` as Administrator on each shop PC
4. Restart Chrome — extension installs automatically

Registry key set by deploy script:
```
HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist
  1 = "<CWS_EXTENSION_ID>;https://clients2.google.com/service/update2/crx"
```

### Development (Load unpacked)

1. Open `chrome://extensions` → Enable Developer mode
2. Click "Load unpacked" → Select `traxis-material-label/` folder
3. Navigate to any ProShop WO page, COTS detail page, or equipment page — button appears

### Updating

Bump version in `manifest.json`, rebuild ZIP (`deployment/build.py` or manual zip), upload to CWS Developer Dashboard. Chrome auto-updates on all shop PCs within a few hours.

### Deployment notes

- Self-hosted CRX via `ExtensionInstallForcelist` does NOT work on non-domain-joined PCs — Chrome requires enterprise management for off-store force installs.
- CWS unlisted + registry policy works on any Windows PC regardless of domain status.
- Same deployment pattern applies to P14 (Workstation Display) and P18 (Message Notifier) when ready.

## Interfaces

Produces: Material label PNGs, Box label PNGs, COTS label PNGs (450px wide), Equipment label PNGs, User label PNGs, Tool label PNGs — all 128px tall, auto-width (except COTS), as base64 PNG via Canvas API
Consumes: ProShop WO page DOM, ProShop COTS page DOM, ProShop Equipment page DOM, ProShop User page DOM, ProShop Tool page DOM (via iframe contentDocument), ProShop GraphQL API (session cookie), Brother PT-P700 print service at http://10.1.1.242:5002
Contracts: Print payload `{image_base64, copies, label_name}` to `/api/print-image` (same as P9/P22). WO and Box labels use QR scheme `proshop://wo/{woNumber}` (same as P9). COTS, equipment, user, and tool labels encode full ProShop URL. All labels 128px tall at 180 DPI (PT-P700 24mm tape). Tool pages use iframe-based DOM — form inputs have `data-display-name` attributes inside iframes, not in top-level document. CWS extension ID used in registry policy on all shop PCs — changing it requires re-running deploy script.
