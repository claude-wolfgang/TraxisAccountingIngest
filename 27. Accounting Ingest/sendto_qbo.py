"""
Send To → QBO Queue
Copies a file into the Accounting Inbox and inserts a PENDING queue record
pre-tagged as VENDOR_INVOICE for QBO routing (skips AI classification).

Usage: Right-click a PDF → Send To → "QBO Queue"
Install: Run INSTALL_SENDTO.bat
"""
import sys
import shutil
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

SCAN_FOLDER = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\Scanned")
DB_PATH     = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\ingest_queue.db")

DEFAULT_DOC_TYPE = "VENDOR_INVOICE"

def main():
    if len(sys.argv) < 2:
        print("Usage: sendto_qbo.py <file>")
        return

    for src_path in sys.argv[1:]:
        src = Path(src_path)
        if not src.exists():
            print(f"File not found: {src}")
            continue
        if src.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"):
            print(f"Skipping non-document: {src.name}")
            continue

        # Copy to scan folder
        SCAN_FOLDER.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = SCAN_FOLDER / f"{ts}_{src.name}"
        shutil.copy2(str(src), str(dst))

        # Insert queue record
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            INSERT INTO queue (source, source_ref, doc_type, pdf_path, extracted_json,
                               confidence, created_at, status)
            VALUES (?,?,?,?,?,?,?,?)
        """, ("sendto", src.name, DEFAULT_DOC_TYPE, str(dst),
              json.dumps({"_note": "Sent via right-click → QBO Queue. Review and extract before pushing."}),
              0.0, datetime.now(timezone.utc).isoformat(), "PENDING"))
        con.commit()
        con.close()
        print(f"Queued for QBO: {src.name}")

if __name__ == "__main__":
    main()
