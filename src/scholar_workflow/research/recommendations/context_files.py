"""Small descriptor-relative context files; never follow a project symlink."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.store import root_directory, storage_lock

MAX_FILE = 32 * 1024 * 1024
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _parts(relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in {".", ".."} for p in path.parts):
        raise ResearchError("Context paths must be safe relative paths.", 7)
    return path.parts


@contextmanager
def directory(root, relative="", *, create=False):
    parts = _parts(relative) if relative else ()
    with root_directory(root) as root_fd:
        current = os.dup(root_fd)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                child = os.open(part, FLAGS, dir_fd=current)
                info = os.fstat(child)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
                    os.close(child)
                    raise ResearchError("Context directories must be owned and not writable by others.", 7)
                os.close(current)
                current = child
            yield current
        except OSError:
            raise ResearchError("Context path is unsafe or unavailable.", 7) from None
        finally:
            os.close(current)


def read_file(fd, name):
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(handle)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o022 or info.st_size > MAX_FILE):
            raise ResearchError("Context files must be bounded owned single-link regular files.", 7)
        with os.fdopen(handle, "rb", closefd=False) as stream:
            content = stream.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise ResearchError("Context file exceeds its size limit.", 7)
        return content
    except OSError:
        raise ResearchError("Context file is unsafe or unavailable.", 7) from None
    finally:
        os.close(handle)


def replace_file(root, relative, content, *, expected=None, create_only=False):
    """Use one directory lock and a compare-before-replace; preserve existing human files."""
    parts = _parts(relative)
    if len(content) > MAX_FILE:
        raise ResearchError("Context file exceeds its size limit.", 7)
    parent = str(Path(*parts[:-1])) if len(parts) > 1 else ""
    with directory(root, parent, create=True) as fd, storage_lock(fd, name=".context.lock"):
        old = read_file(fd, parts[-1])
        if create_only and old is not None:
            return old
        if expected is not None and digest(old) != expected:
            raise ResearchError("Context changed; reread it before saving.", 5)
        name = ".context-" + secrets.token_hex(12)
        target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            with os.fdopen(target, "wb", closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(target)
            with directory(root, parent) as actual:
                observed, pinned = os.fstat(actual), os.fstat(fd)
                if (observed.st_dev, observed.st_ino) != (pinned.st_dev, pinned.st_ino):
                    raise ResearchError("Context directory changed during the write.", 5)
            if read_file(fd, parts[-1]) != old:
                raise ResearchError("Context changed outside its writer lock.", 5)
            os.replace(name, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(target)
            try:
                os.unlink(name, dir_fd=fd)
            except FileNotFoundError:
                pass
    return content


def digest(content):
    return "absent" if content is None else hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def read_context(root, relative):
    parts = _parts(relative)
    parent = str(Path(*parts[:-1])) if len(parts) > 1 else ""
    with directory(root, parent) as fd:
        return read_file(fd, parts[-1])


def project_jsonl(root, relative, records, *, allowed_removed=None, remove_empty=False):
    """Materialize a complete derived event view; edits conflict rather than disappear."""
    try:
        old = read_context(root, relative)
    except FileNotFoundError:
        old = None
    except ResearchError:
        # Missing parent directories are created only for this declared projection.
        with directory(root, str(Path(relative).parent), create=True):
            pass
        old = read_context(root, relative)
    content = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)
                        + "\n").encode() for row in records)
    if old == content:
        return
    if old:
        try:
            old_records = [json.loads(line) for line in old.decode().splitlines() if line]
        except (ValueError, UnicodeError):
            raise ResearchError("Feedback projection contains edits; preserve it before rebuilding.", 5) from None
        known = {row["event_id"]: row for row in records}
        removed = allowed_removed or {}
        if any(not isinstance(row, dict) or (known.get(row.get("event_id")) != row
               and removed.get(row.get("event_id")) != row) for row in old_records):
            raise ResearchError("Feedback projection was edited; automatic overwrite was refused.", 5)
    if not records and remove_empty:
        if old is None:
            return
        parts = _parts(relative)
        with directory(root, str(Path(relative).parent)) as fd, storage_lock(fd, name=".context.lock"):
            if read_file(fd, parts[-1]) != old:
                raise ResearchError("Feedback changed before cleanup.", 5)
            os.unlink(parts[-1], dir_fd=fd)
            os.fsync(fd)
        return
    replace_file(root, relative, content, expected=digest(old))
