"""Paper import workflow with an injected fake adapter (no network, no real Zotero)."""
from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from scholar_workflow.models import Resource, ResourceKind, Identifiers, ActionPlan, ActionItem
from scholar_workflow.state import StateStore
from scholar_workflow.workflows.paper import run_paper_import
from scholar_workflow.adapters import ZoteroWriteResult


class FakeBridge:
    def __init__(self):
        self.upserts = []

    def health_check(self) -> bool:
        return True

    def upsert_paper(self, payload: dict, idempotency_key: str) -> ZoteroWriteResult:
        self.upserts.append(payload)
        return ZoteroWriteResult(item_key="IT1", attachment_key="AT1",
                                 version=1, final_path=payload.get("title", ""))

    def link_attachment(self, *a, **k): ...
    def update_metadata(self, *a, **k): ...


class Cfg:
    class zotero: pass
    papers_root = "/tmp/does-not-matter"


@pytest.fixture
def store(tmp_path):
    s = StateStore(tmp_path / "state.db")
    yield s
    s.close()


def _plan(*items):
    return ActionPlan(input_digest="x", expires_at=datetime.utcnow() + timedelta(hours=1),
                      approved_at=datetime.utcnow(), actions=list(items))


def _res(rid, **ids):
    return Resource(resource_id=rid, kind=ResourceKind.PAPER, title=rid,
                    identifiers=Identifiers(**ids))


def test_no_arxiv_does_not_raise_nameerror(store):
    # regression: pdf_path used to be undefined on the no-arXiv branch
    res = _res("paper:doi:10.1/x", doi="10.1/x")
    plan = _plan(ActionItem(resource_id=res.resource_id, operation="create"))
    plan.input_digest = _digest([res])
    bridge = FakeBridge()
    out = run_paper_import(plan, [res], Cfg(), store, adapter=bridge)
    assert out[res.resource_id]["status"] == "completed"
    assert bridge.upserts[0]["attachment"] is None


def test_skip_and_conflict_are_not_written(store):
    a = _res("paper:doi:10.1/skip", doi="10.1/skip")
    b = _res("paper:doi:10.1/conflict", doi="10.1/conflict")
    plan = _plan(ActionItem(resource_id=a.resource_id, operation="skip"),
                 ActionItem(resource_id=b.resource_id, operation="conflict"))
    plan.input_digest = _digest([a, b])
    bridge = FakeBridge()
    out = run_paper_import(plan, [a, b], Cfg(), store, adapter=bridge)
    assert bridge.upserts == []
    assert out == {}


def _digest(resources):
    from scholar_workflow.planning import _input_digest
    return _input_digest(resources)
