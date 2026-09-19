"""Runtime dependency diagnostics invoked by the SessionStart hook."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter, ZoteroLocalError


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def probe_zotero_local() -> dict:
    """Probe the Zotero Local API without requesting write authorization."""
    try:
        with ZoteroLocalAdapter() as adapter:
            server = adapter.probe()
    except ZoteroLocalError:
        return {
            "name": "zotero_local_api",
            "ok": False,
            "scope": "local",
            "detail": (
                "unavailable — start Zotero and enable the Local API in Settings → Advanced"
            ),
        }
    schema = f", schema {server.schema_version}" if server.schema_version else ""
    return {
        "name": "zotero_local_api",
        "ok": True,
        "scope": "local",
        "detail": f"reachable (API {server.api_version}{schema})",
    }


def run_doctor(config, *, zotero_probe: Callable[[], dict] | None = None) -> dict:
    """Check required local paths and report Local API availability as advisory."""
    checks: list[Check] = []
    for name, root in (
        ("paper_inbox", config.paper_inbox),
        ("research_vault_root", config.research_vault_root),
    ):
        path = Path(root)
        checks.append(Check(name, path.is_dir(), str(path)))

    probe = zotero_probe or probe_zotero_local
    return {
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
        "advisories": [probe()],
    }
