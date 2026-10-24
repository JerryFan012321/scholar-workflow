"""Research acquisition contracts, using isolated bytes and MockTransport only."""
from __future__ import annotations

import json
import socket
import ssl

import httpx
import pytest

from scholar_workflow.adapters import research_http, research_sources
from scholar_workflow.adapters.research_sources import fetch_channel


def channel(kind="rss", url="https://research.example/feed.xml"):
    return {
        "channel_id": "example", "name": "Example research", "publisher": "Example",
        "publisher_kind": "lab", "kind": kind, "url": url, "enabled": True,
        "topics": ["world models"],
    }


RSS = b"""<rss version="2.0"><channel><title>Research</title><item>
<guid isPermaLink="false">article-1</guid><title>First result</title>
<link>https://research.example/result</link>
<description><![CDATA[<p>A complete <b>result</b>.</p>]]></description>
<pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate>
</item></channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Research</title>
<entry><id>urn:example:article-2</id><title>Second result</title>
<link rel="self" href="https://research.example/api/2"/>
<link rel="alternate" href="/second"/>
<content type="html">&lt;p&gt;A useful finding.&lt;/p&gt;</content>
<published>2026-09-01T12:00:00Z</published><updated>2026-09-02T12:00:00Z</updated>
</entry></feed>"""


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_rss_stable_identity_and_no_body_persistence():
    with client_for(lambda _: httpx.Response(200, content=RSS)) as client:
        first = fetch_channel(channel(), client=client)
        second = fetch_channel(channel(), client=client)
        assert not client.is_closed
    assert first == second
    assert first["status"] == "ok"
    item = first["items"][0]
    assert item["item_id"] == "article-1"
    assert item["url"] == "https://research.example/result"
    assert item["title"] == "First result"
    assert item["published_at"] == "Tue, 01 Sep 2026 12:00:00 GMT"
    assert item["content_digest"].startswith("sha256:")
    assert len(item["content_digest"]) == 71
    assert "A complete" not in json.dumps(first)


def test_atom_alternate_relative_link_and_source_dates():
    with client_for(lambda _: httpx.Response(200, content=ATOM)) as client:
        result = fetch_channel(channel("atom"), client=client)
    assert result["status"] == "ok"
    item = result["items"][0]
    assert item["item_id"] == "urn:example:article-2"
    assert item["url"] == "https://research.example/second"
    assert item["updated_at"] == "2026-09-02T12:00:00Z"


@pytest.mark.parametrize("base_attributes,expected", [
    (("https://research.example/blog/", "", ""), "https://research.example/blog/result"),
    (("https://research.example/blog/", "papers/", ""), "https://research.example/blog/papers/result"),
    (("https://research.example/blog/", "papers/", "../notes/"), "https://research.example/blog/notes/result"),
])
def test_atom_inherits_feed_entry_and_link_xml_base(base_attributes, expected):
    feed_base, entry_base, link_base = base_attributes
    raw = f'''<feed xmlns="http://www.w3.org/2005/Atom" xml:base="{feed_base}">
    <entry xml:base="{entry_base}"><id>urn:example:base</id><title>Result</title>
    <link rel="alternate" xml:base="{link_base}" href="result"/></entry></feed>'''
    with client_for(lambda _: httpx.Response(200, text=raw)) as client:
        result = fetch_channel(channel("atom"), client=client)
    assert result["status"] == "ok"
    assert result["items"][0]["url"] == expected


def test_atom_private_xml_base_is_refused():
    raw = '''<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://127.0.0.1/">
    <entry><id>urn:private</id><title>Result</title><link href="result"/></entry></feed>'''
    with client_for(lambda _: httpx.Response(200, text=raw)) as client:
        assert fetch_channel(channel("atom"), client=client)["status"] == "failed"


