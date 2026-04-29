"""
Traxis Label Printer — Extension Host Server
Serves .crx and update_manifest.xml for Chrome enterprise deployment.

Usage:  pythonw host.py [--port PORT]
Default port: 8484
"""

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = 8484
SERVE_DIR = Path(__file__).resolve().parent


class CRXHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".crx": "application/x-chrome-extension",
        ".xml": "application/xml",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SERVE_DIR), **kwargs)

    def log_message(self, format, *args):
        pass


def main():
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    server = HTTPServer(("0.0.0.0", port), CRXHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
