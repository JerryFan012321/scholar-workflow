"""Explicit Vault asset manifest and additive-only storage boundary.

Vault assets are not discovered from Markdown embeds or filenames.  Their bytes
live in the Vault and their relationships are declared by one small, portable
manifest.  Zotero paper attachments are outside this module entirely.
"""
from __future__ import annotations

import hashlib
import io
import mimetypes
import os
import tempfile
import threading
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from pydantic import ValidationError
from ruamel.yaml import YAML

from scholar_workflow.adapters.obsidian import VaultPathError, safe_vault_path
from scholar_workflow.hub.catalog import CatalogProvider
from scholar_workflow.hub.models import (
    AssetRole,
    CatalogDiagnostic,
    HubAsset,
    HubCatalog,
    SourceStatus,
)


ASSET_MANIFEST_PATH = Path(".scholar-workflow/assets.yml")
DEFAULT_MAX_ASSET_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024


class AssetManifestError(ValueError):
    """The manifest cannot be updated without losing or fabricating entries."""


class InvalidAssetNameError(ValueError):
    """An uploaded filename is not one portable, visible filename."""


class UnknownAssetError(KeyError):
    """The requested opaque asset ID is not declared in the current manifest."""


class AssetIntegrityError(AssetManifestError):
    """A declared asset no longer matches its safe path or recorded bytes."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AssetManifestSnapshot:
    exists: bool
    assets: list[HubAsset]
    diagnostics: list[CatalogDiagnostic]


class VaultAssetManifestStore:
    """Read and atomically replace the human-checkable Vault asset manifest."""

    def __init__(self, vault_root: Path) -> None:
        self._vault_root = Path(vault_root)

    @property
    def path(self) -> Path:
        return safe_vault_path(self._vault_root, ASSET_MANIFEST_PATH)

    @property
    def vault_root(self) -> Path:
        return self._vault_root

    def resolve_asset_path(self, vault_path: str) -> Path:
        """Resolve one manifest path without exposing or accepting an absolute path."""
        current = self._vault_root
        for part in PurePosixPath(vault_path).parts:
            current = current / part
            if current.is_symlink():
                raise VaultPathError(f"symbolic links are not allowed for assets: {vault_path}")
        return safe_vault_path(self._vault_root, vault_path)

    def load(self) -> AssetManifestSnapshot:
        try:
            path = self.path
        except VaultPathError:
            return AssetManifestSnapshot(
                exists=False,
                assets=[],
                diagnostics=[_manifest_diagnostic("unsafe-vault-asset-manifest")],
            )
        if not path.exists():
            return AssetManifestSnapshot(exists=False, assets=[], diagnostics=[])
        if not path.is_file() or path.stat().st_size > _MAX_MANIFEST_BYTES:
            return AssetManifestSnapshot(
                exists=True,
                assets=[],
                diagnostics=[_manifest_diagnostic("invalid-vault-asset-manifest")],
            )

        yaml = YAML(typ="safe")
        try:
            payload = yaml.load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            # YAML parsers use several exception classes across ruamel versions.
            # Keep this read boundary diagnostic-only rather than leaking a parser error.
            return AssetManifestSnapshot(
                exists=True,
                assets=[],
                diagnostics=[
                    _manifest_diagnostic(
                        "invalid-vault-asset-manifest",
                        detail=type(exc).__name__,
                    )
                ],
            )
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("assets"), list)
        ):
            return AssetManifestSnapshot(
                exists=True,
                assets=[],
                diagnostics=[_manifest_diagnostic("invalid-vault-asset-manifest")],
            )

        assets: list[HubAsset] = []
        diagnostics: list[CatalogDiagnostic] = []
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        for row in payload["assets"]:
            entity_id = row.get("asset_id") if isinstance(row, Mapping) else None
            try:
                asset = HubAsset.model_validate(row)
            except ValidationError:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="warning",
                        code="invalid-vault-asset",
                        message="Ignored an invalid entry in the Vault asset manifest.",
                        entity_id=entity_id if isinstance(entity_id, str) else None,
                    )
                )
                continue
            if asset.asset_id in seen_ids:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="error",
                        code="duplicate-vault-asset-id",
                        message="One Vault asset ID is declared more than once.",
                        entity_id=asset.asset_id,
                    )
                )
                continue
            if asset.vault_path in seen_paths:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="error",
                        code="duplicate-vault-asset-path",
                        message="One Vault asset path is declared more than once.",
                        entity_id=asset.asset_id,
                    )
                )
                continue
            seen_ids.add(asset.asset_id)
            seen_paths.add(asset.vault_path)
            assets.append(asset)
        return AssetManifestSnapshot(
            exists=True,
            assets=assets,
            diagnostics=diagnostics,
        )

    def save(self, assets: list[HubAsset]) -> None:
        _validate_unique_assets(assets)
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.indent(mapping=2, sequence=4, offset=2)
        payload = {
            "schema_version": 1,
            "assets": [
                asset.model_dump(mode="json")
                for asset in sorted(assets, key=lambda item: item.asset_id)
            ],
        }
        buffer = StringIO()
        yaml.dump(payload, buffer)
        _atomic_write_text(path, buffer.getvalue())


class VaultAssetCatalogProvider:
    """Overlay only manifest-declared Vault assets onto a base catalog."""

    def __init__(
        self,
        catalog: CatalogProvider,
        manifest_store: VaultAssetManifestStore,
    ) -> None:
        self._catalog = catalog
        self._manifest_store = manifest_store
        self._fingerprints: dict[str, tuple[int, int, str]] = {}

    def load(self) -> HubCatalog:
        catalog = self._catalog.load()
        snapshot = self._manifest_store.load()
        diagnostics = [*catalog.diagnostics, *snapshot.diagnostics]
        known_artifacts = {artifact.artifact_id for artifact in catalog.artifacts}
        assets: list[HubAsset] = []
        for asset in snapshot.assets:
            missing = sorted(set(asset.owner_artifact_ids) - known_artifacts)
            if missing:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="warning",
                        code="dangling-vault-asset-owner",
                        message=(
                            "Ignored a Vault asset whose owner artifact is not in "
                            "HubCatalog."
                        ),
                        entity_id=asset.asset_id,
                    )
                )
                continue
            try:
                _verified_asset_path(
                    self._manifest_store,
                    asset,
                    fingerprint_cache=self._fingerprints,
                )
            except AssetIntegrityError as exc:
                diagnostics.append(
                    CatalogDiagnostic(
                        level="warning",
                        code=exc.code,
                        message=str(exc),
                        entity_id=asset.asset_id,
                    )
                )
                continue
            assets.append(asset)

        sources = {row.source: row for row in catalog.sources}
        sources["vault-asset-manifest"] = SourceStatus(
            source="vault-asset-manifest",
            available=snapshot.exists,
            detail="explicit manifest only; Markdown bodies and embeds are not parsed",
        )
        return HubCatalog(
            generated_at=catalog.generated_at,
            sources=list(sources.values()),
            resources=catalog.resources,
            topics=catalog.topics,
            artifacts=catalog.artifacts,
            assets=assets,
            diagnostics=diagnostics,
        )


class VaultAssetStore:
    """Add files under a server-derived Vault path and update the manifest.

    This first contract intentionally exposes no replace, move, or delete method.
    """

    def __init__(
        self,
        vault_root: Path,
        catalog: CatalogProvider,
        *,
        manifest_store: VaultAssetManifestStore | None = None,
        max_bytes: int = DEFAULT_MAX_ASSET_BYTES,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._vault_root = Path(vault_root)
        self._catalog = catalog
        self._manifest = manifest_store or VaultAssetManifestStore(self._vault_root)
        self._max_bytes = max_bytes
        self._id_factory = id_factory or (lambda: f"asset:{uuid.uuid4().hex}")
        self._lock = threading.RLock()

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def get(self, asset_id: str) -> HubAsset:
        """Return one currently valid asset by opaque ID, never by client path."""
        asset, _path = self._registered_asset(asset_id)
        return asset

    def resolve_path(self, asset_id: str) -> Path:
        """Resolve one registered, integrity-checked asset inside the Vault."""
        _asset, path = self._registered_asset(asset_id)
        return path

    def add_bytes(
        self,
        owner_artifact_id: str,
        display_name: str,
        content: bytes,
        *,
        role: AssetRole = AssetRole.SUPPLEMENT,
    ) -> HubAsset:
        if len(content) > self._max_bytes:
            raise ValueError("asset is too large")
        return self._add_stream(
            owner_artifact_id,
            display_name,
            io.BytesIO(content),
            role=role,
        )

    def add_file(
        self,
        owner_artifact_id: str,
        source_path: Path,
        *,
        display_name: str | None = None,
        role: AssetRole = AssetRole.SUPPLEMENT,
    ) -> HubAsset:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError("asset source file does not exist")
        if source.stat().st_size > self._max_bytes:
            raise ValueError("asset is too large")
        with source.open("rb") as handle:
            return self._add_stream(
                owner_artifact_id,
                display_name or source.name,
                handle,
                role=role,
            )

    def list_for_artifact(self, artifact_id: str) -> list[HubAsset]:
        snapshot = self._manifest.load()
        if snapshot.diagnostics:
            raise AssetManifestError("cannot read an invalid manifest")
        return [
            asset
            for asset in snapshot.assets
            if artifact_id in asset.owner_artifact_ids
        ]

    def _add_stream(
        self,
        owner_artifact_id: str,
        display_name: str,
        stream: BinaryIO,
        *,
        role: AssetRole,
    ) -> HubAsset:
        name = _normalize_asset_name(display_name)
        with self._lock:
            catalog = self._catalog.load()
            known_artifacts = {artifact.artifact_id for artifact in catalog.artifacts}
            if owner_artifact_id not in known_artifacts:
                raise KeyError(f"unknown Hub artifact: {owner_artifact_id}")
            snapshot = self._manifest.load()
            if snapshot.diagnostics:
                raise AssetManifestError("cannot update an invalid manifest")
            for existing in snapshot.assets:
                if any(owner not in known_artifacts for owner in existing.owner_artifact_ids):
                    raise AssetManifestError("cannot update a manifest with dangling owners")

            if not self._vault_root.is_dir():
                raise FileNotFoundError("Vault root does not exist")
            folder_rel = Path("attachments") / _owner_directory(owner_artifact_id)
            folder = safe_vault_path(self._vault_root, folder_rel)
            folder.mkdir(parents=True, exist_ok=True)
            destination, size, digest = self._store_stream(folder, name, stream)
            try:
                relative_path = destination.relative_to(self._vault_root.resolve()).as_posix()
                asset = HubAsset(
                    asset_id=self._next_asset_id(snapshot.assets),
                    owner_artifact_ids=[owner_artifact_id],
                    vault_path=relative_path,
                    display_name=destination.name,
                    media_type=(
                        mimetypes.guess_type(destination.name)[0]
                        or "application/octet-stream"
                    ),
                    size=size,
                    sha256=f"sha256:{digest}",
                    role=role,
                )
                self._manifest.save([*snapshot.assets, asset])
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            return asset

    def _registered_asset(self, asset_id: str) -> tuple[HubAsset, Path]:
        snapshot = self._manifest.load()
        if snapshot.diagnostics:
            raise AssetManifestError("cannot read an invalid manifest")
        asset = next(
            (candidate for candidate in snapshot.assets if candidate.asset_id == asset_id),
            None,
        )
        if asset is None:
            raise UnknownAssetError(asset_id)
        known_artifacts = {
            artifact.artifact_id for artifact in self._catalog.load().artifacts
        }
        if any(owner not in known_artifacts for owner in asset.owner_artifact_ids):
            raise AssetIntegrityError(
                "dangling-vault-asset-owner",
                "Vault asset owner is not in the current HubCatalog.",
            )
        return asset, _verified_asset_path(self._manifest, asset)

    def _store_stream(
        self,
        folder: Path,
        name: str,
        stream: BinaryIO,
    ) -> tuple[Path, int, str]:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".scholar-asset-",
            suffix=".part",
            dir=folder,
        )
        temporary = Path(temporary_name)
        size = 0
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, "wb") as handle:
                while True:
                    chunk = stream.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise ValueError("asset is too large")
                    handle.write(chunk)
                    digest.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            suffix_index = 1
            while True:
                candidate_name = name if suffix_index == 1 else _suffixed_name(name, suffix_index)
                destination = safe_vault_path(
                    self._vault_root,
                    folder.relative_to(self._vault_root.resolve()) / candidate_name,
                )
                try:
                    os.link(temporary, destination, follow_symlinks=False)
                except FileExistsError:
                    suffix_index += 1
                    continue
                temporary.unlink()
                return destination, size, digest.hexdigest()
        finally:
            temporary.unlink(missing_ok=True)

    def _next_asset_id(self, existing: list[HubAsset]) -> str:
        known = {asset.asset_id for asset in existing}
        for _ in range(16):
            candidate = self._id_factory()
            if candidate not in known:
                return candidate
        raise AssetManifestError("asset ID generator repeatedly returned duplicates")


def _normalize_asset_name(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidAssetNameError("asset name must be text")
    name = unicodedata.normalize("NFC", value)
    try:
        # Reuse the canonical contract validation without inventing a second rule set.
        HubAsset(
            asset_id="validation",
            owner_artifact_ids=["validation"],
            vault_path=f"attachments/validation/{name}",
            display_name=name,
            media_type="application/octet-stream",
            size=0,
            sha256="sha256:" + "0" * 64,
            role=AssetRole.SUPPLEMENT,
        )
    except ValidationError as exc:
        raise InvalidAssetNameError("asset name must be one visible filename") from exc
    if len(name.encode("utf-8")) > 240:
        raise InvalidAssetNameError("asset name is too long")
    return name


def _owner_directory(owner_artifact_id: str) -> str:
    normalized = unicodedata.normalize("NFKC", owner_artifact_id)
    characters: list[str] = []
    pending_dash = False
    for char in normalized:
        if char.isalnum() or char in {"-", "_"}:
            if pending_dash and characters:
                characters.append("-")
            characters.append(char.lower())
            pending_dash = False
        else:
            pending_dash = True
    slug = "".join(characters).strip("-_")[:48] or "artifact"
    short_hash = hashlib.sha256(owner_artifact_id.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{short_hash}"


def _suffixed_name(name: str, index: int) -> str:
    path = Path(name)
    return f"{path.stem}-{index}{path.suffix}"


def _validate_unique_assets(assets: list[HubAsset]) -> None:
    ids: set[str] = set()
    paths: set[str] = set()
    for asset in assets:
        if asset.asset_id in ids:
            raise AssetManifestError(f"duplicate asset ID: {asset.asset_id}")
        if asset.vault_path in paths:
            raise AssetManifestError(f"duplicate asset path: {asset.vault_path}")
        ids.add(asset.asset_id)
        paths.add(asset.vault_path)


def _verified_asset_path(
    manifest_store: VaultAssetManifestStore,
    asset: HubAsset,
    *,
    fingerprint_cache: dict[str, tuple[int, int, str]] | None = None,
) -> Path:
    try:
        path = manifest_store.resolve_asset_path(asset.vault_path)
    except VaultPathError as exc:
        raise AssetIntegrityError(
            "unsafe-vault-asset-path",
            "Ignored a Vault asset whose path escaped the Vault or used a symlink.",
        ) from exc
    if not path.is_file():
        raise AssetIntegrityError(
            "missing-vault-asset-file",
            "Ignored a Vault asset whose file is missing.",
        )
    stat_result = path.stat(follow_symlinks=False)
    if stat_result.st_size != asset.size:
        raise AssetIntegrityError(
            "vault-asset-size-drift",
            "Ignored a Vault asset whose byte size no longer matches its manifest.",
        )
    cache_key = asset.vault_path
    fingerprint = None if fingerprint_cache is None else fingerprint_cache.get(cache_key)
    if (
        fingerprint is None
        or fingerprint[0] != stat_result.st_size
        or fingerprint[1] != stat_result.st_mtime_ns
    ):
        actual_sha256 = _sha256_path(path)
        if fingerprint_cache is not None:
            fingerprint_cache[cache_key] = (
                stat_result.st_size,
                stat_result.st_mtime_ns,
                actual_sha256,
            )
    else:
        actual_sha256 = fingerprint[2]
    if f"sha256:{actual_sha256}" != asset.sha256:
        raise AssetIntegrityError(
            "vault-asset-hash-drift",
            "Ignored a Vault asset whose content hash no longer matches its manifest.",
        )
    return path


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_diagnostic(code: str, *, detail: str | None = None) -> CatalogDiagnostic:
    message = "Ignored an invalid Vault asset manifest."
    if detail:
        message = f"{message} Parser detail: {detail}."
    return CatalogDiagnostic(
        level="warning",
        code=code,
        message=message,
        entity_id=None,
    )


__all__ = [
    "ASSET_MANIFEST_PATH",
    "AssetIntegrityError",
    "AssetManifestError",
    "AssetManifestSnapshot",
    "DEFAULT_MAX_ASSET_BYTES",
    "InvalidAssetNameError",
    "UnknownAssetError",
    "VaultAssetCatalogProvider",
    "VaultAssetManifestStore",
    "VaultAssetStore",
]
