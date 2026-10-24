"""Bounded public research-channel acquisition; no knowledge bodies are retained.

Called by the outbound tracking script, not the deterministic local CLI. These are
observations of finite feeds, explicit pages or complete API lists, not a guarantee
that a content change represents scientific progress or usable model availability.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from scholar_workflow.adapters.research_http import (
    NetworkSafetyError,
    is_synthetic_client,
    send_pinned,
)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_PAGES = 20
MAX_ITEMS = 5000
MAX_REDIRECTS = 5
MAX_SECONDS = 45
REQUEST_SECONDS = 10
PAGE_SIZE = 100

_KINDS = {"rss", "atom", "webpage", "github_releases", "hf_models"}
_SECRET_QUERY = re.compile(
    r"(?:^|[-_])(?:token|key|secret|password|auth|credential)(?:$|[-_])", re.IGNORECASE,
)
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_DIAGNOSTICS = {
    "unsafe_url": "A channel or response URL is outside the public HTTPS boundary.",
    "invalid_channel": "The channel kind or enabled state is not valid for acquisition.",
    "disabled": "This channel is disabled; no request was made.",
    "http_error": "The public source returned an unsuccessful HTTP response.",
    "network_error": "The public source could not be read; no observation was committed.",
    "invalid_response": "The response is malformed or lacks required item information.",
    "unsafe_xml": "XML declarations or entities are not accepted.",
    "unsupported_content": "The response is not supported readable metadata or text.",
    "limit_exceeded": "The response, item, time or pagination bound was exceeded.",
    "incomplete_pagination": "API pagination did not prove a complete observation.",
    "unsupported_client": "Only synthetic MockTransport clients may be injected; normal acquisition uses IP pinning.",
    "unsupported_proxy": "The configured proxy type cannot preserve the required safe connection boundary.",
}


class _AcquisitionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _public_url(value: object, *, base: str | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise _AcquisitionError("unsafe_url")
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise _AcquisitionError("unsafe_url")
    try:
        parts = urlsplit(urljoin(base, value) if base else value)
        host = (parts.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
        port = parts.port
    except (ValueError, UnicodeError):
        raise _AcquisitionError("unsafe_url") from None
    if (parts.scheme != "https" or not host or parts.username is not None
            or parts.password is not None or parts.fragment):
        raise _AcquisitionError("unsafe_url")
    if ("%" in host or host == "localhost"
            or host.endswith((".localhost", ".local", ".internal", ".onion"))):
        raise _AcquisitionError("unsafe_url")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.startswith("0x") or host.rsplit(".", 1)[-1].isdigit():
            raise _AcquisitionError("unsafe_url") from None
    else:
        if (not address.is_global or address.is_multicast or address.is_reserved
                or getattr(address, "is_site_local", False)):
            raise _AcquisitionError("unsafe_url")
    if any(_SECRET_QUERY.search(key) or key.lower() in {"apikey", "accesstoken", "authorization"}
           for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
        raise _AcquisitionError("unsafe_url")
    authority = f"[{host}]" if ":" in host else host
    if port is not None and port != 443:
        authority += f":{port}"
    return urlunsplit(("https", authority, parts.path or "/", parts.query, ""))


def _value(value: object, *, limit: int = 512, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise _AcquisitionError("invalid_response")
    result = " ".join(unicodedata.normalize("NFC", value).split())
    if required and not result:
        raise _AcquisitionError("invalid_response")
    if any(ord(char) < 32 or ord(char) == 127 for char in result):
        raise _AcquisitionError("invalid_response")
    return result


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class _ReadableHTML(HTMLParser):
    """A narrow text projection: prefer article/main and discard page chrome.

    This is not browser rendering or an unrestricted readability implementation.
    Script-only/empty pages fail rather than acquiring a misleading empty body.
    """

    _SKIP = frozenset({"script", "style", "nav", "header", "footer", "aside", "form", "button",
                       "noscript", "template", "svg", "canvas"})
    _VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                       "meta", "param", "source", "track", "wbr"})
    _BLOCK = frozenset({"article", "body", "main", "section", "div", "p", "li", "ul", "ol",
                        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "table", "tr", "td", "br", "hr"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.texts: dict[str, list[str]] = {key: [] for key in ("all", "body", "main", "article", "title")}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
        hidden = (tag in self._SKIP or "hidden" in attributes
                  or attributes.get("aria-hidden") == "true"
                  or "display:none" in style or "visibility:hidden" in style)
        if tag not in self._VOID:
            self.stack.append((tag, hidden))
        if tag in self._BLOCK:
            self.handle_data(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK:
            self.handle_data(" ")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if any(hidden for _, hidden in self.stack):
            return
        tags = {tag for tag, _ in self.stack}
        if "title" in tags:
            self.texts["title"].append(data)
            return
        if "head" in tags:
            return
        self.texts["all"].append(data)
        for region in ("body", "main", "article"):
            if region in tags:
                self.texts[region].append(data)

    def readable(self) -> str:
        for region in ("article", "main", "body", "all"):
            text = " ".join("".join(self.texts[region]).split())
            if text:
                return unicodedata.normalize("NFC", text)
        return ""


def _html_text(raw: str) -> tuple[str, str]:
    parser = _ReadableHTML()
    parser.feed(raw)
    parser.close()
    title = " ".join("".join(parser.texts["title"]).split())
    return title, parser.readable()


class _Reader:
    def __init__(self, client: httpx.Client | None):
        self.client = client
        self.deadline = time.monotonic() + MAX_SECONDS
        self.bytes_read = 0

    def get(self, url: str, headers: dict[str, str] | None = None,
            *, api_scope: tuple[str, str, str | None] | None = None) -> tuple[int, dict, bytes, str]:
        target = _public_url(url)
        request_headers = {"User-Agent": "scholar-workflow-research-tracker",
                           "Accept": "application/json, application/atom+xml, application/rss+xml, text/html;q=0.8"}
        request_headers.update(headers or {})
        for _ in range(MAX_REDIRECTS + 1):
            _check_api_url(target, api_scope)
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise _AcquisitionError("limit_exceeded")
            timeout = min(REQUEST_SECONDS, remaining)
            # A fresh Request avoids injected client cookies/default secret headers.
            request = httpx.Request("GET", target, headers=request_headers, extensions={
                "timeout": {key: timeout for key in ("connect", "read", "write", "pool")},
            })
            owned_client = None
            if self.client is None:
                response, owned_client = send_pinned(request, timeout=timeout)
            else:
                response = self.client.send(request, stream=True, auth=None, follow_redirects=False)
            try:
                response_headers = dict(response.headers)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise _AcquisitionError("invalid_response")
                    next_target = _public_url(location, base=target)
                    if urlsplit(next_target).netloc != urlsplit(target).netloc:
                        request_headers.pop("If-None-Match", None)
                        request_headers.pop("If-Modified-Since", None)
                    target = next_target
                    continue
                if response.status_code == 304:
                    return 304, response_headers, b"", target
                if response.status_code != 200:
                    raise _AcquisitionError("http_error")
                length = response.headers.get("content-length", "")
                if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
                    raise _AcquisitionError("limit_exceeded")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    self.bytes_read += len(chunk)
                    if (len(body) > MAX_RESPONSE_BYTES or self.bytes_read > MAX_TOTAL_BYTES
                            or time.monotonic() > self.deadline):
                        raise _AcquisitionError("limit_exceeded")
                return 200, response_headers, bytes(body), target
            finally:
                response.close()
                if owned_client is not None:
                    owned_client.close()
        raise _AcquisitionError("limit_exceeded")


def _check_api_url(url: str, scope: tuple[str, str, str | None] | None) -> None:
    if scope is None:
        return
    host, path, author = scope
    parts = urlsplit(url)
    if parts.netloc != host or parts.path != path:
        raise _AcquisitionError("incomplete_pagination")
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    params = dict(pairs)
    if author is not None:
        allowed = {"author", "limit", "expand", "cursor"}
        if (params.get("author") != author or params.get("limit") != str(PAGE_SIZE)
                or any(key not in allowed for key, _ in pairs)
                or any(sum(key == other for other, _ in pairs) > 1
                       for key in ("author", "limit", "cursor"))):
            raise _AcquisitionError("incomplete_pagination")
    elif (set(params) != {"per_page", "page"} or len(pairs) != 2
          or params.get("per_page") != str(PAGE_SIZE)
          or not params.get("page", "").isdigit() or int(params["page"]) < 1):
        raise _AcquisitionError("incomplete_pagination")


def _decode(body: bytes, headers: dict) -> str:
    content_type = headers.get("content-type", "").lower().split(";", 1)[0].strip()
    if content_type and content_type not in {
        "text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml",
        "application/atom+xml", "application/rss+xml", "application/json", "application/feed+json",
    }:
        raise _AcquisitionError("unsupported_content")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _AcquisitionError("invalid_response") from None
    if "\x00" in text:
        raise _AcquisitionError("invalid_response")
    return text


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element if _local(child.tag) == name), None)


def _node_text(element: ET.Element, name: str) -> str:
    child = _child(element, name)
    return "" if child is None else "".join(child.itertext()).strip()


def _item(item_id: str, url: str, title: str, content: object, *, published: object = None,
          updated: object = None, version: object = None) -> dict:
    result = {"item_id": _value(item_id), "url": _public_url(url),
              "title": _value(title, limit=1000), "content_digest": _digest(content)}
    for key, value in (("published_at", published), ("updated_at", updated), ("version", version)):
        if value is not None and value != "":
            result[key] = _value(value, limit=128)
    return result


def _feed(kind: str, raw: str, base: str) -> list[dict]:
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.IGNORECASE):
        raise _AcquisitionError("unsafe_xml")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise _AcquisitionError("invalid_response") from None
    if sum(1 for _ in root.iter()) > MAX_ITEMS * 30:
        raise _AcquisitionError("limit_exceeded")
    if kind == "rss":
        channel = _child(root, "channel")
        if _local(root.tag) != "rss" or channel is None:
            raise _AcquisitionError("invalid_response")
        entries = [element for element in channel if _local(element.tag) == "item"]
    else:
        if _local(root.tag) != "feed":
            raise _AcquisitionError("invalid_response")
        entries = [element for element in root if _local(element.tag) == "entry"]
    xml_base = "{http://www.w3.org/XML/1998/namespace}base"
    feed_base = _public_url(root.attrib.get(xml_base) or base, base=base)
    result = []
    for entry in entries:
        title = _value(_node_text(entry, "title"), limit=1000)
        if kind == "rss":
            link = _node_text(entry, "link")
            identity = _node_text(entry, "guid")
            content = _node_text(entry, "encoded") or _node_text(entry, "description")
            published = _node_text(entry, "pubDate") or _node_text(entry, "date")
            updated = None
        else:
            entry_base = _public_url(entry.attrib.get(xml_base) or feed_base, base=feed_base)
            links = [node for node in entry if _local(node.tag) == "link"
                     and node.attrib.get("rel", "alternate") == "alternate"]
            link_node = next((node for node in links if node.attrib.get("type", "text/html")
                              in {"text/html", "application/xhtml+xml"}), None)
            if link_node is None:
                raise _AcquisitionError("invalid_response")
            link_base = _public_url(link_node.attrib.get(xml_base) or entry_base, base=entry_base)
            link = _public_url(link_node.attrib.get("href", ""), base=link_base)
            identity = _node_text(entry, "id")
            content = _node_text(entry, "content") or _node_text(entry, "summary")
            published = _node_text(entry, "published")
            updated = _node_text(entry, "updated")
        url = _public_url(link, base=base)
        _, clean_content = _html_text(content)
        result.append(_item(identity or url, url, title, {"title": title, "text": clean_content, "url": url},
                            published=published, updated=updated))
    return _deduplicate(result)


def _deduplicate(items: list[dict]) -> list[dict]:
    if len(items) > MAX_ITEMS:
        raise _AcquisitionError("limit_exceeded")
    indexed: dict[str, dict] = {}
    for item in items:
        if item["item_id"] in indexed and indexed[item["item_id"]] != item:
            raise _AcquisitionError("invalid_response")
        indexed[item["item_id"]] = item
    return list(indexed.values())


def _next_page(link_header: str, base: str) -> str | None:
    if not link_header:
        return None
    next_links = []
    for part in re.split(r",(?=\s*<)", link_header):
        match = re.fullmatch(r'\s*<([^>]+)>\s*((?:;[^,]*)?)\s*', part)
        if not match:
            raise _AcquisitionError("incomplete_pagination")
        relations = re.findall(r';\s*rel\s*=\s*"?([^";]+)"?', match[2], flags=re.IGNORECASE)
        if any("next" in relation.strip().split() for relation in relations):
            next_links.append(_public_url(match[1], base=base))
    if len(next_links) > 1:
        raise _AcquisitionError("incomplete_pagination")
    return next_links[0] if next_links else None


def _github_item(row: object, owner: str, repo: str) -> dict:
    if not isinstance(row, dict) or not isinstance(row.get("id"), int) or isinstance(row["id"], bool):
        raise _AcquisitionError("invalid_response")
    if row.get("draft") is True:
        raise _AcquisitionError("invalid_response")
    url = _public_url(row.get("html_url"))
    parts = urlsplit(url)
    if (parts.netloc != "github.com"
            or not parts.path.casefold().startswith(f"/{owner}/{repo}/releases/".casefold())):
        raise _AcquisitionError("invalid_response")
    version = _value(row.get("tag_name"), limit=128)
    title = _value(row.get("name") or version, limit=1000)
    body = _value(row.get("body") or "", limit=MAX_RESPONSE_BYTES, required=False)
    _, text = _html_text(body)
    content = {"title": title, "body": text, "version": version,
               "prerelease": row.get("prerelease", False), "url": url}
    return _item(f"github-release:{row['id']}", url, title, content,
                 published=row.get("published_at"), updated=row.get("updated_at"), version=version)


def _hf_item(row: object, author: str) -> dict:
    if not isinstance(row, dict):
        raise _AcquisitionError("invalid_response")
    identity = _value(row.get("id"))
    parts = identity.split("/")
    if (len(parts) != 2 or parts[0].casefold() != author.casefold()
            or not all(_SEGMENT.fullmatch(part) for part in parts)
            or row.get("private") is True):
        raise _AcquisitionError("invalid_response")
    version = _value(row.get("sha"), limit=128, required=False)
    # Popularity counters and list order are deliberately excluded from progress.
    content = {key: row[key] for key in ("sha", "pipeline_tag", "tags", "gated", "disabled", "cardData")
               if key in row}
    if "tags" in content:
        tags = content["tags"]
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise _AcquisitionError("invalid_response")
        content["tags"] = sorted(tags)
    return _item(f"hf-model:{identity}", f"https://huggingface.co/{identity}", identity, content,
                 published=row.get("createdAt"), updated=row.get("lastModified"), version=version)


def _api(reader: _Reader, kind: str, registered_url: str) -> list[dict]:
    parts = urlsplit(registered_url)
    segments = parts.path.strip("/").split("/")
    if parts.query or parts.port not in {None, 443}:
        raise _AcquisitionError("unsafe_url")
    if kind == "github_releases":
        if parts.hostname != "github.com" or len(segments) != 2 or not all(_SEGMENT.fullmatch(s) for s in segments):
            raise _AcquisitionError("unsafe_url")
        owner, repo = segments
        path = f"/repos/{owner}/{repo}/releases"
        scope = ("api.github.com", path, None)
        target = f"https://api.github.com{path}?per_page={PAGE_SIZE}&page=1"
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    else:
        if parts.hostname != "huggingface.co" or len(segments) != 1 or not _SEGMENT.fullmatch(segments[0]):
            raise _AcquisitionError("unsafe_url")
        author = segments[0]
        scope = ("huggingface.co", "/api/models", author)
        params = [("author", author), ("limit", str(PAGE_SIZE))]
        params += [("expand", name) for name in ("sha", "createdAt", "lastModified", "pipeline_tag", "tags", "gated", "disabled")]
        target = "https://huggingface.co/api/models?" + urlencode(params)
        headers = {"Accept": "application/json"}
    seen: set[str] = set()
    result = []
    for _ in range(MAX_PAGES):
        if target in seen:
            raise _AcquisitionError("incomplete_pagination")
        seen.add(target)
        status, response_headers, body, final_url = reader.get(target, headers, api_scope=scope)
        if status != 200:
            raise _AcquisitionError("incomplete_pagination")
        try:
            rows = json.loads(_decode(body, response_headers))
        except (json.JSONDecodeError, ValueError):
            raise _AcquisitionError("invalid_response") from None
        if not isinstance(rows, list):
            raise _AcquisitionError("invalid_response")
        for row in rows:
            result.append(_github_item(row, owner, repo) if kind == "github_releases" else _hf_item(row, author))
        if len(result) > MAX_ITEMS:
            raise _AcquisitionError("limit_exceeded")
        next_url = _next_page(response_headers.get("link", ""), final_url)
        if next_url is None:
            if len(rows) >= PAGE_SIZE:
                raise _AcquisitionError("incomplete_pagination")
            return _deduplicate(result)
        _check_api_url(next_url, scope)
        target = next_url
    raise _AcquisitionError("limit_exceeded")


def _validators(headers: dict) -> dict:
    result = {}
    for header, key in (("etag", "etag"), ("last-modified", "last_modified")):
        value = headers.get(header)
        if isinstance(value, str) and len(value) <= 512 and all(32 <= ord(c) < 127 for c in value):
            result[key] = value
    return result


def fetch_channel(channel: dict, previous: dict | None = None, *,
                  client: httpx.Client | None = None) -> dict:
    """Read one explicitly registered channel; failures always contain zero items.

    The caller owns durable checkpoints and determines whether a 304 has a valid
    successful baseline. API list requests never use a first-page ETag as evidence
    that later pages are unchanged. Injected clients stay open and make no DNS
    requests when backed by MockTransport. Default clients retain environment proxy
    routing, but no source authentication or user headers are forwarded.
    """
    try:
        if not isinstance(channel, dict) or channel.get("kind") not in _KINDS:
            raise _AcquisitionError("invalid_channel")
        if channel.get("enabled") is not True:
            raise _AcquisitionError("disabled")
        url = _public_url(channel.get("url"))
        if client is not None and not is_synthetic_client(client):
            raise _AcquisitionError("unsupported_client")
        reader = _Reader(client)
        kind = channel["kind"]
        if kind in {"github_releases", "hf_models"}:
            return {"status": "ok", "items": _api(reader, kind, url)}
        headers = {}
        previous = previous if isinstance(previous, dict) else {}
        for key, header in (("etag", "If-None-Match"), ("last_modified", "If-Modified-Since")):
            value = previous.get(key)
            if isinstance(value, str) and len(value) <= 512 and all(32 <= ord(c) < 127 for c in value):
                headers[header] = value
        status, response_headers, body, final_url = reader.get(url, headers)
        validators = _validators(response_headers)
        if status == 304:
            return {"status": "not_modified", "items": [], **validators}
        raw = _decode(body, response_headers)
        if kind in {"rss", "atom"}:
            items = _feed(kind, raw, final_url)
        else:
            title, text = _html_text(raw)
            if not text:
                raise _AcquisitionError("unsupported_content")
            title = title or channel.get("name") or "Research page"
            items = [_item(url, url, title, {"title": title, "text": text})]
        return {"status": "ok", "items": items, **validators}
    except (_AcquisitionError, NetworkSafetyError) as error:
        code = error.code
    except (httpx.HTTPError, OSError):
        code = "network_error"
    except (TypeError, ValueError, OverflowError, RecursionError):
        code = "invalid_response"
    except Exception:  # noqa: BLE001 - This outbound boundary must sanitize arbitrary transport errors.
        # Remote parse/transport implementations must not expose exception bodies.
        code = "invalid_response"
    return {"status": "failed", "items": [], "diagnostic": {"code": code, "message": _DIAGNOSTICS[code]}}
