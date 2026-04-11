"""
Traxis Accounting Ingest Tool v1.2.0

Monitors accounting@traxismfg.com (via Microsoft Graph API) and the scanned
documents folder for incoming accounting documents. Uses Claude AI to classify
and route documents:

  - Vendor invoices  → QuickBooks Online (Bills via API)
  - Packing slips    → ProShop addPackingSlip
  - Customer POs     → ProShop addCustomerPo
  - Vendor POs/quotes → ProShop addPurchaseOrder
  - Customer quotes  → ProShop addQuote
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
import json
import sqlite3
import requests
import base64
import io
import re
from pathlib import Path
from datetime import datetime, timezone
import anthropic

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

# ─── Configuration ────────────────────────────────────────────────────────────

VERSION = "1.2.0"
APP_TITLE = f"Traxis Accounting Ingest v{VERSION}"

SCAN_FOLDER  = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\Scanned")
EMAIL_FOLDER = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\From Email")
DB_PATH      = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\ingest_queue.db")

GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/inbox/messages"
GRAPH_ATTACHMENTS_URL = "https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{msg_id}/attachments"

PROSHOP_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
PROSHOP_GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"

QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
# Toggle: "sandbox" or "production" — switch after Intuit approves production keys
QBO_ENVIRONMENT = ENV.get("QBO_ENVIRONMENT", "sandbox")
QBO_BASE_URLS = {
    "sandbox":    "https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}",
    "production": "https://quickbooks.api.intuit.com/v3/company/{realm_id}",
}
QBO_BASE_URL = QBO_BASE_URLS[QBO_ENVIRONMENT]
QBO_APP_URLS = {
    "sandbox":    "https://app.sandbox.qbo.intuit.com/app/bill?txnId={bill_id}",
    "production": "https://app.qbo.intuit.com/app/bill?txnId={bill_id}",
}

DOC_TYPES = ["VENDOR_INVOICE", "PACKING_SLIP", "CUSTOMER_PO", "VENDOR_PO", "CUSTOMER_QUOTE", "UNKNOWN"]
DOC_TYPE_LABELS = {
    "VENDOR_INVOICE": "Vendor Invoice → QBO",
    "PACKING_SLIP":   "Packing Slip → ProShop",
    "CUSTOMER_PO":    "Customer PO → ProShop",
    "VENDOR_PO":      "Vendor PO / Quote → ProShop",
    "CUSTOMER_QUOTE": "Customer Quote → ProShop",
    "UNKNOWN":        "Unknown",
}
# Doc types that go to QBO instead of ProShop
QBO_DOC_TYPES = {"VENDOR_INVOICE"}

EMAIL_POLL_INTERVAL = 300  # seconds
FOLDER_POLL_INTERVAL = 10  # seconds

# ─── Credential Loading ────────────────────────────────────────────────────────

def load_env():
    paths = [
        Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env"),
        Path(r"C:\Users\TRAXIS\.traxis.env"),
    ]
    env = {}
    for p in paths:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            break
    return env

ENV = load_env()

def _update_env_value(key, value):
    """Overwrite a single KEY=value line in .traxis.env (used to persist refreshed QBO tokens)."""
    paths = [
        Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env"),
        Path(r"C:\Users\TRAXIS\.traxis.env"),
    ]
    for p in paths:
        if p.exists():
            lines = p.read_text().splitlines()
            new_lines = [f"{key}={value}" if ln.startswith(f"{key}=") else ln for ln in lines]
            p.write_text("\n".join(new_lines) + "\n")
            break

# ─── Database ─────────────────────────────────────────────────────────────────

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS email_log (
            id          INTEGER PRIMARY KEY,
            graph_id    TEXT UNIQUE,
            from_addr   TEXT,
            subject     TEXT,
            received_at TEXT,
            processed   INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id                INTEGER PRIMARY KEY,
            source            TEXT,
            source_ref        TEXT,
            doc_type          TEXT,
            status            TEXT DEFAULT 'PENDING',
            pdf_path          TEXT,
            extracted_json    TEXT,
            edited_json       TEXT,
            contact_name      TEXT,
            confidence        REAL DEFAULT 0,
            created_at        TEXT,
            reviewed_at       TEXT,
            proshop_id        TEXT,
            proshop_url       TEXT,
            upload_error      TEXT,
            from_addr         TEXT,
            doc_hash          TEXT,
            duplicate_of      INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sender_blocklist (
            id          INTEGER PRIMARY KEY,
            from_addr   TEXT UNIQUE,
            reason      TEXT,
            added_at    TEXT
        )
    """)
    # Migrations — add columns that didn't exist in earlier versions
    existing = {row[1] for row in con.execute("PRAGMA table_info(queue)")}
    if "from_addr" not in existing:
        con.execute("ALTER TABLE queue ADD COLUMN from_addr TEXT")
    if "doc_hash" not in existing:
        con.execute("ALTER TABLE queue ADD COLUMN doc_hash TEXT")
    if "duplicate_of" not in existing:
        con.execute("ALTER TABLE queue ADD COLUMN duplicate_of INTEGER")
    con.commit()
    con.close()

def is_sender_blocked(from_addr):
    con = db()
    row = con.execute("SELECT id FROM sender_blocklist WHERE from_addr=?",
                      (from_addr.lower(),)).fetchone()
    con.close()
    return row is not None

def add_sender_to_blocklist(from_addr, reason=""):
    con = db()
    con.execute("""
        INSERT OR IGNORE INTO sender_blocklist (from_addr, reason, added_at)
        VALUES (?,?,?)
    """, (from_addr.lower(), reason, datetime.now(timezone.utc).isoformat()))
    con.commit()
    con.close()

def make_doc_hash(extracted):
    """Hash vendor/customer + reference number + amount for duplicate detection."""
    import hashlib
    vendor  = (extracted.get("vendor_name") or extracted.get("customer_name") or "").strip().lower()
    ref     = (extracted.get("invoice_number") or extracted.get("po_number") or
               extracted.get("packing_slip_number") or extracted.get("quote_number") or "").strip().lower()
    amount  = str(extracted.get("total_amount") or extracted.get("subtotal") or "").strip()
    raw = f"{vendor}|{ref}|{amount}"
    return hashlib.sha256(raw.encode()).hexdigest()

def check_local_duplicate(doc_hash):
    """Returns (queue_id, status) of existing record with same hash, or None."""
    con = db()
    row = con.execute(
        "SELECT id, status FROM queue WHERE doc_hash=? AND status != 'REJECTED' ORDER BY id ASC LIMIT 1",
        (doc_hash,)
    ).fetchone()
    con.close()
    return row  # (id, status) or None

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# ─── Graph API ────────────────────────────────────────────────────────────────

