"""Prepared synthetic ownership contracts; execute only after authorization.

Hand-written expectations precede this file in fixtures/knowledge-ownership/EXPECTED.md.
Fixture preparation uses existing models, never the new resolver's output.
"""
from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.knowledge.catalog_models import HubCatalog, HubResource
from scholar_workflow.knowledge.fields import (
    FieldDefinition,
    FieldManifest,
    FieldRegistryError,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.knowledge.models import (
    KnowledgeAtomicResource,
    KnowledgeCoreDocument,
    KnowledgeManifest,
    KnowledgeSupportingDocument,
)
from scholar_workflow.models import ResourceKind
from scholar_workflow.project.context import build_project_overview

SOURCE_A = "11111111-1111-4111-8111-111111111111"
SOURCE_B = "22222222-2222-4222-8222-222222222222"
FIELD_A = "33333333-3333-4333-8333-333333333333"
FIELD_B = "44444444-4444-4444-8444-444444444444"
PROJECT_A = "55555555-5555-4555-8555-555555555555"
PROJECT_B = "66666666-6666-4666-8666-666666666666"
PAPER = "paper:synthetic:ownership"
ANALYSIS = "analysis:paper:synthetic:ownership"
CANVAS = "analysis:paper:synthetic:ownership:canvas"
CORE = "core:synthetic:ownership"
SIDECAR = "analysis:paper:synthetic:ownership:sidecar"
OWNER_PATH = "research/resources/papers/ownership/Paper.md"
ANALYSIS_PATH = "research/resources/papers/ownership/Analysis.md"
CANVAS_PATH = "research/resources/papers/ownership/Analysis.canvas"
CORE_PATH = "research/Overview.md"
SIDECAR_PATH = "research/resources/papers/ownership/analysis.baseline.json"
PATHS = {PAPER: OWNER_PATH, ANALYSIS: ANALYSIS_PATH, CANVAS: CANVAS_PATH,
         CORE: CORE_PATH, SIDECAR: SIDECAR_PATH}
ROOT_PATHS = {
    PAPER: "resources/papers/ownership/Paper.md",
    ANALYSIS: "resources/papers/ownership/Analysis.md",
    CANVAS: "resources/papers/ownership/Analysis.canvas",
    CORE: "Overview.md",
}
DEFAULT_OVERVIEW = Path(__file__).parents[1] / "fixtures/knowledge-ownership/DEFAULT-OVERVIEW.md"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class SyntheticScope:
    temporary: Path
    root: Path
    registry: KnowledgeSourceRegistry
    provider: Path
    project: Path
    source_roots: dict[str, Path]
    fixture_writer_active: bool = False


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_source(root: Path, provider: Path, source_id: str, field_id: str,
                  *, supporting: bool = True, field_root: str = "research",
                  paths: dict[str, str] | None = None) -> None:
    """Declare legal input from existing contracts; do not derive expected answers."""
    paths = PATHS if paths is None else paths
    (root / paths[PAPER]).parent.mkdir(parents=True)
    (root / paths[PAPER]).write_text("# Synthetic ownership paper\n", encoding="utf-8")
    (root / paths[CORE]).write_text("# Synthetic reusable overview\n", encoding="utf-8")
    documents = []
    if supporting:
        (root / paths[ANALYSIS]).write_text("# Synthetic paper analysis\n", encoding="utf-8")
        (root / paths[CANVAS]).write_text('{"nodes": [], "edges": []}\n', encoding="utf-8")
        documents = [
            KnowledgeSupportingDocument(document_id=ANALYSIS, kind="analysis", title="合成分析",
                                        vault_path=paths[ANALYSIS], owner_id=PAPER),
            KnowledgeSupportingDocument(document_id=CANVAS, kind="analysis_canvas", title="合成解析树",
                                        vault_path=paths[CANVAS], owner_id=PAPER),
        ]
    fields = FieldManifest(
        source_id=source_id,
        fields=[FieldDefinition(field_id=field_id, title="合成研究领域", relative_root=field_root,
                                home="Overview.md")],
    )
    manifest_path = root / ".scholar-workflow/fields.yml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(yaml.safe_dump(fields.model_dump(mode="json"), allow_unicode=True),
                             encoding="utf-8")
    manifest = KnowledgeManifest(
        atomic_resources=[KnowledgeAtomicResource(resource_id=PAPER, kind=ResourceKind.PAPER,
                                                  title="合成论文", markdown_path=paths[PAPER])],
        core_documents=[KnowledgeCoreDocument(document_id=CORE, kind="catalog", title="合成纲领",
                                              markdown_path=paths[CORE])],
        supporting_documents=documents,
    )
    info = root.stat()
    snapshot = KnowledgeProviderSnapshot(
        vault_binding={"root_path": str(root), "device": info.st_dev, "inode": info.st_ino},
        manifest=manifest,
        catalog=HubCatalog(generated_at=NOW, resources=[HubResource(resource_id=PAPER,
                                                                   kind=ResourceKind.PAPER,
                                                                   title="合成论文")]),
    )
    _write_json(provider, snapshot.model_dump(mode="json"))


