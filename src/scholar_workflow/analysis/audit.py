"""Read-only conformance audit for manifest-supplied analysis pairs."""
from __future__ import annotations

import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path

from scholar_workflow.analysis.batch import AnalysisBatchStore
from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    ATOMIC_RESOURCE_KINDS,
    AnalysisAuditReport,
    AnalysisAuditTarget,
    AnalysisBaseline,
    AnalysisCommitReceipt,
    AnalysisState,
    ConformanceFinding,
    CoreDocumentKind,
    KnowledgeAuditManifest,
    SupportingDocumentKind,
)
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import create_baseline

_RAW_HUB_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost):23128(?:[/\s]|$)")
_UNRESOLVED_TEMPLATE = re.compile(
    r"\{\{[^{}\n]+\}\}|<FILL_ME>|__PLACEHOLDER__|\[TODO\]",
    re.IGNORECASE,
)


def audit_analysis_batch_store(store: AnalysisBatchStore) -> AnalysisAuditReport:
    """Report unfinished items and retained failed stages without mutating state."""
    findings: list[ConformanceFinding] = []
    checked: list[str] = []
    for batch_id, item in store.list_items():
        qualified_id = f"{batch_id}/{item.item_id}"
        checked.append(qualified_id)
        if item.state in {AnalysisState.QUEUED, AnalysisState.RUNNING}:
            findings.append(
                ConformanceFinding(
                    code="unfinished-batch-item",
                    path=f"batches/{qualified_id}",
                    message=f"Batch item remains {item.state.value}.",
                    repairable=False,
                )
            )
        if item.state is AnalysisState.FAILED and item.stage_path is not None:
            findings.append(
                ConformanceFinding(
                    code="failed-stage-residue",
                    path=f"batches/{qualified_id}",
                    message="A failed item retains a staging path after cleanup failure.",
                    repairable=False,
                )
            )
    return AnalysisAuditReport(
        ok=not findings,
        checked_item_ids=checked,
        findings=findings,
    )


def _resolve_readonly(vault_root: Path, relative_path: str) -> Path:
    candidate = vault_root.joinpath(*relative_path.split("/"))
    current = vault_root
    for part in relative_path.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError("analysis audit target cannot traverse a symlink")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(vault_root):
        raise ValueError("analysis audit target escaped the Vault root")
    return candidate


