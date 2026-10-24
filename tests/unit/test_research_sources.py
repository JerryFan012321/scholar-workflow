"""Independent synthetic subscription fixtures; no user config or outbound requests."""
from __future__ import annotations

import os
import stat

import pytest

from scholar_workflow.research import ResearchError, read_sources, register_source, validate_channel


def channel(**changes):
    return {
        "channel_id": "lab-news", "name": "Research updates", "publisher": "Example Lab",
        "publisher_kind": "lab", "kind": "rss", "url": "https://example.test/feed.xml",
        "enabled": True, "topics": ["world models"], **changes,
    }


def test_missing_sources_and_updates_do_not_initialize(tmp_path):
    from scholar_workflow.research import read_updates

    root = tmp_path / "missing"
    assert read_sources(root) == {
        "schema_version": 1, "status": "uninitialized", "revision": "absent",
        "channels": [], "diagnostics": [],
    }
    assert read_updates(root)["status"] == "uninitialized"
    assert not root.exists()


def test_registration_private_files_and_stable_replay(tmp_path):
    root = tmp_path / "home"
    result = register_source(root, channel())
    path = root / "research-sources.yml"
    before = path.read_bytes()
    assert result["status"] == "created"
    assert result["channel"] == channel()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    replay = register_source(root, channel())
    assert replay["status"] == "unchanged"
    assert replay["revision"] == result["revision"]
    assert path.read_bytes() == before
    assert read_sources(root)["channels"] == [channel()]
    assert not (root / "research").exists()


def test_source_patch_requires_current_revision_and_preserves_other_channels(tmp_path):
    root = tmp_path / "home"
    register_source(root, channel())
    second = channel(channel_id="other", url="https://other.example.test/feed")
    revision = register_source(root, second)["revision"]
    before = (root / "research-sources.yml").read_bytes()
    for expected in (None, "absent", "sha256:" + "0" * 64):
        with pytest.raises(ResearchError) as caught:
            register_source(root, {"channel_id": "lab-news", "enabled": False},
                            expected_revision=expected)
        assert caught.value.exit_code == 5
        assert (root / "research-sources.yml").read_bytes() == before
    result = register_source(root, {"channel_id": "lab-news", "enabled": False},
                             expected_revision=revision)
    assert result["status"] == "updated"
    assert read_sources(root)["channels"] == [channel(enabled=False), second]


@pytest.mark.parametrize("kind", ["rss", "atom", "webpage", "github_releases", "hf_models"])
def test_channel_kinds_and_defaults(kind):
    record = channel(kind=kind)
    del record["enabled"]
    del record["topics"]
    assert validate_channel(record) == channel(kind=kind, topics=[])


@pytest.mark.parametrize("changes", [
    {"url": "http://example.test/feed"},
    {"url": "https://user:DO-NOT-ECHO@example.test/feed"},
    {"url": "https://example.test/feed#fragment"},
    {"url": "https://127.0.0.1/feed"},
    {"url": "https://[::1]/feed"},
    {"url": "https://localhost/feed"},
    {"url": "https://example.test/feed?api_key=DO-NOT-ECHO"},
    {"token": "DO-NOT-ECHO"},
    {"name": "-----BEGIN PRIVATE KEY----- DO-NOT-ECHO"},
    {"channel_id": "../escape"},
    {"kind": "paper"},
    {"enabled": "yes"},
    {"topics": ["same", "same"]},
    {"publisher_kind": "arbitrary"},
    {"unexpected": "body"},
])
def test_invalid_source_is_rejected_before_creating_root(tmp_path, changes):
    root = tmp_path / "missing"
    with pytest.raises(ResearchError) as caught:
        register_source(root, channel(**changes))
    assert "DO-NOT-ECHO" not in str(caught.value)
    assert not root.exists()


def test_symlink_root_and_ledger_are_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert read_sources(alias)["status"] == "invalid"
    with pytest.raises(ResearchError) as caught:
        register_source(alias, channel())
    assert caught.value.exit_code == 7
    external = tmp_path / "external.yml"
    external.write_text("schema_version: 1\nchannels: []\n")
    external.chmod(0o600)
    (real / "research-sources.yml").symlink_to(external)
    assert read_sources(real)["status"] == "invalid"
    with pytest.raises(ResearchError):
        register_source(real, channel())
    assert external.read_text() == "schema_version: 1\nchannels: []\n"


def test_symlink_lock_and_hardlink_ledger_are_refused(tmp_path):
    root = tmp_path / "home"
    register_source(root, channel())
    lock = root / ".research.lock"
    lock.unlink()
    outside = tmp_path / "outside"
    outside.write_text("keep")
    lock.symlink_to(outside)
    with pytest.raises(ResearchError):
        register_source(root, channel(channel_id="another"))
    assert outside.read_text() == "keep"
    lock.unlink()
    os.link(root / "research-sources.yml", root / "alias.yml")
    assert read_sources(root)["status"] == "invalid"


@pytest.mark.parametrize("text", [
    "schema_version: 1\nschema_version: 1\nchannels: []\n",
    "schema_version: 9\nchannels: []\n",
    "schema_version: 1\nchannels: []\nsecret: DO-NOT-ECHO\n",
    "schema_version: 1\nchannels: &loop [*loop]\n",
])
def test_malformed_sources_are_diagnostic_and_read_only(tmp_path, text):
    root = tmp_path / "home"
    root.mkdir(mode=0o700)
    path = root / "research-sources.yml"
    path.write_text(text)
    path.chmod(0o600)
    before = path.read_bytes()
    result = read_sources(root)
    assert result["status"] == "invalid"
    assert result["channels"] == []
    assert "DO-NOT-ECHO" not in str(result)
    assert path.read_bytes() == before


def test_empty_valid_registry_is_available_without_state(tmp_path):
    root = tmp_path / "home"
    root.mkdir(mode=0o700)
    path = root / "research-sources.yml"
    path.write_text("schema_version: 1\nchannels: []\n")
    path.chmod(0o600)
    assert read_sources(root)["status"] == "available"
    assert read_sources(root)["channels"] == []


def test_direct_registry_edit_during_registration_is_not_overwritten(tmp_path, monkeypatch):
    from scholar_workflow.research import store

    root = tmp_path / "home"
    receipt = register_source(root, channel())
    path = root / "research-sources.yml"
    outside_edit = b"schema_version: 1\nchannels: []\n"
    original_dump = store.dump_registry

    def editing_dump(document):
        output = original_dump(document)
        path.write_bytes(outside_edit)
        return output

    monkeypatch.setattr(store, "dump_registry", editing_dump)
    with pytest.raises(ResearchError) as caught:
        register_source(root, {"channel_id": "lab-news", "name": "Changed"},
                        expected_revision=receipt["revision"])
    assert caught.value.exit_code == 5
    assert path.read_bytes() == outside_edit
    assert not list(root.glob(".research-*.tmp"))


@pytest.mark.parametrize("duplicate_url", [
    "https://EXAMPLE.TEST", "https://example.test:443/", "https://example.test/",
])
def test_same_url_cannot_be_registered_under_another_channel_id(tmp_path, duplicate_url):
    root = tmp_path / "home"
    register_source(root, channel(url="https://example.test"))
    before = (root / "research-sources.yml").read_bytes()
    with pytest.raises(ResearchError) as caught:
        register_source(root, channel(channel_id="duplicate", url=duplicate_url))
    assert caught.value.exit_code == 5
    assert (root / "research-sources.yml").read_bytes() == before
