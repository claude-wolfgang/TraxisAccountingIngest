"""Relay: moves new PDFs from the scanner's default output (Pictures) to the
Accounting Inbox Scanned folder where P27 picks them up automatically.

Run at startup or leave running in background.
"""
import time
import shutil
from pathlib import Path

SRC = Path(r"C:\Users\Superuser\Pictures")
DST = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Accounting Inbox\Scanned")
POLL = 5  # seconds

def relay():
    DST.mkdir(parents=True, exist_ok=True)
    seen = {f.name for f in DST.iterdir() if f.is_file()}
    print(f"Scan relay active: {SRC} -> {DST}")
    print(f"  {len(seen)} files already in destination")
    while True:
        for f in SRC.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() != ".pdf":
                continue
            if f.name in seen:
                continue
            # Wait a moment for the scanner to finish writing
            size1 = f.stat().st_size
            time.sleep(1)
            if f.stat().st_size != size1:
                continue
            dest = DST / f.name
            shutil.move(str(f), str(dest))
            seen.add(f.name)
            print(f"  Moved: {f.name}")
        time.sleep(POLL)

if __name__ == "__main__":
    relay()
