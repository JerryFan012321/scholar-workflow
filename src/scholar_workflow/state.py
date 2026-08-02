"""Persistent job state machine backed by SQLite."""
from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from scholar_workflow.models import TaskState


DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    plan_id TEXT,
    resource_id TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    artifacts TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_jobs_resource ON jobs (resource_id);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs (state);
"""


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(DDL)
        self._db.commit()

    def upsert(self, job_id: str, resource_id: str, state: TaskState,
               plan_id: str | None = None, artifacts: dict | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """INSERT INTO jobs (job_id, plan_id, resource_id, state, created_at, updated_at, artifacts)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET
                 state=excluded.state, updated_at=excluded.updated_at,
                 artifacts=excluded.artifacts""",
            (job_id, plan_id, resource_id, state.value, now, now,
             json.dumps(artifacts or {})),
        )
        self._db.commit()

    def get(self, job_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._db.execute("SELECT * FROM jobs LIMIT 0").description]
        return dict(zip(cols, row))

    def active_jobs(self) -> list[dict]:
        rows = self._db.execute("SELECT * FROM jobs").fetchall()
        cols = [d[0] for d in self._db.execute("SELECT * FROM jobs LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        self._db.close()
