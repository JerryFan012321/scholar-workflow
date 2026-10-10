"""Independent synthetic tests for single-manifest Field reference changes.

Hand-written expectations precede this file in field-reference-writes/EXPECTED.md.
Only pytest roots are used; plan output is never the expected manifest oracle.

Publication boundary expectations, prepared before the tests below:
- Approval is the existing CLI's plain 64-hex digest, not a sha256:-prefixed hash.
- Replacing the manifest with identical bytes but a new inode after temporary
  content fsync must refuse publication and retain the replacement inode.
- FIFO or oversized manifest replacements at that boundary must refuse without
  blocking, writing over the replacement, or leaving a temporary file.
- Swapping the registered root or its state directory after temporary content
  fsync must refuse; neither the detached directory nor its replacement receives
  the approved reference or any leaked publication file.
- An unchanged operation still reports a directory durability failure rather
  than claiming success; its manifest remains byte-identical.
- After temporary-file fsync, changed target/primary file metadata or replaced
  provider, other-Source Field manifest, or registry declarations invalidate the
  whole approval read set. Refuse before the selected manifest's final replace;
  preserve the injected change and the byte-identical referring manifest.
"""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import builtins
import io
import json
import os
import re
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.knowledge.fields import FieldRegistryError
from tests.contract.test_knowledge_ownership import (
    ANALYSIS,
    CORE,
    FIELD_A,
    FIELD_B,
    OWNER_PATH,
    PAPER,
    PATHS,
    SOURCE_A,
    SOURCE_B,
    _add_source,
    _filesystem,
    _inspection_guard,
    _write_json,
    ownership_scope,  # noqa: F401
)

_REFERENCE_ID = "shared-paper"
_PURPOSE = "Use the existing paper without copying or reassigning its owner."
_OTHER_FIELD = "77777777-7777-4777-8777-777777777777"
_UNKNOWN_SOURCE = "99999999-9999-4999-8999-999999999999"


def _api():
    # Missing implementation must be visible RED, not a collection-time failure.
    from scholar_workflow.workflows.field_references import change_reference, reference_plan

    return reference_plan, change_reference


def _reference(reference_id=_REFERENCE_ID, *, source_id=SOURCE_A, object_id=PAPER, purpose=_PURPOSE):
    return {"reference_id": reference_id,
            "target": {"source_id": source_id, "object_id": object_id}, "purpose": purpose}


def _selection(*, source_id=SOURCE_A, field_id=FIELD_A, operation="add",
               reference_id=_REFERENCE_ID, target_source_id=SOURCE_A, object_id=PAPER,
               purpose=_PURPOSE):
    value = {"source_id": source_id, "field_id": field_id,
             "operation": operation, "reference_id": reference_id}
    if operation != "remove":
        value.update(target_source_id=target_source_id, object_id=object_id, purpose=purpose)
    return value


def _fields(scope, source_id=SOURCE_A):
    return scope.source_roots[source_id] / ".scholar-workflow/fields.yml"


def _make_writable(scope, source_id=SOURCE_A):
    document = json.loads(scope.registry.path.read_bytes())
    source = next(row for row in document["sources"] if row["source_id"] == source_id)
    folder = next(row for row in document["folders"] if row["folder_id"] == source["folder_id"])
    source["capabilities"] = folder["capabilities"] = ["read", "write"]
    _write_json(scope.registry.path, document)


def _clear_provider(provider):
    # Fixture setup only: use the existing model to form a legal empty provider.
    document = json.loads(provider.read_bytes())
    for member in ("atomic_resources", "core_documents", "supporting_documents"):
        document["manifest"][member] = []
    document["catalog"].update(resources=[], revision="")
    document["snapshot_revision"] = ""
    _write_json(provider, KnowledgeProviderSnapshot.model_validate(document).model_dump(mode="json"))


