"""Bounded reading tasks use synthetic candidates and exact local state requests."""
from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path

import pytest

_helpers = runpy.run_path(str(Path(__file__).with_name("test_recommendation_browsing_ui.py")))
candidate, nodes, render = (_helpers[name] for name in ("candidate", "nodes", "render"))


def pair():
    first = candidate()
    second = candidate(candidate_id="candidate-" + "b" * 64,
                       resource={**first["resource"], "title": "Second synthetic work"})
    return [first, second]


def test_compact_card_has_direct_source_and_reversible_save_without_opening_detail():
    result = render(action="quick_save", candidate=candidate(decision="unread"))
    assert result["detail_hidden"]
    assert nodes(result["feed"], "entry-original")[0]["href"] == candidate()["resource"]["url"]
    assert result["posts"] == [{"path": "/api/decisions", "body": {
        "candidate_id": candidate()["candidate_id"], "expected_revision": 3, "decision": "saved"}}]
    assert nodes(result["feed"], "entry-save")[0]["attributes"]["aria-pressed"] == "true"


def test_undo_uses_saved_response_revision_without_review_or_ingestion():
    result = render(action="quick_undo", candidate=candidate(decision="unread"))
    assert result["posts"][-1] == {"path": "/api/decisions", "body": {
        "candidate_id": candidate()["candidate_id"], "expected_revision": 4, "decision": "unread"}}
    assert not any("reviews" in row["path"] or "ingestion" in row["path"] for row in result["posts"])


def test_reader_steps_within_filtered_order_without_marking_anything_read():
    result = render(action="reader_next", candidates=pair())
    assert "Second synthetic work" in result["detail"]["text"]
    assert "2 / 2" in result["reader_position"]
    assert result["reader_scroll"] == 0
    assert result["reader_next_disabled"] and not result["reader_previous_disabled"]
    assert result["posts"] == []


def test_reader_continues_across_page_boundary_without_closing_or_mutating_candidates():
    rows = [candidate(candidate_id="candidate-" + f"{index:064x}",
                      resource={**candidate()["resource"], "title": f"Synthetic work {index}"}) for index in range(21)]
    result = render(action="reader_page_boundary", candidate=rows[0], candidates=rows)
    assert "Synthetic work 20" in result["detail"]["text"]
    assert "21 / 21" in result["reader_position"]
    assert not result["detail_hidden"] and result["reader_next_disabled"]
    assert any("offset=20" in request for request in result["reads"])
    assert result["posts"] == []


def test_previous_returns_to_first_and_updates_keep_reading_position():
    result = render(action="reader_next_previous", candidates=pair())
    assert "Second synthetic work" not in result["detail"]["text"]
    assert "1 / 2" in result["reader_position"] and result["reader_previous_disabled"]
    result = render(action="reader_update_scroll")
    assert result["reader_scroll"] == 420


def test_back_closes_reader_and_keyboard_does_not_steal_editor_input():
    assert render(action="reader_back")["detail_hidden"]
    result = render(action="reader_keyboard_in_text", candidates=pair())
    assert "Second synthetic work" not in result["detail"]["text"]
    assert "Second synthetic work" in render(action="reader_keyboard_next", candidates=pair())["detail"]["text"]


def test_filter_chip_removes_its_own_condition_from_next_request():
    result = render(action="filter_remove")
    queries = [path for path in result["reads"] if path.startswith("/api/candidates?") and "decision=selected" not in path]
    assert "kind=paper" in queries[-2]
    assert "kind=" not in queries[-1]
    assert not nodes(result["filters"], "filter-chip")


def test_evaluation_draft_survives_same_origin_refresh_but_not_another_pool_or_profile():
    first = render(action="evaluation_draft_reopen", comment="刷新前仍未保存的评价")
    restored = render(action="detail", storage=first["storage"])
    assert nodes(restored["detail"], "evaluation-comment")[0]["value"] == "刷新前仍未保存的评价"
    other = render(action="detail", storage=first["storage"], profile="personal")
    assert nodes(other["detail"], "evaluation-comment")[0]["value"] == ""
    other = render(action="detail", storage=first["storage"], pool_id="pool-" + "c" * 32)
    assert nodes(other["detail"], "evaluation-comment")[0]["value"] == ""


@pytest.mark.parametrize("leave_reader", ["popstate", "settings_click"])
def test_delayed_history_restore_cannot_reopen_reader_after_entering_settings(leave_reader):
    """Hold page 2, enter settings, then release the old synthetic response."""
    if not _helpers["NODE"]:
        pytest.skip("Node is required for the isolated reader race.")
    runner = _helpers["RUNNER"].replace(
        'if(payload)posts.push({path,body:payload});else reads.push(path);',
        '''if(payload)posts.push({path,body:payload});else reads.push(path);
  if(input.action==="reader_popstate_race"&&!holdUsed&&path.startsWith("/api/candidates?")&&new URLSearchParams(path.split("?")[1]).get("offset")==="20"){
   holdUsed=true;await new Promise(resolve=>releaseHeld=resolve);
  }''')
    runner = runner.replace('process.stdout.write(JSON.stringify({posts,reads,sessions,initial', '''
 if(input.action==="reader_popstate_race"){
  const oldState={scholarRecommendationPage:"recommendations",scholarRecommendationDetail:candidates[20].candidate_id,scholarRecommendationOffset:20};
  context.window.history.state=oldState;
  const pending=(windowEvents.popstate||[]).map(fn=>fn({state:oldState}));await settle();
  if(!releaseHeld)throw Error("The cross-page response was not delayed");
  if(input.leave_reader==="settings_click"){await pages[1].fire("click");}
  else{
   const nextState={scholarRecommendationPage:"sources"};context.window.history.state=nextState;
   for(const fn of windowEvents.popstate||[])fn({state:nextState});
  }
  await settle();releaseHeld();await Promise.all(pending);await settle();
 }
 process.stdout.write(JSON.stringify({posts,reads,sessions,initial''')
    rows = [candidate(candidate_id="candidate-" + f"{index:064x}",
                      resource={**candidate()["resource"], "title": f"Synthetic work {index}"}) for index in range(21)]
    static = _helpers["STATIC"]
    response = subprocess.run([_helpers["NODE"], "-e", runner, str(static / "app.js"),
                               str(static / "workspace.js"), str(static / "requirements.js")],
                              input=json.dumps({"candidate": rows[0], "candidates": rows,
                                                "action": "reader_popstate_race", "leave_reader": leave_reader}),
                              text=True, capture_output=True, check=True)
    result = json.loads(response.stdout)
    assert result["detail_hidden"] and not result["views"]["sources"]
    assert result["views"]["recommendations"] and result["posts"] == []
    assert any("offset=20" in path for path in result["reads"])


