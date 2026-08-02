"""Technical document archival workflow."""
from __future__ import annotations
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from scholar_workflow.models import Resource


def archive_document(res: Resource, source_path: Path,
                     vault_root: Path, vault_rel: str) -> dict:
    """Copy source file into Vault and write sidecar metadata. Never touches Zotero storage."""
    dest = vault_root / vault_rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    sha = _sha256(source_path)
    shutil.copy2(source_path, dest)

    meta = {
        "resource_id": res.resource_id,
        "title": res.title,
        "source": str(res.identifiers.url or source_path),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "sha256": sha,
        "vault_path": vault_rel,
    }
    meta_path = dest.with_suffix(dest.suffix + ".meta.json")
    import json
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {"vault_path": vault_rel, "sha256": sha}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
