"""Reference complete, explicitly registered paper units without saving state."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

from scholar_workflow.config import DEFAULT_HOME
from scholar_workflow.knowledge.exploration import ExplorationError
from scholar_workflow.knowledge.exploration_import import import_paper_units
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.workflows.exploration_assets import include_resource_links, resource_links
from scholar_workflow.workflows.field_paper_units import field_paper_units


def _text(value, name: str) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 1000
            or any(ord(char) < 32 for char in value)):
        raise ExplorationError(f"{name} must be a nonblank text value")
    return value


def _revision(registry, expected: str) -> None:
    if registry.revision() != expected:
        raise ExplorationError("Source registration changed; reload the selection.", 5)


def _source_roots(document) -> dict:
    folders = {row.folder_id: row.root for row in document.folders
               if row.enabled and "read" in row.capabilities}
    return {row.source_id: folders[row.folder_id] for row in document.sources
            if row.enabled and "read" in row.capabilities and row.folder_id in folders}


def _offline_links(unit: dict) -> dict:
    """Retain pre-enriched references, otherwise derive registered offline links."""
    result = deepcopy(unit)
    if "resource_links" not in result:
        resource = result.get("catalog_resource")
        if isinstance(resource, dict):
            if resource.get("resource_id") != result["resource_id"]:
                raise ExplorationError("Provider resource identity changed; reload.", 5)
            resolved = resource_links(resource)
            result["resource_links"] = resolved["links"]
            result["resource_notes"] = resolved["notes"]
        else:
            result["resource_links"] = []
            result["resource_notes"] = ["原文来源记录缺失；网页与 Zotero 入口尚未核实。"]
    if not isinstance(result["resource_links"], list):
        raise ExplorationError("Provider resource links must be a list")
    notes = result.get("resource_notes", [])
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise ExplorationError("Provider resource diagnostics must be text entries")
    return result


def _unit_diagnostics(unit: dict) -> list[str]:
    notes = list(unit.get("resource_notes", []))
    ownership = unit.get("ownership")
    if not isinstance(ownership, dict) or ownership.get("status") != "resolved":
        notes.append("论文单元归属尚未解析或存在冲突，暂不能引用。")
    files = unit["files"]
    if not files:
        notes.append("论文单元没有已声明资产，清单尚不完整。")
    for row in files:
        if not isinstance(row, dict):
            raise ExplorationError("Declared paper files must be objects")
        if row.get("file_state") != "available":
            notes.append(f"已声明资产“{_text(row.get('title'), 'asset title')}”目前不可用。")
        elif row.get("open_state") not in {"ready", "unsupported_type"}:
            notes.append(f"已声明资产“{_text(row.get('title'), 'asset title')}”打开入口尚未就绪。")
    return list(dict.fromkeys(notes))


class _ScopedRegistry(KnowledgeSourceRegistry):
    """Check the document returned to each selector and registry resolution."""

    def __init__(self, path, root_validator):
        super().__init__(path)
        self.root_validator = root_validator

    def load_document(self):
        document = super().load_document()
        for folder in document.folders:
            if folder.enabled:
                self.root_validator(folder.root)
        return document


class ExplorationReferenceService:
    """Read current registrations and prepare a whole-unit reference proposal.

    Methods never save the exploration manifest, allocate a paper identity, read
    paper bodies or modify owned assets. Provider ownership resolution remains a
    separate read; these methods do not establish scientific support.
    """

    def __init__(self, registry_path=None, *, resolve_reader=True, enrich_resources=True,
                 root_validator=None) -> None:
        self.registry_path = (Path(registry_path) if registry_path is not None else
                              Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)) /
                              "hub" / "sources.json")
        self.resolve_reader = resolve_reader
        self.enrich_resources = enrich_resources
        self.root_validator = root_validator

    def _registry(self):
        return (_ScopedRegistry(self.registry_path, self.root_validator)
                if self.root_validator is not None else KnowledgeSourceRegistry(self.registry_path))

    def fields(self) -> dict:
        """List existing public selectors, without discovering directories."""
        try:
            registry = self._registry()
            before = registry.revision()
            rows = FieldService(registry).list_fields()
            if not isinstance(rows, list):
                raise ExplorationError("Registered Field inventory must be a list")
            fields, diagnostics, seen = [], [], set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ExplorationError("Registered Field entries must be objects")
                if not row.get("available", True):
                    diagnostics.append("已登记知识来源当前不可用，部分领域无法列出。")
                    continue
                source_id = _text(row.get("source_id"), "source_id")
                field_id = _text(row.get("field_id"), "field_id")
                if (source_id, field_id) in seen:
                    raise ExplorationError("Registered Field identity is repeated", 5)
                seen.add((source_id, field_id))
                field = {"source_id": source_id, "field_id": field_id,
                         "title": _text(row.get("title"), "Field title")}
                if row.get("source_title") is not None:
                    field["source_title"] = _text(row["source_title"], "Source title")
                fields.append(field)
            _revision(registry, before)
            return {"fields": fields, "diagnostics": list(dict.fromkeys(diagnostics))}
        except ExplorationError:
            raise
        except (FieldRegistryError, OSError, ValueError) as exc:
            raise ExplorationError("Registered Fields could not be read safely") from exc

    def _inventory(self, source_id: str, field_id: str):
        _text(source_id, "source_id")
        _text(field_id, "field_id")
        registry = self._registry()
        before = registry.revision()
        roots = _source_roots(registry.load_document())
        if source_id not in roots:
            raise ExplorationError("Select an enabled registered Source with read capability")
        options = {"resolve_reader": False} if not self.resolve_reader else {}
        if self.root_validator is not None:
            options["root_validator"] = self.root_validator
        payload = field_paper_units(self.registry_path, source_id=source_id, field_id=field_id,
                                    include_resource_links=True, **options)
        if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != 1
                or not isinstance(payload.get("paper_units"), list)):
            raise ExplorationError("Expected a current paper-unit inventory")
        if payload.get("source_id") != source_id or payload.get("field_id") != field_id:
            raise ExplorationError("Provider Field selection changed; reload.", 5)
        result = deepcopy(payload)
        units, seen = [], set()
        for unit in result["paper_units"]:
            if not isinstance(unit, dict):
                raise ExplorationError("Paper units must be objects")
            identity = (_text(unit.get("source_id"), "unit source_id"),
                        _text(unit.get("resource_id"), "resource_id"))
            if identity in seen:
                raise ExplorationError("Paper-unit inventory repeats a qualified identity", 5)
            seen.add(identity)
            _text(unit.get("title"), "paper title")
            if not isinstance(unit.get("files"), list):
                raise ExplorationError("A paper unit must retain its complete declared file list")
            units.append(_offline_links(unit))
        result["paper_units"] = units
        _revision(registry, before)
        return registry, before, roots, result

    def units(self, source_id: str, field_id: str) -> dict:
        """Return whole-unit summaries; diagnostic entries remain selectable data."""
        try:
            registry, before, _roots, payload = self._inventory(source_id, field_id)
            units = [{"entity_ref": {"source_id": row["source_id"], "object_id": row["resource_id"]},
                      "title": row["title"],
                      "asset_count": len(row["files"]) + len(row["resource_links"]),
                      "diagnostics": _unit_diagnostics(row)} for row in payload["paper_units"]]
            diagnostics = []
            if payload.get("unresolved_references"):
                diagnostics.append("领域存在未解析的资源引用，请先处理归属问题。")
            if payload.get("issues"):
                diagnostics.append("当前资源清单存在诊断，请在引用前核对。")
            _revision(registry, before)
            return {"units": units, "diagnostics": diagnostics}
        except ExplorationError:
            raise
        except (FieldRegistryError, OSError, ValueError) as exc:
            raise ExplorationError("Registered paper units could not be read safely") from exc

    def reading_snapshot(self, root, source_id: str, field_id: str) -> dict:
        """Read only selected Source-owned packages; never authorize an import."""
        from scholar_workflow.knowledge.exploration_import import preview_paper_units

        registry, before, roots, payload = self._inventory(source_id, field_id)
        # Cross-Field references require their own verified ownership operation.
        payload["paper_units"] = [unit for unit in payload["paper_units"]
                                  if unit["source_id"] == source_id
                                  and "owned" in unit.get("selected_by", [])]
        if not payload["paper_units"]:
            raise ExplorationError("The selected Field has no declared owned paper units")
        data = preview_paper_units(root, payload, source_roots=roots)
        diagnostics = ["只读浏览现有论文包；不会保存定位或改写原文件。"]
        if payload.get("issues") or payload.get("unresolved_references"):
            diagnostics.append("部分来源或引用尚未核实；全局归属诊断保留，正式引用和写入仍受阻止。")
        stamp = json.dumps({"data": data, "issues": payload.get("issues", []),
                            "unresolved": payload.get("unresolved_references", [])},
                           sort_keys=True, ensure_ascii=False).encode()
        _revision(registry, before)
        return {"data": data, "revision": "read-only:" + hashlib.sha256(stamp).hexdigest(),
                "read_only": True, "diagnostics": diagnostics}

    def current_unit(self, ref: dict) -> dict:
        """Reload one qualified owner's registered inventory for native reading."""
        if not isinstance(ref, dict) or set(ref) != {"source_id", "object_id"}:
            raise ExplorationError("A qualified source_id and object_id are required")
        source_id = _text(ref["source_id"], "source_id")
        owner_id = _text(ref["object_id"], "object_id")
        try:
            registry = self._registry()
            before = registry.revision()
            result = None
            for field in FieldService(registry).list_fields():
                if field.get("source_id") != source_id or not field.get("available", True):
                    continue
                _registry, _before, _roots, payload = self._inventory(source_id, field["field_id"])
                for unit in payload["paper_units"]:
                    if unit["source_id"] != source_id or unit["resource_id"] != owner_id:
                        continue
                    if unit.get("ownership", {}).get("status") != "resolved":
                        raise ExplorationError("The current unit ownership is unresolved", 5)
                    if result is not None and any(result.get(key) != unit.get(key)
                            for key in ("catalog_resource", "files")):
                        raise ExplorationError("Registered unit inventories disagree", 5)
                    result = unit
            _revision(registry, before)
            if result is None:
                raise ExplorationError("The unit is not in its current registered Source")
            return deepcopy(result)
        except ExplorationError:
            raise
        except (FieldRegistryError, OSError, ValueError, KeyError) as exc:
            raise ExplorationError("The current registered unit could not be read safely") from exc

    def reference(self, root, data: dict, source_id: str, field_id: str, unit_refs: list) -> dict:
        """Prepare complete references for explicit qualified units, without saving."""
        if not isinstance(unit_refs, list) or not unit_refs:
            raise ExplorationError("Select at least one whole paper unit")
        selections = []
        seen = set()
        for ref in unit_refs:
            if not isinstance(ref, dict) or set(ref) != {"source_id", "object_id"}:
                raise ExplorationError("Select whole units by source_id and object_id only")
            identity = (_text(ref["source_id"], "unit source_id"),
                        _text(ref["object_id"], "unit object_id"))
            if identity in seen:
                raise ExplorationError("The same qualified unit was selected twice", 5)
            seen.add(identity)
            selections.append(identity)
        try:
            registry, before, roots, payload = self._inventory(source_id, field_id)
            available = {(row["source_id"], row["resource_id"]): row
                         for row in payload["paper_units"]}
            selected = []
            for identity in selections:
                if identity not in available:
                    raise ExplorationError("Selected unit is not in the current Field inventory")
                unit = available[identity]
                ownership = unit.get("ownership")
                if not isinstance(ownership, dict) or ownership.get("status") != "resolved":
                    raise ExplorationError("Selected unit has unresolved or conflicting ownership", 5)
                if identity[0] not in roots:
                    raise ExplorationError("Selected unit has no readable registered Source", 5)
                selected.append(unit)
            payload["paper_units"] = selected
            if self.enrich_resources:
                payload = include_resource_links(payload)
            proposed = import_paper_units(root, data, payload, source_roots=roots)
            _revision(registry, before)
            return proposed
        except ExplorationError:
            raise
        except (FieldRegistryError, OSError, ValueError) as exc:
            raise ExplorationError("Selected paper units could not be referenced safely") from exc


class RegisteredReadingStore:
    """A live, nonpersisted projection; it has deliberately no save operation."""

    def __init__(self, root, source_id, field_id, service=None):
        self.root, self.source_id, self.field_id = root, source_id, field_id
        self.service = service or ExplorationReferenceService()

    def load(self):
        return self.service.reading_snapshot(self.root, self.source_id, self.field_id)
