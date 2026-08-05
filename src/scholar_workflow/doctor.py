"""Runtime dependency diagnostics (invoked by the SessionStart hook)."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def probe_http_mcp_endpoints(claude_json_path: str, cwd: str,
                             timeout: float = 3.0) -> list[dict]:
    """Advisory-only probe of type:http MCP endpoints configured for this project.

    Claude Code registers an HTTP-transport MCP server only at session start, by connecting
    to its `url`; if the endpoint isn't listening then, the server is silently skipped for
    the whole session and never re-attempted. So a dead endpoint here means "restart the
    session after the endpoint is up", not "config is wrong". This checks the TCP/HTTP layer
    only — NOT MCP semantics (whether tools are registered), which the CLI cannot see and
    which stays a skill-layer check (INV16). Read-only; never raises; returns one advisory
    dict per http server: {name, ok, detail}.
    """
    try:
        data = json.loads(Path(claude_json_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []  # no config / unreadable — nothing to advise on
    servers = (data.get("projects", {}).get(cwd, {}) or {}).get("mcpServers", {}) or {}

    advisories: list[dict] = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict) or cfg.get("type") != "http":
            continue  # stdio servers are spawned by Claude Code itself — not our concern
        url = cfg.get("url", "")
        ok, detail = _reachable(url, timeout)
        advisories.append({"name": name, "ok": ok, "detail": detail})
    return advisories


def _reachable(url: str, timeout: float) -> tuple[bool, str]:
    """True if `url` answers over HTTP. Bypasses any local proxy (the loopback MCP endpoint
    must be hit directly; a proxy in between reports spurious failures)."""
    if not url:
        return False, "no url configured"
    # An opener with no ProxyHandler entries disables proxying for this request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as resp:
            return True, f"reachable (HTTP {resp.status}) at {url}"
    except urllib.error.HTTPError as e:
        # A 4xx/5xx still proves the endpoint is listening (MCP endpoints often 405 a bare GET).
        return True, f"reachable (HTTP {e.code}) at {url}"
    except (urllib.error.URLError, OSError, ValueError):
        return False, (f"endpoint not reachable at {url} — start the MCP server (e.g. Zotero "
                       f"+ its plugin) BEFORE session start, then restart the session; "
                       f"HTTP-MCP registers only at session start")


def run_doctor(config) -> dict:
    """Probe local config paths (read-only, no writes) plus an advisory HTTP-MCP endpoint
    check. Zotero access goes through zotero-mcp, which the CLI subprocess cannot reach, so
    MCP tool-registration is verified by the host LLM at the skill layer, not here. The
    endpoint probe is TCP/HTTP-layer only and is ADVISORY — it never affects top-level `ok`,
    so a not-yet-open Zotero can't make SessionStart fail.
    """
    checks: list[Check] = []

    for name, root in (("paper_inbox", config.paper_inbox),
                       ("research_vault_root", config.research_vault_root)):
        p = Path(root)
        checks.append(Check(name, p.is_dir(), str(p)))

    advisories = probe_http_mcp_endpoints(
        str(Path(os.path.expanduser("~")) / ".claude.json"), os.getcwd())

    return {
        "ok": all(c.ok for c in checks),  # advisories deliberately excluded
        "checks": [asdict(c) for c in checks],
        "advisories": advisories,
    }
