"""Independent expectations for shared management state and admitted library writes."""
from datetime import UTC, datetime, timedelta

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.store import RecommendationStore, _digest


def selected(tmp_path):
    s=RecommendationStore(tmp_path/'pool')
    r=s.submit({'schema_version':1,'producer':{'producer_id':'fixture','name':'Fixture'},'run_id':'one',
        'items':[{'submission_id':'one','tags':[], 'resource':{'kind':'paper','title':'Synthetic work',
        'url':'https://arxiv.org/abs/2401.01234','authors':['Ada Example'],
        'abstract_original':'The complete synthetic abstract.','abstract_zh':'完整合成摘要。'}}]})
    row=s.get_candidate(r['receipts'][0]['candidate_id'])
    row=s.review_candidate(row['candidate_id'],row['revision'])
    row=s.set_decision(row['candidate_id'],'selected',row['revision'])
    return s,row


def plan_for(row):
    return dict(candidate_id=row['candidate_id'],candidate_revision=row['revision'],
        resource_digest=_digest(row['resource']),collection_key='ABCD1234',
        provider_identity='synthetic-provider',collection_version=1,
        expires_at=(datetime.now(UTC)+timedelta(minutes=10)).isoformat(),metadata={'title':'Synthetic work'})


def test_plan_rechecks_human_choice_and_repeated_claim_is_not_a_second_write(tmp_path):
    s,row=selected(tmp_path)
    plan=s.create_ingestion_plan(plan_for(row))
    assert s.create_ingestion_plan(plan_for(row))['plan_id']==plan['plan_id']
    assert s.claim_ingestion_plan(plan['plan_id'])['status']=='in_progress'
    with pytest.raises(ResearchError): s.claim_ingestion_plan(plan['plan_id'])
    done=s.finish_ingestion_plan(plan['plan_id'],{'status':'completed','item_key':'ITEM1234','collection_key':'ABCD1234'})
    assert done['receipt']['item_key']=='ITEM1234'
    assert s.claim_ingestion_plan(plan['plan_id'])['status']=='completed'
    assert RecommendationStore(s.state_dir).ingestion_history()[0]['plan_id']==plan['plan_id']


def test_stale_plan_is_blocked_after_candidate_or_selection_change(tmp_path):
    s,row=selected(tmp_path); plan=s.create_ingestion_plan(plan_for(row))
    s.set_decision(row['candidate_id'],'unread',row['revision'])
    with pytest.raises(ResearchError): s.claim_ingestion_plan(plan['plan_id'])


def test_incomplete_receipt_cannot_claim_ingestion_success(tmp_path):
    s,row=selected(tmp_path); plan=s.create_ingestion_plan(plan_for(row));s.claim_ingestion_plan(plan['plan_id'])
    with pytest.raises(ResearchError):s.finish_ingestion_plan(plan['plan_id'],{'status':'completed'})
    assert s.get_ingestion_plan(plan['plan_id'])['status']=='in_progress'


def operation(**changes):
    return {"operation_id": "agent-one", "source_id": "alphaxiv", "actor": "external-agent",
            "action": "follow_researcher", "status": "proposed",
            "summary": "Consider following the researcher after human review.",
            "observed_at": "2026-11-09T12:00:00+08:00",
            "evidence_urls": ["https://www.alphaxiv.org/"]} | changes


def test_source_context_survives_another_agent_without_overwriting_stale_edits(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    assert store.source_context("alphaxiv")["revision"] == 0
    saved = store.update_source_context("alphaxiv", expected_revision=0,
        topics=["world models"], notes="Check evaluation settings; researcher suggestions are proposals.")
    other = RecommendationStore(store.state_dir)
    assert other.source_context("alphaxiv") == saved
    assert other.source_context("another-source")["topics"] == []
    with pytest.raises(ResearchError):
        other.update_source_context("alphaxiv", expected_revision=0, topics=[], notes="Stale edit")
    assert other.source_context("alphaxiv") == saved


def test_external_operation_is_reported_not_remote_execution_and_is_idempotent(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    first = store.record_source_operation(operation())
    assert first["status"] == "recorded"
    assert first["record"]["verification"] == "agent_reported"
    assert first["record"]["status"] == "proposed"
    assert store.list_candidates()["total"] == 0
    assert store.record_source_operation(operation())["status"] == "unchanged"
    other = RecommendationStore(store.state_dir)
    assert other.source_history("alphaxiv")["items"] == [first["record"]]
    assert other.source_history("another-source")["items"] == []
    with pytest.raises(ResearchError):
        other.record_source_operation(operation(summary="Different operation under the same ID"))
    assert len(other.source_history()["items"]) == 1


@pytest.mark.parametrize("status", ["reported_completed", "reported_failed", "unconfirmed"])
def test_external_outcomes_remain_agent_reported(tmp_path, status):
    store = RecommendationStore(tmp_path / "pool")
    receipt = store.record_source_operation(operation(status=status))["record"]
    assert receipt["verification"] == "agent_reported"
    assert receipt["status"] == status
    assert "result" not in receipt
    assert store.list_candidates()["total"] == 0


@pytest.mark.parametrize("value", ["api_key=synthetic-secret-value", "Authorization: Bearer synthetic-value"])
def test_credentials_do_not_enter_source_notes_or_history(tmp_path, value):
    store = RecommendationStore(tmp_path / "pool")
    with pytest.raises(ResearchError):
        store.record_source_operation(operation(summary=value))
    with pytest.raises(ResearchError):
        store.update_source_context("alphaxiv", expected_revision=0, topics=[], notes=value)
    assert store.source_history()["items"] == []
    assert store.source_context("alphaxiv")["revision"] == 0


@pytest.mark.parametrize("changes", [
    {"status": "completed"}, {"status": []}, {"observed_at": "2026-11-09T12:00:00"},
    {"evidence_urls": ["http://127.0.0.1/private"]}, {"command": "not-an-executor"},
    {"source_id": "../not-a-source"},
])
def test_unbounded_or_misleading_operation_records_are_rejected(tmp_path, changes):
    store = RecommendationStore(tmp_path / "pool")
    with pytest.raises(ResearchError):
        store.record_source_operation(operation(**changes))
    assert store.source_history()["items"] == []


def test_in_progress_bibliography_freezes_its_authorized_candidate_snapshot(tmp_path):
    s,row=selected(tmp_path);plan=s.create_ingestion_plan(plan_for(row));s.claim_ingestion_plan(plan['plan_id'])
    with pytest.raises(ResearchError):s.set_decision(row['candidate_id'],'unread',row['revision'])
    result=s.submit({'schema_version':1,'producer':{'producer_id':'another','name':'Another'},'run_id':'two',
        'items':[{'submission_id':'changed','tags':[], 'resource':{**row['resource'],'title':'Changed while writing'}}]})
    assert result['receipts'][0]['status']=='conflict'
    assert s.get_candidate(row['candidate_id'])['resource']==row['resource']
