"""End-to-end CLI contract for readable Obsidian + HubCatalog projection."""
from __future__ import annotations

import json

from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.hub.models import HubCatalog


def _payload() -> dict:
    return {
        "root": "世界模型",
        "paperlist_only": True,
        "doc": {
            "generated_at": "2026-09-18T00:00:00Z",
            "topic_id": "world-models",
            "topic": "世界模型",
            "paper_list": [
                {
                    "resource_id": "arxiv:2301.04104",
                    "title": "DreamerV3",
                    "authors": ["Danijar Hafner"],
                    "zotero_key": "S6LZUS6S",
                    "attachment_key": "ABCD2345",
                    "classified": False,
                }
            ],
            "tree": {"name": "世界模型", "kind": "topic", "children": []},
        },
    }


def test_project_literature_tree_updates_readable_note_and_catalog(tmp_path):
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    storage = tmp_path / "storage"
    home.mkdir()
    vault.mkdir()
    storage.mkdir()
    (home / "config.yml").write_text(
        "version: 1\n"
        f"research_vault_root: {vault}\n"
        "link_service:\n"
        "  port: 23128\n"
        f"  storage_root: {storage}\n",
        encoding="utf-8",
    )
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["project-literature-tree", "--input", str(input_path)],
        env={"SCHOLAR_WORKFLOW_HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    note = (vault / "世界模型" / "01-Paperlist.md").read_text(encoding="utf-8")
    assert "sw_kind: paper-list" in note
    assert "| DreamerV3 | Danijar Hafner |" in note
    catalog = HubCatalog.model_validate_json(
        (home / "hub" / "catalog.json").read_text(encoding="utf-8")
    )
    assert catalog.topics[0].topic_id == "world-models"
    assert catalog.resources[0].title == "DreamerV3"
    assert json.loads(result.output)["hub_revision"] == catalog.revision