class GraphClient:
    def __init__(self):
        self.token = None
        self.expires_at = 0

    def _get_token(self):
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        url = GRAPH_TOKEN_URL.format(tenant_id=ENV["GRAPH_TENANT_ID"])
        r = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": ENV["GRAPH_CLIENT_ID"],
            "client_secret": ENV["GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        })
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data.get("expires_in", 3600)
        return self.token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    def get_unread_with_attachments(self):
        url = GRAPH_MESSAGES_URL.format(mailbox=ENV["GRAPH_MAILBOX"])
        params = {
            "$filter": "hasAttachments eq true and receivedDateTime ge 2026-03-15T00:00:00Z",
            "$select": "id,subject,from,receivedDateTime,hasAttachments",
            "$top": "50",
        }
        r = requests.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json().get("value", [])

    def get_attachments(self, msg_id):
        url = GRAPH_ATTACHMENTS_URL.format(
            mailbox=ENV["GRAPH_MAILBOX"], msg_id=msg_id
        )
        r = requests.get(url, headers=self._headers())
        r.raise_for_status()
        return r.json().get("value", [])

    def mark_read(self, msg_id):
        url = f"https://graph.microsoft.com/v1.0/users/{ENV['GRAPH_MAILBOX']}/messages/{msg_id}"
        requests.patch(url, headers=self._headers(), json={"isRead": True})

# ─── ProShop Client ───────────────────────────────────────────────────────────

class ProShopClient:
    def __init__(self):
        self.token = None
        self.expires_at = 0
        self._contacts_cache = None
        self._contacts_cache_time = 0

    def _get_token(self):
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        r = requests.post(PROSHOP_TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": ENV["ACCOUNTING_CLIENT_ID"],
            "client_secret": ENV["ACCOUNTING_CLIENT_SECRET"],
            "scope": ENV["ACCOUNTING_SCOPE"],
        })
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data.get("expires_in", 86400) - 60
        return self.token

    def query(self, gql, variables=None):
        r = requests.post(
            PROSHOP_GRAPHQL_URL,
            headers={"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"},
            json={"query": gql, "variables": variables or {}},
            timeout=30,
        )
        r.raise_for_status()
        result = r.json()
        if "errors" in result:
            raise RuntimeError(result["errors"][0]["message"])
        return result.get("data", {})

    def get_contacts(self):
        if self._contacts_cache and time.time() - self._contacts_cache_time < 3600:
            return self._contacts_cache
        data = self.query("{ contacts(pageSize: 500) { records { name companyName } } }")
        self._contacts_cache = data.get("contacts", {}).get("records", [])
        self._contacts_cache_time = time.time()
        return self._contacts_cache

    def fuzzy_match_contact(self, company_name):
        """Returns list of (score, contact) sorted best first."""
        import difflib
        contacts = self.get_contacts()
        results = []
        name_lower = company_name.lower()
        for c in contacts:
            cn = (c.get("companyName") or "").lower()
            score = difflib.SequenceMatcher(None, name_lower, cn).ratio()
            results.append((score, c))
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:5]

    def add_bill(self, data):
        gql = """
        mutation AddBill($data: AddBillInput!) {
          addBill(data: $data) { billId proshopUrl }
        }"""
        return self.query(gql, {"data": data})

    def add_packing_slip(self, data):
        gql = """
        mutation AddPackingSlip($data: AddPackingSlipInput!) {
          addPackingSlip(data: $data) { packingSlipId proshopUrl }
        }"""
        return self.query(gql, {"data": data})

    def add_customer_po(self, data):
        gql = """
        mutation AddCustomerPo($data: AddCustomerPoInput!) {
          addCustomerPo(data: $data) { poId proshopUrl }
        }"""
        return self.query(gql, {"data": data})

    def add_purchase_order(self, data):
        gql = """
        mutation AddPurchaseOrder($data: AddPurchaseOrderInput!) {
          addPurchaseOrder(data: $data) { purchaseOrderId proshopUrl }
        }"""
        return self.query(gql, {"data": data})

    def add_quote(self, data):
        gql = """
        mutation AddQuote($data: AddQuoteInput!) {
          addQuote(data: $data) { quoteId proshopUrl }
        }"""
        return self.query(gql, {"data": data})


# ─── QuickBooks Online Client ─────────────────────────────────────────────────

class QBOClient:
    """QuickBooks Online API client — OAuth2 refresh-token flow."""

    def __init__(self):
        self.access_token = None
        self.expires_at = 0
        self._vendors_cache = None
        self._vendors_cache_time = 0
        self._default_account_ref = None

    def _refresh(self):
        if self.access_token and time.time() < self.expires_at - 60:
            return self.access_token
        creds = base64.b64encode(
            f"{ENV['QBO_CLIENT_ID']}:{ENV['QBO_CLIENT_SECRET']}".encode()
        ).decode()
        r = requests.post(QBO_TOKEN_URL, headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }, data={
            "grant_type": "refresh_token",
            "refresh_token": ENV["QBO_REFRESH_TOKEN"],
        })
        r.raise_for_status()
        data = r.json()
        self.access_token = data["access_token"]
        self.expires_at = time.time() + data.get("expires_in", 3600)
        new_refresh = data.get("refresh_token")
        if new_refresh and new_refresh != ENV.get("QBO_REFRESH_TOKEN"):
            ENV["QBO_REFRESH_TOKEN"] = new_refresh
            _update_env_value("QBO_REFRESH_TOKEN", new_refresh)
        return self.access_token

    def _url(self, path):
        return QBO_BASE_URL.format(realm_id=ENV["QBO_REALM_ID"]) + "/" + path

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._refresh()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _raise_qbo_error(self, r):
        """Raise with intuit_tid for Intuit support troubleshooting."""
        tid = r.headers.get("intuit_tid", "unknown")
        try:
            body = r.json()
            fault = body.get("Fault", {}).get("Error", [{}])[0]
            detail = fault.get("Detail", fault.get("Message", r.text))
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(
            f"QBO API {r.status_code}: {detail}  [intuit_tid={tid}]"
        )

    def qbo_query(self, sql):
        r = requests.get(self._url("query"), headers=self._headers(),
                         params={"query": sql, "minorversion": "65"})
        if not r.ok:
            self._raise_qbo_error(r)
        return r.json()

    def get_vendors(self):
        if self._vendors_cache and time.time() - self._vendors_cache_time < 3600:
            return self._vendors_cache
        data = self.qbo_query("SELECT * FROM Vendor MAXRESULTS 500")
        self._vendors_cache = data.get("QueryResponse", {}).get("Vendor", [])
        self._vendors_cache_time = time.time()
        return self._vendors_cache

    def fuzzy_match_vendor(self, name):
        import difflib
        vendors = self.get_vendors()
        results = []
        name_lower = name.lower()
        for v in vendors:
            vn = v.get("DisplayName", "").lower()
            score = difflib.SequenceMatcher(None, name_lower, vn).ratio()
            results.append((score, v))
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:5]

    def get_default_expense_account(self):
        if self._default_account_ref:
            return self._default_account_ref
        # Prefer Cost of Goods Sold, fall back to any Expense account
        for acct_type in ("Cost of Goods Sold", "Expense"):
            data = self.qbo_query(
                f"SELECT * FROM Account WHERE AccountType = '{acct_type}' MAXRESULTS 1"
            )
            accts = data.get("QueryResponse", {}).get("Account", [])
            if accts:
                self._default_account_ref = {
                    "value": accts[0]["Id"],
                    "name": accts[0]["Name"],
                }
                return self._default_account_ref
        return {"value": "1"}  # last-resort fallback

    def create_bill(self, extracted, vendor_id, vendor_display=""):
        """Create a Bill in QBO.  Returns (bill_id, qbo_url)."""
        account_ref = self.get_default_expense_account()

        # Build line items from extracted data, or single total line
        lines = []
        for item in extracted.get("line_items", []):
            try:
                amt = float(
                    str(item.get("extended_price") or item.get("unit_price") or 0)
                    .replace(",", "").replace("$", "").strip()
                )
            except (ValueError, TypeError):
                amt = 0.0
            if amt > 0:
                lines.append({
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": round(amt, 2),
                    "Description": item.get("description", ""),
                    "AccountBasedExpenseLineDetail": {
                        "AccountRef": account_ref,
                        "BillableStatus": "NotBillable",
                    },
                })

        if not lines:
            try:
                total = float(
                    str(extracted.get("total_amount") or extracted.get("subtotal") or 0)
                    .replace(",", "").replace("$", "").strip()
                )
            except (ValueError, TypeError):
                total = 0.0
            lines.append({
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": round(total, 2),
                "Description": f"Invoice {extracted.get('invoice_number', '')}".strip(),
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": account_ref,
                    "BillableStatus": "NotBillable",
                },
            })

        bill = {
            "Line": lines,
            "VendorRef": {"value": vendor_id, "name": vendor_display},
        }
        if extracted.get("invoice_date"):
            bill["TxnDate"] = extracted["invoice_date"]
        if extracted.get("due_date"):
            bill["DueDate"] = extracted["due_date"]
        if extracted.get("invoice_number"):
            bill["DocNumber"] = extracted["invoice_number"]
        if extracted.get("notes"):
            bill["PrivateNote"] = extracted["notes"]

        r = requests.post(
            self._url("bill"),
            headers=self._headers(),
            params={"minorversion": "65"},
            json={"Bill": bill},
        )
        if not r.ok:
            self._raise_qbo_error(r)
        result = r.json()
        bill_id = result.get("Bill", {}).get("Id", "")
        qbo_url = QBO_APP_URLS[QBO_ENVIRONMENT].format(bill_id=bill_id)
        return bill_id, qbo_url

    def attach_pdf(self, entity_type, entity_id, pdf_path):
        """Upload a PDF and attach it to a QBO entity (e.g. Bill).
        Uses the Attachable upload endpoint (multipart)."""
        p = Path(pdf_path)
        if not p.exists():
            return None
        metadata = json.dumps({
            "AttachableRef": [{"EntityRef": {"type": entity_type, "value": entity_id}}],
            "FileName": p.name,
            "ContentType": "application/pdf",
        })
        r = requests.post(
            self._url("upload"),
            headers={"Authorization": f"Bearer {self._refresh()}", "Accept": "application/json"},
            params={"minorversion": "65"},
            files={
                "file_metadata_0": ("metadata.json", metadata, "application/json"),
                "file_content_0": (p.name, p.read_bytes(), "application/pdf"),
            },
        )
        if not r.ok:
            self._raise_qbo_error(r)
        return r.json()

    def check_duplicate_bill(self, doc_number):
        """Return QBO URL if a Bill with this DocNumber already exists, else None."""
        if not doc_number:
            return None
        try:
            safe = doc_number.replace("'", "\\'")
            data = self.qbo_query(
                f"SELECT * FROM Bill WHERE DocNumber = '{safe}' MAXRESULTS 1"
            )
            bills = data.get("QueryResponse", {}).get("Bill", [])
            if bills:
                bid = bills[0].get("Id", "")
                return QBO_APP_URLS[QBO_ENVIRONMENT].format(bill_id=bid)
        except Exception:
            pass
        return None


