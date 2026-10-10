"""Independent synthetic CLI contracts for one Field reference change.

Expectations are documented in fixtures/field-reference-writes/EXPECTED.md.
These tests never use real Sources, readers, network, or application state.
"""
# Pytest injects the imported fixture by parameter name.
# ruff: noqa: F811
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
from scholar_workflow.knowledge.fields import FieldService
from tests.contract.test_knowledge_ownership import (
    ANALYSIS,
    ANALYSIS_PATH,
    CANVAS,
    FIELD_A,
    FIELD_B,
    PAPER,
    SOURCE_A,
    SOURCE_B,
    SyntheticScope,
    _add_source,
    _filesystem,
    _inspection_guard,
    _write_json,
    ownership_scope,  # noqa: F401
)

REFERENCE_ID = "selected-analysis"
KEEP_ID = "retained-canvas"
UNKNOWN_SOURCE = "99999999-9999-4999-8999-999999999999"
PURPOSES = {
    "en": "Use the existing analysis as evidence for this topic.",
    "zh": "为当前专题提供既有分析依据。",
}


@pytest.fixture
def write_scope(ownership_scope) -> SyntheticScope:
    scope = ownership_scope
    other_provider = _add_source(scope)
    # The selected owner exists only in read-only Source B. Source A owns the
    # mutable reference manifest, not a duplicate paper or analysis placement.
    snapshot = json.loads(scope.provider.read_text(encoding="utf-8"))
    for name in ("atomic_resources", "core_documents", "supporting_documents"):
        snapshot["manifest"][name] = []
    snapshot["catalog"]["resources"] = []
    snapshot["catalog"]["revision"] = ""
    snapshot["snapshot_revision"] = ""
    prepared = KnowledgeProviderSnapshot.model_validate(snapshot)
    _write_json(scope.provider, prepared.model_dump(mode="json"))
    registry = scope.registry.load_document()
    registry.sources[0].capabilities = ["read", "write"]
    registry.folders[0].capabilities = ["read", "write"]
    _write_json(scope.registry.path, registry.model_dump(mode="json"))
    assert registry.sources[1].capabilities == ["read"]
    assert registry.folders[1].capabilities == ["read"]
    # Coordination locks are existing host state, not reference or provider
    # content. Prepare them before snapshots so exact write checks stay strict.
    for lock in (
        scope.registry.path.with_name(f".{scope.registry.path.name}.lock"),
        scope.provider.parent / ".knowledge-provider.apply.lock",
        other_provider.parent / ".knowledge-provider.apply.lock",
    ):
        lock.touch()
    return scope


def _reference(*, reference_id: str = REFERENCE_ID, object_id: str = ANALYSIS,
               purpose: str = PURPOSES["en"]) -> dict:
    return {"reference_id": reference_id,
            "target": {"source_id": SOURCE_B, "object_id": object_id},
            "purpose": purpose}


def _declare_references(scope: SyntheticScope, references: list[dict]) -> None:
    path = scope.root / ".scholar-workflow/fields.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest["fields"][0]["references"] = references
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")


def _selection(operation: str = "add", *, language: str = "en", reference_id: str = REFERENCE_ID,
               source_id: str = SOURCE_A, target_source_id: str = SOURCE_B,
               purpose: str | None = None) -> list[str]:
    arguments = ["--source-id", source_id, "--field-id", FIELD_A,
                 "--operation", operation, "--reference-id", reference_id]
    if operation == "add":
        arguments += ["--target-source-id", target_source_id, "--object-id", ANALYSIS,
                      "--purpose", purpose if purpose is not None else PURPOSES[language]]
    return arguments


