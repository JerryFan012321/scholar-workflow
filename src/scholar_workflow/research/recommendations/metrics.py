"""Bounded anonymous observations from explicitly declared public repositories."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx


_MAX_TARGETS = 6
_MAX_BODY = 256 * 1024
_TIMEOUT = 5.0
_GITHUB_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
_REPO_NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_HF_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")
_GITHUB_ROUTES = {
    "apps", "collections", "discussions", "enterprise", "explore", "features",
    "issues", "login", "marketplace", "notifications", "orgs", "pulls", "search",
    "settings", "signup", "sponsors", "stars", "topics", "users",
}
_HF_ROUTES = {
    "api", "blog", "chat", "collections", "datasets", "docs", "enterprise",
    "inference-api", "join", "learn", "login", "models", "notifications",
    "organizations", "papers", "pricing", "settings", "spaces", "tasks",
}


def _target(url) -> dict | None:
    if (not isinstance(url, str) or not url or len(url) > 4096
            or any(ord(char) <= 32 or ord(char) == 127 for char in url)
            or "?" in url or "#" in url):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = parsed.netloc.casefold()
    if parsed.scheme != "https" or host not in {"github.com", "huggingface.co"}:
        return None
    parts = parsed.path.removesuffix("/").split("/")[1:]
    if not parts or any(not _REPO_NAME.fullmatch(part) or part in {".", ".."}
                        or part.casefold().endswith(".git") for part in parts):
        return None
    if host == "github.com":
        if (len(parts) != 2 or not _GITHUB_OWNER.fullmatch(parts[0])
                or parts[0].casefold() in _GITHUB_ROUTES):
            return None
        return {"platform": "github", "metric": "stars", "url": url,
                "api_url": "https://api.github.com/repos/" + "/".join(parts)}
    repo_type = "models"
    if len(parts) == 3 and parts[0] in {"datasets", "spaces"}:
        repo_type, parts = parts[0], parts[1:]
    elif len(parts) != 2 or parts[0].casefold() in _HF_ROUTES:
        return None
    if not _HF_OWNER.fullmatch(parts[0]):
        return None
    return {"platform": "huggingface", "metric": "likes", "url": url,
            "api_url": f"https://huggingface.co/api/{repo_type}/{'/'.join(parts)}?expand=likes"}


def metric_targets(resource: dict) -> list[dict]:
    """Identify up to six declared repository homepages without fetching other pages."""
    if not isinstance(resource, dict):
        return []
    urls = [resource.get("url"), resource.get("project_url")]
    links = resource.get("links", [])
    if isinstance(links, list):
        urls.extend(link.get("url") for link in links[:30] if isinstance(link, dict))
    targets, seen = [], set()
    for url in urls:
        target = _target(url)
        if target is None:
            continue
        identity = target["api_url"]
        if target["platform"] == "github":
            identity = identity.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        targets.append(target)
        if len(targets) == _MAX_TARGETS:
            break
    return targets


def _payload(response: httpx.Response, deadline: float):
    # Identity encoding keeps the byte cap meaningful before JSON decoding.
    if response.headers.get("content-encoding", "identity").casefold() != "identity":
        raise ValueError("Encoded metric body is unavailable.")
    content_length = response.headers.get("content-length", "")
    if content_length.isdecimal() and int(content_length) > _MAX_BODY:
        raise ValueError("Metric body is too large.")
    body = bytearray()
    for chunk in response.iter_bytes():
        if len(body) + len(chunk) > _MAX_BODY or time.monotonic() > deadline:
            raise ValueError("Metric body limit exceeded.")
        body.extend(chunk)
    if time.monotonic() > deadline:
        raise ValueError("Metric request deadline exceeded.")
    return json.loads(body)


def _observe(target: dict, client: httpx.Client) -> tuple[str, int | None]:
    headers = {
        "Accept": "application/vnd.github+json" if target["platform"] == "github"
        else "application/json",
        "Accept-Encoding": "identity", "User-Agent": "scholar-workflow",
    }
    # Building the request directly avoids client default headers and cookies.
    request = httpx.Request("GET", target["api_url"], headers=headers, extensions={
        "timeout": httpx.Timeout(_TIMEOUT).as_dict(),
    })
    deadline = time.monotonic() + _TIMEOUT
    try:
        response = client.send(request, stream=True, auth=None, follow_redirects=False)
        try:
            if response.status_code == 429:
                return "rate_limited", None
            if response.status_code == 403:
                if (response.headers.get("x-ratelimit-remaining") == "0"
                        or response.headers.get("retry-after")):
                    return "rate_limited", None
                payload = _payload(response, deadline)
                message = payload.get("message", "") if isinstance(payload, dict) else ""
                if isinstance(message, str) and "rate limit" in message.casefold():
                    return "rate_limited", None
                return "unavailable", None
            if response.status_code != 200:
                return "unavailable", None
            payload = _payload(response, deadline)
        finally:
            response.close()
    except (httpx.HTTPError, ValueError, RecursionError):
        return "unavailable", None
    if not isinstance(payload, dict) or payload.get("private") is True:
        return "unavailable", None
    field = "stargazers_count" if target["platform"] == "github" else "likes"
    value = payload.get(field)
    if type(value) is not int or value < 0:
        return "unavailable", None
    return "ok", value


def collect_metrics(resource: dict, client: httpx.Client | None = None) -> dict:
    """Collect raw public counts, keeping failures separate from observations."""
    targets = metric_targets(resource)
    if not targets:
        return {"observations": [], "checks": []}
    if client is None:
        with httpx.Client(trust_env=False, timeout=_TIMEOUT, follow_redirects=False) as owned:
            return _collect(targets, owned)
    return _collect(targets, client)


def _collect(targets: list[dict], client: httpx.Client) -> dict:
    observations, checks = [], []
    for target in targets:
        status, value = _observe(target, client)
        timestamp = datetime.now(timezone.utc).isoformat()
        identity = {key: target[key] for key in ("platform", "metric", "url")}
        checks.append({**identity, "status": status, "checked_at": timestamp})
        if status == "ok":
            observations.append({**identity, "value": value, "observed_at": timestamp})
    return {"observations": observations, "checks": checks}
