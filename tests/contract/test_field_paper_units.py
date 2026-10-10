"""Independent synthetic contracts for opt-in Field paper-unit navigation.

EXPECTED.md was written before implementation. Only fixture declarations supply
the expected inventory; no new resolver or renderer supplies its own oracle.
Preparation and execution are separate: this file is intentionally not self-run.
"""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.adapters.obsidian_registry import (
    resolve_obsidian_reader as _actual_reader,
)
from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.knowledge.catalog_models import HubResource
from scholar_workflow.knowledge.fields import FieldManifest, FieldService
from scholar_workflow.knowledge.models import (
    KnowledgeAtomicResource,
    KnowledgeCoreDocument,
)
from scholar_workflow.models import ResourceKind
from tests.contract.test_knowledge_ownership import (
    ANALYSIS,
    CANVAS,
    CORE,
    FIELD_A,
    FIELD_B,
    PAPER,
    PATHS,
    SOURCE_A,
    SOURCE_B,
    SyntheticScope,
    _add_source,
    _filesystem,
    _inspection_guard,
    _write_json,
    ownership_scope,  # noqa: F401
)

ALPHA = PAPER
ALPHA_ANALYSIS = ANALYSIS
ALPHA_CANVAS = CANVAS
BETA = "paper:synthetic:beta"
GAMMA = "paper:synthetic:gamma"
GAMMA_ANALYSIS = "analysis:paper:synthetic:gamma"
GAMMA_CANVAS = "analysis:paper:synthetic:gamma:canvas"
GAMMA_CORE = "core:synthetic:gamma"
ALPHA_SIDECAR = "analysis:paper:synthetic:ownership:sidecar"
OTHER = "paper:synthetic:other-field"
OTHER_FIELD = "88888888-8888-4888-8888-888888888888"
UNKNOWN_SOURCE = "99999999-9999-4999-8999-999999999999"
UNKNOWN_OBJECT = "paper:synthetic:not-declared"
SHARED_TITLE = "Same display title"
SELECTED_TITLE = "Selected synthetic Field"
EXTERNAL_TITLE = "External synthetic Field"
BETA_PATH = "research/resources/papers/beta/Paper.md"
OTHER_PATH = "comparison/resources/papers/other/Paper.md"
NEIGHBOR_PATH = "research/resources/papers/ownership/Nearby analysis.md"
SIDECAR_PATH = "research/resources/papers/ownership/analysis.baseline.json"
VAULT_A = "1111111111111111"
VAULT_B = "2222222222222222"
LOCAL_PURPOSE = "Use Alpha's existing analysis as the local foundation."
GAMMA_PURPOSE = "Compare the same-title external baseline."
CANVAS_PURPOSE = "Inspect the external baseline's editable structure."
GAMMA_IDS = {PAPER: GAMMA, ANALYSIS: GAMMA_ANALYSIS, CANVAS: GAMMA_CANVAS, CORE: GAMMA_CORE}
READY_FILES = {
    (SOURCE_A, ALPHA): {ALPHA: PATHS[PAPER], ALPHA_ANALYSIS: PATHS[ANALYSIS], ALPHA_CANVAS: PATHS[CANVAS]},
    (SOURCE_A, BETA): {BETA: BETA_PATH},
    (SOURCE_B, GAMMA): {GAMMA: PATHS[PAPER], GAMMA_ANALYSIS: PATHS[ANALYSIS], GAMMA_CANVAS: PATHS[CANVAS]},
}


@dataclass
class PaperUnitCorpus:
    scope: SyntheticScope
    reader_config: Path
    external_provider: Path


def _reference(reference_id: str, source_id: str, object_id: str, purpose: str) -> dict:
    return {"reference_id": reference_id,
            "target": {"source_id": source_id, "object_id": object_id}, "purpose": purpose}


REFERENCES = [
    _reference("local-analysis", SOURCE_A, ALPHA_ANALYSIS, LOCAL_PURPOSE),
    _reference("external-paper", SOURCE_B, GAMMA, GAMMA_PURPOSE),
    _reference("external-canvas", SOURCE_B, GAMMA_CANVAS, CANVAS_PURPOSE),
]


def _snapshot_input(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_snapshot_input(path: Path, value: dict) -> None:
    # Revisions are recalculated by the existing input model, not by the new API.
    value["snapshot_revision"] = ""
    value["catalog"]["revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(value)
    _write_json(path, snapshot.model_dump(mode="json"))


def _fields(scope: SyntheticScope, references: list[dict] = REFERENCES) -> None:
    value = {"schema_version": 2, "source_id": SOURCE_A, "fields": [
        {"field_id": FIELD_A, "title": SELECTED_TITLE, "relative_root": "research",
         "home": "Overview.md", "references": copy.deepcopy(references)},
        {"field_id": OTHER_FIELD, "title": "Other synthetic Field", "relative_root": "comparison",
         "home": "Overview.md"},
    ]}
    manifest = FieldManifest.model_validate(value)
    path = scope.root / ".scholar-workflow/fields.yml"
    path.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True), encoding="utf-8")


