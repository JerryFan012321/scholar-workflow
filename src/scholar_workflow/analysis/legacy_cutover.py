"""Pure, fixture-safe composition of the three mechanical JEPA cutover gates.

This module never writes artifacts. A matching digest proves proposal integrity,
not the origin of human approval or the truth of claims about a paper. The caller
must authenticate the external approval and use a separate CAS transaction.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from types import MappingProxyType

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.legacy_canvas_migration import (
    LegacyCanvasElementMapping,
    LegacyCanvasMigrationError,
    LegacyCanvasMigrationPlan,
    validate_legacy_canvas_migration,
)
from scholar_workflow.analysis.legacy_migration import (
    LegacyFieldMapping,
    LegacyFragment,
    LegacyMigrationError,
    LegacyMigrationPlan,
    LegacyTarget,
    LegacyUnmarkedDecision,
    validate_legacy_migration,
)
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import AnalysisUpdateError, create_baseline
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload


@dataclass(frozen=True)
class LegacyCutoverArtifacts:
    """Only populated when every mechanical gate and the composite approval pass."""

    markdown: bytes
    canvas: bytes
    sidecar: bytes


@dataclass(frozen=True)
class LegacyCutoverFinding:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class LegacyCutoverReport:
    ok: bool
    cutover_digest: str | None
    findings: tuple[LegacyCutoverFinding, ...]
    artifacts: LegacyCutoverArtifacts | None


class LegacyFieldPayloadError(ValueError):
    """The legacy cutover cannot be passed to a Field transaction."""

    def __init__(self, message: str, *, report: LegacyCutoverReport | None = None) -> None:
        super().__init__(message)
        self.report = report


class LegacyFieldProposalError(ValueError):
    """An operator-supplied candidate JSON package violates the strict schema."""


@dataclass(frozen=True, slots=True)
class LegacyFieldProposal:
    """Typed, untrusted candidate; source files must be read by the server."""

    markdown_path: str
    canvas_path: str
    sidecar_path: str
    note_stem: str
    document: AnalysisDocument
    bundle: AnalysisBundle
    markdown_plan: LegacyMigrationPlan
    canvas_plan: LegacyCanvasMigrationPlan


@dataclass(frozen=True, slots=True)
class PreparedLegacyFieldPayload:
    """Immutable, reviewed bytes for one analysis pair inside a Field.

    This is a mechanical validation result, not proof that the caller obtained
    an authentic human approval. The Field transaction must independently check
    source bytes/absence and bind this payload to its complete plan digest.
    All paths are relative to the selected Field root, never to the Vault root.
    """

    markdown_path: str
    canvas_path: str
    sidecar_path: str
    source_markdown_sha256: str
    source_canvas_sha256: str
    source_sidecar_sha256: str | None
    markdown: bytes
    canvas: bytes
    sidecar: bytes
    cutover_digest: str
    payload_digest: str

    @property
    def files(self) -> Mapping[str, bytes]:
        """Return a read-only map of Field-root-relative candidate file bytes."""
        return MappingProxyType(
            {
                self.markdown_path: self.markdown,
                self.canvas_path: self.canvas,
                self.sidecar_path: self.sidecar,
            }
        )

    @property
    def sources(self) -> Mapping[str, str | None]:
        """Return exact old-file hashes; None requires the sidecar to be absent."""
        return MappingProxyType(
            {
                self.markdown_path: self.source_markdown_sha256,
                self.canvas_path: self.source_canvas_sha256,
                self.sidecar_path: self.source_sidecar_sha256,
            }
        )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


_MAX_PROPOSAL_BYTES = 8 * 1024 * 1024
_MAX_PROPOSAL_FILE_BYTES = 2 * 1024 * 1024
_MAX_PROPOSAL_ITEMS = 4096
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LEGACY_PATH = re.compile(r"[a-z0-9][a-z0-9/-]{0,239}\Z")
_CLAIM_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise LegacyFieldProposalError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise LegacyFieldProposalError(f"non-finite JSON value: {value}")


def _finite_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise LegacyFieldProposalError("non-finite JSON number")
    return number


def _require_json_tree(value: object, *, depth: int = 0) -> None:
    if depth > 64:
        raise LegacyFieldProposalError("proposal JSON is too deeply nested")
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise LegacyFieldProposalError("proposal contains invalid UTF-8 text") from exc
        return
    if value is None or type(value) in {int, bool}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise LegacyFieldProposalError("non-finite JSON number")
        return
    if type(value) is list:
        for item in value:
            _require_json_tree(item, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise LegacyFieldProposalError("proposal JSON keys must be strings")
            _require_json_tree(item, depth=depth + 1)
        return
    raise LegacyFieldProposalError("proposal contains a non-JSON value")


def _proposal_json(value: bytes | Mapping[str, object]) -> object:
    if isinstance(value, bytes):
        if len(value) > _MAX_PROPOSAL_BYTES:
            raise LegacyFieldProposalError("proposal JSON is too large")
        raw = value
    elif isinstance(value, Mapping):
        _require_json_tree(value)
        try:
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (UnicodeEncodeError, ValueError, OverflowError, RecursionError) as exc:
            raise LegacyFieldProposalError("proposal contains invalid JSON data") from exc
        if len(raw) > _MAX_PROPOSAL_BYTES:
            raise LegacyFieldProposalError("proposal JSON is too large")
    else:
        raise LegacyFieldProposalError("proposal must be a JSON object or UTF-8 bytes")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
        _require_json_tree(parsed)
        return parsed
    except LegacyFieldProposalError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise LegacyFieldProposalError("proposal is not valid UTF-8 JSON") from exc


def _object(
    value: object,
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, object]:
    if type(value) is not dict:
        raise LegacyFieldProposalError(f"{path} must be an object")
    optional = optional or set()
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        raise LegacyFieldProposalError(f"{path} has missing or unknown keys: {sorted(missing | extra)}")
    return value


def _array(value: object, path: str) -> list[object]:
    if type(value) is not list or len(value) > _MAX_PROPOSAL_ITEMS:
        raise LegacyFieldProposalError(f"{path} must be a bounded JSON array")
    return value


def _text(value: object, path: str, *, limit: int = 1024) -> str:
    try:
        encoded_length = len(value.encode("utf-8")) if type(value) is str else None
    except UnicodeEncodeError as exc:
        raise LegacyFieldProposalError(f"{path} is not valid UTF-8 text") from exc
    if type(value) is not str or not value or encoded_length is None or encoded_length > limit:
        raise LegacyFieldProposalError(f"{path} must be bounded nonempty text")
    return value


def _hash_text(value: object, path: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise LegacyFieldProposalError(f"{path} must be a sha256 hex digest")
    return value


def _legacy_path(value: object, path: str) -> str:
    text = _text(value, path, limit=240)
    if _LEGACY_PATH.fullmatch(text) is None:
        raise LegacyFieldProposalError(f"{path} is not a legacy field path")
    return text


def _disposition(value: object, path: str, allowed: set[str]) -> str:
    if type(value) is not str or value not in allowed:
        raise LegacyFieldProposalError(f"{path} has an invalid disposition")
    return value


def _target(value: object, path: str) -> LegacyTarget:
    row = _object(value, path, required={"claim_id"}, optional={"point_id"})
    claim_id = _text(row["claim_id"], f"{path}/claim_id", limit=64)
    if _CLAIM_ID.fullmatch(claim_id) is None:
        raise LegacyFieldProposalError(f"{path}/claim_id is invalid")
    point_id = row.get("point_id")
    if point_id is not None:
        point_id = _text(point_id, f"{path}/point_id", limit=64)
        if _CLAIM_ID.fullmatch(point_id) is None:
            raise LegacyFieldProposalError(f"{path}/point_id is invalid")
    return LegacyTarget(claim_id, point_id)


def _markdown_plan(value: object) -> LegacyMigrationPlan:
    row = _object(
        value,
        "markdown_plan",
        required={"source_sha256", "expected_field_count", "mappings", "split_targets"},
        optional={"unmarked"},
    )
    count = row["expected_field_count"]
    if type(count) is not int or not 0 <= count <= _MAX_PROPOSAL_ITEMS:
        raise LegacyFieldProposalError("markdown_plan/expected_field_count is invalid")
    mappings: list[LegacyFieldMapping] = []
    for index, item in enumerate(_array(row["mappings"], "markdown_plan/mappings")):
        path = f"markdown_plan/mappings/{index}"
        mapping = _object(item, path, required={"path", "source_sha256", "fragments"})
        fragments: list[LegacyFragment] = []
        for frag_index, frag in enumerate(_array(mapping["fragments"], f"{path}/fragments")):
            frag_path = f"{path}/fragments/{frag_index}"
            part = _object(
                frag,
                frag_path,
                required={"start", "end", "sha256", "disposition"},
                optional={"target"},
            )
            start, end = part["start"], part["end"]
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= _MAX_PROPOSAL_FILE_BYTES
            ):
                raise LegacyFieldProposalError(f"{frag_path} has invalid byte offsets")
            target = part.get("target")
            fragments.append(
                LegacyFragment(
                    start,
                    end,
                    _hash_text(part["sha256"], f"{frag_path}/sha256"),
                    _disposition(
                        part["disposition"],
                        f"{frag_path}/disposition",
                        {"copy", "rewrite", "retire", "pending"},
                    ),
                    None if target is None else _target(target, f"{frag_path}/target"),
                )
            )
        mappings.append(
            LegacyFieldMapping(
                _legacy_path(mapping["path"], f"{path}/path"),
                _hash_text(mapping["source_sha256"], f"{path}/source_sha256"),
                tuple(fragments),
            )
        )
    split_raw = row["split_targets"]
    if type(split_raw) is not dict or len(split_raw) > _MAX_PROPOSAL_ITEMS:
        raise LegacyFieldProposalError("markdown_plan/split_targets must be a bounded object")
    split_targets: dict[str, tuple[LegacyTarget, ...]] = {}
    for key, targets in split_raw.items():
        path = _legacy_path(key, "markdown_plan/split_targets/key")
        split_targets[path] = tuple(
            _target(item, f"markdown_plan/split_targets/{path}/{index}")
            for index, item in enumerate(_array(targets, f"markdown_plan/split_targets/{path}"))
        )
    unmarked: list[LegacyUnmarkedDecision] = []
    for index, item in enumerate(_array(row.get("unmarked", []), "markdown_plan/unmarked")):
        path = f"markdown_plan/unmarked/{index}"
        decision = _object(
            item,
            path,
            required={"location", "source_sha256", "disposition"},
        )
        unmarked.append(
            LegacyUnmarkedDecision(
                _text(decision["location"], f"{path}/location"),
                _hash_text(decision["source_sha256"], f"{path}/source_sha256"),
                _disposition(
                    decision["disposition"],
                    f"{path}/disposition",
                    {"copy", "rewrite", "retire", "pending"},
                ),
            )
        )
    return LegacyMigrationPlan(
        _hash_text(row["source_sha256"], "markdown_plan/source_sha256"),
        count,
        tuple(mappings),
        split_targets,
        tuple(unmarked),
    )


def _canvas_plan(value: object) -> LegacyCanvasMigrationPlan:
    row = _object(
        value,
        "canvas_plan",
        required={"source_sha256", "candidate_sha256", "mappings"},
    )
    mappings: list[LegacyCanvasElementMapping] = []
    for index, item in enumerate(_array(row["mappings"], "canvas_plan/mappings")):
        path = f"canvas_plan/mappings/{index}"
        mapping = _object(
            item,
            path,
            required={"kind", "source_id", "source_payload_sha256", "disposition"},
            optional={"target_id", "target_payload_sha256"},
        )
        kind = mapping["kind"]
        if type(kind) is not str or kind not in {"node", "edge"}:
            raise LegacyFieldProposalError(f"{path}/kind is invalid")
        target_id = mapping.get("target_id")
        if target_id is not None:
            target_id = _text(target_id, f"{path}/target_id", limit=256)
        target_hash = mapping.get("target_payload_sha256")
        if target_hash is not None:
            target_hash = _hash_text(target_hash, f"{path}/target_payload_sha256")
        mappings.append(
            LegacyCanvasElementMapping(
                kind,
                _text(mapping["source_id"], f"{path}/source_id", limit=256),
                _hash_text(mapping["source_payload_sha256"], f"{path}/source_payload_sha256"),
                _disposition(
                    mapping["disposition"],
                    f"{path}/disposition",
                    {"preserve", "reviewed_rewrite", "retire", "pending"},
                ),
                target_id,
                target_hash,
            )
        )
    return LegacyCanvasMigrationPlan(
        _hash_text(row["source_sha256"], "canvas_plan/source_sha256"),
        _hash_text(row["candidate_sha256"], "canvas_plan/candidate_sha256"),
        tuple(mappings),
    )


def parse_legacy_field_proposal(value: bytes | Mapping[str, object]) -> LegacyFieldProposal:
    """Parse bounded operator JSON without trusting old files or absolute paths.

    Pass raw request bytes where possible so duplicate JSON keys are detectable.
    This only checks the package shape; source conservation and conformance run
    later against server-read old files via ``prepare_legacy_field_payload``.
    """
    row = _object(
        _proposal_json(value),
        "proposal",
        required={
            "schema_version",
            "markdown_path",
            "canvas_path",
            "sidecar_path",
            "document",
            "bundle",
            "markdown_plan",
            "canvas_plan",
        },
    )
    if type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise LegacyFieldProposalError("proposal schema_version must be 1")
    markdown_path = _text(row["markdown_path"], "proposal/markdown_path")
    canvas_path = _text(row["canvas_path"], "proposal/canvas_path")
    sidecar_path = _text(row["sidecar_path"], "proposal/sidecar_path")
    note_stem = PurePosixPath(markdown_path).stem
    try:
        _validate_field_paths(markdown_path, canvas_path, sidecar_path, note_stem)
    except LegacyFieldPayloadError as exc:
        raise LegacyFieldProposalError(str(exc)) from exc
    try:
        document = AnalysisDocument.model_validate(row["document"])
    except ValueError as exc:
        raise LegacyFieldProposalError("proposal document is not a valid Analysis IR") from exc
    pair = _object(row["bundle"], "bundle", required={"markdown", "canvas"})
    markdown = _text(pair["markdown"], "bundle/markdown", limit=_MAX_PROPOSAL_FILE_BYTES)
    try:
        canvas = validate_canvas_payload(pair["canvas"])
    except CanvasValidationError as exc:
        raise LegacyFieldProposalError("bundle/canvas is not valid JSON Canvas") from exc
    if len(_json_bytes(canvas)) > _MAX_PROPOSAL_FILE_BYTES:
        raise LegacyFieldProposalError("bundle/canvas is too large")
    return LegacyFieldProposal(
        markdown_path,
        canvas_path,
        sidecar_path,
        note_stem,
        document,
        AnalysisBundle(markdown, deepcopy(canvas)),
        _markdown_plan(row["markdown_plan"]),
        _canvas_plan(row["canvas_plan"]),
    )


def _failed(
    *findings: LegacyCutoverFinding,
    cutover_digest: str | None = None,
) -> LegacyCutoverReport:
    return LegacyCutoverReport(False, cutover_digest, tuple(findings), None)


def _safe_field_path(value: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise LegacyFieldPayloadError("Field payload path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts)
    ):
        raise LegacyFieldPayloadError("Field payload path must be a canonical visible relative path")
    return path


def _validate_field_paths(
    markdown_path: str,
    canvas_path: str,
    sidecar_path: str,
    note_stem: str,
) -> None:
    markdown = _safe_field_path(markdown_path)
    canvas = _safe_field_path(canvas_path)
    sidecar = _safe_field_path(sidecar_path)
    matching_canvas = markdown.with_suffix(".canvas")
    legacy_canvas = None
    if isinstance(note_stem, str) and note_stem.endswith("分析") and len(note_stem) > len("分析"):
        legacy_canvas = markdown.with_name(f"{note_stem.removesuffix('分析')}解析树.canvas")
    if (
        not isinstance(note_stem, str)
        or not note_stem
        or "/" in note_stem
        or "\\" in note_stem
        or note_stem.startswith(".")
        or any(ord(char) < 32 for char in note_stem)
        or markdown.name != f"{note_stem}.md"
        or canvas not in {matching_canvas, legacy_canvas}
        or sidecar != markdown.with_suffix(".analysis.json")
    ):
        raise LegacyFieldPayloadError(
            "Field payload paths must use one approved Markdown/Canvas name pair "
            "and a Markdown-stem sidecar"
        )


def prepare_legacy_field_payload(
    *,
    markdown_path: str,
    canvas_path: str,
    sidecar_path: str,
    source_markdown: bytes,
    source_canvas: bytes,
    source_sidecar: bytes | None,
    document: AnalysisDocument,
    bundle: AnalysisBundle,
    markdown_plan: LegacyMigrationPlan,
    canvas_plan: LegacyCanvasMigrationPlan,
    note_stem: str,
    approved_cutover_digest: str | None,
) -> PreparedLegacyFieldPayload:
    """Validate and bind one old analysis pair to three Field-root-relative paths.

    A caller first uses ``validate_legacy_cutover`` without approval to show
    the complete proposal and digest. It must authenticate the later approval
    before supplying that digest here. No disk read or write happens here.
    """
    _validate_field_paths(markdown_path, canvas_path, sidecar_path, note_stem)
    if not isinstance(source_markdown, bytes) or not isinstance(source_canvas, bytes):
        raise LegacyFieldPayloadError("legacy Markdown and Canvas sources must be bytes")
    if source_sidecar is not None and not isinstance(source_sidecar, bytes):
        raise LegacyFieldPayloadError("legacy sidecar source must be bytes or absent")
    report = validate_legacy_cutover(
        source_markdown,
        source_canvas,
        document,
        bundle,
        markdown_plan,
        canvas_plan,
        note_stem=note_stem,
        approved_digest=approved_cutover_digest,
    )
    if not report.ok or report.artifacts is None or report.cutover_digest is None:
        codes = ", ".join(finding.code for finding in report.findings) or "invalid-cutover"
        raise LegacyFieldPayloadError(f"legacy Field payload rejected: {codes}", report=report)
    source_sidecar_sha256 = None if source_sidecar is None else _sha256(source_sidecar)
    artifacts = report.artifacts
    digest_payload = {
        "kind": "legacy-field-payload",
        "schema_version": 1,
        "cutover_digest": report.cutover_digest,
        "sources": {
            markdown_path: _sha256(source_markdown),
            canvas_path: _sha256(source_canvas),
            sidecar_path: source_sidecar_sha256,
        },
        "targets": {
            markdown_path: _sha256(artifacts.markdown),
            canvas_path: _sha256(artifacts.canvas),
            sidecar_path: _sha256(artifacts.sidecar),
        },
    }
    payload_digest = _sha256(
        json.dumps(
            digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    return PreparedLegacyFieldPayload(
        markdown_path=markdown_path,
        canvas_path=canvas_path,
        sidecar_path=sidecar_path,
        source_markdown_sha256=_sha256(source_markdown),
        source_canvas_sha256=_sha256(source_canvas),
        source_sidecar_sha256=source_sidecar_sha256,
        markdown=artifacts.markdown,
        canvas=artifacts.canvas,
        sidecar=artifacts.sidecar,
        cutover_digest=report.cutover_digest,
        payload_digest=payload_digest,
    )


def validate_legacy_cutover(
    source_markdown: bytes,
    source_canvas: bytes,
    document: AnalysisDocument,
    bundle: AnalysisBundle,
    markdown_plan: LegacyMigrationPlan,
    canvas_plan: LegacyCanvasMigrationPlan,
    *,
    note_stem: str,
    approved_digest: str | None = None,
) -> LegacyCutoverReport:
    """Return stageable bytes only if all old/new mechanical contracts pass.

    The first call with no approval yields a composite ``cutover_digest`` when
    the candidate is otherwise valid. An applying layer must establish that a
    human reviewed that exact digest before passing it back as ``approved_digest``.
    No semantic equivalence or paper fact is inferred here.
    """
    try:
        frozen_document = document.model_copy(deep=True)
        frozen_markdown_plan = deepcopy(markdown_plan)
        frozen_canvas_plan = deepcopy(canvas_plan)
        markdown = bundle.markdown
        markdown_bytes = markdown.encode("utf-8")
        canvas_bytes = _json_bytes(bundle.canvas)
        frozen_bundle = AnalysisBundle(markdown, json.loads(canvas_bytes))
        if b"sw-analysis-field" in canvas_bytes:
            return _failed(
                LegacyCutoverFinding(
                    "legacy-canvas-marker-retained",
                    "candidate/canvas",
                    "Candidate Canvas still contains old field markers.",
                )
            )
        conformance = validate_bundle(frozen_document, frozen_bundle, note_stem=note_stem)
    except (TypeError, ValueError) as exc:
        return _failed(LegacyCutoverFinding("invalid-candidate", "candidate", str(exc)))
    if not conformance.ok:
        return _failed(
            *(
                LegacyCutoverFinding(f"bundle-{finding.code}", finding.path, finding.message)
                for finding in conformance.findings
            )
        )

    try:
        baseline = create_baseline(frozen_document, frozen_bundle, note_stem=note_stem)
        sidecar_bytes = _json_bytes(baseline.model_dump(mode="json"))
    except (AnalysisUpdateError, TypeError, ValueError) as exc:
        return _failed(LegacyCutoverFinding("baseline-invalid", "sidecar", str(exc)))

    try:
        markdown_report = validate_legacy_migration(
            source_markdown, frozen_document, markdown, frozen_markdown_plan
        )
        canvas_report = validate_legacy_canvas_migration(
            source_canvas, canvas_bytes, frozen_canvas_plan
        )
    except (LegacyMigrationError, LegacyCanvasMigrationError, TypeError, ValueError) as exc:
        return _failed(LegacyCutoverFinding("invalid-legacy-input", "source", str(exc)))

    gate_findings = [
        LegacyCutoverFinding(f"markdown-{finding.code}", finding.path, finding.message)
        for finding in markdown_report.findings
        if finding.code != "human-review-required"
    ]
    gate_findings.extend(
        LegacyCutoverFinding(f"canvas-{finding.code}", finding.path, finding.message)
        for finding in canvas_report.findings
        if finding.code != "human-review-required"
    )
    if gate_findings:
        return _failed(*gate_findings)

    digest_payload = {
        "source_markdown_sha256": _sha256(source_markdown),
        "source_canvas_sha256": _sha256(source_canvas),
        "candidate_markdown_sha256": _sha256(markdown_bytes),
        "candidate_canvas_sha256": _sha256(canvas_bytes),
        "candidate_sidecar_sha256": _sha256(sidecar_bytes),
        "markdown_mapping": asdict(frozen_markdown_plan),
        "canvas_mapping": asdict(frozen_canvas_plan),
        "markdown_review_digest": markdown_report.plan_digest,
        "canvas_review_digest": canvas_report.plan_digest,
        "note_stem": note_stem,
    }
    cutover_digest = _sha256(
        json.dumps(
            digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    if approved_digest != cutover_digest:
        code = "approval-required" if approved_digest is None else "approval-digest-mismatch"
        return _failed(
            LegacyCutoverFinding(
                code, "approval", "A trusted review of this exact cutover is required."
            ),
            cutover_digest=cutover_digest,
        )

    # The trusted composite review authorizes both component proposals. Recheck
    # their local approval conditions before exposing any stageable bytes.
    approved_markdown = validate_legacy_migration(
        source_markdown,
        frozen_document,
        markdown,
        frozen_markdown_plan,
        approved_review_digest=markdown_report.plan_digest,
    )
    approved_canvas = validate_legacy_canvas_migration(
        source_canvas,
        canvas_bytes,
        frozen_canvas_plan,
        approved_review_digest=canvas_report.plan_digest,
    )
    if not approved_markdown.ok or not approved_canvas.ok:
        return _failed(
            LegacyCutoverFinding(
                "approval-recheck-failed",
                "approval",
                "A legacy conservation gate changed during approval recheck.",
            ),
            cutover_digest=cutover_digest,
        )
    return LegacyCutoverReport(
        True,
        cutover_digest,
        (),
        LegacyCutoverArtifacts(markdown_bytes, canvas_bytes, sidecar_bytes),
    )


__all__ = [
    "LegacyCutoverArtifacts",
    "LegacyCutoverFinding",
    "LegacyCutoverReport",
    "LegacyFieldPayloadError",
    "LegacyFieldProposal",
    "LegacyFieldProposalError",
    "PreparedLegacyFieldPayload",
    "parse_legacy_field_proposal",
    "prepare_legacy_field_payload",
    "validate_legacy_cutover",
]
