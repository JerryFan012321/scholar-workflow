"""Public Field transaction routes separate browser preview from local commits."""

from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.legacy_canvas_migration import (
    LegacyCanvasElementMapping,
    LegacyCanvasMigrationPlan,
    inventory_legacy_canvas,
)
from scholar_workflow.analysis.legacy_migration import (
    LegacyFieldMapping,
    LegacyFragment,
    LegacyMigrationPlan,
    LegacyTarget,
    parse_legacy_fields,
)
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.cli import main
from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.field_transaction import FieldTransactionService
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.hub.models import HubCatalog
from scholar_workflow.hub.server import start_hub_server


class _Picker:
    def __init__(self, path: Path) -> None:
        self.path = path

    def choose(self) -> Path:
        return self.path


def _request(
    port: int,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    encoded = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method="POST" if encoded is not None else "GET",
        data=encoded,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        content = exc.read()
        try:
            return exc.code, json.loads(content)
        except json.JSONDecodeError:
            return exc.code, {"error": content.decode("utf-8", errors="replace")}


@pytest.fixture
def field_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    field = vault / "世界模型"
    field.mkdir()
    source = field / "00-领域入口.md"
    source.write_text("# 世界模型\n", encoding="utf-8")
    storage = tmp_path / "storage"
    storage.mkdir()
    runtime_dir = home / "runtime"
    runtime_dir.mkdir(parents=True, mode=0o700)
    runtime_dir.chmod(0o700)
    generation = "service_" + "a" * 32
    field_service = FieldService(KnowledgeSourceRegistry(home / "hub" / "sources.json"))
    transaction = FieldTransactionService(
        field_service,
        state_root=runtime_dir / "field-transactions-private",
        link_resolver=lambda key: f"zotero://open-pdf/library/items/{key}",
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(
            HubCatalog(generated_at=datetime(2026, 9, 27, tzinfo=UTC), resources=[])
        ),
        field_service=field_service,
        field_transaction_service=transaction,
        folder_picker=_Picker(vault),
        service_generation=generation,
        log_path=runtime_dir / "hub.log",
    )
    try:
        yield server, source, field_service, transaction, runtime_dir, generation
    finally:
        server.shutdown()
        server.server_close()


def _browser_headers(port: int) -> dict[str, str]:
    _, session = _request(port, "/api/v1/session")
    return {
        "Content-Type": "application/json",
        "Origin": f"http://127.0.0.1:{port}",
        "X-Scholar-Hub-Token": str(session["csrf_token"]),
    }


def _fake_managed_status(monkeypatch, port: int, runtime_dir: Path, generation: str) -> None:
    from scholar_workflow.hub.lifecycle import HubStatus

    class _Manager:
        def status(self):
            record = type(
                "Record",
                (),
                {
                    "port": port,
                    "pid": os.getpid(),
                    "service_generation": generation,
                    "log_path": str(runtime_dir / "hub.log"),
                },
            )()
            return HubStatus(True, record, {}, "running")

    monkeypatch.setattr("scholar_workflow.hub.lifecycle.HubServiceManager", _Manager)


def _legacy_package(source_markdown: bytes, source_canvas: bytes) -> dict[str, object]:
    note_stem = "Fixture Paper分析"
    document = AnalysisDocument.model_validate(
        {
            "schema_version": 4,
            "artifact_id": "analysis:fixture-paper",
            "paper_title": "Fixture Paper",
            "language": "en",
            "profile": {"kind": "whole", "framework": "reference_tree"},
            "claims": [
                {
                    "claim_id": "task",
                    "role": "abstract",
                    "outline_path": "abstract/task",
                    "title": "Task",
                    "body": "Original task statement",
                    "evidence": {
                        "kind": "author_stated",
                        "anchor": "§1",
                        "source_spans": [
                            {
                                "kind": "zotero_pdf",
                                "library_type": "personal",
                                "library_id": "17685951",
                                "attachment_key": "QR4ZU2S9",
                                "content_hash": "md5:" + "a" * 32,
                                "page_index": 0,
                            }
                        ],
                    },
                }
            ],
        }
    )
    rendered = render_analysis(document, note_stem=note_stem)
    candidate_canvas = deepcopy(rendered.canvas)
    candidate_canvas["nodes"].extend(json.loads(source_canvas)["nodes"])
    canvas_bytes = (
        json.dumps(candidate_canvas, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    old_field = parse_legacy_fields(source_markdown)[0]
    markdown_plan = LegacyMigrationPlan(
        source_sha256=sha256(source_markdown).hexdigest(),
        expected_field_count=1,
        mappings=(
            LegacyFieldMapping(
                "task",
                old_field.sha256,
                (
                    LegacyFragment(
                        0, len(old_field.content), old_field.sha256, "copy", LegacyTarget("task")
                    ),
                ),
            ),
        ),
        split_targets={},
    )
    canvas_plan = LegacyCanvasMigrationPlan(
        source_sha256=sha256(source_canvas).hexdigest(),
        candidate_sha256=sha256(canvas_bytes).hexdigest(),
        mappings=tuple(
            LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "preserve")
            for row in inventory_legacy_canvas(source_canvas)
        ),
    )
    return {
        "schema_version": 1,
        "markdown_path": "Fixture Paper分析.md",
        "canvas_path": "Fixture Paper解析树.canvas",
        "sidecar_path": "Fixture Paper分析.analysis.json",
        "document": document.model_dump(mode="json"),
        "bundle": {"markdown": rendered.markdown, "canvas": candidate_canvas},
        "markdown_plan": asdict(markdown_plan),
        "canvas_plan": asdict(canvas_plan),
    }


def _install_legacy_pair(source: Path) -> tuple[bytes, bytes]:
    visible = b"Original task statement"
    markdown = (
        visible
        + b"\n"
        + f'<!-- sw-analysis-field path="task" base_sha256="{sha256(visible).hexdigest()}" -->\n'.encode()
    )
    canvas = (
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "user-owned-note",
                        "type": "text",
                        "text": "Keep this personal note",
                        "x": 10000,
                        "y": 10000,
                        "width": 400,
                        "height": 200,
                        "color": "4",
                    }
                ],
                "edges": [],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode()
    (source.parent / "Fixture Paper分析.md").write_bytes(markdown)
    (source.parent / "Fixture Paper解析树.canvas").write_bytes(canvas)
    return markdown, canvas


def test_browser_plan_is_read_only_and_cannot_assert_writer_pause(field_server) -> None:
    server, source, service, transaction, runtime_dir, generation = field_server
    port = server.server_address[1]
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    field = preview["fields"][0]
    status, planned = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={"candidate_token": preview["candidate_token"], "field_id": field["field_id"]},
        headers=headers,
    )
    assert status == 200
    plan = planned["plan"]
    assert plan["plan_digest"].startswith("sha256:")
    assert plan["analysis_conformance"] == "not-evaluated"
    assert not service.registry.path.exists()
    assert not (source.parents[1] / ".scholar-workflow" / "fields.yml").exists()
    assert not transaction.state_root.exists()

    status, _rejected_relocation = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={
            "candidate_token": preview["candidate_token"],
            "field_id": field["field_id"],
            "relocations": {"00-领域入口.md": "resources/papers/x/00-领域入口.md"},
        },
        headers=headers,
    )
    assert status == 400
    assert not transaction.state_root.exists()

    status, rejected = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={
            "candidate_token": preview["candidate_token"],
            "field_id": field["field_id"],
            "staged_bundle": {"JEPA.md": "arbitrary browser bytes"},
        },
        headers=headers,
    )
    assert status == 400
    assert "candidate_token" in rejected["error"]

    status, _ = _request(
        port,
        "/api/v3/field-transactions/apply",
        payload={
            "plan_token": plan["plan_token"],
            "approved_digest": plan["plan_digest"],
            "external_writers_paused": True,
        },
        headers=headers,
    )
    assert status in {400, 403}
    status, _ = _request(
        port,
        "/api/v3/field-transactions/apply",
        payload={"plan_token": plan["plan_token"], "approved_digest": plan["plan_digest"]},
        headers=headers,
    )
    assert status == 403
    assert not service.registry.path.exists()
    credential = runtime_dir / "field-operator.json"
    assert credential.is_file()
    assert stat.S_IMODE(credential.stat().st_mode) == 0o600
    assert json.loads(credential.read_text())["service_generation"] == generation
    assert "operator_token" not in json.dumps(planned)
    for public_path in ("/api/v1/session", "/api/v3/identity", "/api/v3/health"):
        status, public = _request(port, public_path)
        assert status == 200
        assert json.loads(credential.read_text())["token"] not in json.dumps(public)


