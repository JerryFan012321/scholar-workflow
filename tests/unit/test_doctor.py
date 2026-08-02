"""Unit tests for runtime diagnostics (offline path checks only)."""
from __future__ import annotations
from scholar_workflow.doctor import run_doctor


class Cfg:
    def __init__(self, inbox, vault):
        self.paper_inbox = inbox
        self.research_vault_root = vault


def test_all_green(tmp_path):
    cfg = Cfg(tmp_path, tmp_path)
    out = run_doctor(cfg)
    assert out["ok"] is True
    assert {c["name"] for c in out["checks"]} == {
        "paper_inbox", "research_vault_root"}


def test_missing_path_fails(tmp_path):
    out = run_doctor(Cfg(tmp_path / "nope", tmp_path))
    assert out["ok"] is False
    assert any(c["name"] == "paper_inbox" and not c["ok"] for c in out["checks"])
