"""Persistent job state machine backed by SQLite."""
from __future__ import annotations
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from scholar_workflow.models import TaskState


DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    plan_id TEXT,
    resource_id TEXT NOT NULL,
    state TEXT NOT NULL,
    input_digest TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    artifacts TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_jobs_resource ON jobs (resource_id);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs (state);

CREATE TABLE IF NOT EXISTS resources (
    resource_id     TEXT PRIMARY KEY,
    doi             TEXT,
    arxiv           TEXT,
    title_norm      TEXT,
    first_author    TEXT,
    year            INTEGER,
    zotero_item_key TEXT,
    status          TEXT,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_res_doi ON resources (doi);
CREATE INDEX IF NOT EXISTS idx_res_arxiv ON resources (arxiv);
CREATE INDEX IF NOT EXISTS idx_res_title ON resources (title_norm);
"""


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(DDL)
        self._db.commit()

    def upsert(self, job_id: str, resource_id: str, state: TaskState,
               plan_id: str | None = None, artifacts: dict | None = None) -> None:
        now = datetime.utcnow().isoformat()
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
        terminal = (TaskState.COMPLETED.value, TaskState.POLICY_DENIED.value)
        rows = self._db.execute(
            f"SELECT * FROM jobs WHERE state NOT IN ({','.join('?'*len(terminal))})",
            terminal
        ).fetchall()
        cols = [d[0] for d in self._db.execute("SELECT * FROM jobs LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    # --- resources identity cache (exact-match authority + fuzzy recall surface) ---

    def upsert_resource(self, resource_id: str, *, doi: str | None = None,
                        arxiv: str | None = None, title_norm: str | None = None,
                        first_author: str | None = None, year: int | None = None,
                        zotero_item_key: str | None = None,
                        status: str | None = None) -> None:
        now = datetime.utcnow().isoformat()
        self._db.execute(
            """INSERT INTO resources
                 (resource_id, doi, arxiv, title_norm, first_author, year,
                  zotero_item_key, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(resource_id) DO UPDATE SET
                 doi=excluded.doi, arxiv=excluded.arxiv,
                 title_norm=excluded.title_norm, first_author=excluded.first_author,
                 year=excluded.year, zotero_item_key=excluded.zotero_item_key,
                 status=excluded.status, updated_at=excluded.updated_at""",
            (resource_id, doi, arxiv, title_norm, first_author, year,
             zotero_item_key, status, now),
        )
        self._db.commit()

    def _rows(self, sql: str, params: tuple) -> list[dict]:
        cur = self._db.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def find_exact(self, *, resource_id: str | None = None, doi: str | None = None,
                   arxiv: str | None = None) -> dict | None:
        """Exact identity lookup by resource_id / DOI / arXiv base id (deterministic)."""
        for col, val in (("resource_id", resource_id), ("doi", doi), ("arxiv", arxiv)):
            if val:
                rows = self._rows(f"SELECT * FROM resources WHERE {col}=?", (val,))
                if rows:
                    return rows[0]
        return None

    def find_candidates(self, title_norm: str, *, year: int | None = None,
                        limit: int = 5) -> list[dict]:
        """Cheap fuzzy prefilter for LLM recall — never decides, just narrows."""
        tokens = [t for t in title_norm.split() if len(t) > 3][:6]
        if not tokens:
            return []
        where = " OR ".join("title_norm LIKE ?" for _ in tokens)
        params = tuple(f"%{t}%" for t in tokens)
        if year is not None:
            where = f"({where}) AND (year IS NULL OR ABS(year - ?) <= 1)"
            params = params + (year,)
        return self._rows(
            f"SELECT * FROM resources WHERE {where} LIMIT ?", params + (limit,))

    def close(self) -> None:
        self._db.close()
