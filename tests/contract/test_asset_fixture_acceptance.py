"""Consume independently frozen asset inputs through the public CLI.

This checks synthetic local state only. No backend helpers prepare expected answers.
The native Vault inventory belongs to separate host-behavior acceptance, not this CLI.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "assets"
LEGACY_MARKER = "SYNTHETIC_ONLY_LEGACY_PASSWORD_DO_NOT_USE_83A7"


@dataclass(frozen=True)
class AssetScope:
    state: Path
    ledger: Path
    new_spec: Path
    update_spec: Path
    runner: CliRunner


def _no_secret(text: str, caplog: pytest.LogCaptureFixture) -> None:
    if LEGACY_MARKER in text or LEGACY_MARKER in caplog.text:
        caplog.clear()
        pytest.fail("Asset CLI exposed the forbidden synthetic credential marker")


def _invoke(
    scope: AssetScope,
    caplog: pytest.LogCaptureFixture,
    *arguments: str,
    expected_exit: int = 0,
):
    result = scope.runner.invoke(
        main,
        list(arguments),
        env={"SCHOLAR_WORKFLOW_HOME": str(scope.state)},
    )
    _no_secret(result.output, caplog)
    if result.exception is not None:
        _no_secret(str(result.exception), caplog)
    assert result.exit_code == expected_exit, result.output
    return result


def _json(scope: AssetScope, caplog: pytest.LogCaptureFixture, *arguments: str):
    return json.loads(_invoke(scope, caplog, *arguments, "--format", "json").output)


def _records(path: Path) -> dict[str, dict]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))["servers"]
    aliases = [row["alias"] for row in rows]
    assert len(aliases) == len(set(aliases)), "Registration created duplicate aliases"
    return {row["alias"]: row for row in rows}


def _same_private_record(left: dict, right: dict) -> None:
    # Avoid including even the synthetic secret in assertion failure diagnostics.
    if left != right:
        pytest.fail("Registration unexpectedly changed a protected existing record")


@pytest.fixture
def asset_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AssetScope:
    # macOS temporary directories may be reached through /var or /tmp symlinks.
    root = tmp_path.resolve(strict=True)
    state = root / "state"
    ledger_root = root / "private-ledger"
    ledger_root.mkdir(mode=0o700)
    ledger = ledger_root / "servers.yaml"
    shutil.copyfile(FIXTURES / "servers.yaml", ledger)
    ledger.chmod(0o600)
    new_spec, update_spec = root / "server-new.json", root / "server-update.json"
    shutil.copyfile(FIXTURES / "server-new.json", new_spec)
    shutil.copyfile(FIXTURES / "server-update.json", update_spec)
    runner = CliRunner()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Synthetic asset acceptance attempted network or process execution")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for name in ("SYNTHETIC_GPU_PASSWORD", "SYNTHETIC_CPU_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    environment = {"SCHOLAR_WORKFLOW_HOME": str(state)}
    initialized = runner.invoke(main, ["config", "init"], env=environment)
    assert initialized.exit_code == 0, initialized.output
    configured = runner.invoke(
        main,
        ["config", "set", "env_records_root", str(ledger_root)],
        env=environment,
    )
    assert configured.exit_code == 0, configured.output
    return AssetScope(state, ledger, new_spec, update_spec, runner)


def test_raw_fixture_list_show_and_check_never_leak_or_write(
    asset_scope: AssetScope, caplog: pytest.LogCaptureFixture,
):
    original = asset_scope.ledger.read_bytes()
    for kind in ("server", "all"):
        result = _invoke(
            asset_scope, caplog, "assets", "list", "--kind", kind,
            "--format", "md", "--language", "zh",
        )
        assert "synthetic-gpu" in result.output
        assert "192.0.2.10" in result.output
        payload = _json(asset_scope, caplog, "assets", "list", "--kind", kind)
        assert "synthetic-gpu" in json.dumps(payload)
    shown = _json(asset_scope, caplog, "assets", "server", "show", "synthetic-gpu")
    serialized = json.dumps(shown)
    for expected in ("synthetic-gpu", "192.0.2.10", "researcher", "2222", "research"):
        assert expected in serialized
    _json(asset_scope, caplog, "assets", "server", "check")
    assert asset_scope.ledger.read_bytes() == original
    assert not (asset_scope.ledger.parent / "apis.yaml").exists()
    assert not (asset_scope.ledger.parent / "setup").exists()


def test_raw_registration_fixture_is_new_then_byte_idempotent(
    asset_scope: AssetScope, caplog: pytest.LogCaptureFixture,
):
    protected = _records(asset_scope.ledger)["synthetic-gpu"]
    _json(
        asset_scope, caplog, "assets", "server", "register",
        "--spec", str(asset_scope.new_spec),
    )
    first_bytes = asset_scope.ledger.read_bytes()
    records = _records(asset_scope.ledger)
    assert set(records) == {"synthetic-gpu", "synthetic-cpu"}
    _same_private_record(protected, records["synthetic-gpu"])
    expected = json.loads(asset_scope.new_spec.read_text(encoding="utf-8"))
    for field, value in expected.items():
        assert records["synthetic-cpu"][field] == value

    repeated = _json(
        asset_scope, caplog, "assets", "server", "register",
        "--spec", str(asset_scope.new_spec),
    )
    assert repeated["status"] == "unchanged"
    assert asset_scope.ledger.read_bytes() == first_bytes
    shown = _json(asset_scope, caplog, "assets", "server", "show", "synthetic-cpu")
    assert "198.51.100.20" in json.dumps(shown)
    assert asset_scope.ledger.stat().st_mode & 0o777 == 0o600


def test_raw_update_fixture_preserves_legacy_and_refuses_stale_revision(
    asset_scope: AssetScope, caplog: pytest.LogCaptureFixture,
):
    original = _records(asset_scope.ledger)["synthetic-gpu"]
    current = _json(asset_scope, caplog, "assets", "server", "show", "synthetic-gpu")
    revision = current["revision"]
    assert isinstance(revision, str) and revision
    _json(
        asset_scope, caplog, "assets", "server", "register",
        "--spec", str(asset_scope.update_spec), "--expected-revision", revision,
    )
    updated = _records(asset_scope.ledger)
    assert set(updated) == {"synthetic-gpu"}
    expected = json.loads(asset_scope.update_spec.read_text(encoding="utf-8"))
    for field, value in expected.items():
        assert updated["synthetic-gpu"][field] == value
    if updated["synthetic-gpu"].get("password") != original["password"]:
        pytest.fail("Safe metadata update lost or changed the legacy credential")
    assert "password" not in expected
    after_success = asset_scope.ledger.read_bytes()

    # A different old-revision request is not identical-repeat compatibility.
    stale_spec = asset_scope.update_spec.parent / "server-stale.json"
    stale_spec.write_text(json.dumps({
        "alias": "synthetic-gpu", "purpose": "Must not overwrite the newer revision",
    }), encoding="utf-8")
    _invoke(
        asset_scope, caplog, "assets", "server", "register",
        "--spec", str(stale_spec), "--expected-revision", revision,
        "--format", "json", expected_exit=7,
    )
    assert asset_scope.ledger.read_bytes() == after_success
    current_after = _json(
        asset_scope, caplog, "assets", "server", "show", "synthetic-gpu",
    )
    assert current_after["revision"] != revision


def test_raw_knowledge_fixture_retains_original_source_and_field_ids(
    asset_scope: AssetScope, caplog: pytest.LogCaptureFixture,
):
    inventory = json.loads((FIXTURES / "knowledge-inventory.json").read_text(encoding="utf-8"))
    selected = inventory["registered_sources"][0]
    manifest = yaml.safe_load((FIXTURES / selected["manifest_fixture"]).read_text(encoding="utf-8"))
    root = asset_scope.state.parent / "synthetic-vault-a" / "World Models"
    (root / ".scholar-workflow").mkdir(parents=True)
    portable = root / ".scholar-workflow" / "fields.yml"
    shutil.copyfile(FIXTURES / selected["manifest_fixture"], portable)
    (root / "00-Overview.md").write_text("# Synthetic World Models\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(asset_scope.state / "hub" / "sources.json")
    registry.path.parent.mkdir(parents=True, exist_ok=True)
    document = KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="synthetic-world-models", root=root, capabilities=["read"])],
        sources=[KnowledgeSourceRegistration(
            source_id=selected["source_id"], folder_id="synthetic-world-models",
            enabled=selected["enabled"], capabilities=["read"],
        )],
    )
    registry.path.write_text(json.dumps(document.model_dump(mode="json")), encoding="utf-8")
    protected_manifest = portable.read_bytes()
    protected_registry = registry.path.read_bytes()
    payload = _json(asset_scope, caplog, "assets", "list", "--kind", "knowledge")
    serialized = json.dumps(payload)
    assert manifest["source_id"] in serialized
    assert manifest["fields"][0]["field_id"] in serialized
    assert "Synthetic World Models" in serialized
    assert "synthetic-native-b" not in serialized
    assert portable.read_bytes() == protected_manifest
    assert registry.path.read_bytes() == protected_registry
