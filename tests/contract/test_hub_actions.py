"""Contract tests for opaque Hub actions and the cmux Notion launcher."""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scholar_workflow.hub.actions import (
    ActionError,
    ActionExecutor,
    ActionKind,
    ActionRegistry,
    CatalogActionService,
    CmuxArtifactLauncher,
    CmuxLaunchError,
    CmuxLauncher,
    CmuxResourceLauncher,
    CmuxUnavailable,
    CodexLauncher,
    InvalidActionTarget,
    ObsidianLauncher,
    UnknownActionError,
    UnsupportedActionError,
    WorkspacePolicy,
    ZoteroLauncher,
    register_artifact_view_actions,
    register_codex_action,
    register_notion_actions,
    register_obsidian_actions,
    register_resource_view_actions,
    register_zotero_actions,
)
from scholar_workflow.hub.cmux import (
    CmuxControl,
    CmuxControlError,
    UnknownWorkspaceError,
    WorkspaceRegistry,
)
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
    HubResource,
    ProjectionLinks,
)


NOTION_URL = "https://www.notion.so/0123456789abcdef0123456789abcdef"


def _executable(tmp_path: Path, name: str = "cmux") -> Path:
    path = tmp_path / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _completed(argv: list[str], returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(argv, returncode, stdout="", stderr=stderr)


def test_registry_public_view_is_opaque_and_excludes_target():
    registry = ActionRegistry(id_factory=lambda: "act_opaque")

    view = registry.register(
        kind=ActionKind.NOTION_CMUX,
        label="Open in cmux",
        target=NOTION_URL,
    )

    assert view.id == "act_opaque"
    assert view.workspace_policy is WorkspacePolicy.NONE
    assert NOTION_URL not in repr(view)
    assert "target" not in asdict(view)
    assert registry.resolve(view.id).target == NOTION_URL


def test_registry_exposes_workspace_policy_but_keeps_target_opaque():
    registry = ActionRegistry(id_factory=lambda: "act_workspace")

    view = registry.register(
        kind=ActionKind.NOTION_CMUX,
        label="Open in cmux",
        target=NOTION_URL,
        workspace_policy=WorkspacePolicy.REQUIRED,
    )

    assert asdict(view) == {
        "id": "act_workspace",
        "label": "Open in cmux",
        "kind": ActionKind.NOTION_CMUX,
        "workspace_policy": WorkspacePolicy.REQUIRED,
    }
    assert registry.resolve(view.id).target == NOTION_URL


def test_registry_rejects_unknown_action_id():
    with pytest.raises(UnknownActionError, match="Unknown Hub action"):
        ActionRegistry().resolve("act_missing")


def test_executor_resolves_target_server_side():
    registry = ActionRegistry(id_factory=lambda: "act_opaque")
    view = registry.register(
        kind=ActionKind.NOTION_CMUX,
        label="Open in cmux",
        target=NOTION_URL,
    )
    seen: list[str] = []

    class FakeLauncher:
        def open(self, target: str):
            seen.append(target)
            return "opened"

    executor = ActionExecutor(registry, {ActionKind.NOTION_CMUX: FakeLauncher()})

    assert executor.execute(view.id) == "opened"
    assert seen == [NOTION_URL]


def test_executor_routes_only_required_actions_to_an_opaque_workspace():
    registry = ActionRegistry(id_factory=lambda: "act_workspace")
    view = registry.register(
        kind=ActionKind.NOTION_CMUX,
        label="Open in cmux",
        target=NOTION_URL,
        workspace_policy=WorkspacePolicy.REQUIRED,
    )
    seen = []

    class FakeLauncher:
        def open(self, target, *, workspace_id=None):
            seen.append((target, workspace_id))
            return "opened"

    executor = ActionExecutor(registry, {ActionKind.NOTION_CMUX: FakeLauncher()})

    with pytest.raises(InvalidActionTarget, match="workspace"):
        executor.execute(view.id)
    assert executor.execute(view.id, workspace_id="ws_opaque") == "opened"
    assert seen == [(NOTION_URL, "ws_opaque")]


def test_executor_rejects_workspace_for_non_workspace_action():
    registry = ActionRegistry(id_factory=lambda: "act_obsidian")
    view = registry.register(
        kind=ActionKind.OBSIDIAN_NOTE,
        label="Edit in Obsidian",
        target="notes/paper.md",
    )

    with pytest.raises(InvalidActionTarget, match="does not accept"):
        ActionExecutor(registry, {ActionKind.OBSIDIAN_NOTE: object()}).execute(
            view.id,
            workspace_id="ws_opaque",
        )


def test_executor_fails_closed_for_unregistered_launcher():
    registry = ActionRegistry(id_factory=lambda: "act_opaque")
    view = registry.register(
        kind=ActionKind.NOTION_CMUX,
        label="Open in cmux",
        target=NOTION_URL,
    )

    with pytest.raises(UnsupportedActionError, match="No launcher"):
        ActionExecutor(registry, {}).execute(view.id)


@pytest.mark.parametrize(
    "url",
    [
        "https://notion.so/page",
        "https://www.notion.so/page",
        "https://notion.com/page",
        "https://www.notion.com/page",
        "https://notion.site/page",
        "https://team.notion.site/page",
    ],
)
def test_cmux_launcher_accepts_only_supported_notion_hosts(tmp_path, url):
    executable = _executable(tmp_path)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed(argv)

    result = CmuxLauncher(configured_path=executable, runner=runner).open(url)

    assert result.opened is True
    assert calls[0][0] == [str(executable), "open", url, "--focus", "true"]


@pytest.mark.parametrize(
    "url",
    [
        "http://notion.so/page",
        "https://notion.so.evil.example/page",
        "https://evilnotion.so/page",
        "https://notion.example/page",
        "https://user@notion.so/page",
        "file:///tmp/notion.html",
        "javascript:alert(1)",
    ],
)
def test_cmux_launcher_rejects_invalid_targets_before_process_start(tmp_path, url):
    executable = _executable(tmp_path)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed(argv)

    with pytest.raises(InvalidActionTarget):
        CmuxLauncher(configured_path=executable, runner=runner).open(url)

    assert calls == []


def test_cmux_launcher_uses_argv_no_shell_timeout_and_scrubbed_env(tmp_path, monkeypatch):
    executable = _executable(tmp_path)
    monkeypatch.setenv("CMUX_RESPECT_EXTERNAL_OPEN_RULES", "1")
    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux-test.sock")
    monkeypatch.setenv("SCHOLAR_WORKFLOW_NOTION_TOKEN", "must-not-reach-child")
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed(argv)

    CmuxLauncher(configured_path=executable, timeout=2.5, runner=runner).open(NOTION_URL)

    argv, kwargs = calls[0]
    assert argv == [str(executable), "open", NOTION_URL, "--focus", "true"]
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 2.5
    assert "CMUX_RESPECT_EXTERNAL_OPEN_RULES" not in kwargs["env"]
    assert kwargs["env"]["CMUX_SOCKET_PATH"] == "/tmp/cmux-test.sock"
    assert "SCHOLAR_WORKFLOW_NOTION_TOKEN" not in kwargs["env"]


def test_cmux_path_resolution_prefers_config_then_path_then_app_bundle(
    tmp_path, monkeypatch
):
    configured = _executable(tmp_path, "configured-cmux")
    path_cmux = _executable(tmp_path, "path-cmux")
    bundle_cmux = _executable(tmp_path, "bundle-cmux")
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed(argv)

    monkeypatch.setattr("scholar_workflow.hub.actions.shutil.which", lambda _: str(path_cmux))
    monkeypatch.setattr("scholar_workflow.hub.actions.DEFAULT_CMUX_PATH", bundle_cmux)

    CmuxLauncher(configured_path=configured, runner=runner).open(NOTION_URL)
    CmuxLauncher(runner=runner).open(NOTION_URL)
    monkeypatch.setattr("scholar_workflow.hub.actions.shutil.which", lambda _: None)
    CmuxLauncher(runner=runner).open(NOTION_URL)

    assert [call[0] for call in calls] == [str(configured), str(path_cmux), str(bundle_cmux)]


def test_cmux_launcher_starts_app_then_retries_with_a_bound(tmp_path):
    executable = _executable(tmp_path)
    calls = []
    sleeps = []
    responses = iter(
        [
            _completed([], 1, "No live cmux socket found"),
            _completed([], 0),
            _completed([], 1, "No live cmux socket found"),
            _completed([], 0),
        ]
    )

    def runner(argv, **kwargs):
        calls.append(argv)
        response = next(responses)
        return _completed(argv, response.returncode, response.stderr)

    result = CmuxLauncher(
        configured_path=executable,
        runner=runner,
        sleeper=sleeps.append,
        retry_attempts=2,
        retry_delay=0.01,
    ).open(NOTION_URL)

    cmux_argv = [str(executable), "open", NOTION_URL, "--focus", "true"]
    assert calls == [
        cmux_argv,
        ["/usr/bin/open", "-b", "com.cmuxterm.app"],
        cmux_argv,
        cmux_argv,
    ]
    assert sleeps == [0.01, 0.01]
    assert result.started_app is True
    assert result.attempts == 3


def test_cmux_launcher_reports_failure_without_browser_fallback(tmp_path):
    executable = _executable(tmp_path)
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed(argv, 7, "blocked by policy")

    with pytest.raises(CmuxLaunchError, match="blocked by policy"):
        CmuxLauncher(configured_path=executable, runner=runner).open(NOTION_URL)

    assert calls == [[str(executable), "open", NOTION_URL, "--focus", "true"]]
    assert all(call[:1] != ["/usr/bin/open"] for call in calls)


def test_cmux_launcher_reports_missing_binary_without_fallback(monkeypatch):
    monkeypatch.setattr("scholar_workflow.hub.actions.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "scholar_workflow.hub.actions.DEFAULT_CMUX_PATH",
        Path("/definitely/missing/cmux"),
    )

    with pytest.raises(CmuxUnavailable, match="cmux CLI was not found"):
        CmuxLauncher().open(NOTION_URL)


def test_catalog_notion_id_becomes_opaque_cmux_action():
    registry = ActionRegistry(id_factory=lambda: "act_notion")
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[
            HubResource(
                resource_id="paper:one",
                kind="paper",
                projections=ProjectionLinks(
                    notion_page_id="01234567-89ab-cdef-0123-456789abcdef"
                ),
            )
        ],
        topics=[],
        artifacts=[],
    )

    public = register_notion_actions(catalog, registry)

    assert public["paper:one"][0].id == "act_notion"
    assert public["paper:one"][0].kind is ActionKind.NOTION_CMUX
    assert registry.resolve("act_notion").target == NOTION_URL


