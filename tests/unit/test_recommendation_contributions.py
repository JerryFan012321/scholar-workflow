"""Contribution provenance, corrections and legacy recommendation compatibility."""
import pytest
from scholar_workflow.research.recommendations.store import RecommendationStore
from tests.unit.test_recommendation_store import submission, candidate
from tests.unit.test_recommendation_browsing_ui import render, candidate as ui_candidate

CONTRIBUTIONS = [{"text_zh": "提出可复现的合成评测协议。", "text_original": "We introduce a reproducible protocol.",
                  "source_url": "https://arxiv.org/html/2601.12345v1#S1", "source_section": "Introduction / Contributions"}]

def test_contributions_survive_submission_and_content_correction(tmp_path):
    store = RecommendationStore(tmp_path / "test")
    item = candidate(store, submission(contributions=CONTRIBUTIONS))
    assert item["resource"]["contributions"] == CONTRIBUTIONS
    corrected = store.revise_content(item["candidate_id"], item["revision"],
        {"contributions": [dict(CONTRIBUTIONS[0], text_zh="提出新的合成评测协议。题设仍须人工核实。") ]},
        {"kind": "agent", "name": "fixture"})
    assert store.list_candidates()["total"] == 1
    assert corrected["candidate"]["resource"]["contributions"][0]["text_zh"].startswith("提出新的")

@pytest.mark.parametrize("field,value", [("source_url", "javascript:alert(1)"), ("source_section", ""), ("text_zh", "")])
def test_invalid_contribution_provenance_is_rejected(tmp_path, field, value):
    store = RecommendationStore(tmp_path / "test")
    result = store.submit(submission(contributions=[dict(CONTRIBUTIONS[0], **{field:value})]))
    assert result["receipts"][0]["status"] == "invalid"

def test_old_items_and_metadata_refresh_keep_existing_contributions(tmp_path):
    store = RecommendationStore(tmp_path / "test")
    item = candidate(store)
    assert "contributions" not in item["resource"]
    candidate(store, submission("second", contributions=CONTRIBUTIONS))
    current = candidate(store, submission("third"))
    assert current["resource"]["contributions"] == CONTRIBUTIONS

def test_detail_has_separate_contributions_and_source():
    item = ui_candidate()
    item["resource"]["contributions"] = CONTRIBUTIONS
    result = render(candidate=item, action="detail")
    assert "贡献" in str(result["detail"])
    assert CONTRIBUTIONS[0]["text_zh"] in str(result["detail"])
    assert CONTRIBUTIONS[0]["source_url"] in str(result["detail"])

def test_new_version_does_not_inherit_old_contributions(tmp_path):
    store = RecommendationStore(tmp_path / "test")
    candidate(store, submission(contributions=CONTRIBUTIONS))
    newer = candidate(store, submission("new-version", arxiv_id="2601.12345v2", url="https://arxiv.org/abs/2601.12345v2"))
    assert "contributions" not in newer["resource"]