def _prepare(scope, *, cross_source=False, object_id=PAPER):
    source_id, field_id = SOURCE_A, FIELD_A
    if cross_source:
        _clear_provider(_add_source(scope))
        source_id, field_id = SOURCE_B, FIELD_B
    _make_writable(scope, source_id)
    # Existing coordination lock files are fixture inputs, not test oracles.
    # The preview guard still rejects writable opens, even on these files.
    (scope.registry.path.parent / f".{scope.registry.path.name}.lock").touch(mode=0o600)
    for provider in (scope.registry.path.parent / "knowledge-providers").iterdir():
        (provider / ".knowledge-provider.apply.lock").touch(mode=0o600)
    return _selection(source_id=source_id, field_id=field_id, object_id=object_id)


def _set_references(scope, references, *, source_id=SOURCE_A):
    path = _fields(scope, source_id)
    document = yaml.safe_load(path.read_bytes())
    document["schema_version"] = 2
    document["fields"][0]["references"] = references
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _assert_business_unchanged(scope, before, *, changed_manifest=None):
    after = _filesystem(scope.temporary)
    if changed_manifest is not None:
        relative = changed_manifest.relative_to(scope.temporary).as_posix()
        before, after = dict(before), dict(after)
        before.pop(relative)
        after.pop(relative)
    assert after == before


def _guarded_plan(scope, selection):
    reference_plan, _ = _api()
    before = _filesystem(scope.temporary)
    with _inspection_guard(scope):
        plan = reference_plan(scope.registry, **selection)
    assert _filesystem(scope.temporary) == before
    return plan


@contextmanager
def _deny_provider_reads(monkeypatch):
    def protected(original):
        def checked(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                candidate = Path(os.fsdecode(path))
                if (candidate.name == "knowledge-provider.snapshot.json"
                        or "knowledge-providers" in candidate.parts):
                    pytest.fail("Reference removal accessed a provider or its lock directory")
            return original(path, *args, **kwargs)
        return checked

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", protected(builtins.open))
        patch.setattr(io, "open", protected(io.open))
        patch.setattr(os, "open", protected(os.open))
        yield


@pytest.mark.parametrize("cross_source", [False, True])
@pytest.mark.parametrize("object_id", [PAPER, ANALYSIS])
def test_preview_and_add_only_change_selected_manifest(ownership_scope, cross_source, object_id):
    scope = ownership_scope
    selection = _prepare(scope, cross_source=cross_source, object_id=object_id)
    fields = _fields(scope, selection["source_id"])
    original_text = fields.read_text(encoding="utf-8")
    expected = yaml.safe_load(original_text)
    expected["schema_version"] = 2
    expected_reference = _reference(object_id=object_id)
    expected["fields"][0]["references"] = [expected_reference]
    before = _filesystem(scope.temporary)

    plan = _guarded_plan(scope, selection)
    assert plan["status"] == "ready"
    assert plan["reference"] == expected_reference
    assert plan["manifest_before"] == original_text
    assert yaml.safe_load(plan["manifest_after"]) == expected
    assert re.fullmatch(r"[0-9a-f]{64}", plan["approved_digest"])
    assert _guarded_plan(scope, selection)["approved_digest"] == plan["approved_digest"]

    _, change_reference = _api()
    result = change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)
    assert result["status"] == "applied"
    assert result["human_verified"] is result["content_rewritten"] is False
    assert yaml.safe_load(fields.read_bytes()) == expected
    _assert_business_unchanged(scope, before, changed_manifest=fields)

    unchanged = _guarded_plan(scope, selection)
    assert unchanged["status"] == "unchanged"
    assert unchanged["reference"] == expected_reference
    assert unchanged["manifest_before"] == unchanged["manifest_after"] == fields.read_text(encoding="utf-8")
    after_add = _filesystem(scope.temporary)
    result = change_reference(scope.registry, approved_digest=unchanged["approved_digest"], **selection)
    assert result["status"] == "unchanged"
    _assert_business_unchanged(scope, after_add)