def test_invalid_notion_projection_id_is_not_registered():
    registry = ActionRegistry(id_factory=lambda: "act_never")
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[
            HubResource(
                resource_id="paper:one",
                kind="paper",
                projections=ProjectionLinks(notion_page_id="not-a-page-id"),
            )
        ],
        topics=[],
        artifacts=[],
    )
    assert register_notion_actions(catalog, registry) == {}


def test_catalog_artifact_becomes_opaque_obsidian_action(tmp_path):
    registry = ActionRegistry(id_factory=lambda: "act_obsidian")
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[],
        artifacts=[
            HubArtifact(
                artifact_id="note:one",
                kind=ArtifactKind.PAPER_ANALYSIS,
                format=ArtifactFormat.MARKDOWN,
                vault_path="topic/analysis.md",
            )
        ],
    )
    public = register_obsidian_actions(catalog, registry)
    assert public["note:one"][0].id == "act_obsidian"
    assert registry.resolve("act_obsidian").target == "topic/analysis.md"


def test_obsidian_launcher_resolves_registered_relative_path_inside_vault(
    tmp_path,
    monkeypatch,
):
    vault = tmp_path / "vault"
    note = vault / "主题" / "analysis.md"
    note.parent.mkdir(parents=True)
    note.write_text("# readable", encoding="utf-8")
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed(argv)

    result = ObsidianLauncher(vault, runner=runner).open("主题/analysis.md")
    assert result.opened is True
    argv, kwargs = calls[0]
    assert argv[0] == "/usr/bin/open"
    assert argv[1].startswith("obsidian://open?path=")
    assert kwargs["shell"] is False
    assert "OPENAI_API_KEY" not in kwargs["env"]


