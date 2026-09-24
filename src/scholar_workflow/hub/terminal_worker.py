"""Private queued Codex worker presented inside one cmux terminal surface.

The browser never constructs this worker command.  A trusted Hub broker writes
one private ticket containing a validated :class:`TaskSubmission` and
:class:`TaskRequest`; the long-lived slot worker consumes it, removes the brief
from disk, re-resolves the execution target, rebuilds the Codex invocation from
the current recipe registry, and sends the brief only through stdin.

Codex JSONL is streamed to the terminal and inspected in memory only to recover
the explicit thread ID.  It is never persisted as a second transcript.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import queue
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

from pydantic import Field, field_validator, model_validator

from scholar_workflow.hub.cmux import minimal_child_environment
from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.fields import KnowledgeSourceRegistry
from scholar_workflow.hub.models import HubModel
from scholar_workflow.hub.routing import ExecutionTargetRegistry
from scholar_workflow.hub.tasks import (
    CodexCapabilities,
    CodexCapabilityProbe,
    CodexCommandBuilder,
    CodexInvocation,
    ProcessGroupReaper,
    TaskContractError,
    TaskRecipeRegistry,
    TaskRequest,
    TaskRun,
    TaskRunState,
    TaskStore,
    TaskSubmission,
    task_configuration_fingerprint,
    task_request_fingerprint,
)

_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_THREAD_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TERMINAL_STATES = {
    TaskRunState.SUCCEEDED,
    TaskRunState.FAILED,
    TaskRunState.INTERRUPTED,
    TaskRunState.CANCELLED,
    TaskRunState.TIMED_OUT,
}


class TerminalWorkerError(RuntimeError):
    """A private worker state, ticket, or process contract was rejected."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _private_identifier(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        raise ValueError(f"{name} must be an opaque portable identifier")
    return value


