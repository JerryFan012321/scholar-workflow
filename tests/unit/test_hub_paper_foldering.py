"""The batch folder planner is review-only and binds exact old file identities."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_workflow.hub.fields import FieldDefinition, FieldNavigationGroup
from scholar_workflow.hub.paper_foldering import (
    PaperFolderingError,
    PaperFolderRelocation,
    plan_paper_foldering,
)

FIELD_ID = "b71ad01c-cb49-49e2-a908-d05302d1badd"
OLD_LINK = "http://127.0.0.1:23128/open/paper/ABCD2345"
NEW_LINK = "zotero://open-pdf/library/items/ABCD2345"


def _fixture(tmp_path: Path) -> tuple[Path, FieldDefinition]:
    vault = tmp_path / "Vault"
    field_root = vault / "World Models"
    assets = field_root / "paper_assets"
    assets.mkdir(parents=True)
    (assets / "One.md").write_text("# One\n\nSource text.\n", encoding="utf-8")
    (assets / "Two.md").write_text("# Two\n\nSource text.\n", encoding="utf-8")
    (field_root / "00-Index.md").write_text(
        f"[One](paper_assets/One.md)\n[Two](paper_assets/Two.md)\n"
        f"[PDF]({OLD_LINK})\n",
        encoding="utf-8",
    )
    field = FieldDefinition(
        field_id=FIELD_ID,
        title="World Models",
        relative_root="World Models",
        home="00-Index.md",
        navigation=[
            FieldNavigationGroup(
                label="Papers",
                items=[
                    "paper_assets/One.md",
                    "paper_assets/Two.md",
                    "paper_assets/Missing-1.md",
                    "paper_assets/Missing-2.md",
                    "paper_assets/Missing-3.md",
                    "paper_assets/Missing-4.md",
                ],
            )
        ],
    )
    return vault, field


def _relocations() -> list[PaperFolderRelocation]:
    return [
        PaperFolderRelocation(
            "paper_assets/One.md", "paper:one", "resources/papers/one/One.md"
        ),
        PaperFolderRelocation(
            "paper_assets/Two.md", "paper:two", "resources/papers/two/Two.md"
        ),
    ]


def _verified_resolver(key: str) -> str:
    assert key == "ABCD2345"
    return NEW_LINK


def test_batch_plan_is_read_only_and_preserves_missing_navigation(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*.md")
    }
    plan = plan_paper_foldering(
        vault_root=vault,
        field=field,
        relocations=_relocations(),
        legacy_link_resolver=_verified_resolver,
    )
    assert plan.read_only is True
    assert plan.recovery_is_verified_backup is False
    assert len(plan.moves) == 2
    assert plan.moves[0].old_path == "World Models/paper_assets/One.md"
    assert plan.moves[0].new_path == "World Models/resources/papers/one/One.md"
    assert plan.moves[0].before_inode > 0
    assert plan.moves[0].before_sha256.startswith("sha256:")
    assert plan.moves[0].destination_absent is True
    assert len(plan.navigation_changes) == 2
    assert plan.proposed_field.navigation[0].items[:2] == [
        "resources/papers/one/One.md",
        "resources/papers/two/Two.md",
    ]
    assert plan.missing_navigation_targets == tuple(
        f"paper_assets/Missing-{index}.md" for index in range(1, 5)
    )
    assert plan.proposed_field.navigation[0].items[2:] == list(plan.missing_navigation_targets)
    assert plan.legacy_link_count == 1
    index = next(row for row in plan.documents if row.source_path.endswith("00-Index.md"))
    assert b"resources/papers/one/One.md" in index.after_bytes
    assert NEW_LINK.encode() in index.after_bytes
    assert OLD_LINK.encode() not in index.after_bytes
    assert not (vault / "World Models/resources").exists()
    assert {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*.md")
    } == before


def test_home_reference_is_substituted_only_when_explicitly_moved(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    field.home = "paper_assets/One.md"
    plan = plan_paper_foldering(
        vault_root=vault, field=field,
        relocations=_relocations(), legacy_link_resolver=_verified_resolver,
    )
    assert plan.proposed_field.home == "resources/papers/one/One.md"
    assert any(row.location == "home" for row in plan.navigation_changes)


@pytest.mark.parametrize(
    "other",
    [
        PaperFolderRelocation("paper_assets/Two.md", "paper:one", "resources/papers/two/Two.md"),
        PaperFolderRelocation("paper_assets/Two.md", "paper:two", "resources/papers/one/Two.md"),
        PaperFolderRelocation("paper_assets/Two.md", "paper:two", "resources/papers/one/One.md"),
    ],
)
def test_duplicate_resource_segment_or_destination_rejected(
    tmp_path: Path, other: PaperFolderRelocation,
) -> None:
    vault, field = _fixture(tmp_path)
    with pytest.raises(PaperFolderingError, match="duplicate"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=[_relocations()[0], other],
            legacy_link_resolver=_verified_resolver,
        )


@pytest.mark.parametrize("unsafe", ["../Outside.md", "/tmp/Outside.md", "paper_assets/./One.md"])
def test_unsafe_or_noncanonical_source_rejected(tmp_path: Path, unsafe: str) -> None:
    vault, field = _fixture(tmp_path)
    with pytest.raises(PaperFolderingError):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=[PaperFolderRelocation(
                unsafe, "paper:one", "resources/papers/one/One.md"
            )],
            legacy_link_resolver=_verified_resolver,
        )


def test_symlink_destination_parent_rejected(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    outside = tmp_path / "Outside"
    outside.mkdir()
    (vault / "World Models/resources").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PaperFolderingError, match="symbolic-link|unsafe"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=[_relocations()[0]],
            legacy_link_resolver=_verified_resolver,
        )
    assert not list(outside.iterdir())


def test_destination_collision_rejected(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    destination = vault / "World Models/resources/papers/one/One.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing", encoding="utf-8")
    with pytest.raises(PaperFolderingError, match="already exists"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=[_relocations()[0]],
            legacy_link_resolver=_verified_resolver,
        )
    assert destination.read_text(encoding="utf-8") == "existing"


def test_legacy_links_require_separately_verified_resolver(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    with pytest.raises(PaperFolderingError, match="validated resolver"):
        plan_paper_foldering(vault_root=vault, field=field, relocations=_relocations())
    with pytest.raises(PaperFolderingError, match="unapproved URI"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=_relocations(), legacy_link_resolver=lambda _key: "https://example.org",
        )
    with pytest.raises(PaperFolderingError, match="cannot be verified"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=_relocations(),
            legacy_link_resolver=lambda _key: (_ for _ in ()).throw(ValueError("missing")),
        )


def test_unreviewed_flat_paper_note_blocks_batch(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    (vault / "World Models/paper_assets/Third.MD").write_text("unreviewed", encoding="utf-8")
    with pytest.raises(PaperFolderingError, match="inventory is incomplete.*Third.MD"):
        plan_paper_foldering(
            vault_root=vault,
            field=field,
            relocations=_relocations(),
            legacy_link_resolver=_verified_resolver,
        )


def test_bulk_legacy_link_count_is_exact(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    index = vault / "World Models/00-Index.md"
    index.write_text("\n".join([f"[PDF]({OLD_LINK})"] * 122), encoding="utf-8")
    calls: list[str] = []

    def resolver(key: str) -> str:
        calls.append(key)
        return _verified_resolver(key)

    plan = plan_paper_foldering(
        vault_root=vault, field=field, relocations=_relocations(),
        legacy_link_resolver=resolver,
    )
    assert plan.legacy_link_count == 122
    assert calls == ["ABCD2345"]
    document = next(row for row in plan.documents if row.source_path.endswith("00-Index.md"))
    assert document.after_bytes.count(NEW_LINK.encode()) == 122
    assert OLD_LINK.encode() not in document.after_bytes


def test_unresolved_loopback_link_rejected(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    index = vault / "World Models/00-Index.md"
    index.write_text(index.read_text(encoding="utf-8") + "http://localhost:23128/other\n")
    with pytest.raises(PaperFolderingError, match="unresolved legacy Hub URL"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=_relocations(), legacy_link_resolver=_verified_resolver,
        )


def test_managed_document_cannot_be_rewritten_as_plain_note(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    index = vault / "World Models/00-Index.md"
    index.write_text(
        "---\nsw_kind: paper-analysis\n---\n" + index.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(PaperFolderingError, match="validated bundle"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=_relocations(), legacy_link_resolver=_verified_resolver,
        )


def test_old_note_with_analysis_sidecar_is_not_plainly_moved(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    (vault / "World Models/paper_assets/One.analysis.json").write_text("{}")
    with pytest.raises(PaperFolderingError, match="managed analysis"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=[_relocations()[0]], legacy_link_resolver=_verified_resolver,
        )


def test_legacy_link_in_non_markdown_requires_separate_handler(tmp_path: Path) -> None:
    vault, field = _fixture(tmp_path)
    (vault / "World Models/extra.txt").write_text(OLD_LINK)
    with pytest.raises(PaperFolderingError, match="validated bundle"):
        plan_paper_foldering(
            vault_root=vault, field=field,
            relocations=_relocations(), legacy_link_resolver=_verified_resolver,
        )