def test_feed_description_markup_is_not_progress():
    outputs = []
    for raw in (RSS, RSS.replace(b"<b>result</b>", b"<em>result</em>"),
                RSS.replace(b"<b>result</b>", b"result")):
        with client_for(lambda _, raw=raw: httpx.Response(200, content=raw)) as client:
            outputs.append(fetch_channel(channel(), client=client))
    assert outputs[0]["items"] == outputs[1]["items"]
    assert outputs[0]["items"] == outputs[2]["items"]


def test_webpage_ignores_markup_navigation_and_scripts():
    first = b"""<html><head><title>Result</title></head><body><nav>Old nav</nav>
    <main><h1>Our result</h1><p>Clear useful explanation.</p></main>
    <script>oldScript()</script></body></html>"""
    second = first.replace(b"Old nav", b"New nav").replace(b"oldScript", b"newScript")
    second = second.replace(b"<p>", b"<p class='new'>").replace(b"Our result", b"Our <b>result</b>")
    results = []
    for raw in (first, second):
        with client_for(lambda _, raw=raw: httpx.Response(200, content=raw)) as client:
            results.append(fetch_channel(channel("webpage"), client=client))
    assert results[0]["status"] == "ok"
    assert results[0]["items"] == results[1]["items"]
    assert "explanation" not in json.dumps(results[0])


def test_webpage_semantic_edit_changes_digest():
    results = []
    for text in ("Supports images", "Supports images and video"):
        raw = f"<html><title>Release</title><main><p>{text}</p></main></html>"
        with client_for(lambda _, raw=raw: httpx.Response(200, text=raw)) as client:
            results.append(fetch_channel(channel("webpage"), client=client))
    assert results[0]["items"][0]["item_id"] == results[1]["items"][0]["item_id"]
    assert results[0]["items"][0]["content_digest"] != results[1]["items"][0]["content_digest"]


def test_conditionals_and_304_are_returned_without_fabricated_items():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(304, headers={"etag": '"version-1"'})

    with client_for(handler) as client:
        result = fetch_channel(channel(), {"etag": '"version-1"'}, client=client)
    assert result["status"] == "not_modified"
    assert result["items"] == []
    assert seen[0].headers["if-none-match"] == '"version-1"'


def test_github_complete_pagination_and_no_conditional_shortcut():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == "api.github.com"
        assert request.url.path == "/repos/example/models/releases"
        assert "if-none-match" not in request.headers
        page = request.url.params.get("page")
        number = 2 if page == "2" else 1
        headers = ({"link": '<https://api.github.com/repos/example/models/releases?per_page=100&page=2>; rel="next"'}
                   if number == 1 else {})
        return httpx.Response(200, headers=headers, json=[{
            "id": number, "tag_name": f"v{number}", "name": f"Version {number}",
            "body": "Research result", "html_url": f"https://github.com/example/models/releases/tag/v{number}",
            "draft": False, "prerelease": False, "published_at": "2026-09-01T00:00:00Z",
        }])

    with client_for(handler) as client:
        result = fetch_channel(channel("github_releases", "https://github.com/example/models"),
                               {"etag": '"first-page-only"'}, client=client)
    assert result["status"] == "ok"
    assert len(seen) == 2
    assert [item["item_id"] for item in result["items"]] == ["github-release:1", "github-release:2"]
    assert result["items"][1]["version"] == "v2"


def test_hf_models_author_version_and_noise_exclusion():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == "/api/models"
        assert request.url.params["author"] == "ExampleLab"
        return httpx.Response(200, json=[{
            "id": "ExampleLab/model-1", "sha": "a" * 40, "private": False,
            "createdAt": "2026-08-01T00:00:00Z", "lastModified": "2026-09-01T00:00:00Z",
            "pipeline_tag": "text-generation", "tags": ["transformers", "en"],
            "downloads": len(seen), "likes": len(seen),
        }])

    with client_for(handler) as client:
        first = fetch_channel(channel("hf_models", "https://huggingface.co/ExampleLab"), client=client)
        second = fetch_channel(channel("hf_models", "https://huggingface.co/ExampleLab"), client=client)
    assert first["status"] == "ok"
    assert first["items"] == second["items"]
    assert first["items"][0]["item_id"] == "hf-model:ExampleLab/model-1"
    assert first["items"][0]["version"] == "a" * 40
    assert len(seen) == 2


