"""Public metric contracts using synthetic JSON and MockTransport only."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest

from scholar_workflow.research.recommendations.metrics import collect_metrics, metric_targets


GITHUB_URL = "https://github.com/ExampleLab/project"
GITHUB_API = "https://api.github.com/repos/ExampleLab/project"
HF_MODEL_URL = "https://huggingface.co/ExampleLab/model"
HF_MODEL_API = "https://huggingface.co/api/models/ExampleLab/model?expand=likes"


@pytest.fixture
def resource():
    return {
        "kind": "paper", "title": "Synthetic research",
        "url": "https://arxiv.org/abs/2601.12345", "project_url": GITHUB_URL,
        "links": [
            {"label": "Model", "url": HF_MODEL_URL},
            {"label": "Dataset", "url": "https://huggingface.co/datasets/ExampleLab/data"},
            {"label": "Space", "url": "https://huggingface.co/spaces/ExampleLab/demo"},
        ],
    }


def client_for(handler, **kwargs):
    return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)


def test_targets_are_only_declared_repository_objects(resource):
    assert metric_targets(resource) == [
        {"platform": "github", "metric": "stars", "url": GITHUB_URL, "api_url": GITHUB_API},
        {"platform": "huggingface", "metric": "likes", "url": HF_MODEL_URL,
         "api_url": HF_MODEL_API},
        {"platform": "huggingface", "metric": "likes",
         "url": "https://huggingface.co/datasets/ExampleLab/data",
         "api_url": "https://huggingface.co/api/datasets/ExampleLab/data?expand=likes"},
        {"platform": "huggingface", "metric": "likes",
         "url": "https://huggingface.co/spaces/ExampleLab/demo",
         "api_url": "https://huggingface.co/api/spaces/ExampleLab/demo?expand=likes"},
    ]


@pytest.mark.parametrize("url", [
    "http://github.com/lab/project", "https://github.com.evil.example/lab/project",
    "https://github.com@evil.example/lab/project", "https://user@github.com/lab/project",
    "https://user:secret@github.com/lab/project", "https://github.com:443/lab/project",
    "https://github.com/lab/project.git", "https://github.com/lab/project/tree/main",
    "https://github.com/lab/project/blob/main/README.md", "https://github.com/lab/project?",
    "https://github.com/lab/project?token=secret", "https://github.com/lab/project#",
    "https://github.com/lab/project#readme", "https://github.com/lab%2Fother/project",
    "https://github.com/lab/../project", "https://github.com/lab/project//",
    "https://github.com/topics/world-models", "https://github.com/orgs/lab",
    "https://huggingface.co/docs/hub", "https://huggingface.co/papers/2601.12345",
    "https://huggingface.co/collections/lab", "https://huggingface.co/spaces/lab",
    "https://huggingface.co/datasets/lab/data/resolve/main/data.parquet",
    "https://huggingface.co/lab/model/tree/main", "https://huggingface.co/lab/model?download=1",
    "https://lab-demo.hf.space/", "https://huggingface.co/lab/model.git",
    "https://github.com/lab/\nproject", " https://github.com/lab/project",
])
def test_unsafe_and_non_object_urls_do_not_become_targets(url):
    assert metric_targets({"url": url}) == []


def test_unknown_homepage_and_unstructured_link_text_do_not_trigger_network():
    resource = {"url": "https://example.org/project", "links": ["https://github.com/lab/project"]}
    with client_for(lambda _: pytest.fail("Unknown homepage must not be fetched")) as client:
        assert collect_metrics(resource, client=client) == {"observations": [], "checks": []}


def test_targets_deduplicate_repository_identity_and_limit_to_six():
    resource = {"url": GITHUB_URL, "project_url": GITHUB_URL.lower() + "/", "links": [
        {"url": f"https://github.com/lab/project-{number}"} for number in range(10)
    ]}
    targets = metric_targets(resource)
    assert len(targets) == 6
    assert targets[0]["url"] == GITHUB_URL
    assert targets[-1]["url"] == "https://github.com/lab/project-4"


def test_success_preserves_each_object_url_raw_count_and_utc_timestamp(resource):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"stargazers_count": 1234, "private": False})
        return httpx.Response(200, json={"likes": 17, "private": False})

    with client_for(handler) as client:
        result = collect_metrics(resource, client=client)
        assert not client.is_closed
    assert seen == [target["api_url"] for target in metric_targets(resource)]
    assert len(result["observations"]) == len(result["checks"]) == 4
    for index, (observation, check) in enumerate(zip(result["observations"], result["checks"])):
        target = metric_targets(resource)[index]
        assert observation == {
            "platform": target["platform"], "metric": target["metric"],
            "value": 1234 if index == 0 else 17, "url": target["url"],
            "observed_at": observation["observed_at"],
        }
        assert check == {"platform": target["platform"], "metric": target["metric"],
                         "url": target["url"], "status": "ok",
                         "checked_at": observation["observed_at"]}
        assert datetime.fromisoformat(observation["observed_at"]).utcoffset() == timedelta(0)


@pytest.mark.parametrize("url,key", [(GITHUB_URL, "stargazers_count"), (HF_MODEL_URL, "likes")])
@pytest.mark.parametrize("value", [None, True, False, -1, 1.5, "12", [], {}])
def test_invalid_metric_values_are_unavailable_and_never_zero(url, key, value):
    with client_for(lambda _: httpx.Response(200, json={key: value})) as client:
        result = collect_metrics({"url": url}, client=client)
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "unavailable"


@pytest.mark.parametrize("payload", [{}, [], {"private": True, "stargazers_count": 10}])
def test_missing_non_object_or_private_payload_is_unavailable(payload):
    with client_for(lambda _: httpx.Response(200, json=payload)) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "unavailable"


def test_valid_zero_is_an_observation():
    with client_for(lambda _: httpx.Response(200, json={"stargazers_count": 0})) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert result["observations"][0]["value"] == 0
    assert result["checks"][0]["status"] == "ok"


@pytest.mark.parametrize("status,headers,expected", [
    (404, {}, "unavailable"), (401, {}, "unavailable"), (403, {}, "unavailable"),
    (500, {}, "unavailable"), (429, {}, "rate_limited"),
    (403, {"x-ratelimit-remaining": "0"}, "rate_limited"),
    (403, {"retry-after": "60"}, "rate_limited"),
])
def test_failed_responses_have_explicit_status_without_fake_observation(status, headers, expected):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers=headers, json={"stargazers_count": 10})

    with client_for(handler) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert len(seen) == 1
    assert result["observations"] == []
    assert result["checks"][0]["status"] == expected


def test_secondary_rate_limit_message_is_recognized_without_quota_headers():
    with client_for(lambda _: httpx.Response(403, json={
        "message": "You have exceeded a secondary rate limit.",
    })) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "rate_limited"


def test_caller_auth_headers_cookies_and_redirect_policy_are_not_inherited():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == "api.github.com"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert "x-secret" not in request.headers
        assert all(0 < value <= 5 for value in request.extensions["timeout"].values())
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    with client_for(handler, auth=("user", "secret"), headers={"X-Secret": "secret"},
                    cookies={"session": "secret"}, follow_redirects=True) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert len(seen) == 1
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "unavailable"
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("raw", [b"not JSON", b'{"stargazers_count":', b"\xff"])
def test_invalid_json_is_unavailable(raw):
    with client_for(lambda _: httpx.Response(200, content=raw)) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "unavailable"


@pytest.mark.parametrize("headers", [
    {"content-length": str(256 * 1024 + 1)}, {"content-encoding": "gzip"},
])
def test_oversized_or_encoded_body_is_refused_before_streaming(headers):
    class UnreadBody(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            pytest.fail("Refused body must not be consumed")
            yield b""

        def close(self):
            self.closed = True

    body = UnreadBody()
    with client_for(lambda _: httpx.Response(200, headers=headers, stream=body)) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert body.closed
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "unavailable"


def test_streamed_body_is_stopped_at_256_kib_and_closed():
    class LargeBody(httpx.SyncByteStream):
        chunks = 0
        closed = False

        def __iter__(self):
            for _ in range(100):
                self.chunks += 1
                yield b"x" * (16 * 1024)

        def close(self):
            self.closed = True

    body = LargeBody()
    with client_for(lambda _: httpx.Response(200, stream=body)) as client:
        result = collect_metrics({"url": GITHUB_URL}, client=client)
    assert body.closed
    assert body.chunks <= 17
    assert result["observations"] == []
    assert result["checks"][0]["status"] == "unavailable"


def test_network_failure_does_not_disclose_diagnostics_or_stop_other_targets(resource):
    def handler(request):
        if request.url.host == "api.github.com":
            raise httpx.ReadError("secret local configuration", request=request)
        return httpx.Response(200, json={"likes": 5})

    with client_for(handler) as client:
        result = collect_metrics(resource, client=client)
    assert [item["status"] for item in result["checks"]] == ["unavailable", "ok", "ok", "ok"]
    assert len(result["observations"]) == 3
    assert "secret" not in json.dumps(result)
