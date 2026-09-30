"""Independent synthetic cases for approved profiles and reviewed local setup.

These tests do not start Codex, cmux, Obsidian, or any external application.
"""
from __future__ import annotations

import json
import io
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow.hub.codex_setup import CodexModelCatalog, CodexSetupError, CodexSetupService
from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.fields import (
    FolderRegistration, KnowledgeSourceRegistration, KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.routing import (
    ExecutionTarget, ExecutionTargetError, ExecutionTargetRegistryDocument, TaskActionRequest,
)
from scholar_workflow.hub.tasks import (
    CodexCommandBuilder,
    CodexModelProfile,
    TaskContractError,
    TaskCoordinator,
    TaskRecipe,
    TaskRecipeRegistry,
    TaskRecipeRegistryDocument,
    TaskRequest,
    TaskRunState,
    TaskSafetyPolicy,
    TaskStore,
)


def _profile(model: str = "fixture-model", *, profile_id: str = "default", supported=None) -> CodexModelProfile:
    supported = supported or ["low", "medium", "high"]
    return CodexModelProfile(
        profile_id=profile_id, title="Fixture model", model=model,
        supported_reasoning_efforts=supported,
        default_reasoning_effort="medium" if "medium" in supported else supported[0], is_default=profile_id == "default",
    )


def _coordinator(tmp_path: Path, *, model: str = "fixture-model", supported=None):
    recipe = TaskRecipe(
        recipe_id="fixture-task", title="Fixture task", project_required=False,
        safety_policy_id="fixture-safe", allowed_model_profile_ids=["default"],
    )
    policy = TaskSafetyPolicy(
        policy_id="fixture-safe", policy_version=1, model=model, sandbox="read-only",
    )
    recipes = TaskRecipeRegistry(tmp_path / "recipes.json")
    recipes.save(TaskRecipeRegistryDocument(
        recipes=[recipe], safety_policies=[policy], model_profiles=[_profile(model, supported=supported)],
    ))
    builder = CodexCommandBuilder(
        codex_executable=Path("/fixture/codex"), safety_policies=recipes.safety_policy_map(),
        model_profiles=recipes.model_profile_map(), runtime_cwd=tmp_path,
    )
    store = TaskStore(tmp_path / "tasks.json")
    return builder, TaskCoordinator(recipes=recipes, store=store, commands=builder), store, recipe


def _request(*, key: str = "fixture-request", **changes) -> TaskRequest:
    return TaskRequest(
        recipe_id="fixture-task", model_profile_id="default",
        brief="Read the fixture note", idempotency_key=key, **changes,
    )


def test_model_and_supported_effort_are_resolved_only_from_server_profile(tmp_path):
    builder, _, _, recipe = _coordinator(tmp_path)
    invocation = builder.build_new(recipe, _request(reasoning_effort="high"))
    assert invocation.argv[invocation.argv.index("-m") + 1] == "fixture-model"
    assert 'model_reasoning_effort="high"' in invocation.argv
    assert invocation.resolved_model == "fixture-model"
    assert invocation.reasoning_effort == "high"
    with pytest.raises(TaskContractError, match="not supported"):
        builder.build_new(recipe, _request(reasoning_effort="ultra"))
    with pytest.raises(TaskContractError, match="not allowlisted"):
        builder.build_new(recipe, TaskRequest(
            recipe_id=recipe.recipe_id, model_profile_id="unapproved",
            brief="Read fixture", idempotency_key="other-request",
        ))


def test_browser_cannot_submit_raw_model_or_unsupported_config():
    payload = {
        "action_id": "task:fixture", "target_id": "fixture-target",
        "brief": "Read fixture", "idempotency_key": "fixture-request",
        "model_profile_id": "default", "reasoning_effort": "high",
    }
    request = TaskActionRequest.model_validate(payload)
    assert request.effort == "standard"
    for forbidden in ("model", "cwd", "sandbox", "permission", "command"):
        with pytest.raises(ValueError):
            TaskActionRequest.model_validate({**payload, forbidden: "arbitrary"})
    with pytest.raises(ValueError):
        TaskActionRequest.model_validate({**payload, "reasoning_effort": 'high";malicious'})


def test_existing_thread_keeps_its_model_when_default_alias_changes(tmp_path):
    _, coordinator, store, _ = _coordinator(tmp_path)
    first = coordinator.create(_request(reasoning_effort="high"), title="Fixture")
    now = datetime.now(UTC)
    store.start(first.run.run_id, now=now, timeout_seconds=30)
    store.finish(
        first.run.run_id, state=TaskRunState.SUCCEEDED, now=now,
        codex_thread_id="8d645f40-55f5-4b76-9db4-18e2bc5464fa",
    )
    _, changed, _, _ = _coordinator(tmp_path, model="replacement-model", supported=["low"])
    resumed = changed.resume(first.task.task_id, _request(key="fixture-resume", reasoning_effort="high"))
    assert resumed.task.resolved_model == "fixture-model"
    assert resumed.run.resolved_model == "fixture-model"
    assert resumed.invocation is not None
    assert resumed.invocation.resolved_model == "fixture-model"
    store.fail_queued(resumed.run.run_id, now=now, reason="Synthetic case complete")
    with pytest.raises(TaskContractError, match="reasoning effort"):
        changed.resume(first.task.task_id, _request(key="fixture-change", reasoning_effort="low"))


def test_schema_two_registry_and_legacy_effort_remain_readable(tmp_path):
    builder, _, _, recipe = _coordinator(tmp_path)
    document = TaskRecipeRegistryDocument.model_validate({
        "schema_version": 2, "recipes": [], "safety_policies": [],
    })
    assert document.model_profiles == []
    request = TaskRequest(
        recipe_id=recipe.recipe_id, brief="Read fixture", effort="standard",
        idempotency_key="legacy-request",
    )
    invocation = builder.build_new(recipe, request)
    assert invocation.model_profile_id is None
    assert invocation.reasoning_effort == "medium"


def test_preprofile_persisted_task_can_resume_without_rewriting_its_identity(tmp_path):
    _, coordinator, store, recipe = _coordinator(tmp_path)
    request = TaskRequest(recipe_id=recipe.recipe_id, brief="Read legacy fixture", idempotency_key="legacy-create")
    first = coordinator.create(request, title="Legacy fixture")
    now = datetime.now(UTC)
    store.start(first.run.run_id, now=now, timeout_seconds=30)
    store.finish(first.run.run_id, state=TaskRunState.SUCCEEDED, now=now,
                 codex_thread_id="8d645f40-55f5-4b76-9db4-18e2bc5464fa")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    for row in [*payload["tasks"], *payload["runs"]]:
        for key in ("model_profile_id", "resolved_model", "reasoning_effort"):
            row.pop(key, None)
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    resumed = coordinator.resume(first.task.task_id, TaskRequest(
        recipe_id=recipe.recipe_id, brief="Continue legacy fixture", idempotency_key="legacy-resume",
    ))
    assert resumed.task.resolved_model is None
    assert resumed.run.resolved_model is None
    assert resumed.invocation is not None
    assert resumed.invocation.resolved_model == "fixture-model"


class _Probe:
    def __init__(self, _path):
        pass

    def probe(self):
        return SimpleNamespace(available=True, create=True, resume=True, fork=True)


def _setup_service(tmp_path: Path, *, catalog_loader=None):
    home = tmp_path / "home"
    executable = home / ".local/bin/codex"
    executable.parent.mkdir(parents=True)
    executable.write_text("fixture executable", encoding="utf-8")
    executable.chmod(0o700)
    root = tmp_path / "hub"
    service = CodexSetupService(
        root, project_registry=ProjectRegistry(root / "projects.json"),
        source_registry=KnowledgeSourceRegistry(root / "sources.json"),
        probe_factory=_Probe, user_home=home, config_home=home / ".codex",
        runner=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="codex 1.2.3\n"),
        catalog_loader=catalog_loader or (lambda _path: [{
            "id": "fixture-model", "model": "fixture-model", "displayName": "Fixture model",
            "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "medium"}],
            "defaultReasoningEffort": "medium", "isDefault": True,
        }]),
    )
    # Isolate this fixture from other fixed installer locations on the test host.
    service._candidate_paths = lambda: [executable]
    return service, executable, home


