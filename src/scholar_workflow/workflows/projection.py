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


# Importance star badges. Keyed by the three-tier text; the renderer appends the badge
# so the column reads e.g. "milestone ★★". A value already carrying stars (or an unknown
# tier) is passed through unchanged, keeping the cell idempotent.
_IMPORTANCE_STARS = {"founding": "★★★", "milestone": "★★", "representative": "★"}


def _importance_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    stars = _IMPORTANCE_STARS.get(text.lower())
    return f"{text} {stars}" if stars else text


def _base_header(assets: bool) -> str:
    cols = ["Title", "Authors", "Year", "Venue", "Importance", "Zotero", "PDF", "arXiv"]
    if assets:
        cols.append("Assets")
    cols.append("Synced")
    aligns = ["---"] * len(cols)
    aligns[2] = "---:"  # Year right-aligned
    return "| " + " | ".join(cols) + " |\n|" + "|".join(aligns) + "|"


HEADER = _base_header(assets=False)


def format_row(entry: dict, port: int, assets: bool = False) -> str:
    """Render one entry as a table row. Columns:
    Title|Authors|Year|Venue|Importance|Zotero|PDF|arXiv|[Assets|]Synced.
    DOI is intentionally not a column (kept only as a dedup identity field). The Assets
    column (a wikilink to the paper's assets note) is emitted only when assets=True."""
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
        _cell(entry.get("venue")), _importance_cell(entry.get("importance")),
        zotero, pdf, arxiv_cell,
    ]
    if assets:
        note = entry.get("asset_note")
        cells.append(f"[[{note}]]" if note else "")
    cells.append(_cell(entry.get("synced")))
    return "| " + " | ".join(cells) + " |"


def render_table(entries: list[dict], port: int, assets: bool = False) -> str:
    """Full paper-table body (header + rows) for a managed block. Set assets=True to add
    an Assets column (used by the literature tree / paper list, not the Zotero mirror)."""
    return "\n".join([_base_header(assets), *(format_row(e, port, assets) for e in entries)])


def project_obsidian(entries: list[dict], index_path: Path, heading: str,
                     adapter, port: int) -> int:
    """Ensure the index exists, then replace the managed block with rendered rows.

    Content outside the managed markers is never touched (INV4). Returns row count.
    """
    adapter.ensure_managed_block(Path(index_path), heading)
    adapter.update_managed_block(Path(index_path), render_table(entries, port))
    return len(entries)
