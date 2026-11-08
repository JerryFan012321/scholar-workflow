"""Legacy recommendation preferences stay readable without a reading-service dependency."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
import yaml

from scholar_workflow.config import RecommendConfig, load_recommend_config


@pytest.mark.parametrize("legacy_value", ["auto_topic", "method_type", "single_notebook"])
def test_legacy_notebook_preferences_are_ignored_without_rewriting_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_value: str,
) -> None:
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
    global_file = tmp_path / "recommend.yml"
    global_file.write_text(yaml.safe_dump({
        "interests": ["reconstruction"], "watchlist": ["author-a"],
        "notebooklm_classification": legacy_value, "daily_limit": 7,
    }))
    overlay = tmp_path / "projects" / "example.yml"
    overlay.parent.mkdir()
    overlay.write_text(yaml.safe_dump({
        "interests": ["reconstruction", "calibration"], "watchlist": ["author-b"],
        "notebooklm_classification": "single_notebook", "daily_limit": 3,
    }))
    before = {path: path.read_bytes() for path in (global_file, overlay)}

    loaded = load_recommend_config(cwd=tmp_path / "example")

    assert loaded.interests == ["reconstruction", "calibration"]
    assert loaded.watchlist == ["author-a", "author-b"]
    assert loaded.daily_limit == 3
    assert "notebooklm_classification" not in loaded.model_dump()
    assert {path: path.read_bytes() for path in before} == before


def test_default_preferences_do_not_advertise_a_retired_service() -> None:
    assert "notebooklm_classification" not in RecommendConfig().model_dump()


def test_aggregator_keeps_metadata_and_source_failures_without_a_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "notebooklm", None)
    (tmp_path / "recommend.yml").write_text(yaml.safe_dump({
        "notebooklm_classification": "auto_topic", "daily_limit": 2,
        "watchlist": ["author-a"],
    }))
    script = Path(__file__).resolve().parents[2] / "bin" / "recommend-papers.py"
    spec = importlib.util.spec_from_file_location("recommend_retirement_fixture", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidate = {
        "arxiv_id": "2601.00001", "title": "Synthetic recommendation", "authors": [],
        "source": "hf_daily", "score": 5, "abstract_snippet": "Synthetic abstract.",
        "url": "https://arxiv.org/abs/2601.00001",
    }
    calls: list[tuple] = []

    def hf_daily(*, limit: int) -> list[dict]:
        calls.append(("hf_daily", limit))
        return [dict(candidate)]

    def author_papers(author_id: str, *, limit: int) -> list[dict]:
        calls.append(("s2_author", author_id, limit))
        return [{**candidate, "source": "s2_author", "score": None}]

    def recommendations(seed_ids: list[str], *, limit: int) -> list[dict]:
        calls.append(("s2_recommendations", seed_ids, limit))
        raise RuntimeError("synthetic source unavailable")

    def scholar_inbox(min_score: float) -> list[dict]:
        calls.append(("scholar_inbox", min_score))
        raise RuntimeError("synthetic session unavailable")

    monkeypatch.setattr(module, "fetch_hf_daily", hf_daily)
    monkeypatch.setattr(module, "fetch_s2_author_papers", author_papers)
    monkeypatch.setattr(module, "fetch_s2_recommendations", recommendations)
    monkeypatch.setattr(module, "_fetch_scholar_inbox", scholar_inbox)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"seed_arxiv_ids":["2501.00001"]}'))

    module.main()

    result = json.loads(capsys.readouterr().out)
    assert result == {
        "candidates": [{**candidate, "sources": ["hf_daily", "s2_author"],
                        "source_observations": [candidate, {**candidate, "source": "s2_author", "score": None}]}],
        "count": 1,
        "skipped": [
            "s2_recommendations: synthetic source unavailable",
            "scholar_inbox: synthetic session unavailable",
        ],
    }
    assert calls == [
        ("hf_daily", 30), ("s2_recommendations", ["2501.00001"], 30),
        ("s2_author", "author-a", 30), ("scholar_inbox", 0.0),
    ]
