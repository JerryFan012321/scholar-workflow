"""Local link resolution service (loopback only)."""
from __future__ import annotations
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


class LocalLinkHandler(BaseHTTPRequestHandler):
    """
    GET /open/paper/{zotero-item-key}
    GET /open/document/{resource-id}
    """
    resolver = None  # injected at startup

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "open":
            self._respond(400, "Bad request")
            return
        kind, ident = parts[1], parts[2] if len(parts) > 2 else ""
        # re-split properly
        seg = parsed.path.strip("/").split("/", 2)
        if len(seg) < 3:
            self._respond(400, "Missing identifier")
            return
        _, kind, ident = seg
        path = self.resolver(kind, ident) if self.resolver else None
        if path is None:
            self._respond(404, f"Resource not found: {ident}")
            return
        self._respond(200, f"Opening: {path}")

    def _respond(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_) -> None:
        pass  # suppress default access log


def start_link_server(port: int = 23128, resolver=None) -> threading.Thread:
    """Start loopback link server in a daemon thread."""
    LocalLinkHandler.resolver = resolver
    server = HTTPServer(("127.0.0.1", port), LocalLinkHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