def test_add_preserves_comments_other_fields_navigation_and_existing_references(ownership_scope):
    scope = ownership_scope
    selection = _prepare(scope)
    fields = _fields(scope)
    document = yaml.safe_load(fields.read_bytes())
    document["schema_version"] = 2
    document["fields"][0]["references"] = [_reference("existing-core", object_id=CORE)]
    document["fields"][0]["navigation"] = [
        {"label": "Existing analysis", "items": ["resources/papers/ownership/Analysis.md"]},
    ]
    other = {"field_id": _OTHER_FIELD, "title": "Unrelated field", "relative_root": "other",
             "home": "Overview.md", "navigation": [],
             "references": [_reference("other-analysis", object_id=ANALYSIS)]}
    document["fields"].append(other)
    (scope.root / "other").mkdir()
    (scope.root / "other/Overview.md").write_text("# Unrelated human note\n", encoding="utf-8")
    text = yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    text = "# Preserve this human comment.\n" + text.replace(
        "schema_version: 2", "schema_version: 2 # Preserve this inline comment.", 1,
    )
    fields.write_text(text, encoding="utf-8")
    expected = yaml.safe_load(text)
    expected["fields"][0]["references"].append(_reference())
    before = _filesystem(scope.temporary)

    plan = _guarded_plan(scope, selection)
    _, change_reference = _api()
    change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    after = fields.read_text(encoding="utf-8")
    assert yaml.safe_load(after) == expected
    assert "# Preserve this human comment." in after
    assert "# Preserve this inline comment." in after
    _assert_business_unchanged(scope, before, changed_manifest=fields)


@pytest.mark.parametrize("conflict", ["id-purpose", "id-target", "target-id"])
def test_add_refuses_id_replacement_and_duplicate_qualified_target(ownership_scope, conflict):
    scope = ownership_scope
    selection = _prepare(scope)
    _set_references(scope, [_reference()])
    if conflict == "id-purpose":
        selection["purpose"] = "A different unapproved purpose."
    elif conflict == "id-target":
        selection["object_id"] = ANALYSIS
    else:
        selection["reference_id"] = "second-name"
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, selection)
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("problem", ["unknown-source", "unknown-object", "wrong-source",
                                      "global-owner-conflict", "external-provider-missing"])
def test_add_requires_globally_unique_owner_and_correct_target_source(ownership_scope, problem):
    scope = ownership_scope
    selection = _prepare(scope)
    if problem == "unknown-source":
        selection["target_source_id"] = _UNKNOWN_SOURCE
    elif problem == "unknown-object":
        selection["object_id"] = "paper:synthetic:undeclared"
    else:
        second_provider = _add_source(scope)
        (second_provider.parent / ".knowledge-provider.apply.lock").touch(mode=0o600)
        if problem != "global-owner-conflict":
            _clear_provider(second_provider)
        if problem == "wrong-source":
            selection["target_source_id"] = SOURCE_B
        elif problem == "external-provider-missing":
            second_provider.unlink()
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, selection)
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("member", ["object", "owner"])
@pytest.mark.parametrize("state", ["missing", "symlink"])
def test_add_requires_available_object_and_primary_files(ownership_scope, member, state):
    scope = ownership_scope
    selection = _prepare(scope, object_id=ANALYSIS)
    path = scope.root / (PATHS[ANALYSIS] if member == "object" else OWNER_PATH)
    content = path.read_bytes()
    path.unlink()
    if state == "symlink":
        outside = scope.temporary / f"external-{member}.md"
        outside.write_bytes(content)
        path.symlink_to(outside)
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, selection)
    _assert_business_unchanged(scope, before)


def test_read_only_reference_source_does_not_gain_write_permission(ownership_scope):
    scope = ownership_scope
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, _selection())
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("target_state", ["registered", "provider-missing", "root-offline",
                                         "unregistered", "all-providers-missing"])