def test_operator_apply_and_recover_are_generation_bound(field_server) -> None:
    server, _source, service, _transaction, runtime_dir, _generation = field_server
    port = server.server_address[1]
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    _, planned = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={
            "candidate_token": preview["candidate_token"],
            "field_id": preview["fields"][0]["field_id"],
        },
        headers=headers,
    )
    plan = planned["plan"]
    status, _ = _request(
        port,
        "/api/v3/field-transactions/recover",
        payload={"source_id": plan["source_id"], "field_id": plan["field_id"]},
        headers=headers,
    )
    assert status == 403
    credential = json.loads((runtime_dir / "field-operator.json").read_text())
    operator_headers = {**headers, "X-Scholar-Hub-Operator": credential["token"]}
    status, applied = _request(
        port,
        "/api/v3/field-transactions/apply",
        payload={"plan_token": plan["plan_token"], "approved_digest": plan["plan_digest"]},
        headers=operator_headers,
    )
    assert status == 200, applied
    assert applied["result"]["recovery_is_verified_backup"] is False
    assert service.registry.path.is_file()
    status, recovered = _request(
        port,
        "/api/v3/field-transactions/recover",
        payload={"source_id": plan["source_id"], "field_id": plan["field_id"]},
        headers=operator_headers,
    )
    assert status == 400
    assert "external_writers_paused" in recovered["error"]
    status, recovered = _request(
        port,
        "/api/v3/field-transactions/recover",
        payload={
            "source_id": plan["source_id"],
            "field_id": plan["field_id"],
            "external_writers_paused": False,
        },
        headers=operator_headers,
    )
    assert status == 409
    assert "writers must be paused" in recovered["error"]
    status, recovered = _request(
        port,
        "/api/v3/field-transactions/recover",
        payload={
            "source_id": plan["source_id"],
            "field_id": plan["field_id"],
            "external_writers_paused": True,
        },
        headers=operator_headers,
    )
    assert status == 200
    assert recovered["result"]["outcome"] == "nothing-to-recover"
    server.shutdown()
    server.server_close()
    assert not (runtime_dir / "field-operator.json").exists()


