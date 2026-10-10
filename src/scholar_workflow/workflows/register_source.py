"""Recoverable first-Source creation, composing the existing three authorities.

Only a genuinely new Source can initialize an empty provider. The host journal is
recovery state, not an owner inventory or permission to recreate lost snapshots.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    _atomic_create,
    _locked_state_root,
    _vault_binding_for_root,
)
from scholar_workflow.knowledge.catalog_models import HubCatalog
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    FieldService,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.knowledge.models import KnowledgeManifest
from scholar_workflow.knowledge.registration import register, registration_plan
from scholar_workflow.workflows.knowledge_ownership import _json, _read_declaration, _root_identity
from scholar_workflow.workflows.register_paper import (
    _SNAPSHOT,
    _bytes,
    _directories,
    _hash,
    _put,
    _read,
)


def _digest(plan: dict) -> str:
    payload = {key: value for key, value in plan.items() if key != "approved_digest"}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _empty_provider(root: Path) -> KnowledgeProviderSnapshot:
    return KnowledgeProviderSnapshot(
        vault_binding=_vault_binding_for_root(root), manifest=KnowledgeManifest(),
        catalog=HubCatalog(generated_at=datetime(1970, 1, 1, tzinfo=UTC)),
    )


def _validate_creation_members(creation: dict, manifest: FieldManifest, root: Path) -> None:
    """A journal checksum cannot authorize unrelated publication payloads."""
    fields = yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    provider = _bytes(_empty_provider(root).model_dump(mode="json")).decode()
    if creation["fields_after"] != fields or creation["provider_after"] != provider:
        raise ValueError("Creation members differ from the approved manifest or empty inventory")
    before_text = creation["registry_before"]
    if before_text is not None and not isinstance(before_text, str):
        raise TypeError("Invalid registry before bytes")
    if ("absent" if before_text is None else _hash(before_text.encode())) != (
        creation["plan"]["registry_base_hash"]
    ):
        raise ValueError("Registry before bytes differ from the approved revision")
    before = (KnowledgeSourceRegistryDocument() if before_text is None else
              KnowledgeSourceRegistryDocument.model_validate(_json(before_text.encode())))
    if not isinstance(creation["registry_after"], str):
        raise TypeError("Invalid registry after bytes")
    after = KnowledgeSourceRegistryDocument.model_validate(_json(creation["registry_after"].encode()))
    selected = next((row for row in after.sources if row.source_id == manifest.source_id), None)
    if selected is None or any(row.source_id == manifest.source_id for row in before.sources):
        raise ValueError("Creation must add exactly the new Source")
    expected = before.model_copy(deep=True)
    folder = next((row for row in expected.folders if row.folder_id == selected.folder_id), None)
    if folder is None:
        expected.folders.append(FolderRegistration(
            folder_id=selected.folder_id, root=root, capabilities=["read", "write"],
        ))
    elif folder.root != root or not folder.enabled or not {"read", "write"}.issubset(folder.capabilities):
        raise ValueError("Creation registry folder differs from the approved root")
    expected.sources.append(KnowledgeSourceRegistration(
        source_id=manifest.source_id, folder_id=selected.folder_id, capabilities=["read", "write"],
    ))
    if after != expected:
        raise ValueError("Creation registry includes unapproved changes")


def _load_record(content: bytes, root: Path, field_root: str | None, approved_digest: str) -> dict:
    try:
        record = _json(content)
        if not isinstance(record, dict) or set(record) != {
            "schema_version", "status", "published_members", "creation", "fingerprint",
        } or record["schema_version"] != 1 or record["status"] not in {"prepared", "committed"}:
            raise ValueError("Invalid creation envelope")
        creation = record["creation"]
        if not isinstance(creation, dict) or set(creation) != {
            "plan", "manifest", "fields_after", "registry_before", "registry_after", "provider_after",
        } or record["fingerprint"] != _hash(_bytes(creation)):
            raise ValueError("Creation journal fingerprint changed")
        plan = creation["plan"]
        if not isinstance(plan, dict) or _digest(plan) != approved_digest or (
            plan["approved_digest"] != approved_digest or plan["root"] != str(root)
            or plan["mode"] != "single-field" or plan["source_id"] is not None
            or plan["existing_fields"] or plan["inventory_initialization"] != "new-empty-provider"
            or plan["status"] != "ready-for-confirmation" or len(plan["fields"]) != 1
            or plan["fields"][0]["relative_root"] != field_root
        ):
            raise ValueError("Creation journal differs from the approved selection")
        manifest = FieldManifest.model_validate(creation["manifest"])
        if [row.model_dump(mode="json", exclude={"field_id"}) for row in manifest.fields] != plan["fields"]:
            raise ValueError("Frozen Fields differ from the approved selection")
        if type(record["published_members"]) is not int or not 0 <= record["published_members"] <= 3:
            raise ValueError("Invalid publication progress")
        if record["status"] == "committed" and record["published_members"] != 3:
            raise ValueError("Incomplete committed creation")
        _validate_creation_members(creation, manifest, root)
        return record
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise FieldRegistryError("Source creation journal is invalid; retain it for review") from exc


def _prepare(service: FieldService, proposal, parent_fd: int) -> dict:
    """Freeze one already-validated preview without minting another set of IDs."""
    candidate = service.candidates.peek(proposal.candidate_token)
    root = service._validate_candidate(candidate)
    preview = candidate.preview
    if preview.existing_manifest or preview.registration_only:
        raise FieldRegistryError("Only a new Source may initialize an empty inventory")
    selected = next(row for row in preview.fields if row.field_id == proposal.selected_id)
    manifest = FieldManifest(source_id=preview.source_id, fields=[selected])
    service._validate_manifest_paths(root, manifest)
    registration = service._planned_registration(root, manifest, preview.folder_id)
    registry_before, _ = _read(parent_fd, service.registry.path.name)
    if service.registry._revision_at(parent_fd) != proposal.payload["registry_base_hash"]:
        raise FieldRegistryError("Source registry changed after preview")
    provider_path = service.registry.path.parent / "knowledge-providers" / manifest.source_id
    if os.path.lexists(provider_path):
        raise FieldRegistryError("New Source provider location already exists; refusing adoption")
    empty = _empty_provider(root)
    fields_after = yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    creation = {
        "plan": proposal.payload, "manifest": manifest.model_dump(mode="json"),
        "fields_after": fields_after,
        "registry_before": registry_before.decode() if registry_before is not None else None,
        "registry_after": registration.model_dump_json(indent=2) + "\n",
        "provider_after": _bytes(empty.model_dump(mode="json")).decode(),
    }
    return {"schema_version": 1, "status": "prepared", "published_members": 0,
            "creation": creation, "fingerprint": _hash(_bytes(creation))}


def register_source(service: FieldService, root: Path, *, field_root: str | None,
                    existing_source: bool, approved_digest: str, fault_inject=None) -> FieldManifest:
    """Create once or resume the exact approved Source/provider transaction."""
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("approved digest must be a SHA-256 hex value")
    root = service._trusted_root(root)
    registry = service.registry
    journal_name = f"source-registration-{approved_digest}.json"
    try:
        saved = _read_declaration(registry.path.parent, journal_name, 16 * 1024 * 1024).content
    except FileNotFoundError:
        saved = None
    if saved is None:
        proposal = registration_plan(service, root, field_root=field_root, existing_source=existing_source)
        if proposal.payload["approved_digest"] != approved_digest:
            raise FieldRegistryError("Registration plan changed; review a fresh plan before confirming")
        if proposal.payload["status"] != "ready-for-confirmation":
            raise FieldRegistryError("Registration is blocked; legacy content requires joint transaction review")
        if proposal.payload["inventory_initialization"] is None:
            return register(service, root, field_root=field_root, existing_source=existing_source,
                            approved_digest=approved_digest)
    else:
        if existing_source:
            raise FieldRegistryError("Source creation journal belongs to a new-Source request")
        _load_record(saved, root, field_root, approved_digest)

    with service._write_lock, registry._write_guard() as parent_fd:
        parent_identity = _root_identity(registry.path.parent)
        locked_parent = os.fstat(parent_fd)
        if parent_identity != (locked_parent.st_dev, locked_parent.st_ino):
            raise FieldRegistryError("Source registry directory differs from its locked binding")
        current, _ = _read(parent_fd, journal_name)
        if current is None:
            if saved is not None:
                raise FieldRegistryError("Source creation journal disappeared; refusing a new transaction")
            record = _prepare(service, proposal, parent_fd)
            current = _bytes(record)
            _atomic_create(parent_fd, journal_name, current)
        else:
            record = _load_record(current, root, field_root, approved_digest)
        creation = record["creation"]
        plan = creation["plan"]
        manifest = FieldManifest.model_validate(creation["manifest"])
        provider_path = registry.path.parent / "knowledge-providers" / manifest.source_id
        if record["published_members"]:
            try:
                _root_identity(provider_path)
            except OSError as exc:
                raise FieldRegistryError("Initialized Source provider is missing; restore, never guess empty") from exc

        with _directories(registry.path.parent, ("knowledge-providers", manifest.source_id)) as (
            _, check_state,
        ), _locked_state_root(provider_path) as provider, _directories(root, (".scholar-workflow",)) as (
            fields_fd, check_fields,
        ):
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fcntl.flock(root_fd, fcntl.LOCK_EX)
                registry_before = (creation["registry_before"].encode()
                                   if creation["registry_before"] is not None else None)
                members = [
                    (provider.fd, _SNAPSHOT, None, creation["provider_after"].encode(), "provider-created"),
                    (fields_fd, "fields.yml", None, creation["fields_after"].encode(), "manifest-published"),
                    (parent_fd, registry.path.name, registry_before,
                     creation["registry_after"].encode(), "registry-published"),
                ]

                def check():
                    if _root_identity(registry.path.parent) != parent_identity:
                        raise FieldRegistryError("Source registry directory binding changed")
                    check_state()
                    check_fields()
                    provider.ensure_current()
                    if (
                        list(service._root_identity(root)) != plan["root_identity"]
                        or _root_identity(root) != (os.fstat(root_fd).st_dev, os.fstat(root_fd).st_ino)
                        or service._preview_content_hash(root) != plan["content_base_hash"]
                    ):
                        raise FieldRegistryError("Source creation authority or content changed")
                    if _read(parent_fd, journal_name)[0] != current:
                        raise FieldRegistryError("Source creation journal changed during publication")
                    for index, (fd, name, before, after, _) in enumerate(members):
                        value, _ = _read(fd, name)
                        if value not in (before, after) or (index < record["published_members"] and value != after):
                            raise FieldRegistryError("Source creation member changed; retain journal for review")

                check()
                if record["status"] == "committed":
                    return manifest
                for index, (fd, name, before, after, phase) in enumerate(members):
                    check()
                    _put(fd, name, before, after)
                    record["published_members"] = max(record["published_members"], index + 1)
                    updated = _bytes(record)
                    _put(parent_fd, journal_name, current, updated)
                    current = updated
                    if fault_inject is not None:
                        fault_inject(phase)
                check()
                record["status"] = "committed"
                _put(parent_fd, journal_name, current, _bytes(record))
                return manifest
            finally:
                fcntl.flock(root_fd, fcntl.LOCK_UN)
                os.close(root_fd)
