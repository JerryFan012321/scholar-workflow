"""User-level macOS supervision for the personal recommendation HTTP service."""
from __future__ import annotations

import hashlib
import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path

from scholar_workflow.research.models import ResearchError


def supported(profile: str) -> bool:
    return sys.platform == "darwin" and profile == "personal"


def identity(state_dir: Path) -> tuple[str, Path]:
    digest = hashlib.sha256(str(state_dir.absolute()).encode()).hexdigest()[:16]
    label = "io.scholar-workflow.recommendations." + digest
    return label, Path.home() / "Library/LaunchAgents" / (label + ".plist")


def definition(state_dir: Path) -> dict:
    label, _ = identity(state_dir)
    return {
        "Label": label,
        "ProgramArguments": [sys.executable, "-m",
                             "scholar_workflow.research.recommendations.cli",
                             "--profile", "personal", "serve-managed"],
        "EnvironmentVariables": {"SCHOLAR_WORKFLOW_HOME": str(state_dir.absolute().parent.parent)},
        "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10, "Umask": 0o077,
        "StandardOutPath": str(state_dir.absolute() / "service.log"),
        "StandardErrorPath": str(state_dir.absolute() / "service.log"),
    }


def _read(state_dir: Path) -> dict | None:
    _, path = identity(state_dir)
    if not path.exists() and not path.is_symlink():
        return None
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ResearchError("Recommendation login service path is unsafe.", 7)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_size > 16384):
                raise ValueError()
            config = plistlib.load(stream)
        if config != definition(state_dir):
            raise ValueError()
        return config
    except (OSError, ValueError, plistlib.InvalidFileException):
        raise ResearchError("Login service differs from the owned definition; nothing was changed.", 7) from None


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True,
                              timeout=15, shell=False, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ResearchError("macOS login service manager is unavailable; no unknown job was stopped.", 3) from None


def _loaded(state_dir: Path) -> bool:
    label, path = identity(state_dir)
    result = _launchctl("print", f"gui/{os.getuid()}/{label}")
    if result.returncode:
        return False
    # Refuse to operate on a job that reused our label with different contents.
    if (f"path = {path}" not in result.stdout
            or f"program = {sys.executable}" not in result.stdout):
        raise ResearchError("Cannot identify the loaded login service; no job was stopped.", 7)
    return True


def status(state_dir: Path, profile: str) -> dict:
    if not supported(profile):
        return {"manager": "detached", "login_start": False, "supervised": False}
    installed = _read(state_dir) is not None
    return {"manager": "launchd" if installed else "detached", "login_start": installed,
            "supervised": installed and _loaded(state_dir)}


def install(state_dir: Path) -> None:
    from scholar_workflow.research.recommendations.lifecycle import ensure_private_dir

    _, path = identity(state_dir)
    existing = _read(state_dir)
    if _loaded(state_dir):
        if existing is None:
            raise ResearchError("Loaded login service has no owned registration.", 7)
        return
    if existing is None:
        # Do not change permissions on the shared LaunchAgents directory.
        path.parent.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in path.parents):
            raise ResearchError("Recommendation login service path is unsafe.", 7)
        ensure_private_dir(state_dir)
        fd = os.open(state_dir / "service.log", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ResearchError("Recommendation log is unsafe.", 7)
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            plistlib.dump(definition(state_dir), stream)
    result = _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
    if result.returncode:
        raise ResearchError("macOS could not load the recommendation login service; run status.", 3)


def remove(state_dir: Path, profile: str) -> None:
    if not supported(profile):
        return
    existing = _read(state_dir)
    if _loaded(state_dir):
        if existing is None:
            raise ResearchError("Loaded login service has no owned registration.", 7)
        label, _ = identity(state_dir)
        if _launchctl("bootout", f"gui/{os.getuid()}/{label}").returncode:
            raise ResearchError("macOS could not unload the identified recommendation service.", 3)
    if existing is not None:
        _, path = identity(state_dir)
        path.unlink()
