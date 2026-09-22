from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.batch import (
    AnalysisBatchConflict,
    AnalysisBatchRunner,
    AnalysisBatchStore,
    AnalysisStageRootError,
    _validate_targeted_repair,
)
from scholar_workflow.analysis.models import (
    AnalysisBatchItem,
    AnalysisBatchRequest,
    AnalysisClaim,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    ConformanceFinding,
    ConformanceReport,
    Evidence,
    EvidenceKind,
    ProfileKind,
)
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis


def _document(title: str) -> AnalysisDocument:
    claims = []
    for role in AnalysisRole:
        claims.append(
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body=f"Readable {role.value} explanation.",
                evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 1"),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
        )
    return AnalysisDocument(
        artifact_id=f"analysis:paper:{title.lower().replace(' ', '-')}",
        paper_title=title,
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=claims,
    )


def _item(item_id: str, title: str) -> AnalysisBatchItem:
    return AnalysisBatchItem(
        item_id=item_id,
        zotero_item_key=item_id.upper(),
        note_stem=f"{title}分析",
        document=_document(title),
    )


def _break_backlink(bundle: AnalysisBundle) -> AnalysisBundle:
    canvas = {"nodes": [dict(node) for node in bundle.canvas["nodes"]], "edges": bundle.canvas["edges"]}
    claim = next(node for node in canvas["nodes"] if "sw-analysis-claim" in node["text"])
    claim["text"] = claim["text"].replace("[[", "[")
    return AnalysisBundle(markdown=bundle.markdown, canvas=canvas)


