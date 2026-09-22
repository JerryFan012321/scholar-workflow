"""Fail-closed planning for baseline-bound whole and focused analysis updates."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    ALL_ROLES,
    AnalysisBaseline,
    AnalysisBaselineClaim,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    ProfileKind,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    claim_canvas_text,
    claim_markdown_lines,
    render_analysis,
)


class AnalysisUpdateError(ValueError):
    """The requested update violates identity or projection contracts."""


@dataclass(frozen=True)
class AnalysisUpdatePlan:
    """A zero-write result; conflicts retain the current pair and expose a proposal."""

    status: str
    document: AnalysisDocument
    current: AnalysisBundle
    proposed: AnalysisBundle
    baseline: AnalysisBaseline | None
    conflicts: tuple[str, ...]


def _text_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _managed_canvas_hash(
    canvas: dict[str, list[dict[str, object]]],
    *,
    node_ids: list[str],
    edge_ids: list[str],
) -> str:
    """Hash renderer-owned content without claiming user layout or custom graph items."""

    nodes = canvas.get("nodes") if isinstance(canvas, dict) else None
    edges = canvas.get("edges") if isinstance(canvas, dict) else None
    node_items = nodes if isinstance(nodes, list) else []
    edge_items = edges if isinstance(edges, list) else []

    managed_nodes: list[dict[str, object]] = []
    for node_id in node_ids:
        matches = [
            node
            for node in node_items
            if isinstance(node, dict) and node.get("id") == node_id
        ]
        managed_nodes.append(
            {
                "id": node_id,
                "match_count": len(matches),
                "type": matches[0].get("type") if len(matches) == 1 else None,
                "text": matches[0].get("text") if len(matches) == 1 else None,
            }
        )

    managed_edges: list[dict[str, object]] = []
    for edge_id in edge_ids:
        matches = [
            edge
            for edge in edge_items
            if isinstance(edge, dict) and edge.get("id") == edge_id
        ]
        managed_edges.append(
            {
                "id": edge_id,
                "match_count": len(matches),
                "fromNode": matches[0].get("fromNode") if len(matches) == 1 else None,
                "toNode": matches[0].get("toNode") if len(matches) == 1 else None,
            }
        )

    encoded = json.dumps(
        {"nodes": managed_nodes, "edges": managed_edges},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def create_baseline(
    document: AnalysisDocument,
    bundle: AnalysisBundle,
    *,
    note_stem: str,
) -> AnalysisBaseline:
    """Create an explicit baseline only for a pair that conforms to the supplied IR."""
    report = validate_bundle(document, bundle, note_stem=note_stem)
    if not report.ok:
        codes = ", ".join(finding.code for finding in report.findings)
        raise AnalysisUpdateError(f"cannot baseline a nonconformant analysis pair: {codes}")

    rendered = render_analysis(document, note_stem=note_stem)
    generated_node_ids = [str(node["id"]) for node in rendered.canvas["nodes"]]
    generated_edge_ids = [str(edge["id"]) for edge in rendered.canvas["edges"]]
    actual_nodes = {
        str(node["id"]): node
        for node in bundle.canvas["nodes"]
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    claim_node_ids: dict[str, str] = {}
    for node in rendered.canvas["nodes"]:
        text = node.get("text")
        if not isinstance(text, str):
            continue
        for claim in document.claims:
            if f'id="{claim.claim_id}" role="{claim.role.value}"' in text:
                claim_node_ids[claim.claim_id] = str(node["id"])

    claims: dict[str, AnalysisBaselineClaim] = {}
    for claim in document.claims:
        node_id = claim_node_ids.get(claim.claim_id)
        node = actual_nodes.get(node_id or "")
        if node_id is None or node is None:
            raise AnalysisUpdateError(f"missing generated Canvas node for {claim.claim_id}")
        markdown = "\n".join(
            claim_markdown_lines(claim, workflow=claim.role is AnalysisRole.WORKFLOW)
        )
        canvas_text = claim_canvas_text(claim, note_stem)
        claims[claim.claim_id] = AnalysisBaselineClaim(
            role=claim.role,
            markdown_sha256=_text_hash(markdown),
            canvas_node_id=node_id,
            canvas_text_sha256=_text_hash(canvas_text),
        )

    return AnalysisBaseline(
        artifact_id=document.artifact_id,
        note_stem=note_stem,
        document=document,
        markdown_sha256=_text_hash(bundle.markdown),
        canvas_sha256=_managed_canvas_hash(
            bundle.canvas,
            node_ids=generated_node_ids,
            edge_ids=generated_edge_ids,
        ),
        claims=claims,
        generated_node_ids=generated_node_ids,
        generated_edge_ids=generated_edge_ids,
    )


def render_analysis_projection(
    document: AnalysisDocument,
    *,
    note_stem: str,
) -> tuple[AnalysisBundle, AnalysisBaseline]:
    """Render a new pair together with the baseline required for future updates."""
    bundle = render_analysis(document, note_stem=note_stem)
    return bundle, create_baseline(document, bundle, note_stem=note_stem)


def _merged_document(
    baseline: AnalysisDocument,
    update: AnalysisDocument,
) -> AnalysisDocument:
    if update.profile.kind is ProfileKind.WHOLE:
        return update

    replaced_roles = set(update.profile.roles)
    claims = [claim for claim in baseline.claims if claim.role not in replaced_roles]
    claims.extend(update.claims)
    role_rank = {role: index for index, role in enumerate(ALL_ROLES)}
    claims.sort(
        key=lambda claim: (
            role_rank[claim.role],
            claim.order or 0,
            claim.claim_id,
        )
    )
    roles = [role for role in ALL_ROLES if any(claim.role is role for claim in claims)]
    profile = (
        AnalysisProfile(kind=ProfileKind.WHOLE)
        if set(roles) == set(ALL_ROLES)
        else AnalysisProfile(kind=ProfileKind.FOCUSED, roles=roles)
    )
    return AnalysisDocument(
        artifact_id=baseline.artifact_id,
        paper_title=baseline.paper_title,
        profile=profile,
        claims=claims,
    )


def _merge_canvas(
    current: dict[str, list[dict[str, Any]]],
    *,
    baseline: AnalysisBaseline,
    rendered: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Replace only the managed subgraph while retaining user graph items and layout."""

    current_nodes = current.get("nodes") if isinstance(current, dict) else None
    current_edges = current.get("edges") if isinstance(current, dict) else None
    node_items = current_nodes if isinstance(current_nodes, list) else []
    edge_items = current_edges if isinstance(current_edges, list) else []

    old_node_ids = set(baseline.generated_node_ids)
    old_edge_ids = set(baseline.generated_edge_ids)
    new_nodes = {str(node["id"]): node for node in rendered["nodes"]}
    new_edges = {str(edge["id"]): edge for edge in rendered["edges"]}

    merged_nodes: list[dict[str, Any]] = []
    emitted_node_ids: set[str] = set()
    for current_node in node_items:
        if not isinstance(current_node, dict):
            # Retain malformed user data in the proposal so validation fails closed
            # instead of silently deleting a human-owned item.
            merged_nodes.append(current_node)
            continue
        node_id = current_node.get("id")
        if not isinstance(node_id, str) or node_id not in old_node_ids:
            merged_nodes.append(deepcopy(current_node))
            if isinstance(node_id, str):
                emitted_node_ids.add(node_id)
            continue
        expected = new_nodes.get(node_id)
        if expected is None:
            continue
        replacement = deepcopy(expected)
        for key, value in current_node.items():
            if key not in {"id", "type", "text"}:
                replacement[key] = deepcopy(value)
        merged_nodes.append(replacement)
        emitted_node_ids.add(node_id)

    for node in rendered["nodes"]:
        node_id = str(node["id"])
        if node_id not in emitted_node_ids:
            merged_nodes.append(deepcopy(node))
            emitted_node_ids.add(node_id)

    merged_edges: list[dict[str, Any]] = []
    emitted_edge_ids: set[str] = set()
    for current_edge in edge_items:
        if not isinstance(current_edge, dict):
            merged_edges.append(current_edge)
            continue
        edge_id = current_edge.get("id")
        if not isinstance(edge_id, str) or edge_id not in old_edge_ids:
            merged_edges.append(deepcopy(current_edge))
            if isinstance(edge_id, str):
                emitted_edge_ids.add(edge_id)
            continue
        expected = new_edges.get(edge_id)
        if expected is None:
            continue
        replacement = deepcopy(expected)
        for key, value in current_edge.items():
            if key not in {"id", "fromNode", "toNode"}:
                replacement[key] = deepcopy(value)
        merged_edges.append(replacement)
        emitted_edge_ids.add(edge_id)

    for edge in rendered["edges"]:
        edge_id = str(edge["id"])
        if edge_id not in emitted_edge_ids:
            merged_edges.append(deepcopy(edge))
            emitted_edge_ids.add(edge_id)

    return {"nodes": merged_nodes, "edges": merged_edges}


