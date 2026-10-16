"""Run bounded synthetic acceptance against a normally installed CLI only.

This runner uses only the standard library. It neither imports Scholar Workflow nor
requires an editor, a network request, a remote login, or an existing private ledger.
Run only after the explicitly authorized hotfix has been normally installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

FIXTURE_FILES = (
    "servers.yaml", "server-new.json", "server-update.json", "fields.yml",
    "knowledge-inventory.json", "host-cases.json",
)
LEGACY_MARKER = "SYNTHETIC_ONLY_LEGACY_PASSWORD_DO_NOT_USE_83A7"


class AcceptanceFailure(Exception):
    """A controlled failure message that never contains captured CLI payloads."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def fixture_scalar(text: str, name: str) -> str:
    """Read one simple scalar from this frozen YAML fixture, not general YAML."""
    matches = re.findall(rf"(?m)^\s*(?:-\s*)?{re.escape(name)}:\s*([^\n#]+?)\s*$", text)
    require(len(matches) == 1, f"Frozen manifest must have exactly one {name}")
    return matches[0].strip().strip("\"'")


def legacy_belongs_to_selected_record(path: Path, alias: str) -> bool:
    """Locate the sentinel's YAML record without loading a credential library."""
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"(?m)^( *)-\s+[A-Za-z_][A-Za-z_0-9]*:", text))
    if not starts:
        return False
    outer_indent = min(len(match.group(1)) for match in starts)
    starts = [match for match in starts if len(match.group(1)) == outer_indent]
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.start():end]
        names = re.findall(r"(?m)^\s*(?:-\s*)?alias:\s*([^\n#]+?)\s*$", block)
        if len(names) == 1 and names[0].strip().strip("\"'") == alias:
            pattern = rf"(?m)^\s*password:\s*[\"']?{re.escape(LEGACY_MARKER)}[\"']?\s*$"
            return re.search(pattern, block) is not None and text.count(LEGACY_MARKER) == 1
    return False


