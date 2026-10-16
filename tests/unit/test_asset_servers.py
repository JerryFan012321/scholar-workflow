"""Server ledger contract: synthetic files only, no SSH or private key reads."""
from __future__ import annotations

import json
import os
import stat

import pytest
from ruamel.yaml import YAML

from scholar_workflow.assets.servers import (
    AssetLedgerError,
    read_servers,
    register_server,
)


def server(**changes):
    return {"alias": "gpu-a", "host": "gpu.example.test", "user": "researcher",
            "port": 22, **changes}


def test_missing_read_does_not_initialize_anything(tmp_path):
    root = tmp_path / "absent"
    result = read_servers(root)
    assert result["status"] == "uninitialized"
    assert result["revision"] == "absent"
    assert result["servers"] == []
    assert not root.exists()


def test_registration_creates_only_private_server_ledger(tmp_path):
    root = tmp_path / "ledger"
    result = register_server(root, server())
    assert result["status"] == "created"
    assert result["server"]["alias"] == "gpu-a"
    assert result["revision"].startswith("sha256:")
    assert {path.name for path in root.iterdir()} == {"servers.yaml", ".servers.lock"}
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for name in ("servers.yaml", ".servers.lock"):
        assert stat.S_IMODE((root / name).stat().st_mode) == 0o600
    result = read_servers(root)
    assert result["status"] == "available"
    assert result["servers"] == [server()]


def test_duplicate_registration_is_byte_identical_and_same_revision(tmp_path):
    root = tmp_path / "ledger"
    first = register_server(root, server())
    before = (root / "servers.yaml").read_bytes()
    second = register_server(root, server())
    assert second["status"] == "unchanged"
    assert second["revision"] == first["revision"]
    assert (root / "servers.yaml").read_bytes() == before


def test_conflicting_update_requires_exact_current_revision(tmp_path):
    root = tmp_path / "ledger"
    first = register_server(root, server())
    before = (root / "servers.yaml").read_bytes()
    for expected in (None, "absent", "sha256:" + "0" * 64):
        with pytest.raises(AssetLedgerError) as caught:
            register_server(root, {"alias": "gpu-a", "port": 2222},
                            expected_revision=expected)
        assert caught.value.exit_code == (5 if expected is None else 7)
        assert (root / "servers.yaml").read_bytes() == before
    result = register_server(root, {"alias": "gpu-a", "port": 2222},
                             expected_revision=first["revision"])
    assert result["status"] == "updated"
    assert result["server"] == server(port=2222)


def test_create_also_honors_explicit_revision(tmp_path):
    root = tmp_path / "ledger"
    first = register_server(root, server())
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(alias="gpu-b"), expected_revision="absent")
    assert caught.value.exit_code == 7
    added = register_server(root, server(alias="gpu-b"),
                            expected_revision=first["revision"])
    assert added["status"] == "created"
    assert len(read_servers(root)["servers"]) == 2


def test_patch_preserves_unrelated_fields_comments_and_existing_secret(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    path = root / "servers.yaml"
    path.write_text(
        "# keep ledger comment\nservers:\n"
        "  - alias: gpu-a # keep host comment\n"
        "    host: gpu.example.test\n    user: researcher\n    port: 22\n"
        "    password: OLD-PRIVATE-VALUE\n    extra_meta: keep-me\n"
        "    environments:\n      - name: base\n        python: '3.11'\n"
        "        setup_script: setup/gpu-a/base.sh\n"
        "  - alias: gpu-b\n    host: other.example.test\n    user: researcher\n"
        "    notes: keep other row\nmetadata:\n  owner: keep top level\n"
    )
    read = read_servers(root)
    assert "OLD-PRIVATE-VALUE" not in json.dumps(read)
    assert read["servers"][0]["legacy_secret_present"] is True
    result = register_server(root, {"alias": "gpu-a", "purpose": "training"},
                             expected_revision=read["revision"])
    text = path.read_text()
    assert "# keep ledger comment" in text
    assert "# keep host comment" in text
    parsed = YAML(typ="safe").load(text)
    assert parsed["servers"][0]["password"] == "OLD-PRIVATE-VALUE"
    assert parsed["servers"][0]["extra_meta"] == "keep-me"
    assert parsed["servers"][0]["environments"][0]["python"] == "3.11"
    assert parsed["servers"][1]["notes"] == "keep other row"
    assert parsed["metadata"]["owner"] == "keep top level"
    assert "OLD-PRIVATE-VALUE" not in json.dumps(result)


@pytest.mark.parametrize("field", ["password", "token", "secret", "api_key"])
def test_rejects_new_plaintext_secrets_before_creating_root(tmp_path, field):
    root = tmp_path / "absent"
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(**{field: "DO-NOT-ECHO"}))
    assert caught.value.exit_code == 7
    assert "DO-NOT-ECHO" not in str(caught.value)
    assert not root.exists()