def test_cli_rejects_stale_or_unsafe_operator_credential(field_server, monkeypatch) -> None:
    server, _source, service, _transaction, runtime_dir, generation = field_server
    port = server.server_address[1]
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    _, planned = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={
            "candidate_token": preview["candidate_token"],
            "field_id": preview["fields"][0]["field_id"],
        },
        headers=headers,
    )
    plan = planned["plan"]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    credential_path = runtime_dir / "field-operator.json"
    credential = json.loads(credential_path.read_text())
    credential["service_generation"] = "service_" + "b" * 32
    credential_path.write_text(json.dumps(credential))
    credential_path.chmod(0o600)
    result = CliRunner().invoke(
        main,
        [
            "hub",
            "field-transaction",
            "apply",
            plan["plan_token"],
            "--approved-digest",
            plan["plan_digest"],
            "--external-writers-paused",
        ],
        input="y\n",
    )
    assert result.exit_code == 7
    assert "generation" in result.output.lower()
    assert not service.registry.path.exists()


def test_cli_plan_apply_and_conditional_recover(field_server, monkeypatch) -> None:
    server, _source, service, transaction, runtime_dir, generation = field_server
    port = server.server_address[1]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    runner = CliRunner()
    planned = runner.invoke(
        main,
        ["hub", "field-transaction", "plan", "--field-root", "世界模型"],
    )
    assert planned.exit_code == 0, planned.output
    plan = json.loads(planned.output)
    assert plan["field_title"] == "世界模型"
    assert plan["candidate_token"].startswith("fld_")
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()

    missing_pause = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "apply",
            plan["plan_token"],
            "--approved-digest",
            plan["plan_digest"],
        ],
    )
    assert missing_pause.exit_code == 7
    assert not service.registry.path.exists()

    applied = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "apply",
            plan["plan_token"],
            "--approved-digest",
            plan["plan_digest"],
            "--external-writers-paused",
        ],
        input="y\n",
    )
    assert applied.exit_code == 0, applied.output
    result = json.loads(applied.output.splitlines()[-1])
    assert result["source_id"] == plan["source_id"]
    assert result["recovery_is_verified_backup"] is False
    assert service.registry.path.is_file()

    recovered = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "recover",
            plan["source_id"],
            plan["field_id"],
            "--confirm-recovery",
        ],
        input="y\n",
    )
    assert recovered.exit_code == 7
    assert "writers must be paused" in recovered.output
    recovered = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "recover",
            plan["source_id"],
            plan["field_id"],
            "--confirm-recovery",
            "--external-writers-paused",
        ],
        input="y\n",
    )
    assert recovered.exit_code == 0, recovered.output
    assert json.loads(recovered.output.splitlines()[-1])["outcome"] == "nothing-to-recover"


