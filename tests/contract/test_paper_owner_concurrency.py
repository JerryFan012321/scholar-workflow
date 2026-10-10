"""One offline, real-process race for a single canonical paper owner."""
from __future__ import annotations

import json
import multiprocessing
import time
from pathlib import Path
from types import SimpleNamespace

import yaml

from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.workflows.register_paper import paper_plan, register_paper

_TIMEOUT_SECONDS = 30
_PAPER_ID = "paper:zotero:123:ABCD2345"
_PAPER_PATH = "resources/papers/concurrent-paper/Paper.md"
_README = b"# Existing Source home\n\nHuman text must remain unchanged.\n"
_PDF = b"%PDF-1.7 synthetic concurrency fixture, not a real paper\n"


class _LocalPaper:
    """Fixed local metadata/locator fake; it performs no external calls."""

    def __init__(self, pdf: Path):
        self.pdf = pdf

    def get_item(self, key: str) -> dict:
        assert key in {"ABCD2345", "EFGH2345"}
        data = ({"itemType": "preprint", "title": "Synthetic concurrent paper"}
                if key == "ABCD2345" else
                {"itemType": "attachment", "parentItem": "ABCD2345",
                 "contentType": "application/pdf", "linkMode": "imported_file"})
        return {"key": key, "library": {"id": 123, "type": "user"}, "data": data}

    def resolve_attachment_locator(self, key: str):
        assert key == "EFGH2345"
        return SimpleNamespace(path=self.pdf, attachment_key=key, library_id="123")


def _register_once(registry_path: str, pdf_path: str, selection: dict,
                   approved_digest: str, start, ready, results) -> None:
    """Top-level worker is importable by spawn on both macOS and Linux."""
    source_id = selection["source_id"]
    ready.put(source_id)
    try:
        if not start.wait(timeout=_TIMEOUT_SECONDS):
            raise TimeoutError("Test start event was never released")
        result = register_paper(
            KnowledgeSourceRegistry(Path(registry_path)), _LocalPaper(Path(pdf_path)),
            approved_digest=approved_digest, **selection,
        )
    except FieldRegistryError as exc:
        results.put({"source_id": source_id, "status": "refused",
                     "error_type": "FieldRegistryError", "detail": str(exc)})
    except Exception as exc:
        results.put({"source_id": source_id, "status": "unexpected-error",
                     "error_type": type(exc).__name__, "detail": str(exc)})
        raise
    else:
        results.put({"source_id": source_id, "status": result["status"]})


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Concurrent paper registration exceeded its test deadline")
    return remaining


def _initialize(service: FieldService, root: Path):
    from scholar_workflow.workflows.register_source import register_source

    proposal = registration_plan(service, root, field_root=".", existing_source=False)
    assert proposal.payload["inventory_initialization"] == "new-empty-provider"
    return register_source(service, root, field_root=".", existing_source=False,
                           approved_digest=proposal.payload["approved_digest"])


