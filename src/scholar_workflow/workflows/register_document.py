"""Register one real Zotero Webpage and its exact, block-addressable source note.

Source.md is the atomic owner, not an invented paper or a second source artifact.
The existing Source/provider locks and bounded CAS primitives protect publication;
the local journal is recovery state, never another knowledge inventory.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import yaml

from scholar_workflow.analysis.apply_changes import (
    KnowledgeApplyReceipt,
    KnowledgeProviderSnapshot,
    _atomic_create,
    _hash_payload,
    _vault_binding_for_root,
)
from scholar_workflow.knowledge.catalog_models import HubCatalog, HubResource, ZoteroLink
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.models import KnowledgeAtomicResource
from scholar_workflow.knowledge.source_blocks import source_paragraphs
from scholar_workflow.models import Identifiers, ResourceKind
from scholar_workflow.workflows.knowledge_ownership import _read_declaration
from scholar_workflow.workflows.register_paper import (
    _KEY,
    _LIMIT,
    _SEGMENT,
    _SNAPSHOT,
    _assert_unused_paper,
    _bytes,
    _directories,
    _hash,
    _identity,
    _location,
    _locked_registered_providers,
    _ownership_read_set,
    _pairs,
    _provider_path,
    _put,
    _read,
    _result,
)

_DOCUMENT_ID = re.compile(
    r"document:zotero:([1-9][0-9]*):([23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})\Z"
)
def _webpage(zotero, item_key: str, source_url: str) -> dict:
    if not isinstance(source_url, str) or len(source_url) > 4096 or (
        any(ord(char) < 33 for char in source_url) or "\\" in source_url
    ):
        raise FieldRegistryError("Select a clean HTTPS source URL")
    try:
        url = urlsplit(source_url)
        if url.scheme != "https" or not url.hostname or url.username is not None or (
            url.password is not None or url.fragment
        ):
            raise ValueError("Invalid HTTPS URL")
        _ = url.port
    except ValueError as exc:
        raise FieldRegistryError("Select a clean HTTPS source URL") from exc
    if not isinstance(item_key, str) or not _KEY.fullmatch(item_key):
        raise FieldRegistryError("Invalid explicit Zotero Webpage key")
    item = zotero.get_item(item_key)
    data, library = item.get("data", {}), item.get("library", {})
    title, library_id = data.get("title"), str(library.get("id", ""))
    version = item.get("version")
    if (item.get("key") != item_key or data.get("itemType") not in {"webpage", "blogPost"}
            or data.get("url") != source_url or not isinstance(title, str)
            or not title.strip() or len(title) > 1000 or any(ord(char) < 32 for char in title)
            or re.fullmatch(r"[1-9][0-9]*", library_id) is None
            or library.get("type") not in {"user", "group"}
            or type(version) is not int or version < 0):
        raise FieldRegistryError("Zotero Webpage identity, version or source URL cannot be verified")
    return {"title": title, "item_key": item_key, "item_type": data["itemType"],
            "library_id": library_id, "library_type": library["type"],
            "version": version, "source_url": source_url}


def _source(markdown_path: Path, retrieved_at: str) -> dict:
    try:
        if not isinstance(retrieved_at, str) or len(retrieved_at) > 64:
            raise ValueError("Invalid retrieval time")
        timestamp = datetime.fromisoformat(retrieved_at)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Retrieval time must include a timezone")
        path = Path(markdown_path)
        if not path.is_absolute() or path.suffix.lower() != ".md":
            raise ValueError("Source input must be an absolute Markdown file")
        declaration = _read_declaration(path.parent, path.name, _LIMIT)
        text = declaration.content.decode("utf-8")
        if "\x00" in text or not text.strip():
            raise ValueError("Source input must be nonblank UTF-8 Markdown")
        blocks = list(source_paragraphs(text))
        if not blocks or len(blocks) != len(set(blocks)):
            raise ValueError("Source input requires unique explicit block anchors")
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise FieldRegistryError("Source input must be stable UTF-8 Markdown with unique blocks and a timezone") from exc
    return {"input_path": str(path), "input_identity": list(declaration.identity),
            "markdown_sha256": _hash(declaration.content), "markdown": text,
            "retrieved_at": retrieved_at, "block_ids": blocks}


def _assert_unused_document(snapshot: KnowledgeProviderSnapshot, document: dict, *,
                            existing_owner_id: str | None = None) -> None:
    _assert_unused_paper(snapshot, document, existing_owner_id=existing_owner_id)
    for resource in snapshot.catalog.resources:
        identity = _DOCUMENT_ID.fullmatch(resource.resource_id)
        if identity is not None and (resource.kind not in {
            ResourceKind.TECHNICAL_DOCUMENT, ResourceKind.BLOG_POST,
        } or resource.zotero.item_key != identity[2]):
            raise FieldRegistryError("Registered document identity has conflicting ownership")
        if resource.zotero.item_key != document["item_key"] or resource.kind is ResourceKind.PAPER:
            continue
        if identity is None:
            raise FieldRegistryError("Registered document library identity cannot be verified")
        if identity[1] == document["library_id"] and resource.resource_id != existing_owner_id:
            raise FieldRegistryError("Document already has a registered Knowledge owner")


def _document_read_set(registry: KnowledgeSourceRegistry, source_id: str, document: dict) -> list[dict]:
    # Reuse the established complete registered-provider read set and paper check,
    # then additionally check the document namespace against those same exact bytes.
    result = _ownership_read_set(registry, source_id, document)
    for row in result:
        declaration = _read_declaration(_provider_path(registry, row["source_id"]), _SNAPSHOT, _LIMIT)
        if _hash(declaration.content) != row["provider_hash"] or (
            list(declaration.identity) != row["provider_identity"]
        ):
            raise FieldRegistryError("Document ownership declarations changed during read")
        _assert_unused_document(KnowledgeProviderSnapshot.model_validate_json(declaration.content), document)
    return result


def _check_authority(registry, zotero, plan, selection, binding) -> None:
    for name in ("source_id", "field_id", "item_key", "segment", "language", "source_url", "retrieved_at"):
        if plan[name] != selection[name]:
            raise FieldRegistryError("Document journal belongs to another selection")
    if (plan["root_binding"] != binding.model_dump(mode="json")
            or plan["registry_hash"] != registry.revision()
            or plan["document"] != _webpage(zotero, selection["item_key"], selection["source_url"])
            or plan["source"] != _source(selection["markdown_path"], selection["retrieved_at"])
            or plan["ownership_read_set"] != _document_read_set(registry, plan["source_id"], plan["document"])):
        raise FieldRegistryError("Document registration authority or source changed; refusing recovery")


def document_plan(registry: KnowledgeSourceRegistry, zotero, *, source_id: str,
                  field_id: str, item_key: str, segment: str, language: str,
                  markdown_path: Path, source_url: str, retrieved_at: str) -> dict:
    """Preview exactly one new non-paper owner; no writes or implicit discovery."""
    if not _SEGMENT.fullmatch(segment) or language not in {"en", "zh"}:
        raise FieldRegistryError("Select a clean document segment and supported language")
    root, binding, manifest, field = _location(registry, source_id, field_id)
    document, source = _webpage(zotero, item_key, source_url), _source(markdown_path, retrieved_at)
    owner_relative = f"resources/{segment}/Source.md"
    owner_path = (PurePosixPath(field.relative_root) / owner_relative).as_posix()
    current = root
    for part in PurePosixPath(owner_path).parts[:-1]:
        current = current / part
        if current.is_symlink() or (os.path.lexists(current) and not current.is_dir()):
            raise FieldRegistryError("Document folder crosses an unsafe directory")
    if os.path.lexists(root / PurePosixPath(owner_path).parent):
        raise FieldRegistryError("Document folder already exists; registration never adopts or overwrites")
    provider = _read_declaration(_provider_path(registry, source_id), _SNAPSHOT, _LIMIT)
    before = KnowledgeProviderSnapshot.model_validate_json(provider.content)
    if before.vault_binding != binding:
        raise FieldRegistryError("Existing provider belongs to a different Source root")
    _assert_unused_document(before, document)
    fields = _read_declaration(root, ".scholar-workflow/fields.yml", 2 * 1024 * 1024)
    if FieldManifest.model_validate(yaml.safe_load(fields.content)) != manifest:
        raise FieldRegistryError("Field declaration changed during planning")
    updated = manifest.model_dump(mode="json")
    next(row for row in updated["fields"] if row["field_id"] == field_id)["navigation"].append(
        {"label": document["title"][:120], "items": [owner_relative]})
    plan = {"schema_version": 1, "source_id": source_id, "field_id": field_id,
            "item_key": item_key, "segment": segment, "language": language,
            "source_url": source_url, "retrieved_at": retrieved_at,
            "root_binding": binding.model_dump(mode="json"), "registry_hash": registry.revision(),
            "document": document, "source": source, "owner_path": owner_path,
            "resource_id": f"document:zotero:{document['library_id']}:{item_key}",
            "ownership_read_set": _document_read_set(registry, source_id, document),
            "fields_before": fields.content.decode(),
            "fields_after": yaml.safe_dump(FieldManifest.model_validate(updated).model_dump(mode="json"),
                                           allow_unicode=True, sort_keys=False),
            "provider_before": provider.content.decode(), "before_snapshot": before.model_dump(mode="json")}
    _check_authority(registry, zotero, plan, locals(), binding)
    if (_read_declaration(_provider_path(registry, source_id), _SNAPSHOT, _LIMIT).content != provider.content
            or _read_declaration(root, ".scholar-workflow/fields.yml", 2 * 1024 * 1024).content != fields.content
            or _vault_binding_for_root(root) != binding):
        raise FieldRegistryError("Document registration declarations changed during planning")
    plan["approved_digest"] = _hash(_bytes(plan)).removeprefix("sha256:")
    if len(_bytes(plan)) + 1024 > _LIMIT:
        raise FieldRegistryError("Document registration plan exceeds the bounded recovery-state size")
    return plan


def _registered_snapshot(plan: dict, applied_at: str) -> tuple[KnowledgeProviderSnapshot, KnowledgeApplyReceipt]:
    before = KnowledgeProviderSnapshot.model_validate(plan["before_snapshot"])
    if KnowledgeProviderSnapshot.model_validate_json(plan["provider_before"].encode()) != before:
        raise FieldRegistryError("Document journal has inconsistent provider before-images")
    catalog = before.catalog.model_dump(mode="json")
    catalog["revision"] = ""
    catalog["resources"].append(HubResource(
        resource_id=plan["resource_id"], kind=ResourceKind.BLOG_POST, title=plan["document"]["title"],
        identifiers=Identifiers(url=plan["source_url"]), zotero=ZoteroLink(item_key=plan["item_key"]),
    ).model_dump(mode="json"))
    projected = HubCatalog.model_validate(catalog)
    semantic = {"change_id": "change:" + plan["approved_digest"],
                "change_fingerprint": "sha256:" + plan["approved_digest"],
                "source_receipt": "document-register:" + plan["approved_digest"],
                "before_catalog_revision": before.catalog.revision,
                "after_catalog_revision": projected.revision, "applied_artifact_ids": []}
    receipt = KnowledgeApplyReceipt(
        receipt_id="knowledge-apply:" + _hash_payload(semantic).removeprefix("sha256:"),
        applied_at=applied_at, **semantic,
    )
    data = before.model_dump(mode="json")
    data["manifest"]["atomic_resources"].append(KnowledgeAtomicResource(
        resource_id=plan["resource_id"], kind=ResourceKind.BLOG_POST, title=plan["document"]["title"],
        markdown_path=plan["owner_path"], markdown_sha256=plan["source"]["markdown_sha256"],
    ).model_dump(mode="json"))
    data.update(snapshot_revision="", catalog=projected.model_dump(mode="json"),
                receipts=data["receipts"] + [receipt.model_dump(mode="json")])
    return KnowledgeProviderSnapshot.model_validate(data), receipt


def register_document(registry: KnowledgeSourceRegistry, zotero, *, approved_digest: str,
                      fault_inject=None, **selection) -> dict:
    """Publish or recover the reviewed source/navigation/provider transaction."""
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("Approved digest must be SHA-256 hex")
    journal_name = f"document-registration-{approved_digest}.json"
    with registry._write_guard():
        root, binding, _, field = _location(registry, selection["source_id"], selection["field_id"])
        with _locked_registered_providers(registry, selection["source_id"]) as provider:
            previous, _ = _read(provider.fd, journal_name)
            if previous is None:
                plan = document_plan(registry, zotero, **selection)
                if plan["approved_digest"] != approved_digest:
                    raise FieldRegistryError("Document registration plan changed; review a new plan")
                journal = {"status": "prepared", "plan": plan, "applied_at": datetime.now(UTC).isoformat()}
                encoded = _bytes(journal)
                if len(encoded) > _LIMIT:
                    raise FieldRegistryError("Document registration journal exceeds its size limit")
                _atomic_create(provider.fd, journal_name, encoded)
            else:
                journal = json.loads(previous, object_pairs_hook=_pairs)
                if not isinstance(journal, dict) or set(journal) != {"status", "plan", "applied_at"} or (
                    journal["status"] not in {"prepared", "committed"}
                ):
                    raise FieldRegistryError("Invalid document registration journal")
                plan = journal["plan"]
                if not isinstance(plan, dict) or plan.get("approved_digest") != approved_digest or (
                    _hash(_bytes({k: v for k, v in plan.items() if k != "approved_digest"})).removeprefix("sha256:")
                    != approved_digest
                ):
                    raise FieldRegistryError("Document registration journal digest is invalid")
            expected = (PurePosixPath(field.relative_root) / "resources"
                        / selection["segment"] / "Source.md").as_posix()
            if plan["owner_path"] != expected or plan["resource_id"] != (
                f"document:zotero:{plan['document']['library_id']}:{selection['item_key']}"
            ):
                raise FieldRegistryError("Selected Field no longer owns the document folder")
            _check_authority(registry, zotero, plan, selection, binding)
            if journal["status"] == "committed":
                current, _ = _read(provider.fd, _SNAPSHOT)
                snapshot = KnowledgeProviderSnapshot.model_validate_json(current or b"")
                owners = [r for r in snapshot.manifest.atomic_resources if r.resource_id == plan["resource_id"]]
                projected = [r for r in snapshot.catalog.resources if r.resource_id == plan["resource_id"]]
                receipt = next((r for r in snapshot.receipts if getattr(r, "source_receipt", None)
                                == "document-register:" + approved_digest), None)
                source = _read_declaration(root, expected, _LIMIT)
                if (len(owners) != 1 or owners[0].markdown_path != expected
                        or owners[0].kind is not ResourceKind.BLOG_POST
                        or owners[0].markdown_sha256 != _hash(source.content)
                        or source.content != plan["source"]["markdown"].encode()
                        or len(projected) != 1 or projected[0].kind is not ResourceKind.BLOG_POST
                        or projected[0].zotero.item_key != selection["item_key"]
                        or projected[0].zotero.attachment_key is not None
                        or projected[0].identifiers.url != selection["source_url"]
                        or snapshot.vault_binding != binding or receipt is None
                        or not any(f"resources/{selection['segment']}/Source.md" in row.items
                                   for row in field.navigation)):
                    raise FieldRegistryError("Committed document ownership or source changed")
                _assert_unused_document(snapshot, plan["document"], existing_owner_id=plan["resource_id"])
                return _result(plan, snapshot, receipt.receipt_id)
            after, receipt = _registered_snapshot(plan, journal["applied_at"])
            owner = PurePosixPath(expected)
            with _directories(root, owner.parts[:-1]) as (note_fd, check_note), (
                _directories(root, (".scholar-workflow",))
            ) as (fields_fd, check_fields):
                root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    fcntl.flock(root_fd, fcntl.LOCK_EX)
                    members = [(note_fd, owner.name, None, plan["source"]["markdown"].encode()),
                               (fields_fd, "fields.yml", plan["fields_before"].encode(), plan["fields_after"].encode()),
                               (provider.fd, _SNAPSHOT, plan["provider_before"].encode(),
                                _bytes(after.model_dump(mode="json")))]
                    for fd, name, old, new in members:
                        value, _ = _read(fd, name)
                        if value not in (old, new):
                            raise FieldRegistryError("Document registration conflict; journal retained")
                    for index, (fd, name, old, new) in enumerate(members):
                        check_note()
                        check_fields()
                        provider.ensure_current()
                        if _vault_binding_for_root(root) != binding or (
                            _identity(os.fstat(root_fd))[:2] != (binding.device, binding.inode)
                        ):
                            raise FieldRegistryError("Source root changed during document publication")
                        _check_authority(registry, zotero, plan, selection, binding)
                        _put(fd, name, old, new)
                        if fault_inject is not None:
                            fault_inject(f"member-{index + 1}")
                    check_note()
                    check_fields()
                    provider.ensure_current()
                    _check_authority(registry, zotero, plan, selection, binding)
                    if any(_read(fd, name)[0] != new for fd, name, _, new in members):
                        raise FieldRegistryError("Document publication changed before completion")
                    journal["status"] = "committed"
                    current, _ = _read(provider.fd, journal_name)
                    _put(provider.fd, journal_name, current, _bytes(journal))
                finally:
                    fcntl.flock(root_fd, fcntl.LOCK_UN)
                    os.close(root_fd)
            return _result(plan, after, receipt.receipt_id)
