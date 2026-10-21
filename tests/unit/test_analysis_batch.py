from __future__ import annotations

from copy import deepcopy
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
    ALL_ROLES,
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
    for role in ALL_ROLES:
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
        schema_version=1,
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


def test_concurrent_claim_keeps_owner_state_and_continues_sibling(
    tmp_path: Path,
) -> None:
    database = tmp_path / "analysis.db"
    owner = AnalysisBatchStore(database)
    contender = AnalysisBatchStore(database)
    request = AnalysisBatchRequest(
        batch_id="concurrent-siblings",
        items=[_item("paper-a", "Paper A"), _item("paper-b", "Paper B")],
    )
    owner.ensure_batch(request)
    for item in request.items:
        owner.ensure_item(request.batch_id, item)
    owner.claim_item(request.batch_id, "paper-a")

    result = AnalysisBatchRunner(
        store=contender,
        stage_root=tmp_path / "stage",
    ).run(request)

    states = {item.item_id: item.state for item in result.items}
    assert states == {
        "paper-a": AnalysisState.RUNNING,
        "paper-b": AnalysisState.VALIDATED,
    }
    persisted = owner.get_item(request.batch_id, "paper-a")
    assert persisted is not None and persisted.state is AnalysisState.RUNNING
    assert not (tmp_path / "stage" / request.batch_id / "paper-a").exists()
    owner.close()
    contender.close()


def test_batch_rejects_duplicate_zotero_identity() -> None:
    first = _item("paper-a", "Paper A")
    second = _item("paper-b", "Paper B").model_copy(
        update={"zotero_item_key": first.zotero_item_key}
    )

    with pytest.raises(ValidationError, match="zotero_item_key values must be unique"):
        AnalysisBatchRequest(batch_id="duplicate-zotero", items=[first, second])


def test_failed_item_can_claim_its_unused_repair_in_a_later_invocation(tmp_path):
    database, stage = tmp_path / "analysis.db", tmp_path / "stage"
    request = AnalysisBatchRequest(batch_id="deferred-repair", items=[_item("a", "A")])
    first_store = AnalysisBatchStore(database)
    first = AnalysisBatchRunner(
        store=first_store, stage_root=stage,
        renderer=lambda doc, stem: _break_backlink(render_analysis(doc, note_stem=stem)),
    ).run(request)
    assert first.items[0].state is AnalysisState.FAILED and first.items[0].repair_count == 0
    assert first.items[0].stage_path is None and not (stage / request.batch_id / "a").exists()
    first_store.close()
    store = AnalysisBatchStore(database)
    repairs = []

    def repair(document, report):
        state = store.get_item(request.batch_id, "a")
        assert state.state is AnalysisState.RUNNING and state.repair_count == 1
        assert report.findings == first.items[0].diagnostics
        repairs.append(document)
        return document

    runner = AnalysisBatchRunner(store=store, stage_root=stage)
    repaired = runner.run(request, repair=repair)
    assert repaired.state == "completed"
    assert repaired.items[0].state is AnalysisState.REPAIRED and repaired.items[0].repair_count == 1
    assert len(repairs) == 1
    bundle_dir = Path(repaired.items[0].stage_path)
    before = {path.name: path.read_bytes() for path in bundle_dir.iterdir()}
    assert runner.run(request, repair=repair) == repaired
    assert runner.run(request) == repaired and len(repairs) == 1
    assert {path.name: path.read_bytes() for path in bundle_dir.iterdir()} == before
    store.close()


