"""Requirements retain immutable versions and bind to producing runs, not papers."""

from __future__ import annotations

import copy

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.store import RecommendationStore

ACTOR = {"kind": "agent", "name": "Synthetic domain agent"}


def save(store, requirement_id="domain-one", expected_revision=0, **overrides):
    arguments = {
        "requirement_id": requirement_id,
        "title": "Synthetic recommendation requirements",
        "content": "关注世界模型。\n保留数据和比较条件；由外部 agent 决定如何获取来源。",
        "enabled": True,
        "expected_revision": expected_revision,
        "updated_by": ACTOR,
    }
    return store.save_requirement(**{**arguments, **overrides})


def payload(*, producer="agent-a", run="run-one", submission="paper-one", requirement=None):
    data = {
        "schema_version": 1,
        "producer": {"producer_id": producer, "name": producer},
        "run_id": run,
        "items": [
            {
                "submission_id": submission,
                "tags": ["synthetic"],
                "resource": {
                    "kind": "paper",
                    "title": "Synthetic Paper",
                    "url": "https://example.org/paper",
                    "abstract_original": "A complete synthetic abstract.",
                    "abstract_zh": "完整的合成摘要。",
                },
            }
        ],
    }
    if requirement is not None:
        data["requirement"] = requirement
    return data


def receipt(store, data):
    return store.submit(data)["receipts"][0]


def test_empty_list_no_defaults_and_versions_remain_readable(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    assert store.list_requirements() == {"items": []}
    first = save(store)
    assert first["revision"] == 1 and first["updated_by"] == ACTOR
    second = save(
        store,
        expected_revision=1,
        content="由人修改的当前要求。",
        enabled=False,
        updated_by={"kind": "human", "name": "Synthetic human"},
    )
    assert second["revision"] == 2 and not second["enabled"]
    assert store.list_requirements()["items"] == [second]
    assert store.get_requirement("domain-one", revision=1) == first
    assert RecommendationStore(store.state_dir).get_requirement("domain-one") == second
    with pytest.raises(ResearchError):
        store.get_requirement("missing")
    with pytest.raises(ResearchError):
        store.get_requirement("domain-one", revision=3)


def test_requirement_cas_rejects_stale_without_overwriting_any_version(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    first = save(store)
    with pytest.raises(ResearchError) as failure:
        save(store, content="Stale content", expected_revision=0)
    assert failure.value.exit_code == 5
    assert store.get_requirement("domain-one") == first
    assert store.get_requirement("domain-one", revision=1) == first


@pytest.mark.parametrize(
    "overrides",
    [
        {"requirement_id": "bad/id"},
        {"requirement_id": "x" * 129},
        {"title": "x" * 201},
        {"content": "x" * 20001},
        {"content": "   "},
        {"content": "hidden\x00value"},
        {"enabled": 1},
        {"expected_revision": True},
        {"updated_by": {"kind": "system", "name": "Synthetic"}},
        {"updated_by": {"kind": "agent", "name": "Synthetic", "token": "do-not-save"}},
    ],
)
def test_invalid_requirement_is_refused_before_any_version_is_written(tmp_path, overrides):
    store = RecommendationStore(tmp_path / "state")
    with pytest.raises(ResearchError):
        save(store, **overrides)
    assert store.list_requirements()["items"] == []


def test_two_producers_can_use_different_requirements_for_same_paper(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    first = save(store, "domain-one")
    second = save(store, "project-two", content="检查该项目的数据、工具和实验入口。")
    a = receipt(store, payload(requirement={"requirement_id": "domain-one", "revision": 1}))
    b = receipt(
        store,
        payload(producer="agent-b", requirement={"requirement_id": "project-two", "revision": 1}),
    )
    assert a["status"] == b["status"] == "accepted" and a["candidate_id"] == b["candidate_id"]
    candidate = store.get_candidate(a["candidate_id"])
    assert "requirement" not in candidate
    records = {item["producer"]["producer_id"]: item for item in candidate["recommendations"]}
    assert records["agent-a"]["requirement"] == first
    assert records["agent-b"]["requirement"] == second


def test_exact_retry_survives_requirement_update_disable_and_keeps_review(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    original = save(store)
    data = payload(requirement={"requirement_id": "domain-one", "revision": 1})
    accepted = receipt(store, data)
    candidate = store.get_candidate(accepted["candidate_id"])
    candidate = store.review_candidate(candidate["candidate_id"], candidate["revision"])
    candidate = store.set_decision(candidate["candidate_id"], "selected", candidate["revision"])
    before = copy.deepcopy(candidate)
    save(store, expected_revision=1, content="Changed and disabled.", enabled=False)
    assert receipt(store, data)["status"] == "duplicate"
    after = store.get_candidate(accepted["candidate_id"])
    assert after == before
    assert after["recommendations"][0]["requirement"] == original
    stale_new = payload(
        producer="agent-new", submission="new-item", requirement=data["requirement"]
    )
    assert receipt(store, stale_new)["status"] == "invalid"
    disabled_new = payload(
        producer="agent-new",
        submission="new-item",
        requirement={"requirement_id": "domain-one", "revision": 2},
    )
    assert receipt(store, disabled_new)["status"] == "invalid"


@pytest.mark.parametrize(
    "reference",
    [
        {"requirement_id": "missing", "revision": 1},
        {"requirement_id": "domain-one", "revision": 99},
    ],
)
def test_new_submission_cannot_use_missing_requirement_version(tmp_path, reference):
    store = RecommendationStore(tmp_path / "state")
    save(store)
    assert receipt(store, payload(requirement=reference))["status"] == "invalid"
    assert store.list_candidates()["total"] == 0


def test_same_producer_run_cannot_switch_requirement_or_drop_reference(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    save(store, "domain-one")
    save(store, "domain-two")
    assert (
        receipt(store, payload(requirement={"requirement_id": "domain-one", "revision": 1}))[
            "status"
        ]
        == "accepted"
    )
    for reference in [{"requirement_id": "domain-two", "revision": 1}, None]:
        assert (
            receipt(store, payload(submission="new-item", requirement=reference))["status"]
            == "invalid"
        )
    assert len(store.list_candidates()["items"][0]["recommendations"]) == 1


def test_legacy_submission_has_no_reference_and_keeps_exact_retry_identity(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    data = payload()
    first = receipt(store, data)
    assert first["status"] == "accepted"
    assert receipt(store, data)["status"] == "duplicate"
    candidate = store.get_candidate(first["candidate_id"])
    assert "requirement" not in candidate["recommendations"][0]
    save(store)
    changed = {**data, "requirement": {"requirement_id": "domain-one", "revision": 1}}
    assert receipt(store, changed)["status"] == "conflict"
