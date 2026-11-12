"""Code-only metadata and human-opinion handoff to a configured Zotero collection."""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.ingestion import (
    IngestionService, _collection, _failure, _preview_identity, _provider_identity, _resource_metadata,
)
from scholar_workflow.research.recommendations.project_tasks import pool_id
from scholar_workflow.research.recommendations.store import _json, _now
from scholar_workflow.research.store import root_directory, storage_lock
from scholar_workflow.workflows.zotero import _data, _exact_match, ingest_item


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def note_text(value):
    parser = _Text()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def intake_note(candidate, selected_at, tasks):
    """Render prepared content and verbatim opinions, never generate a new summary."""
    resource = candidate["resource"]

    def paragraph(value):
        return "<p>" + html.escape(str(value)).replace("\n", "<br>") + "</p>"

    parts = ["<h1>收录说明</h1>", "<h2>中文介绍</h2>"]
    if candidate["reading_kind"] == "abstract":
        parts.append(paragraph("摘要译文"))
        parts.append(paragraph(resource.get("abstract_zh", "")))
    else:
        parts.append(paragraph("资料总结"))
        parts.append(paragraph(resource.get("summary_zh") or resource.get("description_zh") or "尚无完整中文介绍。"))
    parts.append("<h2>用户意见</h2>")
    evaluation = candidate["evaluation"]
    parts.append(paragraph(evaluation["comment"] or "未填写意见。"))
    if evaluation["score"] is not None:
        parts.append(paragraph(f"评分：{evaluation['score']}/5"))
    parts.append("<h2>推荐背景</h2>")
    seen = set()
    task_map = {row["producer_id"]: row for row in tasks}
    for record in candidate["recommendations"]:
        producer = record["producer"]
        identifier = producer["producer_id"]
        reason = record.get("recommendation_reason", "")
        pair = (identifier, reason)
        if pair in seen:
            continue
        seen.add(pair)
        parts.append(paragraph(f"推荐任务：{producer['name']}"))
        if reason:
            parts.append(paragraph(reason))
        task = task_map.get(identifier)
        if task:
            parts.append(paragraph(f"项目：{task['project_title']}；任务：{task['title']}"))
        if record.get("requirement"):
            parts.append(paragraph(record["requirement"]["content"]))
        for channel in record.get("channels", []):
            parts.append(paragraph(f"发现来源：{channel['name']} — {channel['url']}"))
    parts.append("<h2>相关资源</h2>")
    links = [{"label": "原文", "url": resource["url"]}, *resource.get("links", [])]
    if resource.get("project_url"):
        links.append({"label": "项目主页", "url": resource["project_url"]})
    links.extend({"label": "总结依据", "url": url} for url in resource.get("summary_sources", []))
    seen = set()
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        parts.append('<p><a href="' + html.escape(link["url"], quote=True) + '">'
                     + html.escape(link["label"]) + "</a></p>")
    if candidate["tags"]:
        parts.append(paragraph("标签：" + "、".join(candidate["tags"])))
    parts.append("<h2>收录记录</h2>")
    parts.append(paragraph("选择时间：" + selected_at))
    parts.append(paragraph("本次接收元信息与意见；原始文件获取、补全和知识整理由后续任务完成。"))
    return "".join(parts)


