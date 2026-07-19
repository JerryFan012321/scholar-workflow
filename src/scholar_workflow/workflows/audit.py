"""Cross-system consistency audit workflow."""
from __future__ import annotations
from pathlib import Path
from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter


def audit_papers_root(papers_root: Path, zotero: ZoteroLocalAdapter) -> list[dict]:
    """Find PDFs in papers_root with no matching Zotero attachment."""
    issues: list[dict] = []
    for pdf in papers_root.rglob("*.pdf"):
        issues.append({
            "severity": "warning",
            "type": "unverified_pdf",
            "path": str(pdf.relative_to(papers_root)),
            "message": "PDF exists but Zotero cross-check not yet implemented",
        })
    return issues


def audit_obsidian_index(index_path: Path, vault_root: Path,
                         zotero: ZoteroLocalAdapter) -> list[dict]:
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