def test_remove_does_not_inspect_target_provider_or_delete_content(ownership_scope, monkeypatch, target_state):
    scope = ownership_scope
    _prepare(scope)
    provider = _add_source(scope)
    (provider.parent / ".knowledge-provider.apply.lock").touch(mode=0o600)
    removed = _reference(source_id=SOURCE_B)
    retained = _reference("retained-analysis", object_id=ANALYSIS)
    _set_references(scope, [removed, retained])
    if target_state == "provider-missing":
        provider.unlink()
    elif target_state == "all-providers-missing":
        provider.unlink()
        scope.provider.unlink()
    elif target_state == "root-offline":
        scope.source_roots[SOURCE_B].rename(scope.temporary / "offline-source-b")
    elif target_state == "unregistered":
        registry = json.loads(scope.registry.path.read_bytes())
        registry["sources"] = [row for row in registry["sources"] if row["source_id"] != SOURCE_B]
        registry["folders"] = [row for row in registry["folders"] if row["folder_id"] != "synthetic-b"]
        _write_json(scope.registry.path, registry)
    fields = _fields(scope)
    expected = yaml.safe_load(fields.read_bytes())
    expected["fields"][0]["references"] = [retained]
    selection = _selection(operation="remove")
    before = _filesystem(scope.temporary)
    reference_plan, change_reference = _api()

    with _inspection_guard(scope), _deny_provider_reads(monkeypatch):
        plan = reference_plan(scope.registry, **selection)
    assert _filesystem(scope.temporary) == before
    assert plan["reference"] == removed and plan["status"] == "ready"
    assert yaml.safe_load(plan["manifest_after"]) == expected
    with _deny_provider_reads(monkeypatch):
        result = change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    assert result["status"] == "applied"
    assert yaml.safe_load(fields.read_bytes()) == expected
    assert expected["schema_version"] == 2
    _assert_business_unchanged(scope, before, changed_manifest=fields)


def test_remove_last_reference_does_not_downgrade_schema(ownership_scope):
    scope = ownership_scope
    _prepare(scope)
    _set_references(scope, [_reference()])
    fields = _fields(scope)
    expected = yaml.safe_load(fields.read_bytes())
    expected["fields"][0].pop("references")
    selection = _selection(operation="remove")
    plan = _guarded_plan(scope, selection)
    _, change_reference = _api()
    change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)
    actual = yaml.safe_load(fields.read_bytes())
    assert actual["schema_version"] == 2
    assert actual["fields"][0].get("references", []) == []
    actual["fields"][0].pop("references", None)
    assert actual == expected


def test_remove_unknown_reference_refuses_without_changes(ownership_scope):
    scope = ownership_scope
    _prepare(scope)
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, _selection(operation="remove"))
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("extra,value", [("target_source_id", SOURCE_A), ("object_id", PAPER),
                                        ("purpose", _PURPOSE)])
def test_remove_rejects_add_only_arguments(ownership_scope, extra, value):
    scope = ownership_scope
    _prepare(scope)
    _set_references(scope, [_reference()])
    selection = _selection(operation="remove")
    selection[extra] = value
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, selection)
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("member,value", [("purpose", " unclean "), ("purpose", "line\nbreak"),
                                         ("reference_id", "../outside"), ("object_id", "/outside.md"),
                                         ("operation", "replace")])
def test_invalid_selection_refuses_without_changes(ownership_scope, member, value):
    scope = ownership_scope
    selection = _prepare(scope)
    selection[member] = value
    before = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        _guarded_plan(scope, selection)
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("mutation", ["manifest", "registry", "provider", "target-fields",
                                      "object-metadata", "owner-metadata", "target-root", "source-root",
                                      "object-symlink", "ancestor-symlink", "manifest-symlink",
                                      "provider-symlink"])
def test_stale_approval_preserves_current_bytes_and_refuses_unsafe_bindings(ownership_scope, mutation):
    scope = ownership_scope
    selection = _prepare(scope, cross_source=True, object_id=ANALYSIS)
    fields = _fields(scope, SOURCE_B)
    plan = _guarded_plan(scope, selection)
    if mutation in {"manifest", "target-fields"}:
        path = fields if mutation == "manifest" else _fields(scope)
        path.write_bytes(path.read_bytes() + b"# Human edit after approval.\n")
    elif mutation in {"registry", "provider"}:
        path = scope.registry.path if mutation == "registry" else scope.provider
        path.write_bytes(path.read_bytes() + b"\n")
    elif mutation in {"object-metadata", "owner-metadata"}:
        path = scope.root / (PATHS[ANALYSIS] if mutation == "object-metadata" else OWNER_PATH)
        metadata = path.stat()
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000))
    elif mutation in {"target-root", "source-root"}:
        root = scope.root if mutation == "target-root" else scope.source_roots[SOURCE_B]
        moved = root.with_name(root.name + "-original")
        root.rename(moved)
        shutil.copytree(moved, root)
        assert root.stat().st_ino != moved.stat().st_ino
    elif mutation == "ancestor-symlink":
        parent = (scope.root / PATHS[ANALYSIS]).parent
        moved = scope.temporary / "external-paper-directory"
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
    else:
        path = {"object-symlink": scope.root / PATHS[ANALYSIS],
                "manifest-symlink": fields, "provider-symlink": scope.provider}[mutation]
        external = scope.temporary / ("external-" + path.name)
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
    before_apply = _filesystem(scope.temporary)
    _, change_reference = _api()
    with pytest.raises(FieldRegistryError):
        change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)
    _assert_business_unchanged(scope, before_apply)


