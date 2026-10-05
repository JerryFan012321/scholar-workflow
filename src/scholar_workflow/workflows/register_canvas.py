"""Publish one explicit, already-owned Canvas identity to its portable manifest."""
from __future__ import annotations

import fcntl
import io
import json
import os
import re
from pathlib import PurePosixPath

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot, _locked_state_root
from scholar_workflow.analysis.commit import _read_target_regular
from scholar_workflow.analysis.models import AnalysisBaseline
from scholar_workflow.analysis.package_check import check_package
from scholar_workflow.knowledge.catalog_models import ArtifactFormat, ArtifactKind, HubArtifact
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    KnowledgeSourceRegistry,
    _open_directory_chain,
)
from scholar_workflow.workflows.register_paper import (
    _SNAPSHOT,
    _bytes,
    _directories,
    _hash,
    _identity,
    _location,
    _pairs,
    _provider_path,
    _put,
    _read,
)

_MANIFEST = "artifacts.yml"
_LIMIT = 2 * 1024 * 1024


def _manifest_after(before: bytes | None, row: dict) -> bytes:
    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    if before is None:
        value = {"schema_version": 1, "artifacts": []}
    else:
        if len(before) > _LIMIT:
            raise FieldRegistryError("Canvas manifest exceeds its size limit")
        try:
            value = yaml.load(before.decode("utf-8"))
        except YAMLError as exc:
            raise FieldRegistryError("Invalid portable Canvas manifest YAML") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "artifacts"} or (
        type(value["schema_version"]) is not int or value["schema_version"] != 1
        or not isinstance(value["artifacts"], list)
    ):
        raise FieldRegistryError("Invalid portable Canvas manifest envelope")
    ids, paths = set(), set()
    present = False
    for raw in value["artifacts"]:
        artifact = HubArtifact.model_validate(raw)
        if artifact.kind != ArtifactKind.ANALYSIS_CANVAS or artifact.format != ArtifactFormat.CANVAS or (
            not artifact.vault_path.endswith(".canvas")
        ):
            raise FieldRegistryError("Canvas manifest contains an unsupported artifact")
        if artifact.artifact_id in ids or artifact.vault_path in paths:
            raise FieldRegistryError("Canvas manifest contains duplicate identity or path")
        ids.add(artifact.artifact_id)
        paths.add(artifact.vault_path)
        if artifact.artifact_id == row["artifact_id"] or artifact.vault_path == row["vault_path"]:
            if artifact.model_dump(mode="json", exclude_none=True) != row:
                raise FieldRegistryError("Canvas identity or path conflicts with an existing declaration")
            present = True
    if present:
        assert before is not None
        return before
    value["artifacts"].append(row)
    stream = io.StringIO()
    yaml.dump(value, stream)
    after = stream.getvalue().encode("utf-8")
    if len(after) > _LIMIT:
        raise FieldRegistryError("Canvas manifest exceeds its size limit")
    return after


def canvas_plan(registry: KnowledgeSourceRegistry, *, source_id: str, field_id: str,
                artifact_id: str) -> dict:
    """Inspect one declared bundle, without creating files, locks or a provider."""
    return _plan(registry, source_id=source_id, field_id=field_id, artifact_id=artifact_id)