@pytest.fixture
def paper_unit_corpus(ownership_scope: SyntheticScope) -> PaperUnitCorpus:
    scope = ownership_scope
    external_provider = _add_source(scope)
    local = _snapshot_input(scope.provider)
    local["manifest"]["atomic_resources"][0]["title"] = SHARED_TITLE
    local["catalog"]["resources"][0]["title"] = SHARED_TITLE
    for resource_id, title, path in ((BETA, "Sparse Beta", BETA_PATH), (OTHER, "Other Field paper", OTHER_PATH)):
        file = scope.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# Synthetic primary body must not be read\n", encoding="utf-8")
        resource = KnowledgeAtomicResource(resource_id=resource_id, kind=ResourceKind.PAPER,
                                           title=title, markdown_path=path)
        local["manifest"]["atomic_resources"].append(resource.model_dump(mode="json"))
        local["catalog"]["resources"].append(HubResource(resource_id=resource_id,
                                                        kind=ResourceKind.PAPER, title=title).model_dump(mode="json"))
    (scope.root / "comparison/Overview.md").write_text("# Other Field\n", encoding="utf-8")
    other_core = KnowledgeCoreDocument(document_id="core:synthetic:other-field", kind="catalog",
                                       title="Other Field", markdown_path="comparison/Overview.md")
    local["manifest"]["core_documents"].append(other_core.model_dump(mode="json"))
    (scope.root / NEIGHBOR_PATH).write_text("# Undeclared neighbor must stay excluded\n", encoding="utf-8")
    (scope.root / "research/01-Paperlist.md").write_text(
        "Manual legacy ledger\n<!-- sw:begin -->\nExisting managed body\n<!-- sw:end -->\n",
        encoding="utf-8",
    )
    _save_snapshot_input(scope.provider, local)
    external = _snapshot_input(external_provider)
    resource = external["manifest"]["atomic_resources"][0]
    resource["resource_id"], resource["title"] = GAMMA, SHARED_TITLE
    external["manifest"]["core_documents"][0]["document_id"] = GAMMA_CORE
    for document in external["manifest"]["supporting_documents"]:
        document["document_id"] = GAMMA_IDS[document["document_id"]]
        document["owner_id"] = GAMMA
    external["catalog"]["resources"][0].update(resource_id=GAMMA, title=SHARED_TITLE)
    _save_snapshot_input(external_provider, external)
    external_manifest = scope.source_roots[SOURCE_B] / ".scholar-workflow/fields.yml"
    value = yaml.safe_load(external_manifest.read_text(encoding="utf-8"))
    value["fields"][0]["title"] = EXTERNAL_TITLE
    external_manifest.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
    _fields(scope)
    reader_config = scope.temporary / "non-secret-reader/obsidian.json"
    _write_json(reader_config, {"vaults": {
        VAULT_A: {"path": str(scope.root)},
        VAULT_B: {"path": str(scope.source_roots[SOURCE_B])},
    }})
    reader_config.chmod(0o600)
    return PaperUnitCorpus(scope, reader_config, external_provider)


@contextmanager
def _query_guard(corpus: PaperUnitCorpus, *, legacy_headers: bool = False,
                 forbid_provider_reads: bool = False):
    scope = corpus.scope
    before = _filesystem(scope.temporary)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Paper-unit query attempted network access, native dispatch, or execution")

    def declaration_only_default(original):
        def checked(file, *args, **kwargs):
            if (isinstance(file, (str, bytes, os.PathLike))
                    and Path(os.fsdecode(file)).name == "knowledge-provider.snapshot.json"):
                pytest.fail("Ordinary Field list attempted to read a paper provider")
            return original(file, *args, **kwargs)
        return checked

    try:
        with pytest.MonkeyPatch.context() as patch:
            # The shared fixture forbids real readers. Restore only the actual
            # non-secret adapter; the exact synthetic config remains I/O guarded.
            patch.setattr("scholar_workflow.adapters.obsidian_registry.resolve_obsidian_reader", _actual_reader)
            patch.setattr(socket, "create_connection", forbidden)
            patch.setattr(socket, "getaddrinfo", forbidden)
            patch.setattr(socket.socket, "connect", forbidden)
            patch.setattr(socket.socket, "connect_ex", forbidden)
            for name in ("run", "Popen", "call", "check_call", "check_output"):
                patch.setattr(subprocess, name, forbidden)
            patch.setattr(os, "system", forbidden)
            patch.setattr(webbrowser, "open", forbidden)
            # Import the implementation before guarding I/O; missing new code
            # must fail a test instead of blocking collection of all contracts.
            import scholar_workflow.workflows.field_paper_units as workflow
            from scholar_workflow.knowledge import registration  # noqa: F401

            if hasattr(workflow, "resolve_obsidian_reader"):
                patch.setattr(workflow, "resolve_obsidian_reader", _actual_reader)
            if forbid_provider_reads:
                patch.setattr(builtins, "open", declaration_only_default(builtins.open))
                patch.setattr(io, "open", declaration_only_default(io.open))
                patch.setattr(os, "open", declaration_only_default(os.open))
            headers = tuple(root / "research/Overview.md" for root in scope.source_roots.values())
            if legacy_headers:
                headers += (scope.root / "comparison/Overview.md",)
            # context_file adds exactly one declaration path to the existing
            # guard. It does not grant access to its directory or other JSON.
            with _inspection_guard(scope, project=corpus.reader_config.parent,
                                   context_file=corpus.reader_config.name,
                                   header_paths=headers if legacy_headers else ()):
                yield workflow, patch
    finally:
        assert _filesystem(scope.temporary) == before


