"""Vault assets use one explicit manifest; Markdown embeds are display-only."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scholar_workflow.hub.assets import (
    AssetIntegrityError,
    AssetManifestError,
    InvalidAssetNameError,
    UnknownAssetError,
    VaultAssetCatalogProvider,
    VaultAssetManifestStore,
    VaultAssetStore,
)
from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.models import (
    AssetRole,
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubAsset,
    HubCatalog,
)


def _catalog() -> HubCatalog:
    return HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        artifacts=[
            HubArtifact(
                artifact_id="analysis:paper-one",
                kind=ArtifactKind.PAPER_ANALYSIS,
                format=ArtifactFormat.MARKDOWN,
                vault_path="世界模型/论文分析.md",
            )
        ],
    )


def _stores(tmp_path, *, max_bytes=64 * 1024 * 1024):
    provider = StaticCatalogProvider(_catalog())
    manifest = VaultAssetManifestStore(tmp_path)
    ids = iter(["asset:one", "asset:two", "asset:three"])
    assets = VaultAssetStore(
        tmp_path,
        provider,
        manifest_store=manifest,
        max_bytes=max_bytes,
        id_factory=ids.__next__,
    )
    return manifest, assets


def test_add_writes_human_checkable_manifest_and_provider_overlay(tmp_path):
    manifest, store = _stores(tmp_path)

    added = store.add_bytes(
        "analysis:paper-one",
        "方法概览.png",
        b"png-bytes",
        role=AssetRole.EMBED,
    )

    assert added.asset_id == "asset:one"
    assert added.owner_artifact_ids == ["analysis:paper-one"]
    assert added.vault_path.startswith("attachments/analysis-paper-one-")
    assert added.vault_path.endswith("/方法概览.png")
    assert added.display_name == "方法概览.png"
    assert added.media_type == "image/png"
    assert added.size == len(b"png-bytes")
    assert added.sha256.startswith("sha256:")
    assert (tmp_path / added.vault_path).read_bytes() == b"png-bytes"
    assert store.max_bytes == 64 * 1024 * 1024
    assert store.get(added.asset_id) == added
    assert store.resolve_path(added.asset_id) == (tmp_path / added.vault_path)
    with pytest.raises(UnknownAssetError):
        store.get("asset:missing")

    manifest_text = (tmp_path / ".scholar-workflow" / "assets.yml").read_text(
        encoding="utf-8"
    )
    assert "schema_version: 1" in manifest_text
    assert "asset:one" in manifest_text
    catalog = VaultAssetCatalogProvider(
        StaticCatalogProvider(_catalog()), manifest
    ).load()
    assert catalog.assets == [added]


def test_free_markdown_embed_is_never_inferred_as_an_asset(tmp_path):
    note = tmp_path / "世界模型" / "论文分析.md"
    note.parent.mkdir()
    note.write_text("# 人工正文\n\n![[attachments/unmanaged.png]]\n", encoding="utf-8")
    manifest = VaultAssetManifestStore(tmp_path)

    catalog = VaultAssetCatalogProvider(
        StaticCatalogProvider(_catalog()), manifest
    ).load()

    assert catalog.assets == []
    assert any(row.source == "vault-asset-manifest" for row in catalog.sources)


def test_invalid_and_dangling_manifest_rows_become_diagnostics(tmp_path):
    manifest_path = tmp_path / ".scholar-workflow" / "assets.yml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """schema_version: 1
assets:
  - asset_id: asset:bad-hash
    owner_artifact_ids: [analysis:paper-one]
    vault_path: attachments/paper/bad.png
    display_name: bad.png
    media_type: image/png
    size: 3
    sha256: nope
    role: embed
  - asset_id: asset:dangling
    owner_artifact_ids: [analysis:missing]
    vault_path: attachments/paper/dangling.png
    display_name: dangling.png
    media_type: image/png
    size: 3
    sha256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    role: embed