def test_same_paper_concurrent_sources_create_exactly_one_owner(tmp_path: Path):
    """Two legitimate pre-race plans compete; either Source may be the winner."""
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    service = FieldService(registry)
    roots = [tmp_path.resolve() / name for name in ("source-one", "source-two")]
    manifests = []
    for root in roots:
        root.mkdir()
        (root / "README.md").write_bytes(_README)
        manifests.append(_initialize(service, root))
    source_ids = [manifest.source_id for manifest in manifests]
    assert len(set(source_ids)) == 2
    snapshots = [registry.path.parent / "knowledge-providers" / source_id
                 / "knowledge-provider.snapshot.json" for source_id in source_ids]
    provider_before = [path.read_bytes() for path in snapshots]
    for raw in provider_before:
        value = json.loads(raw)
        assert value["manifest"]["atomic_resources"] == []
        assert value["catalog"]["resources"] == []
    field_paths = [root / ".scholar-workflow/fields.yml" for root in roots]
    fields_before = [path.read_bytes() for path in field_paths]
    registry_before = registry.path.read_bytes()
    pdf = tmp_path / "local-synthetic.pdf"
    pdf.write_bytes(_PDF)
    selections = [{"source_id": manifest.source_id,
                   "field_id": manifest.fields[0].field_id,
                   "item_key": "ABCD2345", "attachment_key": "EFGH2345",
                   "segment": "concurrent-paper", "language": "en"}
                  for manifest in manifests]
    # Both approved plans are produced before either worker can write. The
    # parent holds no registration/provider locks when processes are started.
    proposals = [paper_plan(registry, _LocalPaper(pdf), **selection)
                 for selection in selections]
    assert [path.read_bytes() for path in snapshots] == provider_before
    assert [path.read_bytes() for path in field_paths] == fields_before
    assert registry.path.read_bytes() == registry_before

    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ready = context.Queue()
    results = context.Queue()
    workers = [context.Process(
        target=_register_once, name="paper-owner-race-" + str(index),
        args=(str(registry.path), str(pdf), selection,
              proposal["approved_digest"], start, ready, results),
    ) for index, (selection, proposal) in enumerate(zip(selections, proposals, strict=True))]
    observed = []
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    try:
        for worker in workers:
            worker.start()
        assert {ready.get(timeout=_remaining(deadline)) for _ in workers} == set(source_ids)
        start.set()
        observed = [results.get(timeout=_remaining(deadline)) for _ in workers]
        for worker in workers:
            worker.join(timeout=_remaining(deadline))
            assert not worker.is_alive(), "Worker failed to finish within the deadline"
            assert worker.exitcode == 0
    finally:
        start.set()
        for worker in workers:
            if worker.pid is None:
                continue
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=3)
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=3)
        ready.cancel_join_thread()
        results.cancel_join_thread()
        ready.close()
        results.close()
        assert all(not worker.is_alive() for worker in workers)

    assert sorted(row["status"] for row in observed) == ["refused", "registered"], observed
    assert {row["source_id"] for row in observed} == set(source_ids)
    refused = next(row for row in observed if row["status"] == "refused")
    assert refused["error_type"] == "FieldRegistryError"
    winner = next(row["source_id"] for row in observed if row["status"] == "registered")
    winner_index = source_ids.index(winner)
    loser_index = 1 - winner_index

    # Inspect declarations and concrete files directly, not through the
    # production validator or uniqueness helper being exercised.
    after = [json.loads(path.read_bytes()) for path in snapshots]
    assert sum(len(value["manifest"]["atomic_resources"]) for value in after) == 1
    assert sum(len(value["catalog"]["resources"]) for value in after) == 1
    assert [row["resource_id"] for row in after[winner_index]["manifest"]["atomic_resources"]] == [
        _PAPER_ID,
    ]
    catalog_resource = after[winner_index]["catalog"]["resources"][0]
    assert catalog_resource["resource_id"] == _PAPER_ID
    assert catalog_resource["zotero"]["item_key"] == "ABCD2345"
    assert catalog_resource["zotero"]["attachment_key"] == "EFGH2345"
    assert after[winner_index]["manifest"]["atomic_resources"][0]["markdown_path"] == _PAPER_PATH
    assert snapshots[loser_index].read_bytes() == provider_before[loser_index]
    assert field_paths[loser_index].read_bytes() == fields_before[loser_index]
    navigation = []
    for index, path in enumerate(field_paths):
        field = yaml.safe_load(path.read_bytes())["fields"][0]
        navigation.extend(index for group in field["navigation"]
                          for item in group["items"] if item == _PAPER_PATH)
    assert navigation == [winner_index]
    assert (roots[winner_index] / _PAPER_PATH).is_file()
    assert not (roots[loser_index] / "resources/papers/concurrent-paper").exists()
    assert sum((root / _PAPER_PATH).is_file() for root in roots) == 1
    assert [(root / "README.md").read_bytes() for root in roots] == [_README, _README]
    assert registry.path.read_bytes() == registry_before
    assert pdf.read_bytes() == _PDF
