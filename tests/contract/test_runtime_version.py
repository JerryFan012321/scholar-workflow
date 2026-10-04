"""Public runtime identity must match both hosts and the distributable package."""

import json
import tomllib
from pathlib import Path

from click.testing import CliRunner

from scholar_workflow import __version__
from scholar_workflow.cli import main


def test_runtime_version_matches_distribution_and_hosts():
    root = Path(__file__).resolve().parents[2]
    package = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert __version__ == package
    for host in (".codex-plugin", ".claude-plugin"):
        assert json.loads((root / host / "plugin.json").read_text())["version"] == package
    result = CliRunner().invoke(main, ["--version"], prog_name="scholar-workflow")
    assert result.exit_code == 0
    assert result.output.strip() == f"scholar-workflow, version {package}"
