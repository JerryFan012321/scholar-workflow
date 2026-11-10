"""Independent expectations for reviewed, explicitly confirmed Zotero bibliography writes."""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scholar_workflow.adapters.zotero_local import ZoteroLocalUnavailable
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.ingestion import IngestionService
from scholar_workflow.research.recommendations.store import RecommendationStore


class FakeZotero:
    def __init__(self):
        self.server_id = "private-provider-identity"
        self.collections = [{"key": "COLL2345", "version": 2,
                             "data": {"name": "Chosen research", "parentCollection": False}}]
        self.items = []
        self.writes = []
        self.unavailable = False
        self.fail_readback = False
        self.fail_after_create = False
        self.searches = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def probe(self):
        if self.unavailable:
            raise ZoteroLocalUnavailable("private failure should not leak")
        return SimpleNamespace(server_id=self.server_id, api_version="3", schema_version="42")

    def get_collections(self, *, limit=None):
        return copy.deepcopy(self.collections)

    def search_items(self, query, *, qmode, limit):
        self.searches += 1
        return copy.deepcopy(self.items)

    def create_item(self, metadata):
        self.writes.append(("create", copy.deepcopy(metadata)))
        self.items.append({"key": "ITEM2345", "version": 1, "data": copy.deepcopy(metadata)})
        if self.fail_after_create:
            self.fail_after_create = False
            raise RuntimeError("response was lost after the external write")
        return "ITEM2345"

    def update_item(self, item_key, changes, *, version):
        self.writes.append(("update", item_key, copy.deepcopy(changes)))
        for row in self.items:
            if row["key"] == item_key:
                row["data"].update(copy.deepcopy(changes))
                row["version"] += 1

    def get_item(self, key):
        if self.fail_readback:
            raise ZoteroLocalUnavailable("readback unavailable")
        return copy.deepcopy(next(row for row in self.items if row["key"] == key))


