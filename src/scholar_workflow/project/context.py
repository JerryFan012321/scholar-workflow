"""Read one explicit project material list and render a service-free overview."""
from __future__ import annotations

import errno
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholar_workflow.project.layout import (
    ProjectLayoutError,
    is_project_id,
    load_project_layout,
    open_project_root,
    read_project_json,
)

PROJECT_CONTEXT = "project-context.json"
EntryKind = Literal["code", "paper", "analysis", "note", "experiment", "result", "other"]
EntryState = Literal["available", "missing", "unsafe", "unverified"]


class ProjectContextError(ValueError):
    """The explicit material list is invalid or belongs to another project."""


class _ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _clean_text(value: str) -> str:
    if value != value.strip() or not value or any(ord(char) < 32 for char in value):
        raise ValueError("Text must be non-empty, trimmed, and free of control characters")
    return value


def _reader_uri(uri: str, provider: str) -> None:
    """Allow known read-only endpoints; never treat URI syntax as source verification."""
    if (
        any(char.isspace() or ord(char) < 32 or char in "<>" for char in uri)
        or re.search(r"%(?![0-9a-fA-F]{2})", uri)
    ):
        raise ValueError("Reader URI contains unsafe characters or malformed encoding")
    parsed = urlsplit(uri)
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("Reader URI cannot contain credentials or a fragment")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=16)
    except ValueError as exc:
        raise ValueError("Reader URI query is invalid") from exc
    params = dict(pairs)
    if len(params) != len(pairs) or any(not value for value in params.values()):
        raise ValueError("Reader URI has duplicate or empty query fields")
    if any(ord(char) < 32 for value in params.values() for char in value):
        raise ValueError("Reader URI query contains control characters")
    key = r"[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}"
    if parsed.scheme == "zotero" and provider == "zotero":
        paths = rf"/(?:library|(?:groups|users)/[0-9]+)/items/{key}"
        if parsed.netloc == "select":
            if not re.fullmatch(rf"(?:{paths}|/items/@?{key})", parsed.path) or params:
                raise ValueError("Zotero selection URI must identify one item without commands")
            return
        if parsed.netloc != "open-pdf" or not re.fullmatch(paths, parsed.path):
            raise ValueError("Zotero reader URI must identify one PDF attachment")
        if set(params) - {"page", "annotation"}:
            raise ValueError("Unknown Zotero reader parameter")
        if "page" in params and not re.fullmatch(r"[1-9][0-9]*", params["page"]):
            raise ValueError("Zotero reader page must be a positive integer")
        if "annotation" in params and not re.fullmatch(key, params["annotation"]):
            raise ValueError("Zotero reader annotation must be an annotation key")
        return
    if parsed.scheme != "obsidian" or parsed.path not in {"", "/"}:
        raise ValueError("Reader URI must use a supported Zotero or Obsidian reader route")
    if provider == "obsidian" and parsed.netloc == "open":
        if set(params) - {"vault", "file", "block"} or not {"vault", "file"} <= set(params):
            raise ValueError("Obsidian reader URI requires only vault, file, and optional block")
        file_path = params["file"]
        if (
            PurePosixPath(file_path).is_absolute() or "\\" in file_path
            or any(part in {"", ".", ".."} for part in file_path.split("/"))
        ):
            raise ValueError("Obsidian reader file must be Vault-relative")
        return
    if provider != "zotero" or parsed.netloc != "zotflow":
        raise ValueError("Unknown or non-reader Obsidian route")
    if (
        set(params) - {"vault", "type", "libraryID", "key", "navigation"}
        or not {"vault", "type", "libraryID", "key"} <= set(params)
        or params["type"] not in {"open-attachment", "open-annotation"}
        or re.fullmatch(r"[1-9][0-9]*", params["libraryID"]) is None
        or re.fullmatch(key, params["key"]) is None
    ):
        raise ValueError("ZotFlow reader URI requires the supported attachment or annotation parameters")
    if "navigation" in params:
        try:
            navigation = json.loads(params["navigation"])
        except json.JSONDecodeError as exc:
            raise ValueError("ZotFlow navigation must be a page-index object") from exc
        if (
            params["type"] != "open-attachment" or not isinstance(navigation, dict)
            or set(navigation) != {"pageIndex"} or type(navigation["pageIndex"]) is not int
            or navigation["pageIndex"] < 0
        ):
            raise ValueError("ZotFlow navigation must contain only a nonnegative pageIndex")


