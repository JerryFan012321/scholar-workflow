from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scholar_workflow.adapters.zotero_local import ServerInfo, ZoteroAttachmentLocator
from scholar_workflow.hub.actions import ActionKind, PublicAction
from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.directory import (
    HubDirectoryService,
    ProjectRegistration,
    ProjectRegistry,
    ToolRegistry,
)
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.hub.models import HubCatalog, HubResource
from scholar_workflow.hub.routing import (
    ExecutionTarget,
    ExecutionTargetRegistry,
    ExecutionTargetRegistryDocument,
)
from scholar_workflow.hub.server import start_hub_server
from scholar_workflow.hub.tasks import (
    CodexCapabilities,
    TaskRecipe,
    TaskRecipeRegistry,
    TaskRecipeRegistryDocument,
    TaskSafetyPolicy,
)
from scholar_workflow.hub.terminal_worker import (
    TerminalWorkerRuntimeConfig,
    TerminalWorkerState,
)

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def _catalog() -> HubCatalog:
    return HubCatalog(
        generated_at=NOW,
        resources=[
            HubResource(
                resource_id="paper:v3",
                kind="paper",
                title="V3 Paper",
                zotero={"item_key": "PAPR2345", "attachment_key": "PDFD2345"},
            )
        ],
    )


def _request(port: int, path: str, *, method: str = "GET", data=None, headers=None):
    return urllib.request.urlopen(
        urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            method=method,
            data=data,
            headers=headers or {},
        ),
        timeout=3,
    )


class _FakeZotero:
    pdf_path: Path

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def probe(self):
        return ServerInfo(server_id="test", api_version="3", schema_version="1")

    def resolve_attachment_locator(self, key: str):
        return ZoteroAttachmentLocator(
            attachment_key=key,
            library_id="1",
            content_hash="sha256:" + "a" * 64,
            path=self.pdf_path,
            filename=self.pdf_path.name,
        )


class _Executor:
    def execute(self, action_id: str, **_kwargs):
        return {"ok": action_id == "safe-action"}


class _TaskService:
    def __init__(self):
        self.requests = []

    @property
    def available(self):
        return True

    @property
    def unavailable_reason(self):
        return None

    def public_actions(self):
        return [{
            "action_id": "task:research",
            "title": "Research",
            "allowed_efforts": ["standard"],
            "allowed_target_ids": ["target:project"],
            "available": True,
            "reason": None,
        }]

    def public_targets(self):
        return [{
            "target_id": "target:project",
            "kind": "project",
            "capabilities": ["codex"],
        }]

    def create(self, request):
        self.requests.append(("create", request))
        return {
            "task_id": "task-123",
            "run_id": "run-123",
            "state": "queued",
            "mode": "create",
            "reused": False,
            "terminal_routed": True,
        }

    def resume(self, task_id, request):
        self.requests.append(("resume", task_id, request))
        return {
            "task_id": task_id,
            "run_id": "run-124",
            "state": "queued",
            "mode": "resume",
            "reused": False,
            "terminal_routed": True,
        }

    def fork(self, task_id, request):
        self.requests.append(("fork", task_id, request))
        return {
            "task_id": "task-456",
            "run_id": "run-125",
            "state": "queued",
            "mode": "fork",
            "reused": False,
            "terminal_routed": True,
        }

    def task_status(self, task_id):
        return [{
            "task_id": task_id,
            "run_id": "run-123",
            "state": "succeeded",
            "mode": "create",
            "reused": False,
            "terminal_routed": True,
        }]

    def run_status(self, run_id):
        return {
            "task_id": "task-123",
            "run_id": run_id,
            "state": "running",
            "mode": "create",
            "reused": False,
            "terminal_routed": True,
        }

    def cancel(self, run_id):
        return {
            "task_id": "task-123",
            "run_id": run_id,
            "state": "cancelled",
            "mode": "create",
            "reused": False,
            "terminal_routed": True,
        }


def test_v3_directory_has_only_document_libraries_and_v2_is_projection(tmp_path: Path):
    provider = StaticCatalogProvider(_catalog())
    service = HubDirectoryService(
        provider,
        ProjectRegistry(tmp_path / "projects.json"),
        ToolRegistry(tmp_path / "tools.json"),
    )

    root = service.load()

    assert root.schema_version == 3
    assert set(root.libraries.model_dump()) == {"papers", "fields"}
    assert root.projects == []
    assert root.tools == []
    compatibility = service.compatibility_directory_v2()
    assert compatibility["schema_version"] == 2
    assert compatibility["knowledge_catalog"] == _catalog().model_dump(mode="json")


