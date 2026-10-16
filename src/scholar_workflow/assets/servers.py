"""Private server ledger access, without connections or secret disclosure."""
from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import os
import re
import secrets
import stat
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from io import StringIO
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

_LEDGER = "servers.yaml"
_LOCK = ".servers.lock"
_MAX_BYTES = 1024 * 1024
_MAX_SERVERS = 1000
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SECRET_KEYS = {"password", "passphrase", "token", "secret", "api_key", "apikey",
                "authorization", "private_key", "access_token", "refresh_token"}
_FIELDS = {"alias", "host", "user", "port", "key", "jump", "environments",
           "cuda_driver", "proxy", "purpose", "added", "notes", "credential_ref"}
_ENV_FIELDS = {"name", "python", "cuda", "key_packages", "compat_notes", "setup_script"}
_PLACEHOLDERS = {"host", "hostname", "ip-or-hostname", "username", "user", "your-host",
                 "your-server", "your-user", "your-username", "changeme", "change-me",
                 "replace-me", "tbd", "todo", "example"}


class AssetLedgerError(ValueError):
    """A sanitized failure with the public CLI exit code."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def _diagnostic(code: str, message: str, alias: str | None = None) -> dict:
    result = {"code": code, "message": message}
    if alias is not None:
        result["alias"] = alias
    return result


def _revision(data: bytes | None) -> str:
    return "absent" if data is None else "sha256:" + hashlib.sha256(data).hexdigest()


def _yaml() -> YAML:
    parser = YAML(typ="rt")
    parser.allow_duplicate_keys = False
    parser.preserve_quotes = True
    parser.indent(mapping=2, sequence=4, offset=2)
    return parser


def _path(root: Path) -> Path:
    raw = os.fspath(root)
    if "\x00" in raw or ".." in Path(raw).parts:
        raise AssetLedgerError("Unsafe server ledger root.", 7)
    path = Path(os.path.abspath(os.path.expanduser(raw)))
    if path == Path(path.anchor):
        raise AssetLedgerError("Unsafe server ledger root.", 7)
    return path


@contextmanager
def _root_directory(root: Path, *, create: bool = False):
    """Walk checked directory descriptors; no path component follows a symlink."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root.anchor, flags)
    try:
        for part in root.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid():
            raise AssetLedgerError("Server ledger root is not owned by the current user.", 7)
        if stat.S_IMODE(info.st_mode) & 0o022:
            raise AssetLedgerError("Server ledger root must not be group- or other-writable.", 7)
        yield descriptor
    except AssetLedgerError:
        raise
    except FileNotFoundError:
        raise
    except OSError:
        raise AssetLedgerError("Server ledger root is unsafe or unavailable.", 7) from None
    finally:
        os.close(descriptor)


def _owned_regular(info: os.stat_result):
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise AssetLedgerError("Server ledger requires an owned, single-link regular file.", 7)


def _read_bytes(root_fd: int) -> tuple[bytes | None, os.stat_result | None]:
    try:
        descriptor = os.open(_LEDGER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=root_fd)
    except FileNotFoundError:
        return None, None
    except OSError:
        raise AssetLedgerError("Server ledger file is unsafe or unreadable.", 7) from None
    try:
        info = os.fstat(descriptor)
        _owned_regular(info)
        if info.st_size > _MAX_BYTES:
            raise AssetLedgerError("Server ledger exceeds the supported size.", 7)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise AssetLedgerError("Server ledger exceeds the supported size.", 7)
        return data, info
    finally:
        os.close(descriptor)


