"""Read-only Vault connections and bounded, non-mutating readiness previews."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from scholar_workflow.knowledge.exploration import ExplorationError
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryCommitUncertain,
    FieldRegistryError,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    SystemFolderPicker,
)

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_LIMIT = 2 * 1024 * 1024
_SCAN_BYTES = 32 * 1024 * 1024
_SCAN_ENTRIES = 8192
_MAX_DEPTH = 32
_TTL = 300


def _error(message, code=7):
    raise ExplorationError(message, code)


def _identity(fd):
    current = os.fstat(fd)
    return current.st_dev, current.st_ino


def _directory(root):
    """Anchor every absolute component without following symbolic links."""
    fd = os.open(root.anchor, _DIRECTORY)
    try:
        for part in root.parts[1:]:
            child = os.open(part, _DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or any(ord(character) < 32 for character in value)):
        _error("A clean relative document path is required", 2)
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value
            or any(part in {".", ".."} or part.startswith(".") for part in path.parts)):
        _error("Document path is outside the selected connection")
    return path.parts


def _read(fd, parts, limit=_LIMIT):
    parent = os.dup(fd)
    handle = None
    try:
        for part in parts[:-1]:
            child = os.open(part, _DIRECTORY, dir_fd=parent)
            os.close(parent)
            parent = child
        handle = os.open(parts[-1], _FILE, dir_fd=parent)
        before = os.fstat(handle)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            _error("The selected document is not a bounded regular file")
        chunks, count = [], 0
        while chunk := os.read(handle, min(65536, limit + 1 - count)):
            chunks.append(chunk)
            count += len(chunk)
            if count > limit:
                _error("The selected document exceeds the safe preview size")
        after = os.fstat(handle)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if count != before.st_size or any(getattr(before, f) != getattr(after, f) for f in fields):
            _error("The selected document changed; inspect it again", 5)
        return b"".join(chunks)
    finally:
        if handle is not None:
            os.close(handle)
        os.close(parent)


@dataclass
class _Candidate:
    root: Path
    binding: tuple[int, int]
    signature: str
    revision: str
    manifest: FieldManifest | None
    expires: float


class VaultConnectionService:
    """Use the existing folder/Source registry, never a second knowledge store.

    A folder-only connection grants read navigation but no paper identity or write
    ownership. Existing portable Sources may attach read-only after ID/path checks.
    """

    def __init__(self, environment, picker=None):
        self.environment = environment
        self.registry = KnowledgeSourceRegistry(environment.registry_path)
        self.picker = picker if picker is not None else SystemFolderPicker()
        self._candidates = {}
        self._bindings = {}
        self._lock = threading.Lock()

    def _check_environment(self):
        check = getattr(self.environment, "check_registry", None)
        if check is not None:
            check()

    def _root(self, path):
        self._check_environment()
        root = Path(path).expanduser()
        self.environment.check_root(root)
        if not root.is_absolute():
            _error("An explicitly selected absolute folder is required")
        try:
            fd = _directory(root)
        except OSError:
            _error("The selected folder is unavailable or crosses a symbolic link")
        return root, fd

    def _snapshot(self, root):
        root, fd = self._root(root)
        documents, issues, changes, inventory = [], [], [], []
        counters = {"entries": 0, "bytes": 0, "truncated": False}

        def walk(parent, prefix=(), depth=0):
            if depth > _MAX_DEPTH:
                counters["truncated"] = True
                return
            for entry in sorted(os.scandir(parent), key=lambda row: row.name):
                if entry.name.startswith("."):
                    continue
                if root.joinpath(*prefix, entry.name) == self.registry.path.parent.parent:
                    continue
                counters["entries"] += 1
                if counters["entries"] > _SCAN_ENTRIES:
                    counters["truncated"] = True
                    return
                relative = (*prefix, entry.name)
                label = PurePosixPath(*relative).as_posix()
                metadata = entry.stat(follow_symlinks=False)
                inventory.append((label, metadata.st_dev, metadata.st_ino, metadata.st_size,
                                  metadata.st_mtime_ns, metadata.st_ctime_ns, metadata.st_mode))
                if stat.S_ISLNK(metadata.st_mode):
                    issues.append({"severity": "warning", "code": "symlink-ignored",
                                   "message": "Symbolic-link content is excluded from this connection.", "path": label})
                elif stat.S_ISDIR(metadata.st_mode):
                    child = os.open(entry.name, _DIRECTORY, dir_fd=parent)
                    try:
                        if _identity(child) != (metadata.st_dev, metadata.st_ino):
                            _error("Selected folder content changed; inspect it again", 5)
                        walk(child, relative, depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(metadata.st_mode) and label.lower().endswith(".md"):
                    documents.append(label)
                    if metadata.st_size > _LIMIT or counters["bytes"] + metadata.st_size > _SCAN_BYTES:
                        issues.append({"severity": "warning", "code": "preview-limit",
                                       "message": "This document was listed but not inspected inline.", "path": label})
                        continue
                    content = _read(fd, relative)
                    counters["bytes"] += len(content)
                    inventory.append((label, hashlib.sha256(content).hexdigest()))
                    if b"127.0.0.1:23128" in content:
                        issues.append({"severity": "optional", "code": "legacy-link",
                                       "message": "An old fixed-port link needs an identity-verified replacement.", "path": label})
                        changes.append({"path": label, "operation": "review-link",
                                        "reason": "Preview a stable source link after confirming the attachment identity; original text stays intact."})
                    if b"sw-analysis-claim" in content:
                        issues.append({"severity": "optional", "code": "machine-marker",
                                       "message": "Visible machine markers should be reviewed against the accepted analysis format.", "path": label})
                        changes.append({"path": label, "operation": "review-format",
                                        "reason": "Review machine annotations without rewriting the accepted analysis or Canvas."})

        try:
            binding = _identity(fd)
            walk(fd)
            manifest, manifest_raw = None, None
            try:
                manifest_raw = _read(fd, (".scholar-workflow", "fields.yml"), limit=512 * 1024)
            except FileNotFoundError:
                pass
            except (OSError, ExplorationError):
                issues.append({"severity": "required", "code": "unsafe-manifest",
                               "message": "The portable manifest cannot be read safely; managed use remains unavailable.",
                               "path": ".scholar-workflow/fields.yml"})
            if manifest_raw is not None:
                inventory.append((".scholar-workflow/fields.yml", hashlib.sha256(manifest_raw).hexdigest()))
                try:
                    manifest = FieldManifest.model_validate(yaml.safe_load(manifest_raw))
                except (ValueError, yaml.YAMLError):
                    issues.append({"severity": "required", "code": "invalid-manifest",
                                   "message": "The portable manifest needs correction before managed paper references can be used.",
                                   "path": ".scholar-workflow/fields.yml"})
            if counters["truncated"]:
                issues.append({"severity": "warning", "code": "inspection-truncated",
                               "message": "This bounded inspection is partial; select a smaller folder for detailed preparation."})
            if manifest is None:
                invalid = any(issue["code"] in {"invalid-manifest", "unsafe-manifest"} for issue in issues)
                changes.insert(0, {"path": ".scholar-workflow/fields.yml",
                                   "operation": "review-manifest" if invalid else "plan-registration",
                                   "reason": ("Review the current invalid manifest and preserve its original bytes; managed reference is unavailable until explicitly corrected."
                                              if invalid else "Select a Field and existing entry document before creating portable registration; optional for read-only connection.")})
            signature = hashlib.sha256(json.dumps(inventory, ensure_ascii=False).encode()).hexdigest()
            return binding, signature, manifest, documents, issues, changes
        finally:
            os.close(fd)

    def _reference_layer(self, root, manifest):
        if manifest is None:
            return {"status": "needs-registration", "issues": [{"code": "ownership-not-registered",
                    "message": "Documents can be read now; paper identities require separate portable registration and owner confirmation."}]}
        document = self.registry.load_document()
        source = next((row for row in document.sources if row.source_id == manifest.source_id), None)
        folder = next((row for row in document.folders if source and row.folder_id == source.folder_id), None)
        if source is None or folder is None or folder.root != root:
            return {"status": "needs-review", "issues": [{"code": "source-not-attached",
                    "message": "Portable Fields were found; attach their existing identity read-only before checking paper ownership."}]}
        from scholar_workflow.workflows.field_paper_units import field_paper_units

        issues, count = [], 0
        for field in manifest.fields:
            try:
                # Ownership checks read declarations and metadata, not bodies or native apps.
                options = {"root_validator": self.environment.check_root} if self.environment.is_test else {}
                inventory = field_paper_units(self.registry.path, source_id=manifest.source_id,
                                              field_id=field.field_id, resolve_reader=False, **options)
                units = inventory.get("paper_units", [])
                count += len(units)
                if (inventory.get("unresolved_references") or inventory.get("issues")
                        or any(unit.get("ownership", {}).get("status") != "resolved"
                               or any(row.get("file_state") != "available" for row in unit.get("files", []))
                               for unit in units)):
                    issues.append({"code": "ownership-needs-review", "message": "Field declarations, paper ownership or asset availability need review.", "path": field.relative_root})
            except (FieldRegistryError, OSError, ValueError):
                issues.append({"code": "provider-unavailable", "message": "The existing provider declaration is unavailable or invalid; it was not initialized or replaced.", "path": field.relative_root})
        if not count:
            issues.append({"code": "no-declared-papers", "message": "No verified declared paper units are available yet; ordinary documents remain readable."})
        return {"status": "needs-review" if issues else "available", "issues": issues}

    def _report(self, root, snapshot, revision, candidate_id=None):
        _binding, _signature, manifest, documents, issues, changes = snapshot
        fields = [{"field_id": field.field_id, "title": field.title,
                   "relative_root": field.relative_root, "home": field.home}
                  for field in manifest.fields] if manifest else []
        reference_layer = self._reference_layer(root, manifest)
        if any(issue["code"] in {"invalid-manifest", "unsafe-manifest"} for issue in issues):
            reference_layer = {"status": "needs-review", "issues": [issue for issue in issues
                                if issue["code"] in {"invalid-manifest", "unsafe-manifest"}]}
        registry = self.registry.load_document()
        matches = [folder for folder in registry.folders if folder.root == root]
        blockers = []
        if len(matches) > 1:
            blockers.append("The selected folder has conflicting registered identities.")
        if matches and (not matches[0].enabled or "read" not in matches[0].capabilities):
            blockers.append("The existing connection is disabled or does not allow reading.")
        if manifest:
            source = next((row for row in registry.sources if row.source_id == manifest.source_id), None)
            if source and (not matches or source.folder_id != matches[0].folder_id):
                blockers.append("The portable Source identity is registered to another folder.")
            if matches and any(row.folder_id == matches[0].folder_id and row.source_id != manifest.source_id
                               for row in registry.sources):
                blockers.append("The selected folder already has another Source identity.")
        result = {"title": root.name, "name": root.name, "revision": revision,
                  "expected_revision": revision, "fields": fields, "documents": documents,
                  "layers": {"readable": {"status": "available", "issues": []},
                             "referenceable": reference_layer,
                             "manageable": {"status": "needs-review", "issues": [
                                 {"code": "format-not-verified", "message": "Existing accepted packages remain unchanged; a selected update requires its existing format, writer and update checks."}]}},
                  "issues": issues, "blockers": blockers, "diagnostics": [], "can_connect": not blockers,
                  "changes": [{"path": "host-registry", "operation": "connect-read-only",
                               "reason": "Record the selected folder for navigation; do not modify its documents."}, *changes]}
        if manifest:
            result["source_id"] = manifest.source_id
        if candidate_id:
            result["candidate_id"] = candidate_id
        return result

    def choose(self):
        try:
            chosen = self.picker.choose()
            snapshot = self._snapshot(chosen)
            revision = self.registry.revision()
            root = Path(chosen).expanduser()
            token = secrets.token_urlsafe(24)
            self._candidates[token] = _Candidate(root, snapshot[0], snapshot[1], revision,
                                                  snapshot[2], time.monotonic() + _TTL)
            return self._report(root, snapshot, revision, token)
        except ExplorationError:
            raise
        except (FieldRegistryError, OSError, ValueError):
            _error("Folder selection or bounded inspection failed; choose the folder again", 2)

    def _candidate(self, candidate_id):
        candidate = self._candidates.get(candidate_id) if isinstance(candidate_id, str) else None
        if candidate is None or candidate.expires < time.monotonic():
            _error("The folder selection expired; choose the folder again", 5)
        snapshot = self._snapshot(candidate.root)
        if snapshot[0] != candidate.binding or snapshot[1] != candidate.signature:
            _error("Selected folder content changed; inspect it again", 5)
        if self.registry.revision() != candidate.revision:
            _error("Source registration changed; inspect the selection again", 5)
        return candidate, snapshot

    def preview_adjustments(self, candidate_id):
        candidate, snapshot = self._candidate(candidate_id)
        return self._report(candidate.root, snapshot, candidate.revision, candidate_id)

    def connect(self, candidate_id, expected_revision):
        with self._lock:
            candidate, snapshot = self._candidate(candidate_id)
            if expected_revision != candidate.revision:
                _error("Source registration changed; inspect the selection again", 5)
            document = self.registry.load_document()
            matching = [folder for folder in document.folders if folder.root == candidate.root]
            if len(matching) > 1:
                _error("The selected folder has conflicting registered identities", 5)
            folder = matching[0] if matching else None
            manifest = candidate.manifest
            if manifest:
                existing = next((source for source in document.sources if source.source_id == manifest.source_id), None)
                if existing and (folder is None or existing.folder_id != folder.folder_id):
                    _error("The portable Source identity is registered to another folder", 5)
                if folder and any(source.folder_id == folder.folder_id and source.source_id != manifest.source_id
                                  for source in document.sources):
                    _error("The folder already has another Source identity", 5)
            changed = False
            if folder is None:
                folder_id = "obsidian-" + hashlib.sha256(str(candidate.root).encode()).hexdigest()[:16]
                if any(existing.folder_id == folder_id for existing in document.folders):
                    _error("The selected folder identifier conflicts with another registration", 5)
                folder = FolderRegistration(folder_id=folder_id, root=candidate.root, capabilities=["read"])
                document.folders.append(folder)
                changed = True
            elif not folder.enabled or "read" not in folder.capabilities:
                _error("The existing connection is disabled or does not allow reading", 7)
            if manifest and not any(source.source_id == manifest.source_id for source in document.sources):
                document.sources.append(KnowledgeSourceRegistration(source_id=manifest.source_id,
                                                                    folder_id=folder.folder_id, capabilities=["read"]))
                changed = True
            try:
                # Hold the registry lock across the last selected-tree check and CAS publication.
                with self.registry._write_guard() as parent:
                    self._candidate(candidate_id)
                    if changed:
                        self.registry._save_locked(document, parent, expected_revision=expected_revision)
                    elif self.registry._revision_at(parent) != expected_revision:
                        _error("Source registration changed; inspect the selection again", 5)
            except FieldRegistryCommitUncertain:
                _error("Connection publication may have completed; inspect current connections before retrying", 6)
            except FieldRegistryError:
                _error("Source registration changed or could not be saved safely; inspect the current connections", 5)
            self._bindings[folder.folder_id] = candidate.binding
            self._candidates.pop(candidate_id, None)
            connection = self._connection(folder, snapshot)
            return {"status": "connected" if changed else "unchanged", "connection": connection,
                    "revision": self.registry.revision()}

    def _connection(self, folder, snapshot):
        report = self._report(folder.root, snapshot, self.registry.revision())
        report.pop("can_connect", None)
        report.pop("changes", None)
        report.update(connection_id=folder.folder_id, status="available")
        return report

    def list_connections(self):
        self._check_environment()
        revision = self.registry.revision()
        document = self.registry.load_document()
        connections = []
        for folder in document.folders:
            if not folder.enabled or "read" not in folder.capabilities:
                continue
            try:
                snapshot = self._snapshot(folder.root)
                binding = self._bindings.setdefault(folder.folder_id, snapshot[0])
                if binding != snapshot[0]:
                    _error("Connected folder changed; review its registration", 5)
                connections.append(self._connection(folder, snapshot))
            except (ExplorationError, OSError, ValueError):
                connections.append({"connection_id": folder.folder_id, "title": folder.root.name,
                                    "name": folder.root.name, "status": "unavailable",
                                    "diagnostics": ["The connected folder is unavailable, changed or outside this environment."]})
        if self.registry.revision() != revision:
            _error("Source registration changed; reload the connections", 5)
        return {"revision": revision, "connections": connections}

    def _registered(self, connection_id):
        self._check_environment()
        revision = self.registry.revision()
        document = self.registry.load_document()
        folder = next((row for row in document.folders if row.folder_id == connection_id
                       and row.enabled and "read" in row.capabilities), None)
        if folder is None:
            _error("The selected connection is unknown or unavailable", 2)
        snapshot = self._snapshot(folder.root)
        if self._bindings.setdefault(folder.folder_id, snapshot[0]) != snapshot[0]:
            _error("Connected folder changed; review its registration", 5)
        if self.registry.revision() != revision:
            _error("Source registration changed; reload the connection", 5)
        return folder, snapshot, revision

    def documents(self, connection_id):
        folder, snapshot, _revision = self._registered(connection_id)
        return {"connection_id": folder.folder_id,
                "documents": [{"relative_path": path, "title": PurePosixPath(path).stem, "kind": "markdown"}
                              for path in snapshot[3]], "diagnostics": []}

    def preview_document(self, connection_id, relative_path):
        parts = _relative(relative_path)
        folder, snapshot, revision = self._registered(connection_id)
        if relative_path not in snapshot[3] or not relative_path.lower().endswith(".md"):
            _error("Only an inspected Markdown document can be previewed", 2)
        _root, fd = self._root(folder.root)
        try:
            if _identity(fd) != snapshot[0]:
                _error("Connected folder changed; inspect it again", 5)
            raw = _read(fd, parts)
        finally:
            os.close(fd)
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            _error("The selected Markdown is not valid UTF-8", 2)
        if self.registry.revision() != revision:
            _error("Source registration changed; reload the connection", 5)
        return {"text": text, "title": PurePosixPath(relative_path).stem,
                "relative_path": relative_path, "document_revision": "sha256:" + hashlib.sha256(raw).hexdigest()}
