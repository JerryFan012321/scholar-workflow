"""Read-only conservation gate for legacy field-by-field paper analyses.

This module does not infer semantic equivalence or write artifacts. A caller must
obtain human approval for every rewritten or retired fragment, bound to the
exact source, candidate, and mapping digest returned by this gate. The normal
analysis bundle conformance check remains a separate required gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

from scholar_workflow.analysis.models import AnalysisDocument, AnalysisPoint

_FIELD_MARKER = re.compile(
    rb'<!--[ \t]*sw-analysis-field[ \t]+path="(?P<path>[a-z0-9][a-z0-9/-]*)"'
    rb'[ \t]+base_sha256="(?P<base>[0-9a-f]{64})"[ \t]*-->'
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LegacyMigrationError(ValueError):
    """The legacy source cannot be safely inventoried."""


@dataclass(frozen=True)
class LegacyFieldSpan:
    path: str
    content: bytes
    sha256: str
    base_sha256: str
    baseline_matches: bool


@dataclass(frozen=True)
class LegacyUnmarkedSpan:
    location: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class LegacyAnalysisInventory:
    fields: tuple[LegacyFieldSpan, ...]
    unmarked: tuple[LegacyUnmarkedSpan, ...]


@dataclass(frozen=True)
class LegacyTarget:
    claim_id: str
    point_id: str | None = None


@dataclass(frozen=True)
class LegacyFragment:
    """Half-open byte range relative to one legacy field's pre-marker content."""

    start: int
    end: int
    sha256: str
    disposition: Literal["copy", "rewrite", "retire", "pending"]
    target: LegacyTarget | None = None


@dataclass(frozen=True)
class LegacyFieldMapping:
    path: str
    source_sha256: str
    fragments: tuple[LegacyFragment, ...]


@dataclass(frozen=True)
class LegacyUnmarkedDecision:
    location: str
    source_sha256: str
    disposition: Literal["copy", "rewrite", "retire", "pending"]


@dataclass(frozen=True)
class LegacyMigrationPlan:
    source_sha256: str
    expected_field_count: int
    mappings: tuple[LegacyFieldMapping, ...]
    split_targets: dict[str, tuple[LegacyTarget, ...]]
    unmarked: tuple[LegacyUnmarkedDecision, ...] = ()


@dataclass(frozen=True)
class LegacyMigrationFinding:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class LegacyMigrationReport:
    ok: bool
    plan_digest: str
    findings: tuple[LegacyMigrationFinding, ...]
    review_required: bool


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _legacy_visible_hash(content: bytes) -> str:
    """Use the historical per-field hash, not the raw inter-marker byte hash."""
    normalized = "\n".join(line.rstrip(" \t") for line in content.decode("utf-8").splitlines())
    return _sha256(normalized.encode("utf-8"))


def _split_visible_region(region: bytes) -> tuple[bytes, bytes]:
    """Separate an immediately preceding field from unmarked earlier prose.

    An old marker follows its heading/field on the next line. The last blank
    separator before that line bounds the visible field; earlier material is
    unmarked and must be adjudicated separately. Ambiguous multi-paragraph
    fields therefore fail closed as unmarked material instead of being adopted.
    """
    if not region.endswith(b"\n"):
        raise LegacyMigrationError("legacy marker does not follow a complete visible line")
    body = region[:-1]
    if body.endswith(b"\r"):
        body = body[:-1]
    start = 0
    offset = 0
    for line in body.splitlines(keepends=True):
        offset += len(line)
        if not line.strip():
            start = offset
    visible = body[start:]
    if not visible.strip():
        raise LegacyMigrationError("legacy marker has no preceding visible field")
    return body[:start], visible


def parse_legacy_analysis(source_markdown: bytes) -> LegacyAnalysisInventory:
    """Inventory old visible fields plus nonblank unmarked prelude/interludes/tail."""
    try:
        source_markdown.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LegacyMigrationError("legacy Markdown must be UTF-8") from exc
    markers = list(_FIELD_MARKER.finditer(source_markdown))
    if not markers or source_markdown.count(b"sw-analysis-field") != len(markers):
        raise LegacyMigrationError("legacy field markers are missing or malformed")
    spans: list[LegacyFieldSpan] = []
    unmarked: list[LegacyUnmarkedSpan] = []
    previous_end = 0
    paths: set[str] = set()
    for marker in markers:
        path = marker.group("path").decode("ascii")
        if path in paths:
            raise LegacyMigrationError(f"duplicate legacy field path: {path}")
        paths.add(path)
        line_start = source_markdown.rfind(b"\n", 0, marker.start()) + 1
        line_end = source_markdown.find(b"\n", marker.end())
        if line_end == -1:
            line_end = len(source_markdown)
            next_start = line_end
        else:
            next_start = line_end + 1
        if source_markdown[line_start : marker.start()].strip(b" \t") or source_markdown[
            marker.end() : line_end
        ].strip(b" \t\r"):
            raise LegacyMigrationError(f"legacy marker must occupy its own line: {path}")
        prefix, content = _split_visible_region(source_markdown[previous_end:line_start])
        if prefix.strip():
            location = f"before:{path}"
            unmarked.append(LegacyUnmarkedSpan(location, prefix, _sha256(prefix)))
        base = marker.group("base").decode("ascii")
        spans.append(
            LegacyFieldSpan(
                path=path,
                content=content,
                sha256=_sha256(content),
                base_sha256=base,
                baseline_matches=_legacy_visible_hash(content) == base,
            )
        )
        previous_end = next_start
    tail = source_markdown[previous_end:]
    if tail.strip():
        unmarked.append(LegacyUnmarkedSpan("tail", tail, _sha256(tail)))
    return LegacyAnalysisInventory(tuple(spans), tuple(unmarked))