def test_fresh_home_defaults_to_unprocessed_only():
    pending = candidate(decision="unread")
    rows = [pending, candidate(candidate_id="candidate-" + "b" * 64, decision="saved")]
    result = render(action="initial", candidate=pending, candidates=rows, fresh_home=True)
    assert len(nodes(result["feed"], "compact-card")) == 1
    assert all("decision=unread" in path or "decision=selected" in path
               for path in result["reads"] if path.startswith("/api/candidates?"))
    assert next(tab for tab in result["tabs"] if tab["dataset"]["decision"] == "unread")["attributes"]["aria-pressed"] == "true"


def test_old_all_filter_does_not_override_new_home_default():
    result = render(action="initial", candidate=candidate(decision="unread"), fresh_home=True,
                    storage={"scholar-recommendations-test-filters": json.dumps({"decision": "", "kind": "paper"})})
    query = next(path for path in result["reads"] if path.startswith("/api/candidates?"))
    assert "decision=unread" in query and "kind=paper" in query


def test_empty_unprocessed_offers_explicit_all_and_remembers_new_choice():
    result = render(action="initial", fresh_home=True)
    assert result["empty_title"] == "未处理已清空" and not result["empty_all_hidden"]
    all_view = render(action="quick_all", fresh_home=True)
    assert len(nodes(all_view["feed"], "compact-card")) == 1
    restored = render(action="initial", fresh_home=True, storage=all_view["storage"])
    assert len(nodes(restored["feed"], "compact-card")) == 1


@pytest.mark.parametrize("reason,label", [("quality", "已标记：质量不符合要求"),
    ("not_relevant", "已忽略：不是当前想关注的方向"), ("other", "已忽略：其他")])
def test_home_feedback_is_reasoned_removes_from_unprocessed_and_offers_undo(reason, label):
    result = render(action="quick_feedback", candidate=candidate(decision="unread"), fresh_home=True, reason=reason)
    assert result["detail_hidden"]
    assert result["posts"] == [{"path": "/api/decisions", "body": {
        "candidate_id": candidate()["candidate_id"], "expected_revision": 3, "decision": "ignored", "reason": reason}}]
    assert not nodes(result["feed"], "compact-card")
    assert label in result["notice"]["text"] and nodes(result["notice"], "notice-undo")
    undo = render(action="quick_feedback_undo", candidate=candidate(decision="unread"), fresh_home=True, reason=reason)
    assert len(nodes(undo["feed"], "compact-card")) == 1
    assert undo["posts"][-1]["body"] == {"candidate_id": candidate()["candidate_id"], "expected_revision": 4, "decision": "unread"}


def test_reason_change_can_undo_without_changing_the_ignored_status():
    row = candidate(decision="ignored", disposition={"reason": "quality", "scope": None})
    result = render(action="quick_feedback_undo", candidate=row, reason="other")
    assert result["posts"][-1]["body"] == {"candidate_id": row["candidate_id"], "expected_revision": 4,
        "decision": "ignored", "reason": "quality", "scope": None}


def test_home_feedback_conflict_keeps_item_and_does_not_claim_success():
    result = render(action="quick_feedback", candidate=candidate(decision="unread"), fresh_home=True, decision_failure=True)
    assert len(nodes(result["feed"], "compact-card")) == 1
    assert "刷新后重试" in result["notice"]["text"]
    assert not nodes(result["notice"], "notice-undo")


@pytest.mark.parametrize("action", ["quick_feedback_escape", "quick_feedback_outside"])
def test_home_feedback_menu_dismisses_without_recording_a_judgment(action):
    result = render(action=action, candidate=candidate(decision="unread"), fresh_home=True)
    assert not nodes(result["feed"], "entry-more")[0]["open"]
    assert not result["posts"]


def test_processing_the_last_card_on_a_page_returns_to_remaining_pending_items():
    rows = [candidate(candidate_id="candidate-" + f"{index:064x}", decision="unread") for index in range(21)]
    result = render(action="quick_feedback_last_page", candidate=rows[-1], candidates=rows,
                    fresh_home=True, reason="other")
    assert len(nodes(result["feed"], "compact-card")) == 20
    assert result["page_number"] == "1 / 1"
    queries = [path for path in result["reads"] if path.startswith("/api/candidates?") and "decision=unread" in path]
    assert any("offset=20" in query for query in queries)
    assert "offset=0" in queries[-1]
