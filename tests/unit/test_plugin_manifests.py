import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_host_manifests_share_identity_version_and_mcp_configuration():
    claude_manifest = _load_json(".claude-plugin/plugin.json")
    codex_manifest = _load_json(".codex-plugin/plugin.json")
    codex_mcp = _load_json(".mcp.json")

    assert codex_manifest["name"] == claude_manifest["name"]
    assert codex_manifest["version"] == claude_manifest["version"]
    assert codex_manifest["skills"] == "./skills/"
    assert codex_manifest["mcpServers"] == "./.mcp.json"
    assert codex_mcp["mcpServers"] == claude_manifest["mcpServers"]


def test_release_builder_includes_codex_runtime_files():
    release_script = (ROOT / "scripts/make-release.sh").read_text(encoding="utf-8")

    assert '".codex-plugin"' in release_script
    assert '".mcp.json"' in release_script