def _query(corpus: PaperUnitCorpus, *, source_id: str = SOURCE_A, field_id: str = FIELD_A) -> dict:
    with _query_guard(corpus) as (workflow, _patch):
        return workflow.field_paper_units(corpus.scope.registry.path, source_id=source_id,
                                          field_id=field_id, reader_config_path=corpus.reader_config)


def _invoke(corpus: PaperUnitCorpus, *options: str):
    ordinary = "--paper-units" not in options and "--resolve-references" not in options
    with _query_guard(corpus, legacy_headers="--paper-units" not in options,
                      forbid_provider_reads=ordinary) as (workflow, patch):
        patch.setattr(cli, "_local_field_service", lambda: FieldService(corpus.scope.registry))
        original = workflow.field_paper_units

        def with_synthetic_reader(registry_path, **kwargs):
            kwargs["reader_config_path"] = corpus.reader_config
            return original(registry_path, **kwargs)

        patch.setattr(workflow, "field_paper_units", with_synthetic_reader)
        return CliRunner().invoke(cli.main, ["knowledge", "list", *options])


def _render(corpus: PaperUnitCorpus, payload: dict, language: str) -> str:
    from scholar_workflow.knowledge.presentation import paper_units_markdown

    original = copy.deepcopy(payload)
    with _query_guard(corpus):
        rendered = paper_units_markdown(payload, language=language)
    assert payload == original
    return rendered


def _units(payload: dict) -> dict[tuple[str, str], dict]:
    rows = payload["paper_units"]
    keys = [(row["source_id"], row["resource_id"]) for row in rows]
    assert len(keys) == len(set(keys)), "Each qualified owner must occur only once"
    return dict(zip(keys, rows, strict=True))


def _files(unit: dict) -> dict[str, dict]:
    rows = unit["files"]
    assert len(rows) == len({row["object_id"] for row in rows})
    return {row["object_id"]: row for row in rows}


def _unresolved(payload: dict) -> dict[str, tuple[dict, dict]]:
    result = {}
    for row in payload["unresolved_references"]:
        # The public behavior retains the declaration. Its carrier may be a
        # nested reference or the existing reference shape plus observations.
        original = row.get("reference")
        if original is None:
            original = {key: row[key] for key in ("reference_id", "target", "purpose")}
        assert original["reference_id"] not in result
        result[original["reference_id"]] = (original, row)
    return result


def _assert_envelope(payload: dict, *, status: str = "complete") -> dict:
    assert payload["schema_version"] == 1
    assert payload["source_id"] == SOURCE_A and payload["field_id"] == FIELD_A
    assert payload["field_title"] == SELECTED_TITLE
    assert payload["status"] == status
    assert isinstance(payload["unresolved_references"], list)
    assert isinstance(payload["issues"], list)
    return _units(payload)


def _assert_uri(row: dict, vault: str, relative_path: str) -> None:
    assert row["open_state"] == "ready" and row["file_state"] == "available"
    uri = row["uri"]
    assert isinstance(uri, str) and uri.startswith("obsidian://open?")
    parsed = urlsplit(uri)
    assert parsed.scheme == "obsidian" and parsed.netloc == "open" and not parsed.fragment
    assert parse_qs(parsed.query) == {"vault": [vault], "file": [relative_path]}
    assert quote(relative_path, safe="") in uri and "+" not in uri


