"""Digest-bound, single-manifest changes to contextual Field references.

References select existing owners. No provider, paper body, reader, copy or second
catalog is created. A failed durability check requires a new observation, not rollback.
"""
from __future__ import annotations

import fcntl
import io
import os
import re
import secrets
from contextlib import ExitStack
from pathlib import Path

import yaml
from ruamel.yaml import YAML

from scholar_workflow.analysis.apply_changes import _locked_state_root
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryCommitUncertain,
    FieldRegistryError,
    FieldResourceReference,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.knowledge.presentation import _text
from scholar_workflow.workflows.knowledge_ownership import (
    _file_observation,
    _json,
    _open_checked_chain,
    _qualified_result,
    _read_declaration,
    _resolve_objects,
    _root_identity,
    _UniqueYaml,
)
from scholar_workflow.workflows.register_paper import (
    _bytes,
    _hash,
    _identity,
    _provider_path,
    _read,
)

_LIMIT = 2 * 1024 * 1024
_MANIFEST = ".scholar-workflow/fields.yml"


def _selected(registry, source_id, field_id):
    declaration = _read_declaration(registry.path.parent, registry.path.name, _LIMIT)
    document = KnowledgeSourceRegistryDocument.model_validate(_json(declaration.content))
    source = next((row for row in document.sources if row.source_id == source_id), None)
    if source is None or not source.enabled or not {"read", "write"} <= set(source.capabilities):
        raise FieldRegistryError("Selected Source is not registered for reading and writing")
    folder = next(row for row in document.folders if row.folder_id == source.folder_id)
    if not folder.enabled or not {"read", "write"} <= set(folder.capabilities):
        raise FieldRegistryError("Selected folder does not permit reading and writing")
    root = folder.root
    binding = _root_identity(root)
    read = _read_declaration(root, _MANIFEST, _LIMIT)
    manifest = FieldManifest.model_validate(yaml.load(read.content, Loader=_UniqueYaml))
    if manifest.source_id != source_id:
        raise FieldRegistryError("Portable manifest belongs to another Source")
    field = next((row for row in manifest.fields if row.field_id == field_id), None)
    if field is None:
        raise FieldRegistryError("Select exactly one existing Field")
    return document, declaration, root, binding, read, manifest, field


def _after(before: bytes, field_id: str, operation: str, reference: dict, *, unchanged: bool) -> bytes:
    if unchanged:
        return before
    codec = YAML(typ="rt")
    codec.allow_duplicate_keys = False
    codec.preserve_quotes = True
    value = codec.load(before.decode("utf-8"))
    field = next(row for row in value["fields"] if row["field_id"] == field_id)
    if operation == "add":
        value["schema_version"] = 2
        field.setdefault("references", []).append(reference)
    else:
        rows = field["references"]
        index = next(i for i, row in enumerate(rows) if row["reference_id"] == reference["reference_id"])
        del rows[index]
        if not rows:
            del field["references"]
    FieldManifest.model_validate(value)
    output = io.StringIO()
    codec.dump(value, output)
    payload = output.getvalue().encode("utf-8")
    if len(payload) > _LIMIT:
        raise FieldRegistryError("Field manifest exceeds its size limit")
    return payload


def reference_plan(registry: KnowledgeSourceRegistry, *, source_id: str, field_id: str,
                   operation: str, reference_id: str, target_source_id: str | None = None,
                   object_id: str | None = None, purpose: str | None = None) -> dict:
    """Observe one explicit delta without writing locks, state or content."""
    try:
        return _reference_plan(registry, source_id=source_id, field_id=field_id, operation=operation,
                               reference_id=reference_id, target_source_id=target_source_id,
                               object_id=object_id, purpose=purpose)
    except FieldRegistryError:
        raise
    except (OSError, ValueError, TypeError, RecursionError, yaml.YAMLError) as exc:
        raise FieldRegistryError("Reference selection or registered declarations are invalid or unsafe") from exc


