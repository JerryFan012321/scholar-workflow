"""Isolated HTTP boundaries for the recommendation-only service."""
from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager

import pytest

from scholar_workflow.research.models import ResearchError

TOKEN = "test-session-token-that-is-not-a-real-credential"


class FakeStore:
    def __init__(self, state_dir):
        self.state_dir = state_dir

    def list_candidates(self, **kwargs):
        return {"items": [], "total": 0, "facets": {"tags": [], "producers": [], "kinds": []},
                "filters": kwargs}

    def set_decision(self, candidate_id, decision, expected_revision):
        if expected_revision != 3:
            raise ResearchError("Candidate revision changed; refresh before retrying.", 5)
        return {"candidate_id": candidate_id, "decision": decision, "revision": 4}

    def review_candidate(self, candidate_id, expected_revision):
        return {"candidate_id": candidate_id, "abstract_reviewed": True,
                "revision": expected_revision + 1}

    def prepare_handoff(self):
        return {"schema_version": 1, "status": "ready", "items": []}


@contextmanager
def running_server(tmp_path, monkeypatch):
    from scholar_workflow.research.recommendations import server as module

    monkeypatch.setattr(module, "RecommendationStore", FakeStore)
    service = module.create_server(tmp_path / "isolated-state", "test", TOKEN)
    service.runtime_identity = {"generation": "synthetic-generation", "pid": 123,
                                "profile": "test", "version": "test", "build": "synthetic"}
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield service
    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def request(service, method, path, *, authenticated=True, origin=None, body=None, host=None, extra_headers=None):
    connection = http.client.HTTPConnection(*service.server_address, timeout=3)
    headers = {"Host": host or f"127.0.0.1:{service.server_port}"}
    if authenticated:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if origin is not None:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    headers.update(extra_headers or {})
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_static_page_contains_no_private_state_and_has_security_headers(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        status, headers, content = request(service, "GET", "/", authenticated=False)
        assert status == 200
        assert "script-src 'self'" in headers["Content-Security-Policy"]
        assert headers["Referrer-Policy"] == "no-referrer"
        assert TOKEN.encode() not in content
        assert str(tmp_path).encode() not in content
        assert request(service, "GET", "/../store.py")[0] == 404


def test_health_identifies_service_without_exposing_session(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        status, _, content = request(service, "GET", "/health", authenticated=False)
        assert status == 200
        health = json.loads(content)
        assert health["service"] == "scholar-recommendations"
        assert health["generation"] == "synthetic-generation"
        assert health["profile"] == "test"
        assert health["pool_id"].startswith("pool-") and len(health["pool_id"]) == 37
        assert json.loads(request(service, "GET", "/health", authenticated=False)[2])["pool_id"] == health["pool_id"]
        assert TOKEN not in content.decode()
        assert str(tmp_path) not in content.decode()


def test_api_requires_auth_and_checks_host_and_origin(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        assert request(service, "GET", "/api/candidates", authenticated=False)[0] == 401
        assert request(service, "GET", "/api/candidates", host="attacker.example")[0] == 403
        assert request(service, "GET", "/api/candidates", origin="https://attacker.example")[0] == 403
        assert request(service, "POST", "/api/decisions", body={})[0] == 403
        assert request(service, "OPTIONS", "/api/candidates", origin="https://attacker.example")[0] == 403


def test_list_forwards_typed_pagination_and_same_record_filters(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        status, _, content = request(service, "GET",
            "/api/candidates?query=world&tag=video&producer_id=weekly&kind=paper&limit=10&offset=20&since=2026-11-01")
        assert status == 200
        filters = json.loads(content)["filters"]
        assert filters["producer_id"] == "weekly"
        assert filters["tag"] == "video"
        assert filters["limit"] == 10
        assert filters["offset"] == 20
        assert filters["since"] == "2026-11-01"
        assert request(service, "GET", "/api/candidates?limit=99999")[0] == 400
        assert request(service, "GET", "/api/candidates?offset=-1")[0] == 400
        assert request(service, "GET", "/api/candidates?query=a&query=b")[0] == 400
        assert request(service, "GET", "/api/candidates?path=/private/test")[0] == 400


def test_decision_requires_exact_fields_and_preserves_cas(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        origin = f"http://127.0.0.1:{service.server_port}"
        body = {"candidate_id": "candidate-test", "decision": "selected", "expected_revision": 3}
        status, _, content = request(service, "POST", "/api/decisions", origin=origin, body=body)
        assert status == 200
        assert json.loads(content)["decision"] == "selected"
        assert request(service, "POST", "/api/decisions", origin=origin,
                       body={**body, "expected_revision": 1})[0] == 409
        assert request(service, "POST", "/api/decisions", origin=origin,
                       body={**body, "command": "whoami"})[0] == 400
        assert request(service, "POST", "/api/decisions", origin=origin,
                       body={**body, "expected_revision": True})[0] == 400


def test_handoff_is_data_only_and_review_is_explicit(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        origin = f"http://127.0.0.1:{service.server_port}"
        status, _, content = request(service, "GET", "/api/handoff")
        assert status == 200
        assert json.loads(content)["items"] == []
        status, _, content = request(service, "POST", "/api/reviews", origin=origin,
                                    body={"candidate_id": "candidate-test", "expected_revision": 3})
        assert status == 200
        assert json.loads(content)["abstract_reviewed"] is True


def test_server_refuses_weak_token_or_unknown_profile(tmp_path):
    from scholar_workflow.research.recommendations.server import create_server

    with pytest.raises(ResearchError):
        create_server(tmp_path, "test", "short")
    with pytest.raises(ResearchError):
        create_server(tmp_path, "production", TOKEN)


def test_platform_refresh_requires_identity_cas_and_no_client_url(tmp_path, monkeypatch):
    from scholar_workflow.research.recommendations import server as module
    calls = []
    def refresh(store, candidate_id, expected_revision):
        calls.append((candidate_id, expected_revision))
        return {"candidate_id": candidate_id, "metrics": [{"platform": "github", "metric": "stars", "value": 0}]}
    monkeypatch.setattr(module, "refresh_candidate_metrics", refresh)
    with running_server(tmp_path, monkeypatch) as service:
        origin = f"http://127.0.0.1:{service.server_port}"
        payload = {"candidate_id": "candidate-fixture", "expected_revision": 3}
        status, _, body = request(service, "POST", "/api/metrics", origin=origin, body=payload)
        assert status == 200 and json.loads(body)["metrics"][0]["value"] == 0
        assert calls == [("candidate-fixture", 3)]
        assert request(service, "POST", "/api/metrics", origin=origin, body={**payload, "url": "https://attacker.example"})[0] == 400
        assert request(service, "POST", "/api/metrics", body=payload)[0] == 403
        assert request(service, "POST", "/api/metrics", origin=origin, authenticated=False, body=payload)[0] == 401
        assert len(calls) == 1


def test_plain_url_bootstrap_allows_independent_clients_not_foreign_sites(tmp_path, monkeypatch):
    with running_server(tmp_path, monkeypatch) as service:
        origin = f"http://127.0.0.1:{service.server_port}"
        header = {"X-Scholar-Client": "recommendation-page", "Sec-Fetch-Site": "same-origin"}
        for _ in range(2):
            assert request(service, "GET", "/", authenticated=False)[0] == 200
            status, headers, body = request(service, "POST", "/api/session", authenticated=False,
                origin=origin, body={}, extra_headers=header)
            assert status == 200 and json.loads(body)["token"] == TOKEN
            assert headers["Cache-Control"] == "no-store"
            assert "Access-Control-Allow-Origin" not in headers
            assert request(service, "GET", "/api/candidates")[0] == 200
        assert request(service, "GET", "/api/session", authenticated=False)[0] == 401
        for changes in [dict(origin=None), dict(origin="https://foreign.example"),
                        dict(host="foreign.example"), dict(extra_headers={}),
                        dict(extra_headers={**header,"Sec-Fetch-Site":"cross-site"})]:
            options = dict(authenticated=False, origin=origin, body={}, extra_headers=header)
            options.update(changes)
            status, headers, body = request(service, "POST", "/api/session", **options)
            assert status == 403 and TOKEN.encode() not in body
            assert "Access-Control-Allow-Origin" not in headers
        assert request(service, "OPTIONS", "/api/session", origin="https://foreign.example")[0] == 403
        assert request(service, "POST", "/api/session", authenticated=False, origin=origin,
                       body={"arbitrary": "value"}, extra_headers=header)[0] == 400
