"""Independent checks for a non-writing, test-root-limited registration fixture."""
# ruff: noqa: F811
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.contract.test_knowledge_ownership import (
    SOURCE_A,
    _add_source,
    _filesystem,
    ownership_scope,  # noqa: F401
)

_SPEC = importlib.util.spec_from_file_location("registration_fixture", Path(__file__).parents[2] /
                                             "dev-guide/demos/prepare_registered_experiment.py")
fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fixture)


def test_projection_keeps_only_selected_test_sources_and_all_original_bytes(ownership_scope):
    scope = ownership_scope
    _add_source(scope)
    before = _filesystem(scope.temporary)
    files, audit = fixture.prepare(scope.registry.path, scope.temporary / "experiment",
                                 test_root=scope.root)
    assert len(audit) == 1 and len(files) == 3
    selected = json.loads(files["hub/sources.json"])
    assert [row["source_id"] for row in selected["sources"]] == [SOURCE_A]
    assert {row["root"] for row in selected["folders"]} == {str(scope.root)}
    assert all(row["path_and_inode_match"] and row["content_hashes_preserved"] for row in audit)
    assert _filesystem(scope.temporary) == before


@pytest.mark.parametrize("change", ["path", "inode"])
def test_projection_refuses_relocation_or_replacement(ownership_scope, change):
    scope = ownership_scope
    value = json.loads(scope.provider.read_bytes())
    value["snapshot_revision"] = ""
    if change == "path":
        value["vault_binding"]["root_path"] += "-other"
    else:
        value["vault_binding"]["inode"] += 1
    from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
    scope.provider.write_text(KnowledgeProviderSnapshot.model_validate(value).model_dump_json())
    with pytest.raises(ValueError, match="identical path and inode"):
        fixture.prepare(scope.registry.path, scope.temporary / "experiment", test_root=scope.root)


def test_device_drift_changes_no_artifact_or_catalog_fields(ownership_scope):
    scope = ownership_scope
    from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
    value = json.loads(scope.provider.read_bytes())
    value["snapshot_revision"] = ""
    value["vault_binding"]["device"] += 1
    original = KnowledgeProviderSnapshot.model_validate(value)
    scope.provider.write_text(original.model_dump_json())
    before = _filesystem(scope.temporary)
    files, audit = fixture.prepare(scope.registry.path, scope.temporary / "experiment",
                                 test_root=scope.root)
    projected = json.loads(files[f"hub/knowledge-providers/{SOURCE_A}/knowledge-provider.snapshot.json"])
    assert projected["vault_binding"]["device"] == scope.root.stat().st_dev
    assert projected["catalog"] == original.model_dump(mode="json")["catalog"]
    assert projected["artifacts"] == original.model_dump(mode="json")["artifacts"]
    assert audit[0]["previous_device"] != audit[0]["observed_device"]
    assert _filesystem(scope.temporary) == before


def _labeled_store_module():
    spec = importlib.util.spec_from_file_location(
        "registered_experiment_server", Path(__file__).parents[2]
        / "dev-guide/demos/serve_registered_experiment.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_experiment_label_preserves_real_diagnostics_and_data():
    current = {"data": {"works": []}, "revision": "unchanged",
               "diagnostics": ["A real provider remains unavailable."]}
    labeled = _labeled_store_module().LabeledStore(SimpleNamespace(load=lambda: current))
    actual = labeled.load()
    assert actual["data"] is current["data"]
    assert actual["revision"] == "unchanged"
    assert actual["diagnostics"][0] == current["diagnostics"][0]
    assert len(actual["diagnostics"]) == 3
    assert current["diagnostics"] == ["A real provider remains unavailable."]


def test_experiment_save_delegates_the_exact_revision_and_data():
    calls = []
    current = {"data": {"works": []}, "revision": "after"}
    inner = SimpleNamespace(load=lambda: current,
                            save=lambda *args, **kwargs: calls.append((args, kwargs)))
    labeled = _labeled_store_module().LabeledStore(inner)
    proposed = {"works": []}
    actual = labeled.save(proposed, expected_revision="before")
    assert calls == [((proposed,), {"expected_revision": "before"})]
    assert actual["data"] is current["data"] and actual["revision"] == "after"
