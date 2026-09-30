"""Prepared API fixtures; no live Zotero, cmux, Obsidian or Codex is required."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scholar_workflow.hub.actions import ActionKind, PublicAction
from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.directory import EntityRef
from scholar_workflow.hub.models import HubCatalog
from scholar_workflow.hub.server import start_hub_server


class RelatedFixture:
    def public_related(self, key):
        assert key == "ABCDEFGH"
        return {
            "paper_ref": {"provider_id": "zotero", "entity_type": "paper", "entity_id": key},
            "documents": [{
                "ref": EntityRef(provider_id="obsidian", entity_type="document", entity_id="doc-one"),
                "title": "Analysis", "source_name": "Fixture Vault", "available": True,
                "actions": [PublicAction(id="open-analysis", label="Open analysis",
                                         kind=ActionKind.OBSIDIAN_RELATED_FILE)],
                "preview_id": "preview-one",
            }], "field_contexts": [], "diagnostics": [],
        }

    def read_preview(self, identifier):
        assert identifier == "preview-one"
        return {"title": "Analysis", "content": "# Fixture\nReadable body.", "revision": "sha256:fixture"}


class SetupFixture:
    def __init__(self):
        self.requests = []

    def public_options(self):
        return {"available": True, "default_profile_id": "default", "model_profiles": [{
            "profile_id": "default", "title": "Default", "supported_reasoning_efforts": ["low", "high"],
            "default_reasoning_effort": "low", "is_default": True,
        }]}

    def preview(self):
        return {"configured": False, "candidates": [{"candidate_id": "candidate-one", "available": True}],
                "targets": self.public_targets(), **self.public_options()}

    def public_targets(self):
        return [{"target_id": "target-one", "title": "Fixture", "kind": "folder", "available": True}]

    def confirm(self, request):
        self.requests.append(request.model_dump(mode="json"))
        return {"configured": True, **self.public_options()}

    def save_preferences(self, profile_id, reasoning_effort):
        if profile_id != "default" or reasoning_effort not in {"low", "high"}:
            raise ValueError("Unknown model selection")
        self.requests.append({"model_profile_id": profile_id, "reasoning_effort": reasoning_effort})
        return {**self.public_options(), "selected_model_profile_id": profile_id,
                "selected_reasoning_effort": reasoning_effort}


@pytest.fixture
def api_server(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "state"))
    vault = tmp_path / "vault"
    vault.mkdir()
    setup = SetupFixture()
    server = start_hub_server(
        storage_root=tmp_path / "storage", vault_root=vault,
        catalog_provider=StaticCatalogProvider(HubCatalog(generated_at=datetime(2026, 9, 30, tzinfo=UTC))),
        public_actions={}, paper_related_service=RelatedFixture(), codex_setup_service=setup,
    )
    yield server, setup
    server.shutdown()
    server.server_close()


def request(server, path, *, body=None, token=True, origin=True):
    base = f"http://127.0.0.1:{server.server_port}"
    headers = {}
    if token:
        headers["X-Scholar-Hub-Token"] = server.runtime.session_token
    if origin:
        headers["Origin"] = base
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers), timeout=3) as response:
        return json.load(response)


def test_paper_related_and_preview_serialize_only_controlled_references(api_server):
    server, _ = api_server
    payload = request(server, "/api/v3/papers/ABCDEFGH/related")
    row = payload["documents"][0]
    assert row["ref"]["entity_id"] == "doc-one"
    assert row["actions"][0]["id"] == "open-analysis"
    assert row["actions"][0]["destination_required"] is False
    assert "path" not in json.dumps(payload)
    assert request(server, "/api/v3/paper-documents/preview-one/content")["content"].startswith("# Fixture")


def test_codex_preview_requires_session_and_model_preferences_use_ids(api_server):
    server, setup = api_server
    with pytest.raises(urllib.error.HTTPError) as error:
        request(server, "/api/v3/codex/setup", token=False)
    assert error.value.code == 403
    assert request(server, "/api/v3/codex/setup")["candidates"][0]["candidate_id"] == "candidate-one"
    result = request(server, "/api/v3/task-options/preferences", body={
        "model_profile_id": "default", "reasoning_effort": "high",
    })
    assert result["selected_reasoning_effort"] == "high"
    assert len(setup.requests) == 1


@pytest.mark.parametrize("extra", ["model", "cwd", "command", "sandbox", "permission", "environment"])
def test_preferences_and_setup_refuse_raw_execution_configuration(api_server, extra):
    server, setup = api_server
    for path, body in [
        ("/api/v3/task-options/preferences", {"model_profile_id": "default", "reasoning_effort": "low"}),
        ("/api/v3/codex/setup", {"candidate_id": "candidate-one", "model_profile_id": "default",
                                 "target_ids": ["target-one"], "sandbox": "read-only"}),
    ]:
        # Setup alone offers an explicit bounded sandbox policy choice; no task/raw config path does.
        if extra == "sandbox" and path.endswith("/setup"):
            body[extra] = "danger-full-access"
        else:
            body[extra] = "arbitrary"
        with pytest.raises(urllib.error.HTTPError) as error:
            request(server, path, body=body)
        assert error.value.code == 409
    assert setup.requests == []


def test_setup_confirmation_and_preferences_require_same_origin_token(api_server):
    server, setup = api_server
    body = {"candidate_id": "candidate-one", "model_profile_id": "default",
            "target_ids": ["target-one"], "sandbox": "read-only"}
    for options in [{"token": False}, {"origin": False}]:
        with pytest.raises(urllib.error.HTTPError) as error:
            request(server, "/api/v3/codex/setup", body=body, **options)
        assert error.value.code == 403
    assert request(server, "/api/v3/codex/setup", body=body)["configured"] is True
    assert setup.requests[0]["candidate_id"] == "candidate-one"


def test_folder_picker_endpoint_never_accepts_browser_paths(api_server):
    server, _ = api_server
    with pytest.raises(urllib.error.HTTPError) as error:
        request(server, "/api/v3/execution-targets/preview", body={"path": "/arbitrary"})
    assert error.value.code == 409
