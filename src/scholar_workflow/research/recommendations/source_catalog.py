"""Portable source packages and native-agent guides; never a tool executor."""

from __future__ import annotations

import copy
import json
import re
from importlib.resources import files
from urllib.parse import urlsplit, urlunsplit

from scholar_workflow.research.models import ResearchError, bounded_tree, public_url

_SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,79}\Z")
_SYMBOLIC_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
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
    "plugin_version",
    "agent",
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


def _operation_io(value):
    """Inspect bounded descriptions/schemas without interpreting or dereferencing them."""
    if not isinstance(value, (str, dict)):
        raise ResearchError("Source operation inputs and outputs need text or a JSON object.")

    def visit(node):
        if isinstance(node, dict):
            for key, item in node.items():
                _text(key, limit=200)
                if isinstance(item, str):
                    _text(f"{key}={item}", limit=4201, multiline=True)
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, str):
            _text(node, limit=4000, multiline=True)
            if node.startswith(("http:", "https:")):
                _url(node, documentation=True)

    visit(value)


def _agent(value):
    if (
        not isinstance(value, dict)
        or set(value) - {"connection_name", "instructions", "operations"}
        or not {"instructions", "operations"} <= value.keys()
    ):
        raise ResearchError("Source agent guidance needs instructions and operations.")
    _text(value["instructions"], limit=6000, multiline=True)
    if "connection_name" in value:
        _text(value["connection_name"], limit=128)
        if not _SYMBOLIC_NAME.fullmatch(value["connection_name"]):
            raise ResearchError("Source connection name must be symbolic, not a command or path.")
    operations = value["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 50:
        raise ResearchError("Source agent guidance needs a bounded nonempty operation list.")
    identifiers = set()
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation) - {"operation_id", "description", "tool_name", "effect", "inputs", "outputs"}
            or not {"operation_id", "description", "effect", "inputs", "outputs"} <= operation.keys()
        ):
            raise ResearchError("Source operation contains unsupported or missing fields.")
        identifier = operation["operation_id"]
        if not isinstance(identifier, str) or not _SOURCE_ID.fullmatch(identifier):
            raise ResearchError("Source operation ID must be a stable lowercase identifier.")
        if identifier in identifiers:
            raise ResearchError("Source operation IDs must not repeat.")
        identifiers.add(identifier)
        _text(operation["description"], limit=3000, multiline=True)
        if "tool_name" in operation:
            _text(operation["tool_name"], limit=128)
            if not _SYMBOLIC_NAME.fullmatch(operation["tool_name"]):
                raise ResearchError("Source native tool hint must be a symbolic name.")
        if not isinstance(operation["effect"], str) or operation["effect"] not in {"read", "write"}:
            raise ResearchError("Source operation must declare read or write effects.")
        _operation_io(operation["inputs"])
        _operation_io(operation["outputs"])


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
    if len(json.dumps(source, ensure_ascii=False).encode("utf-8")) > 128 * 1024:
        raise ResearchError("Source definition exceeds the supported size limit.", 7)
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
    if "plugin_version" in source and (
        not isinstance(source["plugin_version"], str)
        or len(source["plugin_version"]) > 100
        or not _SEMVER.fullmatch(source["plugin_version"])
    ):
        raise ResearchError("Source plugin version must use semantic versioning.")
    if "agent" in source:
        _agent(source["agent"])
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
        "plugin_ready": bool(
            source.get("plugin_version")
            and source.get("agent", {}).get("operations")
            and source["status"] == "available"
            and source["enabled"]
        ),
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
        overrides = local.get("overrides", {})
        if (
            not isinstance(overrides, dict)
            or len(overrides) > 200
            or any(
                not isinstance(source_id, str)
                or not _SOURCE_ID.fullmatch(source_id)
                or not isinstance(override, dict)
                or set(override) != {"enabled"}
                or type(override["enabled"]) is not bool
                for source_id, override in overrides.items()
            )
        ):
            raise ResearchError("Local recommendation source enable states are invalid.", 7)
        for source in builtins:
            if source["source_id"] in overrides:
                enabled = overrides[source["source_id"]]["enabled"]
                if source["status"] == "planned" and enabled:
                    raise ResearchError("A planned source cannot be enabled.", 7)
                source["enabled"] = enabled
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

    def export_plugin(self, source_id):
        """Export the portable definition, not host enable overrides or projections."""
        source = self.get_source(source_id)
        if source["origin"] == "builtin":
            source = next(item for item in builtin_sources() if item["source_id"] == source_id)
        else:
            source = {key: value for key, value in source.items() if key in _FIELDS}
        return {"schema_version": 1, "source": copy.deepcopy(source)}

    def import_plugin(self, package, expected_revision):
        """Import data only; host tools, credentials and network access remain external."""
        bounded_tree(package, budget=5000)
        if (
            not isinstance(package, dict)
            or set(package) != {"schema_version", "source"}
            or type(package["schema_version"]) is not int
            or package["schema_version"] != 1
            or not isinstance(package["source"], dict)
        ):
            raise ResearchError("Source plugin package needs schema_version 1 and one source.")
        source = package["source"]
        if source.get("source_id") in {item["source_id"] for item in builtin_sources()}:
            raise ResearchError("A source plugin cannot replace a packaged builtin definition.", 5)
        source = validate_source(source)
        if "plugin_version" not in source or "agent" not in source:
            raise ResearchError("A source plugin package needs its version and complete agent guidance.")
        return self.register(source, expected_revision=expected_revision)

    def set_enabled(self, source_id, enabled, expected_revision):
        current = self.list_sources()
        if type(expected_revision) is not int or expected_revision != current["revision"]:
            raise ResearchError("Recommendation sources changed; read them before updating.", 5)
        if type(enabled) is not bool:
            raise ResearchError("A source enabled state must be a boolean.")
        source = self.get_source(source_id)
        if enabled and source["status"] != "available":
            raise ResearchError("A planned source cannot be enabled.", 7)
        if source["origin"] == "registered":
            definition = self.export_plugin(source_id)["source"]
            definition["enabled"] = enabled
            return self.register(definition, expected_revision=expected_revision)
        definition = self.export_plugin(source_id)["source"]
        receipt = self.store.set_builtin_source_enabled(
            source_id, enabled=enabled, expected_revision=expected_revision,
            default_enabled=definition["enabled"],
        )
        definition["enabled"] = enabled
        return {**receipt, "source": definition}

    def guide(self, source_id, *, profile="personal"):
        """Join current source instructions and shared records without provider access."""
        if profile not in {"personal", "test"}:
            raise ResearchError("Unknown recommendation profile.")
        catalog = self.list_sources()
        source = next((item for item in catalog["items"] if item["source_id"] == source_id), None)
        if source is None:
            raise ResearchError("The requested recommendation source is not registered.", 3)
        return {
            "profile": profile,
            "source": source,
            "catalog_revision": catalog["revision"],
            "requirements": self.store.list_requirements(source_id=source_id),
            "context": self.store.source_context(source_id),
            "recent_operations": self.store.source_history(source_id),
            "discovery": {"method": "host_native", "require_current_tool_schema": True},
            "submission": {
                "schema": f"scholar-research recommendations --profile {profile} schema",
                "entry": f"scholar-research recommendations --profile {profile} submit",
            },
        }