def audit_analysis_pairs(
    vault_root: Path,
    targets: list[AnalysisAuditTarget],
    *,
    receipt_root: Path | None = None,
    require_commit_metadata: bool = False,
) -> AnalysisAuditReport:
    """Read explicit targets without scanning, repairing, or writing any store."""
    root = vault_root.resolve(strict=True)
    receipts = receipt_root.resolve(strict=True) if receipt_root is not None else root
    findings: list[ConformanceFinding] = []
    checked: list[str] = []
    for target in targets:
        checked.append(target.item_id)
        try:
            markdown_path = _resolve_readonly(root, target.markdown_path)
            canvas_path = _resolve_readonly(root, target.canvas_path)
            markdown = markdown_path.read_text(encoding="utf-8")
            canvas = json.loads(canvas_path.read_text(encoding="utf-8"))
            if not isinstance(canvas, dict):
                raise TypeError("Canvas root must be an object")
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            findings.append(
                ConformanceFinding(
                    code="analysis-audit-read-failed",
                    path=f"items/{target.item_id}",
                    message=str(exc),
                    repairable=False,
                )
            )
            continue
        report = validate_bundle(
            target.document,
            AnalysisBundle(markdown=markdown, canvas=canvas),
            note_stem=target.note_stem,
        )
        findings.extend(
            finding.model_copy(update={"path": f"items/{target.item_id}/{finding.path}"})
            for finding in report.findings
        )
        if require_commit_metadata and target.sidecar_path is None:
            findings.append(
                _finding(
                    "analysis-sidecar-untracked",
                    f"items/{target.item_id}",
                    "Weekly audit requires an explicit canonical analysis sidecar.",
                )
            )
        elif target.sidecar_path is not None:
            try:
                sidecar_path = _resolve_readonly(root, target.sidecar_path)
                baseline = AnalysisBaseline.model_validate_json(
                    sidecar_path.read_text(encoding="utf-8")
                )
                expected = create_baseline(
                    target.document,
                    AnalysisBundle(markdown=markdown, canvas=canvas),
                    note_stem=target.note_stem,
                )
                if baseline.model_dump(mode="json") != expected.model_dump(mode="json"):
                    raise ValueError(
                        "analysis sidecar does not match canonical Markdown/Canvas revisions"
                    )
            except (OSError, UnicodeError, ValueError) as exc:
                findings.append(
                    _finding(
                        "analysis-sidecar-drift",
                        f"items/{target.item_id}/sidecar",
                        str(exc),
                    )
                )

        if require_commit_metadata and target.receipt_path is None:
            findings.append(
                _finding(
                    "analysis-receipt-untracked",
                    f"items/{target.item_id}",
                    "Weekly audit requires an explicit canonical commit receipt.",
                )
            )
        elif target.receipt_path is not None:
            try:
                receipt_path = _resolve_readonly(receipts, target.receipt_path)
                receipt = AnalysisCommitReceipt.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
                if receipt.artifact_id != target.document.artifact_id:
                    raise ValueError("commit receipt artifact identity differs from analysis IR")
                expected_paths = {
                    target.markdown_path,
                    target.canvas_path,
                    target.sidecar_path,
                }
                receipt_paths = {item.path for item in receipt.files}
                if None in expected_paths or receipt_paths != expected_paths:
                    raise ValueError("commit receipt does not bind the canonical three-file set")
                for record in receipt.files:
                    canonical = _resolve_readonly(root, record.path)
                    digest = "sha256:" + sha256(canonical.read_bytes()).hexdigest()
                    if digest != record.after_sha256:
                        raise ValueError(
                            f"canonical revision differs from receipt for {record.path}"
                        )
            except (OSError, UnicodeError, ValueError) as exc:
                findings.append(
                    _finding(
                        "analysis-receipt-drift",
                        f"items/{target.item_id}/receipt",
                        str(exc),
                    )
                )
    return AnalysisAuditReport(
        ok=not any(finding.severity == "error" for finding in findings),
        checked_item_ids=checked,
        findings=findings,
    )


def _finding(
    code: str,
    path: str,
    message: str,
    *,
    repairable: bool = False,
    severity: str = "error",
) -> ConformanceFinding:
    return ConformanceFinding(
        code=code,
        path=path,
        message=message,
        repairable=repairable,
        severity=severity,  # type: ignore[arg-type]
    )


