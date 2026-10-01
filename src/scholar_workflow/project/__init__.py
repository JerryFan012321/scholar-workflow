"""Project contracts; experiment exports load only when requested."""

from importlib import import_module

__all__ = [
    "ExperimentError",
    "create_attempt",
    "create_run",
    "finalize_attempt",
    "promote_artifact",
    "rebuild_index",
    "record_manifest_only_artifact",
    "register_target",
    "start_attempt",
    "validate_project",
]


def __getattr__(name: str):
    """Keep the public experiment API without loading it for layout-only callers."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module("scholar_workflow.project.experiments"), name)