def _bounded_tree(value, ancestors: frozenset[int] = frozenset(), budget=None, depth=0):
    if budget is None:
        budget = [20000]
    budget[0] -= 1
    if depth > 16 or budget[0] < 0:
        raise AssetLedgerError("Server ledger structure exceeds the supported limits.")
    if isinstance(value, (dict, list)):
        if id(value) in ancestors:
            raise AssetLedgerError("Server ledger contains recursive aliases.")
        ancestors = ancestors | {id(value)}
        entries = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in entries:
            if isinstance(value, dict) and not isinstance(key, str):
                raise AssetLedgerError("Server ledger field names must be strings.")
            _bounded_tree(child, ancestors, budget, depth + 1)
    elif not isinstance(value, (str, int, float, bool, date, type(None))):
        raise AssetLedgerError("Server ledger contains an unsupported YAML value.")


def _text(value, label: str, *, nullable=False, limit=8192) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise AssetLedgerError(f"Invalid server {label}.")
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise AssetLedgerError(f"Invalid server {label}.")
    return value


def _identifier(value, label: str) -> str:
    value = _text(value, label, limit=128)
    if not _IDENTIFIER.fullmatch(value):
        raise AssetLedgerError(f"Invalid server {label}.")
    return value


def _placeholder(value: str) -> bool:
    return value.casefold() in _PLACEHOLDERS or "<" in value or ">" in value


def _host(value):
    value = _text(value, "host", limit=253)
    if _placeholder(value) or any(char.isspace() for char in value):
        raise AssetLedgerError("Server host must be a real hostname or IP address.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.?", value):
            raise AssetLedgerError("Server host must be a hostname or IP address.")


