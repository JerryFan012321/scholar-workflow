"""Unit tests for config.yml primitives: path resolution, minimal atomic init,
dotted-key set with type coercion, and unknown/secret-key rejection.

These exercise the pure functions (no CLI); the CLI wrapper is covered in
tests/contract/test_config_cli.py.
"""
from __future__ import annotations
import pytest
from scholar_workflow import config as C


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
    return tmp_path


def test_config_path_honours_home(home):
    assert C.config_path() == home / "config.yml"


def test_config_path_no_existence_requirement(home):
    # Never raises even though nothing has been written yet.
    assert not C.config_path().exists()


def test_init_writes_minimal_not_all_defaults(home):
    p = C.init_config("~/research")
    text = p.read_text()
    assert "research_vault_root" in text and "version" in text
    # A minimal write must NOT dump defaulted blocks the user never set.
    assert "obsidian:" not in text
    assert "policy:" not in text
    assert "link_service:" not in text


def test_init_with_extras_nested(home):
    p = C.init_config("~/research", {"notion.enabled": "true", "link_service.port": "9000"})
    cfg = C.load_config()
    assert cfg.notion.enabled is True
    assert cfg.link_service.port == 9000
    assert p.exists()


def test_code_repo_root_defaulted_and_settable(home):
    from pathlib import Path
    # Not dumped on a minimal init (it is a default, not user-set).
    p = C.init_config("~/research")
    assert "code_repo_root" not in p.read_text()
    # The default is the exact documented path, not merely "some absolute path".
    assert C.load_config().code_repo_root == (Path.home() / "code" / "paper-repos").resolve()
    # It is a settable, ~-expanded key.
    C.set_config_value("code_repo_root", "~/code/repos")
    assert C.load_config().code_repo_root == (Path.home() / "code" / "repos").resolve()


def test_code_repo_root_expands_env_var(home, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("MY_REPO_DIR", str(home / "repos"))
    C.init_config("~/research")
    C.set_config_value("code_repo_root", "$MY_REPO_DIR/papers")
    assert C.load_config().code_repo_root == (home / "repos" / "papers").resolve()


def test_init_idempotent_byte_stable(home):
    p1 = C.init_config("~/research", {"notion.enabled": "true"})
    b1 = p1.read_bytes()
    p2 = C.init_config("~/research", {"notion.enabled": "true"})
    assert p1 == p2
    assert p2.read_bytes() == b1  # identical re-init is a true no-op


def test_init_conflict_refused_no_force(home):
    C.init_config("~/research")
    with pytest.raises(C.ConfigError, match="already exists"):
        C.init_config("~/somewhere-else")


def test_load_config_missing_raises_confignotfound(home):
    with pytest.raises(C.ConfigNotFound):
        C.load_config()
    # ConfigNotFound must remain a FileNotFoundError for backward compatibility.
    assert issubclass(C.ConfigNotFound, FileNotFoundError)


def test_set_bool_coercion_strict(home):
    C.init_config("~/research")
    assert C.set_config_value("notion.enabled", "true") is True
    assert C.set_config_value("notion.enabled", "false") is False
    with pytest.raises(C.ConfigError, match="true or false"):
        C.set_config_value("notion.enabled", "yes")


def test_set_int_coercion(home):
    C.init_config("~/research")
    assert C.set_config_value("link_service.port", "9100") == 9100
    with pytest.raises(C.ConfigError, match="integer"):
        C.set_config_value("link_service.port", "abc")


def test_set_rejects_unknown_key_without_writing(home):
    C.init_config("~/research")
    before = C.config_path().read_bytes()
    with pytest.raises(C.ConfigError, match="Unknown config key"):
        C.set_config_value("does.not.exist", "x")
    assert C.config_path().read_bytes() == before  # nothing touched


def test_set_rejects_secret_key(home):
    C.init_config("~/research")
    with pytest.raises(C.ConfigError, match="secret"):
        C.set_config_value("notion.cookie", "abc")


def test_set_missing_file_raises_confignotfound(home):
    with pytest.raises(C.ConfigNotFound):
        C.set_config_value("notion.enabled", "true")


def test_set_preserves_comments(home):
    p = C.init_config("~/research")
    p.write_text("# hand-written note\n" + p.read_text())
    C.set_config_value("notion.enabled", "true")
    assert "# hand-written note" in p.read_text()