def test_hf_optional_revision_is_not_invented_and_author_is_case_insensitive():
    with client_for(lambda _: httpx.Response(200, json=[{
        "id": "examplelab/empty-model", "sha": None, "private": False,
    }])) as client:
        result = fetch_channel(channel("hf_models", "https://huggingface.co/ExampleLab"), client=client)
    assert result["status"] == "ok"
    assert "version" not in result["items"][0]


@pytest.mark.parametrize("kind,url", [
    ("rss", "http://research.example/feed"),
    ("rss", "https://user:password@research.example/feed"),
    ("rss", "https://localhost/feed"),
    ("rss", "https://127.0.0.1/feed"),
    ("rss", "https://[::1]/feed"),
    ("rss", "https://10.1.2.3/feed"),
    ("rss", "https://169.254.169.254/feed"),
    ("rss", "https://research.example/feed#fragment"),
    ("rss", "https://research.example/feed?token=secret"),
    ("github_releases", "https://github.com/example/models/extra"),
    ("hf_models", "https://huggingface.co/ExampleLab/model"),
])
def test_unsafe_channel_is_refused_before_request(kind, url):
    def unexpected(_):
        pytest.fail("Rejected channel must not perform any HTTP request")

    with client_for(unexpected) as client:
        result = fetch_channel(channel(kind, url), client=client)
    assert result["status"] == "failed"
    assert result["diagnostic"]["code"] == "unsafe_url"
    assert "secret" not in json.dumps(result)
    assert "password" not in json.dumps(result)


def test_redirect_each_hop_validated_without_credentials_or_client_secrets():
    seen = []

    def handler(request):
        seen.append(request)
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert "x-secret" not in request.headers
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    with httpx.Client(transport=httpx.MockTransport(handler), auth=("user", "password"),
                      headers={"X-Secret": "private"}, cookies={"session": "private"},
                      follow_redirects=True) as client:
        result = fetch_channel(channel(), client=client)
    assert result["status"] == "failed"
    assert result["diagnostic"]["code"] == "unsafe_url"
    assert len(seen) == 1


@pytest.mark.parametrize("raw", [
    b'<!DOCTYPE rss [<!ENTITY local SYSTEM "file:///private/example">]><rss/>',
    b'<!DOCTYPE rss [<!ENTITY x "lol">]><rss><channel>&x;</channel></rss>',
    b'<html><body>not an RSS feed</body></html>',
    b'<rss><channel><item><title>Broken item</title></item></channel></rss>',
    b'<rss><channel>',
])
def test_xml_and_incomplete_feed_refusals(raw):
    with client_for(lambda _: httpx.Response(200, content=raw)) as client:
        result = fetch_channel(channel(), client=client)
    assert result["status"] == "failed"
    assert result["items"] == []


def test_empty_well_formed_feed_is_finite_empty_success():
    with client_for(lambda _: httpx.Response(200, content=b"<rss><channel/></rss>")) as client:
        result = fetch_channel(channel(), client=client)
    assert result["status"] == "ok"
    assert result["items"] == []


def test_feed_item_unsafe_link_is_not_silently_dropped():
    with client_for(lambda _: httpx.Response(200, content=RSS.replace(
        b"https://research.example/result", b"https://localhost/private"))) as client:
        result = fetch_channel(channel(), client=client)
    assert result["status"] == "failed"
    assert result["items"] == []