def _credential_proxy(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.username is not None or parsed.password is not None
    except ValueError:
        return "@" in value


def _recognizable_secret(value: str) -> bool:
    """Detect explicit credential syntax, not every possible arbitrary secret."""
    upper = value.upper()
    if "-----BEGIN" in upper and "PRIVATE KEY" in upper:
        return True
    if re.search(r"\bBearer[ \t]+[A-Za-z0-9._~+/=-]{8,}", value, re.IGNORECASE):
        return True
    if re.search(r"\b(?:Proxy-)?Authorization[ \t]*:[ \t]*Basic[ \t]+"
                 r"[A-Za-z0-9+/]+={0,2}(?=$|[\s;,])", value, re.IGNORECASE):
        return True
    return any(_credential_proxy(match.group(0)) for match in re.finditer(
        r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+", value))


def _secret_present(value) -> bool:
    if isinstance(value, dict):
        return any((str(key).casefold() in _SECRET_KEYS and child is not None)
                   or _secret_present(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_secret_present(child) for child in value)
    return isinstance(value, str) and _recognizable_secret(value)


def _reject_submitted_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in _SECRET_KEYS and child is not None:
                raise AssetLedgerError("Plaintext secrets cannot be registered; use a credential reference.", 7)
            _reject_submitted_secrets(child)
    elif isinstance(value, list):
        for child in value:
            _reject_submitted_secrets(child)
    elif isinstance(value, str) and _recognizable_secret(value):
        raise AssetLedgerError("Recognizable credential material cannot be registered in plaintext.", 7)


def _validate_fields(record: dict, *, partial: bool = False, submitted: bool = False):
    if not isinstance(record, dict):
        raise AssetLedgerError("Server record must be an object.")
    _identifier(record.get("alias"), "alias")
    if submitted:
        _reject_submitted_secrets(record)
        if set(record) - _FIELDS - _SECRET_KEYS:
            raise AssetLedgerError("Server record contains unsupported registration fields.")
    for required in ("host", "user"):
        if not partial or required in record:
            if required == "host":
                _host(record.get(required))
            else:
                user = _text(record.get(required), "user", limit=128)
                if _placeholder(user) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*\$?", user):
                    raise AssetLedgerError("Server user must be a real SSH username.")
    if "port" in record:
        port = record["port"]
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise AssetLedgerError("Server port must be an integer from 1 to 65535.")
    if record.get("jump") is not None:
        _identifier(record["jump"], "jump alias")
    if record.get("key") is not None:
        key = _text(record["key"], "key path", limit=4096)
        if "-----BEGIN" in key or any(character in key for character in "\n\r\t"):
            raise AssetLedgerError("SSH keys must be file references, never credential material.", 7)
        if "://" in key or key in {"/", "~", "."} or ".." in Path(key).parts:
            raise AssetLedgerError("Invalid server key path.")
    if record.get("credential_ref") is not None:
        reference = _text(record["credential_ref"], "credential reference", limit=256)
        if not re.fullmatch(r"(?:keychain|env|secret-service|credential-manager):[A-Za-z0-9_./-]+", reference):
            raise AssetLedgerError("Credential reference must identify an external credential store.")
    for field in ("cuda_driver", "purpose", "notes"):
        if field in record:
            _text(record[field], field, nullable=True)
    if "added" in record and not isinstance(record["added"], (str, date)):
        raise AssetLedgerError("Invalid server added date.")
    environments = record.get("environments", [])
    if not isinstance(environments, list) or len(environments) > 1000:
        raise AssetLedgerError("Server environments must be a bounded list.")
    names = set()
    for environment in environments:
        if not isinstance(environment, dict):
            raise AssetLedgerError("Each server environment must be an object.")
        name = _identifier(environment.get("name"), "environment name")
        if _placeholder(name) or name in names:
            raise AssetLedgerError("Server environment names must be real and unique.")
        names.add(name)
        if submitted and set(environment) - _ENV_FIELDS:
            raise AssetLedgerError("Server environment contains unsupported registration fields.")
        for field in ("python", "cuda", "compat_notes"):
            if field in environment:
                _text(environment[field], "environment " + field, nullable=True)
        if "key_packages" in environment:
            packages = environment["key_packages"]
            if not isinstance(packages, list) or len(packages) > 1000:
                raise AssetLedgerError("Environment packages must be a bounded list.")
            for package in packages:
                _text(package, "environment package", limit=512)
        script = environment.get("setup_script")
        if script is not None:
            script = _text(script, "environment setup path", limit=4096)
            path = PurePosixPath(script)
            if (path.is_absolute() or "\\" in script or ".." in path.parts
                    or len(path.parts) < 3 or path.parts[:2] != ("setup", record["alias"])
                    or script != path.as_posix()):
                raise AssetLedgerError("Environment setup path must stay under setup/<alias>/.")
    proxy = record.get("proxy")
    if proxy is not None:
        if not isinstance(proxy, dict) or set(proxy) - {"http", "https", "no_proxy"}:
            raise AssetLedgerError("Server proxy must contain only http, https and no_proxy.")
        for key, value in proxy.items():
            _text(value, "proxy " + key, nullable=True, limit=4096)
            if key != "no_proxy" and value is not None:
                if submitted and _credential_proxy(value):
                    raise AssetLedgerError("Proxy credentials cannot be registered in plaintext.", 7)
                try:
                    parsed = urlsplit(value)
                    if parsed.scheme not in {"http", "https", "socks4", "socks5", "socks5h"} or not parsed.hostname:
                        raise ValueError
                    _ = parsed.port
                except ValueError:
                    raise AssetLedgerError("Invalid server proxy URL.") from None


def _load(data: bytes | None):
    if data is None:
        return CommentedMap(servers=CommentedSeq())
    try:
        document = _yaml().load(data.decode("utf-8"))
        _bounded_tree(document)
        if not isinstance(document, dict) or not isinstance(document.get("servers"), list):
            raise TypeError
        if len(document["servers"]) > _MAX_SERVERS:
            raise ValueError
        aliases = set()
        for record in document["servers"]:
            _validate_fields(record)
            if record["alias"] in aliases:
                raise ValueError
            aliases.add(record["alias"])
        return document
    except (YAMLError, UnicodeError, ValueError, TypeError, RecursionError):
        # Parser exceptions can include line excerpts containing credentials.
        raise AssetLedgerError("Invalid server ledger; check its YAML structure and records.") from None


def _public(record: dict) -> dict:
    result = {}
    for field in sorted(_FIELDS):
        if field not in record:
            continue
        value = record[field]
        if field == "environments":
            value = [{key: deepcopy(child) for key, child in environment.items()
                      if key in _ENV_FIELDS} for environment in value]
        elif field == "proxy" and value is not None:
            value = {key: "[credential-bearing proxy hidden]" if _credential_proxy(child)
                     else child for key, child in value.items()}
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        result[field] = _public_value(value)
    proxy_secret = any(_credential_proxy(value) for value in (record.get("proxy") or {}).values())
    if _secret_present(record) or proxy_secret:
        result["legacy_secret_present"] = True
    return result


def _public_value(value):
    if isinstance(value, str) and _recognizable_secret(value):
        return "[credential material hidden]"
    if isinstance(value, dict):
        return {key: _public_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_public_value(child) for child in value]
    return deepcopy(value)


def _setup_diagnostics(root_fd: int, record: dict) -> list[dict]:
    diagnostics = []
    for environment in record.get("environments", []):
        script = environment.get("setup_script")
        if script is None:
            continue
        descriptor = os.dup(root_fd)
        code = None
        try:
            parts = PurePosixPath(script).parts
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
                directory = os.fstat(descriptor)
                if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) & 0o022:
                    raise AssetLedgerError("Unsafe setup directory.", 7)
            info = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            _owned_regular(info)
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise AssetLedgerError("Unsafe setup file.", 7)
        except FileNotFoundError:
            code = "setup_script_missing"
        except (OSError, AssetLedgerError):
            code = "setup_script_unsafe"
        finally:
            os.close(descriptor)
        if code is not None:
            diagnostics.append(_diagnostic(
                code, "Declared setup script metadata is " +
                ("missing" if code == "setup_script_missing" else "unsafe") +
                "; no script content was read or executed.", record["alias"]))
    return diagnostics


def _patch(current: dict, submitted: dict) -> dict:
    """Mappings patch recursively; explicitly submitted lists replace that list."""
    updated = deepcopy(current)
    for field, value in submitted.items():
        if field.casefold() in _SECRET_KEYS:
            if current.get(field) is not None:
                raise AssetLedgerError("Legacy credentials cannot be changed through server registration.", 7)
            continue
        if isinstance(value, dict) and isinstance(current.get(field), dict):
            updated[field] = _patch(current[field], value)
        else:
            updated[field] = deepcopy(value)
    return updated


def read_servers(root: Path) -> dict:
    """Read the authority without creating, modifying, connecting or exposing secrets."""
    result = {"schema_version": 1, "status": "uninitialized", "revision": "absent",
              "servers": [], "diagnostics": []}
    try:
        path = _path(root)
        with _root_directory(path) as root_fd:
            data, info = _read_bytes(root_fd)
            result["revision"] = _revision(data)
            if data is None:
                return result
            document = _load(data)
            result["status"] = "available"
            result["servers"] = [_public(record) for record in document["servers"]]
            if stat.S_IMODE(info.st_mode) & 0o077:
                result["diagnostics"].append(_diagnostic(
                    "ledger_permissions", "Server ledger permissions are not private; read made no changes."))
            for record in result["servers"]:
                if record.get("legacy_secret_present"):
                    result["diagnostics"].append(_diagnostic(
                        "legacy_secret_present", "Recognizable legacy credential material is present and hidden.",
                        record["alias"]))
            for record in document["servers"]:
                result["diagnostics"].extend(_setup_diagnostics(root_fd, record))
    except FileNotFoundError:
        pass
    except AssetLedgerError as error:
        result.update(status="invalid", servers=[])
        result["diagnostics"].append(_diagnostic("invalid_server_ledger", str(error)))
    except OSError:
        result.update(status="invalid", servers=[])
        result["diagnostics"].append(_diagnostic("invalid_server_ledger", "Server ledger is unavailable."))
    return result


@contextmanager
def _lock(root_fd: int):
    try:
        descriptor = os.open(_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                             mode=0o600, dir_fd=root_fd)
    except OSError:
        raise AssetLedgerError("Server ledger lock is unsafe or unavailable.", 7) from None
    try:
        info = os.fstat(descriptor)
        _owned_regular(info)
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise AssetLedgerError("Server ledger lock permissions are not private.", 7)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield descriptor
    finally:
        os.close(descriptor)


def _replace(root: Path, root_fd: int, lock_fd: int, expected: bytes | None, output: bytes):
    if len(output) > _MAX_BYTES:
        raise AssetLedgerError("Server ledger exceeds the supported size.", 7)
    temporary = ".servers-" + secrets.token_hex(16) + ".tmp"
    descriptor = None
    replaced = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             mode=0o600, dir_fd=root_fd)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(output)
            handle.flush()
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        with _root_directory(root) as current_fd:
            original = os.fstat(root_fd)
            current = os.fstat(current_fd)
            if (original.st_dev, original.st_ino) != (current.st_dev, current.st_ino):
                raise AssetLedgerError("Server ledger root changed during registration.", 7)
        current_data, _ = _read_bytes(root_fd)
        if current_data != expected:
            raise AssetLedgerError("Server ledger changed during registration; read it again.", 7)
        current_lock = os.stat(_LOCK, dir_fd=root_fd, follow_symlinks=False)
        held_lock = os.fstat(lock_fd)
        _owned_regular(current_lock)
        if (current_lock.st_dev, current_lock.st_ino) != (held_lock.st_dev, held_lock.st_ino):
            raise AssetLedgerError("Server ledger lock changed during registration.", 7)
        os.replace(temporary, _LEDGER, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        replaced = True
        os.fsync(root_fd)
    except AssetLedgerError:
        raise
    except OSError:
        if replaced:
            raise AssetLedgerError(
                "Server ledger was replaced but durability is unconfirmed; read it before retrying.", 6) from None
        raise AssetLedgerError("Server ledger could not be safely written.", 7) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=root_fd)
        except FileNotFoundError:
            pass


def register_server(root: Path, record: dict, *, expected_revision: str | None = None) -> dict:
    """Add or CAS-patch one alias; preserve existing unrelated content and secrets."""
    _bounded_tree(record)
    _validate_fields(record, partial=True, submitted=True)
    if expected_revision is not None and not re.fullmatch(r"absent|sha256:[0-9a-f]{64}", expected_revision):
        raise AssetLedgerError("Invalid server ledger revision.")
    path = _path(root)
    try:
        with _root_directory(path) as probe_fd:
            initial_data, _ = _read_bytes(probe_fd)
    except FileNotFoundError:
        initial_data = None
    initial_document = _load(initial_data)
    if not any(row["alias"] == record["alias"] for row in initial_document["servers"]):
        _validate_fields(record, submitted=True)
    with _root_directory(path, create=True) as root_fd, _lock(root_fd) as lock_fd:
        data, _ = _read_bytes(root_fd)
        document = _load(data)
        revision = _revision(data)
        if expected_revision is not None and expected_revision != revision:
            raise AssetLedgerError("Server ledger revision conflict; read it again before changing this alias.", 7)
        index = next((index for index, row in enumerate(document["servers"])
                      if row["alias"] == record["alias"]), None)
        current = None if index is None else document["servers"][index]
        updated = _patch(CommentedMap() if current is None else current, record)
        _validate_fields(updated)
        if current is not None and updated == current:
            return {"status": "unchanged", "revision": revision, "server": _public(current)}
        if current is not None and expected_revision is None:
            raise AssetLedgerError("Changing an existing server requires its exact current ledger revision.", 5)
        if index is None:
            document["servers"].append(updated)
            status = "created"
        else:
            document["servers"][index] = updated
            status = "updated"
        stream = StringIO()
        _yaml().dump(document, stream)
        output = stream.getvalue().encode("utf-8")
        _load(output)
        _replace(path, root_fd, lock_fd, data, output)
        return {"status": status, "revision": _revision(output), "server": _public(updated)}
