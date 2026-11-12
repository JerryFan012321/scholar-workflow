"""Explicit project-owned recommendation tasks, independent of agent sessions."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scholar_workflow.project.layout import ProjectLayoutError, validate_project_identity
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import context_files as disk

BASE = ".agents/context/recommendations"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
DDL = """
CREATE TABLE IF NOT EXISTS recommendation_projects(project_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recommendation_tasks(producer_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, record TEXT NOT NULL);
"""


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value in {".", ".."}:
        raise ResearchError("A recommendation task needs a safe stable producer ID.")
    return value


def pool_id(store):
    return "pool-" + hashlib.sha256(str(store.state_dir).encode()).hexdigest()[:32]


def project_identity(root):
    try:
        raw = disk.read_context(root, "project-layout.json")
        return validate_project_identity(json.loads(raw or b"null"))
    except (ValueError, TypeError, UnicodeError, ProjectLayoutError):
        raise ResearchError("The selected project needs its existing schema-2 project_id; initialize it first.") from None


class ProjectTasks:
    def __init__(self, store, profile="personal"):
        if profile not in {"personal", "test"}:
            raise ResearchError("Unknown recommendation profile.")
        self.store, self.profile = store, profile

    def enable(self, project_root):
        from scholar_workflow.research.store import root_path
        from scholar_workflow.research.recommendations.store import _json

        root = root_path(project_root)
        project_id = project_identity(root)
        with self.store._database() as db:
            existing = db.execute("SELECT record FROM recommendation_projects WHERE project_id=?", (project_id,)).fetchone()
            if existing and json.loads(existing[0])["root"] != str(root):
                raise ResearchError("This project ID is already registered at another root; resolve it explicitly.", 5)
        if disk.read_context(root, "AGENTS.md") is None:
            if any(disk.read_context(root, name) is not None for name in ("AGENT.md", "CLAUDE.md")):
                raise ResearchError("Resolve the existing instruction topology before adding a new canonical AGENTS entry.", 5)
        component = {"schema_version": 1, "project_id": project_id,
                     "pool_id": pool_id(self.store), "profile": self.profile}
        actual = disk.replace_file(root, f"{BASE}/component.json", disk.json_bytes(component), create_only=True)
        if actual != disk.json_bytes(component):
            raise ResearchError("This project context belongs to another pool/profile; use a separate test project.", 5)
        entry = ("# Project recommendation tasks\n\n"
                 "Use the installed recommend-papers Skill for task registration, feedback and submission.\n"
                 "Each directory under tasks/ is one recurring task, not an agent identity.\n"
                 "Read only the selected task's CONTEXT.md and feedback.jsonl. Keep project background here.\n"
                 "List registered tasks with `scholar-research recommendations --profile " + self.profile
                 + " tasks list --project-id " + project_id + "`.\n"
                 "Feedback is delivered by code. After incorporating it, save task context with its exact revision.\n")
        disk.replace_file(root, f"{BASE}/CONTEXT.md", entry.encode(), create_only=True)
        link = f"[Project recommendation tasks]({BASE}/CONTEXT.md)"
        original = disk.read_context(root, "AGENTS.md")
        if original is None or link.encode() not in original:
            revised = (original or b"").rstrip() + (
                "\n\n## Recommendation tasks\n\nFor project recommendations and feedback, read " + link + ".\n"
            ).encode()
            disk.replace_file(root, "AGENTS.md", revised, expected=disk.digest(original))
        with self.store._database(write=True) as db:
            prior = db.execute("SELECT record FROM recommendation_projects WHERE project_id=?", (project_id,)).fetchone()
            revision = json.loads(prior[0])["revision"] if prior else 0
            if prior and json.loads(prior[0])["root"] != str(root):
                raise ResearchError("This project ID is already registered at another root; resolve it explicitly.", 5)
            record = {**component, "root": str(root), "revision": revision or 1,
                      "entry": f"{BASE}/CONTEXT.md", "name": root.name}
            db.execute("INSERT INTO recommendation_projects VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET record=excluded.record",
                       (project_id, _json(record)))
        return record

    def project(self, project_id):
        with self.store._database() as db:
            row = db.execute("SELECT record FROM recommendation_projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise ResearchError("Project recommendation context is not registered.")
        record = json.loads(row[0])
        if record["profile"] != self.profile or record["pool_id"] != pool_id(self.store):
            raise ResearchError("Project context belongs to another pool/profile.", 5)
        return record

    def register(self, project_id, producer_id, title, *, expected_revision=0):
        from scholar_workflow.research.recommendations.store import _json, _nonsecret_management, _safe_text
        from scholar_workflow.research.recommendations.feedback import record_baseline

        producer_id = identifier(producer_id)
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise ResearchError("Task title must contain 1-300 characters.")
        _safe_text(title)
        _nonsecret_management(title)
        project = self.project(project_id)
        if project_identity(project["root"]) != project_id:
            raise ResearchError("The registered project identity changed.", 5)
        relative = f"{BASE}/tasks/{producer_id}"
        with self.store._database(write=True) as db:
            old = db.execute("SELECT record FROM recommendation_tasks WHERE producer_id=?", (producer_id,)).fetchone()
            prior = json.loads(old[0]) if old else None
            if type(expected_revision) is not int or expected_revision != (prior["revision"] if prior else 0):
                raise ResearchError("Task registration changed; use its current revision.", 5)
            if prior and prior["project_id"] != project_id:
                raise ResearchError("A producer ID already belongs to another project.", 5)
            record = {"schema_version": 1, "project_id": project_id, "producer_id": producer_id,
                      "title": title, "project_title": project["name"], "revision": expected_revision + 1,
                      "context_file": f"{relative}/CONTEXT.md", "feedback_file": f"{relative}/feedback.jsonl",
                      "checkpoint_file": f"{relative}/state.json", "profile": self.profile,
                      "pool_id": pool_id(self.store)}
            disk.replace_file(project["root"], record["context_file"], (
                f"# {title}\n\nDescribe this task's project-specific purpose and requirements here.\n"
                "Read feedback.jsonl before continuing. Record scientific judgments here; keep human feedback unchanged.\n"
            ).encode(), create_only=True)
            disk.replace_file(project["root"], record["checkpoint_file"], disk.json_bytes({
                "schema_version": 1, "revision": 0, "consumed_event_ids": [],
                "project_id": project_id, "producer_id": producer_id, "pool_id": pool_id(self.store),
            }), create_only=True)
            db.execute("INSERT INTO recommendation_tasks VALUES(?,?,?) ON CONFLICT(producer_id) DO UPDATE SET record=excluded.record",
                       (producer_id, project_id, _json(record)))
            if not prior:
                record_baseline(self.store, db, producer_id)
        return record

    def list(self, project_id=None):
        with self.store._database() as db:
            rows = db.execute("SELECT record FROM recommendation_tasks ORDER BY producer_id").fetchall()
        return {"schema_version": 1, "pool_id": pool_id(self.store), "tasks": [
            json.loads(row[0]) for row in rows if project_id is None or json.loads(row[0])["project_id"] == project_id]}

    def guide(self, producer_id, *, include_context=False):
        identifier(producer_id)
        tasks = self.list()["tasks"]
        task = next((row for row in tasks if row["producer_id"] == producer_id), None)
        if task is None:
            raise ResearchError("Recommendation task is not registered.")
        project = self.project(task["project_id"])
        if project_identity(project["root"]) != task["project_id"]:
            raise ResearchError("The registered project identity changed.", 5)
        result = {"task": task, "project_root": project["root"], "project_entry": project["entry"]}
        if include_context:
            context = disk.read_context(project["root"], task["context_file"])
            try:
                checkpoint = json.loads(disk.read_context(project["root"], task["checkpoint_file"]) or b"null")
                if (not isinstance(checkpoint, dict) or checkpoint.get("project_id") != task["project_id"]
                        or checkpoint.get("producer_id") != producer_id or checkpoint.get("pool_id") != pool_id(self.store)
                        or checkpoint.get("schema_version") != 1
                        or type(checkpoint.get("revision")) is not int or checkpoint["revision"] < 0
                        or not isinstance(checkpoint.get("consumed_event_ids"), list)
                        or any(not isinstance(i, str) for i in checkpoint["consumed_event_ids"])):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                raise ResearchError("Task checkpoint is invalid or belongs to another project/task/pool.", 5) from None
            result.update(context=(context or b"").decode(), context_revision=disk.digest(context), checkpoint=checkpoint)
        return result

    def save_context(self, producer_id, content, expected_revision, consumed_event_ids):
        from scholar_workflow.research.store import storage_lock
        guide = self.guide(producer_id)
        with disk.directory(guide["project_root"], str(Path(guide["task"]["context_file"]).parent)) as fd:
            with storage_lock(fd, name=".task-update.lock"):
                return self._save_context_locked(producer_id, content, expected_revision, consumed_event_ids)

    def _save_context_locked(self, producer_id, content, expected_revision, consumed_event_ids):
        """Commit interpretation first; advance the separate consumption checkpoint only afterward."""
        from scholar_workflow.research.recommendations.store import _nonsecret_management
        if not isinstance(content, str) or len(content.encode()) > 128 * 1024:
            raise ResearchError("Task context must be UTF-8 text within 128 KiB.")
        _nonsecret_management(content)
        current = self.guide(producer_id, include_context=True)
        if expected_revision != current["context_revision"]:
            raise ResearchError("Task context changed; reread it before saving.", 5)
        if not isinstance(consumed_event_ids, list) or len(consumed_event_ids) > 1000 or any(not isinstance(i, str) for i in consumed_event_ids):
            raise ResearchError("Consumed feedback must be an explicit bounded event-ID list.")
        with self.store._database() as db:
            known = {row[0] for row in db.execute("SELECT event_id FROM feedback_deliveries WHERE recipient=?", ("task:" + producer_id,))}
        if not set(consumed_event_ids) <= known:
            raise ResearchError("Cannot consume another task's feedback.", 7)
        task, root = current["task"], current["project_root"]
        disk.replace_file(root, task["context_file"], content.encode(), expected=expected_revision)
        before = disk.read_context(root, task["checkpoint_file"])
        checkpoint = json.loads(before)
        checkpoint["revision"] += 1
        checkpoint["context_revision"] = disk.digest(content.encode())
        checkpoint["consumed_event_ids"] = sorted(set(checkpoint["consumed_event_ids"]) | set(consumed_event_ids))
        disk.replace_file(root, task["checkpoint_file"], disk.json_bytes(checkpoint), expected=disk.digest(before))
        return {"producer_id": producer_id, "context_revision": checkpoint["context_revision"], "checkpoint": checkpoint}
