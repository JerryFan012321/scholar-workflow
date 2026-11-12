"""Private, profile-separated lifecycle for the recommendation page only."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import socket
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scholar_workflow import __version__
from scholar_workflow.research.models import ResearchError


def build_id() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".html", ".css", ".js", ".json"}:
            digest.update(str(path.relative_to(Path(__file__).parent)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def ensure_private_dir(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if current.is_symlink() or not current.is_dir():
            raise ResearchError("Recommendation state path is unsafe.", 7)
    os.chmod(absolute, 0o700)


def _read_runtime(state_dir: Path) -> dict | None:
    path = state_dir / "runtime.json"
    if not path.exists() and not path.is_symlink():
        return None
    # Validate ancestors without creating anything on read-only status calls.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ResearchError("Recommendation runtime path is unsafe.", 7)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ResearchError("Recommendation runtime record is not private.", 7)
            raw = stream.read(16385)
        record = json.loads(raw) if len(raw) <= 16384 else None
        if not isinstance(record, dict) or set(record) != {
            "generation", "pid", "port", "token", "profile", "version", "build",
            "started_at", "executable",
        }:
            raise ValueError()
        if (type(record["pid"]) is not int or record["pid"] <= 0
                or type(record["port"]) is not int or not 1 <= record["port"] <= 65535
                or not isinstance(record["token"], str) or len(record["token"]) < 32
                or not isinstance(record["generation"], str) or len(record["generation"]) < 16
                or record["profile"] not in {"personal", "test"}):
            raise ValueError()
        return record
    except FileNotFoundError:
        # The owned service can remove its record while shutdown is being observed.
        return None
    except (OSError, ValueError, TypeError, KeyError):
        raise ResearchError("Recommendation runtime record is invalid or unavailable.", 7) from None


def _write_runtime(state_dir: Path, record: dict) -> None:
    temporary = state_dir / (".runtime-" + secrets.token_hex(12))
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        target = state_dir / "runtime.json"
        if target.is_symlink():
            raise ResearchError("Recommendation runtime path is unsafe.", 7)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _health(record: dict) -> dict | None:
    try:
        with httpx.Client(trust_env=False, timeout=1.5, follow_redirects=False) as client:
            response = client.get(f"http://127.0.0.1:{record['port']}/health")
            response.raise_for_status()
            payload = response.json()
        if all(payload.get(key) == record[key] for key in
               ("generation", "pid", "profile", "version", "build")):
            return payload
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def status(state_dir: Path, profile: str) -> dict:
    from scholar_workflow.research.recommendations import background

    manager = background.status(state_dir, profile)
    record = _read_runtime(state_dir)
    port = _desired_port(state_dir, profile)
    if record is None:
        return {"status": "stopped", "profile": profile, **manager,
                "port": port or None, "url": f"http://127.0.0.1:{port}/" if port else None}
    if record["profile"] != profile:
        raise ResearchError("Recommendation runtime belongs to another profile.", 7)
    health = _health(record)
    return {"status": "running" if health else "unavailable", "profile": profile, **manager,
            "pid": record["pid"], "port": record["port"], "version": record["version"],
            "build": record["build"], "started_at": record["started_at"],
            "executable": record["executable"],
            "log_path": str(state_dir / "service.log"),
            "url": f"http://127.0.0.1:{record['port']}/",
            "current_build": bool(health and record["version"] == __version__
                                  and record["build"] == build_id())}


def _desired_port(state_dir: Path, profile: str, requested: int | None = None) -> int:
    if requested is not None:
        if type(requested) is not int or not 1024 <= requested <= 65535:
            raise ResearchError("Choose a local port between 1024 and 65535.")
        return requested
    path = state_dir / "endpoint.json"
    if path.exists() or path.is_symlink():
        try:
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError()
                content = json.loads(stream.read(1025))
            if (set(content) != {"port"} or type(content["port"]) is not int
                    or not 1024 <= content["port"] <= 65535):
                raise ValueError()
            return content["port"]
        except (OSError, ValueError, TypeError, KeyError):
            raise ResearchError("Recommendation endpoint record is unsafe or invalid.", 7) from None
    if profile == "personal":
        return 61201
    record = _read_runtime(state_dir)
    return record["port"] if record else 0


def _save_port(state_dir: Path, port: int) -> None:
    # Persist only the port, independently from the replaceable process identity.
    temporary = state_dir / (".endpoint-" + secrets.token_hex(12))
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"port": port}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        target = state_dir / "endpoint.json"
        if target.is_symlink():
            raise ResearchError("Recommendation endpoint path is unsafe.", 7)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _check_port(port: int) -> None:
    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
    except OSError:
        raise ResearchError(f"Local port {port} is occupied. No unrelated process was stopped; "
                            "choose another port with recommendations start --port PORT.", 3) from None


@contextmanager
def _lifecycle_lock(state_dir: Path):
    ensure_private_dir(state_dir)
    fd = os.open(state_dir / "lifecycle.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ResearchError("Recommendation lifecycle lock is unsafe.", 7)
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _stop_record(state_dir: Path, record: dict) -> None:
    if _health(record) is None:
        if _alive(record["pid"]):
            raise ResearchError("Cannot identify the recorded service; no process was stopped.", 7)
    else:
        url = f"http://127.0.0.1:{record['port']}"
        try:
            with httpx.Client(trust_env=False, timeout=2, follow_redirects=False) as client:
                response = client.post(url + "/api/shutdown", json={}, headers={
                    "Authorization": "Bearer " + record["token"], "Origin": url,
                })
                response.raise_for_status()
        except httpx.HTTPError:
            raise ResearchError("The identified recommendation service did not stop.", 3) from None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _health(record) is None:
                break
            time.sleep(0.05)
        else:
            raise ResearchError("Recommendation service shutdown timed out.", 3)
    current = _read_runtime(state_dir)
    if current and current["generation"] == record["generation"]:
        (state_dir / "runtime.json").unlink(missing_ok=True)


def stop(state_dir: Path, profile: str) -> dict:
    from scholar_workflow.research.recommendations import background

    if not state_dir.exists():
        background.remove(state_dir, profile)
        return {"status": "stopped", "profile": profile}
    with _lifecycle_lock(state_dir):
        record = _read_runtime(state_dir)
        if record:
            if record["profile"] != profile:
                raise ResearchError("Recommendation runtime belongs to another profile.", 7)
            _stop_record(state_dir, record)
        background.remove(state_dir, profile)
    return {"status": "stopped", "profile": profile}


def start(state_dir: Path, profile: str, port: int | None = None) -> dict:
    from scholar_workflow.research.recommendations import background

    with _lifecycle_lock(state_dir):
        selected_port = _desired_port(state_dir, profile, port)
        managed = background.supported(profile)
        record = _read_runtime(state_dir)
        if record:
            if record["profile"] != profile:
                raise ResearchError("Recommendation runtime belongs to another profile.", 7)
            if (_health(record) and record["version"] == __version__
                    and record["build"] == build_id() and record["port"] == selected_port
                    and (not managed or background.status(state_dir, profile)["supervised"])):
                return record
            if selected_port and record["port"] != selected_port:
                _check_port(selected_port)
            _stop_record(state_dir, record)
        background.remove(state_dir, profile)
        if selected_port:
            _check_port(selected_port)
            _save_port(state_dir, selected_port)
        if managed:
            background.install(state_dir)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                record = _read_runtime(state_dir)
                if (record and _health(record) and record["version"] == __version__
                        and record["build"] == build_id() and record["port"] == selected_port):
                    return record
                time.sleep(0.1)
            raise ResearchError("Login service did not become ready; inspect status and the service log.", 3)
        generation, token = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        # No repository path or shell expression is needed to run the installed package.
        log_fd = os.open(state_dir / "service.log", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(log_fd).st_mode):
                raise ResearchError("Recommendation service log is unsafe.", 7)
            os.fchmod(log_fd, 0o600)
            process = subprocess.Popen(
                [sys.executable, "-m", "scholar_workflow.research.recommendations.cli",
                 "--profile", profile, "serve"],
                stdin=subprocess.PIPE, stdout=log_fd, stderr=log_fd,
                start_new_session=True, shell=False,
            )
        finally:
            os.close(log_fd)
        try:
            process.communicate(json.dumps({"generation": generation, "token": token}).encode(),
                                timeout=0.05)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            record = _read_runtime(state_dir)
            if record and record["generation"] == generation and _health(record):
                return record
            if process.poll() is not None:
                break
            time.sleep(0.05)
        # This Popen handle proves ownership even if startup never created a record.
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        raise ResearchError("Recommendation page failed to start; run status before retrying.", 3)


def serve(state_dir: Path, profile: str, credentials: dict) -> None:
    if (set(credentials) != {"generation", "token"}
            or not all(isinstance(value, str) and len(value) >= 32
                       for value in credentials.values())):
        raise ResearchError("Recommendation service credentials are invalid.", 7)
    ensure_private_dir(state_dir)
    # Held for the server's lifetime, independently from the caller's lifecycle lock.
    lock = os.open(state_dir / "server.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise ResearchError("Recommendation server lock is unsafe.", 7)
        os.fchmod(lock, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ResearchError):
        os.close(lock)
        raise ResearchError("Another service owns this recommendation pool.", 7) from None
    try:
        _serve_locked(state_dir, profile, credentials)
    finally:
        os.close(lock)


def _serve_locked(state_dir: Path, profile: str, credentials: dict) -> None:
    from scholar_workflow.research.recommendations.server import create_server

    try:
        server = create_server(state_dir, profile, credentials["token"],
                               port=_desired_port(state_dir, profile))
    except OSError:
        raise ResearchError("The saved recommendation port is unavailable; no alternate URL was chosen.", 3) from None
    _save_port(state_dir, server.server_address[1])
    record = {**credentials, "pid": os.getpid(), "port": server.server_address[1],
              "profile": profile, "version": __version__, "build": build_id(),
              "started_at": datetime.now(UTC).isoformat(), "executable": sys.executable}
    server.runtime_identity = {key: record[key] for key in
                               ("generation", "pid", "profile", "version", "build")}
    _write_runtime(state_dir, record)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        current = _read_runtime(state_dir)
        if current and current["generation"] == record["generation"]:
            (state_dir / "runtime.json").unlink(missing_ok=True)
