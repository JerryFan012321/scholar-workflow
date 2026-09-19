import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_host_manifests_share_identity_version_without_bundled_mcp():
    claude_manifest = _load_json(".claude-plugin/plugin.json")
    codex_manifest = _load_json(".codex-plugin/plugin.json")

    assert codex_manifest["name"] == claude_manifest["name"]
    assert codex_manifest["version"] == claude_manifest["version"]
    assert codex_manifest["skills"] == "./skills/"
    assert "mcpServers" not in codex_manifest
    assert "mcpServers" not in claude_manifest
    assert not (ROOT / ".mcp.json").exists()


def test_release_builder_includes_codex_runtime_files():
    release_script = (ROOT / "scripts/make-release.sh").read_text(encoding="utf-8")

    assert '".codex-plugin"' in release_script
    assert '".mcp.json"' not in release_script


def test_marketplace_entry_has_current_codex_metadata():
    marketplace = _load_json(".claude-plugin/marketplace.json")
    entry = next(
        plugin
        for plugin in marketplace["plugins"]
        if plugin["name"] == "scholar-workflow"
    )

    assert marketplace["interface"]["displayName"]
    assert entry["source"] == {
        "source": "github",
        "repo": "JerryFan012321/scholar-workflow",
        "ref": "release",
    }
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert entry["category"] == "Education & Research"


def test_skill_inventory_uses_collaboration_not_review_workflows():
    skill_names = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}

    assert "agent-collaboration" in skill_names
    assert "init-project" in skill_names
    assert skill_names.isdisjoint({"project-review", "code-review"})
