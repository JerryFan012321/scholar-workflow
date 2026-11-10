"""Non-secret source descriptions for any external agent; never a tool executor."""

from __future__ import annotations

import copy
import json
import re
from importlib.resources import files
from urllib.parse import urlsplit, urlunsplit

from scholar_workflow.research.models import ResearchError, bounded_tree, public_url

_SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,79}\Z")
_PRIVATE_PATH = re.compile(
    r"(?:^|[\s=:(])(?:/(?:Users|home|private|tmp|var|etc|root|Volumes)/|~/|[A-Za-z]:[\\/]|\\\\)"
)
_SECRET = re.compile(
    r"-----BEGIN (?:[A-Z ]*PRIVATE KEY|PGP PRIVATE KEY)|"
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})|"
    r"\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|authorization|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_FIELDS = {
    "source_id",
    "name",
    "purpose",
    "status",
    "enabled",
    "scope",
    "interfaces",
    "capabilities",
    "documentation",
    "auth",
}


def _text(value, *, limit=300, multiline=False):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(
            ord(char) == 127 or (ord(char) < 32 and (not multiline or char not in "\n\t"))
            for char in value
        )
    ):
        raise ResearchError("Source descriptor text is invalid.")
    if _SECRET.search(value) or _PRIVATE_PATH.search(value) or value.startswith(("/", "~")):
        raise ResearchError(
            "Source descriptors cannot contain credentials or private absolute paths.", 7
        )
    return value


def _url(value, *, documentation=False):
    if not isinstance(value, str):
        raise ResearchError("Source descriptor URL must be a string.")
    try:
        parts = urlsplit(value)
    except ValueError:
        raise ResearchError("Source descriptor URL is invalid.") from None
    fragment = parts.fragment
    normalized = public_url(urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")))
    if fragment:
        if not documentation:
            raise ResearchError("Source interface URLs cannot contain fragments.", 7)
        _text(fragment, limit=300)
    return normalized + ("#" + fragment if fragment else "")


def validate_source(value, *, builtin=False):
    """Validate data only; registration does not configure any external harness."""
    bounded_tree(value, budget=5000)
    allowed = _FIELDS | ({"execution"} if builtin else set())
    if (
        not isinstance(value, dict)
        or set(value) - allowed
        or not {"source_id", "name", "purpose", "status", "interfaces", "capabilities"}
        <= value.keys()
    ):
        raise ResearchError("Source descriptor contains unsupported or missing fields.")
    source = copy.deepcopy(value)
    source_id = _text(source["source_id"], limit=80)
    if not _SOURCE_ID.fullmatch(source_id):
        raise ResearchError("Source ID must be a stable lowercase identifier.")
    _text(source["name"], limit=300)
    _text(source["purpose"], limit=3000, multiline=True)
    if not isinstance(source["status"], str) or source["status"] not in {"available", "planned"}:
        raise ResearchError("Unknown source definition status.")
    source.setdefault("enabled", source["status"] == "available")
    if type(source["enabled"]) is not bool or (source["status"] == "planned" and source["enabled"]):
        raise ResearchError("A planned source cannot be enabled or presented as integrated.")
    source.setdefault("scope", "selected_channel")
    _text(source["scope"], limit=200)
    interfaces = source["interfaces"]
    if not isinstance(interfaces, list) or not 1 <= len(interfaces) <= 8:
        raise ResearchError("Source interfaces must be a bounded nonempty list.")
    for interface in interfaces:
        if (
            not isinstance(interface, dict)
            or set(interface) - {"kind", "url", "instructions"}
            or not isinstance(interface.get("kind"), str)
            or interface["kind"] not in {"mcp", "api", "feed", "cli"}
        ):
            raise ResearchError(
                "A source interface must describe MCP, API, feed or native CLI use."
            )
        if interface["kind"] == "cli":
            if "instructions" not in interface:
                raise ResearchError("A native CLI interface needs human-readable instructions.")
        elif "url" not in interface:
            raise ResearchError("A network source interface needs its public URL.")
        if "url" in interface:
            interface["url"] = _url(interface["url"])
        if "instructions" in interface:
            _text(interface["instructions"], limit=3000, multiline=True)
    capabilities = source["capabilities"]
    if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 50:
        raise ResearchError("Source capabilities must be a bounded nonempty list.")
    for capability in capabilities:
        _text(capability, limit=200)
    if len(set(capabilities)) != len(capabilities):
        raise ResearchError("Source capability descriptions must not repeat.")
    source.setdefault("documentation", [])
    if not isinstance(source["documentation"], list) or len(source["documentation"]) > 20:
        raise ResearchError("Source documentation must be a bounded URL list.")
    source["documentation"] = [_url(url, documentation=True) for url in source["documentation"]]
    if "auth" in source:
        auth = source["auth"]
        if (
            not isinstance(auth, dict)
            or set(auth) - {"method", "reference", "instructions"}
            or not {"method", "instructions"} <= auth.keys()
        ):
            raise ResearchError(
                "Source authentication stores instructions and a reference, never credentials."
            )
        _text(auth["method"], limit=100)
        _text(auth["instructions"], limit=3000, multiline=True)
        if "reference" in auth:
            _text(auth["reference"], limit=200)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", auth["reference"]):
                raise ResearchError(
                    "Source credential reference must be symbolic, not a secret or private path."
                )
    if builtin and "execution" in source:
        execution = source["execution"]
        if (
            not isinstance(execution, dict)
            or set(execution) - {"kind", "host_connection_name", "entry"}
            or not isinstance(execution.get("kind"), str)
            or execution["kind"] not in {"native_mcp", "existing_aggregator", "planned"}
        ):
            raise ResearchError("Builtin source execution description is invalid.")
        for text in execution.values():
            _text(text, limit=200)
    return source


def builtin_sources():
    """Read package definitions; no account, configuration file or network lookup."""
    try:
        raw = files(__package__).joinpath("source_catalog.json").read_text(encoding="utf-8")
        if len(raw.encode()) > 256 * 1024:
            raise ValueError()
        document = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        raise ResearchError("The installed source catalog definition is unavailable.", 3) from None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or not isinstance(document.get("sources"), list)
    ):
        raise ResearchError("The installed source catalog definition is invalid.", 3)
    result = [validate_source(source, builtin=True) for source in document["sources"]]
    if len({source["source_id"] for source in result}) != len(result):
        raise ResearchError("The installed source catalog contains duplicate source IDs.", 3)
    return result


