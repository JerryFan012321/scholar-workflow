"""Read declared Markdown and bind its original links to session-only actions."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import secrets
import stat
import struct
import threading
from copy import deepcopy
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from scholar_workflow.adapters.exploration_readers import ReaderUnavailable, parse_reading_uri
from scholar_workflow.knowledge.exploration import _open_relative, _uri_parts
from scholar_workflow.knowledge.exploration_import import _identity
from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

_LIMIT = 2 * 1024 * 1024
_IMAGE_LIMIT = 16 * 1024 * 1024
_IMAGE_PIXELS = 32 * 1024 * 1024
_LINK = re.compile(r"\[\[([^\]\n]+)\]\]|\[([^\]\n]+)\]\((?:<([^>\n]+)>|([^\s)\n]+))\)")
_IMAGE = re.compile(r"!\[\[([^\]\n]+)\]\]|!\[([^\]\n]*)\]\((?:<([^>\n]+)>|([^\s)\n]+))\)")


class PreviewUnavailable(RuntimeError):
    def __init__(self, message: str, code: str = "preview_changed") -> None:
        super().__init__(message)
        self.code = code


def _fail(message="The document or link changed; refresh the preview.", code="preview_changed"):
    raise PreviewUnavailable(message, code)


def _clean(value):
    return isinstance(value, str) and bool(value) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _signature(work, asset):
    return (work["id"], asset["id"], asset["uri"],
            json.dumps(work.get("entity_ref"), sort_keys=True, ensure_ascii=False))


def _read(root: Path, relative: str, *, text=False):
    try:
        parts, path = _uri_parts(relative)
        if path is None or parts.fragment or (text and Path(path).suffix.lower() != ".md"):
            _fail("Preview requires a declared local Markdown file.", "preview_unavailable")
        with _open_relative(root, path) as fd:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or text and before.st_size > _LIMIT:
                _fail("The declared file cannot be previewed safely.", "preview_unavailable")
            if not text:
                return None
            chunks, count = [], 0
            while True:
                chunk = os.read(fd, min(65536, _LIMIT + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > _LIMIT:
                    _fail("The document exceeds the preview size limit.", "preview_unavailable")
            after = os.fstat(fd)
            raw = b"".join(chunks)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if len(raw) != before.st_size or any(getattr(before, f) != getattr(after, f) for f in fields):
                _fail()
            return raw.decode("utf-8"), "sha256:" + hashlib.sha256(raw).hexdigest()
    except PreviewUnavailable:
        raise
    except (OSError, ValueError, UnicodeError, TypeError):
        _fail("The declared document could not be read safely.", "preview_unavailable")


def _inline_matches(text, pattern):
    excluded, fence, fence_start, offset = [], None, 0, 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and marker:
            fence, fence_start = marker[1], offset
        elif fence is not None:
            if (marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence)
                    and not line[marker.end():].strip()):
                excluded.append((fence_start, offset + len(line)))
                fence = None
        else:
            excluded.extend((offset + m.start(), offset + m.end())
                            for m in re.finditer(r"(`+).*?\1", line))
        offset += len(line)
    if fence is not None:
        excluded.append((fence_start, len(text)))
    excluded.sort()
    blocked, previous, units = 0, 0, 0
    for match in pattern.finditer(text):
        while blocked < len(excluded) and excluded[blocked][1] <= match.start():
            blocked += 1
        if (blocked < len(excluded) and excluded[blocked][0] <= match.start()
                or match.start() > 0 and text[match.start() - 1] in {"!", "\\"}):
            continue
        start = units + len(text[previous:match.start()].encode("utf-16-le")) // 2
        end = start + len(match[0].encode("utf-16-le")) // 2
        previous, units = match.end(), end
        yield match, start, end


def _occurrences(text):
    for match, start, end in _inline_matches(text, _LINK):
        if match[1] is not None:
            target, separator, label = match[1].partition("|")
            label = label if separator else target
            wiki = True
        else:
            label, target, wiki = match[2], match[3] or match[4], False
        yield {"start": start, "end": end, "label": label}, target, wiki, match[0]


def _image_occurrences(text):
    for match, start, end in _inline_matches(text, _IMAGE):
        if match[1] is not None:
            target, _separator, _width = match[1].partition("|")
            label, wiki = target, True
        else:
            label, target, wiki = match[2], match[3] or match[4], False
        yield {"start": start, "end": end, "label": label}, target, wiki, match[0]


def _image_content_type(raw, suffix):
    formats = {
        ".png": ("png", "image/png", raw.startswith(b"\x89PNG\r\n\x1a\n")),
        ".jpg": ("jpeg", "image/jpeg", raw.startswith(b"\xff\xd8\xff")),
        ".jpeg": ("jpeg", "image/jpeg", raw.startswith(b"\xff\xd8\xff")),
        ".gif": ("gif", "image/gif", raw[:6] in {b"GIF87a", b"GIF89a"}),
        ".webp": ("webp", "image/webp", raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"),
        ".avif": ("avif", "image/avif", raw[4:8] == b"ftyp" and raw[8:12] in {b"avif", b"avis"}),
    }
    candidate = formats.get(suffix.lower())
    if candidate is None or not candidate[2]:
        _fail("Only verified local raster images can be displayed.", "unsupported_image")
    try:
        import fitz
    except ImportError:
        _fail("The raster decoder is unavailable.", "unsupported_image")
    try:
        width, height = _image_dimensions(raw, candidate[0])
        if not (0 < width <= 32768 and 0 < height <= 32768
                and width * height <= _IMAGE_PIXELS):
            _fail("The raster exceeds the safe decoding size.", "image_too_large")
        with fitz.open(stream=raw, filetype=candidate[0]) as document:
            rect = document[0].rect
            if not (0 < rect.width <= 32768 and 0 < rect.height <= 32768
                    and rect.width * rect.height <= _IMAGE_PIXELS):
                _fail("The raster exceeds the safe decoding size.", "image_too_large")
        image = fitz.Pixmap(raw)
        if not (0 < image.width <= 32768 and 0 < image.height <= 32768
                and image.width * image.height <= _IMAGE_PIXELS):
            _fail("The raster exceeds the safe decoding size.", "image_too_large")
    except PreviewUnavailable:
        raise
    except (RuntimeError, ValueError, TypeError, IndexError, struct.error, fitz.mupdf.FzErrorBase):
        _fail("This raster could not be decoded safely.", "unsupported_image")
    return candidate[1]


def _image_dimensions(raw, kind):
    """Check encoded pixel dimensions before asking the decoder to allocate."""
    if kind == "png" and raw[12:16] == b"IHDR":
        return struct.unpack(">II", raw[16:24])
    if kind == "gif":
        return struct.unpack("<HH", raw[6:10])
    if kind == "jpeg":
        offset = 2
        while offset < len(raw):
            if raw[offset] != 255:
                break
            while offset < len(raw) and raw[offset] == 255:
                offset += 1
            marker = raw[offset]
            offset += 1
            if marker in {0x01, *range(0xD0, 0xDA)}:
                continue
            length = int.from_bytes(raw[offset:offset + 2], "big")
            if length < 2 or offset + length > len(raw) or marker == 0xDA:
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and length >= 8:
                height, width = struct.unpack(">HH", raw[offset + 3:offset + 7])
                return width, height
            offset += length
    if kind == "webp":
        if raw[12:16] == b"VP8X" and len(raw) >= 30:
            return 1 + int.from_bytes(raw[24:27], "little"), 1 + int.from_bytes(raw[27:30], "little")
        if raw[12:16] == b"VP8L" and len(raw) >= 25 and raw[20] == 0x2F:
            bits = int.from_bytes(raw[21:25], "little")
            return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
        if raw[12:16] == b"VP8 " and len(raw) >= 30 and raw[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", raw[26:30])
            return width & 0x3FFF, height & 0x3FFF
    _fail("The raster format cannot be bounded before decoding.", "unsupported_image")


def _read_image(root, uri):
    try:
        parsed, path = _uri_parts(uri)
        if path is None or parsed.fragment:
            _fail("Only declared local raster files can be displayed.", "unsupported_image")
        with _open_relative(root, path) as fd:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _IMAGE_LIMIT:
                _fail("The image exceeds the safe preview size.", "image_too_large")
            chunks, count = [], 0
            while True:
                chunk = os.read(fd, min(65536, _IMAGE_LIMIT + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > _IMAGE_LIMIT:
                    _fail("The image exceeds the safe preview size.", "image_too_large")
            raw, after = b"".join(chunks), os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if len(raw) != before.st_size or any(getattr(before, f) != getattr(after, f) for f in fields):
                _fail()
        content_type = _image_content_type(raw, PurePosixPath(path).suffix)
        return raw, content_type, "sha256:" + hashlib.sha256(raw).hexdigest()
    except PreviewUnavailable:
        raise
    except (OSError, ValueError, TypeError):
        _fail("The declared image could not be read safely.", "image_unavailable")


def _native_identity(uri, work):
    try:
        action = parse_reading_uri(uri)
    except ReaderUnavailable:
        return None
    formal = re.fullmatch(r"(?:paper|document):zotero:([1-9][0-9]*):[^:]+",
                          (work.get("entity_ref") or {}).get("object_id", ""))
    library = action.get("library") or action.get("group") or (formal[1] if formal else None)
    annotation_target = action["kind"] == "zotflow" and bool(action.get("annotation"))
    return action["key"], annotation_target, str(library) if library else None, (
        "group" if action.get("group") else "user" if action["kind"] == "zotero" else None)


class ExplorationPreviewService:
    def __init__(self, root, store, reader_gate, root_validator=None):
        self.root, self.store, self.reader_gate = Path(root), store, reader_gate
        self.root_validator = root_validator
        self._links = {}
        self._media = {}
        self._lock = threading.RLock()

    def _document(self, work_id, asset_id):
        try:
            data = self.store.load()["data"]
            work = next(row for row in data["works"] if row["id"] == work_id)
            asset = next(row for row in work["assets"] if row["id"] == asset_id)
            text, revision = _read(self.root, asset["uri"], text=True)
            return data, work, asset, text, revision
        except PreviewUnavailable:
            raise
        except (RuntimeError, OSError, ValueError, KeyError, StopIteration, TypeError):
            _fail()

    def _provider_file(self, work, asset):
        ref = work.get("entity_ref")
        references = getattr(self.reader_gate, "references", None)
        if not isinstance(ref, dict) or references is None:
            return None
        try:
            unit = references.current_unit(ref)
            for row in unit["files"]:
                identity = _identity(ref["source_id"], ref["object_id"], row["object_id"], prefix="paper-asset-")
                if identity == asset["id"]:
                    return row
        except (RuntimeError, OSError, ValueError, KeyError, TypeError):
            return None
        return None

    def _aliases(self, work, asset, cache, providers=False):
        key = work["id"], asset["id"], providers
        if key not in cache:
            aliases = set()
            try:
                parsed, relative = _uri_parts(asset["uri"])
                if relative is not None:
                    aliases.add(relative)
                elif parsed.scheme == "obsidian" and parsed.netloc == "open":
                    values = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
                    params = dict(values)
                    if len(params) == len(values):
                        location = params.get("path") or params.get("file")
                        if location:
                            aliases.add(location.split("#", 1)[0])
                            if not params.get("path") and params.get("vault"):
                                aliases.add("obsidian-vault:" + params["vault"] + ":" + location.split("#", 1)[0])
            except (ValueError, TypeError):
                pass
            row = self._provider_file(work, asset) if providers else None
            if row and isinstance(row.get("relative_path"), str):
                aliases.add(row["relative_path"])
                if isinstance(row.get("uri"), str):
                    try:
                        params = dict(parse_qsl(urlsplit(row["uri"]).query, strict_parsing=True))
                        if params.get("vault") and params.get("file"):
                            aliases.add("obsidian-vault:" + params["vault"] + ":" + params["file"])
                    except ValueError:
                        pass
            cache[key] = aliases
        return cache[key]

    def _local_path(self, work, asset):
        _parts, relative = _uri_parts(asset["uri"])
        if relative is not None:
            _read(self.root, asset["uri"])
            return self.root.absolute() / relative
        row = self._provider_file(work, asset)
        registry_path = getattr(self.reader_gate, "registry_path", None)
        if row is None or registry_path is None:
            _fail("The local target has no current registered file location.", "unregistered_target")
        ref = work["entity_ref"]
        try:
            registry = KnowledgeSourceRegistry(registry_path)
            before = registry.revision()
            source = registry.resolve(ref["source_id"], capability="read")
            if self.root_validator is not None:
                self.root_validator(source)
            _read(source, row["relative_path"])
            if registry.revision() != before:
                _fail()
            return source / row["relative_path"]
        except PreviewUnavailable:
            raise
        except (RuntimeError, OSError, ValueError, KeyError, TypeError):
            _fail("The registered local document is currently unavailable.", "unregistered_target")

    def _local_target(self, data, source_asset, target, wiki, cache):
        parsed = urlsplit(target)
        vault = None
        if parsed.scheme:
            if parsed.scheme != "obsidian" or parsed.netloc != "open" or parsed.path not in {"", "/"} or parsed.fragment:
                _fail("This native document action is not permitted.", "unsupported_link")
            values = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
            params = dict(values)
            if len(params) != len(values) or set(params) - {"path", "vault", "file"}:
                _fail("The native document parameters are invalid.", "unsupported_link")
            location = params.get("path") or params.get("file")
            if not _clean(location):
                _fail("The native document location is invalid.", "unsupported_link")
            path, _, anchor = location.partition("#")
            vault = params.get("vault") if not params.get("path") else None
        else:
            if parsed.netloc or parsed.query:
                _fail("The document link is not a local registered reference.", "unregistered_target")
            path, anchor = unquote(parsed.path), unquote(parsed.fragment)
            if not wiki:
                source_path = unquote(urlsplit(source_asset["uri"]).path)
                path = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), path))
        if (not _clean(path) or "\\" in path or path.startswith("~")
                or any(part == ".." for part in PurePosixPath(path).parts)
                or anchor and (not _clean(anchor) or "#" in anchor)):
            _fail("The document link escapes its registered scope.", "unregistered_target")
        if not PurePosixPath(path).suffix:
            path += ".md"
        wanted = "obsidian-vault:" + vault + ":" + path if vault else path
        candidates = []
        for providers in (False, True):
            for work in data["works"]:
                for asset in work.get("assets", []):
                    aliases = self._aliases(work, asset, cache, providers)
                    local_uri = urlsplit(asset["uri"])
                    if not local_uri.scheme:
                        aliases = aliases | {str(self.root.absolute() / unquote(local_uri.path))}
                    if wanted in aliases:
                        candidates.append((work, asset))
            if candidates:
                break
        if len(candidates) != 1:
            _fail("The document target is not uniquely registered.", "ambiguous_target" if candidates else "unregistered_target")
        work, asset = candidates[0]
        file_path = self._local_path(work, asset)
        uri = "obsidian://open?" + urlencode({"path": str(file_path) + ("#" + anchor if anchor else "")}, quote_via=quote)
        return work, {"id": asset["id"], "uri": uri, "kind": "registered-document"}

    def _resolve(self, data, work, source_asset, target, wiki, cache):
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https"}:
            _uri_parts(target)
            return {"kind": "web", "uri": target}, None
        if parsed.scheme in {"zotero", "obsidian"} and parsed.netloc != "open":
            action = parse_reading_uri(target)
            wanted = _native_identity(target, work)
            matches = {}
            for candidate in data["works"]:
                for asset in candidate.get("assets", []):
                    identity = _native_identity(asset["uri"], candidate)
                    if (identity and wanted and identity[:2] == wanted[:2]
                            and (identity[2] is None or wanted[2] is None or identity[2] == wanted[2])
                            and (identity[3] is None or wanted[3] is None or identity[3] == wanted[3])):
                        matches[candidate["id"]] = candidate
            if len(matches) > 1:
                _fail("The reader target belongs to multiple declared units.", "ambiguous_target")
            target_work = next(iter(matches.values())) if matches else work
            virtual_id = "source-link-" + hashlib.sha256(target.encode()).hexdigest()
            return {"kind": "native"}, (target_work, {"id": virtual_id, "uri": action["uri"], "kind": "source-link"})
        target_work, asset = self._local_target(data, source_asset, target, wiki, cache)
        return {"kind": "native"}, (target_work, asset)

    def _image_target(self, data, work, source_asset, target, wiki, cache):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            _fail("Remote and native image requests are not permitted.", "unsupported_image")
        path = unquote(parsed.path)
        if not _clean(path) or path.startswith(("/", "~")) or "\\" in path:
            _fail("The image target escapes its registered scope.", "unregistered_image")
        if not wiki:
            _parts, source_path = _uri_parts(source_asset["uri"])
            path = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), path))
        if any(part in {"", ".", ".."} for part in path.split("/")):
            _fail("The image target escapes its registered scope.", "unregistered_image")

        def matches(candidate):
            return [asset for asset in candidate.get("assets", []) if any(
                path in self._aliases(candidate, asset, cache, providers)
                for providers in (False, True))]

        own = matches(work)
        if len(own) != 1:
            code = "ambiguous_image" if own else "cross_paper_image" if any(
                matches(other) for other in data["works"] if other["id"] != work["id"]
            ) else "unregistered_image"
            _fail("The image is not uniquely declared by this unit.", code)
        asset = own[0]
        _parsed, relative = _uri_parts(asset["uri"])
        if relative is None:
            _fail("The declared image is not available inside this preview root.", "image_unavailable")
        return asset

    def preview(self, work_id, asset_id):
        data, work, asset, text, revision = self._document(work_id, asset_id)
        links, entries, images, media_entries, cache = [], {}, [], {}, {}
        for display, target, wiki, literal in _occurrences(text):
            try:
                result, native = self._resolve(data, work, asset, target, wiki, cache)
                display.update(result)
                if native is not None:
                    token = "link_" + secrets.token_urlsafe(24)
                    display["link_id"] = token
                    entries[token] = {"document": _signature(work, asset), "revision": revision,
                                      "target": target, "wiki": wiki, "literal": literal,
                                      "start": display["start"], "end": display["end"],
                                      "native": _signature(*native), "prepared": False}
            except (PreviewUnavailable, ReaderUnavailable, ValueError, TypeError) as error:
                display.update(kind="unavailable", reason_code=getattr(error, "code", "unsupported_link"))
            links.append(display)
        for display, target, wiki, literal in _image_occurrences(text):
            try:
                image = self._image_target(data, work, asset, target, wiki, cache)
                _raw, content_type, digest = _read_image(self.root, image["uri"])
                token = "media_" + secrets.token_urlsafe(24)
                display["media_id"] = token
                media_entries[token] = {"document": _signature(work, asset), "revision": revision,
                    "target": target, "wiki": wiki, "literal": literal,
                    "start": display["start"], "end": display["end"],
                    "image": _signature(work, image), "digest": digest, "content_type": content_type}
            except (PreviewUnavailable, ValueError, TypeError) as error:
                display["reason_code"] = getattr(error, "code", "unsupported_image")
            images.append(display)
        with self._lock:
            for token in [key for key, value in self._links.items() if value["document"][:2] == (work_id, asset_id)]:
                self._links.pop(token)
            self._links.update(entries)
            for token in [key for key, value in self._media.items() if value["document"][:2] == (work_id, asset_id)]:
                self._media.pop(token)
            self._media.update(media_entries)
        return {"text": text, "document_revision": revision, "links": links, "images": images}

    def media(self, media_id):
        with self._lock:
            entry = deepcopy(self._media.get(media_id)) if isinstance(media_id, str) else None
        if entry is None:
            _fail("The preview image is unknown or expired.", "media_expired")
        data, work, asset, text, revision = self._document(*entry["document"][:2])
        if _signature(work, asset) != entry["document"] or revision != entry["revision"]:
            _fail()
        literal = text.encode("utf-16-le")[entry["start"] * 2:entry["end"] * 2].decode("utf-16-le")
        if literal != entry["literal"]:
            _fail()
        image = self._image_target(data, work, asset, entry["target"], entry["wiki"], {})
        if _signature(work, image) != entry["image"]:
            _fail()
        raw, content_type, digest = _read_image(self.root, image["uri"])
        if digest != entry["digest"] or content_type != entry["content_type"]:
            _fail()
        _data, current_work, current_asset, _text, current_revision = self._document(*entry["document"][:2])
        if _signature(current_work, current_asset) != entry["document"] or current_revision != revision:
            _fail()
        current_image = self._image_target(_data, current_work, current_asset,
                                          entry["target"], entry["wiki"], {})
        if _signature(current_work, current_image) != entry["image"]:
            _fail()
        with self._lock:
            if self._media.get(media_id) != entry:
                _fail("The preview image is unknown or expired.", "media_expired")
        return raw, content_type

    def _current(self, link_id):
        with self._lock:
            entry = deepcopy(self._links.get(link_id)) if isinstance(link_id, str) else None
        if entry is None:
            _fail("The preview link is unknown or expired.", "link_expired")
        try:
            data, work, asset, text, revision = self._document(*entry["document"][:2])
        except PreviewUnavailable:
            _fail()
        if _signature(work, asset) != entry["document"] or revision != entry["revision"]:
            _fail()
        literal = text.encode("utf-16-le")[entry["start"] * 2:entry["end"] * 2].decode("utf-16-le")
        if literal != entry["literal"]:
            _fail()
        _display, native = self._resolve(data, work, asset, entry["target"], entry["wiki"], {})
        if native is None or _signature(*native) != entry["native"]:
            _fail()
        return entry, native

    def prepare(self, link_id):
        entry, (work, asset) = self._current(link_id)
        result = self.reader_gate.availability(work, asset)
        self._current(link_id)
        with self._lock:
            current = self._links.get(link_id)
            if current is None or current["document"] != entry["document"]:
                _fail()
            current["prepared"] = result.get("native_available") is True
        return result

    def require_current(self, link_id):
        entry, (work, asset) = self._current(link_id)
        if not entry["prepared"]:
            _fail("Prepare the original link again before opening it.", "refresh_required")
        try:
            self.reader_gate.require_current(work, asset)
        except ReaderUnavailable as error:
            raise PreviewUnavailable(str(error), code=error.code) from None
        self._current(link_id)
        return asset["uri"]
