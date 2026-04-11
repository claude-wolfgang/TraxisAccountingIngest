"""Test: Create a Packing Slip in ProShop."""
import sys
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import ProShopClient, ProShopUploader

ps = ProShopClient()
uploader = ProShopUploader(ps, lambda msg: print(f"  LOG: {msg}"))

contacts = ps.get_contacts()
contact_code = contacts[0]["name"]
print(f"Using contact: {contact_code} - {contacts[0]['companyName']}")

test_ps = {
    "vendor_name": "Test Supplier Inc",
    "packing_slip_number": "PS-TEST-001",
    "ship_date": "2026-04-10",
    "po_number": "PO-12345",
    "carrier": "UPS",
    "tracking_number": "1Z999AA10123456784",
    "notes": "Test packing slip - safe to delete",
    "line_items": [
        {"part_number": "10983", "description": "Widget Housing", "quantity_shipped": "50", "quantity_ordered": "100"},
        {"part_number": "10984", "description": "Widget Cap", "quantity_shipped": "100", "quantity_ordered": "100"},
    ],
    "confidence": 0.92,
}

print(f"\nCreating Packing Slip...")
print(f"  PS #: {test_ps['packing_slip_number']}")
print(f"  Carrier: {test_ps['carrier']}")
print(f"  Tracking: {test_ps['tracking_number']}")
print(f"  Lines: {len(test_ps['line_items'])}")

try:
    result = uploader._upload_packing_slip(test_ps, contact_code)
    rec = result.get("addPackingSlip", {})
    print(f"\nPacking Slip created!")
    print(f"  ID: {rec.get('id')}")
    print(f"  URL: {rec.get('proshopUrl')}")
except Exception as e:
    print(f"\nFailed: {e}")

print("\nDone.")
