"""
Traxis Label Printer — Extension Build Script
Packs the Chrome extension as .crx and generates deployment files.

Usage:  python build.py [--host URL]
Default host: http://10.1.1.71:8484
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOST_URL = "http://10.1.1.71:8484"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
EXT_DIR = PROJECT_DIR / "traxis-material-label"
MANIFEST = EXT_DIR / "manifest.json"
PEM_PATH = SCRIPT_DIR / "signing_key.pem"
CRX_PATH = SCRIPT_DIR / "traxis-label-printer.crx"
XML_PATH = SCRIPT_DIR / "update_manifest.xml"
ID_PATH = SCRIPT_DIR / "extension_id.txt"


def find_chrome():
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env, "")
        if base:
            p = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if p.exists():
                return str(p)
    return None


# ── Extension ID from CRX3 header ──────────────────────────────

def _read_varint(data, pos):
    result = shift = 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def extension_id_from_crx(crx_path):
    """Extract extension ID from a packed CRX3 file's embedded public key."""
    with open(crx_path, "rb") as f:
        f.read(4)  # Cr24 magic
        f.read(4)  # version
        header_len = int.from_bytes(f.read(4), "little")
        header = f.read(header_len)

    # Parse protobuf: field 2 (sha256_with_rsa) → field 1 (public_key)
    tag, pos = _read_varint(header, 0)
    length, pos = _read_varint(header, pos)
    proof = header[pos:pos + length]

    inner_tag, inner_pos = _read_varint(proof, 0)
    pub_key_len, inner_pos = _read_varint(proof, inner_pos)
    pub_key = proof[inner_pos:inner_pos + pub_key_len]

    digest = hashlib.sha256(pub_key).digest()
    return "".join(
        chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0xf))
        for b in digest[:16]
    )


# ── Main ───────────────────────────────────────────────────────

def main():
    host = sys.argv[sys.argv.index("--host") + 1] if "--host" in sys.argv else HOST_URL

    chrome = find_chrome()
    if not chrome:
        print("ERROR: Chrome not found.")
        sys.exit(1)

    version = json.loads(MANIFEST.read_text())["version"]
    print(f"Packing Traxis Label Printer v{version}")

    cmd = [chrome, f"--pack-extension={EXT_DIR}"]
    if PEM_PATH.exists():
        cmd.append(f"--pack-extension-key={PEM_PATH}")

    subprocess.run(cmd)

    gen_crx = PROJECT_DIR / "traxis-material-label.crx"
    gen_pem = PROJECT_DIR / "traxis-material-label.pem"

    for _ in range(20):
        if gen_crx.exists():
            break
        time.sleep(0.5)
    else:
        print("ERROR: Chrome did not produce .crx file.")
        print("If Chrome showed an error dialog, dismiss it and retry.")
        sys.exit(1)

    shutil.move(str(gen_crx), str(CRX_PATH))
    print(f"  {CRX_PATH.name}")

    if gen_pem.exists():
        if PEM_PATH.exists():
            gen_pem.unlink()
        else:
            shutil.move(str(gen_pem), str(PEM_PATH))
            print(f"  {PEM_PATH.name}  (signing key — keep this file)")

    ext_id = extension_id_from_crx(CRX_PATH)
    ID_PATH.write_text(ext_id)
    print(f"  Extension ID: {ext_id}")

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
  <app appid="{ext_id}">
    <updatecheck codebase="{host}/{CRX_PATH.name}" version="{version}" />
  </app>
</gupdate>
'''
    XML_PATH.write_text(xml, encoding="utf-8")
    print(f"  {XML_PATH.name}")

    print(f"\nDone. Next steps:")
    print(f"  1. Copy deployment/ to the host machine ({host.split('//')[1].split(':')[0]})")
    print(f"  2. Run install_host.bat as Administrator on the host")
    print(f"  3. Run deploy_client.bat as Administrator on each shop PC")


if __name__ == "__main__":
    main()