def test_setup_preview_uses_opaque_ids_and_confirmation_registers_reviewed_catalog(tmp_path):
    service, executable, _ = _setup_service(tmp_path)
    preview = service.preview()
    assert not service.root.exists()
    assert str(executable) not in str(preview)
    candidate = preview["candidates"][0]
    assert candidate["version"] == "1.2.3"
    assert candidate["available"] is True
    result = service.confirm({
        "candidate_id": candidate["candidate_id"], "model_profile_id": "default",
        "target_ids": [], "sandbox": "read-only",
    })
    assert result["configured"] is True
    assert result["restart_required"] is False
    assert service.recipes.load().model_profiles
    assert (service.root / "task-worker/runtime.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(CodexSetupError, match="preview expired"):
        service.confirm({"candidate_id": candidate["candidate_id"], "model_profile_id": "default"})


def test_changed_executable_or_targets_invalidates_reviewed_setup(tmp_path):
    service, executable, _ = _setup_service(tmp_path)
    candidate = service.preview()["candidates"][0]
    executable.write_text("changed fixture executable", encoding="utf-8")
    with pytest.raises(CodexSetupError, match="installation changed"):
        service.confirm({"candidate_id": candidate["candidate_id"], "model_profile_id": "default"})


def test_explicit_configuration_requires_all_three_codex_modes(tmp_path):
    service, executable, _ = _setup_service(tmp_path)
    service._probe_factory = lambda _path: SimpleNamespace(probe=lambda: SimpleNamespace(
        available=True, create=True, resume=False, fork=True,
    ))
    with pytest.raises(CodexSetupError, match="required task capabilities"):
        service.register_explicit(executable=executable, model="fixture-model", sandbox="read-only", target_ids=[])
    assert not service.root.exists()


def test_catalog_failure_falls_back_only_to_local_default_without_reading_auth(tmp_path):
    def unavailable(_path):
        raise CodexSetupError("Unavailable fixture catalog")

    service, _, home = _setup_service(tmp_path, catalog_loader=unavailable)
    config = home / ".codex"
    config.mkdir()
    (config / "config.toml").write_text(
        'model = "configured-model"\nmodel_reasoning_effort = "high"\n'
        '[model_providers.fixture]\nmodel = "ignored-provider-model"\n', encoding="utf-8",
    )
    (config / "auth.json").write_text('{"secret":"must-not-appear"}', encoding="utf-8")
    preview = service.preview()
    assert "must-not-appear" not in str(preview)
    profiles = preview["model_profiles"]
    assert [row["profile_id"] for row in profiles][0] == "default"
    assert all(row["supported_reasoning_efforts"] == ["high"] for row in profiles)
    assert "ignored-provider-model" not in str(preview)


def test_setup_grants_only_selected_registered_field_and_resolves_field_cwd(tmp_path):
    service, _, _ = _setup_service(tmp_path)
    source_id = "d1103fb2-0dc7-4d72-a9d5-385b8eddbf46"
    field_id = "1ab903ea-b674-4bf8-b207-d5fbbd99bb67"
    other_field_id = "6e6153c5-9d10-4cba-82c4-3f8d2045b361"
    vault = tmp_path / "fixture-vault"
    field_root = vault / "world-models"
    field_root.mkdir(parents=True)
    (field_root / "home.md").write_text("Fixture Field", encoding="utf-8")
    other_field_root = vault / "other-field"
    other_field_root.mkdir()
    (other_field_root / "home.md").write_text("Other fixture Field", encoding="utf-8")
    manifest_dir = vault / ".scholar-workflow"
    manifest_dir.mkdir()
    (manifest_dir / "fields.yml").write_text(
        f"schema_version: 1\nsource_id: {source_id}\nfields:\n"
        f"  - field_id: {field_id}\n    title: Fixture Field\n"
        "    relative_root: world-models\n    home: home.md\n    navigation: []\n"
        f"  - field_id: {other_field_id}\n    title: Other fixture Field\n"
        "    relative_root: other-field\n    home: home.md\n    navigation: []\n", encoding="utf-8",
    )
    service._sources.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="fixture-vault", root=vault, capabilities=["read", "write"])],
        sources=[KnowledgeSourceRegistration(source_id=source_id, folder_id="fixture-vault")],
    ))
    service.targets.save(ExecutionTargetRegistryDocument(targets=[ExecutionTarget(
        target_id="previous-full-vault", kind="vault", registered_root_id="fixture-vault",
        capabilities=["codex"],
    ), ExecutionTarget(
        target_id="previous-other-field", kind="vault", registered_root_id="fixture-vault",
        source_id=source_id, field_id=other_field_id, capabilities=["codex"],
    )]))
    with pytest.raises(ExecutionTargetError, match="does not allow codex"):
        service.targets.resolve("previous-full-vault", capability="codex")
    preview = service.preview()
    target = next(row for row in preview["targets"] if row.get("field_id") == field_id)
    assert target["registration_required"] is True
    assert target["permission_note"]
    assert "codex" not in service._sources.load_document().folders[0].capabilities
    service.confirm({
        "candidate_id": preview["candidates"][0]["candidate_id"], "model_profile_id": "default",
        "target_ids": [target["target_id"]], "sandbox": "read-only",
    })
    resolved = service.targets.resolve(target["target_id"], capability="codex")
    assert resolved.cwd == field_root
    assert resolved.target.source_id == source_id
    assert resolved.target.field_id == field_id
    assert f"codex.field:{field_id}" in service._sources.load_document().folders[0].capabilities
    assert "codex" not in service._sources.load_document().folders[0].capabilities
    with pytest.raises(ExecutionTargetError, match="does not allow codex"):
        service.targets.resolve("previous-full-vault", capability="codex")
    with pytest.raises(ExecutionTargetError, match="does not allow codex"):
        service.targets.resolve("previous-other-field", capability="codex")
    current = service.preview()
    assert current["sandbox"] == "read-only"
    assert next(row for row in current["targets"] if row["target_id"] == target["target_id"])["selected"]


