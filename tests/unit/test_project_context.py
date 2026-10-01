"""Prepared synthetic project-context checks; no real project or provider access."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholar_workflow.project.context import (
    ProjectContext,
    ProjectContextError,
    build_project_overview,
    load_project_context,
    render_project_overview,
)
from scholar_workflow.project.layout import (
    ProjectLayoutError,
    is_project_id,
    load_project_identity,
    load_project_layout,
    validate_project_identity,
    validate_project_layout,
)

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"


def _layout() -> dict:
    return {
        "schema_version": 2, "project_id": PROJECT_ID, "language": "python",
        "package": None, "source_profile": None, "addons": [],
    }


def _entry(entry_id: str = "reader", path: str = "src/reader.py", **extra) -> dict:
    return {
        "entry_id": entry_id, "kind": "code", "title": "Reader implementation",
        "purpose": "Implements the evaluated input conversion.",
        "ref": {"kind": "project-file", "relative_path": path}, **extra,
    }


def _context(entries: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1, "project_id": PROJECT_ID,
        "title": "Synthetic reconstruction project",
        "summary": "Selected implementation, sources, and outcomes for one project.",
        "entries": entries if entries is not None else [_entry()],
    }


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "project-layout.json").write_text(json.dumps(_layout()), encoding="utf-8")
    (root / "project-context.json").write_text(json.dumps(_context()), encoding="utf-8")
    (root / "src").mkdir()
    (root / "src/reader.py").write_text("# Synthetic fixture only\n", encoding="utf-8")
    return root


def test_read_only_load_and_render(project: Path) -> None:
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
    context = load_project_context(project)
    overview = build_project_overview(project, context)
    markdown = render_project_overview(overview)
    assert overview.entries[0].state == "available"
    assert "Implements the evaluated input conversion" in markdown
    assert "Available locally (path checked only)" in markdown
    assert "[Reader implementation](src/reader.py)" in markdown
    assert PROJECT_ID not in markdown and str(project) not in markdown
    assert before == {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
    assert overview.model_dump(mode="json")["project_id"] == PROJECT_ID


def test_no_undeclared_discovery(project: Path) -> None:
    (project / "undocumented.txt").write_text("not selected", encoding="utf-8")
    overview = build_project_overview(project)
    assert len(overview.entries) == 1
    assert "undocumented" not in render_project_overview(overview)


def test_missing_path_is_diagnostic_not_discarded(project: Path) -> None:
    context = ProjectContext.model_validate(_context([_entry(path="results/missing.csv")]))
    overview = build_project_overview(project, context)
    assert overview.entries[0].state == "missing"
    assert "Missing" in render_project_overview(overview)
    assert "results/missing.csv" not in render_project_overview(overview)


def test_directory_reference_is_read_only_available(project: Path) -> None:
    context = ProjectContext.model_validate(_context([_entry(path="src")]))
    assert build_project_overview(project, context).entries[0].state == "available"


def test_unverified_commit_does_not_claim_version_availability(project: Path) -> None:
    entry = _entry()
    entry["ref"]["commit"] = "a" * 40
    overview = build_project_overview(project, ProjectContext.model_validate(_context([entry])))
    assert overview.entries[0].state == "unverified"
    assert "declared commit was not verified" in render_project_overview(overview)
    assert "a" * 40 not in render_project_overview(overview)


@pytest.mark.parametrize("provider,uri", [
    ("zotero", "zotero://open-pdf/library/items/ABCD2345?page=4"),
    ("obsidian", "obsidian://open?vault=test&file=Research%2Fpaper.md"),
    ("obsidian", None),
    ("zotero", "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCD2345"),
    ("zotero", "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCD2345&navigation=%7B%22pageIndex%22%3A3%7D"),
    ("zotero", "obsidian://zotflow?vault=test&type=open-annotation&libraryID=1&key=ABCD2345"),
])
def test_external_resource_remains_unverified(project: Path, provider: str, uri: str | None) -> None:
    entry = _entry(kind="paper", ref={
        "kind": "external-resource", "provider": provider,
        "resource_id": "provider-owned-example", "uri": uri,
    })
    overview = build_project_overview(project, ProjectContext.model_validate(_context([entry])))
    assert overview.entries[0].state == "unverified"
    markdown = render_project_overview(overview)
    assert "External object was not queried" in markdown
    assert "provider-owned-example" not in markdown


@pytest.mark.parametrize("path", ["/outside", "../outside", "src/../outside", "./src", "src//x", "src\\x", "src/"])
def test_unsafe_relative_reference_is_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="safe POSIX relative"):
        ProjectContext.model_validate(_context([_entry(path=path)]))


def test_local_symlink_and_symlink_ancestor_are_not_followed(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not read", encoding="utf-8")
    (project / "outside-link").symlink_to(outside, target_is_directory=True)
    (project / "secret-link").symlink_to(outside / "secret.txt")
    context = ProjectContext.model_validate(_context([
        _entry("ancestor", "outside-link/secret.txt"), _entry("leaf", "secret-link"),
    ]))
    overview = build_project_overview(project, context)
    assert [entry.state for entry in overview.entries] == ["unsafe", "unsafe"]
    assert "not read" not in render_project_overview(overview)


@pytest.mark.parametrize("filename", ["project-context.json", "project-layout.json"])
def test_declaration_symlink_rejected(project: Path, tmp_path: Path, filename: str) -> None:
    outside = tmp_path / "external-declaration.json"
    source = project / filename
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(ProjectContextError, match="unsafe"):
        load_project_context(project)


def test_project_root_symlink_rejected(project: Path, tmp_path: Path) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(project, target_is_directory=True)
    with pytest.raises(ProjectContextError, match="symlink"):
        load_project_context(alias)


def test_context_identity_mismatch_rejected(project: Path) -> None:
    payload = _context()
    payload["project_id"] = OTHER_ID
    (project / "project-context.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectContextError, match="identity does not match"):
        load_project_context(project)
    with pytest.raises(ProjectContextError, match="identity does not match"):
        build_project_overview(project, ProjectContext.model_validate(payload))


def test_duplicate_entry_id_rejected() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        ProjectContext.model_validate(_context([_entry(), _entry(path="README.md")]))


@pytest.mark.parametrize("uri", [
    "https://example.org/paper", "http://127.0.0.1:23128/open/paper/ABCD2345",
    "obsidian://open?vault=test", "zotero://user:password@open-pdf/x", "zotero://open-pdf/a b",
])
def test_external_uri_scheme_and_credential_rejected(uri: str) -> None:
    entry = _entry(ref={
        "kind": "external-resource", "provider": "zotero", "resource_id": "ABCD2345", "uri": uri,
    })
    with pytest.raises(ValueError):
        ProjectContext.model_validate(_context([entry]))


@pytest.mark.parametrize("provider,uri", [
    ("obsidian", "obsidian://advanced-uri?vault=test&commandid=delete-file"),
    ("obsidian", "obsidian://new?vault=test&file=note&content=overwrite"),
    ("obsidian", "obsidian://open?vault=test&file=note&commandid=anything"),
    ("obsidian", "obsidian://open?vault=test&file=../outside"),
    ("obsidian", "obsidian://open?vault=test&file=note&file=other"),
    ("zotero", "zotero://open-pdf/library/items/ABCD2345?url=https%3A%2F%2Fexample.org"),
    ("zotero", "zotero://open-pdf/library/items/ABCD2345?page=1&page=2"),
    ("zotero", "obsidian://zotflow?vault=test&type=delete-item&libraryID=1&key=ABCD2345"),
    ("zotero", "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCD2345&command=run"),
    ("zotero", "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCD2345&navigation=%7B%22url%22%3A%22https%3A%2F%2Fexample.org%22%7D"),
])
def test_non_reader_uri_and_query_extensions_rejected(provider: str, uri: str) -> None:
    entry = _entry(ref={
        "kind": "external-resource", "provider": provider, "resource_id": "declared", "uri": uri,
    })
    with pytest.raises(ValueError):
        ProjectContext.model_validate(_context([entry]))


def test_chinese_overview_labels_and_diagnostics_are_consistent(project: Path) -> None:
    payload = _context([
        _entry(title="数据读取实现", purpose="将输入转换成实验需要的格式"),
        _entry("missing", "results/missing.csv", kind="result", title="比较结果", purpose="比较两个方法"),
        _entry("paper", kind="paper", title="来源论文", purpose="解释基线方法", ref={
            "kind": "external-resource", "provider": "zotero", "resource_id": "ABCD2345",
            "uri": "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCD2345",
        }),
    ])
    payload.update(language="zh", title="合成重建项目", summary="将实现、论文与实验结果组织在一起")
    overview = build_project_overview(project, ProjectContext.model_validate(payload))
    markdown = render_project_overview(overview)
    assert overview.language == "zh"
    assert "## 代码" in markdown and "## 论文" in markdown and "## 成果" in markdown
    assert "用途:" in markdown and "状态:" in markdown
    assert "未查询外部对象" in markdown and "本地可定位" in markdown
    assert "Purpose:" not in markdown and "External object" not in markdown


def test_supplied_context_layout_failure_has_context_error(project: Path) -> None:
    context = ProjectContext.model_validate(_context())
    (project / "project-layout.json").unlink()
    with pytest.raises(ProjectContextError, match="missing or unsafe"):
        build_project_overview(project, context)


def test_duplicate_json_key_rejected(project: Path) -> None:
    (project / "project-context.json").write_text(
        '{"schema_version":1,"schema_version":1}', encoding="utf-8",
    )
    with pytest.raises(ProjectContextError, match="duplicate JSON"):
        load_project_context(project)


def test_empty_material_list_has_human_explanation(project: Path) -> None:
    overview = build_project_overview(project, ProjectContext.model_validate(_context([])))
    assert "No project material has been declared yet" in render_project_overview(overview)


def test_identity_guard_does_not_require_complete_layout(project: Path) -> None:
    payload = {"schema_version": 2, "project_id": PROJECT_ID}
    assert validate_project_identity(payload) == PROJECT_ID
    (project / "project-layout.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_project_identity(project) == PROJECT_ID
    with pytest.raises(ValueError):
        load_project_layout(project)


@pytest.mark.parametrize("identifier", [
    None, "invalid", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", "11111111-1111-1111-8111-111111111111",
])
def test_invalid_identity_rejected(identifier: object) -> None:
    assert not is_project_id(identifier)
    with pytest.raises(ProjectLayoutError, match="canonical UUIDv4"):
        validate_project_identity({"schema_version": 2, "project_id": identifier})


def test_layout_catalog_preserves_profile_selection_semantics() -> None:
    payload = _layout()
    payload.update(package="sample", source_profile={"id": "python-package", "version": 1})
    catalog = {"profiles": {"python-package": {"version": 1}}, "addons": {}}
    layout = validate_project_layout(payload, catalog=catalog)
    assert layout.source_profile.id == "python-package"
    with pytest.raises(ProjectLayoutError, match="unknown source profile"):
        validate_project_layout(payload, catalog={"profiles": {}, "addons": {}})


def test_layout_addons_must_remain_sorted_unique() -> None:
    payload = _layout()
    payload.update(package="sample", addons=[{"id": "z", "version": 1}, {"id": "a", "version": 1}])
    with pytest.raises(ValueError, match="unique and sorted"):
        validate_project_layout(payload)
