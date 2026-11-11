"""Portable source packages and agent guides without executing provider data."""

from __future__ import annotations

import copy
import socket

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.source_catalog import SourceCatalog, validate_source
from scholar_workflow.research.recommendations.store import RecommendationStore


def plugin():
    return {
        "schema_version": 1,
        "source": {
            "source_id": "synthetic-releases",
            "name": "Synthetic releases",
            "purpose": "Read an explicitly selected research release feed.",
            "status": "available",
            "enabled": True,
            "scope": "selected_channel",
            "interfaces": [{"kind": "mcp", "url": "https://example.org/mcp"}],
            "capabilities": ["research releases"],
            "documentation": ["https://example.org/docs"],
            "plugin_version": "1.2.0",
            "agent": {
                "connection_name": "synthetic-releases",
                "instructions": "Use the host's registered connection and current native schemas.",
                "operations": [{
                    "operation_id": "recent-releases",
                    "description": "Read releases for the selected topic.",
                    "tool_name": "list_releases",
                    "effect": "read",
                    "inputs": {"type": "object", "properties": {"topic": {"type": "string"}}},
                    "outputs": "Release identities, original links and publication times.",
                }],
            },
        },
    }


@pytest.fixture
def catalog(tmp_path):
    return SourceCatalog(RecommendationStore(tmp_path / "pool"))


def test_package_import_export_and_restart_preserve_definition(catalog):
    package = plugin()
    original = copy.deepcopy(package)
    result = catalog.import_plugin(package, expected_revision=0)
    assert result["changed"] and result["revision"] == 1
    exported = catalog.export_plugin(package["source"]["source_id"])
    assert exported == original
    assert package == original
    assert not {"origin", "connection_status", "plugin_ready"} & exported["source"].keys()
    restored = SourceCatalog(RecommendationStore(catalog.store.state_dir))
    assert restored.export_plugin(package["source"]["source_id"]) == original
    assert restored.import_plugin(original, expected_revision=1)["changed"] is False
    with pytest.raises(ResearchError) as exc:
        restored.import_plugin(original, expected_revision=0)
    assert exc.value.exit_code == 5


def test_legacy_descriptor_stays_readable_but_not_plugin_ready(catalog):
    source = plugin()["source"]
    source.pop("plugin_version")
    source.pop("agent")
    catalog.register(source, expected_revision=0)
    current = catalog.get_source(source["source_id"])
    assert current["enabled"] is True and current["plugin_ready"] is False
    assert current["connection_status"] == "not_checked"
    with pytest.raises(ResearchError):
        catalog.import_plugin({"schema_version": 1, "source": source}, expected_revision=1)


@pytest.mark.parametrize("version", ["1", "1.2", "01.2.3", "v1.2.3", "1.2.3-", 2, None])
def test_plugin_versions_require_semver(catalog, version):
    package = plugin()
    package["source"]["plugin_version"] = version
    with pytest.raises(ResearchError):
        catalog.import_plugin(package, expected_revision=0)


@pytest.mark.parametrize("version", ["0.1.0", "1.2.3-rc.1", "1.2.3+build.7"])
def test_valid_plugin_versions_are_portable(catalog, version):
    package = plugin()
    package["source"]["plugin_version"] = version
    assert catalog.import_plugin(package, expected_revision=0)["changed"]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=2),
    lambda p: p.update(unexpected=True),
    lambda p: p["source"].pop("agent"),
    lambda p: p["source"]["agent"].update(operations=[]),
    lambda p: p["source"]["agent"].update(command="run arbitrary code"),
    lambda p: p["source"]["agent"].update(connection_name="../private"),
    lambda p: p["source"]["agent"]["operations"][0].update(effect="execute"),
    lambda p: p["source"]["agent"]["operations"].append(copy.deepcopy(p["source"]["agent"]["operations"][0])),
    lambda p: p["source"]["agent"]["operations"][0].pop("outputs"),
    lambda p: p["source"]["agent"]["operations"][0].update(inputs=[]),
    lambda p: p["source"]["agent"]["operations"][0].update(tool_name="tool; echo bad"),
])
def test_invalid_package_or_operation_is_refused(catalog, mutation):
    package = plugin()
    mutation(package)
    with pytest.raises(ResearchError):
        catalog.import_plugin(package, expected_revision=0)
    assert catalog.list_sources()["revision"] == 0


@pytest.mark.parametrize("value", [
    {"token": "sk-" + "x" * 30},
    {"description": "Read /Users/alice/private/config"},
    {"$ref": "https://example.org/schema?token=credential"},
    {"$ref": "http://127.0.0.1/private"},
])
def test_operation_schema_cannot_smuggle_secrets_or_private_locations(catalog, value):
    package = plugin()
    package["source"]["agent"]["operations"][0]["inputs"] = value
    with pytest.raises(ResearchError):
        catalog.import_plugin(package, expected_revision=0)


@pytest.mark.parametrize("field", ["connection_name", "tool_name"])
@pytest.mark.parametrize("value", ["ghp_" + "x" * 30, "sk-" + "x" * 30])
def test_symbolic_hints_cannot_contain_credential_like_strings(catalog, field, value):
    package = plugin()
    if field == "connection_name":
        package["source"]["agent"][field] = value
    else:
        package["source"]["agent"]["operations"][0][field] = value
    with pytest.raises(ResearchError) as exc:
        catalog.import_plugin(package, expected_revision=0)
    assert exc.value.exit_code == 7
    assert catalog.list_sources()["revision"] == 0


