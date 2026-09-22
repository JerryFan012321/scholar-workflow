"""Zotero 10+ Local API transport with loopback-only write authorization."""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import os
import re
import subprocess
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Self
from urllib.parse import urlparse
from uuid import uuid4

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:23119/api/"
API_VERSION = "3"
KEY_ENV_VAR = "SCHOLAR_WORKFLOW_ZOTERO_LOCAL_API_KEY"
KEYCHAIN_SERVICE = "scholar-workflow.zotero-local"
ZOTERO_KEY_RE = re.compile(r"^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$")
_ITEM_TYPE_SEARCH_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9]*(?: \|\| [A-Za-z][A-Za-z0-9]*)*$"
)
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024 - 1
UPLOAD_CHUNK_BYTES = 1024 * 1024


class ZoteroLocalError(RuntimeError):
    """A Local API request failed or returned an unsafe response."""


class ZoteroLocalUnavailable(ZoteroLocalError):
    """Zotero's Local API is not reachable."""


class ZoteroAuthorizationError(ZoteroLocalError):
    """Zotero did not grant a usable local write key."""


class ZoteroFileUploadError(ZoteroLocalError):
    """An attachment item exists, but its file upload did not finish."""

    def __init__(self, attachment_key: str, detail: str) -> None:
        self.attachment_key = attachment_key
        super().__init__(
            f"Zotero attachment {attachment_key} exists but its upload failed: {detail}"
        )


class LocalKeyStore(Protocol):
    """Storage boundary for a Zotero Local API key."""

    def get(self, server_id: str) -> str | None: ...

    def put(self, server_id: str, key: str) -> None: ...

    def delete(self, server_id: str) -> None: ...


Runner = Callable[..., subprocess.CompletedProcess[str]]


