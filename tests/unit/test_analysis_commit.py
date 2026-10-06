from __future__ import annotations

import json
import multiprocessing
import queue
import struct
import zlib
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from scholar_workflow.analysis.apply_changes import (
    apply_knowledge_change_set,
    initialize_knowledge_provider_snapshot,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.commit import (
    AnalysisCommitConflict,
    AnalysisCommitError,
    AnalysisCommitPartialError,
    AnalysisCommitSafetyError,
    _request_fingerprint,
    commit_analysis_bundle,
)
from scholar_workflow.analysis.models import (
    ALL_ROLES,
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeArtifactChange,
    KnowledgeAtomicResource,
    KnowledgeManifest,
    KnowledgeProjection,
    KnowledgeRelation,
    KnowledgeSupportingDocument,
    ProfileKind,
    SupportingDocumentKind,
)
from scholar_workflow.analysis.updates import render_analysis_projection
from scholar_workflow.hub.fields import (
    FieldDefinition,
    FieldManifest,
    FieldNavigationGroup,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.models import HubCatalog, HubResource, ZoteroLink
from scholar_workflow.hub.zotflow import ZotFlowError
from scholar_workflow.models import ResourceKind

_V4_SOURCE_ID = "00000000-0000-4000-8000-000000000041"
_V4_FIELD_ID = "00000000-0000-4000-8000-000000000042"


def _register_v4_source(tmp_path: Path, vault: Path) -> Path:
    registry = KnowledgeSourceRegistry(tmp_path / "hub" / "sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(
            folder_id="analysis-vault",
            root=vault,
            capabilities=["read", "write"],
        )],
        sources=[KnowledgeSourceRegistration(
            source_id=_V4_SOURCE_ID,
            folder_id="analysis-vault",
        )],
    ))
    manifest = FieldManifest(
        source_id=_V4_SOURCE_ID,
        fields=[FieldDefinition(
            field_id=_V4_FIELD_ID,
            title="Analysis field",
            relative_root="field",
            home="home.md",
            navigation=[FieldNavigationGroup(label="Entry", items=["home.md"])],
        )],
    )
    (vault / ".scholar-workflow").mkdir(exist_ok=True)
    (vault / ".scholar-workflow" / "fields.yml").write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    (vault / "field").mkdir(exist_ok=True)
    (vault / "field" / "home.md").write_text("# Analysis field\n", encoding="utf-8")
    return registry.path.parent / "knowledge-providers" / _V4_SOURCE_ID


def _registry_for_provider(provider: Path) -> KnowledgeSourceRegistry:
    return KnowledgeSourceRegistry(provider.parent.parent / "sources.json")


def _image_commit_case(tmp_path: Path):
    """Prepare one independent, explicitly owned synthetic process PNG."""
    vault, state = _roots(tmp_path)
    folder = vault / "field/resources/papers/commit"
    (folder / "attachments").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path, vault, [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    width, height = 1200, 360
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * (width * 3)) * height)) + chunk(b"IEND", b"")
    image = folder / "attachments/flow.png"
    image.write_bytes(png)
    payload = _v4_document().model_dump(mode="json")
    payload["schema_version"] = 5
    payload["profile"] = {"kind": "whole", "framework": "reference_tree_v5", "markdown_quotes": True}
    source = {"kind": "zotero_pdf", "library_type": "personal", "library_id": "1", "attachment_key": "IMG00001", "content_hash": "sha256:" + "b" * 64, "page_index": 0}
    method = payload["claims"][0]
    method.update(claim_id="method", role="method", outline_path="method/overview", title="Synthetic process")
    method["evidence"] = {"kind": "author_stated", "anchor": "Figure 1", "source_spans": [{**source, "quote": "The synthetic process estimates one scalar."}]}
    method["canvas_image"] = {"kind": "process_diagram", "asset_id": "asset:flow", "image_path": "attachments/flow.png", "sha256": sha256(png).hexdigest(), "pixel_width": width, "pixel_height": height, "caption": "Figure 1: synthetic process", "source": source}
    asset = {"asset_id": "asset:flow", "owner_artifact_ids": [payload["artifact_id"]], "vault_path": "field/resources/papers/commit/attachments/flow.png", "display_name": "flow.png", "media_type": "image/png", "size": len(png), "sha256": "sha256:" + sha256(png).hexdigest(), "role": "supplement"}
    (vault / ".scholar-workflow/assets.yml").write_text(yaml.safe_dump({"schema_version": 1, "assets": [asset]}))
    document = AnalysisDocument.model_validate(payload)
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    return vault, state, provider, request, bundle, baseline, image


def test_v5_image_commit_and_replay_use_owned_real_png(tmp_path: Path) -> None:
    vault, state, provider, request, bundle, baseline, image = _image_commit_case(tmp_path)
    before = image.read_bytes()
    receipt = commit_analysis_bundle(vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline, source_registry=_registry_for_provider(provider))
    assert receipt.state == "committed"
    replay = commit_analysis_bundle(vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline, source_registry=_registry_for_provider(provider))
    assert replay == receipt
    assert image.read_bytes() == before
    from scholar_workflow.analysis.package_check import check_package

    report = check_package(image.parent.parent, markdown="Commit分析.md", canvas="Commit解析树.canvas", sidecar="Commit分析.analysis.json")
    assert report["status"] == "conformant"
    assert report["files"]["attachments/flow.png"] == "sha256:" + sha256(before).hexdigest()
    image.write_bytes(before + b"changed after commit")
    from scholar_workflow.analysis.image_assets import ImageAssetError

    with pytest.raises(ImageAssetError):
        check_package(image.parent.parent, markdown="Commit分析.md", canvas="Commit解析树.canvas", sidecar="Commit分析.analysis.json")


