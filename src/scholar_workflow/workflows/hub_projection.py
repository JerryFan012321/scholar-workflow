"""Project structured literature data into the canonical HubCatalog.

This adapter consumes the same validated payload that renders the readable
Obsidian documents.  It never parses their Markdown bodies.  Zotero-backed
refresh can replace bibliography fields later without changing relationships.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    CatalogDiagnostic,
    HubArtifact,
    HubCatalog,
    HubResource,
    HubTopic,
    ProjectionLinks,
    SourceStatus,
    TreeKind,
    ZoteroLink,
)
from scholar_workflow.models import Identifiers, ResourceKind
from scholar_workflow.workflows.novelty_tree import plan_novelty_tree, plan_paperlist


def _tree_resource_ids(node: dict) -> set[str]:
    result = set(node.get("papers") or [])
    for child in node.get("children") or []:
        result.update(_tree_resource_ids(child))
    return result


def _paper_hub_id(topic_id: str, resource_id: str) -> str:
    digest = hashlib.sha256(resource_id.encode("utf-8")).hexdigest()[:16]
    return f"paper-hub:{topic_id}:{digest}"


def _generated_at(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def build_topic_catalog_patch(
    doc: dict,
    root: str,
    port: int,
    filename: str,
    *,
    paperlist_only: bool,
) -> HubCatalog:
    """Build one topic projection without reading free-form Markdown."""
    plan = (
        plan_paperlist(doc, root, port, filename)
        if paperlist_only
        else plan_novelty_tree(doc, root, port, filename)
    )[0]
    metadata = plan["frontmatter"]
    topic_id = metadata["sw_topic_id"]
    document_artifact = HubArtifact(
        artifact_id=metadata["sw_catalog_id"],
        kind=ArtifactKind(metadata["sw_kind"]),
        format=ArtifactFormat.MARKDOWN,
        vault_path=plan["path"],
        topic_id=topic_id,
        tree_kind=(TreeKind(metadata["sw_tree_kind"])
                   if metadata.get("sw_tree_kind") else None),
        revision=metadata["sw_revision"],
    )
    represented = (
        {str(row["resource_id"]) for row in doc.get("paper_list", [])}
        if paperlist_only
        else _tree_resource_ids(doc.get("tree") or {})
    )
    resources: list[HubResource] = []
    artifacts: list[HubArtifact] = [document_artifact]
    for entry in doc.get("paper_list", []):
        resource_id = str(entry["resource_id"])
        artifact_ids: list[str] = []
        if resource_id in represented:
            artifact_ids.append(document_artifact.artifact_id)
        asset_note = entry.get("asset_note")
        if asset_note:
            paper_hub_id = _paper_hub_id(topic_id, resource_id)
            artifacts.append(
                HubArtifact(
                    artifact_id=paper_hub_id,
                    kind=ArtifactKind.PAPER_HUB,
                    format=ArtifactFormat.MARKDOWN,
                    vault_path=str(asset_note),
                    resource_id=resource_id,
                    topic_id=topic_id,
                    parent_id=resource_id,
                )
            )
            artifact_ids.append(paper_hub_id)
        resources.append(
            HubResource(
                resource_id=resource_id,
                kind=ResourceKind.PAPER,
                title=entry.get("title"),
                authors=list(entry.get("authors") or []),
                year=entry.get("year"),
                venue=entry.get("venue"),
                importance=entry.get("importance"),
                identifiers=Identifiers(
                    doi=entry.get("doi"),
                    arxiv=entry.get("arxiv"),
                ),
                zotero=ZoteroLink(
                    item_key=entry.get("zotero_key"),
                    attachment_key=entry.get("attachment_key"),
                ),
                projections=ProjectionLinks(),
                topic_ids=[topic_id],
                artifact_ids=artifact_ids,
            )
        )
    topic_name = str(doc.get("topic") or (doc.get("tree") or {}).get("name") or root)
    topic = HubTopic(
        topic_id=topic_id,
        name=topic_name,
        resource_ids=[resource.resource_id for resource in resources],
        artifact_ids=[artifact.artifact_id for artifact in artifacts],
    )
    return HubCatalog(
        generated_at=_generated_at(doc.get("generated_at")),
        sources=[
            SourceStatus(
                source="literature-tree-payload",
                available=True,
                detail="structured projection input; not parsed from Markdown",
            )
        ],
        resources=resources,
        topics=[topic],
        artifacts=artifacts,
        diagnostics=[
            CatalogDiagnostic(
                level="info",
                code="bibliography-awaits-zotero-refresh",
                message=(
                    "Bibliography came from structured projection input; "
                    "Zotero remains authoritative."
                ),
                entity_id=topic_id,
            )
        ],
    )


def _ordered_union(first: list[str], second: list[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))


def merge_catalog_patch(base: HubCatalog, patch: HubCatalog) -> HubCatalog:
    """Merge projection identities while supporting one paper in many topics."""
    artifact_by_id = {row.artifact_id: row for row in base.artifacts}
    artifact_by_id.update({row.artifact_id: row for row in patch.artifacts})
    asset_by_id = {row.asset_id: row for row in base.assets}
    asset_by_id.update({row.asset_id: row for row in patch.assets})

    resource_by_id = {row.resource_id: row for row in base.resources}
    for incoming in patch.resources:
        current = resource_by_id.get(incoming.resource_id)
        if current is None:
            resource_by_id[incoming.resource_id] = incoming
            continue
        data = incoming.model_dump()
        data["topic_ids"] = _ordered_union(current.topic_ids, incoming.topic_ids)
        data["artifact_ids"] = _ordered_union(current.artifact_ids, incoming.artifact_ids)
        current_notion = current.projections.notion_page_id
        if incoming.projections.notion_page_id is None and current_notion is not None:
            data["projections"]["notion_page_id"] = current_notion
        resource_by_id[incoming.resource_id] = HubResource.model_validate(data)

    topic_by_id = {row.topic_id: row for row in base.topics}
    for incoming in patch.topics:
        current = topic_by_id.get(incoming.topic_id)
        if current is None:
            topic_by_id[incoming.topic_id] = incoming
            continue
        data = incoming.model_dump()
        data["artifact_ids"] = _ordered_union(current.artifact_ids, incoming.artifact_ids)
        topic_by_id[incoming.topic_id] = HubTopic.model_validate(data)

    sources = {row.source: row for row in base.sources}
    sources.update({row.source: row for row in patch.sources})
    diagnostics = {
        (row.level, row.code, row.entity_id): row
        for row in [*base.diagnostics, *patch.diagnostics]
    }
    return HubCatalog(
        generated_at=max(base.generated_at, patch.generated_at),
        sources=list(sources.values()),
        resources=list(resource_by_id.values()),
        topics=list(topic_by_id.values()),
        artifacts=list(artifact_by_id.values()),
        assets=list(asset_by_id.values()),
        diagnostics=list(diagnostics.values()),
    )
