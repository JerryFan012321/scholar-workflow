"""Discover Hub-governed artifacts from Obsidian frontmatter.

Only the reserved ``sw_*`` identity layer is read. Human YAML and document
bodies are deliberately ignored, so the Hub contract governs Obsidian rather
than learning accidental structure from prose or filenames.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ruamel.yaml import YAML

from scholar_workflow.adapters.obsidian import VaultPathError, safe_vault_path
from scholar_workflow.hub.catalog import CatalogProvider
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    CatalogDiagnostic,
    HubArtifact,
    HubCatalog,
    HubResource,
    HubTopic,
    SourceStatus,
    TreeKind,
)
from scholar_workflow.hub.obsidian_contract import MANAGED_FRONTMATTER_FIELDS


_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?\n",
    re.DOTALL | re.MULTILINE,
)
_SCAN_BYTES = 256 * 1024


class VaultCatalogProvider:
    """Overlay artifacts declared through Hub-owned Vault frontmatter."""

    def __init__(self, catalog: CatalogProvider, vault_root: Path) -> None:
        self._catalog = catalog
        self._vault_root = Path(vault_root)

    def load(self) -> HubCatalog:
        catalog = self._catalog.load()
        diagnostics = list(catalog.diagnostics)
        declarations, rejected_ids, rejected_paths = self._declarations(diagnostics)
        resource_ids = {row.resource_id for row in catalog.resources}
        topic_ids = {row.topic_id for row in catalog.topics}
        known_parent_ids = resource_ids | topic_ids | set(declarations)

        discovered: list[HubArtifact] = []
        for artifact_id, declaration in declarations.items():
            resource_id = _known_optional(
                declaration.get("sw_resource_id"),
                resource_ids,
                diagnostics,
                code="dangling-vault-resource",
                artifact_id=artifact_id,
            )
            topic_id = _known_optional(
                declaration.get("sw_topic_id"),
                topic_ids,
                diagnostics,
                code="dangling-vault-topic",
                artifact_id=artifact_id,
            )
            parent_id = _known_optional(
                declaration.get("sw_parent_id"),
                known_parent_ids,
                diagnostics,
                code="dangling-vault-parent",
                artifact_id=artifact_id,
            )
            tree_kind = declaration.get("sw_tree_kind")
            if tree_kind not in {None, "technical", "challenge"}:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="warning",
                        code="invalid-vault-tree-kind",
                        message="Managed tree kind is not supported by HubCatalog.",
                        entity_id=artifact_id,
                    )
                )
                tree_kind = None
            revision = declaration.get("sw_revision")
            discovered.append(
                HubArtifact(
                    artifact_id=artifact_id,
                    kind=ArtifactKind(str(declaration["sw_kind"])),
                    format=(
                        ArtifactFormat.CANVAS
                        if str(declaration["vault_path"]).endswith(".canvas")
                        else ArtifactFormat.MARKDOWN
                    ),
                    vault_path=str(declaration["vault_path"]),
                    resource_id=resource_id,
                    topic_id=topic_id,
                    parent_id=parent_id,
                    tree_kind=TreeKind(tree_kind) if tree_kind else None,
                    revision=str(revision) if revision is not None else None,
                )
            )

        artifact_by_id = {
            row.artifact_id: row
            for row in catalog.artifacts
            if row.artifact_id not in rejected_ids
            and row.vault_path not in rejected_paths
        }
        for artifact in discovered:
            # One Vault declaration is authoritative for its current path. This lets
            # a human rename or move a note in Obsidian without leaving the Hub pinned
            # to a stale rebuildable snapshot. Duplicate declarations inside the Vault
            # are rejected earlier by ``_declarations``.
            artifact_by_id[artifact.artifact_id] = artifact

        surviving_parents = resource_ids | topic_ids | set(artifact_by_id)
        for artifact_id, artifact in list(artifact_by_id.items()):
            if artifact.parent_id is not None and artifact.parent_id not in surviving_parents:
                artifact_by_id[artifact_id] = artifact.model_copy(
                    update={"parent_id": None}
                )
                diagnostics.append(
                    CatalogDiagnostic(
                        level="warning",
                        code="dangling-parent-after-vault-artifact-rejection",
                        message="Cleared a parent relation whose Vault artifact was rejected.",
                        entity_id=artifact_id,
                    )
                )

        resource_payloads = {
            row.resource_id: row.model_dump() for row in catalog.resources
        }
        topic_payloads = {row.topic_id: row.model_dump() for row in catalog.topics}
        controlled_ids = rejected_ids | {row.artifact_id for row in discovered}
        for payload in resource_payloads.values():
            payload["artifact_ids"] = [
                value for value in payload["artifact_ids"] if value not in controlled_ids
            ]
        for payload in topic_payloads.values():
            payload["artifact_ids"] = [
                value for value in payload["artifact_ids"] if value not in controlled_ids
            ]
        for artifact in artifact_by_id.values():
            if artifact.resource_id in resource_payloads:
                refs = resource_payloads[artifact.resource_id]["artifact_ids"]
                if artifact.artifact_id not in refs:
                    refs.append(artifact.artifact_id)
            if artifact.topic_id in topic_payloads:
                refs = topic_payloads[artifact.topic_id]["artifact_ids"]
                if artifact.artifact_id not in refs:
                    refs.append(artifact.artifact_id)

        sources = {row.source: row for row in catalog.sources}
        sources["obsidian-vault"] = SourceStatus(
            source="obsidian-vault",
            available=self._vault_root.is_dir(),
            detail="reads only sw_* frontmatter; human body is not catalogued",
        )
        remaining_artifact_ids = set(artifact_by_id)
        assets = []
        for asset in catalog.assets:
            if all(owner in remaining_artifact_ids for owner in asset.owner_artifact_ids):
                assets.append(asset)
            else:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="warning",
                        code="dangling-asset-after-vault-artifact-rejection",
                        message="Ignored an asset whose owner artifact was rejected.",
                        entity_id=asset.asset_id,
                    )
                )
        return HubCatalog(
            generated_at=catalog.generated_at,
            sources=list(sources.values()),
            resources=[HubResource.model_validate(row) for row in resource_payloads.values()],
            topics=[HubTopic.model_validate(row) for row in topic_payloads.values()],
            artifacts=list(artifact_by_id.values()),
            assets=assets,
            diagnostics=diagnostics,
        )

    def _declarations(
        self,
        diagnostics: list[CatalogDiagnostic],
    ) -> tuple[dict[str, dict], set[str], set[str]]:
        declarations: dict[str, dict] = {}
        rejected_ids: set[str] = set()
        rejected_paths: set[str] = set()
        if not self._vault_root.is_dir():
            return declarations, rejected_ids, rejected_paths
        root = self._vault_root.resolve()
        paths = sorted(self._vault_root.rglob("*.md"))
        yaml = YAML(typ="safe")
        for candidate in paths:
            try:
                path = safe_vault_path(root, candidate.relative_to(self._vault_root))
            except (VaultPathError, ValueError):
                continue
            if not path.is_file():
                continue
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                prefix = handle.read(_SCAN_BYTES)
            match = _FRONTMATTER_RE.match(prefix)
            if match is None or "sw_" not in match.group(1):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                frontmatter = yaml.load(match.group(1)) or {}
            except Exception:
                rejected_paths.add(relative)
                diagnostics.append(_invalid_diagnostic(relative, "invalid-vault-frontmatter"))
                continue
            if not isinstance(frontmatter, Mapping):
                rejected_paths.add(relative)
                diagnostics.append(_invalid_diagnostic(relative, "invalid-vault-frontmatter"))
                continue
            possible_id = frontmatter.get("sw_catalog_id")
            if isinstance(possible_id, str) and possible_id:
                candidate_id = possible_id
            else:
                candidate_id = None
            unknown_managed = {
                str(key)
                for key in frontmatter
                if isinstance(key, str)
                and key.startswith("sw_")
                and key not in MANAGED_FRONTMATTER_FIELDS
            }
            if unknown_managed:
                rejected_paths.add(relative)
                if candidate_id:
                    rejected_ids.add(candidate_id)
                diagnostics.append(
                    _invalid_diagnostic(relative, "unknown-vault-managed-field")
                )
                continue
            if frontmatter.get("sw_schema") != 1:
                rejected_paths.add(relative)
                if candidate_id:
                    rejected_ids.add(candidate_id)
                diagnostics.append(_invalid_diagnostic(relative, "unsupported-vault-schema"))
                continue
            artifact_id = frontmatter.get("sw_catalog_id")
            kind = frontmatter.get("sw_kind")
            try:
                ArtifactKind(str(kind))
            except ValueError:
                rejected_paths.add(relative)
                if candidate_id:
                    rejected_ids.add(candidate_id)
                diagnostics.append(_invalid_diagnostic(relative, "invalid-vault-kind"))
                continue
            if not isinstance(artifact_id, str) or not artifact_id:
                rejected_paths.add(relative)
                diagnostics.append(_invalid_diagnostic(relative, "missing-vault-artifact-id"))
                continue
            if artifact_id in declarations or artifact_id in rejected_ids:
                previous = declarations.pop(artifact_id, None)
                if previous is not None:
                    rejected_paths.add(str(previous["vault_path"]))
                rejected_paths.add(relative)
                rejected_ids.add(artifact_id)
                diagnostics.append(
                    CatalogDiagnostic(
                        level="error",
                        code="duplicate-vault-artifact-id",
                        message="One artifact ID was declared more than once in the Vault.",
                        entity_id=artifact_id,
                    )
                )
                continue
            declaration = dict(frontmatter)
            declaration["vault_path"] = relative
            declarations[artifact_id] = declaration
        return declarations, rejected_ids, rejected_paths


def _known_optional(
    value: object,
    known: set[str],
    diagnostics: list[CatalogDiagnostic],
    *,
    code: str,
    artifact_id: str,
) -> str | None:
    if value is None:
        return None
    candidate = str(value)
    if candidate in known:
        return candidate
    diagnostics.append(
        CatalogDiagnostic(
            level="warning",
            code=code,
            message="Managed Vault relation has no matching HubCatalog entity.",
            entity_id=artifact_id,
        )
    )
    return None


def _invalid_diagnostic(path: str, code: str) -> CatalogDiagnostic:
    return CatalogDiagnostic(
        level="warning",
        code=code,
        message=f"Ignored invalid managed frontmatter in {path}.",
        entity_id=None,
    )
