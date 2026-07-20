"""Runtime dependency diagnostics (invoked by the SessionStart hook)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _probe_local_api(url: str) -> bool:
    """Best-effort reachability probe of the Zotero Local API (read-only)."""
    try:
        import httpx
        r = httpx.get(url.rstrip("/") + "/users/0/collections?limit=1", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def run_doctor(config, probe=None) -> dict:
    """Probe config paths and the Zotero Local API. Read-only, no writes.

    `probe` is injectable for testing; when None, a real HTTP probe is used.
    """
    checks: list[Check] = []

    for name, root in (("papers_root", config.papers_root),
                       ("paper_inbox", config.paper_inbox),
                       ("vault_root", config.vault_root)):
        p = Path(root)
        checks.append(Check(name, p.is_dir(), str(p)))

    url = config.zotero.local_api_url
    if probe is None:
        probe = _probe_local_api
    checks.append(Check("zotero_local_api", probe(url), url))

    return {
        "ok": all(c.ok for c in checks),
        "checks": [asdict(c) for c in checks],
    }
