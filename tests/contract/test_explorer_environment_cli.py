"""Public commands make test scope explicit before any file or native access."""

from click.testing import CliRunner

from scholar_workflow.cli import main
from tests.contract.test_knowledge_ownership import (
    FIELD_A,
    PAPER,
    SOURCE_A,
    _add_source,
    ownership_scope,  # noqa: F401
)


def test_explore_test_mode_requires_explicit_context_before_server(tmp_path, monkeypatch):
    from scholar_workflow.adapters import knowledge_explorer

    def forbidden(*_args, **_kwargs):
        raise AssertionError("A server must not start without an explicit test context")

    monkeypatch.setattr(knowledge_explorer, "make_server", forbidden)
    result = CliRunner().invoke(main, ["knowledge", "explore", "--root", str(tmp_path),
                                      "--environment", "test", "--no-open"])
    assert result.exit_code == 7, result.output
    assert "explicit" in result.output


def test_test_query_refuses_root_outside_allowlist(tmp_path):
    vault, outside = tmp_path / "test-vault", tmp_path / "other-vault"
    vault.mkdir()
    outside.mkdir()
    result = CliRunner().invoke(main, ["knowledge", "exploration-query", "--root", str(outside),
        "--environment", "test", "--state-root", str(tmp_path / "state"),
        "--test-root", str(vault)])
    assert result.exit_code == 7, result.output
    assert not (outside / ".scholar-workflow").exists()


def test_test_explore_passes_explicit_environment_without_changing_process(tmp_path, monkeypatch):
    import os

    from scholar_workflow.adapters import knowledge_explorer

    vault = tmp_path / "test-vault"
    vault.mkdir()
    ambient = str(tmp_path / "personal-state")
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", ambient)
    received = {}

    class Server:
        server_address = ("127.0.0.1", 12345)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            received["closed"] = True

    def make_server(root, **kwargs):
        received.update(root=root, **kwargs)
        return Server(), "synthetic-token"

    monkeypatch.setattr(knowledge_explorer, "make_server", make_server)
    result = CliRunner().invoke(main, ["knowledge", "explore", "--root", str(vault),
        "--environment", "test", "--state-root", str(tmp_path / "state"),
        "--test-root", str(vault), "--no-open"])
    assert result.exit_code == 0, result.output
    assert received["environment"].is_test
    assert received["environment"].registry_path == tmp_path / "state/hub/sources.json"
    assert received["closed"]
    assert os.environ["SCHOLAR_WORKFLOW_HOME"] == ambient


def test_all_exploration_commands_describe_environment_options():
    for command in ("explore", "exploration-init", "exploration-apply", "exploration-import",
                    "exploration-query", "exploration-export"):
        result = CliRunner().invoke(main, ["knowledge", command, "--help"])
        assert result.exit_code == 0
        assert "--environment" in result.output
        assert "--test-root" in result.output


def test_offline_reference_service_never_resolves_native_readers_or_live_zotero(
        ownership_scope, monkeypatch):  # noqa: F811
    from scholar_workflow.adapters import zotero_local
    from scholar_workflow.knowledge.exploration import default_data
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Test references must not consult real readers or Zotero")

    monkeypatch.setattr(zotero_local, "ZoteroLocalAdapter", forbidden)
    service = ExplorationReferenceService(ownership_scope.registry.path,
        resolve_reader=False, enrich_resources=False)
    assert service.fields()["fields"]
    assert service.units(SOURCE_A, FIELD_A)["units"]
    ref = {"source_id": SOURCE_A, "object_id": PAPER}
    assert service.current_unit(ref)["resource_id"] == PAPER
    proposed = service.reference(ownership_scope.root, default_data(), SOURCE_A, FIELD_A, [ref])
    assert proposed["works"][0]["entity_ref"] == ref


def test_changed_registry_is_checked_before_any_foreign_source_read(ownership_scope, monkeypatch):  # noqa: F811
    import pytest

    from scholar_workflow.knowledge.exploration import ExplorationError
    from scholar_workflow.workflows import knowledge_ownership
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService

    scope = ownership_scope
    selected = scope.root
    reads = []
    changed = False
    original = knowledge_ownership._read_declaration

    def validate_root(root):
        if root != selected and selected not in root.parents:
            raise ExplorationError("Outside test boundary", 7)

    def observed_read(root, relative, limit):
        nonlocal changed
        if root == scope.registry.path.parent and relative == scope.registry.path.name and not changed:
            changed = True
            _add_source(scope)
        if root != scope.registry.path.parent:
            reads.append(root)
            assert root == selected, "Foreign Source was read before its test-boundary check"
        return original(root, relative, limit)

    service = ExplorationReferenceService(scope.registry.path, resolve_reader=False,
        enrich_resources=False, root_validator=validate_root)
    # A safe earlier selector/registry check must not authorize a later replacement.
    assert service.fields()["fields"]
    monkeypatch.setattr(knowledge_ownership, "_read_declaration", observed_read)
    with pytest.raises(ExplorationError, match="test boundary"):
        service.units(SOURCE_A, FIELD_A)
    assert changed
    assert reads == []


def test_selector_validates_the_exact_loaded_registry_before_field_inspection(ownership_scope):  # noqa: F811
    import pytest

    from scholar_workflow.knowledge.exploration import ExplorationError
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService

    scope = ownership_scope
    _add_source(scope)

    def validate_root(root):
        if root != scope.root and scope.root not in root.parents:
            raise ExplorationError("Outside test boundary", 7)

    service = ExplorationReferenceService(scope.registry.path, resolve_reader=False,
        enrich_resources=False, root_validator=validate_root)
    with pytest.raises(ExplorationError, match="test boundary"):
        service.fields()