def test_post_publication_fsync_failure_is_not_a_stale_approval_recovery_license(ownership_scope, monkeypatch):
    scope = ownership_scope
    selection = _prepare(scope)
    fields = _fields(scope)
    expected = yaml.safe_load(fields.read_bytes())
    expected["schema_version"] = 2
    expected["fields"][0]["references"] = [_reference()]
    plan = _guarded_plan(scope, selection)
    before = _filesystem(scope.temporary)
    _, change_reference = _api()
    original_replace, original_fsync = os.replace, os.fsync
    state = {"published": False, "failed": False}

    def replacing(source, destination, *args, **kwargs):
        result = original_replace(source, destination, *args, **kwargs)
        if Path(os.fsdecode(destination)).name == "fields.yml":
            state["published"] = True
        return result

    def syncing(descriptor):
        if (state["published"] and not state["failed"]
                and stat.S_ISDIR(os.fstat(descriptor).st_mode)):
            state["failed"] = True
            raise OSError("Synthetic post-publication directory durability failure")
        return original_fsync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", replacing)
        patch.setattr(os, "fsync", syncing)
        with pytest.raises(FieldRegistryError):
            change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    assert state == {"published": True, "failed": True}
    assert yaml.safe_load(fields.read_bytes()) == expected
    _assert_business_unchanged(scope, before, changed_manifest=fields)
    after_publication = _filesystem(scope.temporary)
    with pytest.raises(FieldRegistryError):
        change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)
    _assert_business_unchanged(scope, after_publication)
    fresh = _guarded_plan(scope, selection)
    assert fresh["status"] == "unchanged"
    assert fresh["reference"] == _reference()
    assert fresh["manifest_before"] == fresh["manifest_after"] == fields.read_text(encoding="utf-8")


def _intercept_publication_fsync(monkeypatch, mutate):
    """Inject after successful temporary-file fsync, not before the plan/CAS."""
    from scholar_workflow.workflows import field_references

    original_publish = field_references._publish_manifest
    original_fsync = os.fsync
    state = {"active": False, "injected": False}

    def publishing(*args, **kwargs):
        state["active"] = True
        try:
            return original_publish(*args, **kwargs)
        finally:
            state["active"] = False

    def syncing(descriptor):
        result = original_fsync(descriptor)
        if (state["active"] and not state["injected"]
                and stat.S_ISREG(os.fstat(descriptor).st_mode)):
            state["injected"] = True
            mutate(descriptor)
        return result

    monkeypatch.setattr(field_references, "_publish_manifest", publishing)
    monkeypatch.setattr(os, "fsync", syncing)
    return state