@pytest.mark.parametrize("target", ["/etc/passwd", "../secret.md"])
def test_obsidian_launcher_rejects_escape_before_process_start(tmp_path, target):
    calls = []
    with pytest.raises(InvalidActionTarget):
        ObsidianLauncher(
            tmp_path,
            runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        ).open(target)
    assert calls == []


def test_workspace_registry_parses_cmux_tree_without_exposing_raw_ids(tmp_path):
    executable = _executable(tmp_path)
    tree = {
        "windows": [
            {
                "id": "window-raw-id",
                "workspaces": [
                    {
                        "id": "workspace-current-raw",
                        "ref": "workspace:1",
                        "title": "Scholar Hub workspace-current-raw",
                        "selected": False,
                        "panes": [
                            {
                                "surfaces": [
                                    {
                                        "type": "browser",
                                        "url": (
                                            "http://127.0.0.1:23128/hub/"
                                            "?instance=hub_instance_token_1234"
                                        ),
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "workspace_id": "workspace-other-raw",
                        "name": "Other Research",
                        "selected": True,
                        "panes": [],
                    },
                ],
            }
        ]
    }
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(tree),
            stderr="",
        )

    ids = iter(["ws_current_opaque", "ws_other_opaque"])
    control = CmuxControl(configured_path=executable, runner=runner)
    registry = WorkspaceRegistry(
        control,
        current_workspace_id="workspace-current-raw",
        hub_url="http://127.0.0.1:23128/hub/",
        id_factory=lambda: next(ids),
    )

    listing = registry.public_workspaces()

    assert calls[0][0] == [str(executable), "--json", "tree", "--all"]
    assert calls[0][1]["shell"] is False
    assert listing.capability_error is None
    assert [workspace.id for workspace in listing.workspaces] == [
        "ws_current_opaque",
        "ws_other_opaque",
    ]
    assert listing.workspaces[0].label == "Scholar Hub <workspace>"
    assert listing.workspaces[0].is_current is True
    assert listing.workspaces[0].contains_hub is True
    assert listing.workspaces[1].is_current is False
    serialized = repr(listing)
    assert "workspace-current-raw" not in serialized
    assert "workspace-other-raw" not in serialized
    assert "window-raw-id" not in serialized
    assert "workspace:1" not in serialized
    assert registry.resolve("ws_current_opaque") == "workspace-current-raw"
    with pytest.raises(UnknownWorkspaceError):
        registry.resolve("workspace-current-raw")

    matching = registry.public_workspaces(instance_token="hub_instance_token_1234")
    other_instance = registry.public_workspaces(instance_token="hub_instance_token_5678")
    assert matching.workspaces[0].contains_hub is True
    assert other_instance.workspaces[0].contains_hub is False


def test_workspace_registry_returns_visible_capability_error(tmp_path):
    executable = _executable(tmp_path)

    def runner(argv, **kwargs):
        return _completed(
            argv,
            1,
            "No live cmux socket found. Tried:\n"
            "/Users/private-user/.local/state/cmux/cmux.sock\n"
            "/tmp/cmux.sock",
        )

    registry = WorkspaceRegistry(CmuxControl(configured_path=executable, runner=runner))

    listing = registry.public_workspaces()

    assert listing.workspaces == ()
    assert listing.capability_error == "No live cmux socket found"
    assert "/Users/private-user" not in listing.capability_error
    assert "/tmp/cmux.sock" not in listing.capability_error
    with pytest.raises(UnknownWorkspaceError):
        registry.resolve("ws_missing")


def test_workspace_registry_reports_invalid_tree_as_capability_error(tmp_path):
    executable = _executable(tmp_path)

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="not-json", stderr="")

    registry = WorkspaceRegistry(CmuxControl(configured_path=executable, runner=runner))

    listing = registry.public_workspaces()

    assert listing.workspaces == ()
    assert listing.capability_error == "cmux returned invalid workspace JSON"


def _workspace_runtime(tmp_path, *, calls):
    executable = _executable(tmp_path)
    tree = {
        "windows": [
            {
                "workspaces": [
                    {
                        "id": "workspace-raw",
                        "title": "Research",
                        "selected": True,
                        "panes": [],
                    }
                ]
            }
        ]
    }

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[1:4] == ["--json", "tree", "--all"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(tree),
                stderr="",
            )
        return _completed(argv)

    control = CmuxControl(configured_path=executable, runner=runner)
    registry = WorkspaceRegistry(
        control,
        current_workspace_id="workspace-raw",
        id_factory=lambda: "ws_opaque",
    )
    registry.public_workspaces()
    return executable, control, registry


def test_notion_launcher_targets_selected_workspace_by_opaque_id(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("CMUX_RESPECT_EXTERNAL_OPEN_RULES", "1")
    executable, control, workspaces = _workspace_runtime(tmp_path, calls=calls)

    result = CmuxLauncher(control=control, workspace_registry=workspaces).open(
        NOTION_URL,
        workspace_id="ws_opaque",
    )

    assert result.opened is True
    argv, kwargs = calls[-1]
    assert argv == [
        str(executable),
        "open",
        NOTION_URL,
        "--workspace",
        "workspace-raw",
        "--focus",
        "true",
    ]
    assert kwargs["shell"] is False
    assert "CMUX_RESPECT_EXTERNAL_OPEN_RULES" not in kwargs["env"]


def test_catalog_resource_view_action_is_opaque_and_uses_fixed_hub_origin(tmp_path):
    registry = ActionRegistry(id_factory=lambda: "act_resource")
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[
            HubResource(
                resource_id="paper:one",
                kind="paper",
                zotero={"attachment_key": "ABCD2345"},
            )
        ],
        topics=[],
        artifacts=[],
    )
    public = register_resource_view_actions(catalog, registry)
    calls = []
    executable, control, workspaces = _workspace_runtime(tmp_path, calls=calls)

    action = public["paper:one"][0]
    assert action.kind is ActionKind.RESOURCE_CMUX
    assert action.workspace_policy is WorkspacePolicy.REQUIRED
    assert "ABCD2345" not in repr(action)
    launcher = CmuxResourceLauncher(
        workspaces,
        control=control,
        hub_origin="http://127.0.0.1:23128",
    )
    launcher.open(registry.resolve(action.id).target, workspace_id="ws_opaque")

    assert calls[-1][0] == [
        str(executable),
        "open",
        "http://127.0.0.1:23128/open/paper/ABCD2345",
        "--workspace",
        "workspace-raw",
        "--focus",
        "true",
    ]


def test_catalog_artifact_view_resolves_only_registered_vault_path(tmp_path):
    vault = tmp_path / "vault"
    note = vault / "topic" / "analysis.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Readable\n", encoding="utf-8")
    registry = ActionRegistry(id_factory=lambda: "act_artifact")
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[],
        topics=[],
        artifacts=[
            HubArtifact(
                artifact_id="note:one",
                kind=ArtifactKind.PAPER_ANALYSIS,
                format=ArtifactFormat.MARKDOWN,
                vault_path="topic/analysis.md",
            )
        ],
    )
    public = register_artifact_view_actions(catalog, registry)
    calls = []
    executable, control, workspaces = _workspace_runtime(tmp_path, calls=calls)

    action = public["note:one"][0]
    assert action.kind is ActionKind.ARTIFACT_CMUX
    assert action.workspace_policy is WorkspacePolicy.REQUIRED
    assert "analysis.md" not in repr(action)
    launcher = CmuxArtifactLauncher(vault, workspaces, control=control)
    launcher.open(registry.resolve(action.id).target, workspace_id="ws_opaque")

    assert calls[-1][0] == [
        str(executable),
        "open",
        str(note),
        "--workspace",
        "workspace-raw",
        "--focus",
        "true",
    ]


