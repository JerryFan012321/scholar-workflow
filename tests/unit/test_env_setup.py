"""Unit tests for the env-records scaffold (pure filesystem, tmp_path)."""
from __future__ import annotations
import yaml
from scholar_workflow.workflows.env_setup import scaffold


def test_scaffold_creates_full_skeleton(tmp_path):
    root = tmp_path / "env-records"
    result = scaffold(root)
    expected = {
        ".gitignore", "README.md",
        "servers.example.yaml", "apis.example.yaml",
        "servers.yaml", "apis.yaml", "setup/.gitkeep",
    }
    assert set(result.created) == expected
    assert result.skipped == []
    for rel in expected:
        assert (root / rel).exists()


def test_gitignore_blocks_real_records_allows_templates(tmp_path):
    root = tmp_path / "env-records"
    scaffold(root)
    gi = (root / ".gitignore").read_text()
    assert "servers.yaml" in gi
    assert "apis.yaml" in gi
    assert "!*.example.yaml" in gi


def test_templates_are_valid_yaml_with_expected_shape(tmp_path):
    root = tmp_path / "env-records"
    scaffold(root)
    servers = yaml.safe_load((root / "servers.example.yaml").read_text())
    assert "servers" in servers
    entry = servers["servers"][0]
    # three blocks: connection / environment inventory / meta
    for field in ("alias", "host", "user", "port", "key", "jump", "password",
                  "environments", "cuda_driver", "proxy", "purpose", "added"):
        assert field in entry, field
    assert isinstance(entry["environments"], list)
    env = entry["environments"][0]
    for field in ("name", "python", "cuda", "key_packages", "compat_notes", "setup_script"):
        assert field in env, field
    assert isinstance(entry["proxy"], dict)
    for field in ("http", "https", "no_proxy"):
        assert field in entry["proxy"], field

    apis = yaml.safe_load((root / "apis.example.yaml").read_text())
    assert "apis" in apis
    akey = apis["apis"][0]
    for field in ("name", "env_var", "value", "owner", "scope", "added"):
        assert field in akey, field


def test_rerun_is_idempotent_and_never_overwrites(tmp_path):
    root = tmp_path / "env-records"
    scaffold(root)
    # user fills a real record with private data
    real = root / "apis.yaml"
    real.write_text("apis:\n  - name: my-secret-key\n    value: DO-NOT-CLOBBER\n")
    before = real.read_text()

    second = scaffold(root)
    assert second.created == []                      # nothing new created
    assert "apis.yaml" in second.skipped             # real record skipped
    assert real.read_text() == before                # private data untouched


def test_setup_dir_present_for_scripts(tmp_path):
    root = tmp_path / "env-records"
    scaffold(root)
    assert (root / "setup").is_dir()
    assert (root / "setup" / ".gitkeep").exists()
