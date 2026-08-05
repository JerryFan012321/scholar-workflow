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


def _http_servers_from_claude_json(claude_json_path: str, cwd: str) -> dict[str, dict]:
    """Collect type:http MCP servers from ~/.claude.json — both the GLOBAL `mcpServers`
    and this project's `projects[cwd].mcpServers`. Project scope overrides global on name
    collision. Each value is tagged with its scope. Never raises."""
    try:
        data = json.loads(Path(claude_json_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for scope, src in (("global", data.get("mcpServers", {}) or {}),
                       ("project", (data.get("projects", {}).get(cwd, {}) or {})
                        .get("mcpServers", {}) or {})):
        for name, cfg in src.items():
            if isinstance(cfg, dict) and cfg.get("type") == "http":
                out[name] = {"url": cfg.get("url", ""), "scope": scope}
    return out


def _http_servers_from_manifest(manifest_path: str) -> dict[str, dict]:
    """Collect type:http MCP servers bundled in the plugin manifest (.claude-plugin/
    plugin.json `mcpServers`). These auto-register in every session the plugin is enabled,
    regardless of cwd — so they must be probed even when absent from ~/.claude.json. Never
    raises."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for name, cfg in (data.get("mcpServers", {}) or {}).items():
        if isinstance(cfg, dict) and cfg.get("type") == "http":
            out[name] = {"url": cfg.get("url", ""), "scope": "plugin"}
    return out


def probe_http_mcp_endpoints(claude_json_path: str, cwd: str,
                             manifest_path: str | None = None,
                             timeout: float = 3.0) -> list[dict]:
    """Advisory-only probe of every type:http MCP endpoint that could serve this session:
    plugin-bundled (manifest) + global + project-scope (~/.claude.json). Precedence on name
    collision: project > global > plugin.

    Claude Code contacts an HTTP-transport MCP server only at session start, by connecting to
    its `url`; if the endpoint isn't listening then, the server is silently skipped for the
    whole session and never re-attempted. So a dead endpoint means "start the endpoint, then
    restart the session", not "config is wrong". This checks the TCP/HTTP layer only — NOT MCP
    semantics (whether tools are registered), which the CLI cannot see and which stays a
    skill-layer check (INV16). Read-only; never raises; returns one advisory dict per http
    server: {name, ok, scope, detail}.
    """
    servers: dict[str, dict] = {}
    if manifest_path:
        servers.update(_http_servers_from_manifest(manifest_path))  # lowest precedence
    servers.update(_http_servers_from_claude_json(claude_json_path, cwd))  # global then project

    advisories: list[dict] = []
    for name, entry in servers.items():
        ok, detail = _reachable(entry["url"], timeout)
        advisories.append({"name": name, "ok": ok, "scope": entry["scope"], "detail": detail})
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

    # Bundled manifest lives at repo-root/.claude-plugin/plugin.json (this file is
    # src/scholar_workflow/doctor.py — two parents up to the repo root).
    manifest = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
    advisories = probe_http_mcp_endpoints(
        str(Path(os.path.expanduser("~")) / ".claude.json"), os.getcwd(),
        manifest_path=str(manifest))

    return {
        "ok": all(c.ok for c in checks),  # advisories deliberately excluded
        "checks": [asdict(c) for c in checks],
        "advisories": advisories,
    }
