"""Test: Create a Purchase Order in ProShop from a simulated vendor quote."""
import sys, json
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import ProShopClient, ProShopUploader

ps = ProShopClient()

# Use a real logging function
def log(msg):
    print(f"  LOG: {msg}")

uploader = ProShopUploader(ps, log)

# First, find a real contact to use
print("Finding contacts...")
contacts = ps.get_contacts()
# Pick a vendor-like contact
for c in contacts:
    if "supply" in (c.get("companyName") or "").lower() or "tool" in (c.get("companyName") or "").lower():
        print(f"  Using: {c['name']} - {c['companyName']}")
        contact_code = c["name"]
        break
else:
    # Just use the first one
    contact_code = contacts[0]["name"]
    print(f"  Using: {contact_code} - {contacts[0]['companyName']}")

# Simulated vendor quote extraction (what Claude AI would produce)
test_vendor_quote = {
    "vendor_name": "Test Tooling Supply",
    "quote_number": "QT-2026-0411",
    "quote_date": "2026-04-10",
    "valid_until": "2026-05-10",
    "total_amount": "385.00",
    "lead_time": "2-3 weeks",
    "payment_terms": "Net 30",
    "notes": "Test PO from Accounting Ingest - safe to delete",
    "line_items": [
        {"part_number": "EM-0500-4FL", "description": "1/2\" 4-Flute Carbide End Mill", "quantity": "5", "unit_price": "45.00", "extended_price": "225.00"},
        {"part_number": "DR-0250", "description": "1/4\" Carbide Drill", "quantity": "10", "unit_price": "16.00", "extended_price": "160.00"},
    ],
    "confidence": 0.95,
}

print(f"\nCreating Purchase Order in ProShop...")
print(f"  Contact: {contact_code}")
print(f"  Quote #: {test_vendor_quote['quote_number']}")
print(f"  Date: {test_vendor_quote['quote_date']}")
print(f"  Lead time: {test_vendor_quote['lead_time']}")
print(f"  Lines: {len(test_vendor_quote['line_items'])}")
print(f"  Total: ${test_vendor_quote['total_amount']}")

try:
    result = uploader._upload_purchase_order(test_vendor_quote, contact_code)
    rec = result.get("addPurchaseOrder", {})
    po_id = rec.get("purchaseOrderId")
    po_url = rec.get("proshopUrl")
    print(f"\nPurchase Order created!")
    print(f"  PO ID: {po_id}")
    print(f"  URL: {po_url}")
except Exception as e:
    print(f"\nFailed: {e}")
    print("\nTrying without line items...")
    # Retry without poItems in case the format is wrong
    test_vendor_quote.pop("line_items")
    try:
        result = uploader._upload_purchase_order(test_vendor_quote, contact_code)
        rec = result.get("addPurchaseOrder", {})
        print(f"  PO ID: {rec.get('purchaseOrderId')}")
        print(f"  URL: {rec.get('proshopUrl')}")
        print("  (created without line items - item format needs fixing)")
    except Exception as e2:
        print(f"  Also failed: {e2}")

print("\nDone.")
