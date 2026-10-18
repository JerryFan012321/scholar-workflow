"""Inspect a selected local Git bundle against child-qualified experiment commits."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import uuid
from pathlib import Path

from .collected import collected_overview
from .collection import _sha
from .layout import open_project_root, read_project_bytes
from .management import PROJECT_MANAGEMENT, load_project_management
from .update_package import _capture
from .update_package import _json as _json_bytes

_BUNDLE_LIMIT = 256 * 1024 * 1024
_OUTPUT_LIMIT = 8 * 1024 * 1024
_COMMIT = re.compile(r"[0-9a-f]{40}")


class CodeRecoveryError(ValueError):
    """Recovery evidence is invalid, incomplete, unsafe or changed."""

    def __init__(self, message, exit_code=2):
        super().__init__(message)
        self.exit_code = exit_code


def _git(executable, root, *arguments, input_bytes=None):
    """No inherited Git config, environment hooks, credentials, transports or shell."""
    command = [executable, "--no-replace-objects", "-C", str(root),
               "-c", "protocol.allow=never", "-c", "core.hooksPath=" + os.devnull,
               "-c", "core.fsmonitor=false", *arguments]
    environment = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
                   "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "",
                   "GIT_NO_LAZY_FETCH": "1", "LC_ALL": "C"}
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=error,
                                   env=environment, shell=False, start_new_session=True)
        try:
            process.communicate(input_bytes, timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            raise CodeRecoveryError("Local Git verification timed out; no project archive was changed") from None
        output.seek(0)
        data = output.read(_OUTPUT_LIMIT + 1)
        if len(data) > _OUTPUT_LIMIT:
            raise CodeRecoveryError("Git inspection output exceeds its bounded limit; nothing was truncated")
        # Raw Git errors can contain paths, object bodies or private reference names.
        return process.returncode, data


def _required(parent_root, child_id, additional):
    management = load_project_management(parent_root)
    if management.kind != "research-parent" or not any(child.project_id == child_id for child in management.children):
        raise CodeRecoveryError("Select one explicitly registered execution child")
    overview = collected_overview(parent_root, child_project_id=child_id)
    if overview["status"] != "complete":
        raise CodeRecoveryError("Selected child archive is incomplete, invalid or pending recovery")
    commits = {}
    for run in overview["children"][0]["runs"]:
        if run["state"] != "verified_archive":
            raise CodeRecoveryError("Selected child archive contains unverified Run evidence")
        commits.setdefault(run["source_commit"], []).append(run["run_id"])
    for commit in additional:
        if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
            raise CodeRecoveryError("Additional recovery commits must be full lowercase SHA-1 identities")
        commits.setdefault(commit, [])
    if not commits:
        raise CodeRecoveryError("No recorded source commits; explicitly select a commit rather than the parent HEAD")
    return management.project_id, [{"commit": key, "run_ids": sorted(set(value))}
                                   for key, value in sorted(commits.items())], overview


def _bundle_bytes(path):
    selected = Path(os.path.abspath(Path(path).expanduser()))
    try:
        with open_project_root(selected.parent) as parent_fd:
            return _capture(parent_fd, selected.name, _BUNDLE_LIMIT)[0]
    except (OSError, ValueError):
        raise CodeRecoveryError("Selected bundle is missing, unsafe, changed or exceeds 256 MiB") from None


def _dependency_gaps(executable, repository, commits):
    lfs, submodules = [], []
    for commit in commits:
        code, raw = _git(executable, repository, "ls-tree", "-r", "--full-tree", "-z", commit)
        if code:
            raise CodeRecoveryError("Cannot inspect the selected commit tree")
        blobs = {}
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            metadata, path = entry.split(b"\t", 1)
            mode, kind, identifier = metadata.split(b" ")
            name = path.decode("utf-8")
            if mode == b"160000":
                submodules.append({"commit": commit, "path": name,
                                   "gitlink_commit": identifier.decode("ascii"), "payload": "not_included"})
            elif kind == b"blob":
                blobs.setdefault(identifier, []).append(name)
        if not blobs:
            continue
        code, sizes = _git(executable, repository, "cat-file", "--batch-check",
                           input_bytes=b"\n".join(blobs) + b"\n")
        if code:
            raise CodeRecoveryError("Cannot inspect blob identities and sizes")
        candidates = []
        for line in sizes.splitlines():
            identifier, kind, size = line.split(b" ")
            if identifier not in blobs or kind != b"blob":
                raise CodeRecoveryError("Invalid blob inspection response")
            if int(size) > 1024:
                continue
            candidates.append((identifier, int(size)))
        if not candidates:
            continue
        code, bodies = _git(executable, repository, "cat-file", "--batch",
                            input_bytes=b"\n".join(item[0] for item in candidates) + b"\n")
        if code:
            raise CodeRecoveryError("Cannot inspect candidate LFS pointers")
        offset = 0
        for identifier, size in candidates:
            boundary = bodies.find(b"\n", offset)
            header = identifier + b" blob " + str(size).encode()
            if boundary < 0 or bodies[offset:boundary] != header:
                raise CodeRecoveryError("Invalid batch blob response")
            body = bodies[boundary + 1:boundary + 1 + size]
            offset = boundary + size + 2
            if len(body) != size or bodies[offset - 1:offset] != b"\n":
                raise CodeRecoveryError("Incomplete batch blob response")
            match = re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\r?\n"
                                 rb"oid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)\r?\n?", body)
            if match:
                lfs.extend({"commit": commit, "path": name, "oid": match[1].decode("ascii"),
                            "size": int(match[2]), "payload": "not_included"} for name in blobs[identifier])
        if offset != len(bodies):
            raise CodeRecoveryError("Unexpected trailing batch blob data")
    return {"lfs_pointers": lfs, "submodules": submodules,
            "uncommitted": "not_checked", "untracked": "not_checked",
            "external_dependencies": "not_checked", "secret_audit": "not_checked"}


def plan_code_recovery(parent_root, *, child_project_id, bundle_file, required_commits=()):
    """Check one self-contained bundle in an isolated bare repository; retain nothing."""
    declaration = read_project_bytes(parent_root, PROJECT_MANAGEMENT)
    parent_id, required, archive = _required(parent_root, child_project_id, required_commits)
    bundle = _bundle_bytes(bundle_file)
    executable = shutil.which("git")
    if executable is None:
        raise CodeRecoveryError("Git is unavailable; code recovery was not checked", 3)
    try:
        with tempfile.TemporaryDirectory(prefix="scholar-code-recovery-") as directory:
            staging = Path(directory)
            copied = staging / "selected.bundle"
            copied.write_bytes(bundle)
            copied.chmod(0o600)
            template = staging / "empty-template"
            template.mkdir()
            code, _ = _git(executable, staging, "init", "--bare", "--object-format=sha1",
                           "--template=" + str(template), "repository")
            if code:
                raise CodeRecoveryError("Git cannot prepare an isolated SHA-1 verification repository")
            repository = staging / "repository"
            code, _ = _git(executable, repository, "bundle", "verify", str(copied))
            if code:
                raise CodeRecoveryError("Bundle is invalid or not self-contained; an independent base is required")
            code, heads_raw = _git(executable, repository, "bundle", "unbundle", str(copied))
            if code:
                raise CodeRecoveryError("Bundle objects could not be recovered into the isolated repository")
            heads = sorted({line.split(b" ", 1)[0].decode("ascii") for line in heads_raw.splitlines()})
            if not heads or any(_COMMIT.fullmatch(value) is None for value in heads):
                raise CodeRecoveryError("Bundle does not advertise supported SHA-1 objects")
            for row in required:
                code, kind = _git(executable, repository, "cat-file", "-t", row["commit"])
                if code or kind != b"commit\n":
                    raise CodeRecoveryError("Bundle is missing a required recorded or explicitly selected source commit")
            code, _ = _git(executable, repository, "fsck", "--full", "--strict", "--no-reflogs",
                           "--no-dangling", *sorted(set(heads) | {row["commit"] for row in required}))
            if code:
                raise CodeRecoveryError("Required source commits do not have intact reachable objects")
            gaps = _dependency_gaps(executable, repository, [row["commit"] for row in required])
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError) as error:
        if isinstance(error, CodeRecoveryError):
            raise
        raise CodeRecoveryError("Local isolated Git inspection failed; source archive was not changed") from None
    if (_bundle_bytes(bundle_file) != bundle
            or read_project_bytes(parent_root, PROJECT_MANAGEMENT) != declaration
            or _required(parent_root, child_project_id, required_commits)[2] != archive):
        raise CodeRecoveryError("Bundle or child archive changed during recovery planning")
    result = {
        "schema_version": 1, "status": "planned_not_retained", "parent_project_id": parent_id,
        "child_project_id": child_project_id,
        "bundle": {"sha256": _sha(bundle), "size": len(bundle), "object_format": "sha1",
                   "self_contained": True, "object_check": "fsck_strict_passed"},
        "required_commits": [{**row, "object_present": True} for row in required],
        "advertised_objects": heads, "gaps": gaps,
        "archive_sha256": _sha(json.dumps(archive, sort_keys=True, separators=(",", ":")).encode()),
        "parent_sha256": _sha(declaration), "backup_state": "not-verified",
        "origin_verification": "declared_child_commits_only",
    }
    result["plan_sha256"] = _sha(json.dumps(result, sort_keys=True, separators=(",", ":")).encode())
    return result


def _material_record(plan):
    return {"schema_version": 1, "parent_project_id": plan["parent_project_id"],
            "child_project_id": plan["child_project_id"], "bundle": plan["bundle"],
            "backup_state": "not-verified"}


def _existing_material(namespace_fd, name, plan):
    from .layout import _unique_json_object
    from .reception import _directory, _read_file

    try:
        os.stat(name, dir_fd=namespace_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    with _directory(namespace_fd, name) as material:
        raw, mode = _read_file(material, "material.json", 1024 * 1024)
        record = json.loads(raw, object_pairs_hook=_unique_json_object)
        if _json_bytes(record) != _json_bytes(_material_record(plan)) or mode != 0o600:
            raise CodeRecoveryError("Existing recovery material has unknown identity or metadata; nothing overwritten", 5)
        content, mode = _read_file(material, "source.bundle", _BUNDLE_LIMIT)
        if (_sha(content), len(content), mode) != (plan["bundle"]["sha256"], plan["bundle"]["size"], 0o600):
            raise CodeRecoveryError("Existing recovery bundle differs; nothing overwritten", 5)
        with _directory(material, "coverage"):
            pass
    return True


def _add_coverage(material_fd, plan):
    from .reception import _directory, _read_file, _write_file

    raw = _json_bytes(plan)
    if len(raw) > 1024 * 1024:
        raise CodeRecoveryError("Coverage record exceeds 1 MiB; nothing was truncated")
    name = plan["plan_sha256"] + ".json"
    with _directory(material_fd, "coverage") as directory:
        try:
            current, mode = _read_file(directory, name, 1024 * 1024)
        except FileNotFoundError:
            temporary = ".coverage-" + uuid.uuid4().hex
            try:
                _write_file(directory, temporary, raw, 0o600)
                if _read_file(directory, temporary, len(raw)) != (raw, 0o600):
                    raise CodeRecoveryError("Coverage staging failed read-back verification", 6)
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
                os.fsync(directory)
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
            except (OSError, ValueError) as error:
                raise CodeRecoveryError("Coverage publication is incomplete or durability unconfirmed", 6) from error
            return True
        if current != raw or mode != 0o600:
            raise CodeRecoveryError("Existing coverage record differs; nothing overwritten", 5)
        try:
            os.fsync(directory)
        except OSError:
            raise CodeRecoveryError("Existing coverage durability is unconfirmed", 6) from None
        return False


def _check_coverage_baseline(parent_root, child_id, plan, additional, bundle_file):
    _parent, _commits, archive = _required(parent_root, child_id, additional)
    if (_sha(json.dumps(archive, sort_keys=True, separators=(",", ":")).encode()) != plan["archive_sha256"]
            or _sha(read_project_bytes(parent_root, PROJECT_MANAGEMENT)) != plan["parent_sha256"]
            or _sha(_bundle_bytes(bundle_file)) != plan["bundle"]["sha256"]):
        raise CodeRecoveryError("Recovery preview is stale; inspect the current evidence again", 5)


def retain_code_recovery(parent_root, *, child_project_id, bundle_file, expected_plan_sha256,
                         required_commits=()):
    """Retain one immutable material per child/bundle hash and append small coverage records."""
    from .reception import _directory, _publish, _read_file, _write_file
    from .transactions import _locked

    if not isinstance(expected_plan_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise CodeRecoveryError("Retention requires a current recovery-plan SHA-256")
    required_commits = tuple(required_commits)
    plan = plan_code_recovery(parent_root, child_project_id=child_project_id,
                              bundle_file=bundle_file, required_commits=required_commits)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise CodeRecoveryError("Recovery preview is stale; nothing retained", 5)
    if len(_json_bytes(plan)) > 1024 * 1024:
        raise CodeRecoveryError("Coverage record exceeds 1 MiB; nothing was truncated")
    namespace = f"backups/code/{child_project_id}"
    name = plan["bundle"]["sha256"]
    material_path = f"{namespace}/{name}"
    modified = False
    staged_path = None
    try:
        with _locked(parent_root) as (root_fd, _baseline, check):
            _check_coverage_baseline(parent_root, child_project_id, plan, required_commits, bundle_file)
            with _directory(root_fd, namespace, create=True) as namespace_fd:
                existing = _existing_material(namespace_fd, name, plan)
                if not existing:
                    staged = ".retain-" + uuid.uuid4().hex
                    os.mkdir(staged, 0o700, dir_fd=namespace_fd)
                    staged_path = f"{namespace}/{staged}"
                    modified = True
                    with _directory(namespace_fd, staged) as material:
                        content = _bundle_bytes(bundle_file)
                        if _sha(content) != name:
                            raise CodeRecoveryError("Selected bundle changed before retention", 5)
                        _write_file(material, "source.bundle", content, 0o600)
                        _write_file(material, "material.json", _json_bytes(_material_record(plan)), 0o600)
                        with _directory(material, "coverage", create=True):
                            pass
                        _add_coverage(material, plan)
                        os.fsync(material)
                    _existing_material(namespace_fd, staged, plan)
                    _check_coverage_baseline(parent_root, child_project_id, plan, required_commits, bundle_file)
                    check()
                    with _directory(root_fd, namespace) as current:
                        a, b = os.fstat(current), os.fstat(namespace_fd)
                        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                            raise CodeRecoveryError("Recovery storage location changed", 5)
                    _publish(namespace_fd, staged, name)
                    staged_path = None
                    status = "retained"
                else:
                    with _directory(namespace_fd, name) as material:
                        added = _add_coverage(material, plan)
                        modified = True
                        os.fsync(material)
                    status = "coverage_added" if added else "unchanged"
                check()
                _check_coverage_baseline(parent_root, child_project_id, plan, required_commits, bundle_file)
                _existing_material(namespace_fd, name, plan)
                with _directory(root_fd, namespace) as current:
                    a, b = os.fstat(current), os.fstat(namespace_fd)
                    if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                        raise CodeRecoveryError("Recovery storage location changed", 6)
                with _directory(namespace_fd, name) as material:
                    expected = _json_bytes(plan)
                    if _read_file(material, f"coverage/{plan['plan_sha256']}.json", len(expected)) != (expected, 0o600):
                        raise CodeRecoveryError("Retained coverage failed read-back verification", 6)
                os.fsync(namespace_fd)
                for path in ("backups/code", "backups"):
                    with _directory(root_fd, path) as directory:
                        os.fsync(directory)
                os.fsync(root_fd)
        return {"status": status, "material_path": material_path,
                "coverage_path": f"{material_path}/coverage/{plan['plan_sha256']}.json",
                "plan_sha256": plan["plan_sha256"], "backup_state": "not-verified",
                "non_git_gaps": plan["gaps"], "origin_verification": plan["origin_verification"]}
    except (OSError, ValueError) as error:
        if modified or getattr(error, "exit_code", None) == 6:
            location = staged_path or material_path
            raise CodeRecoveryError(f"Retention is incomplete or durability unconfirmed; inspect {location}", 6) from error
        if isinstance(error, CodeRecoveryError):
            raise
        raise CodeRecoveryError("Recovery storage is unsafe or conflicts with existing material; nothing overwritten", 5) from None