def _invoke(scope: SyntheticScope, command: str, *arguments: str, input: str | None = None,
            forbid_provider_reads: bool = False):
    # Preload lazy CLI dependencies before production reads are guarded.
    from scholar_workflow.workflows import field_references  # noqa: F401

    before = _filesystem(scope.temporary)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Reference CLI attempted network access or shell execution")

    def no_provider_read(original):
        def checked(file, *args, **kwargs):
            if (isinstance(file, (str, bytes, os.PathLike))
                    and Path(os.fsdecode(file)).name == "knowledge-provider.snapshot.json"):
                pytest.fail("Reference removal attempted to open a provider")
            return original(file, *args, **kwargs)
        return checked

    with pytest.MonkeyPatch.context() as patch:
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
        if command == "reference-plan":
            headers = tuple(root / "research/Overview.md" for root in scope.source_roots.values())
            with _inspection_guard(scope, header_paths=headers):
                result = CliRunner().invoke(cli.main, ["knowledge", command, *arguments], input=input)
        else:
            result = CliRunner().invoke(cli.main, ["knowledge", command, *arguments], input=input)
    if command == "reference-plan":
        assert _filesystem(scope.temporary) == before
    return result


def _payload(result) -> dict:
    assert result.exit_code == 0, result.output
    # Interactive confirmation may precede the JSON result; it is not a second
    # machine object, and successful --yes output must still be ordinary JSON.
    start = result.output.find("{")
    assert start >= 0, result.output
    return json.loads(result.output[start:])


def _plan(scope: SyntheticScope, operation: str = "add", *, language: str = "en") -> dict:
    result = _invoke(scope, "reference-plan", *_selection(operation, language=language),
                     "--format", "json", "--language", language,
                     forbid_provider_reads=operation == "remove")
    payload = _payload(result)
    assert re.fullmatch(r"[0-9a-f]{64}", payload["approved_digest"])
    return payload


