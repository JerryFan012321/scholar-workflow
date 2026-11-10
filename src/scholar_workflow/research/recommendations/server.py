"""Authenticated loopback presentation for the recommendation candidate pool."""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from scholar_workflow import __version__
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.ingestion import IngestionService
from scholar_workflow.research.recommendations.ranking import RecommendationRanking
from scholar_workflow.research.recommendations.refresh import refresh_candidate_metrics
from scholar_workflow.research.recommendations.source_catalog import SourceCatalog
from scholar_workflow.research.recommendations.store import RecommendationStore

_STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
           "/index.html": ("index.html", "text/html; charset=utf-8"),
           "/app.js": ("app.js", "text/javascript; charset=utf-8"),
           "/workspace.js": ("workspace.js", "text/javascript; charset=utf-8"),
           "/requirements.js": ("requirements.js", "text/javascript; charset=utf-8"),
           "/style.css": ("style.css", "text/css; charset=utf-8")}
_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self'; font-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_MAX_BODY = 64 * 1024


class RecommendationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def create_server(state_dir: Path, profile: str, token: str, port: int = 0) -> ThreadingHTTPServer:
    """Bind loopback; expose browser credentials only through constrained bootstrap."""
    if profile not in {"personal", "test"}:
        raise ResearchError("Unknown recommendation profile.")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
        raise ResearchError("Recommendation session requires a strong URL-safe token.", 7)
    if type(port) is not int or not 0 <= port <= 65535:
        raise ResearchError("Invalid recommendation service port.")
    store = RecommendationStore(Path(state_dir))
    ingestion = IngestionService(store, profile)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ScholarRecommendations"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            # Request paths, credentials and candidate content are never logged.
            return

        def _respond(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _error(self, message, code=2, status=None):
            status = status or {2: 400, 3: 503, 5: 409, 6: 409, 7: 403, 8: 502}.get(code, 500)
            self._respond(status, {"error": message, "exit_code": code})

        def _boundary(self, *, authenticated=False, writing=False):
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get_all("Host", []) != [expected_host]:
                self._error("Request host is not the local recommendation service.", 7)
                return False
            origin = self.headers.get_all("Origin", [])
            expected_origin = f"http://{expected_host}"
            if (origin and origin != [expected_origin]) or (writing and origin != [expected_origin]):
                self._error("Request origin is not the local recommendation page.", 7)
                return False
            if len(self.path) > 8192:
                self._error("Request URL exceeds the supported length.")
                return False
            if authenticated:
                authorization = self.headers.get_all("Authorization", [])
                if (len(authorization) != 1
                        or not secrets.compare_digest(authorization[0].encode("utf-8"), f"Bearer {token}".encode("utf-8"))):
                    self._error("Open this recommendation page through its authenticated CLI URL.", 7, 401)
                    return False
            return True

        def _body(self, *, limit=_MAX_BODY):
            if self.headers.get("Transfer-Encoding"):
                raise ResearchError("Transfer encoding is unsupported.")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise ResearchError("A bounded JSON content length is required.")
            length = int(lengths[0])
            if length > limit:
                raise ResearchError("Request body exceeds the supported limit.")
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise ResearchError("Request content must be JSON.")

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate key")
                    result[key] = value
                return result

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"), object_pairs_hook=unique)
            except (ValueError, UnicodeError, RecursionError):
                raise ResearchError("Request must contain valid JSON with unique keys.") from None
            if not isinstance(payload, dict):
                raise ResearchError("Request JSON must be an object.")
            return payload

        def _query(self, raw_query):
            try:
                params = parse_qs(raw_query, keep_blank_values=False, strict_parsing=True,
                                  max_num_fields=12)
            except ValueError:
                raise ResearchError("Invalid recommendation filters.") from None
            allowed = {"query", "kind", "tag", "producer_id", "decision", "sort", "limit", "offset", "since"}
            if set(params) - allowed or any(len(value) != 1 for value in params.values()):
                raise ResearchError("Unknown or duplicate recommendation filter.")
            result = {key: value[0] for key, value in params.items()}
            for key, default, low, high in (("limit", 40, 1, 100), ("offset", 0, 0, 1000000)):
                value = result.get(key, str(default))
                if not re.fullmatch(r"[0-9]{1,7}", value) or not low <= int(value) <= high:
                    raise ResearchError("Invalid recommendation pagination.")
                result[key] = int(value)
            for key in ("query", "tag", "producer_id"):
                if len(result.get(key, "")) > 300:
                    raise ResearchError("Recommendation filter exceeds the supported length.")
            if "kind" in result and result["kind"] not in {"paper", "project", "blog"}:
                raise ResearchError("Unknown recommendation resource type.")
            if "decision" in result and result["decision"] not in {"unread", "saved", "selected", "ignored"}:
                raise ResearchError("Unknown recommendation decision.")
            if result.get("sort", "newest") not in {"newest", "oldest", "published", "agent"}:
                raise ResearchError("Unknown recommendation sorting rule.")
            if "since" in result:
                try:
                    date.fromisoformat(result["since"])
                except ValueError:
                    raise ResearchError("Publication filter must be an ISO date.") from None
            return result

        def do_GET(self):
            path = urlsplit(self.path)
            if not self._boundary(authenticated=path.path.startswith("/api/")):
                return
            try:
                if path.path in _STATIC and not path.query:
                    filename, content_type = _STATIC[path.path]
                    content = files(__package__).joinpath("static", filename).read_bytes()
                    self._respond(200, content, content_type)
                elif path.path == "/health" and not path.query:
                    identity = getattr(self.server, "runtime_identity", {})
                    allowed = {key: identity[key] for key in ("generation", "pid", "version", "build", "profile")
                               if key in identity}
                    self._respond(200, {"service": "scholar-recommendations", "protocol": 1,
                                        "profile": profile, "version": __version__,
                                        "pool_id": RecommendationRanking(store).pool_id, **allowed})
                elif path.path == "/api/candidates":
                    self._respond(200, store.list_candidates(**self._query(path.query)))
                elif path.path == "/api/ranking/context" and not path.query:
                    self._respond(200, RecommendationRanking(store).context())
                elif path.path == "/api/handoff" and not path.query:
                    self._respond(200, {**store.prepare_handoff(), "profile": profile})
                elif path.path == "/api/requirements":
                    source_id = None
                    if path.query:
                        try:
                            values = parse_qs(path.query, keep_blank_values=True,
                                              strict_parsing=True, max_num_fields=1)
                        except ValueError:
                            raise ResearchError("Requirement list query needs one source_id.") from None
                        if set(values) != {"source_id"} or len(values["source_id"]) != 1:
                            raise ResearchError("Requirement list query needs one source_id.")
                        source_id = values["source_id"][0]
                    self._respond(200, store.list_requirements(source_id=source_id))
                elif path.path.startswith("/api/requirements/"):
                    requirement_id = path.path.removeprefix("/api/requirements/")
                    revision = None
                    if path.query:
                        try:
                            values = parse_qs(path.query, keep_blank_values=True,
                                              strict_parsing=True, max_num_fields=1)
                        except ValueError:
                            raise ResearchError("Requirement query needs one positive revision.") from None
                        if (set(values) != {"revision"} or len(values["revision"]) != 1
                                or not re.fullmatch(r"[1-9][0-9]{0,17}", values["revision"][0])):
                            raise ResearchError("Requirement query needs one positive revision.")
                        revision = int(values["revision"][0])
                    self._respond(200, store.get_requirement(requirement_id, revision))
                elif path.path == "/api/sources" and not path.query:
                    self._respond(200, SourceCatalog(store).list_sources())
                elif path.path == "/api/ingestion/history" and not path.query:
                    self._respond(200, {"items": ingestion.history()})
                elif path.path == "/api/ingestion/targets" and not path.query:
                    try:
                        targets = ingestion.targets()
                        self._respond(200, {**targets, "available": True, "targets": [
                            {**target, "key": target["collection_key"]} for target in targets["targets"]]})
                    except ResearchError as exc:
                        self._respond(200, {"available": False, "reason": str(exc), "targets": [],
                                            "scope": "zotero_bibliography", "exit_code": exc.exit_code})
                else:
                    self._error("Recommendation route was not found.", 2, 404)
            except ResearchError as exc:
                self._error(str(exc), exc.exit_code)
            except (OSError, ValueError, TypeError, KeyError):
                self._error("Recommendation content is unavailable; inspect the service status.", 3)

        def do_POST(self):
            path = urlsplit(self.path)
            bootstrap = path.path == "/api/session"
            if not self._boundary(authenticated=not bootstrap, writing=True):
                return
            try:
                if path.query:
                    raise ResearchError("Mutation URLs cannot contain query parameters.")
                if bootstrap:
                    # A foreign browser origin cannot send this non-simple header
                    # without a CORS preflight, which this service always refuses.
                    if (self.headers.get_all("X-Scholar-Client", []) != ["recommendation-page"]
                            or self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin"):
                        raise ResearchError("Session initialization requires the local recommendation page.", 7)
                    if self._body() != {}:
                        raise ResearchError("Session initialization does not accept parameters.")
                    self._respond(200, {"token": token})
                    return
                payload = self._body(limit=96 * 1024 if path.path in {"/api/requirements", "/api/ranking/context"} else _MAX_BODY)
                if path.path == "/api/ranking/context":
                    if set(payload) != {"content", "expected_revision"}:
                        raise ResearchError("Shared context needs text and its current revision.")
                    self._respond(200, RecommendationRanking(store).save_context(
                        **payload, updated_by={"kind": "human", "name": "推荐页"}))
                    return
                if path.path == "/api/evaluations":
                    if set(payload) != {"candidate_id", "score", "comment", "expected_revision", "expected_candidate_revision"}:
                        raise ResearchError("Evaluation needs a candidate, score, comment and both displayed revisions.")
                    self._respond(200, store.save_evaluation(**payload))
                    return
                if path.path == "/api/requirements":
                    expected = {"requirement_id", "title", "content", "enabled", "expected_revision"}
                    if not expected <= set(payload) <= expected | {"source_id"}:
                        raise ResearchError("A requirement edit needs its identity, text, enabled state and current revision.")
                    self._respond(200, store.save_requirement(
                        **payload, updated_by={"kind": "human", "name": "推荐页"}))
                    return
                if path.path == "/api/ingestion/plan":
                    if set(payload) != {"candidate_id", "expected_revision", "collection_key"}:
                        raise ResearchError("Ingestion preview needs a candidate, revision and selected collection.")
                    plan = ingestion.plan(**payload)
                    collection = plan["collection"]
                    self._respond(200, {"plan_id": plan["plan_id"], "title": plan["resource"]["title"],
                        "scope": plan["scope"], "expires_at": plan["expires_at"], "status": plan["status"],
                        "collection": {"key": collection["collection_key"], "name": collection["name"]},
                        "existing": bool(plan.get("existing_item_key")), "item_type": plan["metadata"]["itemType"],
                        "warnings": ["本次仅加入 Zotero 书目；PDF 和 Vault 知识单元不在本次操作内。"]})
                    return
                if path.path == "/api/ingestion/execute":
                    if not ({"plan_id", "confirmed"} <= set(payload) <= {"plan_id", "confirmed", "retry"}):
                        raise ResearchError("Ingestion execution needs a confirmed server preview.")
                    self._respond(200, ingestion.execute(payload["plan_id"], payload["confirmed"], retry=payload.get("retry", False)))
                    return
                if path.path == "/api/shutdown":
                    if payload:
                        raise ResearchError("Shutdown does not accept parameters.")
                    self._respond(200, {"status": "stopping"})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                expected = {"candidate_id", "expected_revision"}
                if path.path == "/api/decisions":
                    expected.add("decision")
                elif path.path not in {"/api/reviews", "/api/reviews/revoke", "/api/metrics"}:
                    self._error("Recommendation route was not found.", 2, 404)
                    return
                if (set(payload) != expected or not isinstance(payload.get("candidate_id"), str)
                        or not 1 <= len(payload["candidate_id"]) <= 128
                        or type(payload.get("expected_revision")) is not int
                        or payload["expected_revision"] < 0):
                    raise ResearchError("Candidate update needs an identity and exact current revision.")
                if path.path == "/api/decisions":
                    if (not isinstance(payload["decision"], str)
                            or payload["decision"] not in {"unread", "saved", "selected", "ignored"}):
                        raise ResearchError("Unknown recommendation decision.")
                    result = store.set_decision(payload["candidate_id"], payload["decision"],
                                                payload["expected_revision"])
                elif path.path == "/api/metrics":
                    result = refresh_candidate_metrics(store, payload["candidate_id"], payload["expected_revision"])
                elif path.path == "/api/reviews/revoke":
                    result = store.revoke_review(payload["candidate_id"], payload["expected_revision"])
                else:
                    result = store.review_candidate(payload["candidate_id"], payload["expected_revision"])
                self._respond(200, result)
            except ResearchError as exc:
                self._error(str(exc), exc.exit_code)
            except (OSError, ValueError, TypeError, KeyError):
                self._error("Recommendation update could not be confirmed; refresh before retrying.", 3)

        def do_OPTIONS(self):
            if self._boundary():
                self._error("Cross-origin API access is unavailable.", 7)

    server = RecommendationHTTPServer(("127.0.0.1", port), Handler)
    server.runtime_identity = {"pid": os.getpid(), "profile": profile, "version": __version__}
    server.timeout = 1
    return server


def serve(state_dir: Path, profile: str, token: str, port: int = 0) -> None:
    """Run the foreground service for the installed CLI's managed child process."""
    server = create_server(state_dir, profile, token, port)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
