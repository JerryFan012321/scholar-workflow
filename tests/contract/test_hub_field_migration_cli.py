"""The Field migration CLI requires a fresh, explicit digest confirmation."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

import scholar_workflow.hub.field_migration as migration_module
from scholar_workflow.cli import main
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry

_LEGACY = "http://127.0.0.1:23128/open/paper/ABCD2345"
_STABLE = "zotero://open-pdf/library/items/ABCD2345"


@pytest.fixture(autouse=True)
def verified_fixture_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolver(key: str) -> str:
        assert key == "ABCD2345"
        return _STABLE

    monkeypatch.setattr(migration_module, "ZoteroPdfLinkResolver", lambda: resolver)


def _registered_field(tmp_path: Path) -> tuple[Path, str, str, Path]:
    selected = tmp_path / "selected-field"
    selected.mkdir()
    home = selected / "00-领域入口.md"
    home.write_text(f"# Field\n\n[Paper]({_LEGACY})\n", encoding="utf-8")
    (selected / "analysis.md").write_text(f"Read {_LEGACY}\n", encoding="utf-8")
    hub_root = tmp_path / "home" / "hub"
    registry = KnowledgeSourceRegistry(hub_root / "sources.json")
    service = FieldService(registry)
    preview = service.preview(selected)
    manifest = service.confirm(preview.candidate_token, preview.fields[0].field_id)
    return selected, manifest.source_id, manifest.fields[0].field_id, hub_root


def test_field_migration_cli_requires_fresh_approved_digest(tmp_path: Path) -> None:
    selected, source_id, field_id, hub_root = _registered_field(tmp_path)
    args = ["hub", "field-migration"]
    env = {"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "home")}
    runner = CliRunner()

    planned = runner.invoke(main, [*args, "plan", source_id, field_id], env=env)

    assert planned.exit_code == 0, planned.output
    plan = json.loads(planned.output)
    assert "plan_token" not in plan
    assert plan["managed_files"] == ["00-领域入口.md", "analysis.md"]
    assert sum(item["occurrences"] for item in plan["link_changes"]) == 2
    assert plan["unresolved_legacy_links"] == []
    assert plan["template_normalization"] == "manual-review-required"
    assert not (hub_root / "field-migration-private").exists()

    stale = runner.invoke(
        main,
        [*args, "apply", source_id, field_id, "--approved-digest", "sha256:wrong"],
        env=env,
    )
    assert stale.exit_code != 0
    assert "review a fresh plan_digest" in stale.output
    assert _LEGACY in (selected / "00-领域入口.md").read_text(encoding="utf-8")
    assert not (hub_root / "field-migration-private").exists()

    missing_pause = runner.invoke(
        main,
        [*args, "apply", source_id, field_id, "--approved-digest", plan["plan_digest"]],
        env=env,
    )
    assert missing_pause.exit_code != 0
    assert "External Field writers must be paused" in missing_pause.output
    assert not (hub_root / "field-migration-private").exists()

    declined = runner.invoke(
        main,
        [
            *args,
            "apply",
            source_id,
            field_id,
            "--approved-digest",
            plan["plan_digest"],
            "--external-writers-paused",
        ],
        env=env,
        input="n\n",
    )
    assert declined.exit_code != 0
    assert "not confirmed" in declined.output
    assert not (hub_root / "field-migration-private").exists()

    approved = runner.invoke(
        main,
        [
            *args,
            "apply",
            source_id,
            field_id,
            "--approved-digest",
            plan["plan_digest"],
            "--external-writers-paused",
        ],
        env=env,
        input="y\n",
    )

    assert approved.exit_code == 0, approved.output
    result = json.loads(approved.output.splitlines()[-1])
    assert result["changed_files"] == ["00-领域入口.md", "analysis.md"]
    assert result["replaced_links"] == 2
    assert result["recovery_is_verified_backup"] is False
    assert Path(result["recovery_snapshot"]).is_file()
    assert stat.S_IMODE(Path(result["recovery_snapshot"]).stat().st_mode) == 0o600
    assert _STABLE in (selected / "00-领域入口.md").read_text(encoding="utf-8")
    assert _LEGACY not in (selected / "analysis.md").read_text(encoding="utf-8")


def test_field_migration_cli_rejects_digest_after_user_edit(tmp_path: Path) -> None:
    selected, source_id, field_id, hub_root = _registered_field(tmp_path)
    args = ["hub", "field-migration"]
    env = {"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "home")}
    runner = CliRunner()
    planned = runner.invoke(main, [*args, "plan", source_id, field_id], env=env)
    digest = json.loads(planned.output)["plan_digest"]
    changed = selected / "analysis.md"
    changed.write_text(f"User edit {_LEGACY}\n", encoding="utf-8")

    result = runner.invoke(
        main,
        [*args, "apply", source_id, field_id, "--approved-digest", digest],
        env=env,
    )

    assert result.exit_code != 0
    assert "review a fresh plan_digest" in result.output
    assert changed.read_text(encoding="utf-8") == f"User edit {_LEGACY}\n"
    assert not (hub_root / "field-migration-private").exists()


def test_field_migration_cli_explicit_recover_is_idempotent_without_journal(
    tmp_path: Path,
) -> None:
    selected, source_id, field_id, hub_root = _registered_field(tmp_path)
    result = CliRunner().invoke(
        main,
        ["hub", "field-migration", "recover", source_id, field_id],
        env={"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["recovered_files"] == []
    assert payload["recovery_snapshot"] is None
    assert payload["recovery_is_verified_backup"] is False
    assert _LEGACY in (selected / "00-领域入口.md").read_text(encoding="utf-8")
    assert not (hub_root / "field-migration-private").exists()


def test_field_migration_cli_reports_offline_zotero_as_plan_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected, source_id, field_id, hub_root = _registered_field(tmp_path)

    def offline(_key: str) -> str:
        raise migration_module.FieldMigrationError("Zotero Local API is unavailable")

    monkeypatch.setattr(migration_module, "ZoteroPdfLinkResolver", lambda: offline)
    args = ["hub", "field-migration"]
    env = {"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "home")}
    runner = CliRunner()

    planned = runner.invoke(main, [*args, "plan", source_id, field_id], env=env)
    assert planned.exit_code == 0, planned.output
    plan = json.loads(planned.output)
    assert any("ABCD2345" in conflict and "unavailable" in conflict for conflict in plan["conflicts"])
    attempted = runner.invoke(
        main,
        [*args, "apply", source_id, field_id, "--approved-digest", plan["plan_digest"]],
        env=env,
    )
    assert attempted.exit_code != 0
    assert _LEGACY in (selected / "00-领域入口.md").read_text(encoding="utf-8")
    assert not (hub_root / "field-migration-private").exists()


def test_field_migration_cli_rejects_analysis_sidecar_without_partial_write(
    tmp_path: Path,
) -> None:
    selected, source_id, field_id, hub_root = _registered_field(tmp_path)
    (selected / "analysis.analysis.json").write_text("{}", encoding="utf-8")
    home_before = (selected / "00-领域入口.md").read_bytes()
    analysis_before = (selected / "analysis.md").read_bytes()
    args = ["hub", "field-migration"]
    env = {"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "home")}
    runner = CliRunner()

    planned = runner.invoke(main, [*args, "plan", source_id, field_id], env=env)

    assert planned.exit_code == 0, planned.output
    plan = json.loads(planned.output)
    assert any(
        "analysis.md" in conflict and "validated Field transaction" in conflict
        for conflict in plan["conflicts"]
    )
    attempted = runner.invoke(
        main,
        [*args, "apply", source_id, field_id, "--approved-digest", plan["plan_digest"]],
        env=env,
    )
    assert attempted.exit_code != 0
    assert (selected / "00-领域入口.md").read_bytes() == home_before
    assert (selected / "analysis.md").read_bytes() == analysis_before
    assert not (hub_root / "field-migration-private").exists()
