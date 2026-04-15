# Project 30 — Traxis Label Printer Extension

Chrome extension (MV3) that injects print-label buttons on ProShop pages. Supports two page types:

- **WO pages** (`/procnc/workorders/*`) — "Print Material Label" button
- **COTS pages** (`/procnc/ots/*`) — "Print COTS Label" button

## Architecture

```
content.js       →  scrapes WO/material data from DOM + API fallback
                  →  LabelGenerator renders label PNG via Canvas API
cots-content.js  →  scrapes COTS ID + description from DOM
                  →  COTSLabelGenerator renders label PNG via Canvas API
Both              →  chrome.runtime.sendMessage → service-worker.js
service-worker.js →  POSTs base64 PNG to http://10.1.1.242:5002/api/print-image
```

Service worker is needed to bypass HTTPS→HTTP mixed-content block.

## Label Specs

**Material labels** (WO pages):
- 128px tall, auto-width, 180 DPI
- QR code left (encodes `proshop://wo/{woNumber}`)
- Text: WO number (bold 36px), material (18px), part number (14px), quantity (14px)

**COTS labels** (COTS pages):
- 128px tall, 450px wide (2.5"), 180 DPI, 2x supersampled
- QR code left (encodes full ProShop COTS URL)
- Text: COTS ID (bold 48px), description (28px, word-wrapped up to 2 lines)

## Key Files

| File | Purpose |
|------|---------|
| `traxis-material-label/manifest.json` | MV3 manifest, matches WO + COTS pages |
| `traxis-material-label/background/service-worker.js` | Print service proxy |
| `traxis-material-label/src/content.js` | WO button injection, DOM scraping, API fallback |
| `traxis-material-label/src/label-generator.js` | WO material label renderer (Canvas) |
| `traxis-material-label/src/cots-content.js` | COTS button injection, DOM scraping |
| `traxis-material-label/src/cots-label-generator.js` | COTS label renderer (Canvas, 2x supersample) |
| `traxis-material-label/src/content.css` | Green button styling with states (shared) |
| `traxis-material-label/lib/qrcode.min.js` | QR code generation library (shared) |

## Installation

1. Open `chrome://extensions` → Enable Developer mode
2. Click "Load unpacked" → Select `traxis-material-label/` folder
3. Navigate to any ProShop WO page or COTS detail page — green button appears

## Interfaces

Produces: Material label PNGs (128px tall, auto-width), COTS label PNGs (128px tall, 450px wide), both as base64 PNG via Canvas API
Consumes: ProShop WO page DOM, ProShop COTS page DOM, ProShop GraphQL API (session cookie), Brother PT-P700 print service at http://10.1.1.242:5002
Contracts: Print payload `{image_base64, copies, label_name}` to `/api/print-image` (same as P9/P22). WO labels use QR scheme `proshop://wo/{woNumber}` (same as P9). COTS labels encode full ProShop URL. All labels 128px tall at 180 DPI (PT-P700 24mm tape).