@pytest.mark.parametrize("case", ["matched", "other-source", "unresolved"])
def test_v5_companion_binding_checks_actual_commit_before_any_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    from scholar_workflow.adapters.obsidian_registry import resolve_obsidian_reader

    vault, state, provider, request, _, _, image = _image_commit_case(tmp_path)
    payload = request.document.model_dump(mode="json")
    path = vault.relative_to(tmp_path) / request.paths.markdown
    payload["profile"]["canvas_note_path"] = (
        path.as_posix() if case != "other-source" else "Other/Commit分析.md"
    )
    request = request.model_copy(update={"document": AnalysisDocument.model_validate(payload)})
    bundle, baseline = render_analysis_projection(request.document, note_stem=request.note_stem)
    config = tmp_path / "obsidian.json"
    config.write_text(json.dumps({"vaults": {"0123456789abcdef": {"path": str(tmp_path)}}}))

    def resolve(root: Path):
        if case == "unresolved":
            raise ZotFlowError("No registered containing Vault")
        return resolve_obsidian_reader(root, config_path=config)

    monkeypatch.setattr("scholar_workflow.analysis.commit.resolve_obsidian_reader", resolve)
    provider_before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    image_before = image.read_bytes()
    if case == "matched":
        receipt = commit_analysis_bundle(
            vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
        assert receipt.state == "committed"
        assert f"[[{path.as_posix()[:-3]}#^" in (vault / request.paths.canvas).read_text()
    else:
        with pytest.raises(AnalysisCommitSafetyError, match="companion"):
            commit_analysis_bundle(
                vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline,
                source_registry=_registry_for_provider(provider),
            )
        assert not state.exists()
        assert not any((vault / path).exists() for path in request.paths.as_list())
        assert (provider / "knowledge-provider.snapshot.json").read_bytes() == provider_before
    assert image.read_bytes() == image_before


@pytest.mark.parametrize("case", ["missing", "changed", "wrong-dimensions", "wrong-owner", "undeclared", "symlink", "corrupt-png"])
def test_v5_image_commit_refuses_invalid_dependencies_before_writes(tmp_path: Path, case: str) -> None:
    vault, state, provider, request, bundle, baseline, image = _image_commit_case(tmp_path)
    manifest = vault / ".scholar-workflow/assets.yml"
    rows = yaml.safe_load(manifest.read_text())
    if case == "missing":
        image.unlink()
    elif case == "changed":
        image.write_bytes(b"not the original image")
    elif case == "wrong-owner":
        rows["assets"][0]["owner_artifact_ids"] = ["analysis:another-paper"]
        manifest.write_text(yaml.safe_dump(rows))
    elif case == "undeclared":
        rows["assets"] = []
        manifest.write_text(yaml.safe_dump(rows))
    elif case == "symlink":
        copied = tmp_path / "external.png"
        copied.write_bytes(image.read_bytes())
        image.unlink()
        image.symlink_to(copied)
    else:
        data = request.document.model_dump(mode="json")
        method = next(c for c in data["claims"] if c["role"] == "method")
        if case == "wrong-dimensions":
            method["canvas_image"]["pixel_height"] += 1
        else:
            damaged = b"not PNG even with matching declared hash"
            image.write_bytes(damaged)
            method["canvas_image"]["sha256"] = sha256(damaged).hexdigest()
            rows["assets"][0].update(sha256="sha256:" + sha256(damaged).hexdigest(), size=len(damaged))
            manifest.write_text(yaml.safe_dump(rows))
        request = request.model_copy(update={"document": AnalysisDocument.model_validate(data)})
        bundle, baseline = render_analysis_projection(request.document, note_stem=request.note_stem)
    with pytest.raises(AnalysisCommitSafetyError):
        commit_analysis_bundle(vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline, source_registry=_registry_for_provider(provider))
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v5_image_change_before_receipt_rolls_back_pair_not_external_edit(tmp_path: Path) -> None:
    vault, state, provider, request, bundle, baseline, image = _image_commit_case(tmp_path)

    def concurrent_edit(event: str) -> None:
        if event == "before-receipt":
            image.write_bytes(b"external image editor changed this")

    with pytest.raises(AnalysisCommitSafetyError):
        commit_analysis_bundle(vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline, source_registry=_registry_for_provider(provider), fault_inject=concurrent_edit)
    assert not any((vault / path).exists() for path in request.paths.as_list())
    assert image.read_bytes() == b"external image editor changed this"


def _document() -> AnalysisDocument:
    return AnalysisDocument(
        schema_version=1,
        artifact_id="analysis:paper:commit",
        paper_title="Commit Paper",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body=f"Readable {role.value}; [[free-prose-link]] is not a relation.",
                evidence=Evidence(
                    kind=EvidenceKind.AUTHOR_STATED,
                    anchor="Section 1",
                ),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
            for role in ALL_ROLES
        ],
    )