def _mappings(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def _assert_json_identity(payload: dict, operation: str) -> None:
    mappings = list(_mappings(payload))
    for key, value in (("source_id", SOURCE_A), ("field_id", FIELD_A),
                       ("operation", operation), ("reference_id", REFERENCE_ID),
                       ("source_id", SOURCE_B), ("object_id", ANALYSIS)):
        assert any(row.get(key) == value for row in mappings), (key, value, payload)


def _assert_human(scope: SyntheticScope, text: str) -> None:
    for hidden in (SOURCE_A, SOURCE_B, FIELD_A, FIELD_B, PAPER, ANALYSIS, CANVAS,
                   str(scope.root), str(scope.source_roots[SOURCE_B]), str(scope.registry.path)):
        assert hidden not in text
    assert '"reference_id"' not in text and '"content_rewritten"' not in text


def _assert_only_manifest_changed(scope: SyntheticScope, before: dict) -> dict:
    after = _filesystem(scope.temporary)
    key = (scope.root / ".scholar-workflow/fields.yml").relative_to(scope.temporary).as_posix()
    assert set(after) == set(before)
    assert {name for name in after if after[name] != before[name]} == {key}
    return yaml.safe_load((scope.root / ".scholar-workflow/fields.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("operation", ["add", "remove"])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_preview_human_explains_selected_field_action_purpose_and_unchanged_content(
    write_scope, operation, language,
):
    scope = write_scope
    if operation == "remove":
        _declare_references(scope, [_reference(purpose=PURPOSES[language])])
    result = _invoke(scope, "reference-plan", *_selection(operation, language=language),
                     "--format", "md", "--language", language,
                     forbid_provider_reads=operation == "remove")
    assert result.exit_code == 0, result.output
    text = result.output
    assert "合成研究领域" in text and PURPOSES[language] in text
    if language == "zh":
        assert "引用" in text and "用途" in text and "摘要" in text
        assert re.search(r"新增|增加|添加" if operation == "add" else r"移除|删除引用", text)
        assert re.search(r"正文|原文|内容", text) and re.search(r"不变|不改|不修改|保持", text)
    else:
        lower = text.lower()
        assert "reference" in lower and "purpose" in lower and "digest" in lower
        assert re.search(r"add|append" if operation == "add" else r"remove", lower)
        assert re.search(r"content|prose|body", lower) and re.search(r"unchanged|not.*(?:write|change|rewrite)", lower)
    if operation == "add":
        assert ANALYSIS_PATH in text
    _assert_human(scope, text)


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_preview_json_preserves_explicit_identities_and_stable_digest(write_scope, operation):
    scope = write_scope
    if operation == "remove":
        _declare_references(scope, [_reference()])
    first = _plan(scope, operation)
    second = _plan(scope, operation)
    _assert_json_identity(first, operation)
    assert first["approved_digest"] == second["approved_digest"]


@pytest.mark.parametrize("language", ["en", "zh"])
def test_confirmation_cancel_changes_nothing(write_scope, language):
    scope = write_scope
    plan = _plan(scope, language=language)
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference", *_selection(language=language),
                     "--approved-digest", plan["approved_digest"],
                     "--format", "md", "--language", language, input="n\n")
    assert result.exit_code != 0
    assert _filesystem(scope.temporary) == before
    _assert_human(scope, result.output)


@pytest.mark.parametrize("fmt,language,confirmation", [
    ("json", "en", "yes"), ("md", "zh", "yes"),
    ("json", "zh", "interactive"), ("md", "en", "interactive"),
])
def test_confirmed_add_changes_only_reference_manifest(write_scope, fmt, language, confirmation):
    scope = write_scope
    plan = _plan(scope, language=language)
    before = _filesystem(scope.temporary)
    arguments = [*_selection(language=language), "--approved-digest", plan["approved_digest"],
                 "--format", fmt, "--language", language]
    if confirmation == "yes":
        arguments.append("--yes")
    result = _invoke(scope, "reference", *arguments, input="y\n" if confirmation == "interactive" else None)
    assert result.exit_code == 0, result.output
    manifest = _assert_only_manifest_changed(scope, before)
    assert manifest["schema_version"] == 2
    assert manifest["fields"][0]["references"] == [_reference(purpose=PURPOSES[language])]
    if fmt == "json":
        payload = _payload(result)
        assert payload["status"] == "applied"
        assert payload["content_rewritten"] is False and payload["human_verified"] is False
    else:
        _assert_human(scope, result.output)
        assert re.search(r"成功|完成|已增加|已更新", result.output) if language == "zh" else re.search(
            r"applied|added|updated|success", result.output.lower())
        assert re.search(r"原文|正文|内容", result.output) if language == "zh" else re.search(
            r"content|prose|body", result.output.lower())
        assert re.search(r"不变|不改|不修改|保持", result.output) if language == "zh" else re.search(
            r"unchanged|not.*(?:write|change|rewrite)", result.output.lower())


def test_identical_add_reports_unchanged_without_writes(write_scope):
    scope = write_scope
    _declare_references(scope, [_reference()])
    plan = _plan(scope)
    assert plan["status"] == "unchanged"
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference", *_selection(), "--approved-digest", plan["approved_digest"],
                     "--yes", "--format", "json")
    payload = _payload(result)
    assert payload["status"] == "unchanged"
    assert payload["content_rewritten"] is False and payload["human_verified"] is False
    assert _filesystem(scope.temporary) == before


@pytest.mark.parametrize("language", ["en", "zh"])
def test_unchanged_human_receipt_is_concise_and_keeps_content_unchanged(write_scope, language):
    scope = write_scope
    _declare_references(scope, [_reference(purpose=PURPOSES[language])])
    plan = _plan(scope, language=language)
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference", *_selection(language=language),
                     "--approved-digest", plan["approved_digest"], "--yes",
                     "--format", "md", "--language", language)
    assert result.exit_code == 0, result.output
    assert _filesystem(scope.temporary) == before
    _assert_human(scope, result.output)
    if language == "zh":
        assert re.search(r"无需|无变化|未改变|未变|没有变化|已存在", result.output)
        assert re.search(r"正文|原文|内容", result.output) and re.search(r"不变|不改|保持", result.output)
    else:
        lower = result.output.lower()
        assert re.search(r"unchanged|no change|already", lower)
        assert re.search(r"content|prose|body", lower) and "unchanged" in lower


