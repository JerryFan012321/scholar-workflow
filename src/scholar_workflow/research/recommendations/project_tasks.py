"""Central task routing with only context.md and recommended.md in each project."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import context_files as disk
from scholar_workflow.research.store import root_directory, root_path

BASE = ".agents/context/recommendations"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
DDL = """
CREATE TABLE IF NOT EXISTS recommendation_tasks(producer_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, record TEXT NOT NULL);
"""


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value in {".", ".."}:
        raise ResearchError("A recommendation task needs a safe stable producer ID.")
    return value


def pool_id(store):
    return "pool-" + hashlib.sha256(str(store.state_dir).encode()).hexdigest()[:32]


class ProjectTasks:
    def __init__(self, store, profile="personal"):
        if profile not in {"personal", "test"}:
            raise ResearchError("Unknown recommendation profile.")
        self.store, self.profile = store, profile

    def bind(self, project_root, producer_id, title, thread_id, *, host="local", expected_revision=0):
        """Explicit binding can update a route using the saved central revision."""
        with self.store._database(write=True) as db:
            return self.bind_in_transaction(db, project_root, producer_id, title, thread_id,
                                            host=host, expected_revision=expected_revision)

    def bind_in_transaction(self, db, project_root, producer_id, title, thread_id, *,
                            host="local", expected_revision=None):
        from scholar_workflow.research.recommendations.store import _json, _nonsecret_management, _safe_text

        producer_id = identifier(producer_id)
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
            raise ResearchError("Task binding requires a non-negative integer revision.")
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise ResearchError("Task title must contain 1-300 characters.")
        _safe_text(title)
        _nonsecret_management(title)
        if not isinstance(project_root, (str, Path)) or not Path(project_root).is_absolute():
            raise ResearchError("Feedback project_root must be an absolute local directory.")
        root = root_path(project_root)
        if host != "local":
            raise ResearchError("Feedback routing currently supports only the local Codex host.")
        try:
            if not isinstance(thread_id, str) or str(uuid.UUID(thread_id)) != thread_id:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ResearchError("Feedback routing requires a canonical Codex thread UUID.") from None
        with root_directory(root):
            pass
        old_row = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (producer_id,)).fetchone()
        old = json.loads(old_row[0]) if old_row else None
        if old and old.get("schema_version") != 2:
            raise ResearchError("This legacy task needs an explicit reviewed migration; old project files were preserved.", 5)
        route = {"project_root": str(root), "thread_id": thread_id, "host": host}
        if old and old["project_root"] != str(root):
            raise ResearchError("A producer ID is already bound to another project; use a distinct task identity.", 5)
        if old and (old["pool_id"] != pool_id(self.store) or old["profile"] != self.profile):
            raise ResearchError("Task belongs to another pool/profile.", 5)
        same = old is not None and all(old.get(k) == v for k, v in route.items()) and old["title"] == title
        if expected_revision is None:
            if old and not same:
                raise ResearchError("Task route changed; explicitly bind it using its current revision.", 5)
        elif type(expected_revision) is not int or expected_revision != (old["revision"] if old else 0):
            if not (same and expected_revision == 0):
                raise ResearchError("Task binding changed; use its current revision.", 5)
        folder = f"{BASE}/{producer_id}"
        context_file, recommended_file = f"{folder}/context.md", f"{folder}/recommended.md"
        # The caller holds the central writer lock. Do not place lock/checkpoint
        # files beside the two human-maintained Markdown documents.
        disk.replace_file(root, context_file,
                          (f"# {title}\n\nMaintain this task's purpose, requirements and learned preferences here.\n").encode(),
                          create_only=True, lock=False)
        disk.replace_file(root, recommended_file,
                          (f"# {title}: recommended resources\n\nRecord each actual recommendation with its date, title and original link.\n").encode(),
                          create_only=True, lock=False)
        if same:
            return old
        project_id = "local-" + hashlib.sha256(str(root).encode()).hexdigest()[:32]
        record = {"schema_version": 2, "producer_id": producer_id, "title": title,
                  "project_id": project_id, "project_title": root.name, **route,
                  "context_file": context_file, "recommended_file": recommended_file,
                  "profile": self.profile, "pool_id": pool_id(self.store),
                  "revision": old["revision"] + 1 if old else 1}
        db.execute("INSERT INTO recommendation_tasks VALUES(?,?,?) ON CONFLICT(producer_id) DO UPDATE SET record=excluded.record",
                   (producer_id, project_id, _json(record)))
        if old is None:
            from scholar_workflow.research.recommendations.feedback import record_baseline
            record_baseline(self.store, db, producer_id)
        return record

    def list(self, project_id=None):
        with self.store._database() as db:
            rows = db.execute("SELECT record FROM recommendation_tasks ORDER BY producer_id").fetchall()
        return {"schema_version": 1, "pool_id": pool_id(self.store), "tasks": [
            json.loads(row[0]) for row in rows if project_id is None or json.loads(row[0])["project_id"] == project_id]}

    def guide(self, producer_id, *, include_context=False):
        identifier(producer_id)
        task = next((row for row in self.list()["tasks"] if row["producer_id"] == producer_id), None)
        if task is None:
            raise ResearchError("Recommendation task is not bound.")
        if task.get("schema_version") != 2:
            raise ResearchError("Legacy task routing is inactive; preserve and review its old files before migration.", 5)
        if task["profile"] != self.profile or task["pool_id"] != pool_id(self.store):
            raise ResearchError("Task belongs to another pool/profile.", 5)
        result = {"task": task, "project_root": task["project_root"]}
        if include_context:
            for key, filename in (("context", "context_file"), ("recommended", "recommended_file")):
                content = disk.read_context(task["project_root"], task[filename])
                if content is None:
                    raise ResearchError("A task Markdown file is missing; restore it explicitly before continuing.", 5)
                try:
                    result[key] = content.decode("utf-8")
                except UnicodeError:
                    raise ResearchError("Task Markdown must be UTF-8.") from None
                result[key + "_revision"] = disk.digest(content)
        return result