def _external(entry_id: str, object_id: str, *, provider: str = "obsidian",
              paths: dict[str, str] | None = None) -> dict:
    paths = PATHS if paths is None else paths
    kind = "note" if object_id in {PAPER, CORE} else "analysis"
    title = {PAPER: "论文资料笔记", ANALYSIS: "共享论文分析", CANVAS: "共享解析树",
             CORE: "共享纲领", SIDECAR: "共享分析快照"}.get(object_id, "明确选定的知识")
    uri = ("obsidian://open?vault=synthetic&file=" + quote(paths.get(object_id, "Unknown.md"), safe="")
           if provider == "obsidian" else "zotero://select/library/items/ABCD2345")
    return {"entry_id": entry_id, "kind": kind, "title": title, "purpose": "用于该项目的研究上下文。",
            "ref": {"kind": "external-resource", "provider": provider,
                    "resource_id": object_id, "uri": uri}}


def _write_project(root: Path, project_id: str, *, objects: tuple[str, ...] = (PAPER, ANALYSIS, CANVAS),
                   paths: dict[str, str] | None = None) -> Path:
    root.mkdir()
    (root / "code.py").write_text("# Synthetic project code\n", encoding="utf-8")
    _write_json(root / "project-layout.json", {"schema_version": 2, "project_id": project_id,
                                               "language": "python", "package": None,
                                               "source_profile": None, "addons": []})
    entries = [_external(f"knowledge-{index}", object_id, paths=paths)
               for index, object_id in enumerate(objects)]
    entries.extend([
        {"entry_id": "code", "kind": "code", "title": "项目代码", "purpose": "项目自身的代码。",
         "ref": {"kind": "project-file", "relative_path": "code.py"}},
        _external("pdf", "zotero:synthetic:attachment", provider="zotero"),
    ])
    _write_json(root / "project-context.json", {"schema_version": 1, "project_id": project_id,
                                                "title": "合成项目", "summary": "显式复用一份知识。",
                                                "language": "zh", "entries": entries})
    return root


@pytest.fixture
def ownership_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SyntheticScope:
    # pytest may expose a macOS temporary path through /var or /tmp symlinks.
    # The fixture root is canonical; only each deliberately introduced link is unsafe.
    tmp_path = tmp_path.resolve(strict=True)
    root = tmp_path / "source-a"
    registry = KnowledgeSourceRegistry(tmp_path / "state/sources.json")
    provider = registry.path.parent / "knowledge-providers" / SOURCE_A / "knowledge-provider.snapshot.json"
    _write_source(root, provider, SOURCE_A, FIELD_A)
    document = KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="synthetic-a", root=root, capabilities=["read"])],
        sources=[KnowledgeSourceRegistration(source_id=SOURCE_A, folder_id="synthetic-a",
                                             capabilities=["read"])],
    )
    _write_json(registry.path, document.model_dump(mode="json"))
    project = _write_project(tmp_path / "project-a", PROJECT_A)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Synthetic ownership inspection accessed config, an app, network, or execution")

    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "unused-home"))
    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    monkeypatch.setattr(cli, "_zotero_adapter", forbidden)
    monkeypatch.setattr(cli, "_local_field_service", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli.webbrowser, "open", forbidden)
    monkeypatch.setattr("scholar_workflow.adapters.obsidian_registry.resolve_obsidian_reader", forbidden)
    monkeypatch.setattr("scholar_workflow.adapters.obsidian_registry.resolve_obsidian_reader_vault_id", forbidden)
    return SyntheticScope(tmp_path, root, registry, provider, project, {SOURCE_A: root})


def _filesystem(root: Path) -> dict:
    """Inventory fixture bytes and links without following symlink targets."""
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                result[relative] = ("symlink", os.readlink(path))
            elif stat.S_ISDIR(mode):
                result[relative] = ("directory",)
            elif stat.S_ISREG(mode):
                result[relative] = ("file", path.read_bytes())
            else:
                result[relative] = ("special", mode)
    return result


def _plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    return dict(value)


