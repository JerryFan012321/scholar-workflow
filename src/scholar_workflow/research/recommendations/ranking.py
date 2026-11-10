"""Shared context and versioned ordering supplied by an external agent, without inference."""
from __future__ import annotations

import copy
import hashlib
import json
import re

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.store import (
    _digest,
    _json,
    _nonsecret_management,
    _now,
    _safe_text,
)


def _revision(value):
    if type(value) is not int or not 0 <= value < 2**63 - 1:
        raise ResearchError("An exact non-negative revision is required.")


def _actor(value):
    if (not isinstance(value, dict) or set(value) != {"kind", "name"}
            or not isinstance(value["kind"], str) or value["kind"] not in {"human", "agent"}
            or not isinstance(value["name"], str) or not 1 <= len(value["name"]) <= 200):
        raise ResearchError("Context editor needs a human/agent kind and name.")
    _safe_text(value["name"])


class RecommendationRanking:
    """Reuse the selected recommendation pool as the only fact store."""

    def __init__(self, store):
        self.store = store
        self.pool_id = "pool-" + hashlib.sha256(str(store.state_dir).encode()).hexdigest()[:32]

    @staticmethod
    def _context(database):
        row = database.execute("SELECT record FROM recommendation_context ORDER BY revision DESC LIMIT 1").fetchone()
        return json.loads(row["record"]) if row else {
            "content": "", "revision": 0, "updated_at": None, "updated_by": None}

    @staticmethod
    def _latest(database):
        row = database.execute("SELECT record FROM recommendation_rankings ORDER BY revision DESC LIMIT 1").fetchone()
        return json.loads(row["record"]) if row else {"revision": 0, "items": []}

    def _inputs(self, database, candidates=None):
        if candidates is None:
            candidates = [self.store._candidate(database, row)
                          for row in database.execute("SELECT * FROM candidates ORDER BY candidate_id")]
        else:
            candidates = copy.deepcopy(candidates)
        for candidate in candidates:
            history = [json.loads(row["record"]) for row in database.execute(
                "SELECT record FROM candidate_evaluation_history WHERE candidate_id=? ORDER BY revision",
                (candidate["candidate_id"],))]
            known = database.execute("SELECT record FROM candidate_evaluations WHERE candidate_id=?",
                                     (candidate["candidate_id"],)).fetchone()
            if known is not None and not any(r["revision"] == candidate["evaluation"]["revision"] for r in history):
                history.append(json.loads(known["record"]))
            candidate["evaluation_history"] = history
        requirements = [json.loads(row["record"]) for row in database.execute(
            "SELECT record FROM recommendation_requirements ORDER BY requirement_id,revision")]
        sources = [json.loads(row["record"]) for row in database.execute(
            "SELECT record FROM source_context ORDER BY source_id")]
        return {"schema_version": 1, "pool_id": self.pool_id, "context": self._context(database),
                "candidates": sorted(candidates, key=lambda row: row["candidate_id"]),
                "requirements": requirements, "source_contexts": sources}

    def _summary(self, database, candidates=None):
        inputs = self._inputs(database, candidates)
        digest = _digest(inputs)
        latest = self._latest(database)
        status = "empty" if not latest["revision"] else (
            "current" if latest["context_digest"] == digest else "stale")
        return {"context": inputs["context"], "candidate_count": len(inputs["candidates"]),
                "ranking": {**latest, "status": status}, "context_digest": digest}

    def context(self):
        with self.store._database() as database:
            result = self._summary(database)
            result["ranking"] = {key: value for key, value in result["ranking"].items() if key != "items"}
            return result

    def snapshot(self):
        """Export current input facts and prior judgments; never fetch or generate content."""
        with self.store._database() as database:
            inputs = self._inputs(database)
            summary = self._summary(database, inputs["candidates"])
            return {**inputs, "context_digest": summary["context_digest"], "ranking": summary["ranking"]}

    def save_context(self, content, expected_revision, updated_by):
        _revision(expected_revision)
        _actor(updated_by)
        if not isinstance(content, str) or len(content) > 16000:
            raise ResearchError("Shared recommendation context is limited to 16000 characters.")
        if content:
            _safe_text(content, multiline=True)
        _nonsecret_management([content, updated_by])
        with self.store._database(write=True) as database:
            current = self._context(database)
            if current["revision"] != expected_revision:
                raise ResearchError("Shared recommendation context changed; reload before saving.", 5)
            record = {"content": content, "revision": expected_revision + 1,
                      "updated_by": copy.deepcopy(updated_by), "updated_at": _now()}
            database.execute("INSERT INTO recommendation_context VALUES(?,?)", (record["revision"], _json(record)))
            result = self._summary(database)
            result["ranking"] = {key: value for key, value in result["ranking"].items() if key != "items"}
            return result

    def submit(self, payload):
        """Admit a complete explicit order bound to the agent's unchanged input snapshot."""
        expected = {"schema_version", "producer", "run_id", "expected_revision", "context_digest", "rationale", "items"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ResearchError("Ranking requires a producer/run, snapshot digest, revision, rationale and ordered items.")
        producer = payload["producer"]
        if (type(payload["schema_version"]) is not int or payload["schema_version"] != 1
                or not isinstance(producer, dict) or set(producer) != {"producer_id", "name"}
                or not isinstance(producer["producer_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", producer["producer_id"])
                or not isinstance(producer["name"], str) or not 1 <= len(producer["name"]) <= 200
                or not isinstance(payload["run_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", payload["run_id"])
                or not isinstance(payload["context_digest"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", payload["context_digest"])
                or not isinstance(payload["rationale"], str) or not 1 <= len(payload["rationale"]) <= 16000
                or not isinstance(payload["items"], list) or not payload["items"]):
            raise ResearchError("External ranking fields are invalid.")
        _revision(payload["expected_revision"])
        _safe_text(producer["name"])
        _safe_text(payload["rationale"], multiline=True)
        for item in payload["items"]:
            if (not isinstance(item, dict) or set(item) != {"candidate_id", "reason"}
                    or not isinstance(item["candidate_id"], str)
                    or not re.fullmatch(r"candidate-[0-9a-f]{64}", item["candidate_id"])
                    or not isinstance(item["reason"], str) or not 1 <= len(item["reason"]) <= 6000):
                raise ResearchError("Ranked entries need an existing candidate identity and reason.")
            _safe_text(item["reason"], multiline=True)
        _nonsecret_management(payload)
        payload_digest = _digest(payload)
        with self.store._database(write=True) as database:
            previous = database.execute(
                "SELECT payload_digest,record FROM recommendation_rankings WHERE producer_id=? AND run_id=?",
                (producer["producer_id"], payload["run_id"])).fetchone()
            if previous is not None:
                if previous["payload_digest"] != payload_digest:
                    raise ResearchError("This agent run already returned a different ranking.", 5)
                return {**json.loads(previous["record"]), "status": "duplicate"}
            current = self._summary(database)
            if (current["context_digest"] != payload["context_digest"]
                    or current["ranking"]["revision"] != payload["expected_revision"]):
                raise ResearchError("Ranking inputs or output revision changed; read a fresh snapshot.", 5)
            identifiers = [item["candidate_id"] for item in payload["items"]]
            existing = {row[0] for row in database.execute("SELECT candidate_id FROM candidates")}
            if len(set(identifiers)) != len(identifiers) or set(identifiers) != existing:
                raise ResearchError("Ranking must list each current candidate exactly once.")
            record = {"revision": payload["expected_revision"] + 1, "producer": copy.deepcopy(producer),
                      "run_id": payload["run_id"], "context_digest": payload["context_digest"],
                      "rationale": payload["rationale"], "items": copy.deepcopy(payload["items"]), "updated_at": _now()}
            database.execute("INSERT INTO recommendation_rankings VALUES(?,?,?,?,?)", (
                record["revision"], producer["producer_id"], payload["run_id"], payload_digest, _json(record)))
            return {**record, "status": "accepted"}

    def history(self):
        with self.store._database() as database:
            return {"items": [json.loads(row["record"]) for row in database.execute(
                "SELECT record FROM recommendation_rankings ORDER BY revision DESC LIMIT 100")]}