def test_expired_transaction_plan_cannot_commit(field_server, monkeypatch) -> None:
    server, source, service, transaction, runtime_dir, _generation = field_server
    tick = [0.0]
    monkeypatch.setattr(transaction, "_clock", lambda: tick[0])
    monkeypatch.setattr(transaction, "_ttl", 1800.0)
    port = server.server_address[1]
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    status, planned = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={
            "candidate_token": preview["candidate_token"],
            "field_id": preview["fields"][0]["field_id"],
        },
        headers=headers,
    )
    assert status == 200
    plan = planned["plan"]
    credential = json.loads((runtime_dir / "field-operator.json").read_text())
    tick[0] = 1800.01
    status, rejected = _request(
        port,
        "/api/v3/field-transactions/apply",
        payload={"plan_token": plan["plan_token"], "approved_digest": plan["plan_digest"]},
        headers={**headers, "X-Scholar-Hub-Operator": credential["token"]},
    )
    assert status == 409
    assert "expired" in rejected["error"]
    assert not service.registry.path.exists()
    assert not (source.parents[1] / ".scholar-workflow" / "fields.yml").exists()
    assert not transaction.state_root.exists()


def test_default_hub_review_tokens_last_thirty_minutes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    vault = tmp_path / "vault"
    vault.mkdir()
    storage = tmp_path / "storage"
    storage.mkdir()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(
            HubCatalog(generated_at=datetime(2026, 9, 27, tzinfo=UTC), resources=[])
        ),
    )
    try:
        assert server.runtime.field_service.candidates._ttl == 1800
        assert server.runtime.field_transaction_service._ttl == 1800
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("legacy_kind", ["analysis", "analysis-marker", "hub-link"])
def test_legacy_field_cannot_be_confirmed_before_unified_transaction(
    field_server, legacy_kind: str
) -> None:
    server, source, service, transaction, _runtime_dir, _generation = field_server
    if legacy_kind == "analysis":
        _install_legacy_pair(source)
        expected_reason = "legacy_analysis"
    elif legacy_kind == "analysis-marker":
        source.write_text("# 世界模型\n\n<!-- sw-analysis-field: legacy -->\n", encoding="utf-8")
        expected_reason = "legacy_analysis"
    else:
        source.write_text(
            "# 世界模型\n\n[Paper](http://127.0.0.1:23128/open/paper/ABCD2345)\n",
            encoding="utf-8",
        )
        expected_reason = "legacy_hub_link"
    port = server.server_address[1]
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    field_id = preview["fields"][0]["field_id"]
    reasons = preview["transaction_required_fields"][0]["reasons"]
    assert expected_reason in reasons
    status, rejected = _request(
        port,
        "/api/v3/fields/confirm",
        payload={"candidate_token": preview["candidate_token"], "field_id": field_id},
        headers=headers,
    )
    assert status == 409
    assert rejected["code"] == "field_transaction_required"
    assert expected_reason in rejected["reasons"]
    assert not service.registry.path.exists()
    assert not (source.parents[1] / ".scholar-workflow" / "fields.yml").exists()
    assert not transaction.state_root.exists()


