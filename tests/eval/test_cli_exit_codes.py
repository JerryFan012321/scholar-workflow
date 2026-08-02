"""CLI-boundary exit-code tests.

After the zotero-mcp pivot, the only surviving exit-3 (dependency) trigger is
`doctor` reporting a missing local config path — its meaning shifted from "Zotero
unreachable" to "a required local path is missing". Existence/dedup/writes now run
in the host LLM via zotero-mcp, so they have no CLI trigger path here.
"""
from __future__ import annotations
import textwrap
from click.testing import CliRunner
from scholar_workflow.cli import main


def _write_config(home, research_vault_root):
    (home / "config.yml").write_text(textwrap.dedent(f"""\
        version: 1
        paper_inbox: {home}/inbox
        research_vault_root: {research_vault_root}
    """))


def test_doctor_exits_3_when_local_path_missing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "inbox").mkdir()
    _write_config(home, research_vault_root=str(tmp_path / "does-not-exist"))

    result = CliRunner().invoke(main, ["doctor"], env={"SCHOLAR_WORKFLOW_HOME": str(home)})

    assert result.exit_code == 3


def test_apply_empty_inputs_is_input_error_exit_2(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _write_config(home, research_vault_root=str(home))

    result = CliRunner().invoke(main, ["apply", ""], env={"SCHOLAR_WORKFLOW_HOME": str(home)})

    assert result.exit_code == 2
