"""arXiv adapter: PDF download only.

Metadata is not parsed from arXiv — it is authoritative from zotero-mcp for library
items, or fetched from an authoritative web source for new items (INV10), never from the
PDF. This module only fetches the PDF so it can land in the paper inbox; the host LLM
then imports it into Zotero via zotero-mcp (`write_item` import).
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import httpx


ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"
PDF_MAGIC = b"%PDF"
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB hard limit


def download_pdf(arxiv_id: str, dest_dir: Path) -> Path:
    """Download arXiv PDF to dest_dir. Validates magic bytes and size. Returns path."""
    url = ARXIV_PDF.format(arxiv_id=arxiv_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f"{arxiv_id}.pdf"

    with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
        resp.raise_for_status()
        content_length = int(resp.headers.get("content-length", 0))
        if content_length > MAX_PDF_BYTES:
            raise ValueError(f"PDF too large: {content_length} bytes")
        data = b""
        for chunk in resp.iter_bytes(chunk_size=65536):
            data += chunk
            if len(data) > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds size limit during download")

    if not data.startswith(PDF_MAGIC):
        raise ValueError(f"Downloaded file is not a PDF (bad magic bytes): {url}")

    tmp.write_bytes(data)
    return tmp


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
