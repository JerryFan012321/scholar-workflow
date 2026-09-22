from __future__ import annotations

import json
import multiprocessing
import queue
from hashlib import sha256
from pathlib import Path

import pytest

from scholar_workflow.analysis.commit import (
    AnalysisCommitConflict,
    AnalysisCommitError,
    AnalysisCommitPartialError,
    AnalysisCommitSafetyError,
    commit_analysis_bundle,
)
from scholar_workflow.analysis.models import (
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeProjection,
    KnowledgeRelation,
    ProfileKind,
)
from scholar_workflow.analysis.updates import render_analysis_projection


def _document() -> AnalysisDocument:
    return AnalysisDocument(
        artifact_id="analysis:paper:commit",
        paper_title="Commit Paper",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body=f"Readable {role.value}; [[free-prose-link]] is not a relation.",
                evidence=Evidence(
                    kind=EvidenceKind.AUTHOR_STATED,
                    anchor="Section 1",
                ),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
            for role in AnalysisRole
        ],
    )


def _request(
    document: AnalysisDocument,
    *,
    base_revisions: dict[str, str | None] | None = None,
) -> AnalysisCommitRequest:
    paths = AnalysisCanonicalPaths(
        markdown="topic/Commit分析.md",
        canvas="topic/Commit解析树.canvas",
        sidecar="topic/Commit分析.analysis.json",
    )
    return AnalysisCommitRequest(
        commit_id="commit-one",
        batch_id="batch-one",
        item_id="paper-one",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:commit",
        note_stem="Commit分析",
        document=document,
        paths=paths,
        base_revisions=base_revisions
        or {path: None for path in paths.as_list()},
        relations=[
            KnowledgeRelation(
                from_id="paper:commit",
                relation="has-analysis",
                to_id=document.artifact_id,
            )
        ],
        projections=[
            KnowledgeProjection(
                projection_id="projection:commit",
                kind="obsidian",
                target_id=document.artifact_id,
            )
        ],
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    (vault / "topic").mkdir(parents=True)
    state = tmp_path / "state"
    return vault, state


def _digest(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _concurrent_commit_worker(
    vault: str,
    state: str,
    request_json: str,
    fail_after_markdown: bool,
    entered,
    release,
    result,
) -> None:
    request = AnalysisCommitRequest.model_validate_json(request_json)
    bundle, baseline = render_analysis_projection(
        request.document,
        note_stem=request.note_stem,
    )

    def inject(point: str) -> None:
        if fail_after_markdown and point == f"after-replace:{request.paths.markdown}":
            entered.set()
            if not release.wait(10):
                raise TimeoutError("test release timed out")
            raise RuntimeError("injected concurrent rollback")

    if not fail_after_markdown:
        entered.set()
    try:
        receipt = commit_analysis_bundle(
            vault_root=Path(vault),
            state_root=Path(state),
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=inject if fail_after_markdown else None,
        )
        result.put(("ok", receipt.commit_id))
    except Exception as exc:  # noqa: BLE001 - cross-process test result
        result.put((type(exc).__name__, str(exc)))


def test_commit_is_canonical_idempotent_and_change_set_is_explicit(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    first = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )
    second = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )

    assert second == first
    assert (vault / request.paths.markdown).read_text(encoding="utf-8") == bundle.markdown
    assert json.loads((vault / request.paths.canvas).read_text(encoding="utf-8")) == bundle.canvas
    assert len(first.change_set.upsert_artifacts) == 3
    assert first.change_set.upsert_relations == request.relations
    assert first.change_set.upsert_projections == request.projections
    assert "free-prose-link" not in first.change_set.model_dump_json()


def test_commit_rejects_canvas_outside_the_shared_standard(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    bundle.canvas["nodes"].append(
        {
            "id": "human-zero-width",
            "type": "group",
            "x": 9000,
            "y": 9000,
            "width": 0,
            "height": 10,
            "label": "Invalid group",
        }
    )
    request = _request(document)

    with pytest.raises(AnalysisCommitError, match="invalid-json-canvas-contract"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_commit_cas_never_overwrites_a_human_edit(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    target = vault / request.paths.markdown
    target.write_text("human edit", encoding="utf-8")

    with pytest.raises(AnalysisCommitConflict, match="base revision changed"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )

    assert target.read_text(encoding="utf-8") == "human edit"


def test_fault_rolls_back_only_files_still_owned_by_the_commit(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    def fail_after_canvas(point: str) -> None:
        if point == f"after-replace:{request.paths.canvas}":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=fail_after_canvas,
        )

    assert not (vault / request.paths.markdown).exists()
    assert not (vault / request.paths.canvas).exists()
    assert not (vault / request.paths.sidecar).exists()
    journal = json.loads(
        (state / "analysis-commits" / "journals" / "commit-one.json").read_text()
    )
    assert journal["status"] == "rolled_back"


def test_conditional_rollback_preserves_concurrent_human_content(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    markdown = vault / request.paths.markdown

    def edit_then_fail(point: str) -> None:
        if point == f"after-replace:{request.paths.markdown}":
            markdown.write_text("concurrent human edit", encoding="utf-8")
            raise RuntimeError("injected after edit")

    with pytest.raises(AnalysisCommitPartialError, match="concurrent edits"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=edit_then_fail,
        )

    assert markdown.read_text(encoding="utf-8") == "concurrent human edit"


def test_fault_restores_replaced_bundle_from_verified_backups(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    paths = AnalysisCanonicalPaths(
        markdown="topic/Commit分析.md",
        canvas="topic/Commit解析树.canvas",
        sidecar="topic/Commit分析.analysis.json",
    )
    originals = {
        paths.markdown: b"old markdown",
        paths.canvas: b'{"nodes": [], "edges": []}\n',
        paths.sidecar: b'{"old": true}\n',
    }
    for relative_path, payload in originals.items():
        (vault / relative_path).write_bytes(payload)
    request = _request(
        document,
        base_revisions={
            relative_path: _digest(payload)
            for relative_path, payload in originals.items()
        },
    )

    def fail_after_canvas(point: str) -> None:
        if point == f"after-replace:{request.paths.canvas}":
            raise RuntimeError("injected replacement failure")

    with pytest.raises(RuntimeError, match="replacement failure"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=fail_after_canvas,
        )

    assert {
        relative_path: (vault / relative_path).read_bytes()
        for relative_path in originals
    } == originals


def test_commit_rejects_symlink_target_without_touching_victim(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    victim = tmp_path / "victim.md"
    victim.write_text("victim", encoding="utf-8")
    (vault / request.paths.markdown).symlink_to(victim)

    with pytest.raises(AnalysisCommitSafetyError, match="symlink"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )

    assert victim.read_text(encoding="utf-8") == "victim"


def test_pre_replace_recheck_detects_edit_after_initial_cas(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    markdown = vault / request.paths.markdown

    def edit_before_replace(point: str) -> None:
        if point == f"before-replace:{request.paths.markdown}":
            markdown.write_text("human edit during commit", encoding="utf-8")

    with pytest.raises(AnalysisCommitPartialError, match="concurrent edits"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=edit_before_replace,
        )

    assert markdown.read_text(encoding="utf-8") == "human edit during commit"


@pytest.mark.parametrize(
    "tamper",
    ["path", "before", "after", "artifact", "change-set"],
)
def test_replay_rejects_receipt_fields_that_do_not_match_request(
    tmp_path: Path,
    tamper: str,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    receipt = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )
    payload = receipt.model_dump(mode="json")
    if tamper == "path":
        old_path = payload["files"][0]["path"]
        new_path = "topic/Forged分析.md"
        payload["files"][0]["path"] = new_path
        payload["change_set"]["expected_base_hashes"][new_path] = payload[
            "change_set"
        ]["expected_base_hashes"].pop(old_path)
        payload["change_set"]["upsert_artifacts"][0]["vault_path"] = new_path
    elif tamper == "before":
        forged = "sha256:" + "0" * 64
        payload["files"][0]["before_sha256"] = forged
        payload["files"][0]["action"] = "replaced"
        payload["change_set"]["expected_base_hashes"][
            payload["files"][0]["path"]
        ] = forged
    elif tamper == "after":
        forged = "sha256:" + "0" * 64
        payload["files"][0]["after_sha256"] = forged
        payload["change_set"]["upsert_artifacts"][0]["sha256"] = forged
    elif tamper == "artifact":
        payload["artifact_id"] = "analysis:forged"
        for artifact in payload["change_set"]["upsert_artifacts"]:
            suffix = {
                "analysis_markdown": "",
                "analysis_canvas": ":canvas",
                "analysis_sidecar": ":sidecar",
            }[artifact["kind"]]
            artifact["artifact_id"] = f"analysis:forged{suffix}"
    else:
        payload["change_set"]["upsert_projections"].append(
            {
                "projection_id": "projection:forged",
                "kind": "obsidian",
                "target_id": document.artifact_id,
            }
        )

    receipt_path = (
        state / "analysis-commits" / "receipts" / f"{request.commit_id}.json"
    )
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AnalysisCommitSafetyError, match="does not match the request"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )


def test_replay_rejects_forged_empty_receipt_without_canonical_files(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    receipt_dir = state / "analysis-commits" / "receipts"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / f"{request.commit_id}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "commit_id": request.commit_id,
                "request_fingerprint": "sha256:" + "0" * 64,
                "artifact_id": document.artifact_id,
                "state": "committed",
                "committed_at": "not-a-date",
                "files": [],
                "change_set": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AnalysisCommitSafetyError, match="invalid commit receipt"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )


def test_rollback_preserves_same_content_replacement_with_a_new_inode(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    markdown = vault / request.paths.markdown
    replacement_inode: int | None = None

    def replace_with_same_content_then_fail(point: str) -> None:
        nonlocal replacement_inode
        if point == f"after-replace:{request.paths.markdown}":
            replacement = markdown.with_name("same-content-winner.md")
            replacement.write_bytes(markdown.read_bytes())
            replacement.replace(markdown)
            replacement_inode = markdown.stat().st_ino
            raise RuntimeError("concurrent same-content winner")

    with pytest.raises(AnalysisCommitPartialError, match="concurrent edits"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=replace_with_same_content_then_fail,
        )

    assert markdown.is_file()
    assert markdown.read_text(encoding="utf-8") == bundle.markdown
    assert markdown.stat().st_ino == replacement_inode


def test_change_set_assigns_every_artifact_to_the_requested_resource(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    receipt = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )

    assert {
        artifact.resource_id for artifact in receipt.change_set.upsert_artifacts
    } == {request.resource_id}


def test_vault_lock_serializes_commits_even_with_different_state_roots(
    tmp_path: Path,
) -> None:
    vault, _state = _roots(tmp_path)
    request = _request(_document())
    context = multiprocessing.get_context("spawn")
    first_entered = context.Event()
    second_entered = context.Event()
    release = context.Event()
    first_result = context.Queue()
    second_result = context.Queue()
    first = context.Process(
        target=_concurrent_commit_worker,
        args=(
            str(vault),
            str(tmp_path / "state-one"),
            request.model_dump_json(),
            True,
            first_entered,
            release,
            first_result,
        ),
    )
    second = context.Process(
        target=_concurrent_commit_worker,
        args=(
            str(vault),
            str(tmp_path / "state-two"),
            request.model_dump_json(),
            False,
            second_entered,
            release,
            second_result,
        ),
    )
    first.start()
    assert first_entered.wait(10)
    second.start()
    assert second_entered.wait(10)
    with pytest.raises(queue.Empty):
        second_result.get(timeout=0.5)

    release.set()
    first_outcome = first_result.get(timeout=10)
    second_outcome = second_result.get(timeout=10)
    first.join(timeout=10)
    second.join(timeout=10)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert first_outcome[0] == "RuntimeError"
    assert second_outcome == ("ok", request.commit_id)
    for relative_path in request.paths.as_list():
        assert (vault / relative_path).is_file()