class IntakeQueue:
    def __init__(self, store, profile="personal", *, service=None):
        self.store = store
        self.service = service or IngestionService(store, profile)
        self.profile = profile

    def configuration(self):
        with self.store._database() as db:
            row = db.execute("SELECT record FROM intake_configuration WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"schema_version": 1, "revision": 0, "enabled": False,
                                              "collection_key": None, "collection_name": None}

    def configure(self, collection_key, expected_revision, enabled=True):
        if type(expected_revision) is not int or expected_revision < 0 or type(enabled) is not bool:
            raise ResearchError("Intake configuration needs its exact revision and enabled boolean.")
        record = {"schema_version": 1, "revision": expected_revision + 1, "enabled": enabled,
                  "pool_id": pool_id(self.store), "profile": self.profile, "updated_at": _now()}
        if enabled:
            with self.service._adapter() as adapter:
                record["provider_identity"] = _provider_identity(adapter)
                collection = _collection(adapter, collection_key)
            record.update(collection_key=collection_key, collection_name=collection["name"])
        else:
            old = self.configuration()
            record.update({key: old.get(key) for key in ("provider_identity", "collection_key", "collection_name")})
        with self.store._database(write=True) as db:
            current = db.execute("SELECT record FROM intake_configuration WHERE id=1").fetchone()
            revision = json.loads(current[0])["revision"] if current else 0
            if revision != expected_revision:
                raise ResearchError("Intake target changed; reread it before saving.", 5)
            db.execute("INSERT INTO intake_configuration VALUES(1,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record", (_json(record),))
        return record

    def history(self):
        with self.store._database() as db:
            jobs = [json.loads(row[0]) for row in db.execute("SELECT record FROM intake_jobs ORDER BY rowid DESC LIMIT 200")]
            for job in jobs:
                candidate = self.store._candidate(db, self.store._row(db, job["candidate_id"]))
                job["title"] = candidate["resource"]["title"]
        return {"items": jobs, "configuration": self.configuration()}

    def _save(self, job):
        with self.store._database(write=True) as db:
            db.execute("UPDATE intake_jobs SET record=? WHERE candidate_id=?", (_json(job), job["candidate_id"]))

    def _note(self, adapter, candidate, parent_key, job):
        marker = "scholar-workflow:intake:" + pool_id(self.store) + ":" + candidate["candidate_id"]
        children = (adapter.get_children_all(parent_key) if hasattr(adapter, "get_children_all")
                    else adapter.get_children(parent_key))
        notes = [row for row in children if _data(row).get("itemType") == "note" and any(
            tag.get("tag") == marker for tag in _data(row).get("tags", []) if isinstance(tag, dict))]
        if len(notes) > 1:
            raise ResearchError("Multiple intake notes need identity review.", 5)
        known_note = (job.get("receipt") or {}).get("note_key")
        if known_note and not any(row.get("key", _data(row).get("key")) == known_note for row in notes):
            raise ResearchError("The previously received note was removed or its ownership marker changed; inspect before retrying.", 5)
        with self.store._database() as db:
            tasks = [json.loads(row[0]) for row in db.execute("SELECT record FROM recommendation_tasks")]
        body = intake_note(candidate, job["selected_at"], tasks)
        if notes:
            note = notes[0]
            key = note.get("key", _data(note).get("key"))
            actual = _data(note).get("note", "")
            if note_text(actual) != note_text(body):
                previous_hash = (job.get("receipt") or {}).get("note_hash")
                if previous_hash != hashlib.sha256(actual.encode()).hexdigest():
                    raise ResearchError("The intake note has human or external edits; automatic overwrite was refused.", 5)
                version = note.get("version", _data(note).get("version"))
                adapter.update_item(key, {"note": body}, version=version)
        else:
            key = adapter.create_item({"itemType": "note", "parentItem": parent_key,
                                       "note": body, "tags": [{"tag": marker}]})
        actual = adapter.get_item(key)
        data = _data(actual)
        if (data.get("itemType") != "note" or data.get("parentItem") != parent_key
                or note_text(data.get("note", "")) != note_text(body)):
            raise ResearchError("The intake note could not be verified after writing.", 6)
        return {"note_key": key, "note_hash": hashlib.sha256(data["note"].encode()).hexdigest()}

    def drain(self, *, limit=5, retry=False):
        """Run a bounded code-only batch. Never erase a human choice after provider failure."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ResearchError("Intake processing is limited to 1-100 items.")
        configuration = self.configuration()
        if not configuration["enabled"]:
            return {"status": "disabled", "items": []}
        results = []
        with root_directory(self.store.state_dir, create=True) as fd, storage_lock(fd, name=".intake-queue.lock", blocking=False):
            with self.store._database() as db:
                jobs = [json.loads(row[0]) for row in db.execute("SELECT record FROM intake_jobs ORDER BY rowid")]
            now = datetime.now(UTC)
            for job in jobs:
                if len(results) >= limit:
                    break
                if job["status"] not in ({"pending", "retry", "running", "needs_attention", "conflict"} if retry else {"pending", "retry", "running"}):
                    continue
                if not retry and job.get("next_attempt_at") and datetime.fromisoformat(job["next_attempt_at"]) > now:
                    continue
                with self.store._database(write=True) as db:
                    latest = json.loads(db.execute("SELECT record FROM intake_jobs WHERE candidate_id=?", (job["candidate_id"],)).fetchone()[0])
                    if latest["fingerprint"] != job["fingerprint"]:
                        continue
                    candidate = self.store._candidate(db, self.store._row(db, job["candidate_id"]))
                    legacy = [json.loads(row[0]) for row in db.execute("SELECT record FROM ingestion_plans WHERE candidate_id=?", (job["candidate_id"],))]
                    if any(row["status"] == "in_progress" for row in legacy):
                        continue
                    if candidate["decision"] != "selected" or (candidate["review_required"] and not candidate["abstract_reviewed"]):
                        job.update(status="cancelled", updated_at=_now())
                        db.execute("UPDATE intake_jobs SET record=? WHERE candidate_id=?", (_json(job), job["candidate_id"]))
                        continue
                    job.update(status="running", attempts=job.get("attempts", 0) + 1, updated_at=_now())
                    job.setdefault("selected_at", job["updated_at"])
                    db.execute("UPDATE intake_jobs SET record=? WHERE candidate_id=?", (_json(job), job["candidate_id"]))
                try:
                    if candidate["reading_kind"] not in {"abstract", "summary"} or not candidate["abstract_reviewed"]:
                        raise ResearchError("Review a prepared complete abstract translation or sourced synopsis before intake.", 7)
                    if configuration["revision"] != job["configuration_revision"]:
                        raise ResearchError("Intake target changed after selection; explicitly select this item again.", 5)
                    from scholar_workflow.research.recommendations.feedback import intake_fingerprint
                    if intake_fingerprint(candidate, configuration["revision"]) != job["fingerprint"]:
                        raise ResearchError("Candidate content changed after selection; review and select it again.", 5)
                    metadata = _resource_metadata(candidate["resource"])
                    with self.service._adapter() as adapter:
                        if _provider_identity(adapter) != configuration["provider_identity"]:
                            raise ResearchError("Zotero identity changed; confirm the intake target again.", 5)
                        _collection(adapter, configuration["collection_key"])
                        existing = _preview_identity(adapter, candidate["resource"], metadata)
                        prior_key = (job.get("receipt") or {}).get("item_key")
                        if prior_key and prior_key != existing:
                            raise ResearchError("Previously observed Zotero identity changed; inspect before retrying.", 5)
                        result = ingest_item(adapter, metadata=metadata, collection_keys=[configuration["collection_key"]])
                        key = result.get("item_key")
                        if not isinstance(key, str) or not re.fullmatch(r"[A-Z0-9]{8}", key):
                            raise ResearchError("Zotero omitted the observed item identity.", 6)
                        actual = adapter.get_item(key)
                        if not _exact_match(actual, metadata) or configuration["collection_key"] not in _data(actual).get("collections", []):
                            raise ResearchError("The bibliography and collection could not be verified.", 6)
                        job["receipt"] = {**(job.get("receipt") or {}), "item_key": key,
                                          "collection_key": configuration["collection_key"], "library_id": "users/0",
                                          "source_files": "not_requested", "knowledge": "not_requested"}
                        self._save(job)
                        job["receipt"].update(self._note(adapter, candidate, key, job))
                    job.update(status="completed", completed_at=_now(), error=None)
                    job.pop("next_attempt_at", None)
                except Exception as exc:
                    message, code = _failure(exc)
                    job.update(status="retry" if code == 3 else ("conflict" if code == 5 else "needs_attention"),
                               error=message, exit_code=code, updated_at=_now())
                    if code == 3:
                        job["next_attempt_at"] = (now + timedelta(seconds=min(300, 5 * 2 ** min(job["attempts"], 6)))).isoformat()
                self._save(job)
                results.append(job)
        return {"status": "complete" if all(job["status"] == "completed" for job in results) else "partial", "items": results}

    def entries(self, *, limit=50, start=0):
        """Read the Zotero queue and its child notes; do not open project contexts."""
        if type(limit) is not int or not 1 <= limit <= 100 or type(start) is not int or start < 0:
            raise ResearchError("Intake pages need a non-negative start and limit of 1-100.")
        configuration = self.configuration()
        if not configuration["enabled"]:
            raise ResearchError("Configure the Zotero intake collection first.")
        with self.store._database() as db:
            received = {}
            for row in db.execute("SELECT record FROM intake_jobs"):
                job = json.loads(row[0])
                key = (job.get("receipt") or {}).get("item_key")
                if not key:
                    continue
                candidate = self.store._candidate(db, self.store._row(db, job["candidate_id"]))
                task_refs = []
                for producer in candidate["producers"]:
                    task = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (producer["producer_id"],)).fetchone()
                    if task is not None:
                        data = json.loads(task[0])
                        task_refs.append({field: data[field] for field in ("project_id", "producer_id", "title", "context_file")})
                received[key] = {"candidate_id": candidate["candidate_id"], "tasks": task_refs,
                                 "current_evaluation": candidate["evaluation"], "decision": candidate["decision"]}
        with self.service._adapter() as adapter:
            if _provider_identity(adapter) != configuration["provider_identity"]:
                raise ResearchError("Zotero identity changed; confirm the target again.", 5)
            rows = adapter.get_collection_items(configuration["collection_key"], limit=limit, start=start)
            result = []
            for row in rows:
                if _data(row).get("itemType") in {"attachment", "note"}:
                    continue
                key = row.get("key", _data(row).get("key"))
                children = adapter.get_children_all(key) if hasattr(adapter, "get_children_all") else adapter.get_children(key)
                result.append({"item": row, "children": children, "recommendation": received.get(key)})
        return {"scope": "zotero_intake", "collection_key": configuration["collection_key"],
                "items": result, "limit": limit, "start": start,
                "next_start": start + len(rows), "may_have_more": len(rows) >= limit}
