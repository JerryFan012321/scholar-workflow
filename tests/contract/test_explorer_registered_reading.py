"""Read a declared local unit without claiming global uniqueness or granting writes."""
# ruff: noqa: F811 - explicit shared fixture injection
import json
import threading
import urllib.error
import urllib.request

import pytest

from scholar_workflow.knowledge.exploration import ExplorationError, default_data
from scholar_workflow.knowledge.exploration_import import import_paper_units
from scholar_workflow.knowledge.fields import FieldRegistryError
from tests.contract.test_field_paper_units import (
    ALPHA,
    SOURCE_A,
    _query,
    paper_unit_corpus,  # noqa: F401
)
from tests.contract.test_knowledge_ownership import ownership_scope  # noqa: F401


def pending_inventory(corpus):
    corpus.external_provider.unlink()
    return _query(corpus)


def test_local_read_proof_does_not_change_incomplete_global_owner(paper_unit_corpus):
    payload = pending_inventory(paper_unit_corpus)
    unit = next(row for row in payload["paper_units"] if row["resource_id"] == ALPHA)
    assert unit["ownership"]["status"] == "incomplete"
    assert unit["local_read_state"] == "declared"
    assert all(row["local_read_state"] == "declared" for row in unit["files"])
    assert all(row["uri"] is None for row in unit["files"])
    with pytest.raises(ExplorationError):
        import_paper_units(paper_unit_corpus.scope.root, default_data(), payload,
                           source_roots=paper_unit_corpus.scope.source_roots)


def test_pending_read_projection_is_whole_unit_and_keeps_diagnostics(paper_unit_corpus):
    from scholar_workflow.knowledge.exploration_import import preview_paper_units

    corpus = paper_unit_corpus
    payload = pending_inventory(corpus)
    payload["paper_units"] = [row for row in payload["paper_units"] if row["resource_id"] == ALPHA]
    data = preview_paper_units(corpus.scope.root, payload, source_roots=corpus.scope.source_roots)
    assert len(data["works"]) == 1
    work = data["works"][0]
    assert work["entity_ref"] == {"source_id": SOURCE_A, "object_id": ALPHA}
    assert len(work["assets"]) == len(payload["paper_units"][0]["files"])
    assert any("归属" in message for message in work["asset_diagnostics"])
    assert not (corpus.scope.root / ".scholar-workflow/exploration.yml").exists()
    for failure in ("conflict", "incomplete-local", "unsafe"):
        import copy
        changed = copy.deepcopy(payload)
        unit = changed["paper_units"][0]
        if failure == "conflict":
            unit["ownership"]["status"] = "conflict"
        elif failure == "incomplete-local":
            unit["local_read_state"] = "unverified"
        else:
            unit["files"][0]["file_state"] = "unsafe"
        with pytest.raises(ExplorationError):
            preview_paper_units(corpus.scope.root, changed, source_roots=corpus.scope.source_roots)


def test_reading_http_cannot_save_even_with_valid_model(paper_unit_corpus):
    from scholar_workflow.knowledge.exploration_import import preview_paper_units
    from tests.contract.explorer_fixture import fixture_server as make_server

    corpus = paper_unit_corpus
    payload = pending_inventory(corpus)
    payload["paper_units"] = [row for row in payload["paper_units"] if row["resource_id"] == ALPHA]
    data = preview_paper_units(corpus.scope.root, payload, source_roots=corpus.scope.source_roots)
    before = {p: p.read_bytes() for p in corpus.scope.root.rglob("*") if p.is_file()}

    class Reading:
        def load(self):
            return {"data": data, "revision": "read-only:synthetic", "read_only": True,
                    "diagnostics": ["归属待核实；只读展示。"]}

    server, token = make_server(corpus.scope.root, reading_store=Reading())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, payload=None):
        req = urllib.request.Request(base + path, data=(json.dumps(payload).encode()
                                      if payload is not None else None), headers={
            "Authorization": f"Bearer {token}", "Origin": base, "Content-Type": "application/json"})
        try:
            response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    try:
        assert request("/api/state")[1]["read_only"] is True
        assert request("/api/query", {})[1]["works"][0]["id"] == data["works"][0]["id"]
        work = data["works"][0]
        asset = work["assets"][0]
        assert request(f"/api/preview/{work['id']}/{asset['id']}")[0] == 200
        assert request("/api/save", {"data": data, "expected_revision": "read-only:synthetic"})[0] == 403
        assert request("/api/unit-reference", {})[0] == 403
        assert request("/api/query", {"_draft": {**data, "works": []}})[0] in {400, 403}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert before == {p: p.read_bytes() for p in corpus.scope.root.rglob("*") if p.is_file()}


def test_live_reading_service_uses_actual_inventory_and_rechecks_changes(paper_unit_corpus, monkeypatch):
    from scholar_workflow.workflows import exploration_references as module

    corpus = paper_unit_corpus
    pending_inventory(corpus)
    original = module.field_asset_units

    def actual_inventory(path, **kwargs):
        return original(path, **kwargs, reader_config_path=corpus.reader_config)

    monkeypatch.setattr(module, "field_asset_units", actual_inventory)
    service = module.ExplorationReferenceService(corpus.scope.registry.path)
    from tests.contract.test_field_paper_units import FIELD_A
    result = service.reading_snapshot(corpus.scope.root, SOURCE_A, FIELD_A)
    assert result["read_only"] and len(result["data"]["works"]) == 2
    assert all(work["entity_ref"]["source_id"] == SOURCE_A for work in result["data"]["works"])
    assert result["diagnostics"] and not (corpus.scope.root / ".scholar-workflow/exploration.yml").exists()
    corpus.scope.provider.unlink()
    with pytest.raises((ExplorationError, FieldRegistryError)):
        service.reading_snapshot(corpus.scope.root, SOURCE_A, FIELD_A)


@pytest.mark.parametrize("selector", ["--source-id", "--field-id"])
def test_reading_cli_requires_both_selectors_before_any_service(tmp_path, selector):
    from click.testing import CliRunner

    from scholar_workflow.knowledge.exploration_cli import explore

    result = CliRunner().invoke(explore, ["--root", str(tmp_path), selector, "fixture", "--no-open"])
    assert result.exit_code == 2 and "both" in result.output
    assert list(tmp_path.iterdir()) == []
