"""Resource identity: normalization, dedup key generation."""
from __future__ import annotations
import hashlib
import re
import unicodedata


ARXIV_BASE_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")


def normalize_arxiv(raw: str) -> str | None:
    """Return base arXiv ID without version suffix, or None if not arXiv format."""
    raw = raw.strip()
    if raw.startswith("arxiv:"):
        raw = raw[6:]
    m = ARXIV_BASE_RE.match(raw)
    return m.group(1) if m else None


def normalize_doi(raw: str) -> str | None:
    """Lowercase and strip doi: prefix."""
    raw = raw.strip().lower()
    if raw.startswith("doi:"):
        raw = raw[4:]
    if raw.startswith("https://doi.org/"):
        raw = raw[16:]
    return raw if raw else None


def normalize_title(title: str) -> str:
    """Unicode NFC + lowercase + collapse whitespace for fuzzy matching."""
    t = unicodedata.normalize("NFC", title).lower()
    return " ".join(t.split())


def make_resource_id(kind: str, identifiers: dict) -> str:
    """Generate deterministic resource_id from strongest available identifier."""
    if arxiv := identifiers.get("arxiv"):
        return f"{kind}:arxiv:{normalize_arxiv(arxiv)}"
    if doi := identifiers.get("doi"):
        return f"{kind}:doi:{normalize_doi(doi)}"
    # fallback: hash of normalized title + first author + year
    title = normalize_title(identifiers.get("title", ""))
    author = identifiers.get("first_author", "")
    year = str(identifiers.get("year", ""))
    digest = hashlib.sha256(f"{title}|{author}|{year}".encode()).hexdigest()[:16]
    return f"{kind}:meta:{digest}"


def dedup_key(resource_id: str, zotero_item_key: str | None = None) -> tuple[str, ...]:
    """Return ordered identity keys for dedup checks."""
    keys = [resource_id]
    if zotero_item_key:
        keys.append(f"zotero:{zotero_item_key}")
    return tuple(keys)