class InstalledCLI:
    def __init__(self, executable: Path, root: Path):
        self.executable = executable
        self.root = root
        self.commands: list[dict] = []
        # Do not inherit tokens, proxy settings, PYTHONPATH, or credential variables.
        self.environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "SCHOLAR_WORKFLOW_HOME": str(root / "state"),
        }

    def call(self, label: str, *arguments: str, expected_exit: int = 0) -> str:
        try:
            result = subprocess.run(
                [str(self.executable), *arguments],
                cwd=self.root,
                env=self.environment,
                shell=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AcceptanceFailure(f"Installed CLI timed out at {label}") from None
        except OSError:
            raise AcceptanceFailure(f"Installed CLI could not start at {label}") from None
        require(
            LEGACY_MARKER not in result.stdout and LEGACY_MARKER not in result.stderr,
            f"Forbidden synthetic credential exposure at {label}",
        )
        self.commands.append({"check": label, "exit_code": result.returncode})
        require(result.returncode == expected_exit, f"Unexpected CLI exit code at {label}")
        return result.stdout

    def json(self, label: str, *arguments: str) -> dict:
        output = self.call(label, *arguments, "--format", "json")
        try:
            value = json.loads(output)
        except (ValueError, TypeError):
            raise AcceptanceFailure(f"Installed CLI did not return JSON at {label}") from None
        require(isinstance(value, dict), f"Installed CLI JSON is not an object at {label}")
        return value


def run(arguments: argparse.Namespace) -> dict:
    cli_argument = Path(arguments.cli)
    require(cli_argument.is_absolute(), "CLI path must be explicit and absolute")
    cli = cli_argument.resolve(strict=True)
    require(cli.is_file() and os.access(cli, os.X_OK), "Installed CLI must be an executable file")
    require(cli.name == "scholar-workflow", "Expected the installed scholar-workflow entry point")
    fixture_root = Path(arguments.fixtures).resolve(strict=True)
    require(fixture_root.is_dir(), "Fixture directory is unavailable")
    requested_root = Path(arguments.root)
    require(requested_root.is_absolute(), "Acceptance root must be explicit and absolute")
    require(requested_root.name not in {"", ".", ".."}, "Acceptance root must be a dedicated directory")
    require(not requested_root.is_symlink(), "Acceptance root may not be a symlink")
    root = requested_root.parent.resolve(strict=True) / requested_root.name
    require(root != fixture_root and fixture_root not in root.parents, "Do not write inside frozen fixtures")
    if root.exists():
        require(root.is_dir() and not any(root.iterdir()), "Acceptance root must be new or empty")
    else:
        root.mkdir(mode=0o700)
    root.chmod(0o700)
    frozen = root / "frozen-inputs"
    frozen.mkdir(mode=0o700)
    fixture_hashes: dict[str, str] = {}
    for name in FIXTURE_FILES:
        source = fixture_root / name
        require(source.is_file() and not source.is_symlink(), f"Unsafe or missing frozen fixture: {name}")
        require(source.stat().st_size <= 65536, f"Oversized frozen fixture: {name}")
        fixture_hashes[name] = digest(source)
        shutil.copyfile(source, frozen / name)
        (frozen / name).chmod(0o400)

    installed = InstalledCLI(cli, root)
    version_output = installed.call("installed-version", "--version")
    versions = re.findall(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])", version_output)
    require(versions == [arguments.expected_version], "Installed CLI version does not match the authorized candidate")
    installed.call("isolated-config-init", "config", "init")
    ledger_root = root / "private-ledger"
    ledger_root.mkdir(mode=0o700)
    ledger = ledger_root / "servers.yaml"
    shutil.copyfile(frozen / "servers.yaml", ledger)
    ledger.chmod(0o600)
    installed.call("isolated-config-ledger", "config", "set", "env_records_root", str(ledger_root))

    # Assemble only the existing public registry shape, using original fixture IDs.
    inventory = json.loads((frozen / "knowledge-inventory.json").read_text(encoding="utf-8"))
    selected = inventory["registered_sources"][0]
    manifest_text = (frozen / "fields.yml").read_text(encoding="utf-8")
    source_id = fixture_scalar(manifest_text, "source_id")
    field_id = fixture_scalar(manifest_text, "field_id")
    field_title = fixture_scalar(manifest_text, "title")
    home_name = fixture_scalar(manifest_text, "home")
    require(source_id == selected["source_id"], "Frozen Source identities disagree")
    require(home_name == Path(home_name).name, "Synthetic homepage must be one safe filename")
    knowledge_root = root / "synthetic-knowledge-source"
    (knowledge_root / ".scholar-workflow").mkdir(parents=True, mode=0o700)
    manifest = knowledge_root / ".scholar-workflow" / "fields.yml"
    shutil.copyfile(frozen / "fields.yml", manifest)
    manifest.chmod(0o600)
    home = knowledge_root / home_name
    home.write_text(f"# {field_title}\n\nSynthetic inventory input only.\n", encoding="utf-8")
    home.chmod(0o600)
    registry = root / "state" / "hub" / "sources.json"
    registry.parent.mkdir(mode=0o700, exist_ok=True)
    write_json(registry, {
        "schema_version": 1,
        "folders": [{
            "folder_id": "synthetic-world-models", "root": str(knowledge_root),
            "enabled": True, "capabilities": ["read"],
        }],
        "sources": [{
            "source_id": source_id, "provider": "obsidian",
            "folder_id": "synthetic-world-models", "enabled": selected["enabled"],
            "capabilities": ["read"],
        }],
    })
    protected = {path: digest(path) for path in [manifest, home, registry, *frozen.iterdir()]}
    original_ledger = ledger.read_bytes()
    original_mode = stat.S_IMODE(ledger.stat().st_mode)
    old_spec = json.loads((frozen / "server-update.json").read_text(encoding="utf-8"))
    new_spec = json.loads((frozen / "server-new.json").read_text(encoding="utf-8"))
    alias = old_spec["alias"]
    require(legacy_belongs_to_selected_record(ledger, alias), "Frozen legacy credential record is unavailable")

    overview = installed.json("A01-existing-assets", "assets", "list", "--kind", "all")
    require(set(overview["providers"]) == {"server", "knowledge"}, "CLI must expose only the requested authoritative providers")
    servers = overview["providers"]["server"]["servers"]
    require(len(servers) == 1 and servers[0]["alias"] == alias, "Existing server inventory differs from frozen input")
    sources = overview["providers"]["knowledge"]["sources"]
    require(len(sources) == 1 and sources[0]["source_id"] == source_id, "Existing Source identity was not retained")
    require([item["field_id"] for item in sources[0]["fields"]] == [field_id], "Existing Field identity was not retained")
    shown = installed.json("A04-existing-server", "assets", "server", "show", alias)
    for field in ("alias", "host", "user", "port", "environments", "credential_ref"):
        require(shown["server"].get(field) == old_spec[field], f"Saved server facts differ at {field}")
    installed.json("A04-local-check", "assets", "server", "check")
    initial_public = installed.call("A01-public-list", "assets", "list", "--kind", "all", "--format", "md", "--language", "zh")
    require(ledger.read_bytes() == original_ledger, "Read-only CLI commands changed the ledger")
    require(stat.S_IMODE(ledger.stat().st_mode) == original_mode, "Read-only CLI commands changed ledger permissions")
    require(all(digest(path) == value for path, value in protected.items()), "Read-only CLI commands changed protected input")

    created = installed.json("A05-register", "assets", "server", "register", "--spec", str(frozen / "server-new.json"))
    require(created["status"] == "created", "Explicit new registration was not reported as created")
    readback = installed.json("A05-readback", "assets", "server", "show", new_spec["alias"])
    for field, expected in new_spec.items():
        require(readback["server"].get(field) == expected, f"New record read-back differs at {field}")
    require(legacy_belongs_to_selected_record(ledger, alias), "New registration changed the legacy credential record")
    first_registered = ledger.read_bytes()
    repeated = installed.json("A06-identical-repeat", "assets", "server", "register", "--spec", str(frozen / "server-new.json"))
    require(repeated["status"] == "unchanged", "Identical registration was not reported as unchanged")
    require(ledger.read_bytes() == first_registered, "Identical registration was not byte-idempotent")

    before_update = installed.json("A08-current-revision", "assets", "server", "show", alias)
    revision = before_update["revision"]
    require(isinstance(revision, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", revision) is not None, "CLI revision does not follow the public interface")
    updated = installed.json("A08-current-update", "assets", "server", "register", "--spec", str(frozen / "server-update.json"), "--expected-revision", revision)
    require(updated["status"] == "updated", "Current-revision metadata change was not reported as updated")
    require(legacy_belongs_to_selected_record(ledger, alias), "Safe metadata update lost the legacy credential")
    update_readback = installed.json("A08-update-readback", "assets", "server", "show", alias)
    for field, expected in old_spec.items():
        require(update_readback["server"].get(field) == expected, f"Updated record read-back differs at {field}")
    successful_bytes = ledger.read_bytes()
    stale_spec = root / "stale-request.json"
    write_json(stale_spec, {"alias": alias, "purpose": "Must not overwrite a newer ledger revision"})
    installed.call("A08-stale-refusal", "assets", "server", "register", "--spec", str(stale_spec), "--expected-revision", revision, "--format", "json", expected_exit=7)
    require(ledger.read_bytes() == successful_bytes, "Stale registration overwrote the current ledger")
    require(stat.S_IMODE(ledger.stat().st_mode) == 0o600, "Updated private ledger permissions are unsafe")
    require(not (ledger_root / "apis.yaml").exists() and not (ledger_root / "setup").exists(), "Server operation initialized unrelated private assets")
    final = installed.json("final-record-count", "assets", "list", "--kind", "all")
    require({item["alias"] for item in final["providers"]["server"]["servers"]} == {alias, new_spec["alias"]}, "Registration duplicated or lost a server")
    require(len(final["providers"]["server"]["servers"]) == 2, "Registration created duplicate server aliases")
    require(all(digest(path) == value for path, value in protected.items()), "Asset registration changed Knowledge or frozen inputs")
    require(all(digest(fixture_root / name) == value for name, value in fixture_hashes.items()), "Original frozen fixture files changed")
    public_list = installed.call("final-public-list", "assets", "list", "--kind", "all", "--format", "md", "--language", "zh")
    require(LEGACY_MARKER not in initial_public + public_list, "Public list exposed a credential marker")
    display = root / "资产清单.md"
    display.write_text(
        "# 安装态资产验收\n\n以下均为虚构资产，仅验证本地登记与查询。未连接服务器、未打开应用、"
        "未修改真实台账或 Vault。原生已知 Vault 库存和宿主主动查询行为需另行验收。\n\n"
        + public_list + "\n\n结果：新增后可查询，重复登记未改字节，过期更新已拒绝，知识身份保持。"
        "外观与易用性仍待人工评鉴。\n",
        encoding="utf-8",
    )
    display.chmod(0o600)
    summary = {
        "status": "passed",
        "scope": "Installed CLI with isolated synthetic local assets only",
        "version": arguments.expected_version,
        "executable": str(cli),
        "root": str(root),
        "server_count": 2,
        "source_id": source_id,
        "field_id": field_id,
        "source_and_fixture_bytes_preserved": True,
        "legacy_credential_preserved_and_not_emitted": True,
        "checks": installed.commands,
        "display": str(display),
        "human_review": "pending",
        "host_behavior": "not-tested",
        "native_inventory": "not-tested",
    }
    write_json(root / "result.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated installed asset CLI acceptance")
    parser.add_argument("--cli", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--expected-version", required=True)
    arguments = parser.parse_args()
    previous_mask = os.umask(0o077)
    try:
        summary = run(arguments)
    except AcceptanceFailure as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False))
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        # Do not serialize exceptions carrying parser data or captured child output.
        print(json.dumps({"status": "failed", "reason": "Unsafe input, unavailable file, or unexpected public CLI shape"}))
        return 1
    finally:
        os.umask(previous_mask)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
