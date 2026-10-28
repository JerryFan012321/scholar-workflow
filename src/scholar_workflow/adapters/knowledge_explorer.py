"""Loopback-only presentation adapter for file-backed knowledge exploration."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from scholar_workflow.adapters.exploration_previews import (
    ExplorationPreviewService,
    PreviewUnavailable,
)
from scholar_workflow.adapters.exploration_readers import ExplorationReaderGate, ReaderUnavailable
from scholar_workflow.adapters.process_environment import minimal_child_environment
from scholar_workflow.knowledge.exploration import (
    ExplorationError,
    ExplorationStore,
    assets,
    preserve_paper_units,
    query,
    validate,
)
from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment

_NATIVE_DOCUMENTS = {
    ".md", ".canvas", ".pdf", ".txt", ".csv", ".rtf", ".docx", ".xlsx", ".pptx",
    ".odt", ".ods", ".odp", ".epub", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".avif", ".bmp", ".tif", ".tiff", ".mp3", ".m4a", ".wav", ".ogg", ".flac",
    ".mp4", ".webm", ".mov", ".mkv",
}
_TEXT_PREVIEWS = {
    ".md", ".txt", ".yaml", ".yml", ".csv", ".json", ".py", ".toml", ".ini",
    ".cfg", ".sh", ".bash", ".zsh", ".command", ".desktop", ".ps1", ".bat",
    ".js", ".ts", ".c", ".h", ".cpp", ".rs", ".css", ".html", ".svg",
}


class _IsolatedReaderGate:
    """Test sessions never consult ambient readers, credentials or applications."""

    def __init__(self, references, registry_path):
        self.references, self.registry_path = references, registry_path

    @staticmethod
    def handles(uri):
        return urlsplit(uri).scheme in {"obsidian", "zotero"}

    @staticmethod
    def availability(work, asset):
        return {"native_available": False,
                "native_reason": "External readers are disabled in this isolated test session",
                "native_reason_code": "test_environment"}

    @staticmethod
    def require_current(work, asset):
        raise ReaderUnavailable("External readers are disabled in this isolated test session",
                                "test_environment")


def _native_reason(uri: str) -> str | None:
    """Permit reading actions, never arbitrary application protocol commands."""
    parsed = urlsplit(uri)
    if not parsed.scheme:
        return None if Path(unquote(parsed.path)).suffix.lower() in _NATIVE_DOCUMENTS else (
            "Native opening is limited to document and media files; use a safe text preview when available"
        )
    if parsed.scheme in {"http", "https"}:
        return None
    action = parsed.netloc.lower()
    parameters = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.scheme == "obsidian" and parsed.path in {"", "/"}:
        if action == "open" and set(parameters) <= {"path", "file", "vault", "heading", "block", "line"}:
            return None
        if (action == "zotflow" and set(parameters) <= {"vault", "type", "libraryID", "key", "page", "navigation"}
                and parameters.get("type") in (["open-attachment"], ["open-annotation"])):
            return None
    if parsed.scheme == "zotero" and action in {"open-pdf", "select"}:
        return None
    return "This native protocol action is not permitted; only registered reading actions can open"


class ExplorerHTTPServer(ThreadingHTTPServer):
    """A session owns a root and token, without depending on a workspace."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, root: Path, address: tuple[str, int], token: str, reference_service=None,
                 reader_gate=None, reading_store=None, environment=None, vault_service=None):
        from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
        from scholar_workflow.workflows.vault_connections import VaultConnectionService

        self.environment = environment or ExplorerEnvironment()
        self.root = self.environment.check_root(root)
        self.environment.check_registry()
        self.read_only = reading_store is not None
        self.store = reading_store if self.read_only else ExplorationStore(root)
        self.token = token
        self.references = (reference_service if reference_service is not None else
                           ExplorationReferenceService(self.environment.registry_path,
                               resolve_reader=not self.environment.is_test,
                               enrich_resources=not self.environment.is_test,
                               root_validator=self.environment.check_root
                                   if self.environment.is_test else None))
        self.reader_gate = (reader_gate if reader_gate is not None else
            _IsolatedReaderGate(self.references, self.environment.registry_path)
            if self.environment.is_test else ExplorationReaderGate(
                registry_path=self.environment.registry_path, reference_service=self.references))
        self.vaults = vault_service or VaultConnectionService(self.environment)
        self.previews = ExplorationPreviewService(self.root, self.store, self.reader_gate,
            root_validator=self.environment.check_root if self.environment.is_test else None)
        # Session-scoped authorization receipts, not another knowledge catalog.
        self.unit_proposals = {}
        self.write_lock = threading.Lock()
        super().__init__(address, ExplorerHandler)

    @staticmethod
    def _paper_signature(work):
        identity = {key: work[key] for key in ("id", "kind", "entity_ref")}
        identity["assets"] = sorted(work["assets"], key=lambda row: row["id"])
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def checked_draft(self, data):
        proposed = validate(data)
        before = self.store.load()["data"]
        if self.read_only:
            if proposed != before:
                raise ExplorationError("Read-only paper browsing cannot edit research records")
            return before
        preserve_paper_units(before, proposed)
        existing = {row["id"]: row for row in before["works"] if row["kind"] == "paper"}
        for work in proposed["works"]:
            if work["kind"] != "paper":
                continue
            if work["id"] in existing and work["assets"] == existing[work["id"]]["assets"]:
                continue
            ref = work["entity_ref"]
            key = ref["source_id"], ref["object_id"]
            if self.unit_proposals.get(key) != self._paper_signature(work):
                raise ExplorationError("New paper units require a complete server-confirmed unit reference")
        return proposed

    def remember_units(self, data, selected):
        proposed = validate(data)
        wanted = set()
        for ref in selected:
            if not isinstance(ref, dict) or set(ref) != {"source_id", "object_id"}:
                raise ExplorationError("Qualified whole-unit references required")
            wanted.add((ref["source_id"], ref["object_id"]))
        found = set()
        for work in proposed["works"]:
            if work["kind"] == "paper":
                ref = work["entity_ref"]
                key = ref["source_id"], ref["object_id"]
                if key in wanted:
                    self.unit_proposals[key] = self._paper_signature(work)
                    found.add(key)
        if found != wanted:
            raise ExplorationError("Selected paper units were not returned as complete objects")
        return self.checked_draft(proposed)


