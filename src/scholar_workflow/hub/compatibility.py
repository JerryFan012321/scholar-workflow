"""Reserved filesystem compatibility for pre-v3 Hub content providers."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from scholar_workflow.config import DEFAULT_HOME


class CompatibilityRootError(RuntimeError):
    """The reserved compatibility root cannot be created safely."""


def compatibility_vault_root(
    configured_root: Path | None,
    *,
    state_home: Path | None = None,
) -> Path:
    """Return a legacy content root without inventing a Knowledge Source.

    A configured, real directory remains available to the one-version compatibility
    projection.  Otherwise the Hub receives a private reserved directory below its
    host state.  This directory is deliberately absent from every Source registry and
    Field manifest; it exists only because the old content provider still requires a
    concrete path while v3 routes knowledge through registered Sources.
    """
    if configured_root is not None:
        candidate = Path(configured_root).expanduser()
        try:
            metadata = candidate.lstat()
        except OSError:
            metadata = None
        if (
            metadata is not None
            and stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
        ):
            return candidate.resolve(strict=True)

    base = Path(
        state_home
        if state_home is not None
        else os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)
    ).expanduser().resolve()
    try:
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise CompatibilityRootError(
            "Hub compatibility root could not be created"
        ) from exc
    root = base / "hub" / "empty-compatibility-vault"
    for directory in (base, base / "hub", root):
        try:
            metadata = directory.lstat()
        except FileNotFoundError:
            directory.mkdir(mode=0o700)
            metadata = directory.lstat()
        except OSError as exc:
            raise CompatibilityRootError(
                "Hub compatibility root could not be inspected"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise CompatibilityRootError(
                "Hub compatibility root must be a private real directory"
            )
        try:
            directory.chmod(0o700)
        except OSError as exc:
            raise CompatibilityRootError(
                "Hub compatibility root permissions could not be secured"
            ) from exc
    return root.resolve(strict=True)


__all__ = [
    "CompatibilityRootError",
    "compatibility_vault_root",
]