@pytest.mark.parametrize("managed_kind", ["kind", "sidecar", "paired"])
def test_managed_analysis_cannot_use_compatibility_field_confirm(
    field_server, managed_kind: str
) -> None:
    server, source, service, transaction, _runtime_dir, _generation = field_server
    paper = source.with_name("Paper.md")
    paper.write_text(
        (
            "---\nsw_kind: paper-analysis\n---\n# Paper\n"
            if managed_kind in {"kind", "paired"}
            else "# Paper\n"
        ),
        encoding="utf-8",
    )
    if managed_kind in {"sidecar", "paired"}:
        source.with_name("Paper.analysis.json").write_text("{}", encoding="utf-8")
    if managed_kind == "paired":
        source.with_name("Paper.canvas").write_text('{"nodes": [], "edges": []}', encoding="utf-8")
    port = server.server_address[1]
    headers = _browser_headers(port)

    status, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)

    assert status == 200
    preview = selected["preview"]
    field_id = preview["fields"][0]["field_id"]
    assert "managed_analysis" in preview["transaction_required_fields"][0]["reasons"]
    status, rejected = _request(
        port,
        "/api/v3/fields/confirm",
        payload={"candidate_token": preview["candidate_token"], "field_id": field_id},
        headers=headers,
    )

    assert status == 409
    assert rejected["code"] == "field_transaction_required"
    assert "managed_analysis" in rejected["reasons"]
    assert "Managed paper analysis" in rejected["error"]
    assert not service.registry.path.exists()
    assert not (source.parents[1] / ".scholar-workflow" / "fields.yml").exists()
    assert not transaction.state_root.exists()


def test_field_ui_disables_legacy_confirm_and_points_to_operator_flow() -> None:
    script = resources.files("scholar_workflow.hub.static").joinpath("hub.js").read_text()
    assert "transaction_required_fields" in script
    assert "selectedTransactionReasons.length !== 0" in script
    assert "scholar-workflow hub field-transaction plan" in script


def test_operator_credential_must_be_private_regular_file(field_server, monkeypatch) -> None:
    server, _source, _service, _transaction, runtime_dir, generation = field_server
    port = server.server_address[1]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    credential_path = runtime_dir / "field-operator.json"
    credential_path.chmod(0o644)
    result = CliRunner().invoke(
        main,
        [
            "hub",
            "field-transaction",
            "recover",
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
            "--confirm-recovery",
            "--external-writers-paused",
        ],
        input="y\n",
    )
    assert result.exit_code == 7
    assert "credential is unsafe" in result.output


def test_operator_credential_rejects_symlink(field_server, monkeypatch) -> None:
    server, _source, _service, _transaction, runtime_dir, generation = field_server
    port = server.server_address[1]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    credential_path = runtime_dir / "field-operator.json"
    replacement = runtime_dir / "replacement.json"
    replacement.write_bytes(credential_path.read_bytes())
    replacement.chmod(0o600)
    credential_path.unlink()
    credential_path.symlink_to(replacement)
    result = CliRunner().invoke(
        main,
        [
            "hub",
            "field-transaction",
            "recover",
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
            "--confirm-recovery",
            "--external-writers-paused",
        ],
        input="y\n",
    )
    assert result.exit_code == 7
    assert "credential is unavailable or unsafe" in result.output


