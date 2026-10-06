"""Export explicit Knowledge ownership as replay input, never as another live root."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from ruamel.yaml import YAML

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    _locked_state_root,
    _vault_binding_for_root,
)
from scholar_workflow.analysis.commit import _read_target_regular
from scholar_workflow.analysis.image_assets import ImageAssetError, verify_canvas_assets
from scholar_workflow.analysis.models import AnalysisBaseline
from scholar_workflow.analysis.package_check import check_package
from scholar_workflow.knowledge.catalog_models import HubAsset, HubCatalog
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    _open_directory_chain,
)
from scholar_workflow.workflows.register_paper import (
    _SNAPSHOT,
    _bytes,
    _directories,
    _hash,
    _identity,
    _pairs,
    _paper,
    _provider_path,
    _put,
    _read,
)


def _asset_projection(snapshot, payload):
    """Overlay explicit portable assets without changing the live provider."""
    if payload is None:
        return snapshot
    try:
        declaration = YAML(typ="safe").load(payload.decode("utf-8"))
        if (not isinstance(declaration, dict) or set(declaration) != {"schema_version", "assets"}
                or type(declaration["schema_version"]) is not int
                or declaration["schema_version"] != 1 or not isinstance(declaration["assets"], list)):
            raise ValueError("Invalid asset manifest shape")
        rows = [HubAsset.model_validate(row) for row in declaration["assets"]]
    except Exception as exc:
        raise FieldRegistryError("Invalid portable asset manifest") from exc
    owners = {row.artifact_id for row in snapshot.catalog.artifacts}
    occupied = {r.markdown_path for r in snapshot.manifest.atomic_resources}
    occupied.update(d.markdown_path for d in snapshot.manifest.core_documents)
    occupied.update(d.vault_path for d in snapshot.manifest.supporting_documents)
    occupied.update(a.vault_path for a in snapshot.artifacts)
    merged = {row.asset_id: row for row in snapshot.catalog.assets}
    seen_ids, seen_paths = set(), set()
    for row in rows:
        if row.asset_id in seen_ids or row.vault_path in seen_paths:
            raise FieldRegistryError("Duplicate portable asset identity or path")
        if (set(row.owner_artifact_ids) - owners or row.vault_path in occupied
                or row.vault_path.startswith(".scholar-workflow/")):
            raise FieldRegistryError("Portable asset has unknown ownership or an occupied path")
        if row.asset_id in merged and merged[row.asset_id] != row:
            raise FieldRegistryError("Portable asset declaration conflicts with provider")
        seen_ids.add(row.asset_id)
        seen_paths.add(row.vault_path)
        merged[row.asset_id] = row
    data = snapshot.model_dump(mode="json")
    catalog = data["catalog"]
    catalog.update(revision="", assets=[merged[key].model_dump(mode="json") for key in sorted(merged)])
    # This is a portable projection, not a new live catalog revision. Original
    # receipt history remains in the untouched provider and cannot certify it.
    data.update(snapshot_revision="", receipts=[],
                catalog=HubCatalog.model_validate(catalog).model_dump(mode="json"))
    return KnowledgeProviderSnapshot.model_validate(data)


def _inventory(root, root_fd, state_fd, fields, snapshot):
    """Check the same complete explicit file set for export and restoration."""
    asset_bytes, _ = _read(state_fd, "assets.yml")
    snapshot = _asset_projection(snapshot, asset_bytes)
    paths = {r.markdown_path for r in snapshot.manifest.atomic_resources}
    paths.update(d.markdown_path for d in snapshot.manifest.core_documents)
    paths.update(d.vault_path for d in snapshot.manifest.supporting_documents)
    paths.update(a.vault_path for a in snapshot.artifacts)
    paths.update(a.vault_path for a in snapshot.catalog.assets)
    for field in fields.fields:
        paths.add((PurePosixPath(field.relative_root) / field.home).as_posix())
        for group in field.navigation:
            paths.update((PurePosixPath(field.relative_root) / p).as_posix() for p in group.items)
    contents = {path: _read_target_regular(root, root_fd, path) for path in sorted(paths)}
    hashes = {path: _hash(payload) for path, payload in contents.items()}
    for artifact in snapshot.artifacts:
        if hashes[artifact.vault_path] != artifact.sha256:
            raise FieldRegistryError("Registered artifact hash differs from actual file")
    for asset in snapshot.catalog.assets:
        if hashes[asset.vault_path] != asset.sha256 or len(contents[asset.vault_path]) != asset.size:
            raise FieldRegistryError("Registered asset hash or size differs from actual file")
    parents = {a.artifact_id for a in snapshot.artifacts if a.kind == "analysis_markdown"}
    required = {identity for parent in parents for identity in (parent, parent + ":canvas", parent + ":sidecar")}
    actual = {a.artifact_id for a in snapshot.artifacts
              if a.kind in {"analysis_markdown", "analysis_canvas", "analysis_sidecar"}}
    if actual != required:
        raise FieldRegistryError("Analysis reproduction requires every complete owned bundle")
    baselines = {}
    for sidecar in [a for a in snapshot.artifacts if a.kind == "analysis_sidecar"]:
        baseline = AnalysisBaseline.model_validate_json(contents[sidecar.vault_path])
        parent_id = sidecar.artifact_id.removesuffix(":sidecar")
        members = {kind: [a for a in snapshot.artifacts if a.artifact_id == identity
                         and a.resource_id == sidecar.resource_id and a.kind == kind]
                   for kind, identity in {"analysis_markdown": parent_id,
                                          "analysis_canvas": parent_id + ":canvas"}.items()}
        if baseline.document.artifact_id != parent_id or any(len(rows) != 1 for rows in members.values()):
            raise FieldRegistryError("Analysis reproduction requires a complete owned bundle")
        md, canvas = members["analysis_markdown"][0], members["analysis_canvas"][0]
        folder = PurePosixPath(sidecar.vault_path).parent
        if any(PurePosixPath(a.vault_path).parent != folder for a in (md, canvas)):
            raise FieldRegistryError("Owned analysis members must share their paper folder")
        report = check_package(root / folder, markdown=PurePosixPath(md.vault_path).name,
                               canvas=PurePosixPath(canvas.vault_path).name,
                               sidecar=PurePosixPath(sidecar.vault_path).name)
        if report["status"] != "conformant" or any(
            report["files"][PurePosixPath(a.vault_path).name] != hashes[a.vault_path]
            for a in (md, canvas, sidecar)
        ):
            raise FieldRegistryError("Analysis reproduction bundle is nonconformant or changed")
        baselines[parent_id] = (sidecar.resource_id, baseline)
        try:
            verify_canvas_assets(baseline.document, folder, snapshot.catalog.assets, contents.__getitem__)
        except (ImageAssetError, KeyError) as exc:
            raise FieldRegistryError("Selected Canvas images are absent, changed or not explicitly owned in the reproduction inventory") from exc
    manifest_bytes = {}
    for name in ("fields.yml", "artifacts.yml", "assets.yml"):
        payload, _ = _read(state_fd, name)
        if name == "assets.yml" and payload != asset_bytes:
            raise FieldRegistryError("Portable asset manifest changed during inspection")
        manifest_bytes[name] = payload
        if payload is not None:
            hashes[".scholar-workflow/" + name] = _hash(payload)
    if manifest_bytes["fields.yml"] is None:
        raise FieldRegistryError("Portable Field manifest disappeared")
    return contents, hashes, manifest_bytes, baselines, snapshot


def reproduction_plan(registry: KnowledgeSourceRegistry, *, source_id: str,
                      _before_verify: Callable[[], None] | None = None) -> dict:
    """Read one registered Source/provider and bind every explicitly declared file.

    No locks, state initialization, discovery, application launches or content
    writes occur here. Destination restoration is a separate operation.
    """
    root = registry.resolve(source_id, capability="read")
    binding = _vault_binding_for_root(root)
    fields = FieldService._load_manifest(root)
    if fields.source_id != source_id:
        raise FieldRegistryError("Portable Source identity differs from registered Source")
    FieldService._validate_manifest_paths(root, fields)
    registry_hash = registry.revision()
    descriptors = []
    try:
        root_fd = _open_directory_chain(root)
        descriptors.append(root_fd)
        state_fd = _open_directory_chain(root / ".scholar-workflow")
        descriptors.append(state_fd)
        provider_path = _provider_path(registry, source_id)
        provider_fd = _open_directory_chain(provider_path)
        descriptors.append(provider_fd)
        provider_bytes, _ = _read(provider_fd, _SNAPSHOT)
        if provider_bytes is None:
            raise FieldRegistryError("Reproduction export requires an existing provider")
        snapshot = KnowledgeProviderSnapshot.model_validate(json.loads(provider_bytes, object_pairs_hook=_pairs))
        if snapshot.vault_binding != binding:
            raise FieldRegistryError("Knowledge provider belongs to another Source root")

        contents, hashes, manifest_bytes, baselines, snapshot = _inventory(
            root, root_fd, state_fd, fields, snapshot)
        reader_rebind = [parent for parent, (_, baseline) in baselines.items()
                         if baseline.document.reader is not None
                         and baseline.document.reader.kind == "zotflow_library"]

        # Catalog diagnostics and host receipts are not portable authority. The
        # existing strict models still validate the complete ownership projection.
        catalog = snapshot.catalog.model_dump(mode="json")
        catalog.update(revision="", sources=[], diagnostics=[])
        portable = snapshot.model_dump(mode="json")
        portable.update(snapshot_revision="", vault_binding=None, receipts=[],
                        catalog=HubCatalog.model_validate(catalog).model_dump(mode="json"))
        portable = KnowledgeProviderSnapshot.model_validate(portable).model_dump(mode="json")
        package = {"schema_version": 1, "source_id": source_id,
                   "fields": fields.model_dump(mode="json"), "provider": portable,
                   "files": hashes, "reader_rebind_required": sorted(reader_rebind)}

        if _before_verify is not None:
            _before_verify()
        if registry.revision() != registry_hash or registry.resolve(source_id, capability="read") != root or (
            _vault_binding_for_root(root) != binding or FieldService._load_manifest(root) != fields
            or _read(provider_fd, _SNAPSHOT)[0] != provider_bytes
            or any(_read_target_regular(root, root_fd, path) != payload for path, payload in contents.items())
            or any(_read(state_fd, name)[0] != payload for name, payload in manifest_bytes.items())
        ):
            raise FieldRegistryError("Reproduction inputs changed during inspection")
        for path, opened in ((root, root_fd), (root / ".scholar-workflow", state_fd), (provider_path, provider_fd)):
            current = _open_directory_chain(path)
            try:
                if _identity(os.fstat(current))[:2] != _identity(os.fstat(opened))[:2]:
                    raise FieldRegistryError("Reproduction directory changed during inspection")
            finally:
                os.close(current)
        return {"schema_version": 1, "status": "exportable", "source_id": source_id,
                "registry_revision": registry_hash, "provider_revision": _hash(provider_bytes),
                "package_digest": _hash(_bytes(package)), "package": package,
                "restore_performed": False, "source_verified": False, "human_verified": False}
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _load_package(path: Path):
    path = Path(os.path.abspath(path))
    fd = _open_directory_chain(path.parent)
    try:
        payload, _ = _read(fd, path.name)
    finally:
        os.close(fd)
    if payload is None:
        raise FieldRegistryError("Reproduction input is missing")
    value = json.loads(payload, object_pairs_hook=_pairs)
    if isinstance(value, dict) and "package" in value:
        if set(value) != {"schema_version", "status", "source_id", "registry_revision", "provider_revision",
                          "package_digest", "package", "restore_performed", "source_verified", "human_verified"}:
            raise FieldRegistryError("Unexpected reproduction export envelope")
        if not isinstance(value["package"], dict):
            raise FieldRegistryError("Reproduction envelope requires a portable package object")
        if (type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["status"] != "exportable" or value["restore_performed"] is not False
                or value["source_verified"] is not False or value["human_verified"] is not False
                or value["package_digest"] != _hash(_bytes(value["package"]))
                or value["source_id"] != value["package"].get("source_id")):
            raise FieldRegistryError("Reproduction envelope or package digest is invalid")
        value = value["package"]
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "source_id", "fields", "provider", "files", "reader_rebind_required"
    } or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise FieldRegistryError("Invalid portable reproduction package")
    fields = FieldManifest.model_validate(value["fields"])
    snapshot = KnowledgeProviderSnapshot.model_validate(value["provider"])
    if (value["source_id"] != fields.source_id or snapshot.vault_binding is not None or snapshot.receipts
            or snapshot.catalog.sources or snapshot.catalog.diagnostics):
        raise FieldRegistryError("Reproduction input must contain only portable ownership")
    hashes = value["files"]
    if not isinstance(hashes, dict) or not hashes or any(
        not isinstance(path, str) or not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        for path, digest in hashes.items()
    ):
        raise FieldRegistryError("Invalid portable file hash inventory")
    readers = value["reader_rebind_required"]
    if (not isinstance(readers, list) or any(not isinstance(v, str) or not v for v in readers)
            or len(readers) != len(set(readers))):
        raise FieldRegistryError("Invalid portable reader inventory")
    return value, fields, snapshot, _hash(payload)


def _source_checks(zotero, source_id, snapshot, baselines, contents):
    """Verify local authority/bytes; not scientific entailment or human acceptance."""
    papers = {}
    for resource in snapshot.catalog.resources:
        if resource.kind != "paper":
            continue
        if resource.zotero.item_key is None or resource.zotero.attachment_key is None:
            raise FieldRegistryError("Paper reproduction requires explicit Local API identities")
        paper = _paper(zotero, resource.zotero.item_key, resource.zotero.attachment_key)
        if resource.resource_id.startswith("paper:zotero:") and resource.resource_id != (
            f"paper:zotero:{paper['library_id']}:{paper['item_key']}"
        ):
            raise FieldRegistryError("Paper library identity differs from portable ownership")
        papers[resource.resource_id] = paper
    attachments = {p["attachment_key"]: p for p in papers.values()}
    blocks = []
    paths_by_identity = {a.artifact_id: a.vault_path for a in snapshot.artifacts}
    paths_by_identity.update({r.resource_id: r.markdown_path for r in snapshot.manifest.atomic_resources})
    paths_by_identity.update({d.document_id: d.markdown_path for d in snapshot.manifest.core_documents})
    for _, baseline in baselines.values():
        for claim in baseline.document.claims:
            for evidence in [claim.evidence, *(point.evidence for point in claim.points)]:
                for span in evidence.source_spans:
                    if span.kind == "vault_markdown":
                        if (str(span.source_id) != source_id
                                or paths_by_identity.get(span.artifact_id) != span.vault_path
                                or span.vault_path not in contents):
                            raise FieldRegistryError("Vault evidence requires its registered Source/document")
                        text = contents[span.vault_path].decode("utf-8")
                        if re.search(r"(?:^|\n)[^\n]*\^" + re.escape(span.block_id) + r"[ \t]*(?:\n|$)", text) is None:
                            raise FieldRegistryError("Registered Vault evidence block is missing")
                        blocks.append(span.model_dump(mode="json", exclude={"quote"}))
                        continue
                    if span.attachment_key not in attachments:
                        child = zotero.get_item(span.attachment_key)
                        parent = child.get("data", {}).get("parentItem")
                        if not isinstance(parent, str):
                            raise FieldRegistryError("Evidence attachment parent identity is missing")
                        attachments[span.attachment_key] = _paper(zotero, parent, span.attachment_key)
                    paper = attachments[span.attachment_key]
                    expected_type = "personal" if paper["library_type"] == "user" else "group"
                    if (span.library_id != paper["library_id"] or span.library_type != expected_type
                            or span.content_hash != paper["pdf_hash"]):
                        raise FieldRegistryError("Evidence attachment library or PDF hash differs from source")
                    if span.annotation_key is not None:
                        annotation = zotero.get_item(span.annotation_key)
                        if (annotation.get("key") != span.annotation_key
                                or annotation.get("data", {}).get("itemType") != "annotation"
                                or annotation.get("data", {}).get("parentItem") != span.attachment_key
                                or str(annotation.get("library", {}).get("id")) != span.library_id):
                            raise FieldRegistryError("Evidence annotation membership cannot be verified")
    return {"papers": papers, "attachments": attachments, "vault_blocks": blocks}


def _reader_checks(root, baselines):
    from scholar_workflow.adapters.obsidian_registry import ZotFlowError, resolve_obsidian_reader
    result = []
    for artifact, (baseline_path, baseline) in sorted(baselines.items()):
        reader = baseline.document.reader
        saved_note = baseline.document.profile.canvas_note_path
        zotflow = reader is not None and reader.kind == "zotflow_library"
        if not zotflow and saved_note is None:
            continue
        current_note = None
        try:
            binding = resolve_obsidian_reader(root)
            current = binding.vault_id
            status = "binding-matched" if not zotflow or current == reader.vault_id else "rebinding-required"
            if saved_note is not None:
                companion = Path(baseline_path).parent / (baseline.note_stem + ".md")
                current_note = (root / companion).relative_to(binding.vault_root).as_posix()
                if saved_note != current_note:
                    status = "rebinding-required"
        except (ZotFlowError, ValueError):
            current, status = None, "reader-unresolved"
        check = {"artifact_id": artifact, "saved_vault_id": reader.vault_id if zotflow else None,
                 "destination_vault_id": current, "status": status,
                 "reader_launch_verified": False}
        if saved_note is not None:
            check.update(saved_canvas_note_path=saved_note, destination_canvas_note_path=current_note,
                         canvas_note_binding=("reader-unresolved" if current is None else
                                              "binding-matched" if saved_note == current_note else
                                              "rebinding-required"))
        result.append(check)
    return result


def _provider_bytes(path):
    # Inspect each existing ancestor without following a dangling symlink. A
    # missing suffix is absence, not permission to create a provider in preview.
    for parent in reversed((path, *path.parents)):
        if os.path.lexists(parent):
            descriptor = _open_directory_chain(parent)
            os.close(descriptor)
    if not os.path.lexists(path):
        return None
    descriptor = _open_directory_chain(path)
    try:
        return _read(descriptor, _SNAPSHOT)[0]
    finally:
        os.close(descriptor)


def restore_plan(registry: KnowledgeSourceRegistry, zotero, *, source_id: str, package: Path,
                 _expected_provider: bytes | None = None,
                 _before_verify: Callable[[], None] | None = None) -> dict:
    """Preview exact ownership restoration into an explicitly attached new host."""
    portable, fields, snapshot, input_hash = _load_package(package)
    if portable["source_id"] != source_id:
        raise FieldRegistryError("Package Source differs from selected destination Source")
    root = registry.resolve(source_id, capability="write")
    binding = _vault_binding_for_root(root)
    registry_hash = registry.revision()
    if FieldService._load_manifest(root) != fields:
        raise FieldRegistryError("Destination portable Fields differ from reproduction input")
    FieldService._validate_manifest_paths(root, fields)
    provider_path = _provider_path(registry, source_id)
    provider_before = _provider_bytes(provider_path)
    if provider_before is not None and provider_before != _expected_provider:
        raise FieldRegistryError("Reproduction never replaces an existing provider")
    root_fd = _open_directory_chain(root)
    try:
        state_fd = _open_directory_chain(root / ".scholar-workflow")
        try:
            contents, hashes, manifests, baselines, snapshot = _inventory(
                root, root_fd, state_fd, fields, snapshot)
            if hashes != portable["files"]:
                raise FieldRegistryError("Destination files differ from the complete reproduction inventory")
            expected_readers = sorted(parent for parent, (_, baseline) in baselines.items()
                                      if baseline.document.reader is not None
                                      and baseline.document.reader.kind == "zotflow_library")
            if expected_readers != sorted(portable["reader_rebind_required"]):
                raise FieldRegistryError("Portable reader inventory differs from saved analyses")
            sources = _source_checks(zotero, source_id, snapshot, baselines, contents)
            readers = _reader_checks(root, baselines)
            after = snapshot.model_dump(mode="json")
            after.update(snapshot_revision="", vault_binding=binding.model_dump(mode="json"))
            after = KnowledgeProviderSnapshot.model_validate(after).model_dump(mode="json")
            if _before_verify:
                _before_verify()
            if (registry.revision() != registry_hash or registry.resolve(source_id, capability="write") != root
                    or _vault_binding_for_root(root) != binding or FieldService._load_manifest(root) != fields
                    or _load_package(package)[3] != input_hash or _provider_bytes(provider_path) != provider_before
                    or any(_read_target_regular(root, root_fd, path) != data for path, data in contents.items())
                    or any(_read(state_fd, name)[0] != data for name, data in manifests.items())
                    or _source_checks(zotero, source_id, snapshot, baselines, contents) != sources
                    or _reader_checks(root, baselines) != readers):
                raise FieldRegistryError("Reproduction authority or files changed during inspection")
            current_state = _open_directory_chain(root / ".scholar-workflow")
            try:
                if _identity(os.fstat(current_state))[:2] != _identity(os.fstat(state_fd))[:2]:
                    raise FieldRegistryError("Destination state directory changed during inspection")
            finally:
                os.close(current_state)
        finally:
            os.close(state_fd)
    finally:
        os.close(root_fd)
    plan = {"schema_version": 1, "source_id": source_id, "root_binding": binding.model_dump(mode="json"),
            "registry_revision": registry_hash, "package_file_hash": input_hash,
            "package_digest": _hash(_bytes(portable)), "files": hashes, "source_checks": sources,
            "readers": readers, "provider_after": after,
            "content_rewritten": False, "human_verified": False, "reproduction_complete": False}
    plan["approved_digest"] = _hash(_bytes(plan)).removeprefix("sha256:")
    return plan


def restore(registry: KnowledgeSourceRegistry, zotero, *, source_id: str, package: Path,
            approved_digest: str, fault_inject=None) -> dict:
    """Create missing host ownership once; replay only an unchanged prepared input."""
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("Approved digest must be SHA-256 hex")
    # Fail before any state initialization for unknown/disabled/read-only Sources.
    registry.resolve(source_id, capability="write")
    provider_path = _provider_path(registry, source_id)
    journal_name = f"knowledge-reproduction-{approved_digest}.json"
    with registry._write_guard():  # noqa: SIM117 - lock acquisition order is explicit
        with _directories(registry.path.parent, ("knowledge-providers", source_id)) as (_, check):
            with _locked_state_root(provider_path) as locked:
                journal_bytes, _ = _read(locked.fd, journal_name)
                expected = None
                if journal_bytes is not None:
                    journal = json.loads(journal_bytes, object_pairs_hook=_pairs)
                    if (not isinstance(journal, dict) or set(journal) != {"status", "plan", "receipt"}
                            or journal["status"] not in {"prepared", "committed"}
                            or not isinstance(journal["plan"], dict)):
                        raise FieldRegistryError("Invalid reproduction journal")
                    saved = dict(journal["plan"])
                    claimed = saved.pop("approved_digest", None)
                    if claimed != approved_digest or _hash(_bytes(saved)).removeprefix("sha256:") != approved_digest:
                        raise FieldRegistryError("Reproduction journal digest differs from approval")
                    expected = _bytes(journal["plan"]["provider_after"])
                plan = restore_plan(registry, zotero, source_id=source_id, package=package,
                                    _expected_provider=expected)
                if plan["approved_digest"] != approved_digest:
                    raise FieldRegistryError("Reproduction inputs changed; review a new plan")
                receipt = {"schema_version": 1, "status": "ownership-restored", "source_id": source_id,
                           "approved_digest": approved_digest, "receipt_id": "knowledge-reproduction:" + approved_digest,
                           "snapshot_revision": plan["provider_after"]["snapshot_revision"],
                           "source_identity_verified": True, "readers": plan["readers"],
                           "content_rewritten": False, "backup_verified": False,
                           "human_verified": False, "scientific_review_verified": False,
                           "reproduction_complete": False}
                prepared = {"status": "prepared", "plan": plan, "receipt": receipt}
                if journal_bytes is not None:
                    if journal["plan"] != plan or journal["receipt"] != receipt:
                        raise FieldRegistryError("Reproduction journal does not match reviewed input")
                    if journal["status"] == "committed":
                        if _read(locked.fd, _SNAPSHOT)[0] != expected:
                            raise FieldRegistryError("Restored provider changed after completion")
                        check()
                        locked.ensure_current()
                        return receipt
                else:
                    _put(locked.fd, journal_name, None, _bytes(prepared))
                if fault_inject:
                    fault_inject("prepared")
                # Recheck after durable preparation, then exclusively create the
                # provider. Content files and portable manifests are never written.
                fresh = restore_plan(registry, zotero, source_id=source_id, package=package,
                                     _expected_provider=expected)
                if fresh != plan:
                    raise FieldRegistryError("Reproduction inputs changed before publication")
                check()
                locked.ensure_current()
                _put(locked.fd, _SNAPSHOT, None, _bytes(plan["provider_after"]))
                if fault_inject:
                    fault_inject("provider-created")
                if restore_plan(registry, zotero, source_id=source_id, package=package,
                                _expected_provider=_bytes(plan["provider_after"])) != plan:
                    raise FieldRegistryError("Reproduction inputs changed during publication")
                check()
                locked.ensure_current()
                current, _ = _read(locked.fd, journal_name)
                if current != _bytes(prepared):
                    raise FieldRegistryError("Reproduction journal changed during publication")
                committed = dict(prepared, status="committed")
                _put(locked.fd, journal_name, current, _bytes(committed))
                return receipt
