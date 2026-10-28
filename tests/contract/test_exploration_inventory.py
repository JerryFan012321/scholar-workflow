"""An opt-in inventory carries existing provider identities without reading paper bodies."""
# ruff: noqa: F811 - pytest fixture import
from scholar_workflow.workflows.field_paper_units import field_paper_units
from tests.contract.test_field_paper_units import (
    ALPHA,
    FIELD_A,
    SOURCE_A,
    _query_guard,
    _save_snapshot_input,
    _snapshot_input,
    paper_unit_corpus,  # noqa: F401
)
from tests.contract.test_knowledge_ownership import ownership_scope  # noqa: F401


def test_opt_in_resource_links_have_exact_qualified_identity(paper_unit_corpus):
    corpus = paper_unit_corpus
    snapshot = _snapshot_input(corpus.scope.provider)
    resource = next(row for row in snapshot["catalog"]["resources"] if row["resource_id"] == ALPHA)
    resource["identifiers"] = {"url": "https://example.test/original", "doi": "10.1234/example"}
    resource["zotero"] = {"item_key": "ABCDEFGH", "attachment_key": "JKLMNPQR"}
    _save_snapshot_input(corpus.scope.provider, snapshot)
    options = {"source_id": SOURCE_A, "field_id": FIELD_A,
               "reader_config_path": corpus.reader_config}
    with _query_guard(corpus):
        regular = field_paper_units(corpus.scope.registry.path, **options)
        assert all("catalog_resource" not in unit for unit in regular["paper_units"])
        enriched = field_paper_units(corpus.scope.registry.path, include_resource_links=True, **options)
    selected = next(unit for unit in enriched["paper_units"]
                    if unit["source_id"] == SOURCE_A and unit["resource_id"] == ALPHA)
    assert selected["catalog_resource"]["identifiers"]["url"] == "https://example.test/original"
    assert selected["catalog_resource"]["zotero"]["attachment_key"] == "JKLMNPQR"
    for unit in enriched["paper_units"]:
        if unit.get("catalog_resource"):
            assert unit["catalog_resource"]["resource_id"] == unit["resource_id"]
