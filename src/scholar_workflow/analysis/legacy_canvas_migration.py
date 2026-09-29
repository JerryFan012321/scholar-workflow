"""Read-only conservation gate for a legacy analysis JSON Canvas.

This inventories old elements, not paper meaning. A reviewed rewrite or retirement
still needs external human approval, and the new analysis bundle must independently
pass its normal conformance gate before any caller may commit it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from scholar_workflow.canvas import validate_canvas_payload

CanvasElementKind = Literal["node", "edge"]
CanvasDisposition = Literal["preserve", "reviewed_rewrite", "retire", "pending"]
_FIELD_MARKER = re.compile(
    r'<!-- sw-analysis-field path="(?P<path>[a-z0-9][a-z0-9/-]*)" '
    r'base_sha256="[0-9a-f]{64}" -->'
)


class LegacyCanvasMigrationError(ValueError):
    """A Canvas cannot be inventoried safely."""


@dataclass(frozen=True)
class LegacyCanvasElement:
    kind: CanvasElementKind
    element_id: str
    payload_sha256: str
    ownership: Literal["generated", "custom"]


@dataclass(frozen=True)
class LegacyCanvasElementMapping:
    kind: CanvasElementKind
    source_id: str
    source_payload_sha256: str
    disposition: CanvasDisposition
    target_id: str | None = None
    target_payload_sha256: str | None = None


@dataclass(frozen=True)
class LegacyCanvasMigrationPlan:
    source_sha256: str
    candidate_sha256: str
    mappings: tuple[LegacyCanvasElementMapping, ...]


@dataclass(frozen=True)
class LegacyCanvasMigrationFinding:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class LegacyCanvasMigrationReport:
    ok: bool
    plan_digest: str
    findings: tuple[LegacyCanvasMigrationFinding, ...]
    review_required: bool


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _payload_sha256(value: dict[str, object]) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    return _sha256(canonical)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LegacyCanvasMigrationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise LegacyCanvasMigrationError(f"non-finite JSON value: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise LegacyCanvasMigrationError("non-finite JSON number")
    return number


def _parse_canvas(raw: bytes) -> dict[str, list[dict[str, object]]]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        canvas = validate_canvas_payload(value)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise LegacyCanvasMigrationError(f"invalid JSON Canvas: {exc}") from exc
    node_ids = {node["id"] for node in canvas["nodes"]}
    edge_ids = {edge["id"] for edge in canvas["edges"]}
    if node_ids & edge_ids:
        raise LegacyCanvasMigrationError("Canvas node and edge IDs must not collide")
    return canvas


def _generated_paths(canvas: dict[str, list[dict[str, object]]]) -> dict[str, str]:
    paths: dict[str, str] = {}
    seen_paths: set[str] = set()
    for node in canvas["nodes"]:
        text = node.get("text")
        if node.get("type") != "text" or not isinstance(text, str):
            continue
        lines = text.rstrip("\r\n").splitlines()
        if not lines:
            continue
        marker = _FIELD_MARKER.fullmatch(lines[-1])
        if marker is not None:
            path = marker.group("path")
            if path in seen_paths:
                raise LegacyCanvasMigrationError(f"duplicate generated Canvas path: {path}")
            seen_paths.add(path)
            paths[str(node["id"])] = path
    return paths


def _inventory(canvas: dict[str, list[dict[str, object]]]) -> tuple[LegacyCanvasElement, ...]:
    generated_paths = _generated_paths(canvas)
    rows: list[LegacyCanvasElement] = []
    for node in canvas["nodes"]:
        node_id = str(node["id"])
        rows.append(
            LegacyCanvasElement(
                "node",
                node_id,
                _payload_sha256(node),
                "generated" if node_id in generated_paths else "custom",
            )
        )
    for edge in canvas["edges"]:
        edge_id = str(edge["id"])
        from_path = generated_paths.get(str(edge["fromNode"]))
        to_path = generated_paths.get(str(edge["toNode"]))
        expected = (
            _sha256(f"edge\n{from_path}\n{to_path}".encode())[:16]
            if from_path is not None and to_path is not None
            else None
        )
        rows.append(
            LegacyCanvasElement(
                "edge",
                edge_id,
                _payload_sha256(edge),
                "generated" if edge_id == expected else "custom",
            )
        )
    return tuple(rows)


def inventory_legacy_canvas(raw: bytes) -> tuple[LegacyCanvasElement, ...]:
    """Return each old node and edge with its complete canonical payload hash."""
    return _inventory(_parse_canvas(raw))


def validate_legacy_canvas_migration(
    source_canvas: bytes,
    candidate_canvas: bytes,
    plan: LegacyCanvasMigrationPlan,
    *,
    approved_review_digest: str | None = None,
) -> LegacyCanvasMigrationReport:
    """Check byte baselines, exact old-element coverage, and explicit disposition.

    A matching ``approved_review_digest`` is only a proposal integrity check. The
    applying layer must obtain it from a trusted human-review record and separately
    check the candidate bundle, Markdown conservation, and transaction CAS.
    """
    source_rows = _inventory(_parse_canvas(source_canvas))
    candidate_rows = _inventory(_parse_canvas(candidate_canvas))
    source = {(row.kind, row.element_id): row for row in source_rows}
    candidate = {(row.kind, row.element_id): row for row in candidate_rows}
    candidate_ids = {row.element_id for row in candidate_rows}
    findings: list[LegacyCanvasMigrationFinding] = []

    def fail(code: str, path: str, message: str) -> None:
        findings.append(LegacyCanvasMigrationFinding(code, path, message))

    digest_payload = {
        "source_sha256": _sha256(source_canvas),
        "candidate_sha256": _sha256(candidate_canvas),
        "plan": asdict(plan),
    }
    plan_digest = _sha256(
        json.dumps(
            digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    )
    if plan.source_sha256 != _sha256(source_canvas):
        fail("source-changed", "source", "Legacy Canvas bytes differ from the plan baseline.")
    if plan.candidate_sha256 != _sha256(candidate_canvas):
        fail("candidate-changed", "candidate", "Candidate Canvas bytes differ from the plan.")

    mappings: dict[tuple[str, str], LegacyCanvasElementMapping] = {}
    for row in plan.mappings:
        key = (row.kind, row.source_id)
        if key in mappings:
            fail("duplicate-mapping", f"{row.kind}/{row.source_id}", "Old element is mapped twice.")
        else:
            mappings[key] = row
        if key not in source:
            fail("unknown-source", f"{row.kind}/{row.source_id}", "Mapping has no old element.")
    for kind, element_id in sorted(set(source) - set(mappings)):
        fail("missing-mapping", f"{kind}/{element_id}", "Old element has no disposition.")

    review_required = False
    for key, row in mappings.items():
        old = source.get(key)
        if old is None:
            continue
        path = f"{old.kind}/{old.element_id}"
        if row.source_payload_sha256 != old.payload_sha256:
            fail("source-payload-changed", path, "Old payload differs from its mapping baseline.")
        if row.disposition == "preserve":
            if row.target_id not in (None, row.source_id) or row.target_payload_sha256 not in (
                None,
                old.payload_sha256,
            ):
                fail(
                    "invalid-preserve-target", path, "Preserve must retain the same ID and payload."
                )
            retained = candidate.get(key)
            if retained is None or retained.payload_sha256 != old.payload_sha256:
                fail("not-preserved", path, "Old element is missing or its full payload changed.")
        elif row.disposition == "reviewed_rewrite":
            review_required = True
            if row.target_id is None or row.target_payload_sha256 is None:
                fail(
                    "missing-rewrite-target",
                    path,
                    "Rewrite needs an exact candidate ID and payload hash.",
                )
                continue
            target = candidate.get((row.kind, row.target_id))
            if target is None or target.payload_sha256 != row.target_payload_sha256:
                fail(
                    "rewrite-target-changed", path, "Declared rewrite target is absent or differs."
                )
            if row.target_id != row.source_id and row.source_id in candidate_ids:
                fail("old-id-retained", path, "Rewritten old ID is still present in the candidate.")
        elif row.disposition == "retire":
            review_required = True
            if row.target_id is not None or row.target_payload_sha256 is not None:
                fail("retired-target", path, "Retirement cannot declare a candidate target.")
            if row.source_id in candidate_ids:
                fail("not-retired", path, "Retired old ID remains in the candidate.")
        elif row.disposition == "pending":
            fail("pending-decision", path, "Unadjudicated old Canvas element cannot pass.")
        else:
            fail("invalid-disposition", path, "Unknown Canvas element disposition.")
    if review_required and approved_review_digest != plan_digest:
        fail(
            "human-review-required",
            "plan",
            "Rewrites and retirements need this exact review digest.",
        )
    return LegacyCanvasMigrationReport(
        ok=not findings,
        plan_digest=plan_digest,
        findings=tuple(findings),
        review_required=review_required,
    )


__all__ = [
    "LegacyCanvasElement",
    "LegacyCanvasElementMapping",
    "LegacyCanvasMigrationError",
    "LegacyCanvasMigrationFinding",
    "LegacyCanvasMigrationPlan",
    "LegacyCanvasMigrationReport",
    "inventory_legacy_canvas",
    "validate_legacy_canvas_migration",
]
