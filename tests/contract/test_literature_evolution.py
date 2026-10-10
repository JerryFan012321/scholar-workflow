"""Independent, synthetic, zero-write literature evolution contracts."""
from __future__ import annotations

import builtins
import copy
import io
import json
import os
import re
import socket
import subprocess
from contextlib import contextmanager
from pathlib import Path

import jsonschema
import pytest
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

_FIXTURE = Path(__file__).parents[1] / "fixtures/literature-evolution/seven-papers.json"
_PARENTS = {
    ("task-seed", "representation-change"),
    ("representation-change", "alternative-route"),
    ("representation-change", "local-module"),
    ("representation-change", "pipeline-refinement"),
    ("representation-change", "mixed-introduction"),
    ("alternative-route", "mixed-adaptation"),
}


def _doc():
    return json.loads(_FIXTURE.read_bytes())


def _api():
    # Import inside tests so absent new capability is feature RED, not a global collection error.
    from scholar_workflow.knowledge.literature_evolution import render_evolution, validate_evolution

    return validate_evolution, render_evolution


def _files(root):
    return {path.relative_to(root).as_posix(): ("dir",) if path.is_dir() else ("file", path.read_bytes())
            for path in root.rglob("*")}


def test_hand_written_seven_paper_fixture_is_preserved_without_reclassification():
    validate, _ = _api()
    document = _doc()
    before = copy.deepcopy(document)
    normalized = validate(document)
    assert normalized == before and document == before
    assert validate(normalized) == before
    assert len(normalized["papers"]) == 7
    assert [(row["novelty_types"], row["placement"]) for row in normalized["contributions"]] == [
        ([1], "main"), ([2], "main"), ([2], "branch"), ([3], "local"),
        ([4], "local"), ([3], "local"), ([3, 4], "local"), ([], "pending"),
    ]
    assert [row["paper_id"] for row in normalized["contributions"]].count("paper-six") == 2
    assert json.loads(json.dumps(normalized)) == before


def test_scientific_relation_cycle_does_not_become_a_parent_cycle():
    validate, _ = _api()
    document = _doc()
    reverse = copy.deepcopy(document["relations"][1])
    reverse.update(relation_id="forward-alternative", from_id="representation-change",
                   to_id="alternative-route", kind="alternative")
    document["relations"].append(reverse)
    expected = copy.deepcopy(document)
    assert validate(document) == expected


def test_known_type_can_remain_pending_and_unverified_cost_is_not_not_reported():
    validate, render = _api()
    document = _doc()
    pending = document["contributions"][-1]
    pending["novelty_types"] = [3]
    pending["classification"] = copy.deepcopy(document["contributions"][3]["classification"])
    cost = document["relations"][1]["cost"]
    cost.update(text="UNVERIFIED-COST-SENTINEL", basis="unverified", evidence=[])
    assert validate(document) == document
    output = render(document)
    lines = output.splitlines()
    line_index = next(index for index, line in enumerate(lines) if "UNVERIFIED-COST-SENTINEL" in line)
    context = "\n".join(lines[max(0, line_index - 1):line_index + 2]).lower()
    assert re.search(r"unverified|not verified|not checked", context)
    assert "not reported" not in context


def test_new_public_schema_accepts_fixture_and_rejects_unknown_versions_and_fields():
    path = Path(__file__).parents[2] / "contracts/literature-evolution.schema.json"
    schema = json.loads(path.read_bytes())
    validator = jsonschema.Draft202012Validator(schema)
    document = _doc()
    validator.validate(document)
    for version in (2, True, "1"):
        invalid = copy.deepcopy(document)
        invalid["schema_version"] = version
        assert not validator.is_valid(invalid)
    invalid = copy.deepcopy(document)
    invalid["papers"][0]["url"] = "https://example.invalid/not-a-note"
    assert not validator.is_valid(invalid)


