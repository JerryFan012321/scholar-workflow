"""Open an explicitly registered Source document in its native editor."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from scholar_workflow.adapters.obsidian_registry import resolve_obsidian_reader
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    KnowledgeSourceRegistry,
    _open_directory_chain,
)


def reader_info(registry: KnowledgeSourceRegistry, source_id: str) -> dict:
    root = registry.resolve(source_id, capability="read")
    binding = resolve_obsidian_reader(root)
    return {"schema_version": 1, "source_id": source_id,
            "source_root": str(root), "reader_vault_root": str(binding.vault_root),
            "reader_vault_id": binding.vault_id, "status": "resolved",
            "authorization": "registered-source-only"}


def _document_identity(root: Path, relative: str) -> tuple[int, int]:
    parts = PurePosixPath(relative).parts
    if (not relative or "\\" in relative or relative != PurePosixPath(relative).as_posix()
            or PurePosixPath(relative).is_absolute() or ":" in relative
            or any(part in {".", ".."} or part.startswith(".") for part in parts)
            or any(ord(char) < 32 for char in relative)
            or PurePosixPath(relative).suffix.lower() not in {".md", ".canvas"}):
        raise FieldRegistryError("Open requires a clean Source-relative Markdown or Canvas path")
    parent_fd = _open_directory_chain(root, parts[:-1])
    try:
        fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0), dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise FieldRegistryError("Open target is not a regular document")
            return info.st_dev, info.st_ino
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def open_document(
    registry: KnowledgeSourceRegistry, source_id: str, relative: str, *,
    config_path: Path | None = None, runner=None,
) -> dict:
    """Validate Source scope before requesting a native open, without writing.

    Validation is at dispatch time, not a lock on subsequent external edits.
    Native open success is not proof of a visible window or human acceptance.
    """
    try:
        revision = registry.revision()
        root = registry.resolve(source_id, capability="read")
        identity = _document_identity(root, relative)
        binding = (resolve_obsidian_reader(root) if config_path is None else
                   resolve_obsidian_reader(root, config_path=config_path))
        vault_relative = (root / relative).relative_to(binding.vault_root).as_posix()
        uri = "obsidian://open?" + urlencode({"vault": binding.vault_id, "file": vault_relative})
        if (registry.revision() != revision
                or registry.resolve(source_id, capability="read") != root
                or _document_identity(root, relative) != identity):
            raise FieldRegistryError("Source or document changed before opening")
        result = (runner or subprocess.run)(
            ["/usr/bin/open", uri], shell=False, capture_output=True, text=True, timeout=5.0,
        )
        if result.returncode != 0:
            raise FieldRegistryError("Obsidian rejected the document open request")
        return {"schema_version": 1, "source_id": source_id,
                "source_relative_path": relative, "reader_vault_id": binding.vault_id,
                "status": "open-requested", "human_assessment": "pending"}
    except (OSError, subprocess.SubprocessError) as exc:
        raise FieldRegistryError("Document cannot be opened safely in Obsidian") from exc
