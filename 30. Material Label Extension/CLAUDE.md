# Project 30 — Material Label Extension

Chrome extension (MV3) that injects a "Print Material Label" button on ProShop WO pages. Scrapes material data from the DOM (with GraphQL API fallback), renders a 128px label PNG client-side, and sends it to the Brother PT-P700 print service.

## Architecture

```
content.js  →  scrapes WO/material data from DOM + API fallback
             →  LabelGenerator renders label PNG via Canvas API
             →  chrome.runtime.sendMessage → service-worker.js
service-worker.js  →  POSTs base64 PNG to http://10.1.1.242:5002/api/print-image
```

Service worker is needed to bypass HTTPS→HTTP mixed-content block.

## Label Spec

- 128px tall, auto-width, 180 DPI (Brother PT-P700 24mm tape)
- QR code left (116x116px, encodes `proshop://wo/{woNumber}`)
- Text right: WO number (bold 36px), material (18px), part number (14px), quantity (14px)

## Key Files

| File | Purpose |
|------|---------|
| `traxis-material-label/manifest.json` | MV3 manifest, matches ProShop WO pages |
| `traxis-material-label/background/service-worker.js` | Print service proxy |
| `traxis-material-label/src/content.js` | Button injection, DOM scraping, API fallback |
| `traxis-material-label/src/label-generator.js` | Canvas-based label rendering |
| `traxis-material-label/src/content.css` | Green button styling with states |
| `traxis-material-label/lib/qrcode.min.js` | QR code generation library |

## Installation

1. Open `chrome://extensions` → Enable Developer mode
2. Click "Load unpacked" → Select `traxis-material-label/` folder
3. Navigate to any ProShop WO page — green button appears

## Interfaces

Produces: Material label PNGs (128px tall, base64 PNG via Canvas API)
Consumes: ProShop WO page DOM, ProShop GraphQL API (session cookie), Brother PT-P700 print service at http://10.1.1.242:5002
Contracts: Print payload `{image_base64, copies, label_name}` to `/api/print-image` (same as P9/P22), QR scheme `proshop://wo/{woNumber}` (same as P9), label height 128px at 180 DPI (PT-P700 24mm tape)
