"""Synthetic webpage-to-v5 contract, independent of live Zotero and any Vault.

Two anchored source paragraphs exercise exact ownership/hash/block/quote checks,
copyright-limited presentation and the unchanged five-branch paired commit. Bad
locators must refuse without canonical writes; a source edit during publication
must roll back only the analysis and retain the external source edit.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.apply_changes import (
    apply_knowledge_change_set,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.commit import AnalysisCommitError, commit_analysis_bundle
from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisCommitRequest, AnalysisDocument
from scholar_workflow.analysis.updates import render_analysis_projection
from scholar_workflow.knowledge.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.knowledge.source_blocks import source_paragraphs
from scholar_workflow.workflows.register_document import document_plan, register_document
from scholar_workflow.workflows.register_source import register_source

ROOT = Path(__file__).resolve().parents[2]
URL = "https://example.org/official-introduction"
SOURCE = "# Synthetic introduction\n\nThe model predicts a synthetic value.\n^prediction\n\nThe training recipe is not disclosed.\n^recipe\n"


class LocalWebpage:
    def get_item(self, key):
        return {"key": key, "version": 1, "library": {"id": 123, "type": "user"}, "data": {
            "itemType": "webpage", "title": "Synthetic introduction", "url": URL,
        }}


def _document(source_id, resource_id, source_path):
    span = {"kind": "vault_markdown", "source_id": source_id, "artifact_id": resource_id,
            "vault_path": source_path, "block_id": "prediction",
            "quote": "The model predicts a synthetic value.",
            "quote_emphasis": ["predicts a synthetic value"]}
    return AnalysisDocument.model_validate({
        "schema_version": 5, "artifact_id": "analysis:document:synthetic",
        "material_kind": "webpage",
        "paper_title": "Synthetic introduction (official webpage)", "language": "en",
        "profile": {"kind": "whole", "framework": "reference_tree_v5",
                    "markdown_quotes": True, "markdown_folded_quotes": True},
        "claims": [
            {"claim_id": "task", "role": "abstract", "outline_path": "abstract/task",
             "title": "Synthetic prediction", "body": "The source describes prediction of a synthetic value. It provides no measured performance claim. The webpage is the material under analysis, not an unseen paper; the short Canvas is only a navigation view of this explanation.",
             "canvas_summary": "Predict a synthetic value; performance is not established.",
             "evidence": {"kind": "author_stated", "anchor": "Prediction", "source_spans": [span]}},
            {"claim_id": "application", "role": "introduction",
             "outline_path": "introduction/task_application", "title": "Disclosed task",
             "body": "The stated task remains synthetic prediction; no downstream application is established here.",
             "evidence": {"kind": "author_stated", "anchor": "Prediction",
                          "quotation_omitted_reason": "copyright_or_permission",
                          "source_spans": [{key: value for key, value in span.items()
                                            if key not in {"quote", "quote_emphasis"}}]}},
        ],
    })


@pytest.fixture
def case(tmp_path, request):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "README.md").write_text("# Synthetic field\n")
    registry = KnowledgeSourceRegistry(tmp_path / "home/hub/sources.json")
    service = FieldService(registry)
    plan = registration_plan(service, root, field_root=".", existing_source=False)
    manifest = register_source(service, root, field_root=".", existing_source=False,
                               approved_digest=plan.payload["approved_digest"])
    original = tmp_path / "source.md"
    original.write_text(getattr(request, "param", SOURCE))
    selection = {"source_id": manifest.source_id, "field_id": manifest.fields[0].field_id,
                 "item_key": "ABCD2345", "segment": "synthetic", "language": "en",
                 "markdown_path": original, "source_url": URL, "retrieved_at": "2026-01-02T03:04:05Z"}
    plan = document_plan(registry, LocalWebpage(), **selection)
    result = register_document(registry, LocalWebpage(), approved_digest=plan["approved_digest"], **selection)
    provider = registry.path.parent / "knowledge-providers" / manifest.source_id
    snapshot = load_knowledge_provider_snapshot(provider)
    document = _document(manifest.source_id, result["resource_id"], result["owner_path"])
    folder = str(Path(result["owner_path"]).parent)
    paths = {"markdown": folder + "/Analysis.md", "canvas": folder + "/Tree.canvas",
             "sidecar": folder + "/Analysis.analysis.json"}
    request = AnalysisCommitRequest.model_validate({
        "commit_id": "document-commit", "batch_id": "document-batch", "item_id": "webpage",
        "source_state": "validated", "resource_id": result["resource_id"], "note_stem": "Analysis",
        "document": document.model_dump(mode="json"), "paths": paths,
        "base_revisions": dict.fromkeys(paths.values()),
        "base_catalog_revision": snapshot.catalog.revision,
        "base_snapshot_revision": snapshot.snapshot_revision, "zotero_item_key": "ABCD2345",
        "relations": [{"from_id": result["resource_id"], "relation": "has-analysis",
                       "to_id": document.artifact_id}],
    })
    return root, registry, provider, request, root / result["owner_path"]


def _commit(case, *, fault_inject=None):
    root, registry, _, request, _ = case
    bundle, baseline = render_analysis_projection(request.document, note_stem=request.note_stem)
    return commit_analysis_bundle(vault_root=root, state_root=root.parent / "analysis-state",
                                  request=request, bundle=bundle, baseline=baseline,
                                  source_registry=registry, fault_inject=fault_inject)


def test_registered_webpage_v5_commits_applies_and_replays_without_pdf(case):
    root, _, provider, request, source = case
    original = source.read_bytes()
    receipt = _commit(case)
    apply_knowledge_change_set(state_root=provider, change_set=receipt.change_set)
    assert _commit(case) == receipt
    assert source.read_bytes() == original
    markdown = (root / request.paths.markdown).read_text()
    canvas = json.loads((root / request.paths.canvas).read_text())
    assert "The webpage is the material under analysis" in markdown
    assert ": Webpage Analysis" in markdown
    assert "Selected official webpage; not a full paper" in markdown
    assert "Scope: Whole paper" not in markdown
    assert "> [!quote]- Original excerpt" in markdown
    assert "**predicts a synthetic value**" in markdown
    assert "copyright or permission limits" in markdown
    assert all("Original excerpt" not in node.get("text", "") for node in canvas["nodes"])
    assert {"Abstract", "Introduction", "Method", "Experiments", "Limitation"}.issubset(
        {node.get("text", "").strip("*") for node in canvas["nodes"]})


@pytest.mark.parametrize("change", ["source_id", "artifact_id", "vault_path", "block_id", "quote"])
def test_changed_source_locator_or_quote_refuses_before_writing(case, change):
    root, _, _, request, _ = case
    payload = request.model_dump(mode="json")
    span = payload["document"]["claims"][0]["evidence"]["source_spans"][0]
    span[change] = {"source_id": "00000000-0000-4000-8000-000000000001",
                    "artifact_id": "document:wrong", "vault_path": "other.md",
                    "block_id": "missing", "quote": "A different complete sentence."}[change]
    if change == "quote":
        span.pop("quote_emphasis")
    changed = AnalysisCommitRequest.model_validate(payload)
    with pytest.raises(AnalysisCommitError):
        _commit((*case[:3], changed, case[4]))
    assert not any((root / path).exists() for path in request.paths.as_list())


@pytest.mark.parametrize("when", ["before", "during", "replay"])
def test_changed_source_hash_fails_closed_and_preserves_external_edit(case, when):
    root, _, _, request, source = case
    before = source.read_bytes()
    if when == "replay":
        _commit(case)
    if when in {"before", "replay"}:
        source.write_bytes(before + b"\nExternal edit\n")
    def mutate(event):
        if event == "after-replace:" + request.paths.markdown:
            source.write_bytes(before + b"\nExternal edit\n")
    with pytest.raises(AnalysisCommitError):
        _commit(case, fault_inject=mutate if when == "during" else None)
    assert source.read_bytes() == before + b"\nExternal edit\n"
    if when != "replay":
        assert not any((root / path).exists() for path in request.paths.as_list())


def test_webpage_quotation_policy_matches_public_schema_and_conformance():
    document = _document("00000000-0000-4000-8000-000000000001",
                         "document:zotero:123:ABCD2345", "resources/synthetic/Source.md")
    payload = document.model_dump(mode="json")
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(payload)
    bundle, _ = render_analysis_projection(document, note_stem="Analysis")
    assert validate_bundle(document, bundle, note_stem="Analysis").ok
    for mutation in ("pdf", "quoted", "no-source", "unsupported", "v4"):
        changed = deepcopy(payload)
        evidence = changed["claims"][1]["evidence"]
        if mutation == "pdf":
            evidence["source_spans"] = [{"kind": "zotero_pdf", "library_type": "personal", "library_id": "123",
                "attachment_key": "EFGH2345", "content_hash": "sha256:" + "a" * 64, "page_index": 0}]
        elif mutation == "quoted":
            evidence["source_spans"][0]["quote"] = "The model predicts a synthetic value."
        elif mutation == "no-source":
            evidence["source_spans"] = []
        elif mutation == "unsupported":
            evidence.update(kind="not_reported")
        else:
            changed.update(schema_version=4)
            changed["profile"]["framework"] = "reference_tree"
        with pytest.raises(ValidationError):
            AnalysisDocument.model_validate(changed)
        assert list(jsonschema.Draft202012Validator(schema).iter_errors(changed))


def test_v5_pdf_quotation_cannot_use_webpage_exception():
    payload = _document("00000000-0000-4000-8000-000000000001",
                        "document:zotero:123:ABCD2345", "resources/synthetic/Source.md").model_dump(mode="json")
    evidence = payload["claims"][0]["evidence"]
    evidence["source_spans"][0].pop("quote")
    evidence["source_spans"][0].pop("quote_emphasis")
    with pytest.raises(ValidationError, match="excerpt"):
        AnalysisDocument.model_validate(payload)


@pytest.mark.parametrize("case", [
    "Unrelated complete sentence.\n\nThe model predicts a synthetic value.\n^prediction\n",
], indirect=True)
def test_quote_in_previous_paragraph_cannot_satisfy_clicked_block(case):
    payload = case[3].model_dump(mode="json")
    span = payload["document"]["claims"][0]["evidence"]["source_spans"][0]
    span.update(quote="Unrelated complete sentence.", quote_emphasis=[])
    changed = AnalysisCommitRequest.model_validate(payload)
    with pytest.raises(AnalysisCommitError, match="exact source block"):
        _commit((*case[:3], changed, case[4]))


@pytest.mark.parametrize("text", [
    "```md\nHidden sentence.\n^hidden\n```\n",
    "<!--\nHidden sentence.\n^hidden\n-->\n",
    "<!-- closed --> <!-- open\nHidden sentence.\n^hidden\n-->\n",
    "```text\n<!--\n```\n-->\n```\nHidden code sentence.\n^hidden\n```\n",
])
def test_hidden_source_anchors_are_not_clickable_blocks(text):
    assert source_paragraphs(text) == {}


def test_explicit_webpage_kind_survives_focused_update_and_cannot_relabel_paper():
    from scholar_workflow.analysis.updates import AnalysisUpdateError, _merged_document
    original = _document("00000000-0000-4000-8000-000000000001",
                         "document:zotero:123:ABCD2345", "resources/synthetic/Source.md")
    selected = original.model_dump(mode="json")
    selected["profile"].update(kind="focused", roles=["abstract"])
    selected["claims"] = selected["claims"][:1]
    changed = AnalysisDocument.model_validate(selected)
    assert _merged_document(original, changed).material_kind == "webpage"
    selected.pop("material_kind")
    paper = AnalysisDocument.model_validate(selected)
    with pytest.raises(AnalysisUpdateError, match="source material kind"):
        _merged_document(original, paper)
