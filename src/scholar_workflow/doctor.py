"""Runtime dependency diagnostics (invoked by the SessionStart hook)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(config, bridge=None) -> dict:
    """Probe config paths and the Zotero write backend. Read-only, no writes.

    `bridge` is injectable for testing; when None, the real BridgeAdapter is used.
    """
    checks: list[Check] = []

    for name, root in (("papers_root", config.papers_root),
                       ("vault_root", config.vault_root)):
        p = Path(root)
        checks.append(Check(name, p.is_dir(), str(p)))

    if bridge is None:
        from scholar_workflow.adapters.zotero_bridge import BridgeAdapter
        bridge = BridgeAdapter(config.zotero.bridge_url)
    bridge_ok = bridge.health_check()
    checks.append(Check("zotero_bridge", bridge_ok, config.zotero.bridge_url))

    return {
        "ok": all(c.ok for c in checks),
        "checks": [asdict(c) for c in checks],
    }
