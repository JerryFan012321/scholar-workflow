"""Real synthetic provider-to-HTTP unit references; no paper-body or external reads."""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

from scholar_workflow.adapters.knowledge_explorer import make_server
from scholar_workflow.knowledge.exploration import default_data
from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
from tests.contract.test_field_paper_units import (
    ALPHA,
    FIELD_A,
    GAMMA,
    READY_FILES,
    SOURCE_A,
    SOURCE_B,
    VAULT_A,
    VAULT_B,
    _filesystem,
    _query_guard,
    ownership_scope,  # noqa: F401
    paper_unit_corpus,  # noqa: F401
)


def test_real_registered_units_referenced_over_http_without_source_or_state_writes(
    paper_unit_corpus, monkeypatch,
):
    from scholar_workflow.workflows import exploration_references

    corpus = paper_unit_corpus
    root = corpus.scope.temporary / "empty-exploration-root"
    root.mkdir()
    service = ExplorationReferenceService(registry_path=corpus.scope.registry.path)
    server, token = make_server(root, reference_service=service)
    base = f"http://127.0.0.1:{server.server_port}"
    before = _filesystem(corpus.scope.temporary)
    provider_calls = []
    external_enrichment = []

    def guarded_provider(registry_path, **kwargs):
        # The guard denies body content, writes, native calls and new network
        # connections only while the provider reads its exact declarations.
        with _query_guard(corpus) as (workflow, _patch):
            result = workflow.field_paper_units(
                registry_path, reader_config_path=corpus.reader_config, **kwargs,
            )
        provider_calls.append((registry_path, kwargs))
        return result

    def no_external_zotero(payload):
        external_enrichment.append(True)
        return deepcopy(payload)

    monkeypatch.setattr(exploration_references, "field_paper_units", guarded_provider)
    monkeypatch.setattr(exploration_references, "include_resource_links", no_external_zotero)

    def request(path, payload=None):
        headers = {"Authorization": f"Bearer {token}"}
        if payload is not None:
            headers.update({"Content-Type": "application/json", "Origin": base})
        req = urllib.request.Request(
            base + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def asset_destinations(work):
        result = set()
        for asset in work["assets"]:
            uri = urlsplit(asset["uri"])
            assert uri.scheme == "obsidian" and uri.netloc == "open"
            query = parse_qs(uri.query)
            result.add((query["vault"][0], query["file"][0]))
        return result

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        choice = {"source_id": SOURCE_A, "field_id": FIELD_A}
        status, options = request("/api/unit-options", choice)
        assert status == 200, options
        units = {(row["entity_ref"]["source_id"], row["entity_ref"]["object_id"]): row
                 for row in options["units"]}
        assert units[SOURCE_A, ALPHA]["asset_count"] == len(READY_FILES[SOURCE_A, ALPHA])
        assert units[SOURCE_B, GAMMA]["asset_count"] == len(READY_FILES[SOURCE_B, GAMMA])

        ref = {"source_id": SOURCE_A, "object_id": ALPHA}
        status, proposed = request("/api/unit-reference", {
            **choice, "data": default_data(), "unit_refs": [ref],
        })
        assert status == 200, proposed
        model = proposed["data"]
        assert len(model["works"]) == 1
        work = model["works"][0]
        assert work["entity_ref"] == ref
        assert len(work["assets"]) == len(READY_FILES[SOURCE_A, ALPHA])
        assert asset_destinations(work) == {
            (VAULT_A, relative) for relative in READY_FILES[SOURCE_A, ALPHA].values()
        }

        status, repeated = request("/api/unit-reference", {
            **choice, "data": model, "unit_refs": [ref],
        })
        assert status == 200, repeated
        assert repeated["data"] == model

        # Multi-dimensional conditional records keep their one paper-unit result.
        model["records"] = [{"id": "condition-" + str(index), "work_id": work["id"],
                              "dimensions": {}, "conditions": {"Data split": split},
                              "result": "Synthetic result", "evidence": [work["assets"][0]["id"]],
                              "assessment": "Synthetic condition only", "origin": "local"}
                             for index, split in enumerate(("train", "held-out"))]
        status, matched = request("/api/query", {"_draft": model})
        assert status == 200, matched
        assert len(matched["works"]) == 1 and len(matched["records"]) == 2

        # A same-title paper in another registered Source remains a separate unit.
        status, external = request("/api/unit-reference", {
            **choice, "data": model,
            "unit_refs": [{"source_id": SOURCE_B, "object_id": GAMMA}],
        })
        assert status == 200, external
        works = external["data"]["works"]
        assert len(works) == 2 and works[0]["title"] == works[1]["title"]
        assert works[0]["id"] != works[1]["id"]
        assert works[1]["entity_ref"] == {"source_id": SOURCE_B, "object_id": GAMMA}
        assert asset_destinations(works[1]) == {
            (VAULT_B, relative) for relative in READY_FILES[SOURCE_B, GAMMA].values()
        }
        assert external["data"]["records"] == model["records"]

        status, unknown = request("/api/unit-reference", {
            **choice, "data": model,
            "unit_refs": [{"source_id": SOURCE_A, "object_id": "paper:synthetic:absent"}],
        })
        assert status == 400 and "current Field inventory" in unknown["error"]
        assert request("/api/state")[1]["revision"] is None
        assert list(root.iterdir()) == []
        assert len(provider_calls) == 5
        assert len(external_enrichment) == 3
        assert all(path == corpus.scope.registry.path and kwargs == {
            "source_id": SOURCE_A, "field_id": FIELD_A, "include_resource_links": True,
        } for path, kwargs in provider_calls)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert _filesystem(corpus.scope.temporary) == before
