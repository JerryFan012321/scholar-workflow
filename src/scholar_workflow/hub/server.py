"""Loopback-only HTTP server for the Scholar Workflow research Hub."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import stat
import sys
import threading
from dataclasses import asdict, dataclass, replace
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from pydantic import ValidationError

from scholar_workflow import __version__
from scholar_workflow.adapters.obsidian import VaultPathError, safe_vault_path
from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter, ZoteroLocalError
from scholar_workflow.hub.actions import (
    ActionKind,
    CatalogActionService,
    CmuxArtifactLauncher,
    CmuxLauncher,
    CmuxResourceLauncher,
    InvalidActionTarget,
    ObsidianLauncher,
    PublicAction,
    SystemPdfLauncher,
    UnknownActionError,
    ZoteroLauncher,
    ZoteroPdfLauncher,
    ZotFlowLauncher,
)
from scholar_workflow.hub.artifact_manifest import VaultArtifactManifestProvider
from scholar_workflow.hub.assets import (
    AssetIntegrityError,
    AssetManifestError,
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
    ArtifactContentStore,
    ArtifactEncodingError,
    ArtifactMissingError,
    ArtifactPathRejectedError,
    ArtifactTooLargeError,
    UnknownArtifactError,
    UnsupportedArtifactError,
)
from scholar_workflow.hub.destinations import DestinationRegistry
from scholar_workflow.hub.directory import (
    CapabilityMatrix,
    CapabilityStatus,
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
from scholar_workflow.hub.field_migration import (
    FieldMigrationError,
    FieldMigrationService,
    _has_legacy_hub_reference,
)
from scholar_workflow.hub.field_transaction import (
    FieldTransactionError,
    FieldTransactionService,
    _has_analysis_identity,
    _open_private_directory,
    _read_target,
)
from scholar_workflow.knowledge.fields import (
    FieldCandidateExpired,
    FieldCandidateStore,
    FieldDefinition,
    FieldManifest,
    FieldRegistryCommitUncertain,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    SystemFolderPicker,
)
from scholar_workflow.hub.links import LinkedCatalogProvider, ProjectionLinkStore
from scholar_workflow.knowledge.catalog_models import AssetRole, HubAsset
from scholar_workflow.hub.project_docs import (
    DocumentCollisionError,
    ProjectConfirmationRequired,
    ProjectDocumentError,
    ProjectDocumentMissingError,
    ProjectDocumentService,
    ProjectPathError,
)
from scholar_workflow.hub.routing import TaskActionRequest
from scholar_workflow.hub.vault import VaultCatalogProvider
from scholar_workflow.hub.workspaces import (
    WorkspaceBindingCoordinator,
    WorkspaceBindingRegistry,
)
from scholar_workflow.hub.zotflow import RegisteredSourceZotFlowAdapter

_KEY_RE = re.compile(r"^[A-Z0-9]+$")
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_HUB_INSTANCE_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_DESTINATION_CAPABILITY = "cmux-destinations-v1"
_V3_CAPABILITIES = (
    "hub-directory-v3",
    "typed-provider-pagination-v2",
    "dynamic-fields-v1",
    "field-transaction-plan-v1",
    "direct-paper-actions-v1",
    "paper-related-documents-v1",
    "codex-guided-setup-v1",
    _DESTINATION_CAPABILITY,
    "trusted-execution-targets-v1",
)
_MAX_V2_WRITE_BYTES = 2 * 1024 * 1024 + 16 * 1024
_MAX_TASK_REQUEST_BYTES = 12 * 1024
_MAX_LEGACY_PROPOSAL_REQUEST_BYTES = 8 * 1024 * 1024
_FIELD_REVIEW_TTL_SECONDS = 30 * 60
OPERATOR_CREDENTIAL_NAME = "field-operator.json"
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
    destination_registry: DestinationRegistry | None = None
    field_service: FieldService | None = None
    field_transaction_service: FieldTransactionService | None = None
    operator_token: str | None = None
    operator_credential_path: Path | None = None
    folder_picker: SystemFolderPicker | None = None
    task_service: Any | None = None
    paper_related_service: Any | None = None
    codex_setup_service: Any | None = None
    execution_folder_setup: Any | None = None
    task_service_factory: Any | None = None
    zotero_adapter_factory: Any = ZoteroLocalAdapter
    binding_registry: WorkspaceBindingRegistry | None = None
    binding_coordinator: WorkspaceBindingCoordinator | None = None
    service_generation: str = "unknown-generation"
    owner_mode: str = "headless"
    require_workspace_binding: bool = True
    log_path: Path | None = None
    state_root: Path | None = None
    catalog_path: Path | None = None
    process_executable: str = ""


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
        self.task_configuration_lock = threading.RLock()
        super().__init__(address, HubRequestHandler)

    def server_close(self) -> None:
        try:
            path = self.runtime.operator_credential_path
            token = self.runtime.operator_token
            if path is not None and token is not None:
                _remove_operator_credential(path, self.runtime.service_generation, token)
        finally:
            super().server_close()


def _operator_record_bytes(generation: str, token: str) -> bytes:
    return json.dumps(
        {"service_generation": generation, "pid": os.getpid(), "token": token},
        sort_keys=True,
    ).encode("utf-8")


def _private_operator_directory(path: Path) -> int:
    descriptor = _open_private_directory(path)
    metadata = os.fstat(descriptor)
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        os.close(descriptor)
        raise ValueError("Hub operator credential parent is not private")
    return descriptor


def _write_operator_credential(path: Path, generation: str, token: str) -> None:
    """Publish a generation-bound operator secret, never returned to browsers."""
    parent_fd = _private_operator_directory(path.parent)
    temporary = f".{OPERATOR_CREDENTIAL_NAME}.{secrets.token_hex(16)}.tmp"
    try:
        try:
            existing = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (
            not stat.S_ISREG(existing.st_mode)
            or existing.st_uid != os.geteuid()
            or stat.S_IMODE(existing.st_mode) != 0o600
            or existing.st_nlink != 1
        ):
            raise ValueError("Hub operator credential target is unsafe")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(_operator_record_bytes(generation, token))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _remove_operator_credential(path: Path, generation: str, token: str) -> None:
    try:
        parent_fd = _private_operator_directory(path.parent)
    except (FileNotFoundError, OSError, ValueError):
        return
    try:
        try:
            descriptor = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except (FileNotFoundError, OSError):
            return
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > 1024
                or handle.read(1025) != _operator_record_bytes(generation, token)
            ):
                return
        try:
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            return
        os.unlink(path.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


class HubRequestHandler(BaseHTTPRequestHandler):
    server: HubHTTPServer

    def do_OPTIONS(self) -> None:
        self._respond_text(405, "Method not allowed")

    def do_HEAD(self) -> None:
        if not self._request_origin_allowed():
            return
        path = urlparse(self.path).path
        if path.startswith("/api/v3/pdfs/zotero/") and path.endswith("/content"):
            self._handle_v3_pdf(path, send_body=False)
            return
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
        elif path == "/api/v3/directory":
            self._handle_v3_directory()
        elif path.startswith("/api/v3/libraries/") and path.endswith("/items"):
            self._handle_v3_library(path, parsed.query)
        elif path.startswith("/api/v3/fields/") and path.endswith("/documents"):
            self._handle_v3_field_read(path, parsed.query)
        elif path.startswith("/api/v3/papers/") and path.endswith("/related"):
            self._handle_v3_paper_related(path)
        elif path.startswith("/api/v3/paper-documents/") and path.endswith("/content"):
            self._handle_v3_paper_document(path)
        elif path == "/api/v3/destinations":
            self._handle_v3_destinations(parsed.query)
        elif path == "/api/v3/execution-targets":
            service = self.server.runtime.task_service
            setup = self.server.runtime.codex_setup_service
            targets = (service.public_targets() if service is not None else
                       setup.public_targets() if setup is not None else [])
            self._respond_json(200, {"targets": [_model_payload(row) for row in targets]})
        elif path == "/api/v3/task-options":
            setup = self.server.runtime.codex_setup_service
            payload = setup.public_options() if setup is not None else {
                "available": False, "model_profiles": [], "default_profile_id": None,
                "reason": "Codex setup is unavailable",
            }
            self._respond_json(200, payload)
        elif path == "/api/v3/codex/setup":
            self._handle_v3_codex_setup(confirm=False)
        elif path == "/api/v3/task-actions":
            service = self.server.runtime.task_service
            actions = service.public_actions() if service is not None else []
            self._respond_json(200, {"actions": [_model_payload(row) for row in actions]})
        elif path.startswith("/api/v3/tasks/"):
            self._handle_v3_task_status(path)
        elif path.startswith("/api/v3/task-runs/"):
            self._handle_v3_task_run_status(path)
        elif path == "/api/v3/identity":
            self._respond_json(200, self._v3_identity_payload())
        elif path == "/api/v3/health":
            self._respond_json(200, self._v3_health_payload())
        elif path == "/api/v2/directory":
            self._handle_v2_directory(parsed.query)
        elif path == "/api/v2/workspaces/status":
            self._handle_v2_workspace_status(parsed.query)
        elif path.startswith("/api/v2/libraries/") and path.endswith("/items"):
            self._handle_v2_library(path, parsed.query)
        elif path == "/api/v2/health":
            self._respond_json(200, self._v2_health_payload())
        elif path == "/api/v3/actions":
            self._respond_json(200, self._public_actions_payload())
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
            payload = self._v3_health_payload()
            payload["compatibility"] = {
                "endpoint": "/api/v1/health",
                "derived_from": "HubDirectory v3",
            }
            self._respond_json(200, payload)
        elif path.startswith("/api/v1/artifacts/") and path.endswith("/content"):
            encoded_id = path[len("/api/v1/artifacts/"):-len("/content")]
            self._handle_artifact_content(unquote(encoded_id))
        elif (artifact_id := self._artifact_assets_id(path)) is not None:
            self._handle_artifact_assets(artifact_id)
        elif (asset_id := self._asset_content_id(path)) is not None:
            self._handle_asset_content(asset_id, send_body=True)
        elif path.startswith("/api/v3/pdfs/zotero/") and path.endswith("/content"):
            self._handle_v3_pdf(path, send_body=True)
        elif path == "/open/paper" or path.startswith("/open/paper/"):
            self._handle_pdf(path, send_body=True)
        else:
            self._respond_text(404, "Not found")

    def do_PUT(self) -> None:
        if not self._request_origin_allowed(require_origin=True):
            return
        path = urlparse(self.path).path
        if path.startswith("/api/v3/fields/") and path.endswith("/documents"):
            self._handle_v3_field_write(path)
            return
        if self._artifact_content_id(path) is None:
            self._respond_text(404, "Not found")
            return
        if not self._require_session_token():
            return
        self._respond_json(
            410,
            {
                "ok": False,
                "code": "v1_read_only_compatibility",
                "error": (
                    "Hub v1 artifact content is read-only compatibility; "
                    "use the Field v3 document or paired analysis workflow"
                ),
            },
        )

    def _handle_v3_field_read(self, path: str, query: str) -> None:
        segments = path.strip("/").split("/")
        if (
            len(segments) != 5
            or segments[:3] != ["api", "v3", "fields"]
            or segments[4] != "documents"
        ):
            self._respond_text(404, "Not found")
            return
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) != {"relative_path"} or len(parameters["relative_path"]) != 1:
            self._respond_text(400, "Expected exactly one relative_path")
            return
        service = self.server.runtime.field_service
        if service is None:
            self._respond_text(503, "Field document reads are unavailable")
            return
        try:
            result = service.read_document(
                unquote(segments[3]),
                parameters["relative_path"][0],
            )
        except ValueError as exc:
            self._respond_text(400, str(exc))
            return
        except FieldRegistryError as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        self._respond_json(200, {"ok": True, **result})

    def _handle_v3_field_write(self, path: str) -> None:
        if not self._require_session_token():
            return
        segments = path.strip("/").split("/")
        if (
            len(segments) != 5
            or segments[:3] != ["api", "v3", "fields"]
            or segments[4] != "documents"
        ):
            self._respond_text(404, "Not found")
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if set(body) != {"relative_path", "content", "base_revision"}:
            self._respond_text(400, "Expected relative_path, content, and base_revision only")
            return
        try:
            _require_string_fields(body, "relative_path", "base_revision")
            if not isinstance(body["content"], str):
                raise TypeError("content must be text")
            service = self.server.runtime.field_service
            if service is None:
                raise FieldRegistryError("Field document writes are unavailable")
            result = service.write_document(
                unquote(segments[3]),
                body["relative_path"],
                content=body["content"],
                base_revision=body["base_revision"],
            )
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        except FieldRegistryError as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        self._respond_json(200, {"ok": True, **result})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/api/v3/codex/setup", "/api/v3/task-options/preferences", "/api/v3/execution-targets/preview",
                    "/api/v3/execution-targets/confirm"}:
            if not self._request_origin_allowed(require_origin=True):
                return
            if path == "/api/v3/codex/setup":
                self._handle_v3_codex_setup(confirm=True)
            elif path == "/api/v3/task-options/preferences":
                self._handle_v3_task_preferences()
            else:
                self._handle_v3_execution_folder(confirm=path.endswith("/confirm"))
            return
        if path == "/api/v3/destinations/default":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_default_destination()
            return
        if path == "/api/v3/fields/select":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_field_select()
            return
        if path == "/api/v3/fields/confirm":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_field_confirm()
            return
        if path == "/api/v3/field-transactions/plan":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_field_transaction_plan()
            return
        if path == "/api/v3/field-transactions/apply":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_field_transaction_apply()
            return
        if path == "/api/v3/field-transactions/recover":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_field_transaction_recover()
            return
        if path == "/api/v3/field-transactions/legacy/preview":
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_legacy_field_proposal(stage=False)
            return
        if path == "/api/v3/field-transactions/legacy/stage":
            if not self._request_origin_allowed(require_origin=True):
                return
            if not self._require_session_token() or not self._require_operator_token():
                return
            self._respond_json(503, {
                "ok": False,
                "error": (
                    "Legacy analysis staging is unavailable until Provider and Field "
                    "changes share one recoverable transaction journal"
                ),
            })
            return
        if path.startswith("/api/v3/actions/"):
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_action(path)
            return
        if path == "/api/v3/tasks" or (
            path.startswith("/api/v3/tasks/")
            and path.endswith(("/resume", "/fork"))
        ):
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_task_dispatch(path)
            return
        if path.startswith("/api/v3/task-runs/") and path.endswith("/cancel"):
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v3_task_cancel(path)
            return
        if path.startswith("/api/v2/"):
            if not self._request_origin_allowed(require_origin=True):
                return
            self._respond_json(
                410,
                {
                    "ok": False,
                    "code": "v2_read_only_compatibility",
                    "error": (
                        "Hub v2 is a read-only compatibility projection; "
                        "use the corresponding /api/v3 endpoint"
                    ),
                },
            )
            return
        if path.startswith("/api/v3/projects/") and "/docs/" in path:
            if not self._request_origin_allowed(require_origin=True):
                return
            self._handle_v2_project_document_operation(path)
            return
        artifact_id = self._artifact_assets_id(path)
        if artifact_id is not None:
            if not self._request_origin_allowed(require_origin=True):
                return
            if not self._require_session_token():
                return
            self._respond_v1_read_only(
                "Legacy attachment uploads are retired; use a supported v3 workflow"
            )
            return
        if not self._request_origin_allowed(require_origin=True):
            return
        if not path.startswith("/api/v1/actions/"):
            self._respond_text(404, "Not found")
            return
        if not self._require_session_token():
            return
        self._respond_v1_read_only(
            "Legacy action invocation is retired; use /api/v3/actions"
        )

    def _respond_v1_read_only(self, detail: str) -> None:
        self._respond_json(
            410,
            {
                "ok": False,
                "code": "v1_read_only_compatibility",
                "error": detail,
            },
        )

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

    def _require_session_token(self) -> bool:
        supplied = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied, self.server.runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return False
        return True

    def _require_operator_token(self) -> bool:
        """A browser session is never sufficient to commit or restore a Field."""
        token = self.server.runtime.operator_token
        supplied = self.headers.get("X-Scholar-Hub-Operator", "")
        if token is None or not secrets.compare_digest(supplied, token):
            self._respond_text(403, "Local Field operator credential required")
            return False
        return True

    @staticmethod
    def _serialize_action(action: Any) -> dict[str, Any]:
        policy = _action_workspace_policy(action)
        return {
            "id": action.id,
            "label": action.label,
            "kind": _enum_value(action.kind),
            "destination_required": policy == "required",
            "available": bool(getattr(action, "available", True)),
            "reason": getattr(action, "reason", None),
            "primary": bool(getattr(action, "primary", False)),
        }

    def _public_actions_payload(self) -> dict[str, list[dict[str, Any]]]:
        service = self.server.runtime.action_service
        groups = service.public_actions() if service is not None else {}
        return {
            entity_id: [self._serialize_action(action) for action in actions]
            for entity_id, actions in groups.items()
        }

    def _handle_v3_directory(self) -> None:
        service = self.server.runtime.directory_service
        if service is None:
            self._respond_text(503, "HubDirectory is unavailable")
            return
        try:
            root = service.load()
        except (LibraryProviderUnavailable, OSError, ValueError, RegistryError):
            self._respond_text(503, "HubDirectory provider failed")
            return
        self._respond_json(200, root.model_dump(mode="json"))

    def _library_parameters(self, query: str) -> dict[str, Any] | None:
        parameters = parse_qs(query, keep_blank_values=True)
        allowed = {"cursor", "limit", "query", "sort", "direction", "type"}
        if set(parameters) - allowed:
            self._respond_text(400, "Unsupported library query field")
            return None
        if any(len(values) != 1 for values in parameters.values()):
            self._respond_text(400, "Library query fields may appear once")
            return None
        try:
            limit = int(parameters.get("limit", ["50"])[0])
        except ValueError:
            self._respond_text(400, "limit must be an integer")
            return None
        return {
            "cursor": parameters.get("cursor", [None])[0],
            "limit": limit,
            "query": parameters.get("query", [None])[0],
            "sort": parameters.get("sort", ["title"])[0],
            "direction": parameters.get("direction", ["asc"])[0],
            "item_type": parameters.get("type", [None])[0],
        }

    def _handle_v3_library(self, path: str, query: str) -> None:
        service = self.server.runtime.directory_service
        if service is None:
            self._respond_text(503, "HubDirectory is unavailable")
            return
        segments = path.strip("/").split("/")
        if len(segments) != 5 or segments[:3] != ["api", "v3", "libraries"]:
            self._respond_text(404, "Not found")
            return
        parameters = self._library_parameters(query)
        if parameters is None:
            return
        library_id = unquote(segments[3])
        try:
            page = service.list_items(library_id, **parameters)
        except UnknownLibraryError:
            self._respond_text(404, "Unknown library")
            return
        except ValueError as exc:
            self._respond_text(400, str(exc))
            return
        except (LibraryProviderUnavailable, OSError, RegistryError, FieldRegistryError):
            self._respond_text(503, "Library provider failed")
            return
        payload = page.model_dump(mode="json")
        if library_id == "papers":
            action_service = self.server.runtime.action_service
            for item in payload["items"]:
                actions = (
                    action_service.paper_actions(item)
                    if action_service is not None
                    and callable(getattr(action_service, "paper_actions", None))
                    else []
                )
                item["actions"] = [self._serialize_action(action) for action in actions]
        elif library_id == "fields" and self.server.runtime.field_service is not None:
            for item in payload["items"]:
                if not item.get("available", True):
                    continue
                try:
                    document = self.server.runtime.field_service.read_document(
                        str(item["field_id"]),
                        str(item["home"]),
                    )
                except FieldRegistryError as exc:
                    item["available"] = False
                    item["detail"] = str(exc)
                else:
                    item["home_content"] = document["content"]
                    item["home_revision"] = document["revision"]
        self._respond_json(200, payload)

    def _handle_v3_paper_related(self, path: str) -> None:
        from scholar_workflow.hub.related import PaperRelatedError

        segments = path.strip("/").split("/")
        if len(segments) != 5 or segments[:3] != ["api", "v3", "papers"]:
            self._respond_text(404, "Not found")
            return
        service = self.server.runtime.paper_related_service
        if service is None:
            self._respond_json(503, {"error": "Paper related documents are unavailable"})
            return
        try:
            payload = service.public_related(unquote(segments[3]))
            for document in payload.get("documents", []):
                document["ref"] = _model_payload(document["ref"])
                document["actions"] = [self._serialize_action(action)
                                       for action in document.get("actions", [])]
        except (PaperRelatedError, OSError, ValueError, ZoteroLocalError, FieldRegistryError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        self._respond_json(200, payload)

    def _handle_v3_paper_document(self, path: str) -> None:
        from scholar_workflow.hub.related import PaperRelatedError

        segments = path.strip("/").split("/")
        if len(segments) != 5 or segments[:3] != ["api", "v3", "paper-documents"]:
            self._respond_text(404, "Not found")
            return
        service = self.server.runtime.paper_related_service
        if service is None:
            self._respond_json(503, {"error": "Paper document preview is unavailable"})
            return
        try:
            payload = service.read_preview(unquote(segments[3]))
        except (PaperRelatedError, OSError, ValueError, FieldRegistryError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        self._respond_json(200, payload)

    def _handle_v3_codex_setup(self, *, confirm: bool) -> None:
        from scholar_workflow.hub.codex_setup import CodexSetupConfirmRequest, CodexSetupError

        service = self.server.runtime.codex_setup_service
        if service is None:
            self._respond_json(503, {"error": "Codex setup is unavailable"})
            return
        if not self._require_session_token():
            return
        try:
            if confirm:
                body = self._read_v2_json_body(maximum_bytes=64 * 1024)
                if body is None:
                    return
                request = CodexSetupConfirmRequest.model_validate(body)
                with self.server.task_configuration_lock:
                    payload = service.confirm(request)
                    factory = self.server.runtime.task_service_factory
                    if factory is not None:
                        self.server.runtime = replace(self.server.runtime, task_service=factory())
            else:
                payload = service.preview()
        except (CodexSetupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        self._respond_json(200, payload)

    def _handle_v3_task_preferences(self) -> None:
        if not self._require_session_token():
            return
        service = self.server.runtime.codex_setup_service
        if service is None:
            self._respond_json(503, {"error": "Codex model choices are unavailable"})
            return
        try:
            body = self._read_v2_json_body(maximum_bytes=4096)
            if body is None:
                return
            if set(body) != {"model_profile_id", "reasoning_effort"}:
                raise ValueError("Expected an approved model profile and reasoning effort only")
            _require_string_fields(body, "model_profile_id", "reasoning_effort")
            payload = service.save_preferences(body["model_profile_id"], body["reasoning_effort"])
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        self._respond_json(200, payload)

    def _handle_v3_execution_folder(self, *, confirm: bool) -> None:
        from scholar_workflow.hub.routing import ExecutionTargetError

        if not self._require_session_token():
            return
        service = self.server.runtime.execution_folder_setup
        if service is None:
            self._respond_json(503, {"error": "Execution folder selection is unavailable"})
            return
        try:
            body = self._read_v2_json_body(maximum_bytes=4096)
            if body is None:
                return
            if confirm:
                if set(body) != {"candidate_token"} or not isinstance(body["candidate_token"], str):
                    raise ValueError("Expected a folder candidate token only")
                payload = {"target": service.confirm(body["candidate_token"])}
            else:
                if body:
                    raise ValueError("Folder selection does not accept client paths")
                picker = self.server.runtime.folder_picker
                if picker is None:
                    raise ValueError("System folder picker is unavailable")
                selected = (picker.choose(prompt="Choose a working folder for Codex")
                            if isinstance(picker, SystemFolderPicker) else picker.choose())
                payload = {"preview": service.preview(selected)}
        except (ExecutionTargetError, FieldRegistryError, OSError, TypeError, ValueError) as exc:
            self._respond_json(409, {"error": str(exc)})
            return
        self._respond_json(200, payload)

    def _handle_v3_destinations(self, query: str) -> None:
        registry = self.server.runtime.destination_registry
        if registry is None:
            self._respond_json(
                200,
                {"destinations": [], "available": False, "reason": "cmux is unavailable"},
            )
            return
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) - {"instance"} or len(parameters.get("instance", [])) > 1:
            self._respond_text(400, "Only one instance token is accepted")
            return
        instance = parameters.get("instance", [None])[0]
        if instance is not None and not _HUB_INSTANCE_RE.fullmatch(instance):
            self._respond_text(400, "Invalid Hub instance token")
            return
        try:
            destinations = registry.list_for_instance(instance)
        except (CmuxControlError, ValueError) as exc:
            self._respond_json(
                200,
                {"destinations": [], "available": False, "reason": str(exc)},
            )
            return
        self._respond_json(
            200,
            {
                "available": True,
                "reason": None,
                "destinations": [row.model_dump(mode="json") for row in destinations],
            },
        )

    def _handle_v3_default_destination(self) -> None:
        if not self._require_session_token():
            return
        instance = self.headers.get("X-Scholar-Hub-Instance", "")
        if not _HUB_INSTANCE_RE.fullmatch(instance):
            self._respond_text(400, "Invalid Hub instance token")
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if set(body) != {"workspace_id"}:
            self._respond_text(400, "Expected workspace_id only")
            return
        try:
            _require_string_fields(body, "workspace_id")
            registry = self.server.runtime.destination_registry
            if registry is None:
                raise CmuxControlError("cmux destination routing is unavailable")
            destination = registry.register_default_from_raw(
                instance_token=instance,
                raw_workspace_id=body["workspace_id"],
            )
        except (CmuxControlError, ValueError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        self._respond_json(200, {"ok": True, **destination.model_dump(mode="json")})

    def _handle_v3_action(self, path: str) -> None:
        if not self._require_session_token():
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if set(body) - {"destination_id"}:
            self._respond_text(400, "Open actions accept destination_id only")
            return
        if "destination_id" in body:
            try:
                _require_string_fields(body, "destination_id")
            except ValueError as exc:
                self._respond_text(400, str(exc))
                return
        service = self.server.runtime.action_service
        if service is None:
            self._respond_text(503, "Actions are unavailable")
            return
        encoded_action = path.removeprefix("/api/v3/actions/")
        if encoded_action.endswith("/invoke"):
            encoded_action = encoded_action.removesuffix("/invoke")
        if not encoded_action or "/" in encoded_action:
            self._respond_text(404, "Unknown action")
            return
        action_id = unquote(encoded_action)
        action = _find_public_action(service, action_id)
        if action is None:
            self._respond_text(404, "Unknown action")
            return
        required = _action_workspace_policy(action) == "required"
        destination_id = body.get("destination_id")
        if required and destination_id is None:
            self._respond_text(400, "This action requires destination_id")
            return
        if not required and destination_id is not None:
            self._respond_text(400, "This action does not accept destination_id")
            return
        try:
            if destination_id is None:
                result = service.execute(action_id)
            else:
                destinations = self.server.runtime.destination_registry
                if destinations is None:
                    raise InvalidActionTarget("cmux destination routing is unavailable")
                workspace_id = destinations.resolve(destination_id)
                result = service.execute(action_id, workspace_id=workspace_id)
        except (KeyError, UnknownActionError):
            self._respond_text(404, "Unknown action")
            return
        except (InvalidActionTarget, CmuxControlError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - external app boundary
            self._respond_json(503, {"ok": False, "error": str(exc)})
            return
        payload = (
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else vars(result) if hasattr(result, "__dict__") else result
        )
        self._respond_json(200, payload)

    def _handle_v3_field_select(self) -> None:
        if not self._require_session_token():
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if body:
            self._respond_text(400, "Folder selection accepts no browser path")
            return
        service = self.server.runtime.field_service
        picker = self.server.runtime.folder_picker
        if service is None or picker is None:
            self._respond_text(503, "Field initialization is unavailable")
            return
        try:
            preview = service.preview(picker.choose())
        except FieldRegistryError as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        payload = preview.model_dump(mode="json")
        payload["transaction_required_fields"] = [
            {"field_id": field.field_id, "reasons": self._field_transaction_reasons(
                service, preview.candidate_token, field.field_id
            )}
            for field in preview.fields
        ]
        self._respond_json(200, {"ok": True, "preview": payload})

    @staticmethod
    def _field_transaction_reasons(
        service: FieldService, candidate_token: str, field_id: str
    ) -> list[str]:
        """Inspect only the selected Field before allowing legacy two-step confirm."""
        try:
            candidate = service.candidates.peek(candidate_token)
            selected = next(
                (row for row in candidate.preview.fields if row.field_id == field_id),
                None,
            )
            if selected is None:
                raise FieldRegistryError("Selected Field is absent from this preview")
            root = service._validate_candidate(candidate)
            manifest = FieldManifest(
                source_id=candidate.preview.source_id,
                fields=[*candidate.preview.registered_fields, selected],
            )
            inventory, _digest, conflicts = FieldMigrationService._inventory(
                root, manifest, selected
            )
            reasons: set[str] = set()
            if conflicts:
                reasons.add("inspection_conflict")
            for relative in inventory:
                name = PurePosixPath(relative).name
                if name.endswith(("分析.md", "解析树.canvas")):
                    reasons.add("legacy_analysis")
                if name.casefold().endswith(".analysis.json"):
                    reasons.add("managed_analysis")
                old = _read_target(root, relative)
                if old is not None and b"sw-analysis-field" in old[0]:
                    reasons.add("legacy_analysis")
                elif old is not None and _has_analysis_identity(old[0]):
                    reasons.add("managed_analysis")
                if old is not None and _has_legacy_hub_reference(old[0], relative):
                    reasons.add("legacy_hub_link")
            return sorted(reasons)
        except (FieldRegistryError, FieldMigrationError, FieldTransactionError, OSError):
            return ["inspection_failed"]

    def _handle_v3_field_confirm(self) -> None:
        if not self._require_session_token():
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        field_registration = set(body) == {"candidate_token", "field_id"}
        source_registration = set(body) == {"candidate_token", "source_id"}
        if not field_registration and not source_registration:
            self._respond_text(400, "Expected candidate_token and one Field or Source ID")
            return
        try:
            _require_string_fields(
                body,
                "candidate_token",
                "field_id" if field_registration else "source_id",
            )
            service = self.server.runtime.field_service
            if service is None:
                raise FieldRegistryError("Field initialization is unavailable")
            if field_registration:
                reasons = self._field_transaction_reasons(
                    service, body["candidate_token"], body["field_id"]
                )
                if reasons:
                    self._respond_json(409, {
                        "ok": False,
                        "code": "field_transaction_required",
                        "error": (
                            "Managed paper analysis or old Hub links require a validated "
                            "local-operator Field transaction; run "
                            "`scholar-workflow hub field-transaction plan` and review "
                            "the proposal before apply. No Field was registered."
                        ),
                        "reasons": reasons,
                    })
                    return
            manifest = (
                service.confirm(body["candidate_token"], body["field_id"])
                if field_registration
                else service.confirm_source(body["candidate_token"], body["source_id"])
            )
        except FieldRegistryCommitUncertain as exc:
            self._respond_json(503, {
                "ok": False,
                "code": "field_registration_commit_uncertain",
                "error": str(exc),
            })
            return
        except (FieldRegistryError, FieldCandidateExpired, ValueError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        self._respond_json(200, {"ok": True, "manifest": manifest.model_dump(mode="json")})

    def _handle_v3_field_transaction_plan(self) -> None:
        if not self._require_session_token():
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if set(body) != {"candidate_token", "field_id"}:
            self._respond_text(400, "Expected candidate_token and field_id only")
            return
        try:
            _require_string_fields(body, "candidate_token", "field_id")
            service = self.server.runtime.field_transaction_service
            if service is None:
                self._respond_text(503, "Field transactions are unavailable")
                return
            plan = service.plan(body["candidate_token"], body["field_id"])
        except (FieldTransactionError, FieldRegistryError, OSError, ValueError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        self._respond_json(200, {"ok": True, "plan": asdict(plan)})

    def _handle_v3_field_transaction_apply(self) -> None:
        if not self._require_session_token() or not self._require_operator_token():
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if set(body) != {"plan_token", "approved_digest"}:
            self._respond_text(400, "Expected plan_token and approved_digest only")
            return
        try:
            _require_string_fields(body, "plan_token", "approved_digest")
            service = self.server.runtime.field_transaction_service
            if service is None:
                self._respond_text(503, "Field transactions are unavailable")
                return
            # The separate operator credential is issued only to the local
            # installed-package CLI. Its operator must explicitly assert a
            # quiet external-writer window before this request is sent.
            result = service.apply(
                body["plan_token"],
                approved_digest=body["approved_digest"],
                external_writers_paused=True,
            )
        except (FieldTransactionError, FieldRegistryError, OSError, ValueError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        payload = asdict(result)
        payload["recovery_snapshot"] = str(result.recovery_snapshot)
        self._respond_json(200, {"ok": True, "result": payload})

    def _handle_v3_field_transaction_recover(self) -> None:
        if not self._require_session_token() or not self._require_operator_token():
            return
        try:
            body = self._read_v2_json_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        if set(body) != {"source_id", "field_id", "external_writers_paused"}:
            self._respond_text(400, "Expected source_id, field_id, and external_writers_paused")
            return
        try:
            _require_string_fields(body, "source_id", "field_id")
            if body["external_writers_paused"] is not True:
                raise FieldTransactionError("external Field writers must be paused before recovery")
            service = self.server.runtime.field_transaction_service
            if service is None:
                self._respond_text(503, "Field transactions are unavailable")
                return
            result = service.recover(
                body["source_id"], body["field_id"], external_writers_paused=True
            )
        except (FieldTransactionError, FieldRegistryError, OSError, ValueError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        payload = asdict(result)
        if result.recovery_snapshot is not None:
            payload["recovery_snapshot"] = str(result.recovery_snapshot)
        self._respond_json(200, {"ok": True, "result": payload})

    def _handle_v3_legacy_field_proposal(self, *, stage: bool) -> None:
        """Validate old bytes server-side; only the local operator may stage them."""
        if not self._require_session_token() or not self._require_operator_token():
            return
        try:
            body = self._read_strict_field_proposal_body()
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        if body is None:
            return
        expected = {"candidate_token", "field_id", "package"}
        if stage:
            expected.add("approved_cutover_digest")
        if set(body) - ({"field_definition"} if stage else set()) != expected:
            self._respond_text(400, "Unexpected Field proposal request fields")
            return
        try:
            from scholar_workflow.analysis.legacy_cutover import (
                LegacyFieldPayloadError,
                LegacyFieldProposalError,
                parse_legacy_field_proposal,
                prepare_legacy_field_payload,
                validate_legacy_cutover,
            )

            _require_string_fields(body, "candidate_token", "field_id")
            if stage:
                _require_string_fields(body, "approved_cutover_digest")
            proposal = parse_legacy_field_proposal(body["package"])
            if (
                proposal.document.schema_version != 4
                or proposal.document.profile.framework != "reference_tree"
                or proposal.document.profile.kind.value != "whole"
            ):
                raise FieldTransactionError(
                    "legacy Field cutover requires an IR v4 reference_tree whole-paper candidate"
                )
            field_service = self.server.runtime.field_service
            transaction = self.server.runtime.field_transaction_service
            if field_service is None or transaction is None:
                self._respond_text(503, "Field transactions are unavailable")
                return
            candidate = field_service.candidates.peek(body["candidate_token"])
            root = field_service._validate_candidate(candidate)
            selected = next(
                (
                    row for row in candidate.preview.fields
                    if row.field_id == body["field_id"]
                ),
                None,
            )
            if selected is None:
                raise FieldTransactionError("Field was not selected in this preview")
            prefix = () if selected.relative_root == "." else PurePosixPath(selected.relative_root).parts
            source_paths = (
                proposal.markdown_path,
                proposal.canvas_path,
                proposal.sidecar_path,
            )
            sources: list[bytes | None] = []
            for name in source_paths:
                relative = PurePosixPath(*prefix, *PurePosixPath(name).parts).as_posix()
                old = _read_target(root, relative)
                sources.append(None if old is None else old[0])
            source_markdown, source_canvas, source_sidecar = sources
            if source_markdown is None or source_canvas is None:
                raise FieldTransactionError("legacy Markdown and Canvas must already exist")
            if not stage:
                report = validate_legacy_cutover(
                    source_markdown,
                    source_canvas,
                    proposal.document,
                    proposal.bundle,
                    proposal.markdown_plan,
                    proposal.canvas_plan,
                    note_stem=proposal.note_stem,
                )
                self._respond_json(200, {
                    "ok": True,
                    "ready_for_approval": report.cutover_digest is not None,
                    "cutover_digest": report.cutover_digest,
                    "findings": [asdict(row) for row in report.findings],
                })
                return
            prepared = prepare_legacy_field_payload(
                markdown_path=proposal.markdown_path,
                canvas_path=proposal.canvas_path,
                sidecar_path=proposal.sidecar_path,
                source_markdown=source_markdown,
                source_canvas=source_canvas,
                source_sidecar=source_sidecar,
                document=proposal.document,
                bundle=proposal.bundle,
                markdown_plan=proposal.markdown_plan,
                canvas_plan=proposal.canvas_plan,
                note_stem=proposal.note_stem,
                approved_cutover_digest=body["approved_cutover_digest"],
            )
            field_definition = (
                FieldDefinition.model_validate(body["field_definition"])
                if "field_definition" in body
                else None
            )
            plan = transaction.plan(
                body["candidate_token"],
                body["field_id"],
                field_definition=field_definition,
                legacy_payloads=(prepared,),
            )
        except LegacyFieldProposalError as exc:
            self._respond_json(400, {"ok": False, "error": str(exc)})
            return
        except LegacyFieldPayloadError as exc:
            findings = (
                [] if exc.report is None
                else [asdict(row) for row in exc.report.findings]
            )
            self._respond_json(409, {"ok": False, "error": str(exc), "findings": findings})
            return
        except (FieldTransactionError, FieldRegistryError, OSError, TypeError, ValueError) as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        self._respond_json(200, {
            "ok": True,
            "plan": asdict(plan),
            "cutover_digest": prepared.cutover_digest,
            "payload_digest": prepared.payload_digest,
        })

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
            directory = service.compatibility_directory_v2()
        except (LibraryProviderUnavailable, OSError, ValueError, RegistryError):
            self._respond_text(503, "HubDirectory provider failed")
            return
        directory["operations"] = self._operation_status(instance_token).model_dump(
            mode="json"
        )
        self._respond_json(200, directory)

    def _handle_v2_workspace_status(self, query: str) -> None:
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) != {"instance"} or len(parameters["instance"]) != 1:
            self._respond_text(400, "Expected exactly one Hub instance token")
            return
        instance_token = parameters["instance"][0]
        if not _HUB_INSTANCE_RE.fullmatch(instance_token):
            self._respond_text(400, "Invalid Hub instance token")
            return
        runtime = self.server.runtime
        self._respond_json(
            200,
            {
                "bound": False,
                "service_generation": runtime.service_generation,
                "workspace_binding_available": False,
                "deprecated": True,
                "detail": (
                    "Workspace binding is retired; v3 destinations only route "
                    "cmux launch actions"
                ),
            },
        )

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
            page = service.list_compat_items(
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
        self._respond_json(200, page)

    def _v3_identity_payload(self) -> dict[str, Any]:
        """Prove process identity without consulting providers or cmux."""
        runtime = self.server.runtime
        return {
            "status": "ok",
            "service": {"name": "scholar-workflow-hub", "version": __version__},
            "build": {"version": __version__},
            "protocol": {"name": "hub-http", "version": 3},
            "service_generation": runtime.service_generation,
            "process": {
                "pid": os.getpid(),
                "executable": runtime.process_executable
                or str(Path(sys.executable).resolve()),
            },
        }

    def _v3_health_payload(self) -> dict[str, Any]:
        runtime = self.server.runtime
        try:
            package_version = version("scholar-workflow")
        except PackageNotFoundError:
            from scholar_workflow import __version__ as package_version

        root = None
        if runtime.directory_service is not None:
            try:
                root = runtime.directory_service.load()
            except (LibraryProviderUnavailable, OSError, ValueError, RegistryError):
                root = None
        provider_capabilities: dict[str, dict[str, Any]] = {}
        if root is not None:
            for descriptor in (root.libraries.papers, root.libraries.fields):
                provider_capabilities[descriptor.library_id] = {
                    "available": descriptor.available,
                    "authority": descriptor.authority,
                    "detail": descriptor.detail,
                }
            provider_capabilities["projects"] = {
                "available": not any(
                    row.code == "projects_provider_invalid" for row in root.diagnostics
                ),
                "authority": "explicit host project registry",
                "detail": "No projects are registered" if not root.projects else None,
            }
            provider_capabilities["tools"] = {
                "available": not any(
                    row.code == "tools_provider_invalid" for row in root.diagnostics
                ),
                "authority": "explicit tool registry",
                "detail": "No tools are registered" if not root.tools else None,
            }
        else:
            provider_capabilities = {
                key: {
                    "available": False,
                    "authority": "unavailable",
                    "detail": "Provider health check failed",
                }
                for key in ("papers", "fields", "projects", "tools")
            }
        cmux_fingerprint: str | None = None
        cmux_detail: str | None = "No live cmux instance is available"
        destinations = runtime.destination_registry
        if destinations is not None:
            try:
                cmux_fingerprint = destinations.workspaces.instance_fingerprint()
                cmux_detail = None
            except (CmuxControlError, ValueError):
                pass
        log_path = str(runtime.log_path) if runtime.log_path is not None else None
        task_service = runtime.task_service
        task_available = bool(getattr(task_service, "available", False))
        task_detail = (
            None
            if task_available
            else getattr(task_service, "unavailable_reason", None)
            or "Codex task runtime is not configured"
        )
        capabilities = list(_V3_CAPABILITIES)
        if task_available:
            capabilities.append("codex-tasks-v1")
        return {
            "status": "ok",
            "service": {"name": "scholar-workflow-hub", "version": package_version},
            "package": {"name": "scholar-workflow", "version": package_version},
            "build": {
                "version": package_version,
                "revision": None,
                "detail": "Installed package build is identified by discovery build_hash",
            },
            "protocol": {"name": "hub-http", "version": 3},
            "hub_directory": {"schema_version": 3},
            "service_name": "scholar-workflow-hub",
            "service_version": package_version,
            "protocol_version": 3,
            "root_schema_version": 3,
            "service_generation": runtime.service_generation,
            "owner_mode": runtime.owner_mode,
            "process": {
                "pid": os.getpid(),
                "executable": runtime.process_executable
                or str(Path(sys.executable).resolve()),
            },
            "origin": (
                f"http://{self.server.server_address[0]}:"
                f"{self.server.server_address[1]}"
            ),
            "roots": {
                "state": str(runtime.state_root) if runtime.state_root is not None else None,
                "catalog": str(runtime.catalog_path) if runtime.catalog_path else None,
            },
            "capabilities": capabilities,
            "capability_matrix": (
                root.capabilities.model_dump(mode="json")
                if root is not None
                else CapabilityMatrix().model_dump(mode="json")
            ),
            "provider_capabilities": provider_capabilities,
            "providers": {
                name: status["available"]
                for name, status in provider_capabilities.items()
            },
            "worker_capabilities": {
                "task_contracts": True,
                "task_execution": task_available,
                "detail": task_detail,
            },
            "workspace_binding_required": False,
            "workspace_binding_available": False,
            "workspace_bound": False,
            "cmux_instance_fingerprint": cmux_fingerprint,
            "cmux": {"instance_fingerprint": cmux_fingerprint, "detail": cmux_detail},
            "task_execution": task_available,
            "log_path": log_path,
            "log": {"path": log_path, "detail": None if log_path else "Unavailable"},
        }

    def _v2_health_payload(self) -> dict[str, Any]:
        payload = self._v3_health_payload()
        payload["protocol"] = {"name": "hub-http", "version": 2}
        payload["hub_directory"] = {"schema_version": 2}
        payload["protocol_version"] = 2
        payload["root_schema_version"] = 2
        payload["provider_capabilities"] = {
            key: value
            for key, value in payload["provider_capabilities"].items()
            if key in {"papers", "projects", "tools"}
        }
        payload["providers"] = {
            key: value["available"]
            for key, value in payload["provider_capabilities"].items()
        }
        payload["compatibility"] = {
            "endpoint": "/api/v2/health",
            "derived_from": "HubDirectory v3",
        }
        return payload

    def _operation_status(self, instance_token: str | None) -> OperationStatus:
        runtime = self.server.runtime
        return OperationStatus(
            bound=False,
            project_documents=runtime.project_document_service is not None,
            workspace_actions=runtime.destination_registry is not None,
            task_actions=False,
            reason="v2 binding is deprecated; v3 capabilities are independent",
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
        # One-cycle compatibility hook.  v3 authorization is rooted in the
        # registered target and CAS, never a cmux destination or lease.
        return True

    def _handle_v2_project_document_operation(self, path: str) -> None:
        runtime = self.server.runtime
        supplied_token = self.headers.get("X-Scholar-Hub-Token", "")
        if not secrets.compare_digest(supplied_token, runtime.session_token):
            self._respond_text(403, "Invalid session token")
            return
        service = runtime.project_document_service
        if service is None:
            self._respond_text(503, "Project document operations are unavailable")
            return
        segments = path.strip("/").split("/")
        if (
            len(segments) != 6
            or segments[:3]
            not in (["api", "v2", "projects"], ["api", "v3", "projects"])
            or segments[4] != "docs"
        ):
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
                try:
                    source_authorized = self._legacy_artifact_source_authorized(
                        body["artifact_id"],
                        capability="read",
                    )
                except UnknownArtifactError as exc:
                    raise ProjectDocumentMissingError(
                        "Unknown knowledge artifact"
                    ) from exc
                except (
                    ArtifactPathRejectedError,
                    ArtifactMissingError,
                    FieldRegistryError,
                ) as exc:
                    raise ProjectPathError(
                        "Knowledge artifact path was rejected"
                    ) from exc
                if not source_authorized:
                    raise ProjectPathError(
                        "Knowledge artifact is not inside a registered readable source"
                    )
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

    def _read_v2_json_body(
        self, *, maximum_bytes: int = _MAX_V2_WRITE_BYTES,
    ) -> dict[str, Any] | None:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._respond_text(415, "Expected application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length < 0:
            raise ValueError("Invalid content length")
        if length > maximum_bytes:
            self._respond_text(413, "Request body too large")
            return None
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(body, dict):
            raise TypeError("Expected a JSON object")
        return body

    def _read_strict_field_proposal_body(self) -> dict[str, Any] | None:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._respond_text(415, "Expected application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length < 0:
            raise ValueError("Invalid content length")
        if length > _MAX_LEGACY_PROPOSAL_REQUEST_BYTES:
            self._respond_text(413, "Field proposal request is too large")
            return None

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate Field proposal JSON key")
                result[key] = value
            return result

        try:
            encoded = self.rfile.read(length)
            if len(encoded) != length:
                raise ValueError("Incomplete Field proposal request")
            body = json.loads(
                encoded,
                object_pairs_hook=unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("Non-finite Field proposal number")
                ),
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid Field proposal JSON") from exc
        if not isinstance(body, dict):
            raise TypeError("Expected a Field proposal JSON object")
        return body

    def _read_task_json_body(self) -> dict[str, Any] | None:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._respond_text(415, "Expected application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length < 0:
            raise ValueError("Invalid content length")
        if length > _MAX_TASK_REQUEST_BYTES:
            self._respond_text(413, "Task request body is too large")
            return None
        try:
            encoded = self.rfile.read(length)
            if len(encoded) != length:
                raise ValueError("Incomplete task request body")
            body = json.loads(encoded)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(body, dict):
            raise TypeError("Expected a JSON object")
        return body

    def _handle_v3_task_dispatch(self, path: str) -> None:
        # A setup confirmation must not race a reservation using its previous policy snapshot.
        with self.server.task_configuration_lock:
            self._handle_v3_task_dispatch_locked(path)

    def _handle_v3_task_dispatch_locked(self, path: str) -> None:
        if not self._require_session_token():
            return
        service = self.server.runtime.task_service
        if service is None or not bool(getattr(service, "available", False)):
            reason = (
                getattr(service, "unavailable_reason", None)
                if service is not None
                else None
            )
            self._respond_json(
                503,
                {"ok": False, "error": reason or "Codex task execution is unavailable"},
            )
            return
        try:
            body = self._read_task_json_body()
            if body is None:
                return
            request = TaskActionRequest.model_validate(body)
        except ValidationError as exc:
            self._respond_json(
                422,
                {
                    "ok": False,
                    "error": "Task request does not match the public contract",
                    "details": exc.errors(include_url=False, include_input=False),
                },
            )
            return
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        try:
            if path == "/api/v3/tasks":
                result = service.create(request)
            else:
                segments = path.strip("/").split("/")
                if len(segments) != 5 or segments[:3] != ["api", "v3", "tasks"]:
                    self._respond_text(404, "Not found")
                    return
                task_id = unquote(segments[3])
                if segments[4] == "resume":
                    result = service.resume(task_id, request)
                elif segments[4] == "fork":
                    result = service.fork(task_id, request)
                else:
                    self._respond_text(404, "Not found")
                    return
        except KeyError:
            self._respond_text(404, "Unknown task, action, target, or destination")
            return
        except ValueError as exc:
            self._respond_json(409, {"ok": False, "error": str(exc)})
            return
        except RuntimeError as exc:
            self._respond_json(503, {"ok": False, "error": str(exc)})
            return
        payload = _model_payload(result)
        self._respond_json(200 if payload.get("reused") else 202, payload)

    def _handle_v3_task_status(self, path: str) -> None:
        segments = path.strip("/").split("/")
        if len(segments) != 4 or segments[:3] != ["api", "v3", "tasks"]:
            self._respond_text(404, "Not found")
            return
        service = self.server.runtime.task_service
        if service is None:
            self._respond_text(503, "Codex task execution is unavailable")
            return
        try:
            result = service.task_status(unquote(segments[3]))
        except (KeyError, ValueError):
            self._respond_text(404, "Unknown logical task")
            return
        self._respond_json(200, _model_payload(result))

    def _handle_v3_task_run_status(self, path: str) -> None:
        segments = path.strip("/").split("/")
        if len(segments) != 4 or segments[:3] != ["api", "v3", "task-runs"]:
            self._respond_text(404, "Not found")
            return
        service = self.server.runtime.task_service
        if service is None:
            self._respond_text(503, "Codex task execution is unavailable")
            return
        try:
            result = service.run_status(unquote(segments[3]))
        except (KeyError, ValueError):
            self._respond_text(404, "Unknown task run")
            return
        self._respond_json(200, _model_payload(result))

    def _handle_v3_task_cancel(self, path: str) -> None:
        if not self._require_session_token():
            return
        segments = path.strip("/").split("/")
        if (
            len(segments) != 5
            or segments[:3] != ["api", "v3", "task-runs"]
            or segments[4] != "cancel"
        ):
            self._respond_text(404, "Not found")
            return
        try:
            body = self._read_task_json_body()
            if body is None:
                return
            if body:
                raise ValueError("Task cancellation accepts no fields")
        except (TypeError, ValueError) as exc:
            self._respond_text(400, str(exc))
            return
        service = self.server.runtime.task_service
        if service is None:
            self._respond_text(503, "Codex task execution is unavailable")
            return
        try:
            result = service.cancel(unquote(segments[3]))
        except (KeyError, ValueError):
            self._respond_text(404, "Unknown task run")
            return
        self._respond_json(200, _model_payload(result))

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
        pdf = self._resolve_pdf(key)
        if pdf is None:
            self._respond_text(404, f"No PDF for attachment: {key}")
            return
        self._serve_pdf(pdf, send_body=send_body)

    def _handle_v3_pdf(self, path: str, *, send_body: bool) -> None:
        segments = path.strip("/").split("/")
        if (
            len(segments) != 6
            or segments[:4] != ["api", "v3", "pdfs", "zotero"]
            or segments[5] != "content"
        ):
            self._respond_text(404, "Not found")
            return
        key = segments[4]
        if not _KEY_RE.fullmatch(key):
            self._respond_text(400, "Invalid attachment key")
            return
        pdf = self._resolve_pdf(key)
        if pdf is None:
            self._respond_text(404, "PDF attachment is unavailable")
            return
        self._serve_pdf(pdf, send_body=send_body)

    def _serve_pdf(self, pdf: Path, *, send_body: bool) -> None:
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

    def _resolve_pdf(self, key: str) -> Path | None:
        try:
            with self.server.runtime.zotero_adapter_factory() as adapter:
                locator = adapter.resolve_attachment_locator(key)
        except (ZoteroLocalError, OSError, ValueError):
            return None
        path = Path(locator.path)
        if path.is_symlink() or not path.is_file() or path.suffix.casefold() != ".pdf":
            return None
        try:
            return path.resolve(strict=True)
        except OSError:
            return None

    def _legacy_artifact_path(self, artifact_id: str) -> Path:
        """Resolve a compatibility artifact without trusting a browser path."""
        runtime = self.server.runtime
        catalog = runtime.catalog_provider.load()
        artifact = next(
            (row for row in catalog.artifacts if row.artifact_id == artifact_id),
            None,
        )
        if artifact is None:
            raise UnknownArtifactError(artifact_id)
        relative = PurePosixPath(artifact.vault_path)
        current = runtime.vault_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactPathRejectedError(artifact.vault_path)
        try:
            target = safe_vault_path(runtime.vault_root.resolve(strict=True), artifact.vault_path)
            resolved = target.resolve(strict=True)
        except VaultPathError as exc:
            raise ArtifactPathRejectedError(artifact.vault_path) from exc
        except OSError as exc:
            raise ArtifactMissingError(artifact_id) from exc
        if not resolved.is_file():
            raise ArtifactMissingError(artifact_id)
        return resolved

    def _legacy_artifact_source_authorized(
        self,
        artifact_id: str,
        *,
        capability: str,
    ) -> bool:
        """Authorize legacy artifact access only through an explicit Source root.

        The legacy catalog remains a one-cycle compatibility projection. It may
        identify a file, but it no longer grants write/read-copy authority by
        itself. A registered folder containing the resolved artifact must grant
        the requested capability.
        """
        target = self._legacy_artifact_path(artifact_id)
        service = self.server.runtime.field_service
        if service is None:
            return False
        document = service.registry.load_document()
        for source in document.sources:
            if not source.enabled or capability not in source.capabilities:
                continue
            try:
                root = service.registry.resolve(
                    source.source_id,
                    capability=capability,
                )
            except FieldRegistryError:
                continue
            if target == root or root in target.parents:
                return True
        return False

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


def _model_payload(value: Any) -> Any:
    """Serialize public task DTOs without accepting arbitrary object internals."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _model_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_model_payload(item) for item in value]
    return value


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
    port: int = 0,
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
    field_service: FieldService | None = None,
    field_transaction_service: FieldTransactionService | None = None,
    destination_registry: DestinationRegistry | None = None,
    folder_picker: SystemFolderPicker | None = None,
    task_service: Any | None = None,
    paper_related_service: Any | None = None,
    codex_setup_service: Any | None = None,
    cmux_control: CmuxControl | None = None,
    zotero_adapter_factory: Any = ZoteroLocalAdapter,
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
    resolved_field_service = field_service or FieldService(
        KnowledgeSourceRegistry(home / "hub" / "sources.json"),
        candidates=FieldCandidateStore(ttl_seconds=_FIELD_REVIEW_TTL_SECONDS),
    )
    resolved_transaction_service = field_transaction_service or FieldTransactionService(
        resolved_field_service,
        state_root=home / "runtime" / "field-transactions-private",
        ttl_seconds=_FIELD_REVIEW_TTL_SECONDS,
    )
    if resolved_transaction_service.field_service is not resolved_field_service:
        raise ValueError("Field transaction and Field services must share one candidate store")
    zotflow_adapter = RegisteredSourceZotFlowAdapter(resolved_field_service.registry)
    from scholar_workflow.hub.codex_setup import CodexSetupService
    from scholar_workflow.hub.routing import ExecutionTargetRegistry
    from scholar_workflow.hub.target_setup import ExecutionFolderSetup

    execution_targets = ExecutionTargetRegistry(
        home / "hub" / "execution-targets.json",
        project_registry=project_registry,
        source_registry=resolved_field_service.registry,
    )
    resolved_codex_setup = codex_setup_service or CodexSetupService(
        home / "hub", project_registry=project_registry,
        source_registry=resolved_field_service.registry,
        target_registry=execution_targets,
    )
    resolved_folder_setup = ExecutionFolderSetup(
        resolved_field_service.registry, execution_targets,
    )
    destination_holder: dict[str, DestinationRegistry | None] = {
        "registry": destination_registry
    }
    task_holder: dict[str, Any | None] = {"service": task_service}

    def current_capabilities() -> CapabilityMatrix:
        vault_available = False
        vault_reason = "No writable knowledge source is registered"
        try:
            source_document = resolved_field_service.registry.load_document()
            for source in source_document.sources:
                if not source.enabled or "write" not in source.capabilities:
                    continue
                resolved_field_service.registry.resolve(source.source_id, capability="write")
                vault_available = True
                vault_reason = None
                break
        except FieldRegistryError as exc:
            vault_reason = str(exc)

        project_available = False
        project_reason = "No writable project docs root is registered"
        try:
            for registration in project_registry.load():
                if not registration.enabled or not {
                    "docs", "docs.write", "project_documents"
                }.intersection(registration.capabilities):
                    continue
                project_registry.resolve(registration.project_id)
                project_available = True
                project_reason = None
                break
        except (RegistryError, OSError, ValueError) as exc:
            project_reason = str(exc)

        cmux_available = False
        cmux_reason = "No live cmux instance is available"
        active_destinations = destination_holder["registry"]
        if active_destinations is not None:
            try:
                active_destinations.workspaces.instance_fingerprint()
                cmux_available = True
                cmux_reason = None
            except (CmuxControlError, ValueError) as exc:
                cmux_reason = str(exc)

        zotflow = zotflow_adapter.probe()
        zotero_available = False
        zotero_reason = "Zotero Local API is unavailable"
        try:
            with zotero_adapter_factory() as adapter:
                adapter.probe()
            zotero_available = True
            zotero_reason = None
        except ZoteroLocalError as exc:
            zotero_reason = str(exc)
        active_task_service = task_holder["service"]
        task_available = bool(getattr(active_task_service, "available", False))
        task_reason = (
            None
            if task_available
            else getattr(active_task_service, "unavailable_reason", None)
            or "Run `scholar-workflow hub codex configure` to enable Codex tasks"
        )
        return CapabilityMatrix(
            vault_writes=CapabilityStatus(
                available=vault_available,
                reason=vault_reason,
            ),
            project_document_writes=CapabilityStatus(
                available=project_available,
                reason=project_reason,
            ),
            cmux_launches=CapabilityStatus(
                available=cmux_available,
                reason=cmux_reason,
            ),
            codex_tasks=CapabilityStatus(
                available=task_available,
                reason=task_reason,
            ),
            zotflow_annotations=CapabilityStatus(
                available=zotflow.available,
                reason=zotflow.reason,
            ),
            zotero_local_api=CapabilityStatus(
                available=zotero_available,
                reason=zotero_reason,
            ),
        )

    resolved_directory_service = directory_service or HubDirectoryService(
        provider,
        project_registry,
        tool_registry,
        paper_provider=(
            ZoteroPaperLibraryProvider(adapter_factory=zotero_adapter_factory)
            if use_live_zotero_paging
            else None
        ),
        field_service=resolved_field_service,
        capability_status=current_capabilities,
    )
    resolved_project_documents = project_document_service or ProjectDocumentService(
        project_registry
    )
    if binding_coordinator is not None:
        if binding_registry is not None and binding_coordinator.registry is not binding_registry:
            raise ValueError("binding_coordinator and binding_registry must share state")
        binding_registry = binding_coordinator.registry
    if binding_registry is not None:
        resolved_bindings = binding_registry
        resolved_generation = binding_registry.service_generation
        if service_generation is not None and service_generation != resolved_generation:
            raise ValueError("service_generation does not match binding_registry")
    else:
        resolved_bindings = None
        resolved_generation = service_generation or f"service_{secrets.token_urlsafe(18)}"
    operator_path = (
        Path(log_path).parent / OPERATOR_CREDENTIAL_NAME
        if log_path is not None and service_generation is not None
        else None
    )
    operator_token = secrets.token_urlsafe(48) if operator_path is not None else None
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
        destination_registry=destination_registry,
        field_service=resolved_field_service,
        field_transaction_service=resolved_transaction_service,
        operator_token=operator_token,
        operator_credential_path=operator_path,
        folder_picker=folder_picker or SystemFolderPicker(),
        task_service=task_service,
        paper_related_service=paper_related_service,
        codex_setup_service=resolved_codex_setup,
        execution_folder_setup=resolved_folder_setup,
        zotero_adapter_factory=zotero_adapter_factory,
        binding_registry=resolved_bindings,
        binding_coordinator=binding_coordinator,
        service_generation=resolved_generation,
        owner_mode=owner_mode,
        require_workspace_binding=require_workspace_binding,
        log_path=log_path,
        state_root=home,
        catalog_path=resolved_catalog_path,
        process_executable=str(Path(sys.executable).resolve()),
    )
    server = HubHTTPServer(("127.0.0.1", port), runtime)
    if configure_default_actions:
        actual_port = server.server_address[1]
        hub_origin = f"http://127.0.0.1:{actual_port}"
        control = cmux_control or CmuxControl()
        workspaces = WorkspaceRegistry(
            control,
            hub_url=f"{hub_origin}/hub/",
        )
        resolved_destinations = destination_registry or DestinationRegistry(workspaces)
        destination_holder["registry"] = resolved_destinations
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
            ActionKind.ZOTERO_PDF: ZoteroPdfLauncher(),
            ActionKind.ZOTFLOW_ATTACHMENT: ZotFlowLauncher(zotflow_adapter),
            ActionKind.SYSTEM_PDF: SystemPdfLauncher(
                adapter_factory=zotero_adapter_factory
            ),
        }
        resolved_action_service = CatalogActionService(
            provider,
            launchers,
            workspace_registry=workspaces,
        )
        from scholar_workflow.hub.related import PaperRelatedService

        related_service = paper_related_service or PaperRelatedService(
            provider, resolved_action_service, vault_root,
            source_registry=resolved_field_service.registry,
            adapter_factory=zotero_adapter_factory, zotflow_adapter=zotflow_adapter,
        )

        def context_exists(ref: Any) -> bool:
            try:
                if ref.provider_id == "zotero":
                    with zotero_adapter_factory() as adapter:
                        item = adapter.get_item(ref.entity_id)
                    if not isinstance(item, dict):
                        return False
                    data = item.get("data", {})
                    if (not isinstance(data, dict) or item.get("deleted") or data.get("deleted")
                            or item.get("key") != ref.entity_id):
                        return False
                    item_type = data.get("itemType")
                    if ref.entity_type in {"attachment", "note", "annotation"}:
                        return item_type == ref.entity_type
                    return (ref.entity_type == "paper" and bool(item_type)
                            and item_type not in {"attachment", "note", "annotation"})
                if ref.provider_id == "field-manifest":
                    return ref.entity_type == "field" and any(row.get("field_id") == ref.entity_id and row.get("available")
                               for row in resolved_field_service.list_fields())
                if ref.provider_id == "project-registry":
                    if ref.entity_type != "project":
                        return False
                    project_registry.resolve(ref.entity_id)
                    return True
                if ref.provider_id == "tool-registry":
                    return ref.entity_type == "tool" and any(row.tool_id == ref.entity_id and row.enabled
                               for row in tool_registry.load())
                return related_service.contains_ref(ref)
            except (OSError, ValueError, RuntimeError):
                return False

        def load_task_service() -> Any | None:
            if task_service is not None:
                task_holder["service"] = task_service
                return task_service
            from scholar_workflow.hub.task_control import TaskControlService
            from scholar_workflow.hub.tasks import (
                CodexCommandBuilder,
                TaskCoordinator,
                TaskRecipeRegistry,
                TaskStore,
            )
            from scholar_workflow.hub.terminal_worker import (
                TerminalWorkerError,
                TerminalWorkerState,
            )

            hub_state = home / "hub"
            worker_state = TerminalWorkerState(hub_state / "task-worker")
            resolved_task_service = None
            if worker_state.runtime_path.exists() or worker_state.runtime_path.is_symlink():
                try:
                    worker_config = worker_state.current_runtime()
                    recipes = TaskRecipeRegistry(hub_state / "task-recipes.json")
                    targets = ExecutionTargetRegistry(
                        hub_state / "execution-targets.json",
                        project_registry=project_registry,
                        source_registry=resolved_field_service.registry,
                    )
                    store = TaskStore(hub_state / "tasks.json")
                    commands = CodexCommandBuilder(
                        codex_executable=worker_config.resolved_codex_executable(),
                        target_registry=targets,
                        safety_policies=recipes.safety_policy_map(),
                        model_profiles=recipes.model_profile_map(),
                    )
                    coordinator = TaskCoordinator(
                        recipes=recipes,
                        store=store,
                        commands=commands,
                    )
                    resolved_task_service = TaskControlService(
                        recipes=recipes,
                        targets=targets,
                        store=store,
                        coordinator=coordinator,
                        destinations=resolved_destinations,
                        cmux=control,
                        worker_state=worker_state,
                        worker_generation=worker_config.generation,
                        context_resolver=context_exists,
                    )
                except (OSError, ValueError, TerminalWorkerError):
                    resolved_task_service = None
            task_holder["service"] = resolved_task_service
            return resolved_task_service

        resolved_task_service = load_task_service()
        server.runtime = replace(
            runtime,
            action_service=resolved_action_service,
            destination_registry=resolved_destinations,
            task_service=resolved_task_service,
            paper_related_service=related_service,
            task_service_factory=load_task_service,
        )
    if operator_path is not None and operator_token is not None:
        try:
            _write_operator_credential(operator_path, resolved_generation, operator_token)
        except BaseException:
            server.server_close()
            raise
    threading.Thread(target=server.serve_forever, daemon=True, name="scholar-hub").start()
    return server


__all__ = ["CatalogSnapshotStore", "StaticCatalogProvider", "start_hub_server"]
