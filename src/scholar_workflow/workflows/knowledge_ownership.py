"""Compose registered declarations into read-only project ownership checks.

This workflow reuses the existing provider validator without moving its legacy
storage or making Knowledge core depend on analysis. It creates no state, locks,
catalog, reader session, or new authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
    _open_directory_chain,
)
from scholar_workflow.knowledge.ownership import (
    KnowledgeOwnerLocation,
    KnowledgeOwnershipIssue,
    KnowledgeOwnershipResolution,
    resolve_declared_ownership,
)
from scholar_workflow.project.context import ExternalResourceRef, ProjectOverview

_READ_FLAGS = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
               | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
_SNAPSHOT = "knowledge-provider.snapshot.json"


@dataclass(frozen=True)
class _Declaration:
    root: Path
    relative_path: str
    limit: int
    content: bytes
    identity: tuple[int, ...]


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_checked_chain(root: Path, parts: tuple[str, ...] = ()) -> int:
    """Pin the absolute root's ancestors too, not just its final component."""
    absolute = root.absolute()
    if ".." in absolute.parts or any(part in {".", ".."} for part in parts):
        raise ValueError("Registered paths must not contain parent traversal")
    return _open_directory_chain(Path(absolute.anchor), absolute.parts[1:] + parts)


def _root_identity(root: Path) -> tuple[int, int]:
    descriptor = _open_checked_chain(root)
    try:
        info = os.fstat(descriptor)
        return info.st_dev, info.st_ino
    finally:
        os.close(descriptor)