def _duplicates(values: list[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _catalog_ids(
    catalog: dict[str, object],
    key: str,
    identity_key: str,
) -> tuple[list[str], list[ConformanceFinding]]:
    findings: list[ConformanceFinding] = []
    rows = catalog.get(key)
    if not isinstance(rows, list):
        return [], [
            _finding(
                "catalog-invalid",
                f"catalog/{key}",
                f"Catalog field {key!r} must be an array.",
            )
        ]
    values: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get(identity_key), str):
            findings.append(
                _finding(
                    "catalog-invalid",
                    f"catalog/{key}/{index}",
                    f"Catalog row must contain string {identity_key!r}.",
                )
            )
            continue
        values.append(row[identity_key])
    for duplicate in sorted(_duplicates(values)):
        findings.append(
            _finding(
                "catalog-duplicate-id",
                f"catalog/{key}",
                f"Catalog contains duplicate identity {duplicate!r}.",
            )
        )
    return values, findings


def audit_knowledge_manifest(
    vault_root: Path,
    manifest: KnowledgeAuditManifest,
    *,
    catalog_root: Path | None = None,
    commit_state_root: Path | None = None,
) -> AnalysisAuditReport:
    """Run the weekly Knowledge audit over only explicitly listed Vault objects.

    This function does not discover files, projects, or Zotero storage and never
    writes to the Vault or catalog.  Free-form Markdown is inspected only for the
    two explicit migration hazards: unresolved template markers and raw legacy
    port URLs.
    """

    root = vault_root.resolve(strict=True)
    catalog_base = (
        catalog_root.resolve(strict=True) if catalog_root is not None else root
    )
    findings: list[ConformanceFinding] = []
    checked: list[str] = []
    object_ids = [item.object_id for item in manifest.objects]
    paths = [item.vault_path for item in manifest.objects]

    for duplicate in sorted(_duplicates(object_ids)):
        findings.append(
            _finding(
                "duplicate-knowledge-id",
                "objects",
                f"Knowledge object ID {duplicate!r} appears more than once.",
            )
        )
    for duplicate in sorted(_duplicates(paths)):
        findings.append(
            _finding(
                "duplicate-knowledge-path",
                "objects",
                f"Vault path {duplicate!r} is assigned more than once.",
            )
        )

    primary_ids = {
        item.object_id
        for item in manifest.objects
        if item.object_class in {"atomic_resource", "core_document"}
    }
    allowed_kinds = {
        "atomic_resource": {item.value for item in ATOMIC_RESOURCE_KINDS},
        "core_document": {item.value for item in CoreDocumentKind},
        "supporting_document": {item.value for item in SupportingDocumentKind},
    }
    for item in manifest.objects:
        if item.object_id not in checked:
            checked.append(item.object_id)
        item_path = f"objects/{item.object_id}"
        if item.kind not in allowed_kinds[item.object_class]:
            findings.append(
                _finding(
                    "knowledge-kind-role-mismatch",
                    item_path,
                    f"Kind {item.kind!r} cannot be used as {item.object_class!r}.",
                )
            )
        if item.object_class == "supporting_document":
            if item.owner_id is None or item.owner_id not in primary_ids:
                findings.append(
                    _finding(
                        "orphan-supporting-document",
                        item_path,
                        "Supporting document has no explicit atomic resource or context owner.",
                    )
                )
            if item.catalog_kind not in {None, "artifact"}:
                findings.append(
                    _finding(
                        "knowledge-catalog-kind-mismatch",
                        item_path,
                        "Supporting documents cannot be projected as atomic resources.",
                    )
                )
        elif item.owner_id is not None:
            findings.append(
                _finding(
                    "knowledge-owner-misuse",
                    item_path,
                    "Atomic resources and core documents cannot use supporting ownership.",
                )
            )
        elif item.object_class == "atomic_resource" and item.catalog_kind not in {
            None,
            "resource",
        }:
            findings.append(
                _finding(
                    "knowledge-catalog-kind-mismatch",
                    item_path,
                    "Atomic resources must project as catalog resources.",
                )
            )

        if (
            item.object_class in {"atomic_resource", "core_document"}
            and not item.vault_path.endswith(".md")
        ):
            findings.append(
                _finding(
                    "human-readable-markdown-required",
                    item_path,
                    "Atomic resources and core documents require a Markdown document.",
                )
            )

        try:
            target = _resolve_readonly(root, item.vault_path)
            payload = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            findings.append(
                _finding(
                    "knowledge-object-read-failed",
                    item_path,
                    str(exc),
                )
            )
            continue
        if not payload.strip():
            findings.append(
                _finding(
                    "empty-human-readable-document",
                    item_path,
                    "Knowledge document is empty.",
                )
            )
        if target.suffix.casefold() == ".md":
            if _UNRESOLVED_TEMPLATE.search(payload):
                findings.append(
                    _finding(
                        "unresolved-template-marker",
                        item_path,
                        "Human-readable Markdown contains an unresolved template marker.",
                    )
                )
            if _RAW_HUB_URL.search(payload):
                findings.append(
                    _finding(
                        "raw-23128-url",
                        item_path,
                        "Markdown contains a raw device-local 23128 URL.",
                    )
                )

    if manifest.analysis_targets:
        pair_report = audit_analysis_pairs(
            root,
            manifest.analysis_targets,
            receipt_root=commit_state_root,
            require_commit_metadata=True,
        )
        for item_id in pair_report.checked_item_ids:
            if item_id not in checked:
                checked.append(item_id)
        findings.extend(pair_report.findings)

    if manifest.catalog_path is not None:
        try:
            catalog_path = _resolve_readonly(catalog_base, manifest.catalog_path)
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            if not isinstance(catalog, dict):
                raise TypeError("Catalog root must be an object")
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            findings.append(
                _finding(
                    "catalog-read-failed",
                    "catalog",
                    str(exc),
                )
            )
        else:
            resources, resource_findings = _catalog_ids(
                catalog,
                "resources",
                "resource_id",
            )
            artifacts, artifact_findings = _catalog_ids(
                catalog,
                "artifacts",
                "artifact_id",
            )
            findings.extend(resource_findings)
            findings.extend(artifact_findings)
            if (
                manifest.expected_catalog_revision is not None
                and catalog.get("revision") != manifest.expected_catalog_revision
            ):
                findings.append(
                    _finding(
                        "catalog-revision-drift",
                        "catalog/revision",
                        "Catalog revision differs from the explicit audit baseline.",
                    )
                )
            resource_set = set(resources)
            artifact_set = set(artifacts)
            resource_rows = catalog.get("resources")
            artifact_rows = catalog.get("artifacts")
            resource_by_id = (
                {
                    row["resource_id"]: row
                    for row in resource_rows
                    if isinstance(row, dict)
                    and isinstance(row.get("resource_id"), str)
                }
                if isinstance(resource_rows, list)
                else {}
            )
            artifact_by_id = (
                {
                    row["artifact_id"]: row
                    for row in artifact_rows
                    if isinstance(row, dict)
                    and isinstance(row.get("artifact_id"), str)
                }
                if isinstance(artifact_rows, list)
                else {}
            )
            artifact_kind_map = {
                SupportingDocumentKind.ANALYSIS.value: "paper-analysis",
                SupportingDocumentKind.ANALYSIS_CANVAS.value: "analysis-canvas",
                SupportingDocumentKind.ANNOTATIONS.value: "annotation-note",
                SupportingDocumentKind.READING_NOTE.value: "reading-note",
            }
            for item in manifest.objects:
                expected_ids = (
                    resource_set if item.catalog_kind == "resource" else artifact_set
                )
                if item.catalog_kind is not None and item.object_id not in expected_ids:
                    findings.append(
                        _finding(
                            "catalog-projection-drift",
                            f"objects/{item.object_id}",
                            f"Expected {item.catalog_kind} projection is missing from catalog.",
                        )
                    )
                    continue
                if item.catalog_kind == "resource":
                    row = resource_by_id.get(item.object_id)
                    if row is not None and row.get("kind") != item.kind:
                        findings.append(
                            _finding(
                                "catalog-projection-drift",
                                f"objects/{item.object_id}",
                                "Catalog resource kind differs from the Knowledge manifest.",
                            )
                        )
                elif item.catalog_kind == "artifact":
                    row = artifact_by_id.get(item.object_id)
                    if row is None:
                        continue
                    expected_kind = artifact_kind_map.get(item.kind)
                    owner_fields = {row.get(key) for key in ("resource_id", "topic_id")}
                    if row.get("vault_path") != item.vault_path:
                        findings.append(
                            _finding(
                                "catalog-projection-drift",
                                f"objects/{item.object_id}",
                                "Catalog artifact path differs from the Knowledge manifest.",
                            )
                        )
                    if item.owner_id is not None and item.owner_id not in owner_fields:
                        findings.append(
                            _finding(
                                "catalog-projection-drift",
                                f"objects/{item.object_id}",
                                "Catalog artifact owner differs from the Knowledge manifest.",
                            )
                        )
                    if expected_kind is not None and row.get("kind") != expected_kind:
                        findings.append(
                            _finding(
                                "catalog-projection-drift",
                                f"objects/{item.object_id}",
                                "Catalog artifact kind differs from the Knowledge manifest.",
                            )
                        )

            resource_ids = set(resources)
            if isinstance(resource_rows, list):
                for index, row in enumerate(resource_rows):
                    if not isinstance(row, dict):
                        continue
                    artifact_ids = row.get("artifact_ids", [])
                    if isinstance(artifact_ids, list):
                        for artifact_id in artifact_ids:
                            if isinstance(artifact_id, str) and artifact_id not in artifact_set:
                                findings.append(
                                    _finding(
                                        "catalog-orphan-relation",
                                        f"catalog/resources/{index}",
                                        f"Resource references missing artifact {artifact_id!r}.",
                                    )
                                )
            if isinstance(artifact_rows, list):
                for index, row in enumerate(artifact_rows):
                    if not isinstance(row, dict):
                        continue
                    resource_id = row.get("resource_id")
                    if isinstance(resource_id, str) and resource_id not in resource_ids:
                        findings.append(
                            _finding(
                                "catalog-orphan-relation",
                                f"catalog/artifacts/{index}",
                                f"Artifact references missing resource {resource_id!r}.",
                            )
                        )

    return AnalysisAuditReport(
        ok=not any(finding.severity == "error" for finding in findings),
        checked_item_ids=checked,
        findings=findings,
    )
