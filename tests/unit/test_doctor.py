"""Unit tests for runtime diagnostics (offline path checks only)."""
from __future__ import annotations
from scholar_workflow.doctor import run_doctor


class Cfg:
    def __init__(self, papers, inbox, vault):
        self.papers_root = papers
        self.paper_inbox = inbox
        self.vault_root = vault


def test_all_green(tmp_path):
    cfg = Cfg(tmp_path, tmp_path, tmp_path)
    out = run_doctor(cfg)
    assert out["ok"] is True
    assert {c["name"] for c in out["checks"]} == {
        "papers_root", "paper_inbox", "vault_root"}


def test_missing_path_fails(tmp_path):
    out = run_doctor(Cfg(tmp_path / "nope", tmp_path, tmp_path))
    assert out["ok"] is False
    assert any(c["name"] == "papers_root" and not c["ok"] for c in out["checks"])
