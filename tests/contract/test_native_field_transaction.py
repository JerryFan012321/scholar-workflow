"""Native Field operations retain the existing transaction without a Hub session.

All inputs are synthetic, under tmp_path. No personal registry, HTTP listener,
cmux, Zotero connection, or formal Vault is used by these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.workflows.field_transaction import LocalFieldTransactions


def _registered_source(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    for title in ("Existing", "Selected"):
        (vault / title).mkdir()
        (vault / title / "README.md").write_text(f"# {title}\n", encoding="utf-8")
    state = tmp_path / "state"
    registry = KnowledgeSourceRegistry(state / "hub" / "sources.json")
    fields = FieldService(registry)
    preview = fields.preview(vault)
    existing = next(row for row in preview.fields if row.relative_root == "Existing")
    manifest = fields.confirm(preview.candidate_token, existing.field_id)
    workflow = LocalFieldTransactions(
        registry, state_root=state / "runtime" / "field-transactions-private"
    )
    return vault, state, registry, manifest, workflow


def test_native_plan_apply_survives_a_fresh_process_without_session(tmp_path: Path):
    vault, _state, registry, manifest, workflow = _registered_source(tmp_path)
    before = (vault / ".scholar-workflow" / "fields.yml").read_bytes()
    planned = workflow.plan(source_id=manifest.source_id, field_root="Selected")
    assert (vault / ".scholar-workflow" / "fields.yml").read_bytes() == before
    assert not workflow.state_root.exists()
    assert "plan_token" not in planned["plan"]
    assert planned["request"]["field"]["relative_root"] == "Selected"

    restarted = LocalFieldTransactions(registry, state_root=workflow.state_root)
    result = restarted.apply(
        json.loads(json.dumps(planned)), approved_digest=planned["plan"]["plan_digest"],
        external_writers_paused=True,
    )
    loaded = FieldService._load_manifest(vault)
    assert loaded.source_id == manifest.source_id
    assert {field.relative_root for field in loaded.fields} == {"Existing", "Selected"}
    assert result.field_id == planned["request"]["field"]["field_id"]
    assert result.recovery_is_verified_backup is False
    assert result.recovery_snapshot.is_file()


def test_native_apply_rejects_changed_bytes_and_missing_pause(tmp_path: Path):
    vault, _, _, manifest, workflow = _registered_source(tmp_path)
    planned = workflow.plan(source_id=manifest.source_id, field_root="Selected")
    with pytest.raises(ValueError, match="writers must be paused"):
        workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"])
    (vault / "Selected" / "README.md").write_text("# Human edit\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed.*fresh plan"):
        workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                       external_writers_paused=True)
    assert not workflow.state_root.exists()
    assert len(FieldService._load_manifest(vault).fields) == 1


def test_native_registered_selection_never_falls_back_to_unknown_root(tmp_path: Path):
    vault, _, _, _, workflow = _registered_source(tmp_path)
    with pytest.raises(ValueError, match="unknown or disabled"):
        workflow.plan(source_id="00000000-0000-0000-0000-000000000001", field_root="Selected")
    with pytest.raises(ValueError, match="exactly one"):
        workflow.plan(root=vault, source_id="00000000-0000-0000-0000-000000000001")


def test_native_registered_read_only_source_cannot_be_upgraded(tmp_path: Path):
    _, _, registry, manifest, workflow = _registered_source(tmp_path)
    document = registry.load_document()
    source = document.sources[0].model_copy(update={"capabilities": ["read"]})
    registry.save(document.model_copy(update={"sources": [source]}))
    before = registry.path.read_bytes()
    with pytest.raises(ValueError, match="does not allow write"):
        workflow.plan(source_id=manifest.source_id, field_root="Selected")
    assert registry.path.read_bytes() == before
    assert not workflow.state_root.exists()


@pytest.mark.parametrize("read_only_owner", ["source", "folder"])
def test_native_explicit_root_cannot_bypass_registered_read_only_capability(
    tmp_path: Path, read_only_owner: str,
):
    vault, _, registry, _, workflow = _registered_source(tmp_path)
    document = registry.load_document()
    if read_only_owner == "source":
        document = document.model_copy(update={"sources": [
            document.sources[0].model_copy(update={"capabilities": ["read"]})
        ]})
    else:
        document = document.model_copy(update={"folders": [
            document.folders[0].model_copy(update={"capabilities": ["read"]})
        ]})
    registry.save(document)
    before_registry = registry.path.read_bytes()
    before_manifest = (vault / ".scholar-workflow" / "fields.yml").read_bytes()
    with pytest.raises(ValueError, match="registered (Source|folder) conflicts"):
        workflow.plan(root=vault, field_root="Selected")
    assert registry.path.read_bytes() == before_registry
    assert (vault / ".scholar-workflow" / "fields.yml").read_bytes() == before_manifest
    assert not workflow.state_root.exists()


def test_native_dotdot_root_refuses_in_vault_state_before_creating_it(tmp_path: Path):
    vault, _, registry, _, _ = _registered_source(tmp_path)
    (tmp_path / "detour").mkdir()
    selected = tmp_path / "detour" / ".." / "vault"
    state = vault / "runtime" / "private"
    workflow = LocalFieldTransactions(registry, state_root=state)
    reviewed = workflow.plan(root=selected, field_root="Selected")
    assert reviewed["request"]["root"] == str(vault)
    with pytest.raises(ValueError, match="outside the Vault"):
        workflow.apply(reviewed, approved_digest=reviewed["plan"]["plan_digest"],
                       external_writers_paused=True)
    assert not (vault / "runtime").exists()
    assert not state.exists()


def test_native_dotdot_cannot_hide_a_symlink_ancestor(tmp_path: Path):
    vault, _, _, _, workflow = _registered_source(tmp_path)
    (tmp_path / "detour").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "detour", target_is_directory=True)
    selected = tmp_path / "alias" / ".." / "vault"
    with pytest.raises(ValueError, match="symlink|unsafe"):
        workflow.plan(root=selected, field_root="Selected")
    assert (vault / "Selected" / "README.md").read_text() == "# Selected\n"
    assert not workflow.state_root.exists()


def test_native_local_proposal_keeps_reviewed_relocation_and_link_rewrites(tmp_path: Path):
    vault, _, _, manifest, workflow = _registered_source(tmp_path)
    selected = vault / "Selected"
    (selected / "Note.md").write_text("# A retained note\n", encoding="utf-8")
    (selected / "README.md").write_text("# Selected\n\n[Note](Note.md)\n", encoding="utf-8")
    initial = workflow.plan(source_id=manifest.source_id, field_root="Selected")
    field = initial["request"]["field"]
    for group in field["navigation"]:
        group["items"] = ["notes/Note.md" if item == "Note.md" else item
                          for item in group["items"]]
    reviewed = workflow.plan(source_id=manifest.source_id, field_root="Selected", proposal={
        "field": field, "relocations": {"Note.md": "notes/Note.md"},
        "link_rewrites": {"README.md": {"Note.md": "notes/Note.md"}},
    })
    assert reviewed["plan"]["relocations"]
    workflow.apply(reviewed, approved_digest=reviewed["plan"]["plan_digest"],
                   external_writers_paused=True)
    assert not (selected / "Note.md").exists()
    assert (selected / "notes" / "Note.md").read_text() == "# A retained note\n"
    assert "[Note](notes/Note.md)" in (selected / "README.md").read_text()


def test_native_proposal_cannot_omit_freshly_inspected_documents(tmp_path: Path):
    vault, _, _, manifest, workflow = _registered_source(tmp_path)
    (vault / "Selected" / "Note.md").write_text("# Must remain owned\n", encoding="utf-8")
    initial = workflow.plan(source_id=manifest.source_id, field_root="Selected")
    field = initial["request"]["field"]
    field["navigation"] = [{"label": "Home", "items": ["README.md"]}]
    with pytest.raises(ValueError, match="omitted previewed documents"):
        workflow.plan(source_id=manifest.source_id, field_root="Selected",
                      proposal={"field": field})
    assert (vault / "Selected" / "Note.md").read_text() == "# Must remain owned\n"
    assert not workflow.state_root.exists()


def test_native_cli_replaces_hub_prerequisite_and_requires_explicit_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    import scholar_workflow.cli as cli_module

    def forbidden(*args, **kwargs):
        raise AssertionError("native operation must not contact a Hub session")

    monkeypatch.setattr(cli_module, "_managed_field_hub_record", forbidden)
    monkeypatch.setattr(cli_module, "_field_hub_request", forbidden)
    _, state, _, manifest, _ = _registered_source(tmp_path)
    runner = CliRunner()
    env = {"SCHOLAR_WORKFLOW_HOME": str(state)}
    args = ["knowledge", "field-transaction", "plan", "--source-id", manifest.source_id,
            "--field-root", "Selected"]
    result = runner.invoke(main, args, env=env)
    assert result.exit_code == 0, result.output
    planned = json.loads(result.output)
    plan_file = tmp_path / "reviewed.json"
    plan_file.write_text(json.dumps(planned), encoding="utf-8")
    applied = runner.invoke(main, ["knowledge", "field-transaction", "apply", str(plan_file),
        "--approved-digest", planned["plan"]["plan_digest"], "--external-writers-paused"],
        env=env, input="y\n")
    assert applied.exit_code == 0, applied.output
    legacy = runner.invoke(main, ["hub", "field-transaction", "plan"], env=env)
    assert legacy.exit_code != 0
    assert "knowledge field-transaction" in legacy.output
    assert "Hub session" not in legacy.output


def test_native_explicit_folder_preview_can_enroll_without_auto_discovery(tmp_path: Path):
    root = tmp_path / "chosen"
    root.mkdir()
    (root / "README.md").write_text("# Explicitly chosen Field\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "host" / "sources.json")
    workflow = LocalFieldTransactions(registry, state_root=tmp_path / "recovery")
    planned = workflow.plan(root=root, field_root=".")
    assert not registry.path.exists()
    workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                   external_writers_paused=True)
    assert registry.resolve(planned["request"]["source_id"]) == root


def test_native_recovery_keeps_existing_journal_format(tmp_path: Path):
    import scholar_workflow.knowledge.field_transaction as core

    vault, _, registry, manifest, workflow = _registered_source(tmp_path)
    planned = workflow.plan(source_id=manifest.source_id, field_root="Selected")
    original = core.FieldTransactionService._replace

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("synthetic interruption after one publication")

    def recovery_interrupted(*args, **kwargs):
        raise core.FieldTransactionError("synthetic process stopped")

    from unittest.mock import patch
    with (
        patch.object(core.FieldTransactionService, "_replace", staticmethod(interrupted)),
        patch.object(core.FieldTransactionService, "_recover_locked", recovery_interrupted),
        pytest.raises(ValueError, match="recover explicitly"),
    ):
        workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                       external_writers_paused=True)
    restarted = LocalFieldTransactions(registry, state_root=workflow.state_root)
    outcome = restarted.recover(planned["request"]["source_id"],
                                planned["request"]["field"]["field_id"],
                                external_writers_paused=True)
    assert outcome.outcome in {"rolled-back", "committed"}
    assert (vault / "Existing" / "README.md").read_text() == "# Existing\n"


def test_hub_module_names_are_identity_compatibility_aliases():
    import scholar_workflow.hub.field_migration as old_migration
    import scholar_workflow.hub.field_transaction as old_transaction
    import scholar_workflow.knowledge.field_migration as migration
    import scholar_workflow.knowledge.field_transaction as transaction

    assert old_migration is migration
    assert old_transaction is transaction