@pytest.mark.parametrize("replacement", ["same-bytes-new-inode", "fifo", "oversized"])
def test_final_manifest_cas_rejects_replacement_without_overwrite_or_blocking(
    ownership_scope, monkeypatch, replacement,
):
    scope = ownership_scope
    selection = _prepare(scope)
    fields = _fields(scope)
    original = fields.read_bytes()
    original_inode = fields.stat().st_ino
    plan = _guarded_plan(scope, selection)
    before = _filesystem(scope.temporary)
    expected = dict(before)
    relative = fields.relative_to(scope.temporary).as_posix()
    replacement_identity = {}

    def mutate(_descriptor):
        if replacement == "same-bytes-new-inode":
            new_file = fields.with_name("human-replacement.yml")
            new_file.write_bytes(original)
            os.replace(new_file, fields)
            assert fields.stat().st_ino != original_inode
        elif replacement == "fifo":
            fields.unlink()
            os.mkfifo(fields, mode=0o600)
            expected[relative] = ("special", fields.lstat().st_mode)
        else:
            payload = b"x" * (2 * 1024 * 1024 + 1)
            fields.unlink()
            fields.write_bytes(payload)
            expected[relative] = ("file", payload)
        metadata = fields.lstat()
        replacement_identity.update(device=metadata.st_dev, inode=metadata.st_ino)

    _, change_reference = _api()
    with monkeypatch.context() as patch:
        state = _intercept_publication_fsync(patch, mutate)
        if replacement == "fifo":
            original_open = os.open

            def nonblocking_open(path, flags, *args, **kwargs):
                if (state["injected"] and isinstance(path, (str, bytes, os.PathLike))
                        and Path(os.fsdecode(path)).name == "fields.yml"):
                    assert flags & os.O_NONBLOCK, "Publication attempted a blocking FIFO open"
                return original_open(path, flags, *args, **kwargs)

            def no_fifo_stream(original_stream):
                def checked(path, *args, **kwargs):
                    if (state["injected"] and isinstance(path, (str, bytes, os.PathLike))
                            and Path(os.fsdecode(path)).name == "fields.yml"):
                        pytest.fail("Publication attempted a blocking high-level FIFO stream")
                    return original_stream(path, *args, **kwargs)
                return checked

            patch.setattr(os, "open", nonblocking_open)
            patch.setattr(builtins, "open", no_fifo_stream(builtins.open))
            patch.setattr(io, "open", no_fifo_stream(io.open))
        with pytest.raises(FieldRegistryError):
            change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    assert state["injected"]
    assert (fields.lstat().st_dev, fields.lstat().st_ino) == (
        replacement_identity["device"], replacement_identity["inode"],
    )
    assert _filesystem(scope.temporary) == expected


@pytest.mark.parametrize("directory", ["root", "state"])
def test_final_publication_refuses_directory_swap_without_writing_either_manifest(
    ownership_scope, monkeypatch, directory,
):
    scope = ownership_scope
    selection = _prepare(scope)
    fields = _fields(scope)
    state_directory = fields.parent
    plan = _guarded_plan(scope, selection)
    before_root = _filesystem(scope.root)
    before_state = _filesystem(state_directory)
    before_host = _filesystem(scope.registry.path.parent)
    before_project = _filesystem(scope.project)
    detached = scope.root.with_name("detached-source-a") if directory == "root" else (
        scope.root / "detached-scholar-state"
    )

    def mutate(descriptor):
        identity = os.fstat(descriptor)
        temporary = [path.name for path in state_directory.iterdir()
                     if path.is_file() and (path.stat().st_dev, path.stat().st_ino)
                     == (identity.st_dev, identity.st_ino)]
        assert len(temporary) == 1 and temporary[0] != "fields.yml"
        original = scope.root if directory == "root" else state_directory
        original.rename(detached)
        copied_state = detached / ".scholar-workflow" if directory == "root" else detached

        def exclude_unpublished_file(current, _names):
            return temporary if Path(current) == copied_state else []

        shutil.copytree(detached, original, ignore=exclude_unpublished_file)

    _, change_reference = _api()
    with monkeypatch.context() as patch:
        state = _intercept_publication_fsync(patch, mutate)
        with pytest.raises(FieldRegistryError):
            change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    assert state["injected"]
    assert _filesystem(scope.registry.path.parent) == before_host
    assert _filesystem(scope.project) == before_project
    if directory == "root":
        assert _filesystem(scope.root) == _filesystem(detached) == before_root
    else:
        assert _filesystem(state_directory) == _filesystem(detached) == before_state
        expected_root = dict(before_root)
        expected_root[detached.name] = ("directory",)
        expected_root.update({f"{detached.name}/{name}": value for name, value in before_state.items()})
        assert _filesystem(scope.root) == expected_root


