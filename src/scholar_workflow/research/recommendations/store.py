"""Private transactional recommendation storage, without network or knowledge writes."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from scholar_workflow.research.models import (
    ResearchError,
    channel_url_identity,
)
from scholar_workflow.research.store import read_bytes, root_directory, root_path, storage_lock

DATABASE = "recommendations.sqlite3"
MAX_DATABASE_BYTES = 128 * 1024 * 1024
MAX_SUBMISSION_BYTES = 16 * 1024 * 1024
KINDS = {"paper", "project", "blog"}
DECISIONS = {"unread", "saved", "selected", "ignored"}
_ARXIV = re.compile(r"(?P<base>(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}))(?:v(?P<version>[1-9]\d*))?\Z", re.I)
_DDL = """
CREATE TABLE candidates (
 candidate_id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL, resource TEXT NOT NULL,
 decision TEXT NOT NULL DEFAULT 'unread', revision INTEGER NOT NULL,
 review_digest TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE recommendations (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, producer_id TEXT NOT NULL,
 submission_id TEXT NOT NULL, payload_digest TEXT NOT NULL,
 candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
 producer TEXT NOT NULL, run_id TEXT NOT NULL, resource TEXT NOT NULL,
 tags TEXT NOT NULL, channels TEXT NOT NULL, metrics TEXT NOT NULL,
 received_at TEXT NOT NULL, UNIQUE(producer_id, submission_id)
);
CREATE INDEX candidate_recommendations ON recommendations(candidate_id, sequence);
PRAGMA user_version=1;
"""


def load_submission_schema() -> dict:
    """Return the single schema shipped with the runtime package."""
    return json.loads(files(__package__).joinpath("schema.json").read_text(encoding="utf-8"))


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_text(value, *, multiline=False):
    if not value.strip() or any((ord(c) < 32 and (not multiline or c not in "\n\r\t"))
                                or ord(c) == 127 for c in value):
        raise ResearchError("Recommendation text is empty or contains unsupported control characters.")


def _nonsecret_management(value):
    """Reject credential fields before writing ordinary management records."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", key.lower())
            if normalized in {"apikey", "accesstoken", "refreshtoken", "authorization", "password", "cookie", "clientsecret", "secret"}:
                raise ResearchError("Keep credentials in the native host or tool credential store; management records cannot contain credentials.", 7)
            _nonsecret_management(item)
    elif isinstance(value, list):
        for item in value:
            _nonsecret_management(item)
    elif isinstance(value, str) and re.search(r"(?i)(?:authorization\s*:\s*bearer\s+\S+|(?:api[_ -]?key|access[_ -]?token|password)\s*[=:]\s*[^\s<>]{8,})", value):
        raise ResearchError("Keep credentials in the native host or tool credential store; management records cannot contain credentials.", 7)


