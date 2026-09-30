"""ZotFlow capability probing and Zotero-owned annotation projections."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import quote, urlencode

from pydantic import Field, field_validator

from scholar_workflow.adapters.zotero_local import (
    ZOTERO_KEY_RE,
    ZoteroAttachmentLocator,
    ZoteroLocalAdapter,
    ZoteroLocalError,
)
from scholar_workflow.hub.cmux import minimal_child_environment
from scholar_workflow.hub.fields import (
    FieldRegistryError,
    KnowledgeSourceRegistry,
    read_obsidian_version,
)
from scholar_workflow.hub.models import HubModel

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_TRANSLATION = re.compile(r"🔤.*?🔤", re.DOTALL)
_AUDITED_LOCAL_FIRST_VERSIONS = frozenset({"1.6.6"})
_LOCAL_SETTINGS_PROTOCOL = "zotflow-local-v1"
_VAULT_ID = re.compile(r"[0-9a-f]{16}\Z")
_MAX_OBSIDIAN_CONFIG_BYTES = 1024 * 1024
# This expression names only the two non-secret ZotFlow settings needed to
# establish a local PDF route. It never enumerates settings or reads data.json.
_LOCAL_SETTINGS_EXPRESSION = (
    "(() => { const p = app.plugins.plugins.zotflow; "
    "return JSON.stringify({protocol:'zotflow-local-v1', "
    "vault:app.vault.adapter.getBasePath(), enabled:!!p, "
    "local:p?.settings?.useZoteroStorage===true, "
    "storagePath:typeof p?.settings?.zoteroStoragePath==='string'"
    "?p.settings.zoteroStoragePath:''}); })()"
)


class ZotFlowError(RuntimeError):
    """ZotFlow cannot safely perform the requested action."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Obsidian config key")
        result[key] = value
    return result