def test_operator_only_legacy_preview_is_read_only_and_stage_is_unavailable(
    field_server, tmp_path: Path, monkeypatch
) -> None:
    server, source, service, transaction, runtime_dir, generation = field_server
    old_markdown, old_canvas = _install_legacy_pair(source)
    package = _legacy_package(old_markdown, old_canvas)
    package_path = tmp_path / "proposal.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    port = server.server_address[1]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    field_definition = dict(preview["fields"][0])
    field_id = field_definition["field_id"]
    candidate_token = preview["candidate_token"]
    field_definition["home"] = "Fixture Paper分析.md"
    definition_path = tmp_path / "field-definition.json"
    definition_path.write_text(json.dumps(field_definition, ensure_ascii=False), encoding="utf-8")

    status, _ = _request(
        port,
        "/api/v3/field-transactions/legacy/preview",
        payload={"candidate_token": candidate_token, "field_id": field_id, "package": package},
        headers=headers,
    )
    assert status == 403
    runner = CliRunner()
    proposed = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "legacy-preview",
            candidate_token,
            field_id,
            "--package-file",
            str(package_path),
        ],
    )
    assert proposed.exit_code == 0, proposed.output
    report = json.loads(proposed.output)
    assert report["ready_for_approval"] is True
    assert report["cutover_digest"]
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()
    assert (source.parent / "Fixture Paper分析.md").read_bytes() == old_markdown

    wrong = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "legacy-stage",
            candidate_token,
            field_id,
            "--package-file",
            str(package_path),
            "--approved-cutover-digest",
            "0" * 64,
        ],
        input="y\n",
    )
    assert wrong.exit_code == 3
    assert "recoverable transaction journal" in wrong.output
    assert not service.registry.path.exists()
    staged = runner.invoke(
        main,
        [
            "hub",
            "field-transaction",
            "legacy-stage",
            candidate_token,
            field_id,
            "--package-file",
            str(package_path),
            "--approved-cutover-digest",
            report["cutover_digest"],
            "--field-definition-file",
            str(definition_path),
        ],
        input="y\n",
    )
    assert staged.exit_code == 3
    assert "recoverable transaction journal" in staged.output
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()

    credential = json.loads((runtime_dir / "field-operator.json").read_text())
    operator_headers = {**headers, "X-Scholar-Hub-Operator": credential["token"]}
    status, rejected = _request(
        port,
        "/api/v3/field-transactions/legacy/stage",
        payload={
            "candidate_token": candidate_token,
            "field_id": field_id,
            "package": package,
            "approved_cutover_digest": report["cutover_digest"],
            "field_definition": field_definition,
        },
        headers=operator_headers,
    )
    assert status == 503
    assert "recoverable transaction journal" in rejected["error"]
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()
    assert (source.parent / "Fixture Paper分析.md").read_bytes() == old_markdown
    assert (source.parent / "Fixture Paper解析树.canvas").read_bytes() == old_canvas
    assert not (source.parent / "Fixture Paper分析.analysis.json").exists()

    status, plain = _request(
        port,
        "/api/v3/field-transactions/plan",
        payload={"candidate_token": candidate_token, "field_id": field_id},
        headers=headers,
    )
    assert status == 200
    assert any("legacy analysis requires" in conflict for conflict in plain["plan"]["conflicts"])


