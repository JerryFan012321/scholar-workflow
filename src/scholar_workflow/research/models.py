"""Bounded non-secret subscription and observation contracts."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

MAX_CHANNELS = 1000
MAX_ITEMS = 20000
MAX_EVENTS = 20000
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_STATE_BYTES = 16 * 1024 * 1024
CHANNEL_FIELDS = {
    "channel_id", "name", "publisher", "publisher_kind", "kind", "url", "enabled", "topics",
}
_SECRET_FIELDS = {
    "password", "passphrase", "token", "secret", "api_key", "apikey", "authorization",
    "private_key", "access_token", "refresh_token", "credential", "credentials",
}
_SLUG = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
_HASH = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_SECRET_TEXT = re.compile(
    r"-----BEGIN (?:[A-Z ]*PRIVATE KEY|PGP PRIVATE KEY)|"
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})|"
    r"\b(?:password|api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
DIAGNOSTICS = {
    "acquisition_failed": "The channel could not be acquired completely.",
    "baseline_required": "A complete successful baseline is required before an unchanged response.",
    "network_error": "The public source could not be reached; check connectivity and retry.",
    "http_error": "The public source returned an unsuccessful HTTP status.",
    "limit_exceeded": "The response exceeded the supported size or item limit.",
    "incomplete_pagination": "Not all result pages were acquired; no partial checkpoint was accepted.",
    "unsafe_url": "A source, redirect or pagination URL failed the public URL safety checks.",
    "invalid_response": "The response did not contain valid complete source metadata.",
    "unsafe_xml": "The source XML contains unsupported declarations or entities.",
    "unsupported_content": "The source did not provide supported readable metadata or text.",
    "invalid_channel": "The channel does not match the expected source URL or provider contract.",
    "unsupported_proxy": "The configured proxy scheme is unsupported; no direct fallback was attempted.",
    "unsupported_client": "An injected client cannot provide the required safe acquisition boundary.",
}


class ResearchError(ValueError):
    """A public failure whose message never includes untrusted values or paths."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def bounded_tree(value, *, budget=150000, depth=0, ancestors=frozenset()):
    """Reject alias cycles and excessive nesting before traversing untrusted records."""
    remaining = [budget]

    def visit(node, level, parents):
        remaining[0] -= 1
        if remaining[0] < 0 or level > 18:
            raise ResearchError("Research record exceeds the supported structure limits.")
        if isinstance(node, (dict, list)):
            if id(node) in parents:
                raise ResearchError("Research record contains recursive aliases.")
            parents = parents | {id(node)}
            if isinstance(node, dict):
                if any(not isinstance(key, str) for key in node):
                    raise ResearchError("Research field names must be strings.")
                children = node.values()
            else:
                children = node
            for child in children:
                visit(child, level + 1, parents)
        elif node is not None and type(node) not in (str, int, bool):
            raise ResearchError("Research record contains an unsupported value.")

    visit(value, depth, ancestors)


def text(value, label, *, limit=512):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ResearchError(f"Invalid research {label}.")
    if _SECRET_TEXT.search(value):
        raise ResearchError("Credential-like material is not allowed in research records.", 7)
    return value


def identifier(value, label="channel ID"):
    value = text(value, label, limit=128)
    if not _SLUG.fullmatch(value):
        raise ResearchError(f"Invalid research {label}.")
    return value


