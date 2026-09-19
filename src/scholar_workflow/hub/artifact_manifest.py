"""Explicit Vault registration for artifacts that cannot carry frontmatter.

JSON Canvas 1.0 reserves the document object for ``nodes`` and ``edges``.  Hub
identity therefore lives in a small Vault-side manifest instead of being
injected into the Canvas payload or inferred from its filename.
"""
from __future__ import annotations

import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError
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
)


ARTIFACT_MANIFEST_PATH = Path(".scholar-workflow/artifacts.yml")
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ArtifactManifestSnapshot:
    exists: bool
    rows: list[object]
    diagnostics: list[CatalogDiagnostic]


class VaultArtifactManifestProvider:
    """Overlay explicitly registered JSON Canvas artifacts onto a catalog."""

    def __init__(self, catalog: CatalogProvider, vault_root: Path) -> None:
        self._catalog = catalog
        self._vault_root = Path(vault_root)

    def load(self) -> HubCatalog:
        catalog = self._catalog.load()
        snapshot = self._load_manifest()
        diagnostics = [*catalog.diagnostics, *snapshot.diagnostics]
        resource_ids = {row.resource_id for row in catalog.resources}
        topic_ids = {row.topic_id for row in catalog.topics}
        base_artifact_ids = {row.artifact_id for row in catalog.artifacts}

        accepted: list[HubArtifact] = []
        rejected_ids: set[str] = set()
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        known_parents = resource_ids | topic_ids | base_artifact_ids

        for raw in snapshot.rows:
            entity_id = (
                str(raw.get("artifact_id"))
                if isinstance(raw, Mapping)
                and isinstance(raw.get("artifact_id"), str)
                and raw.get("artifact_id")
                else None
            )
            try:
                artifact = HubArtifact.model_validate(raw)
            except ValidationError:
                if entity_id:
                    rejected_ids.add(entity_id)
                diagnostics.append(
                    _diagnostic(
                        "invalid-vault-artifact-entry",
                        "Ignored an invalid Vault artifact manifest entry.",
                        entity_id,
                    )
                )
                continue
            if artifact.format != ArtifactFormat.CANVAS or artifact.kind != ArtifactKind.ANALYSIS_CANVAS:
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "unsupported-vault-artifact-manifest-entry",
                        "The Vault artifact manifest currently accepts analysis Canvas files only.",
                        artifact.artifact_id,
                    )
                )
                continue
            if PurePosixPath(artifact.vault_path).suffix.lower() != ".canvas":
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "invalid-vault-canvas-path",
                        "A registered analysis Canvas must use the .canvas suffix.",
                        artifact.artifact_id,
                    )
                )
                continue
            if artifact.artifact_id in seen_ids or artifact.vault_path in seen_paths:
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "duplicate-vault-artifact-manifest-entry",
                        "A Vault artifact ID or path was declared more than once.",
                        artifact.artifact_id,
                    )
                )
                continue
            try:
                _existing_regular_file(self._vault_root, artifact.vault_path)
            except (VaultPathError, FileNotFoundError):
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "missing-or-unsafe-vault-artifact",
                        "Ignored a Vault artifact whose file is missing, unsafe, or a symlink.",
                        artifact.artifact_id,
                    )
                )
                continue
            if artifact.resource_id is not None and artifact.resource_id not in resource_ids:
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "dangling-vault-artifact-resource",
                        "Ignored a Vault artifact with an unknown resource relation.",
                        artifact.artifact_id,
                    )
                )
                continue
            if artifact.topic_id is not None and artifact.topic_id not in topic_ids:
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "dangling-vault-artifact-topic",
                        "Ignored a Vault artifact with an unknown topic relation.",
                        artifact.artifact_id,
                    )
                )
                continue
            if artifact.parent_id is not None and artifact.parent_id not in known_parents:
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "dangling-vault-artifact-parent",
                        "Ignored a Vault artifact with an unknown parent relation.",
                        artifact.artifact_id,
                    )
                )
                continue
            seen_ids.add(artifact.artifact_id)
            seen_paths.add(artifact.vault_path)
            accepted.append(artifact)

        accepted_ids = {row.artifact_id for row in accepted}
        for artifact in catalog.artifacts:
            if (
                artifact.format == ArtifactFormat.CANVAS
                and artifact.artifact_id not in accepted_ids
            ):
                rejected_ids.add(artifact.artifact_id)
                diagnostics.append(
                    _diagnostic(
                        "unregistered-vault-canvas",
                        "Ignored a snapshot Canvas without a valid Vault artifact manifest entry.",
                        artifact.artifact_id,
                    )
                )

        controlled_ids = rejected_ids | {row.artifact_id for row in accepted}
        artifacts = {
            row.artifact_id: row
            for row in catalog.artifacts
            if row.artifact_id not in rejected_ids
        }
        artifacts.update({row.artifact_id: row for row in accepted})
        surviving_parents = resource_ids | topic_ids | set(artifacts)
        for artifact_id, artifact in list(artifacts.items()):
            if artifact.parent_id is not None and artifact.parent_id not in surviving_parents:
                artifacts[artifact_id] = artifact.model_copy(update={"parent_id": None})
                diagnostics.append(
                    _diagnostic(
                        "dangling-parent-after-manifest-rejection",
                        "Cleared a parent relation whose manifest artifact was rejected.",
                        artifact_id,
                    )
                )
        remaining_artifact_ids = set(artifacts)
        assets = []
        for asset in catalog.assets:
            if all(owner in remaining_artifact_ids for owner in asset.owner_artifact_ids):
                assets.append(asset)
            else:
                diagnostics.append(
                    _diagnostic(
                        "dangling-asset-after-artifact-rejection",
                        "Ignored an asset whose owner artifact was rejected.",
                        asset.asset_id,
                    )
                )

        resource_payloads = {
            row.resource_id: row.model_dump() for row in catalog.resources
        }
        topic_payloads = {row.topic_id: row.model_dump() for row in catalog.topics}
        for payload in resource_payloads.values():
            payload["artifact_ids"] = [
                value for value in payload["artifact_ids"] if value not in controlled_ids
            ]
        for payload in topic_payloads.values():
            payload["artifact_ids"] = [
                value for value in payload["artifact_ids"] if value not in controlled_ids
            ]
        for artifact in accepted:
            if artifact.resource_id in resource_payloads:
                resource_payloads[artifact.resource_id]["artifact_ids"].append(
                    artifact.artifact_id
                )
            if artifact.topic_id in topic_payloads:
                topic_payloads[artifact.topic_id]["artifact_ids"].append(
                    artifact.artifact_id
                )

        sources = {row.source: row for row in catalog.sources}
        sources["vault-artifact-manifest"] = SourceStatus(
            source="vault-artifact-manifest",
            available=snapshot.exists,
            detail="explicit registration for JSON Canvas; no filename inference",
        )
        return HubCatalog(
            generated_at=catalog.generated_at,
            sources=list(sources.values()),
            resources=[
                HubResource.model_validate(row) for row in resource_payloads.values()
            ],
            topics=[HubTopic.model_validate(row) for row in topic_payloads.values()],
            artifacts=list(artifacts.values()),
            assets=assets,
            diagnostics=diagnostics,
        )

    def _load_manifest(self) -> ArtifactManifestSnapshot:
        try:
            path = _manifest_path(self._vault_root)
        except VaultPathError:
            return ArtifactManifestSnapshot(
                exists=False,
                rows=[],
                diagnostics=[
                    _diagnostic(
                        "unsafe-vault-artifact-manifest",
                        "Ignored an unsafe Vault artifact manifest path.",
                    )
                ],
            )
        if not path.exists():
            return ArtifactManifestSnapshot(False, [], [])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_MANIFEST_BYTES:
            return ArtifactManifestSnapshot(
                exists=True,
                rows=[],
                diagnostics=[
                    _diagnostic(
                        "invalid-vault-artifact-manifest",
                        "Ignored an invalid Vault artifact manifest.",
                    )
                ],
            )
        yaml = YAML(typ="safe")
        yaml.allow_duplicate_keys = False
        try:
            payload = yaml.load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return ArtifactManifestSnapshot(
                exists=True,
                rows=[],
                diagnostics=[
                    _diagnostic(
                        "invalid-vault-artifact-manifest",
                        f"Ignored an invalid Vault artifact manifest ({type(exc).__name__}).",
                    )
                ],
            )
        if (
            not isinstance(payload, Mapping)
            or set(payload) != {"schema_version", "artifacts"}
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("artifacts"), list)
        ):
            return ArtifactManifestSnapshot(
                exists=True,
                rows=[],
                diagnostics=[
                    _diagnostic(
                        "invalid-vault-artifact-manifest",
                        "Ignored an invalid Vault artifact manifest.",
                    )
                ],
            )
        return ArtifactManifestSnapshot(True, list(payload["artifacts"]), [])


def _manifest_path(vault_root: Path) -> Path:
    current = Path(vault_root)
    for part in ARTIFACT_MANIFEST_PATH.parts:
        current = current / part
        if current.is_symlink():
            raise VaultPathError("symbolic links are not allowed for the artifact manifest")
    return safe_vault_path(vault_root, ARTIFACT_MANIFEST_PATH)


def _existing_regular_file(vault_root: Path, vault_path: str) -> Path:
    current = Path(vault_root)
    for part in PurePosixPath(vault_path).parts:
        current = current / part
        if current.is_symlink():
            raise VaultPathError("symbolic links are not allowed for registered artifacts")
    path = safe_vault_path(vault_root, vault_path)
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        raise FileNotFoundError(vault_path) from exc
    if not stat.S_ISREG(mode):
        raise FileNotFoundError(vault_path)
    return path


def _diagnostic(
    code: str,
    message: str,
    entity_id: str | None = None,
) -> CatalogDiagnostic:
    return CatalogDiagnostic(
        level="warning",
        code=code,
        message=message,
        entity_id=entity_id,
    )


__all__ = [
    "ARTIFACT_MANIFEST_PATH",
    "ArtifactManifestSnapshot",
    "VaultArtifactManifestProvider",
]
