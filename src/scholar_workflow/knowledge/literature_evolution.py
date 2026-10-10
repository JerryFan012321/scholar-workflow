"""Pure contribution/evolution contract and readable, non-writing preview."""

from __future__ import annotations

import html
import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholar_workflow.knowledge.models import _validate_vault_path

Slug = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=4000, pattern=r"^[^\x00-\x1f\x7f]+$")]
NoveltyType = Annotated[int, Field(strict=True, ge=1, le=4)]
_TRADEOFFS = ("change", "reason", "benefit", "cost", "conditions")
_REPORTED = {"author_statement", "experimental_result", "analysis_inference"}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def _nonblank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("text must not be blank")
        return value


class EvolutionPaper(_Model):
    paper_id: Slug
    source_id: str = Field(pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    object_id: str = Field(min_length=1, max_length=240, pattern=r"^[^\s\x00-\x1f\x7f]+$")
    title: Text
    note_path: str = Field(min_length=4, max_length=512)

    @field_validator("note_path")
    @classmethod
    def _note(cls, value: str) -> str:
        _validate_vault_path(value, suffix=".md")
        if any(char in value for char in "#|[]`<>") or any(
            ord(char) < 32 or ord(char) == 127 for char in value
        ):
            raise ValueError("note_path must be a safe relative Markdown declaration")
        return value


class PdfEvidence(_Model):
    paper_id: Slug
    library_type: Literal["personal", "group"]
    library_id: str = Field(pattern=r"^[1-9][0-9]*$")
    attachment_key: str = Field(pattern=r"^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$")
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    page_index: int = Field(strict=True, ge=0)
    section: Text


class EvolutionStatement(_Model):
    text: Text
    basis: Literal[
        "author_statement", "experimental_result", "analysis_inference", "not_reported", "unverified"
    ]
    evidence: list[PdfEvidence] = Field(max_length=32)

    @model_validator(mode="after")
    def _support(self) -> Self:
        if self.basis in _REPORTED and not self.evidence:
            raise ValueError("reported statements require evidence")
        if self.basis == "not_reported" and self.evidence:
            raise ValueError("not_reported has no supporting evidence")
        return self


class EvolutionContribution(_Model):
    contribution_id: Slug
    paper_id: Slug
    title: Text
    novelty_types: list[NoveltyType] = Field(max_length=4)
    placement: Literal["main", "branch", "local", "pending"]
    parent_id: Slug | None
    classification: EvolutionStatement

    @model_validator(mode="after")
    def _eligibility(self) -> Self:
        types = set(self.novelty_types)
        if len(types) != len(self.novelty_types):
            raise ValueError("novelty types must not repeat")
        if self.placement == "pending":
            if self.parent_id is not None:
                raise ValueError("pending placement has no structural parent")
            return self
        if not types or self.classification.basis not in _REPORTED:
            raise ValueError("nonpending placement requires supported classification")
        if self.placement in {"main", "branch"} and not types <= {1, 2}:
            raise ValueError("only novelty types 1/2 are eligible for main/branch placement")
        if self.placement in {"branch", "local"} and self.parent_id is None:
            raise ValueError("branch/local placement requires a structural parent")
        return self


class EvolutionRelation(_Model):
    relation_id: Slug
    from_id: Slug
    to_id: Slug
    kind: Literal["extends", "alternative", "component", "comparison"]
    change: EvolutionStatement
    reason: EvolutionStatement
    benefit: EvolutionStatement
    cost: EvolutionStatement
    conditions: EvolutionStatement


class LiteratureEvolution(_Model):
    schema_version: Literal[1]
    topic: Text
    corpus_scope: Text
    language: Literal["en", "zh"]
    synthetic: bool
    papers: list[EvolutionPaper] = Field(max_length=512)
    contributions: list[EvolutionContribution] = Field(max_length=2048)
    relations: list[EvolutionRelation] = Field(max_length=4096)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def _references(self) -> Self:
        papers = {paper.paper_id: paper for paper in self.papers}
        nodes = {node.contribution_id: node for node in self.contributions}
        if len(papers) != len(self.papers) or len(nodes) != len(self.contributions):
            raise ValueError("paper and contribution identifiers must be unique")
        if len({(p.source_id, p.object_id) for p in self.papers}) != len(self.papers):
            raise ValueError("reuse one ledger entry for the same qualified paper identity")
        if len({r.relation_id for r in self.relations}) != len(self.relations):
            raise ValueError("relation identifiers must be unique")
        statements = []
        for node in self.contributions:
            if node.paper_id not in papers:
                raise ValueError("unknown contribution paper reference")
            if node.parent_id is not None:
                parent = nodes.get(node.parent_id)
                if parent is None or parent.placement == "pending":
                    raise ValueError("structural parent must exist and not be pending")
                if node.placement == "main" and parent.placement != "main":
                    raise ValueError("a main contribution may only have a main parent")
            visited = set()
            cursor = node
            while cursor is not None:
                if cursor.contribution_id in visited:
                    raise ValueError("structural parent graph must be acyclic")
                visited.add(cursor.contribution_id)
                cursor = nodes.get(cursor.parent_id)
            statements.append(node.classification)
        for relation in self.relations:
            if relation.from_id not in nodes or relation.to_id not in nodes:
                raise ValueError("unknown scientific relation endpoint")
            if relation.from_id == relation.to_id:
                raise ValueError("scientific relations require distinct endpoints")
            statements.extend(getattr(relation, key) for key in _TRADEOFFS)
        if any(pointer.paper_id not in papers for s in statements for pointer in s.evidence):
            raise ValueError("unknown evidence paper reference")
        return self


def validate_evolution(doc: dict) -> dict:
    """Normalize explicit input without reading sources or certifying scientific claims."""
    return LiteratureEvolution.model_validate(doc).model_dump(mode="json")


def _text(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#!|>~])", r"\\\1", html.escape(value, quote=False))


def _diagram_text(value: str) -> str:
    # Encode delimiters before interpolation into a Mermaid quoted node label.
    reserved = '&"<>[]`#|\\'
    return "".join(f"#{ord(char)};" if char in reserved else char for char in value)


_LABELS = {
    "en": {
        "scope": "Corpus scope", "synthetic": "Synthetic example — not real scientific evidence. Source links are synthetic examples, not reader-test targets.",
        "legend": "1: seminal milestone task; 2: seminal pipeline/representation; 3: seminal module; 4: module augmentation of an existing pipeline. These are contribution types, not quality scores.",
        "unverified": "Sources, declared notes and reader behavior have not been verified.",
        "overview": "Placement overview", "membership": "Lines show structural membership only, not scientific inheritance. Scientific relations remain complete below; this is not the final evolution figure.",
        "papers": "Papers", "contributions": "Contributions", "relations": "Relations",
        "note": "Declared note (not checked)", "none": "None declared", "paper": "Paper",
        "novelty": "Novelty types", "main": "Main", "branch": "Major branch", "local": "Local",
        "pending": "Pending", "unclassified": "Unclassified", "parent": "Structural parent", "classification": "Classification basis",
        "author_statement": "Author statement", "experimental_result": "Experimental result",
        "analysis_inference": "Analysis inference", "not_reported": "Not reported (input assertion)",
        "unchecked": "Unverified / not yet analyzed", "page": "physical page",
        "change": "Change", "reason": "Reason", "benefit": "Benefit", "cost": "Cost",
        "conditions": "Conditions", "extends": "Extension", "alternative": "Alternative",
        "component": "Component", "comparison": "Comparison",
    },
    "zh": {
        "scope": "语料范围", "synthetic": "合成示例——不是真实科学证据。来源链接仅是合成格式示例，不用于阅读器实测。",
        "legend": "1：里程碑任务的开创工作；2：新流程／表示的开创工作；3：新模块的开创工作；4：加入模块改进已有流程。类别描述贡献性质，不是质量评分。",
        "unverified": "来源、声明的资料笔记及阅读器行为尚未核验。",
        "overview": "位置归属概览", "membership": "连线只表示结构归属，不表示科学继承。科学关系完整保留在下方；此图不是最终技术演进图。",
        "papers": "论文列表", "contributions": "贡献", "relations": "演进关系",
        "note": "声明的资料笔记（未检查）", "none": "尚未声明", "paper": "论文",
        "novelty": "创新类别", "main": "主线", "branch": "主要支线", "local": "局部",
        "pending": "待定", "unclassified": "未分类", "parent": "结构归属", "classification": "分类依据",
        "author_statement": "作者陈述", "experimental_result": "实验结果",
        "analysis_inference": "分析推断", "not_reported": "未报告（输入者声明）",
        "unchecked": "未核验／尚未分析", "page": "物理页",
        "change": "变更", "reason": "原因", "benefit": "收益", "cost": "代价",
        "conditions": "比较条件", "extends": "扩展", "alternative": "替代方案",
        "component": "组件", "comparison": "比较",
    },
}


def _statement(statement: dict, labels: dict, papers: dict) -> str:
    basis = labels["unchecked" if statement["basis"] == "unverified" else statement["basis"]]
    body = f"{_text(statement['text'])} **({basis})**"
    links = []
    for pointer in statement["evidence"]:
        page = pointer["page_index"] + 1
        library = (
            "library" if pointer["library_type"] == "personal"
            else f"groups/{pointer['library_id']}"
        )
        uri = f"zotero://open-pdf/{library}/items/{pointer['attachment_key']}?page={page}"
        title = _text(papers[pointer["paper_id"]]["title"])
        label = f"{title} · {labels['page']} {page} · {_text(pointer['section'])}"
        links.append(f"[{label}]({uri})")
    return body + (" — " + "; ".join(links) if links else "")


def render_evolution(doc: dict) -> str:
    """Render every contribution/tradeoff; draw membership separately from science."""
    doc = validate_evolution(doc)
    labels = _LABELS[doc["language"]]
    papers = {paper["paper_id"]: paper for paper in doc["papers"]}
    nodes = {node["contribution_id"]: node for node in doc["contributions"]}
    parts = [f"## {_text(doc['topic'])}", f"{labels['scope']}: {_text(doc['corpus_scope'])}"]
    if doc["synthetic"]:
        parts.append(f"> {labels['synthetic']}")
    parts.append(f"> {labels['unverified']}")
    parts.append(labels["legend"])
    parts.extend([f"### {labels['overview']}", labels["membership"]])
    diagram = [
        "```mermaid",
        '%%{init: {"flowchart": {"curve": "step", "nodeSpacing": 20, "rankSpacing": 28, "padding": 8}}}%%',
        "flowchart TD",
        "  classDef main fill:#e4efec,stroke:#376d70,color:#243338;",
        "  classDef branch fill:#f2e8d4,stroke:#94743b,color:#243338;",
        "  classDef local fill:#eceeec,stroke:#59626c,color:#243338;",
    ]
    visible = [node for node in nodes.values() if node["placement"] != "pending"]
    aliases = {node["contribution_id"]: f"n{index}" for index, node in enumerate(visible)}
    for node in visible:
        label = _diagram_text(node["title"] + " · " + "/".join(map(str, node["novelty_types"])))
        diagram.append(f'  {aliases[node["contribution_id"]]}["{label}"]:::{node["placement"]}')
    for node in visible:
        if node["parent_id"] is not None:
            diagram.append(f"  {aliases[node['parent_id']]} --- {aliases[node['contribution_id']]}")
    diagram.append("```")
    parts.append("\n".join(diagram) if visible else labels["none"])
    parts.append(f"### {labels['papers']}")
    if not papers:
        parts.append(labels["none"])
    for paper in papers.values():
        parts.append(f"- **{_text(paper['title'])}** — {labels['note']}: `{paper['note_path']}`")
    parts.append(f"### {labels['contributions']}")
    if not nodes:
        parts.append(labels["none"])
    for node in nodes.values():
        types = "/".join(map(str, node["novelty_types"])) or labels["unclassified"]
        parent = nodes.get(node["parent_id"])
        parts.extend([
            f"#### {_text(node['title'])}",
            f"{labels['paper']}: {_text(papers[node['paper_id']]['title'])}",
            f"{labels['novelty']}: {types} · {labels[node['placement']]}",
            f"{labels['parent']}: {_text(parent['title']) if parent else labels['none']}",
            f"**{labels['classification']}:** {_statement(node['classification'], labels, papers)}",
        ])
    parts.append(f"### {labels['relations']}")
    if not doc["relations"]:
        parts.append(labels["none"])
    for relation in doc["relations"]:
        parts.append(
            f"#### {_text(nodes[relation['from_id']]['title'])} → "
            f"{_text(nodes[relation['to_id']]['title'])} · {labels[relation['kind']]}"
        )
        parts.extend(
            f"**{labels[key]}:** {_statement(relation[key], labels, papers)}" for key in _TRADEOFFS
        )
    return "\n\n".join(parts) + "\n"