class MacOSKeychainStore:
    """Store remembered Local API keys in the current user's macOS Keychain."""

    def __init__(self, runner: Runner = subprocess.run) -> None:
        self._runner = runner

    def get(self, server_id: str) -> str | None:
        environment_key = os.environ.get(KEY_ENV_VAR)
        if environment_key:
            return environment_key
        try:
            result = self._runner(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    server_id,
                    "-s",
                    KEYCHAIN_SERVICE,
                    "-w",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ZoteroAuthorizationError(
                "macOS Keychain command is unavailable; set "
                f"{KEY_ENV_VAR} for this process instead"
            ) from exc
        if result.returncode == 44:
            return None
        if result.returncode != 0:
            raise ZoteroAuthorizationError("could not read the Zotero key from macOS Keychain")
        return result.stdout.rstrip("\n") or None

    def put(self, server_id: str, key: str) -> None:
        try:
            result = self._runner(
                [
                    "security",
                    "add-generic-password",
                    "-a",
                    server_id,
                    "-s",
                    KEYCHAIN_SERVICE,
                    "-w",
                    key,
                    "-U",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ZoteroAuthorizationError("macOS Keychain command is unavailable") from exc
        if result.returncode != 0:
            raise ZoteroAuthorizationError("could not save the Zotero key to macOS Keychain")

    def delete(self, server_id: str) -> None:
        if os.environ.get(KEY_ENV_VAR):
            return
        try:
            result = self._runner(
                [
                    "security",
                    "delete-generic-password",
                    "-a",
                    server_id,
                    "-s",
                    KEYCHAIN_SERVICE,
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ZoteroAuthorizationError("macOS Keychain command is unavailable") from exc
        if result.returncode not in {0, 44}:
            raise ZoteroAuthorizationError("could not clear the rejected Zotero key")


@dataclass(frozen=True)
class ServerInfo:
    """Identity and protocol versions reported by the running Zotero instance."""

    server_id: str
    api_version: str
    schema_version: str | None


@dataclass(frozen=True)
class Authorization:
    """A local write authorization; the key is deliberately hidden from repr."""

    key: str = field(repr=False)
    remember: bool


@dataclass(frozen=True)
class ZoteroItemPage:
    """One server-paginated page from the Zotero Local API."""

    items: tuple[dict[str, Any], ...]
    start: int
    limit: int
    total: int | None


def _is_loopback_url(url: str, *, api_root: bool = False) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname != "localhost":
        try:
            if not ipaddress.ip_address(hostname).is_loopback:
                return False
        except ValueError:
            return False
    return not api_root or parsed.path.rstrip("/") == "/api"


def _validate_key(key: str) -> str:
    if not ZOTERO_KEY_RE.fullmatch(key):
        raise ValueError("invalid Zotero object key")
    return key


class ZoteroLocalAdapter:
    """Read and write the current user's Zotero library over its Local API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        client: httpx.Client | None = None,
        key_store: LocalKeyStore | None = None,
    ) -> None:
        effective_base_url = str(client.base_url) if client is not None else base_url
        if not _is_loopback_url(effective_base_url, api_root=True):
            raise ValueError("Zotero Local API base URL must be an HTTP loopback /api URL")
        self._base_port = urlparse(effective_base_url).port or 80
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=15,
            follow_redirects=False,
            trust_env=False,
        )
        self._key_store = key_store or MacOSKeychainStore()
        self._server: ServerInfo | None = None
        self._authorization: Authorization | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise ZoteroLocalUnavailable(
                "Zotero Local API is unavailable; start Zotero and enable its Local API. "
                "In a sandboxed host, grant localhost/network access and retry"
            ) from exc
        if response.status_code == 401:
            self._authorization = None
            delete = getattr(self._key_store, "delete", None)
            if self._server is not None and delete is not None:
                delete(self._server.server_id)
            raise ZoteroAuthorizationError("Zotero rejected the local write authorization")
        if response.status_code == 403 and method == "GET" and url in {"", "/"}:
            raise ZoteroLocalUnavailable(
                "Zotero Local API is disabled; enable it in Zotero Settings → Advanced"
            )
        request_path = urlparse(url).path.rstrip("/")
        if response.status_code == 403 and request_path.endswith("local/authorize"):
            raise ZoteroAuthorizationError("Zotero write authorization was denied")
        if response.status_code >= 400:
            detail = response.text[:300].strip()
            suffix = f": {detail}" if detail else ""
            raise ZoteroLocalError(
                f"Zotero Local API returned HTTP {response.status_code}{suffix}"
            )
        return response

    @staticmethod
    def _read_server_info(response: httpx.Response) -> ServerInfo:
        server_id = response.headers.get("Zotero-Server-ID")
        api_version = response.headers.get("Zotero-API-Version")
        if not server_id:
            raise ZoteroLocalError("Zotero Local API response omitted Zotero-Server-ID")
        if api_version != API_VERSION:
            raise ZoteroLocalError(
                f"unsupported Zotero Local API version {api_version!r}; expected {API_VERSION}"
            )
        return ServerInfo(
            server_id=server_id,
            api_version=api_version,
            schema_version=response.headers.get("Zotero-Schema-Version"),
        )

    def probe(self) -> ServerInfo:
        response = self._request("GET", "")
        self._server = self._read_server_info(response)
        return self._server

    def _ensure_server(self) -> ServerInfo:
        return self._server or self.probe()

    def authorize(self) -> Authorization:
        server = self._ensure_server()
        response = self._request(
            "POST",
            "local/authorize",
            headers={
                "Zotero-API-Version": API_VERSION,
                "Zotero-Server-ID": server.server_id,
            },
            json={"appName": "Scholar Workflow"},
        )
        payload = response.json()
        key = payload.get("key")
        if not isinstance(key, str) or not key:
            raise ZoteroAuthorizationError("Zotero did not return a local write key")
        authorization = Authorization(key=key, remember=bool(payload.get("remember")))
        self._authorization = authorization
        if authorization.remember:
            self._key_store.put(server.server_id, authorization.key)
        return authorization

    def ensure_write_authorization(self, *, require_remembered: bool = False) -> Authorization:
        server = self._ensure_server()
        authorization = self._authorization
        if authorization is None:
            stored_key = self._key_store.get(server.server_id)
            if stored_key:
                authorization = Authorization(key=stored_key, remember=True)
                self._authorization = authorization
            else:
                authorization = self.authorize()
        if require_remembered and not authorization.remember:
            raise ZoteroAuthorizationError(
                "this operation needs a persistent key; choose Always Allow in Zotero"
            )
        return authorization

    def _write_headers(
        self,
        *,
        require_remembered: bool = False,
        include_write_token: bool = True,
    ) -> dict[str, str]:
        server = self._ensure_server()
        authorization = self.ensure_write_authorization(require_remembered=require_remembered)
        headers = {
            "Zotero-API-Version": API_VERSION,
            "Zotero-Server-ID": server.server_id,
            "Zotero-API-Key": authorization.key,
        }
        if include_write_token:
            headers["Zotero-Write-Token"] = uuid4().hex
        return headers

    def search_items(
        self,
        query: str,
        *,
        qmode: str = "titleCreatorYear",
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        if qmode not in {"titleCreatorYear", "everything"}:
            raise ValueError("qmode must be titleCreatorYear or everything")
        params: dict[str, str | int] = {"q": query, "qmode": qmode}
        if limit is not None:
            params["limit"] = limit
        response = self._request(
            "GET",
            "users/0/items/top",
            headers={"Zotero-API-Version": API_VERSION},
            params=params,
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise ZoteroLocalError("Zotero search returned an unexpected response")
        return payload

    def list_items_page(
        self,
        *,
        start: int,
        limit: int,
        query: str | None = None,
        qmode: str = "titleCreatorYear",
        sort: str = "title",
        direction: str = "asc",
        item_type: str | None = None,
    ) -> ZoteroItemPage:
        """Read one top-level library page without materializing the whole library."""
        if isinstance(start, bool) or start < 0:
            raise ValueError("start must be a non-negative integer")
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if qmode not in {"titleCreatorYear", "everything"}:
            raise ValueError("qmode must be titleCreatorYear or everything")
        if sort not in {"title", "date", "dateAdded"}:
            raise ValueError("unsupported Zotero page sort")
        if direction not in {"asc", "desc"}:
            raise ValueError("direction must be asc or desc")
        if (
            item_type is not None
            and (len(item_type) > 1024 or not _ITEM_TYPE_SEARCH_RE.fullmatch(item_type))
        ):
            raise ValueError("invalid Zotero item type filter")
        params: dict[str, str | int] = {
            "start": start,
            "limit": limit,
            "sort": sort,
            "direction": direction,
        }
        if item_type is not None:
            params["itemType"] = item_type
        if query:
            if query != query.strip() or len(query) > 200:
                raise ValueError("query must be clean text of at most 200 characters")
            params.update({"q": query, "qmode": qmode})
        response = self._request(
            "GET",
            "users/0/items/top",
            headers={"Zotero-API-Version": API_VERSION},
            params=params,
        )
        payload = response.json()
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ZoteroLocalError("Zotero library page returned an unexpected response")
        total_header = response.headers.get("Total-Results")
        try:
            total = int(total_header) if total_header is not None else None
        except ValueError as exc:
            raise ZoteroLocalError("Zotero library page returned an invalid total") from exc
        if total is not None and total < 0:
            raise ZoteroLocalError("Zotero library page returned an invalid total")
        return ZoteroItemPage(
            items=tuple(payload),
            start=start,
            limit=limit,
            total=total,
        )

    def get_item(self, item_key: str) -> dict[str, Any]:
        item_key = _validate_key(item_key)
        response = self._request(
            "GET",
            f"users/0/items/{item_key}",
            headers={"Zotero-API-Version": API_VERSION},
        )
        return response.json()

    def get_children(self, item_key: str) -> list[dict[str, Any]]:
        item_key = _validate_key(item_key)
        response = self._request(
            "GET",
            f"users/0/items/{item_key}/children",
            headers={"Zotero-API-Version": API_VERSION},
        )
        return response.json()

    def get_item_template(
        self,
        item_type: str,
        *,
        link_mode: str | None = None,
    ) -> dict[str, Any]:
        params = {"itemType": item_type}
        if link_mode is not None:
            params["linkMode"] = link_mode
        response = self._request(
            "GET",
            "items/new",
            headers={"Zotero-API-Version": API_VERSION},
            params=params,
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ZoteroLocalError("Zotero item template returned an unexpected response")
        return payload

    def get_fulltext(self, attachment_key: str) -> dict[str, Any]:
        attachment_key = _validate_key(attachment_key)
        response = self._request(
            "GET",
            f"users/0/items/{attachment_key}/fulltext",
            headers={"Zotero-API-Version": API_VERSION},
        )
        return response.json()

    def get_collections(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "users/0/collections",
            headers={"Zotero-API-Version": API_VERSION},
            params={"limit": limit} if limit is not None else None,
        )
        return response.json()

    def get_collection_items(
        self, collection_key: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        collection_key = _validate_key(collection_key)
        response = self._request(
            "GET",
            f"users/0/collections/{collection_key}/items/top",
            headers={"Zotero-API-Version": API_VERSION},
            params={"limit": limit} if limit is not None else None,
        )
        return response.json()

    def create_item(self, item: Mapping[str, Any]) -> str:
        response = self._request(
            "POST",
            "users/0/items",
            headers=self._write_headers(),
            json=[dict(item)],
        )
        payload = response.json()
        failed = payload.get("failed", {})
        if failed:
            raise ZoteroLocalError("Zotero rejected the new item")
        key = payload.get("success", {}).get("0")
        if not isinstance(key, str) or not key:
            raise ZoteroLocalError("Zotero did not return the new item key")
        try:
            return _validate_key(key)
        except ValueError as exc:
            raise ZoteroLocalError("Zotero returned an invalid new item key") from exc

    def update_item(
        self,
        item_key: str,
        changes: Mapping[str, Any],
        *,
        version: int,
    ) -> None:
        item_key = _validate_key(item_key)
        if isinstance(version, bool) or version < 0:
            raise ValueError("Zotero item version must be a non-negative integer")
        headers = self._write_headers(include_write_token=False)
        headers["If-Unmodified-Since-Version"] = str(version)
        self._request("PATCH", f"users/0/items/{item_key}", headers=headers, json=dict(changes))

    @staticmethod
    def _file_md5(path: Path) -> str:
        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as handle:
            while chunk := handle.read(UPLOAD_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _upload_body(path: Path, prefix: str, suffix: str) -> Iterator[bytes]:
        if prefix:
            yield prefix.encode()
        with path.open("rb") as handle:
            while chunk := handle.read(UPLOAD_CHUNK_BYTES):
                yield chunk
        if suffix:
            yield suffix.encode()

    def upload_file(self, attachment_key: str, path: Path) -> dict[str, Any]:
        """Upload a file into an existing stored-file attachment item."""
        attachment_key = _validate_key(attachment_key)
        if not path.is_file():
            raise ZoteroLocalError("attachment file does not exist")
        stat = path.stat()
        if stat.st_size > MAX_UPLOAD_BYTES:
            raise ZoteroLocalError("attachment exceeds the Local API limit (must be under 4 GiB)")
        self.ensure_write_authorization(require_remembered=True)
        digest = self._file_md5(path)
        upload_response = self._request(
            "POST",
            f"users/0/items/{attachment_key}/file",
            headers={
                **self._write_headers(
                    require_remembered=True,
                    include_write_token=False,
                ),
                "If-None-Match": "*",
            },
            data={
                "md5": digest,
                "filename": path.name,
                "filesize": str(stat.st_size),
                "mtime": str(int(stat.st_mtime * 1000)),
            },
        )
        upload = upload_response.json()
        if upload.get("exists") in (1, True):
            return {"attachment_key": attachment_key, "uploaded": False}
        upload_url = upload.get("url")
        upload_key = upload.get("uploadKey")
        parsed_upload = urlparse(upload_url) if isinstance(upload_url, str) else None
        safe_upload = (
            isinstance(upload_url, str)
            and _is_loopback_url(upload_url)
            and parsed_upload is not None
            and (parsed_upload.port or 80) == self._base_port
            and parsed_upload.path.startswith("/api/local/uploads/")
        )
        if not safe_upload:
            raise ZoteroLocalError("Zotero returned an unsafe upload URL")
        if not isinstance(upload_key, str) or not upload_key:
            raise ZoteroLocalError("Zotero did not return an upload key")
        prefix = str(upload.get("prefix", ""))
        suffix = str(upload.get("suffix", ""))
        self._request(
            "POST",
            upload_url,
            headers={
                "Content-Type": str(upload.get("contentType", "application/octet-stream")),
                "Content-Length": str(len(prefix.encode()) + stat.st_size + len(suffix.encode())),
            },
            content=self._upload_body(path, prefix, suffix),
        )
        self._request(
            "POST",
            f"users/0/items/{attachment_key}/file",
            headers={
                **self._write_headers(
                    require_remembered=True,
                    include_write_token=False,
                ),
                "If-None-Match": "*",
            },
            data={"upload": upload_key},
        )
        return {"attachment_key": attachment_key, "uploaded": True}

    def import_file(self, parent_key: str, path: Path) -> dict[str, Any]:
        parent_key = _validate_key(parent_key)
        if not path.is_file():
            raise ZoteroLocalError("attachment file does not exist")
        stat = path.stat()
        if stat.st_size > MAX_UPLOAD_BYTES:
            raise ZoteroLocalError("attachment exceeds the Local API limit (must be under 4 GiB)")
        self.ensure_write_authorization(require_remembered=True)
        attachment = {
            "itemType": "attachment",
            "linkMode": "imported_file",
            "title": path.name,
            "filename": path.name,
            "contentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "parentItem": parent_key,
            "tags": [],
            "relations": {},
        }
        attachment_key = self.create_item(attachment)
        try:
            return self.upload_file(attachment_key, path)
        except Exception as exc:
            raise ZoteroFileUploadError(attachment_key, str(exc)) from exc