def plan_analysis_update(
    *,
    current: AnalysisBundle,
    baseline: AnalysisBaseline,
    update: AnalysisDocument,
    note_stem: str,
) -> AnalysisUpdatePlan:
    """Plan an update without writing; any stale/human edit returns a paired conflict."""
    if baseline.artifact_id != update.artifact_id:
        raise AnalysisUpdateError("update artifact_id differs from the baseline identity")
    if baseline.note_stem != note_stem:
        raise AnalysisUpdateError("note_stem differs from the trusted baseline")
    if update.profile.kind is ProfileKind.FOCUSED and update.paper_title != baseline.document.paper_title:
        raise AnalysisUpdateError("a focused update cannot change the paper title")

    trusted_bundle = render_analysis(baseline.document, note_stem=note_stem)
    trusted = create_baseline(baseline.document, trusted_bundle, note_stem=note_stem)
    if trusted.model_dump(mode="json") != baseline.model_dump(mode="json"):
        raise AnalysisUpdateError("analysis baseline is corrupt or does not match its embedded IR")

    merged = _merged_document(baseline.document, update)
    rendered = render_analysis(merged, note_stem=note_stem)
    proposed = AnalysisBundle(
        markdown=rendered.markdown,
        canvas=_merge_canvas(current.canvas, baseline=baseline, rendered=rendered.canvas),
    )
    conflicts: list[str] = []
    if _text_hash(current.markdown) != baseline.markdown_sha256:
        conflicts.append("markdown-revision-conflict")
    if (
        _managed_canvas_hash(
            current.canvas,
            node_ids=baseline.generated_node_ids,
            edge_ids=baseline.generated_edge_ids,
        )
        != baseline.canvas_sha256
    ):
        conflicts.append("canvas-revision-conflict")
    proposal_report = validate_bundle(merged, proposed, note_stem=note_stem)
    if not proposal_report.ok:
        conflicts.append("canvas-integrity-conflict")
    if conflicts:
        return AnalysisUpdatePlan(
            status="conflict",
            document=merged,
            current=current,
            proposed=proposed,
            baseline=None,
            conflicts=tuple(conflicts),
        )

    next_baseline = create_baseline(merged, proposed, note_stem=note_stem)
    return AnalysisUpdatePlan(
        status="ready",
        document=merged,
        current=current,
        proposed=proposed,
        baseline=next_baseline,
        conflicts=(),
    )
