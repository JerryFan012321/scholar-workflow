"""Import explicit public paper-unit references without scanning or modifying units."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

from scholar_workflow.knowledge.exploration import ExplorationError, validate


def _identity(*parts: str, prefix: str) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return prefix + hashlib.sha256(raw).hexdigest()


def _text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ExplorationError(f"paper-unit {name} must be a nonblank string")
    return value


def _relative(value) -> str:
    value = _text(value, "relative_path")
    if (value.startswith(("/", "~")) or "\\" in value or
            any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ExplorationError("paper-unit relative_path must remain within its declared Source")
    return value


def _asset_uri(root: Path, source_root, row: dict, source_id: str) -> str:
    uri = row.get("uri")
    if uri is not None:
        uri = _text(uri, "uri")
        scheme = urlsplit(uri).scheme
        if scheme not in {"https", "http", "obsidian", "zotero"}:
            raise ExplorationError("paper-unit URI must be an explicit supported native or web URL")
        # Public web and Zotero identities must not be replaced with a guessed file.
        if scheme in {"https", "http", "zotero"} or "relative_path" not in row:
            return uri
    relative = _relative(row.get("relative_path"))
    if source_root is not None:
        declared_root = Path(source_root)
        if not declared_root.is_absolute():
            raise ExplorationError("Source roots must be explicit absolute registered roots")
        resolved_root = declared_root.resolve()
        try:
            # Combine only the explicit Source and checked relative declaration.
            # Do not resolve the asset: readers must still refuse symlink traversal.
            inside = (resolved_root / relative).relative_to(root)
        except ValueError:
            pass
        else:
            return quote(inside.as_posix(), safe="/")
    if uri is not None:
        return uri
    raise ExplorationError(
        f"paper-unit asset {source_id}/{row.get('object_id', '?')} has no root-relative "
        "location or declared native/web URI; provide its registered Source root"
    )


def import_paper_units(root, data: dict, payload: dict, *, source_roots=None) -> dict:
    return _import_units(root, data, payload, source_roots=source_roots, read_only=False)


def preview_paper_units(root, payload: dict, *, source_roots=None) -> dict:
    """Build a nonpersisted reading projection, never an authorized reference."""
    from scholar_workflow.knowledge.exploration import default_data

    return _import_units(root, default_data(), payload, source_roots=source_roots, read_only=True)


def _import_units(root, data: dict, payload: dict, *, source_roots, read_only: bool) -> dict:
    """Return augmented explorer state; callers separately review and CAS-save it.

    ``payload`` is the public ``field_paper_units`` response, not a directory listing.
    ``source_roots`` is an optional explicit registry mapping. Paths from one Source
    are never assumed to belong to another Source or to ``root``. Shared files get
    per-work asset-reference IDs while continuing to point to the same source URI.
    Existing work metadata and research judgments are left intact.
    """
    updated = validate(data)
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ExplorationError("exploration root must be an existing nonsymlink directory")
    root = root.resolve()
    if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
            or payload["schema_version"] != 1 or not isinstance(payload.get("paper_units"), list)):
        raise ExplorationError("expected a schema_version 1 public paper-unit payload")
    if payload.get("unresolved_references") and not read_only:
        raise ExplorationError("Selected Field has unresolved references; nothing was imported")
    if source_roots is None:
        source_roots = {}
    if not isinstance(source_roots, Mapping):
        raise ExplorationError("Source roots must be an explicit registry mapping")
    identities = {
        (work["entity_ref"]["source_id"], work["entity_ref"]["object_id"]): work
        for work in updated["works"] if work.get("entity_ref")
    }
    work_ids = {work["id"] for work in updated["works"]}
    asset_owners = {asset["id"]: work["id"] for work in updated["works"] for asset in work["assets"]}
    seen = set()
    for unit in payload["paper_units"]:
        if not isinstance(unit, dict):
            raise ExplorationError("paper units must be objects")
        source_id = _text(unit.get("source_id"), "source_id")
        resource_id = _text(unit.get("resource_id"), "resource_id")
        identity = source_id, resource_id
        if identity in seen:
            raise ExplorationError("paper-unit payload repeats a qualified paper identity")
        seen.add(identity)
        pending = (read_only and unit.get("local_read_state") == "declared"
                   and isinstance(unit.get("ownership"), dict)
                   and unit["ownership"].get("status") == "incomplete")
        if (not isinstance(unit.get("ownership"), dict)
                or unit["ownership"].get("status") != "resolved" and not pending):
            raise ExplorationError(f"paper-unit {source_id}/{resource_id} has unresolved ownership")
        title = _text(unit.get("title"), "title")
        files = unit.get("files")
        if not isinstance(files, list) or not files:
            raise ExplorationError("paper unit must retain all explicitly declared files")
        work = identities.get(identity)
        if work is not None and work["kind"] != "paper":
            raise ExplorationError("qualified paper identity belongs to an existing non-paper resource", 5)
        if work is None:
            work_id = _identity(*identity, prefix="paper-unit-")
            if work_id in work_ids:
                raise ExplorationError("generated work identity is occupied; reconcile explicitly", 5)
            work = {"id": work_id, "title": title, "kind": "paper", "attributes": {},
                    "entity_ref": {"source_id": source_id, "object_id": resource_id}, "assets": []}
            updated["works"].append(work)
            identities[identity] = work
            work_ids.add(work_id)
        existing = {asset["id"]: asset for asset in work["assets"]}
        links = unit.get("resource_links", [])
        if not isinstance(links, list):
            raise ExplorationError("resource links must be an explicit list")
        if "resource_notes" in unit:
            work["asset_diagnostics"] = unit["resource_notes"]
        if pending:
            work.setdefault("asset_diagnostics", []).append(
                "当前知识来源的论文包可只读浏览；其他来源登记不可用，全局唯一归属仍待核实。")
        seen_objects = set()
        for row in [*files, *links]:
            if not isinstance(row, dict):
                raise ExplorationError("declared paper-unit files must be objects")
            object_id = _text(row.get("object_id"), "object_id")
            if object_id in seen_objects:
                raise ExplorationError("paper unit repeats a declared file identity")
            seen_objects.add(object_id)
            if (row.get("file_state") == "unsafe" or row.get("open_state") == "ownership_unresolved"
                    and not (pending and row.get("local_read_state") == "declared")):
                raise ExplorationError(f"paper-unit asset {source_id}/{object_id} is unsafe")
            if row in links and (not isinstance(row.get("uri"), str)
                                 or urlsplit(row["uri"]).scheme not in
                                 {"https", "http", "obsidian", "zotero"}):
                raise ExplorationError("resource links require explicit native or web URLs")
            asset = {
                "id": _identity(source_id, resource_id, object_id, prefix="paper-asset-"),
                "label": (_text(row.get("title"), "file title") if row.get("title") != object_id
                          else Path(row.get("relative_path", object_id)).name),
                "kind": _text(row.get("kind"), "file kind"),
                "uri": _asset_uri(root, source_roots.get(source_id), row, source_id),
            }
            prior = existing.get(asset["id"])
            if prior is not None:
                if prior["uri"] != asset["uri"]:
                    raise ExplorationError("existing paper asset has a different URI; reconcile explicitly", 5)
                continue
            if asset["id"] in asset_owners:
                raise ExplorationError("generated asset identity belongs to another work", 5)
            work["assets"].append(asset)
            existing[asset["id"]] = asset
            asset_owners[asset["id"]] = work["id"]
    return validate(updated)
