"""Private router contract: fixed cmux verbs, generation, and safe replacement."""
from __future__ import annotations

import json
import shlex
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scholar_workflow.hub import cmux_router
from scholar_workflow.hub.cmux import CmuxControlError

GENERATION = "service_1234567890abcdef"
FINGERPRINT = "sha256:" + "a" * 64


class FakeCmux:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def instance_fingerprint(self) -> str:
        return FINGERPRINT

    def tree_all(self) -> dict[str, object]:
        return {"workspaces": [{"id": "workspace:7"}]}

    def open(self, target: str, *, workspace_id: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(("open", target, workspace_id))
        return subprocess.CompletedProcess([], 0, "", "")

    def new_terminal_worker(
        self,
        *,
        workspace_id: str,
        working_directory: Path,
        command: str,
        focus: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(("terminal", workspace_id, working_directory, command, focus))
        return subprocess.CompletedProcess([], 0, "", "")

    def new_codex_session(
        self, *, workspace_id: str, working_directory: Path
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(("codex", workspace_id, working_directory))
        return subprocess.CompletedProcess([], 0, "", "")


def _start_router(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    backend: FakeCmux,
    *,
    previous_id: str | None = None,
) -> tuple[threading.Event, threading.Thread, cmux_router.RouterControl]:
    monkeypatch.setattr(cmux_router, "_service_is_current", lambda *_args: True)
    root = cmux_router._checked_root(root, create=True)
    stop = threading.Event()
    thread = threading.Thread(
        target=cmux_router._serve,
        args=(root, GENERATION),
        kwargs={"control": backend, "stop": stop},
        daemon=True,
    )
    thread.start()
    client = cmux_router.RouterControl(root, GENERATION)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            response = client.ping()
        except CmuxControlError:
            time.sleep(0.01)
        else:
            if response["router_id"] != previous_id:
                break
            time.sleep(0.01)
    else:
        stop.set()
        thread.join(2)
        pytest.fail("test router did not become ready")
    return stop, thread, client


def test_router_round_trip_uses_private_record_and_fixed_verbs(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    backend = FakeCmux()
    stop, thread, client = _start_router(monkeypatch, root, backend)
    try:
        record = cmux_router._read_record(root)
        assert record is not None
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE((root / "hub-router.json").stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(record["socket_path"]).stat().st_mode) == 0o600
        assert client.ping() == {
            "service_generation": GENERATION,
            "router_id": record["router_id"],
            "instance_fingerprint": FINGERPRINT,
        }
        assert client.instance_fingerprint() == FINGERPRINT
        assert client.tree_all() == {"workspaces": [{"id": "workspace:7"}]}
        document = tmp_path / "document.txt"
        document.write_text("test", encoding="utf-8")
        client.open(str(document), workspace_id="workspace:7")
        client.new_codex_session(workspace_id="workspace:7", working_directory=tmp_path)

        state_root = tmp_path / "hub" / "task-worker"
        command = shlex.join(
            [
                str(Path(sys.executable).resolve()),
                "-m",
                "scholar_workflow.hub.terminal_worker",
                "--state-root",
                str(state_root),
                "--slot",
                "slot_123",
                "--generation",
                "worker_123",
            ]
        )
        client.new_terminal_worker(
            workspace_id="workspace:7",
            working_directory=tmp_path,
            command=command,
            focus=False,
        )
        assert backend.calls == [
            ("open", str(document), "workspace:7"),
            ("codex", "workspace:7", tmp_path),
            ("terminal", "workspace:7", tmp_path, command, False),
        ]
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive()
    assert cmux_router._read_record(root) is None
    assert not Path(record["socket_path"]).exists()


def test_router_rejects_wrong_generation_auth_and_shell_recipe(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    backend = FakeCmux()
    stop, thread, client = _start_router(monkeypatch, root, backend)
    try:
        record = cmux_router._read_record(root)
        assert record is not None
        with pytest.raises(CmuxControlError, match="generation"):
            cmux_router.RouterControl(root, "service_different12345678").tree_all()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(record["socket_path"])
            connection.sendall(
                json.dumps(
                    {
                        "generation": GENERATION,
                        "auth": "0" * 64,
                        "method": "tree_all",
                        "params": {},
                    }
                ).encode()
                + b"\n"
            )
            response = cmux_router._receive(connection, cmux_router._MAX_RESPONSE)
        assert response == {"ok": False, "error": "router authentication failed"}
        with pytest.raises(CmuxControlError, match="allowed recipe"):
            client.new_terminal_worker(
                workspace_id="workspace:7",
                working_directory=tmp_path,
                command="sh -c 'echo unsafe'",
            )
        with pytest.raises(CmuxControlError, match=r"HTTP\(S\)"):
            client.open("file:///private/etc/passwd", workspace_id="workspace:7")
        assert backend.calls == []
    finally:
        stop.set()
        thread.join(2)


def test_router_replacement_exits_old_process_without_killing_it(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    first_stop, first_thread, client = _start_router(monkeypatch, root, FakeCmux())
    first = cmux_router._read_record(root)
    assert first is not None
    second_stop, second_thread, client = _start_router(
        monkeypatch, root, FakeCmux(), previous_id=first["router_id"]
    )
    second = cmux_router._read_record(root)
    assert second is not None
    try:
        assert second["router_id"] != first["router_id"]
        first_thread.join(2)
        assert not first_thread.is_alive()
        assert not Path(first["socket_path"]).exists()
        assert client.ping()["router_id"] == second["router_id"]
    finally:
        first_stop.set()
        second_stop.set()
        second_thread.join(2)


def test_replaced_router_cannot_execute_a_late_authenticated_action(tmp_path, monkeypatch):
    root = cmux_router._checked_root(tmp_path / "runtime", create=True)
    monkeypatch.setattr(cmux_router, "_service_is_current", lambda *_args: True)
    original = {
        "schema_version": 1,
        "service_generation": GENERATION,
        "router_id": "a" * 32,
        "pid": 12345,
        "socket_path": str(cmux_router._socket_directory(root, create=True) / f"r.{'a' * 16}.sock"),
        "auth_token": "c" * 64,
        "instance_fingerprint": FINGERPRINT,
    }
    replacement = {**original, "router_id": "b" * 32}
    replacement["socket_path"] = str(
        cmux_router._socket_directory(root, create=True) / f"r.{'b' * 16}.sock"
    )
    cmux_router._write_record(root, replacement)
    backend = FakeCmux()
    request = {
        "generation": GENERATION,
        "auth": original["auth_token"],
        "method": "open",
        "params": {"target": "https://example.com", "workspace_id": "workspace:7"},
    }

    with pytest.raises(CmuxControlError, match="ownership changed"):
        cmux_router._dispatch(backend, root, original, request, threading.Event())
    assert backend.calls == []


def test_stop_router_uses_authenticated_shutdown_not_process_signal(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    stop, thread, client = _start_router(monkeypatch, root, FakeCmux())
    record = cmux_router._read_record(root)
    assert record is not None
    monkeypatch.setattr(
        cmux_router.os,
        "kill",
        lambda *_args: pytest.fail("router shutdown must not signal a PID"),
    )

    assert cmux_router.stop_router(root, GENERATION) is True
    thread.join(2)
    assert not thread.is_alive()
    assert cmux_router._read_record(root) is None
    assert not Path(record["socket_path"]).exists()
    assert cmux_router.stop_router(root, GENERATION) is False
    stop.set()
    with pytest.raises(CmuxControlError, match="unavailable"):
        client.ping()


def test_stop_router_clears_only_proven_stale_same_generation(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    stop, thread, _client = _start_router(monkeypatch, root, FakeCmux())
    record = cmux_router._read_record(root)
    assert record is not None
    stop.set()
    thread.join(2)
    cmux_router._write_record(root, record)
    assert cmux_router.stop_router(root, "service_different12345678") is False
    assert cmux_router._read_record(root) == record
    assert cmux_router.stop_router(root, GENERATION) is False
    assert cmux_router._read_record(root) is None


def test_ensure_router_reuses_live_matching_instance(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    stop, thread, client = _start_router(monkeypatch, root, FakeCmux())

    class FakeLauncher:
        def instance_fingerprint(self) -> str:
            return FINGERPRINT

        def new_terminal_worker(self, **_kwargs: object) -> None:
            pytest.fail("matching router must be reused")

    monkeypatch.setattr(cmux_router, "CmuxControl", FakeLauncher)
    try:
        actual = cmux_router.ensure_router(root, GENERATION, "workspace:7", Path(sys.executable))
        assert actual.ping() == client.ping()
    finally:
        stop.set()
        thread.join(2)


def test_ensure_router_launches_only_fixed_installed_command(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(cmux_router, "_service_is_current", lambda *_args: True)
    ready = False
    calls: list[dict[str, object]] = []

    def ping(_self: object) -> dict[str, str]:
        if not ready:
            raise CmuxControlError("not ready")
        return {
            "service_generation": GENERATION,
            "router_id": "a" * 32,
            "instance_fingerprint": FINGERPRINT,
        }

    class FakeLauncher:
        def instance_fingerprint(self) -> str:
            return FINGERPRINT

        def new_terminal_worker(self, **kwargs: object) -> None:
            nonlocal ready
            calls.append(kwargs)
            ready = True

    monkeypatch.setattr(cmux_router.RouterControl, "ping", ping)
    monkeypatch.setattr(cmux_router.RouterControl, "tree_all", lambda _self: {})
    monkeypatch.setattr(cmux_router, "CmuxControl", FakeLauncher)
    cmux_router.ensure_router(root, GENERATION, "workspace:7", Path(sys.executable))

    assert len(calls) == 1
    assert calls[0]["focus"] is False
    assert calls[0]["workspace_id"] == "workspace:7"
    assert calls[0]["working_directory"] == root
    command = shlex.split(str(calls[0]["command"]))
    assert command == [
        "exec", str(Path(sys.executable).resolve()), "_hub-router", "--generation",
        GENERATION, "--runtime-root", str(root),
    ]


def test_missing_router_fails_closed_without_cmux_access(tmp_path):
    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    client = cmux_router.RouterControl(root, GENERATION)
    with pytest.raises(CmuxControlError, match="unavailable"):
        client.tree_all()
    with pytest.raises(CmuxControlError, match="unavailable"):
        client.open("https://example.com", workspace_id="workspace:7")


def test_readiness_check_times_out_behind_busy_router(tmp_path, monkeypatch):
    class BlockingCmux(FakeCmux):
        def __init__(self) -> None:
            super().__init__()
            self.block = False
            self.entered = threading.Event()
            self.release = threading.Event()

        def tree_all(self) -> dict[str, object]:
            if self.block:
                self.entered.set()
                assert self.release.wait(3)
            return super().tree_all()

    backend = BlockingCmux()
    stop, router_thread, client = _start_router(monkeypatch, tmp_path / "runtime", backend)
    backend.block = True
    busy = threading.Thread(target=client.tree_all, daemon=True)
    busy.start()
    try:
        assert backend.entered.wait(2)
        start = time.monotonic()
        with pytest.raises(CmuxControlError, match="unavailable"):
            client.instance_fingerprint()
        assert time.monotonic() - start < 1.5
    finally:
        backend.release.set()
        busy.join(3)
        stop.set()
        router_thread.join(3)
    assert not busy.is_alive()
    assert not router_thread.is_alive()


def test_long_runtime_root_uses_private_short_socket_directory(tmp_path):
    root = cmux_router._checked_root(tmp_path / ("a" * 70) / "runtime", create=True)
    socket_dir = cmux_router._socket_directory(root, create=True)
    assert socket_dir != root
    assert stat.S_IMODE(socket_dir.stat().st_mode) == 0o700
    assert len(str(socket_dir / "r.0123456789abcdef.sock").encode()) <= 100
