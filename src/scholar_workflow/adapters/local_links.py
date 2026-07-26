"""Local link resolution service (loopback only).

Serves the raw PDF for a Zotero attachment over 127.0.0.1 so projection links
(Obsidian / Notion) open in a local browser. Resolves by *attachment key* — the
Zotero storage folder is named by the attachment key, not the item key
(GOALS INV17). Read-only filesystem access; never reaches MCP or zotero.sqlite.
"""
from __future__ import annotations
from pathlib import Path
import glob
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# Zotero keys are uppercase alphanumeric. Reject anything else before touching
# the filesystem — blocks path traversal (no '/', '.', '..' can pass).
_KEY_RE = re.compile(r"^[A-Z0-9]+$")


class LocalLinkHandler(BaseHTTPRequestHandler):
    """GET /open/paper/{attachment-key} -> inline stream of the attachment PDF."""

    storage_root: Path = Path.home() / "Zotero" / "storage"

    def do_GET(self) -> None:
        seg = urlparse(self.path).path.strip("/").split("/")
        if len(seg) != 3 or seg[0] != "open":
            self._respond(400, "Bad request")
            return
        _, _kind, key = seg
        if not _KEY_RE.match(key):
            self._respond(400, "Invalid key")
            return
        hits = glob.glob(str(self.storage_root / key / "*.pdf"))
        if not hits:
            self._respond(404, f"No PDF for attachment: {key}")
            return
        self._serve_pdf(Path(hits[0]))

    def _serve_pdf(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _respond(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_) -> None:
        pass  # suppress default access log


def start_link_server(port: int = 23128,
                      storage_root: Path | None = None) -> HTTPServer:
    """Start loopback link server in a daemon thread; return the server.

    Bind port 0 to get an OS-assigned free port (tests read server.server_address).
    """
    if storage_root is not None:
        LocalLinkHandler.storage_root = Path(storage_root)
    server = HTTPServer(("127.0.0.1", port), LocalLinkHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