def test_v3_health_direct_pdf_and_action_input_allowlist(tmp_path: Path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfixture")
    _FakeZotero.pdf_path = pdf
    action = PublicAction(
        id="safe-action",
        label="Safe",
        kind=ActionKind.ZOTERO_ITEM,
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        action_executor=_Executor(),
        public_actions={"paper:v3": [action]},
        zotero_adapter_factory=_FakeZotero,
        service_generation="service_abcdefghijklmnop",
    )
    try:
        port = server.server_address[1]
        health = json.loads(_request(port, "/api/v3/health").read())
        assert health["protocol"]["version"] == 3
        assert health["hub_directory"]["schema_version"] == 3
        assert "cmux-destinations-v1" in health["capabilities"]
        direct = _request(port, "/api/v3/pdfs/zotero/PDFD2345/content")
        assert direct.read().startswith(b"%PDF-1.7")

        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": token,
        }
        for forbidden in ("url", "command", "cwd", "model", "permission", "environment"):
            body = json.dumps({forbidden: "untrusted"}).encode()
            with pytest.raises(urllib.error.HTTPError) as error:
                _request(
                    port,
                    "/api/v3/actions/safe-action/invoke",
                    method="POST",
                    data=body,
                    headers=headers,
                )
            assert error.value.code == 400
        result = json.loads(
            _request(
                port,
                "/api/v3/actions/safe-action/invoke",
                method="POST",
                data=b"{}",
                headers=headers,
            ).read()
        )
        assert result == {"ok": True}
    finally:
        server.shutdown()
        server.server_close()

def test_field_navigation_reads_only_manifest_declared_markdown(tmp_path: Path):
    storage = tmp_path / "storage"
    selected = tmp_path / "世界模型"
    storage.mkdir()
    selected.mkdir()
    (selected / "00-领域入口.md").write_text("# 世界模型\n", encoding="utf-8")
    (selected / "JEPA.md").write_text("# JEPA\n", encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))
    preview = service.preview(selected)
    manifest = service.confirm(preview.candidate_token, preview.fields[0].field_id)
    field_id = manifest.fields[0].field_id
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=selected,
        catalog_provider=StaticCatalogProvider(_catalog()),
        field_service=service,
        zotero_adapter_factory=_FakeZotero,
    )
    try:
        port = server.server_address[1]
        page = json.loads(_request(port, "/api/v3/libraries/fields/items").read())
        assert page["items"][0]["home_content"] == "# 世界模型\n"
        query = urllib.parse.urlencode({"relative_path": "JEPA.md"})
        document = json.loads(
            _request(
                port,
                f"/api/v3/fields/{field_id}/documents?{query}",
            ).read()
        )
        assert document["content"] == "# JEPA\n"
        with pytest.raises(urllib.error.HTTPError) as error:
            _request(
                port,
                f"/api/v3/fields/{field_id}/documents?relative_path=../outside.md",
            )
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_v3_task_api_exposes_only_public_contract_and_strict_action_request(tmp_path: Path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    tasks = _TaskService()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        task_service=tasks,
        zotero_adapter_factory=_FakeZotero,
    )
    try:
        port = server.server_address[1]
        targets = json.loads(_request(port, "/api/v3/execution-targets").read())
        actions = json.loads(_request(port, "/api/v3/task-actions").read())
        assert targets == {"targets": tasks.public_targets()}
        assert actions == {"actions": tasks.public_actions()}
        serialized = json.dumps({"targets": targets, "actions": actions})
        assert "registered_root_id" not in serialized
        assert "cwd" not in serialized
        assert "model" not in serialized
        assert "sandbox" not in serialized

        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": token,
        }
        body = {
            "action_id": "task:research",
            "destination_id": "dst_12345678",
            "target_id": "target:project",
            "brief": "Inspect the registered target",
            "effort": "standard",
            "idempotency_key": "request-123",
        }
        created = _request(
            port,
            "/api/v3/tasks",
            method="POST",
            data=json.dumps(body).encode(),
            headers=headers,
        )
        assert created.status == 202
        assert json.loads(created.read())["terminal_routed"] is True
        request = tasks.requests[0][1]
        assert request.destination_id == "dst_12345678"
        assert request.target_id == "target:project"
        assert request.brief == "Inspect the registered target"

        with pytest.raises(urllib.error.HTTPError) as error:
            _request(
                port,
                "/api/v3/tasks",
                method="POST",
                data=json.dumps({**body, "cwd": "/tmp"}).encode(),
                headers=headers,
            )
        assert error.value.code == 422

        resumed = _request(
            port,
            "/api/v3/tasks/task-123/resume",
            method="POST",
            data=json.dumps({**body, "idempotency_key": "request-124"}).encode(),
            headers=headers,
        )
        assert resumed.status == 202
        forked = _request(
            port,
            "/api/v3/tasks/task-123/fork",
            method="POST",
            data=json.dumps({**body, "idempotency_key": "request-125"}).encode(),
            headers=headers,
        )
        assert forked.status == 202

        status = json.loads(_request(port, "/api/v3/tasks/task-123").read())
        assert status[0]["run_id"] == "run-123"
        run = json.loads(_request(port, "/api/v3/task-runs/run-123").read())
        assert run["state"] == "running"
        cancelled = json.loads(
            _request(
                port,
                "/api/v3/task-runs/run-123/cancel",
                method="POST",
                data=b"{}",
                headers=headers,
            ).read()
        )
        assert cancelled["state"] == "cancelled"
    finally:
        server.shutdown()
        server.server_close()


