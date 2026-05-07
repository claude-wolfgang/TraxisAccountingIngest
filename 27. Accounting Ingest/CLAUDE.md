# Project 27: Accounting Ingest

Ingests vendor invoices, bills, packing slips, quotes, and purchase orders into ProShop and QuickBooks Online. Processes email attachments and scanned documents (PDF/image) via Claude AI extraction, fuzzy-matches contacts, and uploads via GraphQL mutations. Includes scan-burst-classify pipeline, tool receiving labels, and VPO receiving automation.

## Key Files

- `accounting_ingest.py` — Main script v1.4.0: ProShopClient, QBOClient, AIExtractor (burst_pdf, classify, extract, classify_html, extract_html), email body extraction, debounced vendor search, manual label printing, cert filing by VPO
- `qbo_auth.py` — QBO OAuth 2.0 production token exchange (manual paste-URL flow via Intuit Playground redirect)
- `tool_receiving_labels.py` — Tool receiving label generator: VPO→tool library lookup (two-client), Brother PT-P700 label printing via P22 print service
- `scan_relay.py` — Watches Pictures folder, moves stable PDFs to Scanned folder
- `proshop_fields.py` — ProShop schema introspection utilities
- `diag_purchase_order.py` — Diagnostic for addPurchaseOrder mutation permissions
- `proshop_basic_auth_test.py` / `proshop_basic_auth_test2.py` — Basic auth (`/api/beginsession`) probes proving `addCustomerPo` works under user-credential flow where OAuth+`auth_010` was blocked

## Interfaces

Produces: ProShop purchase orders (addPurchaseOrder), bills (addBill), packing slips (addPackingSlip), customer POs (addCustomerPo — production pipeline currently doesn't write these; basic-auth path proven, OAuth path blocked historically), quotes (addQuote); VPO receiving (updatePurchaseOrder mutation — receivedQty/releasedQty); tool receiving labels (PNG via P22 print service, manual button only); QBO bills (production API, realm 123146014753554); cert PDFs filed by VPO in Accounting Inbox/Certs/VPO-XXXXXX/; burst PDFs in Accounting Inbox/Scanned/burst/
Consumes: ProShop GraphQL API (ACCOUNTING_CLIENT_ID for purchaseorders/customerpos scope, TOOLKIOSK_CLIENT_ID for tools scope), QBO REST API (OAuth 2.0 production, refresh token auto-renews), Microsoft Graph API (email attachments + email body text via get_body()), Claude AI API (Sonnet for extraction, Haiku for HTML classification), P22 print service (10.1.1.242:5002 /api/print-image), .traxis.env (credentials), Scanner → Pictures folder (scan_relay.py)
Contracts: PO line items use `toolNumber` field (not `itemNumber`) for tools and COTS. `orderNumber` field carries brand + EDP. `shipTo` defaults to Traxis MFG 511 E St Elmo Rd. updatePurchaseOrder mutation: `id` is a separate arg (not inside `data`), poItems use selector {field: "orderNumber", value: "..."} + data {receivedQty, releasedQty, receivedDate, releasedDate}. P22 print service contract: POST /api/print-image with {image_base64, copies, label_name}. Customer PO mutations: OAuth path historically blocked at `acceptNewRecord` permission (root cause unknown); basic-auth flow (`/api/beginsession` with PROSHOP_USERNAME=full-email + PROSHOP_PASSWORD + space-delimited scope) bypasses this and works for `addCustomerPo`. Service user `auth_010` deleted 2026-05-06; AccountingConnector OAuth client is now mapped to nothing/undefined.

## Next Steps

- **[NEEDS WOLFGANG]** Send drafted email to Joao @ Adion (text in `joao_reply_2026-05-06.txt`, also on clipboard). Use Outlook with From = wolfgang@traxismfg.com.
- **Test other heavy mutations under basic auth** before migrating the production pipeline — confirm `addPurchaseOrder`, `addBill`, `addPackingSlip`, equipment mutations, and `updatePurchaseOrder` all work via the basic-auth session token. Today we only proved `addCustomerPo`.
- **Migrate `accounting_ingest.py` from OAuth to basic auth** once the above confirms no functional gaps. Wrap a `BasicAuthSession` class that handles 300s session expiry by re-`beginsession`ing on 401. **Share this class with P35** — `purchasing/proshop_basic_auth.py` per P35 PLAN.md Phase 2; build it once, import from both. Trade-offs: audit log shows Wolfgang's name on every mutation; pipeline breaks silently on password rotation.

- **Bundle all `addCustomerPo` field-shape fixes with the basic-auth migration** — schema introspection 2026-05-06 found `AddCustomerPoInput` is 25 fields and `UpdateCustomerPoPartOrderedDataInput` is 25 line-item fields; current `_upload_customer_po` (accounting_ingest.py:1488) sends only 8 header fields and zero line items. Three concrete improvements to land in one pass:
  1. **Fix `fob`/`shiptoAddress` mapping bug** (line 1502-1503): `data["ship_to"]` is currently being written to `fob` (freight-on-board enum) instead of `shiptoAddress`. Two-line fix.
  2. **Send `partsOrdered`** — mirror `_build_po_items` from the vendor side. AI extraction already pulls line items for vendor POs; same shape feeds this. Maps to: `part` (our part#), `clientPartNumber`, `quantityOrdered`, `pricePer`, `dueDate`, `requestDate`, `partRev`, `drawingRev`, `lineItemNotes`, `firstArticleRequired`. Customer POs currently ingest as bodyless headers — this is the highest-value gap.
  3. **Fill QBO-relevant fields** — `taxStatus`, `paymentTermsDiscount`, `paymentTermsDiscountDays`, `currency` from extraction. Lets QBO bill creation pull a more accurate record from the same source instead of needing manual entry.
  Reference: P35's `probe_addpo_api.py` is the introspection harness — extend it (or copy the pattern) for customer-PO probing if needed before implementation.
- **Watch for Joao's reply** on (a) whether any API operations are OAuth-only — answer determines whether we keep OAuth around at all, and (b) whether `acceptNewRecord` control gets documented via his developer ticket — needed if we want a proper service account someday.
- **If OAuth is kept around for any reason**, set up a fresh service user once `acceptNewRecord` control is documented. Don't repeat the 010 dead-end.
