"""Transactional human feedback and automatic, recoverable file projections."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import context_files as disk
from scholar_workflow.research.recommendations.project_tasks import pool_id, project_identity
from scholar_workflow.research.recommendations.store import _digest, _json, _now
from scholar_workflow.research.store import root_directory, storage_lock

DDL = """
CREATE TABLE IF NOT EXISTS feedback_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
 candidate_id TEXT NOT NULL, record TEXT NOT NULL, consumed_at TEXT);
CREATE TABLE IF NOT EXISTS feedback_deliveries(
 event_id TEXT NOT NULL, recipient TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
 error TEXT, PRIMARY KEY(event_id,recipient));
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
    tasks = []
    for task_id in recipients:
        row = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (task_id,)).fetchone()
        task = json.loads(row[0])
        tasks.append({key: task[key] for key in ("project_id", "producer_id", "title")})
    now = _now()
    record = {"schema_version": 1, "pool_id": pool_id(store), "event_id": event_id,
              "kind": kind, "candidate_id": candidate["candidate_id"], "title": resource["title"],
              "url": resource["url"], "tags": candidate["tags"],
              "summary": resource.get("abstract_zh") or resource.get("summary_zh") or resource.get("description_zh") or "",
              "processed_at": None if kind == "baseline" else now, "observed_at": now,
              "decision": candidate["decision"], "disposition": candidate.get("disposition"),
              "evaluation": candidate["evaluation"], "candidate_revision": candidate["revision"],
              "resource_digest": _digest(resource), "tasks": tasks}
    cursor = db.execute("INSERT INTO feedback_events(event_id,candidate_id,record) VALUES(?,?,?)",
                        (event_id, candidate["candidate_id"], _json(record)))
    record["sequence"] = cursor.lastrowid
    db.execute("UPDATE feedback_events SET record=? WHERE event_id=?", (_json(record), event_id))
    for recipient in [*("task:" + task for task in recipients), *(["curator"] if kind != "baseline" else [])]:
        db.execute("INSERT INTO feedback_deliveries(event_id,recipient) VALUES(?,?)", (event_id, recipient))
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
    def __init__(self, store):
        self.store = store

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
        """Immediately deliver committed events; failed destinations remain a durable outbox."""
        with root_directory(self.store.state_dir, create=True) as root_fd:
            with storage_lock(root_fd, name=".feedback-delivery.lock"):
                with self.store._database() as db:
                    pending = db.execute("SELECT DISTINCT recipient FROM feedback_deliveries WHERE delivered=0").fetchall()
                for entry in pending:
                    recipient = entry[0]
                    try:
                        with self.store._database() as db:
                            rows = db.execute("SELECT e.record,e.consumed_at FROM feedback_events e JOIN feedback_deliveries d "
                                              "ON e.event_id=d.event_id WHERE d.recipient=? ORDER BY e.sequence", (recipient,)).fetchall()
                            records = [json.loads(row[0]) for row in rows]
                            task = project = None
                            if recipient.startswith("task:"):
                                task = json.loads(db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (recipient[5:],)).fetchone()[0])
                                project = json.loads(db.execute("SELECT record FROM recommendation_projects WHERE project_id=?", (task["project_id"],)).fetchone()[0])
                        if recipient == "curator":
                            dates = {}
                            consumed = {}
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
                        else:
                            if project_identity(project["root"]) != task["project_id"]:
                                raise ResearchError("Registered project identity changed.", 5)
                            component = json.loads(disk.read_context(project["root"], ".agents/context/recommendations/component.json"))
                            if component["pool_id"] != pool_id(self.store):
                                raise ResearchError("Project feedback target belongs to another pool.", 5)
                            disk.project_jsonl(project["root"], task["feedback_file"], records)
                        # Mark only the snapshot just written. Concurrent arrivals remain pending.
                        with self.store._database(write=True, dispatch=False) as db:
                            db.executemany("UPDATE feedback_deliveries SET delivered=1,error=NULL WHERE recipient=? AND event_id=?",
                                           [(recipient, row["event_id"]) for row in records])
                    except (ResearchError, OSError, ValueError, TypeError, KeyError):
                        with self.store._database(write=True, dispatch=False) as db:
                            db.execute("UPDATE feedback_deliveries SET error=? WHERE recipient=? AND delivered=0",
                                       ("Context projection is unavailable, unsafe or externally edited; retained for retry.", recipient))
                self._preferences_file()
        return self.status()

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
