"""Unit tests for runtime diagnostics (offline path checks + advisory HTTP-MCP probe)."""
from __future__ import annotations
import json
from scholar_workflow.doctor import (
    run_doctor, probe_http_mcp_endpoints,
    _http_servers_from_manifest, _http_servers_from_claude_json,
)


class Cfg:
    def __init__(self, inbox, vault):
        self.paper_inbox = inbox
        self.research_vault_root = vault


def test_all_green(tmp_path):
    cfg = Cfg(tmp_path, tmp_path)
    out = run_doctor(cfg)
    assert out["ok"] is True
    assert {c["name"] for c in out["checks"]} == {
        "paper_inbox", "research_vault_root"}


def test_missing_path_fails(tmp_path):
    out = run_doctor(Cfg(tmp_path / "nope", tmp_path))
    assert out["ok"] is False
    assert any(c["name"] == "paper_inbox" and not c["ok"] for c in out["checks"])


# --- advisory HTTP-MCP endpoint probe (INV16-adjacent: TCP/HTTP layer, not MCP semantics) ---


def _claude_json(tmp_path, servers: dict) -> str:
    """Write a minimal ~/.claude.json with a project entry keyed by cwd."""
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps({
        "mcpServers": {},  # global is empty — the real config lives per-project
        "projects": {str(tmp_path): {"mcpServers": servers}},
    }), encoding="utf-8")
    return str(p)


def test_probe_skips_when_no_config(tmp_path):
    """No ~/.claude.json → no advisories, never raises."""
    assert probe_http_mcp_endpoints(str(tmp_path / "absent.json"), str(tmp_path)) == []


def test_probe_skips_stdio_servers(tmp_path):
    """Only type:http servers are probed; stdio (command+args) ones are ignored."""
    cj = _claude_json(tmp_path, {"some-stdio": {"command": "uvx", "args": ["x"]}})
    assert probe_http_mcp_endpoints(cj, str(tmp_path)) == []


def test_probe_reports_unreachable_http_endpoint(tmp_path):
    """A type:http server whose endpoint refuses connection → one advisory, ok=False.
    Port 1 is reserved/unbindable, so the connection is refused fast."""
    cj = _claude_json(tmp_path, {
        "zotero-mcp": {"type": "http", "url": "http://127.0.0.1:1/mcp"},
    })
    advs = probe_http_mcp_endpoints(cj, str(tmp_path))
    assert len(advs) == 1
    a = advs[0]
    assert a["name"] == "zotero-mcp" and a["ok"] is False and a["scope"] == "project"
    assert "session start" in a["detail"].lower()


def test_probe_reads_global_scope(tmp_path):
    """A type:http server in the GLOBAL mcpServers is probed even with no project entry —
    fixes the bug where a bundled/global server was silent because only project scope was read."""
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps({
        "mcpServers": {"zotero-mcp": {"type": "http", "url": "http://127.0.0.1:1/mcp"}},
        "projects": {},
    }), encoding="utf-8")
    advs = probe_http_mcp_endpoints(str(p), str(tmp_path))
    assert len(advs) == 1 and advs[0]["scope"] == "global" and advs[0]["ok"] is False


def test_probe_reads_bundled_manifest(tmp_path):
    """A type:http server declared in the plugin manifest is probed regardless of cwd/config —
    this is what makes the post-bundling probe non-silent (point 4)."""
    mani = tmp_path / "plugin.json"
    mani.write_text(json.dumps({
        "mcpServers": {"zotero-mcp": {"type": "http", "url": "http://127.0.0.1:1/mcp"}},
    }), encoding="utf-8")
    advs = probe_http_mcp_endpoints(str(tmp_path / "absent.json"), str(tmp_path),
                                    manifest_path=str(mani))
    assert len(advs) == 1 and advs[0]["scope"] == "plugin" and advs[0]["ok"] is False


def test_project_scope_overrides_bundle(tmp_path):
    """Same server name in both manifest and project scope → probed once, project scope wins."""
    mani = tmp_path / "plugin.json"
    mani.write_text(json.dumps({
        "mcpServers": {"zotero-mcp": {"type": "http", "url": "http://127.0.0.1:1/mcp"}},
    }), encoding="utf-8")
    cj = _claude_json(tmp_path, {"zotero-mcp": {"type": "http", "url": "http://127.0.0.1:1/mcp"}})
    advs = probe_http_mcp_endpoints(cj, str(tmp_path), manifest_path=str(mani))
    assert len(advs) == 1 and advs[0]["scope"] == "project"


def test_manifest_helper_ignores_non_http(tmp_path):
    """_http_servers_from_manifest skips stdio entries and tolerates a missing file."""
    assert _http_servers_from_manifest(str(tmp_path / "nope.json")) == {}
    mani = tmp_path / "plugin.json"
    mani.write_text(json.dumps({
        "mcpServers": {"s": {"command": "uvx", "args": ["x"]}},
    }), encoding="utf-8")
    assert _http_servers_from_manifest(str(mani)) == {}


def test_run_doctor_advisories_do_not_affect_ok(tmp_path, monkeypatch):
    """An unreachable HTTP-MCP endpoint must NOT flip doctor's top-level ok (advisory only)
    — otherwise a not-yet-open Zotero would make SessionStart exit 3."""
    cj = _claude_json(tmp_path, {
        "zotero-mcp": {"type": "http", "url": "http://127.0.0.1:1/mcp"},
    })
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    out = run_doctor(Cfg(tmp_path, tmp_path))
    assert out["ok"] is True  # local paths fine → ok stays true despite dead endpoint
    assert out["advisories"] and out["advisories"][0]["ok"] is False