@pytest.fixture
def setup(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    payload = {"schema_version": 1, "producer": {"producer_id": "fixture", "name": "Fixture"},
               "run_id": "run", "items": [{"submission_id": "paper", "tags": ["synthetic"],
               "resource": {"kind": "paper", "title": "Synthetic paper", "url": "https://arxiv.org/abs/2401.12345v2",
                            "arxiv_id": "2401.12345v2", "authors": ["Alice Example"],
                            "abstract_original": "The complete original abstract.", "abstract_zh": "完整的合成摘要。"}}]}
    receipt = store.submit(payload)
    row = store.get_candidate(receipt["receipts"][0]["candidate_id"])
    row = store.review_candidate(row["candidate_id"], row["revision"])
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    adapter = FakeZotero()
    service = IngestionService(store, profile="test", adapter_factory=lambda: adapter)
    return store, row, adapter, service


def make_plan(setup):
    _, row, _, service = setup
    return service.plan(row["candidate_id"], row["revision"], "COLL2345")


def test_plan_is_read_only_and_confirmed_execute_returns_observed_bibliography(setup):
    store, row, adapter, service = setup
    plan = make_plan(setup)
    assert not adapter.writes
    assert plan["scope"] == "zotero_bibliography"
    assert plan["metadata"]["itemType"] == "preprint"
    assert plan["metadata"]["creators"] == [{"creatorType": "author", "name": "Alice Example"}]
    assert plan["metadata"]["abstractNote"] == "The complete original abstract."
    assert "private-provider-identity" not in str(plan)
    receipt = service.execute(plan["plan_id"], confirmed=True)
    assert receipt["status"] == "completed"
    assert receipt["scope"] == "zotero_bibliography"
    assert receipt["item_key"] == "ITEM2345"
    assert receipt["collection_key"] == "COLL2345"
    assert receipt["pdf_status"] == receipt["knowledge_status"] == "not_requested"
    assert adapter.items[0]["data"]["collections"] == ["COLL2345"]
    assert service.execute(plan["plan_id"], confirmed=True) == receipt
    assert len(adapter.writes) == 1
    assert service.history()[0]["status"] == "completed"
    assert store.get_candidate(row["candidate_id"])["decision"] == "selected"


@pytest.mark.parametrize("change", ["unselected", "stale_revision", "unreviewed"])
def test_plan_refuses_unselected_unreviewed_or_stale_candidates(setup, change):
    store, row, adapter, service = setup
    revision = row["revision"]
    if change == "unselected":
        row = store.set_decision(row["candidate_id"], "saved", revision)
        revision = row["revision"]
    elif change == "stale_revision":
        revision -= 1
    else:
        payload = {"schema_version": 1, "producer": {"producer_id": "changed", "name": "Changed"},
                   "run_id": "changed", "items": [{"submission_id": "changed", "tags": [],
                   "resource": {**row["resource"], "abstract_original": "Changed original.", "abstract_zh": "已改变。"}}]}
        store.submit(payload)
        revision = store.get_candidate(row["candidate_id"])["revision"]
    with pytest.raises(ResearchError):
        service.plan(row["candidate_id"], revision, "COLL2345")
    assert not adapter.writes


def test_collection_must_exist_and_paper_authors_cannot_be_invented(setup):
    store, row, adapter, service = setup
    with pytest.raises(ResearchError):
        service.plan(row["candidate_id"], row["revision"], "UNKNOWN1")
    row["resource"]["authors"] = []
    original = store.get_candidate
    store.get_candidate = lambda identifier: row if identifier == row["candidate_id"] else original(identifier)
    with pytest.raises(ResearchError, match="author"):
        service.plan(row["candidate_id"], row["revision"], "COLL2345")
    assert not adapter.writes


@pytest.mark.parametrize("change", ["provider", "collection", "candidate", "expiry"])
def test_execute_revalidates_before_any_external_write(setup, monkeypatch, change):
    store, row, adapter, service = setup
    plan = make_plan(setup)
    if change == "provider":
        adapter.server_id = "another-library"
    elif change == "collection":
        adapter.collections[0]["version"] += 1
    elif change == "candidate":
        store.set_decision(row["candidate_id"], "saved", row["revision"])
    else:
        from scholar_workflow.research.recommendations import ingestion
        monkeypatch.setattr(ingestion, "_now", lambda: datetime.now(UTC) + timedelta(days=1))
    with pytest.raises(ResearchError):
        service.execute(plan["plan_id"], confirmed=True)
    assert not adapter.writes


def test_execute_requires_literal_confirmation(setup):
    plan = make_plan(setup)
    service = setup[3]
    for confirmation in [False, "yes", 1, None]:
        with pytest.raises(ResearchError):
            service.execute(plan["plan_id"], confirmed=confirmation)
    assert not setup[2].writes


def test_exact_existing_item_preserves_other_memberships(setup):
    _, _, adapter, service = setup
    adapter.items = [{"key": "KEEP2345", "version": 3, "data": {"itemType": "preprint", "title": "Synthetic paper",
        "creators": [{"creatorType": "author", "name": "Alice Example"}], "collections": ["OLD23456"], "archiveID": "2401.12345v2"}}]
    plan = make_plan(setup)
    receipt = service.execute(plan["plan_id"], confirmed=True)
    assert receipt["item_key"] == "KEEP2345"
    assert adapter.items[0]["data"]["collections"] == ["OLD23456", "COLL2345"]
    assert adapter.writes[0][0] == "update"


def test_same_arxiv_with_changed_identity_or_multiple_matches_refuses(setup):
    _, _, adapter, service = setup
    adapter.items = [{"key": "KEEP2345", "version": 3, "data": {"itemType": "preprint", "title": "Published variation",
        "creators": [{"creatorType": "author", "name": "Different Author"}], "archiveID": "2401.12345v1"}}]
    with pytest.raises(ResearchError):
        make_plan(setup)
    assert not adapter.writes


def test_lost_external_response_requires_explicit_retry_and_reuses_created_item(setup):
    _, _, adapter, service = setup
    plan = make_plan(setup)
    adapter.fail_after_create = True
    receipt = service.execute(plan["plan_id"], confirmed=True)
    assert receipt["status"] == "needs_attention"
    with pytest.raises(ResearchError):
        service.execute(plan["plan_id"], confirmed=True)
    result = service.execute(plan["plan_id"], confirmed=True, retry=True)
    assert result["status"] == "completed"
    assert len(adapter.writes) == 1


def test_readback_failure_never_reports_completion_and_retains_observed_key(setup):
    _, _, adapter, service = setup
    plan = make_plan(setup)
    adapter.fail_readback = True
    receipt = service.execute(plan["plan_id"], confirmed=True)
    assert receipt["status"] == "needs_attention"
    assert receipt["item_key"] == "ITEM2345"
    adapter.fail_readback = False
    assert service.execute(plan["plan_id"], confirmed=True, retry=True)["status"] == "completed"
    assert len(adapter.writes) == 1


def test_unavailable_provider_is_dependency_gap_and_test_defaults_never_open_native_adapter(setup):
    _, row, adapter, service = setup
    adapter.unavailable = True
    with pytest.raises(ResearchError) as error:
        service.plan(row["candidate_id"], row["revision"], "COLL2345")
    assert error.value.exit_code == 3
    with pytest.raises(ResearchError):
        IngestionService(setup[0], profile="test").targets()
    assert not adapter.writes


@pytest.mark.parametrize("kind,item_type", [("blog", "blogPost"), ("project", "webpage")])
def test_nonpaper_bibliography_does_not_claim_vault_snapshot_or_fake_abstract(setup, kind, item_type):
    store, _, adapter, service = setup
    data = {"schema_version": 1, "producer": {"producer_id": kind, "name": kind}, "run_id": kind,
        "items": [{"submission_id": kind, "tags": [], "resource": {"kind": kind, "title": "Synthetic " + kind,
        "url": "https://example.org/" + kind, "summary_zh": "有来源的整理总结。", "summary_sources": ["https://example.org/" + kind]}}]}
    receipt = store.submit(data);row = store.get_candidate(receipt["receipts"][0]["candidate_id"])
    row = store.review_candidate(row["candidate_id"], row["revision"])
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    plan = service.plan(row["candidate_id"], row["revision"], "COLL2345")
    assert plan["metadata"]["itemType"] == item_type
    assert "abstractNote" not in plan["metadata"]
    result = service.execute(plan["plan_id"], confirmed=True)
    assert result["knowledge_status"] == "not_requested"
    assert result["pdf_status"] == "not_requested"


def test_same_title_nonpaper_with_other_url_is_an_identity_conflict(setup):
    store, _, adapter, service = setup
    data = {"schema_version": 1, "producer": {"producer_id": "blog-conflict", "name": "Blog"}, "run_id": "blog",
        "items": [{"submission_id": "blog", "tags": [], "resource": {"kind": "blog", "title": "Same named announcement",
        "url": "https://example.org/new", "description_original": "Original introduction."}}]}
    result = store.submit(data)
    row = store.get_candidate(result["receipts"][0]["candidate_id"])
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    adapter.items = [{"key": "KEEP2345", "version": 3, "data": {"itemType": "blogPost", "title": "Same named announcement",
        "url": "https://example.org/different", "creators": []}}]
    with pytest.raises(ResearchError) as error:
        service.plan(row["candidate_id"], row["revision"], "COLL2345")
    assert error.value.exit_code == 5 and not adapter.writes


def test_multiple_exact_matches_refuse_before_any_write(setup):
    _, _, adapter, _ = setup
    adapter.items = [{"key": key, "version": 3, "data": {"itemType": "preprint", "title": "Synthetic paper",
        "creators": [{"creatorType": "author", "name": "Alice Example"}], "archiveID": "2401.12345v2"}}
        for key in ["KEEP2345", "KEEP6789"]]
    with pytest.raises(ResearchError) as error:
        make_plan(setup)
    assert error.value.exit_code == 5 and not adapter.writes


def test_history_projects_readable_plan_and_result_without_private_metadata(setup):
    _, _, adapter, service = setup
    plan = make_plan(setup)
    pending = service.history()[0]
    assert pending["title"] == "Synthetic paper"
    assert pending["collection"]["name"] == "Chosen research"
    assert pending["status"] == "pending"
    assert "metadata" not in pending and "resource" not in pending and "provider_identity" not in pending
    adapter.fail_readback = True
    result = service.execute(plan["plan_id"], confirmed=True)
    row = service.history()[0]
    assert row["status"] == "needs_attention"
    assert row["error"] == result["error"]
    assert row["item_key"] == "ITEM2345"
    assert row["zotero_url"] == "zotero://select/library/items/ITEM2345"
    assert row["checked_at"] == result["checked_at"]
    assert row["receipt"] == result
    assert "private-provider-identity" not in str(row)


def test_project_author_abstract_is_preserved_in_bibliography_metadata():
    from scholar_workflow.research.recommendations.ingestion import _resource_metadata
    result = _resource_metadata({"kind":"project", "title":"Synthetic project with an author abstract",
        "url":"https://example.org/project", "abstract_original":"Complete author abstract.",
        "description_original":"Old short subtitle."})
    assert result["itemType"] == "webpage"
    assert result["abstractNote"] == "Complete author abstract."
