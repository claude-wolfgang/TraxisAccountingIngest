# CWS Store Listing — v1.6.0

Paste the relevant sections into the Chrome Web Store Developer Dashboard → **Store listing** tab.

---

## Summary (short, 132 char limit)

Print material, COTS, equipment, box, user, and tool labels and queue purchase orders from ProShop ERP pages.

---

## Description (long)

Internal-use Chrome extension for employees of Traxis Manufacturing LLC. Published as **unlisted** on the Chrome Web Store and distributed to company-owned shop-floor PCs via enterprise registry policy (ExtensionInstallForcelist). Not intended for, marketed to, or usable by the general public.

**What it does**

Traxis Label Printer injects two kinds of buttons on pages within our company's private ProShop ERP instance (traxismfg.adionsystems.com):

1. **Print-label buttons** on work-order, COTS, equipment, user, and tool pages. The extension reads the relevant fields from the page DOM (and, for some types, queries the ProShop GraphQL API using the user's existing session cookie), renders a 24 mm label image in the browser tab via the Canvas API, and POSTs the PNG to a Brother PT-P700 label printer service on our private LAN.

2. **"Buy" button** (new in v1.6.0) on COTS, Tools, and Parts pages. The user is prompted for a quantity; the extension best-effort scrapes the unit cost, brand, and supplier from the page, then POSTs the request to an internal purchasing-queue Flask service on our private LAN. The service either auto-approves the request under preconfigured rules or surfaces it on an approval inbox for manual review by authorized staff.

**Privacy and data handling**

No data leaves the local network. The extension communicates with exactly three hosts, all declared in the manifest and all internal to the company:

- `https://traxismfg.adionsystems.com/*` — the company's ProShop ERP instance
- `http://10.1.1.242:5002/*` — the LAN-only Brother PT-P700 print service
- `http://10.1.1.71:5003/*` — the LAN-only purchasing-queue service (new in v1.6.0)

No analytics, telemetry, cookies, third-party services, or external endpoints. The extension does not store any data and reads page content solely from our private ERP. Full privacy policy: https://claude-wolfgang.github.io/traxis-privacy/

**What's new in v1.6.0**

- "Buy" button on COTS, Tools, and Parts pages that queues purchase-order requests to the internal LAN purchasing service.
- New host permission for `http://10.1.1.71:5003/*` (the internal purchasing service); declared in manifest and documented in the privacy policy.
- Tightened manifest description length to satisfy Chrome's 132-character cap.

**Support**

This is a private internal tool. Questions from authorized Traxis staff: tom@traxismfg.com

---

## Category

Productivity (or Developer Tools — either is appropriate for an internal ERP-integration extension)

---

## Language

English (United States)
