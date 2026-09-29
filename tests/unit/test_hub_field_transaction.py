"""Fixture-only checks for one recoverable Field enrollment transaction."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

import scholar_workflow.hub.field_transaction as transaction_module
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import create_baseline
from scholar_workflow.hub.field_transaction import (
    FieldTransactionError,
    FieldTransactionService,
)
from scholar_workflow.hub.fields import (
    FieldDefinition,
    FieldNavigationGroup,
    FieldService,
    KnowledgeSourceRegistry,
)

_KEY = "D5HXDNKJ"
_OLD = f"http://127.0.0.1:23128/open/paper/{_KEY}"
_NEW = f"zotero://open-pdf/library/items/{_KEY}"


def _fixture(tmp_path: Path) -> tuple[Path, Path, FieldService, FieldTransactionService]:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    world = vault / "世界模型"
    world.mkdir()
    (world / "00-领域入口.md").write_text(f"# 世界模型\n\n[论文]({_OLD})\n", encoding="utf-8")
    (world / "JEPA.md").write_text("# JEPA\n\n原文保留。\n", encoding="utf-8")
    sibling = vault / "3DGS"
    sibling.mkdir()
    (sibling / "00-领域入口.md").write_text("# 3DGS\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "host" / "sources.json")
    field_service = FieldService(registry)
    service = FieldTransactionService(
        field_service,
        state_root=tmp_path / "private-state",
        link_resolver=lambda key: f"zotero://open-pdf/library/items/{key}",
    )
    return vault, world, field_service, service


def _selected(field_service: FieldService, vault: Path):
    preview = field_service.preview(vault)
    selected = next(row for row in preview.fields if row.relative_root == "世界模型")
    return preview, selected


def _canvas() -> bytes:
    return json.dumps(
        {
            "nodes": [
                {
                    "id": "0123456789abcdef",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 400,
                    "height": 200,
                    "text": "# JEPA 流程",
                }
            ],
            "edges": [],
        }
    ).encode("utf-8")


def _relocation_plan(
    vault: Path,
    world: Path,
    field_service: FieldService,
    service: FieldTransactionService,
):
    source = world / "paper_assets" / "Fixture.md"
    source.parent.mkdir()
    source.write_text("# Fixture\n\nA companion note.\n", encoding="utf-8")
    home = world / "00-领域入口.md"
    home.write_text(
        home.read_text(encoding="utf-8") + "\n[笔记](paper_assets/Fixture.md)\n", encoding="utf-8"
    )
    preview, selected = _selected(field_service, vault)
    revised = selected.model_copy(
        update={
            "navigation": [
                FieldNavigationGroup(
                    label=group.label,
                    items=[
                        "resources/papers/fixture/Fixture.md"
                        if item == "paper_assets/Fixture.md"
                        else item
                        for item in group.items
                    ],
                )
                for group in selected.navigation
            ]
        }
    )
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        field_definition=revised,
        relocations={"paper_assets/Fixture.md": "resources/papers/fixture/Fixture.md"},
        link_rewrites={
            "00-领域入口.md": {"paper_assets/Fixture.md": "resources/papers/fixture/Fixture.md"}
        },
    )
    return preview, selected, plan, source, home


def test_reviewed_relocation_creates_directory_rewrites_link_and_removes_source(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected, plan, source, home = _relocation_plan(vault, world, field_service, service)
    original = source.read_bytes()
    source_inode = source.stat().st_ino
    destination = world / "resources" / "papers" / "fixture" / "Fixture.md"

    assert not destination.exists()
    assert not service.state_root.exists()
    assert plan.conflicts == ()
    assert plan.relocations[0].source_inode == source_inode
    assert plan.relocations[0].source_sha256 == transaction_module._hash(original)
    assert plan.relocations[0].created_directories == (
        "世界模型/resources",
        "世界模型/resources/papers",
        "世界模型/resources/papers/fixture",
    )
    assert plan.relocations[0].link_rewrites == (
        (
            "世界模型/00-领域入口.md",
            "paper_assets/Fixture.md",
            "resources/papers/fixture/Fixture.md",
            1,
        ),
    )
    assert {change.kind for change in plan.changes} >= {
        "relocation-destination",
        "relocation-source",
        "manifest",
    }
    result = service.apply(
        plan.plan_token,
        approved_digest=plan.plan_digest,
        external_writers_paused=True,
    )
    assert not source.exists()
    assert destination.read_bytes() == original
    assert "resources/papers/fixture/Fixture.md" in home.read_text(encoding="utf-8")
    with zipfile.ZipFile(result.recovery_snapshot) as archive:
        receipt = json.loads(archive.read("recovery.json"))
        assert receipt["schema_version"] == 2
        assert receipt["relocations"][0]["source_path"] == "世界模型/paper_assets/Fixture.md"
    assert service.recover(preview.source_id, selected.field_id).outcome == "nothing-to-recover"


@pytest.mark.parametrize("changed", ["source", "destination", "directory"])
def test_relocation_cas_rejects_external_changes_without_writes(
    tmp_path: Path, changed: str
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    _preview, _selected_field, plan, source, _home = _relocation_plan(
        vault, world, field_service, service
    )
    destination = world / "resources" / "papers" / "fixture" / "Fixture.md"
    if changed == "source":
        source.write_bytes(b"human edit\n")
    elif changed == "destination":
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"human destination\n")
    else:
        (world / "resources").mkdir()
    with pytest.raises(
        FieldTransactionError,
        match="content changed|inventory changed|target changed|directory changed",
    ):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert not field_service.registry.path.exists()
    assert not (vault / ".scholar-workflow").exists()
    assert not service.state_root.exists()


def test_relocation_recovers_after_source_unlink_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected, plan, source, home = _relocation_plan(vault, world, field_service, service)
    old_source = source.read_bytes()
    old_home = home.read_bytes()
    original_remove = service._remove_source

    def interrupt_after_unlink(root, removal):
        original_remove(root, removal)
        raise OSError("process interrupted after source unlink")

    monkeypatch.setattr(service, "_remove_source", interrupt_after_unlink)
    monkeypatch.setattr(
        service,
        "_recover_locked",
        lambda *_args: (_ for _ in ()).throw(FieldTransactionError("process stopped")),
    )
    with pytest.raises(FieldTransactionError, match="recover explicitly"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert not source.exists()
    restarted = FieldTransactionService(
        FieldService(field_service.registry),
        state_root=service.state_root,
    )
    with pytest.raises(FieldTransactionError, match="writers must be paused"):
        restarted.recover(preview.source_id, selected.field_id)
    recovery = restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert recovery.outcome == "rolled-back"
    assert source.read_bytes() == old_source
    assert home.read_bytes() == old_home
    assert not (world / "resources").exists()
    assert not field_service.registry.path.exists()


def test_relocation_recovery_refuses_externally_recreated_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected, plan, source, _home = _relocation_plan(vault, world, field_service, service)
    original_bytes = source.read_bytes()
    original_remove = service._remove_source

    def interrupt_after_unlink(root, removal):
        original_remove(root, removal)
        raise OSError("process interrupted after source unlink")

    monkeypatch.setattr(service, "_remove_source", interrupt_after_unlink)
    monkeypatch.setattr(
        service,
        "_recover_locked",
        lambda *_args: (_ for _ in ()).throw(FieldTransactionError("process stopped")),
    )
    with pytest.raises(FieldTransactionError, match="recover explicitly"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    source.write_bytes(original_bytes)
    restarted = FieldTransactionService(
        FieldService(field_service.registry), state_root=service.state_root
    )
    with pytest.raises(FieldTransactionError, match="external edit"):
        restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert source.read_bytes() == original_bytes
    assert next(service.state_root.rglob("pending.json")).exists()


def test_relocation_recovery_finishes_published_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected, plan, source, _home = _relocation_plan(vault, world, field_service, service)
    monkeypatch.setattr(
        service,
        "_clear_journal",
        lambda _directory: (_ for _ in ()).throw(OSError("finalization interrupted")),
    )
    with pytest.raises(FieldTransactionError, match="commit may already be published"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    restarted = FieldTransactionService(
        FieldService(field_service.registry), state_root=service.state_root
    )
    recovery = restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert recovery.outcome == "committed"
    assert not source.exists()
    assert (world / "resources" / "papers" / "fixture" / "Fixture.md").is_file()


def test_relocation_recovers_after_first_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected, plan, source, home = _relocation_plan(vault, world, field_service, service)
    old_source = source.read_bytes()
    old_home = home.read_bytes()
    original_create = service._create_directory
    created = False

    def interrupt_after_mkdir(root, row, **kwargs):
        nonlocal created
        result = original_create(root, row, **kwargs)
        if not created:
            created = True
            raise OSError("process interrupted after directory creation")
        return result

    monkeypatch.setattr(service, "_create_directory", interrupt_after_mkdir)
    monkeypatch.setattr(
        service,
        "_recover_locked",
        lambda *_args: (_ for _ in ()).throw(FieldTransactionError("process stopped")),
    )
    with pytest.raises(FieldTransactionError, match="recover explicitly"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert (world / "resources").is_dir()
    restarted = FieldTransactionService(
        FieldService(field_service.registry), state_root=service.state_root
    )
    recovery = restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert recovery.outcome == "rolled-back"
    assert not (world / "resources").exists()
    assert source.read_bytes() == old_source
    assert home.read_bytes() == old_home


@pytest.mark.parametrize("source_name", ["JEPA分析.md", "JEPA解析树.canvas"])
def test_managed_analysis_cannot_use_unvalidated_file_relocation(
    tmp_path: Path, source_name: str
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    _existing_v2_analysis(world, note_stem="JEPA分析", canvas_name="JEPA解析树.canvas")
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="validated paired cutover"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            relocations={source_name: "resources/papers/jepa/" + source_name},
        )
    assert not service.state_root.exists()
    assert not field_service.registry.path.exists()


def test_external_owned_markdown_cannot_be_relocated(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    note = world / "paper_assets" / "External.md"
    note.parent.mkdir()
    note.write_text(
        "---\nzotflow-locked: false\nzotero-key: D5HXDNKJ\nlibrary-id: 1\n---\n# Note\n",
        encoding="utf-8",
    )
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="external-owned Markdown"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            relocations={"paper_assets/External.md": "resources/papers/x/External.md"},
        )
    assert note.is_file()
    assert not service.state_root.exists()


def test_relocation_rejects_normalized_duplicate_source_before_journal(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    source = world / "paper_assets" / "Fixture.md"
    source.parent.mkdir()
    source.write_bytes(b"# Fixture\n")
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="duplicate Field relocation source"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            relocations={
                "paper_assets/Fixture.md": "resources/papers/a/Fixture.md",
                "paper_assets//Fixture.md": "resources/papers/b/Fixture.md",
            },
        )
    assert source.read_bytes() == b"# Fixture\n"
    assert not service.state_root.exists()


def test_relocation_rejects_symlinked_destination_parent(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    source = world / "paper_assets" / "Fixture.md"
    source.parent.mkdir()
    source.write_bytes(b"# Fixture\n")
    (world / "resources").symlink_to(vault / "3DGS", target_is_directory=True)
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="unsafe"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            relocations={"paper_assets/Fixture.md": "resources/papers/x/Fixture.md"},
        )
    assert source.read_bytes() == b"# Fixture\n"
    assert not service.state_root.exists()


def _existing_v2_analysis(
    world: Path, *, note_stem: str = "JEPA", canvas_name: str = "JEPA.canvas"
) -> None:
    document = AnalysisDocument.model_validate(
        {
            "schema_version": 2,
            "artifact_id": "analysis:fixture-jepa",
            "paper_title": "JEPA",
            "profile": {"kind": "whole"},
            "claims": [
                {
                    "claim_id": role,
                    "role": role,
                    "title": role,
                    "body": f"{role} statement",
                    "order": 1 if role == "workflow" else None,
                    "evidence": {"kind": "author_stated", "anchor": "§1"},
                }
                for role in ("task", "input", "workflow", "output", "boundary")
            ],
        }
    )
    bundle = render_analysis(document, note_stem=note_stem)
    baseline = create_baseline(document, bundle, note_stem=note_stem)
    (world / f"{note_stem}.md").write_text(bundle.markdown, encoding="utf-8")
    (world / canvas_name).write_text(
        json.dumps(bundle.canvas, ensure_ascii=False), encoding="utf-8"
    )
    (world / f"{note_stem}.analysis.json").write_text(
        baseline.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def test_existing_conformant_v2_pair_is_read_only_validated_before_registration(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    _existing_v2_analysis(world)
    originals = {
        name: (world / name).read_bytes()
        for name in ("JEPA.md", "JEPA.canvas", "JEPA.analysis.json")
    }
    preview, selected = _selected(field_service, vault)

    plan = service.plan(preview.candidate_token, selected.field_id)

    assert plan.conflicts == ()
    assert plan.analysis_conformance == "validated-existing-v2"
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()
    assert not service.state_root.exists()
    result = service.apply(
        plan.plan_token,
        approved_digest=plan.plan_digest,
        external_writers_paused=True,
    )
    assert result.field_id == selected.field_id
    assert all((world / name).read_bytes() == old for name, old in originals.items())
    assert (vault / ".scholar-workflow" / "fields.yml").is_file()
    assert field_service.registry.path.is_file()


def test_existing_v2_analysis_accepts_canonical_analysis_canvas_names(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    _existing_v2_analysis(world, note_stem="JEPA分析", canvas_name="JEPA解析树.canvas")
    preview, selected = _selected(field_service, vault)

    plan = service.plan(preview.candidate_token, selected.field_id)

    assert plan.conflicts == ()
    assert plan.analysis_conformance == "validated-existing-v2"
    assert not field_service.registry.path.exists()


@pytest.mark.parametrize(
    "broken",
    [
        "missing-canvas",
        "missing-sidecar",
        "bad-markdown",
        "bad-canvas",
        "bad-sidecar",
        "sidecar-with-ordinary-markdown",
    ],
)
def test_existing_invalid_v2_pair_blocks_registration_without_writes(
    tmp_path: Path, broken: str
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    _existing_v2_analysis(world)
    if broken == "missing-canvas":
        (world / "JEPA.canvas").unlink()
    elif broken == "missing-sidecar":
        (world / "JEPA.analysis.json").unlink()
    elif broken == "bad-markdown":
        markdown = world / "JEPA.md"
        markdown.write_text(
            markdown.read_text(encoding="utf-8").replace("# JEPA：论文分析", "# Wrong"),
            encoding="utf-8",
        )
    elif broken == "bad-canvas":
        canvas = world / "JEPA.canvas"
        content = json.loads(canvas.read_text(encoding="utf-8"))
        content["nodes"][0]["text"] = "Unreviewed edit"
        canvas.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    elif broken == "bad-sidecar":
        (world / "JEPA.analysis.json").write_text("{}", encoding="utf-8")
    else:
        (world / "JEPA.md").write_text("# Ordinary note\n", encoding="utf-8")
    originals = {
        name: (world / name).read_bytes()
        for name in ("JEPA.md", "JEPA.canvas", "JEPA.analysis.json")
        if (world / name).exists()
    }
    preview, selected = _selected(field_service, vault)

    plan = service.plan(preview.candidate_token, selected.field_id)

    assert any("validated cutover" in conflict for conflict in plan.conflicts)
    with pytest.raises(FieldTransactionError, match="unresolved conflicts"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert all((world / name).read_bytes() == old for name, old in originals.items())
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()
    assert not service.state_root.exists()


@pytest.mark.parametrize(
    "markdown_name,canvas_name",
    [("JEPA.md", "JEPA.canvas"), ("JEPA分析.md", "JEPA解析树.canvas")],
)
def test_canvas_only_analysis_marker_requires_validated_pair(
    tmp_path: Path, markdown_name: str, canvas_name: str
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / markdown_name).write_text("# Ordinary-looking note\n", encoding="utf-8")
    (world / canvas_name).write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "0123456789abcdef",
                        "type": "text",
                        "x": 0,
                        "y": 0,
                        "width": 400,
                        "height": 200,
                        "text": '<!-- sw-analysis-claim id="task" role="task" -->',
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    preview, selected = _selected(field_service, vault)

    plan = service.plan(preview.candidate_token, selected.field_id)

    assert any("validated cutover" in conflict for conflict in plan.conflicts)
    with pytest.raises(FieldTransactionError, match="unresolved conflicts"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()
    assert not service.state_root.exists()


def test_first_field_commits_manifest_registry_markdown_canvas_together(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    registry_path = field_service.registry.path
    proposed = {
        "JEPA.canvas": _canvas(),
    }
    plan = service.plan(preview.candidate_token, selected.field_id, staged_bundle=proposed)

    assert not manifest_path.exists()
    assert not registry_path.exists()
    assert not service.state_root.exists()
    assert plan.conflicts == ()
    assert plan.analysis_conformance == "not-evaluated"
    assert plan.replaced_links == 1
    assert plan.registry_before_sha256 is None
    assert plan.registry_after_sha256.startswith("sha256:")
    assert any(_NEW in change.preview_diff for change in plan.changes)
    assert {change.kind for change in plan.changes} == {"content", "manifest"}
    result = service.apply(
        plan.plan_token,
        approved_digest=plan.plan_digest,
        external_writers_paused=True,
    )

    assert result.recovery_is_verified_backup is False
    assert manifest_path.exists()
    assert len(field_service.registry.load_document().sources) == 1
    assert _NEW in (world / "00-领域入口.md").read_text()
    assert (world / "JEPA.md").read_text() == "# JEPA\n\n原文保留。\n"
    assert (world / "JEPA.canvas").read_bytes() == proposed["JEPA.canvas"]
    assert (vault / "3DGS" / "00-领域入口.md").read_text() == "# 3DGS\n"
    assert not (result.recovery_snapshot.parent / "pending.json").exists()
    with zipfile.ZipFile(result.recovery_snapshot) as archive:
        receipt = json.loads(archive.read("recovery.json"))
        assert receipt["verified_backup"] is False


def test_field_plan_includes_new_home_and_navigation_in_the_same_commit(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    revised = FieldDefinition(
        field_id=selected.field_id,
        title=selected.title,
        relative_root=selected.relative_root,
        home="index.md",
        navigation=[
            FieldNavigationGroup(label="入口", items=["index.md", "00-领域入口.md"]),
            FieldNavigationGroup(label="论文", items=["JEPA.md"]),
        ],
    )
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        field_definition=revised,
        staged_bundle={"index.md": b"# World Models\n"},
    )

    assert plan.conflicts == ()
    assert {change.relative_path for change in plan.changes} >= {
        "世界模型/index.md",
        ".scholar-workflow/fields.yml",
        "世界模型/00-领域入口.md",
    }
    result = service.apply(
        plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
    )
    manifest = field_service._load_manifest(vault)
    assert manifest.fields[0].home == "index.md"
    assert [group.label for group in manifest.fields[0].navigation] == ["入口", "论文"]
    assert (world / "index.md").read_bytes() == b"# World Models\n"
    assert "世界模型/index.md" in result.changed_files


def test_field_definition_override_cannot_change_preview_identity_or_add_missing_home(
    tmp_path: Path,
) -> None:
    vault, _world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    altered_root = selected.model_copy(update={"relative_root": "."})
    with pytest.raises(FieldTransactionError, match="preview identity"):
        service.plan(preview.candidate_token, selected.field_id, field_definition=altered_root)

    missing_home = selected.model_copy(update={"home": "missing.md"})
    with pytest.raises(FieldTransactionError, match="Field path is unavailable"):
        service.plan(preview.candidate_token, selected.field_id, field_definition=missing_home)


@pytest.mark.parametrize("field_name", ["home", "navigation"])
def test_field_plan_revalidates_non_markdown_definition_override(
    tmp_path: Path, field_name: str
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / "tree.canvas").write_bytes(_canvas())
    preview, selected = _selected(field_service, vault)
    if field_name == "home":
        revised = selected.model_copy(update={"home": "tree.canvas"})
    else:
        revised = selected.model_copy(
            update={
                "navigation": [
                    FieldNavigationGroup.model_construct(label="Read", items=["tree.canvas"])
                ]
            }
        )

    with pytest.raises(FieldTransactionError, match="invalid proposed Field definition"):
        service.plan(preview.candidate_token, selected.field_id, field_definition=revised)
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()


def test_field_definition_override_must_keep_every_previewed_document(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    omitted = selected.model_copy(
        update={
            "navigation": [FieldNavigationGroup(label="Only home", items=[selected.home])],
        }
    )

    with pytest.raises(FieldTransactionError, match="navigation omitted previewed documents"):
        service.plan(preview.candidate_token, selected.field_id, field_definition=omitted)

    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()
    assert (world / "JEPA.md").read_text(encoding="utf-8") == "# JEPA\n\n原文保留。\n"


def test_first_registration_cannot_skip_legacy_analysis_cutover(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / "JEPA.md").write_text(
        "# JEPA\n\n<!-- sw-analysis-field: legacy -->\n", encoding="utf-8"
    )
    preview, selected = _selected(field_service, vault)
    plan = service.plan(preview.candidate_token, selected.field_id)

    assert any("legacy analysis requires" in conflict for conflict in plan.conflicts)
    with pytest.raises(FieldTransactionError, match="unresolved conflicts"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()


def test_changed_canvas_after_plan_rejects_without_vault_or_state_write(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / "JEPA.canvas").write_bytes(_canvas())
    preview, selected = _selected(field_service, vault)
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        staged_bundle={"JEPA.canvas": _canvas()},
    )
    (world / "JEPA.canvas").write_bytes(_canvas().replace(b"JEPA", b"Human"))

    with pytest.raises(FieldTransactionError, match="inventory changed|content changed"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not (vault / ".scholar-workflow").exists()
    assert not field_service.registry.path.exists()
    assert not service.state_root.exists()


def test_partial_failure_rolls_back_only_selected_field(tmp_path: Path, monkeypatch) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    old_home = (world / "00-领域入口.md").read_bytes()
    sibling = (vault / "3DGS" / "00-领域入口.md").read_bytes()
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        staged_bundle={"JEPA.canvas": _canvas()},
    )
    original = service._replace
    calls = 0

    def fail_second(root, target, content, *, expect_new, **kwargs):
        nonlocal calls
        if not expect_new:
            calls += 1
            if calls == 2:
                raise OSError("injected second replacement failure")
        return original(root, target, content, expect_new=expect_new, **kwargs)

    monkeypatch.setattr(service, "_replace", fail_second)
    with pytest.raises(FieldTransactionError, match="rolled back"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert (world / "00-领域入口.md").read_bytes() == old_home
    assert (world / "JEPA.md").read_text() == "# JEPA\n\n原文保留。\n"
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()
    assert (vault / "3DGS" / "00-领域入口.md").read_bytes() == sibling
    recovery = service.recover(preview.source_id, selected.field_id)
    assert recovery.outcome == "nothing-to-recover"


def test_restart_can_explicitly_recover_interrupted_field(tmp_path: Path, monkeypatch) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    old_home = (world / "00-领域入口.md").read_bytes()
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        staged_bundle={"JEPA.canvas": _canvas()},
    )
    original = service._replace
    calls = 0

    def fail_second(root, target, content, *, expect_new, **kwargs):
        nonlocal calls
        if not expect_new:
            calls += 1
            if calls == 2:
                raise OSError("simulated interruption")
        return original(root, target, content, expect_new=expect_new, **kwargs)

    monkeypatch.setattr(service, "_replace", fail_second)
    monkeypatch.setattr(
        service,
        "_recover_locked",
        lambda *_args: (_ for _ in ()).throw(FieldTransactionError("process stopped")),
    )
    with pytest.raises(FieldTransactionError, match="recover explicitly"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )

    restarted = FieldTransactionService(
        FieldService(field_service.registry),
        state_root=service.state_root,
        link_resolver=lambda key: f"zotero://open-pdf/library/items/{key}",
    )
    snapshot = next(service.state_root.rglob("originals-*.zip"))
    assert json.loads((snapshot.parent / "pending.json").read_text())["schema_version"] == 2
    safe_snapshot = snapshot.read_bytes()
    snapshot.write_bytes(b"corrupt")
    with pytest.raises(FieldTransactionError, match="writers must be paused"):
        restarted.recover(preview.source_id, selected.field_id)
    with pytest.raises(FieldTransactionError, match="snapshot is invalid"):
        restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert (snapshot.parent / "pending.json").exists()
    snapshot.write_bytes(safe_snapshot)
    recovery = restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert recovery.outcome == "rolled-back"
    assert (world / "00-领域入口.md").read_bytes() == old_home
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()
    assert restarted.recover(preview.source_id, selected.field_id).outcome == "nothing-to-recover"


def test_published_journal_finalizes_after_restart(tmp_path: Path, monkeypatch) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    plan = service.plan(preview.candidate_token, selected.field_id)
    monkeypatch.setattr(
        service,
        "_clear_journal",
        lambda _directory: (_ for _ in ()).throw(OSError("simulated journal finalization crash")),
    )
    with pytest.raises(FieldTransactionError, match="commit may already be published"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert field_service.registry.load_document().sources[0].source_id == preview.source_id
    assert _NEW in (world / "00-领域入口.md").read_text()
    restarted = FieldTransactionService(
        FieldService(field_service.registry),
        state_root=service.state_root,
    )
    with pytest.raises(FieldTransactionError, match="writers must be paused"):
        restarted.recover(preview.source_id, selected.field_id)
    recovery = restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert recovery.outcome == "committed"
    assert _NEW in (world / "00-领域入口.md").read_text()
    assert not (recovery.recovery_snapshot.parent / "pending.json").exists()


def test_candidate_consumption_failure_reports_published_uncertainty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    plan = service.plan(preview.candidate_token, selected.field_id)
    monkeypatch.setattr(
        field_service.candidates,
        "consume",
        lambda _token: (_ for _ in ()).throw(RuntimeError("candidate cache failed")),
    )
    with pytest.raises(FieldTransactionError, match="commit may already be published"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert (vault / ".scholar-workflow" / "fields.yml").exists()
    assert field_service.registry.load_document().sources[0].source_id == preview.source_id
    assert _NEW in (world / "00-领域入口.md").read_text()
    assert service.recover(preview.source_id, selected.field_id).outcome == "nothing-to-recover"


def test_append_second_field_preserves_first_field_and_registry(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    first, selected = _selected(field_service, vault)
    field_service.confirm(first.candidate_token, selected.field_id)
    first_bytes = (world / "JEPA.md").read_bytes()
    registry_bytes = field_service.registry.path.read_bytes()
    second = field_service.preview(vault)
    other = next(row for row in second.fields if row.relative_root == "3DGS")
    plan = service.plan(second.candidate_token, other.field_id)

    result = service.apply(
        plan.plan_token,
        approved_digest=plan.plan_digest,
        external_writers_paused=True,
    )

    assert result.field_id == other.field_id
    assert field_service.registry.path.read_bytes() == registry_bytes
    assert (world / "JEPA.md").read_bytes() == first_bytes
    assert [row.relative_root for row in field_service._load_manifest(vault).fields] == [
        "世界模型",
        "3DGS",
    ]


def test_approval_digest_and_bundle_paths_fail_closed(tmp_path: Path) -> None:
    vault, _world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="unsafe path"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            staged_bundle={"../3DGS/00-领域入口.md": b"# overwrite\n"},
        )
    bad_canvas = _canvas().replace(b'"width": 400', b'"width": -1')
    with pytest.raises(FieldTransactionError, match="invalid JSON Canvas"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            staged_bundle={"JEPA.canvas": bad_canvas},
        )
    plan = service.plan(preview.candidate_token, selected.field_id)
    with pytest.raises(FieldTransactionError, match="external Field writers must be paused"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)
    assert not service.state_root.exists()
    with pytest.raises(FieldTransactionError, match="not approved"):
        service.apply(
            plan.plan_token,
            approved_digest="wrong",
            external_writers_paused=True,
        )
    assert not field_service.registry.path.exists()
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()


def test_legacy_jepa_analysis_rewrite_requires_separate_conformance(tmp_path: Path) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / "JEPA.md").write_text(
        "# JEPA\n\n<!-- sw-analysis-field:method -->\n旧内容。\n", encoding="utf-8"
    )
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="validated migration bundle"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            staged_bundle={"JEPA.md": b"# JEPA\n\nShort replacement.\n"},
        )
    assert not service.state_root.exists()
    assert not field_service.registry.path.exists()


def test_analysis_sidecar_cannot_be_staged_without_validated_receipt(tmp_path: Path) -> None:
    vault, _world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="validated bundle receipt"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            staged_bundle={"JEPA.analysis.json": b'{"schema_version":1}'},
        )
    assert not service.state_root.exists()


def test_existing_v2_sidecar_protects_its_markdown_from_unreviewed_rewrite(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / "JEPA.analysis.json").write_text("{}", encoding="utf-8")
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="validated migration bundle"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            staged_bundle={"JEPA.md": b"# JEPA\n\nCompressed analysis.\n"},
        )
    assert not service.state_root.exists()


def test_foreign_sidecar_and_markerless_existing_analysis_cannot_be_rewritten(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    sidecar = world / "metadata" / "JEPA-state.json"
    sidecar.parent.mkdir()
    sidecar.write_text('{"sw_kind":"paper-analysis"}', encoding="utf-8")
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="validated migration bundle"):
        service.plan(
            preview.candidate_token,
            selected.field_id,
            staged_bundle={"JEPA.md": b"# JEPA\n\nUnreviewed replacement.\n"},
        )
    assert (world / "JEPA.md").read_text() == "# JEPA\n\n原文保留。\n"
    assert not service.state_root.exists()


def test_v2_analysis_identity_blocks_even_deterministic_legacy_link_rewrite(
    tmp_path: Path,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    (world / "JEPA.md").write_text(
        f"---\nsw_kind: paper-analysis\n---\n# JEPA\n[{_KEY}]({_OLD})\n",
        encoding="utf-8",
    )
    preview, selected = _selected(field_service, vault)
    with pytest.raises(FieldTransactionError, match="separately validated migration"):
        service.plan(preview.candidate_token, selected.field_id)
    assert not service.state_root.exists()


def test_same_byte_external_replacement_blocks_recovery(tmp_path: Path, monkeypatch) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        staged_bundle={"JEPA.canvas": _canvas()},
    )
    original = service._replace
    calls = 0

    def interrupt_after_first(root, target, content, *, expect_new, **kwargs):
        nonlocal calls
        if not expect_new:
            calls += 1
            if calls == 2:
                raise OSError("simulated process interruption")
        return original(root, target, content, expect_new=expect_new, **kwargs)

    monkeypatch.setattr(service, "_replace", interrupt_after_first)
    monkeypatch.setattr(
        service,
        "_recover_locked",
        lambda *_args: (_ for _ in ()).throw(FieldTransactionError("process stopped")),
    )
    with pytest.raises(FieldTransactionError, match="recover explicitly"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    home = world / "00-领域入口.md"
    committed_bytes = home.read_bytes()
    old_inode = home.stat().st_ino
    temporary = world / "human-save.md"
    temporary.write_bytes(committed_bytes)
    os.chmod(temporary, home.stat().st_mode & 0o777)
    os.replace(temporary, home)
    assert home.stat().st_ino != old_inode
    restarted = FieldTransactionService(
        FieldService(field_service.registry),
        state_root=service.state_root,
    )
    with pytest.raises(FieldTransactionError, match="external edit"):
        restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert home.read_bytes() == committed_bytes
    assert next(service.state_root.rglob("pending.json")).exists()
    assert not field_service.registry.path.exists()


def test_restart_finishes_rollback_after_restore_rename_crash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    original_home = (world / "00-领域入口.md").read_bytes()
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        staged_bundle={"JEPA.canvas": _canvas()},
    )
    original_replace = service._replace
    commit_calls = 0

    def interrupt_restore(root, target, content, *, expect_new, **kwargs):
        nonlocal commit_calls
        if not expect_new:
            commit_calls += 1
            if commit_calls == 2:
                raise OSError("commit interrupted")
        result = original_replace(root, target, content, expect_new=expect_new, **kwargs)
        if expect_new:
            raise OSError("restore completed before process interruption")
        return result

    monkeypatch.setattr(service, "_replace", interrupt_restore)
    with pytest.raises(FieldTransactionError, match="recover explicitly"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert (world / "00-领域入口.md").read_bytes() == original_home
    restarted = FieldTransactionService(
        FieldService(field_service.registry),
        state_root=service.state_root,
    )
    recovery = restarted.recover(preview.source_id, selected.field_id, external_writers_paused=True)
    assert recovery.outcome == "rolled-back"
    assert (world / "00-领域入口.md").read_bytes() == original_home
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not field_service.registry.path.exists()


def test_private_state_symlink_ancestor_is_rejected_before_content_write(
    tmp_path: Path,
) -> None:
    vault, world, field_service, _service = _fixture(tmp_path)
    actual_state_parent = tmp_path / "actual-state-parent"
    actual_state_parent.mkdir()
    (tmp_path / "state-alias").symlink_to(actual_state_parent, target_is_directory=True)
    service = FieldTransactionService(
        field_service,
        state_root=tmp_path / "state-alias" / "private-state",
        link_resolver=lambda key: f"zotero://open-pdf/library/items/{key}",
    )
    preview, selected = _selected(field_service, vault)
    plan = service.plan(preview.candidate_token, selected.field_id)
    original_home = (world / "00-领域入口.md").read_bytes()
    with pytest.raises(FieldTransactionError, match="unavailable or unsafe"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert (world / "00-领域入口.md").read_bytes() == original_home
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not (vault / ".scholar-workflow").exists()
    assert not field_service.registry.path.exists()


def test_private_directory_fsync_failure_prevents_vault_content_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    plan = service.plan(preview.candidate_token, selected.field_id)
    home = (world / "00-领域入口.md").read_bytes()
    original = transaction_module.os.fsync
    calls = 0

    def fail_new_private_directory_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        # No Vault directory may be created before this private journal root.
        if calls == 1:
            raise OSError("simulated private directory durability failure")
        original(descriptor)

    monkeypatch.setattr(transaction_module.os, "fsync", fail_new_private_directory_fsync)
    with pytest.raises(
        FieldTransactionError, match="recovery directory could not be durably created"
    ):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert calls >= 1
    assert (world / "00-领域入口.md").read_bytes() == home
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not (vault / ".scholar-workflow").exists()
    assert not field_service.registry.path.exists()


def test_journal_creation_failure_cleans_unreferenced_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault, world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    plan = service.plan(preview.candidate_token, selected.field_id)
    original_home = (world / "00-领域入口.md").read_bytes()
    monkeypatch.setattr(
        service,
        "_write_journal",
        lambda *_args: (_ for _ in ()).throw(OSError("simulated journal failure")),
    )
    with pytest.raises(FieldTransactionError, match="no Vault content changed"):
        service.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert not list(service.state_root.rglob("originals-*.zip"))
    assert (world / "00-领域入口.md").read_bytes() == original_home
    assert not (vault / ".scholar-workflow" / "fields.yml").exists()
    assert not (vault / ".scholar-workflow").exists()
    assert not field_service.registry.path.exists()


def test_transaction_byte_budget_includes_managed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, _world, field_service, service = _fixture(tmp_path)
    preview, selected = _selected(field_service, vault)
    monkeypatch.setattr(transaction_module, "_MAX_TRANSACTION_BYTES", 10)
    with pytest.raises(FieldTransactionError, match="snapshot limit"):
        service.plan(preview.candidate_token, selected.field_id)
    assert not service.state_root.exists()
