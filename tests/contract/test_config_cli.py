"""Contract tests for the `config` CLI surface: init/set/get/show/path exit codes,
JSON output shape, missing-file guidance, and doctor's graceful degradation.
"""
from __future__ import annotations
import json
from click.testing import CliRunner
from scholar_workflow.cli import main


def _run(args, home):
    return CliRunner().invoke(main, args, env={"SCHOLAR_WORKFLOW_HOME": str(home)})


def test_path_succeeds_without_file(tmp_path):
    r = _run(["config", "path"], tmp_path)
    assert r.exit_code == 0
    assert r.output.strip() == str(tmp_path / "config.yml")


def test_init_then_show_roundtrip(tmp_path):
    r = _run(["config", "init", "--research-vault-root", str(tmp_path / "v")], tmp_path)
    assert r.exit_code == 0
    assert json.loads(r.output)["config"] == str(tmp_path / "config.yml")
    show = _run(["config", "show", "--raw"], tmp_path)
    assert show.exit_code == 0 and "research_vault_root" in show.output


def test_init_missing_required_vault_is_exit_2(tmp_path):
    r = _run(["config", "init"], tmp_path)
    assert r.exit_code == 2  # click: missing required option


def test_set_before_init_gives_guidance_exit_2(tmp_path):
    r = _run(["config", "set", "notion.enabled", "true"], tmp_path)
    assert r.exit_code == 2
    assert "config init" in r.output


def test_set_and_get(tmp_path):
    _run(["config", "init", "--research-vault-root", str(tmp_path / "v")], tmp_path)
    s = _run(["config", "set", "link_service.port", "9200"], tmp_path)
    assert s.exit_code == 0 and json.loads(s.output)["link_service.port"] == 9200
    g = _run(["config", "get", "link_service.port"], tmp_path)
    assert g.exit_code == 0 and g.output.strip() == "9200"


def test_set_unknown_key_exit_2(tmp_path):
    _run(["config", "init", "--research-vault-root", str(tmp_path / "v")], tmp_path)
    r = _run(["config", "set", "no.such.key", "1"], tmp_path)
    assert r.exit_code == 2 and "Unknown config key" in r.output


def test_show_raw_before_init_exit_3(tmp_path):
    r = _run(["config", "show", "--raw"], tmp_path)
    assert r.exit_code == 3 and "config init" in r.output


def test_doctor_missing_config_no_traceback_exit_3(tmp_path):
    r = _run(["doctor"], tmp_path)
    assert r.exit_code == 3
    assert "Traceback" not in r.output
    assert "config init" in r.output


def test_doctor_missing_config_json_shape(tmp_path):
    r = _run(["doctor", "--json"], tmp_path)
    assert r.exit_code == 3
    payload = json.loads(r.output)
    assert payload["ok"] is False and payload["configured"] is False
