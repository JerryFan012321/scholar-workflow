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


def _check_strings(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            _check_strings(child, child_key)
    elif isinstance(value, list):
        for child in value:
            _check_strings(child, key)
    elif isinstance(value, str):
        _safe_text(value, multiline=key in {"abstract_original", "abstract_zh", "description_original", "description_zh"})
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


def _review_digest(resource):
    if resource["kind"] != "paper":
        return None
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
                    digest = _digest({"producer": producer, "run_id": payload["run_id"], "item": normalized})
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
                    candidate_id = "candidate-" + hashlib.sha256(identity.encode()).hexdigest()
                    timestamp = _now()
                    source_resource = _json(normalized["resource"])
                    resource = source_resource
                    existing_candidate = database.execute(
                        "SELECT candidate_id,resource FROM candidates WHERE identity=?", (identity,),
                    ).fetchone()
                    if existing_candidate:
                        resource = _json(_merge_resource(json.loads(existing_candidate["resource"]), normalized["resource"]))
                        database.execute("UPDATE candidates SET resource=?,revision=revision+1,updated_at=? WHERE candidate_id=?",
                                         (resource, timestamp, candidate_id))
                    else:
                        database.execute("INSERT INTO candidates(candidate_id,identity,resource,revision,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                                         (candidate_id, identity, resource, 1, timestamp, timestamp))
                    database.execute("""INSERT INTO recommendations
                        (producer_id,submission_id,payload_digest,candidate_id,producer,run_id,resource,tags,channels,metrics,received_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                            producer["producer_id"], normalized["submission_id"], digest, candidate_id,
                            _json(producer), payload["run_id"], source_resource, _json(normalized["tags"]),
                            _json(normalized["channels"]), _json(normalized["metrics"]), timestamp,
                        ))
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
            for metric in json.loads(item["metrics"]):
                key = _json(metric)
                if key not in metric_keys:
                    metrics.append(metric)
                    metric_keys.add(key)
        return {"candidate_id": row["candidate_id"], "resource": resource, "tags": sorted(tags),
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

    def list_candidates(self, query="", kind=None, tag=None, producer_id=None, decision=None,
                        sort="newest", limit=40, offset=0, since=None) -> dict:
        if (not isinstance(query, str) or len(query) > 500 or kind not in KINDS | {None}
                or decision not in DECISIONS | {None} or sort not in {"newest", "oldest", "published"}
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
        if sort == "published":
            matching.sort(key=lambda row: (row["resource"].get("published_at", ""), row["created_at"]), reverse=True)
        else:
            def recommendation_time(row):
                observations = [item["received_at"] for item in row["recommendations"]]
                return (max(observations) if sort == "newest" else min(observations), row["candidate_id"])
            matching.sort(key=recommendation_time, reverse=sort == "newest")
        return {"schema_version": 1, "items": matching[offset:offset + limit], "total": len(matching),
                "facets": {"tags": sorted(all_tags), "producers": sorted(all_producers.values(), key=lambda p: p["name"]),
                           "kinds": sorted(all_kinds)}}

    def _update(self, candidate_id, expected_revision, *, decision=None, review=False):
        if type(expected_revision) is not int or expected_revision < 1:
            raise ResearchError("Recommendation revision must be a positive integer.")
        with self._database(write=True) as database:
            row = self._row(database, candidate_id)
            if row["revision"] != expected_revision:
                raise ResearchError("Recommendation changed; reload before updating your choice.", 5)
            if review:
                resource = json.loads(row["resource"])
                if resource["kind"] != "paper" or not all(resource.get(key, "").strip() for key in ("abstract_original", "abstract_zh")):
                    raise ResearchError("A complete original abstract and Chinese translation are required for review.", 7)
                database.execute("UPDATE candidates SET review_digest=?,revision=revision+1,updated_at=? WHERE candidate_id=?",
                                 (_review_digest(resource), _now(), candidate_id))
            else:
                database.execute("UPDATE candidates SET decision=?,revision=revision+1,updated_at=? WHERE candidate_id=?",
                                 (decision, _now(), candidate_id))
            return self._candidate(database, self._row(database, candidate_id))

    def set_decision(self, candidate_id, decision, expected_revision):
        if decision not in DECISIONS:
            raise ResearchError("Recommendation decision is invalid.")
        return self._update(candidate_id, expected_revision, decision=decision)

    def review_candidate(self, candidate_id, expected_revision):
        return self._update(candidate_id, expected_revision, review=True)

    def prepare_handoff(self):
        with self._database() as database:
            items = [self._candidate(database, row) for row in database.execute(
                "SELECT * FROM candidates WHERE decision='selected' ORDER BY created_at,candidate_id")]
        if any(row["resource"]["kind"] == "paper" and not row["abstract_reviewed"] for row in items):
            raise ResearchError("Review every selected paper's complete translated abstract before preparing ingestion.", 7)
        pool_id = "pool-" + hashlib.sha256(str(self.state_dir).encode("utf-8")).hexdigest()[:32]
        return {"schema_version": 1, "status": "ready", "pool_id": pool_id, "items": items}
