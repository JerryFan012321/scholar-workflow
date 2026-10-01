"""Prepared schema and architecture contracts for the explicit project overview."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import jsonschema
import pytest

from scholar_workflow.project.context import (
    ProjectContext,
    build_project_overview,
    render_project_overview,
)

ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = "11111111-1111-4111-8111-111111111111"


def _payload() -> dict:
    return {
        "schema_version": 1, "project_id": PROJECT_ID,
        "title": "One synthetic project", "summary": "Code, source material, and outcomes.",
        "entries": [
            {"entry_id": "source", "kind": "code", "title": "Source", "purpose": "Reproduces the method.",
             "ref": {"kind": "project-file", "relative_path": "src", "commit": None}},
            {"entry_id": "paper", "kind": "paper", "title": "Reference paper", "purpose": "Defines the baseline.",
             "ref": {"kind": "external-resource", "provider": "zotero", "resource_id": "ABCD2345",
                     "uri": "zotero://open-pdf/library/items/ABCD2345"}},
            {"entry_id": "note", "kind": "note", "title": "Interpretation", "purpose": "Records design choices.",
             "ref": {"kind": "external-resource", "provider": "obsidian", "resource_id": "sample-note", "uri": None}},
        ],
    }


def test_context_payload_matches_public_schema() -> None:
    schema = json.loads((ROOT / "contracts/project-context.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_payload(), schema)
    model = ProjectContext.model_validate(_payload())
    jsonschema.validate(model.model_dump(mode="json"), schema)


@pytest.mark.parametrize("path", ["/tmp/file", "../file", "src/../file", "src//file", "src\\file", "./file", "src/"])
def test_public_schema_rejects_escaping_paths(path: str) -> None:
    schema = json.loads((ROOT / "contracts/project-context.schema.json").read_text(encoding="utf-8"))
    payload = _payload()
    payload["entries"][0]["ref"]["relative_path"] = path
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_public_schema_rejects_provider_uri_mismatch() -> None:
    schema = json.loads((ROOT / "contracts/project-context.schema.json").read_text(encoding="utf-8"))
    payload = _payload()
    payload["entries"][1]["ref"]["uri"] = "obsidian://open?file=note"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_zotero_identity_can_use_zotflow_reader_projection() -> None:
    schema = json.loads((ROOT / "contracts/project-context.schema.json").read_text(encoding="utf-8"))
    payload = _payload()
    payload["entries"][1]["ref"]["uri"] = "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCD2345"
    jsonschema.validate(payload, schema)
    model = ProjectContext.model_validate(payload)
    assert model.entries[1].ref.provider == "zotero"


@pytest.mark.parametrize("uri", [
    "obsidian://advanced-uri?vault=test&commandid=run",
    "obsidian://new?vault=test&file=note",
    "obsidian://open?vault=test&file=note&command=run",
])
def test_public_schema_rejects_non_reader_routes(uri: str) -> None:
    schema = json.loads((ROOT / "contracts/project-context.schema.json").read_text(encoding="utf-8"))
    payload = _payload()
    payload["entries"][2]["ref"]["uri"] = uri
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_overview_has_no_hub_or_external_execution_dependency() -> None:
    for filename in ("layout.py", "context.py"):
        source = (ROOT / "src/scholar_workflow/project" / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
        assert not any(name.startswith("scholar_workflow.hub") for name in imports)
        assert not any(name.split(".")[0] in {"httpx", "requests", "subprocess", "webbrowser", "socket"} for name in imports)
        assert "rglob(" not in source and ".glob(" not in source


def test_shared_layout_keeps_initializer_standard_library_only() -> None:
    tree = ast.parse((ROOT / "src/scholar_workflow/project/layout.py").read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name.split(".")[0] in {"pydantic", "yaml", "jsonschema", "httpx"} for name in imports)
    assert not any(name.startswith("scholar_workflow") for name in imports)


def test_single_project_overview_all_kinds_without_service(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "project-layout.json").write_text(json.dumps({
        "schema_version": 2, "project_id": PROJECT_ID, "language": "python",
        "package": None, "source_profile": None, "addons": [],
    }), encoding="utf-8")
    (root / "src").mkdir()
    payload = _payload()
    for kind in ("analysis", "experiment", "result", "other"):
        payload["entries"].append({
            "entry_id": kind, "kind": kind, "title": kind.title(),
            "purpose": f"Explains this project's {kind} material.",
            "ref": {"kind": "project-file", "relative_path": f"docs/{kind}.md"},
        })
    (root / "project-context.json").write_text(json.dumps(payload), encoding="utf-8")
    overview = build_project_overview(root)
    markdown = render_project_overview(overview)
    assert len(overview.entries) == 7
    for heading in ("Code", "Papers", "Analyses", "Knowledge notes", "Experiments", "Results", "Other material"):
        assert f"## {heading}" in markdown
    assert "Purpose:" in markdown and "Status:" in markdown
    assert "HTTP" not in markdown and "Hub" not in markdown
    assert str(root) not in markdown and PROJECT_ID not in markdown