class ProjectFileRef(_ContextModel):
    kind: Literal["project-file"]
    relative_path: str = Field(min_length=1, max_length=1024)
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")

    @field_validator("relative_path")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        _clean_text(value)
        path = PurePosixPath(value)
        if path.is_absolute() or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Project file reference must be a safe POSIX relative path")
        return value


class ExternalResourceRef(_ContextModel):
    kind: Literal["external-resource"]
    provider: Literal["zotero", "obsidian"]
    resource_id: str = Field(min_length=1, max_length=256)
    uri: str | None = Field(default=None, max_length=4096)

    @field_validator("resource_id")
    @classmethod
    def _resource_id(cls, value: str) -> str:
        return _clean_text(value)

    @model_validator(mode="after")
    def _stable_reader_uri(self) -> ExternalResourceRef:
        if self.uri is not None:
            _reader_uri(self.uri, self.provider)
        return self


ProjectReference = Annotated[ProjectFileRef | ExternalResourceRef, Field(discriminator="kind")]


class ProjectContextEntry(_ContextModel):
    entry_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
    kind: EntryKind
    title: str = Field(min_length=1, max_length=1000)
    purpose: str = Field(min_length=1, max_length=4000)
    ref: ProjectReference

    @field_validator("title", "purpose")
    @classmethod
    def _text(cls, value: str) -> str:
        return _clean_text(value)