def test_credential_reference_is_not_a_secret(tmp_path):
    root = tmp_path / "ledger"
    result = register_server(root, server(credential_ref="keychain:servers/gpu-a"))
    assert result["server"]["credential_ref"] == "keychain:servers/gpu-a"


def test_key_is_a_path_not_private_key_material(tmp_path):
    root = tmp_path / "absent"
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(key="-----BEGIN OPENSSH PRIVATE KEY-----\nPRIVATE"))
    assert caught.value.exit_code == 7
    assert "PRIVATE" not in str(caught.value)
    assert not root.exists()
    result = register_server(root, server(key="~/.ssh/id_ed25519"))
    assert result["server"]["key"] == "~/.ssh/id_ed25519"


@pytest.mark.parametrize("field", ["notes", "purpose"])
@pytest.mark.parametrize("secret", [
    "-----BEGIN OPENSSH PRIVATE KEY-----\nDO-NOT-ECHO\n-----END OPENSSH PRIVATE KEY-----",
    "Authorization: Bearer DO-NOT-ECHO-TOKEN",
    "Credentials at https://alice:DO-NOT-ECHO@host.example.test/path",
])
def test_recognizable_string_secrets_rejected_in_every_submitted_field(tmp_path, field, secret):
    root = tmp_path / "absent"
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(**{field: secret}))
    assert caught.value.exit_code == 7
    assert "DO-NOT-ECHO" not in str(caught.value)
    assert not root.exists()


@pytest.mark.parametrize("field", ["notes", "purpose"])
@pytest.mark.parametrize("secret", [
    "-----BEGIN OPENSSH PRIVATE KEY----- DO-NOT-ECHO",
    "Authorization: Bearer DO-NOT-ECHO-TOKEN",
    "https://alice:DO-NOT-ECHO@host.example.test/path",
])
def test_recognizable_legacy_string_secrets_hidden_but_preserved(tmp_path, field, secret):
    root = tmp_path / "ledger"
    register_server(root, server())
    path = root / "servers.yaml"
    document = YAML(typ="safe").load(path.read_text())
    document["servers"][0][field] = secret
    with path.open("w") as handle:
        YAML().dump(document, handle)
    before = path.read_bytes()
    result = read_servers(root)
    assert result["status"] == "available"
    assert "DO-NOT-ECHO" not in json.dumps(result)
    assert result["servers"][0][field] == "[credential material hidden]"
    assert result["servers"][0]["legacy_secret_present"] is True
    assert path.read_bytes() == before
    updated = register_server(root, {"alias": "gpu-a", "port": 2222},
                              expected_revision=result["revision"])
    assert "DO-NOT-ECHO" not in json.dumps(updated)
    assert YAML(typ="safe").load(path.read_text())["servers"][0][field] == secret