@pytest.mark.parametrize("mode", ["bad_second_page", "loop", "external_next", "missing_next"])
def test_api_pagination_failure_never_becomes_partial_success(mode):
    def handler(request):
        row = {"id": 1, "tag_name": "v1", "name": "Version 1", "body": "Result",
               "html_url": "https://github.com/example/models/releases/tag/v1"}
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"not": "a list"})
        if mode == "missing_next":
            return httpx.Response(200, json=[dict(row, id=number) for number in range(100)])
        target = {
            "bad_second_page": "https://api.github.com/repos/example/models/releases?per_page=100&page=2",
            "loop": str(request.url),
            "external_next": "https://elsewhere.example/api/releases?page=2",
        }[mode]
        return httpx.Response(200, json=[row], headers={"link": f'<{target}>; rel="next"'})

    with client_for(handler) as client:
        result = fetch_channel(channel("github_releases", "https://github.com/example/models"), client=client)
    assert result["status"] == "failed"
    assert result["items"] == []


def test_hf_pagination_keeps_author_scope():
    def handler(_):
        return httpx.Response(200, json=[], headers={
            "link": '<https://huggingface.co/api/models?author=Other&cursor=next>; rel="next"',
        })

    with client_for(handler) as client:
        result = fetch_channel(channel("hf_models", "https://huggingface.co/ExampleLab"), client=client)
    assert result["status"] == "failed"


def test_api_next_link_cannot_silently_narrow_the_collection():
    def handler(_):
        return httpx.Response(200, json=[], headers={
            "link": '<https://huggingface.co/api/models?author=ExampleLab&limit=100&search=only-one>; rel="next"',
        })

    with client_for(handler) as client:
        result = fetch_channel(channel("hf_models", "https://huggingface.co/ExampleLab"), client=client)
    assert result["status"] == "failed"


def test_response_size_limit_and_media_are_refused(monkeypatch):
    monkeypatch.setattr(research_sources, "MAX_RESPONSE_BYTES", 32)
    with client_for(lambda _: httpx.Response(200, content=b"x" * 33)) as client:
        assert fetch_channel(channel(), client=client)["status"] == "failed"
    with client_for(lambda _: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})) as client:
        assert fetch_channel(channel("webpage"), client=client)["status"] == "failed"


def test_exceptions_are_sanitized():
    def handler(_):
        raise httpx.ReadError("credentials=secret private configuration")

    with client_for(handler) as client:
        result = fetch_channel(channel(), client=client)
    assert result["status"] == "failed"
    assert result["items"] == []
    assert "secret" not in json.dumps(result)
    assert "configuration" not in json.dumps(result)


def test_page_and_total_bounds_refuse_incomplete_observation(monkeypatch):
    monkeypatch.setattr(research_sources, "MAX_PAGES", 1)

    def handler(_):
        return httpx.Response(200, json=[], headers={
            "link": '<https://huggingface.co/api/models?author=ExampleLab&cursor=next>; rel="next"',
        })

    with client_for(handler) as client:
        result = fetch_channel(channel("hf_models", "https://huggingface.co/ExampleLab"), client=client)
    assert result["status"] == "failed"
    assert result["items"] == []


def test_unknown_or_disabled_channel_does_not_request():
    def unexpected(_):
        pytest.fail("Disabled or invalid channel must not request")

    with client_for(unexpected) as client:
        invalid = fetch_channel(channel("unsupported"), client=client)
        disabled = fetch_channel({**channel(), "enabled": False}, client=client)
    assert invalid["status"] == "failed"
    assert disabled["status"] == "failed"


def _dns(*addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET,
             socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443)) for address in addresses]


def _capture_network(monkeypatch, addresses=("8.8.8.8",), handler=None):
    calls = []
    resolutions = []

    def resolve(host, port, **kwargs):
        resolutions.append((host, port))
        return _dns(*addresses)

    class FakeTransport(httpx.BaseTransport):
        def __init__(self, **kwargs):
            self.options = kwargs

        def handle_request(self, request):
            calls.append((request, self.options))
            return handler(request) if handler else httpx.Response(200, content=RSS)

    monkeypatch.setattr(research_http.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(research_http.httpx, "HTTPTransport", FakeTransport)
    monkeypatch.setattr(research_http, "getproxies", dict)
    return calls, resolutions


@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("::1",), ("10.0.0.1",),
                                       ("8.8.8.8", "192.168.0.1"), ("::ffff:127.0.0.1",)])