@pytest.mark.parametrize("interrupted", [False, True])
def test_failed_deferred_repair_cannot_receive_another_budget(tmp_path, interrupted):
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    request = AnalysisBatchRequest(batch_id="deferred-failed", items=[_item("a", "A")])
    calls, repairs = [], []

    def renderer(document, stem):
        calls.append(document)
        return _break_backlink(render_analysis(document, note_stem=stem))

    def repair(document, report):
        repairs.append(document)
        assert store.get_item(request.batch_id, "a").repair_count == 1
        if interrupted:
            raise RuntimeError("Synthetic repair interruption")
        return document

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    assert runner.run(request).items[0].repair_count == 0
    failed = runner.run(request, repair=repair)
    assert failed.items[0].state is AnalysisState.FAILED and failed.items[0].repair_count == 1
    assert failed.items[0].stage_path is None
    assert runner.run(request, repair=repair) == failed
    assert len(repairs) == 1 and len(calls) == (1 if interrupted else 2)
    assert not (tmp_path / "stage" / request.batch_id / "a").exists()
    store.close()


def test_atomic_deferred_repair_claim_excludes_a_second_store(tmp_path):
    database = tmp_path / "analysis.db"
    owner = AnalysisBatchStore(database)
    request = AnalysisBatchRequest(batch_id="repair-claim", items=[_item("a", "A")])
    failed = AnalysisBatchRunner(
        store=owner, stage_root=tmp_path / "stage",
        renderer=lambda doc, stem: _break_backlink(render_analysis(doc, note_stem=stem)),
    ).run(request)
    contender = AnalysisBatchStore(database)
    claimed = owner.claim_repair(request.batch_id, "a")
    assert claimed.state is AnalysisState.RUNNING and claimed.repair_count == 1
    assert claimed.diagnostics == failed.items[0].diagnostics
    with pytest.raises(AnalysisBatchConflict):
        contender.claim_repair(request.batch_id, "a")
    assert contender.get_item(request.batch_id, "a") == claimed
    owner.close()
    contender.close()


@pytest.mark.parametrize("reason", ["nonrepairable", "empty-diagnostics", "retained-stage", "spent"])
def test_ineligible_failed_items_never_start_a_repair(tmp_path, reason):
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    request = AnalysisBatchRequest(batch_id="repair-ineligible", items=[_item("a", "A")])
    store.ensure_batch(request)
    store.ensure_item(request.batch_id, request.items[0])
    findings = [] if reason == "empty-diagnostics" else [ConformanceFinding(
        code="synthetic-finding", path="canvas/claims/task", message="Synthetic failure",
        repairable=reason != "nonrepairable",
    )]
    store.update_item(
        request.batch_id, "a", AnalysisState.FAILED, diagnostics=findings,
        repair_count=int(reason == "spent"),
        stage_path=str(tmp_path / "retained") if reason == "retained-stage" else None,
    )
    expected = store.get_item(request.batch_id, "a")

    def forbidden(*args):
        pytest.fail("An ineligible item must not render or call a repairer")

    result = AnalysisBatchRunner(
        store=store, stage_root=tmp_path / "stage", renderer=forbidden,
    ).run(request, repair=forbidden)
    assert result.items[0] == expected and store.get_item(request.batch_id, "a") == expected
    with pytest.raises(AnalysisBatchConflict):
        store.claim_repair(request.batch_id, "a")
    store.close()


@pytest.mark.parametrize("symlink", [False, True])
def test_deferred_repair_never_cleans_an_unexpected_existing_stage(tmp_path, symlink):
    store, stage = AnalysisBatchStore(tmp_path / "analysis.db"), tmp_path / "stage"
    request = AnalysisBatchRequest(batch_id="foreign-stage", items=[_item("a", "A")])
    first = AnalysisBatchRunner(
        store=store, stage_root=stage,
        renderer=lambda doc, stem: _break_backlink(render_analysis(doc, note_stem=stem)),
    ).run(request)
    assert first.items[0].state is AnalysisState.FAILED
    directory = stage / request.batch_id / "a"
    if symlink:
        victim = tmp_path / "foreign-victim"
        victim.mkdir()
        directory.parent.mkdir(parents=True)
        directory.symlink_to(victim, target_is_directory=True)
    else:
        directory.mkdir(parents=True)
    foreign = directory / "analysis.md"
    foreign.write_text("A foreign file must survive, even with a known basename.")

    def forbidden(*args):
        pytest.fail("Stage conflict must be rejected before model/render callbacks")

    result = AnalysisBatchRunner(store=store, stage_root=stage, renderer=forbidden).run(
        request, repair=forbidden,
    )
    assert result.items[0].state is AnalysisState.FAILED and result.items[0].repair_count == 1
    assert result.items[0].stage_path == str(directory)
    assert any(not finding.repairable for finding in result.items[0].diagnostics)
    assert foreign.read_text() == "A foreign file must survive, even with a known basename."
    assert directory.is_symlink() is symlink
    store.close()


