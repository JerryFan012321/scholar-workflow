"""Public CLI contracts for one synthetic Webpage, never a live library.

Inputs: a temporary registered Source, a fake read-only Local API Webpage, and
two anchored UTF-8 paragraphs. Invoke the real document-plan/register-document
flags, verify their human heading/JSON receipt and exact source bytes, then stage,
commit and apply one synthetic v5 pair using public CLI commands only. Invalid
flags, digests, URLs and absent confirmation refuse without publishing the source.
These checks prove CLI wiring/ownership integrity, not scientific or GUI acceptance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.workflows.register_source import register_source

URL = "https://example.org/official-model"
SOURCE = (
    "# Synthetic official source\n\n"
    "The synthetic model predicts three numerical values.\n^prediction\n\n"
    "This fixture does not report measured performance.\n^scope\n"
)


@pytest.fixture
def cli_case(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("# Existing synthetic Field\n")
    home = tmp_path / "home"
    registry = KnowledgeSourceRegistry(home / "hub/sources.json")
    service = FieldService(registry)
    preview = registration_plan(service, root, field_root=".", existing_source=False)
    manifest = register_source(service, root, field_root=".", existing_source=False,
                               approved_digest=preview.payload["approved_digest"])
    source = tmp_path / "source-input.md"
    source.write_text(SOURCE)
    calls = []

    class LocalWebpage:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get_item(self, key):
            calls.append(key)
            assert key == "ABCD2345", "The document flow must not request a PDF attachment."
            return {"key": key, "version": 7, "library": {"id": 123, "type": "user"},
                    "data": {"itemType": "webpage", "title": "Synthetic official source", "url": URL}}

    monkeypatch.setattr("scholar_workflow.adapters.zotero_local.ZoteroLocalAdapter", LocalWebpage)
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    args = ["--source-id", manifest.source_id, "--field-id", manifest.fields[0].field_id,
            "--item-key", "ABCD2345", "--segment", "synthetic-webpage", "--language", "en",
            "--markdown", str(source), "--source-url", URL,
            "--retrieved-at", "2026-01-02T03:04:05Z"]
    return {"root": root, "home": home, "registry": registry, "source": source,
            "source_id": manifest.source_id, "args": args, "calls": calls,
            "runner": CliRunner(), "tmp": tmp_path}


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _invoke(case, command, *args, input=None):
    return case["runner"].invoke(main, [*command, *args], input=input)


def _register(case):
    before = _files(case["tmp"])
    proposal = _invoke(case, ["knowledge", "document-plan"], *case["args"], "--format", "json")
    assert proposal.exit_code == 0, proposal.output
    plan = json.loads(proposal.output)
    assert _files(case["tmp"]) == before
    assert plan["document"]["item_type"] == "webpage"
    assert plan["document"]["source_url"] == URL
    assert plan["source"]["markdown_sha256"] == "sha256:" + hashlib.sha256(SOURCE.encode()).hexdigest()
    result = _invoke(case, ["knowledge", "register-document"], *case["args"],
                     "--approved-digest", plan["approved_digest"], "--yes")
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "registered"
    assert receipt["resource_id"] == "document:zotero:123:ABCD2345"
    assert receipt["owner_path"] == "resources/synthetic-webpage/Source.md"
    assert receipt["receipt_id"].startswith("knowledge-apply:")
    assert not receipt["analysis_committed"] and not receipt["backup_verified"]
    return plan, receipt


def test_public_document_plan_header_registration_and_replay(cli_case):
    case = cli_case
    before = _files(case["tmp"])
    preview = _invoke(case, ["knowledge", "document-plan"], *case["args"])
    assert preview.exit_code == 0, preview.output
    assert preview.output.startswith("# Document source registration plan\n")
    assert "New source note: resources/synthetic-webpage/Source.md" in preview.output
    assert "Nothing written; source registration is not analysis or scientific acceptance." in preview.output
    assert URL in preview.output
    assert _files(case["tmp"]) == before

    plan, receipt = _register(case)
    assert (case["root"] / receipt["owner_path"]).read_bytes() == SOURCE.encode()
    before_replay = _files(case["tmp"])
    replay = _invoke(case, ["knowledge", "register-document"], *case["args"],
                     "--approved-digest", plan["approved_digest"], "--yes")
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.output) == receipt
    assert _files(case["tmp"]) == before_replay
    assert case["calls"] and set(case["calls"]) == {"ABCD2345"}


@pytest.mark.parametrize("failure", ["digest", "url", "missing-markdown", "confirmation"])
def test_public_document_cli_refuses_bad_selection_without_source_publication(cli_case, failure):
    case = cli_case
    proposal = _invoke(case, ["knowledge", "document-plan"], *case["args"], "--format", "json")
    assert proposal.exit_code == 0, proposal.output
    plan = json.loads(proposal.output)
    args = list(case["args"])
    before = _files(case["tmp"])
    if failure == "digest":
        result = _invoke(case, ["knowledge", "register-document"], *args,
                         "--approved-digest", "0" * 64, "--yes")
        assert result.exit_code == 7 and "plan changed" in result.output
    elif failure == "url":
        args[args.index("--source-url") + 1] = "https://example.org/a-different-source"
        result = _invoke(case, ["knowledge", "document-plan"], *args, "--format", "json")
        assert result.exit_code == 7 and "source URL" in result.output
    elif failure == "missing-markdown":
        position = args.index("--markdown")
        del args[position:position + 2]
        result = _invoke(case, ["knowledge", "document-plan"], *args, "--format", "json")
        assert result.exit_code == 2 and "--markdown" in result.output
    else:
        result = _invoke(case, ["knowledge", "register-document"], *args,
                         "--approved-digest", plan["approved_digest"], input="n\n")
        assert result.exit_code == 1 and "Aborted" in result.output
    assert _files(case["tmp"]) == before
    assert not (case["root"] / "resources/synthetic-webpage/Source.md").exists()


def test_public_webpage_cli_stages_commits_and_applies_v5_without_pdf(cli_case):
    case = cli_case
    _, owner = _register(case)
    document = {
        "schema_version": 5, "material_kind": "webpage",
        "artifact_id": "analysis:" + owner["resource_id"],
        "paper_title": "Synthetic official source", "language": "en",
        "profile": {"kind": "whole", "framework": "reference_tree_v5", "markdown_quotes": True,
                    "markdown_folded_quotes": True},
        "claims": [{"claim_id": "task", "role": "abstract", "outline_path": "abstract/task",
                    "title": "Synthetic prediction",
                    "body": "The source describes prediction of three numerical values. It does not establish measured performance, downstream usefulness or a particular implementation. This explanatory body remains distinct from the short editable Canvas navigation.",
                    "canvas_summary": "Predict three values; performance is not established.",
                    "evidence": {"kind": "author_stated", "anchor": "Source prediction paragraph",
                                 "source_spans": [{"kind": "vault_markdown", "source_id": case["source_id"],
                                                   "artifact_id": owner["resource_id"], "vault_path": owner["owner_path"],
                                                   "block_id": "prediction",
                                                   "quote": "The synthetic model predicts three numerical values.",
                                                   "quote_emphasis": ["predicts three numerical values"]}]}}],
    }
    batch_path = case["tmp"] / "batch.json"
    batch_path.write_text(json.dumps({"schema_version": 1, "batch_id": "webpage-cli",
                                      "items": [{"item_id": "one", "zotero_item_key": "ABCD2345",
                                                 "note_stem": "Analysis", "document": document}]}))
    state_db, stage_root = case["tmp"] / "batch.db", case["tmp"] / "stage"
    staged = _invoke(case, ["analysis", "batch-run"], "--request", str(batch_path),
                     "--state-db", str(state_db), "--stage-root", str(stage_root))
    assert staged.exit_code == 0, staged.output
    assert json.loads(staged.output)["items"][0]["state"] == "validated"
    folder = Path(owner["owner_path"]).parent.as_posix()
    paths = {"markdown": folder + "/Analysis.md", "canvas": folder + "/Tree.canvas",
             "sidecar": folder + "/analysis.baseline.json"}
    request = {
        "schema_version": 1, "commit_id": "webpage-cli-commit", "batch_id": "webpage-cli", "item_id": "one",
        "source_state": "validated", "resource_id": owner["resource_id"], "note_stem": "Analysis",
        "document": document, "paths": paths, "base_revisions": dict.fromkeys(paths.values()),
        "base_catalog_revision": owner["catalog_revision"], "base_snapshot_revision": owner["snapshot_revision"],
        "zotero_item_key": "ABCD2345",
        "relations": [{"from_id": owner["resource_id"], "relation": "has-analysis", "to_id": document["artifact_id"]}],
        "projections": [],
    }
    request_path = case["tmp"] / "commit.json"
    request_path.write_text(json.dumps(request))
    committed = _invoke(case, ["analysis", "commit-bundle"], "--request", str(request_path),
                        "--vault-root", str(case["root"]), "--state-db", str(state_db),
                        "--stage-root", str(stage_root), "--commit-state-root", str(case["tmp"] / "commit-state"))
    assert committed.exit_code == 0, committed.output
    receipt = json.loads(committed.output)
    assert receipt["artifact_id"] == document["artifact_id"] and receipt["state"] == "committed"
    assert {row["resource_id"] for row in receipt["change_set"]["upsert_artifacts"]} == {owner["resource_id"]}
    change_path = case["tmp"] / "change.json"
    change_path.write_text(json.dumps(receipt["change_set"]))
    provider = case["home"] / "hub/knowledge-providers" / case["source_id"]
    applied = _invoke(case, ["analysis", "apply-change-set"], "--change-set", str(change_path),
                      "--provider-state-root", str(provider))
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["source_receipt"] == receipt["change_set"]["source_receipt"]
    assert receipt["change_set"]["source_receipt"] == "analysis-commit:webpage-cli-commit"
    snapshot = load_knowledge_provider_snapshot(provider)
    assert {item.kind for item in snapshot.artifacts} == {
        "analysis_markdown", "analysis_canvas", "analysis_sidecar"}
    assert (case["root"] / owner["owner_path"]).read_text() == SOURCE
    markdown = (case["root"] / paths["markdown"]).read_text()
    assert "Webpage Analysis" in markdown and "Whole paper" not in markdown
    assert "**predicts three numerical values**" in markdown
    assert "Source#^prediction" in markdown
    assert "zotero://open-pdf" not in markdown
    canvas = json.loads((case["root"] / paths["canvas"]).read_text())
    for branch in ("Abstract", "Introduction", "Method", "Experiments", "Limitation"):
        assert any(node.get("text") == f"**{branch}**" for node in canvas["nodes"])
    assert not any("zotero://open-pdf" in node.get("text", "") for node in canvas["nodes"])
    checked = _invoke(case, ["analysis", "check-bundle"], str(case["root"] / folder),
                      "--markdown", "Analysis.md", "--canvas", "Tree.canvas",
                      "--sidecar", "analysis.baseline.json", "--require-ir", "5", "--format", "json")
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["status"] == "conformant"