def _request(
    document: AnalysisDocument,
    *,
    base_revisions: dict[str, str | None] | None = None,
) -> AnalysisCommitRequest:
    paths = AnalysisCanonicalPaths(
        markdown="topic/Commit分析.md",
        canvas="topic/Commit解析树.canvas",
        sidecar="topic/Commit分析.analysis.json",
    )
    return AnalysisCommitRequest(
        commit_id="commit-one",
        batch_id="batch-one",
        item_id="paper-one",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:commit",
        note_stem="Commit分析",
        document=document,
        paths=paths,
        base_revisions=base_revisions
        or {path: None for path in paths.as_list()},
        relations=[
            KnowledgeRelation(
                from_id="paper:commit",
                relation="has-analysis",
                to_id=document.artifact_id,
            )
        ],
        projections=[
            KnowledgeProjection(
                projection_id="projection:commit",
                kind="obsidian",
                target_id=document.artifact_id,
            )
        ],
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    (vault / "topic").mkdir(parents=True)
    state = tmp_path / "state"
    return vault, state


def test_legacy_commit_fingerprint_preserves_pre_v4_request_shape() -> None:
    request = _request(_document())
    legacy_payload = request.model_dump(mode="json")
    legacy_payload.pop("base_snapshot_revision")
    legacy_payload.pop("zotero_item_key")
    expected = "sha256:" + sha256(
        json.dumps(
            legacy_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert _request_fingerprint(request) == expected


def _digest(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _v4_document() -> AnalysisDocument:
    return AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:commit",
        paper_title="Commit Paper",
        language="en",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
        claims=[
            AnalysisClaim(
                claim_id="task",
                role=AnalysisRole.ABSTRACT,
                outline_path="abstract/task",
                title="Task",
                body="Readable task description.",
                evidence=Evidence(
                    kind=EvidenceKind.NOT_APPLICABLE,
                    detail="Test fixture.",
                ),
            )
        ],
    )


def _v4_zotflow_document(
    vault_name: str | None = None,
    *,
    vault_id: str | None = None,
) -> AnalysisDocument:
    payload = _v4_document().model_dump(mode="json")
    payload["reader"] = {
        "kind": "zotflow_library",
        "vault_name": vault_name,
        "vault_id": vault_id,
    }
    payload["claims"][0]["evidence"] = {
        "kind": "author_stated",
        "anchor": "Abstract",
        "source_spans": [{
            "kind": "zotero_pdf",
            "library_type": "personal",
            "library_id": "17685951",
            "attachment_key": "QR4ZU2S9",
            "content_hash": "md5:" + "a" * 32,
            "page_index": 3,
        }],
    }
    return AnalysisDocument.model_validate(payload)


def _v4_request(
    document: AnalysisDocument,
    base_catalog_revision: str | None,
    *,
    base_snapshot_revision: str | None = None,
    resource_id: str = "paper:commit",
) -> AnalysisCommitRequest:
    paths = AnalysisCanonicalPaths(
        markdown="field/resources/papers/commit/Commit分析.md",
        canvas="field/resources/papers/commit/Commit解析树.canvas",
        sidecar="field/resources/papers/commit/Commit分析.analysis.json",
    )
    return AnalysisCommitRequest(
        commit_id="commit-v4",
        batch_id="batch-v4",
        item_id="paper-one",
        source_state=AnalysisState.VALIDATED,
        resource_id=resource_id,
        note_stem="Commit分析",
        document=document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        base_catalog_revision=base_catalog_revision,
        base_snapshot_revision=base_snapshot_revision,
        zotero_item_key="ABCDEFGH",
        relations=[
            KnowledgeRelation(
                from_id=resource_id,
                relation="has-analysis",
                to_id=document.artifact_id,
            )
        ],
    )


def _provider_state(
    tmp_path: Path,
    vault_root: Path,
    resources: list[tuple[str, ResourceKind, str]],
) -> tuple[Path, str, str]:
    state = _register_v4_source(tmp_path, vault_root)
    state.mkdir(parents=True)
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 29, tzinfo=UTC),
        resources=[
            HubResource(
                resource_id=resource_id,
                kind=kind,
                zotero=ZoteroLink(item_key="ABCDEFGH"),
            )
            for resource_id, kind, _ in resources
        ],
    )
    snapshot = initialize_knowledge_provider_snapshot(
        state_root=state,
        vault_root=vault_root,
        manifest=KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id=resource_id,
                    kind=kind,
                    title=resource_id,
                    markdown_path=markdown_path,
                )
                for resource_id, kind, markdown_path in resources
            ]
        ),
        catalog=catalog,
    )
    return state, catalog.revision, snapshot.snapshot_revision


def test_v4_commit_uses_unique_provider_manifest_paper_folder(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    first = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
        source_registry=_registry_for_provider(provider),
    )
    apply_knowledge_change_set(
        state_root=provider,
        change_set=first.change_set,
    )
    replay = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
        source_registry=_registry_for_provider(provider),
    )

    assert replay == first
    assert all((vault / path).is_file() for path in request.paths.as_list())

    applied_snapshot = load_knowledge_provider_snapshot(provider)
    next_request = AnalysisCommitRequest.model_validate(
        {
            **request.model_dump(mode="json"),
            "commit_id": "commit-v4-next",
            "base_revisions": {item.path: item.after_sha256 for item in first.files},
            "base_catalog_revision": applied_snapshot.catalog.revision,
            "base_snapshot_revision": applied_snapshot.snapshot_revision,
        }
    )
    unchanged = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=next_request,
        bundle=bundle,
        baseline=baseline,
        source_registry=_registry_for_provider(provider),
    )
    assert all(item.action == "unchanged" for item in unchanged.files)


@pytest.mark.parametrize("changed_field", ["none", "serialization", "text", "layout", "frontmatter", "stale"])
def test_editor_metadata_acknowledgement_is_bounded_and_replayable(
    tmp_path: Path, changed_field: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    from scholar_workflow.analysis.editor_metadata import acknowledge_canvas_metadata
    from scholar_workflow.cli import main

    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path, vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    if changed_field == "serialization":
        bundle.canvas["metadata"] = {"version": "1.0-1.0", "frontmatter": {}}
    initial = commit_analysis_bundle(
        vault_root=vault, state_root=state, request=request, bundle=bundle,
        baseline=baseline, source_registry=_registry_for_provider(provider),
    )
    apply_knowledge_change_set(state_root=provider, change_set=initial.change_set)
    snapshot = load_knowledge_provider_snapshot(provider)
    canvas_path = vault / request.paths.canvas
    canvas = json.loads(canvas_path.read_text())
    canvas["metadata"] = {"version": "1.0-1.0", "frontmatter": {}}
    if changed_field == "text":
        canvas["nodes"][0]["text"] += " human content"
    elif changed_field == "layout":
        canvas["nodes"][0]["x"] += 128
    elif changed_field == "frontmatter":
        canvas["metadata"]["frontmatter"]["human"] = "observation"
    canvas_path.write_text(json.dumps(canvas))
    bases = {p: _digest((vault / p).read_bytes()) for p in request.paths.as_list()}
    if changed_field == "stale":
        bases[request.paths.canvas] = "sha256:" + "0" * 64
    update = request.model_copy(update={
        "base_revisions": bases, "base_catalog_revision": snapshot.catalog.revision,
        "base_snapshot_revision": snapshot.snapshot_revision,
    })
    before = {p: (vault / p).read_bytes() for p in request.paths.as_list()}
    provider_before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    if changed_field not in {"none", "serialization"}:
        with pytest.raises((AnalysisCommitConflict, AnalysisCommitSafetyError)):
            acknowledge_canvas_metadata(
                vault_root=vault, request=update, source_registry=_registry_for_provider(provider),
            )
        assert (provider / "knowledge-provider.snapshot.json").read_bytes() == provider_before
    else:
        request_path = tmp_path / "metadata-request.json"
        request_path.write_text(update.model_dump_json())
        args = ["analysis", "acknowledge-canvas-metadata", "--request", str(request_path),
                "--vault-root", str(vault)]
        registered_hash = None
        if changed_field == "serialization":
            registered_hash = next(a.sha256 for a in snapshot.artifacts if a.kind == "analysis_canvas")
            wrong_hash = "sha256:" + "0" * 64
            monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
            wrong = CliRunner().invoke(main, [*args, "--registered-canvas-hash", wrong_hash])
            assert wrong.exit_code == 5, wrong.output
            assert (provider / "knowledge-provider.snapshot.json").read_bytes() == provider_before
            args.extend(["--registered-canvas-hash", registered_hash])
        monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "unknown-source"))
        refused = CliRunner().invoke(main, args)
        assert refused.exit_code == 7, refused.output
        assert (provider / "knowledge-provider.snapshot.json").read_bytes() == provider_before
        monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
        acknowledged = CliRunner().invoke(main, args)
        assert acknowledged.exit_code == 0, acknowledged.output
        result = json.loads(acknowledged.output)
        applied = (provider / "knowledge-provider.snapshot.json").read_bytes()
        replay = acknowledge_canvas_metadata(
            vault_root=vault, request=update, source_registry=_registry_for_provider(provider),
            registered_canvas_hash=registered_hash,
        )
        assert replay == result
        assert result["canonical_written"] is False
        assert (provider / "knowledge-provider.snapshot.json").read_bytes() == applied
        current = load_knowledge_provider_snapshot(provider)
        next_request = AnalysisCommitRequest.model_validate(result["next_request"])
        assert next_request.base_catalog_revision == current.catalog.revision
        assert next_request.base_snapshot_revision == current.snapshot_revision
        assert next_request.base_revisions == bases
        assert next_request.document == update.document
        cli_replay = CliRunner().invoke(main, args)
        assert cli_replay.exit_code == 0, cli_replay.output
        assert json.loads(cli_replay.output) == result
        registered = next(a for a in current.artifacts if a.kind == "analysis_canvas")
        assert registered.sha256 == bases[request.paths.canvas]
        assert current.manifest.atomic_resources == snapshot.manifest.atomic_resources
        assert current.relations == snapshot.relations
        assert current.projections == snapshot.projections
    assert {p: (vault / p).read_bytes() for p in request.paths.as_list()} == before


