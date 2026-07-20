"""arXiv adapter: metadata resolution and PDF download."""
from __future__ import annotations
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx


ARXIV_API = "https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"
PDF_MAGIC = b"%PDF"
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB hard limit

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


def parse_arxiv_atom(xml_text: str) -> dict:
    """Parse an arXiv Atom feed into normalized metadata (pure, offline).

    Returns {} when the feed has no <entry> (unknown id). Raises on malformed XML.
    """
    root = ET.fromstring(xml_text)
    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        return {}

    title = (entry.findtext(f"{_ATOM}title") or "").strip()
    title = " ".join(title.split())
    authors = [n.strip() for a in entry.findall(f"{_ATOM}author")
               if (n := a.findtext(f"{_ATOM}name"))]
    published = entry.findtext(f"{_ATOM}published") or ""
    year = int(published[:4]) if published[:4].isdigit() else None
    doi = entry.findtext(f"{_ARXIV}doi")

    return {"title": title, "authors": authors, "year": year,
            "doi": doi.strip() if doi else None}


def fetch_metadata(arxiv_id: str) -> dict:
    """Fetch + parse arXiv metadata. Returns {} for an unknown id. Raises on network error."""
    r = httpx.get(ARXIV_API.format(arxiv_id=arxiv_id), timeout=20)
    r.raise_for_status()
    meta = parse_arxiv_atom(r.text)
    if meta:
        meta["arxiv_id"] = arxiv_id
    return meta


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