def _invalid(case):
    document = _doc()
    contributions, relations = document["contributions"], document["relations"]
    if case == "duplicate-paper-id":
        duplicate = copy.deepcopy(document["papers"][0])
        duplicate.update(source_id="33333333-3333-4333-8333-333333333333", object_id="paper:extra")
        document["papers"].append(duplicate)
    elif case == "duplicate-qualified-paper":
        duplicate = copy.deepcopy(document["papers"][0])
        duplicate["paper_id"] = "paper-extra"
        document["papers"].append(duplicate)
    elif case == "third-class-main":
        contributions[3]["placement"] = "main"
    elif case == "local-missing-parent":
        contributions[3]["parent_id"] = None
    elif case == "branch-missing-parent":
        contributions[2]["parent_id"] = None
    elif case == "pending-parent":
        contributions[-1]["parent_id"] = "task-seed"
    elif case == "parent-cycle":
        contributions[0]["parent_id"] = "representation-change"
    elif case == "parent-pending":
        contributions[3]["parent_id"] = "pending-contribution"
    elif case == "unknown-paper-reference":
        contributions[0]["paper_id"] = "paper-absent"
    elif case == "unknown-relation-endpoint":
        relations[0]["to_id"] = "contribution-absent"
    elif case == "not-reported-with-evidence":
        relations[1]["cost"]["evidence"] = copy.deepcopy(relations[1]["change"]["evidence"])
    elif case == "reported-without-evidence":
        relations[0]["change"]["evidence"] = []
    elif case == "nonpending-unverified-classification":
        contributions[0]["classification"]["basis"] = "unverified"
    elif case == "boolean-page-index":
        contributions[0]["classification"]["evidence"][0]["page_index"] = True
    elif case == "boolean-novelty-type":
        contributions[0]["novelty_types"] = [True]
    elif case == "unsafe-note-traversal":
        document["papers"][0]["note_path"] = "../outside.md"
    else:
        raise AssertionError(f"Unknown independent test case: {case}")
    return document


@pytest.mark.parametrize("case", [
    "duplicate-paper-id", "duplicate-qualified-paper", "third-class-main",
    "local-missing-parent", "branch-missing-parent", "pending-parent", "parent-cycle",
    "parent-pending", "unknown-paper-reference", "unknown-relation-endpoint",
    "not-reported-with-evidence", "reported-without-evidence", "nonpending-unverified-classification",
    "boolean-page-index", "boolean-novelty-type", "unsafe-note-traversal",
])
def test_invalid_semantics_refuse_in_validator_and_renderer(case):
    validate, render = _api()
    document = _invalid(case)
    before = copy.deepcopy(document)
    with pytest.raises(ValueError):
        validate(document)
    with pytest.raises(ValueError):
        render(document)
    assert document == before


@pytest.mark.parametrize("level", ["root", "statement", "evidence"])
def test_unknown_nested_fields_are_not_silently_discarded(level):
    validate, _ = _api()
    document = _doc()
    statement = document["contributions"][0]["classification"]
    destination = {"root": document, "statement": statement, "evidence": statement["evidence"][0]}[level]
    destination["unexpected"] = "must refuse"
    with pytest.raises(ValueError):
        validate(document)


def test_human_preview_is_complete_bilingual_and_does_not_claim_source_verification():
    _, render = _api()
    for language in ("en", "zh"):
        document = _doc()
        document["language"] = language
        output = render(document)
        assert not re.search(r"(?m)^#\s", output)
        assert document["topic"] in output and document["corpus_scope"] in output
        for paper in document["papers"]:
            assert paper["title"] in output and paper["note_path"] in output
            assert paper["source_id"] not in output and paper["object_id"] not in output
        for contribution in document["contributions"]:
            assert contribution["title"] in output and contribution["classification"]["text"] in output
        for relation in document["relations"]:
            for slot in ("change", "reason", "benefit", "cost", "conditions"):
                assert relation[slot]["text"] in output
        meanings = ([r"papers|paper ledger", r"contributions", r"relations", r"change", r"reason|rationale",
                     r"benefit|gain", r"cost", r"conditions", r"author.statement|author.stated",
                     r"experimental.result", r"analysis.inference", r"not.reported", r"pending",
                     r"synthetic", r"not.verified|unverified|not.checked"] if language == "en" else
                    [r"论文", r"贡献", r"关系", r"变更|改变", r"原因|理由", r"收益|获益", r"代价|成本",
                     r"条件", r"作者陈述|作者声明", r"实验结果", r"分析推断", r"未报告", r"待定",
                     r"合成", r"未核验|未检查"])
        for meaning in meanings:
            assert re.search(meaning, output, re.IGNORECASE), meaning
        if language == "zh":
            assert not re.search(r"(?mi)^#{2,6}\s+(Papers|Contributions|Relations)\b", output)
        else:
            assert not any(label in output for label in ("待定", "未报告", "未核验"))
        assert "zotero://open-pdf/library/items/BCDE3456?page=3" in output
        assert "zotero://open-pdf/groups/456/items/CDEF4567?page=5" in output
        assert "sha256:" not in output and "127.0.0.1" not in output and "[[" not in output
        graph = re.search(r"```mermaid\s+(.*?)```", output, re.DOTALL)
        assert graph and re.search(r"flowchart\s+(TD|TB)\b", graph[1])
        nodes = re.findall(r'(?m)^\s*([A-Za-z0-9_-]+)\s*\[\s*"([^"]+)"\s*\]', graph[1])
        by_node = {}
        for node_id, label in nodes:
            matches = [row for row in document["contributions"] if row["title"] in label]
            if matches:
                by_node[node_id] = max(matches, key=lambda row: len(row["title"]))["contribution_id"]
        edges = re.findall(r"(?m)^\s*([A-Za-z0-9_-]+)\s*(?:-->|---)\s*([A-Za-z0-9_-]+)", graph[1])
        assert edges
        mapped = {(by_node[first], by_node[second]) for first, second in edges}
        assert mapped == _PARENTS
        assert ("task-seed", "representation-change") in mapped
        assert ("alternative-route", "representation-change") not in mapped