def test_catalog_zotero_action_hides_key_and_launcher_builds_deep_link(
    tmp_path,
    monkeypatch,
):
    registry = ActionRegistry(id_factory=lambda: "act_zotero")
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[
            HubResource(
                resource_id="paper:one",
                kind="paper",
                zotero={"item_key": "ABCD2345"},
            )
        ],
        topics=[],
        artifacts=[],
    )
    public = register_zotero_actions(catalog, registry)
    calls = []
    monkeypatch.setenv("SCHOLAR_WORKFLOW_NOTION_TOKEN", "must-not-reach-child")

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed(argv)

    action = public["paper:one"][0]
    assert action.kind is ActionKind.ZOTERO_ITEM
    assert action.workspace_policy is WorkspacePolicy.NONE
    assert "ABCD2345" not in repr(action)
    result = ZoteroLauncher(runner=runner).open(registry.resolve(action.id).target)

    assert result.opened is True
    assert calls[0][0] == [
        "/usr/bin/open",
        "zotero://select/library/items/ABCD2345",
    ]
    assert calls[0][1]["shell"] is False
    assert "SCHOLAR_WORKFLOW_NOTION_TOKEN" not in calls[0][1]["env"]


def test_zotero_launcher_rejects_non_catalog_key_before_process_start():
    calls = []
    with pytest.raises(InvalidActionTarget):
        ZoteroLauncher(runner=lambda *args, **kwargs: calls.append((args, kwargs))).open(
            "https://attacker.example"
        )
    assert calls == []