""",
        encoding="utf-8",
    )

    catalog = VaultAssetCatalogProvider(
        StaticCatalogProvider(_catalog()), VaultAssetManifestStore(tmp_path)
    ).load()

    assert catalog.assets == []
    assert {row.code for row in catalog.diagnostics} >= {
        "invalid-vault-asset",
        "dangling-vault-asset-owner",
    }


def test_missing_manifest_file_is_a_diagnostic_not_a_catalog_asset(tmp_path):
    manifest = VaultAssetManifestStore(tmp_path)
    manifest.save(
        [
            HubAsset(
                asset_id="asset:missing",
                owner_artifact_ids=["analysis:paper-one"],
                vault_path="attachments/paper/missing.png",
                display_name="missing.png",
                media_type="image/png",
                size=3,
                sha256="sha256:" + "a" * 64,
                role=AssetRole.EMBED,
            )
        ]
    )

    catalog = VaultAssetCatalogProvider(
        StaticCatalogProvider(_catalog()), manifest
    ).load()

    assert catalog.assets == []
    assert any(
        row.code == "missing-vault-asset-file" for row in catalog.diagnostics
    )


def test_same_name_never_overwrites_and_gets_a_stable_suffix(tmp_path):
    _manifest, store = _stores(tmp_path)
    first = store.add_bytes("analysis:paper-one", "result.csv", b"first")
    second = store.add_bytes("analysis:paper-one", "result.csv", b"second")

    assert first.vault_path.endswith("/result.csv")
    assert second.vault_path.endswith("/result-2.csv")
    assert second.display_name == "result-2.csv"
    assert (tmp_path / first.vault_path).read_bytes() == b"first"
    assert (tmp_path / second.vault_path).read_bytes() == b"second"


def test_duplicate_generated_id_rolls_back_new_file(tmp_path):
    manifest, first_store = _stores(tmp_path)
    first_store.add_bytes("analysis:paper-one", "first.png", b"first")
    duplicate_store = VaultAssetStore(
        tmp_path,
        StaticCatalogProvider(_catalog()),
        manifest_store=manifest,
        id_factory=lambda: "asset:one",
    )

    with pytest.raises(AssetManifestError, match="generator"):
        duplicate_store.add_bytes("analysis:paper-one", "second.png", b"second")

    assert list((tmp_path / "attachments").rglob("second.png")) == []


def test_provider_and_safe_read_reject_symlink_even_when_it_stays_in_vault(tmp_path):
    manifest, store = _stores(tmp_path)
    added = store.add_bytes("analysis:paper-one", "figure.png", b"content")
    declared = tmp_path / added.vault_path
    target = tmp_path / "real-figure.png"
    target.write_bytes(declared.read_bytes())
    declared.unlink()
    declared.symlink_to(target)

    catalog = VaultAssetCatalogProvider(
        StaticCatalogProvider(_catalog()), manifest
    ).load()

    assert catalog.assets == []
    assert any(row.code == "unsafe-vault-asset-path" for row in catalog.diagnostics)
    with pytest.raises(AssetIntegrityError, match="symlink"):
        store.resolve_path(added.asset_id)


@pytest.mark.parametrize(
    ("replacement", "diagnostic"),
    [
        (b"different-size", "vault-asset-size-drift"),
        (b"changed", "vault-asset-hash-drift"),
    ],
)
def test_provider_rejects_size_and_hash_drift(tmp_path, replacement, diagnostic):
    manifest, store = _stores(tmp_path)
    added = store.add_bytes("analysis:paper-one", "data.bin", b"content")
    (tmp_path / added.vault_path).write_bytes(replacement)

    catalog = VaultAssetCatalogProvider(
        StaticCatalogProvider(_catalog()), manifest
    ).load()

    assert catalog.assets == []
    assert any(row.code == diagnostic for row in catalog.diagnostics)


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        ".hidden",
        "../outside.png",
        "nested/file.png",
        "a\\b.png",
        "bad\0name",
        "bad:name.png",
        "trailing. ",
    ],
)
def test_asset_names_are_single_visible_cross_platform_filenames(tmp_path, name):
    _manifest, store = _stores(tmp_path)

    with pytest.raises(InvalidAssetNameError):
        store.add_bytes("analysis:paper-one", name, b"content")


def test_unknown_owner_and_size_limit_fail_before_writing(tmp_path):
    _manifest, store = _stores(tmp_path, max_bytes=4)

    with pytest.raises(KeyError, match="unknown Hub artifact"):
        store.add_bytes("analysis:missing", "small.bin", b"1234")
    with pytest.raises(ValueError, match="too large"):
        store.add_bytes("analysis:paper-one", "large.bin", b"12345")
    assert not (tmp_path / "attachments").exists()


def test_manifest_failure_rolls_back_new_file(tmp_path, monkeypatch):
    manifest, store = _stores(tmp_path)

    def fail(_assets):
        raise OSError("disk full")

    monkeypatch.setattr(manifest, "save", fail)
    with pytest.raises(OSError, match="disk full"):
        store.add_bytes("analysis:paper-one", "figure.png", b"content")

    assert list((tmp_path / "attachments").rglob("figure.png")) == []


def test_invalid_existing_manifest_is_not_silently_rewritten(tmp_path):
    manifest_path = tmp_path / ".scholar-workflow" / "assets.yml"
    manifest_path.parent.mkdir()
    original = "schema_version: 99\nassets: []\n"
    manifest_path.write_text(original, encoding="utf-8")
    manifest = VaultAssetManifestStore(tmp_path)
    store = VaultAssetStore(
        tmp_path,
        StaticCatalogProvider(_catalog()),
        manifest_store=manifest,
    )

    with pytest.raises(AssetManifestError, match="invalid manifest"):
        store.add_bytes("analysis:paper-one", "figure.png", b"content")

    assert manifest_path.read_text(encoding="utf-8") == original