@pytest.mark.parametrize("changed_field", ["metadata", "layout"])
def test_existing_commit_does_not_bypass_provider_revision_drift(
    tmp_path: Path, changed_field: str,
) -> None:
    from scholar_workflow.analysis.commit import plan_existing_analysis_update

    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path, vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    first = commit_analysis_bundle(
        vault_root=vault, state_root=state, request=request, bundle=bundle,
        baseline=baseline, source_registry=_registry_for_provider(provider),
    )
    apply_knowledge_change_set(state_root=provider, change_set=first.change_set)
    snapshot = load_knowledge_provider_snapshot(provider)
    path = vault / request.paths.canvas
    graph = json.loads(path.read_text())
    if changed_field == "metadata":
        graph["metadata"] = {"version": "1.0-1.0", "frontmatter": {}}
    else:
        for node in graph["nodes"]:
            node["x"] += 128
    path.write_text(json.dumps(graph))
    payload = request.model_dump(mode="json")
    payload.update({
        "commit_id": "provider-drift", "batch_id": "provider-drift",
        "base_revisions": {p: _digest((vault / p).read_bytes()) for p in request.paths.as_list()},
        "base_catalog_revision": snapshot.catalog.revision,
        "base_snapshot_revision": snapshot.snapshot_revision,
    })
    update_request = AnalysisCommitRequest.model_validate(payload)
    plan = plan_existing_analysis_update(vault_root=vault, request=update_request)
    assert plan.status == "ready"
    before = {p: (vault / p).read_bytes() for p in request.paths.as_list()}
    provider_before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    with pytest.raises(AnalysisCommitConflict, match="provider artifact revision changed"):
        commit_analysis_bundle(
            vault_root=vault, state_root=state, request=update_request, bundle=plan.proposed,
            baseline=plan.baseline, source_registry=_registry_for_provider(provider),
        )
    assert {p: (vault / p).read_bytes() for p in request.paths.as_list()} == before
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == provider_before


def test_existing_commit_rejects_reflow_and_accepts_preserved_update(tmp_path: Path) -> None:
    from scholar_workflow.analysis.commit import plan_existing_analysis_update
    from scholar_workflow.analysis.rendering import AnalysisBundle

    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path, vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    translated = deepcopy(bundle.canvas)
    for node in translated["nodes"]:
        node["x"] += 128
    retained = AnalysisBundle(markdown=bundle.markdown, canvas=translated)
    first = commit_analysis_bundle(
        vault_root=vault, state_root=state, request=request, bundle=retained,
        baseline=baseline, source_registry=_registry_for_provider(provider),
    )
    apply_knowledge_change_set(state_root=provider, change_set=first.change_set)
    snapshot = load_knowledge_provider_snapshot(provider)
    payload = document.model_dump(mode="json")
    payload["claims"][0]["body"] = "Updated synthetic task description."
    update = AnalysisDocument.model_validate(payload)
    request = AnalysisCommitRequest.model_validate({
        **request.model_dump(mode="json"), "commit_id": "preserved-update",
        "batch_id": "preserved-update", "document": payload,
        "base_revisions": {item.path: item.after_sha256 for item in first.files},
        "base_catalog_revision": snapshot.catalog.revision,
        "base_snapshot_revision": snapshot.snapshot_revision,
    })
    before = {path: (vault / path).read_bytes() for path in request.paths.as_list()}
    fresh, fresh_baseline = render_analysis_projection(update, note_stem=request.note_stem)
    with pytest.raises(AnalysisCommitConflict, match="discard the existing graph"):
        commit_analysis_bundle(
            vault_root=vault, state_root=state, request=request, bundle=fresh,
            baseline=fresh_baseline, source_registry=_registry_for_provider(provider),
        )
    assert {p: (vault / p).read_bytes() for p in request.paths.as_list()} == before
    plan = plan_existing_analysis_update(vault_root=vault, request=request)
    assert plan.status == "ready"
    committed = commit_analysis_bundle(
        vault_root=vault, state_root=state, request=request, bundle=plan.proposed,
        baseline=plan.baseline, source_registry=_registry_for_provider(provider),
    )
    apply_knowledge_change_set(state_root=provider, change_set=committed.change_set)
    replay = commit_analysis_bundle(
        vault_root=vault, state_root=state, request=request, bundle=plan.proposed,
        baseline=plan.baseline, source_registry=_registry_for_provider(provider),
    )
    assert replay == committed
    actual = json.loads((vault / request.paths.canvas).read_text())
    assert [(n["x"], n["y"]) for n in actual["nodes"]] == [
        (n["x"], n["y"]) for n in translated["nodes"]
    ]