@pytest.mark.parametrize("stage", [False, True], ids=["preview", "stage"])
def test_real_field_cutover_rejects_old_five_role_candidate(
    field_server, monkeypatch, stage: bool
) -> None:
    server, source, service, transaction, runtime_dir, generation = field_server
    old_markdown, old_canvas = _install_legacy_pair(source)
    package = _legacy_package(old_markdown, old_canvas)
    package["document"] = AnalysisDocument.model_validate(
        {
            "schema_version": 2,
            "artifact_id": "analysis:fixture-paper",
            "paper_title": "Fixture Paper",
            "profile": {"kind": "whole"},
            "claims": [
                {
                    "claim_id": role,
                    "role": role,
                    "title": role,
                    "body": "Old five-role projection",
                    "order": 1 if role == "workflow" else None,
                    "evidence": {"kind": "not_reported"},
                }
                for role in ("task", "input", "workflow", "output", "boundary")
            ],
        }
    ).model_dump(mode="json")
    port = server.server_address[1]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    candidate_token = selected["preview"]["candidate_token"]
    field_id = selected["preview"]["fields"][0]["field_id"]
    credential = json.loads((runtime_dir / "field-operator.json").read_text())
    operator_headers = {**headers, "X-Scholar-Hub-Operator": credential["token"]}

    payload = {"candidate_token": candidate_token, "field_id": field_id, "package": package}
    if stage:
        payload["approved_cutover_digest"] = "unapproved-v2-digest"
    status, response = _request(
        port,
        f"/api/v3/field-transactions/legacy/{'stage' if stage else 'preview'}",
        payload=payload,
        headers=operator_headers,
    )
    if stage:
        assert status == 503
        assert "recoverable transaction journal" in response["error"]
    else:
        assert status == 409
        assert "IR v4 reference_tree" in response["error"]
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()


def test_legacy_package_rejects_escape_and_duplicate_json_before_any_write(
    field_server, tmp_path: Path, monkeypatch
) -> None:
    server, source, service, transaction, runtime_dir, generation = field_server
    old_markdown, old_canvas = _install_legacy_pair(source)
    package = _legacy_package(old_markdown, old_canvas)
    port = server.server_address[1]
    _fake_managed_status(monkeypatch, port, runtime_dir, generation)
    headers = _browser_headers(port)
    _, selected = _request(port, "/api/v3/fields/select", payload={}, headers=headers)
    preview = selected["preview"]
    candidate_token = preview["candidate_token"]
    field_id = preview["fields"][0]["field_id"]
    credential = json.loads((runtime_dir / "field-operator.json").read_text())
    operator_headers = {**headers, "X-Scholar-Hub-Operator": credential["token"]}
    package["markdown_path"] = "../escape.md"
    status, _ = _request(
        port,
        "/api/v3/field-transactions/legacy/preview",
        payload={"candidate_token": candidate_token, "field_id": field_id, "package": package},
        headers=operator_headers,
    )
    assert status == 400
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()

    raw_duplicate = (
        '{"candidate_token":"'
        + candidate_token
        + '","field_id":"'
        + field_id
        + '","package":{"schema_version":1,"schema_version":1}}'
    ).encode()
    with pytest.raises(urllib.error.HTTPError) as duplicate_http:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v3/field-transactions/legacy/preview",
                method="POST",
                data=raw_duplicate,
                headers=operator_headers,
            ),
            timeout=3,
        )
    assert duplicate_http.value.code == 400
    assert not service.registry.path.exists()

    valid_package = _legacy_package(old_markdown, old_canvas)
    status, cutover = _request(
        port,
        "/api/v3/field-transactions/legacy/preview",
        payload={
            "candidate_token": candidate_token,
            "field_id": field_id,
            "package": valid_package,
        },
        headers=operator_headers,
    )
    assert status == 200
    bad_definition = dict(preview["fields"][0])
    bad_definition["field_id"] = "00000000-0000-4000-8000-000000000001"
    status, _ = _request(
        port,
        "/api/v3/field-transactions/legacy/stage",
        payload={
            "candidate_token": candidate_token,
            "field_id": field_id,
            "package": valid_package,
            "approved_cutover_digest": cutover["cutover_digest"],
            "field_definition": bad_definition,
        },
        headers=operator_headers,
    )
    assert status == 503
    assert not service.registry.path.exists()
    assert not transaction.state_root.exists()

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"schema_version":1,"schema_version":1}')
    rejected = CliRunner().invoke(
        main,
        [
            "hub",
            "field-transaction",
            "legacy-preview",
            candidate_token,
            field_id,
            "--package-file",
            str(duplicate_path),
        ],
    )
    assert rejected.exit_code == 2
    assert "Duplicate" in rejected.output
    assert not service.registry.path.exists()
