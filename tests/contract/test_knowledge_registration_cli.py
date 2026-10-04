from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow.cli import main


def invoke(state: Path, *args: str, input: str | None = None):
    return CliRunner().invoke(main, ["knowledge", *args], input=input,
                              env={"SCHOLAR_WORKFLOW_HOME": str(state)})


def prepare(tmp_path: Path):
    root = tmp_path / "field"
    root.mkdir()
    for name in ("README.md", "A.md", "B.md"):
        (root / name).write_text(f"# {name}\n", encoding="utf-8")
    return root, tmp_path / "state"


def plan(root: Path, state: Path, *args: str):
    result = invoke(state, "registration-plan", str(root), *args, "--format", "json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def register(root: Path, state: Path, digest: str, *args: str, input: str = "y\n"):
    return invoke(state, "register", str(root), *args, "--approved-digest", digest,
                  "--format", "json", input=input)


def test_cross_process_plan_register_list_preserves_bytes(tmp_path: Path):
    root, state = prepare(tmp_path)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    first = plan(root, state, "--field-root", ".")
    second = plan(root, state, "--field-root", ".")
    assert first["approved_digest"] == second["approved_digest"]
    assert first["status"] == "ready-for-confirmation"
    assert "candidate_token" not in first
    assert not state.exists()
    assert not (root / ".scholar-workflow").exists()
    result = register(root, state, first["approved_digest"], "--field-root", ".")
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output[result.output.index("{"):])
    assert receipt["status"] == "registered"
    manifest = yaml.safe_load((root / ".scholar-workflow/fields.yml").read_text())
    assert receipt["manifest"] == manifest
    assert len(manifest["fields"]) == 1
    assert [item for group in manifest["fields"][0]["navigation"]
            for item in group["items"]] == ["README.md", "A.md", "B.md"]
    assert all((root / name).read_bytes() == content for name, content in before.items())
    assert (state / "hub/sources.json").is_file()
    listed = invoke(state, "list", "--format", "json")
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["fields"][0]["field_id"] == manifest["fields"][0]["field_id"]


def test_choose_one_field_not_siblings(tmp_path: Path):
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    for name in ("one", "two"):
        (root / name).mkdir()
        (root / name / "README.md").write_text(f"# {name}\n")
    state = tmp_path / "state"
    first = plan(root, state, "--field-root", "two")
    result = register(root, state, first["approved_digest"], "--field-root", "two")
    assert result.exit_code == 0, result.output
    manifest = yaml.safe_load((root / ".scholar-workflow/fields.yml").read_text())
    assert [field["relative_root"] for field in manifest["fields"]] == ["two"]


@pytest.mark.parametrize("name,content", [
    ("旧分析.md", "# old"),
    ("旧解析树.canvas", "{}"),
    ("old.md", "<!-- sw-analysis-field -->"),
    ("analysis.md", "---\nsw_kind: paper-analysis\n---\n"),
    ("arbitrary.json", '{"artifact_id":"analysis:a","document":{},"claims":{}}'),
    ("analysis.baseline.json", "{}"),
    ("note.md", "http://127.0.0.1:23128/open/paper/ABCD2345"),
    ("note.canvas", '{"text":"http://127.0.0.1:23128/hub/item?a"}'),
])
def test_simple_registration_cannot_skip_joint_review(tmp_path: Path, name: str, content: str):
    root, state = prepare(tmp_path)
    (root / name).write_text(content)
    first = plan(root, state, "--field-root", ".")
    assert first["status"] == "blocked"
    assert first["transaction_reasons"]
    result = register(root, state, first["approved_digest"], "--field-root", ".")
    assert result.exit_code == 7, result.output
    assert not state.exists()
    assert not (root / ".scholar-workflow").exists()


@pytest.mark.parametrize("change", ["markdown", "canvas", "json", "registry", "inode", "manifest"])
def test_stale_digest_refuses(tmp_path: Path, change: str):
    root, state = prepare(tmp_path)
    (root / "metadata.json").write_text('{"a":1}')
    (root / "drawing.canvas").write_text('{"nodes":[],"edges":[]}')
    first = plan(root, state, "--field-root", ".")
    if change == "markdown":
        (root / "A.md").write_text("new")
    elif change == "canvas":
        (root / "drawing.canvas").write_text('{"nodes":[1],"edges":[]}')
    elif change == "json":
        (root / "metadata.json").write_text('{"a":2}')
    elif change == "inode":
        root.rename(tmp_path / "old")
        root.mkdir()
        for path in (tmp_path / "old").iterdir():
            (root / path.name).write_bytes(path.read_bytes())
    elif change == "manifest":
        (root / ".scholar-workflow").mkdir()
        (root / ".scholar-workflow/fields.yml").write_text("invalid: true")
    else:
        (state / "hub").mkdir(parents=True)
        (state / "hub/sources.json").write_text('{"schema_version":1,"folders":[],"sources":[]}')
    result = register(root, state, first["approved_digest"], "--field-root", ".")
    assert result.exit_code == 7, result.output
    if change != "manifest":
        assert not (root / ".scholar-workflow/fields.yml").exists()


def test_cancel_and_bad_digest_zero_writes(tmp_path: Path):
    root, state = prepare(tmp_path)
    first = plan(root, state, "--field-root", ".")
    result = register(root, state, first["approved_digest"], "--field-root", ".", input="n\n")
    assert result.exit_code != 0
    result = register(root, state, "0" * 64, "--field-root", ".")
    assert result.exit_code == 7
    assert not state.exists()
    assert not (root / ".scholar-workflow").exists()


@pytest.mark.parametrize("args", [[], ["--field-root", "unknown"],
                                  ["--field-root", ".", "--existing-source"]])
def test_explicit_scope_required(tmp_path: Path, args: list[str]):
    root, state = prepare(tmp_path)
    result = invoke(state, "registration-plan", str(root), *args)
    assert result.exit_code in {2, 7}
    assert not state.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "fifo", "utf8", "oversized"])
def test_unsafe_inventory_refuses(tmp_path: Path, kind: str):
    import os

    root, state = prepare(tmp_path)
    if kind == "file":
        (root / "linked.json").symlink_to(root / "README.md")
    elif kind == "directory":
        (root / "linked").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "fifo":
        os.mkfifo(root / "fifo.json")
    elif kind == "utf8":
        (root / "bad.json").write_bytes(b"\xff")
    else:
        (root / "big.json").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    result = invoke(state, "registration-plan", str(root), "--field-root", ".", "--format", "json")
    if result.exit_code == 0:
        first = json.loads(result.output)
        assert first["status"] == "blocked"
        result = register(root, state, first["approved_digest"], "--field-root", ".")
    assert result.exit_code == 7
    assert not state.exists()


def test_existing_source_attach_preserves_portable_identity(tmp_path: Path):
    root, state = prepare(tmp_path)
    first = plan(root, state, "--field-root", ".")
    assert register(root, state, first["approved_digest"], "--field-root", ".").exit_code == 0
    original = (root / ".scholar-workflow/fields.yml").read_bytes()
    other = tmp_path / "other-state"
    attach = plan(root, other, "--existing-source")
    assert attach["mode"] == "existing-source"
    result = register(root, other, attach["approved_digest"], "--existing-source")
    assert result.exit_code == 0, result.output
    assert (root / ".scholar-workflow/fields.yml").read_bytes() == original
    assert json.loads((state / "hub/sources.json").read_text()) == json.loads(
        (other / "hub/sources.json").read_text())