def test_selected_field_has_exact_qualified_paper_inventory(paper_unit_corpus):
    payload = _query(paper_unit_corpus)
    units = _assert_envelope(payload)
    assert set(units) == {(SOURCE_A, ALPHA), (SOURCE_A, BETA), (SOURCE_B, GAMMA)}
    assert payload["unresolved_references"] == payload["issues"] == []
    assert units[SOURCE_A, ALPHA]["title"] == units[SOURCE_B, GAMMA]["title"] == SHARED_TITLE
    assert units[SOURCE_B, GAMMA]["field_title"] == EXTERNAL_TITLE
    assert units[SOURCE_A, ALPHA]["field_title"] == SELECTED_TITLE
    for key, expected in READY_FILES.items():
        files = _files(units[key])
        assert {identity: row["relative_path"] for identity, row in files.items()} == expected
        assert all(row["title"] and row["kind"] for row in files.values())
        assert units[key]["ownership"]["status"] == "resolved"
    assert OTHER not in {row["resource_id"] for row in payload["paper_units"]}
    assert NEIGHBOR_PATH not in json.dumps(payload)


def test_local_and_external_reference_purposes_merge_without_new_owner(paper_unit_corpus):
    units = _units(_query(paper_unit_corpus))
    assert set(units[SOURCE_A, ALPHA]["selected_by"]) == {"owned", "referenced"}
    assert set(units[SOURCE_A, ALPHA]["purposes"]) == {LOCAL_PURPOSE}
    assert set(units[SOURCE_A, BETA]["selected_by"]) == {"owned"}
    assert units[SOURCE_A, BETA]["purposes"] == []
    assert set(units[SOURCE_B, GAMMA]["selected_by"]) == {"referenced"}
    assert set(units[SOURCE_B, GAMMA]["purposes"]) == {GAMMA_PURPOSE, CANVAS_PURPOSE}
    owner = units[SOURCE_B, GAMMA]["ownership"]
    assert owner["object_id"] == GAMMA and owner["status"] == "resolved"
    assert {(row["source_id"], row["field_id"], row["owner_id"])
            for row in owner["owner_candidates"]} == {(SOURCE_B, FIELD_B, GAMMA)}


def test_ready_uris_use_each_files_own_reader(paper_unit_corpus):
    for key, unit in _units(_query(paper_unit_corpus)).items():
        for row in unit["files"]:
            _assert_uri(row, VAULT_A if key[0] == SOURCE_A else VAULT_B, row["relative_path"])


def test_declared_missing_canvas_retains_identity_and_disables_uri(paper_unit_corpus):
    corpus = paper_unit_corpus
    (corpus.scope.root / PATHS[CANVAS]).unlink()
    payload = _query(corpus)
    units = _assert_envelope(payload, status="partial")
    canvas = _files(units[SOURCE_A, ALPHA])[ALPHA_CANVAS]
    assert canvas["relative_path"] == PATHS[CANVAS]
    assert canvas["file_state"] == "missing" and canvas["open_state"] == "file_unavailable"
    assert canvas["uri"] is None
    assert units[SOURCE_A, ALPHA]["ownership"]["status"] == "resolved"
    assert _files(units[SOURCE_A, ALPHA])[ALPHA_ANALYSIS]["open_state"] == "ready"


def test_sparse_paper_has_undeclared_analysis_without_invented_file(paper_unit_corpus):
    corpus = paper_unit_corpus
    payload = _query(corpus)
    assert set(_files(_units(payload)[SOURCE_A, BETA])) == {BETA}
    text = _render(corpus, payload, "en")
    assert "Sparse Beta" in text and "undeclared" in text.lower()
    assert "Sparse Beta/Analysis.md" not in text
    assert payload["status"] == "complete"


def test_nonpaper_and_unknown_references_keep_original_declarations(paper_unit_corpus):
    corpus = paper_unit_corpus
    extra = [
        _reference("core-selection", SOURCE_A, CORE, "Read the Field's organizing document."),
        _reference("unknown-selection", SOURCE_A, UNKNOWN_OBJECT, "Retain the unavailable choice."),
    ]
    _fields(corpus.scope, REFERENCES + extra)
    payload = _query(corpus)
    units = _assert_envelope(payload, status="partial")
    assert set(units) == set(READY_FILES)
    unresolved = _unresolved(payload)
    assert set(unresolved) == {row["reference_id"] for row in extra}
    for original in extra:
        declaration, row = unresolved[original["reference_id"]]
        assert declaration == original and isinstance(row["reason"], str) and row["reason"]
        assert row["resolution"]["object_id"] == original["target"]["object_id"]
    assert unresolved["unknown-selection"][1]["resolution"]["status"] == "not_found"
    assert unresolved["core-selection"][1]["resolution"]["status"] == "resolved"


