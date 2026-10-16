"""Synthetic public asset-command expectations; no real host records or tools."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.cli import main

SOURCE_ID = "11111111-1111-4111-8111-111111111111"
FIELD_ID = "22222222-2222-4222-8222-222222222222"


def invoke(state: Path, *args: str):
    return CliRunner().invoke(main, ["assets", *args],
                              env={"SCHOLAR_WORKFLOW_HOME": str(state)})


def config(state: Path, ledger: Path) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.yml").write_text(
        "version: 1\nenv_records_root: " + json.dumps(str(ledger)) + "\n",
        encoding="utf-8",
    )


def registered_source(state: Path, root: Path, *, available: bool = True) -> None:
    if available:
        (root / ".scholar-workflow").mkdir(parents=True)
        (root / "README.md").write_text("# Synthetic Field\n", encoding="utf-8")
        (root / ".scholar-workflow/fields.yml").write_text(
            f"schema_version: 1\nsource_id: {SOURCE_ID}\nfields:\n"
            f"  - field_id: {FIELD_ID}\n    title: Synthetic Field\n"
            "    relative_root: .\n    home: README.md\n    navigation: []\n",
            encoding="utf-8",
        )
    (state / "hub").mkdir(parents=True, exist_ok=True)
    (state / "hub/sources.json").write_text(json.dumps({
        "schema_version": 1,
        "folders": [{"folder_id": "synthetic-vault", "root": str(root),
                     "enabled": True, "capabilities": ["read"]}],
        "sources": [{"source_id": SOURCE_ID, "folder_id": "synthetic-vault",
                     "provider": "obsidian", "enabled": True,
                     "capabilities": ["read"]}],
    }), encoding="utf-8")


def test_empty_list_is_read_only_and_both_providers_remain_visible(tmp_path: Path):
    state = tmp_path / "state"
    result = invoke(state, "list", "--format", "json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload["providers"]) == {"server", "knowledge"}
    assert payload["providers"]["server"]["status"] == "unavailable"
    assert payload["providers"]["knowledge"]["status"] == "uninitialized"
    assert not state.exists()


def test_knowledge_inventory_reuses_existing_registry_and_keeps_roots(tmp_path: Path):
    state, root = tmp_path / "state", tmp_path / "vault"
    registered_source(state, root)
    before = {str(path.relative_to(tmp_path)): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file()}
    result = invoke(state, "list", "--kind", "knowledge", "--format", "json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload["providers"]) == {"knowledge"}
    provider = payload["providers"]["knowledge"]
    assert provider["status"] == "available"
    source = provider["sources"][0]
    assert source["source_id"] == SOURCE_ID
    assert source["root"] == str(root)
    assert source["fields"][0]["field_id"] == FIELD_ID
    assert source["fields"][0]["title"] == "Synthetic Field"
    assert source["status"] == "available"
    assert {str(path.relative_to(tmp_path)): path.read_bytes()
            for path in tmp_path.rglob("*") if path.is_file()} == before


def test_provider_failure_does_not_hide_other_assets(tmp_path: Path, monkeypatch):
    state, root = tmp_path / "state", tmp_path / "vault"
    registered_source(state, root)
    config(state, tmp_path / "ledger")
    from scholar_workflow.assets import servers

    monkeypatch.setattr(servers, "read_servers", lambda _root: {
        "schema_version": 1, "status": "invalid", "revision": None,
        "servers": [], "diagnostics": ["Server ledger is invalid."],
    })
    result = invoke(state, "list", "--format", "json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "partial"
    assert payload["providers"]["server"]["status"] == "invalid"
    assert payload["providers"]["knowledge"]["sources"][0]["fields"]


def test_invalid_knowledge_root_keeps_registered_source_visible(tmp_path: Path):
    state = tmp_path / "state"
    registered_source(state, tmp_path / "missing-vault", available=False)
    result = invoke(state, "list", "--kind", "knowledge", "--format", "json")
    assert result.exit_code == 0, result.output
    provider = json.loads(result.output)["providers"]["knowledge"]
    assert provider["status"] == "partial"
    assert provider["sources"][0]["source_id"] == SOURCE_ID
    assert provider["sources"][0]["status"] == "unavailable"
    assert provider["sources"][0]["diagnostics"]


def test_unavailable_field_keeps_declared_identity_and_title(tmp_path: Path, monkeypatch):
    state, root = tmp_path / "state", tmp_path / "vault"
    registered_source(state, root)
    from scholar_workflow.knowledge.fields import FieldService

    monkeypatch.setattr(FieldService, "list_fields", lambda _self: [{
        "source_id": SOURCE_ID, "field_id": FIELD_ID, "title": "Declared Field",
        "home": "README.md", "relative_root": ".", "available": False,
        "detail": "Synthetic unavailable declaration.",
    }])
    result = invoke(state, "list", "--kind", "knowledge", "--format", "json")
    assert result.exit_code == 0, result.output
    source = json.loads(result.output)["providers"]["knowledge"]["sources"][0]
    assert source["status"] == "unavailable"
    assert source["fields"][0]["field_id"] == FIELD_ID
    assert source["fields"][0]["title"] == "Declared Field"
    assert source["fields"][0]["available"] is False
    human = invoke(state, "list", "--kind", "knowledge", "--language", "zh")
    assert human.exit_code == 0, human.output
    assert "Declared Field" in human.output


def test_disabled_source_displays_declared_root_without_reading_it(tmp_path: Path, monkeypatch):
    state, root = tmp_path / "state", tmp_path / "disabled-vault"
    registered_source(state, root, available=False)
    registry = state / "hub/sources.json"
    document = json.loads(registry.read_text())
    document["sources"][0]["enabled"] = False
    registry.write_text(json.dumps(document))
    from scholar_workflow.knowledge.fields import FieldService

    def forbidden(*args, **kwargs):
        pytest.fail("Disabled Source content must not be read")

    monkeypatch.setattr(FieldService, "_load_manifest", forbidden)
    before = registry.read_bytes()
    result = invoke(state, "list", "--kind", "knowledge", "--format", "json")
    assert result.exit_code == 0, result.output
    source = json.loads(result.output)["providers"]["knowledge"]["sources"][0]
    assert source["status"] == "disabled"
    assert source["root"] == str(root)
    assert source["root_verified"] is False
    human = invoke(state, "list", "--kind", "knowledge", "--language", "zh")
    assert human.exit_code == 0, human.output
    assert str(root) in human.output and "未校验" in human.output
    assert registry.read_bytes() == before
    assert not root.exists()


def test_uninitialized_server_check_and_show_are_not_success(tmp_path: Path):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    checked = invoke(state, "server", "check", "--format", "json")
    assert checked.exit_code == 3, checked.output
    assert json.loads(checked.output)["status"] == "uninitialized"
    shown = invoke(state, "server", "show", "synthetic-gpu", "--language", "en")
    assert shown.exit_code == 3, shown.output
    assert "not initialized" in shown.output
    assert "ambiguous" not in shown.output
    assert not ledger.exists()


def test_chinese_diagnostics_translate_known_codes_but_keep_json_technical(tmp_path: Path, monkeypatch):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    from scholar_workflow.assets import servers

    message = "Server ledger permissions are not private; read made no changes."
    monkeypatch.setattr(servers, "read_servers", lambda _root: {
        "schema_version": 1, "status": "available", "revision": "absent", "servers": [],
        "diagnostics": [{"code": "ledger_permissions", "message": message}],
    })
    human = invoke(state, "server", "check", "--language", "zh")
    assert human.exit_code == 0, human.output
    assert "权限" in human.output and message not in human.output
    machine = invoke(state, "server", "check", "--format", "json", "--language", "zh")
    assert machine.exit_code == 0, machine.output
    assert json.loads(machine.output)["diagnostics"][0]["message"] == message


@pytest.mark.parametrize("exit_code", [6, 7])
def test_registration_preserves_uncertain_commit_and_safety_exit_codes(
    tmp_path: Path, monkeypatch, exit_code: int,
):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    from scholar_workflow.assets import servers

    def refused(*args, **kwargs):
        raise servers.AssetLedgerError("Synthetic safe diagnostic.", exit_code=exit_code)

    monkeypatch.setattr(servers, "register_server", refused)
    spec = tmp_path / "server.json"
    spec.write_text('{"alias":"synthetic-gpu"}')
    result = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert result.exit_code == exit_code, result.output


def test_server_show_check_and_registration_use_configured_root(tmp_path: Path, monkeypatch):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    from scholar_workflow.assets import servers

    server = {"alias": "synthetic-gpu", "host": "192.0.2.10", "user": "researcher",
              "port": 22, "purpose": "Synthetic test"}
    calls = []

    def read(root):
        calls.append(root)
        return {"schema_version": 1, "status": "available", "revision": "sha256:old",
                "servers": [server], "diagnostics": []}

    def register(root, record, expected_revision=None):
        assert root == ledger
        assert record == server
        assert expected_revision == "sha256:old"
        return {"status": "unchanged", "revision": "sha256:old", "server": server}

    monkeypatch.setattr(servers, "read_servers", read)
    monkeypatch.setattr(servers, "register_server", register)
    spec = tmp_path / "server.json"
    spec.write_text(json.dumps(server), encoding="utf-8")
    for args in [("show", "synthetic-gpu"), ("check",)]:
        result = invoke(state, "server", *args, "--format", "json")
        assert result.exit_code == 0, result.output
        assert "synthetic-gpu" in result.output
    result = invoke(state, "server", "register", "--spec", str(spec),
                    "--expected-revision", "sha256:old", "--format", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "unchanged"
    assert calls == [ledger, ledger]


@pytest.mark.parametrize("kind", ["duplicate", "invalid", "oversized", "symlink",
                                  "parent-symlink", "fifo"])
def test_registration_spec_rejects_unsafe_input_without_echoing_values(
    tmp_path: Path, monkeypatch, kind: str,
):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    from scholar_workflow.assets import servers

    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe input reached the server ledger writer")

    monkeypatch.setattr(servers, "register_server", forbidden)
    spec = tmp_path / "server.json"
    marker = "private-value-must-not-leak"
    if kind == "duplicate":
        spec.write_text('{"alias":"synthetic","alias":"' + marker + '"}')
    elif kind == "invalid":
        spec.write_text('{"password":"' + marker + '"')
    elif kind == "oversized":
        spec.write_text(marker + "x" * (64 * 1024))
    elif kind == "symlink":
        target = tmp_path / "target.json"
        target.write_text('{"password":"' + marker + '"}')
        spec.symlink_to(target)
    elif kind == "parent-symlink":
        parent = tmp_path / "physical"
        parent.mkdir()
        (parent / "server.json").write_text('{"password":"' + marker + '"}')
        linked = tmp_path / "linked"
        linked.symlink_to(parent, target_is_directory=True)
        spec = linked / "server.json"
    else:
        os.mkfifo(spec)
    result = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert result.exit_code in {2, 7}, result.output
    assert marker not in result.output
    assert "Traceback" not in result.output
    assert not ledger.exists()


@pytest.mark.parametrize("secret_field", ["password", "api_key", "token"])
def test_secret_fields_are_rejected_without_leaking_values(tmp_path: Path, secret_field: str):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    marker = "private-value-must-not-leak"
    spec = tmp_path / "server.json"
    spec.write_text(json.dumps({"alias": "synthetic-gpu", "host": "192.0.2.10",
                                "user": "researcher", secret_field: marker}))
    result = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert result.exit_code in {2, 7}, result.output
    assert marker not in result.output
    assert not (ledger / "servers.yaml").exists()


def test_real_backend_registration_is_idempotent_and_requires_cas_for_update(tmp_path: Path):
    state, ledger = tmp_path / "state", tmp_path / "ledger"
    config(state, ledger)
    spec = tmp_path / "server.json"
    record = {"alias": "synthetic-gpu", "host": "192.0.2.10", "user": "researcher",
              "port": 22, "purpose": "Synthetic test"}
    spec.write_text(json.dumps(record))
    created = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert created.exit_code == 0, created.output
    first = json.loads(created.output)
    assert first["status"] == "created"
    unchanged = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert unchanged.exit_code == 0, unchanged.output
    assert json.loads(unchanged.output)["status"] == "unchanged"
    before = (ledger / "servers.yaml").read_bytes()
    record["purpose"] = "Updated synthetic purpose"
    spec.write_text(json.dumps(record))
    rejected = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert rejected.exit_code == 5, rejected.output
    assert (ledger / "servers.yaml").read_bytes() == before
    updated = invoke(state, "server", "register", "--spec", str(spec),
                     "--expected-revision", first["revision"], "--format", "json")
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["status"] == "updated"
    latest = (ledger / "servers.yaml").read_bytes()
    record["purpose"] = "Stale synthetic purpose"
    spec.write_text(json.dumps(record))
    stale = invoke(state, "server", "register", "--spec", str(spec),
                   "--expected-revision", first["revision"], "--format", "json")
    assert stale.exit_code == 7, stale.output
    assert (ledger / "servers.yaml").read_bytes() == latest


def test_invalid_config_error_does_not_expose_values_and_knowledge_stays_visible(tmp_path: Path):
    state, root = tmp_path / "state", tmp_path / "vault"
    registered_source(state, root)
    marker = "private-value-must-not-leak"
    (state / "config.yml").write_text("env_records_root: [" + marker + "]\n")
    result = invoke(state, "list", "--format", "json")
    assert result.exit_code == 0, result.output
    assert marker not in result.output
    payload = json.loads(result.output)
    assert payload["providers"]["server"]["status"] == "unavailable"
    assert payload["providers"]["knowledge"]["status"] == "available"


def test_malformed_config_keeps_knowledge_visible_without_parser_values(tmp_path: Path):
    state, root = tmp_path / "state", tmp_path / "vault"
    registered_source(state, root)
    marker = "private-parser-value-must-not-leak"
    (state / "config.yml").write_text("env_records_root: [" + marker + "\n")
    result = invoke(state, "list", "--format", "json")
    assert result.exit_code == 0, result.output
    assert marker not in result.output
    payload = json.loads(result.output)
    assert payload["providers"]["server"]["status"] == "unavailable"
    assert payload["providers"]["knowledge"]["sources"]
    assert payload["providers"]["knowledge"]["status"] == "available"


@pytest.mark.parametrize("kind", ["root-symlink", "parent-symlink", "parent-traversal"])
def test_config_preserves_unsafe_ledger_components_for_cli_refusal(tmp_path: Path, kind: str):
    state = tmp_path / "state"
    physical = tmp_path / "physical"
    physical.mkdir()
    if kind == "root-symlink":
        ledger = tmp_path / "linked-ledger"
        ledger.symlink_to(physical, target_is_directory=True)
    elif kind == "parent-symlink":
        parent = tmp_path / "linked-parent"
        parent.symlink_to(physical, target_is_directory=True)
        ledger = parent / "ledger"
    else:
        (tmp_path / "nested").mkdir()
        ledger = tmp_path / "nested" / ".." / "ledger"
    config(state, ledger)
    spec = tmp_path / "server.json"
    spec.write_text(json.dumps({"alias": "synthetic-gpu", "host": "192.0.2.10",
                                "user": "researcher"}))
    before = {str(path.relative_to(tmp_path)): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file() and not path.is_symlink()}
    entries = {str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")}
    listed = invoke(state, "list", "--kind", "server", "--format", "json")
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["providers"]["server"]["status"] == "invalid"
    checked = invoke(state, "server", "check", "--format", "json")
    assert checked.exit_code == 7, checked.output
    assert json.loads(checked.output)["status"] == "invalid"
    rejected = invoke(state, "server", "register", "--spec", str(spec), "--format", "json")
    assert rejected.exit_code == 7, rejected.output
    assert {str(path.relative_to(tmp_path)): path.read_bytes()
            for path in tmp_path.rglob("*") if path.is_file() and not path.is_symlink()} == before
    assert {str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")} == entries
    assert not (physical / "servers.yaml").exists()


def test_human_summaries_keep_language_and_do_not_dump_revisions(tmp_path: Path):
    state, root = tmp_path / "state", tmp_path / "vault"
    registered_source(state, root)
    zh = invoke(state, "list", "--kind", "knowledge", "--language", "zh")
    en = invoke(state, "list", "--kind", "knowledge", "--language", "en")
    assert zh.exit_code == en.exit_code == 0
    assert "知识库" in zh.output and "目录" in zh.output
    assert "Knowledge" in en.output and "Folder" in en.output
    assert "不是" in zh.output and "ownership" in en.output
    assert "sha256:" not in zh.output + en.output
    assert "11111111-1111" not in zh.output + en.output


@pytest.mark.parametrize("args", [["list", "--kind", "arbitrary"],
                                  ["server", "delete"], ["server", "connect"],
                                  ["exec"], ["server", "register"]])
def test_unsupported_actions_are_not_available(tmp_path: Path, args: list[str]):
    result = invoke(tmp_path / "state", *args)
    assert result.exit_code == 2
