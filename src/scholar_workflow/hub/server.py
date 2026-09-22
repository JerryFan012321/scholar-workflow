"""Loopback-only HTTP server for the Scholar Workflow research Hub."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import sys
import threading
from dataclasses import dataclass, replace
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from scholar_workflow.hub.actions import (
    ActionKind,
    CatalogActionService,
    CmuxArtifactLauncher,
    CmuxLauncher,
    CmuxResourceLauncher,
    InvalidActionTarget,
    ObsidianLauncher,
    PublicAction,
    UnknownActionError,
    ZoteroLauncher,
)
from scholar_workflow.hub.artifact_manifest import VaultArtifactManifestProvider
from scholar_workflow.hub.assets import (
    AssetIntegrityError,
    AssetManifestError,
    InvalidAssetNameError,
    UnknownAssetError,
    VaultAssetCatalogProvider,
    VaultAssetManifestStore,
    VaultAssetStore,
)
from scholar_workflow.hub.catalog import (
    CatalogProvider,
    CatalogSnapshotStore,
    StaticCatalogProvider,
)
from scholar_workflow.hub.cmux import CmuxControl, CmuxControlError, WorkspaceRegistry
from scholar_workflow.hub.content import (
    MAX_WRITE_REQUEST_BYTES,
    ArtifactContentStore,
    ArtifactEncodingError,
    ArtifactMissingError,
    ArtifactPathRejectedError,
    ArtifactTooLargeError,
    InvalidArtifactContentError,
    RevisionConflictError,
    UnknownArtifactError,
    UnsupportedArtifactError,
)
from scholar_workflow.hub.directory import (
    HubDirectoryService,
    LibraryProviderUnavailable,
    OperationStatus,
    ProjectRegistry,
    RegistryError,
    ToolRegistry,
    TypedEntityRef,
    UnknownLibraryError,
    ZoteroPaperLibraryProvider,
)
from scholar_workflow.hub.links import LinkedCatalogProvider, ProjectionLinkStore
from scholar_workflow.hub.models import AssetRole, HubAsset
from scholar_workflow.hub.project_docs import (
    DocumentCollisionError,
    ProjectConfirmationRequired,
    ProjectDocumentError,
    ProjectDocumentMissingError,
    ProjectDocumentService,
    ProjectPathError,
)
from scholar_workflow.hub.vault import VaultCatalogProvider
from scholar_workflow.hub.workspaces import (
    WorkspaceBindingCoordinator,
    WorkspaceBindingRegistry,
    WorkspaceProfile,
)

_KEY_RE = re.compile(r"^[A-Z0-9]+$")
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_HUB_INSTANCE_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_CMUX_HUB_CAPABILITY = "cmux-workspace-actions-v1"
_V2_CAPABILITIES = (
    "hub-directory-v2",
    "typed-library-pagination-v1",
    "explicit-project-registry-v1",
    "explicit-tool-registry-v1",
    "project-documents-v1",
    "workspace-binding-v1",
    "task-contracts-v1",
)
_MAX_V2_WRITE_BYTES = 32 * 1024
_STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
_INLINE_ASSET_TYPES = {
    "application/json",
    "application/pdf",
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/csv",
    "text/markdown",
    "text/plain",
}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@dataclass(frozen=True)
class HubRuntime:
    storage_root: Path
    vault_root: Path
    catalog_provider: CatalogProvider
    session_token: str
    content_store: ArtifactContentStore
    asset_store: VaultAssetStore
    action_service: Any | None = None
    directory_service: HubDirectoryService | None = None
    project_document_service: ProjectDocumentService | None = None
    binding_registry: WorkspaceBindingRegistry | None = None
    binding_coordinator: WorkspaceBindingCoordinator | None = None
    service_generation: str = "unknown-generation"
    owner_mode: str = "headless"
    require_workspace_binding: bool = True
    log_path: Path | None = None
    state_root: Path | None = None
    catalog_path: Path | None = None


class _StaticActionService:
    """Compatibility wrapper for explicitly injected test/application actions."""

    def __init__(
        self,
        executor: Any | None,
        public_actions: dict[str, list[PublicAction]] | None,
    ) -> None:
        self._executor = executor
        self._public_actions = public_actions or {}

    def public_actions(self) -> dict[str, list[PublicAction]]:
        return self._public_actions

    def execute(self, action_id: str, *, workspace_id: str | None = None) -> Any:
        if self._executor is None:
            raise UnknownActionError("Hub actions are unavailable")
        if workspace_id is None:
            return self._executor.execute(action_id)
        return self._executor.execute(action_id, workspace_id=workspace_id)


class HubHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], runtime: HubRuntime) -> None:
        self.runtime = runtime
        super().__init__(address, HubRequestHandler)


class HubRequestHandler(BaseHTTPRequestHandler):
    server: HubHTTPServer

    def do_OPTIONS(self) -> None:
        self._respond_text(405, "Method not allowed")

    def do_HEAD(self) -> None:
        if not self._request_origin_allowed():
            return
        path = urlparse(self.path).path
        if path == "/open/paper" or path.startswith("/open/paper/"):
            self._handle_pdf(path, send_body=False)
            return
        asset_id = self._asset_content_id(path)
        if asset_id is not None:
            self._handle_asset_content(asset_id, send_body=False)
            return
        self._respond_text(405, "Method not allowed")

    def do_GET(self) -> None:
        if not self._request_origin_allowed():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/hub", "/hub/"}:
            self._serve_static("index.html")
        elif path == "/hub/item":
            self._handle_typed_item_landing(parsed.query)
        elif path.startswith("/hub/assets/"):
            self._serve_static(path.removeprefix("/hub/assets/"))
        elif path == "/api/v1/session":
            self._respond_json(200, {"csrf_token": self.server.runtime.session_token})
        elif path == "/api/v1/catalog":
            service = self.server.runtime.directory_service
            catalog = (
                service.compatibility_catalog()
                if service is not None
                else self.server.runtime.catalog_provider.load()
            )
            self._respond_json(200, catalog.model_dump(mode="json"))
        elif path == "/api/v2/directory":
            self._handle_v2_directory(parsed.query)
        elif path.startswith("/api/v2/libraries/") and path.endswith("/items"):
            self._handle_v2_library(path, parsed.query)
        elif path == "/api/v2/health":
            self._respond_json(200, self._v2_health_payload())
        elif path == "/api/v1/actions":
            service = self.server.runtime.action_service
            groups = service.public_actions() if service is not None else {}
            self._respond_json(
                200,
                {
                    entity_id: [
                        {
                            "id": action.id,
                            "label": action.label,
                            "kind": _enum_value(action.kind),
                            "workspace_policy": _action_workspace_policy(action),
                        }
                        for action in actions
                    ]
                    for entity_id, actions in groups.items()
                },
            )
        elif path == "/api/v1/cmux/workspaces":
            self._handle_cmux_workspaces(parsed.query)
        elif path == "/api/v1/health":
            self._respond_json(
                200,
                {
                    "status": "ok",
                    "schema_version": 1,
                    "capabilities": [_CMUX_HUB_CAPABILITY],
                },
            )
        elif path.startswith("/api/v1/artifacts/") and path.endswith("/content"):
            encoded_id = path[len("/api/v1/artifacts/"):-len("/content")]
            self._handle_artifact_content(unquote(encoded_id))
        elif (artifact_id := self._artifact_assets_id(path)) is not None:
            self._handle_artifact_assets(artifact_id)
        elif (asset_id := self._asset_content_id(path)) is not None:
            self._handle_asset_content(asset_id, send_body=True)
        elif path == "/open/paper" or path.startswith("/open/paper/"):
            self._handle_pdf(path, send_body=True)
        else:
            self._respond_text(404, "Not found")

    def do_PUT(self) -> None:
        if not self._request_origin_allowed(require_origin=True):
            return
        if not self._legacy_write_binding_allowed():
            return
        path = urlparse(self.path).path
        artifact_id = self._artifact_content_id(path)
        if artifact_id is None:
            self._respond_text(404, "Not found")
            return
        supplied_token = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied_token, self.server.runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._respond_text(415, "Expected application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond_text(400, "Invalid content length")
            return
        if length < 0:
            self._respond_text(400, "Invalid content length")
            return
        if length > MAX_WRITE_REQUEST_BYTES:
            self._respond_text(413, "Request body too large")
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._respond_text(400, "Invalid JSON")
            return
        if not isinstance(body, dict) or set(body) != {"content", "base_revision"}:
            self._respond_text(400, "Expected content and base_revision only")
            return
        content = body.get("content")
        base_revision = body.get("base_revision")
        if not isinstance(content, str) or not isinstance(base_revision, str):
            self._respond_text(400, "content and base_revision must be strings")
            return
        try:
            saved = self.server.runtime.content_store.write(
                artifact_id,
                content=content,
                base_revision=base_revision,
            )
        except RevisionConflictError as exc:
            self._respond_json(
                409,
                {"error": str(exc), "current_revision": exc.current_revision},
            )
            return
        except InvalidArtifactContentError as exc:
            self._respond_text(422, str(exc))
            return
        except ArtifactPathRejectedError:
            self._respond_text(403, "Artifact path was rejected")
            return
        except (UnknownArtifactError, ArtifactMissingError):
            self._respond_text(404, "Unknown or missing artifact")
            return
        except (UnsupportedArtifactError, ArtifactEncodingError):
            self._respond_text(415, "Artifact format is not editable")
            return
        except ArtifactTooLargeError:
            self._respond_text(413, "Artifact is too large for the Hub editor")
            return
        self._respond_json(200, saved.as_payload())

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/api/v2/workspaces/nonce", "/api/v2/workspaces/bind"}:
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v2_workspace_binding(path)
            return
        if path.startswith("/api/v2/projects/") and "/docs/" in path:
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v2_project_document_operation(path)
            return
        artifact_id = self._artifact_assets_id(path)
        if artifact_id is not None:
            if not self._request_origin_allowed(require_origin=True):
                return
            if not self._legacy_write_binding_allowed():
                return
            self._handle_asset_upload(artifact_id, parsed.query)
            return
        if not self._request_origin_allowed(require_origin=True):
            return
        if not self._legacy_write_binding_allowed():
            return
        if not path.startswith("/api/v1/actions/"):
            self._respond_text(404, "Not found")
            return
        supplied_token = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied_token, self.server.runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._respond_text(415, "Expected application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond_text(400, "Invalid content length")
            return
        if length < 0:
            self._respond_text(400, "Invalid content length")
            return
        if length > 1024:
            self._respond_text(413, "Request body too large")
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._respond_text(400, "Invalid JSON")
            return
        if not isinstance(body, dict) or set(body) - {"workspace_id"}:
            self._respond_text(400, "Expected no fields or workspace_id only")
            return
        workspace_supplied = "workspace_id" in body
        workspace_id = body.get("workspace_id")
        if workspace_supplied and (
            not isinstance(workspace_id, str)
            or not workspace_id
            or workspace_id != workspace_id.strip()
            or len(workspace_id) > 256
        ):
            self._respond_text(400, "workspace_id must be a non-empty opaque id")
            return
        service = self.server.runtime.action_service
        if service is None:
            self._respond_text(503, "Actions are unavailable")
            return
        action_id = unquote(path.removeprefix("/api/v1/actions/"))
        action = _find_public_action(service, action_id)
        if action is None:
            self._respond_text(404, "Unknown action")
            return
        workspace_policy = _action_workspace_policy(action)
        if workspace_policy == "required" and not workspace_supplied:
            self._respond_text(400, "This action requires workspace_id")
            return
        if workspace_supplied and workspace_policy not in {"required", "selectable"}:
            self._respond_text(400, "This action does not accept workspace_id")
            return
        try:
            if workspace_id is None:
                result = service.execute(action_id)
            else:
                result = service.execute(action_id, workspace_id=workspace_id)
        except (KeyError, UnknownActionError):
            self._respond_text(404, "Unknown action")
            return
        except InvalidActionTarget as exc:
            self._respond_json(400, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP boundary for launcher plugins
            self._respond_json(503, {"ok": False, "error": str(exc)})
            return
        if hasattr(result, "model_dump"):
            payload = result.model_dump(mode="json")
        elif hasattr(result, "__dict__"):
            payload = vars(result)
        else:
            payload = result
        self._respond_json(200, payload)

    def _handle_v2_workspace_binding(self, path: str) -> None:
        runtime = self.server.runtime
        supplied_token = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied_token, runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return
        if runtime.owner_mode != "cmux-visible":
            self._respond_json(
                409,
                {
                    "ok": False,
                    "code": "headless_read_only",
                    "error": "Headless Hub services cannot bind writable views",
                },
            )
            return
        instance_token = self.headers.get("X-Scholar-Hub-Instance", "")
        if not _HUB_INSTANCE_RE.fullmatch(instance_token):
            self._respond_text(400, "Invalid Hub instance token")
            return
        coordinator = runtime.binding_coordinator
        if coordinator is None:
            self._respond_text(503, "Workspace binding is unavailable")
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if path.endswith("/nonce"):
            if body:
                self._respond_text(400, "Workspace nonce request accepts no fields")
                return
            nonce = coordinator.issue_nonce(instance_token)
            self._respond_json(
                200,
                {
                    "nonce": nonce,
                    "service_generation": runtime.service_generation,
                    "expires_in_seconds": 120,
                },
            )
            return
        if set(body) != {"nonce", "profile_id", "workspace_id"}:
            self._respond_text(400, "Expected nonce, profile_id, and workspace_id only")
            return
        try:
            _require_string_fields(body, "nonce", "profile_id", "workspace_id")
            lease = coordinator.bind(
                instance_token=instance_token,
                nonce=body["nonce"],
                profile_id=body["profile_id"],
                opaque_workspace_id=body["workspace_id"],
            )
        except (CmuxControlError, ValueError) as exc:
            self._respond_json(409, {"ok": False, "code": "binding_rejected", "error": str(exc)})
            return
        self._respond_json(
            200,
            {
                "ok": True,
                "profile_id": lease.profile_id,
                "lease_generation": lease.lease_generation,
                "service_generation": lease.service_generation,
                "expires_at": lease.expires_at.isoformat(),
            },
        )

    def _handle_v2_directory(self, query: str) -> None:
        service = self.server.runtime.directory_service
        if service is None:
            self._respond_text(503, "HubDirectory is unavailable")
            return
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) - {"instance"}:
            self._respond_text(400, "Only instance is accepted")
            return
        values = parameters.get("instance", [])
        if len(values) > 1:
            self._respond_text(400, "Expected at most one instance")
            return
        instance_token = values[0] if values else None
        if instance_token is not None and not _HUB_INSTANCE_RE.fullmatch(instance_token):
            self._respond_text(400, "Invalid Hub instance token")
            return
        try:
            directory = service.load()
        except (LibraryProviderUnavailable, OSError, ValueError, RegistryError):
            self._respond_text(503, "HubDirectory provider failed")
            return
        directory = directory.model_copy(
            update={"operations": self._operation_status(instance_token)}
        )
        self._respond_json(200, directory.model_dump(mode="json"))

    def _handle_v2_library(self, path: str, query: str) -> None:
        service = self.server.runtime.directory_service
        if service is None:
            self._respond_text(503, "HubDirectory is unavailable")
            return
        segments = path.strip("/").split("/")
        if len(segments) != 5 or segments[:3] != ["api", "v2", "libraries"]:
            self._respond_text(404, "Not found")
            return
        library_id = unquote(segments[3])
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) - {"cursor", "limit", "query", "sort", "direction", "type"}:
            self._respond_text(400, "Unsupported library query field")
            return
        if any(len(values) != 1 for values in parameters.values()):
            self._respond_text(400, "Library query fields may appear once")
            return
        cursor = parameters.get("cursor", [None])[0]
        query_text = parameters.get("query", [None])[0]
        try:
            limit = int(parameters.get("limit", ["50"])[0])
            page = service.list_items(
                library_id,
                cursor=cursor,
                limit=limit,
                query=query_text,
                sort=parameters.get("sort", ["title"])[0],
                direction=parameters.get("direction", ["asc"])[0],
                item_type=parameters.get("type", [None])[0],
            )
        except UnknownLibraryError:
            self._respond_text(404, "Unknown library")
            return
        except ValueError as exc:
            self._respond_text(400, str(exc))
            return
        except (LibraryProviderUnavailable, OSError, RegistryError):
            self._respond_text(503, "Library provider failed")
            return
        self._respond_json(200, page.model_dump(mode="json"))

    def _v2_health_payload(self) -> dict[str, Any]:
        runtime = self.server.runtime
        try:
            package_version = version("scholar-workflow")
        except PackageNotFoundError:
            package_version = "unknown"
        provider_capabilities: dict[str, dict[str, Any]] = {
            identifier: {
                "available": False,
                "authority": "unavailable",
                "detail": "HubDirectory provider is not configured",
            }
            for identifier in ("papers", "projects", "tools")
        }
        if runtime.directory_service is not None:
            try:
                provider_capabilities = {
                    row.library_id: {
                        "available": row.available,
                        "authority": row.authority,
                        "detail": row.detail,
                    }
                    for row in runtime.directory_service.load().libraries
                }
            except (LibraryProviderUnavailable, OSError, ValueError, RegistryError):
                provider_capabilities = {
                    identifier: {
                        "available": False,
                        "authority": "unavailable",
                        "detail": "Provider health check failed",
                    }
                    for identifier in ("papers", "projects", "tools")
                }
        cmux_fingerprint: str | None = None
        cmux_detail = "Hub service is headless"
        if runtime.owner_mode == "cmux-visible" and runtime.binding_coordinator is not None:
            try:
                cmux_fingerprint = (
                    runtime.binding_coordinator.current_instance_fingerprint()
                )
                cmux_detail = None
            except (CmuxControlError, ValueError):
                cmux_detail = "Current cmux instance is unavailable"
        instance_token = self.headers.get("X-Scholar-Hub-Instance", "")
        workspace_bound = False
        if instance_token and runtime.owner_mode == "cmux-visible":
            try:
                self._require_live_binding(instance_token)
            except (CmuxControlError, ValueError):
                pass
            else:
                workspace_bound = True
        build_revision = None
        log_path = str(runtime.log_path) if runtime.log_path is not None else None
        return {
            "status": "ok",
            "service": {
                "name": "scholar-workflow-hub",
                "version": package_version,
            },
            "package": {
                "name": "scholar-workflow",
                "version": package_version,
            },
            "build": {
                "version": package_version,
                "revision": build_revision,
                "detail": "Build revision is unavailable",
            },
            "protocol": {"name": "hub-http", "version": 2},
            "hub_directory": {"schema_version": 2},
            # Flat aliases remain temporarily for diagnostics consumers that
            # predate the structured v2 health contract.
            "service_name": "scholar-workflow-hub",
            "service_version": package_version,
            "protocol_version": 2,
            "root_schema_version": 2,
            "service_generation": runtime.service_generation,
            "owner_mode": runtime.owner_mode,
            "process": {
                "pid": os.getpid(),
                "executable": str(Path(sys.executable).resolve()),
            },
            "origin": (
                f"http://{self.server.server_address[0]}:"
                f"{self.server.server_address[1]}"
            ),
            "roots": {
                "state": str(runtime.state_root) if runtime.state_root is not None else None,
                "catalog": (
                    str(runtime.catalog_path)
                    if runtime.catalog_path is not None
                    else None
                ),
                "vault": str(runtime.vault_root),
                "storage": str(runtime.storage_root),
            },
            "capabilities": list(_V2_CAPABILITIES),
            "provider_capabilities": provider_capabilities,
            "providers": {
                identifier: detail["available"]
                for identifier, detail in provider_capabilities.items()
            },
            "worker_capabilities": {
                "task_contracts": True,
                "task_execution": False,
                "detail": "Codex task worker is not enabled in this release",
            },
            "workspace_binding_required": runtime.require_workspace_binding,
            "workspace_binding_available": (
                runtime.owner_mode == "cmux-visible"
                and runtime.binding_coordinator is not None
            ),
            "workspace_bound": workspace_bound,
            "cmux_instance_fingerprint": cmux_fingerprint,
            "cmux": {
                "instance_fingerprint": cmux_fingerprint,
                "detail": cmux_detail,
            },
            "task_execution": False,
            "log_path": log_path,
            "log": {
                "path": log_path,
                "detail": (
                    None if log_path is not None else "Log location is unavailable"
                ),
            },
        }

    def _operation_status(self, instance_token: str | None) -> OperationStatus:
        runtime = self.server.runtime
        if runtime.owner_mode != "cmux-visible":
            return OperationStatus(reason="Headless Hub service is read-only")
        if instance_token is None:
            return OperationStatus()
        try:
            self._require_live_binding(instance_token)
        except (CmuxControlError, ValueError):
            return OperationStatus()
        return OperationStatus(
            bound=True,
            project_documents=runtime.project_document_service is not None,
            workspace_actions=runtime.action_service is not None,
            task_actions=False,
            reason="Task worker execution is not enabled",
        )

    def _require_live_binding(self, instance_token: str):
        runtime = self.server.runtime
        if runtime.owner_mode != "cmux-visible":
            raise ValueError("Headless Hub service is read-only")
        coordinator = runtime.binding_coordinator
        if coordinator is None:
            raise ValueError("Workspace binding is unavailable")
        return coordinator.require_current_binding(instance_token)

    def _legacy_write_binding_allowed(self) -> bool:
        runtime = self.server.runtime
        if runtime.owner_mode != "cmux-visible":
            self._respond_json(
                409,
                {
                    "ok": False,
                    "code": "headless_read_only",
                    "error": "Headless Hub services are read-only",
                },
            )
            return False
        if not runtime.require_workspace_binding:
            return True
        instance_token = self.headers.get("X-Scholar-Hub-Instance", "")
        if instance_token:
            try:
                self._require_live_binding(instance_token)
            except (CmuxControlError, ValueError):
                pass
            else:
                return True
        self._respond_json(
            409,
            {
                "ok": False,
                "code": "workspace_unbound",
                "error": "Hub view must be bound before state-changing operations",
            },
        )
        return False

    def _handle_v2_project_document_operation(self, path: str) -> None:
        runtime = self.server.runtime
        supplied_token = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied_token, runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return
        if runtime.owner_mode != "cmux-visible":
            self._respond_json(
                409,
                {
                    "ok": False,
                    "code": "headless_read_only",
                    "error": "Headless Hub services are read-only",
                },
            )
            return
        instance_token = self.headers.get("X-Scholar-Hub-Instance", "")
        try:
            self._require_live_binding(instance_token)
        except (CmuxControlError, ValueError):
            self._respond_json(
                409,
                {
                    "ok": False,
                    "code": "workspace_unbound",
                    "error": "Hub view must be bound before project document operations",
                },
            )
            return
        service = runtime.project_document_service
        if service is None:
            self._respond_text(503, "Project document operations are unavailable")
            return
        segments = path.strip("/").split("/")
        if len(segments) != 6 or segments[:3] != ["api", "v2", "projects"] or segments[4] != "docs":
            self._respond_text(404, "Not found")
            return
        project_id = unquote(segments[3])
        operation = segments[5]
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        try:
            if operation == "copy":
                if set(body) - {"source_path", "destination_path", "confirm_git"} or not {
                    "source_path",
                    "destination_path",
                }.issubset(body):
                    raise ValueError(
                        "Expected source_path, destination_path, and optional confirm_git only"
                    )
                _require_string_fields(body, "source_path", "destination_path")
                _require_optional_bool(body, "confirm_git")
                result = service.copy_within(
                    project_id,
                    body["source_path"],
                    body["destination_path"],
                    confirm_git=body.get("confirm_git", False),
                )
            elif operation == "copy-knowledge":
                if set(body) - {"artifact_id", "destination_path", "confirm_git"} or not {
                    "artifact_id",
                    "destination_path",
                }.issubset(body):
                    raise ValueError(
                        "Expected artifact_id, destination_path, and optional confirm_git only"
                    )
                _require_string_fields(body, "artifact_id", "destination_path")
                _require_optional_bool(body, "confirm_git")
                result = service.copy_knowledge_artifact(
                    project_id,
                    body["artifact_id"],
                    body["destination_path"],
                    catalog_provider=runtime.catalog_provider,
                    vault_root=runtime.vault_root,
                    confirm_git=body.get("confirm_git", False),
                )
            elif operation == "paste":
                if set(body) - {"destination_path", "content", "confirm_git"} or not {
                    "destination_path",
                    "content",
                }.issubset(body):
                    raise ValueError(
                        "Expected destination_path, content, and optional confirm_git only"
                    )
                _require_string_fields(body, "destination_path")
                if not isinstance(body["content"], str) or "\x00" in body["content"]:
                    raise ValueError("content must be UTF-8 text without NUL bytes")
                _require_optional_bool(body, "confirm_git")
                result = service.paste_text(
                    project_id,
                    body["destination_path"],
                    body["content"],
                    confirm_git=body.get("confirm_git", False),
                )
            elif operation == "trash":
                if set(body) - {"relative_path", "confirm_git"} or "relative_path" not in body:
                    raise ValueError("Expected relative_path and optional confirm_git only")
                _require_string_fields(body, "relative_path")
                _require_optional_bool(body, "confirm_git")
                result = service.trash(
                    project_id,
                    body["relative_path"],
                    confirm_git=body.get("confirm_git", False),
                )
            else:
                self._respond_text(404, "Unknown project document operation")
                return
        except ValueError as exc:
            self._respond_text(400, str(exc))
            return
        except ProjectConfirmationRequired as exc:
            self._respond_json(
                409,
                {
                    "ok": False,
                    "code": "confirmation_required",
                    "error": str(exc),
                    "git_state": exc.git_state,
                    "path_role": exc.path_role,
                },
            )
            return
        except DocumentCollisionError as exc:
            self._respond_json(409, {"ok": False, "code": "destination_exists", "error": str(exc)})
            return
        except ProjectPathError as exc:
            self._respond_json(403, {"ok": False, "code": "path_rejected", "error": str(exc)})
            return
        except ProjectDocumentMissingError as exc:
            self._respond_json(404, {"ok": False, "code": "document_missing", "error": str(exc)})
            return
        except ProjectDocumentError:
            self._respond_text(503, "Project document operation failed")
            return
        self._respond_json(200, {"ok": True, **result.as_payload()})

    def _read_v2_json_body(self) -> dict[str, Any] | None:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._respond_text(415, "Expected application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length < 0:
            raise ValueError("Invalid content length")
        if length > _MAX_V2_WRITE_BYTES:
            self._respond_text(413, "Request body too large")
            return None
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(body, dict):
            raise TypeError("Expected a JSON object")
        return body

    def _request_origin_allowed(self, *, require_origin: bool = False) -> bool:
        host = self.headers.get("Host", "")
        expected_port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{expected_port}", f"localhost:{expected_port}"}
        if host not in allowed_hosts:
            self._respond_text(403, "Invalid Host")
            return False
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://{candidate}" for candidate in allowed_hosts}
        if require_origin and origin is None:
            self._respond_text(403, "Origin is required")
            return False
        if origin is not None and origin not in allowed_origins:
            self._respond_text(403, "Invalid Origin")
            return False
        return True

    def _serve_static(self, relative_name: str) -> None:
        if not relative_name or "/" in relative_name or "\\" in relative_name:
            self._respond_text(404, "Not found")
            return
        try:
            asset = resources.files("scholar_workflow.hub.static").joinpath(relative_name)
            data = asset.read_bytes()
        except (FileNotFoundError, ModuleNotFoundError):
            self._respond_text(404, "Not found")
            return
        content_type = _STATIC_TYPES.get(Path(relative_name).suffix)
        if content_type is None:
            content_type = mimetypes.guess_type(relative_name)[0] or "application/octet-stream"
        self._respond_bytes(200, data, content_type)

    def _handle_typed_item_landing(self, query: str) -> None:
        parameters = parse_qs(query, keep_blank_values=True)
        expected = {"library_id", "item_type", "item_id"}
        if set(parameters) != expected or any(
            len(parameters[name]) != 1 for name in expected
        ):
            self._respond_text(400, "Expected one complete typed entity reference")
            return
        try:
            reference = TypedEntityRef(
                library_id=parameters["library_id"][0],
                item_type=parameters["item_type"][0],
                item_id=parameters["item_id"][0],
            )
        except ValueError:
            self._respond_text(400, "Invalid typed entity reference")
            return
        service = self.server.runtime.directory_service
        if service is None:
            self._respond_text(503, "HubDirectory is unavailable")
            return
        try:
            item = service.resolve_item(reference)
        except LibraryProviderUnavailable:
            self._respond_text(503, "Authoritative provider is unavailable")
            return
        if item is None:
            self._respond_text(404, "Typed item is unavailable")
            return
        title = escape(
            str(
                item.get("title")
                or item.get("display_name")
                or reference.item_id
            )
        )
        identity = escape(
            f"{reference.library_id}:{reference.item_type}:{reference.item_id}"
        )
        details = []
        authors = item.get("authors")
        if isinstance(authors, list) and authors:
            details.append(f"<p>{escape(' · '.join(map(str, authors)))}</p>")
        venue = item.get("venue")
        if venue:
            details.append(f"<p>{escape(str(venue))}</p>")
        capabilities = item.get("capabilities")
        if isinstance(capabilities, list) and capabilities:
            details.append(
                f"<p>Capabilities: {escape(' · '.join(map(str, capabilities)))}</p>"
            )

        entry = ""
        attachment_key = item.get("attachment_key")
        if reference.item_type == "paper":
            if isinstance(attachment_key, str) and _KEY_RE.fullmatch(attachment_key):
                attachment_query = urlencode(
                    {
                        "library_id": "papers",
                        "item_type": "attachment",
                        "item_id": attachment_key,
                    }
                )
                entry = (
                    f'<p><a href="/hub/item?{escape(attachment_query, quote=True)}">'
                    "打开 PDF 附件落地页</a></p>"
                )
            else:
                entry = "<p>当前没有可用 PDF 附件。</p>"
        elif reference.item_type == "attachment":
            if isinstance(attachment_key, str) and _KEY_RE.fullmatch(attachment_key):
                entry = (
                    f'<p><a href="/open/paper/{quote(attachment_key, safe="")}">'
                    "阅读 PDF</a></p>"
                )
        elif reference.item_type == "artifact":
            artifact_query = urlencode({"artifact": reference.item_id})
            entry = (
                f'<p><a href="/hub/?{escape(artifact_query, quote=True)}">在 Hub 中阅读</a></p>'
            )
            kind = item.get("kind")
            vault_path = item.get("vault_path")
            if kind:
                details.append(f"<p>类型：{escape(str(kind))}</p>")
            if vault_path:
                details.append(f"<p>Vault 路径：{escape(str(vault_path))}</p>")
        document = (
            "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<title>{title} · Scholar Workflow</title></head><body>"
            '<nav><a href="/hub/">返回 Hub</a></nav>'
            f"<main><h1>{title}</h1>{''.join(details)}"
            f"<p><code>{identity}</code></p>{entry}</main></body></html>"
        ).encode()
        self._respond_bytes(200, document, "text/html; charset=utf-8")

    def _handle_pdf(self, path: str, *, send_body: bool) -> None:
        segments = path.strip("/").split("/")
        if len(segments) != 3 or segments[:2] != ["open", "paper"]:
            self._respond_text(400, "Bad request")
            return
        key = segments[2]
        if not _KEY_RE.fullmatch(key):
            self._respond_text(400, "Invalid key")
            return
        pdf = self._find_pdf(key)
        if pdf is None:
            self._respond_text(404, f"No PDF for attachment: {key}")
            return
        size = pdf.stat().st_size
        byte_range = self._parse_range(size)
        if byte_range is False:
            self.send_response(416)
            self._security_headers()
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start, end = byte_range if byte_range is not None else (0, size - 1)
        length = max(0, end - start + 1)
        self.send_response(206 if byte_range is not None else 200)
        self._security_headers()
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if byte_range is not None:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        encoded_name = quote(pdf.name, safe="")
        self.send_header(
            "Content-Disposition",
            f"inline; filename=paper.pdf; filename*=UTF-8''{encoded_name}",
        )
        self.end_headers()
        if not send_body or length == 0:
            return
        with pdf.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _handle_cmux_workspaces(self, query: str) -> None:
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) - {"instance"}:
            self._respond_text(400, "Only the Hub instance token is accepted")
            return
        instance_values = parameters.get("instance", [])
        if len(instance_values) > 1:
            self._respond_text(400, "Expected at most one Hub instance token")
            return
        instance_token = instance_values[0] if instance_values else None
        if instance_token is not None and not _HUB_INSTANCE_RE.fullmatch(instance_token):
            self._respond_text(400, "Invalid Hub instance token")
            return
        self._respond_json(
            200,
            _workspace_listing_payload(
                self.server.runtime.action_service,
                instance_token=instance_token,
            ),
        )

    def _find_pdf(self, key: str) -> Path | None:
        root = self.server.runtime.storage_root.resolve()
        directory = (root / key).resolve()
        if directory.parent != root or not directory.is_dir():
            return None
        for candidate in sorted(directory.glob("*.pdf")):
            resolved = candidate.resolve()
            if resolved.parent == directory and resolved.is_file():
                return resolved
        return None

    def _handle_artifact_content(self, artifact_id: str) -> None:
        try:
            content = self.server.runtime.content_store.read(artifact_id)
        except ArtifactPathRejectedError:
            self._respond_text(403, "Artifact escaped the Vault")
            return
        except (UnknownArtifactError, ArtifactMissingError):
            self._respond_text(404, "Unknown or missing artifact")
            return
        except ArtifactTooLargeError:
            self._respond_text(413, "Artifact is too large for inline preview")
            return
        except (UnsupportedArtifactError, ArtifactEncodingError):
            self._respond_text(415, "Artifact is not UTF-8 text")
            return
        self._respond_json(200, content.as_payload())

    def _handle_artifact_assets(self, artifact_id: str) -> None:
        catalog = self.server.runtime.catalog_provider.load()
        if not any(row.artifact_id == artifact_id for row in catalog.artifacts):
            self._respond_text(404, "Unknown artifact")
            return
        try:
            declared = self.server.runtime.asset_store.list_for_artifact(artifact_id)
            assets = [self.server.runtime.asset_store.get(row.asset_id) for row in declared]
        except (AssetManifestError, AssetIntegrityError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        self._respond_json(
            200,
            {"artifact_id": artifact_id, "assets": [_asset_payload(row) for row in assets]},
        )

    def _handle_asset_upload(self, artifact_id: str, query: str) -> None:
        supplied_token = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied_token, self.server.runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) - {"name", "role"} or len(parameters.get("name", [])) != 1:
            self._respond_text(400, "Expected one attachment name")
            return
        name = parameters["name"][0]
        role_values = parameters.get("role", [AssetRole.SUPPLEMENT.value])
        if len(role_values) != 1:
            self._respond_text(400, "Expected one attachment role")
            return
        try:
            role = AssetRole(role_values[0])
        except ValueError:
            self._respond_text(422, "Unsupported attachment role")
            return
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._respond_text(411, "Content-Length is required")
            return
        try:
            length = int(raw_length)
        except ValueError:
            self._respond_text(400, "Invalid content length")
            return
        if length < 0:
            self._respond_text(400, "Invalid content length")
            return
        if length > self.server.runtime.asset_store.max_bytes:
            self._respond_text(413, "Attachment is too large")
            return
        content = self.rfile.read(length)
        if len(content) != length:
            self._respond_text(400, "Incomplete attachment body")
            return
        try:
            asset = self.server.runtime.asset_store.add_bytes(
                artifact_id,
                name,
                content,
                role=role,
            )
        except KeyError:
            self._respond_text(404, "Unknown artifact")
            return
        except InvalidAssetNameError as exc:
            self._respond_text(422, str(exc))
            return
        except ValueError as exc:
            if "too large" in str(exc):
                self._respond_text(413, "Attachment is too large")
            else:
                self._respond_text(422, str(exc))
            return
        except (AssetManifestError, AssetIntegrityError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        except OSError as exc:
            self._respond_json(503, {"error": f"Attachment storage failed: {exc}"})
            return
        self._respond_json(201, _asset_payload(asset))

    def _handle_asset_content(self, asset_id: str, *, send_body: bool) -> None:
        try:
            asset = self.server.runtime.asset_store.get(asset_id)
            path = self.server.runtime.asset_store.resolve_path(asset_id)
        except UnknownAssetError:
            self._respond_text(404, "Unknown attachment")
            return
        except (AssetManifestError, AssetIntegrityError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        disposition = "inline" if asset.media_type in _INLINE_ASSET_TYPES else "attachment"
        encoded_name = quote(asset.display_name, safe="")
        self.send_response(200)
        self._security_headers()
        self.send_header("Content-Type", asset.media_type)
        self.send_header("Content-Length", str(asset.size))
        self.send_header(
            "Content-Disposition",
            f"{disposition}; filename=attachment; filename*=UTF-8''{encoded_name}",
        )
        self.end_headers()
        if not send_body or asset.size == 0:
            return
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    @staticmethod
    def _artifact_content_id(path: str) -> str | None:
        prefix = "/api/v1/artifacts/"
        suffix = "/content"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        encoded_id = path[len(prefix):-len(suffix)]
        if not encoded_id:
            return None
        return unquote(encoded_id)

    @staticmethod
    def _artifact_assets_id(path: str) -> str | None:
        prefix = "/api/v1/artifacts/"
        suffix = "/assets"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        encoded_id = path[len(prefix):-len(suffix)]
        if not encoded_id:
            return None
        return unquote(encoded_id)

    @staticmethod
    def _asset_content_id(path: str) -> str | None:
        prefix = "/api/v1/assets/"
        suffix = "/content"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        encoded_id = path[len(prefix):-len(suffix)]
        if not encoded_id:
            return None
        return unquote(encoded_id)

    def _parse_range(self, size: int) -> tuple[int, int] | None | bool:
        value = self.headers.get("Range")
        if value is None:
            return None
        match = _RANGE_RE.fullmatch(value.strip())
        if not match or size == 0:
            return False
        start_text, end_text = match.groups()
        if not start_text and not end_text:
            return False
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            suffix = int(end_text)
            if suffix <= 0:
                return False
            start = max(0, size - suffix)
            end = size - 1
        if start >= size or start > end:
            return False
        return start, min(end, size - 1)

    def _respond_json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._respond_bytes(status, data, "application/json; charset=utf-8")

    def _respond_text(self, status: int, text: str) -> None:
        self._respond_bytes(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _respond_bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _security_headers(self) -> None:
        for name, value in _SECURITY_HEADERS.items():
            self.send_header(name, value)

    def log_message(self, *_: object) -> None:
        pass


def _asset_payload(asset: HubAsset) -> dict[str, Any]:
    payload = asset.model_dump(mode="json")
    payload["content_url"] = (
        f"/api/v1/assets/{quote(asset.asset_id, safe='')}/content"
    )
    prefix = "!" if asset.role == AssetRole.EMBED else ""
    payload["obsidian_link"] = f"{prefix}[[{asset.vault_path}]]"
    return payload


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _action_workspace_policy(action: Any) -> str:
    """Return the public workspace policy, with legacy cmux compatibility."""
    declared = getattr(action, "workspace_policy", None)
    if declared is not None:
        return _enum_value(declared)
    kind = _enum_value(getattr(action, "kind", ""))
    return "required" if "cmux" in kind.split(".") else "none"


def _require_string_fields(payload: dict[str, Any], *names: str) -> None:
    for name in names:
        value = payload.get(name)
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 1024
            or "\x00" in value
        ):
            raise ValueError(f"{name} must be a non-empty bounded string")


def _require_optional_bool(payload: dict[str, Any], name: str) -> None:
    if name in payload and not isinstance(payload[name], bool):
        raise ValueError(f"{name} must be a boolean")


def _find_public_action(service: Any, action_id: str) -> Any | None:
    """Resolve only public action metadata; trusted targets remain service-private."""
    for actions in service.public_actions().values():
        for action in actions:
            if getattr(action, "id", None) == action_id:
                return action
    return None


def _public_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _workspace_listing_payload(
    service: Any | None,
    *,
    instance_token: str | None = None,
) -> dict[str, Any]:
    """Serialize the workspace registry through a strict public-field allowlist."""
    unavailable = {
        "capabilities": {"workspace_actions": False},
        "workspaces": [],
        "capability_error": "cmux workspace control is unavailable",
    }
    if service is None or not callable(getattr(service, "public_workspaces", None)):
        return unavailable
    try:
        if instance_token is None:
            listing = service.public_workspaces()
        else:
            listing = service.public_workspaces(instance_token=instance_token)
    except Exception:  # noqa: BLE001 - compatibility boundary for injected services
        return {
            **unavailable,
            "capability_error": "cmux workspace discovery failed",
        }
    error = _public_field(listing, "capability_error")
    if error is not None:
        error = str(error)
    workspaces = []
    for workspace in _public_field(listing, "workspaces", ()) or ():
        workspace_id = _public_field(workspace, "id")
        label = _public_field(workspace, "label")
        if not isinstance(workspace_id, str) or not workspace_id:
            continue
        workspaces.append(
            {
                "id": workspace_id,
                "label": str(label or "cmux workspace"),
                "is_current": bool(_public_field(workspace, "is_current", False)),
                "contains_hub": bool(_public_field(workspace, "contains_hub", False)),
            }
        )
    return {
        "capabilities": {"workspace_actions": error is None},
        "workspaces": workspaces,
        "capability_error": error,
    }


def start_hub_server(
    *,
    port: int = 23128,
    storage_root: Path,
    vault_root: Path,
    catalog_provider: CatalogProvider | None = None,
    knowledge_provider_state_root: Path | None = None,
    action_executor: Any | None = None,
    public_actions: dict[str, list[PublicAction]] | None = None,
    action_service: Any | None = None,
    codex_working_directory: Path | None = None,
    directory_service: HubDirectoryService | None = None,
    project_document_service: ProjectDocumentService | None = None,
    binding_registry: WorkspaceBindingRegistry | None = None,
    binding_coordinator: WorkspaceBindingCoordinator | None = None,
    service_generation: str | None = None,
    owner_mode: str = "headless",
    require_workspace_binding: bool = True,
    log_path: Path | None = None,
) -> HubHTTPServer:
    """Start the local Hub on loopback and return its server object."""
    if owner_mode not in {"headless", "cmux-visible"}:
        raise ValueError("owner_mode must be headless or cmux-visible")
    if catalog_provider is not None and knowledge_provider_state_root is not None:
        raise ValueError(
            "catalog_provider and knowledge_provider_state_root are mutually exclusive"
        )
    home = Path(
        os.environ.get(
            "SCHOLAR_WORKFLOW_HOME",
            Path.home() / ".config" / "scholar-workflow",
        )
    )
    asset_manifest = VaultAssetManifestStore(vault_root)
    use_live_zotero_paging = catalog_provider is None
    resolved_catalog_path: Path | None = None
    if catalog_provider is None:
        provider_state_root = (
            Path(knowledge_provider_state_root)
            if knowledge_provider_state_root is not None
            else home / "knowledge-provider"
        )
        provider_snapshot = provider_state_root / "knowledge-provider.snapshot.json"
        if provider_snapshot.is_file():
            from scholar_workflow.analysis.apply_changes import (
                KnowledgeSnapshotCatalogProvider,
            )

            provider = KnowledgeSnapshotCatalogProvider(provider_state_root)
            provider.load()
            resolved_catalog_path = provider_snapshot
        elif knowledge_provider_state_root is not None:
            raise ValueError(
                "explicit Knowledge provider state root has no provider snapshot"
            )
        else:
            resolved_catalog_path = home / "hub" / "catalog.json"
            provider = LinkedCatalogProvider(
                VaultAssetCatalogProvider(
                    VaultArtifactManifestProvider(
                        VaultCatalogProvider(
                            CatalogSnapshotStore(resolved_catalog_path),
                            vault_root,
                        ),
                        vault_root,
                    ),
                    asset_manifest,
                ),
                ProjectionLinkStore(home / "hub" / "projection-links.json"),
            )
    else:
        provider = catalog_provider
    project_registry = ProjectRegistry(home / "hub" / "projects.json")
    tool_registry = ToolRegistry(home / "hub" / "tools.json")
    resolved_directory_service = directory_service or HubDirectoryService(
        provider,
        project_registry,
        tool_registry,
        paper_provider=ZoteroPaperLibraryProvider() if use_live_zotero_paging else None,
    )
    resolved_project_documents = project_document_service or ProjectDocumentService(
        project_registry
    )
    if binding_coordinator is not None:
        if binding_registry is not None and binding_coordinator.registry is not binding_registry:
            raise ValueError("binding_coordinator and binding_registry must share state")
        binding_registry = binding_coordinator.registry
    if binding_registry is None:
        resolved_generation = service_generation or f"service_{secrets.token_urlsafe(18)}"
        resolved_bindings = WorkspaceBindingRegistry(
            service_generation=resolved_generation,
            profiles=[
                WorkspaceProfile(profile_id="hub", role="hub"),
                WorkspaceProfile(profile_id="runtime", role="runtime"),
                WorkspaceProfile(profile_id="notion", role="notion"),
            ],
        )
    else:
        resolved_bindings = binding_registry
        resolved_generation = binding_registry.service_generation
        if service_generation is not None and service_generation != resolved_generation:
            raise ValueError("service_generation does not match binding_registry")
    if action_service is not None and (
        action_executor is not None or public_actions is not None
    ):
        raise ValueError(
            "action_service cannot be combined with action_executor or public_actions"
        )
    configure_default_actions = (
        action_service is None
        and action_executor is None
        and public_actions is None
    )
    if action_service is not None:
        resolved_action_service = action_service
    elif configure_default_actions:
        resolved_action_service = None
    else:
        resolved_action_service = _StaticActionService(action_executor, public_actions)
    runtime = HubRuntime(
        storage_root=Path(storage_root),
        vault_root=Path(vault_root),
        catalog_provider=provider,
        session_token=secrets.token_urlsafe(32),
        content_store=ArtifactContentStore(vault_root, provider),
        asset_store=VaultAssetStore(
            vault_root,
            provider,
            manifest_store=asset_manifest,
        ),
        action_service=resolved_action_service,
        directory_service=resolved_directory_service,
        project_document_service=resolved_project_documents,
        binding_registry=resolved_bindings,
        binding_coordinator=binding_coordinator,
        service_generation=resolved_generation,
        owner_mode=owner_mode,
        require_workspace_binding=require_workspace_binding,
        log_path=log_path,
        state_root=home,
        catalog_path=resolved_catalog_path,
    )
    server = HubHTTPServer(("127.0.0.1", port), runtime)
    if configure_default_actions:
        actual_port = server.server_address[1]
        hub_origin = f"http://127.0.0.1:{actual_port}"
        control = CmuxControl()
        workspaces = WorkspaceRegistry(
            control,
            hub_url=f"{hub_origin}/hub/",
        )
        launchers: dict[ActionKind, Any] = {
            ActionKind.RESOURCE_CMUX: CmuxResourceLauncher(
                workspaces,
                control=control,
                hub_origin=hub_origin,
            ),
            ActionKind.ARTIFACT_CMUX: CmuxArtifactLauncher(
                vault_root,
                workspaces,
                control=control,
            ),
            ActionKind.NOTION_CMUX: CmuxLauncher(
                control=control,
                workspace_registry=workspaces,
            ),
            ActionKind.OBSIDIAN_NOTE: ObsidianLauncher(vault_root),
            ActionKind.ZOTERO_ITEM: ZoteroLauncher(),
        }
        # TaskRecipe/TaskRun contracts exist, but a secure long-lived Codex
        # worker is not enabled yet.  Do not expose the legacy blank-session
        # action as if Hub v2 task execution were available.
        resolved_action_service = CatalogActionService(
            provider,
            launchers,
            workspace_registry=workspaces,
        )
        server.runtime = replace(
            runtime,
            action_service=resolved_action_service,
            binding_coordinator=binding_coordinator
            or WorkspaceBindingCoordinator(
                resolved_bindings,
                resolve_workspace=workspaces.resolve,
                instance_fingerprint=workspaces.instance_fingerprint,
            ),
        )
    threading.Thread(target=server.serve_forever, daemon=True, name="scholar-hub").start()
    return server


__all__ = ["CatalogSnapshotStore", "StaticCatalogProvider", "start_hub_server"]
