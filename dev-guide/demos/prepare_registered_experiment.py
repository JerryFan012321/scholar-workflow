"""Print a reviewed experiment-state patch; never mutate a production registration.

Only Sources within the explicit test Vault enter the isolated registry. Same-path/
same-inode device drift may be projected into their copied provider bindings;
artifact hashes and content are never adopted or repaired. This developer fixture
is not a runtime recovery operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import yaml

from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    KnowledgeSourceRegistry,
    _open_directory_chain,
)
from scholar_workflow.workflows.knowledge_ownership import _placements


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def prepare(registry_path, destination, selected=None, *, test_root):
    context = ExplorerEnvironment("test", destination, (test_root,))
    registry = KnowledgeSourceRegistry(registry_path)
    registry_before = registry_path.read_bytes()
    document = registry.load_document()
    test_root = context.check_root(test_root)
    folders = {row.folder_id: row for row in document.folders
               if row.enabled and (row.root == test_root or test_root in row.root.parents)}
    selected_sources = [row for row in document.sources
                        if row.enabled and row.folder_id in folders]
    selected_folders = {row.folder_id for row in selected_sources}
    isolated = document.model_copy(update={
        "folders": [row for row in document.folders if row.folder_id in selected_folders],
        "sources": selected_sources,
    })
    files = {"hub/sources.json": isolated.model_dump_json(indent=2) + "\n"}
    audit = []
    for source in selected_sources:
        root = registry.resolve(source.source_id, capability="read")
        context.check_root(root)
        descriptor = _open_directory_chain(root)
        try:
            info = os.fstat(descriptor)
            portable = root / ".scholar-workflow/fields.yml"
            portable_before = portable.read_bytes()
            fields = FieldManifest.model_validate(yaml.safe_load(portable_before))
            if fields.source_id != source.source_id:
                raise ValueError("Source identity does not match its portable manifest")
            path = registry_path.parent / "knowledge-providers" / source.source_id / "knowledge-provider.snapshot.json"
            state_fd = _open_directory_chain(path.parent)
            os.close(state_fd)
            if path.is_symlink():
                raise ValueError("Provider snapshot must not be a symbolic link")
            provider_before = path.read_bytes()
            snapshot = KnowledgeProviderSnapshot.model_validate_json(provider_before)
            old = snapshot.vault_binding
            if old is None or old.root_path != str(root) or old.inode != info.st_ino:
                raise ValueError("Experiment refuses anything except identical path and inode")
            _placements(source.source_id, fields, snapshot)
            data = snapshot.model_dump(mode="json")
            data["vault_binding"]["device"] = info.st_dev
            data["snapshot_revision"] = ""
            projected = KnowledgeProviderSnapshot.model_validate(data).model_dump(mode="json")
            original = snapshot.model_dump(mode="json")
            assert all(projected[key] == original[key] for key in original
                       if key not in {"vault_binding", "snapshot_revision"})
            if (registry_path.read_bytes() != registry_before or portable.read_bytes() != portable_before
                    or path.read_bytes() != provider_before or root.stat().st_ino != info.st_ino
                    or root.stat().st_dev != info.st_dev):
                raise ValueError("Experiment inputs changed during observation")
            relative = f"hub/knowledge-providers/{source.source_id}/knowledge-provider.snapshot.json"
            files[relative] = json.dumps(projected, ensure_ascii=False, indent=2) + "\n"
            audit.append({"source_id": source.source_id, "provider_sha256": digest(provider_before),
                          "fields_sha256": digest(portable_before), "path_and_inode_match": True,
                          "previous_device": old.device, "observed_device": info.st_dev,
                          "content_hashes_preserved": True})
        finally:
            os.close(descriptor)
    if registry_path.read_bytes() != registry_before:
        raise ValueError("Registered Source set changed during observation")
    files["audit.json"] = json.dumps({"mode": "experiment-only", "production_written": False,
        "registry_sha256": digest(registry_before), "test_root": str(test_root),
        "excluded_sources": len(document.sources) - len(selected_sources),
        "sources": audit}, ensure_ascii=False, indent=2) + "\n"
    if destination.is_symlink():
        raise ValueError("Experiment destination must not be a symlink")
    for relative in files:
        if selected is not None and relative != selected:
            continue
        if (destination / relative).exists():
            raise ValueError("Experiment refuses to overwrite an existing state")
    return files, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--patch", action="store_true")
    parser.add_argument("--select", help="Emit exactly one file of the same test-scoped fixture")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    files, audit = prepare(args.registry, args.destination, args.select, test_root=args.test_root)
    if args.list:
        print(json.dumps(list(files)))
        return
    if args.select:
        files = {args.select: files[args.select]}
    if not args.patch:
        print(json.dumps({"sources": len(audit), "same_path_and_inode": all(
            row["path_and_inode_match"] for row in audit), "device_drift": sum(
            row["previous_device"] != row["observed_device"] for row in audit),
            "production_written": False, "file_count": len(files)}))
        return
    print("*** Begin Patch")
    for relative, contents in files.items():
        print("*** Add File: " + str(args.destination / relative))
        for line in contents.splitlines():
            print("+" + line)
    print("*** End Patch")


if __name__ == "__main__":
    main()