# ─── Claude AI Extractor ──────────────────────────────────────────────────────

EXTRACTION_PROMPTS = {
    "VENDOR_INVOICE": """Extract all data from this vendor invoice. Return JSON with these fields:
{
  "vendor_name": "company name on the invoice",
  "invoice_number": "invoice/reference number",
  "invoice_date": "date issued (YYYY-MM-DD)",
  "due_date": "payment due date (YYYY-MM-DD) or null",
  "total_amount": "total dollar amount as string e.g. '1234.56'",
  "subtotal": "subtotal before tax/shipping or null",
  "tax_amount": "tax amount or null",
  "shipping_amount": "shipping/freight amount or null",
  "payment_terms": "e.g. Net 30 or null",
  "notes": "any special notes or null",
  "line_items": [
    {"description": "...", "quantity": "...", "unit_price": "...", "extended_price": "..."}
  ],
  "confidence": 0.0-1.0
}""",

    "PACKING_SLIP": """Extract all data from this packing slip/delivery note. Return JSON:
{
  "vendor_name": "shipper/vendor company name",
  "packing_slip_number": "packing slip or delivery number",
  "ship_date": "date shipped (YYYY-MM-DD) or null",
  "po_number": "related PO number or null",
  "carrier": "shipping carrier e.g. UPS, FedEx or null",
  "tracking_number": "tracking number or null",
  "ship_method": "shipping method or null",
  "line_items": [
    {"part_number": "...", "description": "...", "quantity_shipped": "...", "quantity_ordered": "..."}
  ],
  "notes": "any notes or null",
  "confidence": 0.0-1.0
}""",

    "CUSTOMER_PO": """Extract all data from this customer purchase order. Return JSON:
{
  "customer_name": "customer company name",
  "po_number": "purchase order number (REQUIRED)",
  "po_date": "date of PO (YYYY-MM-DD) (REQUIRED)",
  "buyer_name": "buyer contact name or null",
  "buyer_email": "buyer email or null",
  "ship_to": "shipping address or null",
  "bill_to": "billing address or null",
  "payment_terms": "e.g. Net 30 or null",
  "required_date": "delivery required by date (YYYY-MM-DD) or null",
  "total_amount": "total PO value or null",
  "line_items": [
    {"line_number": "...", "part_number": "...", "description": "...", "quantity": "...", "unit_price": "...", "extended_price": "...", "required_date": "..."}
  ],
  "notes": "any special instructions or null",
  "confidence": 0.0-1.0
}""",

    "VENDOR_PO": """Extract all data from this vendor quote or purchase order. Return JSON:
{
  "vendor_name": "vendor/supplier company name",
  "quote_number": "quote or PO number or null",
  "quote_date": "date (YYYY-MM-DD) or null",
  "valid_until": "quote validity date (YYYY-MM-DD) or null",
  "total_amount": "total amount or null",
  "lead_time": "lead time e.g. '4-6 weeks' or null",
  "payment_terms": "payment terms or null",
  "line_items": [
    {"part_number": "...", "description": "...", "quantity": "...", "unit_price": "...", "extended_price": "..."}
  ],
  "notes": "any notes or null",
  "confidence": 0.0-1.0
}""",

    "CUSTOMER_QUOTE": """Extract all data from this customer quote or RFQ. Return JSON:
{
  "customer_name": "customer company name",
  "quote_number": "quote or RFQ number or null",
  "quote_date": "date (YYYY-MM-DD) or null",
  "valid_until": "validity date (YYYY-MM-DD) or null",
  "contact_name": "customer contact name or null",
  "contact_email": "customer contact email or null",
  "total_amount": "total amount or null",
  "line_items": [
    {"part_number": "...", "description": "...", "quantity": "...", "unit_price": "...", "extended_price": "..."}
  ],
  "notes": "any notes or null",
  "confidence": 0.0-1.0
}""",
}

CLASSIFY_PROMPT = """Look at this document and classify it as exactly one of:
VENDOR_INVOICE - a bill/invoice FROM a vendor/supplier TO us
PACKING_SLIP - a delivery/shipping document listing items received
CUSTOMER_PO - a purchase order FROM a customer TO us (they are buying from us)
VENDOR_PO - a quote or PO we are sending TO a vendor, or a vendor's quote response
CUSTOMER_QUOTE - a quote or estimate we are providing TO a customer, or an RFQ from a customer
UNKNOWN - cannot determine

Reply with ONLY the classification word, nothing else."""


class AIExtractor:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ENV.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "")))

    def pdf_to_images(self, pdf_path, max_pages=4):
        """Convert PDF pages to base64 PNG images."""
        if not HAS_FITZ:
            return []
        images = []
        doc = fitz.open(pdf_path)
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            mat = fitz.Matrix(2.0, 2.0)  # 2x scale = ~144dpi
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            images.append(base64.standard_b64encode(img_bytes).decode())
        doc.close()
        return images

    def classify(self, pdf_path, subject="", sender=""):
        """Quick classify — returns doc type string."""
        # Rule-based first
        text = (subject + " " + sender).lower()
        if any(w in text for w in ["invoice", "inv #", "bill", "statement"]):
            return "VENDOR_INVOICE"
        if any(w in text for w in ["packing slip", "delivery note", "shipment"]):
            return "PACKING_SLIP"
        if any(w in text for w in ["purchase order", " po #", "p.o. "]):
            return "CUSTOMER_PO"
        if any(w in text for w in ["quote", "quotation", "rfq", "proposal"]):
            return "CUSTOMER_QUOTE"

        # Fall back to Claude vision
        images = self.pdf_to_images(pdf_path, max_pages=1)
        if not images:
            return "UNKNOWN"
        msg = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": images[0]}},
                    {"type": "text", "text": CLASSIFY_PROMPT},
                ]
            }]
        )
        result = msg.content[0].text.strip().upper()
        return result if result in DOC_TYPES else "UNKNOWN"

    def extract(self, pdf_path, doc_type):
        """Full extraction — returns dict."""
        images = self.pdf_to_images(pdf_path, max_pages=4)
        if not images:
            return {"error": "Could not render PDF", "confidence": 0}

        prompt = EXTRACTION_PROMPTS.get(doc_type, EXTRACTION_PROMPTS["VENDOR_INVOICE"])
        content = []
        for img in images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}})
        content.append({"type": "text", "text": prompt + "\n\nReturn ONLY valid JSON, no explanation."})

        msg = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": content}]
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw, "error": "JSON parse failed", "confidence": 0}


