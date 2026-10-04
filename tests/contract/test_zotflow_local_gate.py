"""ZotFlow may open a paper only through a verified local-storage route."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from scholar_workflow.adapters.zotero_local import ZoteroAttachmentLocator
from scholar_workflow.hub.actions import InvalidActionTarget, ZotFlowLauncher
from scholar_workflow.hub.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.zotflow import (
    AnnotationIR,
    PdfRef,
    RegisteredSourceZotFlowAdapter,
    ZotFlowError,
    ZotFlowReaderAdapter,
    resolve_obsidian_vault_id,
)

_KEY = "PDFD2345"
_PDF_BYTES = b"%PDF-1.7\n"
_HASH = "md5:" + hashlib.md5(_PDF_BYTES).hexdigest()
_VAULT_A_ID = "1111111111111111"
_VAULT_B_ID = "2222222222222222"


def _obsidian_config(tmp_path: Path, vaults: dict[str, Path]) -> Path:
    config = tmp_path / "obsidian.json"
    config.write_text(
        json.dumps({"vaults": {
            vault_id: {"path": str(path)} for vault_id, path in vaults.items()
        }}), encoding="utf-8"
    )
    return config


def _ready_vault(
    tmp_path: Path, *, plugin_version: str = "1.6.6"
) -> tuple[Path, Path, Path]:
    vault = tmp_path / "vault"
    plugin = vault / ".obsidian" / "plugins" / "zotflow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps({"id": "zotflow", "version": plugin_version, "minAppVersion": "1.13.4"}),
        encoding="utf-8",
    )
    (vault / ".obsidian" / "community-plugins.json").write_text(
        '["zotflow"]', encoding="utf-8"
    )
    # The capability probe must never inspect ZotFlow's persisted data or secrets.
    (plugin / "data.json").write_text(
        '{"webApiKey":"DO_NOT_READ", "useZoteroStorage":false}', encoding="utf-8"
    )
    app = tmp_path / "Obsidian.app"
    info = app / "Contents" / "Info.plist"
    info.parent.mkdir(parents=True)
    with info.open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": "1.13.7"}, handle)
    storage = tmp_path / "zotero" / "storage"
    pdf = storage / _KEY / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(_PDF_BYTES)
    return vault, app, pdf


class _LocalZotero:
    def __init__(
        self,
        pdf: Path,
        *,
        link_mode: str = "imported_file",
        filename: str | None = None,
    ) -> None:
        self.pdf = pdf
        self.link_mode = link_mode
        self.filename = filename or pdf.name

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_item(self, key: str):
        assert key == _KEY
        return {"data": {
            "itemType": "attachment",
            "linkMode": self.link_mode,
            "filename": self.filename,
        }}

    def resolve_attachment_locator(self, key: str) -> ZoteroAttachmentLocator:
        assert key == _KEY
        return ZoteroAttachmentLocator(
            attachment_key=key,
            library_id="1",
            content_hash=_HASH,
            path=self.pdf,
            filename=self.pdf.name,
        )


def _adapter(
    vault: Path,
    app: Path,
    pdf: Path,
    *,
    local: bool = True,
    vault_in_cli: Path | None = None,
    storage_in_cli: Path | None = None,
    link_mode: str = "imported_file",
    filename: str | None = None,
    cli_returncode: int = 0,
    config_vaults: dict[str, Path] | None = None,
):
    calls: list[list[str]] = []
    config_path = _obsidian_config(
        vault.parent, config_vaults if config_vaults is not None else {_VAULT_A_ID: vault}
    )

    def cli_runner(argv, **kwargs):
        calls.append(list(argv))
        assert kwargs["shell"] is False
        assert kwargs["timeout"] > 0
        assert argv[1] == f"vault={_VAULT_A_ID}"
        assert argv[2] == "eval"
        assert "useZoteroStorage" in argv[3]
        assert "zoteroStoragePath" in argv[3]
        assert "webApiKey" not in argv[3]
        payload = {
            "protocol": "zotflow-local-v1",
            "vault": str(vault_in_cli or vault),
            "enabled": True,
            "local": local,
            "storagePath": str(storage_in_cli or pdf.parent.parent),
        }
        return SimpleNamespace(
            returncode=cli_returncode,
            stdout="=> " + json.dumps(payload),
            stderr="",
        )

    def open_runner(argv, **kwargs):
        calls.append(list(argv))
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=0)

    adapter = ZotFlowReaderAdapter(
        vault,
        app_path=app,
        runner=open_runner,
        cli_runner=cli_runner,
        zotero_factory=lambda: _LocalZotero(
            pdf, link_mode=link_mode, filename=filename
        ),
        obsidian_config_path=config_path,
    )
    return adapter, calls


def _ref() -> PdfRef:
    return PdfRef(library_id="1", attachment_key=_KEY, content_hash=_HASH)


def test_zotflow_requires_narrow_live_local_storage_probe_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault, app, pdf = _ready_vault(tmp_path)
    adapter, calls = _adapter(vault, app, pdf)
    original_read_text = Path.read_text

    def reject_data_read(path: Path, *args, **kwargs):
        if path.name == "data.json":
            raise AssertionError("ZotFlow data.json must not be read")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_data_read)

    assert adapter.probe().available is True
    assert adapter.probe_attachment(_ref()).available is True
    assert adapter.open_attachment(_ref()) == {"opened": True}
    assert calls[-1] == [
        "/usr/bin/open",
        f"obsidian://zotflow?vault={_VAULT_A_ID}&type=open-attachment&libraryID=1&key=PDFD2345",
    ]
    assert all("DO_NOT_READ" not in str(call) for call in calls)


def test_zotflow_uri_targets_the_verified_vault_id(tmp_path: Path):
    vault, app, pdf = _ready_vault(tmp_path)
    named_vault = tmp_path / "研究 & Notes"
    vault.rename(named_vault)
    adapter, calls = _adapter(named_vault, app, pdf)

    assert adapter.open_attachment(_ref()) == {"opened": True}
    uri = calls[-1][1]
    assert f"vault={_VAULT_A_ID}" in uri
    assert parse_qs(urlsplit(uri).query) == {
        "vault": [_VAULT_A_ID],
        "type": ["open-attachment"],
        "libraryID": ["1"],
        "key": [_KEY],
    }


def test_unregistered_same_named_vault_cannot_steal_attachment_or_annotation_uri(
    tmp_path: Path,
):
    vault, app, pdf = _ready_vault(tmp_path)
    unregistered = tmp_path / "other" / vault.name
    unregistered.mkdir(parents=True)
    adapter, calls = _adapter(
        vault, app, pdf,
        config_vaults={_VAULT_A_ID: vault, _VAULT_B_ID: unregistered},
    )
    annotation = AnnotationIR(
        annotation_id="ANNP2345", source_id="ANNP2345", pdf_ref=_ref(),
        type="highlight", source_link="zotero://select/library/items/ANNP2345",
        source_pdf_hash=_HASH,
    )

    assert adapter.open_attachment(_ref()) == {"opened": True}
    assert adapter.open_annotation(annotation) == {"opened": True}
    opened = [call[1] for call in calls if call[0] == "/usr/bin/open"]
    assert len(opened) == 2
    assert all(parse_qs(urlsplit(uri).query)["vault"] == [_VAULT_A_ID] for uri in opened)
    assert all(call[1] == f"vault={_VAULT_A_ID}" for call in calls if call[0] == "obsidian")


@pytest.mark.parametrize("case", ["missing", "duplicate", "stale"])
def test_vault_id_resolution_fails_closed_without_unique_current_id(
    tmp_path: Path, case: str,
):
    vault, app, pdf = _ready_vault(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    mappings = {
        "missing": {_VAULT_A_ID: other},
        "duplicate": {_VAULT_A_ID: vault, _VAULT_B_ID: vault},
        "stale": {_VAULT_A_ID: tmp_path / "moved-away"},
    }
    adapter, calls = _adapter(vault, app, pdf, config_vaults=mappings[case])

    assert adapter.probe().available is False
    with pytest.raises(ZotFlowError, match="Vault ID"):
        adapter.open_attachment(_ref())
    assert all(call[0] not in {"obsidian", "/usr/bin/open"} for call in calls)


def test_vault_id_resolver_rejects_symlink_and_malformed_registry(tmp_path: Path):
    vault, _, _ = _ready_vault(tmp_path)
    config = _obsidian_config(tmp_path, {_VAULT_A_ID: vault})
    link = tmp_path / "linked.json"
    link.symlink_to(config)
    with pytest.raises(ZotFlowError, match="unsafe"):
        resolve_obsidian_vault_id(vault, config_path=link)

    config.write_text(
        '{"vaults":{"1111111111111111":{"path":"/a"},'
        '"1111111111111111":{"path":"/b"}}}', encoding="utf-8"
    )
    with pytest.raises(ZotFlowError, match="unsafe"):
        resolve_obsidian_vault_id(vault, config_path=config)


def test_registered_source_subdirectory_uses_parent_reader_not_parent_authority(tmp_path: Path):
    vault, app, pdf = _ready_vault(tmp_path)
    reader, calls = _adapter(vault, app, pdf)
    source = vault / "Chosen Field"
    source.mkdir()
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    source_id = "11111111-1111-4111-8111-111111111111"
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="child", root=source, capabilities=["read"])],
        sources=[KnowledgeSourceRegistration(source_id=source_id, folder_id="child")],
    ))
    adapter = RegisteredSourceZotFlowAdapter(
        registry, app_path=app, runner=reader._runner, cli_runner=reader._cli_runner,
        zotero_factory=reader._zotero_factory, obsidian_config_path=reader._obsidian_config_path,
    )
    before = registry.path.read_bytes()
    assert adapter.open_attachment(_ref()) == {"opened": True}
    assert registry.resolve(source_id, capability="read") == source
    assert registry.path.read_bytes() == before
    assert any(call[0] == "/usr/bin/open" for call in calls)
    assert all(call[1] == f"vault={_VAULT_A_ID}" for call in calls if call[0] == "obsidian")


def test_vault_id_resolver_rejects_untrusted_owner_or_oversized_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    vault, _, _ = _ready_vault(tmp_path)
    config = _obsidian_config(tmp_path, {_VAULT_A_ID: vault})
    uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    with pytest.raises(ZotFlowError, match="unsafe"):
        resolve_obsidian_vault_id(vault, config_path=config)
    monkeypatch.undo()

    config.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ZotFlowError, match="unsafe"):
        resolve_obsidian_vault_id(vault, config_path=config)


def _registered_adapter(
    tmp_path: Path, *, disable_first: bool = False, disable_second: bool = False
) -> tuple[RegisteredSourceZotFlowAdapter, list[list[str]]]:
    first, app, pdf = _ready_vault(tmp_path)
    first.rename(tmp_path / "Alpha Vault")
    first = tmp_path / "Alpha Vault"
    if disable_first:
        (first / ".obsidian" / "community-plugins.json").write_text(
            "[]", encoding="utf-8"
        )
    second = tmp_path / "Beta Vault"
    second_plugin = second / ".obsidian" / "plugins" / "zotflow"
    second_plugin.mkdir(parents=True)
    (second_plugin / "manifest.json").write_text(
        json.dumps({"id": "zotflow", "version": "1.6.6", "minAppVersion": "1.13.4"}),
        encoding="utf-8",
    )
    (second / ".obsidian" / "community-plugins.json").write_text(
        "[]" if disable_second else '["zotflow"]', encoding="utf-8"
    )
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[
            FolderRegistration(folder_id="vault-a", root=first),
            FolderRegistration(folder_id="vault-b", root=second),
        ],
        sources=[
            KnowledgeSourceRegistration(
                source_id="d742d7a9-e882-45fc-b81c-e467b698eefa", folder_id="vault-a"
            ),
            KnowledgeSourceRegistration(
                source_id="5ea83d2b-3f16-49d3-a061-53c96834d2d3", folder_id="vault-b"
            ),
        ],
    ))
    config_path = _obsidian_config(tmp_path, {
        _VAULT_A_ID: first, _VAULT_B_ID: second,
    })
    calls: list[list[str]] = []

    def cli_runner(argv, **_kwargs):
        calls.append(list(argv))
        vault_id = argv[1].removeprefix("vault=")
        assert vault_id in {_VAULT_A_ID, _VAULT_B_ID}
        vault = first if vault_id == _VAULT_A_ID else second
        return SimpleNamespace(returncode=0, stdout="=> " + json.dumps({
            "protocol": "zotflow-local-v1",
            "vault": str(vault),
            "enabled": not (
                (disable_first and vault == first) or (disable_second and vault == second)
            ),
            "local": True,
            "storagePath": str(pdf.parent.parent),
        }))

    def open_runner(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    return RegisteredSourceZotFlowAdapter(
        registry,
        app_path=app,
        runner=open_runner,
        cli_runner=cli_runner,
        zotero_factory=lambda: _LocalZotero(pdf),
        obsidian_config_path=config_path,
    ), calls


def test_two_eligible_registered_vaults_fail_closed_without_source_choice(tmp_path: Path):
    adapter, calls = _registered_adapter(tmp_path)

    capability = adapter.probe_attachment(_ref())
    assert capability.available is False
    assert "select a Source" in (capability.reason or "")
    with pytest.raises(ZotFlowError, match="select a Source"):
        adapter.open_attachment(_ref())
    assert all(call[0] != "/usr/bin/open" for call in calls)


def test_same_named_registered_vaults_route_by_id(tmp_path: Path):
    adapter, calls = _registered_adapter(tmp_path, disable_second=True)
    duplicate = tmp_path / "elsewhere" / "Alpha Vault"
    duplicate.mkdir(parents=True)
    document = adapter.registry.load_document()
    document.folders[1].root = duplicate
    adapter.registry.save(document)
    _obsidian_config(tmp_path, {_VAULT_A_ID: tmp_path / "Alpha Vault", _VAULT_B_ID: duplicate})

    capability = adapter.probe_attachment(_ref())
    assert capability.available is True
    assert adapter.open_attachment(_ref()) == {"opened": True}
    assert parse_qs(urlsplit(calls[-1][1]).query)["vault"] == [_VAULT_A_ID]


@pytest.mark.parametrize(
    ("disabled", "expected"),
    [("first", _VAULT_B_ID), ("second", _VAULT_A_ID)],
)
def test_only_eligible_registered_vault_is_the_uri_destination(
    tmp_path: Path, disabled: str, expected: str
):
    adapter, calls = _registered_adapter(
        tmp_path,
        disable_first=disabled == "first",
        disable_second=disabled == "second",
    )

    assert adapter.open_attachment(_ref()) == {"opened": True}
    uri = calls[-1][1]
    assert parse_qs(urlsplit(uri).query)["vault"] == [expected]
    with pytest.raises(ValidationError):
        PdfRef.model_validate({**_ref().model_dump(), "vault": "Beta Vault"})
    with pytest.raises(InvalidActionTarget):
        ZotFlowLauncher(adapter).open(
            json.dumps({**_ref().model_dump(), "vault": "Unregistered Vault"})
        )
    assert len([call for call in calls if call[0] == "/usr/bin/open"]) == 1


@pytest.mark.parametrize(
    "condition",
    [
        "local_off", "wrong_vault", "wrong_storage", "linked_file",
        "missing_pdf", "wrong_filename", "cli_failed",
    ],
)
def test_zotflow_rejects_unverified_or_nonlocal_pdf_without_launch(
    tmp_path: Path, condition: str
):
    vault, app, pdf = _ready_vault(tmp_path)
    if condition == "missing_pdf":
        pdf.unlink()
    adapter, calls = _adapter(
        vault,
        app,
        pdf,
        local=condition != "local_off",
        vault_in_cli=tmp_path / "other" if condition == "wrong_vault" else None,
        storage_in_cli=tmp_path / "other" if condition == "wrong_storage" else None,
        link_mode="linked_file" if condition == "linked_file" else "imported_file",
        filename="other.pdf" if condition == "wrong_filename" else None,
        cli_returncode=1 if condition == "cli_failed" else 0,
    )

    assert adapter.probe_attachment(_ref()).available is False
    with pytest.raises(ZotFlowError):
        adapter.open_attachment(_ref())
    assert all(call[0] != "/usr/bin/open" for call in calls)


def test_zotflow_rechecks_local_mode_when_action_is_executed(tmp_path: Path):
    vault, app, pdf = _ready_vault(tmp_path)
    local = True
    calls: list[list[str]] = []

    def cli_runner(argv, **_kwargs):
        calls.append(list(argv))
        payload = {
            "protocol": "zotflow-local-v1",
            "vault": str(vault),
            "enabled": True,
            "local": local,
            "storagePath": str(pdf.parent.parent),
        }
        return SimpleNamespace(returncode=0, stdout="=> " + json.dumps(payload), stderr="")

    adapter = ZotFlowReaderAdapter(
        vault,
        app_path=app,
        runner=lambda argv, **_kwargs: calls.append(list(argv)),
        cli_runner=cli_runner,
        zotero_factory=lambda: _LocalZotero(pdf),
        obsidian_config_path=_obsidian_config(tmp_path, {_VAULT_A_ID: vault}),
    )
    assert adapter.probe_attachment(_ref()).available is True
    local = False

    with pytest.raises(ZotFlowError):
        adapter.open_attachment(_ref())
    assert all(call[0] != "/usr/bin/open" for call in calls)


def test_zotflow_direct_open_rejects_same_path_pdf_byte_replacement(tmp_path: Path):
    vault, app, pdf = _ready_vault(tmp_path)
    adapter, calls = _adapter(vault, app, pdf)
    assert adapter.probe_attachment(_ref()).available is True
    pdf.write_bytes(b"%PDF-1.7\nchanged")

    with pytest.raises(ZotFlowError, match="content hash"):
        adapter.open_attachment(_ref())
    assert all(call[0] != "/usr/bin/open" for call in calls)


def test_zotflow_unknown_plugin_version_is_not_trusted_for_local_first(tmp_path: Path):
    vault, app, pdf = _ready_vault(tmp_path, plugin_version="1.7.0")
    adapter, calls = _adapter(vault, app, pdf)

    capability = adapter.probe_attachment(_ref())

    assert capability.available is False
    assert "audited" in (capability.reason or "").lower()
    with pytest.raises(ZotFlowError):
        adapter.open_attachment(_ref())
    assert all(call[0] != "/usr/bin/open" for call in calls)
