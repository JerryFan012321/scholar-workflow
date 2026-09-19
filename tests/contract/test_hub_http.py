"""HTTP contract for the loopback research Hub."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
)
from scholar_workflow.hub.actions import ActionExecutor, ActionKind, ActionRegistry
from scholar_workflow.hub.server import StaticCatalogProvider, start_hub_server


@pytest.fixture()
def hub_server(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    (storage / "S6LZUS6S").mkdir(parents=True)
    (storage / "S6LZUS6S" / "论文.pdf").write_bytes(b"%PDF-1.7\n0123456789")
    vault.mkdir()
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[],
        topics=[],
        artifacts=[],
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
    )
    yield server, server.server_address[1]
    server.shutdown()
    server.server_close()


def _request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    headers=None,
    data: bytes | None = None,
):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        headers=headers or {},
        data=data,
    )
    return urllib.request.urlopen(request)


def test_hub_shell_and_catalog_are_served_with_security_headers(hub_server):
    _server, port = hub_server
    page = _request(port, "/hub/")
    assert b"Scholar Workflow" in page.read()
    assert page.headers["Content-Security-Policy"]
    assert page.headers["X-Content-Type-Options"] == "nosniff"

    response = _request(port, "/api/v1/catalog")
    payload = json.loads(response.read())
    assert payload["schema_version"] == 1
    assert "Access-Control-Allow-Origin" not in response.headers

    health = json.loads(_request(port, "/api/v1/health").read())
    assert health == {
        "status": "ok",
        "schema_version": 1,
        "capabilities": ["cmux-workspace-actions-v1"],
    }


def test_hub_static_ui_keeps_editing_and_attachments_secondary(hub_server):
    _server, port = hub_server
    html = _request(port, "/hub/").read().decode("utf-8")
    script = _request(port, "/hub/assets/hub.js").read().decode("utf-8")

    assert 'id="preview-editor-layout"' in html
    assert 'id="preview-live-content"' in html
    assert '<details class="attachment-slot">' in html
    assert '<details class="attachment-slot" open' not in html
    assert "innerHTML" not in script
    assert "renderReadable" in script
    assert "renderTable" in script
    assert 'node("strong")' in script


def test_hub_static_ui_exposes_workspace_target_without_eager_actions(hub_server):
    _server, port = hub_server
    html = _request(port, "/hub/").read().decode("utf-8")
    script = _request(port, "/hub/assets/hub.js").read().decode("utf-8")

    assert 'id="workspace-select"' in html
    assert 'id="cmux-status"' in html
    assert 'id="hub-actions"' in html
    assert "/api/v1/cmux/workspaces" in script
    assert 'state.actions["__hub__"]' in script
    assert "window.confirm" in script
    assert "启动空白 Codex" in script
    assert "pdfLink" not in script
    boot_source = script.split("async function boot()", 1)[1].split(
        "document.querySelector", 1
    )[0]
    assert 'method: "POST"' not in boot_source


def test_pdf_supports_head_and_single_byte_range(hub_server):
    _server, port = hub_server
    head = _request(port, "/open/paper/S6LZUS6S", method="HEAD")
    assert head.status == 200
    assert head.headers["Content-Type"] == "application/pdf"
    assert head.read() == b""

    partial = _request(
        port,
        "/open/paper/S6LZUS6S",
        headers={"Range": "bytes=0-7"},
    )
    assert partial.status == 206
    assert partial.headers["Content-Range"].startswith("bytes 0-7/")
    assert partial.read() == b"%PDF-1.7"


@pytest.mark.parametrize("path", ["/open/paper/../PASSWD", "/open/paper/abc123"])
def test_pdf_route_rejects_unsafe_keys(hub_server, path):
    _server, port = hub_server
    with pytest.raises(urllib.error.HTTPError) as error:
        _request(port, path)
    assert error.value.code in {400, 404}


def test_options_and_cross_origin_requests_are_rejected(hub_server):
    _server, port = hub_server
    with pytest.raises(urllib.error.HTTPError) as options_error:
        _request(port, "/api/v1/catalog", method="OPTIONS")
    assert options_error.value.code == 405

    with pytest.raises(urllib.error.HTTPError) as origin_error:
        _request(
            port,
            "/api/v1/catalog",
            headers={"Origin": "https://attacker.example"},
        )
    assert origin_error.value.code == 403


def test_action_surface_exposes_only_opaque_id_and_rejects_client_target(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    registry = ActionRegistry(id_factory=lambda: "act_public_only")
    public = registry.register(
        kind=ActionKind.NOTION_CMUX,
        label="在 cmux 中打开 Notion",
        target="https://www.notion.so/0123456789abcdef0123456789abcdef",
    )
    seen = []

    class Launcher:
        def open(self, target):
            seen.append(target)
            return {"opened": True}

    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[],
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
        action_executor=ActionExecutor(registry, {ActionKind.NOTION_CMUX: Launcher()}),
        public_actions={"manual": [public]},
    )
    try:
        port = server.server_address[1]
        action_payload = json.loads(_request(port, "/api/v1/actions").read())
        action_text = json.dumps(action_payload)
        assert "act_public_only" in action_text
        assert "https://" not in action_text
        assert "target" not in action_text

        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/actions/act_public_only",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Scholar-Hub-Token": token,
                "Origin": f"http://127.0.0.1:{port}",
            },
        )
        assert json.loads(urllib.request.urlopen(request).read()) == {"opened": True}
        assert seen == ["https://www.notion.so/0123456789abcdef0123456789abcdef"]

        bad = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/actions/act_public_only",
            data=b'{"url":"https://attacker.example"}',
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Scholar-Hub-Token": token,
                "Origin": f"http://127.0.0.1:{port}",
            },
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(bad)
        assert error.value.code == 400
        assert len(seen) == 1

        missing_origin = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/actions/act_public_only",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Scholar-Hub-Token": token,
            },
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(missing_origin)
        assert error.value.code == 403
        assert len(seen) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_cmux_workspaces_and_workspace_scoped_actions_use_only_opaque_ids(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[],
    )

    @dataclass(frozen=True)
    class PublicWorkspace:
        id: str
        label: str
        is_current: bool
        contains_hub: bool

    @dataclass(frozen=True)
    class WorkspaceListing:
        workspaces: tuple[PublicWorkspace, ...]
        capability_error: str | None

    workspace_action = SimpleNamespace(
        id="act_open",
        label="在 cmux 中查看",
        kind=SimpleNamespace(value="resource.cmux"),
        workspace_policy=SimpleNamespace(value="required"),
    )
    local_action = SimpleNamespace(
        id="act_obsidian",
        label="在 Obsidian 中编辑",
        kind=SimpleNamespace(value="obsidian.note"),
        workspace_policy=SimpleNamespace(value="none"),
    )

    class ActionService:
        def __init__(self):
            self.calls = []
            self.instance_tokens = []

        def public_actions(self):
            return {"paper:one": [workspace_action, local_action]}

        def public_workspaces(self, *, instance_token=None):
            self.instance_tokens.append(instance_token)
            return WorkspaceListing(
                workspaces=(
                    PublicWorkspace("ws_current", "Research", True, True),
                    PublicWorkspace("ws_other", "Reading", False, False),
                ),
                capability_error=None,
            )

        def execute(self, action_id, *, workspace_id=None):
            self.calls.append((action_id, workspace_id))
            return {"ok": True}

    action_service = ActionService()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
        action_service=action_service,
    )
    try:
        port = server.server_address[1]
        listing = json.loads(_request(port, "/api/v1/cmux/workspaces").read())
        assert listing == {
            "capabilities": {"workspace_actions": True},
            "workspaces": [
                {
                    "id": "ws_current",
                    "label": "Research",
                    "is_current": True,
                    "contains_hub": True,
                },
                {
                    "id": "ws_other",
                    "label": "Reading",
                    "is_current": False,
                    "contains_hub": False,
                },
            ],
            "capability_error": None,
        }
        assert "raw-workspace-uuid" not in json.dumps(listing)
        assert action_service.instance_tokens == [None]

        _request(
            port,
            "/api/v1/cmux/workspaces?instance=Hub_run-1234",
        ).read()
        assert action_service.instance_tokens == [None, "Hub_run-1234"]

        for path in (
            "/api/v1/cmux/workspaces?instance=short",
            "/api/v1/cmux/workspaces?instance=Hub_run-1234&workspace=raw",
            "/api/v1/cmux/workspaces?instance=Hub.run.1234",
            "/api/v1/cmux/workspaces?instance=one&instance=two",
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                _request(port, path)
            assert error.value.code == 400
        assert action_service.instance_tokens == [None, "Hub_run-1234"]

        actions = json.loads(_request(port, "/api/v1/actions").read())
        assert actions["paper:one"][0]["workspace_policy"] == "required"
        assert actions["paper:one"][1]["workspace_policy"] == "none"

        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        response = _post_action(
            port,
            "act_open",
            {"workspace_id": "ws_other"},
            token=token,
        )
        assert json.loads(response.read()) == {"ok": True}
        assert action_service.calls == [("act_open", "ws_other")]
    finally:
        server.shutdown()
        server.server_close()


def _post_action(port: int, action_id: str, payload, *, token: str, origin=True):
    headers = {
        "Content-Type": "application/json",
        "X-Scholar-Hub-Token": token,
    }
    if origin:
        headers["Origin"] = f"http://127.0.0.1:{port}"
    return _request(
        port,
        f"/api/v1/actions/{urllib.parse.quote(action_id, safe='')}",
        method="POST",
        headers=headers,
        data=json.dumps(payload).encode("utf-8"),
    )


def test_action_request_shape_and_workspace_policy_are_enforced(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[],
    )
    selectable = SimpleNamespace(
        id="act_cmux",
        label="在 cmux 中查看",
        kind=SimpleNamespace(value="resource.cmux"),
        workspace_policy=SimpleNamespace(value="required"),
    )
    local = SimpleNamespace(
        id="act_local",
        label="在 Zotero 中编辑",
        kind=SimpleNamespace(value="zotero.item"),
        workspace_policy=SimpleNamespace(value="none"),
    )

    class ActionService:
        def __init__(self):
            self.calls = []

        def public_actions(self):
            return {"paper:one": [selectable, local]}

        def public_workspaces(self):
            return {"workspaces": [], "capability_error": "cmux is not running"}

        def execute(self, action_id, *, workspace_id=None):
            self.calls.append((action_id, workspace_id))
            return {"ok": True}

    service = ActionService()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
        action_service=service,
    )
    try:
        port = server.server_address[1]
        unavailable = json.loads(_request(port, "/api/v1/cmux/workspaces").read())
        assert unavailable["capabilities"] == {"workspace_actions": False}
        assert unavailable["capability_error"] == "cmux is not running"
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]

        for action_id, payload in (
            ("act_cmux", {"workspace_id": "ws_one", "command": "codex"}),
            ("act_cmux", {"workspace_id": ""}),
            ("act_cmux", {"workspace_id": None}),
            ("act_cmux", []),
            ("act_cmux", {}),
            ("act_local", {"workspace_id": "ws_one"}),
            ("act_local", {"workspace_id": None}),
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                _post_action(port, action_id, payload, token=token)
            assert error.value.code == 400

        assert service.calls == []
        assert json.loads(
            _post_action(port, "act_local", {}, token=token).read()
        ) == {"ok": True}
        assert service.calls == [("act_local", None)]
    finally:
        server.shutdown()
        server.server_close()


def test_codex_action_is_global_and_only_registered_for_explicit_trusted_cwd(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    project = tmp_path / "trusted-project"
    storage.mkdir()
    vault.mkdir()
    project.mkdir()
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[],
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
        codex_working_directory=project,
    )
    try:
        port = server.server_address[1]
        actions = json.loads(_request(port, "/api/v1/actions").read())
        assert list(actions) == ["__hub__"]
        assert len(actions["__hub__"]) == 1
        assert actions["__hub__"][0]["kind"] == "codex.session"
        assert actions["__hub__"][0]["workspace_policy"] == "required"
        assert str(project) not in json.dumps(actions)
    finally:
        server.shutdown()
        server.server_close()


def test_action_surface_refreshes_when_live_catalog_revision_changes(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()

    class MutableCatalogProvider:
        def __init__(self, catalog):
            self.catalog = catalog

        def load(self):
            return self.catalog

    empty = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[],
    )
    provider = MutableCatalogProvider(empty)
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=provider,
    )
    try:
        port = server.server_address[1]
        assert json.loads(_request(port, "/api/v1/actions").read()) == {}

        note = vault / "研究" / "新笔记.md"
        note.parent.mkdir()
        note.write_text("# New\n", encoding="utf-8")
        artifact = HubArtifact(
            artifact_id="note:new",
            kind=ArtifactKind.READING_NOTE,
            format=ArtifactFormat.MARKDOWN,
            vault_path="研究/新笔记.md",
        )
        provider.catalog = HubCatalog(
            generated_at=empty.generated_at,
            resources=[], topics=[], artifacts=[artifact],
        )

        actions = json.loads(_request(port, "/api/v1/actions").read())
        assert list(actions) == ["note:new"]
        assert {
            (action["kind"], action["workspace_policy"])
            for action in actions["note:new"]
        } == {
            ("artifact.cmux", "required"),
            ("obsidian.note", "none"),
        }
        assert "新笔记.md" not in json.dumps(actions, ensure_ascii=False)
    finally:
        server.shutdown()
        server.server_close()


def test_artifact_preview_reads_only_catalog_registered_vault_file(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    note = vault / "世界模型" / "分析.md"
    note.parent.mkdir(parents=True)
    body = "# 人类可读标题\n\n<script>不应作为 HTML 执行</script>\n"
    note.write_text(body, encoding="utf-8")
    artifact = HubArtifact(
        artifact_id="analysis:world-models",
        kind=ArtifactKind.PAPER_ANALYSIS,
        format=ArtifactFormat.MARKDOWN,
        vault_path="世界模型/分析.md",
    )
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[artifact],
    )
    server = start_hub_server(
        port=0, storage_root=storage, vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
    )
    try:
        port = server.server_address[1]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        response = _request(port, f"/api/v1/artifacts/{encoded}/content")
        payload = json.loads(response.read())
        assert payload["content"] == body
        assert payload["vault_path"] == "世界模型/分析.md"
        assert payload["revision"].startswith("sha256:")
        with pytest.raises(urllib.error.HTTPError) as error:
            _request(port, "/api/v1/artifacts/unknown/content")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def _editable_hub(tmp_path, *, artifact_format=ArtifactFormat.MARKDOWN, suffix=".md"):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    note = vault / "研究" / f"内容{suffix}"
    note.parent.mkdir(parents=True)
    initial = "# 人类标题\n\n正文保持原样。\n"
    if artifact_format == ArtifactFormat.CANVAS:
        initial = '{"nodes":[],"edges":[]}\n'
    note.write_text(initial, encoding="utf-8")
    artifact = HubArtifact(
        artifact_id="artifact:editable",
        kind=(
            ArtifactKind.ANALYSIS_CANVAS
            if artifact_format == ArtifactFormat.CANVAS
            else ArtifactKind.PAPER_ANALYSIS
        ),
        format=artifact_format,
        vault_path=f"研究/内容{suffix}",
    )
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[],
        topics=[],
        artifacts=[artifact],
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
    )
    return server, note, artifact


def _put_content(port: int, artifact_id: str, payload: dict, *, token: str, origin=True):
    encoded = urllib.parse.quote(artifact_id, safe="")
    headers = {
        "Content-Type": "application/json",
        "X-Scholar-Hub-Token": token,
    }
    if origin:
        headers["Origin"] = f"http://127.0.0.1:{port}"
    return _request(
        port,
        f"/api/v1/artifacts/{encoded}/content",
        method="PUT",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def test_registered_markdown_can_be_saved_verbatim_with_revision_check(tmp_path):
    server, note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        before = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded}/content").read()
        )
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        updated = "---\ntitle: 人类字段\n---\n# 人类标题\n\n编辑后的正文。  \n"

        response = _put_content(
            port,
            artifact.artifact_id,
            {"content": updated, "base_revision": before["revision"]},
            token=token,
        )
        payload = json.loads(response.read())

        assert note.read_text(encoding="utf-8") == updated
        assert payload["content"] == updated
        assert payload["revision"].startswith("sha256:")
        assert payload["revision"] != before["revision"]
    finally:
        server.shutdown()
        server.server_close()


def test_managed_markdown_preserves_identity_and_projector_revision(tmp_path):
    server, note, artifact = _editable_hub(tmp_path)
    managed = (
        "---\n"
        "title: 人类标题\n"
        "sw_schema: 1\n"
        "sw_kind: paper-analysis\n"
        "sw_catalog_id: artifact:editable\n"
        "sw_revision: sha256:old\n"
        "---\n"
        "# 原正文\n"
    )
    note.write_text(managed, encoding="utf-8")
    try:
        port = server.server_address[1]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        before = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded}/content").read()
        )
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        proposed = managed.replace("# 原正文\n", "# 新正文\n\n人类内容保持可读。\n")

        response = _put_content(
            port,
            artifact.artifact_id,
            {"content": proposed, "base_revision": before["revision"]},
            token=token,
        )
        saved = json.loads(response.read())["content"]

        assert "sw_catalog_id: artifact:editable" in saved
        assert "sw_revision: sha256:old" in saved
        assert saved.endswith("# 新正文\n\n人类内容保持可读。\n")
        assert note.read_text(encoding="utf-8") == saved
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text: text.replace("sw_catalog_id: artifact:editable\n", ""),
        lambda text: text.replace(
            "sw_catalog_id: artifact:editable",
            "sw_catalog_id: artifact:other",
        ),
        lambda text: text.replace("sw_schema: 1", "sw_schema: 1\nsw_unknown: injected"),
        lambda text: text.replace("sw_revision: sha256:old", "sw_revision: chosen-by-client"),
    ],
)
def test_managed_markdown_rejects_client_changes_to_sw_fields(tmp_path, mutate):
    server, note, artifact = _editable_hub(tmp_path)
    managed = (
        "---\n"
        "sw_schema: 1\n"
        "sw_kind: paper-analysis\n"
        "sw_catalog_id: artifact:editable\n"
        "sw_revision: sha256:old\n"
        "---\n"
        "# 正文\n"
    )
    note.write_text(managed, encoding="utf-8")
    try:
        port = server.server_address[1]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        before = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded}/content").read()
        )
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]

        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {
                    "content": mutate(managed).replace("# 正文", "# 新正文"),
                    "base_revision": before["revision"],
                },
                token=token,
            )
        assert error.value.code == 422
        assert note.read_text(encoding="utf-8") == managed
    finally:
        server.shutdown()
        server.server_close()


def test_stale_revision_returns_409_without_overwriting(tmp_path):
    server, note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        original = note.read_text(encoding="utf-8")
        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {"content": "不应写入\n", "base_revision": "sha256:stale"},
                token=token,
            )
        assert error.value.code == 409
        assert note.read_text(encoding="utf-8") == original
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"origin": True, "token": "wrong"}, 403),
        ({"origin": False, "token": "valid"}, 403),
    ],
)
def test_artifact_write_requires_csrf_and_explicit_same_origin(tmp_path, headers, expected):
    server, _note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        session = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        current = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded}/content").read()
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {"content": "blocked", "base_revision": current["revision"]},
                token=session if headers["token"] == "valid" else headers["token"],
                origin=headers["origin"],
            )
        assert error.value.code == expected
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("content", ["[]", "null", "not json"])
def test_canvas_write_requires_a_json_object(tmp_path, content):
    server, note, artifact = _editable_hub(
        tmp_path, artifact_format=ArtifactFormat.CANVAS, suffix=".canvas"
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        current = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded}/content").read()
        )
        original = note.read_text(encoding="utf-8")
        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {"content": content, "base_revision": current["revision"]},
                token=token,
            )
        assert error.value.code == 422
        assert note.read_text(encoding="utf-8") == original
    finally:
        server.shutdown()
        server.server_close()


def test_write_never_creates_unknown_or_missing_registered_file(tmp_path):
    server, note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        note.unlink()
        for artifact_id in (artifact.artifact_id, "artifact:unknown"):
            with pytest.raises(urllib.error.HTTPError) as error:
                _put_content(
                    port,
                    artifact_id,
                    {"content": "must not exist", "base_revision": "sha256:any"},
                    token=token,
                )
            assert error.value.code == 404
        assert not note.exists()
    finally:
        server.shutdown()
        server.server_close()


def test_write_rejects_symlink_even_when_target_stays_inside_vault(tmp_path):
    server, note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        target = note.with_name("真实文件.md")
        note.rename(target)
        note.symlink_to(target.name)

        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {"content": "must not write", "base_revision": "sha256:any"},
                token=token,
            )
        assert error.value.code == 403
        assert target.read_text(encoding="utf-8").startswith("# 人类标题")
    finally:
        server.shutdown()
        server.server_close()


def test_write_rejects_oversized_content_before_replacing_file(tmp_path):
    server, note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        encoded = urllib.parse.quote(artifact.artifact_id, safe="")
        before = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded}/content").read()
        )
        original = note.read_text(encoding="utf-8")

        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {
                    "content": "x" * (2 * 1024 * 1024 + 1),
                    "base_revision": before["revision"],
                },
                token=token,
            )
        assert error.value.code == 413
        assert note.read_text(encoding="utf-8") == original
    finally:
        server.shutdown()
        server.server_close()


def test_write_rejects_catalog_path_escape_even_if_validation_was_bypassed(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    artifact = HubArtifact.model_construct(
        artifact_id="artifact:escape",
        kind=ArtifactKind.PAPER_ANALYSIS,
        format=ArtifactFormat.MARKDOWN,
        vault_path="../outside.md",
        resource_id=None,
        topic_id=None,
        parent_id=None,
        tree_kind=None,
        revision=None,
    )
    catalog = HubCatalog.model_construct(
        schema_version=1,
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        revision="test",
        sources=[],
        resources=[],
        topics=[],
        artifacts=[artifact],
        diagnostics=[],
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(catalog),
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        with pytest.raises(urllib.error.HTTPError) as error:
            _put_content(
                port,
                artifact.artifact_id,
                {"content": "must not write", "base_revision": "sha256:any"},
                token=token,
            )
        assert error.value.code == 403
        assert outside.read_text(encoding="utf-8") == "outside\n"
    finally:
        server.shutdown()
        server.server_close()


def _post_asset(
    port: int,
    artifact_id: str,
    name: str,
    content: bytes,
    *,
    token: str,
    role: str = "supplement",
    origin: bool = True,
    extra_query: str = "",
):
    encoded_id = urllib.parse.quote(artifact_id, safe="")
    query = urllib.parse.urlencode({"name": name, "role": role}) + extra_query
    headers = {
        "Content-Type": "application/octet-stream",
        "X-Scholar-Hub-Token": token,
    }
    if origin:
        headers["Origin"] = f"http://127.0.0.1:{port}"
    return _request(
        port,
        f"/api/v1/artifacts/{encoded_id}/assets?{query}",
        method="POST",
        headers=headers,
        data=content,
    )


def test_vault_asset_upload_list_and_read_are_bound_to_registered_artifact(tmp_path):
    server, _note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        first = json.loads(
            _post_asset(
                port,
                artifact.artifact_id,
                "方法概览.png",
                b"png-one",
                token=token,
                role="embed",
            ).read()
        )
        second = json.loads(
            _post_asset(
                port,
                artifact.artifact_id,
                "方法概览.png",
                b"png-two",
                token=token,
                role="embed",
            ).read()
        )

        assert first["vault_path"].endswith("/方法概览.png")
        assert second["vault_path"].endswith("/方法概览-2.png")
        assert first["obsidian_link"] == f"![[{first['vault_path']}]]"
        assert first["content_url"].startswith("/api/v1/assets/")
        manifest = tmp_path / "vault" / ".scholar-workflow" / "assets.yml"
        assert "方法概览.png" in manifest.read_text(encoding="utf-8")

        encoded_artifact = urllib.parse.quote(artifact.artifact_id, safe="")
        listed = json.loads(
            _request(port, f"/api/v1/artifacts/{encoded_artifact}/assets").read()
        )
        assert {row["asset_id"] for row in listed["assets"]} == {
            first["asset_id"],
            second["asset_id"],
        }

        content = _request(port, first["content_url"])
        assert content.headers["Content-Type"] == "image/png"
        assert content.headers["Content-Disposition"].startswith("inline;")
        assert content.read() == b"png-one"
        head = _request(port, first["content_url"], method="HEAD")
        assert head.headers["Content-Length"] == str(len(b"png-one"))
        assert head.read() == b""
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("artifact_id", "name", "token_mode", "origin", "extra_query", "status"),
    [
        ("artifact:missing", "safe.txt", "valid", True, "", 404),
        ("artifact:editable", "../escape.txt", "valid", True, "", 422),
        ("artifact:editable", "safe.txt", "wrong", True, "", 403),
        ("artifact:editable", "safe.txt", "valid", False, "", 403),
        ("artifact:editable", "safe.txt", "valid", True, "&destination=/tmp", 400),
    ],
)
def test_vault_asset_upload_rejects_unregistered_or_client_chosen_targets(
    tmp_path,
    artifact_id,
    name,
    token_mode,
    origin,
    extra_query,
    status,
):
    server, _note, _artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        valid = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        with pytest.raises(urllib.error.HTTPError) as error:
            _post_asset(
                port,
                artifact_id,
                name,
                b"content",
                token=valid if token_mode == "valid" else "wrong",
                origin=origin,
                extra_query=extra_query,
            )
        assert error.value.code == status
        attachment_root = tmp_path / "vault" / "attachments"
        assert not attachment_root.exists()
    finally:
        server.shutdown()
        server.server_close()


def test_unsafe_asset_types_download_instead_of_inline(tmp_path):
    server, _note, artifact = _editable_hub(tmp_path)
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        uploaded = json.loads(
            _post_asset(
                port,
                artifact.artifact_id,
                "page.html",
                b"<script>alert(1)</script>",
                token=token,
            ).read()
        )

        response = _request(port, uploaded["content_url"])
        assert response.headers["Content-Type"] == "text/html"
        assert response.headers["Content-Disposition"].startswith("attachment;")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        server.shutdown()
        server.server_close()
