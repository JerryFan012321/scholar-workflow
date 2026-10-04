"""Host-local reader identity; never a file-authorization registry."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VAULT_ID = re.compile(r"[0-9a-f]{16}\Z")
_MAX_CONFIG_BYTES = 1024 * 1024


class ZotFlowError(RuntimeError):
    """An Obsidian/ZotFlow reader cannot be resolved or opened safely."""


@dataclass(frozen=True)
class ObsidianReaderBinding:
    source_root: Path
    vault_root: Path
    vault_id: str


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Obsidian config key")
        result[key] = value
    return result


def _resolve(
    source_root: Path, *, config_path: Path | None, containing: bool,
) -> ObsidianReaderBinding:
    config = config_path or Path.home() / "Library/Application Support/obsidian/obsidian.json"
    try:
        fd = os.open(config, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o022 or not 0 < info.st_size <= _MAX_CONFIG_BYTES):
                raise ZotFlowError("Obsidian Vault registry is unsafe or unavailable")
            raw = handle.read(_MAX_CONFIG_BYTES + 1)
            after = os.fstat(handle.fileno())
            if (len(raw) != info.st_size or
                    (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) !=
                    (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ZotFlowError("Obsidian Vault registry changed during reading")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
        vaults = document.get("vaults") if isinstance(document, dict) else None
        if not isinstance(vaults, dict):
            raise ZotFlowError("Obsidian Vault registry is invalid")
        source = Path(source_root)
        if source.is_symlink():
            raise ZotFlowError("Registered Source crosses a symbolic link")
        expected = source.resolve(strict=True)
        if not expected.is_dir():
            raise ZotFlowError("Registered Obsidian Source is unavailable")
        matches: list[ObsidianReaderBinding] = []
        for vault_id, entry in vaults.items():
            if not isinstance(vault_id, str) or _VAULT_ID.fullmatch(vault_id) is None:
                raise ZotFlowError("Obsidian Vault registry is invalid")
            path = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(path, str) or not path or not Path(path).is_absolute():
                raise ZotFlowError("Obsidian Vault registry is invalid")
            try:
                candidate = Path(path).resolve(strict=True)
                if candidate.is_dir() and (candidate.samefile(expected) or
                                          (containing and candidate in expected.parents)):
                    matches.append(ObsidianReaderBinding(expected, candidate, vault_id))
            except (OSError, ValueError, RuntimeError):
                continue  # A stale unrelated Vault cannot authorize this Source.
        if len(matches) != 1:
            raise ZotFlowError("Registered Obsidian Vault ID is missing or ambiguous")
        return matches[0]
    except ZotFlowError:
        raise
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        raise ZotFlowError("Obsidian Vault registry is unsafe or unavailable") from exc


def resolve_obsidian_reader(
    source_root: Path, *, config_path: Path | None = None,
) -> ObsidianReaderBinding:
    """Resolve the unique registered Vault containing the selected Source.

    The caller must retain its Source registry for all file access. Neither this
    result nor the parent Vault path grants read/write access outside that Source.
    Nested or duplicate registered Vaults are ambiguous; never pick the first.
    """
    return _resolve(source_root, config_path=config_path, containing=True)


def resolve_obsidian_reader_vault_id(
    source_root: Path, *, config_path: Path | None = None,
) -> str:
    return resolve_obsidian_reader(source_root, config_path=config_path).vault_id


def resolve_obsidian_vault_id(vault_root: Path, *, config_path: Path | None = None) -> str:
    """Compatibility interface: accept an exact registered Vault root only."""
    return _resolve(vault_root, config_path=config_path, containing=False).vault_id