def _geometry_document():
    return AnalysisDocument.model_validate({
        "schema_version": 5, "artifact_id": "analysis:paper:synthetic-summary-repair",
        "paper_title": "Synthetic Summary Repair", "language": "en",
        "profile": {"kind": "focused", "roles": ["method"], "framework": "reference_tree_v5", "markdown_quotes": True},
        "claims": [{
            "claim_id": name, "role": "method", "outline_path": f"method/modules/{name}",
            "title": f"Synthetic {name}", "body": "Synthetic complete body is immutable.",
            "canvas_summary": "Synthetic original summary.",
            "evidence": {"kind": "not_applicable", "detail": "Synthetic geometry only."},
            "points": [{
                "point_id": slot, "text": "Synthetic full point is immutable.",
                "canvas_summary": "Synthetic original point summary.",
                "evidence": {"kind": "not_applicable", "detail": "Synthetic geometry only."},
            } for slot in ("motivation", "method")],
        } for name in ("alpha", "beta")],
    })


def _aspect_report():
    return ConformanceReport(ok=False, findings=[ConformanceFinding(
        code="canvas-aspect-limit", path="canvas/geometry", message="Synthetic tall layout.",
    )])


@pytest.mark.parametrize("scope", ["claim", "point", "both"])
def test_global_aspect_repair_allows_only_canvas_summary_fields(scope):
    original = _geometry_document()
    raw = original.model_dump(mode="json")
    if scope in {"claim", "both"}:
        raw["claims"][0]["canvas_summary"] = "Synthetic shorter summary."
    if scope in {"point", "both"}:
        raw["claims"][0]["points"][0]["canvas_summary"] = "Synthetic shorter point."
    repaired = AnalysisDocument.model_validate(raw)
    _validate_targeted_repair(original, repaired, _aspect_report())


@pytest.mark.parametrize("change", ["body", "point-text", "evidence", "title", "claims-order", "points-order"])
def test_global_aspect_repair_does_not_authorize_other_changes(change):
    original = _geometry_document()
    raw = deepcopy(original.model_dump(mode="json"))
    if change == "body":
        raw["claims"][0]["body"] = "Unauthorized body rewrite."
    elif change == "point-text":
        raw["claims"][0]["points"][0]["text"] = "Unauthorized point rewrite."
    elif change == "evidence":
        raw["claims"][0]["evidence"]["detail"] = "Unauthorized evidence rewrite."
    elif change == "title":
        raw["claims"][0]["title"] = "Unauthorized title rewrite"
    elif change == "claims-order":
        raw["claims"].reverse()
    else:
        raw["claims"][0]["points"].reverse()
    with pytest.raises(ValueError):
        _validate_targeted_repair(original, AnalysisDocument.model_validate(raw), _aspect_report())


def test_an_unrelated_global_finding_does_not_authorize_summary_rewrites():
    original = _geometry_document()
    raw = original.model_dump(mode="json")
    raw["claims"][0]["canvas_summary"] = "A different summary."
    unrelated = ConformanceReport(ok=False, findings=[ConformanceFinding(
        code="unrelated-finding", path="canvas/geometry", message="Not an aspect finding.",
    )])
    with pytest.raises(ValueError, match="outside reported findings"):
        _validate_targeted_repair(original, AnalysisDocument.model_validate(raw), unrelated)


