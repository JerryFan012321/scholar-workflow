"""Paper import workflow (Saga: each step retryable, no auto-rollback)."""
from __future__ import annotations
import uuid
from pathlib import Path
from scholar_workflow.models import Resource, ActionPlan, TaskState
from scholar_workflow.approvals import assert_executable
from scholar_workflow.adapters import get_write_adapter
from scholar_workflow.adapters.arxiv import download_pdf, sha256_file
from scholar_workflow.state import StateStore


def run_paper_import(plan: ActionPlan, resources: list[Resource],
                     config, store: StateStore) -> dict:
    assert_executable(plan, resources)
    results = {}
    adapter = get_write_adapter(config)

    for action in plan.actions:
        if action.operation == "skip":
            continue
        res = next((r for r in resources if r.resource_id == action.resource_id), None)
        if res is None:
            continue

        job_id = str(uuid.uuid4())
        store.upsert(job_id, res.resource_id, TaskState.APPROVED, plan_id=plan.plan_id)

        try:
            # Download
            if action.download_url and res.identifiers.arxiv:
                tmp = Path(config.papers_root) / ".tmp"
                pdf_path = download_pdf(res.identifiers.arxiv, tmp)
                sha = sha256_file(pdf_path)
                store.upsert(job_id, res.resource_id, TaskState.DOWNLOADED,
                             artifacts={"tmp_path": str(pdf_path), "sha256": sha})

            # Zotero upsert
            idempotency_key = f"{plan.plan_id}:{res.resource_id}:zotero"
            zr = adapter.upsert_paper(
                _build_zotero_payload(res, action, str(pdf_path)),
                idempotency_key,
            )
            store.upsert(job_id, res.resource_id, TaskState.ZOTERO_SYNCED,
                         artifacts={"item_key": zr.item_key, "final_path": zr.final_path})

            results[res.resource_id] = {
                "status": "completed",
                "item_key": zr.item_key,
                "attachment_key": zr.attachment_key,
                "final_path": zr.final_path,
            }
            store.upsert(job_id, res.resource_id, TaskState.COMPLETED)

        except Exception as exc:
            store.upsert(job_id, res.resource_id, TaskState.ZOTERO_FAILED,
                         artifacts={"error": str(exc)})
            results[res.resource_id] = {"status": "failed", "error": str(exc)}

    return results


def _build_zotero_payload(res: Resource, action, pdf_path: str) -> dict:
    return {
        "title": res.title,
        "authors": res.authors,
        "doi": res.identifiers.doi,
        "arxiv_id": res.identifiers.arxiv,
        "year": res.year,
        "tags": [],
        "collection_key": action.zotero_collection_key or "",
        "attachment": {"mode": "linked_file", "absolute_path": pdf_path},
    }