def _read_declaration(root: Path, relative_path: str, limit: int) -> _Declaration:
    """Pin ancestors and leaf, bound reads, and reject replacement during a read."""
    parts = PurePosixPath(relative_path).parts
    if not parts or PurePosixPath(relative_path).is_absolute() or ".." in parts:
        raise ValueError("Declaration must have a safe relative path")
    parent = _open_checked_chain(root, parts[:-1])
    descriptor: int | None = None
    try:
        descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit
                or before.st_uid != os.getuid() or before.st_mode & 0o022):
            raise ValueError("Declaration is not a bounded regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(limit + 1)
        after = os.fstat(descriptor)
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (len(content) != before.st_size or _identity(before) != _identity(after)
                or _identity(after) != _identity(named) or stat.S_ISLNK(named.st_mode)):
            raise ValueError("Declaration changed during reading")
        # Re-opening the named chain also catches a replaced ancestor directory.
        check_parent = _open_checked_chain(root, parts[:-1])
        try:
            check = os.stat(parts[-1], dir_fd=check_parent, follow_symlinks=False)
            if _identity(check) != _identity(after):
                raise ValueError("Declaration ancestor changed during reading")
        finally:
            os.close(check_parent)
        return _Declaration(root, relative_path, limit, content, _identity(after))
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Declaration has duplicate JSON keys")
        result[key] = value
    return result


def _json(content: bytes) -> object:
    return json.loads(content.decode("utf-8"), object_pairs_hook=_unique_json)


class _UniqueYaml(yaml.SafeLoader):
    """Field declarations cannot silently override an earlier mapping member."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ValueError("Field declaration cannot contain aliases")
        return super().compose_node(parent, index)


def _yaml_mapping(loader: _UniqueYaml, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                None, None, "Field mapping keys must be strings", key_node.start_mark,
            )
        if key in mapping:
            raise ValueError("Field declaration has duplicate YAML keys")
        mapping[key] = loader.construct_object(value_node)
    return mapping


_UniqueYaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping)


def _file_state(root: Path, relative_path: str) -> str:
    """Check a declared file without reading its body or following a symlink."""
    descriptor: int | None = None
    parent: int | None = None
    try:
        path = PurePosixPath(relative_path)
        if (path.is_absolute() or relative_path != path.as_posix() or "\\" in relative_path
                or any(part in {".", ".."} or part.startswith(".") for part in path.parts)):
            return "unsafe"
        parent = _open_checked_chain(root, path.parts[:-1])
        descriptor = os.open(path.name, _READ_FLAGS, dir_fd=parent)
        info = os.fstat(descriptor)
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or _identity(info) != _identity(named):
            return "unsafe"
        current_parent = _open_checked_chain(root, path.parts[:-1])
        try:
            current = os.stat(path.name, dir_fd=current_parent, follow_symlinks=False)
            if _identity(info) != _identity(current):
                return "unsafe"
        finally:
            os.close(current_parent)
        return "available"
    except FileNotFoundError:
        return "missing"
    except (OSError, ValueError):
        return "unsafe"
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def _placements(
    source_id: str, manifest: FieldManifest, snapshot: KnowledgeProviderSnapshot,
) -> list[KnowledgeOwnerLocation]:
    primary = {
        **{row.resource_id: row.markdown_path for row in snapshot.manifest.atomic_resources},
        **{row.document_id: row.markdown_path for row in snapshot.manifest.core_documents},
    }
    objects = {key: (key, path) for key, path in primary.items()}
    objects.update({row.document_id: (row.owner_id, row.vault_path)
                    for row in snapshot.manifest.supporting_documents})
    # Sidecars need not appear in the human catalog, but retain their declared owner.
    for row in snapshot.artifacts:
        objects.setdefault(row.artifact_id, (row.resource_id, row.vault_path))
    result = []
    for object_id, (owner_id, path) in objects.items():
        owner_path = primary[owner_id]
        if any(value != value.strip() or any(ord(char) < 32 for char in value)
               for value in (path, owner_path)):
            raise ValueError("Object paths must be clean relative paths")
        fields = [field for field in manifest.fields if field.relative_root == "." or (
            owner_path.startswith(field.relative_root + "/")
            and path.startswith(field.relative_root + "/")
        )]
        if len(fields) != 1:
            raise ValueError("Object must belong to exactly one registered Field")
        field = fields[0]
        result.append(KnowledgeOwnerLocation(
            source_id=source_id, field_id=field.field_id, field_title=field.title,
            object_id=object_id, owner_id=owner_id, relative_path=path, owner_path=owner_path,
        ))
    return result


def resolve_project_knowledge(
    overview: ProjectOverview, registry_path: Path,
) -> dict[str, KnowledgeOwnershipResolution]:
    """Check selected Obsidian identities only; no filesystem discovery or writes."""
    entries = [entry for entry in overview.entries if isinstance(entry.ref, ExternalResourceRef)
               and entry.ref.provider == "obsidian"]
    if not entries:
        return {}
    wanted = {entry.ref.resource_id for entry in entries}
    locations: list[KnowledgeOwnerLocation] = []
    issues: list[KnowledgeOwnershipIssue] = []
    reads: list[tuple[str | None, _Declaration]] = []
    bindings: list[tuple[str, Path, tuple[int, int]]] = []
    roots: dict[str, Path] = {}
    registry = KnowledgeSourceRegistry(registry_path)

    def issue(source_id: str | None, code: str) -> None:
        issues.append(KnowledgeOwnershipIssue(source_id=source_id, code=code))

    try:
        read = _read_declaration(registry.path.parent, registry.path.name, 2 * 1024 * 1024)
        document = KnowledgeSourceRegistryDocument.model_validate(_json(read.content))
        reads.append((None, read))
    except (OSError, ValueError, RecursionError, FieldRegistryError):
        issue(None, "registry_unavailable")
        document = KnowledgeSourceRegistryDocument()

    for source in document.sources:
        folder = next(row for row in document.folders if row.folder_id == source.folder_id)
        if (not source.enabled or "read" not in source.capabilities
                or not folder.enabled or "read" not in folder.capabilities):
            issue(source.source_id, "source_disabled")
            continue
        try:
            root = folder.root
            root_identity = _root_identity(root)
            field_read = _read_declaration(root, ".scholar-workflow/fields.yml", 2 * 1024 * 1024)
            manifest = FieldManifest.model_validate(yaml.load(field_read.content, Loader=_UniqueYaml))
            if manifest.source_id != source.source_id:
                raise ValueError("Field manifest belongs to another Source")
            provider_relative = f"knowledge-providers/{source.source_id}/{_SNAPSHOT}"
            provider_read = _read_declaration(registry.path.parent, provider_relative, 16 * 1024 * 1024)
            snapshot = KnowledgeProviderSnapshot.model_validate(_json(provider_read.content))
            binding = snapshot.vault_binding
            if binding is None or (binding.root_path, binding.device, binding.inode) != (
                str(root), *root_identity,
            ):
                raise ValueError("Provider binding differs from the registered Source")
            current_identity = _root_identity(root)
            if current_identity != root_identity:
                raise ValueError("Source root changed during reading")
            locations.extend(_placements(source.source_id, manifest, snapshot))
            roots[source.source_id] = root
            bindings.append((source.source_id, root, current_identity))
            reads.extend(((source.source_id, field_read), (source.source_id, provider_read)))
        except (OSError, ValueError, KeyError, RecursionError, FieldRegistryError, yaml.YAMLError):
            issue(source.source_id, "source_declaration_unavailable")

    inspected = wanted | {row.owner_id for row in locations if row.object_id in wanted}
    locations = [row.model_copy(update={"file_state": _file_state(roots[row.source_id], row.relative_path)})
                 if row.object_id in inspected else row for row in locations]
    # Observe declarations again; no shared or exclusive write lock is created.
    for source_id, read in reads:
        try:
            current = _read_declaration(read.root, read.relative_path, read.limit)
            if (current.identity != read.identity
                    or hashlib.sha256(current.content).digest() != hashlib.sha256(read.content).digest()):
                issue(source_id, "declaration_changed")
        except (OSError, ValueError):
            issue(source_id, "declaration_changed")
    for source_id, root, expected in bindings:
        try:
            if _root_identity(root) != expected:
                issue(source_id, "source_binding_changed")
        except OSError:
            issue(source_id, "source_binding_changed")
    return {entry.entry_id: resolve_declared_ownership(entry.ref.resource_id, locations, issues)
            for entry in entries}
