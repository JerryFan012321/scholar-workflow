"""Derive paper links and optionally enrich known identities through the Local API."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections import Counter
from copy import deepcopy
from urllib.parse import quote, unquote, urlsplit

from scholar_workflow.knowledge.exploration import ExplorationError

_KEY = re.compile(r"[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}\Z")
_RESOURCE = re.compile(
    r"(?:paper|document):zotero:([1-9][0-9]*):([23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})\Z"
)
_DOI = re.compile(r"10\.[0-9]{4,9}/[^\s]+\Z")
_ARXIV = re.compile(r"(?:[0-9]{4}\.[0-9]{4,5}|[a-zA-Z][a-zA-Z.\-]*/[0-9]{7})(?:v[1-9][0-9]*)?\Z")


def include_resource_links(payload):
    """Read only selected known parents/children, preserving offline diagnostics."""
    from scholar_workflow.adapters.zotero_local import (
        ZoteroLocalAdapter,
        ZoteroLocalError,
        ZoteroLocalUnavailable,
    )

    enriched = deepcopy(payload)
    offline = False
    with ZoteroLocalAdapter() as local:
        for unit in enriched.get("paper_units", []):
            resource = unit.get("catalog_resource")
            if not isinstance(resource, dict):
                unit["resource_notes"] = ["资源来源记录缺失；原文和 Zotero 入口未核实。"]
                continue
            if resource.get("resource_id") != unit.get("resource_id"):
                raise ExplorationError("Provider resource identity changed; reload.", 5)
            parent = children = None
            failure = None
            zotero = resource.get("zotero") or {}
            key = zotero.get("item_key") if isinstance(zotero, dict) else None
            if key and not offline:
                try:
                    parent = local.get_item(key)
                    children = local.get_children_all(key)
                except ZoteroLocalUnavailable:
                    offline = True
                    failure = "Zotero Local API 不可用；保留已登记文件和网页，未确认的附件不推测。"
                except (ZoteroLocalError, ValueError):
                    failure = "对应 Zotero 条目或子条目未能完整读取；附件清单尚未核实。"
            resolved = resource_links(resource, parent, children)
            unit["resource_links"] = resolved["links"]
            unit["resource_notes"] = resolved["notes"] + ([failure] if failure else [])
    return enriched


def _key(value) -> bool:
    return isinstance(value, str) and bool(_KEY.fullmatch(value))


def _loopback(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Browsers can also interpret legacy numeric IPv4 forms locally.
        components = host.split(".")
        if not 1 <= len(components) <= 4:
            return False
        try:
            numbers = [int(part, 16) if part.startswith("0x") else
                       int(part, 8) if len(part) > 1 and part.startswith("0") else int(part, 10)
                       for part in components]
        except ValueError:
            return False
        if any(number < 0 for number in numbers):
            return False
        if len(numbers) == 1:
            return 0 <= numbers[0] < 2**32 and numbers[0] >> 24 == 127
        return numbers[0] == 127
    return address.is_loopback or bool(getattr(address, "ipv4_mapped", None) and
                                       address.ipv4_mapped.is_loopback)


def _web_url(value) -> str | None:
    if (not isinstance(value, str) or not value or "\\" in value
            or any(ord(char) <= 32 or ord(char) == 127 for char in value)):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
        if host:
            host = host.encode("idna").decode("ascii")
        if (parts.scheme != "https" or not host or parts.username is not None
                or parts.password is not None or "%" in host or _loopback(host)
                or port is not None and not 1 <= port <= 65535):
            return None
    except (ValueError, UnicodeError):
        return None
    return value


def _library(payload) -> tuple[str, int] | None:
    if not isinstance(payload, dict):
        return None
    library = payload.get("library")
    if not isinstance(library, dict):
        return None
    kind, identity = library.get("type"), library.get("id")
    if (not isinstance(kind, str) or kind not in {"user", "group"}
            or type(identity) is not int or identity <= 0):
        return None
    return kind, identity


def _active_data(payload, key: str, kinds: set[str] | None = None) -> dict | None:
    if not isinstance(payload, dict) or payload.get("key") != key or payload.get("deleted"):
        return None
    data = payload.get("data")
    if (not isinstance(data, dict) or data.get("deleted")
            or "key" in data and data["key"] != key):
        return None
    item_type = data.get("itemType")
    if not isinstance(item_type, str) or not item_type:
        return None
    if kinds is not None and item_type not in kinds:
        return None
    return data


def resource_links(resource: dict, parent: dict | None = None,
                   children: list | None = None) -> dict:
    """Return stable explicit links and readable omissions from supplied snapshots.

    Source URLs require HTTPS. Zotero links require the observed parent library;
    an attachment key alone cannot establish that library or its parent. Native
    PDF links establish identity only, not local availability or reader success.
    Caller dictionaries are never changed and no external access is performed.
    """
    links: list[dict[str, str]] = []
    notes: list[str] = []
    seen_uris: set[str] = set()

    def add(title: str, kind: str, uri: str) -> None:
        if uri in seen_uris:
            return
        seen_uris.add(uri)
        identity = hashlib.sha256(uri.encode("utf-8")).hexdigest()
        links.append({"object_id": f"resource-link:{identity}", "title": title,
                      "kind": kind, "uri": uri})

    if not isinstance(resource, dict):
        return {"links": [], "notes": ["资源记录无效；Zotero 未读取。"]}
    identifiers = resource.get("identifiers", {})
    if not isinstance(identifiers, dict):
        notes.append("资源标识格式无效，未生成原文网页入口。")
        identifiers = {}
    source_url = identifiers.get("url")
    if source_url is not None:
        uri = _web_url(source_url)
        if uri is None:
            notes.append("原文网页地址无效：需要无凭据、非本机回环的 HTTPS 地址。")
        else:
            add("原文网页", "original-page", uri)
    doi = identifiers.get("doi")
    if doi is not None:
        normalized = doi if isinstance(doi, str) else ""
        if normalized.lower().startswith("doi:"):
            normalized = normalized[4:]
        elif normalized.startswith("https://doi.org/") and _web_url(normalized):
            normalized = unquote(normalized[len("https://doi.org/"):])
        if (not _DOI.fullmatch(normalized)
                or any(ord(char) <= 32 or ord(char) == 127 for char in normalized)):
            notes.append("DOI 标识无效，未生成 DOI 原文入口。")
        else:
            add("DOI 原文入口", "doi", "https://doi.org/" + quote(normalized, safe="/"))
    arxiv = identifiers.get("arxiv")
    if arxiv is not None:
        normalized = arxiv if isinstance(arxiv, str) else ""
        if normalized.lower().startswith("arxiv:"):
            normalized = normalized[6:]
        if not _ARXIV.fullmatch(normalized):
            notes.append("arXiv 标识无效，未生成 arXiv 原文入口。")
        else:
            add("arXiv 原文入口", "arxiv", "https://arxiv.org/abs/" + normalized)

    zotero = resource.get("zotero", {})
    if not isinstance(zotero, dict):
        notes.append("Zotero 关联格式无效，未读取对应条目。")
        return {"links": links, "notes": notes}
    item_key = zotero.get("item_key")
    if not _key(item_key):
        notes.append("没有有效的 Zotero 条目登记，Zotero 未读取。")
        return {"links": links, "notes": notes}
    if parent is None:
        notes.append("Zotero 未读取；条目和附件入口尚未核实。")
        return {"links": links, "notes": notes}
    data, library = _active_data(parent, item_key), _library(parent)
    if (data is None or data["itemType"] in {"attachment", "note", "annotation"}
            or library is None):
        notes.append("Zotero 原条目身份、状态或文库信息不符，未生成对应入口。")
        return {"links": links, "notes": notes}
    resource_id = resource.get("resource_id")
    formal = _RESOURCE.fullmatch(resource_id) if isinstance(resource_id, str) else None
    if formal is not None and (formal[1] != str(library[1]) or formal[2] != item_key):
        notes.append("已登记资源身份与 Zotero 条目或文库不符，未生成对应入口。")
        return {"links": links, "notes": notes}
    # Current bibliographic fields are authoritative only after parent and
    # library identity checks. Older provider snapshots may not carry them.
    if data.get("url"):
        current_url = _web_url(data["url"])
        if current_url is not None:
            add("Zotero 登记的原文网页", "original-page", current_url)
        else:
            notes.append("Zotero 原文网页地址未通过公共 HTTPS 地址检查。")
    if data.get("DOI"):
        current_doi = data["DOI"] if isinstance(data["DOI"], str) else ""
        if current_doi.lower().startswith("doi:"):
            current_doi = current_doi[4:]
        elif current_doi.startswith("https://doi.org/") and _web_url(current_doi):
            current_doi = unquote(current_doi[len("https://doi.org/"):])
        if (_DOI.fullmatch(current_doi)
                and not any(ord(char) <= 32 or ord(char) == 127 for char in current_doi)):
            add("Zotero 登记的 DOI 原文入口", "doi", "https://doi.org/" + quote(current_doi, safe="/"))
        else:
            notes.append("Zotero DOI 标识无效，未生成对应入口。")
    library_path = "library" if library[0] == "user" else f"groups/{library[1]}"
    add("在 Zotero 打开条目", "zotero-item", f"zotero://select/{library_path}/items/{item_key}")
    if children is None:
        notes.append("Zotero 子条目未读取，附件与笔记清单尚未核实。")
        return {"links": links, "notes": notes}
    if not isinstance(children, list):
        notes.append("Zotero 子条目列表格式无效，附件与笔记未加入。")
        return {"links": links, "notes": notes}
    counts = Counter(row.get("key") for row in children
                     if isinstance(row, dict) and _key(row.get("key")))
    for key, count in counts.items():
        if count > 1:
            notes.append(f"Zotero 子条目 {key} 重复，未采用重复身份。")
    accepted: set[str] = set()
    for index, row in enumerate(children, start=1):
        key = row.get("key") if isinstance(row, dict) else None
        if not _key(key):
            notes.append(f"Zotero 第 {index} 个子条目格式或标识无效，未采用。")
            continue
        if counts[key] > 1:
            continue
        child_data = _active_data(row, key, {"attachment", "note"})
        if (key == item_key or child_data is None or child_data.get("parentItem") != item_key
                or _library(row) != library):
            notes.append(f"Zotero 子条目 {key} 的归属、文库、类型或状态不符，未采用。")
            continue
        accepted.add(key)
        kind = child_data["itemType"]
        if kind == "attachment" and child_data.get("contentType") == "application/pdf":
            add("在 Zotero 打开原 PDF", "zotero-pdf",
                f"zotero://open-pdf/{library_path}/items/{key}")
        else:
            add("在 Zotero 打开笔记" if kind == "note" else "在 Zotero 打开附件",
                "zotero-note" if kind == "note" else "zotero-attachment",
                f"zotero://select/{library_path}/items/{key}")
        if kind == "attachment" and child_data.get("linkMode") == "linked_url":
            uri = _web_url(child_data.get("url"))
            if uri is None:
                notes.append(f"Zotero 子附件 {key} 的关联网页地址无效，未生成网页入口。")
            else:
                add("子附件关联网页", "linked-page", uri)
    attachment_key = zotero.get("attachment_key")
    if attachment_key is not None and (not _key(attachment_key) or attachment_key not in accepted):
        notes.append("已登记的 Zotero 附件未在当前有效子条目中确认；未推测 PDF 入口。")
    return {"links": links, "notes": notes}
