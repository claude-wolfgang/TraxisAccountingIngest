# Project 27: Accounting Ingest

Ingests vendor invoices, bills, packing slips, quotes, and purchase orders into ProShop and QuickBooks Online. Processes email attachments and scanned documents (PDF/image) via Claude AI extraction, fuzzy-matches contacts, and uploads via GraphQL mutations. Includes scan-burst-classify pipeline, tool receiving labels, and VPO receiving automation.

## Key Files

- `accounting_ingest.py` — Main script v1.4.0: ProShopClient, QBOClient, AIExtractor (burst_pdf, classify, extract, classify_html, extract_html), email body extraction, debounced vendor search, manual label printing, cert filing by VPO
- `qbo_auth.py` — QBO OAuth 2.0 production token exchange (manual paste-URL flow via Intuit Playground redirect)
- `tool_receiving_labels.py` — Tool receiving label generator: VPO→tool library lookup (two-client), Brother PT-P700 label printing via P22 print service
- `scan_relay.py` — Watches Pictures folder, moves stable PDFs to Scanned folder
- `proshop_fields.py` — ProShop schema introspection utilities
- `diag_purchase_order.py` — Diagnostic for addPurchaseOrder mutation permissions

## Interfaces

Produces: ProShop purchase orders (addPurchaseOrder), bills (addBill), packing slips (addPackingSlip), customer POs (addCustomerPo — blocked by permissions), quotes (addQuote); VPO receiving (updatePurchaseOrder mutation — receivedQty/releasedQty); tool receiving labels (PNG via P22 print service, manual button only); QBO bills (production API, realm 123146014753554); cert PDFs filed by VPO in Accounting Inbox/Certs/VPO-XXXXXX/; burst PDFs in Accounting Inbox/Scanned/burst/
Consumes: ProShop GraphQL API (ACCOUNTING_CLIENT_ID for purchaseorders/customerpos scope, TOOLKIOSK_CLIENT_ID for tools scope), QBO REST API (OAuth 2.0 production, refresh token auto-renews), Microsoft Graph API (email attachments + email body text via get_body()), Claude AI API (Sonnet for extraction, Haiku for HTML classification), P22 print service (10.1.1.242:5002 /api/print-image), .traxis.env (credentials), Scanner → Pictures folder (scan_relay.py)
Contracts: PO line items use `toolNumber` field (not `itemNumber`) for tools and COTS. `orderNumber` field carries brand + EDP. `shipTo` defaults to Traxis MFG 511 E St Elmo Rd. updatePurchaseOrder mutation: `id` is a separate arg (not inside `data`), poItems use selector {field: "orderNumber", value: "..."} + data {receivedQty, releasedQty, receivedDate, releasedDate}. P22 print service contract: POST /api/print-image with {image_base64, copies, label_name}. Customer PO mutations (add/update) blocked by auth_010 user permissions — read-only via API.
