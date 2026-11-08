"""Explicit, bounded platform refresh separate from recommendation submissions."""
from __future__ import annotations

import threading

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.metrics import collect_metrics

_ACTIVE = threading.BoundedSemaphore(4)


def refresh_candidate_metrics(store, candidate_id, expected_revision=None, *, client=None):
    row = store.get_candidate(candidate_id)
    revision = row["revision"] if expected_revision is None else expected_revision
    if type(revision) is not int or revision != row["revision"]:
        raise ResearchError("Recommendation changed; reload before refreshing metrics.", 5)
    if not row["metric_targets"]:
        return row
    if not _ACTIVE.acquire(blocking=False):
        raise ResearchError("Platform refresh is busy; retry after current requests finish.", 3)
    try:
        result = collect_metrics(row["resource"], client=client)
        return store.record_metric_refresh(candidate_id, revision, result)
    finally:
        _ACTIVE.release()
