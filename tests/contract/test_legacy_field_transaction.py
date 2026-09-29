"""Fixture-only contract for validated legacy analysis in a single Field commit."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from scholar_workflow.analysis.legacy_canvas_migration import (
    LegacyCanvasElementMapping,
    LegacyCanvasMigrationPlan,
    inventory_legacy_canvas,
)
from scholar_workflow.analysis.legacy_cutover import (
    PreparedLegacyFieldPayload,
    prepare_legacy_field_payload,
    validate_legacy_cutover,
)
from scholar_workflow.analysis.legacy_migration import (
    LegacyFieldMapping,
    LegacyFragment,
    LegacyMigrationPlan,
    LegacyTarget,
    parse_legacy_fields,
)
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.hub.field_transaction import FieldTransactionError, FieldTransactionService
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry

NOTE_STEM = "JEPA分析"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class _Fixture:
    vault: Path
    field_root: Path
    field_service: FieldService
    transaction: FieldTransactionService
    candidate_token: str
    field_id: str
    source_markdown: bytes
    source_canvas: bytes
    document: AnalysisDocument
    bundle: AnalysisBundle
    markdown_plan: LegacyMigrationPlan
    canvas_plan: LegacyCanvasMigrationPlan

    def prepare(self, *, document: AnalysisDocument | None = None) -> PreparedLegacyFieldPayload:
        chosen = document or self.document
        if chosen is self.document:
            bundle, canvas_plan = self.bundle, self.canvas_plan
        else:
            rendered = render_analysis(chosen, note_stem=NOTE_STEM)
            canvas = deepcopy(rendered.canvas)
            canvas["nodes"].append(json.loads(self.source_canvas)["nodes"][0])
            bundle = AnalysisBundle(rendered.markdown, canvas)
            canvas_plan = replace(
                self.canvas_plan, candidate_sha256=_sha256(_json_bytes(canvas))
            )
        pending = validate_legacy_cutover(
            self.source_markdown,
            self.source_canvas,
            chosen,
            bundle,
            self.markdown_plan,
            canvas_plan,
            note_stem=NOTE_STEM,
        )
        assert pending.cutover_digest is not None
        assert pending.artifacts is None
        return prepare_legacy_field_payload(
            markdown_path=f"{NOTE_STEM}.md",
            canvas_path=f"{NOTE_STEM}.canvas",
            sidecar_path=f"{NOTE_STEM}.analysis.json",
            source_markdown=self.source_markdown,
            source_canvas=self.source_canvas,
            source_sidecar=None,
            document=chosen,
            bundle=bundle,
            markdown_plan=self.markdown_plan,
            canvas_plan=canvas_plan,
            note_stem=NOTE_STEM,
            approved_cutover_digest=pending.cutover_digest,
        )


def _fixture(tmp_path: Path) -> _Fixture:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    field_root = vault / "世界模型"
    field_root.mkdir()
    (field_root / "00-领域入口.md").write_text("# 世界模型\n", encoding="utf-8")
    visible = b"Original task statement"
    source_markdown = (
        visible
        + b"\n"
        + f'<!-- sw-analysis-field path="task" base_sha256="{_sha256(visible)}" -->\n'.encode()
    )
    (field_root / f"{NOTE_STEM}.md").write_bytes(source_markdown)
    custom_node = {
        "id": "user-owned-note",
        "type": "text",
        "text": "Keep this personal note",
        "x": 10000,
        "y": 10000,
        "width": 400,
        "height": 200,
        "color": "4",
    }
    source_canvas = _json_bytes({"nodes": [custom_node], "edges": []})
    (field_root / f"{NOTE_STEM}.canvas").write_bytes(source_canvas)
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
                    "body": body,
                    "order": 1 if role == "workflow" else None,
                    "evidence": {"kind": "author_stated", "anchor": "§1"},
                }
                for role, body in (
                    ("task", "Original task statement"),
                    ("input", "Input statement"),
                    ("workflow", "Workflow statement"),
                    ("output", "Output statement"),
                    ("boundary", "Boundary statement"),
                )
            ],
        }
    )
    rendered = render_analysis(document, note_stem=NOTE_STEM)
    canvas = deepcopy(rendered.canvas)
    canvas["nodes"].append(custom_node)
    bundle = AnalysisBundle(rendered.markdown, canvas)
    field = parse_legacy_fields(source_markdown)[0]
    markdown_plan = LegacyMigrationPlan(
        source_sha256=_sha256(source_markdown),
        expected_field_count=1,
        mappings=(
            LegacyFieldMapping(
                "task",
                field.sha256,
                (
                    LegacyFragment(
                        0,
                        len(field.content),
                        field.sha256,
                        "copy",
                        LegacyTarget("task"),
                    ),
                ),
            ),
        ),
        split_targets={},
    )
    canvas_plan = LegacyCanvasMigrationPlan(
        source_sha256=_sha256(source_canvas),
        candidate_sha256=_sha256(_json_bytes(bundle.canvas)),
        mappings=tuple(
            LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "preserve")
            for row in inventory_legacy_canvas(source_canvas)
        ),
    )
    field_service = FieldService(KnowledgeSourceRegistry(tmp_path / "host" / "sources.json"))
    preview = field_service.preview(vault)
    selected = next(row for row in preview.fields if row.relative_root == "世界模型")
    transaction = FieldTransactionService(
        field_service,
        state_root=tmp_path / "private-state",
        link_resolver=lambda key: f"zotero://open-pdf/library/items/{key}",
    )
    return _Fixture(
        vault,
        field_root,
        field_service,
        transaction,
        preview.candidate_token,
        selected.field_id,
        source_markdown,
        source_canvas,
        document,
        bundle,
        markdown_plan,
        canvas_plan,
    )


def _no_registration(fixture: _Fixture) -> None:
    assert not (fixture.vault / ".scholar-workflow" / "fields.yml").exists()
    assert not fixture.field_service.registry.path.exists()


def test_validated_analysis_triple_commits_with_first_field_manifest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    payload = fixture.prepare()
    plan = fixture.transaction.plan(
        fixture.candidate_token,
        fixture.field_id,
        legacy_payloads=(payload,),
    )
    _no_registration(fixture)
    assert not fixture.transaction.state_root.exists()
    assert plan.conflicts == ()
    assert plan.analysis_conformance == "validated-legacy-cutover"
    assert {f"世界模型/{name}" for name in payload.files}.issubset(
        {change.relative_path for change in plan.changes}
    )
    result = fixture.transaction.apply(
        plan.plan_token,
        approved_digest=plan.plan_digest,
        external_writers_paused=True,
    )
    assert result.recovery_is_verified_backup is False
    assert len(fixture.field_service.registry.load_document().sources) == 1
    assert (fixture.vault / ".scholar-workflow" / "fields.yml").is_file()
    for relative, content in payload.files.items():
        assert (fixture.field_root / relative).read_bytes() == content


def test_real_analysis_to_tree_canvas_name_commits_without_renaming(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    old_canvas = fixture.field_root / f"{NOTE_STEM}.canvas"
    tree_canvas = fixture.field_root / "JEPA解析树.canvas"
    old_canvas.rename(tree_canvas)
    preview = fixture.field_service.preview(fixture.vault)
    selected = next(row for row in preview.fields if row.relative_root == "世界模型")
    pending = validate_legacy_cutover(
        fixture.source_markdown,
        fixture.source_canvas,
        fixture.document,
        fixture.bundle,
        fixture.markdown_plan,
        fixture.canvas_plan,
        note_stem=NOTE_STEM,
    )
    assert pending.cutover_digest is not None
    payload = prepare_legacy_field_payload(
        markdown_path=f"{NOTE_STEM}.md",
        canvas_path="JEPA解析树.canvas",
        sidecar_path=f"{NOTE_STEM}.analysis.json",
        source_markdown=fixture.source_markdown,
        source_canvas=fixture.source_canvas,
        source_sidecar=None,
        document=fixture.document,
        bundle=fixture.bundle,
        markdown_plan=fixture.markdown_plan,
        canvas_plan=fixture.canvas_plan,
        note_stem=NOTE_STEM,
        approved_cutover_digest=pending.cutover_digest,
    )
    plan = fixture.transaction.plan(
        preview.candidate_token, selected.field_id, legacy_payloads=(payload,)
    )
    fixture.transaction.apply(
        plan.plan_token,
        approved_digest=plan.plan_digest,
        external_writers_paused=True,
    )
    assert tree_canvas.read_bytes() == payload.canvas
    assert not old_canvas.exists()
    assert (fixture.field_root / f"{NOTE_STEM}.analysis.json").read_bytes() == payload.sidecar


@pytest.mark.parametrize("changed", ["markdown", "canvas", "sidecar"])
def test_source_hash_or_absence_conflict_rejects_before_any_commit(
    tmp_path: Path, changed: str
) -> None:
    fixture = _fixture(tmp_path)
    payload = fixture.prepare()
    target = fixture.field_root / f"{NOTE_STEM}.{changed if changed != 'markdown' else 'md'}"
    if changed == "sidecar":
        target = fixture.field_root / f"{NOTE_STEM}.analysis.json"
        target.write_bytes(b'{}\n')
    else:
        target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(FieldTransactionError, match="Selected folder content changed after preview"):
        fixture.transaction.plan(
            fixture.candidate_token,
            fixture.field_id,
            legacy_payloads=(payload,),
        )
    fresh_preview = fixture.field_service.preview(fixture.vault)
    fresh_field = next(
        row for row in fresh_preview.fields if row.relative_root == "世界模型"
    )
    with pytest.raises(FieldTransactionError, match="legacy analysis source changed"):
        fixture.transaction.plan(
            fresh_preview.candidate_token,
            fresh_field.field_id,
            legacy_payloads=(payload,),
        )
    _no_registration(fixture)
    assert not fixture.transaction.state_root.exists()


def test_field_plan_digest_changes_with_validated_candidate_bytes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    original = fixture.prepare()
    revised = fixture.document.model_copy(deep=True)
    revised.claims[1].body = "A revised input statement"
    changed = fixture.prepare(document=revised)
    assert original.cutover_digest != changed.cutover_digest
    assert original.payload_digest != changed.payload_digest
    first_plan = fixture.transaction.plan(
        fixture.candidate_token, fixture.field_id, legacy_payloads=(original,)
    )
    second_plan = fixture.transaction.plan(
        fixture.candidate_token, fixture.field_id, legacy_payloads=(changed,)
    )
    assert first_plan.plan_digest != second_plan.plan_digest
    with pytest.raises(FieldTransactionError, match="exact Field transaction plan"):
        fixture.transaction.apply(
            second_plan.plan_token,
            approved_digest=first_plan.plan_digest,
            external_writers_paused=True,
        )
    _no_registration(fixture)


def test_tampered_payload_digest_is_rejected_before_planning(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    payload = replace(fixture.prepare(), payload_digest="0" * 64)
    with pytest.raises(FieldTransactionError, match="payload digest changed"):
        fixture.transaction.plan(
            fixture.candidate_token, fixture.field_id, legacy_payloads=(payload,)
        )
    _no_registration(fixture)


def test_partial_commit_failure_restores_original_analysis_and_no_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    payload = fixture.prepare()
    plan = fixture.transaction.plan(
        fixture.candidate_token, fixture.field_id, legacy_payloads=(payload,)
    )
    original_replace = fixture.transaction._replace
    attempts = 0

    def fail_after_first(root, target, content, *, expect_new, **kwargs):
        nonlocal attempts
        if not expect_new:
            attempts += 1
            if attempts == 2:
                raise OSError("injected second replacement failure")
        return original_replace(root, target, content, expect_new=expect_new, **kwargs)

    monkeypatch.setattr(fixture.transaction, "_replace", fail_after_first)
    with pytest.raises(FieldTransactionError, match="rolled back"):
        fixture.transaction.apply(
            plan.plan_token,
            approved_digest=plan.plan_digest,
            external_writers_paused=True,
        )
    assert (fixture.field_root / f"{NOTE_STEM}.md").read_bytes() == fixture.source_markdown
    assert (fixture.field_root / f"{NOTE_STEM}.canvas").read_bytes() == fixture.source_canvas
    assert not (fixture.field_root / f"{NOTE_STEM}.analysis.json").exists()
    _no_registration(fixture)
