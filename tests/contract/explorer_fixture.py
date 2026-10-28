"""Explicit synthetic dependencies for preserved explorer HTTP/browser contracts."""

from urllib.parse import urlsplit

from scholar_workflow.adapters.exploration_readers import ReaderUnavailable
from scholar_workflow.adapters.knowledge_explorer import make_server
from scholar_workflow.knowledge.exploration import ExplorationError
from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment


class EmptyReferences:
    def fields(self):
        return {"fields": [], "diagnostics": []}

    def _denied(self, *_args, **_kwargs):
        raise ExplorationError("No registered units were supplied by this fixture", 7)

    units = current_unit = reference = _denied


class EmptyVaults:
    def list_connections(self):
        return {"revision": None, "connections": [], "diagnostics": []}

    def _denied(self, *_args, **_kwargs):
        raise ExplorationError("This fixture cannot select or connect external folders", 7)

    choose = preview_adjustments = connect = documents = preview_document = _denied


class DeniedReader:
    def handles(self, uri):
        return urlsplit(uri).scheme in {"obsidian", "zotero"}

    def availability(self, *_args):
        return {"native_available": False, "native_reason": "No reader supplied by this fixture"}

    def require_current(self, *_args):
        raise ReaderUnavailable("No reader supplied by this fixture", "fixture_reader")


def fixture_server(root, **kwargs):
    """Use the real adapter, without ambient services or surviving request threads."""
    kwargs.setdefault("environment", ExplorerEnvironment(state_root=root / ".fixture-state"))
    kwargs.setdefault("reference_service", EmptyReferences())
    kwargs.setdefault("reader_gate", DeniedReader())
    kwargs.setdefault("vault_service", EmptyVaults())
    server, token = make_server(root, **kwargs)
    # server_close must finish request handlers before monkeypatches are restored.
    server.daemon_threads = False
    return server, token
