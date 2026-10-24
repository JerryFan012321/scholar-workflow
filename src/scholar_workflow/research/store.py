"""Private descriptor-relative storage, shared locks and compare-before-replace writes."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .models import (
    CHANNEL_FIELDS,
    MAX_REGISTRY_BYTES,
    MAX_STATE_BYTES,
    ResearchError,
    bounded_tree,
    validate_channel,
    validate_registry,
    validate_state,
)

REGISTRY = "research-sources.yml"
STATE_DIRECTORY = "research"
STATE_FILE = "tracking.json"
LOCK = ".research.lock"
_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def root_path(root):
    try:
        raw = os.fspath(root)
    except TypeError:
        raise ResearchError("Invalid research storage root.", 7) from None
    if not isinstance(raw, str) or "\x00" in raw or ".." in Path(raw).parts:
        raise ResearchError("Unsafe research storage root.", 7)
    path = Path(os.path.abspath(os.path.expanduser(raw)))
    if path == Path(path.anchor):
        raise ResearchError("Unsafe research storage root.", 7)
    return path


def _owned_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ResearchError("Research storage requires private, owned single-link regular files.", 7)


def _owned_directory(info):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o022):
        raise ResearchError("Research storage directory is unsafe.", 7)


@contextmanager
def root_directory(root, *, create=False):
    """Refuse symlinks in every original path component, including existing parents."""
    root = root_path(root)
    descriptor = os.open(root.anchor, _FLAGS)
    try:
        for part in root.parts[1:]:
            try:
                child = os.open(part, _FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, _FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        _owned_directory(os.fstat(descriptor))
        yield descriptor
    except (ResearchError, FileNotFoundError):
        raise
    except OSError:
        raise ResearchError("Research storage root is unsafe or unavailable.", 7) from None
    finally:
        os.close(descriptor)


@contextmanager
def state_directory(root_fd, *, create=False):
    try:
        try:
            descriptor = os.open(STATE_DIRECTORY, _FLAGS, dir_fd=root_fd)
        except FileNotFoundError:
            if not create:
                raise
            try:
                os.mkdir(STATE_DIRECTORY, mode=0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            except FileExistsError:
                pass
            descriptor = os.open(STATE_DIRECTORY, _FLAGS, dir_fd=root_fd)
        try:
            info = os.fstat(descriptor)
            _owned_directory(info)
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ResearchError("Research observation directory must be private.", 7)
            yield descriptor
        finally:
            os.close(descriptor)
    except (ResearchError, FileNotFoundError):
        raise
    except OSError:
        raise ResearchError("Research observation directory is unsafe or unavailable.", 7) from None


def read_bytes(directory_fd, name, limit):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError:
        raise ResearchError("Research storage file is unsafe or unreadable.", 7) from None
    try:
        info = os.fstat(descriptor)
        _owned_file(info)
        if info.st_size > limit:
            raise ResearchError("Research storage file exceeds its size limit.", 7)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ResearchError("Research storage file exceeds its size limit.", 7)
        return data
    finally:
        os.close(descriptor)


def revision(data):
    return "absent" if data is None else "sha256:" + hashlib.sha256(data).hexdigest()


def load_registry(data):
    if data is None:
        return {"schema_version": 1, "channels": []}
    try:
        parser = YAML(typ="safe")
        parser.allow_duplicate_keys = False
        document = parser.load(data.decode("utf-8"))
    except (YAMLError, ValueError, UnicodeError, RecursionError):
        raise ResearchError("Research source registry is not valid YAML.") from None
    return validate_registry(document)


def dump_registry(document):
    output = StringIO()
    parser = YAML()
    parser.indent(mapping=2, sequence=4, offset=2)
    parser.dump(document, output)
    return output.getvalue().encode("utf-8")


def load_state(data):
    if data is None:
        return {"schema_version": 1, "channels": {}, "events": []}

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ResearchError("Research tracking state has duplicate fields.")
            value[key] = item
        return value

    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise ResearchError("Research tracking state is not valid JSON.") from None
    return validate_state(document)


def dump_state(document):
    validate_state(document)
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


@contextmanager
def storage_lock(root_fd, *, name=LOCK, blocking=True):
    try:
        descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                             mode=0o600, dir_fd=root_fd)
    except OSError:
        raise ResearchError("Research storage lock is unsafe or unavailable.", 7) from None
    try:
        _owned_file(os.fstat(descriptor))
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ResearchError("Another research check is already running.", 5) from None
        yield descriptor
    finally:
        os.close(descriptor)


def _same_directory(expected, current):
    a, b = os.fstat(expected), os.fstat(current)
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def replace_bytes(root, root_fd, directory_fd, name, expected, output, lock_fd, *, state=False,
                  registry_expected=None):
    """Revalidate path, held lock and exact target bytes immediately before rename."""
    limit = MAX_STATE_BYTES if state else MAX_REGISTRY_BYTES
    if len(output) > limit:
        raise ResearchError("Research storage capacity reached; no records were discarded.", 6)
    temporary = ".research-" + secrets.token_hex(16) + ".tmp"
    descriptor = None
    replaced = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             mode=0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(output)
            handle.flush()
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        with root_directory(root) as current_fd:
            if not _same_directory(root_fd, current_fd):
                raise ResearchError("Research storage root changed during the operation.", 7)
        if state:
            with state_directory(root_fd) as current_state_fd:
                if not _same_directory(directory_fd, current_state_fd):
                    raise ResearchError("Research observation directory changed during the operation.", 7)
        lock_info = os.stat(LOCK, dir_fd=root_fd, follow_symlinks=False)
        _owned_file(lock_info)
        held = os.fstat(lock_fd)
        if (lock_info.st_dev, lock_info.st_ino) != (held.st_dev, held.st_ino):
            raise ResearchError("Research storage lock changed during the operation.", 7)
        if read_bytes(directory_fd, name, limit) != expected:
            raise ResearchError("Research storage changed during the operation; read it again.", 5)
        if registry_expected is not None and read_bytes(
            root_fd, REGISTRY, MAX_REGISTRY_BYTES,
        ) != registry_expected:
            raise ResearchError("Research channel configuration changed before observation replacement.", 5)
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        replaced = True
        os.fsync(directory_fd)
    except ResearchError:
        raise
    except OSError:
        if replaced:
            raise ResearchError(
                "Research state was replaced but durability is unconfirmed; read before retrying.", 6,
            ) from None
        raise ResearchError("Research state could not be safely written.", 7) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except OSError:
            pass


def read_sources(root):
    """Read non-paper subscriptions without initializing any directory or lock."""
    result = {"schema_version": 1, "status": "uninitialized", "revision": "absent",
              "channels": [], "diagnostics": []}
    try:
        with root_directory(root) as descriptor:
            data = read_bytes(descriptor, REGISTRY, MAX_REGISTRY_BYTES)
        result["revision"] = revision(data)
        if data is not None:
            result.update(status="available", channels=load_registry(data)["channels"])
    except FileNotFoundError:
        pass
    except (ResearchError, OSError):
        result.update(status="invalid", channels=[])
        result["diagnostics"] = [{"code": "invalid_research_sources",
                                  "message": "Research source registry is invalid or unsafe."}]
    return result


def register_source(root, record, expected_revision=None):
    """Add a channel, or change one existing channel with its current registry revision."""
    bounded_tree(record, budget=1000)
    if not isinstance(record, dict) or "channel_id" not in record or set(record) - CHANNEL_FIELDS:
        # Full validation supplies the same sanitized secret-field refusal.
        validate_channel(record)
        raise ResearchError("Invalid research channel registration.")
    from .models import identifier
    identifier(record["channel_id"])
    if expected_revision is not None:
        import re
        if not isinstance(expected_revision, str) or not re.fullmatch(
            r"absent|sha256:[0-9a-f]{64}", expected_revision,
        ):
            raise ResearchError("Invalid research registry revision.")
    path = root_path(root)
    try:
        with root_directory(path) as descriptor:
            before = read_bytes(descriptor, REGISTRY, MAX_REGISTRY_BYTES)
    except FileNotFoundError:
        before = None
    initial = load_registry(before)
    current = next((row for row in initial["channels"]
                    if row["channel_id"] == record["channel_id"]), None)
    validate_channel({**(current or {}), **record})
    with root_directory(path, create=True) as root_fd, storage_lock(root_fd) as lock_fd:
        data = read_bytes(root_fd, REGISTRY, MAX_REGISTRY_BYTES)
        document = load_registry(data)
        current_revision = revision(data)
        if expected_revision is not None and expected_revision != current_revision:
            raise ResearchError("Research registry revision conflict; read the registry again.", 5)
        index = next((position for position, row in enumerate(document["channels"])
                      if row["channel_id"] == record["channel_id"]), None)
        current = None if index is None else document["channels"][index]
        updated = validate_channel({**(current or {}), **record})
        status = "created" if current is None else "updated"
        if current == updated:
            return {"schema_version": 1, "status": "unchanged", "revision": current_revision,
                    "channel": current, "channels": document["channels"], "diagnostics": []}
        if current is not None and expected_revision is None:
            raise ResearchError("Changing a research channel requires the current registry revision.", 5)
        if index is None:
            document["channels"].append(updated)
        else:
            document["channels"][index] = updated
        validate_registry(document)
        output = dump_registry(document)
        replace_bytes(path, root_fd, root_fd, REGISTRY, data, output, lock_fd)
        return {"schema_version": 1, "status": status, "revision": revision(output),
                "channel": updated, "channels": document["channels"], "diagnostics": []}


@contextmanager
def check_lock(root):
    """Prevent overlapping outbound checks; independent local registration remains possible."""
    with root_directory(root, create=True) as root_fd, storage_lock(
        root_fd, name=".research-check.lock", blocking=False,
    ):
        yield
