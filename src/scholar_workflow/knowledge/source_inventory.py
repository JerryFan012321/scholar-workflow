"""The bound empty inventory member of a genuinely new Source transaction.

This module never publishes a Source registration or repairs a lost inventory.
The caller owns the registry lock, approval and recovery journal.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from scholar_workflow.knowledge.fields import (
    _DIRECTORY_FLAGS,
    _canonical_uuid,
    _open_directory_chain,
    _read_regular_at,
)

SNAPSHOT = "knowledge-provider.snapshot.json"


def _directory(path: Path) -> int:
    value = path.absolute()
    return _open_directory_chain(Path(value.anchor), value.parts[1:])


def empty_source_inventory(root: Path):
    """Keep the existing deterministic first-Source representation."""
    from scholar_workflow.analysis.apply_changes import (
        KnowledgeProviderSnapshot,
        _vault_binding_for_root,
    )
    from scholar_workflow.knowledge.catalog_models import HubCatalog
    from scholar_workflow.knowledge.models import KnowledgeManifest

    return KnowledgeProviderSnapshot(
        vault_binding=_vault_binding_for_root(root), manifest=KnowledgeManifest(),
        catalog=HubCatalog(generated_at=datetime(1970, 1, 1, tzinfo=UTC)),
    )


def _bytes(root: Path) -> bytes:
    return (json.dumps(empty_source_inventory(root).model_dump(mode="json"),
                       ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def inventory_path(registry_path: Path, source_id: str) -> Path:
    source_id = _canonical_uuid(source_id, name="source_id")
    return registry_path.parent / "knowledge-providers" / source_id


def initialization_spec(source_id: str, root: Path) -> dict:
    return {"schema_version": 1, "kind": "new-empty-provider",
            "source_id": _canonical_uuid(source_id, name="source_id"),
            "snapshot_sha256": "sha256:" + hashlib.sha256(_bytes(root)).hexdigest()}


def assert_inventory_absent(registry_path: Path, source_id: str) -> None:
    """Check without creating a host directory or following symlink ancestors."""
    path = inventory_path(registry_path, source_id)
    try:
        fd = _directory(path.parent)
    except FileNotFoundError:
        return
    try:
        try:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ValueError("New Source inventory location already exists; refusing adoption")
    finally:
        os.close(fd)


def create_inventory(registry_path: Path, source_id: str, root: Path, spec: dict) -> None:
    """Publish the inventory before registry publication, after the journal."""
    from scholar_workflow.analysis.apply_changes import _atomic_create

    if spec != initialization_spec(source_id, root):
        raise ValueError("Source inventory initialization differs from the approved binding")
    assert_inventory_absent(registry_path, source_id)
    fd = _directory(registry_path.parent)
    try:
        for part in ("knowledge-providers", source_id):
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
                os.fsync(fd)
            except FileExistsError:
                if part == source_id:
                    raise ValueError("New Source inventory appeared during publication") from None
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
            metadata = os.fstat(child)
            if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
                os.close(child)
                raise ValueError("Source inventory directory must be private")
            os.close(fd)
            fd = child
        _atomic_create(fd, SNAPSHOT, _bytes(root))
        payload, _ = _read_regular_at(fd, SNAPSHOT, limit=2 * 1024 * 1024)
        if payload != _bytes(root):
            raise ValueError("Source inventory changed during initialization")
    finally:
        os.close(fd)


def verify_initialization(
    registry_path: Path, source_id: str, root: Path, spec: dict, *, published: bool,
) -> None:
    """Validate recovery; never replace unknown, populated or lost state."""
    from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot

    if spec != initialization_spec(source_id, root):
        raise ValueError("Source inventory recovery binding differs from its journal")
    path = inventory_path(registry_path, source_id)
    try:
        fd = _directory(path)
        try:
            payload, _ = _read_regular_at(fd, SNAPSHOT, limit=16 * 1024 * 1024)
        finally:
            os.close(fd)
    except FileNotFoundError:
        if published:
            raise ValueError("Published Source inventory is missing; restore it, never infer empty") from None
        return
    snapshot = KnowledgeProviderSnapshot.model_validate_json(payload)
    if snapshot.vault_binding != empty_source_inventory(root).vault_binding:
        raise ValueError("Source inventory belongs to another root")
    if not published and payload != _bytes(root):
        raise ValueError("Unpublished Source inventory changed; retain it for explicit review")