def public_url(value):
    value = text(value, "public URL", limit=4096)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        credentials = parsed.username is not None or parsed.password is not None
    except ValueError:
        raise ResearchError("Invalid research public URL.") from None
    if (parsed.scheme != "https" or not host or "#" in value or credentials
            or parsed.netloc.endswith(":") or port == 0):
        raise ResearchError("Research URLs must be public HTTPS without credentials or fragments.", 7)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        normalized = host.casefold().rstrip(".")
        if ("." not in normalized or normalized == "localhost"
                or normalized.endswith((".localhost", ".local", ".internal"))
                or "%" in host or "\\" in value):
            raise ResearchError("Research URLs must identify public hosts.", 7)
        try:
            ascii_host = normalized.encode("idna").decode("ascii")
        except UnicodeError:
            raise ResearchError("Invalid research public hostname.", 7) from None
        if (len(ascii_host) > 253 or any(not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part,
        ) for part in ascii_host.split(".")) or all(part.isdigit() for part in ascii_host.split("."))):
            raise ResearchError("Invalid research public hostname.", 7)
    else:
        if (not address.is_global or address.is_multicast or address.is_reserved
                or getattr(address, "is_site_local", False)):
            raise ResearchError("Research URLs must identify public hosts.", 7)
    sensitive_keys = _SECRET_FIELDS | {
        "key", "auth", "signature", "sig", "x-amz-signature", "x-goog-signature",
        "x-amz-credential", "x-amz-security-token",
    }
    query_keys = [unquote(key).casefold().replace("-", "_")
                  for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    if any(key in {name.replace("-", "_") for name in sensitive_keys}
           or key.endswith(("token", "secret", "password", "signature", "credential", "api_key"))
           for key in query_keys):
        raise ResearchError("Credential-bearing research URLs are not allowed.", 7)
    return value


def channel_url_identity(value):
    """One URL has one channel identity despite host/default-port/empty-path spelling."""
    parsed = urlsplit(public_url(value))
    host = parsed.hostname.casefold().rstrip(".")
    host = "[" + host + "]" if ":" in host else host.encode("idna").decode("ascii")
    netloc = host + (":" + str(parsed.port) if parsed.port not in (None, 443) else "")
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def _fields(record, allowed, label):
    if not isinstance(record, dict):
        raise ResearchError(f"Invalid research {label}.")
    unknown = set(record) - allowed
    if any(key.casefold().replace("-", "_") in _SECRET_FIELDS for key in unknown):
        raise ResearchError("Secret fields are not allowed in research records.", 7)
    if unknown:
        raise ResearchError(f"Unknown research {label} fields.")


def validate_channel(record):
    """Normalize one public channel; it is not a Vault Source or a paper feed."""
    bounded_tree(record, budget=1000)
    _fields(record, CHANNEL_FIELDS, "channel")
    required = CHANNEL_FIELDS - {"enabled", "topics"}
    if not required <= record.keys():
        raise ResearchError("Research channel is missing required fields.")
    result = {
        "channel_id": identifier(record["channel_id"]),
        "name": text(record["name"], "channel name", limit=300),
        "publisher": text(record["publisher"], "publisher", limit=300),
        "publisher_kind": record["publisher_kind"], "kind": record["kind"],
        "url": public_url(record["url"]), "enabled": record.get("enabled", True),
        "topics": record.get("topics", []),
    }
    if (not isinstance(result["publisher_kind"], str)
            or result["publisher_kind"] not in {"researcher", "lab", "company", "team", "other"}):
        raise ResearchError("Unknown research publisher kind.")
    if (not isinstance(result["kind"], str)
            or result["kind"] not in {"rss", "atom", "webpage", "github_releases", "hf_models"}):
        raise ResearchError("Unknown research channel kind.")
    if type(result["enabled"]) is not bool:
        raise ResearchError("Research channel enabled must be a boolean.")
    topics = result["topics"]
    if not isinstance(topics, list) or len(topics) > 32:
        raise ResearchError("Invalid research topics.")
    result["topics"] = [text(topic, "topic", limit=200) for topic in topics]
    if len(set(result["topics"])) != len(result["topics"]):
        raise ResearchError("Research topics must not repeat.")
    return result


def validate_registry(document):
    bounded_tree(document)
    if (not isinstance(document, dict) or set(document) != {"schema_version", "channels"}
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or not isinstance(document["channels"], list)
            or len(document["channels"]) > MAX_CHANNELS):
        raise ResearchError("Invalid research source registry.")
    channels = [validate_channel(channel) for channel in document["channels"]]
    if len({channel["channel_id"] for channel in channels}) != len(channels):
        raise ResearchError("Research channel IDs must be unique.")
    if len({channel_url_identity(channel["url"]) for channel in channels}) != len(channels):
        raise ResearchError("A research URL is already registered under another channel ID.", 5)
    return {"schema_version": 1, "channels": channels}


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def checked_time(value):
    value = text(value, "observation time", limit=64)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ResearchError("Research observation time must be an ISO timestamp.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchError("Research observation time requires a timezone.")
    return parsed


def validate_item(record):
    allowed = {"item_id", "url", "title", "content_digest", "published_at", "updated_at", "version"}
    _fields(record, allowed, "observed item")
    if not {"item_id", "url", "title", "content_digest"} <= record.keys():
        raise ResearchError("Observed research item is missing required fields.")
    content_digest = text(record["content_digest"], "content digest", limit=71)
    if not _HASH.fullmatch(content_digest):
        raise ResearchError("Invalid research content digest.")
    result = {"item_id": text(record["item_id"], "item ID", limit=512),
              "url": public_url(record["url"]), "title": text(record["title"], "title", limit=1000),
              "content_digest": "sha256:" + content_digest.removeprefix("sha256:")}
    for key in ("published_at", "updated_at", "version"):
        if key in record and record[key] is not None:
            result[key] = text(record[key], "publisher date or version", limit=256)
    return result


def validate_observation(record):
    bounded_tree(record)
    allowed = {"status", "items", "etag", "last_modified", "diagnostic"}
    _fields(record, allowed, "observation")
    if (not isinstance(record.get("status"), str)
            or record.get("status") not in {"ok", "not_modified", "failed"}):
        raise ResearchError("Unknown research observation status.")
    items = record.get("items", [])
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ResearchError("Research observation exceeds the supported item count.")
    if record["status"] != "ok" and items:
        raise ResearchError("Failed or unchanged observations cannot contain partial items.")
    result = {"status": record["status"], "items": [validate_item(item) for item in items]}
    if len({item["item_id"] for item in result["items"]}) != len(items):
        raise ResearchError("Observed research item IDs must be unique within a channel.")
    for key in ("etag", "last_modified"):
        if record.get(key) is not None:
            result[key] = text(record[key], "HTTP validator", limit=1024)
    if "diagnostic" in record:
        # Transport diagnostics can contain URL credentials or response fragments.
        # Preserve only recognized codes, paired with a locally fixed message.
        supplied = record["diagnostic"]
        code = supplied.get("code") if isinstance(supplied, dict) else None
        if not isinstance(code, str) or code not in DIAGNOSTICS or code == "baseline_required":
            code = "acquisition_failed"
        result["diagnostic"] = {"code": code, "message": DIAGNOSTICS[code]}
    return result


def validate_state(document):
    """Validate persisted state, including injected/manual edits, before any disclosure."""
    bounded_tree(document, budget=500000)
    if (not isinstance(document, dict) or set(document) != {"schema_version", "channels", "events"}
            or type(document.get("schema_version")) is not int or document["schema_version"] != 1
            or not isinstance(document["channels"], dict)
            or len(document["channels"]) > MAX_CHANNELS or not isinstance(document["events"], list)
            or len(document["events"]) > MAX_EVENTS):
        raise ResearchError("Invalid research tracking state.")
    channel_fields = {"config_revision", "initialized", "last_checked_at", "last_success_at",
                      "last_status", "last_observation_digest", "items", "etag", "last_modified",
                      "diagnostic", "window_item_count", "last_observation_config_revision"}
    event_fields = {"event_id", "channel_id", "item_id", "kind", "observed_at", "item",
                    "disposition", "sequence", "config_revision", "source"}
    total_items = 0
    for channel_id, state in document["channels"].items():
        identifier(channel_id)
        if (not isinstance(state, dict) or set(state) - channel_fields
                or not {"config_revision", "initialized", "last_checked_at", "last_success_at",
                        "last_status", "last_observation_digest", "items", "window_item_count",
                        "last_observation_config_revision"}
                <= state.keys()):
            raise ResearchError("Invalid research channel state.")
        for key in ("config_revision", "last_observation_digest", "last_observation_config_revision"):
            if not isinstance(state[key], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", state[key]):
                raise ResearchError("Invalid research state revision.")
        if type(state["initialized"]) is not bool or not isinstance(state["items"], dict):
            raise ResearchError("Invalid research initialization state.")
        if (not isinstance(state["last_status"], str)
                or state["last_status"] not in {"baseline", "observed", "not_modified", "failed"}):
            raise ResearchError("Invalid research checkpoint status.")
        checked_time(state["last_checked_at"])
        if (state["last_success_at"] is not None
                and checked_time(state["last_success_at"]) > checked_time(state["last_checked_at"])):
            raise ResearchError("Research success checkpoint exceeds observation time.")
        if state["initialized"] != (state["last_success_at"] is not None):
            raise ResearchError("Research initialization checkpoint is inconsistent.")
        if type(state["window_item_count"]) is not int or not 0 <= state["window_item_count"] <= MAX_ITEMS:
            raise ResearchError("Invalid research observed-window count.")
        for key in ("etag", "last_modified"):
            if key in state:
                text(state[key], "HTTP validator", limit=1024)
        if "diagnostic" in state:
            _validate_diagnostic(state["diagnostic"])
        total_items += len(state["items"])
        if total_items > MAX_ITEMS:
            raise ResearchError("Research state exceeds the supported item count.")
        for item_id, seen in state["items"].items():
            if (not isinstance(seen, dict) or set(seen) != {"item", "sequence"}
                    or type(seen["sequence"]) is not int or seen["sequence"] < 1
                    or seen["sequence"] > 1000000000 or validate_item(seen["item"])["item_id"] != item_id):
                raise ResearchError("Invalid research item checkpoint.")
    event_ids = set()
    for event in document["events"]:
        if not isinstance(event, dict) or set(event) != event_fields:
            raise ResearchError("Invalid research event.")
        if not isinstance(event["event_id"], str) or not re.fullmatch(r"event-[0-9a-f]{64}", event["event_id"]):
            raise ResearchError("Invalid research event ID.")
        if event["event_id"] in event_ids:
            raise ResearchError("Duplicate research event ID.")
        event_ids.add(event["event_id"])
        identifier(event["channel_id"])
        if event["channel_id"] not in document["channels"]:
            raise ResearchError("Research event has no channel checkpoint.")
        if (not isinstance(event["kind"], str) or event["kind"] not in {"discovered", "new", "updated"}
                or not isinstance(event["disposition"], str)
                or event["disposition"] not in {"unread", "read", "selected", "ignored"}
                or type(event["sequence"]) is not int or not 1 <= event["sequence"] <= 1000000000
                or not isinstance(event["config_revision"], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", event["config_revision"])):
            raise ResearchError("Invalid research event metadata.")
        checked_time(event["observed_at"])
        if validate_item(event["item"])["item_id"] != event["item_id"]:
            raise ResearchError("Research event item identity is inconsistent.")
        source = event["source"]
        if not isinstance(source, dict) or set(source) != {"name", "publisher", "url"}:
            raise ResearchError("Invalid research event source snapshot.")
        text(source["name"], "channel name", limit=300)
        text(source["publisher"], "publisher", limit=300)
        public_url(source["url"])
    return document


def _validate_diagnostic(record):
    if (not isinstance(record, dict) or set(record) != {"code", "message"}
            or not isinstance(record["code"], str) or record["code"] not in DIAGNOSTICS):
        raise ResearchError("Invalid research diagnostic.")
    if record["message"] != DIAGNOSTICS[record["code"]]:
        raise ResearchError("Invalid research diagnostic message.")