def test_source_qualification_does_not_hide_duplicate_global_owner(paper_unit_corpus):
    corpus = paper_unit_corpus
    value = _snapshot_input(corpus.external_provider)
    duplicate_path = "research/resources/papers/duplicate-alpha/Paper.md"
    duplicate = corpus.scope.source_roots[SOURCE_B] / duplicate_path
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text("# Duplicate owner body must not be read\n", encoding="utf-8")
    value["manifest"]["atomic_resources"].append(KnowledgeAtomicResource(
        resource_id=ALPHA, kind=ResourceKind.PAPER, title="Conflicting Alpha", markdown_path=duplicate_path,
    ).model_dump(mode="json"))
    value["catalog"]["resources"].append(HubResource(
        resource_id=ALPHA, kind=ResourceKind.PAPER, title="Conflicting Alpha",
    ).model_dump(mode="json"))
    _save_snapshot_input(corpus.external_provider, value)
    payload = _query(corpus)
    alpha = _assert_envelope(payload, status="partial")[SOURCE_A, ALPHA]
    assert alpha["ownership"]["status"] == "conflict"
    assert {row["source_id"] for row in alpha["ownership"]["owner_candidates"]} == {SOURCE_A, SOURCE_B}
    assert all(row["uri"] is None and row["open_state"] == "ownership_unresolved" for row in alpha["files"])
    assert not any((row["source_id"], row["resource_id"]) == (SOURCE_B, ALPHA)
                   for row in payload["paper_units"])


def test_read_only_registration_is_sufficient_for_paper_units(paper_unit_corpus):
    corpus = paper_unit_corpus
    document = corpus.scope.registry.load_document()
    assert all(row.capabilities == ["read"] for row in document.folders + document.sources)
    with pytest.raises(RuntimeError):
        corpus.scope.registry.resolve(SOURCE_A, capability="write")
    assert set(_assert_envelope(_query(corpus))) == set(READY_FILES)


@pytest.mark.parametrize("failure", ["unknown-source", "unknown-field", "disabled", "no-read", "missing-provider",
                                    "corrupt-provider", "unsafe-provider"])
def test_unavailable_selected_authority_refuses_instead_of_returning_empty(paper_unit_corpus, failure):
    corpus = paper_unit_corpus
    source_id, field_id = SOURCE_A, FIELD_A
    if failure == "unknown-source":
        source_id = UNKNOWN_SOURCE
    elif failure == "unknown-field":
        field_id = OTHER_FIELD.replace("8", "7")
    elif failure in {"disabled", "no-read"}:
        document = corpus.scope.registry.load_document()
        if failure == "disabled":
            document.sources[0].enabled = False
        else:
            document.folders[0].capabilities = ["write"]
        _write_json(corpus.scope.registry.path, document.model_dump(mode="json"))
    elif failure == "missing-provider":
        corpus.scope.provider.unlink()
    elif failure == "corrupt-provider":
        corpus.scope.provider.write_text("{not-json", encoding="utf-8")
    else:
        corpus.scope.provider.chmod(0o666)
    with pytest.raises((RuntimeError, OSError, ValueError)):
        _query(corpus, source_id=source_id, field_id=field_id)


def test_unavailable_external_provider_is_diagnostic_not_absent_reference(paper_unit_corpus):
    corpus = paper_unit_corpus
    corpus.external_provider.unlink()
    payload = _query(corpus)
    assert payload["status"] == "partial"
    assert {(row["source_id"], row["resource_id"]) for row in payload["paper_units"]} == {
        (SOURCE_A, ALPHA), (SOURCE_A, BETA),
    }
    unresolved = _unresolved(payload)
    # Existing ownership semantics require checking every registered Source for
    # duplicates. An unreadable external authority also leaves local uniqueness
    # incomplete; a local declaration alone cannot authorize a document link.
    assert set(unresolved) == {original["reference_id"] for original in REFERENCES}
    for original in REFERENCES:
        declaration, row = unresolved[original["reference_id"]]
        assert declaration == original and row["reason"]
        assert row["resolution"]["status"] == "incomplete"
        assert any(issue["source_id"] == SOURCE_B for issue in row["resolution"]["issues"])
    local_resolution = unresolved["local-analysis"][1]["resolution"]
    assert {(row["source_id"], row["object_id"], row["relative_path"])
            for row in local_resolution["locations"]} == {(SOURCE_A, ALPHA_ANALYSIS, PATHS[ANALYSIS])}
    for unit in payload["paper_units"]:
        assert unit["ownership"]["status"] == "incomplete"
        assert all(row["uri"] is None and row["open_state"] == "ownership_unresolved"
                   for row in unit["files"])


def test_selected_provider_replacement_during_read_refuses(paper_unit_corpus, monkeypatch):
    corpus = paper_unit_corpus
    scope = corpus.scope
    target = scope.provider
    content = target.read_bytes()
    original_identity = (target.stat().st_dev, target.stat().st_ino)
    original_fdopen = os.fdopen
    injected = []

    class ConcurrentReplacementStream:
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
            if not injected:
                # Only this fixture hook simulates an independent writer. The
                # production query remains under the ordinary mutation guard.
                replacement = target.with_name(target.name + ".fixture-replacement")
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
        if (info.st_dev, info.st_ino) == original_identity:
            return ConcurrentReplacementStream(stream)
        return stream

    monkeypatch.setattr(os, "fdopen", racing_fdopen)
    with pytest.raises((RuntimeError, OSError, ValueError)):
        _query(corpus)
    assert injected == [True] and target.read_bytes() == content
    assert not target.with_name(target.name + ".fixture-replacement").exists()