@contextmanager
def _inspection_guard(scope: SyntheticScope, *, project: Path | None = None,
                      context_file: str | None = None):
    """Permit exact declaration reads; deny every other body and production write."""
    allowed_paths = {scope.registry.path.absolute()}
    for source_id, root in scope.source_roots.items():
        allowed_paths.add((root / ".scholar-workflow/fields.yml").absolute())
        allowed_paths.add((scope.registry.path.parent / "knowledge-providers" / source_id
                           / "knowledge-provider.snapshot.json").absolute())
    if project is not None:
        allowed_paths.update((project / name).absolute()
                             for name in ("project-layout.json", "project-context.json"))
        if context_file is not None:
            allowed_paths.add((project / context_file).absolute())
    # Track the named origin of descriptor-relative opens. In particular, a .json
    # artifact is not readable merely because declarations also have that suffix.
    descriptor_paths: dict[int, Path] = {}

    def denied(message):
        pytest.fail("Read-only Knowledge ownership inspection " + message)

    original_builtin_open = builtins.open
    original_io_open = io.open
    original_os_open = os.open
    original_close = os.close
    original_fdopen = os.fdopen
    original_read = os.read

    def named_path(value, *, dir_fd=None):
        if not isinstance(value, (str, bytes, os.PathLike)):
            return None
        path = Path(os.fsdecode(value))
        if path.is_absolute():
            return path.absolute()
        if dir_fd is not None:
            parent = descriptor_paths.get(dir_fd)
            return None if parent is None else (parent / path).absolute()
        return path.absolute()

    def require_declaration_descriptor(descriptor):
        if scope.fixture_writer_active:
            return
        if descriptor_paths.get(descriptor) not in allowed_paths:
            denied("attempted to read non-declaration file content")
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            denied("attempted to read a non-regular declaration")

    def require_declaration_file(file):
        if isinstance(file, int):
            require_declaration_descriptor(file)
            return
        path = named_path(file)
        if path not in allowed_paths:
            denied("attempted to read non-declaration file content")
        # No stream open may block on a FIFO or dereference a declaration leaf
        # symlink; low-level metadata opens remain permitted below.
        if not stat.S_ISREG(path.lstat().st_mode):
            denied("attempted to read a non-regular declaration")

    def checked_stream_open(original):
        def open_stream(file, mode="r", *args, **kwargs):
            if not scope.fixture_writer_active and any(char in mode for char in "wax+"):
                denied("attempted a file write")
            if not scope.fixture_writer_active:
                require_declaration_file(file)
            return original(file, mode, *args, **kwargs)
        return open_stream

    def checked_os_open(path, flags, *args, **kwargs):
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if writing and not scope.fixture_writer_active:
            denied("attempted a writable file descriptor or lock")
        try:
            info = os.stat(path, dir_fd=kwargs.get("dir_fd"), follow_symlinks=False)
        except OSError:
            info = None
        if info is not None and stat.S_ISFIFO(info.st_mode) and not flags & os.O_NONBLOCK:
            denied("attempted a blocking FIFO open")
        descriptor = original_os_open(path, flags, *args, **kwargs)
        declared_path = named_path(path, dir_fd=kwargs.get("dir_fd"))
        if declared_path is not None:
            descriptor_paths[descriptor] = declared_path
        return descriptor

    def checked_close(descriptor):
        descriptor_paths.pop(descriptor, None)
        return original_close(descriptor)

    def checked_fdopen(descriptor, mode="r", *args, **kwargs):
        if not scope.fixture_writer_active and any(char in mode for char in "wax+"):
            denied("attempted a writable content stream")
        require_declaration_descriptor(descriptor)
        return original_fdopen(descriptor, mode, *args, **kwargs)

    def checked_read(descriptor, *args, **kwargs):
        require_declaration_descriptor(descriptor)
        return original_read(descriptor, *args, **kwargs)

    def checked_mutation(original):
        def mutate(*args, **kwargs):
            if not scope.fixture_writer_active:
                denied("attempted a filesystem mutation")
            return original(*args, **kwargs)
        return mutate

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builtins, "open", checked_stream_open(original_builtin_open))
        patch.setattr(io, "open", checked_stream_open(original_io_open))
        patch.setattr(os, "open", checked_os_open)
        patch.setattr(os, "close", checked_close)
        patch.setattr(os, "fdopen", checked_fdopen)
        patch.setattr(os, "read", checked_read)
        if hasattr(os, "pread"):
            original_pread = os.pread

            def checked_pread(descriptor, *args, **kwargs):
                require_declaration_descriptor(descriptor)
                return original_pread(descriptor, *args, **kwargs)

            patch.setattr(os, "pread", checked_pread)
        if hasattr(os, "readv"):
            original_readv = os.readv

            def checked_readv(descriptor, *args, **kwargs):
                require_declaration_descriptor(descriptor)
                return original_readv(descriptor, *args, **kwargs)

            patch.setattr(os, "readv", checked_readv)
        for name in ("mkdir", "makedirs", "unlink", "remove", "rmdir", "rename", "replace", "symlink", "link",
                     "chmod", "fchmod", "truncate", "ftruncate", "utime", "mkfifo", "mknod"):
            if hasattr(os, name):
                patch.setattr(os, name, checked_mutation(getattr(os, name)))
        yield


def _resolve(scope: SyntheticScope, *, project: Path | None = None) -> dict:
    from scholar_workflow.workflows.knowledge_ownership import resolve_project_knowledge

    overview = build_project_overview(project or scope.project)
    original = overview.model_dump(mode="json")
    before = _filesystem(scope.temporary)
    try:
        with _inspection_guard(scope):
            result = resolve_project_knowledge(overview, scope.registry.path)
        return {entry_id: _plain(value) for entry_id, value in result.items()}
    finally:
        assert overview.model_dump(mode="json") == original
        assert _filesystem(scope.temporary) == before


def _invoke(scope: SyntheticScope, *options: str):
    # Preload the workflow before guarding production I/O, including isolated CLI tests.
    from scholar_workflow.workflows import knowledge_ownership  # noqa: F401

    context_file = None
    if "--context-file" in options:
        context_file = options[options.index("--context-file") + 1]
    before = _filesystem(scope.temporary)
    with _inspection_guard(scope, project=scope.project, context_file=context_file):
        result = CliRunner().invoke(cli.main, ["project", "overview", "--project-root", str(scope.project), *options])
    assert _filesystem(scope.temporary) == before
    return result