def test_model_preferences_are_persistent_private_and_supported(tmp_path):
    service, _, _ = _setup_service(tmp_path)
    preview = service.preview()
    service.confirm({"candidate_id": preview["candidates"][0]["candidate_id"], "model_profile_id": "default"})
    saved = service.save_preferences("default", "low")
    assert saved["selected_model_profile_id"] == "default"
    assert saved["selected_reasoning_effort"] == "low"
    assert (service.root / "task-preferences.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(CodexSetupError, match="supported reasoning"):
        service.save_preferences("default", "ultra")
    assert service.public_options()["selected_reasoning_effort"] == "low"


def test_model_catalog_uses_fixed_rpc_and_reaps_its_ephemeral_process(monkeypatch):
    class Capture(io.StringIO):
        captured = ""

        def close(self):
            if not self.closed:
                self.captured = self.getvalue()
            super().close()

    class Process:
        pid = 424242
        returncode = None
        stdin = Capture()
        stdout = io.StringIO(
            json.dumps({"id": 1, "result": {"userAgent": "fixture"}}) + "\n" +
            json.dumps({"id": 2, "result": {"data": [{"id": "fixture-model"}], "nextCursor": None}}) + "\n"
        )

        def poll(self):
            return self.returncode

        def wait(self, *, timeout):
            self.returncode = 0
            return 0

    process = Process()
    calls = []
    signals = []
    monkeypatch.setattr("scholar_workflow.hub.codex_setup.os.killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setenv("ZOTERO_API_KEY", "must-not-propagate")

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    catalog = CodexModelCatalog(popen_factory=popen)
    assert catalog.load(Path("/fixture/codex")) == [{"id": "fixture-model"}]
    assert calls[0][0] == ["/fixture/codex", "app-server"]
    assert calls[0][1]["shell"] is False
    assert "ZOTERO_API_KEY" not in calls[0][1]["env"]
    requests = [json.loads(line) for line in process.stdin.captured.splitlines()]
    assert [row["method"] for row in requests] == ["initialize", "initialized", "model/list"]
    assert signals and process.returncode == 0
