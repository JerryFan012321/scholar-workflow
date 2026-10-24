"""Explicit paragraph blocks supported by archived Markdown source notes."""
from __future__ import annotations

import re


def source_paragraphs(text: str) -> dict[str, str]:
    """Resolve standalone anchors to the immediately preceding paragraph only.

    Fenced code and HTML comments are not source block declarations. This narrow
    source-note format does not claim to implement every Obsidian block grammar.
    """
    blocks: dict[str, str] = {}
    preceding: list[str] = []
    fence = None
    comment = False
    for line in text.splitlines():
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            preceding = []
            continue
        if comment or "<!--" in line:
            for token in re.finditer(r"<!--|-->", line):
                comment = token[0] == "<!--"
            preceding = []
            continue
        if marker:
            fence = marker[1]
            preceding = []
            continue
        anchor = re.fullmatch(r"\^([A-Za-z0-9][A-Za-z0-9-]{0,127})[ \t]*", line)
        if anchor:
            paragraph = "\n".join(preceding).strip()
            if not paragraph or anchor[1] in blocks:
                raise ValueError("Source anchors require unique nonempty paragraph blocks")
            blocks[anchor[1]] = paragraph
            preceding = []
        elif line.strip():
            preceding.append(line)
        else:
            preceding = []
    return blocks