# ─── Email Poller ─────────────────────────────────────────────────────────────

class EmailPoller:
    def __init__(self, graph, extractor, on_new_doc, log):
        self.graph = graph
        self.extractor = extractor
        self.on_new_doc = on_new_doc
        self.log = log
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        while not self._stop:
            try:
                self._poll()
            except Exception as e:
                self.log(f"Email poll error: {e}")
            for _ in range(EMAIL_POLL_INTERVAL):
                if self._stop:
                    return
                time.sleep(1)

    def _poll(self):
        msgs = self.graph.get_unread_with_attachments()
        if not msgs:
            return
        self.log(f"Found {len(msgs)} unread email(s) with attachments")
        con = db()
        for msg in msgs:
            gid = msg["id"]
            row = con.execute("SELECT id FROM email_log WHERE graph_id=?", (gid,)).fetchone()
            if row:
                continue
            subject = msg.get("subject", "")
            sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
            received = msg.get("receivedDateTime", "")
            con.execute(
                "INSERT OR IGNORE INTO email_log (graph_id, from_addr, subject, received_at) VALUES (?,?,?,?)",
                (gid, sender, subject, received)
            )
            con.commit()
            self._process_message(msg, subject, sender, con)
        con.close()

    def _process_message(self, msg, subject, sender, con):
        # Skip internal Traxis emails
        if sender.lower().endswith("@traxismfg.com"):
            self.log(f"Skipping internal email from {sender}")
            return
        # Skip blocked senders
        if is_sender_blocked(sender):
            self.log(f"Skipping blocked sender: {sender}")
            return

        attachments = self.graph.get_attachments(msg["id"])
        for att in attachments:
            name = att.get("name", "")
            # Email attachments: PDFs only — images from email are not accounting docs
            if not name.lower().endswith(".pdf"):
                continue
            content_bytes = att.get("contentBytes")
            if not content_bytes:
                continue
            # Save to email folder
            safe_name = re.sub(r'[^\w\.\-]', '_', name)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = EMAIL_FOLDER / f"{ts}_{safe_name}"
            EMAIL_FOLDER.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(base64.b64decode(content_bytes))
            self.log(f"Saved attachment: {out_path.name}")
            self._enqueue(str(out_path), "email", msg["id"], subject, sender, con)

    def _enqueue(self, pdf_path, source, source_ref, subject, sender, con):
        doc_type = self.extractor.classify(pdf_path, subject, sender)
        extracted = self.extractor.extract(pdf_path, doc_type)
        doc_hash = make_doc_hash(extracted)
        existing = check_local_duplicate(doc_hash)
        status = "POSSIBLE_DUPLICATE" if existing else "PENDING"
        duplicate_of = existing[0] if existing else None

        con.execute("""
            INSERT INTO queue (source, source_ref, doc_type, pdf_path, extracted_json, confidence,
                               created_at, from_addr, doc_hash, duplicate_of, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (source, source_ref, doc_type, pdf_path,
              json.dumps(extracted),
              extracted.get("confidence", 0),
              datetime.now(timezone.utc).isoformat(),
              sender, doc_hash, duplicate_of, status))
        con.commit()
        if existing:
            self.log(f"Possible duplicate of queue #{existing[0]}: {Path(pdf_path).name}")
        else:
            self.log(f"Queued: {doc_type} — {Path(pdf_path).name}")
        self.on_new_doc()


# ─── Folder Watcher ───────────────────────────────────────────────────────────

class FolderWatcher:
    def __init__(self, extractor, on_new_doc, log):
        self.extractor = extractor
        self.on_new_doc = on_new_doc
        self.log = log
        self._stop = False
        self._seen = set()

    def stop(self):
        self._stop = True

    def run(self):
        # Pre-seed seen set with already-queued scan files
        con = db()
        rows = con.execute("SELECT pdf_path FROM queue WHERE source='scan'").fetchall()
        self._seen = {r[0] for r in rows}
        con.close()

        while not self._stop:
            try:
                self._check()
            except Exception as e:
                self.log(f"Folder watch error: {e}")
            for _ in range(FOLDER_POLL_INTERVAL):
                if self._stop:
                    return
                time.sleep(1)

    def _check(self):
        if not SCAN_FOLDER.exists():
            return
        for f in SCAN_FOLDER.iterdir():
            if f.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"):
                continue
            if str(f) in self._seen:
                continue
            self._seen.add(str(f))
            self.log(f"New scan detected: {f.name}")
            doc_type = self.extractor.classify(str(f))
            extracted = self.extractor.extract(str(f), doc_type)
            con = db()
            con.execute("""
                INSERT INTO queue (source, source_ref, doc_type, pdf_path, extracted_json, confidence, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, ("scan", f.name, doc_type, str(f),
                  json.dumps(extracted),
                  extracted.get("confidence", 0),
                  datetime.now(timezone.utc).isoformat()))
            con.commit()
            con.close()
            self.on_new_doc()


# ─── ProShop Uploader ─────────────────────────────────────────────────────────

class ProShopUploader:
    def __init__(self, proshop, log):
        self.proshop = proshop
        self.log = log

    def upload(self, queue_id, doc_type, edited_json, contact_name):
        """Upload a reviewed record to ProShop. Returns (proshop_id, proshop_url)."""
        data = json.loads(edited_json)

        if doc_type == "VENDOR_INVOICE":
            result = self._upload_bill(data, contact_name)
            rec = result.get("addBill", {})
            return rec.get("billId"), rec.get("proshopUrl")

        elif doc_type == "PACKING_SLIP":
            result = self._upload_packing_slip(data, contact_name)
            rec = result.get("addPackingSlip", {})
            return rec.get("packingSlipId"), rec.get("proshopUrl")

        elif doc_type == "CUSTOMER_PO":
            result = self._upload_customer_po(data, contact_name)
            rec = result.get("addCustomerPo", {})
            return rec.get("poId"), rec.get("proshopUrl")

        elif doc_type == "VENDOR_PO":
            result = self._upload_purchase_order(data, contact_name)
            rec = result.get("addPurchaseOrder", {})
            return rec.get("purchaseOrderId"), rec.get("proshopUrl")

        elif doc_type == "CUSTOMER_QUOTE":
            result = self._upload_quote(data, contact_name)
            rec = result.get("addQuote", {})
            return rec.get("quoteId"), rec.get("proshopUrl")

        else:
            raise ValueError(f"Unknown doc type: {doc_type}")

    def _upload_bill(self, data, contact_name):
        payload = {}
        if contact_name:
            payload["supplier"] = contact_name
        if data.get("invoice_number"):
            payload["referenceNumber"] = data["invoice_number"]
        if data.get("invoice_date"):
            payload["dateIssued"] = data["invoice_date"]
        if data.get("due_date"):
            payload["dueDate"] = data["due_date"]
        if data.get("notes"):
            payload["note"] = data["notes"]
        payload["year"] = (data.get("invoice_date") or "")[:4] or str(datetime.now().year)
        return self.proshop.add_bill(payload)

    def _upload_packing_slip(self, data, contact_name):
        payload = {}
        if contact_name:
            payload["soldTo"] = contact_name
        if data.get("carrier"):
            payload["shipVia"] = data["carrier"]
        if data.get("notes"):
            payload["specialInstructions"] = data["notes"]
        payload["year"] = str(datetime.now().year)
        return self.proshop.add_packing_slip(payload)

    def _upload_customer_po(self, data, contact_name):
        payload = {}
        if contact_name:
            payload["client"] = contact_name
        if data.get("po_number"):
            payload["clientPONumber"] = data["po_number"]
        if data.get("po_date"):
            payload["dateEntered"] = data["po_date"]
        if data.get("payment_terms"):
            payload["paymentTerms"] = data["payment_terms"]
        if data.get("notes"):
            payload["notes"] = data["notes"]
        payload["year"] = (data.get("po_date") or "")[:4] or str(datetime.now().year)
        return self.proshop.add_customer_po(payload)

    def _upload_purchase_order(self, data, contact_name):
        payload = {"poType": "Standard"}
        if contact_name:
            payload["supplier"] = contact_name
        if data.get("notes"):
            payload["remarks"] = data["notes"]
        payload["year"] = (data.get("quote_date") or "")[:4] or str(datetime.now().year)
        return self.proshop.add_purchase_order(payload)

    def _upload_quote(self, data, contact_name):
        payload = {}
        if contact_name:
            payload["client"] = contact_name
        if data.get("notes"):
            payload["notes"] = data["notes"]
        payload["year"] = (data.get("quote_date") or "")[:4] or str(datetime.now().year)
        return self.proshop.add_quote(payload)


# ─── Main Application Window ──────────────────────────────────────────────────

class AccountingIngestApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1000, 700)

        # Services
        self.graph = GraphClient()
        self.proshop = ProShopClient()
        self.qbo = QBOClient()
        self.extractor = AIExtractor()
        self.uploader = ProShopUploader(self.proshop, self._log)

        # State
        self._current_id = None
        self._current_doc = None
        self._current_doc_type = None
        self._pdf_images = []
        self._pdf_page = 0
        self._contact_matches = []     # ProShop contacts
        self._qbo_vendor_matches = []  # QBO vendors

        init_db()
        self._build_ui()
        self._start_workers()
        self._refresh_queue()
        self._log("Ready. Monitoring email and scan folder.")

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        self.configure(bg="#1e1e1e")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#1e1e1e", foreground="#ffffff", fieldbackground="#2d2d2d")
        style.configure("Treeview", background="#2d2d2d", foreground="#ffffff",
                        fieldbackground="#2d2d2d", rowheight=26)
        style.configure("Treeview.Heading", background="#3a3a3a", foreground="#ffffff")
        style.map("Treeview", background=[("selected", "#0078d4")])
        style.configure("TButton", padding=6)
        style.configure("TLabel", background="#1e1e1e", foreground="#ffffff")
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabelframe", background="#1e1e1e", foreground="#aaaaaa")
        style.configure("TLabelframe.Label", background="#1e1e1e", foreground="#aaaaaa")
        style.configure("TCombobox", fieldbackground="#2d2d2d", foreground="#ffffff")
        style.configure("TEntry", fieldbackground="#2d2d2d", foreground="#ffffff", insertcolor="#ffffff")

        # Top bar
        topbar = tk.Frame(self, bg="#0078d4", height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text=APP_TITLE, bg="#0078d4", fg="white",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=8)
        self._status_label = tk.Label(topbar, text="", bg="#0078d4", fg="#cce4ff",
                                      font=("Segoe UI", 10))
        self._status_label.pack(side="right", padx=16)

        # Main panes: queue left, review right
        paned = tk.PanedWindow(self, orient="horizontal", bg="#1e1e1e",
                               sashwidth=6, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        # Left: queue panel
        left = tk.Frame(paned, bg="#1e1e1e")
        paned.add(left, minsize=340)
        self._build_queue_panel(left)

        # Right: review panel
        right = tk.Frame(paned, bg="#1e1e1e")
        paned.add(right, minsize=600)
        self._build_review_panel(right)

        # Bottom log
        log_frame = tk.Frame(self, bg="#111111", height=110)
        log_frame.pack(fill="x")
        log_frame.pack_propagate(False)
        self._log_text = tk.Text(log_frame, bg="#111111", fg="#888888",
                                 font=("Consolas", 9), state="disabled",
                                 relief="flat", bd=0, height=6)
        self._log_text.pack(fill="both", expand=True, padx=8, pady=4)

    def _build_queue_panel(self, parent):
        tk.Label(parent, text="DOCUMENT QUEUE", bg="#1e1e1e", fg="#888888",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        # Toolbar
        tb = tk.Frame(parent, bg="#1e1e1e")
        tb.pack(fill="x", padx=8, pady=2)
        ttk.Button(tb, text="Open File", command=self._open_file).pack(side="left", padx=2)
        ttk.Button(tb, text="Poll Now", command=self._poll_now).pack(side="left", padx=2)
        ttk.Button(tb, text="Refresh", command=self._refresh_queue).pack(side="left", padx=2)
        ttk.Button(tb, text="Open QBO", command=self._open_qbo_folder).pack(side="left", padx=2)

        # Filter
        filter_frame = tk.Frame(parent, bg="#1e1e1e")
        filter_frame.pack(fill="x", padx=8, pady=2)
        tk.Label(filter_frame, text="Show:", bg="#1e1e1e", fg="#888888",
                 font=("Segoe UI", 9)).pack(side="left")
        self._filter_var = tk.StringVar(value="PENDING")
        for val, label in [("PENDING", "Pending"), ("POSSIBLE_DUPLICATE", "Dupes"), ("QBO", "QBO"), ("UPLOADED", "Uploaded"), ("ALL", "All")]:
            tk.Radiobutton(filter_frame, text=label, variable=self._filter_var, value=val,
                           bg="#1e1e1e", fg="#cccccc", selectcolor="#333333",
                           activebackground="#1e1e1e", font=("Segoe UI", 9),
                           command=self._refresh_queue).pack(side="left", padx=4)

        # Queue treeview
        cols = ("type", "source", "date", "confidence")
        self._tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("type", text="Type")
        self._tree.heading("source", text="Source")
        self._tree.heading("date", text="Date")
        self._tree.heading("confidence", text="Conf")
        self._tree.column("type", width=130)
        self._tree.column("source", width=60)
        self._tree.column("date", width=80)
        self._tree.column("confidence", width=50, anchor="center")

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        vsb.pack(side="left", fill="y", pady=4)
        self._tree.bind("<<TreeviewSelect>>", self._on_queue_select)

        # Tag colors
        self._tree.tag_configure("PENDING", foreground="#ffd700")
        self._tree.tag_configure("POSSIBLE_DUPLICATE", foreground="#ff9800")
        self._tree.tag_configure("UPLOADED", foreground="#4caf50")
        self._tree.tag_configure("REJECTED", foreground="#888888")
        self._tree.tag_configure("UPLOAD_FAILED", foreground="#f44336")
        self._tree.tag_configure("QBO", foreground="#00bcd4")

    def _build_review_panel(self, parent):
        # Split horizontally: PDF top/left, fields top/right
        review_paned = tk.PanedWindow(parent, orient="horizontal", bg="#1e1e1e",
                                      sashwidth=6, sashrelief="flat")
        review_paned.pack(fill="both", expand=True, padx=4, pady=4)

        # PDF viewer
        pdf_frame = tk.Frame(review_paned, bg="#2a2a2a")
        review_paned.add(pdf_frame, minsize=400)
        self._build_pdf_viewer(pdf_frame)

        # Fields panel
        fields_frame = tk.Frame(review_paned, bg="#1e1e1e")
        review_paned.add(fields_frame, minsize=320)
        self._build_fields_panel(fields_frame)

    def _build_pdf_viewer(self, parent):
        # Nav bar
        nav = tk.Frame(parent, bg="#2a2a2a")
        nav.pack(fill="x", padx=4, pady=4)
        ttk.Button(nav, text="◀", width=3, command=self._prev_page).pack(side="left")
        self._page_label = tk.Label(nav, text="Page 1 / 1", bg="#2a2a2a", fg="#cccccc",
                                    font=("Segoe UI", 9))
        self._page_label.pack(side="left", padx=8)
        ttk.Button(nav, text="▶", width=3, command=self._next_page).pack(side="left")

        # Canvas
        self._canvas = tk.Canvas(parent, bg="#3a3a3a", cursor="crosshair",
                                 highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self._pdf_tk_image = None

    def _build_fields_panel(self, parent):
        tk.Label(parent, text="EXTRACTED DATA", bg="#1e1e1e", fg="#888888",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        # Doc type selector
        type_frame = tk.Frame(parent, bg="#1e1e1e")
        type_frame.pack(fill="x", padx=8, pady=2)
        tk.Label(type_frame, text="Type:", bg="#1e1e1e", fg="#cccccc",
                 font=("Segoe UI", 9)).pack(side="left")
        self._type_var = tk.StringVar()
        type_cb = ttk.Combobox(type_frame, textvariable=self._type_var,
                               values=[DOC_TYPE_LABELS[t] for t in DOC_TYPES],
                               state="readonly", width=28)
        type_cb.pack(side="left", padx=4)

        # Contact match
        self._contact_frame = ttk.LabelFrame(parent, text="Customer / Vendor")
        contact_frame = self._contact_frame
        contact_frame.pack(fill="x", padx=8, pady=4)
        self._contact_search_var = tk.StringVar()
        self._contact_search_var.trace_add("write", self._on_contact_search)
        ttk.Entry(contact_frame, textvariable=self._contact_search_var).pack(
            fill="x", padx=4, pady=2)
        self._contact_listbox = tk.Listbox(contact_frame, bg="#2d2d2d", fg="#ffffff",
                                           height=4, font=("Segoe UI", 9),
                                           selectbackground="#0078d4")
        self._contact_listbox.pack(fill="x", padx=4, pady=2)
        self._contact_label = tk.Label(contact_frame, text="No match selected",
                                       bg="#1e1e1e", fg="#888888", font=("Segoe UI", 8))
        self._contact_label.pack(anchor="w", padx=4)

        # JSON editor
        json_frame = ttk.LabelFrame(parent, text="Extracted Fields (editable JSON)")
        json_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self._json_text = tk.Text(json_frame, bg="#2d2d2d", fg="#ffffff",
                                  font=("Consolas", 9), wrap="none",
                                  insertbackground="#ffffff")
        json_scroll_v = ttk.Scrollbar(json_frame, orient="vertical",
                                      command=self._json_text.yview)
        json_scroll_h = ttk.Scrollbar(json_frame, orient="horizontal",
                                      command=self._json_text.xview)
        self._json_text.configure(yscrollcommand=json_scroll_v.set,
                                  xscrollcommand=json_scroll_h.set)
        json_scroll_v.pack(side="right", fill="y")
        json_scroll_h.pack(side="bottom", fill="x")
        self._json_text.pack(fill="both", expand=True, padx=2, pady=2)

        # Action buttons
        btn_frame = tk.Frame(parent, bg="#1e1e1e")
        btn_frame.pack(fill="x", padx=8, pady=8)
        self._approve_btn = tk.Button(btn_frame, text="✓  APPROVE & PUSH",
                                      bg="#1a7a3a", fg="white", font=("Segoe UI", 10, "bold"),
                                      relief="flat", padx=12, pady=8,
                                      command=self._approve)
        self._approve_btn.pack(side="left", padx=(0, 4))
        self._extract_btn = tk.Button(btn_frame, text="⟳  Re-extract",
                                      bg="#2a5a7a", fg="white", font=("Segoe UI", 10),
                                      relief="flat", padx=12, pady=8,
                                      command=self._re_extract)
        self._extract_btn.pack(side="left", padx=(0, 4))
        self._reject_btn = tk.Button(btn_frame, text="✗  Reject",
                                     bg="#7a2a2a", fg="white", font=("Segoe UI", 10),
                                     relief="flat", padx=12, pady=8,
                                     command=self._reject)
        self._reject_btn.pack(side="left")

        # ProShop link
        self._link_label = tk.Label(parent, text="", bg="#1e1e1e", fg="#0078d4",
                                    font=("Segoe UI", 9, "underline"), cursor="hand2")
        self._link_label.pack(anchor="w", padx=10, pady=2)
        self._link_label.bind("<Button-1>", self._open_proshop_link)
        self._proshop_url = None

    # ── Queue Management ───────────────────────────────────────────────────

    def _refresh_queue(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        filter_val = self._filter_var.get()
        con = db()
        if filter_val == "ALL":
            rows = con.execute(
                "SELECT id, doc_type, source, created_at, confidence, status FROM queue ORDER BY id DESC"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, doc_type, source, created_at, confidence, status FROM queue WHERE status=? ORDER BY id DESC",
                (filter_val,)
            ).fetchall()
        con.close()

        pending = 0
        for r in rows:
            qid, doc_type, source, created_at, confidence, status = r
            date_str = created_at[:10] if created_at else ""
            conf_str = f"{int((confidence or 0)*100)}%"
            label = DOC_TYPE_LABELS.get(doc_type, doc_type)
            tag = status
            self._tree.insert("", "end", iid=str(qid),
                               values=(label, source, date_str, conf_str), tags=(tag,))
            if status == "PENDING":
                pending += 1

        self._status_label.config(text=f"{pending} pending")

    def _on_queue_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        qid = int(sel[0])
        self._load_record(qid)

    def _load_record(self, qid):
        con = db()
        row = con.execute(
            "SELECT id, doc_type, pdf_path, extracted_json, edited_json, contact_name, proshop_url, status FROM queue WHERE id=?",
            (qid,)
        ).fetchone()
        con.close()
        if not row:
            return

        self._current_id = qid
        qid_v, doc_type, pdf_path, extracted_json, edited_json, contact_name, proshop_url, status = row
        self._current_doc_type = doc_type

        # Set doc type
        label = DOC_TYPE_LABELS.get(doc_type, doc_type)
        self._type_var.set(label)

        # Update contact panel label
        if doc_type in QBO_DOC_TYPES:
            self._contact_frame.config(text="QBO Vendor")
        else:
            self._contact_frame.config(text="Customer / Vendor (ProShop)")

        # Load PDF
        self._pdf_images = []
        self._pdf_page = 0
        if pdf_path and Path(pdf_path).exists() and HAS_FITZ:
            doc = fitz.open(pdf_path)
            for page in doc:
                mat = fitz.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat)
                self._pdf_images.append(pix.tobytes("png"))
            doc.close()
        self._show_pdf_page()

        # Load JSON
        display_json = edited_json or extracted_json or "{}"
        try:
            parsed = json.loads(display_json)
            pretty = json.dumps(parsed, indent=2)
        except Exception:
            pretty = display_json
        self._json_text.config(state="normal")
        self._json_text.delete("1.0", "end")
        self._json_text.insert("1.0", pretty)
        self._json_text.config(state="normal")

        # Contact
        if contact_name:
            self._contact_search_var.set(contact_name)
        else:
            # Pre-populate from extracted data
            try:
                data = json.loads(extracted_json or "{}")
                vendor = (data.get("vendor_name") or data.get("customer_name") or
                          data.get("company_name") or "")
                self._contact_search_var.set(vendor)
            except Exception:
                pass

        # View link (ProShop or QBO)
        self._proshop_url = proshop_url
        if proshop_url:
            prefix = "View in QBO:" if doc_type in QBO_DOC_TYPES else "View in ProShop:"
            self._link_label.config(text=f"{prefix} {proshop_url}")
        else:
            self._link_label.config(text="")

        # Button states
        if status == "QBO":
            self._approve_btn.config(state="disabled", text="Uploaded to QBO ✓")
            self._reject_btn.config(state="disabled")
        elif status == "UPLOADED":
            self._approve_btn.config(state="disabled", text="Uploaded to ProShop ✓")
            self._reject_btn.config(state="disabled")
        else:
            if doc_type in QBO_DOC_TYPES:
                self._approve_btn.config(state="normal", text="✓  APPROVE & PUSH TO QBO")
            else:
                self._approve_btn.config(state="normal", text="✓  APPROVE & PUSH TO PROSHOP")
            self._reject_btn.config(state="normal")

    # ── PDF Viewer ─────────────────────────────────────────────────────────

    def _show_pdf_page(self):
        self._canvas.delete("all")
        self._pdf_tk_image = None
        if not self._pdf_images:
            self._canvas.create_text(200, 200, text="No preview available",
                                     fill="#666666", font=("Segoe UI", 12))
            self._page_label.config(text="No document")
            return
        total = len(self._pdf_images)
        idx = max(0, min(self._pdf_page, total - 1))
        self._pdf_page = idx
        self._page_label.config(text=f"Page {idx+1} / {total}")

        img_data = self._pdf_images[idx]
        from tkinter import PhotoImage
        import io as _io
        try:
            from PIL import Image, ImageTk
            img = Image.open(_io.BytesIO(img_data))
            cw = self._canvas.winfo_width() or 500
            ch = self._canvas.winfo_height() or 700
            img.thumbnail((cw - 8, ch - 8), Image.LANCZOS)
            self._pdf_tk_image = ImageTk.PhotoImage(img)
            self._canvas.create_image(4, 4, anchor="nw", image=self._pdf_tk_image)
        except ImportError:
            self._canvas.create_text(200, 200,
                                     text="Install Pillow for PDF preview\npip install Pillow",
                                     fill="#888888", font=("Segoe UI", 11))

    def _prev_page(self):
        self._pdf_page = max(0, self._pdf_page - 1)
        self._show_pdf_page()

    def _next_page(self):
        self._pdf_page = min(len(self._pdf_images) - 1, self._pdf_page + 1)
        self._show_pdf_page()

    # ── Contact Search ─────────────────────────────────────────────────────

    def _on_contact_search(self, *_):
        search = self._contact_search_var.get()
        self._contact_listbox.delete(0, "end")
        if len(search) < 2:
            return
        is_qbo = (self._current_doc_type in QBO_DOC_TYPES)
        try:
            if is_qbo:
                matches = self.qbo.fuzzy_match_vendor(search)
                self._qbo_vendor_matches = matches
                self._contact_matches = []
                for score, v in matches:
                    label = f"{v.get('DisplayName', '')}  [ID {v.get('Id','')}]  {int(score*100)}%"
                    self._contact_listbox.insert("end", label)
                if matches:
                    self._contact_listbox.selection_set(0)
                    self._update_contact_label(0)
            else:
                matches = self.proshop.fuzzy_match_contact(search)
                self._contact_matches = matches
                self._qbo_vendor_matches = []
                for score, c in matches:
                    label = f"{c['companyName']}  [{c['name']}]  {int(score*100)}%"
                    self._contact_listbox.insert("end", label)
                if matches:
                    self._contact_listbox.selection_set(0)
                    self._update_contact_label(0)
        except Exception:
            pass
        self._contact_listbox.bind("<<ListboxSelect>>",
                                   lambda e: self._update_contact_label(
                                       self._contact_listbox.curselection()[0]
                                       if self._contact_listbox.curselection() else 0))

    def _update_contact_label(self, idx):
        is_qbo = (self._current_doc_type in QBO_DOC_TYPES)
        if is_qbo:
            if idx < len(self._qbo_vendor_matches):
                score, v = self._qbo_vendor_matches[idx]
                self._contact_label.config(
                    text=f"QBO vendor ID: {v.get('Id','')}  ({int(score*100)}% match)",
                    fg="#4caf50" if score > 0.8 else "#ffd700" if score > 0.6 else "#f44336"
                )
        else:
            if idx < len(self._contact_matches):
                score, c = self._contact_matches[idx]
                self._contact_label.config(
                    text=f"ProShop code: {c['name']}  ({int(score*100)}% match)",
                    fg="#4caf50" if score > 0.8 else "#ffd700" if score > 0.6 else "#f44336"
                )

    def _get_selected_contact_code(self):
        """For ProShop docs — returns ProShop contact code string."""
        sel = self._contact_listbox.curselection()
        if sel and sel[0] < len(self._contact_matches):
            return self._contact_matches[sel[0]][1]["name"]
        return None

    def _get_selected_qbo_vendor(self):
        """For QBO docs — returns (vendor_id, display_name) or (None, None)."""
        sel = self._contact_listbox.curselection()
        if sel and sel[0] < len(self._qbo_vendor_matches):
            _, v = self._qbo_vendor_matches[sel[0]]
            return v.get("Id"), v.get("DisplayName", "")
        return None, None

    # ── Actions ────────────────────────────────────────────────────────────

    def _approve(self):
        if not self._current_id:
            return
        # Get doc type
        label = self._type_var.get()
        doc_type = next((k for k, v in DOC_TYPE_LABELS.items() if v == label), "UNKNOWN")
        # Get edited JSON
        edited_raw = self._json_text.get("1.0", "end").strip()
        try:
            json.loads(edited_raw)  # validate
        except json.JSONDecodeError as e:
            messagebox.showerror("Invalid JSON", f"Fix the JSON before approving:\n{e}")
            return

        if doc_type in QBO_DOC_TYPES:
            # ── QBO path ──────────────────────────────────────────────────────
            vendor_id, vendor_display = self._get_selected_qbo_vendor()
            if not vendor_id:
                messagebox.showwarning(
                    "Vendor Required",
                    "Select a QBO vendor above before pushing to QuickBooks."
                )
                return
            cur_id = self._current_id

            def do_qbo_upload():
                try:
                    data = json.loads(edited_raw)
                    # Check for duplicate in QBO
                    inv_num = data.get("invoice_number")
                    if inv_num:
                        dup_url = self.qbo.check_duplicate_bill(inv_num)
                        if dup_url:
                            proceed = messagebox.askyesno(
                                "Possible Duplicate in QBO",
                                f"A Bill with invoice # '{inv_num}' may already exist:\n{dup_url}\n\nPush anyway?"
                            )
                            if not proceed:
                                return
                    bill_id, qbo_url = self.qbo.create_bill(data, vendor_id, vendor_display)
                    self._log(f"Created QBO Bill #{bill_id} for {vendor_display}")

                    # Attach the source PDF to the bill
                    con = db()
                    row = con.execute("SELECT pdf_path FROM queue WHERE id=?", (cur_id,)).fetchone()
                    con.close()
                    if row and row[0] and Path(row[0]).exists():
                        try:
                            self.qbo.attach_pdf("Bill", bill_id, row[0])
                            self._log(f"Attached PDF to Bill #{bill_id}")
                        except Exception as att_err:
                            self._log(f"PDF attach failed (bill still created): {att_err}")

                    con = db()
                    con.execute("""
                        UPDATE queue SET status='QBO', edited_json=?, contact_name=?,
                        proshop_id=?, proshop_url=?, reviewed_at=? WHERE id=?
                    """, (edited_raw, vendor_display, bill_id, qbo_url,
                          datetime.now(timezone.utc).isoformat(), cur_id))
                    con.commit()
                    con.close()
                    self.after(0, self._refresh_queue)
                    self.after(0, lambda: self._load_record(cur_id))
                    self.after(0, self._advance_queue)
                except Exception as e:
                    con = db()
                    con.execute("UPDATE queue SET status='UPLOAD_FAILED', upload_error=? WHERE id=?",
                                (str(e), cur_id))
                    con.commit()
                    con.close()
                    self._log(f"QBO upload failed: {e}")
                    self.after(0, lambda: messagebox.showerror("QBO Upload Failed", str(e)))
                    self.after(0, self._refresh_queue)

            threading.Thread(target=do_qbo_upload, daemon=True).start()

        else:
            # ── ProShop path ──────────────────────────────────────────────────
            contact_code = self._get_selected_contact_code()
            if doc_type == "CUSTOMER_PO" and not contact_code:
                messagebox.showwarning("Contact Required",
                                       "Customer PO requires a matched contact.\n"
                                       "Search and select the customer above.")
                return
            cur_id = self._current_id

            def do_upload():
                try:
                    ref_number = None
                    try:
                        data_check = json.loads(edited_raw)
                        ref_number = (data_check.get("invoice_number") or data_check.get("po_number") or
                                      data_check.get("packing_slip_number") or data_check.get("quote_number"))
                    except Exception:
                        pass

                    if ref_number:
                        existing_url = self._check_proshop_duplicate(doc_type, ref_number)
                        if existing_url:
                            proceed = messagebox.askyesno(
                                "Possible Duplicate in ProShop",
                                f"A record with reference '{ref_number}' may already exist in ProShop.\n\n"
                                f"{existing_url}\n\nPush anyway?"
                            )
                            if not proceed:
                                return

                    proshop_id, proshop_url = self.uploader.upload(
                        cur_id, doc_type, edited_raw, contact_code
                    )
                    con = db()
                    con.execute("""
                        UPDATE queue SET status='UPLOADED', edited_json=?, contact_name=?,
                        proshop_id=?, proshop_url=?, reviewed_at=? WHERE id=?
                    """, (edited_raw, contact_code, proshop_id, proshop_url,
                          datetime.now(timezone.utc).isoformat(), cur_id))
                    con.commit()
                    con.close()
                    self._log(f"Uploaded: {doc_type} → ProShop ID {proshop_id}")
                    self.after(0, self._refresh_queue)
                    self.after(0, lambda: self._load_record(cur_id))
                    self.after(0, self._advance_queue)
                except Exception as e:
                    con = db()
                    con.execute("UPDATE queue SET status='UPLOAD_FAILED', upload_error=? WHERE id=?",
                                (str(e), cur_id))
                    con.commit()
                    con.close()
                    self._log(f"Upload failed: {e}")
                    self.after(0, lambda: messagebox.showerror("Upload Failed", str(e)))
                    self.after(0, self._refresh_queue)

            threading.Thread(target=do_upload, daemon=True).start()

    def _reject(self):
        if not self._current_id:
            return
        con = db()
        row = con.execute("SELECT from_addr, source FROM queue WHERE id=?",
                          (self._current_id,)).fetchone()
        con.execute("UPDATE queue SET status='REJECTED', reviewed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), self._current_id))
        con.commit()
        con.close()
        self._log(f"Rejected queue item {self._current_id}")
        self._refresh_queue()
        self._advance_queue()

        # Offer to block sender if this came from email
        if row:
            from_addr, source = row
            if source == "email" and from_addr and not from_addr.lower().endswith("@traxismfg.com"):
                if messagebox.askyesno(
                    "Block Sender?",
                    f"Always skip future emails from:\n{from_addr}?"
                ):
                    add_sender_to_blocklist(from_addr, reason="rejected by user")
                    self._log(f"Blocked sender: {from_addr}")

    def _advance_queue(self):
        """Select the next PENDING item in the queue."""
        for item in self._tree.get_children():
            tags = self._tree.item(item, "tags")
            if "PENDING" in tags:
                self._tree.selection_set(item)
                self._tree.see(item)
                self._on_queue_select()
                return

    def _re_extract(self):
        """Run AI extraction (or re-extraction) on the currently selected record."""
        if not self._current_id:
            return
        qid = self._current_id
        con = db()
        row = con.execute("SELECT pdf_path, doc_type FROM queue WHERE id=?", (qid,)).fetchone()
        con.close()
        if not row or not row[0]:
            return
        pdf_path, current_type = row

        # Use the type selected in the dropdown (user may have changed it)
        label = self._type_var.get()
        doc_type = next((k for k, v in DOC_TYPE_LABELS.items() if v == label), current_type)

        self._log(f"Extracting: {Path(pdf_path).name} as {doc_type}...")
        self._extract_btn.config(state="disabled", text="Extracting...")

        def do_extract():
            try:
                extracted = self.extractor.extract(pdf_path, doc_type)
                pretty = json.dumps(extracted, indent=2)
                con = db()
                con.execute("UPDATE queue SET doc_type=?, extracted_json=?, confidence=? WHERE id=?",
                            (doc_type, json.dumps(extracted), extracted.get("confidence", 0), qid))
                con.commit()
                con.close()
                self._log(f"Extraction complete: {doc_type} conf={extracted.get('confidence', 0):.0%}")
                self.after(0, lambda: self._load_record(qid))
                self.after(0, self._refresh_queue)
            except Exception as e:
                self._log(f"Extraction failed: {e}")
            finally:
                self.after(0, lambda: self._extract_btn.config(state="normal", text="⟳  Re-extract"))

        threading.Thread(target=do_extract, daemon=True).start()

    def _check_proshop_duplicate(self, doc_type, ref_number):
        """Query ProShop for an existing record with the same referenceNumber. Returns URL or None."""
        query_map = {
            "VENDOR_INVOICE": ("bills",       "bills",       "billId"),
            "PACKING_SLIP":   ("packingSlips","packingSlips","packingSlipId"),
            "CUSTOMER_PO":    ("customerPOs", "customerPOs", "poId"),
            "VENDOR_PO":      ("purchaseOrders","purchaseOrders","purchaseOrderId"),
            "CUSTOMER_QUOTE": ("quotes",      "quotes",      "quoteId"),
        }
        if doc_type not in query_map:
            return None
        field, _, _ = query_map[doc_type]
        try:
            gql = f"""{{
              {field}(filter: {{referenceNumber: ["{ref_number}"]}}, pageSize: 1) {{
                records {{ proshopUrl }}
              }}
            }}"""
            data = self.proshop.query(gql)
            records = data.get(field, {}).get("records", [])
            if records:
                return records[0].get("proshopUrl", "existing record found")
        except Exception:
            pass
        return None

    def _open_proshop_link(self, _event=None):
        if self._proshop_url:
            import webbrowser
            webbrowser.open(self._proshop_url)

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open Document",
            filetypes=[("Documents", "*.pdf *.png *.jpg *.jpeg *.tiff *.tif"), ("All files", "*.*")]
        )
        if not path:
            return
        doc_type = self.extractor.classify(path)
        self._log(f"Classifying {Path(path).name} → {doc_type}")

        def do_extract():
            extracted = self.extractor.extract(path, doc_type)
            con = db()
            con.execute("""
                INSERT INTO queue (source, source_ref, doc_type, pdf_path, extracted_json, confidence, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, ("manual", Path(path).name, doc_type, path,
                  json.dumps(extracted), extracted.get("confidence", 0),
                  datetime.now(timezone.utc).isoformat()))
            con.commit()
            con.close()
            self._log(f"Added: {Path(path).name} → {doc_type}")
            self.after(0, self._refresh_queue)

        threading.Thread(target=do_extract, daemon=True).start()

    def _open_qbo_folder(self):
        import webbrowser
        webbrowser.open("https://app.sandbox.qbo.intuit.com/app/bills")

    def _poll_now(self):
        self._log("Manual email poll triggered...")
        threading.Thread(target=self._email_poller.run, daemon=True).start()

    # ── Background Workers ─────────────────────────────────────────────────

    def _start_workers(self):
        self._email_poller = EmailPoller(
            self.graph, self.extractor,
            on_new_doc=lambda: self.after(0, self._refresh_queue),
            log=self._log
        )
        self._folder_watcher = FolderWatcher(
            self.extractor,
            on_new_doc=lambda: self.after(0, self._refresh_queue),
            log=self._log
        )
        threading.Thread(target=self._email_poller.run, daemon=True, name="email_poller").start()
        threading.Thread(target=self._folder_watcher.run, daemon=True, name="folder_watcher").start()

    # ── Logging ────────────────────────────────────────────────────────────

    def _log(self, msg):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_text.config(state="normal")
            self._log_text.insert("end", f"[{ts}] {msg}\n")
            self._log_text.see("end")
            self._log_text.config(state="disabled")
        self.after(0, _do)

    def on_close(self):
        self._email_poller.stop()
        self._folder_watcher.stop()
        self.destroy()


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = AccountingIngestApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