def _reference_plan(registry: KnowledgeSourceRegistry, *, source_id: str, field_id: str,
                    operation: str, reference_id: str, target_source_id: str | None,
                    object_id: str | None, purpose: str | None) -> dict:
    if operation not in {"add", "remove"}:
        raise FieldRegistryError("Reference operation must be add or remove")
    if operation == "remove" and any(value is not None for value in (target_source_id, object_id, purpose)):
        raise FieldRegistryError("Remove accepts only the selected reference identity")
    _, registry_read, root, binding, read, _, field = _selected(registry, source_id, field_id)
    existing = next((row for row in field.references if row.reference_id == reference_id), None)
    observation, resolution = {}, None
    if operation == "add":
        reference = FieldResourceReference.model_validate({
            "reference_id": reference_id, "target": {"source_id": target_source_id, "object_id": object_id},
            "purpose": purpose,
        })
        if existing is not None and existing != reference:
            raise FieldRegistryError("Reference identity already selects different content")
        if any(row.reference_id != reference_id and row.target == reference.target for row in field.references):
            raise FieldRegistryError("Qualified target already has a reference in this Field")
        results, available = _resolve_objects({reference.target.object_id}, registry.path, observation=observation)
        resolved = _qualified_result(reference, results, available)
        if resolved.status != "resolved" or any(
            row.file_state != "available" for row in [*resolved.locations, *resolved.owner_candidates]
        ):
            raise FieldRegistryError("Reference target has no unique, available registered owner")
        resolution = resolved.model_dump(mode="json")
    else:
        if existing is None:
            raise FieldRegistryError("Reference identity does not exist in the selected Field")
        reference = existing
    before = read.content
    after = _after(before, field_id, operation, reference.model_dump(mode="json"),
                   unchanged=operation == "add" and existing is not None)
    current = _selected(registry, source_id, field_id)
    if (current[1] != registry_read or current[3] != binding or current[4] != read
            or _root_identity(root) != binding):
        raise FieldRegistryError("Reference authority changed during planning")
    plan = {"schema_version": 1, "source_id": source_id, "field_id": field_id,
            "field_title": field.title, "operation": operation,
            "reference": reference.model_dump(mode="json"), "resolution": resolution,
            "root": str(root), "root_identity": list(binding),
            "registry_identity": list(registry_read.identity), "registry_hash": _hash(registry_read.content),
            "manifest_identity": list(read.identity), "manifest_before": before.decode("utf-8"),
            "manifest_after": after.decode("utf-8"), "ownership_read_set": observation,
            "status": "unchanged" if before == after else "ready"}
    plan["approved_digest"] = _hash(_bytes(plan)).removeprefix("sha256:")
    return plan


def _check_inputs(registry: KnowledgeSourceRegistry, plan: dict) -> None:
    """Recheck the exact declarations and metadata immediately before publication."""
    try:
        current = _read_declaration(registry.path.parent, registry.path.name, _LIMIT)
        if (list(current.identity) != plan["registry_identity"]
                or _hash(current.content) != plan["registry_hash"]):
            raise FieldRegistryError("Reference registry changed before publication")
        observed = plan["ownership_read_set"]
        for row in observed.get("declarations", []):
            current = _read_declaration(Path(row["root"]), row["relative_path"], row["limit"])
            if list(current.identity) != row["identity"] or _hash(current.content) != row["hash"]:
                raise FieldRegistryError("Reference ownership declaration changed before publication")
        roots = {row["source_id"]: Path(row["root"]) for row in observed.get("roots", [])}
        for row in observed.get("roots", []):
            if list(_root_identity(Path(row["root"]))) != row["identity"]:
                raise FieldRegistryError("Reference owner directory changed before publication")
        for row in observed.get("providers", []):
            if list(_root_identity(_provider_path(registry, row["source_id"]))) != row["identity"]:
                raise FieldRegistryError("Reference provider directory changed before publication")
        for row in observed.get("files", []):
            state, identity = _file_observation(roots[row["source_id"]], row["relative_path"])
            if state != row["state"] or (list(identity) if identity else None) != row["identity"]:
                raise FieldRegistryError("Reference target or primary file changed before publication")
    except FieldRegistryError:
        raise
    except (OSError, ValueError) as exc:
        raise FieldRegistryError("Reference approval read set is no longer available or safe") from exc


def _publish_manifest(fd: int, before: bytes, after: bytes, expected_identity: tuple[int, ...],
                      check_bindings, check_inputs) -> None:
    """Keep every CAS read bounded/nonblocking and tied to the approved leaf inode."""
    def check_leaf():
        check_bindings()
        check_inputs()
        content, identity = _read(fd, "fields.yml")
        if content != before or identity != expected_identity or len(content) > _LIMIT:
            raise FieldRegistryError("Field manifest identity or bytes changed before publication")

    check_leaf()
    if before == after:
        os.fsync(fd)
        check_bindings()
        return
    temporary = ".field-reference-" + secrets.token_hex(12) + ".tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=fd)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        check_leaf()
        os.replace(temporary, "fields.yml", src_dir_fd=fd, dst_dir_fd=fd)
        check_bindings()
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