def parse_legacy_fields(source_markdown: bytes) -> tuple[LegacyFieldSpan, ...]:
    """Return historical visible fields; use parse_legacy_analysis for unmarked text."""
    return parse_legacy_analysis(source_markdown).fields


def validate_legacy_migration(
    source_markdown: bytes,
    candidate: AnalysisDocument,
    candidate_markdown: str,
    plan: LegacyMigrationPlan,
    *,
    approved_review_digest: str | None = None,
) -> LegacyMigrationReport:
    """Require exact source coverage and explicit adjudication before a legacy cutover.

    ``approved_review_digest`` must come from an external human review of the
    proposed content and mapping. Passing a digest does not prove paper facts;
    it only prevents a reviewed proposal from being silently changed later.
    """
    inventory = parse_legacy_analysis(source_markdown)
    source = inventory.fields
    findings: list[LegacyMigrationFinding] = []

    def fail(code: str, path: str, message: str) -> None:
        findings.append(LegacyMigrationFinding(code, path, message))

    candidate_bytes = candidate_markdown.encode("utf-8")
    digest_payload = {
        "source_sha256": _sha256(source_markdown),
        "candidate_ir": candidate.model_dump(mode="json"),
        "candidate_markdown_sha256": _sha256(candidate_bytes),
        "plan": asdict(plan),
    }
    plan_digest = _sha256(
        json.dumps(
            digest_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    )
    if plan.source_sha256 != _sha256(source_markdown):
        fail("source-changed", "source", "The legacy Markdown differs from the plan baseline.")
    if plan.expected_field_count != len(source):
        fail("field-count-mismatch", "source", "Legacy field count differs from the plan.")
    if "sw-analysis-field" in candidate_markdown:
        fail("legacy-marker-retained", "candidate", "Candidate Markdown retains old field markers.")

    spans = {row.path: row for row in source}
    mapping_paths = [row.path for row in plan.mappings]
    if len(mapping_paths) != len(set(mapping_paths)):
        fail("duplicate-path-mapping", "plan", "Each legacy path must be mapped once.")
    for path in sorted(set(spans) - set(mapping_paths)):
        fail("missing-path-mapping", path, "Legacy field has no migration mapping.")
    for path in sorted(set(mapping_paths) - set(spans)):
        fail("unknown-path-mapping", path, "Mapping refers to no legacy field.")
    unmarked_spans = {row.location: row for row in inventory.unmarked}
    unmarked_locations = [row.location for row in plan.unmarked]
    if len(unmarked_locations) != len(set(unmarked_locations)):
        fail("duplicate-unmarked-decision", "plan", "Each unmarked span needs one decision.")
    for location in sorted(set(unmarked_spans) - set(unmarked_locations)):
        fail("missing-unmarked-decision", location, "Unmarked source text must be adjudicated.")
    for location in sorted(set(unmarked_locations) - set(unmarked_spans)):
        fail("unknown-unmarked-decision", location, "Decision refers to no unmarked source text.")
    claim_by_id = {claim.claim_id: claim for claim in candidate.claims}
    copy_counts: Counter[tuple[LegacyTarget, bytes]] = Counter()
    all_copy_counts: Counter[bytes] = Counter()
    review_required = False

    for decision in plan.unmarked:
        span = unmarked_spans.get(decision.location)
        if span is None:
            continue
        if not _SHA256.fullmatch(decision.source_sha256) or decision.source_sha256 != span.sha256:
            fail("unmarked-changed", decision.location, "Unmarked text differs from its baseline.")
        if decision.disposition == "pending":
            fail("pending-unmarked-decision", decision.location, "Unmarked text needs a decision.")
        elif decision.disposition in {"rewrite", "retire"}:
            review_required = True
        elif decision.disposition == "copy":
            if candidate_bytes.count(span.content) != 1:
                fail(
                    "unmarked-copy-mismatch",
                    decision.location,
                    "Unmarked text is not copied exactly once.",
                )
        else:
            fail("invalid-unmarked-disposition", decision.location, "Unknown unmarked disposition.")

    for mapping in plan.mappings:
        span = spans.get(mapping.path)
        if span is None:
            continue
        if not _SHA256.fullmatch(mapping.source_sha256) or mapping.source_sha256 != span.sha256:
            fail("field-changed", mapping.path, "Field content differs from its mapping baseline.")
        if not span.baseline_matches:
            if any(fragment.disposition == "copy" for fragment in mapping.fragments):
                fail(
                    "human-edited-field-copy",
                    mapping.path,
                    "The historical field baseline changed; automatic copy is not authorized.",
                )
            review_required = True
        cursor = 0
        actual_targets: list[LegacyTarget] = []
        for index, fragment in enumerate(mapping.fragments):
            path = f"{mapping.path}/fragments/{index}"
            if (
                not isinstance(fragment.start, int)
                or not isinstance(fragment.end, int)
                or fragment.start != cursor
                or fragment.end <= fragment.start
                or fragment.end > len(span.content)
            ):
                fail(
                    "fragment-coverage", path, "Fragments must partition field bytes exactly once."
                )
                continue
            content = span.content[fragment.start : fragment.end]
            cursor = fragment.end
            if not _SHA256.fullmatch(fragment.sha256) or fragment.sha256 != _sha256(content):
                fail("fragment-changed", path, "Fragment byte hash differs from the source.")
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError:
                fail("split-codepoint", path, "Fragment cuts through a UTF-8 character.")
                decoded = None
            target = fragment.target
            target_text: str | None = None
            if target is not None:
                if target not in actual_targets:
                    actual_targets.append(target)
                claim = claim_by_id.get(target.claim_id)
                if claim is None:
                    fail(
                        "unknown-target", path, "Destination claim is absent from the analysis IR."
                    )
                elif target.point_id is None:
                    target_text = claim.body
                else:
                    point: AnalysisPoint | None = next(
                        (row for row in claim.points if row.point_id == target.point_id), None
                    )
                    if point is None:
                        fail(
                            "unknown-target",
                            path,
                            "Destination point is absent from the analysis IR.",
                        )
                    else:
                        target_text = point.text
            if fragment.disposition in {"copy", "rewrite"} and target is None:
                fail(
                    "missing-target",
                    path,
                    "Preserved or rewritten content needs a claim/point target.",
                )
            if fragment.disposition == "retire" and target is not None:
                fail("retired-target", path, "Retired content must not claim a destination.")
            if mapping.path.endswith("/evidence") and (
                fragment.disposition != "rewrite" or target is None
            ):
                fail(
                    "evidence-unmapped",
                    path,
                    "Detached Evidence needs reviewed inline claim/point attribution.",
                )
            if fragment.disposition == "pending":
                fail("pending-decision", path, "Unadjudicated legacy content cannot pass.")
            elif fragment.disposition in {"rewrite", "retire"}:
                review_required = True
            elif fragment.disposition == "copy" and target_text is not None and decoded is not None:
                if decoded not in target_text:
                    fail(
                        "copy-not-in-target", path, "Exact original text is absent from its target."
                    )
                copy_counts[(target, content)] += 1
                all_copy_counts[content] += 1
            elif fragment.disposition not in {"copy", "rewrite", "retire", "pending"}:
                fail("invalid-disposition", path, "Unknown fragment disposition.")
        if cursor != len(span.content) or not mapping.fragments:
            fail(
                "fragment-coverage",
                mapping.path,
                "Fragments must cover every pre-marker byte once.",
            )
        declared_targets = plan.split_targets.get(mapping.path)
        if len(actual_targets) > 1:
            if declared_targets != tuple(actual_targets):
                fail(
                    "split-target-mismatch",
                    mapping.path,
                    "All split destinations must be declared in order.",
                )
        elif declared_targets is not None:
            fail("unexpected-split", mapping.path, "A non-split field declares split targets.")

    for path in sorted(set(plan.split_targets) - set(mapping_paths)):
        fail("unknown-split", path, "Split declaration refers to no mapped field.")
    for (target, content), expected in copy_counts.items():
        claim = claim_by_id[target.claim_id]
        target_text = (
            claim.body
            if target.point_id is None
            else next(row.text for row in claim.points if row.point_id == target.point_id)
        )
        if target_text.encode("utf-8").count(content) != expected:
            fail(
                "copy-count-in-target",
                target.claim_id,
                "Exact text is not preserved once per mapped fragment.",
            )
    for content, expected in all_copy_counts.items():
        if candidate_bytes.count(content) != expected:
            fail(
                "copy-count-in-markdown",
                "candidate",
                "Exact original text is not preserved once per mapped fragment.",
            )
    if review_required and approved_review_digest != plan_digest:
        fail(
            "human-review-required",
            "plan",
            "Rewrites and retirements need approval of this exact plan digest.",
        )
    return LegacyMigrationReport(
        ok=not findings,
        plan_digest=plan_digest,
        findings=tuple(findings),
        review_required=review_required,
    )


__all__ = [
    "LegacyAnalysisInventory",
    "LegacyFieldMapping",
    "LegacyFieldSpan",
    "LegacyFragment",
    "LegacyMigrationError",
    "LegacyMigrationFinding",
    "LegacyMigrationPlan",
    "LegacyMigrationReport",
    "LegacyTarget",
    "LegacyUnmarkedDecision",
    "LegacyUnmarkedSpan",
    "parse_legacy_analysis",
    "parse_legacy_fields",
    "validate_legacy_migration",
]