def test_unchanged_operation_does_not_claim_success_after_directory_fsync_failure(
    ownership_scope, monkeypatch,
):
    scope = ownership_scope
    selection = _prepare(scope)
    _set_references(scope, [_reference()])
    plan = _guarded_plan(scope, selection)
    assert plan["status"] == "unchanged"
    fields = _fields(scope)
    original = fields.read_bytes()
    directory = fields.parent.stat()
    before = _filesystem(scope.temporary)
    original_fsync = os.fsync
    state = {"failed": False}

    def syncing(descriptor):
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) == (directory.st_dev, directory.st_ino):
            state["failed"] = True
            raise OSError("Synthetic unchanged-manifest directory durability failure")
        return original_fsync(descriptor)

    _, change_reference = _api()
    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", syncing)
        with pytest.raises(FieldRegistryError):
            change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    assert state["failed"]
    assert fields.read_bytes() == original
    _assert_business_unchanged(scope, before)


@pytest.mark.parametrize("changed_input", ["target-metadata", "owner-metadata", "provider",
                                         "other-source-fields", "registry"])
def test_final_publication_rechecks_whole_read_set_before_manifest_replace(
    ownership_scope, monkeypatch, changed_input,
):
    scope = ownership_scope
    selection = _prepare(scope, cross_source=True, object_id=ANALYSIS)
    fields = _fields(scope, SOURCE_B)
    original_manifest = fields.read_bytes()
    manifest_inode = fields.stat().st_ino
    selected_state = fields.parent.stat()
    plan = _guarded_plan(scope, selection)
    before = _filesystem(scope.temporary)
    changed_path = {
        "target-metadata": scope.root / PATHS[ANALYSIS],
        "owner-metadata": scope.root / OWNER_PATH,
        "provider": scope.provider,
        "other-source-fields": _fields(scope, SOURCE_A),
        "registry": scope.registry.path,
    }[changed_input]
    original_input = changed_path.read_bytes()
    original_input_inode = changed_path.stat().st_ino
    injected_metadata = {}
    replacement_attempts = []
    original_replace = os.replace

    def mutate(_descriptor):
        if changed_input.endswith("metadata"):
            metadata = changed_path.stat()
            os.utime(changed_path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000))
        else:
            # Identical bytes are deliberate: a hash-only refresh must not hide
            # replacement of an approved authoritative declaration's inode.
            replacement = changed_path.with_name(".late-reference-declaration")
            replacement.write_bytes(original_input)
            os.replace(replacement, changed_path)
            assert changed_path.stat().st_ino != original_input_inode
        metadata = changed_path.stat()
        injected_metadata.update(device=metadata.st_dev, inode=metadata.st_ino,
                                 mtime_ns=metadata.st_mtime_ns, ctime_ns=metadata.st_ctime_ns)

    def replacing(source, destination, *args, **kwargs):
        path = Path(os.fsdecode(destination))
        selected = path.is_absolute() and path == fields
        if not path.is_absolute() and path.name == "fields.yml" and kwargs.get("dst_dir_fd") is not None:
            metadata = os.fstat(kwargs["dst_dir_fd"])
            selected = (metadata.st_dev, metadata.st_ino) == (selected_state.st_dev, selected_state.st_ino)
        if selected:
            replacement_attempts.append("selected-manifest")
        return original_replace(source, destination, *args, **kwargs)

    _, change_reference = _api()
    with monkeypatch.context() as patch:
        state = _intercept_publication_fsync(patch, mutate)
        patch.setattr(os, "replace", replacing)
        with pytest.raises(FieldRegistryError):
            change_reference(scope.registry, approved_digest=plan["approved_digest"], **selection)

    assert state["injected"]
    assert replacement_attempts == []
    assert fields.read_bytes() == original_manifest
    assert fields.stat().st_ino == manifest_inode
    assert changed_path.read_bytes() == original_input
    current = changed_path.stat()
    assert (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns) == (
        injected_metadata["device"], injected_metadata["inode"],
        injected_metadata["mtime_ns"], injected_metadata["ctime_ns"],
    )
    _assert_business_unchanged(scope, before)