def _plan(registry: KnowledgeSourceRegistry, *, source_id: str, field_id: str,
          artifact_id: str, manifest_before: bytes | None = None, replay: bool = False) -> dict:
    root, binding, manifest, field = _location(registry, source_id, field_id)
    registry_hash = registry.revision()
    descriptors = []
    try:
        provider_fd = _open_directory_chain(_provider_path(registry, source_id))
        descriptors.append(provider_fd)
        root_fd = _open_directory_chain(root)
        descriptors.append(root_fd)
        state_fd = _open_directory_chain(root / ".scholar-workflow")
        descriptors.append(state_fd)
        provider_bytes, _ = _read(provider_fd, _SNAPSHOT)
        if provider_bytes is None:
            raise FieldRegistryError("Canvas registration requires an existing authoritative provider")
        snapshot = KnowledgeProviderSnapshot.model_validate_json(provider_bytes)
        if snapshot.vault_binding != binding:
            raise FieldRegistryError("Canvas provider belongs to another Source directory")
        selected = [a for a in snapshot.artifacts if a.artifact_id == artifact_id
                    and a.kind == "analysis_canvas"]
        if len(selected) != 1:
            raise FieldRegistryError("Select exactly one already-owned analysis Canvas")
        canvas = selected[0]
        parent_id = artifact_id.removesuffix(":canvas")
        if parent_id == artifact_id:
            raise FieldRegistryError("Canvas identity has no explicit analysis parent")
        expected = {"analysis_markdown": parent_id, "analysis_canvas": artifact_id,
                    "analysis_sidecar": parent_id + ":sidecar"}
        bundle = {kind: [a for a in snapshot.artifacts if a.artifact_id == identity
                         and a.kind == kind and a.resource_id == canvas.resource_id]
                  for kind, identity in expected.items()}
        if any(len(rows) != 1 for rows in bundle.values()):
            raise FieldRegistryError("Canvas registration requires its complete owned analysis bundle")
        members = {kind: rows[0] for kind, rows in bundle.items()}
        folder = PurePosixPath(canvas.vault_path).parent
        owners = [r for r in snapshot.manifest.atomic_resources if r.resource_id == canvas.resource_id]
        if len(owners) != 1 or PurePosixPath(owners[0].markdown_path).parent != folder or (
            folder.parent != PurePosixPath(field.relative_root) / "resources" / "papers"
            or any(PurePosixPath(a.vault_path).parent != folder for a in members.values())
        ):
            raise FieldRegistryError("Selected Field and paper owner do not own this analysis folder")
        contents = {a.vault_path: _read_target_regular(root, root_fd, a.vault_path)
                    for a in members.values()}
        files = {path: _hash(payload) for path, payload in contents.items()}
        if any(files[a.vault_path] != a.sha256 for a in members.values()):
            raise FieldRegistryError("Analysis bundle differs from its registered provider hashes")
        baseline = AnalysisBaseline.model_validate_json(contents[members["analysis_sidecar"].vault_path])
        if baseline.document.artifact_id != parent_id or baseline.document.schema_version not in {4, 5}:
            raise FieldRegistryError("Canvas baseline identity or version differs from its owner")
        report = check_package(root / folder, markdown=PurePosixPath(members["analysis_markdown"].vault_path).name,
                               canvas=PurePosixPath(canvas.vault_path).name,
                               sidecar=PurePosixPath(members["analysis_sidecar"].vault_path).name)
        if report["status"] != "conformant" or any(
            report["files"][PurePosixPath(path).name] != digest for path, digest in files.items()
        ):
            raise FieldRegistryError("Actual Canvas bundle is nonconformant or changed during inspection")
        projected = [a for a in snapshot.catalog.artifacts if a.artifact_id == artifact_id]
        if len(projected) != 1 or projected[0].parent_id not in {None, parent_id} or (
            projected[0].resource_id != canvas.resource_id or projected[0].vault_path != canvas.vault_path
            or projected[0].kind != ArtifactKind.ANALYSIS_CANVAS
            or projected[0].format != ArtifactFormat.CANVAS
        ):
            raise FieldRegistryError("Canvas projection disagrees with authoritative ownership")
        row = projected[0].model_dump(mode="json", exclude_none=True, exclude={"revision"})
        row["parent_id"] = parent_id
        current_manifest, _ = _read(state_fd, _MANIFEST)
        before = manifest_before if replay else current_manifest
        after = _manifest_after(before, row)
        fields_bytes, _ = _read(state_fd, "fields.yml")
        current_root, current_binding, current_fields, _ = _location(registry, source_id, field_id)
        if fields_bytes is None or registry.revision() != registry_hash or (
            current_root != root or current_binding != binding or current_fields != manifest
        ):
            raise FieldRegistryError("Canvas registration authority changed during inspection")
        # Revalidate the full read set after checking the baseline and rendering contract.
        if _read(provider_fd, _SNAPSHOT)[0] != provider_bytes or any(
            _read_target_regular(root, root_fd, path) != value for path, value in contents.items()
        ) or _identity(os.fstat(root_fd))[:2] != (binding.device, binding.inode):
            raise FieldRegistryError("Canvas registration inputs changed during inspection")
        plan = {"schema_version": 1, "source_id": source_id, "field_id": field_id,
                "artifact_id": artifact_id, "root_binding": binding.model_dump(mode="json"),
                "registry_hash": registry_hash, "fields_hash": _hash(fields_bytes),
                "provider_hash": _hash(provider_bytes), "files": files, "artifact": row,
                "manifest_path": ".scholar-workflow/artifacts.yml",
                "manifest_before": before.decode() if before is not None else None,
                "manifest_after": after.decode(), "status": "ready" if before != after else "unchanged"}
        plan["approved_digest"] = _hash(_bytes(plan)).removeprefix("sha256:")
        return plan
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def register_canvas(registry: KnowledgeSourceRegistry, *, approved_digest: str,
                    fault_inject=None, **selection) -> dict:
    """CAS-publish or recover one reviewed portable declaration; never rewrite content."""
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("Approved digest must be SHA-256 hex")
    with registry._write_guard():
        root, binding, _, _ = _location(registry, selection["source_id"], selection["field_id"])
        with _locked_state_root(_provider_path(registry, selection["source_id"])) as provider:
            journal_name = f"canvas-registration-{approved_digest}.json"
            previous, _ = _read(provider.fd, journal_name)
            if previous is None:
                plan = canvas_plan(registry, **selection)
                if plan["approved_digest"] != approved_digest:
                    raise FieldRegistryError("Canvas registration plan changed; review a new plan")
                journal = {"status": "prepared", "plan": plan}
                _put(provider.fd, journal_name, None, _bytes(journal))
            else:
                journal = json.loads(previous, object_pairs_hook=_pairs)
                if not isinstance(journal, dict) or set(journal) != {"status", "plan"} or (
                    journal["status"] not in ("prepared", "committed") or not isinstance(journal["plan"], dict)
                ):
                    raise FieldRegistryError("Invalid Canvas registration journal")
                plan = journal["plan"]
                if _hash(_bytes({k: v for k, v in plan.items() if k != "approved_digest"})).removeprefix(
                    "sha256:"
                ) != approved_digest or plan.get("approved_digest") != approved_digest:
                    raise FieldRegistryError("Canvas registration journal digest is invalid")
            if any(plan.get(key) != value for key, value in selection.items()):
                raise FieldRegistryError("Canvas registration journal belongs to another selection")
            before = plan["manifest_before"].encode() if plan["manifest_before"] is not None else None
            after = plan["manifest_after"].encode()
            with _directories(root, (".scholar-workflow",)) as (state_fd, check_state):
                root_fd = _open_directory_chain(root)
                try:
                    fcntl.flock(root_fd, fcntl.LOCK_EX)
                    def verify():
                        provider.ensure_current()
                        check_state()
                        if _identity(os.fstat(root_fd))[:2] != (binding.device, binding.inode) or (
                            _plan(registry, **selection, manifest_before=before, replay=True) != plan
                        ):
                            raise FieldRegistryError("Canvas registration authority or bundle changed")
                        current, _ = _read(state_fd, _MANIFEST)
                        if current not in (before, after):
                            raise FieldRegistryError("Canvas manifest changed; refusing to overwrite")
                    verify()
                    _put(state_fd, _MANIFEST, before, after)
                    if fault_inject is not None:
                        fault_inject("manifest-written")
                    verify()
                    committed = dict(journal, status="committed")
                    _put(provider.fd, journal_name, _bytes(journal), _bytes(committed))
                    return {"schema_version": 1, "status": "registered",
                            "receipt_id": "canvas-registration:" + approved_digest,
                            "source_id": selection["source_id"], "field_id": selection["field_id"],
                            "artifact": plan["artifact"], "manifest_path": plan["manifest_path"],
                            "manifest_hash": _hash(after), "content_rewritten": False,
                            "human_verified": False, "backup_verified": False}
                finally:
                    fcntl.flock(root_fd, fcntl.LOCK_UN)
                    os.close(root_fd)
