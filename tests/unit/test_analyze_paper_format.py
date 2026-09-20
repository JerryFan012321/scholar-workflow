from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "analyze-paper"
FORMAT = SKILL_DIR / "references" / "analysis-format.md"


def _format_text() -> str:
    return FORMAT.read_text(encoding="utf-8")


def _canonical_tree() -> str:
    after_heading = _format_text().split("## Canonical content tree", 1)[1]
    return after_heading.split("```text", 1)[1].split("```", 1)[0]


def _markdown_template() -> str:
    return _format_text().split("```markdown", 1)[1].split("```", 1)[0]


def test_analyze_paper_uses_one_canonical_format_reference() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "references/analysis-format.md" in skill
    assert "analysis-note-format.md" not in skill
    assert "analysis-canvas-format.md" not in skill
    assert FORMAT.is_file()
    assert not (SKILL_DIR / "references" / "analysis-note-format.md").exists()
    assert not (SKILL_DIR / "references" / "analysis-canvas-format.md").exists()


def test_canonical_tree_pins_reference_image_branches_and_fields() -> None:
    tree = _canonical_tree()
    branches = [
        "├── Abstract",
        "├── Introduction",
        "├── Method",
        "├── Experiments",
        "└── Limitation",
    ]
    positions = [tree.index(branch) for branch in branches]
    assert positions == sorted(positions)

    required_fields = [
        "Technical challenge for previous methods",
        "Key insight / motivation",
        "Technical contributions",
        "Task and application",
        "Previous method",
        "Failure cases / limitation",
        "Technical reason",
        "Our pipeline",
        "为了解决什么问题",
        "具体怎么做",
        "Advantage / insight",
        "Demos / applications",
        "Overview",
        "方法步骤",
        "Pipeline module N",
        "为什么有效",
        "Technical advantage",
        "Comparison experiment N",
        "Baseline / metric",
        "关键结果",
        "Ablation study N",
        "性能影响",
        "可归因结论",
        "Limitation N",
        "成因",
        "影响范围",
        "作者明确陈述 / 分析推断",
    ]
    for field in required_fields:
        assert field in tree


def test_markdown_canvas_projection_and_source_gap_contract_are_explicit() -> None:
    text = _format_text()
    flat_text = " ".join(text.split())

    for heading in [
        "## Abstract｜结论速览",
        "## Introduction｜问题背景与解法",
        "## Method｜方法",
        "## Experiments｜实验",
        "## Limitation｜局限",
    ]:
        assert heading in text

    for state in [
        "作者明确陈述",
        "分析推断",
        "论文未报告",
        "当前正文通道无法核实",
        "不适用",
    ]:
        assert state in text

    assert "<field>: <value> 〔作者明确陈述 · <anchor>〕" in text
    assert "<value> 〔<evidence-or-availability-state>〕" in text
    assert 'exact top-level shape\n`{"nodes": [...], "edges": [...]}`' in text
    assert "SHA-256" in text
    assert "focused updates modify only their" in text
    assert "user-created nodes/edges" in text
    assert "must not add a claim that the note does not contain" in flat_text

    exempt_prefixes = ("- **Evidence：**", "- **归属：**", "- **方法步骤：**")
    for line in _markdown_template().splitlines():
        if line.startswith("- **") and not line.startswith(exempt_prefixes):
            assert "〔<evidence-or-availability-state>〕" in line
        if line.lstrip().startswith("1. <step>"):
            assert "〔<evidence-or-availability-state>〕" in line


def test_generated_field_baseline_preserves_human_edits() -> None:
    text = _format_text()

    assert "sw-analysis-field" in text
    assert "Markdown heading (root, fixed structural, or repeated)" in text
    assert "base_sha256" in text
    assert '"\\n".join(line.rstrip(" \\t") for line in visible_fragment.splitlines())' in text
    assert 'normalized.encode("utf-8")' in text
    assert "do not apply Unicode normalization" in text
    assert "current visible-value hash equals `base_sha256`" in text
    assert "When the hashes differ, the field is human-edited" in text
    assert "Preserve it verbatim and report its canonical" in text
    assert "form one cross-artifact update" in text
    assert "change neither" in text
    assert "the `#2` fallback is not an ownership bypass" in text
    assert "A Canvas node without a generated field marker is user-created" in text
    assert "all other edges are" in text
    assert "user-created" in text
