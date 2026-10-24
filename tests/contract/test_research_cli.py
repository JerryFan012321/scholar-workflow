"""Public local research operations with isolated synthetic roots only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from click.testing import CliRunner

from scholar_workflow.cli import main


def channel(**changes):
    return {"channel_id": "sample-blog", "name": "研究笔记", "publisher": "Sample Lab",
            "publisher_kind": "lab", "kind": "rss", "url": "https://example.org/feed.xml",
            "enabled": True, "topics": ["world models"], **changes}


def call(root: Path, *args):
    return CliRunner().invoke(main, ["research", *args],
                              env={"SCHOLAR_WORKFLOW_HOME": str(root)})


def test_public_empty_read_does_not_initialize(tmp_path):
    root = tmp_path / "absent"
    for args in (("sources", "list"), ("updates",)):
        result = call(root, *args, "--format", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == "uninitialized"
    assert not root.exists()


def test_public_registration_replay_and_cas(tmp_path):
    root, spec = tmp_path / "state", tmp_path / "channel.json"
    spec.write_text(json.dumps(channel()), encoding="utf-8")
    created = call(root, "sources", "register", "--spec", str(spec), "--format", "json")
    assert created.exit_code == 0, created.output
    record = json.loads(created.output)
    assert record["status"] == "created"
    repeated = call(root, "sources", "register", "--spec", str(spec), "--format", "json")
    assert json.loads(repeated.output)["status"] == "unchanged"
    assert json.loads(call(root, "sources", "list", "--format", "json").output)["channels"] == [channel()]
    spec.write_text(json.dumps(channel(enabled=False)), encoding="utf-8")
    rejected = call(root, "sources", "register", "--spec", str(spec), "--format", "json")
    assert rejected.exit_code == 5, rejected.output
    updated = call(root, "sources", "register", "--spec", str(spec),
                   "--expected-revision", record["revision"], "--format", "json")
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["status"] == "updated"


def test_public_duplicate_keys_and_symlink_spec_refuse_without_state(tmp_path):
    root, spec = tmp_path / "state", tmp_path / "bad.json"
    spec.write_text('{"channel_id":"a","channel_id":"b"}', encoding="utf-8")
    assert call(root, "sources", "register", "--spec", str(spec)).exit_code == 2
    link = tmp_path / "link.json"
    link.symlink_to(spec)
    assert call(root, "sources", "register", "--spec", str(link)).exit_code == 7
    assert not root.exists()


def test_public_event_disposition_and_escaped_readable_result(tmp_path):
    from scholar_workflow.research import apply_observation, register_source

    root = tmp_path / "state"
    register_source(root, channel())
    item = {"item_id": "article:one", "url": "https://example.org/article",
            "title": "A | B <script>alert(1)</script>",
            "content_digest": "sha256:" + hashlib.sha256(b"body").hexdigest()}
    observed = apply_observation(root, channel(), {"status": "ok", "items": [item]},
                                 "2026-10-24T12:00:00+00:00", initial_mode="report")
    event_id = observed["events"][0]["event_id"]
    marked = call(root, "mark", event_id, "--disposition", "selected", "--format", "json")
    assert marked.exit_code == 0, marked.output
    result = call(root, "updates", "--format", "json")
    assert json.loads(result.output)["events"][0]["disposition"] == "selected"
    rendered = call(root, "updates", "--language", "zh")
    assert rendered.exit_code == 0, rendered.output
    assert "&lt;script&gt;" in rendered.output and "\\|" in rendered.output
    assert event_id not in rendered.output
    assert "sha256:" not in rendered.output


def test_assets_research_provider_reads_same_store(tmp_path):
    from scholar_workflow.research import register_source

    root = tmp_path / "state"
    register_source(root, channel())
    before = (root / "research-sources.yml").read_bytes()
    result = CliRunner().invoke(main, ["assets", "list", "--kind", "research", "--format", "json"],
                                env={"SCHOLAR_WORKFLOW_HOME": str(root)})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload["providers"]) == {"research"}
    assert payload["providers"]["research"]["channels"][0]["channel_id"] == "sample-blog"
    assert (root / "research-sources.yml").read_bytes() == before
    assert not (root / "research").exists()
