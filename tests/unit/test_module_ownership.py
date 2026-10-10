"""Prepared ownership/compatibility checks; all fixtures are in-memory or source-only."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "scholar_workflow"
LEGACY_MODULES = (
    ("hub.fields", "knowledge.fields", "FieldService", "_safe_relative"),
    ("hub.models", "knowledge.catalog_models", "HubCatalog", "_ensure_unique"),
    (
        "hub.obsidian_contract",
        "knowledge.obsidian_contract",
        "MANAGED_FRONTMATTER_FIELDS",
        "content_revision",
    ),
)
KNOWLEDGE_EXPORTS = (
    "ATOMIC_RESOURCE_KINDS",
    "CoreDocumentKind",
    "SupportingDocumentKind",
    "_validate_vault_path",
    "KnowledgeAtomicResource",
    "KnowledgeCoreDocument",
    "KnowledgeSupportingDocument",
    "KnowledgeManifest",
    "KnowledgeRelation",
    "KnowledgeProjection",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return imported


@pytest.mark.parametrize("relative", (
    "models.py", "catalog_models.py", "fields.py", "obsidian_contract.py", "literature_evolution.py",
))
def test_knowledge_core_does_not_import_hub_or_analysis(relative: str) -> None:
    imported = _imports(SOURCE_ROOT / "knowledge" / relative)
    assert not any(
        name in {"scholar_workflow.hub", "scholar_workflow.analysis"}
        or name.startswith(("scholar_workflow.hub.", "scholar_workflow.analysis."))
        for name in imported
    )


@pytest.mark.parametrize("legacy_name,canonical_name,public_name,helper_name", LEGACY_MODULES)
def test_legacy_module_alias_preserves_public_and_private_identity(
    legacy_name: str,
    canonical_name: str,
    public_name: str,
    helper_name: str,
) -> None:
    legacy = importlib.import_module(f"scholar_workflow.{legacy_name}")
    canonical = importlib.import_module(f"scholar_workflow.{canonical_name}")
    assert legacy is canonical
    assert getattr(legacy, public_name) is getattr(canonical, public_name)
    assert getattr(legacy, helper_name) is getattr(canonical, helper_name)


def test_legacy_private_helper_monkeypatch_targets_the_canonical_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = importlib.import_module("scholar_workflow.hub.fields")
    canonical = importlib.import_module("scholar_workflow.knowledge.fields")
    seen: list[str] = []

    def observe(value: str, *, allow_dot: bool = False) -> str:
        seen.append(value)
        return value

    monkeypatch.setattr(legacy, "_safe_relative", observe)
    assert canonical._markdown_relative("note.md") == "note.md"
    assert seen == ["note.md"]


@pytest.mark.parametrize("export_name", KNOWLEDGE_EXPORTS)
def test_analysis_reexports_the_same_knowledge_type(export_name: str) -> None:
    legacy = importlib.import_module("scholar_workflow.analysis.models")
    canonical = importlib.import_module("scholar_workflow.knowledge.models")
    assert getattr(legacy, export_name) is getattr(canonical, export_name)


def test_knowledge_type_names_and_manifest_fields_remain_compatible() -> None:
    models = importlib.import_module("scholar_workflow.knowledge.models")
    assert models.KnowledgeManifest.model_json_schema()["title"] == "KnowledgeManifest"
    assert set(models.KnowledgeManifest.model_fields) == {
        "schema_version", "atomic_resources", "core_documents", "supporting_documents",
    }
    assert [value.value for value in models.CoreDocumentKind] == ["charter", "survey", "catalog"]
    assert [value.value for value in models.SupportingDocumentKind] == [
        "analysis", "analysis_canvas", "annotations", "reading_note", "attachment",
    ]
    assert models.KnowledgeManifest().model_dump(mode="json") == {
        "schema_version": 1,
        "atomic_resources": [],
        "core_documents": [],
        "supporting_documents": [],
    }


def test_native_content_callers_use_the_knowledge_owner() -> None:
    moved_paths = {
        "scholar_workflow.hub.models",
        "scholar_workflow.hub.fields",
        "scholar_workflow.hub.obsidian_contract",
    }
    for directory in ("analysis", "workflows", "adapters"):
        for path in (SOURCE_ROOT / directory).glob("*.py"):
            assert not (_imports(path) & moved_paths), path.relative_to(SOURCE_ROOT)
