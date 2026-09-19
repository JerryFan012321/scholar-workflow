"""Unit tests for local paths and the advisory Zotero Local API probe."""

from __future__ import annotations

from scholar_workflow.adapters.zotero_local import ServerInfo, ZoteroLocalUnavailable
from scholar_workflow.doctor import probe_zotero_local, run_doctor


class Cfg:
    def __init__(self, inbox, vault):
        self.paper_inbox = inbox
        self.research_vault_root = vault


def test_all_green(tmp_path):
    out = run_doctor(Cfg(tmp_path, tmp_path), zotero_probe=lambda: _available())
    assert out["ok"] is True
    assert {c["name"] for c in out["checks"]} == {
        "paper_inbox",
        "research_vault_root",
    }


def test_missing_path_fails(tmp_path):
    out = run_doctor(Cfg(tmp_path / "nope", tmp_path), zotero_probe=lambda: _available())
    assert out["ok"] is False
    assert any(c["name"] == "paper_inbox" and not c["ok"] for c in out["checks"])


def _available() -> dict:
    return {
        "name": "zotero_local_api",
        "ok": True,
        "scope": "local",
        "detail": "reachable (API 3, schema 42)",
    }


def test_probe_reports_server_versions(monkeypatch):
    class FakeAdapter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def probe(self):
            return ServerInfo(server_id="server-1", api_version="3", schema_version="42")

    monkeypatch.setattr("scholar_workflow.doctor.ZoteroLocalAdapter", FakeAdapter)
    assert probe_zotero_local() == _available()


def test_probe_reports_unavailable_without_raising(monkeypatch):
    class FakeAdapter:
        def __enter__(self):
            raise ZoteroLocalUnavailable("not running")

        def __exit__(self, *args):
            return None

    monkeypatch.setattr("scholar_workflow.doctor.ZoteroLocalAdapter", FakeAdapter)
    advisory = probe_zotero_local()
    assert advisory["ok"] is False
    assert "start Zotero" in advisory["detail"]


def test_run_doctor_advisory_does_not_affect_ok(tmp_path):
    unavailable = {
        "name": "zotero_local_api",
        "ok": False,
        "scope": "local",
        "detail": "start Zotero",
    }
    out = run_doctor(Cfg(tmp_path, tmp_path), zotero_probe=lambda: unavailable)
    assert out["ok"] is True
    assert out["advisories"] == [unavailable]
