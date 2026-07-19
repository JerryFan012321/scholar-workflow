"""Obsidian adapter: managed block updates and index maintenance."""
from __future__ import annotations
import re
from pathlib import Path


class ObsidianAdapter:
    def __init__(self, vault_root: Path, managed_start: str, managed_end: str) -> None:
        self._root = vault_root
        self._start = managed_start
        self._end = managed_end

    def update_managed_block(self, index_path: Path, rows: list[str]) -> None:
        """Replace content inside managed block; preserve everything outside."""
        full_path = self._root / index_path if not index_path.is_absolute() else index_path
        if not full_path.exists():
            raise FileNotFoundError(f"Index file not found: {full_path}")

        content = full_path.read_text(encoding="utf-8")
        header = (
            "| Title | Authors | Year | Venue | Zotero | PDF | arXiv | DOI | Synced |\n"
            "|---|---|---:|---|---|---|---|---|---|\n"
        )
        block_content = header + "\n".join(rows)
        pattern = re.escape(self._start) + r".*?" + re.escape(self._end)
        replacement = f"{self._start}\n{block_content}\n{self._end}"
        new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
        if count == 0:
            raise ValueError(f"Managed block markers not found in {full_path}")
        full_path.write_text(new_content, encoding="utf-8")

    def ensure_managed_block(self, index_path: Path, heading: str) -> None:
        """Create index file with empty managed block if it doesn't exist."""
        full_path = self._root / index_path if not index_path.is_absolute() else index_path
        if full_path.exists():
            return
        full_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# {heading}\n\n"
            f"{self._start}\n"
            "| Title | Authors | Year | Venue | Zotero | PDF | arXiv | DOI | Synced |\n"
            "|---|---|---:|---|---|---|---|---|---|\n"
            f"{self._end}\n"
        )
        full_path.write_text(content, encoding="utf-8")