def _expected_location(object_id: str, *, source_id: str = SOURCE_A, field_id: str = FIELD_A,
                       file_state: str = "available", paths: dict[str, str] | None = None) -> dict:
    paths = PATHS if paths is None else paths
    owner_id = CORE if object_id == CORE else PAPER
    return {"source_id": source_id, "field_id": field_id, "field_title": "合成研究领域",
            "object_id": object_id, "owner_id": owner_id, "relative_path": paths[object_id],
            "owner_path": paths[owner_id], "file_state": file_state}


def _assert_location(actual, expected: dict) -> None:
    row = _plain(actual)
    assert {key: row[key] for key in expected} == expected


def _assert_resolution(row: dict, object_id: str, status: str) -> None:
    assert row["object_id"] == object_id
    assert row["status"] == status
    assert row["reader_state"] == "unverified"
    assert isinstance(row["locations"], list)
    assert isinstance(row["owner_candidates"], list)
    assert isinstance(row["issues"], list)
    for issue in row["issues"]:
        issue = _plain(issue)
        assert "source_id" in issue
        assert isinstance(issue["code"], str) and issue["code"]


def _add_source(scope: SyntheticScope, *, supporting: bool = True) -> Path:
    root = scope.temporary / "source-b"
    provider = scope.registry.path.parent / "knowledge-providers" / SOURCE_B / "knowledge-provider.snapshot.json"
    _write_source(root, provider, SOURCE_B, FIELD_B, supporting=supporting)
    document = scope.registry.load_document()
    document.folders.append(FolderRegistration(folder_id="synthetic-b", root=root, capabilities=["read"]))
    document.sources.append(KnowledgeSourceRegistration(source_id=SOURCE_B, folder_id="synthetic-b",
                                                        capabilities=["read"]))
    _write_json(scope.registry.path, document.model_dump(mode="json"))
    scope.source_roots[SOURCE_B] = root
    return provider


