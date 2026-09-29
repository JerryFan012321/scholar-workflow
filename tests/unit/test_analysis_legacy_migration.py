"""Fixture-only checks for conservative legacy analysis migration planning."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.legacy_migration import (
    LegacyFieldMapping,
    LegacyFragment,
    LegacyMigrationError,
    LegacyMigrationPlan,
    LegacyTarget,
    LegacyUnmarkedDecision,
    parse_legacy_analysis,
    parse_legacy_fields,
    validate_legacy_migration,
)
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _source(*fields: tuple[str, bytes]) -> bytes:
    return b"".join(
        content
        + b"\n"
        + (
            f'<!-- sw-analysis-field path="{path}" '
            f'base_sha256="{_sha256(_legacy_normalized(content))}" -->'
        ).encode()
        + b"\n"
        for path, content in fields
    )


def _legacy_normalized(content: bytes) -> bytes:
    return "\n".join(line.rstrip(" \t") for line in content.decode("utf-8").splitlines()).encode()


def _document() -> AnalysisDocument:
    return AnalysisDocument.model_validate(
        {
            "schema_version": 2,
            "artifact_id": "analysis:fixture-paper",
            "paper_title": "Fixture Paper",
            "profile": {"kind": "whole"},
            "claims": [
                {
                    "claim_id": "task",
                    "role": "task",
                    "title": "Task",
                    "body": "Original task statement",
                    "evidence": {"kind": "author_stated", "anchor": "§1"},
                    "points": [
                        {
                            "point_id": "source",
                            "text": "A separate reported fact",
                            "evidence": {"kind": "author_stated", "anchor": "§1"},
                        }
                    ],
                },
                {
                    "claim_id": "input",
                    "role": "input",
                    "title": "Input",
                    "body": "Original input statement",
                    "evidence": {"kind": "author_stated", "anchor": "§2"},
                },
                {
                    "claim_id": "step",
                    "role": "workflow",
                    "title": "Step",
                    "body": "Original workflow statement",
                    "order": 1,
                    "evidence": {"kind": "author_stated", "anchor": "§3"},
                },
                {
                    "claim_id": "output",
                    "role": "output",
                    "title": "Output",
                    "body": "Original output statement",
                    "evidence": {"kind": "author_stated", "anchor": "§4"},
                },
                {
                    "claim_id": "boundary",
                    "role": "boundary",
                    "title": "Boundary",
                    "body": "Original boundary statement",
                    "evidence": {"kind": "analysis_inference", "detail": "fixture observation"},
                },
            ],
        }
    )


def _fixture() -> tuple[bytes, AnalysisDocument, str, LegacyMigrationPlan]:
    source = _source(
        ("task", b"Original task statement"),
        ("task/evidence", b"Old citation: section 1"),
        ("input", b"Original input statement"),
        ("workflow", b"Original workflow statement"),
        ("output", b"Original output statement"),
        ("boundary", b"Original boundary statement"),
    )
    document = _document()
    markdown = render_analysis(document, note_stem="Fixture Paper分析").markdown
    mappings: list[LegacyFieldMapping] = []
    for span in parse_legacy_fields(source):
        target = (
            LegacyTarget("task", "source")
            if span.path == "task/evidence"
            else LegacyTarget("step" if span.path == "workflow" else span.path)
        )
        disposition = "rewrite" if span.path.endswith("/evidence") else "copy"
        mappings.append(
            LegacyFieldMapping(
                path=span.path,
                source_sha256=span.sha256,
                fragments=(
                    LegacyFragment(
                        start=0,
                        end=len(span.content),
                        sha256=span.sha256,
                        disposition=disposition,
                        target=target,
                    ),
                ),
            )
        )
    plan = LegacyMigrationPlan(
        source_sha256=_sha256(source),
        expected_field_count=len(mappings),
        mappings=tuple(mappings),
        split_targets={},
    )
    return source, document, markdown, plan


def _codes(report: object) -> set[str]:
    return {finding.code for finding in report.findings}


def test_fixture_requires_external_review_digest_and_normal_bundle_conformance() -> None:
    source, document, markdown, plan = _fixture()
    pending = validate_legacy_migration(source, document, markdown, plan)
    assert not pending.ok
    assert pending.review_required
    assert _codes(pending) == {"human-review-required"}

    approved = validate_legacy_migration(
        source, document, markdown, plan, approved_review_digest=pending.plan_digest
    )
    assert approved.ok
    assert validate_bundle(
        document,
        render_analysis(document, note_stem="Fixture Paper分析"),
        note_stem="Fixture Paper分析",
    ).ok


@pytest.mark.parametrize("end_delta", [-1, 1])
def test_fragment_partition_rejects_gap_or_out_of_range(end_delta: int) -> None:
    source, document, markdown, plan = _fixture()
    first = plan.mappings[0]
    bad_fragment = replace(first.fragments[0], end=first.fragments[0].end + end_delta)
    mappings = (replace(first, fragments=(bad_fragment,)), *plan.mappings[1:])
    report = validate_legacy_migration(source, document, markdown, replace(plan, mappings=mappings))
    assert "fragment-coverage" in _codes(report)


def test_split_requires_exact_declared_destinations_and_byte_coverage() -> None:
    source, document, markdown, _plan = _fixture()
    mixed = b"Original task statementOriginal input statement"
    source = _source(("mixed", mixed))
    span = parse_legacy_fields(source)[0]
    boundary = len(b"Original task statement")
    task = LegacyTarget("task")
    input_target = LegacyTarget("input")
    mapping = LegacyFieldMapping(
        path="mixed",
        source_sha256=span.sha256,
        fragments=(
            LegacyFragment(0, boundary, _sha256(mixed[:boundary]), "copy", task),
            LegacyFragment(boundary, len(mixed), _sha256(mixed[boundary:]), "copy", input_target),
        ),
    )
    plan = LegacyMigrationPlan(_sha256(source), 1, (mapping,), {})
    report = validate_legacy_migration(source, document, markdown, plan)
    assert "split-target-mismatch" in _codes(report)
    declared = replace(plan, split_targets={"mixed": (task, input_target)})
    assert validate_legacy_migration(source, document, markdown, declared).ok


def test_missing_path_and_duplicate_mapping_fail_closed() -> None:
    source, document, markdown, plan = _fixture()
    missing = replace(plan, mappings=plan.mappings[1:])
    assert "missing-path-mapping" in _codes(
        validate_legacy_migration(source, document, markdown, missing)
    )
    duplicate = replace(plan, mappings=(*plan.mappings, plan.mappings[0]))
    assert "duplicate-path-mapping" in _codes(
        validate_legacy_migration(source, document, markdown, duplicate)
    )


def test_detached_evidence_cannot_be_copied_or_left_pending() -> None:
    source, document, markdown, plan = _fixture()
    evidence = plan.mappings[1]
    copied = replace(evidence, fragments=(replace(evidence.fragments[0], disposition="copy"),))
    report = validate_legacy_migration(
        source,
        document,
        markdown,
        replace(plan, mappings=(plan.mappings[0], copied, *plan.mappings[2:])),
    )
    assert "evidence-unmapped" in _codes(report)
    pending = replace(evidence, fragments=(replace(evidence.fragments[0], disposition="pending"),))
    report = validate_legacy_migration(
        source,
        document,
        markdown,
        replace(plan, mappings=(plan.mappings[0], pending, *plan.mappings[2:])),
    )
    assert {"evidence-unmapped", "pending-decision"}.issubset(_codes(report))


def test_copy_must_be_present_in_target_and_once_in_markdown() -> None:
    source, document, markdown, plan = _fixture()
    report = validate_legacy_migration(
        source, document, markdown.replace("Original task statement", "Shortened task"), plan
    )
    assert "copy-count-in-markdown" in _codes(report)
    duplicate = validate_legacy_migration(
        source, document, markdown + "\nOriginal task statement\n", plan
    )
    assert "copy-count-in-markdown" in _codes(duplicate)


def test_digest_is_bound_to_source_candidate_and_mapping() -> None:
    source, document, markdown, plan = _fixture()
    base = validate_legacy_migration(source, document, markdown, plan)
    changed_candidate = validate_legacy_migration(
        source,
        document,
        markdown + "\nNew paragraph\n",
        plan,
        approved_review_digest=base.plan_digest,
    )
    assert "human-review-required" in _codes(changed_candidate)
    changed_source = validate_legacy_migration(
        source.replace(b"Original task statement", b"Updated task statement"),
        document,
        markdown,
        plan,
        approved_review_digest=base.plan_digest,
    )
    assert {"source-changed", "field-changed", "human-review-required"}.issubset(
        _codes(changed_source)
    )


def test_malformed_duplicate_legacy_path_is_not_inventoried() -> None:
    source = _source(("task", b"one"), ("task", b"two"))
    with pytest.raises(LegacyMigrationError, match="duplicate"):
        parse_legacy_fields(source)


def test_realistic_legacy_lines_are_separated_from_yaml_and_normalized_for_baseline() -> None:
    source = b"---\nsw_schema: 1\n---\n\n" + _source(
        ("paper-analysis", b"# Old paper title"),
        ("abstract/task", b"- **Task:** Old visible statement  \n  continuation\t"),
    ).replace(b"\n- **Task:**", b"\n\n- **Task:**")
    inventory = parse_legacy_analysis(source)
    assert [span.path for span in inventory.fields] == ["paper-analysis", "abstract/task"]
    assert inventory.fields[0].content == b"# Old paper title"
    assert inventory.fields[1].content == b"- **Task:** Old visible statement  \n  continuation\t"
    assert all(span.baseline_matches for span in inventory.fields)
    assert len(inventory.unmarked) == 1
    assert inventory.unmarked[0].location == "before:paper-analysis"
    assert inventory.unmarked[0].content.startswith(b"---\nsw_schema: 1")


def test_unmarked_preamble_and_tail_require_distinct_decisions() -> None:
    source, document, markdown, plan = _fixture()
    source = b"Human preface not annotated\n\n" + source + b"Human tail not annotated\n"
    inventory = parse_legacy_analysis(source)
    assert [row.location for row in inventory.unmarked] == ["before:task", "tail"]
    plan = replace(plan, source_sha256=_sha256(source))
    missing = validate_legacy_migration(source, document, markdown, plan)
    assert _codes(missing) == {"missing-unmarked-decision", "human-review-required"}

    decisions = tuple(
        LegacyUnmarkedDecision(row.location, row.sha256, "rewrite") for row in inventory.unmarked
    )
    planned = replace(plan, unmarked=decisions)
    pending_review = validate_legacy_migration(source, document, markdown, planned)
    assert _codes(pending_review) == {"human-review-required"}
    approved = validate_legacy_migration(
        source,
        document,
        markdown,
        planned,
        approved_review_digest=pending_review.plan_digest,
    )
    assert approved.ok


def test_human_changed_historical_field_cannot_auto_copy_even_with_digest() -> None:
    source, document, _markdown, plan = _fixture()
    edited = source.replace(
        b"Original task statement\n",
        b"Human revised task statement\n",
        1,
    )
    spans = parse_legacy_fields(edited)
    assert not spans[0].baseline_matches
    revised_claim = document.claims[0].model_copy(update={"body": "Human revised task statement"})
    revised = document.model_copy(update={"claims": [revised_claim, *document.claims[1:]]})
    markdown = render_analysis(revised, note_stem="Fixture Paper分析").markdown
    first = plan.mappings[0]
    updated_first = replace(
        first,
        source_sha256=spans[0].sha256,
        fragments=(
            replace(
                first.fragments[0],
                end=len(spans[0].content),
                sha256=spans[0].sha256,
            ),
        ),
    )
    changed_plan = replace(
        plan,
        source_sha256=_sha256(edited),
        mappings=(updated_first, *plan.mappings[1:]),
    )
    first_report = validate_legacy_migration(edited, revised, markdown, changed_plan)
    assert "human-edited-field-copy" in _codes(first_report)
    approved = validate_legacy_migration(
        edited,
        revised,
        markdown,
        changed_plan,
        approved_review_digest=first_report.plan_digest,
    )
    assert "human-edited-field-copy" in _codes(approved)


def test_human_changed_field_can_only_proceed_as_reviewed_rewrite() -> None:
    source, document, markdown, plan = _fixture()
    edited = source.replace(b"Original task statement\n", b"Human revision\n", 1)
    span = parse_legacy_fields(edited)[0]
    first = plan.mappings[0]
    reviewed = replace(
        first,
        source_sha256=span.sha256,
        fragments=(
            replace(
                first.fragments[0],
                end=len(span.content),
                sha256=span.sha256,
                disposition="rewrite",
            ),
        ),
    )
    planned = replace(plan, source_sha256=_sha256(edited), mappings=(reviewed, *plan.mappings[1:]))
    pending = validate_legacy_migration(edited, document, markdown, planned)
    assert _codes(pending) == {"human-review-required"}
    assert validate_legacy_migration(
        edited, document, markdown, planned, approved_review_digest=pending.plan_digest
    ).ok


def test_legacy_marker_must_occupy_its_own_line() -> None:
    source = _source(("task", b"old text"))
    source = source.replace(b"old text\n<!--", b"old text <!--")
    with pytest.raises(LegacyMigrationError, match="complete visible line|own line"):
        parse_legacy_analysis(source)
