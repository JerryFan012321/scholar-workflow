from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "analyze-paper"
FORMAT = SKILL_DIR / "references" / "analysis-format.md"
BATCH = SKILL_DIR / "references" / "analysis-batch.md"


def _format_text() -> str:
    return FORMAT.read_text(encoding="utf-8")


def test_analyze_paper_references_versioned_format_and_conditional_batch_contract() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "references/analysis-format.md" in skill
    assert "references/analysis-batch.md" in skill
    assert "load only for multi-paper analysis" in skill
    assert FORMAT.is_file()
    assert BATCH.is_file()


def test_format_uses_five_observable_roles_and_declared_profiles() -> None:
    text = _format_text()

    assert "**Task, Input, Workflow, Output, Boundary**" in text
    assert "`whole` covers all five roles" in text
    assert "`focused` names a non-empty subset" in text
    assert "an output interface, not a reading sequence" in text
    assert "${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json" in text


def test_evidence_is_inline_and_canvas_links_back_to_markdown() -> None:
    text = _format_text()

    for state in (
        "作者明确陈述",
        "分析推断",
        "论文未报告",
        "当前正文通道无法核实",
        "不适用",
    ):
        assert state in text
    assert "standalone Evidence section" in text
    assert "#^claim-<claim-id>|正文" in text
    assert "same Markdown block and Canvas node" in text


def test_canvas_contract_is_readable_bounded_and_does_not_invent_pipeline_nodes() -> None:
    text = _format_text()

    assert "at most 40 semantic nodes" in text
    assert "at least 360 px wide and 140 px high" in text
    assert "Workflow steps form one visible ordered flow" in text
    assert "`对应挑战`, `对应贡献`" in text
    assert "exact top-level shape:" in text
    assert '{"nodes": [], "edges": []}' in text


def test_batch_contract_pins_one_repair_cleanup_and_per_paper_isolation() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert "one targeted repair" in text
    assert "never exceeds one" in text
    assert "failing item never rolls back a conformant sibling" in text
    assert "never deletes or changes a Zotero item" in text
    assert "Path escape, symlink traversal" in text