def test_default_network_refuses_private_or_mixed_dns_before_transport(monkeypatch, addresses):
    calls, _ = _capture_network(monkeypatch, addresses)
    result = fetch_channel(channel())
    assert result["status"] == "failed"
    assert result["diagnostic"]["code"] == "unsafe_url"
    assert calls == []


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700:4700::1111"])
def test_default_network_pins_global_ip_keeps_host_and_strict_tls(monkeypatch, address):
    calls, resolutions = _capture_network(monkeypatch, (address,))
    result = fetch_channel(channel())
    assert result["status"] == "ok"
    assert resolutions == [("research.example", 443)]
    request, options = calls[0]
    assert request.url.host == address
    assert request.headers["host"] == "research.example"
    assert isinstance(options["verify"], research_http.OriginTLSContext)
    assert options["verify"].check_hostname is True
    assert options["verify"].verify_mode == ssl.CERT_REQUIRED


def test_origin_context_restores_both_socket_and_bio_sni(monkeypatch):
    seen = []

    def wrap_socket(context, sock, **kwargs):
        seen.append(("socket", kwargs["server_hostname"], context.check_hostname))
        return object()

    def wrap_bio(context, incoming, outgoing, **kwargs):
        seen.append(("bio", kwargs["server_hostname"], context.check_hostname))
        return object()

    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
    monkeypatch.setattr(ssl.SSLContext, "wrap_bio", wrap_bio)
    context = research_http.OriginTLSContext("research.example", "8.8.8.8")
    context.wrap_socket(object(), server_hostname="8.8.8.8")
    context.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(), server_hostname="8.8.8.8")
    assert seen == [("socket", "research.example", True), ("bio", "research.example", True)]
    with pytest.raises(research_http.NetworkSafetyError):
        context.wrap_socket(object(), server_hostname="another.example")


@pytest.mark.parametrize("proxy_url", ["http://127.0.0.1:46993", "https://proxy.example:8443"])
def test_proxy_uses_original_host_selection_and_numeric_connect_target(monkeypatch, proxy_url):
    calls, _ = _capture_network(monkeypatch)
    monkeypatch.setattr(research_http, "getproxies", lambda: {"https": proxy_url})
    result = fetch_channel(channel())
    assert result["status"] == "ok"
    request, options = calls[0]
    assert request.url.host == "8.8.8.8"
    assert str(options["proxy"].url) == proxy_url
    if proxy_url.startswith("https:"):
        assert not isinstance(options["proxy"].ssl_context, research_http.OriginTLSContext)
        assert options["proxy"].ssl_context.check_hostname is True


def test_no_proxy_is_matched_before_numeric_ip_replacement(monkeypatch):
    calls, _ = _capture_network(monkeypatch)
    monkeypatch.setattr(research_http, "getproxies", lambda: {
        "https": "http://127.0.0.1:46993", "no": "research.example",
    })
    assert fetch_channel(channel())["status"] == "ok"
    assert calls[0][1]["proxy"] is None


def test_redirect_resolves_and_repins_each_original_host(monkeypatch):
    calls, resolutions = _capture_network(monkeypatch, handler=lambda request:
        httpx.Response(302, headers={"location": "https://second.example/feed"})
        if len(resolutions) == 1 else httpx.Response(200, content=RSS))
    assert fetch_channel(channel())["status"] == "ok"
    assert resolutions == [("research.example", 443), ("second.example", 443)]
    assert [request.headers["host"] for request, _ in calls] == ["research.example", "second.example"]


