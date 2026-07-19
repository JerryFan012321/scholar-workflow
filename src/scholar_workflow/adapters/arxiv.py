"""arXiv adapter: metadata resolution and PDF download."""
from __future__ import annotations
import hashlib
import re
import tempfile
from pathlib import Path
import httpx


ARXIV_API = "https://export.arxiv.org/abs/{arxiv_id}"
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"
PDF_MAGIC = b"%PDF"
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB hard limit


def fetch_metadata(arxiv_id: str) -> dict:
    """Return normalized metadata dict from arXiv API. Raises on failure."""
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
    r = httpx.get(url, timeout=20)
    r.raise_for_status()
    # minimal XML parse — replace with feedparser in real implementation
    return {"arxiv_id": arxiv_id, "raw_xml": r.text}


def check_pdf_available(arxiv_id: str) -> bool:
    """HEAD request to confirm arXiv PDF exists."""
    try:
        r = httpx.head(ARXIV_PDF.format(arxiv_id=arxiv_id), timeout=10, follow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


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