@pytest.mark.parametrize("field", ["notes", "purpose"])
def test_http_basic_credentials_rejected_in_new_registration(tmp_path, field):
    root = tmp_path / "absent"
    authorization = "Authorization: Basic dXNlcjpETy1OT1QtRUNITw=="
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(**{field: authorization}))
    assert caught.value.exit_code == 7
    assert "dXNlcjpETy1OT1QtRUNITw==" not in str(caught.value)
    assert not root.exists()


@pytest.mark.parametrize("field", ["notes", "purpose"])
def test_legacy_http_basic_credentials_hidden_and_preserved(tmp_path, field):
    root = tmp_path / "ledger"
    register_server(root, server())
    path = root / "servers.yaml"
    authorization = "Authorization: Basic dXNlcjpETy1OT1QtRUNITw=="
    document = YAML(typ="safe").load(path.read_text())
    document["servers"][0][field] = authorization
    with path.open("w") as handle:
        YAML().dump(document, handle)
    before = path.read_bytes()
    result = read_servers(root)
    assert result["status"] == "available"
    assert result["servers"][0][field] == "[credential material hidden]"
    assert result["servers"][0]["legacy_secret_present"] is True
    assert path.read_bytes() == before
    updated = register_server(root, {"alias": "gpu-a", "port": 2222},
                              expected_revision=result["revision"])
    assert "dXNlcjpETy1OT1QtRUNITw==" not in json.dumps(updated)
    assert YAML(typ="safe").load(path.read_text())["servers"][0][field] == authorization


def test_safe_output_contains_no_basic_authorization_credential(tmp_path):
    root = tmp_path / "ledger"
    register_server(root, server())
    path = root / "servers.yaml"
    document = YAML(typ="safe").load(path.read_text())
    document["servers"][0]["notes"] = "Proxy-Authorization: bAsIc dXNlcjpETy1OT1QtRUNITw=="
    with path.open("w") as handle:
        YAML().dump(document, handle)
    result = read_servers(root)
    serialized = json.dumps(result)
    assert "dXNlcjpETy1OT1QtRUNITw==" not in serialized
    assert "Proxy-Authorization" not in serialized
    assert result["servers"][0]["notes"] == "[credential material hidden]"
    assert any(d["code"] == "legacy_secret_present" for d in result["diagnostics"])


def test_legacy_secret_cannot_be_cleared_or_replaced_by_patch(tmp_path):
    root = tmp_path / "ledger"
    register_server(root, server())
    path = root / "servers.yaml"
    text = path.read_text() + ""
    parsed = YAML(typ="safe").load(text)
    parsed["servers"][0]["password"] = "LEGACY-SECRET"
    with path.open("w") as handle:
        YAML().dump(parsed, handle)
    before = path.read_bytes()
    for value in (None, "NEW-SECRET"):
        with pytest.raises(AssetLedgerError) as caught:
            register_server(root, {"alias": "gpu-a", "password": value},
                            expected_revision=read_servers(root)["revision"])
        assert caught.value.exit_code == 7
        assert path.read_bytes() == before


def test_proxy_credentials_are_hidden_and_new_credentials_rejected(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    path = root / "servers.yaml"
    path.write_text("servers:\n  - alias: gpu-a\n    host: gpu.example.test\n"
                    "    user: researcher\n    proxy:\n"
                    "      https: https://alice:DO-NOT-ECHO@proxy.example.test:8443\n")
    result = read_servers(root)
    assert result["status"] == "available"
    assert "DO-NOT-ECHO" not in json.dumps(result)
    assert "alice" not in json.dumps(result)
    assert result["servers"][0]["proxy"]["https"] == "[credential-bearing proxy hidden]"
    assert any(d["code"] == "legacy_secret_present" for d in result["diagnostics"])
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(alias="gpu-b", proxy={
            "http": "http://alice:DO-NOT-ECHO@proxy.example.test"}))
    assert caught.value.exit_code == 7
    assert "DO-NOT-ECHO" not in str(caught.value)