def test_rebinding_after_first_resolution_cannot_change_connection_host(monkeypatch):
    calls, resolutions = _capture_network(monkeypatch)
    original_resolve = research_http.socket.getaddrinfo

    def rebinding(host, port, **kwargs):
        if resolutions:
            return _dns("127.0.0.1")
        return original_resolve(host, port, **kwargs)

    monkeypatch.setattr(research_http.socket, "getaddrinfo", rebinding)
    assert fetch_channel(channel())["status"] == "ok"
    assert len(resolutions) == 1
    assert calls[0][0].url.host == "8.8.8.8"


def test_dns_timeout_is_sanitized_without_transport(monkeypatch):
    calls, _ = _capture_network(monkeypatch)

    def fail_dns(*args, **kwargs):
        raise TimeoutError("private resolver details")

    monkeypatch.setattr(research_http.socket, "getaddrinfo", fail_dns)
    result = fetch_channel(channel())
    assert result["status"] == "failed"
    assert "private resolver" not in json.dumps(result)
    assert calls == []


def test_non_mock_injected_client_is_explicitly_refused_without_dns(monkeypatch):
    with httpx.Client(trust_env=False) as client:
        result = fetch_channel(channel(), client=client)
        assert not client.is_closed
    assert result["status"] == "failed"
    assert result["diagnostic"]["code"] == "unsupported_client"


@pytest.mark.parametrize("proxy_url", [None, "http://127.0.0.1:46993", "https://proxy.example:8443"])
def test_real_httpcore_uses_pinned_connect_and_original_tls_identity_without_sockets(monkeypatch, proxy_url):
    connects, tls_names, writes = [], [], []

    class Stream:
        def __init__(self):
            self.read_count = 0
            self.tls_object = None

        def read(self, max_bytes, timeout=None):
            self.read_count += 1
            if proxy_url and self.read_count == 1:
                return b"HTTP/1.1 200 Connection Established\r\n\r\n"
            return b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(RSS)).encode() + b"\r\n\r\n" + RSS

        def write(self, buffer, timeout=None):
            writes.append(buffer)

        def close(self):
            pass

        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            self.tls_object = ssl_context.wrap_bio(
                ssl.MemoryBIO(), ssl.MemoryBIO(), server_hostname=server_hostname,
            )
            tls_names.append((server_hostname, self.tls_object.server_hostname,
                              ssl_context.check_hostname, ssl_context.verify_mode))
            return self

        def get_extra_info(self, key):
            return self.tls_object if key == "ssl_object" else False

    class Backend:
        def connect_tcp(self, host, port, **kwargs):
            connects.append((host, port))
            return Stream()

    original_transport = httpx.HTTPTransport

    def transport(**kwargs):
        instance = original_transport(**kwargs)
        instance._pool._network_backend = Backend()
        return instance

    monkeypatch.setattr(research_http.httpx, "HTTPTransport", transport)
    monkeypatch.setattr(research_http.socket, "getaddrinfo", lambda *args, **kwargs: _dns("8.8.8.8"))
    monkeypatch.setattr(research_http, "getproxies", lambda: {"https": proxy_url} if proxy_url else {})
    assert fetch_channel(channel())["status"] == "ok"
    expected_connect = (("127.0.0.1", 46993) if proxy_url and proxy_url.startswith("http:")
                        else ("proxy.example", 8443) if proxy_url else ("8.8.8.8", 443))
    assert connects == [expected_connect]
    assert tls_names[-1] == ("8.8.8.8", "research.example", True, ssl.CERT_REQUIRED)
    if proxy_url:
        assert b"CONNECT 8.8.8.8:443 HTTP/1.1" in writes[0]
    if proxy_url and proxy_url.startswith("https:"):
        assert tls_names[0] == ("proxy.example", "proxy.example", True, ssl.CERT_REQUIRED)
    assert any(b"Host: research.example\r\n" in chunk for chunk in writes)