def _check_strings(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            _check_strings(child, child_key)
    elif isinstance(value, list):
        for child in value:
            _check_strings(child, key)
    elif isinstance(value, str):
        _safe_text(value, multiline=key in {"abstract_original", "abstract_zh", "description_original", "description_zh", "summary_zh", "recommendation_reason"})
    elif isinstance(value, float) and not math.isfinite(value):
        raise ResearchError("Recommendation numbers must be finite.")


def _arxiv_id(value: str) -> tuple[str, int | None]:
    match = _ARXIV.fullmatch(value)
    if not match:
        raise ResearchError("Recommendation arXiv identity is invalid.")
    return match["base"].lower(), int(match["version"]) if match["version"] else None


def _arxiv_url_identity(value: str) -> tuple[str, int | None] | None:
    parsed = urlsplit(value)
    if parsed.hostname.casefold().rstrip(".") not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        return None
    path = parsed.path
    if not any(path.startswith(prefix) for prefix in ("/abs/", "/pdf/", "/html/")):
        return None
    identifier = path.split("/", 2)[2].removesuffix(".pdf").rstrip("/")
    return _arxiv_id(identifier)


def _normalize_resource(resource: dict) -> tuple[dict, str]:
    result = copy.deepcopy(resource)
    result["url"] = channel_url_identity(result["url"])
    if "project_url" in result:
        result["project_url"] = channel_url_identity(result["project_url"])
    for link in result.get("links", []):
        link["url"] = channel_url_identity(link["url"])
    if "summary_sources" in result:
        result["summary_sources"] = [channel_url_identity(url) for url in result["summary_sources"]]
    kind = result["kind"]
    if kind == "paper":
        url_id = _arxiv_url_identity(result["url"])
        explicit = _arxiv_id(result["arxiv_id"]) if "arxiv_id" in result else None
        if explicit and url_id and (explicit[0] != url_id[0]
                                    or (explicit[1] and url_id[1] and explicit[1] != url_id[1])):
            raise ResearchError("Recommendation URL and arXiv identity conflict.", 5)
        arxiv = explicit or url_id
        if explicit and explicit[1] is None and url_id and url_id[1] is not None:
            arxiv = url_id
        if arxiv:
            if explicit is None or explicit != arxiv:
                result["arxiv_id"] = arxiv[0] + (f"v{arxiv[1]}" if arxiv[1] else "")
            return result, "paper:arxiv:" + arxiv[0]
        if "doi" in result:
            doi = result["doi"].removeprefix("https://doi.org/").removeprefix("doi:").strip().lower()
            if not re.fullmatch(r"10\.\d{4,9}/[^\s]+", doi):
                raise ResearchError("Recommendation DOI identity is invalid.")
            result["doi"] = doi
            return result, "paper:doi:" + doi
        parsed = urlsplit(result["url"])
        if parsed.hostname in {"doi.org", "dx.doi.org"}:
            doi = parsed.path.lstrip("/").lower()
            if re.fullmatch(r"10\.\d{4,9}/[^\s]+", doi):
                result["doi"] = doi
                return result, "paper:doi:" + doi
    return result, kind + ":url:" + result["url"]


def _validate_item(item, schema):
    item_schema = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/item"}
    if next(Draft202012Validator(item_schema, format_checker=FormatChecker()).iter_errors(item), None):
        raise ResearchError("Recommendation item does not match submission schema v1.")
    _check_strings(item)
    result = copy.deepcopy(item)
    resource, identity = _normalize_resource(result["resource"])
    result["resource"] = resource
    result.setdefault("channels", [])
    result.setdefault("metrics", [])
    for channel in result["channels"]:
        channel["url"] = channel_url_identity(channel["url"])
    for metric in result["metrics"]:
        metric["url"] = channel_url_identity(metric["url"])
        try:
            observed = datetime.fromisoformat(metric["observed_at"])
            if observed.tzinfo is None or observed.utcoffset() is None:
                raise ValueError("Missing timezone")
        except ValueError:
            raise ResearchError("Recommendation metric observation requires an ISO timestamp with timezone.") from None
    published = resource.get("published_at")
    if published:
        try:
            if len(published) == 10:
                date.fromisoformat(published)
            else:
                parsed = datetime.fromisoformat(published)
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError("Missing timezone")
        except ValueError:
            raise ResearchError("Recommendation publication date is invalid.") from None
    return result, identity


def reading_kind(resource):
    """Identify the actual reading content without substituting a summary for a translation."""
    if resource.get("abstract_original"):
        return "abstract" if resource.get("abstract_zh") else "unavailable"
    if resource.get("summary_zh") and resource.get("summary_sources"):
        return "summary"
    if resource["kind"] != "paper" and resource.get("description_original"):
        return "description"
    return "unavailable"


def _review_digest(resource):
    kind = reading_kind(resource)
    if kind == "summary":
        return _digest({key: resource.get(key) for key in
                        ("kind", "title", "url", "arxiv_id", "doi", "summary_zh", "summary_sources")})
    if kind != "abstract":
        return None
    # Preserve existing abstract-review hashes across this additive change.
    return _digest({key: resource.get(key) for key in
                    ("kind", "title", "arxiv_id", "doi", "abstract_original", "abstract_zh")})


def _merge_resource(previous, incoming):
    """Retain absent metadata without attaching an old translation to changed text."""
    if previous.get("arxiv_id") and incoming.get("arxiv_id"):
        old_identity, old_version = _arxiv_id(previous["arxiv_id"])
        new_identity, new_version = _arxiv_id(incoming["arxiv_id"])
        if old_identity == new_identity and old_version:
            if new_version and new_version < old_version:
                return previous
            if new_version is None:
                if any(key in incoming and incoming[key] != previous.get(key)
                       for key in ("abstract_original", "abstract_zh")):
                    return previous
                # Metadata without a version cannot erase the version bound to the body.
                incoming = {**incoming, "arxiv_id": previous["arxiv_id"], "url": previous["url"]}
    merged = {**previous, **incoming}
    for original, translated in (("abstract_original", "abstract_zh"),
                                 ("description_original", "description_zh")):
        if (original in incoming and incoming[original] != previous.get(original)
                and translated not in incoming):
            merged.pop(translated, None)
    return merged


class RecommendationStore:
    """A single local candidate pool, independently usable by multiple agent processes."""

    def __init__(self, state_dir: Path):
        self.state_dir = root_path(state_dir)

    @staticmethod
    def _connect(data):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA trusted_schema=OFF")
        if data is not None:
            connection.deserialize(data)
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                connection.close()
                raise ResearchError("Recommendation state schema is unsupported.", 2)
        else:
            connection.executescript(_DDL)
        connection.execute("""CREATE TABLE IF NOT EXISTS metric_refreshes (
            candidate_id TEXT PRIMARY KEY REFERENCES candidates(candidate_id), snapshot TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS ingestion_plans (
            plan_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
            record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS source_catalog (
            name TEXT PRIMARY KEY, record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS source_context (
            source_id TEXT PRIMARY KEY, record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS source_operations (
            operation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS recommendation_requirements (
            requirement_id TEXT NOT NULL, revision INTEGER NOT NULL, record TEXT NOT NULL,
            PRIMARY KEY(requirement_id,revision))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS recommendation_requirement_uses (
            sequence INTEGER PRIMARY KEY REFERENCES recommendations(sequence), record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS candidate_evaluations (
            candidate_id TEXT PRIMARY KEY REFERENCES candidates(candidate_id), record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS candidate_evaluation_history (
            candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id), revision INTEGER NOT NULL,
            record TEXT NOT NULL, PRIMARY KEY(candidate_id,revision))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS recommendation_reasons (
            sequence INTEGER PRIMARY KEY REFERENCES recommendations(sequence), reason TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS recommendation_context (
            revision INTEGER PRIMARY KEY, record TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS recommendation_rankings (
            revision INTEGER PRIMARY KEY, producer_id TEXT NOT NULL, run_id TEXT NOT NULL,
            payload_digest TEXT NOT NULL, record TEXT NOT NULL, UNIQUE(producer_id,run_id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS candidate_content_revisions (
            candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id), revision INTEGER NOT NULL,
            record TEXT NOT NULL, PRIMARY KEY(candidate_id,revision))""")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _database(self, *, write=False):
        connection = None
        try:
            with root_directory(self.state_dir, create=write) as directory:
                with storage_lock(directory, name=".recommendations.lock"):
                    original = read_bytes(directory, DATABASE, MAX_DATABASE_BYTES)
                    connection = self._connect(original)
                    if write:
                        connection.execute("BEGIN IMMEDIATE")
                    yield connection
                    if write:
                        connection.commit()
                        data = connection.serialize()
                        if len(data) > MAX_DATABASE_BYTES:
                            raise ResearchError("Recommendation state exceeds the supported size limit.", 7)
                        with root_directory(self.state_dir) as current:
                            a, b = os.fstat(directory), os.fstat(current)
                            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                                raise ResearchError("Recommendation storage changed during the operation.", 5)
                        if read_bytes(directory, DATABASE, MAX_DATABASE_BYTES) != original:
                            raise ResearchError("Recommendation state changed outside its writer lock.", 5)
                        name = ".recommendations-" + secrets.token_hex(12)
                        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                             mode=0o600, dir_fd=directory)
                        try:
                            with os.fdopen(descriptor, "wb", closefd=False) as output:
                                output.write(data)
                                output.flush()
                                os.fsync(descriptor)
                            os.replace(name, DATABASE, src_dir_fd=directory, dst_dir_fd=directory)
                            os.fsync(directory)
                        finally:
                            os.close(descriptor)
                            try:
                                os.unlink(name, dir_fd=directory)
                            except FileNotFoundError:
                                pass
        except FileNotFoundError:
            if write:
                raise ResearchError("Recommendation storage is unavailable.", 7) from None
            connection = self._connect(None)
            yield connection
        except sqlite3.Error:
            raise ResearchError("Recommendation state is invalid or unavailable.", 2) from None
        except OSError:
            raise ResearchError("Recommendation storage is unsafe or unavailable.", 7) from None
        finally:
            if connection:
                connection.close()

    def submit(self, payload: dict) -> dict:
        """Validate an envelope and atomically preserve accepted per-item submissions."""
        schema = load_submission_schema()
        envelope_schema = copy.deepcopy(schema)
        envelope_schema["properties"]["items"]["items"] = {}
        try:
            size = len(_json(payload).encode("utf-8"))
        except (TypeError, ValueError, RecursionError):
            raise ResearchError("Recommendation submission must be finite UTF-8 JSON.") from None
        if size > MAX_SUBMISSION_BYTES:
            raise ResearchError("Recommendation submission exceeds its size limit.", 7)
        if next(Draft202012Validator(envelope_schema, format_checker=FormatChecker()).iter_errors(payload), None):
            raise ResearchError("Recommendation envelope does not match submission schema v1.")
        _check_strings(payload["producer"])
        producer = copy.deepcopy(payload["producer"])
        if "task_url" in producer:
            producer["task_url"] = channel_url_identity(producer["task_url"])
        receipts = []
        with self._database(write=True) as database:
            for item in payload["items"]:
                submission_id = item.get("submission_id") if isinstance(item, dict) else None
                receipt = {"submission_id": submission_id if isinstance(submission_id, str)
                           and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", submission_id) else None}
                try:
                    normalized, identity = _validate_item(item, schema)
                    digest_payload = {"producer": producer, "run_id": payload["run_id"], "item": normalized}
                    if "requirement" in payload:
                        digest_payload["requirement"] = payload["requirement"]
                    digest = _digest(digest_payload)
                    existing = database.execute(
                        "SELECT candidate_id,payload_digest FROM recommendations WHERE producer_id=? AND submission_id=?",
                        (producer["producer_id"], normalized["submission_id"]),
                    ).fetchone()
                    if existing:
                        status = "duplicate" if existing["payload_digest"] == digest else "conflict"
                        receipts.append({**receipt, "status": status, "candidate_id": existing["candidate_id"],
                                         **({"message": "Submission identity already contains different content."}
                                            if status == "conflict" else {})})
                        continue
                    requirement = self._admit_recommendation_requirement(
                        database, producer["producer_id"], payload["run_id"], payload.get("requirement"))
                    candidate_id = "candidate-" + hashlib.sha256(identity.encode()).hexdigest()
                    timestamp = _now()
                    source_resource = _json(normalized["resource"])
                    resource = source_resource
                    existing_candidate = database.execute(
                        "SELECT candidate_id,resource FROM candidates WHERE identity=?", (identity,),
                    ).fetchone()
                    if existing_candidate:
                        if self._ingestion_active(database, candidate_id):
                            receipts.append({**receipt, "status": "conflict", "candidate_id": candidate_id,
                                             "message": "Bibliography ingestion is in progress; retry this submission after its receipt."})
                            continue
                        resource = _json(_merge_resource(json.loads(existing_candidate["resource"]), normalized["resource"]))
                        database.execute("UPDATE candidates SET resource=?,revision=revision+1,updated_at=? WHERE candidate_id=?",
                                         (resource, timestamp, candidate_id))
                    else:
                        database.execute("INSERT INTO candidates(candidate_id,identity,resource,revision,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                                         (candidate_id, identity, resource, 1, timestamp, timestamp))
                    inserted = database.execute("""INSERT INTO recommendations
                        (producer_id,submission_id,payload_digest,candidate_id,producer,run_id,resource,tags,channels,metrics,received_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                            producer["producer_id"], normalized["submission_id"], digest, candidate_id,
                            _json(producer), payload["run_id"], source_resource, _json(normalized["tags"]),
                            _json(normalized["channels"]), _json(normalized["metrics"]), timestamp,
                        ))
                    if requirement is not None:
                        database.execute("INSERT INTO recommendation_requirement_uses VALUES(?,?)",
                                         (inserted.lastrowid, _json({key: requirement[key]
                                                                   for key in ("requirement_id", "revision")})))
                    if "recommendation_reason" in normalized:
                        database.execute("INSERT INTO recommendation_reasons VALUES(?,?)",
                                         (inserted.lastrowid, normalized["recommendation_reason"]))
                    receipts.append({**receipt, "status": "accepted", "candidate_id": candidate_id})
                except ResearchError as error:
                    receipts.append({**receipt, "status": "invalid", "message": str(error)})
        unsuccessful = any(row["status"] in {"invalid", "conflict"} for row in receipts)
        return {"schema_version": 1, "status": "partial" if unsuccessful else "complete", "receipts": receipts}

    @staticmethod
    def _candidate(database, row):
        resource = json.loads(row["resource"])
        recommendations, metrics, producers, tags = [], [], {}, set()
        metric_keys = set()
        for item in database.execute("SELECT * FROM recommendations WHERE candidate_id=? ORDER BY sequence",
                                     (row["candidate_id"],)):
            producer = json.loads(item["producer"])
            item_tags = json.loads(item["tags"])
            producers[producer["producer_id"]] = {"producer_id": producer["producer_id"], "name": producer["name"]}
            tags.update(item_tags)
            recommendations.append({"producer": producer, "run_id": item["run_id"],
                                    "submission_id": item["submission_id"], "tags": item_tags,
                                    "resource": json.loads(item["resource"]),
                                    "channels": json.loads(item["channels"]), "received_at": item["received_at"]})
            reason = database.execute("SELECT reason FROM recommendation_reasons WHERE sequence=?",
                                      (item["sequence"],)).fetchone()
            if reason is not None:
                recommendations[-1]["recommendation_reason"] = reason["reason"]
            requirement = database.execute(
                "SELECT record FROM recommendation_requirement_uses WHERE sequence=?", (item["sequence"],)
            ).fetchone()
            if requirement is not None:
                reference = json.loads(requirement["record"])
                recommendations[-1]["requirement"] = RecommendationStore._requirement(
                    database, reference["requirement_id"], reference["revision"])
            for metric in json.loads(item["metrics"]):
                key = _json(metric)
                if key not in metric_keys:
                    metrics.append(metric)
                    metric_keys.add(key)
        from scholar_workflow.research.recommendations.metrics import metric_targets

        targets = [{key: target[key] for key in ("platform", "metric", "url")}
                   for target in metric_targets(resource)]
        keys = {(item["platform"], item["metric"], item["url"]) for item in targets}
        refreshed = database.execute("SELECT snapshot FROM metric_refreshes WHERE candidate_id=?",
                                     (row["candidate_id"],)).fetchone()
        snapshot = json.loads(refreshed["snapshot"]) if refreshed else {"observations": [], "checks": []}
        metrics.extend(item for item in snapshot["observations"]
                       if (item["platform"], item["metric"], item["url"]) in keys)
        kind = reading_kind(resource)
        ingestion = database.execute("SELECT record FROM ingestion_plans WHERE candidate_id=? ORDER BY rowid DESC LIMIT 1",
                                     (row["candidate_id"],)).fetchone()
        ingestion = json.loads(ingestion["record"]) if ingestion else None
        return {"candidate_id": row["candidate_id"], "resource": resource, "tags": sorted(tags),
                "evaluation": RecommendationStore._evaluation(database, row["candidate_id"], resource),
                "ingestion": ({"plan_id": ingestion["plan_id"], "status": ingestion["status"],
                               "scope": "zotero_bibliography", "receipt": ingestion.get("receipt"),
                               "matches_current_content": ingestion["resource_digest"] == _digest(resource)}
                              if ingestion else None),
                "metric_targets": targets, "metric_refresh": {"checks": [
                    item for item in snapshot["checks"]
                    if (item["platform"], item["metric"], item["url"]) in keys]},
                "reading_kind": kind, "review_required": resource["kind"] == "paper"
                or bool(resource.get("abstract_original")) or kind == "summary",
                "review_available": kind in {"abstract", "summary"},
                "producers": list(producers.values()), "recommendations": recommendations,
                "metrics": metrics, "decision": row["decision"], "revision": row["revision"],
                "abstract_reviewed": bool(row["review_digest"] and row["review_digest"] == _review_digest(resource)),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    @staticmethod
    def _row(database, candidate_id):
        if not isinstance(candidate_id, str) or not re.fullmatch(r"candidate-[0-9a-f]{64}", candidate_id):
            raise ResearchError("Recommendation candidate identity is invalid.")
        row = database.execute("SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        if row is None:
            raise ResearchError("Recommendation candidate was not found.")
        return row

    def get_candidate(self, candidate_id: str) -> dict:
        with self._database() as database:
            return self._candidate(database, self._row(database, candidate_id))

    @staticmethod
    def _evaluation(database, candidate_id, resource):
        row = database.execute("SELECT record FROM candidate_evaluations WHERE candidate_id=?",
                               (candidate_id,)).fetchone()
        if row is None:
            return {"score": None, "comment": "", "revision": 0, "updated_at": None,
                    "matches_current_content": True}
        record = json.loads(row["record"])
        return {key: record[key] for key in ("score", "comment", "revision", "updated_at")} | {
            "matches_current_content": record["resource_digest"] == _digest(resource)}

    def revise_content(self, candidate_id, expected_revision, changes, updated_by):
        """Correct an existing reading body without adding a recommendation event."""
        allowed = {"abstract_original", "abstract_zh", "description_original", "description_zh",
                   "summary_zh", "summary_sources"}
        if (type(expected_revision) is not int or not 1 <= expected_revision < 2**63 - 1
                or not isinstance(changes, dict) or not changes or set(changes) - allowed):
            raise ResearchError("Content correction needs an exact revision and supported reading fields.")
        if (not isinstance(updated_by, dict) or set(updated_by) != {"kind", "name"}
                or not isinstance(updated_by.get("kind"), str) or updated_by["kind"] not in {"human", "agent"}
                or not isinstance(updated_by.get("name"), str) or not 1 <= len(updated_by["name"]) <= 200):
            raise ResearchError("Content correction needs a named human or agent editor.")
        _safe_text(updated_by["name"])
        _nonsecret_management(updated_by)
        try:
            if len(_json(changes).encode("utf-8")) > 512 * 1024:
                raise ResearchError("Content correction exceeds the supported input limit.")
        except (TypeError, ValueError, RecursionError):
            raise ResearchError("Content correction must contain finite UTF-8 JSON.") from None
        with self._database(write=True) as database:
            row = self._row(database, candidate_id)
            if row["revision"] != expected_revision:
                raise ResearchError("Recommendation content changed; reload before correcting it.", 5)
            if self._ingestion_active(database, candidate_id):
                raise ResearchError("Bibliography ingestion is in progress; wait for its receipt before correcting content.", 5)
            previous = json.loads(row["resource"])
            # Updating original text invalidates an omitted old translation.
            incoming = {key: value for key, value in changes.items() if value is not None}
            resource = _merge_resource(previous, incoming)
            for key, value in changes.items():
                if value is None:
                    resource.pop(key, None)
            normalized, identity = _validate_item({"submission_id": "content-correction",
                "resource": resource, "tags": []}, load_submission_schema())
            resource = normalized["resource"]
            if identity != row["identity"]:
                raise ResearchError("Content correction cannot change resource identity.", 5)
            if reading_kind(resource) not in {"abstract", "summary"}:
                raise ResearchError("Complete the author abstract translation or provide a source-backed summary before correcting content.", 7)
            if resource == previous:
                return {"status": "unchanged", "candidate": self._candidate(database, row), "revision_record": None}
            timestamp = _now()
            revision = row["revision"] + 1
            decision = "unread" if row["decision"] == "selected" else row["decision"]
            record = {"candidate_id": candidate_id, "revision": revision, "updated_at": timestamp,
                      "updated_by": copy.deepcopy(updated_by), "changes": copy.deepcopy(changes),
                      "before": {"resource": previous, "revision": row["revision"], "decision": row["decision"],
                                 "abstract_reviewed": bool(row["review_digest"] and row["review_digest"] == _review_digest(previous))},
                      "after": {"resource": resource, "revision": revision, "decision": decision,
                                "abstract_reviewed": False}}
            database.execute("""UPDATE candidates SET resource=?,review_digest=NULL,decision=?,revision=?,updated_at=?
                WHERE candidate_id=?""", (_json(resource), decision, revision, timestamp, candidate_id))
            database.execute("INSERT INTO candidate_content_revisions VALUES(?,?,?)",
                             (candidate_id, revision, _json(record)))
            return {"status": "updated", "candidate": self._candidate(database, self._row(database, candidate_id)),
                    "revision_record": record}

    def content_revision_history(self, candidate_id):
        """Read attributed before/after records from this candidate's own pool."""
        with self._database() as database:
            self._row(database, candidate_id)
            return {"candidate_id": candidate_id, "items": [json.loads(row["record"]) for row in database.execute(
                "SELECT record FROM candidate_content_revisions WHERE candidate_id=? ORDER BY revision", (candidate_id,))]}

    def save_evaluation(self, candidate_id, score, comment, expected_revision, expected_candidate_revision):
        """Save a person's evaluation without changing review or ingestion revisions."""
        if score is not None and (type(score) is not int or not 1 <= score <= 5):
            raise ResearchError("Evaluation score must be an integer from 1 to 5, or null.")
        if not isinstance(comment, str) or len(comment) > 4000:
            raise ResearchError("Evaluation comment must contain at most 4000 characters.")
        if comment:
            _safe_text(comment, multiline=True)
        if type(expected_revision) is not int or not 0 <= expected_revision < 2**63 - 1:
            raise ResearchError("Evaluation needs its exact current revision.")
        if type(expected_candidate_revision) is not int or not 1 <= expected_candidate_revision < 2**63:
            raise ResearchError("Evaluation needs the revision of the displayed candidate.")
        with self._database(write=True) as database:
            row = self._row(database, candidate_id)
            if row["revision"] != expected_candidate_revision:
                raise ResearchError("Recommendation content changed; reload before evaluating it.", 5)
            current = self._evaluation(database, candidate_id, json.loads(row["resource"]))
            if current["revision"] != expected_revision:
                raise ResearchError("Evaluation changed; reload before editing again.", 5)
            record = {"score": score, "comment": comment, "revision": expected_revision + 1,
                      "updated_at": _now(), "resource_digest": _digest(json.loads(row["resource"]))}
            previous = database.execute("SELECT record FROM candidate_evaluations WHERE candidate_id=?",
                                        (candidate_id,)).fetchone()
            if previous is not None:
                database.execute("INSERT OR IGNORE INTO candidate_evaluation_history VALUES(?,?,?)",
                                 (candidate_id, current["revision"], previous["record"]))
            database.execute("INSERT INTO candidate_evaluation_history VALUES(?,?,?)",
                             (candidate_id, record["revision"], _json(record)))
            database.execute("INSERT INTO candidate_evaluations(candidate_id,record) VALUES(?,?) "
                             "ON CONFLICT(candidate_id) DO UPDATE SET record=excluded.record",
                             (candidate_id, _json(record)))
            return self._candidate(database, row)

    def list_candidates(self, query="", kind=None, tag=None, producer_id=None, decision=None,
                        sort="newest", limit=40, offset=0, since=None) -> dict:
        if (not isinstance(query, str) or len(query) > 500 or kind not in KINDS | {None}
                or decision not in DECISIONS | {None} or sort not in {"newest", "oldest", "published", "agent"}
                or type(limit) is not int or not 1 <= limit <= 200
                or type(offset) is not int or offset < 0
                or (tag is not None and (not isinstance(tag, str) or len(tag) > 120))
                or (producer_id is not None and (not isinstance(producer_id, str) or len(producer_id) > 128))):
            raise ResearchError("Recommendation filters are invalid.")
        if since is not None:
            try:
                date.fromisoformat(since)
            except (TypeError, ValueError):
                raise ResearchError("Recommendation date filter must be an ISO calendar date.") from None
        with self._database() as database:
            rows = [self._candidate(database, row) for row in database.execute("SELECT * FROM candidates")]
            from scholar_workflow.research.recommendations.ranking import RecommendationRanking
            ranking = RecommendationRanking(self)._summary(database, candidates=rows)["ranking"]
        all_tags, all_producers, all_kinds = set(), {}, set()
        for row in rows:
            all_tags.update(row["tags"])
            all_kinds.add(row["resource"]["kind"])
            for producer in row["producers"]:
                all_producers[producer["producer_id"]] = producer
        matching = []
        for row in rows:
            resource = row["resource"]
            if kind and resource["kind"] != kind or decision and row["decision"] != decision:
                continue
            if since and (not resource.get("published_at") or resource["published_at"][:10] < since):
                continue
            if query.casefold() not in " ".join([resource["title"], *resource.get("authors", [])]).casefold():
                continue
            if (tag or producer_id) and not any(
                (not tag or tag in record["tags"])
                and (not producer_id or producer_id == record["producer"]["producer_id"])
                for record in row["recommendations"]
            ):
                continue
            matching.append(row)
        if sort in {"published", "agent"}:
            matching.sort(key=lambda row: (row["resource"].get("published_at", ""), row["created_at"]), reverse=True)
            if sort == "agent" and ranking["status"] == "current":
                positions = {item["candidate_id"]: index for index, item in enumerate(ranking["items"])}
                reasons = {item["candidate_id"]: item["reason"] for item in ranking["items"]}
                matching.sort(key=lambda row: positions[row["candidate_id"]])
                for row in matching:
                    row["ranking_reason"] = reasons[row["candidate_id"]]
        else:
            def recommendation_time(row):
                observations = [item["received_at"] for item in row["recommendations"]]
                return (max(observations) if sort == "newest" else min(observations), row["candidate_id"])
            matching.sort(key=recommendation_time, reverse=sort == "newest")
        return {"schema_version": 1, "items": matching[offset:offset + limit], "total": len(matching),
                "ranking": {key: value for key, value in ranking.items() if key != "items"},
                "facets": {"tags": sorted(all_tags), "producers": sorted(all_producers.values(), key=lambda p: p["name"]),
                           "kinds": sorted(all_kinds)}}

    def _update(self, candidate_id, expected_revision, *, decision=None, review=False, clear_review=False):
        if type(expected_revision) is not int or expected_revision < 1:
            raise ResearchError("Recommendation revision must be a positive integer.")
        with self._database(write=True) as database:
            row = self._row(database, candidate_id)
            if self._ingestion_active(database, candidate_id):
                raise ResearchError("Bibliography ingestion is in progress; wait for its receipt before changing this candidate.", 5)
            if row["revision"] != expected_revision:
                raise ResearchError("Recommendation changed; reload before updating your choice.", 5)
            if clear_review:
                database.execute("""UPDATE candidates SET review_digest=NULL,
                    decision=CASE WHEN decision='selected' THEN 'unread' ELSE decision END,
                    revision=revision+1,updated_at=? WHERE candidate_id=?""", (_now(), candidate_id))
            elif review:
                resource = json.loads(row["resource"])
                if reading_kind(resource) not in {"abstract", "summary"}:
                    raise ResearchError("Review requires a complete translated abstract or a sourced, explicit summary.", 7)
                database.execute("UPDATE candidates SET review_digest=?,revision=revision+1,updated_at=? WHERE candidate_id=?",
                                 (_review_digest(resource), _now(), candidate_id))
            else:
                database.execute("UPDATE candidates SET decision=?,revision=revision+1,updated_at=? WHERE candidate_id=?",
                                 (decision, _now(), candidate_id))
            return self._candidate(database, self._row(database, candidate_id))

    def record_metric_refresh(self, candidate_id, expected_revision, result):
        """Write only platform observations; preserve recommendation and human state."""
        from scholar_workflow.research.recommendations.metrics import metric_targets

        if (type(expected_revision) is not int or expected_revision < 1
                or not isinstance(result, dict) or set(result) != {"observations", "checks"}
                or not all(isinstance(result[key], list) and len(result[key]) <= 6 for key in result)):
            raise ResearchError("Metric refresh payload is invalid.")
        with self._database(write=True) as database:
            row = self._row(database, candidate_id)
            if row["revision"] != expected_revision:
                raise ResearchError("Recommendation changed; reload before refreshing metrics.", 5)
            resource = json.loads(row["resource"])
            allowed = {(item["platform"], item["metric"], item["url"])
                       for item in metric_targets(resource)}
            def key(item):
                return item["platform"], item["metric"], item["url"]
            def timestamp(value):
                try:
                    parsed = datetime.fromisoformat(value)
                    if parsed.utcoffset() is None:
                        raise ValueError()
                    return parsed.astimezone(UTC).isoformat()
                except (ValueError, TypeError):
                    raise ResearchError("Metric refresh requires a valid timezone timestamp.") from None
            normalized, _ = _validate_item({"submission_id": "metric-refresh", "resource": resource,
                                            "tags": [], "metrics": result["observations"]}, load_submission_schema())
            observations = normalized["metrics"]
            checks = copy.deepcopy(result["checks"])
            for check in checks:
                if (not isinstance(check, dict)
                        or set(check) != {"platform", "metric", "url", "status", "checked_at"}
                        or check["status"] not in {"ok", "unavailable", "rate_limited"}):
                    raise ResearchError("Metric refresh check is invalid.")
                check["url"] = channel_url_identity(check["url"])
                if key(check) not in allowed:
                    raise ResearchError("Metric target is not declared by this candidate.", 7)
                check["checked_at"] = timestamp(check["checked_at"])
            for item in observations:
                item["observed_at"] = timestamp(item["observed_at"])
                if (key(item) not in allowed or not any(key(check) == key(item)
                        and check["status"] == "ok" and check["checked_at"] == item["observed_at"] for check in checks)):
                    raise ResearchError("Metric observation does not match an authorized successful check.", 7)
            previous = database.execute("SELECT snapshot FROM metric_refreshes WHERE candidate_id=?", (candidate_id,)).fetchone()
            snapshot = json.loads(previous["snapshot"]) if previous else {"observations": [], "checks": []}
            for field, date_key, incoming in (("observations", "observed_at", observations), ("checks", "checked_at", checks)):
                latest = {key(item): item for item in snapshot[field] if key(item) in allowed}
                for item in incoming:
                    if key(item) not in latest or item[date_key] >= latest[key(item)][date_key]:
                        latest[key(item)] = item
                snapshot[field] = list(latest.values())
            database.execute("INSERT INTO metric_refreshes(candidate_id,snapshot) VALUES(?,?) "
                             "ON CONFLICT(candidate_id) DO UPDATE SET snapshot=excluded.snapshot",
                             (candidate_id, _json(snapshot)))
            return self._candidate(database, row)

    def set_decision(self, candidate_id, decision, expected_revision):
        if decision not in DECISIONS:
            raise ResearchError("Recommendation decision is invalid.")
        return self._update(candidate_id, expected_revision, decision=decision)

    def review_candidate(self, candidate_id, expected_revision):
        return self._update(candidate_id, expected_revision, review=True)

    def revoke_review(self, candidate_id, expected_revision):
        """Withdraw current review and pending selection, retaining ingestion facts."""
        return self._update(candidate_id, expected_revision, clear_review=True)

    def prepare_handoff(self):
        with self._database() as database:
            items = [self._candidate(database, row) for row in database.execute(
                "SELECT * FROM candidates WHERE decision='selected' ORDER BY created_at,candidate_id")]
        if any(row["review_required"] and not row["abstract_reviewed"] for row in items):
            raise ResearchError("Review every selected item's current abstract or sourced summary before preparing ingestion.", 7)
        pool_id = "pool-" + hashlib.sha256(str(self.state_dir).encode("utf-8")).hexdigest()[:32]
        return {"schema_version": 1, "status": "ready", "pool_id": pool_id, "items": items}


    @staticmethod
    def _admit_plan(database, plan):
        row = RecommendationStore._row(database, plan.get("candidate_id"))
        candidate = RecommendationStore._candidate(database, row)
        if (type(plan.get("candidate_revision")) is not int
                or candidate["revision"] != plan["candidate_revision"]
                or _digest(candidate["resource"]) != plan.get("resource_digest")):
            raise ResearchError("The ingestion content changed; prepare a fresh preview.", 5)
        if candidate["decision"] != "selected" or (candidate["review_required"] and not candidate["abstract_reviewed"]):
            raise ResearchError("Ingestion requires the current reviewed human selection.", 7)
        try:
            expiry = datetime.fromisoformat(plan["expires_at"])
            if expiry.utcoffset() is None or expiry <= datetime.now(UTC):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ResearchError("The ingestion preview expired; prepare a fresh preview.", 5) from None

    @staticmethod
    def _ingestion_active(database, candidate_id):
        return any(json.loads(row["record"])["status"] == "in_progress" for row in database.execute(
            "SELECT record FROM ingestion_plans WHERE candidate_id=?", (candidate_id,)))

    def create_ingestion_plan(self, plan):
        plan = copy.deepcopy(plan)
        if (not isinstance(plan, dict) or len(_json(plan).encode()) > 256 * 1024
                or not re.fullmatch(r"[A-Z0-9]{8}", str(plan.get("collection_key", "")))
                or not isinstance(plan.get("provider_identity"), str)):
            raise ResearchError("Ingestion preview is invalid.")
        with self._database(write=True) as database:
            self._admit_plan(database, plan)
            for saved in database.execute("SELECT record FROM ingestion_plans WHERE candidate_id=? ORDER BY rowid DESC",
                                          (plan["candidate_id"],)):
                previous = json.loads(saved["record"])
                same = all(previous.get(key) == plan.get(key) for key in
                           ("candidate_revision", "resource_digest", "collection_key", "provider_identity", "collection_version"))
                if previous["status"] == "in_progress":
                    raise ResearchError("This candidate already has an ingestion operation in progress.", 5)
                if same and previous["status"] == "completed":
                    return previous
                if same and previous["status"] == "pending" and previous["expires_at"] > _now():
                    return previous
            plan.update(plan_id="ingest-" + secrets.token_hex(16), status="pending", created_at=_now())
            database.execute("INSERT INTO ingestion_plans VALUES(?,?,?)",
                             (plan["plan_id"], plan["candidate_id"], _json(plan)))
        return plan

    @staticmethod
    def _ingestion_plan(database, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch(r"ingest-[0-9a-f]{32}", plan_id):
            raise ResearchError("Ingestion plan identity is invalid.")
        row = database.execute("SELECT record FROM ingestion_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            raise ResearchError("Ingestion preview was not found.")
        return json.loads(row["record"])

    def get_ingestion_plan(self, plan_id):
        with self._database() as database:
            return self._ingestion_plan(database, plan_id)

    def claim_ingestion_plan(self, plan_id, *, retry=False):
        with self._database(write=True) as database:
            plan = self._ingestion_plan(database, plan_id)
            if plan["status"] == "completed":
                return plan
            self._admit_plan(database, plan)
            if plan["status"] != "pending" and not (retry is True and plan["status"] in {"needs_attention", "interrupted"}):
                raise ResearchError("This operation needs explicit inspection before retrying.", 5)
            running = database.execute("SELECT record FROM ingestion_plans WHERE candidate_id=? AND plan_id<>?",
                                       (plan["candidate_id"], plan_id)).fetchall()
            if any(json.loads(row["record"])["status"] == "in_progress" for row in running):
                raise ResearchError("This candidate already has an ingestion operation in progress.", 5)
            plan.update(status="in_progress", started_at=_now())
            database.execute("UPDATE ingestion_plans SET record=? WHERE plan_id=?", (_json(plan), plan_id))
        return plan

    def finish_ingestion_plan(self, plan_id, receipt):
        if not isinstance(receipt, dict) or receipt.get("status") not in {"completed", "needs_attention", "conflict"}:
            raise ResearchError("Ingestion receipt is invalid.")
        with self._database(write=True) as database:
            plan = self._ingestion_plan(database, plan_id)
            if plan["status"] != "in_progress":
                raise ResearchError("This ingestion operation is not active.", 5)
            if receipt["status"] == "completed" and (
                    not re.fullmatch(r"[A-Z0-9]{8}", str(receipt.get("item_key", "")))
                    or receipt.get("collection_key") != plan["collection_key"]):
                raise ResearchError("A completed ingestion needs an observed item and target.", 7)
            receipt = {**copy.deepcopy(receipt), "plan_id": plan_id, "candidate_id": plan["candidate_id"],
                       "scope": "zotero_bibliography"}
            if receipt.get("item_key") and re.fullmatch(r"[A-Z0-9]{8}", receipt["item_key"]):
                receipt["zotero_url"] = "zotero://select/library/items/" + receipt["item_key"]
            plan.update(status=receipt["status"], receipt=receipt, updated_at=_now())
            database.execute("UPDATE ingestion_plans SET record=? WHERE plan_id=?", (_json(plan), plan_id))
        return plan

    def ingestion_history(self):
        with self._database() as database:
            return [json.loads(row["record"]) for row in database.execute(
                "SELECT record FROM ingestion_plans ORDER BY rowid DESC LIMIT 200")]


    @staticmethod
    def _requirement_id(requirement_id):
        if (not isinstance(requirement_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", requirement_id)):
            raise ResearchError("A recommendation requirement needs a stable identity.")
        return requirement_id

    @staticmethod
    def _requirement(database, requirement_id, revision=None):
        RecommendationStore._requirement_id(requirement_id)
        if revision is not None and (type(revision) is not int or not 1 <= revision <= 9223372036854775807):
            raise ResearchError("A requirement version must be a positive integer.")
        row = database.execute(
            "SELECT record FROM recommendation_requirements WHERE requirement_id=?"
            + (" AND revision=?" if revision is not None else " ORDER BY revision DESC LIMIT 1"),
            (requirement_id, revision) if revision is not None else (requirement_id,),
        ).fetchone()
        if row is None:
            raise ResearchError("The requested recommendation requirement version was not found.", 3)
        return json.loads(row["record"])

    def list_requirements(self, source_id=None):
        """List the latest versions, including disabled requirements; create no defaults."""
        if source_id is not None:
            from scholar_workflow.research.recommendations.source_catalog import SourceCatalog
            SourceCatalog(self).get_source(source_id)
        with self._database() as database:
            rows = database.execute("""SELECT versions.record FROM recommendation_requirements AS versions
                JOIN (SELECT requirement_id, MAX(revision) AS revision FROM recommendation_requirements
                      GROUP BY requirement_id) AS latest
                ON versions.requirement_id=latest.requirement_id AND versions.revision=latest.revision
                ORDER BY versions.requirement_id""")
            items = [json.loads(row["record"]) for row in rows]
            if source_id is not None:
                items = [item for item in items if item.get("source_id") == source_id]
            return {"items": items}

    def get_requirement(self, requirement_id, revision=None):
        with self._database() as database:
            return self._requirement(database, requirement_id, revision)

    def save_requirement(self, requirement_id, title, content, enabled, expected_revision, updated_by,
                         source_id=None):
        """Append one human/agent-declared edit using an exact current revision."""
        self._requirement_id(requirement_id)
        if (not isinstance(title, str) or not 1 <= len(title) <= 200
                or not isinstance(content, str) or not 1 <= len(content) <= 20000
                or type(enabled) is not bool or type(expected_revision) is not int or expected_revision < 0
                or not isinstance(updated_by, dict) or set(updated_by) != {"kind", "name"}
                or not isinstance(updated_by["kind"], str) or updated_by["kind"] not in {"human", "agent"}
                or not isinstance(updated_by["name"], str) or not 1 <= len(updated_by["name"]) <= 200):
            raise ResearchError("Recommendation requirement fields are invalid.")
        _safe_text(title)
        _safe_text(content, multiline=True)
        _safe_text(updated_by["name"])
        _nonsecret_management([title, content, updated_by])
        if source_id is not None:
            from scholar_workflow.research.recommendations.source_catalog import SourceCatalog
            SourceCatalog(self).get_source(source_id)
        with self._database(write=True) as database:
            current = database.execute(
                "SELECT MAX(revision) AS revision FROM recommendation_requirements WHERE requirement_id=?",
                (requirement_id,),
            ).fetchone()["revision"] or 0
            if expected_revision != current:
                raise ResearchError("The recommendation requirement changed; read it before saving.", 5)
            record = {"requirement_id": requirement_id, "title": title, "content": content,
                      "enabled": enabled, "revision": current + 1, "updated_at": _now(),
                      "updated_by": copy.deepcopy(updated_by)}
            if source_id is None and current:
                source_id = self._requirement(database, requirement_id, current).get("source_id")
            if source_id is not None:
                record["source_id"] = source_id
            database.execute("INSERT INTO recommendation_requirements VALUES(?,?,?)",
                             (requirement_id, record["revision"], _json(record)))
        return record

    @staticmethod
    def _admit_recommendation_requirement(database, producer_id, run_id, reference):
        previous = database.execute("""SELECT uses.record FROM recommendations AS recs
            LEFT JOIN recommendation_requirement_uses AS uses ON recs.sequence=uses.sequence
            WHERE recs.producer_id=? AND recs.run_id=? ORDER BY recs.sequence LIMIT 1""",
            (producer_id, run_id)).fetchone()
        if previous is not None:
            snapshot = json.loads(previous["record"]) if previous["record"] is not None else None
            prior_reference = ({"requirement_id": snapshot["requirement_id"], "revision": snapshot["revision"]}
                               if snapshot else None)
            if prior_reference != reference:
                raise ResearchError("One producing run must retain the same recommendation requirement reference.", 5)
        if reference is None:
            return None
        requirement = RecommendationStore._requirement(database, reference["requirement_id"])
        if requirement["revision"] != reference["revision"] or not requirement["enabled"]:
            raise ResearchError("New recommendations require the current enabled requirement version.", 7)
        return requirement

    @staticmethod
    def _source_id(source_id):
        if not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,79}", source_id):
            raise ResearchError("A source needs a stable lower-case identity.")
        return source_id

    def recommendation_sources(self):
        with self._database() as database:
            row = database.execute("SELECT record FROM source_catalog WHERE name='catalog'").fetchone()
            return json.loads(row["record"]) if row else {"revision": 0, "items": []}

    def register_recommendation_source(self, source, expected_revision):
        self._source_id(source.get("source_id"))
        _nonsecret_management(source)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ResearchError("Read the source directory revision before changing it.")
        with self._database(write=True) as database:
            row = database.execute("SELECT record FROM source_catalog WHERE name='catalog'").fetchone()
            catalog = json.loads(row["record"]) if row else {"revision": 0, "items": []}
            if catalog["revision"] != expected_revision:
                raise ResearchError("The source directory changed; read it before updating.", 5)
            index = next((i for i, item in enumerate(catalog["items"]) if item["source_id"] == source["source_id"]), None)
            if index is not None and catalog["items"][index] == source:
                return {"revision": catalog["revision"], "source": source, "changed": False}
            if index is None:
                if len(catalog["items"]) >= 200:
                    raise ResearchError("The recommendation-source directory is full.", 7)
                catalog["items"].append(copy.deepcopy(source))
            else:
                catalog["items"][index] = copy.deepcopy(source)
            catalog["revision"] += 1
            database.execute("INSERT INTO source_catalog VALUES('catalog',?) ON CONFLICT(name) DO UPDATE SET record=excluded.record",
                             (_json(catalog),))
        return {"revision": catalog["revision"], "source": source, "changed": True}

    def source_context(self, source_id):
        self._source_id(source_id)
        with self._database() as database:
            row = database.execute("SELECT record FROM source_context WHERE source_id=?", (source_id,)).fetchone()
            return json.loads(row["record"]) if row else {"source_id": source_id, "revision": 0, "topics": [], "notes": ""}

    def update_source_context(self, source_id, *, expected_revision, topics, notes):
        self._source_id(source_id)
        _nonsecret_management([topics, notes])
        if (type(expected_revision) is not int or expected_revision < 0
                or not isinstance(topics, list) or len(topics) > 100
                or any(not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 120 for topic in topics)
                or not isinstance(notes, str) or len(notes) > 20000):
            raise ResearchError("Source management context is invalid.")
        for topic in topics:
            _safe_text(topic)
        with self._database(write=True) as database:
            row = database.execute("SELECT record FROM source_context WHERE source_id=?", (source_id,)).fetchone()
            current = json.loads(row["record"]) if row else {"source_id": source_id, "revision": 0, "topics": [], "notes": ""}
            if current["revision"] != expected_revision:
                raise ResearchError("The shared source context changed; read it before updating.", 5)
            current.update(revision=current["revision"] + 1, topics=list(dict.fromkeys(topics)), notes=notes, updated_at=_now())
            database.execute("INSERT INTO source_context VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET record=excluded.record",
                             (source_id, _json(current)))
        return current

    def record_source_operation(self, record):
        required = {"operation_id", "source_id", "actor", "action", "status", "summary", "observed_at", "evidence_urls"}
        if not isinstance(record, dict) or set(record) != required:
            raise ResearchError("An external-agent record needs its identity, source, actor, action, status, summary, time and evidence links.")
        self._source_id(record["source_id"])
        _nonsecret_management(record)
        if (not isinstance(record["operation_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", record["operation_id"])
                or not isinstance(record["status"], str)
                or record["status"] not in {"proposed", "reported_completed", "reported_failed", "unconfirmed"}
                or any(not isinstance(record[key], str) or not 1 <= len(record[key].strip()) <= limit
                       for key, limit in (("actor", 128), ("action", 200), ("summary", 5000)))
                or not isinstance(record["evidence_urls"], list) or len(record["evidence_urls"]) > 30):
            raise ResearchError("External-agent source record is invalid.")
        try:
            observed = datetime.fromisoformat(record["observed_at"])
            if observed.utcoffset() is None:
                raise ValueError()
        except (TypeError, ValueError):
            raise ResearchError("Source observation time requires an ISO timestamp with timezone.") from None
        data = {**copy.deepcopy(record), "evidence_urls": [channel_url_identity(url) for url in record["evidence_urls"]],
                "verification": "agent_reported"}
        with self._database(write=True) as database:
            old = database.execute("SELECT record FROM source_operations WHERE operation_id=?", (data["operation_id"],)).fetchone()
            if old:
                previous = json.loads(old["record"])
                if {key: previous[key] for key in data} != data:
                    raise ResearchError("This external-operation ID already contains a different record.", 5)
                return {"status": "unchanged", "record": previous}
            data["recorded_at"] = _now()
            database.execute("INSERT INTO source_operations VALUES(?,?,?)", (data["operation_id"], data["source_id"], _json(data)))
        return {"status": "recorded", "record": data}

    def source_history(self, source_id=None):
        if source_id is not None:
            self._source_id(source_id)
        with self._database() as database:
            sql = "SELECT record FROM source_operations"
            rows = database.execute(sql + (" WHERE source_id=?" if source_id else "") + " ORDER BY rowid DESC LIMIT 200",
                                    (source_id,) if source_id else ())
            return {"items": [json.loads(row["record"]) for row in rows]}