def test_special_title_is_literal_not_html_javascript_wikilink_or_graph_injection():
    _, render = _api()
    document = _doc()
    attack = 'Payload [x](javascript:alert(1)) <script>x</script> ![[secret]] "] --> injected["x'
    document["papers"][0]["title"] = attack
    document["contributions"][0]["title"] = attack
    output = render(document)
    assert "Payload" in output and "secret" in output
    assert not re.search(r"(?<!\\)<script\b", output, re.IGNORECASE)
    assert not re.search(r"(?<!\\)\[[^\]\n]+\]\(\s*javascript:", output, re.IGNORECASE)
    assert not re.search(r"(?<!\\)!\[\[", output)
    graph = re.search(r"```mermaid\s+(.*?)```", output, re.DOTALL)
    assert graph and not re.search(r"(?m)^\s*injected\b", graph[1])
    assert '"] --> injected["' not in graph[1]


@contextmanager
def _preview_guard(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Pure literature preview accessed config/registry/network/execution or wrote files")

    def stream_guard(original):
        def checked(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                forbidden()
            return original(file, mode, *args, **kwargs)
        return checked

    original_open = os.open

    def checked_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            forbidden()
        return original_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        for name in ("_load_cfg", "_local_field_service", "_zotero_adapter"):
            patch.setattr(cli, name, forbidden)
        for name in ("load_document", "resolve", "revision"):
            patch.setattr(KnowledgeSourceRegistry, name, forbidden)
        patch.setattr(subprocess, "run", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(os, "system", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(builtins, "open", stream_guard(builtins.open))
        patch.setattr(io, "open", stream_guard(io.open))
        patch.setattr(os, "open", checked_open)
        for name in ("mkdir", "makedirs", "unlink", "remove", "rename", "replace", "symlink"):
            patch.setattr(os, name, forbidden)
        yield


@pytest.mark.parametrize("input_mode,fmt", [("file", "md"), ("file", "json"),
                                          ("stdin", "md"), ("stdin", "json")])
def test_cli_file_and_stdin_preview_need_no_config_and_write_nothing(tmp_path, monkeypatch, input_mode, fmt):
    _api()  # Preload new capability before applying the production I/O guard.
    document = _doc()
    serialized = json.dumps(document)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        root = Path.cwd()
        input_path = root / "synthetic-evolution.json"
        input_path.write_text(serialized, encoding="utf-8")
        before = _files(root)
        with _preview_guard(monkeypatch):
            result = runner.invoke(cli.main, ["literature-preview", "--input",
                                             str(input_path) if input_mode == "file" else "-",
                                             "--format", fmt],
                                   input=serialized if input_mode == "stdin" else None)
        assert result.exit_code == 0, result.output
        if fmt == "json":
            assert json.loads(result.output) == document
        else:
            assert document["topic"] in result.output and "Synthetic Unclassified Resource" in result.output
            assert not re.search(r"(?m)^#\s", result.output)
        assert _files(root) == before


def test_invalid_cli_input_does_not_print_a_partial_success_preview(tmp_path, monkeypatch):
    _api()
    document = _invalid("unknown-relation-endpoint")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        root = Path.cwd()
        before = _files(root)
        with _preview_guard(monkeypatch):
            result = runner.invoke(cli.main, ["literature-preview", "--input", "-", "--format", "md"],
                                   input=json.dumps(document))
        assert result.exit_code != 0
        assert "```mermaid" not in result.output
        assert _files(root) == before
