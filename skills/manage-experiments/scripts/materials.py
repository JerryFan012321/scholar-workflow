#!/usr/bin/env python3
"""Read-only preview of an explicitly selected experiment material operation."""

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath

KINDS = {"result", "recipe", "record", "diagnostic", "input", "model", "raw", "temporary"}
RETURNABLE = {"result", "recipe", "record", "diagnostic"}
KEEPS = {"retain", "cleanup", "undecided"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    if Path(path).is_symlink():
        raise ValueError("The operation document cannot be a symlink")
    with open(path, "rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Operation document exceeds 1 MiB")
    return json.loads(data)


def validate_selection(value):
    if not isinstance(value, dict) or set(value) != {"schema_version", "files"}:
        raise ValueError("Expected schema_version and files")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported selection version")
    if not isinstance(value["files"], list) or not value["files"]:
        raise ValueError("Select at least one explicit file")
    seen = set()
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "kind", "use", "keep", "return"}:
            raise ValueError("Each file needs path, kind, use, keep and return")
        name = item["path"]
        if not isinstance(name, str) or not name:
            raise ValueError("A path must be nonempty text")
        rel = PurePosixPath(name)
        if (rel.is_absolute() or str(rel) != name or ".." in rel.parts
                or name == "." or "\\" in name or ".git" in rel.parts
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise ValueError(f"Unsafe relative path: {name!r}")
        if name in seen:
            raise ValueError(f"Duplicate selection: {name}")
        seen.add(name)
        if not isinstance(item["kind"], str) or item["kind"] not in KINDS:
            raise ValueError(f"Unknown material kind: {name}")
        if not isinstance(item["keep"], str) or item["keep"] not in KEEPS:
            raise ValueError(f"Unknown keep decision: {name}")
        if not isinstance(item["use"], str) or not item["use"].strip():
            raise ValueError(f"State the material's use: {name}")
        if type(item["return"]) is not bool:
            raise ValueError(f"Return must be a boolean: {name}")
        if item["return"] and (item["kind"] not in RETURNABLE or item["keep"] != "retain"):
            raise ValueError(f"Only retained analytical evidence may return: {name}")
    return value


def signature(info):
    return {"device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def open_root(root):
    # Resolve no user-selected symlink; hold directory descriptors during observation.
    path = Path(os.path.abspath(root))
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def observe(root_fd, item):
    parts = PurePosixPath(item["path"]).parts
    directory = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = new
        before = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"Expected a regular file with one link: {item['path']}")
        result = {"path": item["path"], **signature(before)}
        if item["return"] or item["keep"] == "cleanup":
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                if signature(os.fstat(stream.fileno())) != signature(before):
                    raise ValueError(f"File changed while opening: {item['path']}")
                checksum = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(chunk)
                if signature(os.fstat(stream.fileno())) != signature(before):
                    raise ValueError(f"File changed while reading: {item['path']}")
                result["sha256"] = checksum.hexdigest()
        if signature(os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)) != signature(before):
            raise ValueError(f"File changed during observation: {item['path']}")
        return result
    finally:
        os.close(directory)


def make_plan(root, selection):
    selection = validate_selection(selection)
    root_fd = open_root(root)
    try:
        identity = os.fstat(root_fd)
        observed = [observe(root_fd, item) for item in selection["files"]]
    finally:
        os.close(root_fd)
    body = {"schema_version": 1, "scope": "explicit_files_only",
            "root_identity": {"device": identity.st_dev, "inode": identity.st_ino},
            "selection": selection, "observed": observed}
    return {**body, "plan_sha256": digest(body)}


def verify(root, plan):
    if not isinstance(plan, dict) or set(plan) != {
        "schema_version", "scope", "root_identity", "selection", "observed", "plan_sha256"
    }:
        raise ValueError("Invalid saved plan")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if digest(body) != plan["plan_sha256"]:
        raise ValueError("Saved plan was changed")
    if make_plan(root, plan["selection"]) != plan:
        raise ValueError("Selected files or root changed; make a new preview")


def markdown(plan):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["# Selected experiment materials", "",
             "Only listed files were inspected. Unlisted files and total disk use are unknown.",
             "", "| File | Use | Bytes | Retention | Return |",
             "|---|---|---:|---|---|"]
    for item, seen in zip(plan["selection"]["files"], plan["observed"]):
        lines.append("| " + " | ".join(map(cell, [item["path"], item["use"], seen["size"],
                                                 item["keep"], "yes" if item["return"] else "no"])) + " |")
    for label, criterion in [("Listed", lambda i: True), ("Return", lambda i: i["return"]),
                             ("Cleanup", lambda i: i["keep"] == "cleanup")]:
        total = sum(o["size"] for i, o in zip(plan["selection"]["files"], plan["observed"]) if criterion(i))
        lines.append(f"\n{label}: {total} bytes.")
    lines.append("\nThis is a preview. No file was copied or deleted.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["plan", "verify"])
    parser.add_argument("root")
    parser.add_argument("document", help="Selection JSON for plan, saved plan JSON for verify")
    parser.add_argument("--json", action="store_true", help="Print the machine plan")
    args = parser.parse_args(argv)
    try:
        document = read_json(args.document)
        if args.operation == "verify":
            verify(args.root, document)
            print("Unchanged preview; no files were modified.")
        else:
            plan = make_plan(args.root, document)
            print(json.dumps(plan, indent=2, ensure_ascii=False) if args.json else markdown(plan), end="\n")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Material check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
