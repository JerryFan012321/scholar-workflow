"""Managed lifecycle for the loopback-only Scholar Workflow Hub service.

The lifecycle is deliberately independent from a source checkout and from any
cmux workspace.  The installed package starts a detached, read-capable HTTP
service; a separate cmux-owned router supplies only window-launch capability.
Closing a workspace must not stop Papers, Fields, or file operations.  The
service publishes an ephemeral port in a private runtime record and proves
identity through health before stop or replacement.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholar_workflow import __version__
from scholar_workflow.config import DEFAULT_HOME

DISCOVERY_SCHEMA_VERSION = 1
HUB_PROTOCOL_VERSION = 3
SERVICE_NAME = "scholar-workflow-hub"
_GENERATION_RE = re.compile(r"^service_[A-Za-z0-9_-]{16,128}$")
_BUILD_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_DISCOVERY_BYTES = 32 * 1024
_START_TIMEOUT_SECONDS = 10.0
_STOP_TIMEOUT_SECONDS = 8.0
_POLL_SECONDS = 0.05


class HubLifecycleError(RuntimeError):
    """Base error for lifecycle operations."""


class HubNotRunning(HubLifecycleError):
    """No live managed Hub is available."""


class HubStartError(HubLifecycleError):
    """The managed Hub could not be started."""


class UnsafeManagedProcess(HubLifecycleError):
    """A live process cannot be proven to be the recorded managed Hub."""


@dataclass(frozen=True)
class HubDiscoveryRecord:
    """Private discovery information for one managed Hub process."""

    schema_version: int
    service_name: str
    pid: int
    port: int
    executable: str
    package_version: str
    build_hash: str
    protocol_version: int
    service_generation: str
    started_at: str
    log_path: str

    @classmethod
    def from_mapping(cls, value: object) -> HubDiscoveryRecord:
        if not isinstance(value, dict):
            raise TypeError("Hub discovery record must be a JSON object")
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            raise ValueError("Hub discovery record has unknown or missing fields")
        record = cls(**value)
        if record.schema_version != DISCOVERY_SCHEMA_VERSION:
            raise ValueError("Unsupported Hub discovery schema")
        if record.service_name != SERVICE_NAME:
            raise ValueError("Discovery record is not for Scholar Workflow Hub")
        if not isinstance(record.pid, int) or isinstance(record.pid, bool) or record.pid <= 1:
            raise ValueError("Invalid Hub PID")
        if (
            not isinstance(record.port, int)
            or isinstance(record.port, bool)
            or not 1 <= record.port <= 65535
        ):
            raise ValueError("Invalid Hub port")
        if not isinstance(record.executable, str) or not Path(record.executable).is_absolute():
            raise ValueError("Hub executable must be an absolute path")
        if not isinstance(record.package_version, str) or not record.package_version:
            raise ValueError("Hub package version is missing")
        if not isinstance(record.build_hash, str) or not _BUILD_RE.fullmatch(
            record.build_hash
        ):
            raise ValueError("Invalid Hub build hash")
        if (
            not isinstance(record.protocol_version, int)
            or isinstance(record.protocol_version, bool)
            or record.protocol_version < 1
        ):
            raise ValueError("Invalid Hub protocol version")
        if not isinstance(record.service_generation, str) or not _GENERATION_RE.fullmatch(
            record.service_generation
        ):
            raise ValueError("Invalid Hub service generation")
        if not isinstance(record.started_at, str) or not record.started_at:
            raise ValueError("Hub start time is missing")
        if not isinstance(record.log_path, str) or not Path(record.log_path).is_absolute():
            raise ValueError("Hub log path must be absolute")
        return record

    def as_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HubStatus:
    """Current lifecycle state with optional live health evidence."""

    running: bool
    record: HubDiscoveryRecord | None
    health: dict[str, Any] | None
    detail: str

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "running": self.running,
            "detail": self.detail,
        }
        if self.record is not None:
            payload.update(self.record.as_payload())
        if self.health is not None:
            payload["health"] = self.health
        return payload


def runtime_root() -> Path:
    """Return the host-local runtime directory without consulting a checkout."""
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)).expanduser().resolve()
    return home / "runtime"


def discovery_path() -> Path:
    return runtime_root() / "hub.json"


def lifecycle_log_path() -> Path:
    return runtime_root() / "hub.log"


def installed_build_hash() -> str:
    """Hash the imported package code, not a configured source-repository path."""
    package_root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    digest.update(f"scholar-workflow\0{__version__}\0".encode())
    try:
        paths = sorted(package_root.rglob("*.py"))
    except OSError:
        paths = []
    for path in paths:
        try:
            relative = path.relative_to(package_root).as_posix()
            content = path.read_bytes()
        except OSError:
            continue
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _ensure_runtime_root(root: Path | None = None) -> Path:
    root = root or runtime_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def write_discovery(record: HubDiscoveryRecord, path: Path | None = None) -> None:
    """Atomically publish a mode-0600 runtime record."""
    destination = path or discovery_path()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(record.as_payload(), ensure_ascii=False, sort_keys=True).encode()
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_discovery(path: Path | None = None) -> HubDiscoveryRecord | None:
    source = path or discovery_path()
    try:
        metadata = source.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise UnsafeManagedProcess("Hub discovery record must be a regular file")
    if metadata.st_size > _MAX_DISCOVERY_BYTES:
        raise UnsafeManagedProcess("Hub discovery record is unexpectedly large")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        return HubDiscoveryRecord.from_mapping(payload)
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise UnsafeManagedProcess(f"Invalid Hub discovery record: {exc}") from None


def remove_discovery_if_owned(record: HubDiscoveryRecord, path: Path | None = None) -> bool:
    destination = path or discovery_path()
    current = load_discovery(destination)
    if current is None:
        return False
    if (
        current.pid != record.pid
        or current.service_generation != record.service_generation
    ):
        return False
    destination.unlink(missing_ok=True)
    return True


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _request_json(
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 1.5,
) -> tuple[int, dict[str, Any] | None]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        content = response.read(65537)
        status_code = response.status
    except (OSError, http.client.HTTPException):
        return 0, None
    finally:
        connection.close()
    if len(content) > 65536:
        return status_code, None
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status_code, None
    return status_code, payload if isinstance(payload, dict) else None


def probe_health(port: int) -> dict[str, Any] | None:
    """Prove identity without depending on slow optional diagnostics."""
    status_code, payload = _request_json(port, "/api/v3/identity")
    if status_code == 200:
        return payload if payload is not None and payload.get("status") == "ok" else None
    if status_code not in {404, 405, 501}:
        return None
    # Older managed builds do not have an identity-only endpoint.  Preserve
    # their health proof during replacement without using detailed v3 health
    # as the normal v3 lifecycle gate.
    for path in ("/api/v3/health", "/api/v2/health"):
        status_code, payload = _request_json(port, path)
        if status_code == 200 and payload is not None and payload.get("status") == "ok":
            return payload
        if status_code not in {404, 405, 501}:
            return None
    return None


def probe_diagnostics(port: int) -> dict[str, Any] | None:
    """Read detailed health after proving identity; never use it to authorize lifecycle actions."""
    identity = probe_health(port)
    if identity is None:
        return None
    if isinstance(identity.get("hub_directory"), dict):
        # An older managed build returned its detailed health as identity proof.
        return identity
    for path in ("/api/v3/health", "/api/v2/health"):
        status_code, payload = _request_json(port, path, timeout=3.0)
        if status_code == 200 and payload is not None and payload.get("status") == "ok":
            service = payload.get("service")
            process = payload.get("process")
            identity_service = identity.get("service")
            identity_process = identity.get("process")
            if (
                isinstance(service, dict)
                and isinstance(process, dict)
                and isinstance(identity_service, dict)
                and isinstance(identity_process, dict)
                and service.get("name") == identity_service.get("name") == SERVICE_NAME
                and process.get("pid") == identity_process.get("pid")
                and payload.get("service_generation") == identity.get("service_generation")
            ):
                return payload
            return None
        if status_code not in {404, 405, 501}:
            return None
    return None


def health_matches_record(
    record: HubDiscoveryRecord,
    health: dict[str, Any] | None,
) -> bool:
    if health is None:
        return False
    service = health.get("service")
    process = health.get("process")
    protocol = health.get("protocol")
    if (
        not isinstance(service, dict)
        or service.get("name") != SERVICE_NAME
        or service.get("version") != record.package_version
    ):
        return False
    if (
        not isinstance(process, dict)
        or process.get("pid") != record.pid
        or process.get("executable") != record.executable
    ):
        return False
    if not isinstance(protocol, dict) or protocol.get("version") != record.protocol_version:
        return False
    return health.get("service_generation") == record.service_generation


@contextmanager
def lifecycle_lock(root: Path | None = None) -> Iterator[None]:
    """Serialize lifecycle transitions across concurrent CLI invocations."""
    import fcntl

    root = _ensure_runtime_root(root)
    path = root / "hub.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(descriptor, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _service_environment() -> dict[str, str]:
    # A detached process loses cmux ancestry after its launcher exits.  Do not
    # pass a socket that can appear to work briefly but later denies routing.
    allowed = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    configured_home = os.environ.get("SCHOLAR_WORKFLOW_HOME")
    if configured_home:
        environment["SCHOLAR_WORKFLOW_HOME"] = configured_home
    return environment


def _installed_cli_executable() -> Path:
    """Resolve the console script paired with the imported installed package."""
    beside_python = Path(sys.executable).resolve().parent / "scholar-workflow"
    candidates: list[Path] = []
    invoked = Path(sys.argv[0]).expanduser()
    if invoked.name == "scholar-workflow":
        try:
            candidates.append(invoked.resolve(strict=True))
        except OSError:
            pass
    candidates.append(beside_python)
    from_path = shutil.which("scholar-workflow")
    if from_path:
        candidates.append(Path(from_path).resolve())
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise HubStartError(
        "The installed scholar-workflow console script could not be resolved"
    )


def _read_log_tail(path: Path, limit: int = 2000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit).decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


class HubServiceManager:
    """Start, inspect, and stop the single host-local managed Hub service."""

    def __init__(self, *, record_path: Path | None = None) -> None:
        self.record_path = (record_path or discovery_path()).expanduser().resolve()

    def status(self) -> HubStatus:
        record = load_discovery(self.record_path)
        if record is None:
            return HubStatus(False, None, None, "managed Hub is stopped")
        if not process_exists(record.pid):
            return HubStatus(False, record, None, "stale discovery record; process is gone")
        health = probe_health(record.port)
        if not health_matches_record(record, health):
            return HubStatus(
                False,
                record,
                health,
                "live PID or port cannot be proven as the recorded managed Hub",
            )
        return HubStatus(True, record, health, "managed Hub is running")

    def ensure_running(self) -> HubDiscoveryRecord:
        with lifecycle_lock(self.record_path.parent):
            return self._ensure_running_locked()

    def start(self) -> HubDiscoveryRecord:
        return self.ensure_running()

    def _ensure_running_locked(self) -> HubDiscoveryRecord:
        status = self.status()
        desired_build = installed_build_hash()
        if status.running and status.record is not None:
            record = status.record
            if (
                record.package_version == __version__
                and record.build_hash == desired_build
                and record.protocol_version == HUB_PROTOCOL_VERSION
            ):
                return record
            self._stop_record(record, status.health)
        elif status.record is not None:
            if process_exists(status.record.pid):
                raise UnsafeManagedProcess(status.detail)
            remove_discovery_if_owned(status.record, self.record_path)

        root = _ensure_runtime_root(self.record_path.parent)
        log_path = (root / "hub.log").resolve()
        executable = str(_installed_cli_executable())
        log_flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            log_flags |= os.O_NOFOLLOW
        try:
            log_descriptor = os.open(log_path, log_flags, 0o600)
        except OSError as exc:
            raise HubStartError(f"Could not open private Hub log: {exc}") from None
        metadata = os.fstat(log_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(log_descriptor)
            raise HubStartError("Hub log path is not a regular file")
        os.fchmod(log_descriptor, 0o600)
        generation = f"service_{hashlib.sha256(os.urandom(32)).hexdigest()[:32]}"
        argv = [
            executable,
            "_hub-service",
            "--generation",
            generation,
            "--discovery",
            str(self.record_path.resolve()),
            "--log",
            str(log_path),
        ]
        with os.fdopen(log_descriptor, "ab", buffering=0) as output:
            try:
                child = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=output,
                    cwd=str(root),
                    env=_service_environment(),
                    shell=False,
                    start_new_session=True,
                    close_fds=True,
                )
            except OSError as exc:
                raise HubStartError(f"Could not launch managed Hub: {exc}") from None

        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if child.poll() is not None:
                detail = _read_log_tail(log_path)
                suffix = f": {detail}" if detail else ""
                raise HubStartError(
                    f"Managed Hub exited during startup with status {child.returncode}{suffix}"
                )
            try:
                record = load_discovery(self.record_path)
            except UnsafeManagedProcess:
                record = None
            if (
                record is not None
                and record.pid == child.pid
                and record.service_generation == generation
                and record.package_version == __version__
                and record.build_hash == desired_build
                and record.protocol_version == HUB_PROTOCOL_VERSION
            ):
                health = probe_health(record.port)
                if health_matches_record(record, health):
                    return record
            time.sleep(_POLL_SECONDS)

        try:
            child.terminate()
        except OSError:
            pass
        try:
            child.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
        detail = _read_log_tail(log_path)
        suffix = f": {detail}" if detail else ""
        raise HubStartError(f"Managed Hub did not become healthy in time{suffix}")

    def stop(self) -> bool:
        with lifecycle_lock(self.record_path.parent):
            record = load_discovery(self.record_path)
            if record is None:
                return False
            if not process_exists(record.pid):
                remove_discovery_if_owned(record, self.record_path)
                return False
            health = probe_health(record.port)
            if not health_matches_record(record, health):
                raise UnsafeManagedProcess(
                    "Refusing to stop a live process that cannot prove the recorded "
                    "Scholar Workflow service generation"
                )
            self._stop_record(record, health)
            return True

    def _stop_record(
        self,
        record: HubDiscoveryRecord,
        health: dict[str, Any] | None,
    ) -> None:
        if not health_matches_record(record, health):
            raise UnsafeManagedProcess("Refusing to stop an unverified process")
        try:
            os.kill(record.pid, signal.SIGTERM)
        except ProcessLookupError:
            remove_discovery_if_owned(record, self.record_path)
            return
        except PermissionError:
            raise UnsafeManagedProcess("Permission denied while stopping managed Hub") from None
        deadline = time.monotonic() + _STOP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if not process_exists(record.pid):
                remove_discovery_if_owned(record, self.record_path)
                return
            time.sleep(_POLL_SECONDS)
        raise HubLifecycleError(
            "Managed Hub did not stop after SIGTERM; discovery record was retained"
        )

    def restart(self) -> HubDiscoveryRecord:
        with lifecycle_lock(self.record_path.parent):
            record = load_discovery(self.record_path)
            if record is not None:
                if process_exists(record.pid):
                    health = probe_health(record.port)
                    if not health_matches_record(record, health):
                        raise UnsafeManagedProcess(
                            "Refusing to restart because the recorded live process "
                            "cannot prove its identity"
                        )
                    self._stop_record(record, health)
                else:
                    remove_discovery_if_owned(record, self.record_path)
            return self._ensure_running_locked()


__all__ = [
    "DISCOVERY_SCHEMA_VERSION",
    "HUB_PROTOCOL_VERSION",
    "SERVICE_NAME",
    "HubDiscoveryRecord",
    "HubLifecycleError",
    "HubNotRunning",
    "HubServiceManager",
    "HubStartError",
    "HubStatus",
    "UnsafeManagedProcess",
    "discovery_path",
    "health_matches_record",
    "installed_build_hash",
    "lifecycle_log_path",
    "load_discovery",
    "probe_diagnostics",
    "probe_health",
    "process_exists",
    "remove_discovery_if_owned",
    "runtime_root",
    "utc_now",
    "write_discovery",
]