def test_interrupted_deferred_owner_is_not_restarted_after_reopening_store(tmp_path):
    database, stage = tmp_path / "analysis.db", tmp_path / "stage"
    store = AnalysisBatchStore(database)
    request = AnalysisBatchRequest(batch_id="repair-process-loss", items=[_item("a", "A")])
    AnalysisBatchRunner(
        store=store, stage_root=stage,
        renderer=lambda doc, stem: _break_backlink(render_analysis(doc, note_stem=stem)),
    ).run(request)

    def interrupted(document, report):
        raise KeyboardInterrupt("Synthetic process loss, not an ordinary callback error")

    with pytest.raises(KeyboardInterrupt):
        AnalysisBatchRunner(store=store, stage_root=stage).run(request, repair=interrupted)
    pending = store.get_item(request.batch_id, "a")
    assert pending.state is AnalysisState.RUNNING and pending.repair_count == 1
    assert pending.stage_path == str(stage / request.batch_id / "a")
    store.close()
    reopened = AnalysisBatchStore(database)

    def forbidden(*args):
        pytest.fail("A persisted running owner must not be restarted")

    replay = AnalysisBatchRunner(store=reopened, stage_root=stage, renderer=forbidden).run(
        request, repair=forbidden,
    )
    assert replay.items[0] == pending and Path(pending.stage_path).is_dir()
    reopened.close()


def test_competing_runner_cannot_touch_repair_owner_or_valid_sibling(tmp_path):
    database, stage = tmp_path / "analysis.db", tmp_path / "stage"
    owner, contender = AnalysisBatchStore(database), AnalysisBatchStore(database)
    request = AnalysisBatchRequest(batch_id="repair-race", items=[_item("a", "A"), _item("b", "B")])
    initial = AnalysisBatchRunner(
        store=owner, stage_root=stage,
        renderer=lambda doc, stem: (
            _break_backlink(render_analysis(doc, note_stem=stem))
            if doc.paper_title == "A" else render_analysis(doc, note_stem=stem)
        ),
    ).run(request)
    sibling_dir = Path(initial.items[1].stage_path)
    sibling = {path.name: path.read_bytes() for path in sibling_dir.iterdir()}
    competing = []

    def forbidden(*args):
        pytest.fail("A contender must not render or repair the claimed item")

    def repair(document, report):
        own_stage = stage / request.batch_id / "a"
        marker = own_stage / ".analysis.md.tmp"
        marker.write_text("Repair owner controls this stage")
        competing.append(AnalysisBatchRunner(
            store=contender, stage_root=stage, renderer=forbidden,
        ).run(request, repair=forbidden))
        assert marker.read_text() == "Repair owner controls this stage"
        assert {path.name: path.read_bytes() for path in sibling_dir.iterdir()} == sibling
        return document

    final = AnalysisBatchRunner(store=owner, stage_root=stage).run(request, repair=repair)
    assert final.state == "completed"
    assert [item.state for item in final.items] == [AnalysisState.REPAIRED, AnalysisState.VALIDATED]
    assert [item.state for item in competing[0].items] == [AnalysisState.RUNNING, AnalysisState.VALIDATED]
    assert competing[0].items[0].repair_count == 1
    assert {path.name: path.read_bytes() for path in sibling_dir.iterdir()} == sibling
    owner.close()
    contender.close()


def test_a_deferred_repair_does_not_relax_the_original_request_fingerprint(tmp_path):
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    request = AnalysisBatchRequest(batch_id="repair-fingerprint", items=[_item("a", "A")])
    runner = AnalysisBatchRunner(
        store=store, stage_root=tmp_path / "stage",
        renderer=lambda doc, stem: _break_backlink(render_analysis(doc, note_stem=stem)),
    )
    failed = runner.run(request).items[0]
    changed = request.model_dump(mode="json")
    changed["items"][0]["document"]["paper_title"] = "Another title"

    def forbidden(*args):
        pytest.fail("Changed original input must not spend a repair")

    with pytest.raises(AnalysisBatchConflict, match="different request"):
        runner.run(AnalysisBatchRequest.model_validate(changed), repair=forbidden)
    assert store.get_item(request.batch_id, "a") == failed
    store.close()
