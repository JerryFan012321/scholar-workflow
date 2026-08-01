"""Paper import workflow with an injected fake downloader (no network)."""
from __future__ import annotations
from pathlib import Path
import pytest
from scholar_workflow.models import Resource, ResourceKind, Identifiers, ActionPlan, ActionItem
from scholar_workflow.state import StateStore
from scholar_workflow.workflows.paper import run_paper_import


class Cfg:
    def __init__(self, inbox):
        self.paper_inbox = inbox


@pytest.fixture
def store(tmp_path):
    s = StateStore(tmp_path / "state.db")
    yield s
    s.close()


def _plan(*items):
    return ActionPlan(actions=list(items))


def _res(rid, **ids):
    return Resource(resource_id=rid, kind=ResourceKind.PAPER, title=rid,
                    identifiers=Identifiers(**ids))


def _fake_download(calls):
    def _dl(arxiv_id, dest_dir):
        calls.append((arxiv_id, dest_dir))
        p = Path(dest_dir) / f"{arxiv_id}.pdf"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4 fake")
        return p
    return _dl


def test_arxiv_downloads_to_inbox(store, tmp_path):
    res = _res("paper:arxiv:2401.01234", arxiv="2401.01234")
    plan = _plan(ActionItem(resource_id=res.resource_id, operation="create"))
    calls: list = []
    out = run_paper_import(plan, [res], Cfg(tmp_path / "inbox"), store,
                           download=_fake_download(calls))
    assert out[res.resource_id]["status"] == "downloaded"
    assert calls == [("2401.01234", tmp_path / "inbox")]
    assert Path(out[res.resource_id]["inbox_path"]).exists()


def test_no_arxiv_reports_no_pdf(store, tmp_path):
    res = _res("paper:doi:10.1/x", doi="10.1/x")
    plan = _plan(ActionItem(resource_id=res.resource_id, operation="create"))
    calls: list = []
    out = run_paper_import(plan, [res], Cfg(tmp_path / "inbox"), store,
                           download=_fake_download(calls))
    assert out[res.resource_id]["status"] == "no_pdf"
    assert calls == []  # never attempts a download without an arXiv id


def test_skip_and_conflict_are_not_downloaded(store, tmp_path):
    a = _res("paper:arxiv:2401.00001", arxiv="2401.00001")
    b = _res("paper:arxiv:2401.00002", arxiv="2401.00002")
    plan = _plan(ActionItem(resource_id=a.resource_id, operation="skip"),
                 ActionItem(resource_id=b.resource_id, operation="conflict"))
    calls: list = []
    out = run_paper_import(plan, [a, b], Cfg(tmp_path / "inbox"), store,
                           download=_fake_download(calls))
    assert calls == []
    assert out == {}