@pytest.mark.parametrize("kind", ["missing", "ambiguous"])
def test_reader_absence_or_ambiguity_preserves_files_without_uri(paper_unit_corpus, kind):
    corpus = paper_unit_corpus
    value = {"vaults": {VAULT_A: {"path": str(corpus.scope.root)}}}
    if kind == "ambiguous":
        value["vaults"][VAULT_B] = {"path": str(corpus.scope.root)}
    _write_json(corpus.reader_config, value)
    payload = _query(corpus)
    gamma = _units(payload)[SOURCE_B, GAMMA]
    assert set(_files(gamma)) == set(READY_FILES[SOURCE_B, GAMMA])
    assert gamma["ownership"]["status"] == "resolved"
    assert all(row["file_state"] == "available" and row["uri"] is None
               and row["open_state"] == "reader_unavailable" for row in gamma["files"])
    alpha = _units(payload)[SOURCE_A, ALPHA]
    if kind == "ambiguous":
        assert all(row["uri"] is None and row["open_state"] == "reader_unavailable" for row in alpha["files"])
    else:
        assert all(row["open_state"] == "ready" for row in alpha["files"])
    text = _render(corpus, payload, "en")
    assert "reader" in text.lower() and "unavailable" in text.lower()
    assert "[[" not in text


def test_symlinked_declared_file_is_unsafe_without_following_target(paper_unit_corpus):
    corpus = paper_unit_corpus
    target = corpus.scope.root / "private-body.md"
    target.write_text("Secret fixture body must never be read\n", encoding="utf-8")
    file = corpus.scope.root / PATHS[ANALYSIS]
    file.unlink()
    file.symlink_to(target)
    payload = _query(corpus)
    analysis = _files(_units(payload)[SOURCE_A, ALPHA])[ALPHA_ANALYSIS]
    assert payload["status"] == "partial"
    assert analysis["file_state"] == "unsafe" and analysis["open_state"] == "file_unavailable"
    assert analysis["uri"] is None


def test_unsafe_provider_path_refuses_before_document_body_access(paper_unit_corpus):
    corpus = paper_unit_corpus
    value = _snapshot_input(corpus.scope.provider)
    value["manifest"]["atomic_resources"][0]["markdown_path"] = "../Outside.md"
    # Deliberately raw malformed authority: a valid model must not sanitize it.
    _write_json(corpus.scope.provider, value)
    with pytest.raises((RuntimeError, OSError, ValueError)):
        _query(corpus)


def test_artifact_only_sidecar_is_owned_but_not_native_openable(paper_unit_corpus):
    corpus = paper_unit_corpus
    content = b'{"body": "artifact contents must never be read"}\n'
    (corpus.scope.root / SIDECAR_PATH).write_bytes(content)
    value = _snapshot_input(corpus.scope.provider)
    value["artifacts"].append({"artifact_id": ALPHA_SIDECAR, "resource_id": ALPHA,
                               "kind": "analysis_sidecar", "vault_path": SIDECAR_PATH,
                               "sha256": "sha256:" + hashlib.sha256(content).hexdigest()})
    _save_snapshot_input(corpus.scope.provider, value)
    row = _files(_units(_query(corpus))[SOURCE_A, ALPHA])[ALPHA_SIDECAR]
    assert row["kind"] == "analysis_sidecar" and row["relative_path"] == SIDECAR_PATH
    assert row["file_state"] == "available" and row["open_state"] == "unsupported_type"
    assert row["uri"] is None


def test_subdirectory_source_uri_keeps_full_containing_vault_path(paper_unit_corpus):
    corpus = paper_unit_corpus
    scope = corpus.scope
    vault = scope.temporary / "Containing Vault"
    vault.mkdir()
    nested = vault / "Chosen Source #1 & [notes]"
    scope.root.rename(nested)
    scope.root = nested
    scope.source_roots[SOURCE_A] = nested
    registry = scope.registry.load_document()
    registry.folders[0].root = nested
    _write_json(scope.registry.path, registry.model_dump(mode="json"))
    value = _snapshot_input(scope.provider)
    info = nested.stat()
    value["vault_binding"] = {"root_path": str(nested), "device": info.st_dev, "inode": info.st_ino}
    _save_snapshot_input(scope.provider, value)
    _write_json(corpus.reader_config, {"vaults": {VAULT_A: {"path": str(vault)},
                                                VAULT_B: {"path": str(scope.source_roots[SOURCE_B])}}})
    alpha = _units(_query(corpus))[SOURCE_A, ALPHA]
    for row in alpha["files"]:
        _assert_uri(row, VAULT_A, f"{nested.name}/{row['relative_path']}")
        assert "%23" in row["uri"] and "%26" in row["uri"] and "%5B" in row["uri"]


