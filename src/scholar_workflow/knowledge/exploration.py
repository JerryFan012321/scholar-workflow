"""File-backed research relationships and queries, independent of paper-unit writers."""

from __future__ import annotations

import fcntl
import hashlib
import html
import math
import os
import re
import secrets
import stat
from contextlib import contextmanager
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_MAX_STATE_BYTES = 2 * 1024 * 1024


class ExplorationError(ValueError):
    """An invalid declaration (2) or a concurrent revision conflict (5)."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.message = message
        self.code = code


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def _readable(cls, value):
        if isinstance(value, str) and (not value.strip() or any(
            ord(c) < 32 and c not in "\n\t" or ord(c) == 127 for c in value
        )):
            raise ValueError("text must be nonblank and contain no control characters")
        return value


_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class _Value(_Model):
    id: str = Field(pattern=_ID)
    label: str
    parent_id: str | None = Field(default=None, pattern=_ID)


class _Dimension(_Model):
    id: str = Field(pattern=_ID)
    label: str
    kind: Literal["enum", "reference", "text", "number", "date"]
    multiple: bool
    scope: Literal["work", "record"]
    values: list[_Value]
    sortable: bool
    unit: str | None = None
    description: str | None = None


class _Asset(_Model):
    id: str = Field(pattern=_ID)
    label: str
    kind: str
    uri: str

    @field_validator("uri")
    @classmethod
    def _uri(cls, value):
        _uri_parts(value)
        return value


class _EntityRef(_Model):
    source_id: str = Field(min_length=1, pattern=r"^[^\s]+$")
    object_id: str = Field(min_length=1, pattern=r"^[^\s]+$")


class _Work(_Model):
    id: str = Field(pattern=_ID)
    title: str
    kind: Literal["paper", "webpage", "report", "book", "other"]
    year: int | None = None
    summary: str | None = None
    entity_ref: _EntityRef | None = None
    attributes: dict[str, Any]
    assets: list[_Asset]
    asset_diagnostics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _paper_unit_reference(self):
        if self.kind == "paper" and self.entity_ref is None:
            raise ValueError("paper entries require a qualified paper-unit entity_ref")
        return self

    @field_validator("asset_diagnostics")
    @classmethod
    def _diagnostics(cls, value):
        if any(not text.strip() or any(ord(c) < 32 or ord(c) == 127 for c in text)
               for text in value):
            raise ValueError("asset diagnostics must be nonblank readable lines")
        return value


class _Record(_Model):
    id: str = Field(pattern=_ID)
    work_id: str = Field(pattern=_ID)
    dimensions: dict[str, Any]
    conditions: dict[str, str]
    result: str
    evidence: list[str]
    assessment: str
    origin: Literal["author", "independent", "local", "analysis"]

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value):
        for key, text in value.items():
            if not key.strip() or not text.strip() or any(
                ord(c) < 32 and c not in "\n\t" or ord(c) == 127 for c in key + text
            ):
                raise ValueError("conditions require readable string keys and values")
        return value


class _Edge(_Model):
    id: str = Field(pattern=_ID)
    from_id: str = Field(pattern=_ID)
    to_id: str = Field(pattern=_ID)
    kind: Literal["extends", "borrows", "competes", "fuses", "context"]
    label: str
    evidence: list[str] = Field(min_length=1)
    explanation: str


class _Filter(_Model):
    mode: Literal["any", "all"]
    values: list[Any] = Field(min_length=1)


class _Selection(_Model):
    filters: dict[str, _Filter] = Field(default_factory=dict)
    text: str | None = None
    sort_by: str = "title"
    descending: bool = False
    include_context: bool = True


class _View(_Model):
    id: str = Field(pattern=_ID)
    title: str
    query: _Selection


class _Document(_Model):
    schema_version: Literal[1]
    dimensions: list[_Dimension]
    works: list[_Work]
    records: list[_Record]
    edges: list[_Edge]
    views: list[_View]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value


def default_data() -> dict:
    """Return editable initial definitions; reading an empty root never saves them."""
    return {
        "schema_version": 1,
        "dimensions": [{
            "id": key, "label": label, "kind": "enum", "multiple": True,
            "scope": "record", "values": [], "sortable": False,
        } for key, label in (
            ("foundation", "基座"), ("paradigm", "范式"),
            ("problem", "前沿问题"), ("task", "系统与任务"),
        )],
        "works": [], "records": [], "edges": [], "views": [],
    }


def _uri_parts(uri: str):
    if any(ord(c) < 32 or ord(c) == 127 for c in uri):
        raise ValueError("asset URI contains control characters")
    try:
        parts = urlsplit(uri)
        if parts.scheme:
            if parts.scheme not in {"https", "http", "obsidian", "zotero"}:
                raise ValueError("unsupported asset URI scheme")
            if not parts.hostname or parts.username or parts.password:
                raise ValueError("asset URI must have a host and no credentials")
            if parts.scheme in {"https", "http"}:
                _ = parts.port
            return parts, None
        path = unquote(parts.path)
        if parts.netloc or parts.query or not path or "\\" in path or path.startswith("~"):
            raise ValueError("local asset must be a root-relative file")
        segments = path.split("/")
        if path.startswith("/") or any(p in {"", ".", ".."} for p in segments):
            raise ValueError("local asset path must not escape or alias its root")
        if any(ord(c) < 32 or ord(c) == 127 for c in path):
            raise ValueError("local asset path contains control characters")
        return parts, path
    except (ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


def _unique(items, what: str):
    result = {item.id: item for item in items}
    if len(result) != len(items):
        raise ExplorationError(f"duplicate {what} identifier")
    return result


def _scalar(value: Any, dimension: _Dimension, work_ids: set[str]):
    kind = dimension.kind
    options = {v.id for v in dimension.values}
    if kind in {"enum", "reference", "text", "date"}:
        if not isinstance(value, str) or not value.strip():
            raise ExplorationError(f"{dimension.id}: value must be a nonblank string")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ExplorationError(f"{dimension.id}: value contains control characters")
    if kind == "enum" and value not in options:
        raise ExplorationError(f"{dimension.id}: unknown enumerated value {value!r}")
    if kind == "reference" and value not in options | work_ids:
        raise ExplorationError(f"{dimension.id}: unknown reference {value!r}")
    if kind == "number" and (
        type(value) not in {int, float} or not math.isfinite(value)
    ):
        raise ExplorationError(f"{dimension.id}: value must be a finite number")
    if kind == "date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("noncanonical date")
        except ValueError as exc:
            raise ExplorationError(f"{dimension.id}: date must use YYYY-MM-DD") from exc


def _assignments(values: dict, scope: str, dimensions: dict, work_ids: set[str]):
    for key, value in values.items():
        dimension = dimensions.get(key)
        if dimension is None or dimension.scope != scope:
            raise ExplorationError(f"unknown {scope} dimension {key!r}")
        if dimension.multiple:
            if not isinstance(value, list):
                raise ExplorationError(f"{key}: multiple values must be a list")
            for entry in value:
                _scalar(entry, dimension, work_ids)
            if len(set(value)) != len(value):
                raise ExplorationError(f"{key}: values must not repeat")
        else:
            _scalar(value, dimension, work_ids)


def _selection(selection: dict, dimensions: dict, work_ids: set[str]) -> _Selection:
    try:
        selected = _Selection.model_validate(selection)
    except ValidationError as exc:
        raise ExplorationError(str(exc)) from exc
    for key, spec in selected.filters.items():
        if key not in dimensions:
            raise ExplorationError(f"unknown filter dimension {key!r}")
        for value in spec.values:
            _scalar(value, dimensions[key], work_ids)
        if len(set(spec.values)) != len(spec.values):
            raise ExplorationError(f"{key}: filter values must not repeat")
    if selected.sort_by not in {"title", "year"}:
        dim = dimensions.get(selected.sort_by)
        if dim is None or not dim.sortable:
            raise ExplorationError("sort_by must name title, year or a sortable dimension")
        if dim.multiple:
            raise ExplorationError("sorting a multiple-value dimension needs an explicit comparison")
        if dim.kind in {"enum", "reference"}:
            raise ExplorationError("enum/reference values have no declared ordering")
    return selected


def _document(data: dict) -> _Document:
    try:
        document = _Document.model_validate(data)
    except (ValidationError, ValueError) as exc:
        raise ExplorationError(str(exc)) from exc
    dimensions = _unique(document.dimensions, "dimension")
    works = _unique(document.works, "work")
    identities = [(w.entity_ref.source_id, w.entity_ref.object_id) for w in document.works
                  if w.entity_ref is not None]
    if len(set(identities)) != len(identities):
        raise ExplorationError("qualified work identities must be unique")
    _unique(document.records, "record")
    _unique(document.edges, "edge")
    _unique(document.views, "view")
    asset_ids = set()
    for dim in document.dimensions:
        values = _unique(dim.values, f"{dim.id} value")
        for value in dim.values:
            seen = set()
            cursor = value
            while cursor is not None:
                if cursor.id in seen:
                    raise ExplorationError(f"{dim.id}: cyclic value hierarchy")
                seen.add(cursor.id)
                if cursor.parent_id is not None and cursor.parent_id not in values:
                    raise ExplorationError(f"{dim.id}: unknown value parent")
                cursor = values.get(cursor.parent_id)
        if dim.kind not in {"enum", "reference"} and dim.values:
            raise ExplorationError(f"{dim.id}: only enum/reference dimensions declare values")
    work_ids = set(works)
    for work in document.works:
        _assignments(work.attributes, "work", dimensions, work_ids)
        for asset in work.assets:
            if asset.id in asset_ids:
                raise ExplorationError("asset identifiers must be globally unique")
            asset_ids.add(asset.id)
    for record in document.records:
        if record.work_id not in works:
            raise ExplorationError(f"{record.id}: unknown work")
        _assignments(record.dimensions, "record", dimensions, work_ids)
        _evidence(record.evidence, asset_ids, record.id)
    for edge in document.edges:
        if edge.from_id not in works or edge.to_id not in works:
            raise ExplorationError(f"{edge.id}: unknown relationship endpoint")
        if edge.from_id == edge.to_id:
            raise ExplorationError(f"{edge.id}: relationship needs two distinct works")
        _evidence(edge.evidence, asset_ids, edge.id)
    for view in document.views:
        _selection(view.query.model_dump(exclude_none=True), dimensions, work_ids)
    return document


def _evidence(evidence: list[str], asset_ids: set[str], owner: str):
    if len(set(evidence)) != len(evidence) or any(e not in asset_ids for e in evidence):
        raise ExplorationError(f"{owner}: evidence must contain unique existing asset IDs")


def validate(data: dict) -> dict:
    """Validate shape, not current ownership, asset completeness or scientific support."""
    return _document(data).model_dump(mode="json", exclude_none=True)


def query(data: dict, selection: dict | None = None) -> dict:
    """Match one joint record before aggregating works; never join unrelated results."""
    document = _document(data)
    dims = {d.id: d for d in document.dimensions}
    works = {w.id: w for w in document.works}
    selected = _selection({} if selection is None else selection, dims, set(works))
    work_filters = {k: v for k, v in selected.filters.items() if dims[k].scope == "work"}
    record_filters = {k: v for k, v in selected.filters.items() if dims[k].scope == "record"}

    def matches(values, filters):
        for key, spec in filters.items():
            current = values.get(key)
            actual = current if isinstance(current, list) else ([] if current is None else [current])
            checks = [value in actual for value in spec.values]
            if not (any(checks) if spec.mode == "any" else all(checks)):
                return False
        return True

    eligible = {w.id for w in document.works if matches(w.attributes, work_filters)}
    if selected.text:
        text = selected.text.casefold()
        eligible &= {w.id for w in document.works if text in f"{w.title}\n{w.summary or ''}".casefold()}
    matched_records = [r for r in document.records if r.work_id in eligible and
                       matches(r.dimensions, record_filters)]
    matched_ids = {r.work_id for r in matched_records} if record_filters else eligible
    matching = [works[key] for key in matched_ids]
    sort_values = {}
    for work in matching:
        if selected.sort_by in {"title", "year"}:
            value = getattr(work, selected.sort_by)
        elif dims[selected.sort_by].scope == "work":
            value = work.attributes.get(selected.sort_by)
        else:
            values = {r.dimensions[selected.sort_by] for r in matched_records
                      if r.work_id == work.id and selected.sort_by in r.dimensions}
            if len(values) > 1:
                raise ExplorationError("record values differ; sorting needs a narrower comparison")
            value = next(iter(values), None)
        sort_values[work.id] = value.casefold() if isinstance(value, str) else value
    present = sorted((w for w in matching if sort_values[w.id] is not None),
                     key=lambda w: (sort_values[w.id], w.id), reverse=selected.descending)
    missing = sorted((w for w in matching if sort_values[w.id] is None), key=lambda w: w.id)
    edges = [e for e in document.edges if e.from_id in matched_ids and e.to_id in matched_ids]
    context_ids = set()
    if selected.include_context:
        edges = [e for e in document.edges if e.from_id in matched_ids or e.to_id in matched_ids]
        context_ids = {key for e in edges for key in (e.from_id, e.to_id)} - matched_ids
    dump = lambda value: value.model_dump(mode="json", exclude_none=True)
    return {"works": [dump(w) for w in present + missing],
            "records": [dump(r) for r in matched_records],
            "edges": [dump(e) for e in edges], "context_work_ids": sorted(context_ids)}


def _root(root: Path) -> Path:
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ExplorationError("knowledge root must be an existing nonsymlink directory")
    return root.resolve()


def _flags(directory=False):
    return os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else os.O_NONBLOCK)


@contextmanager
def _open_relative(root: Path, path: str, directory=False):
    """Walk relative components with descriptors so symlink swaps cannot escape."""
    descriptor = os.open(root, _flags(directory=True))
    try:
        parts = PurePosixPath(path).parts
        for index, part in enumerate(parts):
            child = os.open(part, _flags(directory=index < len(parts) - 1 or directory),
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def assets(root: Path, data: dict, work_id: str) -> list[dict]:
    """Return every declared asset, retaining missing or unsafe-file diagnostics."""
    document = _document(data)
    work = next((w for w in document.works if w.id == work_id), None)
    if work is None:
        raise ExplorationError("unknown work identifier")
    root = _root(root)
    result = []
    for asset in work.assets:
        _, path = _uri_parts(asset.uri)
        available = True
        reason = "External link; availability is not checked" if path is None else "Available"
        if path is not None:
            try:
                with _open_relative(root, path) as descriptor:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise OSError("asset is not a regular file")
            except OSError:
                available = False
                reason = "Missing, unreadable or unsafe local file"
        result.append({**asset.model_dump(), "local": path is not None,
                       "available": available, "reason": reason})
    return result


class _Loader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ExplorationError("YAML aliases are not supported")
        return super().compose_node(parent, index)


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ExplorationError("YAML mappings require unique string keys")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def preserve_paper_units(before: dict, after: dict):
    """Check normalized outer models: whole removal, never retargeting or fragments."""
    by_id = {row["id"]: row for row in after["works"]}
    by_identity = {(row["entity_ref"]["source_id"], row["entity_ref"]["object_id"]): row
                   for row in after["works"] if row.get("entity_ref")}
    for prior in before["works"]:
        if prior["kind"] != "paper":
            continue
        identity = prior["entity_ref"]
        current = by_id.get(prior["id"])
        if current is None:
            if (identity["source_id"], identity["object_id"]) in by_identity:
                raise ExplorationError("Existing paper unit identity must not be reallocated")
            continue
        if current["kind"] != "paper" or current.get("entity_ref") != identity:
            raise ExplorationError("Existing paper unit identity and kind must be preserved")
        locations = {row["id"]: row["uri"] for row in current["assets"]}
        if any(locations.get(asset["id"]) != asset["uri"] for asset in prior["assets"]):
            raise ExplorationError("Existing paper unit assets must stay together; reconcile ownership separately")


class ExplorationStore:
    """The only managed file is .scholar-workflow/exploration.yml."""

    def __init__(self, root: Path):
        self.root = _root(root)
        self.path = self.root / ".scholar-workflow" / "exploration.yml"

    def _read_at(self, descriptor):
        try:
            fd = os.open("exploration.yml", _flags(), dir_fd=descriptor)
        except FileNotFoundError:
            return {"revision": None, "data": default_data()}
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ExplorationError("exploration file must be regular")
            if info.st_size > _MAX_STATE_BYTES:
                raise ExplorationError("exploration state exceeds the 2 MiB limit")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(_MAX_STATE_BYTES + 1)
            if len(raw) > _MAX_STATE_BYTES:
                raise ExplorationError("exploration state exceeds the 2 MiB limit")
            after = os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if len(raw) != info.st_size or any(
                getattr(info, field) != getattr(after, field) for field in fields
            ):
                raise ExplorationError("exploration state changed while reading; reload before retrying", 5)
        finally:
            os.close(fd)
        try:
            data = yaml.load(raw.decode("utf-8"), Loader=_Loader)
        except (UnicodeError, yaml.YAMLError) as exc:
            raise ExplorationError("invalid exploration YAML") from exc
        return {"revision": "sha256:" + hashlib.sha256(raw).hexdigest(), "data": validate(data)}

    def load(self) -> dict:
        try:
            with _open_relative(self.root, ".scholar-workflow", directory=True) as descriptor:
                return self._read_at(descriptor)
        except FileNotFoundError:
            return {"revision": None, "data": default_data()}
        except OSError as exc:
            raise ExplorationError("cannot safely read exploration state") from exc

    def save(self, data: dict, expected_revision: str | None = None) -> dict:
        validated = validate(data)
        if expected_revision is not None and (
            not isinstance(expected_revision, str) or
            not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_revision)
        ):
            raise ExplorationError("expected_revision must be null or a SHA-256 revision")
        payload = yaml.safe_dump(validated, allow_unicode=True, sort_keys=False).encode("utf-8")
        if len(payload) > _MAX_STATE_BYTES:
            raise ExplorationError("exploration state exceeds the 2 MiB limit")
        try:
            with _open_relative(self.root, ".", directory=True) as root_fd:
                try:
                    os.mkdir(".scholar-workflow", mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            with _open_relative(self.root, ".scholar-workflow", directory=True) as descriptor:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                temporary = None
                try:
                    current = self._read_at(descriptor)
                    if current["revision"] != expected_revision:
                        raise ExplorationError("exploration revision conflict; reload before saving", 5)
                    preserve_paper_units(current["data"], validated)
                    # Random names are transient; the directory descriptor pins the write root.
                    name = ".exploration-" + secrets.token_hex(12)
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=descriptor)
                    temporary = name
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    # Recheck immediately before replacement for edits from external tools.
                    if self._read_at(descriptor)["revision"] != expected_revision:
                        raise ExplorationError("exploration revision conflict; reload before saving", 5)
                    os.replace(name, "exploration.yml", src_dir_fd=descriptor, dst_dir_fd=descriptor)
                    temporary = None
                    os.fsync(descriptor)
                finally:
                    if temporary is not None:
                        os.unlink(temporary, dir_fd=descriptor)
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError as exc:
            raise ExplorationError("cannot safely save exploration state") from exc
        return {"revision": "sha256:" + hashlib.sha256(payload).hexdigest(), "data": validated}


def _text(value) -> str:
    return re.sub(r"([\\`*_{}\[\]()#!|>~])", r"\\\1", html.escape(str(value), quote=False))


def _link(asset):
    label = _text(asset["label"])
    return f"[{label}](<{quote(asset['uri'], safe='/:?=&%#@+~')}>)"


def render_markdown(root: Path, data: dict) -> str:
    """Render an independent navigation document without rewriting any paper unit."""
    document = _document(data)
    dims = {d.id: d for d in document.dimensions}
    asset_map = {a.id: a.model_dump() for w in document.works for a in w.assets}
    works = {w.id: w for w in document.works}
    lines = ["# 研究定位与资料导航", ""]

    def positioning(assignments):
        for key, value in assignments.items():
            dim = dims[key]
            labels = {v.id: v.label for v in dim.values}
            entries = value if isinstance(value, list) else [value]
            display = "、".join(str(labels.get(v, works[v].title
                                if dim.kind == "reference" and v in works else v))
                               for v in entries)
            unit = f" {dim.unit}" if dim.unit else ""
            lines.append(f"- {_text(dim.label)}：{_text(display)}{_text(unit)}")

    for work in document.works:
        lines.extend([f"## {_text(work.title)}", ""])
        if work.summary:
            lines.extend([_text(work.summary), ""])
        positioning(work.attributes)
        lines.extend(["", "### 相关资料", ""])
        work_assets = assets(root, data, work.id)
        for asset in work_assets:
            status = "" if asset["available"] else " — 文件缺失、不可读或路径不安全"
            lines.append(f"- {_link(asset)}{status}")
        if not work_assets:
            lines.append("尚未登记相关资料。")
        for diagnostic in work.asset_diagnostics:
            lines.append(f"- 资料状态：{_text(diagnostic)}")
        lines.extend(["", "### 条件与结果", ""])
        records = [r for r in document.records if r.work_id == work.id]
        for record in records:
            positioning(record.dimensions)
            for key, value in record.conditions.items():
                lines.append(f"- {_text(key)}：{_text(value)}")
            origin = {"author": "作者报告", "independent": "独立评测", "local": "本地复现",
                      "analysis": "分析判断"}[record.origin]
            lines.extend([f"- 结果（{origin}）：{_text(record.result)}",
                          f"- 评价与边界：{_text(record.assessment)}",
                          "- 依据：" + ("；".join(_link(asset_map[e]) for e in record.evidence)
                                       or "未提供证据入口"), ""])
        if not records:
            lines.extend(["尚未登记条件化研究记录。", ""])
        lines.extend(["### 相关工作与关系", ""])
        edges = [e for e in document.edges if work.id in {e.from_id, e.to_id}]
        for edge in edges:
            direction = " ↔ " if edge.kind == "competes" else " → "
            relation = direction.join(_text(works[key].title) for key in (edge.from_id, edge.to_id))
            lines.extend([f"- {relation}：{_text(edge.label)}。{_text(edge.explanation)}",
                          "  依据：" + "；".join(_link(asset_map[e]) for e in edge.evidence)])
        if not edges:
            lines.append("尚未登记有依据的工作关系。")
        lines.append("")
    if not document.works:
        lines.extend(["尚未登记研究工作。", ""])
    return "\n".join(lines)
