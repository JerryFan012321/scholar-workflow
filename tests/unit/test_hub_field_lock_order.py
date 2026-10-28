"""Process-level regression checks for Source registry before Vault locking."""

from __future__ import annotations

import fcntl
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from scholar_workflow.hub.field_transaction import FieldTransactionError, FieldTransactionService
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.workflows.register_source import register_source


def _transaction_worker(service, plan, operation, start, attempted, result):
    original_flock = fcntl.flock
    registry_lock = service.registry.path.with_name(f".{service.registry.path.name}.lock")

    def observed_flock(descriptor, flags):
        if flags & fcntl.LOCK_EX:
            metadata = os.fstat(descriptor)
            registry_metadata = registry_lock.stat()
            attempted.put(
                "registry"
                if (metadata.st_dev, metadata.st_ino)
                == (registry_metadata.st_dev, registry_metadata.st_ino)
                else "vault"
            )
        return original_flock(descriptor, flags)

    start.wait(10)
    fcntl.flock = observed_flock
    try:
        if operation == "apply":
            service.apply(
                plan.plan_token,
                approved_digest=plan.plan_digest,
                external_writers_paused=True,
            )
            result.put("applied")
        else:
            recovery = service.recover(
                plan.source_id, plan.field_id, external_writers_paused=True
            )
            result.put(recovery.outcome)
    except (FieldTransactionError, OSError) as exc:
        result.put(repr(exc))
    finally:
        fcntl.flock = original_flock


def _field_confirm_worker(fields, token, field_id, start, attempted, result):
    original_flock = fcntl.flock
    registry_lock = fields.registry.path.with_name(f".{fields.registry.path.name}.lock")

    def observed_flock(descriptor, flags):
        if flags & fcntl.LOCK_EX:
            metadata = os.fstat(descriptor)
            registry_metadata = registry_lock.stat()
            attempted.put(
                "registry"
                if (metadata.st_dev, metadata.st_ino)
                == (registry_metadata.st_dev, registry_metadata.st_ino)
                else "vault"
            )
        return original_flock(descriptor, flags)

    start.wait(10)
    fcntl.flock = observed_flock
    try:
        fields.confirm(token, field_id)
        result.put("confirmed")
    except (OSError, ValueError) as exc:
        result.put(repr(exc))
    finally:
        fcntl.flock = original_flock


