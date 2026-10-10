"""Independent synthetic contracts for paper-unit supplemental asset inventory.

ASSETS-EXPECTED.md precedes production implementation. The expected membership is
hand-written below; the query, renderer, and manifest loader are not test oracles.
Preparation and execution are separate; this module is not self-run.
"""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

import pytest
import yaml

from scholar_workflow.knowledge.catalog_models import HubAsset
from tests.contract.test_field_paper_units import (
    ALPHA,
    ALPHA_ANALYSIS,
    ALPHA_CANVAS,
    ALPHA_SIDECAR,
    BETA,
    FIELD_A,
    GAMMA,
    GAMMA_ANALYSIS,
    GAMMA_CANVAS,
    OTHER,
    PATHS,
    READY_FILES,
    SOURCE_A,
    SOURCE_B,
    VAULT_A,
    VAULT_B,
    PaperUnitCorpus,
    _assert_uri,
    _files,
    _invoke,
    _query,
    _query_guard,
    _render,
    _save_snapshot_input,
    _snapshot_input,
    _units,
    ownership_scope,  # noqa: F401
    paper_unit_corpus,  # noqa: F401
)

MANIFEST = ".scholar-workflow/assets.yml"
SYNTHETIC_HASH = "sha256:" + "7" * 64
ASSET_BYTES = b"Synthetic asset bytes: queries must not read or hash these.\n"
ALPHA_FOLDER = "research/resources/papers/ownership/attachments"
OTHER_SIDECAR = "analysis:paper:synthetic:other-field:sidecar"
GAMMA_SIDECAR = "analysis:paper:synthetic:gamma:sidecar"
CATALOG_ID = "asset:synthetic:catalog-only"
SHARED_ID = "asset:synthetic:shared"
FIGURE_ID = "asset:synthetic:alpha-figure"
EXTERNAL_FIGURE_ID = "asset:synthetic:gamma-figure"
EXCLUDED_ID = "asset:synthetic:other-field"
NEIGHBOR = ALPHA_FOLDER + "/Undeclared same-title figure.png"


def _asset(identity: str, owners: list[str], path: str, name: str,
           media: str = "application/octet-stream", role: str = "supplement") -> dict:
    # Recorded hash/size are deliberately metadata, not claims about these bytes.
    return HubAsset(asset_id=identity, owner_artifact_ids=owners, vault_path=path,
                    display_name=name, media_type=media, size=999,
                    sha256=SYNTHETIC_HASH, role=role).model_dump(mode="json")


LOCAL_ASSETS = [
    _asset(FIGURE_ID, [ALPHA_ANALYSIS], ALPHA_FOLDER + "/Figure.png",
           "Figure [draft](x) #1.png", "image/png", "embed"),
    _asset("asset:synthetic:measurements", [ALPHA_ANALYSIS], ALPHA_FOLDER + "/measurements.csv",
           "Measurements.csv", "text/csv", "data"),
    _asset("asset:synthetic:appendix", [ALPHA_CANVAS], ALPHA_FOLDER + "/appendix.bin", "Appendix.bin"),
    _asset("asset:synthetic:source", [ALPHA_ANALYSIS], ALPHA_FOLDER + "/source-region.txt",
           "Source region.txt", "text/plain", "source"),
    _asset(SHARED_ID, [ALPHA_ANALYSIS, ALPHA_CANVAS], ALPHA_FOLDER + "/shared.png",
           "Shared figure.png", "image/png", "embed"),
    _asset("asset:synthetic:sidecar-data", [ALPHA_SIDECAR], ALPHA_FOLDER + "/sidecar-data.npz",
           "Sidecar data.npz", role="data"),
    _asset("asset:synthetic:legacy", [ALPHA_ANALYSIS], "attachments/Legacy supplement.bin",
           "Legacy supplement.bin"),
]
EXTERNAL_ASSETS = [
    _asset(EXTERNAL_FIGURE_ID, [GAMMA_ANALYSIS], ALPHA_FOLDER + "/Figure.png",
           "Figure [draft](x) #1.png", "image/png", "embed"),
    _asset("asset:synthetic:gamma-data", [GAMMA_CANVAS], ALPHA_FOLDER + "/gamma-data.csv",
           "Gamma data.csv", "text/csv", "data"),
]
CATALOG_ASSET = _asset(CATALOG_ID, [ALPHA_ANALYSIS], ALPHA_FOLDER + "/catalog-only.bin",
                       "Catalog supplement.bin")