def change_reference(registry: KnowledgeSourceRegistry, *, approved_digest: str, **selection) -> dict:
    """Re-observe approval under existing locks and publish one complete manifest."""
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("Approved digest must be SHA-256 hex")
    initial = reference_plan(registry, **selection)
    if initial["approved_digest"] != approved_digest:
        raise FieldRegistryError("Reference plan changed; review a fresh plan")
    with registry._write_guard() as registry_fd, ExitStack() as stack:
        document, _, root, binding, _, _, _ = _selected(registry, selection["source_id"], selection["field_id"])
        providers = []
        if selection["operation"] == "add":
            for source in sorted(document.sources, key=lambda row: row.source_id):
                path = _provider_path(registry, source.source_id)
                descriptor = _open_checked_chain(path)
                os.close(descriptor)
                providers.append(stack.enter_context(_locked_state_root(path)))
        root_fd = _open_checked_chain(root)
        stack.callback(os.close, root_fd)
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        stack.callback(fcntl.flock, root_fd, fcntl.LOCK_UN)
        state_fd = _open_checked_chain(root, (".scholar-workflow",))
        stack.callback(os.close, state_fd)
        state_binding = _identity(os.fstat(state_fd))[:2]

        def check_bindings():
            if (_root_identity(registry.path.parent) != _identity(os.fstat(registry_fd))[:2]
                    or _root_identity(root) != binding
                    or _identity(os.fstat(root_fd))[:2] != binding):
                raise FieldRegistryError("Reference directory binding changed during publication")
            descriptor = _open_checked_chain(root, (".scholar-workflow",))
            try:
                if _identity(os.fstat(descriptor))[:2] != state_binding:
                    raise FieldRegistryError("Field state directory changed during publication")
            finally:
                os.close(descriptor)
            for provider in providers:
                provider.ensure_current()

        check_bindings()
        plan = reference_plan(registry, **selection)
        if plan != initial:
            raise FieldRegistryError("Reference plan changed under the write lock; review a fresh plan")
        before, after = plan["manifest_before"].encode(), plan["manifest_after"].encode()
        try:
            check_bindings()
            _publish_manifest(state_fd, before, after, tuple(plan["manifest_identity"]), check_bindings,
                              lambda: _check_inputs(registry, plan))
            check_bindings()
            if _read(state_fd, "fields.yml")[0] != after:
                raise FieldRegistryError("Field reference manifest changed after publication")
            # Also confirms durability for a fresh unchanged plan after an uncertain write.
            os.fsync(state_fd)
            check_bindings()
        except (OSError, RuntimeError, ValueError) as exc:
            try:
                check_bindings()
                actual = _read(state_fd, "fields.yml")[0]
            except (OSError, RuntimeError, ValueError):
                actual = None
            if actual != before or before == after:
                raise FieldRegistryCommitUncertain(
                    "Field reference publication outcome or durability is uncertain; inspect a fresh "
                    "reference-plan before retrying. Do not roll back or reuse the old digest."
                ) from exc
            raise
        return {"schema_version": 1, "status": "unchanged" if before == after else "applied",
                "source_id": plan["source_id"], "field_id": plan["field_id"],
                "operation": plan["operation"], "reference": plan["reference"],
                "manifest_hash": _hash(after), "approved_digest": approved_digest,
                "content_rewritten": False, "human_verified": False, "backup_verified": False}


def reference_plan_markdown(plan: dict, *, language: str) -> str:
    zh = language == "zh"
    lines = ["# 领域引用变更预览" if zh else "# Field reference change preview", "",
             f"## {_text(plan['field_title'])}", "",
             ("操作：新增引用" if plan["operation"] == "add" else "操作：移除引用") if zh else
             ("Action: Add reference" if plan["operation"] == "add" else "Action: Remove reference"), "",
             ("引用名称：" if zh else "Reference name: ") + _text(plan["reference"]["reference_id"]), "",
             ("用途：" if zh else "Purpose: ") + _text(plan["reference"]["purpose"]), ""]
    if plan["resolution"] is not None:
        row = plan["resolution"]["locations"][0]
        lines += [("所属领域：" if zh else "Owning Field: ") + _text(row["field_title"]),
                  ("资料文件：" if zh else "Resource file: ") + _text(row["relative_path"]), ""]
    lines += [("状态：无需改变" if zh else "Status: Unchanged") if plan["status"] == "unchanged" else
              ("状态：待确认" if zh else "Status: Ready for confirmation"), "",
              ("只修改引用方清单；原文、解析树及目标归属不变，不复制或删除资料。" if zh else
               "Only the referencing manifest changes; source content, Canvas and target ownership "
               "remain unchanged. No resource is copied or deleted."), "",
              "## 确认摘要" if zh else "## Confirmation digest", "", f"`{plan['approved_digest']}`", "",
              "尚未写入。" if zh else "Nothing has been written.", ""]
    return "\n".join(lines)