def test_batch_allows_one_repair_and_persists_repaired_state(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    calls = 0

    def renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
        nonlocal calls
        calls += 1
        bundle = render_analysis(document, note_stem=note_stem)
        return _break_backlink(bundle) if calls == 1 else bundle

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    request = AnalysisBatchRequest(batch_id="batch-one", items=[_item("paper-a", "Paper A")])
    result = runner.run(request, repair=lambda document, _report: document)

    assert result.items[0].state is AnalysisState.REPAIRED
    assert result.items[0].repair_count == 1
    assert calls == 2
    persisted = store.get_item("batch-one", "paper-a")
    assert persisted is not None
    assert persisted.state is AnalysisState.REPAIRED

    repeated = runner.run(request, repair=lambda document, _report: document)
    assert repeated.items[0].state is AnalysisState.REPAIRED
    assert calls == 2


def test_failed_item_is_cleaned_without_rolling_back_valid_sibling(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")

    def renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
        bundle = render_analysis(document, note_stem=note_stem)
        return _break_backlink(bundle) if document.paper_title == "Broken" else bundle

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    request = AnalysisBatchRequest(
        batch_id="batch-isolation",
        items=[_item("broken", "Broken"), _item("valid", "Valid")],
    )
    result = runner.run(request)
    states = {item.item_id: item.state for item in result.items}

    assert states == {"broken": AnalysisState.FAILED, "valid": AnalysisState.VALIDATED}
    assert result.state == "partial"
    assert not (tmp_path / "stage" / "batch-isolation" / "broken").exists()
    assert (tmp_path / "stage" / "batch-isolation" / "valid" / "analysis.md").is_file()
    failed = store.get_item("batch-isolation", "broken")
    assert failed is not None
    assert failed.diagnostics


def test_second_failed_check_does_not_start_another_repair(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    calls = 0

    def renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
        nonlocal calls
        calls += 1
        return _break_backlink(render_analysis(document, note_stem=note_stem))

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    request = AnalysisBatchRequest(batch_id="batch-failed", items=[_item("paper-a", "Paper A")])

    first = runner.run(request, repair=lambda document, _report: document)
    second = runner.run(request, repair=lambda document, _report: document)
    assert first.items[0].state is AnalysisState.FAILED
    assert first.items[0].repair_count == 1
    assert second.items[0].repair_count == 1
    assert calls == 2


def test_batch_id_cannot_be_reused_for_different_request(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage")
    runner.run(AnalysisBatchRequest(batch_id="stable-batch", items=[_item("a", "A")]))

    with pytest.raises(AnalysisBatchConflict, match="different request"):
        runner.run(AnalysisBatchRequest(batch_id="stable-batch", items=[_item("b", "B")]))


def test_repair_budget_is_claimed_before_repair_callback(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")

    def renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
        return _break_backlink(render_analysis(document, note_stem=note_stem))

    def interrupted_repair(document: AnalysisDocument, _report) -> AnalysisDocument:
        raise RuntimeError("repair process interrupted")

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    request = AnalysisBatchRequest(batch_id="repair-crash", items=[_item("paper-a", "Paper A")])
    first = runner.run(request, repair=interrupted_repair)
    second = runner.run(request, repair=interrupted_repair)

    assert first.items[0].state is AnalysisState.FAILED
    assert first.items[0].repair_count == 1
    assert second.items[0].repair_count == 1


def test_cleanup_failure_retains_stage_path_for_audit(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    stage_root = tmp_path / "stage"

    def renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
        owned = stage_root / "cleanup-failure" / "paper-a"
        owned.mkdir(parents=True, exist_ok=True)
        (owned / "unowned.txt").write_text("preserve", encoding="utf-8")
        return _break_backlink(render_analysis(document, note_stem=note_stem))

    runner = AnalysisBatchRunner(store=store, stage_root=stage_root, renderer=renderer)
    request = AnalysisBatchRequest(
        batch_id="cleanup-failure",
        items=[_item("paper-a", "Paper A")],
    )
    result = runner.run(request)

    assert result.items[0].state is AnalysisState.FAILED
    assert result.items[0].stage_path == str(
        stage_root / "cleanup-failure" / "paper-a"
    )
    assert (stage_root / "cleanup-failure" / "paper-a" / "unowned.txt").is_file()


def test_intermediate_stage_symlink_is_rejected_without_touching_victim(
    tmp_path: Path,
) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    stage_root = tmp_path / "stage"
    victim = stage_root / "victim-batch" / "paper-a"
    victim.mkdir(parents=True)
    victim_file = victim / "analysis.md"
    victim_file.write_text("human-owned victim", encoding="utf-8")
    (stage_root / "hostile-batch").mkdir()
    (stage_root / "hostile-batch" / "paper-a").symlink_to(
        victim,
        target_is_directory=True,
    )

    runner = AnalysisBatchRunner(store=store, stage_root=stage_root)
    request = AnalysisBatchRequest(
        batch_id="hostile-batch",
        items=[_item("paper-a", "Paper A"), _item("paper-b", "Paper B")],
    )

    result = runner.run(request)

    assert victim_file.read_text(encoding="utf-8") == "human-owned victim"
    assert {item.item_id: item.state for item in result.items} == {
        "paper-a": AnalysisState.FAILED,
        "paper-b": AnalysisState.VALIDATED,
    }
    assert "cannot traverse a symlink" in result.items[0].diagnostics[0].message


def test_targeted_repair_requires_an_exact_structured_claim_path() -> None:
    original = _document("Paper A")
    repaired_claims = [
        claim.model_copy(update={"body": "unauthorized rewrite"})
        if claim.claim_id == "task"
        else claim
        for claim in original.claims
    ]
    repaired = original.model_copy(update={"claims": repaired_claims})
    report = ConformanceReport(
        ok=False,
        findings=[
            ConformanceFinding(
                code="unexpected-canvas-claim",
                path="canvas/claims/task-extra",
                message="different claim",
            )
        ],
    )

    with pytest.raises(ValueError, match="outside reported findings"):
        _validate_targeted_repair(original, repaired, report)


def test_claim_failure_is_isolated_and_sibling_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage")
    original_claim = store.claim_item

    def fail_first_claim(batch_id: str, item_id: str):
        if item_id == "paper-a":
            raise ValueError("unsafe item claim")
        return original_claim(batch_id, item_id)

    monkeypatch.setattr(store, "claim_item", fail_first_claim)
    request = AnalysisBatchRequest(
        batch_id="claim-isolation",
        items=[_item("paper-a", "Paper A"), _item("paper-b", "Paper B")],
    )

    result = runner.run(request)

    assert {item.item_id: item.state for item in result.items} == {
        "paper-a": AnalysisState.FAILED,
        "paper-b": AnalysisState.VALIDATED,
    }


def test_stage_root_identity_failure_stops_the_batch(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    stage_root = tmp_path / "stage"
    runner = AnalysisBatchRunner(store=store, stage_root=stage_root)
    stage_root.rmdir()
    stage_root.mkdir()
    request = AnalysisBatchRequest(
        batch_id="root-failure",
        items=[_item("paper-a", "Paper A"), _item("paper-b", "Paper B")],
    )

    with pytest.raises(AnalysisStageRootError, match="identity changed"):
        runner.run(request)

    first = store.get_item(request.batch_id, "paper-a")
    second = store.get_item(request.batch_id, "paper-b")
    assert first is not None and first.state is AnalysisState.QUEUED
    assert second is None


def test_targeted_repair_cannot_rewrite_identity_or_unrelated_claims(
    tmp_path: Path,
) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    calls = 0

    def renderer(document: AnalysisDocument, note_stem: str) -> AnalysisBundle:
        nonlocal calls
        calls += 1
        bundle = render_analysis(document, note_stem=note_stem)
        return _break_backlink(bundle) if calls == 1 else bundle

    def rewrite_title(document: AnalysisDocument, _report) -> AnalysisDocument:
        return document.model_copy(update={"paper_title": "Unrelated rewrite"})

    runner = AnalysisBatchRunner(
        store=store,
        stage_root=tmp_path / "stage",
        renderer=renderer,
    )
    request = AnalysisBatchRequest(
        batch_id="targeted-repair",
        items=[_item("paper-a", "Paper A")],
    )

    result = runner.run(request, repair=rewrite_title)

    assert result.items[0].state is AnalysisState.FAILED
    assert result.items[0].repair_count == 1
    assert "paper title" in result.items[0].diagnostics[0].message


def test_two_stores_cannot_claim_the_same_batch_item(tmp_path: Path) -> None:
    database = tmp_path / "analysis.db"
    first = AnalysisBatchStore(database)
    second = AnalysisBatchStore(database)
    item = _item("paper-a", "Paper A")
    request = AnalysisBatchRequest(batch_id="claim-once", items=[item])
    first.ensure_batch(request)
    first.ensure_item(request.batch_id, item)

    claimed = first.claim_item(request.batch_id, item.item_id)

    assert claimed.state is AnalysisState.RUNNING
    with pytest.raises(AnalysisBatchConflict, match="cannot be claimed from running"):
        second.claim_item(request.batch_id, item.item_id)
    first.close()
    second.close()


def test_batch_rejects_duplicate_zotero_identity() -> None:
    first = _item("paper-a", "Paper A")
    second = _item("paper-b", "Paper B").model_copy(
        update={"zotero_item_key": first.zotero_item_key}
    )

    with pytest.raises(ValidationError, match="zotero_item_key values must be unique"):
        AnalysisBatchRequest(batch_id="duplicate-zotero", items=[first, second])