def test_markdown_delimiter_paths_are_encoded_and_titles_cannot_inject_links(paper_unit_corpus):
    corpus = paper_unit_corpus
    unsafe_title = "Alpha | [injected](https://invalid.example/attack) <img src=x>"
    path = "research/resources/papers/ownership/Analysis #1 & [draft](x)|.md"
    (corpus.scope.root / PATHS[ANALYSIS]).rename(corpus.scope.root / path)
    value = _snapshot_input(corpus.scope.provider)
    value["manifest"]["atomic_resources"][0]["title"] = unsafe_title
    value["catalog"]["resources"][0]["title"] = unsafe_title
    value["manifest"]["supporting_documents"][0]["vault_path"] = path
    _save_snapshot_input(corpus.scope.provider, value)
    payload = _query(corpus)
    alpha = _units(payload)[SOURCE_A, ALPHA]
    assert alpha["title"] == unsafe_title
    _assert_uri(_files(alpha)[ALPHA_ANALYSIS], VAULT_A, path)
    text = _render(corpus, payload, "en")
    assert "[injected](https://invalid.example/attack)" not in text
    assert "<img src=x>" not in text
    assert "\\[injected\\]" in text and "&lt;img src=x&gt;" in text
    assert "\\|" in text and not re.search(r"(?m)^\s*\|\s*\[injected", text)
    assert "[[" not in text


@pytest.mark.parametrize("language", ["en", "zh"])
def test_human_renderer_keeps_full_purposes_and_hides_machine_internals(paper_unit_corpus, language):
    corpus = paper_unit_corpus
    payload = _query(corpus)
    text = _render(corpus, payload, language)
    for purpose in (LOCAL_PURPOSE, GAMMA_PURPOSE, CANVAS_PURPOSE):
        assert purpose in text
    assert SHARED_TITLE in text and "Sparse Beta" in text and EXTERNAL_TITLE in text
    assert "obsidian://open?" in text
    if language == "en":
        assert "paper" in text.lower() and "purpose" in text.lower() and "undeclared" in text.lower()
        assert not any(label in text for label in ("用途", "未声明", "归属冲突"))
    else:
        assert "论文" in text and "用途" in text and "未声明" in text
        assert not re.search(r"\b(?:undeclared|reader_unavailable|file_unavailable|ownership_unresolved)\b", text)
    for value in (SOURCE_A, SOURCE_B, FIELD_A, FIELD_B, ALPHA, BETA, GAMMA,
                  str(corpus.scope.root), str(corpus.scope.registry.path),
                  _snapshot_input(corpus.scope.provider)["snapshot_revision"]):
        assert value not in text
    assert not re.search(r"opened successfully|GUI verified|已成功打开|人工验收通过", text, re.IGNORECASE)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_machine_support_titles_get_readable_link_labels_without_changing_json(paper_unit_corpus, language):
    corpus = paper_unit_corpus
    local = _snapshot_input(corpus.scope.provider)
    for document in local["manifest"]["supporting_documents"]:
        document["title"] = document["document_id"]
    _save_snapshot_input(corpus.scope.provider, local)
    custom_titles = {GAMMA_ANALYSIS: "Gamma custom analysis label", GAMMA_CANVAS: "Gamma custom Canvas label"}
    external = _snapshot_input(corpus.external_provider)
    for document in external["manifest"]["supporting_documents"]:
        document["title"] = custom_titles[document["document_id"]]
    _save_snapshot_input(corpus.external_provider, external)

    payload = _query(corpus)
    units = _assert_envelope(payload)
    alpha_files = _files(units[SOURCE_A, ALPHA])
    gamma_files = _files(units[SOURCE_B, GAMMA])
    for object_id in (ALPHA_ANALYSIS, ALPHA_CANVAS):
        assert alpha_files[object_id]["object_id"] == object_id
        assert alpha_files[object_id]["title"] == object_id
    for object_id, title in custom_titles.items():
        assert gamma_files[object_id]["object_id"] == object_id
        assert gamma_files[object_id]["title"] == title

    text = _render(corpus, payload, language)
    links = {}
    # Both angle-delimited and bare link destinations are valid CommonMark.
    pattern = r"\[([^\]\n]+)\]\((?:<(obsidian://open\?[^>\n]+)>|(obsidian://open\?[^)\n]+))\)"
    for label, angle_uri, bare_uri in re.findall(pattern, text):
        parsed = urlsplit(angle_uri or bare_uri)
        assert parsed.scheme == "obsidian" and parsed.netloc == "open" and not parsed.fragment
        query = parse_qs(parsed.query)
        assert set(query) == {"vault", "file"} and len(query["vault"]) == len(query["file"]) == 1
        links[query["vault"][0], query["file"][0]] = label
    for object_id in (ALPHA_ANALYSIS, ALPHA_CANVAS):
        label = links[VAULT_A, alpha_files[object_id]["relative_path"]]
        assert label.strip() and label != object_id
        assert label != alpha_files[object_id]["relative_path"]
    for object_id, title in custom_titles.items():
        assert links[VAULT_B, gamma_files[object_id]["relative_path"]] == title
    for object_id in (ALPHA_ANALYSIS, ALPHA_CANVAS, GAMMA_ANALYSIS, GAMMA_CANVAS):
        assert object_id not in text