def test_nested_patch_changes_only_submitted_proxy_fields(tmp_path):
    root = tmp_path / "ledger"
    first = register_server(root, server(proxy={
        "http": "http://first.example.test:8080",
        "https": "http://secure.example.test:8080", "no_proxy": "localhost"}))
    result = register_server(root, {"alias": "gpu-a", "proxy": {
        "http": "http://second.example.test:8080"}}, expected_revision=first["revision"])
    assert result["server"]["proxy"] == {
        "http": "http://second.example.test:8080",
        "https": "http://secure.example.test:8080", "no_proxy": "localhost"}


def test_new_server_requires_host_and_user_before_creating_root(tmp_path):
    root = tmp_path / "absent"
    with pytest.raises(AssetLedgerError):
        register_server(root, {"alias": "gpu-a"})
    assert not root.exists()


@pytest.mark.parametrize("changes", [
    {"alias": "bad/alias"}, {"host": "<ip-or-hostname>"}, {"user": "<username>"},
    {"host": "host"}, {"user": "username"}, {"port": 0}, {"port": 65536},
    {"port": True}, {"environments": "base"},
    {"environments": [{"name": "base", "setup_script": "../escape.sh"}]},
    {"environments": [{"name": "base", "setup_script": "/absolute.sh"}]},
    {"environments": [{"name": "base", "setup_script": "setup/gpu-b/base.sh"}]},
    {"environments": [{"name": "base"}, {"name": "base"}]},
])
def test_invalid_registration_inputs_are_rejected_without_writes(tmp_path, changes):
    root = tmp_path / "absent"
    with pytest.raises(AssetLedgerError):
        register_server(root, server(**changes))
    assert not root.exists()


@pytest.mark.parametrize("contents", [
    "servers:\n  - alias: gpu-a\n    alias: gpu-b\n",
    "servers: []\nservers: []\n",
    ("servers:\n  - alias: gpu-a\n    host: first.example.test\n    user: researcher\n"
     "  - alias: gpu-a\n    host: second.example.test\n    user: researcher\n"),
    "servers: not-a-list\n",
    "servers: [SECRET-BROKEN-VALUE\n",
])
def test_invalid_ledger_is_sanitized_and_never_rewritten(tmp_path, contents):
    root = tmp_path / "ledger"
    root.mkdir()
    path = root / "servers.yaml"
    path.write_text(contents)
    before = path.read_bytes()
    result = read_servers(root)
    assert result["status"] == "invalid"
    assert result["servers"] == []
    assert "SECRET-BROKEN-VALUE" not in json.dumps(result)
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server())
    assert "SECRET-BROKEN-VALUE" not in str(caught.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["root", "ledger", "lock", "parent"])
def test_symlinks_never_followed(tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_ledger = outside / "servers.yaml"
    outside_ledger.write_text("servers: []\n")
    before = outside_ledger.read_bytes()
    root = tmp_path / "ledger"
    if kind == "root":
        root.symlink_to(outside, target_is_directory=True)
    elif kind == "parent":
        parent = tmp_path / "linked-parent"
        parent.symlink_to(outside, target_is_directory=True)
        root = parent / "ledger"
    else:
        root.mkdir()
        (root / ("servers.yaml" if kind == "ledger" else ".servers.lock")).symlink_to(
            outside_ledger)
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server())
    assert caught.value.exit_code == 7
    assert outside_ledger.read_bytes() == before
    if kind != "lock":
        assert read_servers(root)["status"] == "invalid"


