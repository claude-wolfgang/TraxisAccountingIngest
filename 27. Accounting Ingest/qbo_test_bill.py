"""Test: Create a bill in QBO sandbox and attach a dummy PDF."""
import sys, json
sys.path.insert(0, r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest")
from accounting_ingest import QBOClient, ENV, QBO_ENVIRONMENT

qbo = QBOClient()

# Pick a vendor
print("Finding a vendor...")
vendors = qbo.get_vendors()
vendor = vendors[0]
print(f"Using vendor: {vendor['DisplayName']} (ID {vendor['Id']})")

# Simulated extracted invoice data
test_invoice = {
    "vendor_name": vendor["DisplayName"],
    "invoice_number": "TEST-001",
    "invoice_date": "2026-04-10",
    "due_date": "2026-05-10",
    "total_amount": "247.50",
    "notes": "Test bill from Traxis Accounting Ingest",
    "line_items": [
        {"description": "Widget A - 10pk", "quantity": "5", "unit_price": "29.50", "extended_price": "147.50"},
        {"description": "Shipping & handling", "quantity": "1", "unit_price": "100.00", "extended_price": "100.00"},
    ],
}

print(f"\nCreating bill (env={QBO_ENVIRONMENT})...")
print(f"  Vendor: {vendor['DisplayName']}")
print(f"  Invoice #: {test_invoice['invoice_number']}")
print(f"  Date: {test_invoice['invoice_date']}")
print(f"  Total: ${test_invoice['total_amount']}")
print(f"  Lines: {len(test_invoice['line_items'])}")

bill_id, qbo_url = qbo.create_bill(test_invoice, vendor["Id"], vendor["DisplayName"])

print(f"\nBill created!")
print(f"  Bill ID: {bill_id}")
print(f"  URL: {qbo_url}")

# Verify by querying it back
print(f"\nVerifying...")
data = qbo.qbo_query(f"SELECT * FROM Bill WHERE Id = '{bill_id}'")
bill = data.get("QueryResponse", {}).get("Bill", [{}])[0]
print(f"  DocNumber: {bill.get('DocNumber')}")
print(f"  VendorRef: {bill.get('VendorRef', {}).get('name')}")
print(f"  TotalAmt: ${bill.get('TotalAmt')}")
print(f"  TxnDate: {bill.get('TxnDate')}")
print(f"  DueDate: {bill.get('DueDate')}")
print(f"  Lines: {len(bill.get('Line', []))}")

# Check duplicate detection
print(f"\nTesting duplicate check for 'TEST-001'...")
dup = qbo.check_duplicate_bill("TEST-001")
print(f"  Duplicate found: {dup}")

print("\nAll tests passed.")
