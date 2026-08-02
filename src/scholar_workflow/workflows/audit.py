"""Cross-system consistency audit workflow."""
from __future__ import annotations
from pathlib import Path


def audit_obsidian_index(index_path: Path, vault_root: Path) -> list[dict]:
    """Check that index entries resolve to valid Zotero keys and PDF paths."""
    # Full implementation in Phase 6
    return []


def compile_report(issues: list[dict]) -> dict:
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {
        "summary": {"errors": len(errors), "warnings": len(warnings),
                    "info": len(issues) - len(errors) - len(warnings)},
        "issues": issues,
    }
