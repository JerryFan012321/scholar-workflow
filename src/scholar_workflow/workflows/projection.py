"""Obsidian projection: render Zotero-sourced entries into a managed-block index.

Entries are produced by the host LLM via zotero-mcp and handed to the CLI as JSON
(GOALS INV18 — planner/executor split, CLI never reaches MCP). The PDF column points
at the loopback link-service by attachment key (INV17). `format_row` is pure —
deterministic in its input — so re-running the same entries is idempotent.
"""
from __future__ import annotations
from pathlib import Path


def _cell(v: object) -> str:
    """Escape a value for a markdown table cell (pipes and newlines break tables)."""
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


HEADER = (
    "| Title | Authors | Year | Venue | Importance | Zotero | PDF | arXiv | DOI | Synced |\n"
    "|---|---|---:|---|---|---|---|---|---|---|"
)


def format_row(entry: dict, port: int) -> str:
    """Render one entry as a 10-column row:
    Title|Authors|Year|Venue|Importance|Zotero|PDF|arXiv|DOI|Synced."""
    authors = entry.get("authors") or []
    authors = "; ".join(authors) if isinstance(authors, list) else authors
    attach = entry.get("attachment_key")
    pdf = f"[PDF](http://127.0.0.1:{port}/open/paper/{attach})" if attach else ""
    zkey = entry.get("zotero_key")
    zotero = f"[open](zotero://select/items/@{zkey})" if zkey else ""
    arxiv = entry.get("arxiv")
    arxiv_cell = f"[{_cell(arxiv)}](https://arxiv.org/abs/{arxiv})" if arxiv else ""
    cells = [
        _cell(entry.get("title")), _cell(authors), _cell(entry.get("year")),
        _cell(entry.get("venue")), _cell(entry.get("importance")), zotero, pdf,
        arxiv_cell, _cell(entry.get("doi")), _cell(entry.get("synced")),
    ]
    return "| " + " | ".join(cells) + " |"


def render_table(entries: list[dict], port: int) -> str:
    """Full paper-table body (header + rows) for a managed block."""
    return "\n".join([HEADER, *(format_row(e, port) for e in entries)])


def project_obsidian(entries: list[dict], index_path: Path, heading: str,
                     adapter, port: int) -> int:
    """Ensure the index exists, then replace the managed block with rendered rows.

    Content outside the managed markers is never touched (INV4). Returns row count.
    """
    adapter.ensure_managed_block(Path(index_path), heading)
    adapter.update_managed_block(Path(index_path), render_table(entries, port))
    return len(entries)
