"""Confirm a system-selected execution folder without accepting browser paths."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholar_workflow.hub.fields import FolderRegistration, KnowledgeSourceRegistry
from scholar_workflow.hub.routing import (
    ExecutionTarget,
    ExecutionTargetError,
    ExecutionTargetRegistry,
)


def _identity(path: Path) -> tuple[int, int]:
    info = path.stat(follow_symlinks=False)
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class _FolderCandidate:
    root: Path
    identity: tuple[int, int]
    source_revision: str
    target_revision: str
    expires_at: float


class ExecutionFolderSetup:
    """Short-lived, one-use folder approvals for the Codex setup screen."""

    def __init__(
        self, sources: KnowledgeSourceRegistry, targets: ExecutionTargetRegistry,
        *, ttl_seconds: float = 600, clock=time.monotonic,
    ) -> None:
        self.sources = sources
        self.targets = targets
        self._ttl = ttl_seconds
        self._clock = clock
        self._candidates: dict[str, _FolderCandidate] = {}
        self._lock = threading.RLock()

    def preview(self, selected_root: Path) -> dict[str, Any]:
        root = Path(selected_root)
        if not root.is_absolute() or root.is_symlink():
            raise ExecutionTargetError("Choose an absolute, non-symlink folder")
        root = root.resolve(strict=True)
        if not root.is_dir() or root == Path(root.anchor) or root == Path.home().resolve():
            raise ExecutionTargetError("Choose a specific working folder, not a home or filesystem root")
        token = secrets.token_urlsafe(32)
        candidate = _FolderCandidate(
            root=root, identity=_identity(root),
            source_revision=self.sources.revision(),
            target_revision=self.targets.revision(),
            expires_at=self._clock() + self._ttl,
        )
        with self._lock:
            self._candidates = {
                key: row for key, row in self._candidates.items()
                if row.expires_at > self._clock()
            }
            self._candidates[token] = candidate
        return {"candidate_token": token, "title": root.name, "kind": "folder",
                "capabilities": ["codex"], "requires_confirmation": True}

    def confirm(self, token: str) -> dict[str, Any]:
        with self._lock:
            candidate = self._candidates.pop(token, None)
            if candidate is None or candidate.expires_at <= self._clock():
                raise ExecutionTargetError("Folder selection expired; choose the folder again")
            if candidate.root.is_symlink() or _identity(candidate.root) != candidate.identity:
                raise ExecutionTargetError("Selected folder changed; choose it again")
            sources = self.sources.load_document()
            targets = self.targets.load()
            if (self.sources.revision() != candidate.source_revision
                    or self.targets.revision() != candidate.target_revision):
                raise ExecutionTargetError("Target registrations changed; review the folder again")
            previous_sources = sources.model_copy(deep=True)
            folder = next((row for row in sources.folders
                           if row.root.resolve() == candidate.root), None)
            if folder is None:
                folder = FolderRegistration(
                    folder_id=f"folder_{secrets.token_hex(12)}", root=candidate.root,
                    capabilities=["read", "codex"],
                )
                sources.folders.append(folder)
            elif not folder.enabled:
                raise ExecutionTargetError("The selected registered folder is disabled")
            elif "codex" not in folder.capabilities:
                folder.capabilities.append("codex")
            existing = next((row for row in targets.targets
                             if row.registered_root_id == folder.folder_id
                             and row.kind == "folder" and row.field_id is None
                             and "codex" in row.capabilities), None)
            target = existing or ExecutionTarget(
                target_id=f"target_{secrets.token_hex(12)}", kind="folder",
                registered_root_id=folder.folder_id, capabilities=["codex"],
            )
            if existing is None:
                targets.targets.append(target)
            self.sources.save(sources, expected_revision=candidate.source_revision)
            written_source_revision = self.sources.revision()
            try:
                self.targets.save(targets, expected_revision=candidate.target_revision)
            except BaseException:
                if self.sources.revision() == written_source_revision:
                    self.sources.save(previous_sources, expected_revision=written_source_revision)
                raise
            return {**target.model_dump(mode="json"), "title": candidate.root.name}


__all__ = ["ExecutionFolderSetup"]
