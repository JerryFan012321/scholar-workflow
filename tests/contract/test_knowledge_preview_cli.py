from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow.cli import main


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def _preview(root: Path, state: Path, *options: str):
    return CliRunner().invoke(
        main,
        ["knowledge", "preview", str(root), *options],
        env={"SCHOLAR_WORKFLOW_HOME": str(state)},
    )


def test_preview_complete_navigation_zero_writes(tmp_path: Path):
    root = tmp_path / "field"
    root.mkdir()
    for name in ("README.md", "A.md", "B.md"):
        (root / name).write_text(f"# {name}\n", encoding="utf-8")
    before = _files(root)
    state = tmp_path / "state"
    result = _preview(root, state, "--format", "json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "preview-only"
    assert "candidate_token" not in payload["preview"]
    field = payload["preview"]["fields"][0]
    assert field["home"] == "README.md"
    assert [item for group in field["navigation"] for item in group["items"]] == [
        "README.md",
        "A.md",
        "B.md",
    ]
    assert _files(root) == before
    assert not (root / ".scholar-workflow").exists()
    assert not state.exists()


def test_empty_preview_explains_no_candidate(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir()
    result = _preview(root, tmp_path / "state", "--language", "zh")
    assert result.exit_code == 0, result.output
    assert "没有可用候选" in result.output
    assert "没有登记、改写或创建首页" in result.output
    assert list(root.iterdir()) == []


def test_external_owner_excluded(tmp_path: Path):
    root = tmp_path / "field"
    root.mkdir()
    (root / "README.md").write_text("# Field\n")
    (root / "source.md").write_text(
        "---\nzotflow-locked: true\nzotero-key: ABCD2345\nlibrary-id: 123\n---\n# Source\n"
    )
    result = _preview(root, tmp_path / "state", "--format", "json")
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)["preview"]
    assert preview["external_managed_documents"] == [
        {"relative_path": "source.md", "owner": "zotflow"}
    ]
    assert preview["fields"][0]["navigation"][0]["items"] == ["README.md"]


def test_existing_manifest_only_host_registration(tmp_path: Path):
    root = tmp_path / "field"
    (root / ".scholar-workflow").mkdir(parents=True)
    (root / "README.md").write_text("# Field\n")
    manifest = {
        "schema_version": 1,
        "source_id": "00000000-0000-4000-8000-000000000001",
        "fields": [
            {
                "field_id": "00000000-0000-4000-8000-000000000002",
                "title": "Field",
                "relative_root": ".",
                "home": "README.md",
                "navigation": [],
            }
        ],
    }
    (root / ".scholar-workflow/fields.yml").write_text(yaml.safe_dump(manifest))
    before = _files(root)
    result = _preview(root, tmp_path / "state", "--format", "json")
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)["preview"]
    assert preview["registration_only"] is True
    assert preview["source_id"] == manifest["source_id"]
    assert preview["registered_fields"] == manifest["fields"]
    assert _files(root) == before


def _registry(state: Path, root: Path, source_id: str) -> Path:
    path = state / "hub/sources.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "folders": [{"folder_id": "folder_test", "root": str(root)}],
                "sources": [{"source_id": source_id, "folder_id": "folder_test"}],
            }
        )
    )
    return path


def test_registered_identity_preserved_and_registry_unchanged(tmp_path: Path):
    root = tmp_path / "field"
    (root / ".scholar-workflow").mkdir(parents=True)
    (root / "README.md").write_text("# Field\n")
    source_id = "00000000-0000-4000-8000-000000000001"
    (root / ".scholar-workflow/fields.yml").write_text(
        yaml.safe_dump(
            {
                "source_id": source_id,
                "fields": [
                    {
                        "field_id": "00000000-0000-4000-8000-000000000002",
                        "title": "Field",
                        "relative_root": ".",
                        "home": "README.md",
                    }
                ],
            }
        )
    )
    state = tmp_path / "state"
    registry = _registry(state, root, source_id)
    before = _files(tmp_path)
    result = _preview(root, state, "--format", "json")
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)["preview"]
    assert preview["source_id"] == source_id
    assert preview["registration_only"] is False
    # The provider retains its initialization gate when there is no new Field.
    assert preview["conflicts"] == ["No unregistered Markdown Field candidate was found"]
    assert registry.is_file()
    assert _files(tmp_path) == before


def test_overlapping_source_is_reported_not_registered(tmp_path: Path):
    root = tmp_path / "parent/field"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Field\n")
    state = tmp_path / "state"
    _registry(state, root.parent, "00000000-0000-4000-8000-000000000001")
    before = _files(tmp_path)
    result = _preview(root, state, "--format", "json")
    assert result.exit_code == 0, result.output
    assert "overlaps registered Source" in json.loads(result.output)["preview"]["conflicts"][0]
    assert _files(tmp_path) == before


@pytest.mark.parametrize("bad", ["relative", "symlink", "manifest"])
def test_invalid_preview_refuses_without_write(tmp_path: Path, bad: str):
    root = tmp_path / "field"
    root.mkdir()
    (root / "README.md").write_text("# Field\n")
    if bad == "relative":
        root = Path("relative-field")
    elif bad == "symlink":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    else:
        (root / ".scholar-workflow").mkdir()
        (root / ".scholar-workflow/fields.yml").write_text("schema_version: 999\n")
    state = tmp_path / "state"
    result = _preview(root, state)
    assert result.exit_code == 7, result.output
    assert "Traceback" not in result.output
    assert not state.exists()


def test_markdown_metadata_is_escaped(tmp_path: Path):
    root = tmp_path / "<b>[Field](bad)"
    root.mkdir()
    (root / "README.md").write_text("# Field\n")
    result = _preview(root, tmp_path / "state")
    assert result.exit_code == 0, result.output
    assert "<b>" not in result.output
    assert "[Field](bad)" not in result.output


@pytest.mark.parametrize("option,value", [("--language", "de"), ("--format", "html")])
def test_unknown_presentation_option_rejected(tmp_path: Path, option: str, value: str):
    root = tmp_path / "field"
    root.mkdir()
    result = _preview(root, tmp_path / "state", option, value)
    assert result.exit_code == 2
    assert list(root.iterdir()) == []
