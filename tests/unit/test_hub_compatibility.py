"""Tests for the reserved non-Source compatibility Vault root."""
from __future__ import annotations

import stat

import pytest

from scholar_workflow.hub.compatibility import (
    CompatibilityRootError,
    compatibility_vault_root,
)


def test_existing_legacy_directory_remains_a_migration_candidate(tmp_path) -> None:
    legacy = tmp_path / "legacy-vault"
    legacy.mkdir()

    assert compatibility_vault_root(legacy, state_home=tmp_path / "state") == legacy.resolve()


def test_missing_legacy_candidate_uses_private_empty_host_state_root(tmp_path) -> None:
    root = compatibility_vault_root(
        tmp_path / "missing-vault",
        state_home=tmp_path / "nested" / "state",
    )

    assert root == (
        tmp_path / "nested" / "state" / "hub" / "empty-compatibility-vault"
    ).resolve()
    assert list(root.iterdir()) == []
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert not (root / ".scholar-workflow" / "fields.yml").exists()


def test_reserved_root_rejects_symlink(tmp_path) -> None:
    state = tmp_path / "state"
    hub = state / "hub"
    hub.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (hub / "empty-compatibility-vault").symlink_to(target)

    with pytest.raises(CompatibilityRootError, match="real directory"):
        compatibility_vault_root(None, state_home=state)