def test_field_confirm_waits_for_registry_before_publishing_manifest(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    field_root = vault / "topic"
    field_root.mkdir()
    (field_root / "00-home.md").write_text("# Topic\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "host" / "sources.json")
    fields = FieldService(registry)
    preview = fields.preview(vault)
    selected = next(row for row in preview.fields if row.relative_root == "topic")

    context = multiprocessing.get_context("fork")
    start = context.Event()
    attempted = context.Queue()
    result = context.Queue()
    worker = context.Process(
        target=_field_confirm_worker,
        args=(fields, preview.candidate_token, selected.field_id, start, attempted, result),
    )
    worker.start()
    registry.path.parent.mkdir(parents=True, exist_ok=True)
    registry_lock = registry.path.with_name(f".{registry.path.name}.lock")
    registry_fd = os.open(registry_lock, os.O_RDWR | os.O_CREAT, 0o600)
    vault_fd = os.open(vault, os.O_RDONLY)
    try:
        # A v4 analysis writer can hold registry SH while requesting Vault EX.
        # Confirm must wait at registry EX instead of publishing a provisional
        # Field and waiting for registry only afterward.
        fcntl.flock(registry_fd, fcntl.LOCK_SH)
        start.set()
        assert attempted.get(timeout=10) == "registry"
        fcntl.flock(vault_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(vault_fd, fcntl.LOCK_UN)
        assert not (vault / ".scholar-workflow" / "fields.yml").exists()
        fcntl.flock(registry_fd, fcntl.LOCK_UN)
        assert result.get(timeout=10) == "confirmed"
        worker.join(timeout=10)
        assert worker.exitcode == 0
    finally:
        os.close(vault_fd)
        os.close(registry_fd)
        if worker.is_alive():
            worker.terminate()
        worker.join(timeout=10)
        attempted.close()
        result.close()

    assert registry.path.is_file()
    assert (vault / ".scholar-workflow" / "fields.yml").is_file()


@pytest.mark.parametrize("schema_version", [2, 3, 4])
@pytest.mark.parametrize("operation", ["apply", "recover"])
def test_field_transaction_waits_for_registry_before_taking_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema_version: int, operation: str
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    field = vault / "topic"
    field.mkdir()
    home = field / "00-home.md"
    home.write_text("# Topic\n", encoding="utf-8")
    note = field / "note.md"
    note.write_text("# Note\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "host" / "sources.json")
    fields = FieldService(registry)
    if schema_version in {2, 3}:
        # Existing Sources retain legacy Field journal formats; first creation
        # now needs schema 4 to bind the inventory member as well.
        existing = vault / "existing"
        existing.mkdir()
        (existing / "README.md").write_text("# Existing Field\n", encoding="utf-8")
        approved = registration_plan(fields, vault, field_root="existing", existing_source=False)
        register_source(fields, vault, field_root="existing", existing_source=False,
                        approved_digest=approved.payload["approved_digest"])
    service = FieldTransactionService(fields, state_root=tmp_path / "private")
    registry_before = registry.path.read_bytes() if registry.path.exists() else None
    preview = fields.preview(vault)
    selected = next(row for row in preview.fields if row.relative_root == "topic")
    if schema_version in {3, 4}:
        selected = selected.model_copy(
            update={
                "navigation": [
                    group.model_copy(
                        update={
                            "items": [
                                "resources/note.md" if item == "note.md" else item
                                for item in group.items
                            ]
                        }
                    )
                    for group in selected.navigation
                ]
            }
        )
    plan = service.plan(
        preview.candidate_token,
        selected.field_id,
        field_definition=selected,
        relocations={"note.md": "resources/note.md"} if schema_version in {3, 4} else None,
    )
    assert plan.conflicts == ()
    if operation == "recover":
        original_replace = service._replace

        def interrupted_replace(*args, **kwargs):
            original_replace(*args, **kwargs)
            raise OSError("interrupted after first Vault write")

        def interrupted_recovery(*args):
            raise FieldTransactionError("process stopped")

        with monkeypatch.context() as patch:
            patch.setattr(service, "_replace", interrupted_replace)
            patch.setattr(service, "_recover_locked", interrupted_recovery)
            with pytest.raises(FieldTransactionError, match="recover explicitly"):
                service.apply(
                    plan.plan_token,
                    approved_digest=plan.plan_digest,
                    external_writers_paused=True,
                )
        journal = next(service.state_root.rglob("pending.json"))
        assert json.loads(journal.read_text())["schema_version"] == schema_version

    # Fork preserves the in-memory approved plan. Open the competitor's locks
    # after fork so the worker cannot inherit descriptors holding those locks.
    context = multiprocessing.get_context("fork")
    start = context.Event()
    attempted = context.Queue()
    result = context.Queue()
    worker = context.Process(
        target=_transaction_worker,
        args=(service, plan, operation, start, attempted, result),
    )
    worker.start()
    registry.path.parent.mkdir(parents=True, exist_ok=True)
    registry_lock = registry.path.with_name(f".{registry.path.name}.lock")
    registry_fd = os.open(registry_lock, os.O_RDWR | os.O_CREAT, 0o600)
    vault_fd = os.open(vault, os.O_RDONLY)
    try:
        # A v4 writer holds registry SH before requesting the same Vault inode.
        fcntl.flock(registry_fd, fcntl.LOCK_SH)
        start.set()
        assert attempted.get(timeout=10) == "registry"
        # Waiting for registry EX must not block that writer's next Vault lock.
        fcntl.flock(vault_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(vault_fd, fcntl.LOCK_UN)
        fcntl.flock(registry_fd, fcntl.LOCK_UN)
        # For a pre-existing Source with only a new manifest member, that first
        # publication is the complete commit. Relocations/new Source registration
        # are still incomplete at this interruption and must roll back.
        expected = "applied" if operation == "apply" else (
            "committed" if schema_version == 2 else "rolled-back"
        )
        assert result.get(timeout=10) == expected
        worker.join(timeout=10)
        assert worker.exitcode == 0
    finally:
        os.close(vault_fd)
        os.close(registry_fd)
        if worker.is_alive():
            worker.terminate()
        worker.join(timeout=10)
        attempted.close()
        result.close()

    if operation == "recover":
        assert note.read_text(encoding="utf-8") == "# Note\n"
        assert home.read_text(encoding="utf-8") == "# Topic\n"
        if registry_before is None:
            assert not registry.path.exists()
        else:
            assert registry.path.read_bytes() == registry_before
    else:
        assert registry.path.is_file()