def test_zotero_launcher_failure_does_not_expose_key_or_deep_link():
    item_key = "ABCD2345"
    uri = f"zotero://select/library/items/{item_key}"

    def runner(argv, **kwargs):
        return _completed(argv, 1, f"could not open {uri}")

    with pytest.raises(ActionError) as error:
        ZoteroLauncher(runner=runner).open(item_key)
    assert item_key not in str(error.value)
    assert "zotero://" not in str(error.value)


def test_codex_action_starts_blank_native_agent_with_fixed_trusted_cwd(tmp_path):
    trusted_cwd = tmp_path / "trusted-project"
    trusted_cwd.mkdir()
    registry = ActionRegistry(id_factory=lambda: "act_codex")
    action = register_codex_action(registry)
    calls = []
    executable, control, workspaces = _workspace_runtime(tmp_path, calls=calls)
    launcher = CodexLauncher(trusted_cwd, workspaces, control=control)

    assert action.kind is ActionKind.CODEX_SESSION
    assert action.workspace_policy is WorkspacePolicy.REQUIRED
    assert str(trusted_cwd) not in repr(action)
    result = launcher.open(registry.resolve(action.id).target, workspace_id="ws_opaque")

    assert result.opened is True
    argv, kwargs = calls[-1]
    assert argv == [
        str(executable),
        "new-surface",
        "--type",
        "agent-session",
        "--provider",
        "codex",
        "--working-directory",
        str(trusted_cwd),
        "--workspace",
        "workspace-raw",
        "--focus",
        "true",
    ]
    assert "--command" not in argv
    assert not any("prompt" in argument.lower() for argument in argv)
    assert not any("danger" in argument.lower() for argument in argv)
    assert kwargs["shell"] is False


