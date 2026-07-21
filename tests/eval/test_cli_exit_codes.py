"""CLI-boundary exit-code tests.

After the zotero-mcp pivot, the only surviving exit-3 (dependency) trigger is
`doctor` reporting a missing local config path — its meaning shifted from "Zotero
unreachable" to "a required local path is missing". Existence/dedup/writes now run
in the host LLM via zotero-mcp, so they have no CLI trigger path here. The exit-4
(needs-approval) cases likewise have no CLI trigger — `apply` signs its own plan
in-process — so that guard stays at the logic layer (approvals.assert_executable).
"""
from __future__ import annotations
import textwrap
from click.testing import CliRunner
from scholar_workflow.cli import main


def _write_config(home, papers_root):
    (home / "config.yml").write_text(textwrap.dedent(f"""\
        version: 1
        papers_root: {papers_root}
        paper_inbox: {home}/inbox
        vault_root: {home}/vault
    """))


def test_doctor_exits_3_when_local_path_missing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "vault").mkdir()
    _write_config(home, papers_root=str(tmp_path / "does-not-exist"))

    result = CliRunner().invoke(main, ["doctor"], env={"SCHOLAR_WORKFLOW_HOME": str(home)})

    assert result.exit_code == 3


def test_apply_empty_inputs_is_input_error_exit_2(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _write_config(home, papers_root=str(home))

    result = CliRunner().invoke(main, ["apply", ""], env={"SCHOLAR_WORKFLOW_HOME": str(home)})

    assert result.exit_code == 2
