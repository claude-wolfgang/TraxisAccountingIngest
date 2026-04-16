# Project 27: Accounting Ingest

Ingests vendor invoices, bills, packing slips, quotes, and purchase orders into ProShop and QuickBooks Online. Processes email attachments (PDF/image) via Claude AI extraction, fuzzy-matches contacts, and uploads via GraphQL mutations.

## Key Files

- `accounting_ingest.py` — Main script: ProShopClient, QBOClient, ProShopUploader, email processing pipeline
- `proshop_fields.py` — ProShop schema introspection utilities
- `diag_purchase_order.py` — Diagnostic for addPurchaseOrder mutation permissions

## Interfaces

Produces: ProShop purchase orders (addPurchaseOrder mutation), bills (addBill), packing slips (addPackingSlip), customer POs (addCustomerPo), quotes (addQuote); QBO bills and bill payments
Consumes: ProShop GraphQL API (OAuth 2.0 via ACCOUNTING_CLIENT_ID), QBO REST API (OAuth 2.0 refresh token), Gmail API (email attachments), .traxis.env (credentials)
Contracts: PO line items use `toolNumber` field (not `itemNumber`) for tools and COTS — maps to ProShop COTS/Tool# column and triggers library auto-fill in UI. `orderNumber` field carries manufacturer brand + EDP for vendor identification. `shipTo` defaults to Traxis Manufacturing, 511 E St Elmo Rd, Austin TX 78745.