def _absolute_path(value: Path, *, name: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be an explicit absolute path")
    return path


class TerminalWorkerRuntimeConfig(HubModel):
    """Private host configuration used to rebuild every task invocation."""

    schema_version: int = 1
    generation: str
    codex_executable: Path
    recipe_registry_path: Path
    task_store_path: Path
    execution_target_registry_path: Path
    project_registry_path: Path
    source_registry_path: Path
    timeout_seconds: float = Field(default=1800.0, gt=0, le=86_400)
    heartbeat_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    poll_interval_seconds: float = Field(default=0.25, gt=0, le=10)

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported terminal worker runtime schema")
        return value

    @field_validator("generation")
    @classmethod
    def _generation(cls, value: str) -> str:
        return _private_identifier(value, name="worker generation")

    @field_validator(
        "codex_executable",
        "recipe_registry_path",
        "task_store_path",
        "execution_target_registry_path",
        "project_registry_path",
        "source_registry_path",
    )
    @classmethod
    def _paths(cls, value: Path) -> Path:
        return _absolute_path(value, name="terminal worker configuration path")

    @model_validator(mode="after")
    def _timing(self) -> TerminalWorkerRuntimeConfig:
        if self.heartbeat_interval_seconds >= self.timeout_seconds:
            raise ValueError("heartbeat interval must be shorter than the task timeout")
        return self

    def resolved_codex_executable(self) -> Path:
        """Resolve one configured executable without consulting ``PATH``."""

        try:
            resolved = self.codex_executable.resolve(strict=True)
            metadata = resolved.stat()
        except OSError as exc:
            raise TerminalWorkerError("configured Codex executable is unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
            raise TerminalWorkerError("configured Codex executable is not executable")
        return resolved


class TerminalTaskTicket(HubModel):
    """Private one-shot payload.  It is unlinked before Codex is started."""

    schema_version: int = 1
    slot_id: str
    generation: str
    queued_at_ns: int = Field(ge=0)
    submission: TaskSubmission
    request: TaskRequest

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported terminal task ticket schema")
        return value

    @field_validator("slot_id", "generation")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _private_identifier(value, name="terminal ticket identifier")

    @model_validator(mode="after")
    def _launchable(self) -> TerminalTaskTicket:
        if self.submission.reused:
            raise ValueError("idempotency replay cannot create a terminal ticket")
        if self.submission.run.state != TaskRunState.QUEUED:
            raise ValueError("terminal tickets require a queued task run")
        if self.submission.run.task_id != self.submission.task.task_id:
            raise ValueError("terminal ticket task and run identities do not match")
        return self


class TerminalQueueReceipt(HubModel):
    """Public-safe result of placing an opaque run in a terminal slot."""

    slot_id: str
    generation: str
    run_id: str
    queued: bool


class TerminalWorkerPublicStatus(HubModel):
    """Public-safe slot state with no path, PID, prompt, argv, or transcript."""

    slot_id: str
    generation: str
    state: Literal["idle", "busy", "stopping"]
    worker_alive: bool
    queued_run_ids: list[str] = Field(default_factory=list)
    active_run_id: str | None = None


class _ActiveRunMarker(HubModel):
    schema_version: int = 2
    slot_id: str
    generation: str
    run_id: str
    started_at: datetime
    phase: Literal["claimed", "launching", "running"] = "claimed"
    process_group_id: int | None = None

    @model_validator(mode="after")
    def _phase_has_process_identity(self) -> _ActiveRunMarker:
        if self.schema_version != 2:
            raise ValueError("unsupported active run marker schema")
        if self.phase == "running":
            if self.process_group_id is None or self.process_group_id <= 1:
                raise ValueError("running marker requires a process group")
        elif self.process_group_id is not None:
            raise ValueError("process group is only valid for a running marker")
        return self


def build_terminal_worker_command(
    *,
    python_executable: Path,
    state_root: Path,
    slot_id: str,
    generation: str,
) -> str:
    """Build the fixed cmux command from installed/runtime-owned values only."""

    python = _absolute_path(python_executable, name="Python executable")
    root = _absolute_path(state_root, name="terminal worker state root")
    slot = _private_identifier(slot_id, name="terminal worker slot")
    worker_generation = _private_identifier(generation, name="worker generation")
    if not python.is_file() or not os.access(python, os.X_OK):
        raise TerminalWorkerError("configured Python executable is not executable")
    return shlex.join(
        [
            str(python.resolve(strict=True)),
            "-m",
            "scholar_workflow.hub.terminal_worker",
            "--state-root",
            str(root),
            "--slot",
            slot,
            "--generation",
            worker_generation,
        ]
    )


class TerminalWorkerState:
    """Cross-process private runtime config and one-shot slot queues."""

    def __init__(self, root: Path) -> None:
        self.root = _absolute_path(root, name="terminal worker state root")
        self.runtime_path = self.root / "runtime.json"
        self.slots_path = self.root / "slots"
        self._held_worker_leases: set[tuple[str, str, int]] = set()

    def initialize(self) -> None:
        self._ensure_private_directory(self.root)
        self._ensure_private_directory(self.slots_path)

    def save_runtime(self, config: TerminalWorkerRuntimeConfig) -> None:
        self.initialize()
        checked = TerminalWorkerRuntimeConfig.model_validate(config)
        executable = checked.resolved_codex_executable()
        checked = checked.model_copy(update={"codex_executable": executable})
        _write_private_json(self.runtime_path, checked.model_dump(mode="json"))

    def load_runtime(self, *, generation: str) -> TerminalWorkerRuntimeConfig:
        requested = _private_identifier(generation, name="worker generation")
        config = self.current_runtime()
        if config.generation != requested:
            raise TerminalWorkerError("terminal worker generation is stale")
        return config

    def current_runtime(self) -> TerminalWorkerRuntimeConfig:
        """Read the private runtime configuration before a generation is known."""

        self._require_initialized()
        try:
            payload = _read_private_json(self.runtime_path)
            config = TerminalWorkerRuntimeConfig.model_validate(payload)
        except (OSError, ValueError, TerminalWorkerError) as exc:
            raise TerminalWorkerError("terminal worker runtime configuration is invalid") from exc
        config.resolved_codex_executable()
        return config

    def enqueue(self, ticket: TerminalTaskTicket) -> TerminalQueueReceipt:
        self._require_initialized()
        self.load_runtime(generation=ticket.generation)
        paths = self._slot_paths(ticket.slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            queued = paths["queue"] / f"{ticket.submission.run.run_id}.json"
            active = paths["active"] / f"{ticket.submission.run.run_id}.json"
            if active.exists():
                return TerminalQueueReceipt(
                    slot_id=ticket.slot_id,
                    generation=ticket.generation,
                    run_id=ticket.submission.run.run_id,
                    queued=False,
                )
            if queued.exists():
                existing = TerminalTaskTicket.model_validate(_read_private_json(queued))
                if existing.model_dump(mode="json") != ticket.model_dump(mode="json"):
                    raise TerminalWorkerError("queued run ticket does not match its replay")
                return TerminalQueueReceipt(
                    slot_id=ticket.slot_id,
                    generation=ticket.generation,
                    run_id=ticket.submission.run.run_id,
                    queued=False,
                )
            _write_private_json(queued, ticket.model_dump(mode="json"), exclusive=True)
        return TerminalQueueReceipt(
            slot_id=ticket.slot_id,
            generation=ticket.generation,
            run_id=ticket.submission.run.run_id,
            queued=True,
        )

    def claim_next(self, *, slot_id: str, generation: str) -> TerminalTaskTicket | None:
        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            active_markers = [
                path for path in paths["active"].iterdir() if path.suffix == ".json"
            ]
            if active_markers:
                raise TerminalWorkerError(
                    "terminal slot has an unfinished active run; recovery is required"
                )
            candidates: list[tuple[int, Path, TerminalTaskTicket]] = []
            for path in paths["queue"].iterdir():
                if path.suffix != ".json":
                    continue
                try:
                    ticket = TerminalTaskTicket.model_validate(_read_private_json(path))
                except (OSError, ValueError, TerminalWorkerError) as exc:
                    raise TerminalWorkerError("terminal task queue contains an invalid ticket") from exc
                if ticket.slot_id != slot_id or ticket.generation != generation:
                    raise TerminalWorkerError("terminal task ticket targets another worker")
                if path.stem != ticket.submission.run.run_id:
                    raise TerminalWorkerError("terminal task ticket filename is inconsistent")
                candidates.append((ticket.queued_at_ns, path, ticket))
            if not candidates:
                return None
            _queued_at, path, ticket = min(candidates, key=lambda row: (row[0], row[1].name))
            marker = _ActiveRunMarker(
                slot_id=slot_id,
                generation=generation,
                run_id=ticket.submission.run.run_id,
                started_at=_utc_now(),
                phase="claimed",
            )
            active_path = paths["active"] / f"{ticket.submission.run.run_id}.json"
            if active_path.exists():
                raise TerminalWorkerError("terminal task run already has an active marker")
            _write_private_json(active_path, marker.model_dump(mode="json"), exclusive=True)
            # The only on-disk copy of the brief is removed before validation or launch.
            path.unlink()
            return ticket

    def mark_launching(self, *, slot_id: str, generation: str, run_id: str) -> None:
        """Persist the uncertain spawn window before calling ``Popen``."""

        self._advance_active(
            slot_id=slot_id,
            generation=generation,
            run_id=run_id,
            previous="claimed",
            phase="launching",
        )

    def mark_running(
        self, *, slot_id: str, generation: str, run_id: str, process_group_id: int
    ) -> None:
        """Record the separate-session group before consuming process output."""

        self._advance_active(
            slot_id=slot_id,
            generation=generation,
            run_id=run_id,
            previous="launching",
            phase="running",
            process_group_id=process_group_id,
        )

    def _advance_active(
        self,
        *,
        slot_id: str,
        generation: str,
        run_id: str,
        previous: Literal["claimed", "launching"],
        phase: Literal["launching", "running"],
        process_group_id: int | None = None,
    ) -> None:
        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            active = paths["active"] / f"{_private_identifier(run_id, name='run ID')}.json"
            try:
                marker = _ActiveRunMarker.model_validate(_read_private_json(active))
            except (OSError, ValueError, TerminalWorkerError) as exc:
                raise TerminalWorkerError("active task marker is invalid") from exc
            if (
                marker.slot_id != slot_id
                or marker.generation != generation
                or marker.run_id != run_id
                or marker.phase != previous
            ):
                raise TerminalWorkerError("active task marker changed during launch")
            updated = marker.model_copy(
                update={"phase": phase, "process_group_id": process_group_id}
            )
            _ActiveRunMarker.model_validate(updated.model_dump(mode="json"))
            _write_private_json(active, updated.model_dump(mode="json"))

    def recover_stale_active(
        self, *, slot_id: str, generation: str, store: TaskStore
    ) -> None:
        """Resolve a prior marker only while this thread owns the worker lease.

        A claimed run has not entered the spawn window.  A running run may be
        resolved only after its recorded process group is absent.  A launching
        marker has no reliable process identity, so it remains blocked.
        """

        self.load_runtime(generation=generation)
        lease_key = (slot_id, generation, threading.get_ident())
        if lease_key not in self._held_worker_leases:
            raise TerminalWorkerError("stale active recovery requires the worker lease")
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            markers = sorted(
                path for path in paths["active"].iterdir() if path.suffix == ".json"
            )
            if not markers:
                return
            if len(markers) != 1 or not _OPAQUE_ID.fullmatch(markers[0].stem):
                raise TerminalWorkerError("terminal slot has ambiguous active markers")
            path = markers[0]
            run_id = path.stem
            # A crash between marker creation and queue unlink can leave the
            # one-shot brief behind.  The worker lease proves the old consumer
            # is gone, so this duplicate ticket must never be replayed.
            (paths["queue"] / f"{run_id}.json").unlink(missing_ok=True)
            try:
                marker = _ActiveRunMarker.model_validate(_read_private_json(path))
            except (OSError, ValueError, TerminalWorkerError) as exc:
                self._fail_closed_stale_run(store, run_id)
                raise TerminalWorkerError("stale active marker cannot prove launch state") from exc
            if (
                marker.slot_id != slot_id
                or marker.run_id != run_id
            ):
                self._fail_closed_stale_run(store, run_id)
                raise TerminalWorkerError("stale active marker identity is inconsistent")
            if marker.phase == "launching" or (
                marker.phase == "running"
                and not self._process_group_absent(marker.process_group_id)
            ):
                self._fail_closed_stale_run(store, run_id)
                raise TerminalWorkerError("stale Codex process group is not proven stopped")
            run = store.get_run(run_id)
            if run.state == TaskRunState.QUEUED:
                store.fail_queued(
                    run_id,
                    now=_utc_now(),
                    reason="Terminal worker exited after claiming the queued task",
                )
            elif run.state in {TaskRunState.RUNNING, TaskRunState.RECOVERY_REQUIRED}:
                store.finish(
                    run_id,
                    state=TaskRunState.INTERRUPTED,
                    now=_utc_now(),
                    result_summary="Terminal worker exited before completing the task",
                )
            elif run.state not in _TERMINAL_STATES:
                raise TerminalWorkerError("stale task run has an unknown state")
            path.unlink()

    @staticmethod
    def _fail_closed_stale_run(store: TaskStore, run_id: str) -> None:
        try:
            run = store.get_run(run_id)
        except TaskContractError:
            return
        if run.state == TaskRunState.RUNNING:
            store.mark_recovery_required(
                run_id,
                now=_utc_now(),
                reason="Terminal worker exit left process cleanup unproven",
            )
        elif run.state == TaskRunState.QUEUED:
            store.fail_queued(
                run_id,
                now=_utc_now(),
                reason="Terminal worker exit left launch state unproven",
            )

    @staticmethod
    def _process_group_absent(process_group_id: int | None) -> bool:
        if process_group_id is None or process_group_id <= 1:
            return False
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        return False

    def complete(self, *, slot_id: str, generation: str, run_id: str) -> None:
        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            active = paths["active"] / f"{_private_identifier(run_id, name='run ID')}.json"
            active.unlink(missing_ok=True)

    def request_stop(self, *, slot_id: str, generation: str) -> None:
        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        _write_private_json(
            paths["stop"],
            {"schema_version": 1, "slot_id": slot_id, "generation": generation},
        )

    def clear_stop(self, *, slot_id: str, generation: str) -> None:
        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            paths["stop"].unlink(missing_ok=True)

    def should_stop(self, *, slot_id: str, generation: str) -> bool:
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        stop = paths["stop"]
        if not stop.exists():
            return False
        payload = _read_private_json(stop)
        return payload == {
            "schema_version": 1,
            "slot_id": slot_id,
            "generation": generation,
        }

    def public_status(
        self, *, slot_id: str, generation: str
    ) -> TerminalWorkerPublicStatus:
        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        with self._slot_lock(paths):
            queued = sorted(
                path.stem
                for path in paths["queue"].iterdir()
                if path.suffix == ".json" and _OPAQUE_ID.fullmatch(path.stem)
            )
            active = sorted(
                path.stem
                for path in paths["active"].iterdir()
                if path.suffix == ".json" and _OPAQUE_ID.fullmatch(path.stem)
            )
            if len(active) > 1:
                raise TerminalWorkerError("terminal slot has multiple active runs")
            stopping = self.should_stop(slot_id=slot_id, generation=generation)
            state: Literal["idle", "busy", "stopping"] = (
                "stopping" if stopping else "busy" if active else "idle"
            )
            return TerminalWorkerPublicStatus(
                slot_id=slot_id,
                generation=generation,
                state=state,
                worker_alive=self.worker_alive(
                    slot_id=slot_id,
                    generation=generation,
                ),
                queued_run_ids=queued,
                active_run_id=active[0] if active else None,
            )

    def _require_initialized(self) -> None:
        _require_private_directory(self.root)
        _require_private_directory(self.slots_path)

    def _slot_paths(self, slot_id: str) -> dict[str, Path]:
        slot = _private_identifier(slot_id, name="terminal worker slot")
        root = self.slots_path / slot
        return {
            "root": root,
            "queue": root / "queue",
            "active": root / "active",
            "lock": root / ".lock",
            "worker_lock": root / ".worker.lock",
            "worker_marker": root / "worker.json",
            "stop": root / "stop.json",
        }

    def _ensure_slot(self, paths: Mapping[str, Path]) -> None:
        self._require_initialized()
        self._ensure_private_directory(paths["root"])
        self._ensure_private_directory(paths["queue"])
        self._ensure_private_directory(paths["active"])

    @staticmethod
    def _ensure_private_directory(path: Path) -> None:
        if not path.exists():
            # Another trusted Hub thread may initialize the same slot between
            # the existence check and mkdir.  The strict lstat check below is
            # the authority; ``exist_ok`` only closes that benign race.
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        _require_private_directory(path)

    @contextmanager
    def _slot_lock(self, paths: Mapping[str, Path]) -> Iterator[None]:
        lock_path = paths["lock"]
        if lock_path.is_symlink():
            raise TerminalWorkerError("terminal worker lock cannot be a symlink")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise TerminalWorkerError("cannot open terminal worker lock") from exc
        try:
            metadata = os.fstat(descriptor)
            _require_private_file_metadata(metadata)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        except OSError as exc:
            raise TerminalWorkerError("terminal worker queue lock failed") from exc
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(descriptor)

    @contextmanager
    def worker_lease(self, *, slot_id: str, generation: str) -> Iterator[None]:
        """Hold the one process lease for a long-lived logical terminal slot."""

        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        lock_path = paths["worker_lock"]
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise TerminalWorkerError("cannot open terminal worker lease") from exc
        try:
            _require_private_file_metadata(os.fstat(descriptor))
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise TerminalWorkerError(
                    "terminal slot already has a long-lived worker"
                ) from exc
            _write_private_json(
                paths["worker_marker"],
                {
                    "schema_version": 1,
                    "slot_id": slot_id,
                    "generation": generation,
                    "started_at": _utc_now().isoformat(),
                    "ready": False,
                },
            )
            lease_key = (slot_id, generation, threading.get_ident())
            self._held_worker_leases.add(lease_key)
            try:
                yield
            finally:
                self._held_worker_leases.discard(lease_key)
                paths["worker_marker"].unlink(missing_ok=True)
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(descriptor)

    def mark_worker_ready(self, *, slot_id: str, generation: str) -> None:
        """Publish readiness only after stale-run recovery succeeds under the lease."""

        lease_key = (slot_id, generation, threading.get_ident())
        if lease_key not in self._held_worker_leases:
            raise TerminalWorkerError("worker readiness requires the worker lease")
        marker_path = self._slot_paths(slot_id)["worker_marker"]
        marker = _read_private_json(marker_path)
        if marker.get("slot_id") != slot_id or marker.get("generation") != generation:
            raise TerminalWorkerError("worker readiness marker is stale")
        _write_private_json(marker_path, {**marker, "ready": True})

    def worker_alive(self, *, slot_id: str, generation: str) -> bool:
        """Require a ready marker and kernel lease before routing new tickets."""

        self.load_runtime(generation=generation)
        paths = self._slot_paths(slot_id)
        self._ensure_slot(paths)
        marker_path = paths["worker_marker"]
        lock_path = paths["worker_lock"]
        if not marker_path.exists() or not lock_path.exists():
            return False
        marker = _read_private_json(marker_path)
        if (
            marker.get("slot_id") != slot_id
            or marker.get("generation") != generation
            or marker.get("ready") is not True
        ):
            return False
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags)
        except OSError as exc:
            raise TerminalWorkerError("cannot inspect terminal worker lease") from exc
        try:
            _require_private_file_metadata(os.fstat(descriptor))
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                return False
        finally:
            os.close(descriptor)


class _TicketValidator:
    """Rebuild and bind a ticket to canonical registries and task metadata."""

    def __init__(self, config: TerminalWorkerRuntimeConfig) -> None:
        self.config = config
        self.recipes = TaskRecipeRegistry(config.recipe_registry_path)
        self.store = TaskStore(config.task_store_path)
        projects = ProjectRegistry(config.project_registry_path)
        sources = KnowledgeSourceRegistry(config.source_registry_path)
        self.targets = ExecutionTargetRegistry(
            config.execution_target_registry_path,
            project_registry=projects,
            source_registry=sources,
        )

    def validate(
        self,
        *,
        submission: TaskSubmission,
        request: TaskRequest,
        compare_submitted_invocation: bool,
    ) -> CodexInvocation:
        if submission.reused or submission.run.state != TaskRunState.QUEUED:
            raise TerminalWorkerError("terminal task submission is not launchable")
        canonical_run = self.store.get_run(submission.run.run_id)
        canonical_task = self.store.get_task(canonical_run.task_id)
        if _model_payload(canonical_run) != _model_payload(submission.run):
            raise TerminalWorkerError("terminal task run differs from the durable reservation")
        if _model_payload(canonical_task) != _model_payload(submission.task):
            raise TerminalWorkerError("terminal logical task differs from its durable record")
        if request.recipe_id != canonical_task.recipe_id:
            raise TerminalWorkerError("terminal request recipe does not match its task")
        if request.idempotency_key != canonical_run.idempotency_key:
            raise TerminalWorkerError("terminal request idempotency key does not match its run")
        if request.target_id != canonical_task.target_id:
            raise TerminalWorkerError("terminal request target does not match its task")
        if request.project_id != canonical_task.project_id:
            raise TerminalWorkerError("terminal request project does not match its task")
        if request.effort != canonical_task.effort:
            raise TerminalWorkerError("terminal request effort does not match its task")
        if canonical_run.mode in {"create", "fork"}:
            brief_hash = "sha256:" + hashlib.sha256(request.brief.encode("utf-8")).hexdigest()
            if brief_hash != canonical_task.brief_hash:
                raise TerminalWorkerError("terminal request brief does not match its approved hash")
        # A resume is a new bounded brief. Its exact content is bound to the
        # durable run by request_fingerprint below, not to the task's first brief.

        recipe = self.recipes.get(request.recipe_id)
        policies = self.recipes.safety_policy_map()
        try:
            policy = policies[recipe.safety_policy_id]
        except KeyError:
            raise TerminalWorkerError("terminal recipe safety policy is unavailable") from None
        configuration = task_configuration_fingerprint(
            recipe,
            request,
            safety_policy=policy,
        )
        if configuration not in {
            canonical_task.configuration_fingerprint,
            canonical_run.configuration_fingerprint,
        } or canonical_task.configuration_fingerprint != canonical_run.configuration_fingerprint:
            raise TerminalWorkerError("terminal task configuration changed after reservation")
        expected_request = self._request_fingerprint(
            run=canonical_run,
            task=canonical_task,
            request=request,
        )
        if expected_request != canonical_run.request_fingerprint:
            raise TerminalWorkerError("terminal task request fingerprint is invalid")

        builder = CodexCommandBuilder(
            codex_executable=self.config.resolved_codex_executable(),
            target_registry=self.targets,
            safety_policies=policies,
        )
        try:
            invocation = (
                builder.build_new(recipe, request)
                if canonical_run.mode == "create"
                else builder.build_continuation(
                    recipe,
                    request,
                    mode=canonical_run.mode,
                    codex_thread_id=self._required_source_thread(canonical_run),
                )
            )
        except (TaskContractError, ValueError) as exc:
            raise TerminalWorkerError("terminal task invocation could not be rebuilt") from exc
        if compare_submitted_invocation:
            if submission.invocation is None:
                raise TerminalWorkerError("terminal task submission has no prepared invocation")
            if _model_payload(submission.invocation) != _model_payload(invocation):
                raise TerminalWorkerError("prepared task invocation differs from current policy")
        return invocation

    def _request_fingerprint(
        self,
        *,
        run: Any,
        task: Any,
        request: TaskRequest,
    ) -> str:
        if run.mode == "create":
            return task_request_fingerprint(
                request,
                mode="create",
                title=task.title,
            )
        if run.mode == "resume":
            return task_request_fingerprint(
                request,
                mode="resume",
                task_id=task.task_id,
            )
        if run.mode == "fork":
            source_task_id = self._source_task_id(run.source_thread_id, task.task_id)
            return task_request_fingerprint(
                request,
                mode="fork",
                source_task_id=source_task_id,
                title=task.title,
            )
        raise TerminalWorkerError("terminal task run has an unsupported mode")

    def _source_task_id(self, source_thread_id: str | None, new_task_id: str) -> str:
        if source_thread_id is None:
            raise TerminalWorkerError("fork run has no explicit source thread")
        candidates = [
            task.task_id
            for task in self.store.snapshot().tasks
            if task.task_id != new_task_id and task.codex_thread_id == source_thread_id
        ]
        if len(candidates) != 1:
            raise TerminalWorkerError("fork source task cannot be resolved uniquely")
        return candidates[0]

    @staticmethod
    def _required_source_thread(run: Any) -> str:
        thread_id = run.source_thread_id
        if not isinstance(thread_id, str) or not _THREAD_ID.fullmatch(thread_id):
            raise TerminalWorkerError("continuation run has no explicit source thread")
        return thread_id


class TerminalTaskBroker:
    """Validate a coordinator submission before placing a private one-shot ticket."""

    def __init__(self, state: TerminalWorkerState, *, generation: str) -> None:
        self.state = state
        self.config = state.load_runtime(generation=generation)
        self.validator = _TicketValidator(self.config)

    def enqueue(
        self,
        *,
        slot_id: str,
        submission: TaskSubmission,
        request: TaskRequest,
    ) -> TerminalQueueReceipt:
        self.validator.validate(
            submission=submission,
            request=request,
            compare_submitted_invocation=True,
        )
        sanitized = submission.model_copy(update={"invocation": None})
        ticket = TerminalTaskTicket(
            slot_id=slot_id,
            generation=self.config.generation,
            queued_at_ns=time.time_ns(),
            submission=sanitized,
            request=request,
        )
        return self.state.enqueue(ticket)


class TerminalSlotWorker:
    """Long-lived queue consumer for one logical cmux terminal slot."""

    def __init__(
        self,
        *,
        state: TerminalWorkerState,
        slot_id: str,
        generation: str,
        capabilities: CodexCapabilities,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        reaper: ProcessGroupReaper | None = None,
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        stdout: TextIO = sys.stdout,
        stderr: TextIO = sys.stderr,
    ) -> None:
        if not (
            capabilities.available
            and capabilities.create
            and capabilities.resume
            and capabilities.fork
        ):
            raise TerminalWorkerError("Codex terminal worker is disabled by capability probe")
        self.state = state
        self.slot_id = _private_identifier(slot_id, name="terminal worker slot")
        self.generation = _private_identifier(generation, name="worker generation")
        self.config = state.load_runtime(generation=self.generation)
        self.validator = _TicketValidator(self.config)
        self.store = self.validator.store
        self._popen_factory = popen_factory
        self._reaper = reaper or ProcessGroupReaper()
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._stdout = stdout
        self._stderr = stderr
        self._stop_requested = threading.Event()
        self._active_process: Any | None = None
        self._active_run_id: str | None = None

    @classmethod
    def from_state(
        cls,
        *,
        state: TerminalWorkerState,
        slot_id: str,
        generation: str,
        probe_factory: Callable[[Path], CodexCapabilityProbe] = CodexCapabilityProbe,
        **kwargs: Any,
    ) -> TerminalSlotWorker:
        config = state.load_runtime(generation=generation)
        capabilities = probe_factory(config.resolved_codex_executable()).probe()
        return cls(
            state=state,
            slot_id=slot_id,
            generation=generation,
            capabilities=capabilities,
            **kwargs,
        )

    def run_forever(self) -> None:
        """Consume this slot until a private stop marker or process signal."""

        previous_handlers = self._install_signal_handlers()
        try:
            with self.state.worker_lease(
                slot_id=self.slot_id,
                generation=self.generation,
            ):
                self.state.recover_stale_active(
                    slot_id=self.slot_id,
                    generation=self.generation,
                    store=self.store,
                )
                self.state.mark_worker_ready(
                    slot_id=self.slot_id,
                    generation=self.generation,
                )
                self._emit_worker_event("worker.started")
                while not self._stop_requested.is_set():
                    try:
                        self.state.load_runtime(generation=self.generation)
                    except TerminalWorkerError:
                        break
                    if self.state.should_stop(
                        slot_id=self.slot_id,
                        generation=self.generation,
                    ):
                        break
                    if not self.run_once():
                        self._sleep(self.config.poll_interval_seconds)
        finally:
            if self._active_process is not None:
                self._interrupt_active("Terminal worker received a stop signal")
            self._restore_signal_handlers(previous_handlers)
            self._emit_worker_event("worker.stopped")

    def run_once(self) -> bool:
        """Consume at most one ticket; return whether a ticket was claimed."""

        ticket = self.state.claim_next(
            slot_id=self.slot_id,
            generation=self.generation,
        )
        if ticket is None:
            return False
        run_id = ticket.submission.run.run_id
        try:
            try:
                invocation = self.validator.validate(
                    submission=ticket.submission,
                    request=ticket.request,
                    compare_submitted_invocation=False,
                )
            except Exception:  # noqa: BLE001 - ticket boundary fails closed
                self._fail_queued(run_id, "Terminal worker rejected the queued task")
                self._emit_worker_event("task.rejected", run_id=run_id)
                return True
            self._execute(ticket, invocation)
            return True
        finally:
            if self.store.get_run(run_id).state in _TERMINAL_STATES:
                self.state.complete(
                    slot_id=self.slot_id,
                    generation=self.generation,
                    run_id=run_id,
                )

    def request_stop(self) -> None:
        self._stop_requested.set()

    def _execute(self, ticket: TerminalTaskTicket, invocation: CodexInvocation) -> TaskRun:
        run_id = ticket.submission.run.run_id
        run = self.store.start(
            run_id,
            now=self._clock(),
            timeout_seconds=self.config.timeout_seconds,
        )
        self.state.mark_launching(
            slot_id=self.slot_id,
            generation=self.generation,
            run_id=run_id,
        )
        try:
            process = self._popen_factory(
                list(invocation.argv),
                cwd=str(invocation.cwd),
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=minimal_child_environment(include_cmux=False),
            )
        except Exception:  # noqa: BLE001 - subprocess boundary fails closed
            return self.store.finish(
                run_id,
                state=TaskRunState.FAILED,
                now=self._clock(),
                result_summary="Codex process could not start",
            )
        self._active_process = process
        self._active_run_id = run_id
        self._emit_worker_event("task.started", run_id=run_id)
        try:
            self.state.mark_running(
                slot_id=self.slot_id,
                generation=self.generation,
                run_id=run_id,
                process_group_id=process.pid,
            )
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise TerminalWorkerError("Codex process did not expose required pipes")
            process.stdin.write(invocation.stdin)
            process.stdin.close()
            outcome, thread_id = self._stream_process(process, run)
            if not self.state._process_group_absent(process.pid):
                return self.store.mark_recovery_required(
                    run_id,
                    now=self._clock(),
                    reason="Codex process group did not stop after task output ended",
                )
            if outcome == "cancelled":
                return self.store.finish(
                    run_id,
                    state=TaskRunState.CANCELLED,
                    now=self._clock(),
                    result_summary="Codex run cancelled",
                )
            if outcome == "timed_out":
                return self.store.finish(
                    run_id,
                    state=TaskRunState.TIMED_OUT,
                    now=self._clock(),
                    result_summary="Codex run exceeded its timeout",
                )
            if outcome == "interrupted":
                return self.store.finish(
                    run_id,
                    state=TaskRunState.INTERRUPTED,
                    now=self._clock(),
                    result_summary="Terminal worker was interrupted",
                )
            if process.returncode != 0:
                return self.store.finish(
                    run_id,
                    state=TaskRunState.FAILED,
                    now=self._clock(),
                    result_summary=f"Codex exited with status {process.returncode}",
                )
            if thread_id is None:
                return self.store.finish(
                    run_id,
                    state=TaskRunState.FAILED,
                    now=self._clock(),
                    result_summary="Codex output did not contain a valid thread identity",
                )
            return self.store.finish(
                run_id,
                state=TaskRunState.SUCCEEDED,
                now=self._clock(),
                codex_thread_id=thread_id,
            )
        except Exception:  # noqa: BLE001 - cleanup must cover every I/O failure
            if process.poll() is None:
                return self._reap_or_recovery(
                    run_id,
                    process,
                    terminal_state=TaskRunState.FAILED,
                    summary="Codex terminal worker I/O failed",
                    recovery="Terminal worker could not confirm process-group cleanup",
                )
            if self.state._process_group_absent(process.pid):
                return self.store.finish(
                    run_id,
                    state=TaskRunState.FAILED,
                    now=self._clock(),
                    result_summary="Codex terminal worker I/O failed",
                )
            return self.store.mark_recovery_required(
                run_id,
                now=self._clock(),
                reason="Codex process group cleanup is unconfirmed",
            )
        finally:
            self._active_process = None
            self._active_run_id = None
            self._emit_worker_event("task.finished", run_id=run_id)

    def _stream_process(self, process: Any, run: TaskRun) -> tuple[str, str | None]:
        events: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=128)
        readers = [
            threading.Thread(
                target=_read_stream,
                args=(process.stdout, "stdout", events),
                daemon=True,
            ),
            threading.Thread(
                target=_read_stream,
                args=(process.stderr, "stderr", events),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        open_streams = 2
        thread_ids: set[str] = set()
        invalid_jsonl = False
        next_heartbeat = self._monotonic() + self.config.heartbeat_interval_seconds
        outcome = "completed"
        while open_streams or process.poll() is None:
            try:
                channel, line = events.get(timeout=self.config.poll_interval_seconds)
            except queue.Empty:
                channel = ""
                line = None
            if channel:
                if line is None:
                    open_streams -= 1
                elif channel == "stdout":
                    self._stdout.write(line)
                    self._stdout.flush()
                    parsed = _thread_id_from_jsonl(line)
                    if parsed is False:
                        invalid_jsonl = True
                    elif isinstance(parsed, str):
                        thread_ids.add(parsed)
                else:
                    self._stderr.write(line)
                    self._stderr.flush()

            current = self.store.get_run(run.run_id)
            if current.cancel_requested_at is not None:
                outcome = "cancelled"
                self._reaper.reap(process)
                break
            if self._stop_requested.is_set() or self.state.should_stop(
                slot_id=self.slot_id,
                generation=self.generation,
            ):
                outcome = "interrupted"
                self._reaper.reap(process)
                break
            try:
                self.state.load_runtime(generation=self.generation)
            except TerminalWorkerError:
                outcome = "interrupted"
                self._reaper.reap(process)
                break
            if current.timeout_at is not None and self._clock() >= current.timeout_at:
                outcome = "timed_out"
                self._reaper.reap(process)
                break
            now_monotonic = self._monotonic()
            if process.poll() is None and now_monotonic >= next_heartbeat:
                self.store.heartbeat(run.run_id, now=self._clock())
                next_heartbeat = now_monotonic + self.config.heartbeat_interval_seconds

        if outcome != "completed":
            drain_deadline = self._monotonic() + 1.0
            while open_streams and self._monotonic() < drain_deadline:
                try:
                    channel, line = events.get(timeout=0.05)
                except queue.Empty:
                    continue
                if line is None:
                    open_streams -= 1
                elif channel == "stdout":
                    self._stdout.write(line)
                    self._stdout.flush()
                else:
                    self._stderr.write(line)
                    self._stderr.flush()
        for reader in readers:
            reader.join(timeout=1.0)
        if process.poll() is None:
            process.wait(timeout=1.0)
        if outcome != "completed":
            return outcome, None
        if invalid_jsonl or len(thread_ids) != 1:
            return outcome, None
        return outcome, next(iter(thread_ids))

    def _interrupt_active(self, summary: str) -> None:
        process = self._active_process
        run_id = self._active_run_id
        if process is None or run_id is None:
            return
        self._reap_or_recovery(
            run_id,
            process,
            terminal_state=TaskRunState.INTERRUPTED,
            summary=summary,
            recovery="Terminal worker signal cleanup could not be confirmed",
        )

    def _reap_or_recovery(
        self,
        run_id: str,
        process: Any,
        *,
        terminal_state: TaskRunState,
        summary: str,
        recovery: str,
    ) -> TaskRun:
        try:
            self._reaper.reap(process)
            if process.poll() is None:
                raise TerminalWorkerError("process-group reaper returned before stop")
            if not self.state._process_group_absent(process.pid):
                raise TerminalWorkerError("process group remains after reaping")
        except Exception:  # noqa: BLE001 - recovery state must survive adapter failure
            return self.store.mark_recovery_required(
                run_id,
                now=self._clock(),
                reason=recovery,
            )
        return self.store.finish(
            run_id,
            state=terminal_state,
            now=self._clock(),
            result_summary=summary,
        )

    def _fail_queued(self, run_id: str, reason: str) -> None:
        try:
            self.store.fail_queued(run_id, now=self._clock(), reason=reason)
        except TaskContractError:
            current = self.store.get_run(run_id)
            if current.state not in _TERMINAL_STATES:
                raise

    def _emit_worker_event(self, event_type: str, *, run_id: str | None = None) -> None:
        payload: dict[str, object] = {
            "type": f"scholar_workflow.{event_type}",
            "slot_id": self.slot_id,
            "generation": self.generation,
        }
        if run_id is not None:
            payload["run_id"] = run_id
        self._stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._stdout.flush()

    def _install_signal_handlers(self) -> dict[int, Any]:
        if threading.current_thread() is not threading.main_thread():
            return {}
        previous: dict[int, Any] = {}
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._signal_stop)
        return previous

    @staticmethod
    def _restore_signal_handlers(previous: Mapping[int, Any]) -> None:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    def _signal_stop(self, _signum: int, _frame: Any) -> None:
        self._stop_requested.set()


def _model_payload(model: Any) -> object:
    return model.model_dump(mode="json")


def _thread_id_from_jsonl(line: str) -> str | bool | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    thread_id = payload.get("thread_id")
    if thread_id is None:
        return None
    if not isinstance(thread_id, str) or not _THREAD_ID.fullmatch(thread_id):
        return False
    return thread_id


def _read_stream(stream: TextIO, channel: str, output: queue.Queue[tuple[str, str | None]]) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put((channel, line))
    finally:
        output.put((channel, None))
        try:
            stream.close()
        except OSError:
            pass


def _require_private_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise TerminalWorkerError("terminal worker private directory is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise TerminalWorkerError("terminal worker state must use real directories")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise TerminalWorkerError("terminal worker directory must be owner-only mode 0700")


def _require_private_file_metadata(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise TerminalWorkerError("terminal worker state must use regular files")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise TerminalWorkerError("terminal worker file must be owner-only mode 0600")


def _read_private_json(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TerminalWorkerError("cannot open private terminal worker state") from exc
    try:
        _require_private_file_metadata(os.fstat(descriptor))
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TerminalWorkerError("private terminal worker state is invalid") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise TerminalWorkerError("private terminal worker state must be a JSON object")
    return payload


def _write_private_json(
    path: Path,
    payload: Mapping[str, object],
    *,
    exclusive: bool = False,
) -> None:
    parent = path.parent
    _require_private_directory(parent)
    if path.is_symlink():
        raise TerminalWorkerError("private terminal worker file cannot be a symlink")
    if exclusive and path.exists():
        raise TerminalWorkerError("private terminal worker file already exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as exc:
                raise TerminalWorkerError("private terminal worker file already exists") from exc
            temporary.unlink()
        else:
            os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one private Scholar Workflow task slot")
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--generation", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        state = TerminalWorkerState(args.state_root)
        worker = TerminalSlotWorker.from_state(
            state=state,
            slot_id=args.slot,
            generation=args.generation,
        )
        worker.run_forever()
    except (OSError, ValueError, TerminalWorkerError, TaskContractError) as exc:
        print(
            json.dumps(
                {
                    "type": "scholar_workflow.worker.unavailable",
                    "detail": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 3
    return 0


__all__ = [
    "TerminalQueueReceipt",
    "TerminalSlotWorker",
    "TerminalTaskBroker",
    "TerminalTaskTicket",
    "TerminalWorkerError",
    "TerminalWorkerPublicStatus",
    "TerminalWorkerRuntimeConfig",
    "TerminalWorkerState",
    "build_terminal_worker_command",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - exercised through installed module
    raise SystemExit(main())