def test_v4_commit_rejects_name_only_zotflow_reader_before_state_write(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_zotflow_document("test")
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    assert "obsidian://zotflow?vault=test" in bundle.markdown

    with pytest.raises(AnalysisCommitSafetyError, match="requires a verified Vault ID"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )

    assert not state.exists()
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_mismatched_zotflow_vault_id_before_state_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_zotflow_document(vault_id="1111111111111111")
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    resolved_roots: list[Path] = []

    def resolve(root: Path) -> str:
        resolved_roots.append(root)
        return "2222222222222222"

    monkeypatch.setattr("scholar_workflow.analysis.commit.resolve_obsidian_vault_id", resolve)
    with pytest.raises(AnalysisCommitSafetyError, match="reader Vault ID differs"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )

    assert resolved_roots == [vault]
    assert not state.exists()
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_unresolved_zotflow_vault_id_before_state_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_zotflow_document(vault_id="0123456789abcdef")
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    def unavailable(root: Path) -> str:
        assert root.samefile(vault)
        raise ZotFlowError("Registered Obsidian Vault ID is missing or ambiguous")

    monkeypatch.setattr(
        "scholar_workflow.analysis.commit.resolve_obsidian_vault_id", unavailable
    )
    with pytest.raises(AnalysisCommitSafetyError, match="Vault ID is unavailable"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )

    assert not state.exists()
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_subdirectory_source_resolves_containing_reader_without_wider_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scholar_workflow.adapters.obsidian_registry import resolve_obsidian_reader_vault_id

    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path, vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    config = tmp_path / "obsidian.json"
    vault_id = "0123456789abcdef"
    config.write_text(json.dumps({"vaults": {vault_id: {"path": str(tmp_path)}}}))
    monkeypatch.setattr(
        "scholar_workflow.analysis.commit.resolve_obsidian_vault_id",
        lambda root: resolve_obsidian_reader_vault_id(root, config_path=config),
    )
    document = _v4_zotflow_document(vault_id=vault_id)
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    commit_analysis_bundle(
        vault_root=vault, state_root=state, request=request, bundle=bundle, baseline=baseline,
        source_registry=_registry_for_provider(provider),
    )
    assert all((vault / path).is_file() for path in request.paths.as_list())
    assert not (tmp_path / "field").exists()
    assert _registry_for_provider(provider).resolve(_V4_SOURCE_ID, capability="write") == vault


def test_v4_commit_accepts_zotflow_reader_for_registered_vault_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    vault_id = "0123456789abcdef"

    def resolve(root: Path) -> str:
        assert root.samefile(vault)
        return vault_id

    monkeypatch.setattr(
        "scholar_workflow.analysis.commit.resolve_obsidian_vault_id", resolve
    )
    document = _v4_zotflow_document(vault_id=vault_id)
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    receipt = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
        source_registry=_registry_for_provider(provider),
    )

    reader_url = f"obsidian://zotflow?vault={vault_id}"
    assert reader_url in (vault / request.paths.markdown).read_text(encoding="utf-8")
    committed_canvas = json.loads((vault / request.paths.canvas).read_text(encoding="utf-8"))
    assert any(reader_url in node["text"] for node in committed_canvas["nodes"])
    assert all(item.action == "created" for item in receipt.files)


