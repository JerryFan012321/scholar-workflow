"""Unit tests for runtime diagnostics (offline, injected bridge)."""
from __future__ import annotations
from scholar_workflow.doctor import run_doctor


class Cfg:
    class zotero:
        bridge_url = "http://127.0.0.1:23119/bridge"

    def __init__(self, papers, vault):
        self.papers_root = papers
        self.vault_root = vault


class Bridge:
    def __init__(self, healthy): self._h = healthy
    def health_check(self): return self._h


def test_all_green(tmp_path):
    cfg = Cfg(tmp_path, tmp_path)
    out = run_doctor(cfg, bridge=Bridge(True))
    assert out["ok"] is True
    assert {c["name"] for c in out["checks"]} == {"papers_root", "vault_root", "zotero_bridge"}


def test_bridge_down_fails(tmp_path):
    out = run_doctor(Cfg(tmp_path, tmp_path), bridge=Bridge(False))
    assert out["ok"] is False
    assert any(c["name"] == "zotero_bridge" and not c["ok"] for c in out["checks"])


def test_missing_path_fails(tmp_path):
    out = run_doctor(Cfg(tmp_path / "nope", tmp_path), bridge=Bridge(True))
    assert out["ok"] is False
    assert any(c["name"] == "papers_root" and not c["ok"] for c in out["checks"])
