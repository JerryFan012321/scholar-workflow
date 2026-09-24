"""ZotFlow capability probing and Zotero-owned annotation projections."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import Field, field_validator

from scholar_workflow.adapters.zotero_local import (
    ZOTERO_KEY_RE,
    ZoteroAttachmentLocator,
    ZoteroLocalAdapter,
)
from scholar_workflow.hub.fields import (
    FieldRegistryError,
    KnowledgeSourceRegistry,
    read_obsidian_version,
)
from scholar_workflow.hub.models import HubModel

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_TRANSLATION = re.compile(r"🔤.*?🔤", re.DOTALL)


class ZotFlowError(RuntimeError):
    """ZotFlow cannot safely perform the requested action."""


class PdfRef(HubModel):
    provider: Literal["zotero"] = "zotero"
    library_id: str
    attachment_key: str
    content_hash: str

    @field_validator("library_id")
    @classmethod
    def _library_id(cls, value: str) -> str:
        if not value or value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("library_id must be clean text")
        return value

    @field_validator("attachment_key")
    @classmethod
    def _attachment_key(cls, value: str) -> str:
        if not ZOTERO_KEY_RE.fullmatch(value):
            raise ValueError("invalid Zotero attachment key")
        return value

    @field_validator("content_hash")
    @classmethod
    def _content_hash(cls, value: str) -> str:
        if not re.fullmatch(r"(?:md5:[0-9a-f]{32}|sha256:[0-9a-f]{64})", value):
            raise ValueError("content_hash must be a lowercase md5 or sha256 digest")
        return value

    @classmethod
    def from_locator(cls, locator: ZoteroAttachmentLocator) -> PdfRef:
        return cls(
            library_id=locator.library_id,
            attachment_key=locator.attachment_key,
            content_hash=locator.content_hash,
        )


class AnnotationIR(HubModel):
    """Read-only normalization of one annotation; it is never a write authority."""

    annotation_id: str
    pdf_ref: PdfRef
    authority: Literal["zotero"] = "zotero"
    source_id: str
    type: Literal["highlight", "underline", "note", "image", "ink"]
    quoted_text: str = ""
    comment: str = ""
    page_index: int | None = Field(default=None, ge=0)
    page_label: str | None = None
    geometry: dict[str, Any] = Field(default_factory=dict)
    color: str | None = None
    author: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    source_link: str
    source_pdf_hash: str
    sort_index: str = ""

    @field_validator("annotation_id", "source_id")
    @classmethod
    def _zotero_key(cls, value: str) -> str:
        if not ZOTERO_KEY_RE.fullmatch(value):
            raise ValueError("annotation/source id must be a Zotero key")
        return value


class ZotFlowCapability(HubModel):
    available: bool
    obsidian_version: str | None = None
    plugin_version: str | None = None
    min_app_version: str | None = None
    enabled: bool = False
    reason: str | None = None


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _SEMVER.fullmatch(value)
    if match is None:
        return None
    return tuple(int(component) for component in match.groups())


class ZotFlowReaderAdapter:
    """Open ZotFlow protocol URIs without reading its settings or credentials."""

    def __init__(
        self,
        vault_root: Path,
        *,
        app_path: Path = Path("/Applications/Obsidian.app"),
        runner=subprocess.run,
        timeout: float = 5.0,
    ) -> None:
        self.vault_root = Path(vault_root)
        self.app_path = Path(app_path)
        self._runner = runner
        self._timeout = timeout

    def probe(self) -> ZotFlowCapability:
        manifest_path = self.vault_root / ".obsidian" / "plugins" / "zotflow" / "manifest.json"
        enabled_path = self.vault_root / ".obsidian" / "community-plugins.json"
        obsidian_version = read_obsidian_version(self.app_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ZotFlowCapability(
                available=False,
                obsidian_version=obsidian_version,
                reason="ZotFlow is not installed in this Vault",
            )
        try:
            enabled_plugins = json.loads(enabled_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            enabled_plugins = []
        plugin_version = manifest.get("version")
        minimum = manifest.get("minAppVersion")
        enabled = (
            manifest.get("id") == "zotflow"
            and isinstance(enabled_plugins, list)
            and "zotflow" in enabled_plugins
        )
        if not enabled:
            return ZotFlowCapability(
                available=False,
                obsidian_version=obsidian_version,
                plugin_version=plugin_version if isinstance(plugin_version, str) else None,
                min_app_version=minimum if isinstance(minimum, str) else None,
                enabled=False,
                reason="ZotFlow is installed but not enabled in this Vault",
            )
        current = _version_tuple(obsidian_version or "")
        required = _version_tuple(minimum if isinstance(minimum, str) else "")
        if current is None or required is None:
            return ZotFlowCapability(
                available=False,
                obsidian_version=obsidian_version,
                plugin_version=plugin_version if isinstance(plugin_version, str) else None,
                min_app_version=minimum if isinstance(minimum, str) else None,
                enabled=True,
                reason="Obsidian/ZotFlow version compatibility could not be verified",
            )
        if current < required:
            return ZotFlowCapability(
                available=False,
                obsidian_version=obsidian_version,
                plugin_version=plugin_version if isinstance(plugin_version, str) else None,
                min_app_version=minimum if isinstance(minimum, str) else None,
                enabled=True,
                reason=f"Obsidian {minimum} or newer is required; installed {obsidian_version}",
            )
        return ZotFlowCapability(
            available=True,
            obsidian_version=obsidian_version,
            plugin_version=plugin_version if isinstance(plugin_version, str) else None,
            min_app_version=minimum if isinstance(minimum, str) else None,
            enabled=True,
        )

    def attachment_uri(self, pdf_ref: PdfRef) -> str:
        return "obsidian://zotflow?" + urlencode(
            {
                "type": "open-attachment",
                "libraryID": pdf_ref.library_id,
                "key": pdf_ref.attachment_key,
            }
        )

    def annotation_uri(self, annotation: AnnotationIR) -> str:
        return "obsidian://zotflow?" + urlencode(
            {
                "type": "open-annotation",
                "libraryID": annotation.pdf_ref.library_id,
                "key": annotation.annotation_id,
            }
        )

    def open_attachment(self, pdf_ref: PdfRef) -> dict[str, bool]:
        return self._open(self.attachment_uri(pdf_ref))

    def open_annotation(self, annotation: AnnotationIR) -> dict[str, bool]:
        return self._open(self.annotation_uri(annotation))

    def _open(self, uri: str) -> dict[str, bool]:
        capability = self.probe()
        if not capability.available:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        try:
            result = self._runner(
                ["/usr/bin/open", uri],
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ZotFlowError("Could not open ZotFlow") from exc
        if result.returncode != 0:
            raise ZotFlowError("Obsidian rejected the ZotFlow action")
        return {"opened": True}


class RegisteredSourceZotFlowAdapter:
    """Resolve ZotFlow only from explicitly registered Obsidian Sources."""

    def __init__(
        self,
        registry: KnowledgeSourceRegistry,
        *,
        app_path: Path = Path("/Applications/Obsidian.app"),
        runner=subprocess.run,
        timeout: float = 5.0,
    ) -> None:
        self.registry = registry
        self.app_path = Path(app_path)
        self._runner = runner
        self._timeout = timeout

    def _adapters(self) -> list[ZotFlowReaderAdapter]:
        try:
            document = self.registry.load_document()
        except FieldRegistryError as exc:
            raise ZotFlowError("Knowledge Source registry is invalid") from exc
        adapters: list[ZotFlowReaderAdapter] = []
        roots: set[Path] = set()
        for source in document.sources:
            if not source.enabled:
                continue
            try:
                root = self.registry.resolve(source.source_id, capability="read")
            except FieldRegistryError:
                continue
            if root in roots:
                continue
            roots.add(root)
            adapters.append(
                ZotFlowReaderAdapter(
                    root,
                    app_path=self.app_path,
                    runner=self._runner,
                    timeout=self._timeout,
                )
            )
        return adapters

    def _select(self) -> tuple[ZotFlowReaderAdapter | None, ZotFlowCapability]:
        try:
            adapters = self._adapters()
        except ZotFlowError as exc:
            return None, ZotFlowCapability(available=False, reason=str(exc))
        if not adapters:
            return None, ZotFlowCapability(
                available=False,
                reason="Register an Obsidian Source before using ZotFlow",
            )
        diagnostics: list[str] = []
        representative: ZotFlowCapability | None = None
        for adapter in adapters:
            capability = adapter.probe()
            if capability.available:
                return adapter, capability
            representative = representative or capability
            if capability.reason and capability.reason not in diagnostics:
                diagnostics.append(capability.reason)
        assert representative is not None
        return None, representative.model_copy(
            update={
                "reason": "; ".join(diagnostics)
                if diagnostics
                else "ZotFlow is unavailable in registered Sources"
            }
        )

    def probe(self) -> ZotFlowCapability:
        return self._select()[1]

    @staticmethod
    def attachment_uri(pdf_ref: PdfRef) -> str:
        return ZotFlowReaderAdapter(Path("/")).attachment_uri(pdf_ref)

    @staticmethod
    def annotation_uri(annotation: AnnotationIR) -> str:
        return ZotFlowReaderAdapter(Path("/")).annotation_uri(annotation)

    def open_attachment(self, pdf_ref: PdfRef) -> dict[str, bool]:
        adapter, capability = self._select()
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        return adapter.open_attachment(pdf_ref)

    def open_annotation(self, annotation: AnnotationIR) -> dict[str, bool]:
        adapter, capability = self._select()
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        return adapter.open_annotation(annotation)


def load_annotation_ir(
    adapter: ZoteroLocalAdapter,
    attachment_key: str,
) -> list[AnnotationIR]:
    """Project Local API annotation items into a sorted, read-only IR."""
    locator = adapter.resolve_attachment_locator(attachment_key)
    pdf_ref = PdfRef.from_locator(locator)
    result: list[AnnotationIR] = []
    for payload in adapter.get_annotations(attachment_key):
        key = payload.get("key")
        data = payload.get("data")
        if not isinstance(key, str) or not isinstance(data, dict):
            continue
        annotation_type = data.get("annotationType")
        if annotation_type not in {"highlight", "underline", "note", "image", "ink"}:
            continue
        raw_position = data.get("annotationPosition")
        try:
            geometry = json.loads(raw_position) if isinstance(raw_position, str) else {}
        except json.JSONDecodeError:
            geometry = {}
        if not isinstance(geometry, dict):
            geometry = {}
        page_index = geometry.get("pageIndex")
        if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
            page_index = None
        source_link = (
            f"zotero://open-pdf/library/items/{attachment_key}?annotation={key}"
        )
        try:
            result.append(
                AnnotationIR(
                    annotation_id=key,
                    pdf_ref=pdf_ref,
                    source_id=key,
                    type=annotation_type,
                    quoted_text=_TRANSLATION.sub(
                        "", str(data.get("annotationText") or "")
                    ).strip(),
                    comment=str(data.get("annotationComment") or "").strip(),
                    page_index=page_index,
                    page_label=(
                        str(data["annotationPageLabel"])
                        if data.get("annotationPageLabel") not in {None, ""}
                        else None
                    ),
                    geometry=geometry,
                    color=(
                        str(data["annotationColor"])
                        if data.get("annotationColor")
                        else None
                    ),
                    author=(
                        str(data["annotationAuthorName"])
                        if data.get("annotationAuthorName")
                        else None
                    ),
                    created_at=(str(data["dateAdded"]) if data.get("dateAdded") else None),
                    modified_at=(
                        str(data["dateModified"]) if data.get("dateModified") else None
                    ),
                    source_link=source_link,
                    source_pdf_hash=pdf_ref.content_hash,
                    sort_index=str(data.get("annotationSortIndex") or ""),
                )
            )
        except ValueError:
            continue
    return sorted(result, key=lambda row: (row.sort_index, row.annotation_id))


def validate_writer_namespaces(
    *,
    zotflow_prefix: str,
    better_notes_prefix: str,
    scholar_prefix: str,
) -> None:
    """Reject any path-prefix overlap between the three Markdown writers."""
    values = {
        "ZotFlow": _prefix_parts(zotflow_prefix),
        "Better Notes": _prefix_parts(better_notes_prefix),
        "Scholar Workflow": _prefix_parts(scholar_prefix),
    }
    for left_name, left in values.items():
        for right_name, right in values.items():
            if left_name >= right_name:
                continue
            shorter = min(len(left), len(right))
            if left[:shorter] == right[:shorter]:
                raise ValueError(
                    f"{left_name} and {right_name} writer namespaces overlap"
                )


def _prefix_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or value != value.strip() or not value or "\\" in value:
        raise ValueError("writer namespace must be a clean relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise ValueError("writer namespace must stay inside the Vault")
    return path.parts


def annotation_ir_from_local_api(
    attachment_key: str,
    *,
    adapter_factory=ZoteroLocalAdapter,
) -> list[AnnotationIR]:
    """Convenience read boundary that never requests a Zotero Web API key."""
    with adapter_factory() as adapter:
        return load_annotation_ir(adapter, attachment_key)


__all__ = [
    "AnnotationIR",
    "PdfRef",
    "RegisteredSourceZotFlowAdapter",
    "ZotFlowCapability",
    "ZotFlowError",
    "ZotFlowReaderAdapter",
    "annotation_ir_from_local_api",
    "load_annotation_ir",
    "validate_writer_namespaces",
]