@pytest.mark.parametrize(
    "resources",
    [
        [],
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/other/Note.md")],
        [("paper:other", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
        [("paper:commit", ResourceKind.TECHNICAL_DOCUMENT, "field/resources/papers/commit/Note.md")],
        [
            ("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md"),
            ("paper:other", ResourceKind.PAPER, "field/resources/papers/commit/Other.md"),
        ],
    ],
)
def test_v4_commit_rejects_missing_mismatched_or_ambiguous_folder_owner(
    tmp_path: Path,
    resources: list[tuple[str, ResourceKind, str]],
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(tmp_path, vault, resources)
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="manifest owner|declared paper"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )

    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_requires_provider_and_matching_catalog_revision(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)

    with pytest.raises(AnalysisCommitSafetyError, match="registered Obsidian Source"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )
    with pytest.raises(AnalysisCommitConflict, match="catalog revision changed"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=_v4_request(
                document,
                "sha256:" + "f" * 64,
                base_snapshot_revision=snapshot_revision,
            ),
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    with pytest.raises(AnalysisCommitConflict, match="requires base_catalog_revision"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=_v4_request(document, None, base_snapshot_revision=snapshot_revision),
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    with pytest.raises(AnalysisCommitConflict, match="requires base_snapshot_revision"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=_v4_request(document, revision),
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_provider_bound_to_another_vault(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    other_vault = tmp_path / "other-vault"
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    (other_vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    _register_v4_source(tmp_path, other_vault)
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="Vault.*binding"):
        commit_analysis_bundle(
            vault_root=other_vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert not any((other_vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_unbound_provider_snapshot(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider = _register_v4_source(tmp_path, vault)
    provider.mkdir(parents=True)
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 29, tzinfo=UTC),
        resources=[
            HubResource(
                resource_id="paper:commit",
                kind=ResourceKind.PAPER,
                zotero=ZoteroLink(item_key="ABCDEFGH"),
            )
        ],
    )
    snapshot = initialize_knowledge_provider_snapshot(
        state_root=provider,
        manifest=KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id="paper:commit",
                    kind=ResourceKind.PAPER,
                    title="Commit Paper",
                    markdown_path="field/resources/papers/commit/Note.md",
                )
            ]
        ),
        catalog=catalog,
    )
    document = _v4_document()
    request = _v4_request(
        document,
        catalog.revision,
        base_snapshot_revision=snapshot.snapshot_revision,
    )
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="Vault.*binding"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_stale_manifest_snapshot_with_unchanged_catalog(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    _, old_catalog_revision, old_snapshot_revision = _provider_state(
        tmp_path / "old",
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Old.md")],
    )
    provider, current_catalog_revision, current_snapshot_revision = _provider_state(
        tmp_path / "current",
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/New.md")],
    )
    assert old_catalog_revision == current_catalog_revision
    assert old_snapshot_revision != current_snapshot_revision
    document = _v4_document()
    request = _v4_request(
        document,
        old_catalog_revision,
        base_snapshot_revision=old_snapshot_revision,
    )
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitConflict, match="snapshot revision changed"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_collision_with_primary_paper_note(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    paper_folder = vault / "field/resources/papers/commit"
    paper_folder.mkdir(parents=True)
    original = b"# Human paper note\n"
    primary_note = paper_folder / "Commit分析.md"
    primary_note.write_bytes(original)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Commit分析.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    payload = request.model_dump(mode="json")
    payload["base_revisions"][request.paths.markdown] = "sha256:" + sha256(original).hexdigest()
    request = AnalysisCommitRequest.model_validate(payload)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="declared Knowledge path"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert primary_note.read_bytes() == original
    assert not (vault / request.paths.canvas).exists()


@pytest.mark.parametrize("collision_kind", ["support", "sidecar-artifact"])
def test_v4_commit_rejects_other_declared_targets_in_paper_folder(
    tmp_path: Path,
    collision_kind: str,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    document = _v4_document()
    request = _v4_request(document, None)
    collision_path = (
        request.paths.canvas if collision_kind == "support" else request.paths.sidecar
    )
    original = b"owned by another Knowledge object\n"
    (vault / collision_path).write_bytes(original)
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 29, tzinfo=UTC),
        resources=[
            HubResource(
                resource_id="paper:commit",
                kind=ResourceKind.PAPER,
                zotero=ZoteroLink(item_key="ABCDEFGH"),
            )
        ],
    )
    supporting = (
        [
            KnowledgeSupportingDocument(
                document_id="analysis:other:canvas",
                kind=SupportingDocumentKind.ANALYSIS_CANVAS,
                title="Other analysis tree",
                vault_path=collision_path,
                owner_id="paper:commit",
            )
        ]
        if collision_kind == "support"
        else []
    )
    artifacts = (
        [
            KnowledgeArtifactChange(
                artifact_id="analysis:other:sidecar",
                resource_id="paper:commit",
                kind="analysis_sidecar",
                vault_path=collision_path,
                sha256="sha256:" + sha256(original).hexdigest(),
            )
        ]
        if collision_kind == "sidecar-artifact"
        else []
    )
    provider = _register_v4_source(tmp_path, vault)
    provider.mkdir(parents=True)
    snapshot = initialize_knowledge_provider_snapshot(
        state_root=provider,
        vault_root=vault,
        manifest=KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id="paper:commit",
                    kind=ResourceKind.PAPER,
                    title="Commit Paper",
                    markdown_path="field/resources/papers/commit/Note.md",
                )
            ],
            supporting_documents=supporting,
        ),
        catalog=catalog,
        artifacts=artifacts,
    )
    payload = request.model_dump(mode="json")
    payload["base_catalog_revision"] = catalog.revision
    payload["base_snapshot_revision"] = snapshot.snapshot_revision
    payload["base_revisions"][collision_path] = "sha256:" + sha256(original).hexdigest()
    request = AnalysisCommitRequest.model_validate(payload)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="declared Knowledge path|another Knowledge artifact"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert (vault / collision_path).read_bytes() == original
    assert not (vault / request.paths.markdown).exists()


def test_v4_commit_rejects_zotero_key_mismatch(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    request = AnalysisCommitRequest.model_validate(
        {**request.model_dump(mode="json"), "zotero_item_key": "WXYZ6789"}
    )
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="Zotero item key"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_does_not_trust_unregistered_same_vault_provider(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    _register_v4_source(tmp_path, vault)
    forged_provider, revision, snapshot_revision = _provider_state(
        tmp_path / "rogue",
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)
    registered = KnowledgeSourceRegistry(tmp_path / "hub" / "sources.json")

    with pytest.raises(AnalysisCommitSafetyError, match="--provider-state-root"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            provider_state_root=forged_provider,
            source_registry=registered,
        )
    with pytest.raises(AnalysisCommitSafetyError, match="provider state root"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=registered,
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_v4_commit_rejects_field_manifest_with_wrong_source(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    (vault / "field/resources/papers/commit").mkdir(parents=True)
    provider, revision, snapshot_revision = _provider_state(
        tmp_path,
        vault,
        [("paper:commit", ResourceKind.PAPER, "field/resources/papers/commit/Note.md")],
    )
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["source_id"] = "00000000-0000-4000-8000-000000000099"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    document = _v4_document()
    request = _v4_request(document, revision, base_snapshot_revision=snapshot_revision)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    with pytest.raises(AnalysisCommitSafetyError, match="Source differs"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            source_registry=_registry_for_provider(provider),
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


@pytest.mark.parametrize("schema_version", [2, 3])
def test_legacy_commit_does_not_require_provider_state(
    tmp_path: Path,
    schema_version: int,
) -> None:
    vault, state = _roots(tmp_path)
    payload = _document().model_dump(mode="json")
    payload["schema_version"] = schema_version
    for claim in payload["claims"]:
        claim["evidence"] = {"kind": "not_applicable", "detail": "Legacy fixture."}
    document = AnalysisDocument.model_validate(payload)
    request = _request(document)
    bundle, baseline = render_analysis_projection(document, note_stem=request.note_stem)

    receipt = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )

    assert receipt.commit_id == request.commit_id
    assert all((vault / path).is_file() for path in request.paths.as_list())


def _concurrent_commit_worker(
    vault: str,
    state: str,
    request_json: str,
    fail_after_markdown: bool,
    entered,
    release,
    result,
) -> None:
    request = AnalysisCommitRequest.model_validate_json(request_json)
    bundle, baseline = render_analysis_projection(
        request.document,
        note_stem=request.note_stem,
    )

    def inject(point: str) -> None:
        if fail_after_markdown and point == f"after-replace:{request.paths.markdown}":
            entered.set()
            if not release.wait(10):
                raise TimeoutError("test release timed out")
            raise RuntimeError("injected concurrent rollback")

    if not fail_after_markdown:
        entered.set()
    try:
        receipt = commit_analysis_bundle(
            vault_root=Path(vault),
            state_root=Path(state),
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=inject if fail_after_markdown else None,
        )
        result.put(("ok", receipt.commit_id))
    except Exception as exc:  # noqa: BLE001 - cross-process test result
        result.put((type(exc).__name__, str(exc)))


def test_commit_is_canonical_idempotent_and_change_set_is_explicit(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    first = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )
    second = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )

    assert second == first
    assert (vault / request.paths.markdown).read_text(encoding="utf-8") == bundle.markdown
    assert json.loads((vault / request.paths.canvas).read_text(encoding="utf-8")) == bundle.canvas
    assert len(first.change_set.upsert_artifacts) == 3
    assert first.change_set.upsert_relations == request.relations
    assert first.change_set.upsert_projections == request.projections
    assert "free-prose-link" not in first.change_set.model_dump_json()


def test_commit_rejects_canvas_outside_the_shared_standard(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    bundle.canvas["nodes"].append(
        {
            "id": "human-zero-width",
            "type": "group",
            "x": 9000,
            "y": 9000,
            "width": 0,
            "height": 10,
            "label": "Invalid group",
        }
    )
    request = _request(document)

    with pytest.raises(AnalysisCommitError, match="invalid-json-canvas-contract"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )
    assert not any((vault / path).exists() for path in request.paths.as_list())


def test_commit_cas_never_overwrites_a_human_edit(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    target = vault / request.paths.markdown
    target.write_text("human edit", encoding="utf-8")

    with pytest.raises(AnalysisCommitConflict, match="base revision changed"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )

    assert target.read_text(encoding="utf-8") == "human edit"


def test_fault_rolls_back_only_files_still_owned_by_the_commit(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    def fail_after_canvas(point: str) -> None:
        if point == f"after-replace:{request.paths.canvas}":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=fail_after_canvas,
        )

    assert not (vault / request.paths.markdown).exists()
    assert not (vault / request.paths.canvas).exists()
    assert not (vault / request.paths.sidecar).exists()
    journal = json.loads(
        (state / "analysis-commits" / "journals" / "commit-one.json").read_text()
    )
    assert journal["status"] == "rolled_back"


def test_conditional_rollback_preserves_concurrent_human_content(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    markdown = vault / request.paths.markdown

    def edit_then_fail(point: str) -> None:
        if point == f"after-replace:{request.paths.markdown}":
            markdown.write_text("concurrent human edit", encoding="utf-8")
            raise RuntimeError("injected after edit")

    with pytest.raises(AnalysisCommitPartialError, match="concurrent edits"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=edit_then_fail,
        )

    assert markdown.read_text(encoding="utf-8") == "concurrent human edit"


def test_fault_restores_replaced_bundle_from_verified_backups(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    paths = AnalysisCanonicalPaths(
        markdown="topic/Commit分析.md",
        canvas="topic/Commit解析树.canvas",
        sidecar="topic/Commit分析.analysis.json",
    )
    originals = {
        paths.markdown: b"old markdown",
        paths.canvas: b'{"nodes": [], "edges": []}\n',
        paths.sidecar: b'{"old": true}\n',
    }
    for relative_path, payload in originals.items():
        (vault / relative_path).write_bytes(payload)
    request = _request(
        document,
        base_revisions={
            relative_path: _digest(payload)
            for relative_path, payload in originals.items()
        },
    )

    def fail_after_canvas(point: str) -> None:
        if point == f"after-replace:{request.paths.canvas}":
            raise RuntimeError("injected replacement failure")

    with pytest.raises(RuntimeError, match="replacement failure"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=fail_after_canvas,
        )

    assert {
        relative_path: (vault / relative_path).read_bytes()
        for relative_path in originals
    } == originals


def test_commit_rejects_symlink_target_without_touching_victim(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    victim = tmp_path / "victim.md"
    victim.write_text("victim", encoding="utf-8")
    (vault / request.paths.markdown).symlink_to(victim)

    with pytest.raises(AnalysisCommitSafetyError, match="symlink"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )

    assert victim.read_text(encoding="utf-8") == "victim"


def test_pre_replace_recheck_detects_edit_after_initial_cas(tmp_path: Path) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    markdown = vault / request.paths.markdown

    def edit_before_replace(point: str) -> None:
        if point == f"before-replace:{request.paths.markdown}":
            markdown.write_text("human edit during commit", encoding="utf-8")

    with pytest.raises(AnalysisCommitPartialError, match="concurrent edits"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=edit_before_replace,
        )

    assert markdown.read_text(encoding="utf-8") == "human edit during commit"


def test_parent_directory_rebind_cannot_redirect_commit_outside_vault(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_parent = vault / "topic-original"

    def rebind_parent(point: str) -> None:
        if point == f"before-replace:{request.paths.markdown}":
            (vault / "topic").rename(original_parent)
            (vault / "topic").symlink_to(outside, target_is_directory=True)

    with pytest.raises(AnalysisCommitPartialError, match="conditional rollback"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=rebind_parent,
        )

    assert not any((outside / Path(path).name).exists() for path in request.paths.as_list())
    assert not any(
        (original_parent / Path(path).name).exists()
        for path in request.paths.as_list()
    )


def test_vault_root_rebind_cannot_split_lock_and_write_domains(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    original_root = tmp_path / "vault-original"

    def rebind_root(point: str) -> None:
        if point == f"before-replace:{request.paths.markdown}":
            vault.rename(original_root)
            (vault / "topic").mkdir(parents=True)

    with pytest.raises(AnalysisCommitPartialError, match="conditional rollback"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=rebind_root,
        )

    for relative_path in request.paths.as_list():
        assert not (vault / relative_path).exists()
        assert not (original_root / relative_path).exists()


def test_state_journal_rebind_cannot_redirect_recovery_outside_state_root(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    def stop_after_journal(point: str) -> None:
        if point == "after-journal":
            raise RuntimeError("stop after journal")

    with pytest.raises(RuntimeError, match="stop after journal"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=stop_after_journal,
        )

    journal_root = state / "analysis-commits" / "journals"
    original_journal_root = state / "analysis-commits" / "journals-original"
    outside = tmp_path / "outside-state"
    outside.mkdir()
    journal_root.rename(original_journal_root)
    journal_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(AnalysisCommitSafetyError, match="state directory"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )

    assert list(outside.iterdir()) == []
    assert not any((vault / path).exists() for path in request.paths.as_list())


@pytest.mark.parametrize(
    "tamper",
    ["path", "before", "after", "artifact", "change-set"],
)
def test_replay_rejects_receipt_fields_that_do_not_match_request(
    tmp_path: Path,
    tamper: str,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    receipt = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )
    payload = receipt.model_dump(mode="json")
    if tamper == "path":
        old_path = payload["files"][0]["path"]
        new_path = "topic/Forged分析.md"
        payload["files"][0]["path"] = new_path
        payload["change_set"]["expected_base_hashes"][new_path] = payload[
            "change_set"
        ]["expected_base_hashes"].pop(old_path)
        payload["change_set"]["upsert_artifacts"][0]["vault_path"] = new_path
    elif tamper == "before":
        forged = "sha256:" + "0" * 64
        payload["files"][0]["before_sha256"] = forged
        payload["files"][0]["action"] = "replaced"
        payload["change_set"]["expected_base_hashes"][
            payload["files"][0]["path"]
        ] = forged
    elif tamper == "after":
        forged = "sha256:" + "0" * 64
        payload["files"][0]["after_sha256"] = forged
        payload["change_set"]["upsert_artifacts"][0]["sha256"] = forged
    elif tamper == "artifact":
        payload["artifact_id"] = "analysis:forged"
        for artifact in payload["change_set"]["upsert_artifacts"]:
            suffix = {
                "analysis_markdown": "",
                "analysis_canvas": ":canvas",
                "analysis_sidecar": ":sidecar",
            }[artifact["kind"]]
            artifact["artifact_id"] = f"analysis:forged{suffix}"
        payload["change_set"]["upsert_relations"][0]["to_id"] = "analysis:forged"
    else:
        payload["change_set"]["upsert_projections"].append(
            {
                "projection_id": "projection:forged",
                "kind": "obsidian",
                "target_id": document.artifact_id,
            }
        )

    receipt_path = (
        state / "analysis-commits" / "receipts" / f"{request.commit_id}.json"
    )
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AnalysisCommitSafetyError, match="does not match the request"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )


def test_replay_rejects_forged_empty_receipt_without_canonical_files(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    receipt_dir = state / "analysis-commits" / "receipts"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / f"{request.commit_id}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "commit_id": request.commit_id,
                "request_fingerprint": "sha256:" + "0" * 64,
                "artifact_id": document.artifact_id,
                "state": "committed",
                "committed_at": "not-a-date",
                "files": [],
                "change_set": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AnalysisCommitSafetyError, match="invalid commit receipt"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )


def test_recovery_rejects_journal_file_rebind_before_rollback(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    def stop_after_journal(point: str) -> None:
        if point == "after-journal":
            raise RuntimeError("stop after journal")

    with pytest.raises(RuntimeError, match="stop after journal"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=stop_after_journal,
        )

    victim = vault / "topic" / "victim.md"
    victim.write_text("human-owned", encoding="utf-8")
    metadata = victim.stat()
    journal_path = (
        state / "analysis-commits" / "journals" / f"{request.commit_id}.json"
    )
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["files"][0].update(
        {
            "path": "topic/victim.md",
            "after_sha256": _digest(victim.read_bytes()),
            "after_identity": {
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "size": metadata.st_size,
                "mtime_ns": metadata.st_mtime_ns,
                "ctime_ns": metadata.st_ctime_ns,
            },
        }
    )
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(AnalysisCommitSafetyError, match="journal file record"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
        )
    assert victim.read_text(encoding="utf-8") == "human-owned"


def test_rollback_preserves_same_content_replacement_with_a_new_inode(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)
    markdown = vault / request.paths.markdown
    replacement_inode: int | None = None

    def replace_with_same_content_then_fail(point: str) -> None:
        nonlocal replacement_inode
        if point == f"after-replace:{request.paths.markdown}":
            replacement = markdown.with_name("same-content-winner.md")
            replacement.write_bytes(markdown.read_bytes())
            replacement.replace(markdown)
            replacement_inode = markdown.stat().st_ino
            raise RuntimeError("concurrent same-content winner")

    with pytest.raises(AnalysisCommitPartialError, match="concurrent edits"):
        commit_analysis_bundle(
            vault_root=vault,
            state_root=state,
            request=request,
            bundle=bundle,
            baseline=baseline,
            fault_inject=replace_with_same_content_then_fail,
        )

    assert markdown.is_file()
    assert markdown.read_text(encoding="utf-8") == bundle.markdown
    assert markdown.stat().st_ino == replacement_inode


def test_change_set_assigns_every_artifact_to_the_requested_resource(
    tmp_path: Path,
) -> None:
    vault, state = _roots(tmp_path)
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Commit分析")
    request = _request(document)

    receipt = commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )

    assert {
        artifact.resource_id for artifact in receipt.change_set.upsert_artifacts
    } == {request.resource_id}


def test_vault_lock_serializes_commits_even_with_different_state_roots(
    tmp_path: Path,
) -> None:
    vault, _state = _roots(tmp_path)
    request = _request(_document())
    context = multiprocessing.get_context("spawn")
    first_entered = context.Event()
    second_entered = context.Event()
    release = context.Event()
    first_result = context.Queue()
    second_result = context.Queue()
    first = context.Process(
        target=_concurrent_commit_worker,
        args=(
            str(vault),
            str(tmp_path / "state-one"),
            request.model_dump_json(),
            True,
            first_entered,
            release,
            first_result,
        ),
    )
    second = context.Process(
        target=_concurrent_commit_worker,
        args=(
            str(vault),
            str(tmp_path / "state-two"),
            request.model_dump_json(),
            False,
            second_entered,
            release,
            second_result,
        ),
    )
    first.start()
    assert first_entered.wait(10)
    second.start()
    assert second_entered.wait(10)
    with pytest.raises(queue.Empty):
        second_result.get(timeout=0.5)

    release.set()
    first_outcome = first_result.get(timeout=10)
    second_outcome = second_result.get(timeout=10)
    first.join(timeout=10)
    second.join(timeout=10)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert first_outcome[0] == "RuntimeError"
    assert second_outcome == ("ok", request.commit_id)
    for relative_path in request.paths.as_list():
        assert (vault / relative_path).is_file()