def test_default_hub_loads_only_explicit_task_runtime(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    hub_state = home / "hub"
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    for path in (storage, vault, project_root):
        path.mkdir()
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    project_id = "11111111-1111-4111-8111-111111111111"
    (project_root / "project-layout.json").write_text(
        json.dumps({"schema_version": 2, "project_id": project_id}),
        encoding="utf-8",
    )
    projects = ProjectRegistry(hub_state / "projects.json")
    projects.save(
        [
            ProjectRegistration(
                project_id=project_id,
                display_name="Fixture",
                root=project_root,
                capabilities=["codex"],
            )
        ]
    )
    sources = KnowledgeSourceRegistry(hub_state / "sources.json")
    targets = ExecutionTargetRegistry(
        hub_state / "execution-targets.json",
        project_registry=projects,
        source_registry=sources,
    )
    targets.save(
        ExecutionTargetRegistryDocument(
            targets=[
                ExecutionTarget(
                    target_id="fixture-project",
                    kind="project",
                    registered_root_id=project_id,
                    capabilities=["codex"],
                )
            ]
        )
    )
    recipes = TaskRecipeRegistry(hub_state / "task-recipes.json")
    recipes.save(
        TaskRecipeRegistryDocument(
            recipes=[
                TaskRecipe(
                    recipe_id="fixture-task",
                    title="Fixture task",
                    allowed_target_ids=["fixture-project"],
                    allowed_efforts=["standard"],
                    safety_policy_id="fixture-safe",
                )
            ],
            safety_policies=[
                TaskSafetyPolicy(
                    policy_id="fixture-safe",
                    policy_version=1,
                    model="private-model",
                    sandbox="read-only",
                )
            ],
        )
    )
    executable = tmp_path / "codex-fixture"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    state = TerminalWorkerState(hub_state / "task-worker")
    state.save_runtime(
        TerminalWorkerRuntimeConfig(
            generation="worker_fixture_generation",
            codex_executable=executable,
            recipe_registry_path=recipes.path,
            task_store_path=hub_state / "tasks.json",
            execution_target_registry_path=targets.path,
            project_registry_path=projects.path,
            source_registry_path=sources.path,
        )
    )
    monkeypatch.setattr(
        "scholar_workflow.hub.tasks.CodexCapabilityProbe.probe",
        lambda _self: CodexCapabilities(
            available=True, create=True, resume=True, fork=True
        ),
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        zotero_adapter_factory=_FakeZotero,
    )
    try:
        port = server.server_address[1]
        health = json.loads(_request(port, "/api/v3/health").read())
        executable_at_start = health["process"]["executable"]
        with monkeypatch.context() as context:
            context.setattr(sys, "executable", str(tmp_path / "ephemeral-python"))
            fresh_health = json.loads(_request(port, "/api/v3/health").read())
        assert fresh_health["process"]["executable"] == executable_at_start
        directory = json.loads(_request(port, "/api/v3/directory").read())
        actions = json.loads(_request(port, "/api/v3/task-actions").read())
        targets_payload = json.loads(_request(port, "/api/v3/execution-targets").read())
        assert health["task_execution"] is True
        assert health["worker_capabilities"]["task_execution"] is True
        assert directory["capabilities"]["codex_tasks"]["available"] is True
        assert len(actions["actions"]) == 1
        assert actions["actions"][0]["allowed_target_ids"] == ["fixture-project"]
        assert targets_payload["targets"][0]["target_id"] == "fixture-project"
        task_service = server.runtime.task_service
        assert task_service._slot_id(
            raw_workspace="workspace-1",
            fingerprint="sha256:" + "a" * 64,
            target_id="fixture-project",
        ) != task_service._slot_id(
            raw_workspace="workspace-1",
            fingerprint="sha256:" + "b" * 64,
            target_id="fixture-project",
        )
        exposed = json.dumps((directory, actions, targets_payload), ensure_ascii=False)
        for forbidden in (str(project_root), str(executable), "private-model", "sandbox"):
            assert forbidden not in exposed
    finally:
        server.shutdown()
        server.server_close()

    state.save_runtime(
        TerminalWorkerRuntimeConfig(
            generation="worker_fixture_generation",
            codex_executable=executable,
            recipe_registry_path=recipes.path,
            task_store_path=hub_state / "tasks.json",
            execution_target_registry_path=targets.path,
            project_registry_path=tmp_path / "different-projects.json",
            source_registry_path=sources.path,
        )
    )
    mismatched = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        zotero_adapter_factory=_FakeZotero,
    )
    try:
        health = json.loads(
            _request(mismatched.server_address[1], "/api/v3/health").read()
        )
        assert health["task_execution"] is False
        assert "registries" in health["worker_capabilities"]["detail"]
    finally:
        mismatched.shutdown()
        mismatched.server_close()