def _view(source, origin):
    return {
        **copy.deepcopy(source),
        "origin": origin,
        "connection_status": "not_implemented" if source["status"] == "planned" else "not_checked",
    }


class SourceCatalog:
    """Package builtins plus explicit registrations in the existing candidate pool."""

    def __init__(self, store):
        self.store = store

    def list_sources(self):
        builtins = builtin_sources()
        identifiers = {source["source_id"] for source in builtins}
        local = self.store.recommendation_sources()
        if (
            not isinstance(local, dict)
            or type(local.get("revision")) is not int
            or local["revision"] < 0
            or not isinstance(local.get("items"), list)
            or len(local["items"]) > 200
        ):
            raise ResearchError("Local recommendation source registrations are invalid.", 7)
        registered = [validate_source(source) for source in local["items"]]
        if identifiers & {source["source_id"] for source in registered} or len(
            {source["source_id"] for source in registered}
        ) != len(registered):
            raise ResearchError(
                "Local source registrations conflict with an existing source identity.", 5
            )
        return {
            "schema_version": 1,
            "revision": local["revision"],
            "items": [_view(source, "builtin") for source in builtins]
            + [_view(source, "registered") for source in registered],
        }

    def get_source(self, source_id):
        if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
            raise ResearchError("Invalid recommendation source ID.")
        source = next(
            (item for item in self.list_sources()["items"] if item["source_id"] == source_id), None
        )
        if source is None:
            raise ResearchError("The requested recommendation source is not registered.", 3)
        return source

    def register(self, source, expected_revision):
        current = self.list_sources()
        if type(expected_revision) is not int or expected_revision != current["revision"]:
            raise ResearchError("Recommendation sources changed; read them before registering.", 5)
        source = validate_source(source)
        if source["source_id"] in {
            item["source_id"] for item in current["items"] if item["origin"] == "builtin"
        }:
            raise ResearchError(
                "A registered source cannot replace a packaged builtin definition.", 5
            )
        return self.store.register_recommendation_source(
            source, expected_revision=expected_revision
        )
