"""Independent synthetic contracts for read-only Field reference resolution.

The caller's references select existing objects; they never create placements.
Expected locations and states are written independently of the new workflow.
"""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import builtins
import io
import json
import os
import re
import socket
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.knowledge.fields import FieldManifest, FieldService
from tests.contract.test_knowledge_ownership import (
    ANALYSIS,
    CANVAS,
    FIELD_A,
    FIELD_B,
    PAPER,
    PATHS,
    SOURCE_A,
    SOURCE_B,
    SyntheticScope,
    _add_source,
    _assert_location,
    _assert_resolution,
    _expected_location,
    _filesystem,
    _inspection_guard,
    _plain,
    _write_json,
    ownership_scope,  # noqa: F401
)

REFERENCE_FIELD = "88888888-8888-4888-8888-888888888888"
UNKNOWN_SOURCE = "99999999-9999-4999-8999-999999999999"
UNKNOWN_OBJECT = "paper:synthetic:not-declared"


def _reference(reference_id: str, object_id: str = PAPER, *, source_id: str = SOURCE_A) -> dict:
    return {
        "reference_id": reference_id,
        "target": {"source_id": source_id, "object_id": object_id},
        "purpose": "Use the existing object without creating a second owner.",
    }


def _manifest(references: list[dict], *, second_references: list[dict] | None = None) -> FieldManifest:
    fields = [{
        "field_id": FIELD_A,
        "title": "Synthetic source topic",
        "relative_root": "research",
        "home": "Overview.md",
        "references": references,
    }]
    if second_references is not None:
        fields.append({
            "field_id": REFERENCE_FIELD,
            "title": "Synthetic comparison topic",
            "relative_root": "comparison",
            "home": "Overview.md",
            "references": second_references,
        })
    return FieldManifest.model_validate({"schema_version": 2, "source_id": SOURCE_A, "fields": fields})