def test_codex_launcher_rejects_any_nonblank_registered_target(tmp_path):
    trusted_cwd = tmp_path / "trusted-project"
    trusted_cwd.mkdir()
    calls = []
    _executable_path, control, workspaces = _workspace_runtime(tmp_path, calls=calls)
    launcher = CodexLauncher(trusted_cwd, workspaces, control=control)
    calls_before = len(calls)

    with pytest.raises(InvalidActionTarget, match="blank"):
        launcher.open("codex:run browser prompt", workspace_id="ws_opaque")

    assert len(calls) == calls_before


def test_cmux_control_failure_is_explicit_and_has_no_system_browser_fallback(tmp_path):
    executable = _executable(tmp_path)
    calls = []
    raw_workspace = "12345678-1234-1234-1234-123456789abc"

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed(argv, 9, f"cmux permission denied for {raw_workspace}")

    control = CmuxControl(configured_path=executable, runner=runner)

    with pytest.raises(CmuxControlError, match="workspace control is not permitted") as error:
        control.open(NOTION_URL, workspace_id=raw_workspace)
    assert raw_workspace not in str(error.value)
    assert calls == [
        [
            str(executable),
            "open",
            NOTION_URL,
            "--workspace",
            raw_workspace,
            "--focus",
            "true",
        ]
    ]
    assert all(call[:1] != ["/usr/bin/open"] for call in calls)


def test_cmux_control_redacts_non_uuid_workspace_and_target_from_error(tmp_path):
    executable = _executable(tmp_path)
    raw_workspace = "workspace-private-raw"
    target = "https://www.notion.so/private-page"

    def runner(argv, **kwargs):
        return _completed(
            argv,
            9,
            f"failed for {raw_workspace} while opening {target}",
        )

    control = CmuxControl(configured_path=executable, runner=runner)

    with pytest.raises(CmuxControlError) as error:
        control.open(target, workspace_id=raw_workspace)
    assert raw_workspace not in str(error.value)
    assert target not in str(error.value)


def test_catalog_action_service_registers_only_configured_kinds_and_global_codex():
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[
            HubResource(
                resource_id="paper:one",
                kind="paper",
                zotero={"item_key": "ABCD2345", "attachment_key": "BCDE3456"},
                projections=ProjectionLinks(
                    notion_page_id="01234567-89ab-cdef-0123-456789abcdef"
                ),
            )
        ],
        topics=[],
        artifacts=[],
    )

    class Provider:
        def load(self):
            return catalog

    launcher = object()
    service = CatalogActionService(
        Provider(),
        {
            ActionKind.RESOURCE_CMUX: launcher,
            ActionKind.ZOTERO_ITEM: launcher,
            ActionKind.CODEX_SESSION: launcher,
        },
    )

    actions = service.public_actions()

    assert [action.kind for action in actions["paper:one"]] == [
        ActionKind.RESOURCE_CMUX,
        ActionKind.ZOTERO_ITEM,
    ]
    assert [action.kind for action in actions["__hub__"]] == [ActionKind.CODEX_SESSION]
    assert all(
        action.kind is not ActionKind.NOTION_CMUX
        for group in actions.values()
        for action in group
    )
