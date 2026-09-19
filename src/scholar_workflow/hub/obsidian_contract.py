"""Hub-owned identity layer for otherwise human-owned Obsidian documents."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping


MANAGED_FRONTMATTER_FIELDS = frozenset(
    {
        "sw_schema",
        "sw_kind",
        "sw_catalog_id",
        "sw_topic_id",
        "sw_resource_id",
        "sw_zotero_item_key",
        "sw_attachment_key",
        "sw_parent_id",
        "sw_revision",
        "sw_tree_kind",
    }
)


def content_revision(body: str) -> str:
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def artifact_id_from_path(kind: str, vault_path: str) -> str:
    """Create a stable ID without storing an absolute path in the catalog."""
    digest = hashlib.sha256(vault_path.encode("utf-8")).hexdigest()[:20]
    return f"vault:{kind}:{digest}"


def managed_frontmatter(
    *,
    kind: str,
    catalog_id: str,
    body: str,
    optional: Mapping[str, object] | None = None,
) -> dict[str, object]:
    values: dict[str, object] = {
        "sw_schema": 1,
        "sw_kind": kind,
        "sw_catalog_id": catalog_id,
        "sw_revision": content_revision(body),
    }
    values.update(optional or {})
    unknown = set(values) - MANAGED_FRONTMATTER_FIELDS
    if unknown:
        raise ValueError(f"unknown Hub frontmatter fields: {sorted(unknown)}")
    return values
