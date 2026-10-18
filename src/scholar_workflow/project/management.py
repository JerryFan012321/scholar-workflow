"""Portable parent/child declarations, without placement or execution authority."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .layout import is_project_id, load_project_identity, read_project_json

PROJECT_MANAGEMENT = "project-management.json"
_SEGMENT = re.compile(r"[a-z][a-z0-9-]{0,63}")


class ProjectManagementError(ValueError):
    """A project management declaration is malformed or inconsistent."""


@dataclass(frozen=True)
class ChildDeclaration:
    project_id: str
    archive_segment: str
    primary: bool

    def model_dump(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "archive_segment": self.archive_segment,
                "primary": self.primary}


@dataclass(frozen=True)
class ProjectManagement:
    project_id: str
    kind: str
    children: tuple[ChildDeclaration, ...] = ()
    parent_project_id: str | None = None
    primary: bool | None = None

    def model_dump(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": 1, "project_id": self.project_id, "kind": self.kind,
        }
        if self.kind == "research-parent":
            payload["children"] = [row.model_dump() for row in self.children]
        else:
            payload.update(parent_project_id=self.parent_project_id, primary=self.primary)
        return payload


def validate_project_management(payload: object) -> ProjectManagement:
    """Validate fields and cross-row invariants; no paths or hosts are resolved."""
    if not isinstance(payload, dict):
        raise ProjectManagementError("Project management declaration must be an object")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ProjectManagementError("Project management declaration requires schema_version 1")
    identifier = payload.get("project_id")
    if not is_project_id(identifier):
        raise ProjectManagementError("Project management identity must be a canonical UUIDv4")
    kind = payload.get("kind")
    common = {"schema_version", "project_id", "kind"}
    if kind == "execution-child":
        if set(payload) != common | {"parent_project_id", "primary"}:
            raise ProjectManagementError("Execution child declaration has unknown or missing fields")
        parent = payload["parent_project_id"]
        if not is_project_id(parent) or parent == identifier:
            raise ProjectManagementError("Execution child requires a distinct canonical parent identity")
        if type(payload["primary"]) is not bool:
            raise ProjectManagementError("Execution child primary must be boolean")
        return ProjectManagement(identifier, kind, parent_project_id=parent,
                                 primary=payload["primary"])
    if kind != "research-parent" or set(payload) != common | {"children"}:
        raise ProjectManagementError("Research parent declaration has unknown kind or fields")
    if not isinstance(payload["children"], list):
        raise ProjectManagementError("Research parent children must be a list")
    children = []
    identifiers: set[str] = set()
    segments: set[str] = set()
    for row in payload["children"]:
        if not isinstance(row, dict) or set(row) != {"project_id", "archive_segment", "primary"}:
            raise ProjectManagementError("Child entry has unknown or missing fields")
        child_id, segment, primary = row["project_id"], row["archive_segment"], row["primary"]
        if not is_project_id(child_id) or child_id == identifier or child_id in identifiers:
            raise ProjectManagementError("Child identity must be distinct and unique within its parent")
        if (
            not isinstance(segment, str) or not _SEGMENT.fullmatch(segment)
            or segment == "profiles" or segment in segments
        ):
            raise ProjectManagementError("Child archive segment must be safe and unique within its parent")
        if type(primary) is not bool:
            raise ProjectManagementError("Child primary must be boolean")
        identifiers.add(child_id)
        segments.add(segment)
        children.append(ChildDeclaration(child_id, segment, primary))
    if sum(row.primary for row in children) > 1:
        raise ProjectManagementError("Research parent may declare at most one primary child")
    return ProjectManagement(identifier, kind, children=tuple(children))


def load_project_management(root: str | Path) -> ProjectManagement:
    """Read only the explicit root's bounded declarations, preserving legacy projects."""
    identity = load_project_identity(root)
    declaration = validate_project_management(read_project_json(root, PROJECT_MANAGEMENT))
    if identity != declaration.project_id:
        raise ProjectManagementError("Project management identity differs from project-layout.json")
    if load_project_identity(root) != identity:
        raise ProjectManagementError("Project identity changed while reading declarations")
    return declaration


def validate_management_pair(parent: ProjectManagement, child: ProjectManagement) -> None:
    """Check mutual declarations, not remote availability, Git policy or authorization."""
    if parent.kind != "research-parent" or child.kind != "execution-child":
        raise ProjectManagementError("Pair requires one research parent and one execution child")
    if child.parent_project_id != parent.project_id:
        raise ProjectManagementError("Child parent identity differs from the supplied parent")
    entry = next((row for row in parent.children if row.project_id == child.project_id), None)
    if entry is None or entry.primary != child.primary:
        raise ProjectManagementError("Parent child identity or primary declaration does not agree")
