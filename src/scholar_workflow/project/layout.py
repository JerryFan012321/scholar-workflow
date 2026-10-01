"""Shared, read-only Project System identity and layout contracts."""
from __future__ import annotations

import json
import os
import re
import stat
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_LAYOUT = "project-layout.json"
MAX_PROJECT_MANIFEST_BYTES = 1024 * 1024
_PACKAGE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
_DIRECTORY_FLAGS |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


class ProjectLayoutError(ValueError):
    """A project declaration is missing, malformed, or unsafe to read."""


def is_project_id(value: object) -> bool:
    """Recognize the accepted canonical UUIDv4 project identity."""
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def validate_project_identity(payload: object) -> str:
    """Check only schema/identity, not a complete layout or profile selection."""
    if not isinstance(payload, Mapping) or type(payload.get("schema_version")) is not int:
        raise ProjectLayoutError("project-layout.json must use schema_version 2")
    if payload["schema_version"] != 2:
        raise ProjectLayoutError("project-layout.json must use schema_version 2")
    identifier = payload.get("project_id")
    if not is_project_id(identifier):
        raise ProjectLayoutError("project-layout.json project_id must be a canonical UUIDv4")
    assert isinstance(identifier, str)
    return identifier


@dataclass(frozen=True)
class ProfileSelection:
    id: str
    version: int

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class ProjectLayout:
    """Schema 2; validation never selects or changes a source profile."""

    schema_version: int
    project_id: str
    language: str
    package: str | None
    source_profile: ProfileSelection | None
    addons: tuple[ProfileSelection, ...]

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "project_id": self.project_id,
            "language": self.language, "package": self.package,
            "source_profile": self.source_profile.model_dump() if self.source_profile else None,
            "addons": [row.model_dump() for row in self.addons],
        }


def _profile_selection(value: object, *, label: str) -> ProfileSelection:
    if not isinstance(value, dict) or set(value) != {"id", "version"}:
        raise ProjectLayoutError(f"project-layout.json has an unknown {label} or version")
    identifier, version = value["id"], value["version"]
    if (
        not isinstance(identifier, str) or re.fullmatch(r"[a-z][a-z0-9-]*", identifier) is None
        or type(version) is not int or version != 1
    ):
        raise ProjectLayoutError(f"project-layout.json has an unknown {label} or version")
    return ProfileSelection(id=identifier, version=version)


def validate_project_layout(
    payload: object, *, catalog: Mapping[str, Any] | None = None,
) -> ProjectLayout:
    """Validate the full layout, optionally against the initializer's catalog."""
    required = {"schema_version", "project_id", "language", "package", "source_profile", "addons"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ProjectLayoutError("project-layout.json has unknown or missing fields")
    validate_project_identity(payload)
    if payload["language"] != "python":
        raise ProjectLayoutError("project-layout.json language must be python")
    package = payload["package"]
    if package is not None and (not isinstance(package, str) or not _PACKAGE.fullmatch(package)):
        raise ProjectLayoutError("project-layout.json package is not a Python identifier")
    source_profile = (
        None if payload["source_profile"] is None
        else _profile_selection(payload["source_profile"], label="source profile")
    )
    if not isinstance(payload["addons"], list):
        raise ProjectLayoutError("project-layout.json addons must be a list")
    addons = tuple(_profile_selection(value, label="addon") for value in payload["addons"])
    addon_ids = [row.id for row in addons]
    if addon_ids != sorted(set(addon_ids)):
        raise ProjectLayoutError("project-layout.json addons must be unique and sorted by id")
    if (source_profile is not None or addons) and package is None:
        raise ProjectLayoutError("project-layout.json requires package with a profile or addon")
    layout = ProjectLayout(
        schema_version=2, project_id=payload["project_id"], language="python", package=package,
        source_profile=source_profile, addons=addons,
    )
    if catalog is not None:
        if layout.source_profile is not None:
            profile = catalog.get("profiles", {}).get(layout.source_profile.id)
            if not isinstance(profile, Mapping) or profile.get("version") != layout.source_profile.version:
                raise ProjectLayoutError("project-layout.json has an unknown source profile or version")
        for addon in layout.addons:
            definition = catalog.get("addons", {}).get(addon.id)
            if not isinstance(definition, Mapping) or definition.get("version") != addon.version:
                raise ProjectLayoutError("project-layout.json has an unknown addon or version")
    return layout


@contextmanager
def open_project_root(root: str | Path) -> Iterator[int]:
    """Pin the explicit root; reject a symlink root and descriptor-walk its canonical parents."""
    selected = Path(os.path.abspath(Path(root).expanduser()))
    descriptor: int | None = None
    try:
        if selected.is_symlink():
            raise ProjectLayoutError("Project root cannot be a symlink")
        path = selected.parent.resolve(strict=True) / selected.name
        descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
        for component in path.parts[1:]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    except OSError as exc:
        raise ProjectLayoutError("Project root is unavailable or contains a symlink") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectLayoutError("Project declaration contains duplicate JSON fields")
        result[key] = value
    return result


def read_project_json(root: str | Path, filename: str) -> object:
    """Read a bounded root-level declaration; never discover other files."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*\.json", filename):
        raise ProjectLayoutError("Project declaration must be a root-level JSON filename")
    with open_project_root(root) as root_fd:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(filename, flags, dir_fd=root_fd)
        except OSError as exc:
            raise ProjectLayoutError(f"{filename} is missing or unsafe") from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PROJECT_MANIFEST_BYTES:
                raise ProjectLayoutError(f"{filename} must be a bounded regular file")
            chunks: list[bytes] = []
            size = 0
            while chunk := os.read(descriptor, 65536):
                size += len(chunk)
                if size > MAX_PROJECT_MANIFEST_BYTES:
                    raise ProjectLayoutError(f"{filename} exceeds its size limit")
                chunks.append(chunk)
            current = os.stat(filename, dir_fd=root_fd, follow_symlinks=False)
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ) or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                raise ProjectLayoutError(f"{filename} changed while it was read")
            return json.loads(b"".join(chunks), object_pairs_hook=_unique_json_object)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectLayoutError(f"{filename} is malformed or changed while reading") from exc
        finally:
            os.close(descriptor)


def load_project_identity(root: str | Path) -> str:
    """Read only the established schema/identity guard from a project root."""
    return validate_project_identity(read_project_json(root, PROJECT_LAYOUT))


def load_project_layout(root: str | Path) -> ProjectLayout:
    return validate_project_layout(read_project_json(root, PROJECT_LAYOUT))
