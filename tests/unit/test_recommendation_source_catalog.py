"""Reusable source descriptors, never executable credentials or a platform enum."""

from __future__ import annotations

import copy

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.source_catalog import SourceCatalog


class Store:
    def __init__(self):
        self.state = {"revision": 0, "items": []}

    def recommendation_sources(self):
        return copy.deepcopy(self.state)

    def register_recommendation_source(self, source, expected_revision):
        if expected_revision != self.state["revision"]:
            raise ResearchError("Synthetic source revision conflict.", 5)
        previous = next(
            (row for row in self.state["items"] if row["source_id"] == source["source_id"]), None
        )
        changed = previous != source
        if changed:
            self.state["items"] = [
                row for row in self.state["items"] if row["source_id"] != source["source_id"]
            ] + [copy.deepcopy(source)]
            self.state["revision"] += 1
        return {
            "revision": self.state["revision"],
            "source": copy.deepcopy(source),
            "changed": changed,
        }


def source():
    return {
        "source_id": "future-lab",
        "name": "Synthetic Lab",
        "purpose": "Selected research releases",
        "status": "available",
        "enabled": True,
        "interfaces": [{"kind": "feed", "url": "https://example.org/releases.atom"}],
        "capabilities": ["research releases"],
        "documentation": ["https://example.org/docs"],
        "auth": {"method": "none", "instructions": "Public feed."},
        "scope": "selected_channel",
    }


def test_builtins_record_real_interfaces_and_planned_self_accounts():
    store = Store()
    catalog = SourceCatalog(store)
    result = catalog.list_sources()
    assert result["revision"] == 0 and not store.state["items"]
    rows = {row["source_id"]: row for row in result["items"]}
    assert rows["alphaxiv"]["execution"] == {
        "kind": "native_mcp",
        "host_connection_name": "alphaxiv",
    }
    assert rows["alphaxiv"]["connection_status"] == "not_checked"
    assert rows["alphaxiv"]["interfaces"][0] == {
        "kind": "mcp",
        "url": "https://api.alphaxiv.org/mcp/v1",
    }
    assert rows["hf-daily"]["status"] == "available"
    for name in ["x-self", "zhihu-self"]:
        assert rows[name]["status"] == "planned" and not rows[name]["enabled"]
        assert rows[name]["scope"] == "self_account_only"
    assert all(row["origin"] == "builtin" for row in rows.values())


def test_custom_source_register_read_update_and_noop_use_same_store():
    store = Store()
    catalog = SourceCatalog(store)
    receipt = catalog.register(source(), expected_revision=0)
    assert receipt["changed"] and receipt["revision"] == 1
    assert catalog.get_source("future-lab")["origin"] == "registered"
    assert catalog.register(source(), expected_revision=1)["changed"] is False
    revised = {**source(), "capabilities": ["releases", "datasets"]}
    with pytest.raises(ResearchError):
        catalog.register(revised, expected_revision=0)
    assert catalog.register(revised, expected_revision=1)["revision"] == 2
    assert len(store.state["items"]) == 1


@pytest.mark.parametrize("kind", ["mcp", "api", "feed", "cli"])
def test_new_provider_is_not_restricted_to_known_platforms(kind):
    item = source()
    item["interfaces"] = [
        {
            "kind": kind,
            **(
                {"url": "https://example.org/interface"}
                if kind != "cli"
                else {
                    "instructions": "Use the provider's installed native CLI after reviewing its help."
                }
            ),
        }
    ]
    catalog = SourceCatalog(Store())
    assert catalog.register(item, expected_revision=0)["changed"]


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1/private",
        "https://user:pass@example.org/",
        "https://example.org/?token=secret",
        "https://example.local/private",
    ],
)
def test_private_or_credential_bearing_endpoint_is_refused(value):
    item = source()
    item["interfaces"][0]["url"] = value
    with pytest.raises(ResearchError):
        SourceCatalog(Store()).register(item, expected_revision=0)


@pytest.mark.parametrize(
    "extra",
    [
        {"api_key": "do-not-store-this"},
        {"command": "curl https://example.org"},
        {"adapter_id": "arbitrary-executor"},
        {"token_path": "/Users/alice/private-key"},
    ],
)
def test_custom_source_cannot_install_credentials_or_a_command_executor(extra):
    with pytest.raises(ResearchError):
        SourceCatalog(Store()).register({**source(), **extra}, expected_revision=0)


@pytest.mark.parametrize(
    "note",
    [
        "API_KEY=do-not-store-this",
        "/Users/alice/private/config",
        "Use /home/alice/private-key",
        "C:\\Users\\alice\\private-key",
    ],
)
def test_plain_text_rejects_obvious_credentials_and_private_absolute_paths(note):
    item = source()
    item["auth"]["instructions"] = note
    with pytest.raises(ResearchError):
        SourceCatalog(Store()).register(item, expected_revision=0)


def test_builtins_cannot_be_shadowed_and_unknown_source_is_an_error():
    catalog = SourceCatalog(Store())
    with pytest.raises(ResearchError):
        catalog.register({**source(), "source_id": "alphaxiv"}, expected_revision=0)
    with pytest.raises(ResearchError):
        catalog.get_source("missing-source")


def test_catalog_reads_do_not_execute_descriptors_or_mutate_sources():
    store = Store()
    catalog = SourceCatalog(store)
    catalog.register(source(), expected_revision=0)
    before = copy.deepcopy(store.state)
    first = catalog.list_sources()
    first["items"][0]["name"] = "changed outside"
    assert catalog.list_sources()["items"][0]["name"] != "changed outside"
    assert store.state == before


def test_catalog_registers_in_real_pool_without_copying_builtins(tmp_path):
    from scholar_workflow.research.recommendations.store import RecommendationStore

    store = RecommendationStore(tmp_path / "state")
    catalog = SourceCatalog(store)
    receipt = catalog.register(source(), expected_revision=0)
    assert receipt["changed"] and receipt["revision"] == 1
    assert len(store.recommendation_sources()["items"]) == 1
    assert len(catalog.list_sources()["items"]) == 5
    assert (
        SourceCatalog(RecommendationStore(store.state_dir)).get_source("future-lab")["name"]
        == "Synthetic Lab"
    )
    with pytest.raises(ResearchError):
        catalog.register(source(), expected_revision=0)


def test_source_identity_length_matches_pool_storage():
    item = source()
    item["source_id"] = "x" * 81
    with pytest.raises(ResearchError):
        SourceCatalog(Store()).register(item, expected_revision=0)