class ProjectContext(_ContextModel):
    schema_version: Literal[1]
    project_id: str
    title: str = Field(min_length=1, max_length=1000)
    summary: str = Field(min_length=1, max_length=8000)
    language: Literal["en", "zh"] = "en"
    entries: list[ProjectContextEntry] = Field(max_length=512)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Project context schema_version must be an integer")
        return value

    @field_validator("project_id")
    @classmethod
    def _project_id(cls, value: str) -> str:
        if not is_project_id(value):
            raise ValueError("Project context project_id must be a canonical UUIDv4")
        return value

    @field_validator("title", "summary")
    @classmethod
    def _text(cls, value: str) -> str:
        return _clean_text(value)

    @model_validator(mode="after")
    def _unique_entries(self) -> ProjectContext:
        identities = [entry.entry_id for entry in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("Project context entry_id values must be unique")
        return self


class ProjectOverviewEntry(_ContextModel):
    entry_id: str
    kind: EntryKind
    title: str
    purpose: str
    ref: ProjectReference
    state: EntryState
    diagnostic: str


class ProjectOverview(_ContextModel):
    schema_version: Literal[1] = 1
    project_id: str
    title: str
    summary: str
    language: Literal["en", "zh"] = "en"
    entries: list[ProjectOverviewEntry]


def load_project_context(root: str | Path) -> ProjectContext:
    """Load only project-context.json and the accepted project-layout.json."""
    try:
        layout = load_project_layout(root)
        context = ProjectContext.model_validate(read_project_json(root, PROJECT_CONTEXT))
    except (ProjectLayoutError, ValueError) as exc:
        raise ProjectContextError(str(exc)) from exc
    if context.project_id != layout.project_id:
        raise ProjectContextError("Project context identity does not match project-layout.json")
    return context


def _local_reference_state(root_fd: int, reference: ProjectFileRef) -> tuple[EntryState, str]:
    descriptor = os.dup(root_fd)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        parts = reference.relative_path.split("/")
        for part in parts[:-1]:
            metadata = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                return "unsafe", "Reference contains a symlink or non-directory ancestor"
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            return "unsafe", "Symlink references are not followed"
        if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
            return "unsafe", "Reference is not a regular project file or directory"
        if reference.commit is not None:
            return "unverified", "Local path exists; the declared commit was not verified"
        return "available", "Local path exists; content and execution were not evaluated"
    except FileNotFoundError:
        return "missing", "Referenced project file or directory is missing"
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            return "unsafe", "Reference contains a symlink or non-directory ancestor"
        return "unsafe", "Referenced project path could not be inspected safely"
    finally:
        os.close(descriptor)


def build_project_overview(
    root: str | Path, context: ProjectContext | None = None,
) -> ProjectOverview:
    """Inspect explicit local refs; do not fetch or claim availability of external objects."""
    try:
        if context is None:
            context = load_project_context(root)
        else:
            context = ProjectContext.model_validate(context.model_dump(mode="json"))
            layout = load_project_layout(root)
            if context.project_id != layout.project_id:
                raise ProjectContextError("Project context identity does not match project-layout.json")
    except (ProjectLayoutError, ValueError) as exc:
        raise ProjectContextError(str(exc)) from exc
    entries: list[ProjectOverviewEntry] = []
    try:
        with open_project_root(root) as root_fd:
            for entry in context.entries:
                if isinstance(entry.ref, ProjectFileRef):
                    state, diagnostic = _local_reference_state(root_fd, entry.ref)
                else:
                    state = "unverified"
                    diagnostic = "External object was not queried; its identity and reader URI remain unverified"
                entries.append(ProjectOverviewEntry(
                    **entry.model_dump(exclude={"ref"}), ref=entry.ref,
                    state=state, diagnostic=diagnostic,
                ))
    except ProjectLayoutError as exc:
        raise ProjectContextError(str(exc)) from exc
    return ProjectOverview(
        project_id=context.project_id, title=context.title, summary=context.summary,
        language=context.language, entries=entries,
    )


def _markdown_text(value: str) -> str:
    value = value.replace("\\", "\\\\").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([`*_{}\[\]()#+.!|])", r"\\\1", value)


def render_project_overview(result: ProjectOverview) -> str:
    """Render human-oriented Markdown without absolute paths, IDs, hashes, or raw metadata."""
    chinese = result.language == "zh"
    groups: tuple[tuple[EntryKind, str, str], ...] = (
        ("code", "Code", "代码"), ("paper", "Papers", "论文"), ("analysis", "Analyses", "分析"),
        ("note", "Knowledge notes", "知识笔记"), ("experiment", "Experiments", "实验"),
        ("result", "Results", "成果"), ("other", "Other material", "其他资料"),
    )
    state_labels = {
        "available": "Available locally (path checked only)",
        "missing": "Missing", "unsafe": "Unsafe reference", "unverified": "Not verified",
    }
    if chinese:
        state_labels = {
            "available": "本地可定位（仅核查路径）", "missing": "缺失",
            "unsafe": "不安全引用", "unverified": "未核验",
        }
    chinese_diagnostics = {
        "Reference contains a symlink or non-directory ancestor": "路径包含符号链接或非目录的上级路径",
        "Symlink references are not followed": "不跟随符号链接引用",
        "Reference is not a regular project file or directory": "引用不是普通项目文件或目录",
        "Local path exists; the declared commit was not verified": "本地路径存在；声明的代码版本尚未核验",
        "Local path exists; content and execution were not evaluated": "本地路径存在；未评估内容或执行效果",
        "Referenced project file or directory is missing": "引用的项目文件或目录不存在",
        "Referenced project path could not be inspected safely": "无法安全检查引用的项目路径",
        "External object was not queried; its identity and reader URI remain unverified": "未查询外部对象；其身份与阅读链接仍未核验",
    }
    lines = [f"# {_markdown_text(result.title)}", "", _markdown_text(result.summary), ""]
    lines.extend([
        "本总览只呈现明确选定的资料，不复制、同步或执行它们。" if chinese else
        "This overview lists explicitly selected material. It does not copy, synchronize, or execute it.",
        "外部对象和阅读链接需在所属应用中核验。" if chinese else
        "External objects and reader links require verification in their owning application.", "",
    ])
    if not result.entries:
        lines.extend(["尚未声明项目资料。" if chinese else "No project material has been declared yet.", ""])
    for kind, heading_en, heading_zh in groups:
        entries = [entry for entry in result.entries if entry.kind == kind]
        if not entries:
            continue
        lines.extend([f"## {heading_zh if chinese else heading_en}", ""])
        for entry in entries:
            label = _markdown_text(entry.title)
            if isinstance(entry.ref, ProjectFileRef) and entry.state in {"available", "unverified"}:
                location = quote(entry.ref.relative_path, safe="/")
                label = f"[{label}]({location})"
            elif isinstance(entry.ref, ExternalResourceRef) and entry.ref.uri is not None:
                label = f"[{label}](<{entry.ref.uri}>)"
            diagnostic = chinese_diagnostics[entry.diagnostic] if chinese else entry.diagnostic
            purpose_label, status_label = ("用途", "状态") if chinese else ("Purpose", "Status")
            punctuation = "。" if chinese else ". "
            lines.extend([
                f"### {label}", "", f"{purpose_label}: {_markdown_text(entry.purpose)}", "",
                f"{status_label}: {state_labels[entry.state]}{punctuation}{_markdown_text(diagnostic)}", "",
            ])
    return "\n".join(lines).rstrip() + "\n"