def test_remove_offline_target_preserves_other_reference_and_all_source_files(write_scope):
    scope = write_scope
    kept = _reference(reference_id=KEEP_ID, object_id=CANVAS)
    _declare_references(scope, [_reference(), kept])
    provider = scope.registry.path.parent / "knowledge-providers" / SOURCE_B / "knowledge-provider.snapshot.json"
    provider.unlink()
    plan = _plan(scope, "remove")
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference", *_selection("remove"),
                     "--approved-digest", plan["approved_digest"], "--yes", "--format", "json",
                     forbid_provider_reads=True)
    payload = _payload(result)
    assert payload["status"] == "applied" and payload["content_rewritten"] is False
    manifest = _assert_only_manifest_changed(scope, before)
    assert manifest["schema_version"] == 2 and manifest["fields"][0]["references"] == [kept]


@pytest.mark.parametrize("case", ["unknown-source", "unknown-target", "dirty-purpose", "remove-extra", "absent-ref"])
def test_safety_refusal_exits_seven_without_writes(write_scope, case):
    scope = write_scope
    if case == "unknown-source":
        selection = _selection(source_id=UNKNOWN_SOURCE)
    elif case == "unknown-target":
        selection = _selection(target_source_id=UNKNOWN_SOURCE)
    elif case == "dirty-purpose":
        selection = _selection(purpose=" leading whitespace")
    elif case == "remove-extra":
        _declare_references(scope, [_reference()])
        selection = [*_selection("remove"), "--purpose", "Remove must reject add-only fields."]
    else:
        selection = _selection("remove", reference_id="not-declared")
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference-plan", *selection, "--format", "md")
    assert result.exit_code == 7, result.output
    assert _filesystem(scope.temporary) == before


def test_wrong_approval_digest_exits_seven_without_writes(write_scope):
    scope = write_scope
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference", *_selection(), "--approved-digest", "0" * 64,
                     "--yes", "--format", "json")
    assert result.exit_code == 7, result.output
    assert _filesystem(scope.temporary) == before


@pytest.mark.parametrize("language", ["en", "zh"])
def test_removal_preview_distinguishes_references_with_identical_purpose(write_scope, language):
    scope = write_scope
    _declare_references(scope, [_reference(purpose=PURPOSES[language]),
                               _reference(reference_id=KEEP_ID, object_id=CANVAS,
                                          purpose=PURPOSES[language])])
    before = _filesystem(scope.temporary)
    result = _invoke(scope, "reference-plan", *_selection("remove"),
                     "--format", "md", "--language", language, forbid_provider_reads=True)
    assert result.exit_code == 0, result.output
    assert REFERENCE_ID in result.output and KEEP_ID not in result.output
    _assert_human(scope, result.output)
    assert _filesystem(scope.temporary) == before


def test_uncertain_publication_exits_six_with_fresh_plan_guidance(write_scope, monkeypatch):
    from scholar_workflow.knowledge.fields import FieldRegistryCommitUncertain
    from scholar_workflow.workflows import field_references

    scope = write_scope
    before = _filesystem(scope.temporary)

    def uncertain(*_args, **_kwargs):
        raise FieldRegistryCommitUncertain(
            "Publication durability is uncertain; inspect a fresh plan before retrying. "
            "Do not reuse a stale digest."
        )

    monkeypatch.setattr(field_references, "change_reference", uncertain)
    result = _invoke(scope, "reference", *_selection(), "--approved-digest", "0" * 64,
                     "--yes", "--format", "md", "--language", "en")
    assert result.exit_code == 6, result.output
    lower = result.output.lower()
    assert "uncertain" in lower and "fresh plan" in lower
    assert "do not reuse a stale digest" in lower
    assert not re.search(r"\b(?:success|successful|applied|updated)\b", lower)
    assert "nothing has been written" not in lower and "not written" not in lower
    assert "未写入" not in result.output
    assert _filesystem(scope.temporary) == before
