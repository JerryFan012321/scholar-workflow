"""Read-only, explicit batch plan for flat Field paper-note relocation.

The caller supplies every paper identity and destination. This planner never
infers a resource from a title, never writes a Vault file, and does not grant
approval to the joint Field/provider transaction. In particular, legacy Hub
links require a separate Zotero Local API-backed resolver.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from scholar_workflow.hub.field_migration import (
    _LEGACY_LINK,
    _RAW_LEGACY_HUB,
    _has_analysis_identity,
)
from scholar_workflow.hub.field_transaction import _has_analysis_sidecar
from scholar_workflow.hub.fields import FieldDefinition, _open_directory_chain, _safe_relative

_SEGMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
_RESOURCE_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{1,127}\Z")
_TEXT_SUFFIXES = {".md", ".canvas", ".json", ".txt", ".html", ".yml", ".yaml", ".ipynb"}
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_FILES = 2048
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class PaperFolderingError(ValueError):
    """A batch paper-folder proposal is unsafe or unresolved."""


@dataclass(frozen=True)
class PaperFolderRelocation:
    """Caller-reviewed, Field-relative identity mapping for one flat owner note."""

    source_note: str
    resource_id: str
    destination_note: str


@dataclass(frozen=True)
class PaperFolderMove:
    resource_id: str
    stable_segment: str
    old_path: str  # Vault-relative
    new_path: str  # Vault-relative
    before_sha256: str
    before_device: int
    before_inode: int
    after_sha256: str
    destination_absent: bool


@dataclass(frozen=True)
class PaperFolderNavigationChange:
    location: str
    old_path: str  # Field-relative
    new_path: str  # Field-relative


@dataclass(frozen=True)
class PaperFolderLinkChange:
    document_path: str  # Vault-relative source path
    old_text: str
    new_text: str
    occurrences: int
    kind: str


@dataclass(frozen=True)
class PaperFolderDocument:
    """Exact candidate bytes; for a moved note, output_path is the new path."""

    source_path: str  # Vault-relative
    output_path: str  # Vault-relative
    before_sha256: str
    before_device: int
    before_inode: int
    after_sha256: str
    after_bytes: bytes


@dataclass(frozen=True)
class PaperFolderingPlan:
    vault_root: Path
    vault_device: int
    vault_inode: int
    field_id: str
    plan_digest: str
    moves: tuple[PaperFolderMove, ...]
    proposed_field: FieldDefinition
    navigation_changes: tuple[PaperFolderNavigationChange, ...]
    missing_navigation_targets: tuple[str, ...]  # Field-relative, unchanged
    link_changes: tuple[PaperFolderLinkChange, ...]
    documents: tuple[PaperFolderDocument, ...]
    legacy_link_count: int
    read_only: bool = True
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class _ObservedFile:
    content: bytes
    device: int
    inode: int

    @property
    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.content).hexdigest()


def _canonical_field_path(value: str) -> str:
    try:
        result = _safe_relative(value)
    except ValueError as exc:
        raise PaperFolderingError("paper note path is not a safe relative path") from exc
    if result != value or any(part.startswith(".") for part in PurePosixPath(result).parts):
        raise PaperFolderingError("paper note path is not canonical or enters hidden state")
    return result


def _vault_path(field: FieldDefinition, relative: str) -> str:
    if field.relative_root == ".":
        return relative
    return f"{field.relative_root}/{relative}"


def _root_identity(path: Path) -> tuple[int, int]:
    if not path.is_absolute() or path != Path(os.path.abspath(path)):
        raise PaperFolderingError("Vault root must be an absolute canonical path")
    try:
        descriptor = _open_directory_chain(Path(path.anchor), path.parts[1:])
    except OSError as exc:
        raise PaperFolderingError("Vault root is unavailable or has a symbolic-link ancestor") from exc
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid():
            raise PaperFolderingError("Vault root is not owned by the current user")
        return info.st_dev, info.st_ino
    finally:
        os.close(descriptor)


def _read(root: Path, relative: str) -> _ObservedFile:
    parts = PurePosixPath(relative).parts
    try:
        parent = _open_directory_chain(root, parts[:-1])
    except OSError as exc:
        raise PaperFolderingError(f"source parent is missing or unsafe: {relative}") from exc
    try:
        try:
            descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent)
        except OSError as exc:
            raise PaperFolderingError(f"source file is missing or unsafe: {relative}") from exc
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or info.st_size > _MAX_FILE_BYTES
            ):
                raise PaperFolderingError(f"source is not a singly owned bounded file: {relative}")
            data = bytearray()
            while chunk := os.read(descriptor, 1024 * 1024):
                data.extend(chunk)
                if len(data) > _MAX_FILE_BYTES:
                    raise PaperFolderingError(f"source exceeds read limit: {relative}")
            return _ObservedFile(bytes(data), info.st_dev, info.st_ino)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def _require_absent(root: Path, relative: str) -> None:
    parts = PurePosixPath(relative).parts
    descriptor = _open_directory_chain(root)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                return
            except OSError as exc:
                raise PaperFolderingError(f"destination parent is unsafe: {relative}") from exc
            os.close(descriptor)
            descriptor = child
        try:
            os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise PaperFolderingError(f"paper note destination already exists: {relative}")
    finally:
        os.close(descriptor)


def _inventory(root: Path, field: FieldDefinition) -> dict[str, _ObservedFile]:
    base = root if field.relative_root == "." else root / field.relative_root
    _root_identity(base)
    found: dict[str, _ObservedFile] = {}
    total_bytes = 0
    for directory, dirs, files in os.walk(base, followlinks=False):
        current = Path(directory)
        for name in list(dirs):
            if name.startswith("."):
                dirs.remove(name)
            elif (current / name).is_symlink():
                raise PaperFolderingError(f"Field inventory has a symbolic-link directory: {name}")
        for name in files:
            if name.startswith("."):
                continue
            item = current / name
            if item.is_symlink():
                raise PaperFolderingError(f"Field inventory has a symbolic-link file: {name}")
            if item.suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            relative = item.relative_to(root).as_posix()
            found[relative] = _read(root, relative)
            total_bytes += len(found[relative].content)
            if len(found) > _MAX_FILES or total_bytes > _MAX_TOTAL_BYTES:
                raise PaperFolderingError("Field inventory exceeds read-only planning limits")
    return found


def _resolve_links(
    content: bytes,
    *,
    relative: str,
    resolver: Callable[[str], str] | None,
) -> tuple[bytes, tuple[PaperFolderLinkChange, ...]]:
    counts: dict[str, int] = {}
    for match in _LEGACY_LINK.finditer(content):
        key = match.group("key").decode("ascii")
        counts[key] = counts.get(key, 0) + 1
    if counts and resolver is None:
        raise PaperFolderingError(f"legacy PDF links require a validated resolver: {relative}")
    replacements: dict[str, bytes] = {}
    for key in sorted(counts):
        try:
            replacement = resolver(key) if resolver is not None else None
        except Exception as exc:
            raise PaperFolderingError(f"legacy PDF link cannot be verified: {key}") from exc
        expected = f"zotero://open-pdf/library/items/{key}"
        if replacement != expected:
            raise PaperFolderingError(f"legacy PDF resolver returned an unapproved URI: {key}")
        replacements[key] = expected.encode("ascii")
    after = _LEGACY_LINK.sub(lambda match: replacements[match.group("key").decode("ascii")], content)
    if _RAW_LEGACY_HUB.search(after):
        raise PaperFolderingError(f"unresolved legacy Hub URL remains: {relative}")
    changes = tuple(
        PaperFolderLinkChange(relative, f"http://127.0.0.1:23128/open/paper/{key}",
                              replacements[key].decode("ascii"), count, "verified-pdf")
        for key, count in sorted(counts.items())
    )
    return after, changes


def plan_paper_foldering(
    *,
    vault_root: Path,
    field: FieldDefinition,
    relocations: Sequence[PaperFolderRelocation],
    legacy_link_resolver: Callable[[str], str] | None = None,
) -> PaperFolderingPlan:
    """Prepare exact bytes and receipts for review, without changing the Vault.

    The joint transaction must separately validate the provider graph and all
    analysis bundles before using these proposed bytes. Missing navigation
    targets are retained and reported; they are never synthesized here.
    """
    root = Path(vault_root)
    root_device, root_inode = _root_identity(root)
    field = FieldDefinition.model_validate(field)
    if not relocations:
        raise PaperFolderingError("at least one explicit paper relocation is required")
    inventory = _inventory(root, field)
    old_to_new: dict[str, str] = {}
    identities: dict[str, str] = {}
    segments: set[str] = set()
    destination_paths: set[str] = set()
    moves: list[PaperFolderMove] = []
    for item in relocations:
        old = _canonical_field_path(item.source_note)
        new = _canonical_field_path(item.destination_note)
        if PurePosixPath(old).parent != PurePosixPath("paper_assets") or (
            PurePosixPath(old).suffix.casefold() != ".md"
        ):
            raise PaperFolderingError("source must be a flat paper_assets Markdown note")
        parts = PurePosixPath(new).parts
        if len(parts) != 4 or parts[:2] != ("resources", "papers") or (
            PurePosixPath(new).suffix.casefold() != ".md"
        ):
            raise PaperFolderingError("destination must be resources/papers/<segment>/<note>.md")
        segment = parts[2]
        if not _SEGMENT.fullmatch(segment):
            raise PaperFolderingError("paper folder segment is not a stable portable segment")
        if not _RESOURCE_ID.fullmatch(item.resource_id):
            raise PaperFolderingError("resource ID must be a stable portable identity")
        if old in old_to_new or item.resource_id in identities or segment.casefold() in segments or (
            new.casefold() in destination_paths
        ):
            raise PaperFolderingError("duplicate source, resource ID, segment, or destination")
        old_to_new[old] = new
        identities[item.resource_id] = old
        segments.add(segment.casefold())
        destination_paths.add(new.casefold())
        source_path = _vault_path(field, old)
        destination_path = _vault_path(field, new)
        source = inventory.get(source_path)
        if source is None:
            raise PaperFolderingError(f"paper source is absent: {source_path}")
        if _has_analysis_identity(source.content) or _has_analysis_sidecar(root, source_path):
            raise PaperFolderingError(
                f"managed analysis cannot be relocated as a plain owner note: {source_path}"
            )
        _require_absent(root, destination_path)
        moves.append(PaperFolderMove(item.resource_id, segment, source_path,
                                     destination_path, source.sha256, source.device,
                                     source.inode, source.sha256, True))
    flat_parent = PurePosixPath(_vault_path(field, "paper_assets"))
    flat_notes = {
        path for path in inventory
        if PurePosixPath(path).parent == flat_parent
        and PurePosixPath(path).suffix.casefold() == ".md"
    }
    reviewed_notes = {row.old_path for row in moves}
    if flat_notes != reviewed_notes:
        missing = sorted(flat_notes - reviewed_notes)
        raise PaperFolderingError(
            f"flat paper note inventory is incomplete: {', '.join(missing)}"
        )
    for old in old_to_new:
        if any(old != other and old.encode() in other.encode() for other in old_to_new):
            raise PaperFolderingError("paper source paths overlap as literal link targets")
    move_by_old = {row.old_path: row for row in moves}
    navigation_changes: list[PaperFolderNavigationChange] = []

    def replace_nav(path: str, location: str) -> str:
        new = old_to_new.get(path)
        if new is not None:
            navigation_changes.append(PaperFolderNavigationChange(location, path, new))
            return new
        return path

    proposed_data = field.model_dump(mode="json")
    proposed_data["home"] = replace_nav(field.home, "home")
    for group_index, group in enumerate(proposed_data["navigation"]):
        group["items"] = [
            replace_nav(path, f"navigation[{group_index}].items[{item_index}]")
            for item_index, path in enumerate(group["items"])
        ]
    proposed_field = FieldDefinition.model_validate(proposed_data)
    listed = [field.home, *(path for group in field.navigation for path in group.items)]
    missing_navigation_targets = tuple(dict.fromkeys(
        path for path in listed
        if path not in old_to_new and _vault_path(field, path) not in inventory
    ))
    link_changes: list[PaperFolderLinkChange] = []
    documents: list[PaperFolderDocument] = []
    total_legacy = 0
    for path, original in sorted(inventory.items()):
        candidate = original.content
        if path.endswith(".md"):
            for old, new in sorted(old_to_new.items()):
                count = candidate.count(old.encode("utf-8"))
                if count:
                    candidate = candidate.replace(old.encode("utf-8"), new.encode("utf-8"))
                    link_changes.append(PaperFolderLinkChange(path, old, new, count,
                                                               "literal-paper-path"))
        candidate, pdf_changes = _resolve_links(
            candidate, relative=path, resolver=legacy_link_resolver,
        )
        link_changes.extend(pdf_changes)
        total_legacy += sum(change.occurrences for change in pdf_changes)
        moved = move_by_old.get(path)
        if moved is not None or candidate != original.content:
            if not path.endswith(".md") or _has_analysis_identity(original.content) or (
                _has_analysis_sidecar(root, path)
            ):
                raise PaperFolderingError(
                    f"structured or managed document needs its own validated bundle: {path}"
                )
            output_path = moved.new_path if moved is not None else path
            after_sha = "sha256:" + hashlib.sha256(candidate).hexdigest()
            documents.append(PaperFolderDocument(path, output_path, original.sha256,
                                                 original.device, original.inode, after_sha,
                                                 candidate))
            if moved is not None:
                moves[moves.index(moved)] = PaperFolderMove(
                    moved.resource_id, moved.stable_segment, moved.old_path, moved.new_path,
                    moved.before_sha256, moved.before_device, moved.before_inode,
                    after_sha, True,
                )
    semantic = {
        "root": str(root), "root_device": root_device, "root_inode": root_inode,
        "field_id": field.field_id, "field_before": field.model_dump(mode="json"),
        "field_after": proposed_field.model_dump(mode="json"),
        "moves": [row.__dict__ for row in moves],
        "missing_navigation_targets": missing_navigation_targets,
        "links": [row.__dict__ for row in link_changes],
        "documents": [
            {key: value for key, value in row.__dict__.items() if key != "after_bytes"}
            for row in documents
        ],
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return PaperFolderingPlan(
        root, root_device, root_inode, field.field_id, digest, tuple(moves),
        proposed_field, tuple(navigation_changes), missing_navigation_targets,
        tuple(link_changes), tuple(documents), total_legacy,
    )


__all__ = [
    "PaperFolderDocument",
    "PaperFolderLinkChange",
    "PaperFolderMove",
    "PaperFolderNavigationChange",
    "PaperFolderRelocation",
    "PaperFolderingError",
    "PaperFolderingPlan",
    "plan_paper_foldering",
]
