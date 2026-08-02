"""Runtime dependency diagnostics (invoked by the SessionStart hook)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(config) -> dict:
    """Probe local config paths. Read-only, no writes.

    Zotero access now goes through zotero-mcp, which the CLI subprocess cannot reach;
    zotero-mcp reachability is verified by the host LLM at the skill layer, not here.
    """
    checks: list[Check] = []

    for name, root in (("paper_inbox", config.paper_inbox),
                       ("research_vault_root", config.research_vault_root)):
        p = Path(root)
        checks.append(Check(name, p.is_dir(), str(p)))

    return {
        "ok": all(c.ok for c in checks),
        "checks": [asdict(c) for c in checks],
    }