@pytest.mark.parametrize("field", ["api_key", "access_token", "password", "secret"])
def test_literal_operation_credentials_are_rejected_before_store(field):
    source = plugin()["source"]
    source["agent"]["operations"][0]["inputs"] = {field: "literal-credential"}
    with pytest.raises(ResearchError) as exc:
        validate_source(source)
    assert exc.value.exit_code == 7


def test_operation_schema_may_describe_a_sensitive_parameter_without_a_value():
    source = plugin()["source"]
    source["agent"]["operations"][0]["inputs"] = {
        "type": "object", "properties": {"api_key": {"type": "string"}},
    }
    # This verifies the descriptor layer, not the store's stricter management rules.
    assert validate_source(source)["agent"]["operations"][0]["inputs"]["properties"]["api_key"] == {
        "type": "string",
    }


def test_builtin_enable_override_is_local_cas_state_not_a_copied_definition(catalog):
    before = catalog.export_plugin("alphaxiv")
    receipt = catalog.set_enabled("alphaxiv", False, expected_revision=0)
    assert receipt["changed"] and receipt["revision"] == 1
    assert receipt["source"]["enabled"] is False
    assert catalog.get_source("alphaxiv")["plugin_ready"] is False
    stored = catalog.store.recommendation_sources()
    assert stored["items"] == []
    assert stored["overrides"] == {"alphaxiv": {"enabled": False}}
    assert catalog.export_plugin("alphaxiv") == before
    assert catalog.set_enabled("alphaxiv", False, expected_revision=1)["changed"] is False
    with pytest.raises(ResearchError) as exc:
        catalog.set_enabled("alphaxiv", True, expected_revision=0)
    assert exc.value.exit_code == 5
    assert catalog.set_enabled("alphaxiv", True, expected_revision=1)["revision"] == 2
    assert catalog.store.recommendation_sources()["overrides"] == {}
    assert catalog.get_source("alphaxiv")["plugin_ready"] is True


def test_custom_enable_uses_existing_registration_and_planned_cannot_enable(catalog):
    source_id = plugin()["source"]["source_id"]
    catalog.import_plugin(plugin(), expected_revision=0)
    assert catalog.set_enabled(source_id, False, expected_revision=1)["revision"] == 2
    assert catalog.store.recommendation_sources()["items"][0]["enabled"] is False
    assert catalog.store.recommendation_sources().get("overrides", {}) == {}
    with pytest.raises(ResearchError):
        catalog.set_enabled("x-self", True, expected_revision=2)
    with pytest.raises(ResearchError):
        catalog.set_enabled(source_id, 1, expected_revision=2)


def test_builtin_package_cannot_replace_packaged_definition(catalog):
    with pytest.raises(ResearchError) as exc:
        catalog.import_plugin(catalog.export_plugin("alphaxiv"), expected_revision=0)
    assert exc.value.exit_code == 5
    assert catalog.list_sources()["revision"] == 0


def test_guide_joins_current_requirements_and_context_without_copying_or_network(catalog, monkeypatch):
    def network_forbidden(*args, **kwargs):
        raise AssertionError("Source guides must not access providers.")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    source_id = plugin()["source"]["source_id"]
    catalog.import_plugin(plugin(), expected_revision=0)
    catalog.store.save_requirement("synthetic-reading", "Selected topic", "Only selected release updates.", True, 0,
                                   {"kind": "human", "name": "Synthetic reviewer"}, source_id=source_id)
    catalog.store.update_source_context(source_id, expected_revision=0, topics=["Synthetic topic"], notes="Continue from these topics.")
    catalog.store.record_source_operation({"operation_id": "synthetic-observation", "source_id": source_id,
        "actor": "synthetic-agent", "action": "recent-releases", "status": "reported_completed",
        "summary": "Synthetic empty result.", "observed_at": "2026-11-10T10:00:00+08:00", "evidence_urls": []})
    before = catalog.store.recommendation_sources()
    guide = catalog.guide(source_id)
    assert guide["source"]["plugin_ready"] is True
    assert guide["source"]["connection_status"] == "not_checked"
    assert guide["catalog_revision"] == 1
    assert guide["requirements"] == catalog.store.list_requirements(source_id=source_id)
    assert guide["context"] == catalog.store.source_context(source_id)
    assert guide["recent_operations"] == catalog.store.source_history(source_id)
    assert guide["discovery"] == {"method": "host_native", "require_current_tool_schema": True}
    assert guide["profile"] == "personal"
    assert guide["submission"] == {
        "schema": "scholar-research recommendations --profile personal schema",
        "entry": "scholar-research recommendations --profile personal submit",
    }
    assert catalog.store.recommendation_sources() == before


def test_builtins_describe_real_agent_entrypoints_without_claiming_connection(catalog):
    for source_id in ["alphaxiv", "hf-daily"]:
        source = catalog.guide(source_id)["source"]
        assert source["plugin_version"] and source["agent"]["operations"]
        assert source["plugin_ready"] is True
        assert source["connection_status"] == "not_checked"
    assert catalog.get_source("x-self")["plugin_ready"] is False



def test_source_storage_keeps_053_readable_projection(catalog):
    import json
    package = plugin()
    catalog.import_plugin(package, expected_revision=0)
    with catalog.store._database() as db:
        raw = json.loads(db.execute("SELECT record FROM source_catalog WHERE name='catalog'").fetchone()[0])
    legacy = raw["items"][0]
    assert "agent" not in legacy and "plugin_version" not in legacy
    assert raw["plugin_contracts"][legacy["source_id"]]["agent"] == package["source"]["agent"]
    assert catalog.export_plugin(legacy["source_id"]) == package