def resolve_obsidian_vault_id(
    vault_root: Path, *, config_path: Path | None = None
) -> str:
    """Resolve one registered directory to its host-local Obsidian Vault ID.

    This reads only Obsidian's bounded local vault registry. It never returns
    registry contents or a path to the browser.
    """
    config = config_path or Path.home() / "Library/Application Support/obsidian/obsidian.json"
    try:
        fd = os.open(config, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or bool(info.st_mode & 0o022)
                or not 0 < info.st_size <= _MAX_OBSIDIAN_CONFIG_BYTES
            ):
                raise ZotFlowError("Obsidian Vault registry is unsafe or unavailable")
            raw = handle.read(_MAX_OBSIDIAN_CONFIG_BYTES + 1)
            if len(raw) != info.st_size:
                raise ZotFlowError("Obsidian Vault registry changed during reading")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        vaults = document.get("vaults") if isinstance(document, dict) else None
        if not isinstance(vaults, dict):
            raise ZotFlowError("Obsidian Vault registry is invalid")
        expected = Path(vault_root).resolve(strict=True)
        if not expected.is_dir():
            raise ZotFlowError("Registered Obsidian Vault is unavailable")
        matches: list[str] = []
        for vault_id, entry in vaults.items():
            if not isinstance(vault_id, str) or _VAULT_ID.fullmatch(vault_id) is None:
                raise ZotFlowError("Obsidian Vault registry is invalid")
            path = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(path, str) or not path or not Path(path).is_absolute():
                raise ZotFlowError("Obsidian Vault registry is invalid")
            try:
                candidate = Path(path).resolve(strict=True)
                if candidate.is_dir() and candidate.samefile(expected):
                    matches.append(vault_id)
            except (OSError, ValueError, RuntimeError):
                continue  # Stale unrelated Vaults do not authorize this Source.
        if len(matches) != 1:
            raise ZotFlowError("Registered Obsidian Vault ID is missing or ambiguous")
        return matches[0]
    except ZotFlowError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        raise ZotFlowError("Obsidian Vault registry is unsafe or unavailable") from exc


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
    """Open ZotFlow only after a narrow live local-storage capability probe."""

    def __init__(
        self,
        vault_root: Path,
        *,
        app_path: Path = Path("/Applications/Obsidian.app"),
        runner=subprocess.run,
        cli_runner=subprocess.run,
        zotero_factory=ZoteroLocalAdapter,
        timeout: float = 5.0,
        obsidian_config_path: Path | None = None,
    ) -> None:
        self.vault_root = Path(vault_root)
        self.app_path = Path(app_path)
        self._runner = runner
        self._cli_runner = cli_runner
        self._zotero_factory = zotero_factory
        self._timeout = timeout
        self._obsidian_config_path = obsidian_config_path

    def _vault_id(self) -> str:
        return resolve_obsidian_vault_id(
            self.vault_root, config_path=self._obsidian_config_path
        )

    def probe(self) -> ZotFlowCapability:
        return self._probe_with_storage()[0]

    def _version_probe(self) -> ZotFlowCapability:
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
        if plugin_version not in _AUDITED_LOCAL_FIRST_VERSIONS:
            return ZotFlowCapability(
                available=False,
                obsidian_version=obsidian_version,
                plugin_version=plugin_version if isinstance(plugin_version, str) else None,
                min_app_version=minimum if isinstance(minimum, str) else None,
                enabled=True,
                reason="ZotFlow version has not been audited for local-first PDF reading",
            )
        return ZotFlowCapability(
            available=True,
            obsidian_version=obsidian_version,
            plugin_version=plugin_version if isinstance(plugin_version, str) else None,
            min_app_version=minimum if isinstance(minimum, str) else None,
            enabled=True,
        )

    def _probe_with_storage(self) -> tuple[ZotFlowCapability, Path | None]:
        capability = self._version_probe()
        if not capability.available:
            return capability, None
        try:
            vault_id = self._vault_id()
        except ZotFlowError as exc:
            return capability.model_copy(update={
                "available": False,
                "reason": str(exc),
            }), None
        try:
            result = self._cli_runner(
                [
                    "obsidian",
                    f"vault={vault_id}",
                    "eval",
                    f"code={_LOCAL_SETTINGS_EXPRESSION}",
                ],
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                env=minimal_child_environment(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return capability.model_copy(update={
                "available": False,
                "reason": "Obsidian CLI could not verify ZotFlow local PDF mode",
            }), None
        output = result.stdout.strip() if isinstance(result.stdout, str) else ""
        if result.returncode != 0 or len(output) > 4096:
            return capability.model_copy(update={
                "available": False,
                "reason": "Obsidian CLI could not verify ZotFlow local PDF mode",
            }), None
        output = output.removeprefix("=> ")
        try:
            settings = json.loads(output)
        except json.JSONDecodeError:
            settings = None
        if not isinstance(settings, dict) or settings.get("protocol") != _LOCAL_SETTINGS_PROTOCOL:
            return capability.model_copy(update={
                "available": False,
                "reason": "ZotFlow local PDF mode returned an invalid capability response",
            }), None
        vault = settings.get("vault")
        try:
            expected_vault = self.vault_root.resolve(strict=True)
            actual_path = Path(vault) if isinstance(vault, str) else None
            actual_vault = (
                actual_path.resolve(strict=True)
                if actual_path is not None and actual_path.is_absolute()
                else None
            )
            vault_matches = (
                actual_vault is not None
                and expected_vault.is_dir()
                and actual_vault.is_dir()
                and expected_vault.samefile(actual_vault)
            )
        except (OSError, ValueError, RuntimeError):
            vault_matches = False
        if not vault_matches or settings.get("enabled") is not True:
            return capability.model_copy(update={
                "available": False,
                "reason": "Obsidian CLI did not confirm the registered ZotFlow Vault",
            }), None
        if settings.get("local") is not True:
            return capability.model_copy(update={
                "available": False,
                "reason": "Enable ZotFlow's local Zotero storage directory before opening PDFs",
            }), None
        storage_path = settings.get("storagePath")
        if not isinstance(storage_path, str) or not storage_path or not Path(storage_path).is_absolute():
            return capability.model_copy(update={
                "available": False,
                "reason": "ZotFlow local Zotero storage path is unavailable",
            }), None
        try:
            storage_root = Path(storage_path).resolve(strict=True)
        except OSError:
            storage_root = None
        if storage_root is None or not storage_root.is_dir():
            return capability.model_copy(update={
                "available": False,
                "reason": "ZotFlow local Zotero storage path is unavailable",
            }), None
        return capability, storage_root

    def probe_attachment(
        self, pdf_ref: PdfRef, *, verify_content: bool = False
    ) -> ZotFlowCapability:
        """Confirm ZotFlow can find this imported PDF without a cloud file request."""
        capability, storage_root = self._probe_with_storage()
        if not capability.available or storage_root is None:
            return capability
        try:
            with self._zotero_factory() as zotero:
                payload = zotero.get_item(pdf_ref.attachment_key)
                locator = zotero.resolve_attachment_locator(pdf_ref.attachment_key)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or data.get("linkMode") not in {
                "imported_file", "imported_url"
            }:
                raise ZotFlowError("ZotFlow local mode requires an imported PDF attachment")
            if (
                locator.attachment_key != pdf_ref.attachment_key
                or locator.library_id != pdf_ref.library_id
                or locator.content_hash != pdf_ref.content_hash
            ):
                raise ZotFlowError("Zotero PDF identity changed; refresh the paper listing")
            resolved_pdf = locator.path.resolve(strict=True)
            if not resolved_pdf.is_file():
                raise ZotFlowError("Zotero PDF is not available on this device")
            try:
                relative = resolved_pdf.relative_to(storage_root)
            except ValueError as exc:
                raise ZotFlowError("Zotero PDF is outside ZotFlow's local storage") from exc
            if len(relative.parts) != 2 or relative.parts[0] != pdf_ref.attachment_key:
                raise ZotFlowError("Zotero PDF is outside ZotFlow's local storage")
            filename = data.get("filename")
            if (
                not isinstance(filename, str)
                or filename in {"", ".", ".."}
                or "/" in filename
                or "\\" in filename
                or relative.parts[1] != filename
            ):
                raise ZotFlowError("Zotero PDF filename does not match its local file")
            if verify_content:
                algorithm, expected_digest = pdf_ref.content_hash.split(":", 1)
                digest = hashlib.new(algorithm)
                with resolved_pdf.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected_digest:
                    raise ZotFlowError("Zotero PDF content hash changed; refresh the paper listing")
        except (OSError, ZoteroLocalError, ZotFlowError) as exc:
            reason = (
                str(exc) if isinstance(exc, ZotFlowError)
                else "Zotero PDF is not available on this device"
            )
            return capability.model_copy(update={"available": False, "reason": reason})
        return capability

    def attachment_uri(self, pdf_ref: PdfRef) -> str:
        vault_id = self._vault_id()
        return "obsidian://zotflow?" + urlencode(
            {
                "vault": vault_id,
                "type": "open-attachment",
                "libraryID": pdf_ref.library_id,
                "key": pdf_ref.attachment_key,
            },
            quote_via=quote,
        )

    def annotation_uri(self, annotation: AnnotationIR) -> str:
        vault_id = self._vault_id()
        return "obsidian://zotflow?" + urlencode(
            {
                "vault": vault_id,
                "type": "open-annotation",
                "libraryID": annotation.pdf_ref.library_id,
                "key": annotation.annotation_id,
            },
            quote_via=quote,
        )

    def probe_source_note(self, library_id: str, item_key: str) -> ZotFlowCapability:
        """Check a ZotFlow-owned note without reading its secrets or downloading PDFs."""
        library_id = str(library_id)
        capability = self._version_probe()
        if not capability.available:
            return capability
        try:
            self._vault_id()
            if not ZOTERO_KEY_RE.fullmatch(item_key):
                raise ZotFlowError("Invalid Zotero item identity")
            with self._zotero_factory() as zotero:
                payload = zotero.get_item(item_key)
            if not isinstance(payload, dict):
                raise ZotFlowError("Zotero returned an invalid item")
            data = payload.get("data", {})
            if (not isinstance(data, dict) or payload.get("deleted") or data.get("deleted")
                    or data.get("itemType") in {"attachment", "note", "annotation"}):
                raise ZotFlowError("Zotero source item is unavailable or is not a parent resource")
            library = payload.get("library")
            actual_id = library.get("id") if isinstance(library, dict) else None
            if str(actual_id) != library_id or payload.get("key") != item_key:
                raise ZotFlowError("Zotero item does not belong to the requested library")
        except (OSError, ZoteroLocalError, ZotFlowError) as exc:
            return capability.model_copy(update={"available": False, "reason": str(exc)})
        return capability

    def source_note_uri(self, library_id: str, item_key: str) -> str:
        library_id = str(library_id)
        if not ZOTERO_KEY_RE.fullmatch(item_key) or not library_id or any(
            ord(char) < 32 for char in library_id
        ):
            raise ZotFlowError("Invalid Zotero source note identity")
        return "obsidian://zotflow?" + urlencode(
            {"vault": self._vault_id(), "type": "open-note", "libraryID": library_id,
             "key": item_key},
            quote_via=quote,
        )

    def open_source_note(self, library_id: str, item_key: str) -> dict[str, bool]:
        capability = self.probe_source_note(library_id, item_key)
        if not capability.available:
            raise ZotFlowError(capability.reason or "ZotFlow source note is unavailable")
        return self._open(self.source_note_uri(library_id, item_key))

    def open_attachment(self, pdf_ref: PdfRef) -> dict[str, bool]:
        capability = self.probe_attachment(pdf_ref, verify_content=True)
        if not capability.available:
            raise ZotFlowError(capability.reason or "ZotFlow local PDF is unavailable")
        return self._open(self.attachment_uri(pdf_ref))

    def open_annotation(self, annotation: AnnotationIR) -> dict[str, bool]:
        capability = self.probe_attachment(annotation.pdf_ref, verify_content=True)
        if not capability.available:
            raise ZotFlowError(capability.reason or "ZotFlow local PDF is unavailable")
        return self._open(self.annotation_uri(annotation))

    def _open(self, uri: str) -> dict[str, bool]:
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
        cli_runner=subprocess.run,
        zotero_factory=ZoteroLocalAdapter,
        timeout: float = 5.0,
        obsidian_config_path: Path | None = None,
    ) -> None:
        self.registry = registry
        self.app_path = Path(app_path)
        self._runner = runner
        self._cli_runner = cli_runner
        self._zotero_factory = zotero_factory
        self._timeout = timeout
        self._obsidian_config_path = obsidian_config_path

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
                    cli_runner=self._cli_runner,
                    zotero_factory=self._zotero_factory,
                    timeout=self._timeout,
                    obsidian_config_path=self._obsidian_config_path,
                )
            )
        return adapters

    def _select(
        self, pdf_ref: PdfRef | None = None
    ) -> tuple[ZotFlowReaderAdapter | None, ZotFlowCapability]:
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
        eligible: list[tuple[ZotFlowReaderAdapter, ZotFlowCapability]] = []
        for adapter in adapters:
            capability = (
                adapter.probe_attachment(pdf_ref)
                if pdf_ref is not None else adapter.probe()
            )
            if capability.available:
                eligible.append((adapter, capability))
                continue
            representative = representative or capability
            if capability.reason and capability.reason not in diagnostics:
                diagnostics.append(capability.reason)
        if len(eligible) == 1:
            return eligible[0]
        if len(eligible) > 1:
            return None, eligible[0][1].model_copy(update={
                "available": False,
                "reason": "Multiple ZotFlow Vaults are available; select a Source before opening",
            })
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

    def probe_attachment(self, pdf_ref: PdfRef) -> ZotFlowCapability:
        return self._select(pdf_ref)[1]

    def attachment_uri(self, pdf_ref: PdfRef) -> str:
        adapter, capability = self._select(pdf_ref)
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        return adapter.attachment_uri(pdf_ref)

    def annotation_uri(self, annotation: AnnotationIR) -> str:
        adapter, capability = self._select(annotation.pdf_ref)
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        return adapter.annotation_uri(annotation)

    def open_attachment(self, pdf_ref: PdfRef) -> dict[str, bool]:
        adapter, capability = self._select(pdf_ref)
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        return adapter.open_attachment(pdf_ref)

    def open_annotation(self, annotation: AnnotationIR) -> dict[str, bool]:
        adapter, capability = self._select(annotation.pdf_ref)
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow is unavailable")
        return adapter.open_annotation(annotation)

    def _source_note_adapter(
        self, library_id: str, item_key: str, *, source_id: str | None = None,
    ) -> tuple[ZotFlowReaderAdapter | None, ZotFlowCapability]:
        try:
            if source_id is None:
                adapters = self._adapters()
            else:
                root = self.registry.resolve(source_id, capability="read")
                adapters = [ZotFlowReaderAdapter(
                    root, app_path=self.app_path, runner=self._runner,
                    cli_runner=self._cli_runner, zotero_factory=self._zotero_factory,
                    timeout=self._timeout, obsidian_config_path=self._obsidian_config_path,
                )]
        except (FieldRegistryError, ZotFlowError) as exc:
            return None, ZotFlowCapability(available=False, reason=str(exc))
        eligible: list[tuple[ZotFlowReaderAdapter, ZotFlowCapability]] = []
        failures: list[str] = []
        for adapter in adapters:
            capability = adapter.probe_source_note(library_id, item_key)
            if capability.available:
                eligible.append((adapter, capability))
            elif capability.reason:
                failures.append(capability.reason)
        if len(eligible) == 1:
            return eligible[0]
        reason = (
            "Multiple ZotFlow Vaults are available; select a Source before opening"
            if eligible else "; ".join(dict.fromkeys(failures))
            or "Register an Obsidian Source before opening ZotFlow notes"
        )
        return None, ZotFlowCapability(available=False, reason=reason)

    def probe_source_note(
        self, library_id: str, item_key: str, *, source_id: str | None = None,
    ) -> ZotFlowCapability:
        return self._source_note_adapter(library_id, item_key, source_id=source_id)[1]

    def open_source_note(
        self, library_id: str, item_key: str, *, source_id: str | None = None,
    ) -> dict[str, bool]:
        adapter, capability = self._source_note_adapter(
            library_id, item_key, source_id=source_id,
        )
        if adapter is None:
            raise ZotFlowError(capability.reason or "ZotFlow source note is unavailable")
        return adapter.open_source_note(library_id, item_key)


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
    "resolve_obsidian_vault_id",
    "validate_writer_namespaces",
]