@pytest.mark.parametrize("fmt", ["json", "md"])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_opt_in_cli_uses_actual_field_composition_and_stdout_only(paper_unit_corpus, fmt, language):
    result = _invoke(paper_unit_corpus, "--paper-units", "--source-id", SOURCE_A,
                     "--field-id", FIELD_A, "--format", fmt, "--language", language)
    assert result.exit_code == 0, result.output
    if fmt == "json":
        assert set(_assert_envelope(json.loads(result.output))) == set(READY_FILES)
    else:
        assert SHARED_TITLE in result.output and "Sparse Beta" in result.output
        for purpose in (LOCAL_PURPOSE, GAMMA_PURPOSE, CANVAS_PURPOSE):
            assert purpose in result.output
        assert ("用途" if language == "zh" else "purpose") in result.output.lower()


@pytest.mark.parametrize("options", [
    ("--paper-units",),
    ("--paper-units", "--source-id", SOURCE_A),
    ("--paper-units", "--field-id", FIELD_A),
    ("--source-id", SOURCE_A, "--field-id", FIELD_A),
    ("--source-id", SOURCE_A),
    ("--field-id", FIELD_A),
    ("--paper-units", "--source-id", SOURCE_A, "--field-id", FIELD_A, "--resolve-references"),
])
def test_cli_requires_explicit_unambiguous_mode_and_both_selectors(paper_unit_corpus, options):
    result = _invoke(paper_unit_corpus, *options, "--format", "json")
    assert result.exit_code == 2, result.output
    assert "paper_units" not in result.output


def test_default_and_resolve_reference_lists_keep_existing_envelope(paper_unit_corpus):
    corpus = paper_unit_corpus
    ordinary = _invoke(corpus, "--format", "json")
    assert ordinary.exit_code == 0, ordinary.output
    payload = json.loads(ordinary.output)
    assert set(payload) == {"schema_version", "fields"} and payload["schema_version"] == 1
    assert len(payload["fields"]) == 3
    selected = next(row for row in payload["fields"] if row["field_id"] == FIELD_A)
    assert selected["references"] == REFERENCES
    assert all("resolution" not in row for row in selected["references"])
    resolved = _invoke(corpus, "--resolve-references", "--format", "json")
    assert resolved.exit_code == 0, resolved.output
    payload = json.loads(resolved.output)
    assert set(payload) == {"schema_version", "fields"}
    selected = next(row for row in payload["fields"] if row["field_id"] == FIELD_A)
    for row, original in zip(selected["references"], REFERENCES, strict=True):
        assert {key: row[key] for key in original} == original
        assert row["resolution"]["object_id"] == original["target"]["object_id"]
        assert row["resolution"]["status"] == "resolved"


def test_legacy_schema_one_serialization_and_paperlist_renderer_stay_independent(paper_unit_corpus):
    from scholar_workflow.workflows.novelty_tree import plan_paperlist, render_paperlist

    corpus = paper_unit_corpus
    original = {"schema_version": 1, "source_id": SOURCE_A, "fields": [{
        "field_id": FIELD_A, "title": "Legacy Field", "relative_root": "research",
        "home": "Overview.md", "navigation": [],
    }]}
    assert FieldManifest.model_validate(original).model_dump(mode="json") == original
    doc = {"paper_list": []}
    with _query_guard(corpus):
        body = render_paperlist(doc, 12345)
        plan = plan_paperlist(doc, "research", 12345)
    assert len(plan) == 1 and plan[0]["path"] == "research/01-Paperlist.md"
    assert plan[0]["body"] == body and plan[0]["heading"] == ""
    assert "paper_units" not in body and "obsidian://open?" not in body
    assert (corpus.scope.root / "research/01-Paperlist.md").read_text(encoding="utf-8") == (
        "Manual legacy ledger\n<!-- sw:begin -->\nExisting managed body\n<!-- sw:end -->\n"
    )
