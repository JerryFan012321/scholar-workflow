"""Obsidian adapter: managed block updates and index maintenance."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from scholar_workflow.hub.obsidian_contract import MANAGED_FRONTMATTER_FIELDS


class VaultPathError(ValueError):
    """A vault-relative path escaped the vault root (absolute, `..`, or symlink)."""


def safe_vault_path(vault_root: Path, rel: str | os.PathLike) -> Path:
    """Resolve `rel` under `vault_root`, rejecting anything that escapes the root.

    A projection is a rebuildable derived index confined to the vault; the payload
    fields that name its files (`root` / `filename` / `index` / `vault_rel`) come from
    stdin, so they are an untrusted system boundary. Reject absolute paths and any input
    that resolves outside the vault root — covering both `..` traversal and symlink
    escape — so no projection can ever write outside the vault."""
    rel_p = Path(rel)
    if rel_p.is_absolute():
        raise VaultPathError(f"absolute path not allowed inside vault: {rel}")
    root_real = Path(os.path.realpath(vault_root))
    target = Path(os.path.realpath(root_real / rel_p))
    if target != root_real and root_real not in target.parents:
        raise VaultPathError(f"path escapes vault root: {rel}")
    return target


class ObsidianAdapter:
    def __init__(self, vault_root: Path, managed_start: str, managed_end: str) -> None:
        self._root = vault_root
        self._start = managed_start
        self._end = managed_end

    def _resolve(self, index_path: Path) -> Path:
        return safe_vault_path(self._root, index_path)

    def update_managed_block(self, index_path: Path, body: str) -> None:
        """Replace the inter-marker region with `body` verbatim; preserve everything
        outside the markers (INV4). The caller owns the body — a paper table, a MOC
        wikilink list, or both — so the adapter stays format-agnostic."""
        full_path = self._resolve(index_path)
        if not full_path.exists():
            raise FileNotFoundError(f"Index file not found: {full_path}")
        content = full_path.read_text(encoding="utf-8")
        pattern = re.escape(self._start) + r".*?" + re.escape(self._end)
        replacement = f"{self._start}\n{body}\n{self._end}"
        new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
        if count == 0:
            raise ValueError(f"Managed block markers not found in {full_path}")
        full_path.write_text(new_content, encoding="utf-8")

    def update_managed_frontmatter(
        self,
        index_path: str | os.PathLike,
        values: Mapping[str, object],
    ) -> None:
        """Update only Hub-owned ``sw_*`` fields in an existing Obsidian note.

        The Hub contract owns a small, explicit metadata namespace. All other YAML
        fields and the complete Markdown body remain human-owned and are preserved.
        """
        full_path = self._resolve(Path(index_path))
        unknown = set(values) - MANAGED_FRONTMATTER_FIELDS
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown managed frontmatter field(s): {names}")
        if not full_path.exists():
            raise FileNotFoundError(f"Index file not found: {full_path}")

        content = full_path.read_text(encoding="utf-8")
        match = re.match(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?\n", content, re.DOTALL | re.MULTILINE)
        if match:
            raw_frontmatter = match.group(1)
            body = content[match.end():]
        else:
            raw_frontmatter = ""
            body = content

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False
        frontmatter = yaml.load(raw_frontmatter) if raw_frontmatter else {}
        if frontmatter is None:
            frontmatter = {}
        if not isinstance(frontmatter, Mapping):
            raise ValueError(f"Frontmatter must be a YAML mapping in {full_path}")
        for key, value in values.items():
            frontmatter[key] = value

        buffer = StringIO()
        yaml.dump(frontmatter, buffer)
        new_content = f"---\n{buffer.getvalue()}---\n{body}"
        if new_content != content:
            full_path.write_text(new_content, encoding="utf-8")

    def ensure_managed_block(self, index_path: Path, heading: str) -> None:
        """Create the file with an empty managed block if it doesn't exist."""
        full_path = self._resolve(index_path)
        if full_path.exists():
            return
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # An empty heading means "no H1" — the filename is the title (avoids a body
        # heading that just repeats the note name). Existing callers pass real headings.
        head = f"# {heading}\n\n" if heading else ""
        content = f"{head}{self._start}\n{self._end}\n"
        full_path.write_text(content, encoding="utf-8")
