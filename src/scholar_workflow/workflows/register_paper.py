"""One explicit paper owner registration, independent of the historical Hub.

The existing provider owns the inventory. This module coordinates three CAS
members; its journal is recovery state, not another knowledge catalog.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

from scholar_workflow.analysis.apply_changes import (
    _SNAPSHOT_NAME,
    KnowledgeApplyReceipt,
    KnowledgeApplySafetyError,
    KnowledgeProviderSnapshot,
    _atomic_create,
    _atomic_replace_if_unchanged,
    _hash_payload,
    _locked_state_root,
    _vault_binding_for_root,
)
from scholar_workflow.knowledge.catalog_models import HubCatalog, HubResource, ZoteroLink
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
    _open_directory_chain,
)
from scholar_workflow.knowledge.models import KnowledgeAtomicResource
from scholar_workflow.knowledge.presentation import _text
from scholar_workflow.models import ResourceKind
from scholar_workflow.workflows.knowledge_ownership import (
    _json,
    _placements,
    _read_declaration,
    _root_identity,
    _UniqueYaml,
)

_SNAPSHOT = _SNAPSHOT_NAME
_LIMIT = 16 * 1024 * 1024
_KEY = re.compile(r"[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}\Z")
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,95}\Z")
_PAPER_ID = re.compile(r"paper:zotero:([1-9][0-9]*):([23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})\Z")


def _bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise FieldRegistryError("Registration journal contains duplicate JSON keys")
        result[key] = value
    return result


def _result(plan: dict, snapshot: KnowledgeProviderSnapshot, receipt_id: str) -> dict:
    return {"schema_version": 1, "status": "registered", "source_id": plan["source_id"],
            "field_id": plan["field_id"], "resource_id": plan["resource_id"],
            "owner_path": plan["owner_path"], "approved_digest": plan["approved_digest"],
            "snapshot_revision": snapshot.snapshot_revision,
            "catalog_revision": snapshot.catalog.revision, "receipt_id": receipt_id,
            "analysis_committed": {a.kind for a in snapshot.artifacts
                                   if a.resource_id == plan["resource_id"]} ==
                                  {"analysis_markdown", "analysis_canvas", "analysis_sidecar"},
            "backup_verified": False}


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read(fd: int, name: str) -> tuple[bytes | None, tuple[int, ...] | None]:
    try:
        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None, None
    try:
        before = os.fstat(child)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _LIMIT:
            raise FieldRegistryError("Registration member must be a bounded regular file")
        with os.fdopen(child, "rb", closefd=False) as stream:
            content = stream.read(_LIMIT + 1)
        named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if len(content) > _LIMIT or _identity(before) != _identity(os.fstat(child)) or (
            _identity(before) != _identity(named)
        ):
            raise FieldRegistryError("Registration member changed during read")
        return content, _identity(before)
    finally:
        os.close(child)


def _put(fd: int, name: str, before: bytes | None, after: bytes) -> None:
    current, identity = _read(fd, name)
    if current == after:
        return
    if current != before:
        raise FieldRegistryError("Registration member changed; refusing to overwrite")
    if before is None:
        _atomic_create(fd, name, after)
    else:
        assert identity is not None
        _atomic_replace_if_unchanged(fd, name, after, expected_bytes=before,
                                     expected_identity=identity)


def _paper(zotero, item_key: str, attachment_key: str) -> dict:
    if not _KEY.fullmatch(item_key) or not _KEY.fullmatch(attachment_key):
        raise FieldRegistryError("Invalid explicit Zotero item or attachment key")
    item = zotero.get_item(item_key)
    attachment = zotero.get_item(attachment_key)
    data, child = item.get("data", {}), attachment.get("data", {})
    library = item.get("library", {})
    library_id = str(library.get("id", ""))
    title = data.get("title")
    if (
        item.get("key") != item_key or attachment.get("key") != attachment_key
        or data.get("itemType") in {None, "attachment", "note", "annotation"}
        or not isinstance(title, str) or not title.strip() or len(title) > 1000
        or any(ord(c) < 32 for c in title)
        or re.fullmatch(r"[1-9][0-9]*", library_id) is None
        or str(attachment.get("library", {}).get("id", "")) != library_id
        or child.get("parentItem") != item_key or child.get("contentType") != "application/pdf"
        or child.get("linkMode") not in {0, "imported_file"}
    ):
        raise FieldRegistryError("Paper and imported PDF identity could not be verified")
    locator = zotero.resolve_attachment_locator(attachment_key)
    if locator.attachment_key != attachment_key or locator.library_id != library_id:
        raise FieldRegistryError("Local attachment locator identity changed")
    path = locator.path
    if not path.is_absolute() or path.is_symlink():
        raise FieldRegistryError("Local PDF must be an absolute regular file")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not before.st_size:
            raise FieldRegistryError("Local PDF is unavailable")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if _identity(before) != _identity(os.fstat(descriptor)) or (
            _identity(before) != _identity(os.stat(path, follow_symlinks=False))
        ):
            raise FieldRegistryError("Local PDF changed during registration verification")
    finally:
        os.close(descriptor)
    return {"title": title, "item_key": item_key, "attachment_key": attachment_key,
            "library_id": library_id, "library_type": library.get("type"),
            "pdf_hash": "sha256:" + digest.hexdigest()}


def _location(registry: KnowledgeSourceRegistry, source_id: str, field_id: str):
    root = registry.resolve(source_id, capability="write")
    binding = _vault_binding_for_root(root)
    manifest = FieldService._load_manifest(root)
    if manifest.source_id != source_id:
        raise FieldRegistryError("Registered Source differs from portable manifest")
    fields = [f for f in manifest.fields if f.field_id == field_id]
    if len(fields) != 1:
        raise FieldRegistryError("Select exactly one Field in the registered Source")
    FieldService._validate_manifest_paths(root, manifest)
    return root, binding, manifest, fields[0]


def _provider_path(registry: KnowledgeSourceRegistry, source_id: str) -> Path:
    return registry.path.parent / "knowledge-providers" / source_id


def _assert_unused_paper(snapshot: KnowledgeProviderSnapshot, paper: dict, *,
                         existing_owner_id: str | None = None) -> None:
    """Compare explicit identities, never a title or an unqualified item key."""
    for resource in snapshot.catalog.resources:
        identity = _PAPER_ID.fullmatch(resource.resource_id)
        if resource.kind != ResourceKind.PAPER:
            if identity is not None:
                raise FieldRegistryError("Registered paper identity has a conflicting resource kind")
            continue
        key = resource.zotero.item_key
        if key is None or (identity is not None and identity[2] != key):
            raise FieldRegistryError("Registered paper identity cannot be verified")
        if key != paper["item_key"]:
            continue
        if identity is None:
            raise FieldRegistryError("Registered paper library identity cannot be verified")
        if identity[1] == paper["library_id"]:
            if resource.resource_id == existing_owner_id:
                continue
            raise FieldRegistryError("Paper already has a registered Knowledge owner; do not create a duplicate")


def _registered_sources(registry: KnowledgeSourceRegistry) -> KnowledgeSourceRegistryDocument:
    declaration = _read_declaration(registry.path.parent, registry.path.name, 2 * 1024 * 1024)
    return KnowledgeSourceRegistryDocument.model_validate(_json(declaration.content))


def _ownership_read_set(registry: KnowledgeSourceRegistry, source_id: str, paper: dict) -> list[dict]:
    """Read only explicit outside-Source declarations, binding absence as unknown."""
    try:
        document = _registered_sources(registry)
    except (OSError, ValueError, RecursionError, FieldRegistryError) as exc:
        raise FieldRegistryError("Registered paper ownership cannot be verified: registry unavailable") from exc
    result = []
    for source in sorted(document.sources, key=lambda row: row.source_id):
        if source.source_id == source_id:
            continue
        try:
            root = registry.resolve(source.source_id, capability="read")
            root_identity = _root_identity(root)
            field_read = _read_declaration(root, ".scholar-workflow/fields.yml", 2 * 1024 * 1024)
            manifest = FieldManifest.model_validate(yaml.load(field_read.content, Loader=_UniqueYaml))
            if manifest.source_id != source.source_id:
                raise ValueError("Field manifest differs from the registered Source")
            provider_path = _provider_path(registry, source.source_id)
            provider_identity = _root_identity(provider_path)
            provider_read = _read_declaration(provider_path, _SNAPSHOT, _LIMIT)
            snapshot = KnowledgeProviderSnapshot.model_validate(_json(provider_read.content))
            binding = snapshot.vault_binding
            if binding is None or (binding.root_path, binding.device, binding.inode) != (
                str(root), *root_identity,
            ):
                raise ValueError("Provider binding differs from the registered Source")
            _placements(source.source_id, manifest, snapshot)
            if (_root_identity(root) != root_identity
                    or _root_identity(provider_path) != provider_identity):
                raise ValueError("Registered Source declaration directory changed")
            _assert_unused_paper(snapshot, paper)
            result.append({"source_id": source.source_id, "folder_id": source.folder_id,
                           "root_binding": binding.model_dump(mode="json"),
                           "provider_binding": list(provider_identity),
                           "fields_identity": list(field_read.identity),
                           "provider_identity": list(provider_read.identity),
                           "fields_hash": _hash(field_read.content),
                           "provider_hash": _hash(provider_read.content)})
        except FieldRegistryError:
            raise
        except (OSError, ValueError, KeyError, RecursionError, KnowledgeApplySafetyError,
                yaml.YAMLError) as exc:
            raise FieldRegistryError(
                f"Registered paper ownership cannot be verified for Source {source.source_id}"
            ) from exc
    return result


def _check_ownership_read_set(registry: KnowledgeSourceRegistry, plan: dict) -> None:
    try:
        current = _ownership_read_set(registry, plan["source_id"], plan["paper"])
        if (plan.get("ownership_read_set", []) != current
                or plan["registry_hash"] != registry.revision()):
            raise FieldRegistryError("Ownership read set differs from the approved plan")
    except (OSError, ValueError, FieldRegistryError) as exc:
        raise FieldRegistryError("Registration ownership declarations changed; review a new plan") from exc


@contextmanager
def _locked_registered_providers(registry: KnowledgeSourceRegistry, source_id: str):
    """Serialize registered provider writers in a stable order, after the registry lock."""
    document = _registered_sources(registry)
    with ExitStack() as stack:
        selected = None
        for source in sorted(document.sources, key=lambda row: row.source_id):
            path = _provider_path(registry, source.source_id)
            if source.source_id != source_id:
                try:
                    descriptor = _open_directory_chain(path)
                except OSError as exc:
                    raise FieldRegistryError("Registered paper ownership cannot be verified") from exc
                else:
                    os.close(descriptor)
            state = stack.enter_context(_locked_state_root(path))
            if source.source_id == source_id:
                selected = state
        if selected is None:
            raise FieldRegistryError("Selected Source is no longer registered")
        yield selected


def _note(paper: dict, language: str) -> str:
    title = _text(paper["title"])
    if paper["library_type"] != "user":
        library = "groups/" + paper["library_id"]
    else:
        library = "library"
    link = f"zotero://open-pdf/{library}/items/{paper['attachment_key']}?page=1"
    return (
        f"# {title}\n\n"
        + (f"[在 Zotero 打开原 PDF]({link})\n\n"
           "论文与附件身份已经 Zotero Local API 核验；PDF 仍由 Zotero 管理。\n\n"
           "## 分析与笔记\n\n分析与附属笔记保存在本论文文件夹；完成状态以各产物的验收记录为准。"
           "资料登记不代表全文分析或科学验收完成。\n"
           if language == "zh" else
           f"[Open original PDF in Zotero]({link})\n\n"
           "Paper and attachment identity were verified through the Zotero Local API. "
           "Zotero retains the PDF.\n\n## Analysis and notes\n\n"
           "Analysis and supporting notes belong in this paper folder. Their receipts record "
           "completion independently. Registration is not scientific acceptance.\n")
    )


def paper_plan(registry: KnowledgeSourceRegistry, zotero, *, source_id: str,
               field_id: str, item_key: str, attachment_key: str,
               segment: str, language: str) -> dict:
    """Zero-write proposal for a new paper folder; never adopt an existing one."""
    if not _SEGMENT.fullmatch(segment) or language not in {"en", "zh"}:
        raise FieldRegistryError("Select a clean paper segment and supported language")
    root, binding, manifest, field = _location(registry, source_id, field_id)
    paper = _paper(zotero, item_key, attachment_key)
    registry_hash = registry.revision()
    owner_relative = f"resources/papers/{segment}/Paper.md"
    owner_path = (PurePosixPath(field.relative_root) / owner_relative).as_posix()
    # Directory absence is checked without following even a dangling symlink.
    current = root
    for component in PurePosixPath(owner_path).parts[:-1]:
        current = current / component
        if current.is_symlink():
            raise FieldRegistryError("Paper directory crosses a symbolic link")
        if os.path.lexists(current) and not current.is_dir():
            raise FieldRegistryError("Paper directory is not a directory")
    if os.path.lexists(root / PurePosixPath(owner_path).parent):
        raise FieldRegistryError("Paper folder already exists; registration never adopts or overwrites it")
    provider_path = _provider_path(registry, source_id)
    provider_before = None
    if os.path.lexists(provider_path):
        fd = _open_directory_chain(provider_path)
        try:
            provider_before, _ = _read(fd, _SNAPSHOT)
        finally:
            os.close(fd)
    if provider_before is None:
        raise FieldRegistryError("Source inventory is missing; restore it, never infer an empty library")
    before = KnowledgeProviderSnapshot.model_validate_json(provider_before)
    if before.vault_binding != binding:
        raise FieldRegistryError("Existing provider belongs to a different Source root")
    resource_id = f"paper:zotero:{paper['library_id']}:{item_key}"
    _assert_unused_paper(before, paper)
    ownership_read_set = _ownership_read_set(registry, source_id, paper)
    after_manifest = manifest.model_dump(mode="json")
    selected = next(f for f in after_manifest["fields"] if f["field_id"] == field_id)
    selected["navigation"].append({"label": paper["title"][:120], "items": [owner_relative]})
    fields_after = yaml.safe_dump(FieldManifest.model_validate(after_manifest).model_dump(mode="json"),
                                  allow_unicode=True, sort_keys=False)
    state_fd = _open_directory_chain(root, (".scholar-workflow",))
    try:
        fields_before, _ = _read(state_fd, "fields.yml")
    finally:
        os.close(state_fd)
    assert fields_before is not None
    if FieldManifest.model_validate(yaml.safe_load(fields_before)) != manifest or (
        registry.revision() != registry_hash or _vault_binding_for_root(root) != binding
    ):
        raise FieldRegistryError("Registration authority changed during planning")
    payload = {"schema_version": 1, "source_id": source_id, "field_id": field_id,
               "root_binding": binding.model_dump(mode="json"), "registry_hash": registry_hash,
               "ownership_read_set": ownership_read_set,
               "paper": paper, "resource_id": resource_id, "segment": segment, "language": language,
               "owner_path": owner_path, "note": _note(paper, language),
               "fields_before": fields_before.decode(), "fields_after": fields_after,
               "provider_before": provider_before.decode() if provider_before else None,
               "before_snapshot": before.model_dump(mode="json")}
    _check_ownership_read_set(registry, payload)
    payload["approved_digest"] = _hash(_bytes(payload)).removeprefix("sha256:")
    return payload


@contextmanager
def _directories(root: Path, parts: tuple[str, ...]):
    descriptors = [_open_directory_chain(root)]
    bindings = []
    try:
        for part in parts:
            try:
                os.mkdir(part, 0o700, dir_fd=descriptors[-1])
                os.fsync(descriptors[-1])
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptors[-1])
            descriptors.append(child)
            bindings.append(part)

        def check():
            for index, part in enumerate(bindings):
                opened = os.fstat(descriptors[index + 1])
                named = os.stat(part, dir_fd=descriptors[index], follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or _identity(opened)[:2] != _identity(named)[:2]:
                    raise FieldRegistryError("Registration directory changed during write")
        check()
        yield descriptors[-1], check
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def register_paper(registry: KnowledgeSourceRegistry, zotero, *, approved_digest: str,
                   fault_inject=None, **selection) -> dict:
    """Publish or conditionally resume the exact reviewed three-member transaction.

    Completed journals do not imply completed analysis. No rollback ever overwrites
    a concurrent human edit; conflicts retain the journal and stop before further writes.
    """
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("Approved digest must be SHA-256 hex")
    journal_name = f"paper-registration-{approved_digest}.json"
    with registry._write_guard():
        root, binding, _, field = _location(registry, selection["source_id"], selection["field_id"])
        with _directories(registry.path.parent,
                          ("knowledge-providers", selection["source_id"])) as (_, check_state), (
            _locked_registered_providers(registry, selection["source_id"])
        ) as provider:
            journal_bytes, _ = _read(provider.fd, journal_name)
            if journal_bytes is None:
                plan = paper_plan(registry, zotero, **selection)
                if plan["approved_digest"] != approved_digest:
                    raise FieldRegistryError("Paper registration plan changed; review a new plan")
                journal = {"status": "prepared", "plan": plan,
                           "applied_at": datetime.now(UTC).isoformat()}
                _atomic_create(provider.fd, journal_name, _bytes(journal))
            else:
                journal = json.loads(journal_bytes, object_pairs_hook=_pairs)
                if not isinstance(journal, dict) or set(journal) != {"status", "plan", "applied_at"} or (
                    journal["status"] not in ("prepared", "committed")
                ):
                    raise FieldRegistryError("Invalid registration journal envelope")
                plan = journal["plan"]
                if not isinstance(plan, dict) or not isinstance(plan.get("approved_digest"), str):
                    raise FieldRegistryError("Invalid registration journal plan")
                digest_payload = {k: v for k, v in plan.items() if k != "approved_digest"}
                if _hash(_bytes(digest_payload)).removeprefix("sha256:") != approved_digest or (
                    plan["approved_digest"] != approved_digest
                ):
                    raise FieldRegistryError("Registration journal digest is invalid")
            for name in ("source_id", "field_id", "segment", "language"):
                if plan[name] != selection[name]:
                    raise FieldRegistryError("Registration journal belongs to another selection")
            expected_owner = (PurePosixPath(field.relative_root) / "resources" / "papers"
                              / selection["segment"] / "Paper.md").as_posix()
            if expected_owner != plan["owner_path"]:
                raise FieldRegistryError("Registered Field no longer owns the selected paper folder")
            if (plan["paper"]["item_key"] != selection["item_key"] or
                plan["paper"]["attachment_key"] != selection["attachment_key"] or
                plan["root_binding"] != binding.model_dump(mode="json") or
                plan["registry_hash"] != registry.revision() or
                plan["paper"] != _paper(zotero, selection["item_key"], selection["attachment_key"])):
                raise FieldRegistryError("Registration authority or source changed; refusing recovery")
            _check_ownership_read_set(registry, plan)
            if journal["status"] == "committed":
                value, _ = _read(provider.fd, _SNAPSHOT)
                if value is None:
                    raise FieldRegistryError("Committed provider snapshot is missing")
                current_snapshot = KnowledgeProviderSnapshot.model_validate_json(value)
                owner_row = next((r for r in current_snapshot.manifest.atomic_resources
                                  if r.resource_id == plan["resource_id"]), None)
                source_receipt = f"paper-register:{approved_digest}"
                prior = next((r for r in current_snapshot.receipts
                              if getattr(r, "source_receipt", None) == source_receipt), None)
                projected = next((r for r in current_snapshot.catalog.resources
                                  if r.resource_id == plan["resource_id"]), None)
                relative_owner = f"resources/papers/{selection['segment']}/Paper.md"
                if (owner_row is None or owner_row.markdown_path != plan["owner_path"]
                    or prior is None or current_snapshot.vault_binding != binding
                    or projected is None or projected.zotero.item_key != selection["item_key"]
                    or projected.zotero.attachment_key != selection["attachment_key"]
                    or not any(relative_owner in group.items for group in field.navigation)):
                    raise FieldRegistryError("Committed paper ownership changed")
                _assert_unused_paper(current_snapshot, plan["paper"],
                                     existing_owner_id=plan["resource_id"])
                return _result(plan, current_snapshot, prior.receipt_id)
            before = KnowledgeProviderSnapshot.model_validate(plan["before_snapshot"])
            catalog_data = before.catalog.model_dump(mode="json")
            catalog_data["revision"] = ""
            catalog_data["resources"].append(HubResource(
                resource_id=plan["resource_id"], kind=ResourceKind.PAPER,
                zotero=ZoteroLink(item_key=selection["item_key"],
                                  attachment_key=selection["attachment_key"]),
            ).model_dump(mode="json"))
            catalog = HubCatalog.model_validate(catalog_data)
            semantic = {"change_id": f"change:{approved_digest}",
                        "change_fingerprint": f"sha256:{approved_digest}",
                        "source_receipt": f"paper-register:{approved_digest}",
                        "before_catalog_revision": before.catalog.revision,
                        "after_catalog_revision": catalog.revision, "applied_artifact_ids": []}
            receipt = KnowledgeApplyReceipt(
                receipt_id="knowledge-apply:" + _hash_payload(semantic).removeprefix("sha256:"),
                applied_at=journal["applied_at"], **semantic,
            )
            inventory = before.manifest.model_dump(mode="json")
            inventory["atomic_resources"].append(KnowledgeAtomicResource(
                resource_id=plan["resource_id"], kind=ResourceKind.PAPER,
                title=plan["paper"]["title"], markdown_path=plan["owner_path"],
            ).model_dump(mode="json"))
            snapshot_data = before.model_dump(mode="json")
            snapshot_data.update(snapshot_revision="", manifest=inventory,
                                 catalog=catalog.model_dump(mode="json"),
                                 receipts=[r.model_dump(mode="json") for r in before.receipts]
                                 + [receipt.model_dump(mode="json")])
            after = KnowledgeProviderSnapshot.model_validate(snapshot_data)
            provider_after = _bytes(after.model_dump(mode="json"))
            expected_provider = (plan["provider_before"].encode()
                                 if plan["provider_before"] is not None else None)
            owner = PurePosixPath(plan["owner_path"])
            with _directories(root, owner.parts[:-1]) as (note_fd, check_note), (
                _directories(root, (".scholar-workflow",))
            ) as (fields_fd, check_fields):
                root_fd = _open_directory_chain(root)
                try:
                    fcntl.flock(root_fd, fcntl.LOCK_EX)
                    if _identity(os.fstat(root_fd))[:2] != (binding.device, binding.inode):
                        raise FieldRegistryError("Source directory binding changed")
                    # Check the complete read/write set before publishing another member.
                    members = [(note_fd, owner.name, None, plan["note"].encode()),
                               (fields_fd, "fields.yml", plan["fields_before"].encode(),
                                plan["fields_after"].encode()),
                               (provider.fd, _SNAPSHOT, expected_provider, provider_after)]
                    for fd, name, old, new in members:
                        value, _ = _read(fd, name)
                        if value not in (old, new):
                            raise FieldRegistryError("Registration conflict; journal retained for manual review")
                    for index, (fd, name, old, new) in enumerate(members):
                        check_state()
                        check_note()
                        check_fields()
                        provider.ensure_current()
                        if _vault_binding_for_root(root) != binding:
                            raise FieldRegistryError("Source root changed during publication")
                        _check_ownership_read_set(registry, plan)
                        _put(fd, name, old, new)
                        if fault_inject is not None:
                            fault_inject(f"member-{index + 1}")
                    check_state()
                    check_note()
                    check_fields()
                    for fd, name, _, new in members:
                        current_member, _ = _read(fd, name)
                        if current_member != new:
                            raise FieldRegistryError("Registration publication changed before completion")
                    _check_ownership_read_set(registry, plan)
                    journal["status"] = "committed"
                    current, _ = _read(provider.fd, journal_name)
                    _put(provider.fd, journal_name, current, _bytes(journal))
                finally:
                    fcntl.flock(root_fd, fcntl.LOCK_UN)
                    os.close(root_fd)
            return _result(plan, after, receipt.receipt_id)
