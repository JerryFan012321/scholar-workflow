"""Obsidian adapter: managed block updates and index maintenance."""
from __future__ import annotations
import re
from pathlib import Path


class ObsidianAdapter:
    def __init__(self, vault_root: Path, managed_start: str, managed_end: str) -> None:
        self._root = vault_root
        self._start = managed_start
        self._end = managed_end

    def _resolve(self, index_path: Path) -> Path:
        p = Path(index_path)
        return p if p.is_absolute() else self._root / p

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

    def ensure_managed_block(self, index_path: Path, heading: str) -> None:
        """Create the file with an empty managed block if it doesn't exist."""
        full_path = self._resolve(index_path)
        if full_path.exists():
            return
        full_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# {heading}\n\n{self._start}\n{self._end}\n"
        full_path.write_text(content, encoding="utf-8")
