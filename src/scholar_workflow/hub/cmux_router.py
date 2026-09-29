"""Private cmux RPC bridge for a detached Hub service.

The router lives in a cmux terminal and retains that terminal's socket access.
The HTTP service never receives a cmux socket or an arbitrary shell endpoint.
"""
from __future__ import annotations

import argparse
import fcntl
import hmac
import json
import os
import re
import secrets
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scholar_workflow.hub.cmux import CmuxControl, CmuxControlError
from scholar_workflow.hub.lifecycle import HubLifecycleError, load_discovery

_GENERATION = re.compile(r"^service_[A-Za-z0-9_-]{16,128}$")
_PRIVATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_ROUTER_ID = re.compile(r"^[0-9a-f]{32}$")
_RECORD_NAME = "hub-router.json"
_LOCK_NAME = "hub-router.lock"
_MAX_RECORD = 4096
_MAX_REQUEST = 16 * 1024
_MAX_RESPONSE = 2 * 1024 * 1024
_RPC_TIMEOUT = 8.0
_READINESS_TIMEOUT = 0.5
_START_TIMEOUT = 10.0
_POLL_INTERVAL = 0.05


def _checked_root(root: Path, *, create: bool) -> Path:
    path = Path(root).expanduser()
    if not path.is_absolute():
        raise CmuxControlError("router runtime root must be absolute")
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        info = path.lstat()
    except OSError as exc:
        raise CmuxControlError("router runtime root is unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
        raise CmuxControlError("router runtime root is not a trusted directory")
    if stat.S_IMODE(info.st_mode) != 0o700:
        if not create:
            raise CmuxControlError("router runtime root must have mode 0700")
        path.chmod(0o700)
    return path.resolve(strict=True)


def _socket_directory(root: Path, *, create: bool) -> Path:
    # Darwin limits Unix socket paths to roughly 104 bytes. A long isolated
    # SCHOLAR_WORKFLOW_HOME still needs a private, discoverable socket address.
    candidate = root / "r.0123456789abcdef.sock"
    if len(os.fsencode(candidate)) <= 100:
        return root
    import hashlib

    suffix = hashlib.sha256(os.fsencode(root)).hexdigest()[:12]
    short = Path(tempfile.gettempdir()) / f"sw-router-{os.getuid()}-{suffix}"
    if len(os.fsencode(short.resolve() / "r.0123456789abcdef.sock")) > 100:
        short = Path("/tmp") / f"sw-r-{os.getuid()}-{suffix}"
    return _checked_root(short, create=create)


def _record_path(root: Path) -> Path:
    return root / _RECORD_NAME


def _read_record(root: Path) -> dict[str, Any] | None:
    path = _record_path(root)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size > _MAX_RECORD
    ):
        raise CmuxControlError("router record is not a trusted private file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                info.st_dev,
                info.st_ino,
            ):
                raise CmuxControlError("router record changed during read")
            data = os.read(descriptor, _MAX_RECORD + 1)
        finally:
            os.close(descriptor)
        if len(data) > _MAX_RECORD:
            raise CmuxControlError("router record is too large")
        value = json.loads(data)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise CmuxControlError("router record is invalid") from exc
    expected = {
        "schema_version",
        "service_generation",
        "router_id",
        "pid",
        "socket_path",
        "auth_token",
        "instance_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != 1:
        raise CmuxControlError("router record has an invalid schema")
    if (
        not isinstance(value["service_generation"], str)
        or not _GENERATION.fullmatch(value["service_generation"])
        or not isinstance(value["router_id"], str)
        or not _ROUTER_ID.fullmatch(value["router_id"])
        or not isinstance(value["auth_token"], str)
        or not _HEX_TOKEN.fullmatch(value["auth_token"])
        or not isinstance(value["instance_fingerprint"], str)
        or not _FINGERPRINT.fullmatch(value["instance_fingerprint"])
        or type(value["pid"]) is not int
        or value["pid"] <= 1
        or not isinstance(value["socket_path"], str)
        or not Path(value["socket_path"]).is_absolute()
    ):
        raise CmuxControlError("router record contains invalid values")
    socket_path = Path(value["socket_path"])
    expected_dir = _socket_directory(root, create=False)
    if socket_path.parent != expected_dir or socket_path.name != f"r.{value['router_id'][:16]}.sock":
        raise CmuxControlError("router socket is outside its private directory")
    return value


def _write_record(root: Path, record: dict[str, Any]) -> None:
    destination = _record_path(root)
    content = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    if len(content) > _MAX_RECORD:
        raise CmuxControlError("router record is too large")
    descriptor, name = tempfile.mkstemp(prefix=".hub-router.", dir=root)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_if_owned(root: Path, router_id: str) -> None:
    try:
        record = _read_record(root)
    except CmuxControlError:
        return
    if record is not None and record["router_id"] == router_id:
        _record_path(root).unlink(missing_ok=True)


def _service_is_current(root: Path, generation: str) -> bool:
    try:
        record = load_discovery(root / "hub.json")
    except (OSError, ValueError, HubLifecycleError):
        return False
    return record is not None and record.service_generation == generation


def _clean_string(value: object, name: str, *, limit: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CmuxControlError(f"invalid {name}")
    return value


def _working_directory(value: object) -> Path:
    raw = _clean_string(value, "working directory")
    path = Path(raw)
    if not path.is_absolute() or not path.is_dir():
        raise CmuxControlError("working directory must be an existing absolute directory")
    return path.resolve(strict=True)


def _open_target(value: object) -> str:
    target = _clean_string(value, "open target")
    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.username:
        return target
    path = Path(target)
    if path.is_absolute() and path.is_file():
        return str(path.resolve(strict=True))
    raise CmuxControlError("open target must be an HTTP(S) URL or existing absolute file")


def _worker_command(value: object, root: Path) -> str:
    command = _clean_string(value, "terminal worker command")
    try:
        arguments = shlex.split(command)
    except ValueError as exc:
        raise CmuxControlError("terminal worker command is malformed") from exc
    if len(arguments) != 9 or arguments[1:4] != [
        "-m",
        "scholar_workflow.hub.terminal_worker",
        "--state-root",
    ] or arguments[5] != "--slot" or arguments[7] != "--generation":
        raise CmuxControlError("terminal worker command is not an allowed recipe")
    executable = Path(arguments[0])
    state_root = Path(arguments[4])
    if (
        not executable.is_absolute()
        or executable.resolve() != Path(sys.executable).resolve()
        or not state_root.is_absolute()
        or state_root.resolve() != (root.parent / "hub" / "task-worker").resolve()
        or not _PRIVATE_ID.fullmatch(arguments[6])
        or not _PRIVATE_ID.fullmatch(arguments[8])
    ):
        raise CmuxControlError("terminal worker command is not an allowed recipe")
    return shlex.join(arguments)


def _receive(connection: socket.socket, limit: int) -> dict[str, Any]:
    chunks = bytearray()
    while len(chunks) <= limit:
        part = connection.recv(min(4096, limit + 1 - len(chunks)))
        if not part:
            break
        chunks.extend(part)
        if b"\n" in part:
            break
    if len(chunks) > limit or not chunks.endswith(b"\n"):
        raise CmuxControlError("router RPC message is too large or incomplete")
    try:
        value = json.loads(chunks[:-1])
    except (ValueError, UnicodeDecodeError) as exc:
        raise CmuxControlError("router RPC message is invalid JSON") from exc
    if not isinstance(value, dict):
        raise CmuxControlError("router RPC message must be an object")
    return value


def _send(connection: socket.socket, response: dict[str, Any]) -> None:
    encoded = json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
    if len(encoded) > _MAX_RESPONSE:
        encoded = b'{"ok":false,"error":"router response exceeded size limit"}\n'
    connection.sendall(encoded)


def _dispatch(
    control: CmuxControl,
    root: Path,
    record: dict[str, Any],
    request: dict[str, Any],
    stop_signal: threading.Event,
) -> Any:
    if set(request) != {"generation", "auth", "method", "params"}:
        raise CmuxControlError("invalid router RPC envelope")
    if (
        not isinstance(request["generation"], str)
        or not hmac.compare_digest(request["generation"], record["service_generation"])
        or not isinstance(request["auth"], str)
        or not hmac.compare_digest(request["auth"], record["auth_token"])
    ):
        raise CmuxControlError("router authentication failed")
    method = request["method"]
    params = request["params"]
    if not isinstance(method, str) or not isinstance(params, dict):
        raise CmuxControlError("invalid router RPC operation")
    if method == "shutdown" and not params:
        stop_signal.set()
        return {"stopping": True}
    current = _read_record(root)
    if (
        current is None
        or current["router_id"] != record["router_id"]
        or not _service_is_current(root, record["service_generation"])
    ):
        raise CmuxControlError("cmux router generation or ownership changed")
    if control.instance_fingerprint() != record["instance_fingerprint"]:
        raise CmuxControlError("cmux instance changed")
    if method == "ping" and not params:
        control.tree_all()
        return {
            "service_generation": record["service_generation"],
            "router_id": record["router_id"],
            "instance_fingerprint": record["instance_fingerprint"],
        }
    if method == "tree_all" and not params:
        return control.tree_all()
    if method == "instance_fingerprint" and not params:
        return record["instance_fingerprint"]
    if method == "open" and set(params) == {"target", "workspace_id"}:
        target = _open_target(params["target"])
        workspace = _clean_string(params["workspace_id"], "workspace ID", limit=256)
        control.open(target, workspace_id=workspace)
        return {"returncode": 0}
    if method == "new_codex_session" and set(params) == {
        "workspace_id", "working_directory"
    }:
        workspace = _clean_string(params["workspace_id"], "workspace ID", limit=256)
        cwd = _working_directory(params["working_directory"])
        control.new_codex_session(workspace_id=workspace, working_directory=cwd)
        return {"returncode": 0}
    if method == "new_terminal_worker" and set(params) == {
        "workspace_id", "working_directory", "command", "focus"
    }:
        workspace = _clean_string(params["workspace_id"], "workspace ID", limit=256)
        cwd = _working_directory(params["working_directory"])
        command = _worker_command(params["command"], root)
        if type(params["focus"]) is not bool:
            raise CmuxControlError("terminal focus must be boolean")
        control.new_terminal_worker(
            workspace_id=workspace,
            working_directory=cwd,
            command=command,
            focus=params["focus"],
        )
        return {"returncode": 0}
    raise CmuxControlError("unknown or invalid router RPC operation")


class RouterControl:
    """CmuxControl-compatible client for the current private router record."""

    def __init__(self, runtime_root: Path, service_generation: str) -> None:
        if not isinstance(service_generation, str) or not _GENERATION.fullmatch(service_generation):
            raise CmuxControlError("invalid Hub service generation")
        self.runtime_root = Path(runtime_root).expanduser()
        self.service_generation = service_generation

    def _call(
        self, method: str, params: dict[str, Any], *, timeout: float = _RPC_TIMEOUT
    ) -> Any:
        root = _checked_root(self.runtime_root, create=False)
        record = _read_record(root)
        if record is None or record["service_generation"] != self.service_generation:
            raise CmuxControlError("cmux router is unavailable for this Hub generation")
        path = Path(record["socket_path"])
        try:
            info = path.lstat()
        except OSError as exc:
            raise CmuxControlError("cmux router socket is unavailable") from exc
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise CmuxControlError("cmux router socket is not trusted")
        request = {
            "generation": self.service_generation,
            "auth": record["auth_token"],
            "method": method,
            "params": params,
        }
        encoded = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > _MAX_REQUEST:
            raise CmuxControlError("router RPC request is too large")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(timeout)
                connection.connect(str(path))
                connection.sendall(encoded)
                response = _receive(connection, _MAX_RESPONSE)
        except (OSError, TimeoutError) as exc:
            raise CmuxControlError("cmux router is unavailable") from exc
        if set(response) == {"ok", "result"} and response["ok"] is True:
            return response["result"]
        if set(response) == {"ok", "error"} and response["ok"] is False:
            raise CmuxControlError(_clean_string(response["error"], "router error", limit=500))
        raise CmuxControlError("cmux router returned an invalid response")

    def ping(self) -> dict[str, str]:
        result = self._call("ping", {})
        if not isinstance(result, dict) or set(result) != {
            "service_generation", "router_id", "instance_fingerprint"
        }:
            raise CmuxControlError("cmux router returned an invalid ping")
        if result["service_generation"] != self.service_generation:
            raise CmuxControlError("cmux router generation changed")
        return result

    def tree_all(self) -> Any:
        result = self._call("tree_all", {})
        if not isinstance(result, (dict, list)):
            raise CmuxControlError("cmux router returned invalid workspace JSON")
        return result

    def instance_fingerprint(self) -> str:
        # Capability diagnostics must not stall the Directory or health page
        # behind a slow cmux tree/action request in this single-threaded router.
        result = self._call("instance_fingerprint", {}, timeout=_READINESS_TIMEOUT)
        if not isinstance(result, str) or not _FINGERPRINT.fullmatch(result):
            raise CmuxControlError("cmux router returned an invalid instance fingerprint")
        return result

    def open(self, target: str, *, workspace_id: str) -> subprocess.CompletedProcess[str]:
        self._call("open", {"target": target, "workspace_id": workspace_id})
        return subprocess.CompletedProcess([], 0, "", "")

    def new_terminal_worker(
        self,
        *,
        workspace_id: str,
        working_directory: Path,
        command: str,
        focus: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self._call(
            "new_terminal_worker",
            {
                "workspace_id": workspace_id,
                "working_directory": str(working_directory),
                "command": command,
                "focus": focus,
            },
        )
        return subprocess.CompletedProcess([], 0, "", "")

    def new_codex_session(
        self, *, workspace_id: str, working_directory: Path
    ) -> subprocess.CompletedProcess[str]:
        self._call(
            "new_codex_session",
            {"workspace_id": workspace_id, "working_directory": str(working_directory)},
        )
        return subprocess.CompletedProcess([], 0, "", "")

    def shutdown(self) -> None:
        result = self._call("shutdown", {})
        if result != {"stopping": True}:
            raise CmuxControlError("cmux router returned an invalid shutdown response")


def _socket_listener_absent(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise CmuxControlError("stale router socket is not trusted")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.5)
            connection.connect(str(path))
    except (FileNotFoundError, ConnectionRefusedError):
        return True
    except OSError as exc:
        raise CmuxControlError("cannot prove router socket is stale") from exc
    return False


def stop_router(runtime_root: Path, service_generation: str) -> bool:
    """Retire only the authenticated router for one Hub generation."""
    if not isinstance(service_generation, str) or not _GENERATION.fullmatch(service_generation):
        raise CmuxControlError("invalid Hub service generation")
    if not Path(runtime_root).exists():
        return False
    root = _checked_root(runtime_root, create=False)
    record = _read_record(root)
    if record is None or record["service_generation"] != service_generation:
        return False
    client = RouterControl(root, service_generation)
    try:
        client.shutdown()
    except CmuxControlError:
        current = _read_record(root)
        if current is None or current["router_id"] != record["router_id"]:
            return False
        socket_path = Path(record["socket_path"])
        if not _socket_listener_absent(socket_path):
            raise CmuxControlError("live cmux router did not accept shutdown") from None
        _remove_if_owned(root, record["router_id"])
        socket_path.unlink(missing_ok=True)
        return False
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        current = _read_record(root)
        if current is None or current["router_id"] != record["router_id"]:
            return True
        time.sleep(_POLL_INTERVAL)
    raise CmuxControlError("cmux router did not stop after authenticated shutdown")


@contextmanager
def _launch_lock(root: Path) -> Iterator[None]:
    path = root / _LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CmuxControlError("router launch lock is unavailable") from exc
    with os.fdopen(descriptor, "a+") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise CmuxControlError("router launch lock is not a regular file")
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ensure_router(
    runtime_root: Path,
    service_generation: str,
    workspace_id: str,
    executable: Path,
) -> RouterControl:
    """Reuse or launch a cmux-owned router for a detached service generation."""
    client = RouterControl(runtime_root, service_generation)
    root = _checked_root(runtime_root, create=True)
    workspace = _clean_string(workspace_id, "workspace ID", limit=256)
    cli = Path(executable)
    if not cli.is_absolute() or not cli.is_file() or not os.access(cli, os.X_OK):
        raise CmuxControlError("installed Scholar Workflow CLI is unavailable")
    control = CmuxControl()
    expected_fingerprint = control.instance_fingerprint()
    if not _service_is_current(root, service_generation):
        raise CmuxControlError("managed Hub generation changed before router launch")
    with _launch_lock(root):
        try:
            ready = client.ping()
        except CmuxControlError:
            ready = None
        if ready is not None and ready["instance_fingerprint"] == expected_fingerprint:
            client.tree_all()
            return client
        command = "exec " + shlex.join(
            [str(cli.resolve(strict=True)), "_hub-router", "--generation", service_generation,
             "--runtime-root", str(root)]
        )
        control.new_terminal_worker(
            workspace_id=workspace,
            working_directory=root,
            command=command,
            focus=False,
        )
        deadline = time.monotonic() + _START_TIMEOUT
        while time.monotonic() < deadline:
            try:
                ready = client.ping()
            except CmuxControlError:
                ready = None
            if ready is not None and ready["instance_fingerprint"] == expected_fingerprint:
                client.tree_all()
                return client
            time.sleep(_POLL_INTERVAL)
        raise CmuxControlError("cmux router did not become ready")


def _serve(
    root: Path,
    generation: str,
    *,
    control: CmuxControl | None = None,
    stop: threading.Event | None = None,
) -> None:
    if not _service_is_current(root, generation):
        raise CmuxControlError("managed Hub generation is no longer current")
    backend = control or CmuxControl()
    fingerprint = backend.instance_fingerprint()
    backend.tree_all()
    router_id = secrets.token_hex(16)
    socket_dir = _socket_directory(root, create=True)
    path = socket_dir / f"r.{router_id[:16]}.sock"
    record: dict[str, Any] = {
        "schema_version": 1,
        "service_generation": generation,
        "router_id": router_id,
        "pid": os.getpid(),
        "socket_path": str(path),
        "auth_token": secrets.token_hex(32),
        "instance_fingerprint": fingerprint,
    }
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stop_signal = stop or threading.Event()
    try:
        listener.bind(str(path))
        path.chmod(0o600)
        listener.listen(16)
        listener.settimeout(0.25)
        _write_record(root, record)
        while not stop_signal.is_set():
            if not _service_is_current(root, generation):
                break
            try:
                current = _read_record(root)
            except CmuxControlError:
                break
            if current is None or current["router_id"] != router_id:
                break
            try:
                connection, _address = listener.accept()
            except TimeoutError:
                continue
            with connection:
                connection.settimeout(_RPC_TIMEOUT)
                try:
                    request = _receive(connection, _MAX_REQUEST)
                    result = _dispatch(backend, root, record, request, stop_signal)
                    _send(connection, {"ok": True, "result": result})
                except (CmuxControlError, OSError, ValueError, TypeError) as exc:
                    try:
                        _send(connection, {"ok": False, "error": str(exc)[:500]})
                    except OSError:
                        pass
    finally:
        listener.close()
        path.unlink(missing_ok=True)
        _remove_if_owned(root, router_id)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private cmux router for a managed Hub")
    parser.add_argument("--generation", required=True)
    parser.add_argument("--runtime-root", required=True, type=Path)
    options = parser.parse_args(argv)
    if not _GENERATION.fullmatch(options.generation):
        raise CmuxControlError("invalid Hub service generation")
    root = _checked_root(options.runtime_root, create=True)
    try:
        _serve(root, options.generation)
    except KeyboardInterrupt:
        pass
    return 0


__all__ = ["RouterControl", "ensure_router", "run", "stop_router"]