def _declare_artifact_only_sidecar(scope: SyntheticScope) -> Path:
    """Add one valid sidecar input, absent from manifest and human catalog."""
    sidecar = scope.root / SIDECAR_PATH
    content = b'{"synthetic": "sidecar body must not be read"}\n'
    sidecar.write_bytes(content)
    value = json.loads(scope.provider.read_text(encoding="utf-8"))
    value["artifacts"].append({
        "artifact_id": SIDECAR, "resource_id": PAPER, "kind": "analysis_sidecar",
        "vault_path": SIDECAR_PATH, "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
    })
    value["snapshot_revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(value)
    assert all(row.document_id != SIDECAR for row in snapshot.manifest.supporting_documents)
    assert all(row.artifact_id != SIDECAR for row in snapshot.catalog.artifacts)
    _write_json(scope.provider, snapshot.model_dump(mode="json"))
    return sidecar


@pytest.mark.parametrize("object_id", [PAPER, ANALYSIS, CANVAS, CORE])
def test_unique_primary_and_supporting_ownership(ownership_scope, object_id):
    scope = ownership_scope
    project = _write_project(scope.temporary / "selected", PROJECT_B, objects=(object_id,))
    row = _resolve(scope, project=project)["knowledge-0"]
    _assert_resolution(row, object_id, "resolved")
    assert row["issues"] == []
    assert len(row["locations"]) == len(row["owner_candidates"]) == 1
    _assert_location(row["locations"][0], _expected_location(object_id))
    owner_id = CORE if object_id == CORE else PAPER
    _assert_location(row["owner_candidates"][0], _expected_location(owner_id))


@pytest.mark.parametrize("object_id", [PAPER, ANALYSIS, CANVAS, CORE])
def test_root_field_uses_actual_source_relative_paths(ownership_scope, object_id):
    scope = ownership_scope
    root = scope.temporary / "source-root-field"
    _write_source(root, scope.provider, SOURCE_A, FIELD_A, field_root=".", paths=ROOT_PATHS)
    document = scope.registry.load_document()
    document.folders[0].root = root
    _write_json(scope.registry.path, document.model_dump(mode="json"))
    scope.root = root
    scope.source_roots[SOURCE_A] = root
    project = _write_project(scope.temporary / "root-field-project", PROJECT_B,
                             objects=(object_id,), paths=ROOT_PATHS)
    assert not (root / "research").exists()
    row = _resolve(scope, project=project)["knowledge-0"]
    _assert_resolution(row, object_id, "resolved")
    assert row["issues"] == []
    assert len(row["locations"]) == len(row["owner_candidates"]) == 1
    _assert_location(row["locations"][0], _expected_location(object_id, paths=ROOT_PATHS))
    owner_id = CORE if object_id == CORE else PAPER
    _assert_location(row["owner_candidates"][0], _expected_location(owner_id, paths=ROOT_PATHS))


@pytest.mark.parametrize("state", ["available", "missing", "unsafe", "conflict"])
def test_artifact_only_sidecar_keeps_explicit_primary_ownership(ownership_scope, state):
    scope = ownership_scope
    sidecar = _declare_artifact_only_sidecar(scope)
    if state == "missing":
        sidecar.unlink()
    elif state == "unsafe":
        sidecar.unlink()
        outside = scope.temporary / "outside-sidecar.json"
        outside.write_bytes(b'{"not": "Knowledge authority"}\n')
        sidecar.symlink_to(outside)
    elif state == "conflict":
        _add_source(scope, supporting=False)
    project = _write_project(scope.temporary / "sidecar-project", PROJECT_B, objects=(SIDECAR,))
    row = _resolve(scope, project=project)["knowledge-0"]
    _assert_resolution(row, SIDECAR, "conflict" if state == "conflict" else "resolved")
    assert len(row["locations"]) == 1
    file_state = state if state in {"missing", "unsafe"} else "available"
    _assert_location(row["locations"][0], _expected_location(SIDECAR, file_state=file_state))
    owners = {_plain(location)["source_id"]: location for location in row["owner_candidates"]}
    assert set(owners) == ({SOURCE_A, SOURCE_B} if state == "conflict" else {SOURCE_A})
    _assert_location(owners[SOURCE_A], _expected_location(PAPER))
    if state == "conflict":
        _assert_location(owners[SOURCE_B], _expected_location(PAPER, source_id=SOURCE_B, field_id=FIELD_B))
    else:
        assert row["issues"] == []


def test_two_projects_reuse_the_same_owner_without_copy(ownership_scope):
    scope = ownership_scope
    second = _write_project(scope.temporary / "project-b", PROJECT_B)
    first_result = _resolve(scope)
    second_result = _resolve(scope, project=second)
    assert first_result == second_result
    assert set(first_result) == {"knowledge-0", "knowledge-1", "knowledge-2"}
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        row = first_result[f"knowledge-{index}"]
        _assert_resolution(row, object_id, "resolved")
        _assert_location(row["locations"][0], _expected_location(object_id))
    assert not (scope.project / "research").exists() and not (second / "research").exists()


def test_unknown_identity_is_not_found_without_filename_guessing(ownership_scope):
    scope = ownership_scope
    unknown = "paper:synthetic:unknown"
    (scope.root / "research/Unknown.md").write_text("# Similar title is not identity\n", encoding="utf-8")
    project = _write_project(scope.temporary / "unknown-project", PROJECT_B, objects=(unknown,))
    row = _resolve(scope, project=project)["knowledge-0"]
    _assert_resolution(row, unknown, "not_found")
    assert row["locations"] == row["owner_candidates"] == []


def test_only_obsidian_external_entries_are_resolved(ownership_scope):
    result = _resolve(ownership_scope)
    assert set(result) == {"knowledge-0", "knowledge-1", "knowledge-2"}
    assert "pdf" not in result and "code" not in result


def test_missing_target_leaf_keeps_identity_but_reports_missing(ownership_scope):
    scope = ownership_scope
    (scope.root / ANALYSIS_PATH).unlink()
    row = _resolve(scope)["knowledge-1"]
    _assert_resolution(row, ANALYSIS, "resolved")
    _assert_location(row["locations"][0], _expected_location(ANALYSIS, file_state="missing"))
    _assert_location(row["owner_candidates"][0], _expected_location(PAPER))


@pytest.mark.parametrize("member", ["leaf", "ancestor"])
def test_target_symlink_is_unsafe_and_never_followed(ownership_scope, member):
    scope = ownership_scope
    if member == "leaf":
        target = scope.root / ANALYSIS_PATH
        target.unlink()
        outside = scope.temporary / "outside-analysis.md"
        outside.write_bytes(b"outside bytes must never become Knowledge authority\n")
        target.symlink_to(outside)
    else:
        original = scope.root / "research/resources/papers/ownership"
        outside = scope.temporary / "outside-paper-directory"
        original.rename(outside)
        original.symlink_to(outside, target_is_directory=True)
    row = _resolve(scope)["knowledge-1"]
    _assert_resolution(row, ANALYSIS, "resolved")
    _assert_location(row["locations"][0], _expected_location(ANALYSIS, file_state="unsafe"))


@pytest.mark.parametrize("state", ["missing", "unsafe"])
def test_primary_owner_file_state_is_separate_from_analysis_state(ownership_scope, state):
    scope = ownership_scope
    owner = scope.root / OWNER_PATH
    owner.unlink()
    if state == "unsafe":
        outside = scope.temporary / "outside-owner.md"
        outside.write_bytes(b"external owner bytes\n")
        owner.symlink_to(outside)
    row = _resolve(scope)["knowledge-1"]
    _assert_resolution(row, ANALYSIS, "resolved")
    _assert_location(row["locations"][0], _expected_location(ANALYSIS))
    _assert_location(row["owner_candidates"][0], _expected_location(PAPER, file_state=state))


@pytest.mark.parametrize("member", ["analysis", "primary", "registry", "fields", "provider"])
@pytest.mark.parametrize("file_kind", ["directory", "fifo"])
def test_non_regular_objects_and_declarations_fail_without_blocking(ownership_scope, member, file_kind):
    scope = ownership_scope
    target = {
        "analysis": scope.root / ANALYSIS_PATH, "primary": scope.root / OWNER_PATH,
        "registry": scope.registry.path, "fields": scope.root / ".scholar-workflow/fields.yml",
        "provider": scope.provider,
    }[member]
    # Fixture-only replacement happens before production inventory and read guard.
    target.unlink()
    if file_kind == "directory":
        target.mkdir()
    else:
        os.mkfifo(target, 0o600)
    result = _resolve(scope)
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        row = result[f"knowledge-{index}"]
        if member in {"registry", "fields", "provider"}:
            _assert_resolution(row, object_id, "incomplete")
            expected_source = None if member == "registry" else SOURCE_A
            assert any(_plain(issue)["source_id"] == expected_source for issue in row["issues"])
        else:
            _assert_resolution(row, object_id, "resolved")
            assert row["issues"] == []
            unsafe_object = ANALYSIS if member == "analysis" else PAPER
            state = "unsafe" if object_id == unsafe_object else "available"
            _assert_location(row["locations"][0], _expected_location(object_id, file_state=state))
            owner_state = "unsafe" if member == "primary" else "available"
            _assert_location(row["owner_candidates"][0], _expected_location(PAPER, file_state=owner_state))


@pytest.mark.parametrize("object_id", [PAPER, ANALYSIS, CANVAS])
def test_primary_owner_conflict_across_sources_even_when_support_is_unique(ownership_scope, object_id):
    scope = ownership_scope
    _add_source(scope, supporting=False)
    project = _write_project(scope.temporary / "conflict-project", PROJECT_B, objects=(object_id,))
    row = _resolve(scope, project=project)["knowledge-0"]
    _assert_resolution(row, object_id, "conflict")
    assert len(row["owner_candidates"]) == 2
    owners = {_plain(location)["source_id"]: location for location in row["owner_candidates"]}
    _assert_location(owners[SOURCE_A], _expected_location(PAPER))
    _assert_location(owners[SOURCE_B], _expected_location(PAPER, source_id=SOURCE_B, field_id=FIELD_B))
    if object_id != PAPER:
        assert len(row["locations"]) == 1
        _assert_location(row["locations"][0], _expected_location(object_id))


@pytest.mark.parametrize("change", ["provider-missing", "provider-invalid", "provider-duplicate-json",
                                    "binding", "disabled", "field-source"])
def test_unverifiable_registered_source_is_incomplete(ownership_scope, change):
    scope = ownership_scope
    if change == "provider-missing":
        scope.provider.unlink()
    elif change == "provider-invalid":
        scope.provider.write_text("{invalid JSON\n", encoding="utf-8")
    elif change == "provider-duplicate-json":
        text = scope.provider.read_text(encoding="utf-8")
        scope.provider.write_text('{"schema_version": 99, ' + text[1:], encoding="utf-8")
    elif change == "binding":
        value = json.loads(scope.provider.read_text(encoding="utf-8"))
        value["vault_binding"]["root_path"] = str(scope.temporary / "different-source")
        value["snapshot_revision"] = ""
        legal_but_foreign = KnowledgeProviderSnapshot.model_validate(value)
        _write_json(scope.provider, legal_but_foreign.model_dump(mode="json"))
    elif change == "disabled":
        document = scope.registry.load_document()
        document.sources[0].enabled = False
        _write_json(scope.registry.path, document.model_dump(mode="json"))
    else:
        path = scope.root / ".scholar-workflow/fields.yml"
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        value["source_id"] = SOURCE_B
        path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
    result = _resolve(scope)
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        row = result[f"knowledge-{index}"]
        _assert_resolution(row, object_id, "incomplete")
        assert any(_plain(issue)["source_id"] == SOURCE_A for issue in row["issues"])


def test_broken_second_source_does_not_make_first_owner_resolved(ownership_scope):
    scope = ownership_scope
    second_provider = _add_source(scope, supporting=False)
    second_provider.unlink()
    row = _resolve(scope)["knowledge-1"]
    _assert_resolution(row, ANALYSIS, "incomplete")
    assert any(_plain(issue)["source_id"] == SOURCE_B for issue in row["issues"])


def test_known_primary_conflict_has_priority_over_incomplete_source(ownership_scope):
    scope = ownership_scope
    _add_source(scope, supporting=False)
    source_c = "77777777-7777-4777-8777-777777777777"
    third_root = scope.temporary / "source-c"
    third_root.mkdir()
    document = scope.registry.load_document()
    document.folders.append(FolderRegistration(folder_id="synthetic-c", root=third_root))
    document.sources.append(KnowledgeSourceRegistration(source_id=source_c, folder_id="synthetic-c"))
    _write_json(scope.registry.path, document.model_dump(mode="json"))
    scope.source_roots[source_c] = third_root
    row = _resolve(scope)["knowledge-1"]
    _assert_resolution(row, ANALYSIS, "conflict")
    assert {_plain(owner)["source_id"] for owner in row["owner_candidates"]} == {SOURCE_A, SOURCE_B}
    assert any(_plain(issue)["source_id"] == source_c for issue in row["issues"])


def test_duplicate_registry_json_keys_never_select_last_value(ownership_scope):
    scope = ownership_scope
    text = scope.registry.path.read_text(encoding="utf-8")
    scope.registry.path.write_text('{"sources": [], ' + text[1:], encoding="utf-8")
    try:
        result = _resolve(scope)
    except (FieldRegistryError, ValueError):
        return
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        _assert_resolution(result[f"knowledge-{index}"], object_id, "incomplete")
        assert result[f"knowledge-{index}"]["issues"]


@pytest.mark.parametrize("chain", ["registry", "source", "provider"])
def test_intermediate_authority_symlink_fails_closed(ownership_scope, chain):
    scope = ownership_scope
    expected_source = SOURCE_A
    if chain == "registry":
        storage = scope.temporary / "registry-storage"
        storage.mkdir()
        scope.registry.path.parent.rename(storage / "inner")
        route = scope.temporary / "registry-route"
        route.symlink_to(storage, target_is_directory=True)
        scope.registry = KnowledgeSourceRegistry(route / "inner/sources.json")
        assert not scope.registry.path.parent.is_symlink()
        expected_source = None
    elif chain == "source":
        storage = scope.temporary / "source-storage"
        storage.mkdir()
        actual_root = storage / "inner"
        document = scope.registry.load_document()
        scope.root.rename(actual_root)
        route = scope.temporary / "source-route"
        route.symlink_to(storage, target_is_directory=True)
        declared_root = route / "inner"
        assert not declared_root.is_symlink()
        document.folders[0].root = declared_root
        _write_json(scope.registry.path, document.model_dump(mode="json"))
        value = json.loads(scope.provider.read_text(encoding="utf-8"))
        info = actual_root.stat()
        value["vault_binding"] = {"root_path": str(actual_root), "device": info.st_dev, "inode": info.st_ino}
        value["snapshot_revision"] = ""
        matching_resolved_binding = KnowledgeProviderSnapshot.model_validate(value)
        _write_json(scope.provider, matching_resolved_binding.model_dump(mode="json"))
        scope.root = declared_root
        scope.source_roots[SOURCE_A] = declared_root
    else:
        base = scope.registry.path.parent / "knowledge-providers"
        storage = scope.temporary / "provider-storage"
        base.rename(storage)
        base.symlink_to(storage, target_is_directory=True)
        assert not scope.provider.parent.is_symlink()
    result = _resolve(scope)
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        row = result[f"knowledge-{index}"]
        _assert_resolution(row, object_id, "incomplete")
        assert any(_plain(issue)["source_id"] == expected_source for issue in row["issues"])


@pytest.mark.parametrize("ambiguity", ["alias", "duplicate-key"])
def test_field_yaml_ambiguity_never_establishes_ownership(ownership_scope, ambiguity):
    scope = ownership_scope
    path = scope.root / ".scholar-workflow/fields.yml"
    text = path.read_text(encoding="utf-8")
    if ambiguity == "alias":
        assert "home: Overview.md" in text and "title: 合成研究领域" in text
        text = text.replace("home: Overview.md", "home: &home Overview.md", 1)
        text = text.replace("title: 合成研究领域", "title: *home", 1)
    else:
        text = "source_id: " + SOURCE_B + "\n" + text
    path.write_text(text, encoding="utf-8")
    result = _resolve(scope)
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        row = result[f"knowledge-{index}"]
        _assert_resolution(row, object_id, "incomplete")
        assert any(_plain(issue)["source_id"] == SOURCE_A for issue in row["issues"])


@pytest.mark.parametrize("declaration", ["registry", "fields", "provider"])
def test_declaration_replaced_during_read_is_incomplete_without_resolver_writes(
    ownership_scope, monkeypatch, declaration,
):
    scope = ownership_scope
    target = {"registry": scope.registry.path, "fields": scope.root / ".scholar-workflow/fields.yml",
              "provider": scope.provider}[declaration]
    original_bytes = target.read_bytes()
    original_identity = (target.stat().st_dev, target.stat().st_ino)
    original_fdopen = os.fdopen
    injected = []

    class ConcurrentReplacementStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def read(self, *args, **kwargs):
            content = self.stream.read(*args, **kwargs)
            if not injected:
                # Only this fixture hook models an independent writer. Production
                # mutation APIs remain denied before and after this operation.
                replacement = target.with_name(target.name + ".fixture-replacement")
                scope.fixture_writer_active = True
                try:
                    replacement.write_bytes(original_bytes)
                    replacement.replace(target)
                finally:
                    scope.fixture_writer_active = False
                injected.append(True)
            return content

    def racing_fdopen(descriptor, *args, **kwargs):
        info = os.fstat(descriptor)
        stream = original_fdopen(descriptor, *args, **kwargs)
        if (info.st_dev, info.st_ino) == original_identity:
            return ConcurrentReplacementStream(stream)
        return stream

    monkeypatch.setattr(os, "fdopen", racing_fdopen)
    result = _resolve(scope)
    assert injected == [True]
    assert target.read_bytes() == original_bytes
    assert not target.with_name(target.name + ".fixture-replacement").exists()
    expected_source = None if declaration == "registry" else SOURCE_A
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        row = result[f"knowledge-{index}"]
        _assert_resolution(row, object_id, "incomplete")
        assert any(_plain(issue)["source_id"] == expected_source for issue in row["issues"])


def test_default_overview_never_accesses_registry_and_keeps_old_output(ownership_scope, monkeypatch):
    from scholar_workflow.workflows import knowledge_ownership

    scope = ownership_scope

    def forbidden(*_args, **_kwargs):
        pytest.fail("Default project overview accessed Knowledge ownership or a registry")

    monkeypatch.setattr(knowledge_ownership, "resolve_project_knowledge", forbidden)
    monkeypatch.setattr(KnowledgeSourceRegistry, "load_document", forbidden)
    baseline = build_project_overview(scope.project)
    json_result = _invoke(scope, "--json")
    assert json_result.exit_code == 0, json_result.output
    assert json.loads(json_result.output) == baseline.model_dump(mode="json")
    markdown_result = _invoke(scope)
    assert markdown_result.exit_code == 0, markdown_result.output
    assert markdown_result.output == DEFAULT_OVERVIEW.read_text(encoding="utf-8")
    assert "knowledge_ownership" not in json_result.output
    assert "归属:" not in markdown_result.output


def test_explicit_cli_json_adds_ownership_without_changing_entry_refs_or_state(ownership_scope):
    scope = ownership_scope
    original = build_project_overview(scope.project).model_dump(mode="json")
    result = _invoke(scope, "--resolve-knowledge", "--knowledge-registry", str(scope.registry.path), "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    ownership = payload.pop("knowledge_ownership")
    assert payload == original
    assert set(ownership) == {"knowledge-0", "knowledge-1", "knowledge-2"}
    for index, object_id in enumerate((PAPER, ANALYSIS, CANVAS)):
        _assert_resolution(ownership[f"knowledge-{index}"], object_id, "resolved")
        _assert_location(ownership[f"knowledge-{index}"]["locations"][0], _expected_location(object_id))
        assert payload["entries"][index]["state"] == "unverified"
        assert payload["entries"][index]["ref"] == original["entries"][index]["ref"]


def test_explicit_chinese_markdown_separates_owner_file_and_unverified_reader(ownership_scope):
    scope = ownership_scope
    result = _invoke(scope, "--resolve-knowledge", "--knowledge-registry", str(scope.registry.path),
                     "--language", "zh")
    assert result.exit_code == 0, result.output
    section = result.output.split("### [共享论文分析]", 1)[1].split("### ", 1)[0]
    assert "归属" in section and "合成研究领域" in section
    assert "文件" in section and "阅读器" in section
    assert "未核验" in section
    for hidden in (SOURCE_A, FIELD_A, PROJECT_A, PAPER, ANALYSIS, CANVAS, str(scope.root),
                   str(scope.registry.path), str(scope.project)):
        assert hidden not in result.output


@pytest.mark.parametrize("state,marker", [("missing", "缺失"), ("unsafe", "不安全")])
def test_chinese_markdown_explicitly_reports_primary_owner_file_failure(ownership_scope, state, marker):
    scope = ownership_scope
    owner = scope.root / OWNER_PATH
    owner.unlink()
    if state == "unsafe":
        outside = scope.temporary / "outside-owner.md"
        outside.write_bytes(b"fixture owner outside its declared location\n")
        owner.symlink_to(outside)
    result = _invoke(scope, "--resolve-knowledge", "--knowledge-registry", str(scope.registry.path),
                     "--language", "zh")
    assert result.exit_code == 0, result.output
    section = result.output.split("### [共享论文分析]", 1)[1].split("### ", 1)[0]
    assert re.search(r"(?:主归属|主资源|主文档|owner)[^\n]*" + marker, section)
    assert re.search(r"文件[:：][^\n]*(?:本地可定位|可定位|可用|存在)", section)
    assert "阅读器" in section and "未核验" in section
    for hidden in (SOURCE_A, FIELD_A, PROJECT_A, PAPER, ANALYSIS, CANVAS, str(scope.root),
                   str(scope.registry.path), str(scope.project)):
        assert hidden not in result.output


def test_registry_option_requires_explicit_resolution_without_access(ownership_scope, monkeypatch):
    from scholar_workflow.workflows import knowledge_ownership

    def forbidden(*_args, **_kwargs):
        pytest.fail("Unpaired registry option attempted ownership resolution")

    monkeypatch.setattr(knowledge_ownership, "resolve_project_knowledge", forbidden)
    monkeypatch.setattr(KnowledgeSourceRegistry, "load_document", forbidden)
    result = _invoke(ownership_scope, "--knowledge-registry", str(ownership_scope.registry.path))
    assert result.exit_code == 2


def test_explicit_missing_registry_is_input_error_and_never_created(ownership_scope):
    scope = ownership_scope
    absent = scope.temporary / "absent-state/sources.json"
    result = _invoke(scope, "--resolve-knowledge", "--knowledge-registry", str(absent), "--json")
    assert result.exit_code == 2
    assert not absent.exists() and not absent.parent.exists()
