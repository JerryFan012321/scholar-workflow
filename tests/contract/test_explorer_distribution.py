"""Read-only runtime boundary and isolated wheel execution, never installation."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]


def test_runtime_candidate_keeps_explorer_complete_and_metadata_aligned():
    script = (REPOSITORY / "scripts/make-release.sh").read_text(encoding="utf-8")
    match = re.search(r"RUNTIME_PATHS=\((.*?)\n\)", script, re.DOTALL)
    assert match is not None
    prefixes = re.findall(r'"([^"\n]+)"', match[1])
    assert len(prefixes) == len(set(prefixes))
    visible = subprocess.run(
        ["rtk", "proxy", "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPOSITORY, check=True, capture_output=True,
    )
    files = {os.fsdecode(path) for path in visible.stdout.split(b"\0") if path}
    payload = {path for path in files if (REPOSITORY / path).is_file()
               and any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)}
    required = {
        "references/knowledge-exploration.md",
        "skills/explore-knowledge/SKILL.md",
        "skills/explore-knowledge/README.md",
        "skills/explore-knowledge/README.zh-CN.md",
        *{"src/scholar_workflow/" + path for path in (
            "knowledge/exploration.py", "knowledge/exploration_cli.py",
            "knowledge/exploration_import.py", "adapters/knowledge_explorer.py",
            "adapters/exploration_readers.py", "adapters/exploration_previews.py",
            "adapters/process_environment.py", "adapters/zotflow.py",
            "workflows/exploration_assets.py", "workflows/exploration_references.py",
            "adapters/explorer_static/__init__.py", "adapters/explorer_static/index.html",
            "adapters/explorer_static/explore.js", "adapters/explorer_static/explore.css",
        )},
    }
    assert required <= payload, "Required explorer runtime files are missing: " + repr(required - payload)
    forbidden = {"dev-guide", "tests", "planning", "evals", "build", ".codex"}
    assert not any(Path(path).parts[0] in forbidden for path in payload)
    assert not payload & {"AGENT.md", "AGENTS.md", "CLAUDE.md"}
    descriptions, versions = {}, {}
    for path in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        document = json.loads((REPOSITORY / path).read_text(encoding="utf-8"))
        descriptions[path] = document["description"]
        versions[path] = document["version"]
    for path in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
        document = json.loads((REPOSITORY / path).read_text(encoding="utf-8"))
        plugin = [row for row in document["plugins"] if row["name"] == "scholar-workflow"]
        assert len(plugin) == 1
        descriptions[path] = plugin[0]["description"]
    assert len(set(descriptions.values())) == 1, descriptions
    project = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    versions["pyproject.toml"] = project["project"]["version"]
    for statement in ast.parse((REPOSITORY / "src/scholar_workflow/__init__.py").read_text()).body:
        if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in statement.targets):
            versions["package"] = ast.literal_eval(statement.value)
    assert "package" in versions and len(set(versions.values())) == 1, versions
    patterns = project["tool"]["setuptools"]["package-data"]
    assert set(patterns["scholar_workflow.adapters.explorer_static"]) >= {
        "*.html", "*.css", "*.js",
    }
    skill = (REPOSITORY / "skills/explore-knowledge/SKILL.md").read_text(encoding="utf-8")
    for reference in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^`\s]+)", skill):
        assert reference in payload, reference


def test_explorer_wheel_executes_only_its_own_package_without_installation(tmp_path):
    wheel_path = os.environ.get("SCHOLAR_EXPLORER_WHEEL")
    if not wheel_path:
        pytest.skip("Set SCHOLAR_EXPLORER_WHEEL to the exact candidate wheel for isolated execution")
    wheel = Path(wheel_path)
    assert wheel.is_absolute() and wheel.is_file() and wheel.suffix == ".whl"
    source = REPOSITORY / "src/scholar_workflow"
    version = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())["project"]["version"]
    suffixes = {".py", ".html", ".css", ".js"}
    expected = {"scholar_workflow/" + path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*") if path.is_file() and path.suffix in suffixes}
    unpacked, working = tmp_path.resolve() / "unpacked", tmp_path.resolve() / "working"
    unpacked.mkdir()
    working.mkdir()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        assert len(metadata_paths) == 1
        metadata = archive.read(metadata_paths[0]).decode("utf-8")
        assert re.search(r"^Version: (.+)$", metadata, re.MULTILINE)[1] == version
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts and "\\" not in name
            assert path.parts[0] not in {"dev-guide", "tests", "planning", "evals", "build", ".codex"}
            assert "demos" not in path.parts
            assert not name.endswith(("AGENT.md", "AGENTS.md", "CLAUDE.md"))
        actual = {name: archive.read(name) for name in names
                  if name.startswith("scholar_workflow/") and PurePosixPath(name).suffix in suffixes}
        assert actual.keys() == expected.keys(), {
            "missing": sorted(expected.keys() - actual.keys()),
            "unexpected": sorted(actual.keys() - expected.keys()),
        }
        assert all(actual[name] == expected[name] for name in expected), [
            name for name in expected if actual[name] != expected[name]
        ]
        for entry in archive.infolist():
            assert (entry.external_attr >> 16) & 0o170000 != 0o120000, entry.filename
        archive.extractall(unpacked)
    result = subprocess.run(
        [sys.executable, "-I", "-c", _ISOLATED_CHECK, str(unpacked), str(working),
         str(source.parent.resolve())],
        cwd=working, text=True, capture_output=True, check=False, timeout=60,
        env={"PATH": os.defpath, "LANG": "en_US.UTF-8",
             "SCHOLAR_WORKFLOW_HOME": str(working / "unused-scholar-config")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["native_calls"] == report["external_calls"] == 0
    assert report["query_units"] == 1 and report["source_unchanged"] is True
    assert report["static_files"] == ["index.html", "explore.css", "explore.js"]
    assert report["help_has_root"] is True
    assert report["package_version"] == version
    assert report["imported_modules"]
    for path in report["imported_modules"].values():
        assert Path(path).is_relative_to(unpacked)


_ISOLATED_CHECK = r'''
import json
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

unpacked, working, source = map(Path, sys.argv[1:])
assert Path.cwd() == working and not list(working.iterdir())
# Isolated mode does not suppress an editable installation's site .pth entry.
# Remove that source entry explicitly; every loaded package file is checked below.
sys.path[:] = [path for path in sys.path if Path(path).resolve() != source]
assert not any(Path(path).resolve() == source for path in sys.path)
assert not any(name == "scholar_workflow" or name.startswith("scholar_workflow.") for name in sys.modules)
sys.path.insert(0, str(unpacked))
Path.home = classmethod(lambda cls: working / "empty-home")
external_calls, native_calls, allowed_ports = [], [], set()

def forbidden(*args, **kwargs):
    external_calls.append(True)
    raise AssertionError("Isolated wheel must not read personal services or configuration")

connect = socket.socket.connect
def local_connect(self, address):
    if not isinstance(address, tuple) or address[0] != "127.0.0.1" or address[1] not in allowed_ports:
        return forbidden()
    return connect(self, address)
socket.socket.connect = local_connect

def no_native(*args, **kwargs):
    native_calls.append(True)
    raise AssertionError("Isolated wheel must not start another native process")
subprocess.Popen = no_native

from scholar_workflow import __version__, config
config.load_config = config.config_path = forbidden
from scholar_workflow.adapters import exploration_readers, knowledge_explorer
from scholar_workflow.adapters.exploration_readers import ReaderUnavailable
from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry
from scholar_workflow.workflows import exploration_references
ZoteroLocalAdapter.__init__ = forbidden
KnowledgeSourceRegistry.__init__ = forbidden
exploration_references.ExplorationReferenceService.__init__ = forbidden
exploration_references.field_paper_units = forbidden
exploration_references.include_resource_links = forbidden
exploration_readers.ExplorationReaderGate.__init__ = forbidden

from click.testing import CliRunner
from scholar_workflow.cli import main
help_result = CliRunner().invoke(main, ["knowledge", "explore", "--help"])
assert help_result.exit_code == 0, help_result.output
assert "--root" in help_result.output and "--no-open" in help_result.output

from scholar_workflow.knowledge.exploration import ExplorationStore, default_data
root = working / "synthetic-knowledge"
root.mkdir()
original = "# Synthetic paper analysis\n\nA complete declared fixture, not scientific evidence.\n"
(root / "Analysis.md").write_text(original, encoding="utf-8")
data = default_data()
data["works"] = [{"id": "one-whole-paper", "title": "Synthetic distribution check",
    "kind": "paper", "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper"},
    "attributes": {}, "assets": [{"id": "analysis", "kind": "markdown",
        "label": "Synthetic analysis", "uri": "Analysis.md"}]}]
store = ExplorationStore(root)
before = store.save(data, expected_revision=None)

class EmptyReferences:
    def fields(self):
        return {"fields": [], "diagnostics": ["Synthetic distribution check only"]}
    current_unit = units = reference = staticmethod(forbidden)

class EmptyVaults:
    def list_connections(self):
        return {"connections": [], "diagnostics": ["Isolated fixture only"]}
    choose = preview_adjustments = connect = documents = preview_document = staticmethod(forbidden)

class DeniedReader:
    def handles(self, uri):
        return True
    def availability(self, work, asset):
        return {"native_available": False, "native_reason": "Synthetic native launch disabled"}
    def require_current(self, work, asset):
        raise ReaderUnavailable("Synthetic native launch disabled")

server, token = knowledge_explorer.make_server(root, reference_service=EmptyReferences(),
                                              reader_gate=DeniedReader(), vault_service=EmptyVaults())
allowed_ports.add(server.server_port)
base = f"http://127.0.0.1:{server.server_port}"
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path, payload=None):
    headers = {"Authorization": "Bearer " + token}
    if payload is not None:
        headers.update({"Content-Type": "application/json", "Origin": base})
    request = urllib.request.Request(base + path, headers=headers,
        data=None if payload is None else json.dumps(payload).encode())
    try:
        response = local_opener.open(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers.get_content_type(), response.read()

try:
    status, kind, raw = request("/api/state")
    assert status == 200 and json.loads(raw) == before
    status, kind, raw = request("/api/unit-fields")
    assert status == 200 and json.loads(raw)["fields"] == []
    status, kind, raw = request("/api/vaults")
    assert status == 200 and json.loads(raw)["connections"] == []
    status, kind, raw = request("/api/query", {})
    matches = json.loads(raw)
    assert status == 200 and len(matches["works"]) == 1
    for path, expected_kind in (("/", "text/html"), ("/explore.css", "text/css"),
                                 ("/explore.js", "text/javascript")):
        status, kind, raw = request(path)
        assert status == 200 and kind == expected_kind
        filename = "index.html" if path == "/" else path[1:]
        assert raw == (unpacked / "scholar_workflow/adapters/explorer_static" / filename).read_bytes()
    status, kind, raw = request("/api/preview/one-whole-paper/analysis")
    assert status == 200 and json.loads(raw)["text"] == original
    status, kind, raw = request("/api/assets/one-whole-paper")
    assert status == 200 and json.loads(raw)[0]["native_available"] is False
    status, kind, raw = request("/api/open", {"work_id": "one-whole-paper", "asset_id": "analysis"})
    assert status == 403 and "error" in json.loads(raw)
    assert store.load() == before
    assert (root / "Analysis.md").read_text(encoding="utf-8") == original
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    assert not thread.is_alive()

modules = {}
for name, module in list(sys.modules.items()):
    if name == "scholar_workflow" or name.startswith("scholar_workflow."):
        filename = getattr(module, "__file__", None)
        assert filename is not None and Path(filename).resolve().is_relative_to(unpacked), (name, filename)
        modules[name] = str(Path(filename).resolve())
assert external_calls == native_calls == []
print(json.dumps({"imported_modules": modules, "native_calls": len(native_calls),
    "external_calls": len(external_calls), "query_units": len(matches["works"]),
    "package_version": __version__,
    "source_unchanged": True, "help_has_root": "--root" in help_result.output,
    "static_files": ["index.html", "explore.css", "explore.js"]}))
'''
