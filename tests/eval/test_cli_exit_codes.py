"""CLI-boundary exit-code assertions for eval cases.

These back the eval case `no-existence-on-unreachable` (evals/safety.json) at the
CLI boundary: a real command run through CliRunner must exit 3 when the Zotero
Local API is unreachable — never silently treat it as "not found" (INV12).

Scope note: the exit-4 safety cases (`no-unapproved-apply`,
`plan-invalidated-on-change`) have no CLI trigger path — the `apply` command signs
its own plan in-process (`approve_plan(generate_plan(...))`), so their guard lives
at the logic layer (`approvals.assert_executable`), not here.
"""
from __future__ import annotations
import yaml
from click.testing import CliRunner
from scholar_workflow.cli import main


def _write_config(home, *, local_api_url):
    """Write a minimal config.yml into a temp SCHOLAR_WORKFLOW_HOME."""
    (home / "config.yml").write_text(yaml.safe_dump({
        "version": 1,
        "papers_root": str(home / "papers"),
        "vault_root": str(home / "vault"),
        "zotero": {"local_api_url": local_api_url},
    }), encoding="utf-8")


def test_locate_fails_closed_with_exit_3_when_zotero_unreachable(tmp_path):
    # Point the adapter at a closed port so the Local API is genuinely unreachable.
    _write_config(tmp_path, local_api_url="http://127.0.0.1:1/api")
    result = CliRunner().invoke(
        main, ["locate", "2401.01234"],
        env={"SCHOLAR_WORKFLOW_HOME": str(tmp_path)},
    )
    assert result.exit_code == 3  # INV12: fail-closed, never NONE/create


def test_plan_fails_closed_with_exit_3_when_zotero_unreachable(tmp_path):
    _write_config(tmp_path, local_api_url="http://127.0.0.1:1/api")
    result = CliRunner().invoke(
        main, ["plan", "2401.01234"],
        env={"SCHOLAR_WORKFLOW_HOME": str(tmp_path)},
    )
    assert result.exit_code == 3


def test_locate_empty_identifier_is_input_error_exit_2(tmp_path):
    # Boundary contract: empty input is a user error (exit 2), not a dependency issue.
    _write_config(tmp_path, local_api_url="http://127.0.0.1:1/api")
    result = CliRunner().invoke(
        main, ["locate", "   "],
        env={"SCHOLAR_WORKFLOW_HOME": str(tmp_path)},
    )
    assert result.exit_code == 2
