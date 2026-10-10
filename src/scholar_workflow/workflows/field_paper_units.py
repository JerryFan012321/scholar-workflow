"""Read-only navigation of one Field's explicitly declared paper packages."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode

import yaml

from scholar_workflow.adapters import obsidian_registry
from scholar_workflow.knowledge.catalog_models import HubAsset
from scholar_workflow.knowledge.fields import FieldRegistryError
from scholar_workflow.knowledge.ownership import (
    KnowledgeOwnershipIssue,
    resolve_declared_ownership,
)
from scholar_workflow.workflows.knowledge_open import _document_identity
from scholar_workflow.workflows.knowledge_ownership import (
    _file_observation,
    _qualified_result,
    _read_declaration,
    _resolve_objects,
    _root_identity,
    _UniqueYaml,
)

_ASSETS = ".scholar-workflow/assets.yml"
_ASSET_LIMIT = 2 * 1024 * 1024


def _source_assets(inventory: dict) -> tuple[dict, list[dict]]:
    """Merge explicit attachments without promoting them to Knowledge owners."""
    assets, issues = {}, []
    inventory["asset_reads"] = {}
    for source_id in sorted({source for source, _owner in inventory["selected_owners"]}):
        snapshot = inventory["snapshots"][source_id]
        root = inventory["roots"][source_id]
        portable = []

        def issue(code="asset_declaration_invalid", source_id=source_id):
            issues.append({"source_id": source_id, "code": code})

        try:
            read = _read_declaration(root, _ASSETS, _ASSET_LIMIT)
        except FileNotFoundError:
            inventory["asset_reads"][source_id] = None
        except (OSError, ValueError):
            issue("asset_declaration_unavailable")
        else:
            inventory["asset_reads"][source_id] = read
            try:
                data = yaml.load(read.content, Loader=_UniqueYaml)
                if (not isinstance(data, dict) or set(data) != {"schema_version", "assets"}
                        or type(data["schema_version"]) is not int or data["schema_version"] != 1
                        or not isinstance(data["assets"], list)):
                    raise ValueError("Invalid asset declaration shape")
                for row in data["assets"]:
                    try:
                        portable.append(HubAsset.model_validate(row))
                    except ValueError:
                        issue()
            except (ValueError, RecursionError, yaml.YAMLError):
                issue()
        owners = {row.artifact_id for row in snapshot.artifacts}
        occupied_ids = {row.object_id for row in inventory["locations"]
                        if row.source_id == source_id}
        occupied_paths = {row.relative_path for row in inventory["locations"]
                          if row.source_id == source_id}
        repeated_ids = {value for value, count in Counter(row.asset_id for row in portable).items()
                        if count > 1}
        repeated_paths = {value for value, count in Counter(row.vault_path for row in portable).items()
                          if count > 1}
        rows = [row.model_copy(update={"owner_artifact_ids": sorted(row.owner_artifact_ids)})
                for row in [*snapshot.catalog.assets, *portable]]
        variants = {}
        path_ids: dict[str, set[str]] = {}
        for row in rows:
            if row.asset_id in variants and variants[row.asset_id] != row:
                repeated_ids.add(row.asset_id)
            variants[row.asset_id] = row
            path_ids.setdefault(row.vault_path, set()).add(row.asset_id)
        repeated_paths.update(path for path, ids in path_ids.items() if len(ids) > 1)
        merged = {}
        for row in rows:
            if (set(row.owner_artifact_ids) - owners or row.asset_id in occupied_ids
                    or row.vault_path in occupied_paths
                    or row.asset_id in repeated_ids or row.vault_path in repeated_paths):
                issue()
                continue
            merged[row.asset_id] = row
        assets[source_id] = [merged[key] for key in sorted(merged)]
    return assets, issues


def _asset_changes(inventory: dict) -> list[dict]:
    """Also detect a declaration appearing after an optional absent observation."""
    issues = []
    for source_id, read in inventory["asset_reads"].items():
        try:
            current = _read_declaration(inventory["roots"][source_id], _ASSETS, _ASSET_LIMIT)
            if read is None or current.identity != read.identity or current.content != read.content:
                raise ValueError("Asset declaration changed")
        except FileNotFoundError:
            if read is None:
                continue
        except (OSError, ValueError):
            pass
        else:
            continue
        issues.append({"source_id": source_id, "code": "asset_declaration_changed"})
    return issues


def _file_ownership_resolved(row: dict, source_id: str, owner_id: str, results: dict) -> bool:
    if results[owner_id].status != "resolved":
        return False
    if row["kind"] != "asset":
        return results[row["object_id"]].status == "resolved"
    # Shared assets may also have owners outside this selection. The selected
    # paper's explicit producer artifacts must resolve in this Source, not by name.
    producers = [results[value] for value in row["owner_artifact_ids"] if value in results
                 and any(location.source_id == source_id and location.owner_id == owner_id
                         for location in results[value].locations)]
    return bool(producers) and all(value.status == "resolved" for value in producers)


def _authority_changes(inventory: dict) -> list[KnowledgeOwnershipIssue]:
    """Recheck declarations and pinned directory bindings without a write lock."""
    changes = []
    for source_id, read in inventory["reads"]:
        try:
            current = _read_declaration(read.root, read.relative_path, read.limit)
            if (current.identity != read.identity or hashlib.sha256(current.content).digest()
                    != hashlib.sha256(read.content).digest()):
                raise ValueError("Declaration changed")
        except (OSError, ValueError):
            changes.append(KnowledgeOwnershipIssue(source_id=source_id, code="declaration_changed"))
    for source_id, root, expected in inventory["bindings"]:
        try:
            if _root_identity(root) != expected:
                raise ValueError("Source binding changed")
        except (OSError, ValueError):
            changes.append(KnowledgeOwnershipIssue(source_id=source_id,
                                                   code="source_binding_changed"))
    for provider in inventory["providers"]:
        root = inventory["registry_parent"] / "knowledge-providers" / provider["source_id"]
        try:
            if list(_root_identity(root)) != provider["identity"]:
                raise ValueError("Provider binding changed")
        except (OSError, ValueError):
            changes.append(KnowledgeOwnershipIssue(source_id=provider["source_id"],
                                                   code="provider_binding_changed"))
    return changes


def _readers(inventory: dict, results: dict, config_path: Path | None) -> tuple[dict, list[dict]]:
    """Resolve and recheck only native reader destinations; never dispatch opens."""
    sources = {source_id for source_id, owner_id in inventory["selected_owners"]
               if results[owner_id].status == "resolved"}
    if not sources:
        return {}, []
    config = config_path or Path.home() / "Library/Application Support/obsidian/obsidian.json"
    bindings = {}
    identities = {}
    issues = []
    try:
        read = _read_declaration(config.parent, config.name, 1024 * 1024)
    except (OSError, ValueError):
        return {}, [{"source_id": source_id, "code": "reader_unavailable"}
                    for source_id in sorted(sources)]
    for source_id in sorted(sources):
        root = inventory["roots"][source_id]
        try:
            binding = obsidian_registry.resolve_obsidian_reader(root, config_path=config)
            identity = _root_identity(binding.vault_root)
            current = obsidian_registry.resolve_obsidian_reader(root, config_path=config)
            if current != binding or _root_identity(current.vault_root) != identity:
                raise ValueError("Reader binding changed")
            bindings[source_id] = binding
            identities[source_id] = identity
        except (OSError, ValueError, obsidian_registry.ZotFlowError):
            issues.append({"source_id": source_id, "code": "reader_unavailable"})
    try:
        current_read = _read_declaration(config.parent, config.name, read.limit)
        if current_read.identity != read.identity or current_read.content != read.content:
            raise ValueError("Reader registry changed")
    except (OSError, ValueError):
        bindings.clear()
        issues.extend({"source_id": source_id, "code": "reader_changed"}
                      for source_id in sorted(sources))
    inventory["reader_observation"] = (read, identities)
    return bindings, issues


def _reader_changes(inventory: dict, readers: dict) -> list[dict]:
    observation = inventory.get("reader_observation")
    if observation is None or not readers:
        return []
    read, identities = observation
    issues = []
    try:
        current = _read_declaration(read.root, read.relative_path, read.limit)
        if current.identity != read.identity or current.content != read.content:
            raise ValueError("Reader registry changed")
    except (OSError, ValueError):
        return [{"source_id": source_id, "code": "reader_changed"} for source_id in readers]
    for source_id, binding in readers.items():
        try:
            current_binding = obsidian_registry.resolve_obsidian_reader(
                inventory["roots"][source_id], config_path=read.root / read.relative_path,
            )
            if (current_binding != binding
                    or _root_identity(binding.vault_root) != identities[source_id]):
                raise ValueError("Reader binding changed")
        except (OSError, ValueError, obsidian_registry.ZotFlowError):
            issues.append({"source_id": source_id, "code": "reader_changed"})
    return issues


def _declared_files(snapshot, owner_id: str, assets: list[HubAsset]) -> list[dict]:
    """Use primary, supporting and artifact declarations, never nearby filenames."""
    owner = next(row for row in snapshot.manifest.atomic_resources if row.resource_id == owner_id)
    files = [{"object_id": owner.resource_id, "kind": "paper", "title": owner.title,
              "relative_path": owner.markdown_path}]
    files.extend({"object_id": row.document_id, "kind": row.kind.value, "title": row.title,
                  "relative_path": row.vault_path}
                 for row in snapshot.manifest.supporting_documents if row.owner_id == owner_id)
    declared = {row["object_id"] for row in files}
    files.extend({"object_id": row.artifact_id, "kind": row.kind,
                  "title": PurePosixPath(row.vault_path).name, "relative_path": row.vault_path}
                 for row in snapshot.artifacts
                 if row.resource_id == owner_id and row.artifact_id not in declared)
    producers = {row.artifact_id for row in snapshot.artifacts if row.resource_id == owner_id}
    files.extend({"object_id": row.asset_id, "kind": "asset", "title": row.display_name,
                  "relative_path": row.vault_path, "owner_artifact_ids": row.owner_artifact_ids,
                  "asset_role": row.role.value}
                 for row in assets if producers.intersection(row.owner_artifact_ids))
    return files


def field_paper_units(
    registry_path: Path, *, source_id: str, field_id: str,
    reader_config_path: Path | None = None,
) -> dict:
    """Compose declared paper units for one explicit Field, without reading bodies.

    Titles are local provider titles, not a refreshed bibliographic record. Native
    URIs are dispatch candidates only; no application, network or subprocess runs.
    """
    if not source_id or not field_id:
        raise FieldRegistryError("Paper units require both Source and Field selectors")
    inventory: dict = {}
    results, available = _resolve_objects(
        set(), Path(registry_path), field_selection=(source_id, field_id), inventory=inventory,
    )
    inventory["registry_parent"] = Path(registry_path).parent
    field = inventory["selected_field"]
    assets, asset_issues = _source_assets(inventory)
    readers, reader_issues = _readers(inventory, results, reader_config_path)
    observations = {(row["source_id"], row["relative_path"]): row for row in inventory["files"]}
    declared = {key: _declared_files(inventory["snapshots"][key[0]], key[1], assets[key[0]])
                for key in sorted(inventory["selected_owners"])}
    for (owner_source, _owner_id), files in declared.items():
        for row in files:
            key = (owner_source, row["relative_path"])
            if key not in observations:
                state, identity = _file_observation(inventory["roots"][owner_source], key[1])
                observations[key] = {"state": state, "identity": list(identity) if identity else None}
    file_views = {}
    file_states = {}
    changes = []
    for (owner_source, owner_id), files in declared.items():
        root = inventory["roots"][owner_source]
        output = []
        for row in files:
            relative = row["relative_path"]
            observed = observations[(owner_source, relative)]
            state, identity = _file_observation(root, relative)
            changed = state != observed["state"] or (
                list(identity) if identity else None) != observed["identity"]
            uri = None
            if changed:
                if row["kind"] == "asset":
                    asset_issues.append({"source_id": owner_source, "code": "asset_file_changed"})
                else:
                    changes.append(KnowledgeOwnershipIssue(source_id=owner_source, code="file_changed"))
                state = "unsafe" if state == "available" else state
            if state != "available":
                open_state = "file_unavailable"
            elif not _file_ownership_resolved(row, owner_source, owner_id, results):
                open_state = "ownership_unresolved"
            elif PurePosixPath(relative).suffix.lower() not in {".md", ".canvas"}:
                open_state = "unsupported_type"
            elif owner_source not in readers:
                open_state = "reader_unavailable"
            else:
                try:
                    if _document_identity(root, relative) != identity[:2]:
                        raise ValueError("Document changed")
                    binding = readers[owner_source]
                    vault_relative = (root / relative).relative_to(binding.vault_root).as_posix()
                    uri = "obsidian://open?" + urlencode(
                        {"vault": binding.vault_id, "file": vault_relative}, quote_via=quote,
                    )
                    open_state = "ready"
                except (OSError, ValueError, FieldRegistryError):
                    state, open_state = "unsafe", "file_unavailable"
            file_states[(owner_source, row["object_id"])] = state
            output.append({**row, "file_state": state, "uri": uri, "open_state": open_state})
        file_views[(owner_source, owner_id)] = output
    # A document or reader check must not hide a changed named file at completion.
    for (owner_source, owner_id), files in file_views.items():
        for row in files:
            observed = observations[(owner_source, row["relative_path"])]
            state, identity = _file_observation(inventory["roots"][owner_source], row["relative_path"])
            if (state != observed["state"] or (list(identity) if identity else None)
                    != observed["identity"]):
                if row["kind"] == "asset":
                    asset_issues.append({"source_id": owner_source, "code": "asset_file_changed"})
                else:
                    changes.append(KnowledgeOwnershipIssue(source_id=owner_source, code="file_changed"))
                row.update(file_state="unsafe" if state == "available" else state,
                           uri=None, open_state="file_unavailable")
                file_states[(owner_source, row["object_id"])] = row["file_state"]
    reader_changes = _reader_changes(inventory, readers)
    reader_issues.extend(reader_changes)
    changed_readers = {row["source_id"] for row in reader_changes}
    for (owner_source, _owner_id), files in file_views.items():
        if owner_source in changed_readers:
            for row in files:
                if row["open_state"] == "ready":
                    row.update(uri=None, open_state="reader_unavailable")
    changes.extend(_authority_changes(inventory))
    asset_issues.extend(_asset_changes(inventory))
    incomplete_assets = {row["source_id"] for row in asset_issues}
    issues = list({(row.source_id, row.code): row
                   for row in [*inventory["issues"], *changes]}.values())
    locations = [row.model_copy(update={"file_state": file_states.get(
        (row.source_id, row.object_id), row.file_state)}) for row in inventory["locations"]]
    results = {object_id: resolve_declared_ownership(object_id, locations, issues)
               for object_id in results}
    selections = {key: {"selected_by": ["owned"], "purposes": []}
                  for key in declared if key[0] == source_id and any(
                      row.source_id == source_id and row.field_id == field_id
                      and row.object_id == key[1] and row.owner_id == key[1] for row in locations)}
    unresolved = []
    for reference in field.references:
        resolution = _qualified_result(reference, results, available)
        reason = "reference_ownership_" + resolution.status
        if resolution.status == "resolved":
            owner = resolution.owner_candidates[0]
            key = (owner.source_id, owner.owner_id)
            if key in declared:
                selection = selections.setdefault(key, {"selected_by": [], "purposes": []})
                if "referenced" not in selection["selected_by"]:
                    selection["selected_by"].append("referenced")
                selection["purposes"].append(reference.purpose)
                continue
            reason = "reference_target_not_paper"
        unresolved.append({**reference.model_dump(mode="json"),
                           "resolution": resolution.model_dump(mode="json"), "reason": reason})
    units = []
    for (owner_source, owner_id), selection in selections.items():
        owner = next(row for row in locations if row.source_id == owner_source
                     and row.object_id == owner_id and row.owner_id == owner_id)
        files = file_views[(owner_source, owner_id)]
        for row in files:
            if (not _file_ownership_resolved(row, owner_source, owner_id, results)
                    or row["kind"] == "asset" and owner_source in incomplete_assets):
                row["uri"] = None
                if (row["file_state"] == "available"
                        and (row["kind"] != "asset" or row["open_state"] != "unsupported_type")):
                    row["open_state"] = "ownership_unresolved"
        units.append({"source_id": owner_source, "resource_id": owner_id,
                      "title": files[0]["title"], "field_title": owner.field_title,
                      **selection, "ownership": results[owner_id].model_dump(mode="json"),
                      "files": files})
    all_issues = list({(row["source_id"], row["code"]): row for row in [
        *(issue.model_dump(mode="json") for issue in issues), *reader_issues, *asset_issues,
    ]}.values())
    partial = bool(unresolved or all_issues or any(
        row["open_state"] not in {"ready", "unsupported_type"}
        for unit in units for row in unit["files"]))
    return {"schema_version": 1, "source_id": source_id, "field_id": field_id,
            "field_title": field.title, "paper_units": units,
            "unresolved_references": unresolved, "issues": all_issues,
            "status": "partial" if partial else "complete"}