def test_nonregular_and_hardlinked_files_rejected_without_blocking(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    path = root / "servers.yaml"
    os.mkfifo(path)
    assert read_servers(root)["status"] == "invalid"
    with pytest.raises(AssetLedgerError):
        register_server(root, server())
    path.unlink()
    outside = tmp_path / "hardlinked"
    outside.write_text("servers: []\n")
    path.hardlink_to(outside)
    assert read_servers(root)["status"] == "invalid"
    with pytest.raises(AssetLedgerError):
        register_server(root, server())


def test_read_warns_existing_public_mode_without_chmod(tmp_path):
    root = tmp_path / "ledger"
    register_server(root, server())
    path = root / "servers.yaml"
    path.chmod(0o644)
    result = read_servers(root)
    assert result["status"] == "available"
    assert any(d["code"] == "ledger_permissions" for d in result["diagnostics"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_group_or_other_writable_root_rejected_without_permission_changes(tmp_path):
    root = tmp_path / "ledger"
    register_server(root, server())
    path = root / "servers.yaml"
    before = path.read_bytes()
    root.chmod(0o777)
    result = read_servers(root)
    assert result["status"] == "invalid"
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, server(alias="gpu-b"))
    assert caught.value.exit_code == 7
    assert path.read_bytes() == before
    assert stat.S_IMODE(root.stat().st_mode) == 0o777


def test_setup_script_diagnostics_use_metadata_only(tmp_path, monkeypatch):
    root = tmp_path / "ledger"
    register_server(root, server(environments=[{
        "name": "base", "setup_script": "setup/gpu-a/base.sh"}]))
    result = read_servers(root)
    assert result["status"] == "available"
    assert any(d["code"] == "setup_script_missing" for d in result["diagnostics"])
    script = root / "setup" / "gpu-a" / "base.sh"
    script.parent.mkdir(parents=True)
    script.write_text("PRIVATE-SCRIPT-CONTENT")
    original_open = os.open

    def refuse_script_read(path, flags, *args, **kwargs):
        assert os.fspath(path) != "base.sh", "Script contents must not be opened"
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse_script_read)
    result = read_servers(root)
    assert not any(d["code"].startswith("setup_script_") for d in result["diagnostics"])
    script.unlink()
    outside = tmp_path / "outside-script"
    outside.write_text("OUTSIDE-CONTENT")
    script.symlink_to(outside)
    result = read_servers(root)
    assert any(d["code"] == "setup_script_unsafe" for d in result["diagnostics"])
    assert "PRIVATE-SCRIPT-CONTENT" not in json.dumps(result)
    assert "OUTSIDE-CONTENT" not in json.dumps(result)


def test_post_replace_directory_fsync_failure_reports_uncertain_result(tmp_path, monkeypatch):
    root = tmp_path / "ledger"
    first = register_server(root, server())
    original_fsync = os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("synthetic directory durability failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, {"alias": "gpu-a", "port": 2222},
                        expected_revision=first["revision"])
    assert caught.value.exit_code == 6
    assert read_servers(root)["servers"][0]["port"] == 2222


def test_change_during_atomic_replace_is_safety_failure_not_overwrite(tmp_path, monkeypatch):
    from scholar_workflow.assets import servers as backend

    root = tmp_path / "ledger"
    first = register_server(root, server())
    path = root / "servers.yaml"
    outside_revision = path.read_bytes() + b"# concurrent operator edit\n"
    original_read = backend._read_bytes
    reads = [0]

    def change_before_final_read(root_fd):
        reads[0] += 1
        if reads[0] == 3:
            path.write_bytes(outside_revision)
        return original_read(root_fd)

    monkeypatch.setattr(backend, "_read_bytes", change_before_final_read)
    with pytest.raises(AssetLedgerError) as caught:
        register_server(root, {"alias": "gpu-a", "port": 2222},
                        expected_revision=first["revision"])
    assert caught.value.exit_code == 7
    assert path.read_bytes() == outside_revision
    assert not list(root.glob(".servers-*.tmp"))


def test_empty_ledger_is_available_not_uninitialized(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    (root / "servers.yaml").write_text("servers: []\n")
    assert read_servers(root)["status"] == "available"
    assert read_servers(root)["servers"] == []


def test_large_ledger_fails_closed_without_returning_its_contents(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    (root / "servers.yaml").write_bytes(b"SECRET" * 200_000)
    result = read_servers(root)
    assert result["status"] == "invalid"
    assert "SECRET" not in json.dumps(result)
