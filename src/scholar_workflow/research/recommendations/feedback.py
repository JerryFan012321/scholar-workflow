"""Transactional feedback, native queue receipts and independent curator projection."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import context_files as disk
from scholar_workflow.research.recommendations.project_tasks import pool_id
from scholar_workflow.research.recommendations import codex_feedback as queue
from scholar_workflow.research.recommendations.store import _digest, _json, _now
from scholar_workflow.research.store import root_directory, storage_lock

DDL = """
CREATE TABLE IF NOT EXISTS feedback_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
 candidate_id TEXT NOT NULL, record TEXT NOT NULL, consumed_at TEXT);
CREATE TABLE IF NOT EXISTS feedback_deliveries(
 event_id TEXT NOT NULL, recipient TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
 error TEXT, PRIMARY KEY(event_id,recipient));
CREATE TABLE IF NOT EXISTS feedback_queue_receipts(
 event_id TEXT NOT NULL, producer_id TEXT NOT NULL, record TEXT NOT NULL,
 PRIMARY KEY(event_id,producer_id));
CREATE TABLE IF NOT EXISTS feedback_batches(batch_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_dispositions(candidate_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intake_configuration(id INTEGER PRIMARY KEY CHECK(id=1), record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intake_jobs(candidate_id TEXT PRIMARY KEY, record TEXT NOT NULL);
"""


def has_feedback(candidate):
    evaluation = candidate["evaluation"]
    return candidate["decision"] != "unread" or evaluation["score"] is not None or bool(evaluation["comment"])


def record_event(store, db, candidate, kind, *, only_task=None):
    """Called inside the human mutation's transaction, before its database is persisted."""
    event_id = "feedback-" + str(uuid.uuid4())
    resource = candidate["resource"]
    recipients = [row[0] for row in db.execute(
        "SELECT DISTINCT t.producer_id FROM recommendation_tasks t "
        "JOIN recommendations r ON r.producer_id=t.producer_id WHERE r.candidate_id=?",
        (candidate["candidate_id"],))]
    if only_task is not None:
        recipients = [only_task]
    tasks, routes = [], []
    for task_id in recipients:
        row = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (task_id,)).fetchone()
        if row is None:
            continue
        task = json.loads(row[0])
        tasks.append({key: task.get(key) for key in ("project_id", "producer_id", "title")})
        if task.get("schema_version") == 2:
            # Snapshot the route, even when unavailable, rather than silently rerouting later.
            routes.append(task)
    now = _now()
    record = {"schema_version": 1, "pool_id": pool_id(store), "pool_state_dir": str(store.state_dir), "event_id": event_id,
              "kind": kind, "candidate_id": candidate["candidate_id"], "title": resource["title"],
              "url": resource["url"], "tags": candidate["tags"],
              "summary": resource.get("abstract_zh") or resource.get("summary_zh") or resource.get("description_zh") or "",
              "processed_at": None if kind == "baseline" else now, "observed_at": now,
              "decision": candidate["decision"], "disposition": candidate.get("disposition"),
              "evaluation": candidate["evaluation"], "candidate_revision": candidate["revision"],
              "resource_digest": _digest(resource), "resource": resource,
              "recommendations": candidate.get("recommendations", []), "tasks": tasks}
    cursor = db.execute("INSERT INTO feedback_events(event_id,candidate_id,record) VALUES(?,?,?)",
                        (event_id, candidate["candidate_id"], _json(record)))
    record["sequence"] = cursor.lastrowid
    db.execute("UPDATE feedback_events SET record=? WHERE event_id=?", (_json(record), event_id))
    for recipient in [*("task:" + task for task in recipients), *(["curator"] if kind != "baseline" else [])]:
        db.execute("INSERT INTO feedback_deliveries(event_id,recipient) VALUES(?,?)", (event_id, recipient))
    for route in routes:
        delivery = {"event_id": event_id, "producer_id": route["producer_id"],
                    "pool_id": pool_id(store), "route": route, "status": "pending",
                    "attempts": 0, "error": None, "created_at": now, "updated_at": now}
        db.execute("INSERT INTO feedback_queue_receipts VALUES(?,?,?)",
                   (event_id, route["producer_id"], _json(delivery)))
    return record


def record_baseline(store, db, producer_id, candidate_id=None):
    query = "SELECT DISTINCT c.* FROM candidates c JOIN recommendations r ON r.candidate_id=c.candidate_id WHERE r.producer_id=?"
    args = [producer_id]
    if candidate_id:
        query += " AND c.candidate_id=?"
        args.append(candidate_id)
    for row in db.execute(query, args).fetchall():
        candidate = store._candidate(db, row)
        if not has_feedback(candidate):
            continue
        known = db.execute("SELECT 1 FROM feedback_deliveries d JOIN feedback_events e ON e.event_id=d.event_id "
                           "WHERE d.recipient=? AND e.candidate_id=?", ("task:" + producer_id, row["candidate_id"])).fetchone()
        if known is None:
            record_event(store, db, candidate, "baseline", only_task=producer_id)


def intake_fingerprint(candidate, configuration_revision):
    return _digest({"resource": candidate["resource"], "evaluation": candidate["evaluation"],
                    "tags": candidate["tags"], "disposition": candidate.get("disposition"),
                    "configuration_revision": configuration_revision})


def queue_intake(db, candidate, *, new_selection=False):
    """Queue only a human-selected/reviewed item under an explicitly configured target."""
    old = db.execute("SELECT record FROM intake_jobs WHERE candidate_id=?", (candidate["candidate_id"],)).fetchone()
    old = json.loads(old[0]) if old else {}
    if candidate["decision"] != "selected" or (candidate["review_required"] and not candidate["abstract_reviewed"]):
        if old.get("status") in {"pending", "retry"}:
            old.update(status="cancelled", updated_at=_now())
            db.execute("UPDATE intake_jobs SET record=? WHERE candidate_id=?", (_json(old), candidate["candidate_id"]))
        return
    config = db.execute("SELECT record FROM intake_configuration WHERE id=1").fetchone()
    if config is None or not json.loads(config[0]).get("enabled"):
        return
    configuration = json.loads(config[0])
    if not new_selection and (not old or old["configuration_revision"] != configuration["revision"]):
        return
    fingerprint = intake_fingerprint(candidate, configuration["revision"])
    if old.get("fingerprint") == fingerprint and old.get("status") in {"pending", "running", "completed"}:
        return
    job = {"candidate_id": candidate["candidate_id"], "status": "pending", "fingerprint": fingerprint,
           "configuration_revision": configuration["revision"], "updated_at": _now(),
           "selected_at": _now() if new_selection else old.get("selected_at") or _now(),
           "attempts": 0, "receipt": old.get("receipt")}
    db.execute("INSERT INTO intake_jobs VALUES(?,?) ON CONFLICT(candidate_id) DO UPDATE SET record=excluded.record",
               (candidate["candidate_id"], _json(job)))


class Feedback:
    def __init__(self, store, *, runner=None, native_enabled=None):
        self.store = store
        self.runner = runner
        self.native_enabled = store.state_dir.name == "personal" if native_enabled is None else bool(native_enabled)

    def status(self):
        with self.store._database() as db:
            pending = [dict(row) for row in db.execute(
                "SELECT event_id,recipient,error FROM feedback_deliveries WHERE delivered=0 ORDER BY rowid")]
            count = db.execute("SELECT count(*) FROM feedback_events WHERE consumed_at IS NULL AND event_id IN "
                               "(SELECT event_id FROM feedback_deliveries WHERE recipient='curator')").fetchone()[0]
        return {"schema_version": 1, "pool_id": pool_id(self.store), "pending_deliveries": pending,
                "curator_pending": count, "context_directory": str(self.store.state_dir / "context")}

    def events(self, *, producer_id=None, after=0, limit=100, expected_pool=None):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ResearchError("Feedback uses a non-negative event sequence and a limit of 1-1000.")
        if (after or expected_pool is not None) and expected_pool != pool_id(self.store):
            raise ResearchError("An incremental cursor requires its matching originating pool_id.", 5)
        with self.store._database() as db:
            if producer_id:
                from scholar_workflow.research.recommendations.project_tasks import identifier
                identifier(producer_id)
                if db.execute("SELECT 1 FROM recommendation_tasks WHERE producer_id=?", (producer_id,)).fetchone() is None:
                    raise ResearchError("Recommendation task is not registered.")
                rows = db.execute("SELECT e.record FROM feedback_events e JOIN feedback_deliveries d ON e.event_id=d.event_id "
                                  "WHERE d.recipient=? AND e.sequence>? ORDER BY e.sequence LIMIT ?",
                                  ("task:" + producer_id, after, limit + 1)).fetchall()
            else:
                rows = db.execute("SELECT record FROM feedback_events WHERE sequence>? ORDER BY sequence LIMIT ?",
                                  (after, limit + 1)).fetchall()
        records = [json.loads(row[0]) for row in rows[:limit]]
        return {"schema_version": 1, "pool_id": pool_id(self.store), "items": records,
                "next_sequence": records[-1]["sequence"] if records else after, "has_more": len(rows) > limit}

    def flush(self):
        """Project curator events and dispatch pending native messages outside the writer lock."""
        with root_directory(self.store.state_dir, create=True) as root_fd:
            with storage_lock(root_fd, name=".feedback-delivery.lock"):
                with self.store._database() as db:
                    pending = db.execute("SELECT DISTINCT recipient FROM feedback_deliveries WHERE delivered=0").fetchall()
                for entry in pending:
                    recipient = entry[0]
                    if recipient != "curator":
                        continue
                    try:
                        with self.store._database() as db:
                            rows = db.execute("SELECT e.record,e.consumed_at FROM feedback_events e JOIN feedback_deliveries d "
                                              "ON e.event_id=d.event_id WHERE d.recipient=? ORDER BY e.sequence", (recipient,)).fetchall()
                        dates, consumed = {}, {}
                        for row in rows:
                            record = json.loads(row[0])
                            day = datetime.fromisoformat(record["observed_at"]).astimezone().date().isoformat()
                            dates.setdefault(day, [])
                            if row[1] is None:
                                dates[day].append(record)
                            else:
                                consumed[record["event_id"]] = record
                        for day, day_records in dates.items():
                            disk.project_jsonl(self.store.state_dir, f"context/inbox/{day}.jsonl", day_records,
                                               allowed_removed=consumed, remove_empty=True)
                        # Concurrent consumption must keep its cleanup notification pending.
                        with self.store._database(write=True, dispatch=False) as db:
                            db.executemany("UPDATE feedback_deliveries SET delivered=1,error=NULL WHERE recipient=? AND event_id=? "
                                           "AND EXISTS (SELECT 1 FROM feedback_events e WHERE e.event_id=feedback_deliveries.event_id "
                                           "AND e.consumed_at IS ?)",
                                           [(recipient, json.loads(row[0])["event_id"], row[1]) for row in rows])
                    except (ResearchError, OSError, ValueError, TypeError, KeyError):
                        with self.store._database(write=True, dispatch=False) as db:
                            db.execute("UPDATE feedback_deliveries SET error=? WHERE recipient=? AND delivered=0",
                                       ("Context projection is unavailable, unsafe or externally edited; retained for retry.", recipient))
                self._flush_queue()
                self._preferences_file()
        return self.status()

    def deliveries(self, *, producer_id=None, event_id=None):
        if producer_id is not None:
            from scholar_workflow.research.recommendations.project_tasks import identifier
            identifier(producer_id)
        with self.store._database() as db:
            rows = db.execute("SELECT q.record FROM feedback_queue_receipts q JOIN feedback_events e "
                              "ON e.event_id=q.event_id ORDER BY e.sequence,q.producer_id").fetchall()
        items = [json.loads(row[0]) for row in rows]
        return {"schema_version": 1, "pool_id": pool_id(self.store), "items": [
            item for item in items if (producer_id is None or item["producer_id"] == producer_id)
            and (event_id is None or item["event_id"] == event_id)]}

    @staticmethod
    def _save_delivery(db, delivery):
        db.execute("UPDATE feedback_queue_receipts SET record=? WHERE event_id=? AND producer_id=?",
                   (_json(delivery), delivery["event_id"], delivery["producer_id"]))
        db.execute("UPDATE feedback_deliveries SET delivered=?,error=? WHERE event_id=? AND recipient=?",
                   (int(delivery["status"] in {"queued", "completed"}), delivery.get("error"),
                    delivery["event_id"], "task:" + delivery["producer_id"]))

    def _flush_queue(self):
        # Legacy projections are retired without reading, modifying or deleting project files.
        with self.store._database(write=True, dispatch=False) as db:
            db.execute("UPDATE feedback_deliveries SET delivered=1,error=? WHERE recipient LIKE 'task:%' "
                       "AND NOT EXISTS (SELECT 1 FROM feedback_queue_receipts q WHERE q.event_id=feedback_deliveries.event_id "
                       "AND 'task:'||q.producer_id=feedback_deliveries.recipient)",
                       ("Legacy project feedback projection retired; explicit schema-2 binding required.",))
        for delivery in self.deliveries()["items"]:
            if delivery["status"] != "pending":
                continue
            route = delivery["route"]
            try:
                queue.validate_route(route, pool_id(self.store))
                if route["profile"] != self.store.profile:
                    raise ResearchError("Feedback route belongs to another active profile.", 5)
                with self.store._database() as db:
                    row = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (delivery["producer_id"],)).fetchone()
                    event_row = db.execute("SELECT record FROM feedback_events WHERE event_id=?", (delivery["event_id"],)).fetchone()
                if row is None or not queue.same_route(route, json.loads(row[0])):
                    raise ResearchError("Feedback task binding changed; its original route is retained for explicit review.", 5)
                from scholar_workflow.research.recommendations.project_tasks import ProjectTasks
                guide = ProjectTasks(self.store, profile=route["profile"]).guide(route["producer_id"], include_context=True)
                if not queue.same_route(route, guide["task"]):
                    raise ResearchError("Feedback task binding changed during delivery preparation.", 5)
                message = queue.message_for(json.loads(event_row[0]), route, state_dir=self.store.state_dir)
                if self.runner is None and not queue.pool_locator(self.store.state_dir, route["profile"])["cli_addressable"]:
                    raise ResearchError("Native feedback requires a CLI-addressable HOME/recommendations/profile pool.")
                if self.runner is None and (not self.native_enabled or route["profile"] != "personal"):
                    raise ResearchError("Native queue delivery is disabled for this pool/profile; retained pending.")
            except (ResearchError, OSError, ValueError, TypeError, KeyError) as error:
                delivery.update(error=str(error), updated_at=_now())
                with self.store._database(write=True, dispatch=False) as db:
                    self._save_delivery(db, delivery)
                continue
            # Persist an ambiguous acceptance BEFORE starting a process. A crash cannot
            # turn into an automatic duplicate. No database lock spans the runner call.
            delivery.update(status="uncertain", attempts=delivery["attempts"] + 1,
                            error="Native queue attempt started; acceptance is not yet known.", updated_at=_now())
            with self.store._database(write=True, dispatch=False) as db:
                self._save_delivery(db, delivery)
            result = queue.enqueue(route, message, self.runner or queue.native_runner)
            with self.store._database(write=True, dispatch=False) as db:
                row = db.execute("SELECT record FROM feedback_queue_receipts WHERE event_id=? AND producer_id=?",
                                 (delivery["event_id"], delivery["producer_id"])).fetchone()
                current = json.loads(row[0])
                if current["status"] == "completed":
                    continue
                if current.get("started_at") and result["status"] == "pending":
                    result.update(status="uncertain", error=(result.get("error") or "")
                                  + " The agent already acknowledged receipt; automatic retry is disabled.")
                current.update(result, updated_at=_now())
                if result["status"] == "queued":
                    current["queued_at"] = _now()
                self._save_delivery(db, current)

    def _check_current_route(self, db, delivery):
        route = delivery["route"]
        queue.validate_route(route, pool_id(self.store))
        if route["profile"] != self.store.profile:
            raise ResearchError("Feedback route belongs to another active profile.", 5)
        row = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (delivery["producer_id"],)).fetchone()
        if row is None or not queue.same_route(route, json.loads(row[0])):
            raise ResearchError("Feedback task binding changed; its original route requires explicit review.", 5)

    def start(self, event_id, producer_id):
        """Record explicit agent acceptance separately from queueing and completion."""
        from scholar_workflow.research.recommendations.project_tasks import identifier

        identifier(producer_id)
        if not isinstance(event_id, str) or not event_id:
            raise ResearchError("Start requires its originating feedback event ID.")
        with self.store._database(write=True, dispatch=False) as db:
            row = db.execute("SELECT record FROM feedback_queue_receipts WHERE event_id=? AND producer_id=?",
                             (event_id, producer_id)).fetchone()
            if row is None:
                raise ResearchError("No feedback delivery exists for this event and producer in this pool.")
            delivery = json.loads(row[0])
            self._check_current_route(db, delivery)
            if delivery["status"] not in {"queued", "uncertain"}:
                raise ResearchError("Only queued or uncertain feedback can be started.", 5)
            if not delivery.get("started_at"):
                delivery.update(started_at=_now(), updated_at=_now())
                self._save_delivery(db, delivery)
        return delivery

    def retry(self, event_id, producer_id, expected_attempts, confirmed_not_queued):
        """Restore an explicitly reviewed uncertain attempt without dispatching it."""
        from scholar_workflow.research.recommendations.project_tasks import identifier

        identifier(producer_id)
        if not isinstance(event_id, str) or not event_id:
            raise ResearchError("Retry requires its originating feedback event ID.")
        if confirmed_not_queued is not True:
            raise ResearchError("Retry requires explicit confirmation that this feedback was not queued.")
        if type(expected_attempts) is not int or expected_attempts < 1:
            raise ResearchError("Retry requires the exact positive attempt count.")
        with root_directory(self.store.state_dir) as root_fd:
            # Share the queue lock so an in-flight process cannot be reset to pending.
            with storage_lock(root_fd, name=".feedback-delivery.lock"):
                with self.store._database(write=True, dispatch=False) as db:
                    row = db.execute("SELECT record FROM feedback_queue_receipts WHERE event_id=? AND producer_id=?",
                                     (event_id, producer_id)).fetchone()
                    if row is None:
                        raise ResearchError("No feedback delivery exists for this event and producer in this pool.")
                    delivery = json.loads(row[0])
                    if delivery["status"] != "uncertain":
                        raise ResearchError("Only uncertain feedback can be restored by an explicit retry review.", 5)
                    if delivery.get("started_at"):
                        raise ResearchError("This feedback already started processing and cannot be reviewed as not queued.", 5)
                    if delivery["attempts"] != expected_attempts:
                        raise ResearchError("Feedback attempt count changed; reread before reviewing a retry.", 5)
                    self._check_current_route(db, delivery)
                    review = {"confirmed_not_queued": True, "reviewed_at": _now(), "previous": {
                        key: delivery.get(key) for key in ("status", "attempts", "error", "updated_at", "queue_message_id")}}
                    delivery.setdefault("retry_reviews", []).append(review)
                    delivery.update(status="pending", error=None, updated_at=_now())
                    self._save_delivery(db, delivery)
        return delivery

    def complete(self, event_id, producer_id, context_digest, summary):
        """Record the task's context receipt without consuming central curator feedback."""
        from scholar_workflow.research.recommendations.project_tasks import ProjectTasks, identifier
        from scholar_workflow.research.recommendations.store import _safe_text, _nonsecret_management

        identifier(producer_id)
        if not isinstance(event_id, str) or not event_id:
            raise ResearchError("Completion requires its originating feedback event ID.")
        if not isinstance(context_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", context_digest):
            raise ResearchError("Completion requires the current context SHA-256 digest.")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 4000:
            raise ResearchError("Completion summary must contain 1-4000 characters.")
        _safe_text(summary, multiline=True)
        _nonsecret_management(summary)
        payload = {"context_digest": context_digest, "summary": summary}
        items = self.deliveries(producer_id=producer_id, event_id=event_id)["items"]
        if not items:
            raise ResearchError("No feedback delivery exists for this event and producer in this pool.")
        delivery = items[0]
        if delivery["status"] == "completed":
            if delivery["completion"] != payload:
                raise ResearchError("Feedback was already completed with a different receipt.", 5)
            return delivery
        if delivery["status"] not in {"queued", "uncertain"}:
            raise ResearchError("Only queued or uncertain feedback can be completed.", 5)
        route = delivery["route"]
        queue.validate_route(route, pool_id(self.store))
        if route["profile"] != self.store.profile:
            raise ResearchError("Feedback route belongs to another active profile.", 5)
        guide = ProjectTasks(self.store, profile=route["profile"]).guide(producer_id, include_context=True)
        if not queue.same_route(route, guide["task"]):
            raise ResearchError("Feedback task binding changed; completion needs explicit review.", 5)
        if guide["context_revision"] != context_digest:
            raise ResearchError("Task context changed; reread its current digest before completing feedback.", 5)
        with self.store._database(write=True, dispatch=False) as db:
            current = json.loads(db.execute("SELECT record FROM feedback_queue_receipts WHERE event_id=? AND producer_id=?",
                                           (event_id, producer_id)).fetchone()[0])
            if current["status"] == "completed":
                if current["completion"] != payload:
                    raise ResearchError("Feedback was already completed with a different receipt.", 5)
                return current
            row = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (producer_id,)).fetchone()
            if row is None or not queue.same_route(route, json.loads(row[0])):
                raise ResearchError("Feedback task binding changed during completion.", 5)
            if current["status"] not in {"queued", "uncertain"}:
                raise ResearchError("Only queued or uncertain feedback can be completed.", 5)
            current.update(status="completed", completion=payload, completed_at=_now(), updated_at=_now(), error=None)
            self._save_delivery(db, current)
        return current

    def _preferences_file(self):
        from scholar_workflow.research.recommendations.ranking import RecommendationRanking
        with self.store._database() as db:
            current = RecommendationRanking._context(db)
            historical = [json.loads(row[0])["content"] for row in db.execute("SELECT record FROM recommendation_context")]
        if not current["revision"]:
            return
        relative = "context/PREFERENCES.md"
        try:
            old = disk.read_context(self.store.state_dir, relative)
        except (FileNotFoundError, ResearchError):
            with disk.directory(self.store.state_dir, "context", create=True):
                pass
            old = disk.read_context(self.store.state_dir, relative)
        if old is not None:
            try:
                if old.decode() not in historical:
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise ResearchError("Preference projection contains external edits; import them explicitly before rebuilding.", 5) from None
        if old != current["content"].encode():
            disk.replace_file(self.store.state_dir, relative, current["content"].encode(), expected=disk.digest(old))

    def batch(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ResearchError("A curator batch is limited to 1-1000 events.")
        from scholar_workflow.research.recommendations.ranking import RecommendationRanking
        with self.store._database(write=True) as db:
            rows = db.execute("SELECT e.record FROM feedback_events e WHERE consumed_at IS NULL AND event_id IN "
                              "(SELECT event_id FROM feedback_deliveries WHERE recipient='curator') ORDER BY sequence LIMIT ?", (limit,)).fetchall()
            records = [json.loads(row[0]) for row in rows]
            record = {"schema_version": 1, "pool_id": pool_id(self.store), "batch_id": "batch-" + str(uuid.uuid4()),
                      "event_ids": [row["event_id"] for row in records], "items": records,
                      "context": RecommendationRanking._context(db), "status": "pending"}
            db.execute("INSERT INTO feedback_batches VALUES(?,?)", (record["batch_id"], _json(record)))
        return record

    def consume(self, batch_id, content, expected_revision, updated_by):
        """Save preferences and acknowledge exactly this batch in one database transaction."""
        from scholar_workflow.research.recommendations.ranking import RecommendationRanking, _actor, _revision
        from scholar_workflow.research.recommendations.store import _nonsecret_management, _safe_text
        _revision(expected_revision)
        _actor(updated_by)
        if not isinstance(content, str) or len(content) > 16000:
            raise ResearchError("Shared recommendation preferences are limited to 16000 characters.")
        if content:
            _safe_text(content, multiline=True)
        _nonsecret_management([content, updated_by])
        payload_hash = _digest({"content": content, "expected_revision": expected_revision, "updated_by": updated_by})
        with self.store._database(write=True) as db:
            row = db.execute("SELECT record FROM feedback_batches WHERE batch_id=?", (batch_id,)).fetchone()
            if row is None:
                raise ResearchError("Curator batch does not exist in this pool.")
            batch = json.loads(row[0])
            if batch["status"] == "consumed":
                if batch["payload_hash"] != payload_hash:
                    raise ResearchError("This curator batch was already consumed with different content.", 5)
                return batch
            current = RecommendationRanking._context(db)
            if current["revision"] != expected_revision:
                raise ResearchError("Preferences changed; reread before consuming feedback.", 5)
            for event_id in batch["event_ids"]:
                if db.execute("SELECT consumed_at FROM feedback_events WHERE event_id=?", (event_id,)).fetchone()[0] is not None:
                    raise ResearchError("This batch overlaps already-consumed feedback; request a fresh batch.", 5)
            context = {"content": content, "revision": expected_revision + 1, "updated_by": updated_by, "updated_at": _now()}
            db.execute("INSERT INTO recommendation_context VALUES(?,?)", (context["revision"], _json(context)))
            batch.update(status="consumed", context=context, payload_hash=payload_hash, consumed_at=_now())
            for event_id in batch["event_ids"]:
                db.execute("UPDATE feedback_events SET consumed_at=? WHERE event_id=?", (batch["consumed_at"], event_id))
                db.execute("UPDATE feedback_deliveries SET delivered=0 WHERE event_id=? AND recipient='curator'", (event_id,))
            db.execute("UPDATE feedback_batches SET record=? WHERE batch_id=?", (_json(batch), batch_id))
        return batch
