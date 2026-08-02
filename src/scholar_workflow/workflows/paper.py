"""Paper import workflow: download PDFs to the inbox for manual Zotero import.

Zotero has no local write API, so the automated workflow ends at "PDF in the
inbox". The user imports into Zotero by hand; Zotero (and its storage) is the
authoritative library. Each step is retryable with no auto-rollback (Saga).
"""
from __future__ import annotations
import uuid
from pathlib import Path
from scholar_workflow.models import Resource, ActionPlan, TaskState
from scholar_workflow.adapters.arxiv import download_pdf, sha256_file
from scholar_workflow.state import StateStore


def run_paper_import(plan: ActionPlan, resources: list[Resource],
                     config, store: StateStore, download=None) -> dict:
    """Download papers into the inbox. `download` is injectable for tests."""
    if download is None:
        download = download_pdf
    inbox = Path(config.paper_inbox)
    results: dict = {}

    for action in plan.actions:
        if action.operation in ("skip", "conflict"):
            continue
        res = next((r for r in resources if r.resource_id == action.resource_id), None)
        if res is None:
            continue

        job_id = str(uuid.uuid4())
        store.upsert(job_id, res.resource_id, TaskState.APPROVED, plan_id=plan.plan_id)

        # arXiv is the only PDF source in phase 1; other inputs carry no PDF.
        if not res.identifiers.arxiv:
            store.upsert(job_id, res.resource_id, TaskState.NO_ARXIV_PDF)
            results[res.resource_id] = {
                "status": "no_pdf",
                "reason": "no arXiv PDF source; add to Zotero manually",
            }
            continue

        try:
            pdf_path = download(res.identifiers.arxiv, inbox)
            sha = sha256_file(pdf_path)
            store.upsert(job_id, res.resource_id, TaskState.DOWNLOADED,
                         artifacts={"inbox_path": str(pdf_path), "sha256": sha})
            results[res.resource_id] = {
                "status": "downloaded",
                "inbox_path": str(pdf_path),
                "sha256": sha,
            }
        except Exception as exc:
            store.upsert(job_id, res.resource_id, TaskState.DOWNLOAD_FAILED,
                         artifacts={"error": str(exc)})
            results[res.resource_id] = {"status": "failed", "error": str(exc)}

    return results
