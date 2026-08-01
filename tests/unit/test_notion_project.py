"""Unit test for bin/notion-project.py — the two-DB orchestration layer (GOALS INV21).

The script is the sole Notion API caller (the CLI makes no outbound network calls), so
its orchestration is worth pinning: papers upserted first, each related-doc `Paper`
relation wired from the captured page_id map, and the token/reference guards. The script
is hyphenated and lives outside the package, so we import it by path and swap in a fake
NotionAdapter (records calls, no network) plus a fake config to stay hermetic.
"""
from __future__ import annotations
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BIN = Path(__file__).resolve().parents[2] / "bin" / "notion-project.py"


def _load():
    spec = importlib.util.spec_from_file_location("notion_project", _BIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


notion_project = _load()

PAYLOAD = {
    "papers": [
        {"resource_id": "arxiv:2409.17106",
         "fields": {"Name": {"title": [{"text": {"content": "Text2CAD"}}]}}},
    ],
    "related_docs": [
        {"doc_id": "paper/科研项目/上汽标注/Text2CAD论文相关资料.md",
         "paper_resource_id": "arxiv:2409.17106",
         "fields": {"Name": {"title": [{"text": {"content": "Text2CAD 相关资料"}}]}}},
    ],
}


class _FakeAdapter:
    """Records upsert calls in order; returns a deterministic page_id per key."""
    instances: list["_FakeAdapter"] = []

    def __init__(self, token, api_version=None):
        self.token = token
        self.calls: list[SimpleNamespace] = []
        _FakeAdapter.instances.append(self)

    def upsert_page(self, data_source_id, key_value, fields, key_property="Resource ID"):
        self.calls.append(SimpleNamespace(
            ds=data_source_id, key=key_value, fields=fields, key_property=key_property))
        return f"pid::{key_value}"

    def close(self):
        pass


def _fake_config():
    notion = SimpleNamespace(data_source_id="papers-ds",
                             related_docs_data_source_id="related-ds",
                             api_version="2026-03-11")
    return SimpleNamespace(notion=notion)


def _setup(monkeypatch, payload, token="test-token"):
    _FakeAdapter.instances.clear()
    if token is None:
        monkeypatch.delenv(notion_project.TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(notion_project.TOKEN_ENV, token)
    monkeypatch.setattr(notion_project, "load_config", _fake_config)
    monkeypatch.setattr(notion_project, "NotionAdapter", _FakeAdapter)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))


def test_papers_upserted_before_related_docs(monkeypatch):
    _setup(monkeypatch, PAYLOAD)
    notion_project.main()
    adapter = _FakeAdapter.instances[-1]
    # papers first (keyed Resource ID), then related docs (keyed Doc ID)
    assert [c.key_property for c in adapter.calls] == ["Resource ID", "Doc ID"]
    assert (adapter.calls[0].ds, adapter.calls[0].key) == ("papers-ds", "arxiv:2409.17106")
    assert adapter.calls[1].ds == "related-ds"
    assert adapter.calls[1].key == "paper/科研项目/上汽标注/Text2CAD论文相关资料.md"


def test_paper_relation_wired_from_page_id_map(monkeypatch, capsys):
    _setup(monkeypatch, PAYLOAD)
    notion_project.main()
    adapter = _FakeAdapter.instances[-1]
    # the doc's Paper relation is injected from the paper's returned page_id
    assert adapter.calls[1].fields["Paper"]["relation"] == [{"id": "pid::arxiv:2409.17106"}]
    out = json.loads(capsys.readouterr().out)
    assert out["papers"] == {"arxiv:2409.17106": "pid::arxiv:2409.17106"}
    assert out["related_docs"] == {
        "paper/科研项目/上汽标注/Text2CAD论文相关资料.md":
        "pid::paper/科研项目/上汽标注/Text2CAD论文相关资料.md"}


def test_missing_token_exits_3(monkeypatch):
    _setup(monkeypatch, PAYLOAD, token=None)
    with pytest.raises(SystemExit) as exc:
        notion_project.main()
    assert exc.value.code == 3


def test_empty_payload_is_noop(monkeypatch, capsys):
    _setup(monkeypatch, {})
    notion_project.main()
    assert _FakeAdapter.instances[-1].calls == []
    assert json.loads(capsys.readouterr().out) == {"papers": {}, "related_docs": {}}


def test_related_doc_referencing_unknown_paper_exits_2(monkeypatch):
    payload = {"papers": [],
               "related_docs": [{"doc_id": "paper/x.md",
                                 "paper_resource_id": "arxiv:does-not-exist",
                                 "fields": {}}]}
    _setup(monkeypatch, payload)
    with pytest.raises(SystemExit) as exc:
        notion_project.main()
    assert exc.value.code == 2