def _clear_declared_objects(provider: Path) -> None:
    """Prepare an enabled, registered Source with no ownership declarations."""
    document = json.loads(provider.read_text(encoding="utf-8"))
    for member in ("atomic_resources", "core_documents", "supporting_documents"):
        document["manifest"][member] = []
    document["catalog"]["resources"] = []
    document["catalog"]["revision"] = ""
    document["snapshot_revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(document)
    _write_json(provider, snapshot.model_dump(mode="json"))


def _resolve(scope: SyntheticScope, manifest: FieldManifest) -> dict[str, dict[str, dict]]:
    # Import before guarding I/O. A missing implementation must fail these tests,
    # not prevent collection of unrelated ownership contracts.
    from scholar_workflow.workflows.knowledge_ownership import resolve_field_references

    original = manifest.model_dump(mode="json")
    before = _filesystem(scope.temporary)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Field reference inspection attempted network access or shell execution")

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(socket, "create_connection", forbidden)
            patch.setattr(socket, "getaddrinfo", forbidden)
            patch.setattr(socket.socket, "connect", forbidden)
            patch.setattr(socket.socket, "connect_ex", forbidden)
            patch.setattr(os, "system", forbidden)
            with _inspection_guard(scope):
                result = resolve_field_references(manifest, scope.registry.path)
        return {
            field_id: {reference_id: _plain(value) for reference_id, value in rows.items()}
            for field_id, rows in result.items()
        }
    finally:
        assert manifest.model_dump(mode="json") == original
        assert _filesystem(scope.temporary) == before


def _has_issue(row: dict, code: str, source_id: str) -> bool:
    return any(
        _plain(issue)["code"] == code and _plain(issue)["source_id"] == source_id
        for issue in row["issues"]
    )


def test_two_fields_reference_one_primary_without_creating_placements(ownership_scope):
    scope = ownership_scope
    manifest = _manifest([_reference("foundation")], second_references=[_reference("comparison")])

    result = _resolve(scope, manifest)

    assert set(result) == {FIELD_A, REFERENCE_FIELD}
    assert set(result[FIELD_A]) == {"foundation"}
    assert set(result[REFERENCE_FIELD]) == {"comparison"}
    first = result[FIELD_A]["foundation"]
    second = result[REFERENCE_FIELD]["comparison"]
    for row in (first, second):
        _assert_resolution(row, PAPER, "resolved")
        assert row["issues"] == []
        assert len(row["locations"]) == len(row["owner_candidates"]) == 1
        _assert_location(row["locations"][0], _expected_location(PAPER))
        _assert_location(row["owner_candidates"][0], _expected_location(PAPER))
    assert first == second
    assert all(location["field_id"] != REFERENCE_FIELD for location in second["locations"])


def test_cross_source_reference_resolves_existing_target_not_calling_field(ownership_scope):
    scope = ownership_scope
    _add_source(scope)
    _clear_declared_objects(scope.provider)
    manifest = _manifest([_reference("external-analysis", ANALYSIS, source_id=SOURCE_B)])

    row = _resolve(scope, manifest)[FIELD_A]["external-analysis"]

    _assert_resolution(row, ANALYSIS, "resolved")
    assert row["issues"] == []
    assert len(row["locations"]) == len(row["owner_candidates"]) == 1
    _assert_location(row["locations"][0], _expected_location(ANALYSIS, source_id=SOURCE_B, field_id=FIELD_B))
    _assert_location(row["owner_candidates"][0], _expected_location(PAPER, source_id=SOURCE_B, field_id=FIELD_B))


@pytest.mark.parametrize("object_id", [PAPER, ANALYSIS, CANVAS])
def test_target_source_never_hides_global_primary_conflict(ownership_scope, object_id):
    scope = ownership_scope
    _add_source(scope, supporting=False)
    manifest = _manifest([_reference("shared", object_id)])

    row = _resolve(scope, manifest)[FIELD_A]["shared"]

    _assert_resolution(row, object_id, "conflict")
    assert {owner["source_id"] for owner in row["owner_candidates"]} == {SOURCE_A, SOURCE_B}
    if object_id != PAPER:
        assert len(row["locations"]) == 1
        _assert_location(row["locations"][0], _expected_location(object_id))


def test_registered_target_mismatch_keeps_actual_location_and_reports_incomplete(ownership_scope):
    scope = ownership_scope
    empty_provider = _add_source(scope)
    _clear_declared_objects(empty_provider)
    manifest = _manifest([_reference("wrong-target", source_id=SOURCE_B)])

    row = _resolve(scope, manifest)[FIELD_A]["wrong-target"]

    _assert_resolution(row, PAPER, "incomplete")
    assert _has_issue(row, "reference_target_mismatch", SOURCE_B)
    assert len(row["locations"]) == len(row["owner_candidates"]) == 1
    _assert_location(row["locations"][0], _expected_location(PAPER))
    _assert_location(row["owner_candidates"][0], _expected_location(PAPER))


@pytest.mark.parametrize("object_id", [PAPER, UNKNOWN_OBJECT])
def test_unregistered_target_preserves_reference_and_reports_unavailable(ownership_scope, object_id):
    manifest = _manifest([_reference("unregistered", object_id, source_id=UNKNOWN_SOURCE)])

    result = _resolve(ownership_scope, manifest)

    assert set(result[FIELD_A]) == {"unregistered"}
    row = result[FIELD_A]["unregistered"]
    _assert_resolution(row, object_id, "incomplete")
    assert _has_issue(row, "reference_target_unavailable", UNKNOWN_SOURCE)
    if object_id == UNKNOWN_OBJECT:
        assert row["locations"] == row["owner_candidates"] == []


@pytest.mark.parametrize("disabled_member", ["source", "folder"])
def test_disabled_target_preserves_reference_even_without_locations(ownership_scope, disabled_member):
    scope = ownership_scope
    registry = scope.registry.load_document()
    if disabled_member == "source":
        registry.sources[0].enabled = False
    else:
        registry.folders[0].enabled = False
    _write_json(scope.registry.path, registry.model_dump(mode="json"))
    manifest = _manifest([_reference("disabled")])

    result = _resolve(scope, manifest)

    assert set(result[FIELD_A]) == {"disabled"}
    row = result[FIELD_A]["disabled"]
    _assert_resolution(row, PAPER, "incomplete")
    assert row["locations"] == row["owner_candidates"] == []
    assert _has_issue(row, "reference_target_unavailable", SOURCE_A)


def test_available_target_with_unknown_object_is_not_found_not_silently_omitted(ownership_scope):
    manifest = _manifest([_reference("absent-object", UNKNOWN_OBJECT)])

    result = _resolve(ownership_scope, manifest)

    assert set(result[FIELD_A]) == {"absent-object"}
    row = result[FIELD_A]["absent-object"]
    _assert_resolution(row, UNKNOWN_OBJECT, "not_found")
    assert row["locations"] == row["owner_candidates"] == []
    assert row["issues"] == []


@pytest.mark.parametrize("object_id", [PAPER, ANALYSIS, CANVAS])
def test_missing_object_retains_resolved_identity_and_missing_file_state(ownership_scope, object_id):
    scope = ownership_scope
    (scope.root / PATHS[object_id]).unlink()
    manifest = _manifest([_reference("missing-file", object_id)])

    row = _resolve(scope, manifest)[FIELD_A]["missing-file"]

    _assert_resolution(row, object_id, "resolved")
    assert row["issues"] == []
    assert len(row["locations"]) == len(row["owner_candidates"]) == 1
    _assert_location(row["locations"][0], _expected_location(object_id, file_state="missing"))
    owner_state = "missing" if object_id == PAPER else "available"
    _assert_location(row["owner_candidates"][0], _expected_location(PAPER, file_state=owner_state))


def test_schema_one_manifest_has_no_reference_resolution_and_does_not_read_registry(ownership_scope):
    scope = ownership_scope
    manifest = FieldManifest.model_validate({
        "schema_version": 1,
        "source_id": SOURCE_A,
        "fields": [{
            "field_id": FIELD_A, "title": "Legacy synthetic topic",
            "relative_root": "research", "home": "Overview.md",
        }],
    })
    # An absent registry is deliberately supplied: the empty legacy operation
    # must not inspect or create it, let alone introduce a lock/state directory.
    from scholar_workflow.workflows.knowledge_ownership import resolve_field_references

    missing_registry = scope.temporary / "absent-state/sources.json"
    before = _filesystem(scope.temporary)
    with _inspection_guard(scope):
        result = resolve_field_references(manifest, missing_registry)
    assert result == {}
    assert _filesystem(scope.temporary) == before
    assert not missing_registry.exists() and not missing_registry.parent.exists()


def _register_references(scope: SyntheticScope, references: list[dict]) -> None:
    """Prepare raw schema 2 input without deriving it from any resolver output."""
    path = scope.root / ".scholar-workflow/fields.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest["fields"][0]["references"] = references
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")


def _invoke_fields(scope: SyntheticScope, *options: str, forbid_provider_reads: bool = False):
    # Load ordinary command dependencies before the exact production read guard.
    from scholar_workflow.knowledge import registration  # noqa: F401
    from scholar_workflow.workflows import knowledge_ownership  # noqa: F401

    before = _filesystem(scope.temporary)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Field list attempted network access or shell execution")

    def no_provider_read(original):
        def checked(file, *args, **kwargs):
            if (isinstance(file, (str, bytes, os.PathLike))
                    and Path(os.fsdecode(file)).name == "knowledge-provider.snapshot.json"):
                pytest.fail("Default Field list attempted to open a provider declaration")
            return original(file, *args, **kwargs)
        return checked

    try:
        with pytest.MonkeyPatch.context() as patch:
            # This override is local; the shared fixture still forbids config,
            # native-app, subprocess, reader and other external integrations.
            patch.setattr(cli, "_local_field_service", lambda: FieldService(scope.registry))
            patch.setattr(socket, "create_connection", forbidden)
            patch.setattr(socket, "getaddrinfo", forbidden)
            patch.setattr(socket.socket, "connect", forbidden)
            patch.setattr(socket.socket, "connect_ex", forbidden)
            patch.setattr(os, "system", forbidden)
            if forbid_provider_reads:
                patch.setattr(builtins, "open", no_provider_read(builtins.open))
                patch.setattr(io, "open", no_provider_read(io.open))
                patch.setattr(os, "open", no_provider_read(os.open))
            header_paths = tuple(root / "research/Overview.md" for root in scope.source_roots.values())
            with _inspection_guard(scope, header_paths=header_paths):
                return CliRunner().invoke(cli.main, ["knowledge", "list", *options])
    finally:
        assert _filesystem(scope.temporary) == before


@pytest.mark.parametrize("fmt", ["json", "md"])
def test_default_list_preserves_declared_references_without_reading_provider(ownership_scope, fmt):
    scope = ownership_scope
    references = [_reference("selected-analysis", ANALYSIS)]
    _register_references(scope, references)

    result = _invoke_fields(scope, "--format", fmt, forbid_provider_reads=True)

    assert result.exit_code == 0, result.output
    if fmt == "json":
        payload = json.loads(result.output)
        assert payload["fields"][0]["references"] == references
        assert "resolution" not in payload["fields"][0]["references"][0]
    else:
        assert "Use the existing object without creating a second owner." in result.output
        assert not re.search(r"(?mi)^\s*ownership:\s*resolved\b", result.output)


def test_explicit_cli_json_adds_resolution_without_changing_reference_declaration(ownership_scope):
    scope = ownership_scope
    references = [_reference("selected-analysis", ANALYSIS)]
    _register_references(scope, references)

    result = _invoke_fields(scope, "--resolve-references", "--format", "json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert len(payload["fields"]) == 1
    field = payload["fields"][0]
    assert field["source_id"] == SOURCE_A and field["field_id"] == FIELD_A
    assert len(field["references"]) == 1
    reference = field["references"][0]
    resolution = reference.pop("resolution")
    assert reference == references[0]
    _assert_resolution(resolution, ANALYSIS, "resolved")
    assert resolution["issues"] == []
    assert len(resolution["locations"]) == len(resolution["owner_candidates"]) == 1
    _assert_location(resolution["locations"][0], _expected_location(ANALYSIS))
    _assert_location(resolution["owner_candidates"][0], _expected_location(PAPER))


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("missing", [False, True])
def test_cli_markdown_shows_purpose_owner_file_and_unverified_reader_without_machine_data(
    ownership_scope, language, missing,
):
    scope = ownership_scope
    second_provider = _add_source(scope)
    _clear_declared_objects(scope.provider)
    second_root = scope.source_roots[SOURCE_B]
    field_path = second_root / ".scholar-workflow/fields.yml"
    fields = yaml.safe_load(field_path.read_text(encoding="utf-8"))
    target_title = "目标知识领域" if language == "zh" else "Target knowledge topic"
    fields["fields"][0]["title"] = target_title
    field_path.write_text(yaml.safe_dump(fields, allow_unicode=True), encoding="utf-8")
    purpose = "为当前研究提供既有分析依据。" if language == "zh" else "Use the existing analysis as research evidence."
    reference = _reference("external-support", ANALYSIS, source_id=SOURCE_B)
    reference["purpose"] = purpose
    _register_references(scope, [reference])
    if missing:
        (second_root / PATHS[ANALYSIS]).unlink()
    provider = json.loads(second_provider.read_text(encoding="utf-8"))
    hidden = (
        SOURCE_A, SOURCE_B, FIELD_A, FIELD_B, PAPER, ANALYSIS, CANVAS,
        "external-support", str(scope.root), str(second_root), str(scope.registry.path),
        provider["snapshot_revision"], provider["catalog"]["revision"],
    )

    result = _invoke_fields(scope, "--resolve-references", "--format", "md", "--language", language)

    assert result.exit_code == 0, result.output
    text = result.output
    assert purpose in text
    # One occurrence is the registered target's own heading. Its reference
    # resolution must independently display that target Field as well.
    assert text.count(target_title) >= 2
    if language == "zh":
        assert "用途" in text and "归属" in text and "文件" in text
        assert re.search(r"已定位|已解析|已核验", text)
        assert "阅读器" in text and "未核验" in text
        assert re.search(r"缺失" if missing else r"存在|可用|可定位", text)
    else:
        lower = text.lower()
        assert "purpose" in lower and "ownership" in lower and "file" in lower
        assert re.search(r"resolved|located|ownership found", lower)
        assert "reader" in lower and re.search(r"unverified|not verified", lower)
        assert re.search(r"missing" if missing else r"exists|available", lower)
    for value in hidden:
        assert value and value not in text
    for uri in ("obsidian://", "zotero://", "127.0.0.1"):
        assert uri not in text
    assert not re.search(r"\[[^\]]*\]\([^\n)]*Analysis\.md", text)


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("fmt", ["json", "md"])
def test_schema_one_default_list_keeps_existing_public_output(ownership_scope, language, fmt):
    result = _invoke_fields(ownership_scope, "--format", fmt, "--language", language,
                            forbid_provider_reads=True)

    assert result.exit_code == 0, result.output
    if fmt == "json":
        assert json.loads(result.output) == {
            "schema_version": 1,
            "fields": [{
                "source_id": SOURCE_A, "field_id": FIELD_A, "title": "合成研究领域",
                "home": "Overview.md", "relative_root": "research",
                "navigation": [], "available": True,
            }],
        }
    else:
        heading = "# 已登记知识领域" if language == "zh" else "# Registered knowledge Fields"
        home_label = "已有入口" if language == "zh" else "Existing home"
        assert result.output == f"{heading}\n\n## 合成研究领域\n\n- {home_label}: Overview.md\n\n"