EXCLUDED_ASSET = _asset(EXCLUDED_ID, [OTHER_SIDECAR],
                        "comparison/resources/papers/other/attachments/Figure.png",
                        "Figure [draft](x) #1.png", "image/png", "embed")
EXPECTED_ASSETS = {
    (SOURCE_A, ALPHA): {row["asset_id"]: row for row in [*LOCAL_ASSETS, CATALOG_ASSET]},
    (SOURCE_A, BETA): {},
    (SOURCE_B, GAMMA): {row["asset_id"]: row for row in EXTERNAL_ASSETS},
}


def _write_manifest(root: Path, rows: list[dict]) -> None:
    (root / MANIFEST).write_text(yaml.safe_dump({"schema_version": 1, "assets": rows},
                                               allow_unicode=True), encoding="utf-8")


def _write_asset_files(root: Path, rows: list[dict]) -> None:
    for row in rows:
        path = root / row["vault_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ASSET_BYTES)


def _declare_artifacts(provider: Path, owner: str, analysis: str, canvas: str,
                       sidecar: str) -> None:
    value = _snapshot_input(provider)
    for identity, kind, path, catalog_kind, fmt in (
        (analysis, "analysis_markdown", PATHS[ALPHA_ANALYSIS], "paper-analysis", "markdown"),
        (canvas, "analysis_canvas", PATHS[ALPHA_CANVAS], "analysis-canvas", "canvas"),
    ):
        value["artifacts"].append({"artifact_id": identity, "resource_id": owner,
                                    "kind": kind, "vault_path": path, "sha256": SYNTHETIC_HASH})
        value["catalog"]["artifacts"].append({"artifact_id": identity, "resource_id": owner,
                                               "kind": catalog_kind, "format": fmt,
                                               "vault_path": path, "revision": SYNTHETIC_HASH})
    value["artifacts"].append({"artifact_id": sidecar, "resource_id": owner,
                                "kind": "analysis_sidecar", "vault_path": PATHS[ALPHA_SIDECAR],
                                "sha256": SYNTHETIC_HASH})
    next(row for row in value["catalog"]["resources"]
         if row["resource_id"] == owner)["artifact_ids"] = [analysis, canvas]
    _save_snapshot_input(provider, value)


@pytest.fixture
def paper_asset_corpus(paper_unit_corpus: PaperUnitCorpus) -> PaperUnitCorpus:
    corpus = paper_unit_corpus
    scope = corpus.scope
    _declare_artifacts(scope.provider, ALPHA, ALPHA_ANALYSIS, ALPHA_CANVAS, ALPHA_SIDECAR)
    _declare_artifacts(corpus.external_provider, GAMMA, GAMMA_ANALYSIS, GAMMA_CANVAS, GAMMA_SIDECAR)
    for root in scope.source_roots.values():
        (root / PATHS[ALPHA_SIDECAR]).write_bytes(b'{"synthetic": "unread sidecar body"}\n')
    other_sidecar_path = "comparison/resources/papers/other/analysis.baseline.json"
    (scope.root / other_sidecar_path).write_bytes(b'{"synthetic": "unread other Field"}\n')
    value = _snapshot_input(scope.provider)
    value["artifacts"].append({"artifact_id": OTHER_SIDECAR, "resource_id": OTHER,
                                "kind": "analysis_sidecar", "vault_path": other_sidecar_path,
                                "sha256": SYNTHETIC_HASH})
    value["catalog"]["assets"] = [copy.deepcopy(CATALOG_ASSET)]
    _save_snapshot_input(scope.provider, value)
    _write_asset_files(scope.root, [*LOCAL_ASSETS, CATALOG_ASSET, EXCLUDED_ASSET])
    _write_asset_files(scope.source_roots[SOURCE_B], EXTERNAL_ASSETS)
    _write_manifest(scope.root, [*LOCAL_ASSETS, EXCLUDED_ASSET])
    _write_manifest(scope.source_roots[SOURCE_B], EXTERNAL_ASSETS)
    (scope.root / NEIGHBOR).write_bytes(ASSET_BYTES)
    # Even a body embed does not declare an asset relationship.
    (scope.root / PATHS[ALPHA]).write_text("# Synthetic paper\n![[attachments/Undeclared same-title figure.png]]\n",
                                         encoding="utf-8")
    return corpus


def _assert_asset(row: dict, expected: dict, *, state: str = "available") -> None:
    assert row["object_id"] == expected["asset_id"]
    assert row["title"] == expected["display_name"]
    assert row["relative_path"] == expected["vault_path"]
    assert row["kind"] and row["kind"] not in {"paper", "primary", "analysis", "analysis_markdown",
                                                "analysis_canvas", "reading_note", "annotations"}
    assert row["file_state"] == state
    assert row["open_state"] == ("unsupported_type" if state == "available" else "file_unavailable")
    assert row["uri"] is None


def _assert_asset_issue(payload: dict, source_id: str, *, changed: bool = False) -> None:
    assert payload["status"] == "partial"
    matches = [row for row in payload["issues"]
               if row["source_id"] == source_id and "asset" in row["code"].lower()]
    assert matches, payload["issues"]
    if changed:
        assert any("chang" in row["code"].lower() for row in matches)


def test_all_asset_roles_and_provider_sidecar_owners_join_existing_files(paper_asset_corpus):
    payload = _query(paper_asset_corpus)
    units = _units(payload)
    assert payload["schema_version"] == 1 and payload["status"] == "complete"
    assert payload["issues"] == payload["unresolved_references"] == []
    assert set(units) == set(READY_FILES)
    for key, expected_assets in EXPECTED_ASSETS.items():
        files = _files(units[key])
        expected_ids = set(READY_FILES[key]) | set(expected_assets)
        if key == (SOURCE_A, ALPHA):
            expected_ids.add(ALPHA_SIDECAR)
        elif key == (SOURCE_B, GAMMA):
            expected_ids.add(GAMMA_SIDECAR)
        assert set(files) == expected_ids
        for identity, expected in expected_assets.items():
            _assert_asset(files[identity], expected)
        for identity, path in READY_FILES[key].items():
            _assert_uri(files[identity], VAULT_A if key[0] == SOURCE_A else VAULT_B, path)
        assert units[key]["ownership"]["status"] == "resolved"
    assert EXCLUDED_ID not in json.dumps(payload) and NEIGHBOR not in json.dumps(payload)


def test_multi_owner_and_catalog_portable_duplicate_is_one_supplement(paper_asset_corpus):
    corpus = paper_asset_corpus
    value = _snapshot_input(corpus.scope.provider)
    value["catalog"]["assets"].append(copy.deepcopy(next(row for row in LOCAL_ASSETS
                                                      if row["asset_id"] == SHARED_ID)))
    _save_snapshot_input(corpus.scope.provider, value)
    payload = _query(corpus)
    assert payload["status"] == "complete" and payload["issues"] == []
    alpha = _units(payload)[SOURCE_A, ALPHA]
    assert len([row for row in alpha["files"] if row["object_id"] == SHARED_ID]) == 1
    assert CATALOG_ID in _files(alpha)


def test_same_owner_set_in_different_order_is_consistent_catalog_portable_declaration(paper_asset_corpus):
    corpus = paper_asset_corpus
    shared = copy.deepcopy(next(row for row in LOCAL_ASSETS if row["asset_id"] == SHARED_ID))
    shared["owner_artifact_ids"].reverse()
    value = _snapshot_input(corpus.scope.provider)
    value["catalog"]["assets"].append(shared)
    _save_snapshot_input(corpus.scope.provider, value)
    payload = _query(corpus)
    assert payload["status"] == "complete" and payload["issues"] == []
    alpha = _units(payload)[SOURCE_A, ALPHA]
    assert len([row for row in alpha["files"] if row["object_id"] == SHARED_ID]) == 1


@pytest.mark.parametrize("conflict", ["id", "path", "owners"])
def test_catalog_portable_conflict_has_no_first_winning_file(paper_asset_corpus, conflict):
    corpus = paper_asset_corpus
    conflicting = copy.deepcopy(CATALOG_ASSET)
    if conflict == "id":
        conflicting["vault_path"] = ALPHA_FOLDER + "/Conflicting choice.md"
        conflicting["display_name"] = "Conflicting choice.md"
        conflicting["media_type"] = "text/markdown"
    elif conflict == "path":
        conflicting["asset_id"] = "asset:synthetic:competing-path"
    else:
        conflicting["owner_artifact_ids"] = [ALPHA_CANVAS]
    _write_asset_files(corpus.scope.root, [conflicting])
    _write_manifest(corpus.scope.root, [*LOCAL_ASSETS, EXCLUDED_ASSET, conflicting])
    payload = _query(corpus)
    _assert_asset_issue(payload, SOURCE_A)
    files = _files(_units(payload)[SOURCE_A, ALPHA])
    assert not ({CATALOG_ID, conflicting["asset_id"]} & set(files))
    assert not ({CATALOG_ASSET["vault_path"], conflicting["vault_path"]}
                & {row["relative_path"] for row in files.values()})
    _assert_asset(files[FIGURE_ID], LOCAL_ASSETS[0])
    _assert_uri(files[ALPHA_ANALYSIS], VAULT_A, PATHS[ALPHA_ANALYSIS])


def test_explicit_asset_shared_by_two_papers_is_listed_once_under_each_owner(paper_asset_corpus):
    corpus = paper_asset_corpus
    beta_sidecar = "analysis:paper:synthetic:beta:sidecar"
    beta_path = "research/resources/papers/beta/analysis.baseline.json"
    (corpus.scope.root / beta_path).write_bytes(b'{"synthetic": "unread sparse-paper sidecar"}\n')
    value = _snapshot_input(corpus.scope.provider)
    value["artifacts"].append({"artifact_id": beta_sidecar, "resource_id": BETA,
                                "kind": "analysis_sidecar", "vault_path": beta_path,
                                "sha256": SYNTHETIC_HASH})
    _save_snapshot_input(corpus.scope.provider, value)
    shared = _asset("asset:synthetic:cross-paper", [ALPHA_ANALYSIS, beta_sidecar],
                    "attachments/Cross-paper supplement.bin", "Cross-paper supplement.bin")
    _write_asset_files(corpus.scope.root, [shared])
    _write_manifest(corpus.scope.root, [*LOCAL_ASSETS, EXCLUDED_ASSET, shared])
    payload = _query(corpus)
    assert payload["status"] == "complete" and payload["issues"] == []
    units = _units(payload)
    assert set(units) == set(READY_FILES)
    for key in ((SOURCE_A, ALPHA), (SOURCE_A, BETA)):
        _assert_asset(_files(units[key])[shared["asset_id"]], shared)
        assert len([row for row in units[key]["files"] if row["object_id"] == shared["asset_id"]]) == 1
    assert shared["asset_id"] not in _files(units[SOURCE_B, GAMMA])


def test_same_asset_id_in_two_sources_keeps_both_qualified_supplements(paper_asset_corpus):
    corpus = paper_asset_corpus
    external = copy.deepcopy(EXTERNAL_ASSETS)
    external[0]["asset_id"] = FIGURE_ID
    _write_manifest(corpus.scope.source_roots[SOURCE_B], external)
    payload = _query(corpus)
    assert payload["status"] == "complete" and payload["issues"] == []
    units = _units(payload)
    _assert_asset(_files(units[SOURCE_A, ALPHA])[FIGURE_ID], LOCAL_ASSETS[0])
    _assert_asset(_files(units[SOURCE_B, GAMMA])[FIGURE_ID], external[0])
    assert set(units) == set(READY_FILES)


@pytest.mark.parametrize("empty", ["absent", "valid-empty"])
def test_optional_manifest_without_portable_assets_preserves_catalog_assets(paper_asset_corpus, empty):
    corpus = paper_asset_corpus
    for root in corpus.scope.source_roots.values():
        if empty == "absent":
            (root / MANIFEST).unlink()
        else:
            _write_manifest(root, [])
    payload = _query(corpus)
    assert payload["status"] == "complete" and payload["issues"] == []
    units = _units(payload)
    _assert_asset(_files(units[SOURCE_A, ALPHA])[CATALOG_ID], CATALOG_ASSET)
    all_ids = {row["object_id"] for unit in units.values() for row in unit["files"]}
    assert not (all_ids & {row["asset_id"] for row in [*LOCAL_ASSETS, *EXTERNAL_ASSETS]})


def test_optional_manifest_appearing_after_absence_does_not_invent_known_asset_relations(paper_asset_corpus):
    corpus = paper_asset_corpus
    scope = corpus.scope
    target = scope.root / MANIFEST
    target.unlink()
    appeared = yaml.safe_dump({"schema_version": 1, "assets": [*LOCAL_ASSETS, EXCLUDED_ASSET]})
    injected = []
    with _query_guard(corpus) as (workflow, patch):
        original_read = workflow._read_declaration

        def manifest_appears(root, relative_path, limit):
            try:
                return original_read(root, relative_path, limit)
            except FileNotFoundError:
                if Path(root) == scope.root and str(relative_path) == MANIFEST and not injected:
                    # The first observation is genuinely absent. Only the
                    # independent fixture writer creates a later declaration.
                    scope.fixture_writer_active = True
                    try:
                        target.write_text(appeared, encoding="utf-8")
                    finally:
                        scope.fixture_writer_active = False
                    injected.append(True)
                raise

        patch.setattr(workflow, "_read_declaration", manifest_appears)
        try:
            payload = workflow.field_paper_units(scope.registry.path, source_id=SOURCE_A,
                                                 field_id=FIELD_A, reader_config_path=corpus.reader_config)
        finally:
            if injected:
                # Restore the fixture before the unchanged-bytes guard exits.
                scope.fixture_writer_active = True
                try:
                    target.unlink()
                finally:
                    scope.fixture_writer_active = False
    assert injected == [True] and not target.exists()
    _assert_asset_issue(payload, SOURCE_A, changed=True)
    files = _files(_units(payload)[SOURCE_A, ALPHA])
    assert not ({row["asset_id"] for row in LOCAL_ASSETS} & set(files))
    _assert_asset(files[CATALOG_ID], CATALOG_ASSET)


def test_external_assets_use_owning_source_even_when_local_relative_path_is_missing(paper_asset_corpus):
    corpus = paper_asset_corpus
    (corpus.scope.root / LOCAL_ASSETS[0]["vault_path"]).unlink()
    payload = _query(corpus)
    units = _units(payload)
    _assert_asset(_files(units[SOURCE_A, ALPHA])[FIGURE_ID], LOCAL_ASSETS[0], state="missing")
    _assert_asset(_files(units[SOURCE_B, GAMMA])[EXTERNAL_FIGURE_ID], EXTERNAL_ASSETS[0])
    assert payload["status"] == "partial"
    assert EXTERNAL_FIGURE_ID not in _files(units[SOURCE_A, ALPHA])
    assert FIGURE_ID not in _files(units[SOURCE_B, GAMMA])


def test_foreign_artifact_id_is_not_borrowed_into_local_paper(paper_asset_corpus):
    corpus = paper_asset_corpus
    foreign = _asset("asset:synthetic:foreign-owner", [GAMMA_ANALYSIS], ALPHA_FOLDER + "/foreign.png",
                     "Foreign owner.png", "image/png", "embed")
    _write_asset_files(corpus.scope.root, [foreign])
    _write_manifest(corpus.scope.root, [*LOCAL_ASSETS, EXCLUDED_ASSET, foreign])
    payload = _query(corpus)
    assert foreign["asset_id"] not in {row["object_id"] for unit in payload["paper_units"]
                                       for row in unit["files"]}
    assert set(_units(payload)) == set(READY_FILES)


@pytest.mark.parametrize("unsafe", ["missing", "symlink-leaf", "symlink-parent", "directory", "fifo"])
def test_unavailable_asset_retains_declaration_without_body_read_or_open(paper_asset_corpus, unsafe):
    corpus = paper_asset_corpus
    expected = LOCAL_ASSETS[0]
    path = corpus.scope.root / expected["vault_path"]
    path.unlink()
    if unsafe == "symlink-leaf":
        private = corpus.scope.root / "private-image-body.png"
        private.write_bytes(b"Private synthetic target must never be read\n")
        path.symlink_to(private)
    elif unsafe == "symlink-parent":
        parent = path.parent
        moved = parent.with_name("unread-attachment-target")
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
    elif unsafe == "directory":
        path.mkdir()
    elif unsafe == "fifo":
        os.mkfifo(path)
    payload = _query(corpus)
    alpha = _units(payload)[SOURCE_A, ALPHA]
    _assert_asset(_files(alpha)[FIGURE_ID], expected,
                  state="missing" if unsafe == "missing" else "unsafe")
    assert payload["status"] == "partial" and CATALOG_ID in _files(alpha)
    assert _files(alpha)[ALPHA_ANALYSIS]["open_state"] == "ready"


@pytest.mark.parametrize("failure", ["malformed", "schema", "invalid-entry", "duplicate-id",
                                     "duplicate-path", "oversized", "directory", "symlink", "unreadable"])
def test_bad_manifest_is_source_diagnostic_with_catalog_inventory_retained(paper_asset_corpus,
                                                                         monkeypatch, failure):
    corpus = paper_asset_corpus
    target = corpus.scope.root / MANIFEST
    if failure == "malformed":
        target.write_text("assets: [unterminated\n", encoding="utf-8")
    elif failure == "schema":
        target.write_text("schema_version: 2\nassets: []\n", encoding="utf-8")
    elif failure == "invalid-entry":
        _write_manifest(corpus.scope.root, [LOCAL_ASSETS[0], {"asset_id": "asset:synthetic:invalid"}])
    elif failure in {"duplicate-id", "duplicate-path"}:
        duplicate = copy.deepcopy(LOCAL_ASSETS[0])
        if failure == "duplicate-id":
            duplicate["vault_path"] = ALPHA_FOLDER + "/duplicate.png"
        else:
            duplicate["asset_id"] = "asset:synthetic:duplicate-path"
        _write_manifest(corpus.scope.root, [*LOCAL_ASSETS, duplicate])
    elif failure == "oversized":
        target.write_text("schema_version: 1\nassets: []\n#" + "x" * (2 * 1024 * 1024), encoding="utf-8")
    elif failure in {"directory", "symlink"}:
        target.unlink()
        if failure == "directory":
            target.mkdir()
        else:
            private = corpus.scope.root / "private-manifest.yml"
            private.write_text("schema_version: 1\nassets: []\n", encoding="utf-8")
            target.symlink_to(private)
    else:
        original_open = os.open

        def unreadable(path, flags, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).name == "assets.yml":
                raise PermissionError("Synthetic manifest access denied")
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", unreadable)
    payload = _query(corpus)
    _assert_asset_issue(payload, SOURCE_A)
    units = _units(payload)
    assert set(units) == set(READY_FILES)
    alpha = units[SOURCE_A, ALPHA]
    _assert_asset(_files(alpha)[CATALOG_ID], CATALOG_ASSET)
    _assert_uri(_files(alpha)[ALPHA_ANALYSIS], VAULT_A, PATHS[ALPHA_ANALYSIS])
    if failure == "invalid-entry":
        _assert_asset(_files(alpha)[FIGURE_ID], LOCAL_ASSETS[0])


@pytest.mark.parametrize("native_asset", [False, True])
@pytest.mark.parametrize("replace_on_read", [1, 2])
def test_same_byte_manifest_replacement_is_changed_not_complete(paper_asset_corpus, monkeypatch,
                                                               native_asset, replace_on_read):
    corpus = paper_asset_corpus
    scope = corpus.scope
    target = scope.root / MANIFEST
    native = _asset("asset:synthetic:native-race", [ALPHA_ANALYSIS],
                    ALPHA_FOLDER + "/Native supplement.md", "Native supplement.md", "text/markdown")
    expected_rows = list(LOCAL_ASSETS)
    if native_asset:
        _write_asset_files(scope.root, [native])
        expected_rows.append(native)
        _write_manifest(scope.root, [*expected_rows, EXCLUDED_ASSET])
    content = target.read_bytes()
    original_identity = (target.stat().st_dev, target.stat().st_ino)
    original_fdopen = os.fdopen
    injected = []
    reads = []

    class ConcurrentManifestReplacement:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def read(self, *args, **kwargs):
            raw = self.stream.read(*args, **kwargs)
            reads.append(True)
            # Read 1 is the initial bounded acquisition; read 2 is the later
            # completion recheck. Only the latter has established relations.
            if len(reads) == replace_on_read and not injected:
                replacement = target.with_name("assets.fixture-replacement.yml")
                scope.fixture_writer_active = True
                try:
                    replacement.write_bytes(content)
                    replacement.replace(target)
                finally:
                    scope.fixture_writer_active = False
                injected.append(True)
            return raw

    def racing_fdopen(descriptor, *args, **kwargs):
        info = os.fstat(descriptor)
        stream = original_fdopen(descriptor, *args, **kwargs)
        return (ConcurrentManifestReplacement(stream)
                if (info.st_dev, info.st_ino) == original_identity else stream)

    monkeypatch.setattr(os, "fdopen", racing_fdopen)
    payload = _query(corpus)
    assert injected == [True] and target.read_bytes() == content
    _assert_asset_issue(payload, SOURCE_A, changed=replace_on_read == 2)
    alpha = _units(payload)[SOURCE_A, ALPHA]
    if replace_on_read == 1:
        # The safe declaration reader rejected its initial racing acquisition.
        # No portable asset relation has become known from that failed read.
        assert not ({row["asset_id"] for row in expected_rows} & set(_files(alpha)))
        _assert_asset(_files(alpha)[CATALOG_ID], CATALOG_ASSET)
        return
    for expected in expected_rows:
        row = _files(alpha)[expected["asset_id"]]
        assert row["relative_path"] == expected["vault_path"] and row["uri"] is None
    if native_asset:
        row = _files(alpha)[native["asset_id"]]
        assert row["file_state"] == "available" and row["open_state"] == "ownership_unresolved"


@pytest.mark.parametrize("source_id,owner_id,producer,vault", [
    (SOURCE_A, ALPHA, ALPHA_ANALYSIS, VAULT_A),
    (SOURCE_B, GAMMA, GAMMA_ANALYSIS, VAULT_B),
])
def test_markdown_asset_reuses_safe_native_action_without_becoming_primary(paper_asset_corpus,
                                                                         source_id, owner_id, producer, vault):
    corpus = paper_asset_corpus
    root = corpus.scope.source_roots[source_id]
    native = _asset("asset:synthetic:native", [producer],
                    ALPHA_FOLDER + "/Supplement #1 & [draft](x).md", "Supplement #1 & [draft](x).md",
                    "text/markdown")
    _write_asset_files(root, [native])
    originals = [*LOCAL_ASSETS, EXCLUDED_ASSET] if source_id == SOURCE_A else EXTERNAL_ASSETS
    _write_manifest(root, [*originals, native])
    payload = _query(corpus)
    assert payload["status"] == "complete" and payload["issues"] == []
    units = _units(payload)
    assert set(units) == set(READY_FILES)
    row = _files(units[source_id, owner_id])[native["asset_id"]]
    assert row["kind"] == "asset" and row["title"] == native["display_name"]
    _assert_uri(row, vault, native["vault_path"])
    assert native["asset_id"] not in _files(units[SOURCE_A, BETA])


def test_markdown_asset_replaced_after_native_validation_loses_candidate_at_completion(paper_asset_corpus):
    corpus = paper_asset_corpus
    scope = corpus.scope
    native = _asset("asset:synthetic:native-file-race", [ALPHA_ANALYSIS],
                    ALPHA_FOLDER + "/Changing supplement.md", "Changing supplement.md", "text/markdown")
    _write_asset_files(scope.root, [native])
    _write_manifest(scope.root, [*LOCAL_ASSETS, EXCLUDED_ASSET, native])
    target = scope.root / native["vault_path"]
    injected = []
    with _query_guard(corpus) as (workflow, patch):
        original_identity = workflow._document_identity

        def replace_after_native_validation(root, relative_path):
            identity = original_identity(root, relative_path)
            if Path(root) == scope.root and relative_path == native["vault_path"] and not injected:
                replacement = target.with_name("Changing supplement.fixture-replacement.md")
                scope.fixture_writer_active = True
                try:
                    replacement.write_bytes(ASSET_BYTES)
                    replacement.replace(target)
                finally:
                    scope.fixture_writer_active = False
                injected.append(True)
            return identity

        patch.setattr(workflow, "_document_identity", replace_after_native_validation)
        payload = workflow.field_paper_units(scope.registry.path, source_id=SOURCE_A,
                                             field_id=FIELD_A, reader_config_path=corpus.reader_config)
    assert injected == [True]
    _assert_asset_issue(payload, SOURCE_A, changed=True)
    row = _files(_units(payload)[SOURCE_A, ALPHA])[native["asset_id"]]
    _assert_asset(row, native, state="unsafe")


@pytest.mark.parametrize("language", ["en", "zh"])
def test_human_assets_are_readable_supplements_with_honest_unsupported_status(paper_asset_corpus, language):
    corpus = paper_asset_corpus
    payload = _query(corpus)
    text = _render(corpus, payload, language)
    assert ("其他附件" if language == "zh" else "Other attachments") in text
    for expected in [*LOCAL_ASSETS, CATALOG_ASSET, *EXTERNAL_ASSETS]:
        escaped = expected["display_name"].replace("[", "\\[").replace("]", "\\]").replace("#", "\\#")
        assert escaped in text
        assert expected["asset_id"] not in text and expected["sha256"] not in text
    assert ("不支持原生打开" if language == "zh" else "Unsupported type") in text
    assert "[draft](x)" not in text and "[[" not in text
    assert str(corpus.scope.root) not in text and str(corpus.scope.registry.path) not in text
    assert not re.search(r"opened successfully|GUI verified|integrity verified|已成功打开|人工验收通过|完整性已验证",
                         text, re.IGNORECASE)
    assert "obsidian://open?" in text


@pytest.mark.parametrize("fmt", ["json", "md"])
def test_opt_in_cli_keeps_asset_inventory_in_existing_stdout_result(paper_asset_corpus, fmt):
    result = _invoke(paper_asset_corpus, "--paper-units", "--source-id", SOURCE_A,
                     "--field-id", FIELD_A, "--format", fmt, "--language", "en")
    assert result.exit_code == 0, result.output
    if fmt == "json":
        payload = json.loads(result.output)
        assert set(_units(payload)) == set(READY_FILES)
        for key, expected_assets in EXPECTED_ASSETS.items():
            files = _files(_units(payload)[key])
            for identity, expected in expected_assets.items():
                _assert_asset(files[identity], expected)
    else:
        assert "Other attachments" in result.output and "Catalog supplement.bin" in result.output
        assert "Unsupported type" in result.output


def test_ordinary_field_list_keeps_legacy_envelope_and_avoids_asset_reads(paper_asset_corpus, monkeypatch):
    original_open = os.open

    def forbidden_asset_read(path, flags, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).name == "assets.yml":
            pytest.fail("Ordinary Field list attempted to acquire an asset manifest")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", forbidden_asset_read)
    result = _invoke(paper_asset_corpus, "--format", "json")
    assert result.exit_code == 0, result.output
    assert set(json.loads(result.output)) == {"schema_version", "fields"}
    assert "paper_units" not in result.output and FIGURE_ID not in result.output