def _open_local(root: Path, uri: str) -> tuple[int, str]:
    """Traverse registered relative components with no symlink following."""
    parts = urlsplit(uri)
    if parts.scheme or parts.netloc or parts.query:
        raise ValueError("Not a relative asset")
    relative = unquote(parts.path)
    components = Path(relative).parts
    if not components or Path(relative).is_absolute() or any(p in {"..", "."} for p in components):
        raise ValueError("Unsafe asset path")
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in components[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        descriptor = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("Asset is not a regular file")
        return descriptor, components[-1]
    finally:
        os.close(parent)


class ExplorerHandler(BaseHTTPRequestHandler):
    server: ExplorerHTTPServer
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        # URLs and user content do not belong in an implicit request log.
        return

    def _headers(self, status: int, kind: str, size: int):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob:; connect-src 'self'; object-src blob:; "
            "frame-src blob:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )

    def _bytes(self, status, body, kind="application/json; charset=utf-8"):
        self._headers(status, kind, len(body))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, value):
        self._bytes(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _fail(self, status, message):
        self._json(status, {"error": message})

    def _guard(self, api=False, write=False):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed or len(self.headers.get_all("Host", [])) != 1:
            self._fail(403, "Host is not this loopback service")
            return False
        origin = self.headers.get("Origin")
        if (origin is not None and origin != f"http://{host}") or (write and origin is None) or len(self.headers.get_all("Origin", [])) > 1:
            self._fail(403, "Same-origin request required")
            return False
        if self.headers.get("Sec-Fetch-Site") in {"cross-site", "same-site"}:
            self._fail(403, "Cross-site request rejected")
            return False
        authorization = self.headers.get("Authorization", "")
        if api and not hmac.compare_digest(authorization.encode(), f"Bearer {self.server.token}".encode()):
            self._fail(401, "Session token required")
            return False
        if api:
            try:
                self.server.environment.check_root(self.server.root)
                self.server.environment.check_registry()
            except (ExplorationError, ValueError, OSError):
                self._fail(403, "The environment boundary changed; restart with a valid isolated scope")
                return False
        return True

    def _route(self):
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            raise ValueError("Unexpected URL parameters")
        return [unquote(p) for p in parsed.path.strip("/").split("/") if p]

    def _work_asset(self, work_id, asset_id):
        data = self.server.store.load()["data"]
        for work in data["works"]:
            if work["id"] == work_id:
                for asset in work.get("assets", []):
                    if asset["id"] == asset_id:
                        return work, asset
        return None, None

    def _asset(self, work_id, asset_id):
        return self._work_asset(work_id, asset_id)[1]

    def _submit_native(self, uri):
        """Only server-resolved reading targets reach the platform opener."""
        if self.server.environment.is_test:
            return self._fail(403, "External applications are disabled in the test environment")
        reason = _native_reason(uri)
        if reason:
            return self._fail(403, reason)
        executable = shutil.which("open" if sys.platform == "darwin" else "xdg-open")
        if executable is None:
            return self._fail(503, "Native opener is unavailable on this host")
        subprocess.Popen([executable, uri], shell=False, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=minimal_child_environment())
        self._json(200, {"submitted": True})

    def do_GET(self):
        try:
            route = self._route()
            if not self._guard(api=bool(route and route[0] == "api")):
                return
            if route == ["api", "state"]:
                self._json(200, self.server.store.load())
            elif route == ["api", "environment"]:
                self._json(200, self.server.environment.public_info(self.server.root))
            elif route == ["api", "vaults"]:
                self._json(200, self.server.vaults.list_connections())
            elif len(route) == 4 and route[:2] == ["api", "vaults"] and route[3] == "documents":
                self._json(200, self.server.vaults.documents(route[2]))
            elif route == ["api", "unit-fields"]:
                self._json(200, self.server.references.fields())
            elif len(route) == 4 and route[:2] == ["api", "preview"]:
                self._json(200, self.server.previews.preview(route[2], route[3]))
            elif len(route) == 3 and route[:2] == ["api", "preview-media"]:
                body, kind = self.server.previews.media(route[2])
                self._bytes(200, body, kind)
            elif len(route) == 3 and route[:2] == ["api", "reading-link"]:
                self._json(200, self.server.previews.prepare(route[2]))
            elif len(route) == 3 and route[:2] == ["api", "assets"]:
                data = self.server.store.load()["data"]
                listing = assets(self.server.root, data, route[2])
                work = next(row for row in data["works"] if row["id"] == route[2])
                for asset in listing:
                    reason = _native_reason(asset["uri"])
                    asset["native_available"] = reason is None and asset["available"]
                    if reason:
                        asset["native_reason"] = reason
                    elif self.server.reader_gate.handles(asset["uri"]):
                        asset.update(self.server.reader_gate.availability(work, asset))
                    if self.server.environment.is_test:
                        asset.update(_IsolatedReaderGate.availability(work, asset))
                self._json(200, listing)
            elif len(route) == 4 and route[:2] == ["api", "asset"]:
                asset = self._asset(route[2], route[3])
                if asset is None:
                    return self._fail(404, "Asset not found")
                try:
                    descriptor, name = _open_local(self.server.root, asset["uri"])
                except (OSError, ValueError):
                    return self._fail(403, "Asset is missing or outside the registered root")
                with os.fdopen(descriptor, "rb") as stream:
                    suffix = Path(name).suffix.lower()
                    if suffix == ".canvas":
                        return self._fail(415, "Canvas is editable in Obsidian; use native open")
                    media = mimetypes.guess_type(name)[0]
                    safe_images = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}
                    if suffix == ".pdf":
                        kind = "application/pdf"
                    elif media in safe_images:
                        kind = media
                    elif suffix in _TEXT_PREVIEWS:
                        kind = "text/plain; charset=utf-8"
                    else:
                        return self._fail(415, "This asset requires its native application")
                    self._headers(200, kind, os.fstat(stream.fileno()).st_size)
                    self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(name)}")
                    self.end_headers()
                    shutil.copyfileobj(stream, self.wfile)
            elif route in ([], ["index.html"], ["explore.css"], ["explore.js"]):
                name = route[0] if route else "index.html"
                path = Path(__file__).parent / "explorer_static" / name
                kind = {"html": "text/html", "css": "text/css", "js": "text/javascript"}[name.rsplit(".", 1)[1]]
                self._bytes(200, path.read_bytes(), f"{kind}; charset=utf-8")
            else:
                self._fail(404, "Not found")
        except (PreviewUnavailable, ReaderUnavailable) as error:
            self._json(403, {"error": str(error), "code": getattr(error, "code", "preview_changed")})
        except ExplorationError as error:
            if error.code == 6:
                self._json(503, {"error": str(error), "code": 6, "status": "uncertain"})
            else:
                self._fail(409 if error.code == 5 else 403 if error.code == 7 else 400, str(error))
        except ValueError:
            self._fail(400, "Knowledge data or request is invalid; check the selected root")
        except OSError:
            self._fail(500, "Could not read knowledge files")

    def do_POST(self):
        if not self._guard(api=True, write=True):
            return
        try:
            if self.headers.get_content_type() != "application/json":
                return self._fail(415, "JSON required")
            if self.headers.get("Transfer-Encoding"):
                return self._fail(400, "Transfer encoding is not supported")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2 * 1024 * 1024:
                return self._fail(413, "Request size must be between 1 byte and 2 MiB")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                return self._fail(400, "JSON object required")
            route = self._route()
            if self.server.read_only and route in (["api", "save"], ["api", "unit-reference"]):
                return self._fail(403, "This session only reads registered paper packages")
            if route == ["api", "vaults", "choose"]:
                if payload:
                    return self._fail(400, "Folder selection accepts no browser paths")
                self._json(200, self.server.vaults.choose())
            elif route == ["api", "vaults", "preview"]:
                if set(payload) != {"candidate_id"} or not isinstance(payload["candidate_id"], str):
                    return self._fail(400, "One server-issued Vault candidate required")
                self._json(200, self.server.vaults.preview_adjustments(payload["candidate_id"]))
            elif route == ["api", "vaults", "connect"]:
                if (set(payload) != {"candidate_id", "expected_revision"}
                        or not isinstance(payload["candidate_id"], str)):
                    return self._fail(400, "Candidate and reviewed registry revision required")
                with self.server.write_lock:
                    self._json(200, self.server.vaults.connect(
                        payload["candidate_id"], payload["expected_revision"]))
            elif route == ["api", "vaults", "document-preview"]:
                if (set(payload) != {"connection_id", "relative_path"}
                        or not all(isinstance(value, str) for value in payload.values())):
                    return self._fail(400, "Connection and relative document identity required")
                self._json(200, self.server.vaults.preview_document(
                    payload["connection_id"], payload["relative_path"]))
            elif route in (["api", "unit-options"], ["api", "unit-reference"]):
                required = {"source_id", "field_id"}
                if route[-1] == "unit-reference":
                    required |= {"data", "unit_refs"}
                if (set(payload) != required or any(not isinstance(payload.get(key), str)
                        or not payload[key].strip() for key in ("source_id", "field_id"))):
                    return self._fail(400, "Explicit registered Source and Field required")
                if route[-1] == "unit-options":
                    self._json(200, self.server.references.units(payload["source_id"], payload["field_id"]))
                else:
                    draft = self.server.checked_draft(payload["data"])
                    proposed = self.server.references.reference(
                        self.server.root, draft, payload["source_id"],
                        payload["field_id"], payload["unit_refs"])
                    with self.server.write_lock:
                        proposed = self.server.remember_units(proposed, payload["unit_refs"])
                    self._json(200, {"data": proposed})
            elif route == ["api", "query"]:
                draft = payload.pop("_draft", None)
                data = (self.server.store.load()["data"] if draft is None else
                        self.server.checked_draft(draft))
                self._json(200, query(data, payload))
            elif route == ["api", "save"]:
                if set(payload) != {"data", "expected_revision"}:
                    return self._fail(400, "data and expected_revision required")
                with self.server.write_lock:
                    data = self.server.checked_draft(payload["data"])
                    self._json(200, self.server.store.save(data, expected_revision=payload["expected_revision"]))
            elif route == ["api", "open-link"]:
                if (set(payload) != {"link_id"} or not isinstance(payload.get("link_id"), str)
                        or not 0 < len(payload["link_id"]) <= 128):
                    return self._fail(400, "One bounded preview link identity required")
                self._submit_native(self.server.previews.require_current(payload["link_id"]))
            elif route == ["api", "open"]:
                if set(payload) != {"work_id", "asset_id"}:
                    return self._fail(400, "Asset identity required")
                work, asset = self._work_asset(payload["work_id"], payload["asset_id"])
                if asset is None:
                    return self._fail(404, "Asset not found")
                uri = asset["uri"]
                reason = _native_reason(uri)
                if reason:
                    return self._fail(403, reason)
                if self.server.reader_gate.handles(uri):
                    self.server.reader_gate.require_current(work, asset)
                scheme = urlsplit(uri).scheme
                if not scheme:
                    try:
                        descriptor, _ = _open_local(self.server.root, uri)
                        os.close(descriptor)
                    except (OSError, ValueError):
                        return self._fail(403, "Asset is missing or outside the registered root")
                    path = self.server.root / unquote(urlsplit(uri).path)
                    if path.suffix.lower() in {".md", ".canvas"}:
                        uri = "obsidian://open?path=" + quote(str(path), safe="")
                    else:
                        uri = str(path)
                elif scheme not in {"http", "https", "obsidian", "zotero"}:
                    return self._fail(403, "Unsupported asset protocol")
                self._submit_native(uri)
            else:
                self._fail(404, "Not found")
        except (PreviewUnavailable, ReaderUnavailable) as error:
            self._json(403, {"error": str(error), "code": getattr(error, "code", "reader_unverified")})
        except ExplorationError as error:
            if error.code == 6:
                self._json(503, {"error": str(error), "code": 6, "status": "uncertain"})
            else:
                self._fail(409 if error.code == 5 else 403 if error.code == 7 else 400, str(error))
        except (ValueError, TypeError, KeyError):
            self._fail(400, "Invalid request")
        except OSError:
            self._fail(500, "Could not access knowledge files or native application")


def make_server(root: Path | str, host: str = "127.0.0.1", port: int = 0, *, reference_service=None,
                reader_gate=None, reading_store=None, environment=None, vault_service=None):
    """Create, but do not start, a loopback HTTP server and its session token."""
    if host != "127.0.0.1":
        raise ValueError("Explorer only listens on 127.0.0.1")
    environment = environment or ExplorerEnvironment()
    root = environment.check_root(Path(root))
    if not root.is_dir():
        raise ValueError("Explorer root must be a directory")
    token = secrets.token_urlsafe(32)
    return ExplorerHTTPServer(root, (host, port), token, reference_service=reference_service,
                              reader_gate=reader_gate, reading_store=reading_store,
                              environment=environment, vault_service=vault_service), token
