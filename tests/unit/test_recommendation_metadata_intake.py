"""Independent metadata/opinion expectations with a fake, file-transfer-forbidden provider."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from scholar_workflow.adapters.zotero_local import ZoteroLocalUnavailable
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.feedback import Feedback
from scholar_workflow.research.recommendations.ingestion import IngestionService
from scholar_workflow.research.recommendations.intake import IntakeQueue, note_text
from scholar_workflow.research.recommendations.store import RecommendationStore


class FakeLibrary:
    def __init__(self):
        self.identity = "synthetic-local-api"
        self.items = {}
        self.offline = False
        self.fail_note_once = False
        self.file_transfers = 0
        self.collection_names = {"INBX2345": "待整理条目", "INBX2346": "Another chosen inbox"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def probe(self):
        if self.offline:
            raise ZoteroLocalUnavailable("synthetic offline")
        return SimpleNamespace(server_id=self.identity, api_version="3", schema_version="42")

    def get_collections(self, *, limit=None):
        return [{"key": key, "version": 1, "data": {"name": name}} for key, name in self.collection_names.items()]

    def search_items(self, query, *, qmode, limit):
        return copy.deepcopy([row for row in self.items.values() if row["data"]["itemType"] != "note"])

    def create_item(self, metadata):
        key = ("NTES" if metadata["itemType"] == "note" else "ITEM") + "ABCDEFGHJKLMNPQRSTUVWXYZ"[len(self.items)] * 4
        self.items[key] = {"key": key, "version": 1, "data": copy.deepcopy(metadata)}
        if metadata["itemType"] == "note" and self.fail_note_once:
            self.fail_note_once = False
            raise RuntimeError("lost response after note creation")
        return key

    def get_item(self, key):
        return copy.deepcopy(self.items[key])

    def update_item(self, key, changes, *, version):
        assert version == self.items[key]["version"]
        self.items[key]["data"].update(copy.deepcopy(changes))
        self.items[key]["version"] += 1

    def get_children_all(self, key):
        return copy.deepcopy([row for row in self.items.values() if row["data"].get("parentItem") == key])

    def get_collection_items(self, collection_key, *, limit, start=0):
        return copy.deepcopy([row for row in self.items.values() if collection_key in row["data"].get("collections", [])][start:start + limit])

    def import_file(self, *_args, **_kwargs):
        self.file_transfers += 1
        pytest.fail("Metadata reception must never transfer an original file")


def submit(store, kind="paper", *, item_type=None):
    resource = {"kind": kind, "title": "Synthetic " + kind, "url": "https://example.org/" + kind,
                "authors": ["Synthetic Lab"], "project_url": "https://example.org/project",
                "links": [{"label": "研究 Blog", "url": "https://example.org/research-blog"}]}
    if item_type:
        resource["item_type"] = item_type
    if kind == "paper" and item_type is None:
        resource.update(arxiv_id="2401.12345", url="https://arxiv.org/abs/2401.12345",
                        abstract_original="Full original abstract with the task, method, evidence and boundary.",
                        abstract_zh="这份完整摘要介绍研究任务、主要方法、实验依据和适用边界。")
    else:
        resource.update(summary_zh="该项目公开了研究目标、方法概要、实验结果及使用入口。尚未披露的技术细节留待后续核实。",
                        summary_sources=[resource["url"]])
    envelope = {"schema_version": 1, "producer": {"producer_id": "project-research", "name": "Project research"},
                "run_id": kind, "items": [{"submission_id": kind, "tags": ["world-models"], "resource": resource,
                                           "recommendation_reason": "Useful to compare evaluation protocols."}]}
    result = store.submit(envelope)
    assert result["receipts"][0]["status"] == "accepted", result
    row = store.get_candidate(result["receipts"][0]["candidate_id"])
    return store.review_candidate(row["candidate_id"], row["revision"])


@pytest.fixture
def setup(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    library = FakeLibrary()
    service = IngestionService(store, profile="test", adapter_factory=lambda: library)
    queue = IntakeQueue(store, "test", service=service)
    queue.configure("INBX2345", 0)
    return store, library, queue


@pytest.mark.parametrize("kind,expected_type", [("paper", "preprint"), ("blog", "blogPost"), ("project", "webpage")])
def test_one_selection_receives_metadata_and_exact_human_context_without_original_files(setup, kind, expected_type):
    store, library, queue = setup
    row = submit(store, kind)
    row = store.save_evaluation(row["candidate_id"], 4, "放进世界模型的评测分类。\n只整理指标，不用全文分析。", 0, row["revision"])
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    assert row["intake_job"]["status"] == "pending"
    result = queue.drain()
    assert result["status"] == "complete", result
    job = result["items"][0]
    parent = library.items[job["receipt"]["item_key"]]["data"]
    note = library.items[job["receipt"]["note_key"]]["data"]
    assert parent["itemType"] == expected_type
    assert parent["collections"] == ["INBX2345"]
    assert "放进世界模型的评测分类。<br>只整理指标，不用全文分析。" in note["note"]
    text = note_text(note["note"])
    assert "Useful to compare evaluation protocols." in text
    assert "评分：4/5" in text
    assert "研究 Blog" in text and "https://example.org/project" in note["note"]
    assert "摘要译文" in text if kind == "paper" else "资料总结" in text
    assert job["receipt"]["source_files"] == job["receipt"]["knowledge"] == "not_requested"
    assert library.file_transfers == 0
    assert len(library.items) == 2
    assert queue.entries()["items"][0]["children"][0]["key"] == job["receipt"]["note_key"]
    assert queue.drain()["items"] == []
    assert len(library.items) == 2


def test_zotero_offline_keeps_human_feedback_and_resumes_without_an_agent(setup):
    store, library, queue = setup
    row = submit(store)
    library.offline = True
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    result = queue.drain()
    assert result["items"][0]["status"] == "retry"
    assert store.get_candidate(row["candidate_id"])["decision"] == "selected"
    assert Feedback(store).status()["curator_pending"] == 1
    assert list(store.state_dir.glob("context/inbox/*.jsonl"))
    library.offline = False
    result = queue.drain(retry=True)
    assert result["items"][0]["status"] == "completed"
    assert len(library.items) == 2


def test_lost_note_response_is_recovered_by_identity_without_duplicates(setup):
    store, library, queue = setup
    row = submit(store, "blog")
    library.fail_note_once = True
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    first = queue.drain()
    assert first["items"][0]["status"] == "needs_attention"
    assert len(library.items) == 2
    assert queue.drain(retry=True)["items"][0]["status"] == "completed"
    assert len(library.items) == 2


def test_human_note_edit_is_preserved_when_later_feedback_arrives(setup):
    store, library, queue = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    receipt = queue.drain()["items"][0]["receipt"]
    note = library.items[receipt["note_key"]]
    note["data"]["note"] += "<p>Human edits must survive.</p>"
    row = store.get_candidate(row["candidate_id"])
    store.save_evaluation(row["candidate_id"], 5, "New classification opinion", 0, row["revision"])
    result = queue.drain()
    assert result["items"][0]["status"] == "conflict"
    assert "Human edits must survive." in note["data"]["note"]
    assert len(library.items) == 2


def test_later_evaluation_updates_the_same_unedited_note(setup):
    store, library, queue = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    receipt = queue.drain()["items"][0]["receipt"]
    row = store.get_candidate(row["candidate_id"])
    store.save_evaluation(row["candidate_id"], 5, "分类意见更新", 0, row["revision"])
    result = queue.drain()
    assert result["items"][0]["status"] == "completed", result
    assert result["items"][0]["receipt"]["note_key"] == receipt["note_key"]
    assert "分类意见更新" in library.items[receipt["note_key"]]["data"]["note"]
    assert len(library.items) == 2


def test_configure_does_not_import_old_selections_and_target_change_needs_new_selection(setup):
    store, library, queue = setup
    queue.configure(None, 1, False)
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    assert row["intake_job"] is None
    queue.configure("INBX2345", 2)
    assert queue.drain()["items"] == []
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    queue.configure("INBX2346", 3)
    assert queue.drain()["items"][0]["status"] == "conflict"
    assert not library.items
    row = store.get_candidate(row["candidate_id"])
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    result = queue.drain()
    assert result["items"][0]["receipt"]["collection_key"] == "INBX2346"


def test_withdrawal_cancels_pending_work_without_deleting_received_items(setup):
    store, library, queue = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    row = store.set_decision(row["candidate_id"], "saved", row["revision"])
    assert row["intake_job"]["status"] == "cancelled"
    assert queue.drain()["items"] == []
    assert not library.items
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    queue.drain()
    store.set_decision(row["candidate_id"], "unread", row["revision"])
    assert len(library.items) == 2


def test_provider_identity_change_refuses_external_writes(setup):
    store, library, queue = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    library.identity = "different-library"
    assert queue.drain()["items"][0]["status"] == "conflict"
    assert not library.items


def test_withdrawal_while_automatic_intake_is_paused_cancels_pending_job(setup):
    store, library, queue = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    queue.configure(None, 1, False)
    row = store.set_decision(row["candidate_id"], "unread", row["revision"])
    assert row["intake_job"]["status"] == "cancelled"
    assert not library.items


def test_removed_note_marker_does_not_create_a_duplicate_note(setup):
    store, library, queue = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    receipt = queue.drain()["items"][0]["receipt"]
    library.items[receipt["note_key"]]["data"]["tags"] = []
    row = store.get_candidate(row["candidate_id"])
    store.save_evaluation(row["candidate_id"], 5, "New opinion", 0, row["revision"])
    assert queue.drain()["items"][0]["status"] == "conflict"
    assert len(library.items) == 2


def test_test_profile_cannot_contact_native_zotero(tmp_path):
    queue = IntakeQueue(RecommendationStore(tmp_path / "state"), "test")
    with pytest.raises(ResearchError) as error:
        queue.configure("INBX2345", 0)
    assert error.value.exit_code == 7


def test_missing_prepared_intro_is_not_generated_or_received(setup):
    store, library, queue = setup
    submitted = store.submit({"schema_version": 1, "producer": {"producer_id": "synthetic", "name": "Synthetic"},
                              "run_id": "empty", "items": [{"submission_id": "empty", "tags": [], "resource": {
                                  "kind": "project", "title": "Unprepared page", "url": "https://example.org/unprepared"}}]})
    identifier = submitted["receipts"][0]["candidate_id"]
    store.set_decision(identifier, "selected", 1)
    result = queue.drain()
    assert result["items"][0]["status"] == "needs_attention"
    assert not library.items


def test_receiving_queue_is_read_in_pages_with_task_context_locators(setup):
    store, library, queue = setup
    for kind in ["paper", "blog", "project"]:
        row = submit(store, kind)
        store.set_decision(row["candidate_id"], "selected", row["revision"])
        assert queue.drain()["status"] == "complete"
    first = queue.entries(limit=2)
    second = queue.entries(limit=2, start=first["next_start"])
    assert len(first["items"]) == 2 and first["may_have_more"]
    assert len(second["items"]) == 1 and not second["may_have_more"]
    assert first["items"][0]["recommendation"]["candidate_id"]


def test_verified_native_report_type_is_retained(setup):
    store, library, queue = setup
    row = submit(store, "project", item_type="report")
    store.set_decision(row["candidate_id"], "selected", row["revision"])
    receipt = queue.drain()["items"][0]["receipt"]
    assert library.items[receipt["item_key"]]["data"]["itemType"] == "report"


def test_http_selection_automatically_writes_feedback_and_zotero_without_an_agent(setup, monkeypatch):
    import http.client
    import json
    import threading
    from scholar_workflow.research.recommendations import server as module

    store, library, queue = setup
    row = submit(store, "blog")
    monkeypatch.setattr(module, "IngestionService", lambda _store, _profile: queue.service)
    token = "synthetic-browser-credential-for-tests-only"
    server = module.create_server(store.state_dir, "test", token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request("POST", "/api/decisions", json.dumps({"candidate_id": row["candidate_id"],
                           "decision": "selected", "expected_revision": row["revision"]}),
                           {"Content-Type": "application/json", "Authorization": "Bearer " + token,
                            "Origin": f"http://127.0.0.1:{server.server_port}"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        assert response.status == 200, payload
        assert payload["decision"] == "selected"
        assert payload["intake_job"]["status"] == "completed"
        assert len(library.items) == 2
        assert Feedback(store).status()["curator_pending"] == 1
        assert list(store.state_dir.glob("context/inbox/*.jsonl"))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        assert not thread.is_alive()
