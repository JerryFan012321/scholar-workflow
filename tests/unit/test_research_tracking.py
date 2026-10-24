"""State-machine fixtures prepared separately from implementation; never fetch a site."""
from __future__ import annotations

import hashlib
import json
import stat

import pytest

from scholar_workflow.research import (
    ResearchError,
    apply_observation,
    mark_event,
    read_sources,
    read_updates,
    register_source,
)


def source(channel_id="lab-news", **changes):
    return {"channel_id": channel_id, "name": "Lab news", "publisher": "Example Lab",
            "publisher_kind": "lab", "kind": "rss", "url": "https://example.test/feed",
            "enabled": True, "topics": [], **changes}


def item(item_id="entry-1", text="first", **changes):
    return {"item_id": item_id, "url": "https://example.test/posts/" + item_id,
            "title": "A model update", "content_digest": "sha256:" + hashlib.sha256(
                text.encode()).hexdigest(), **changes}


def ok(*items, **extra):
    return {"status": "ok", "items": list(items), **extra}


def test_baseline_new_update_failure_304_and_idempotent_replay(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    baseline = apply_observation(root, channel, ok(item(), etag='"one"'),
                                 "2026-01-01T00:00:00Z")
    assert baseline["status"] == "baseline"
    assert baseline["events"] == []
    assert read_updates(root)["events"] == []
    result = apply_observation(root, channel, ok(item(), item("entry-2")),
                               "2026-01-02T00:00:00Z")
    assert [event["kind"] for event in result["events"]] == ["new"]
    update = apply_observation(root, channel, ok(item("entry-2", text="changed")),
                               "2026-01-03T00:00:00Z")
    assert [event["kind"] for event in update["events"]] == ["updated"]
    state = root / "research" / "tracking.json"
    before = state.read_bytes()
    replay = apply_observation(root, channel, ok(item("entry-2", text="changed")),
                               "2026-01-03T00:00:00Z")
    assert replay["status"] == "unchanged"
    assert replay["events"] == []
    assert state.read_bytes() == before
    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    failure = apply_observation(root, channel, {
        "status": "failed", "items": [], "diagnostic": "token=DO-NOT-ECHO"},
        "2026-01-04T00:00:00Z")
    assert failure["status"] == "failed"
    summary = read_updates(root)["channels"][0]
    assert summary["last_success_at"] == "2026-01-03T00:00:00Z"
    assert summary["observed_item_count"] == 2
    assert "DO-NOT-ECHO" not in state.read_text()
    assert len(read_updates(root)["events"]) == 2
    response = apply_observation(root, channel, {"status": "not_modified", "items": []},
                                 "2026-01-05T00:00:00Z")
    assert response["status"] == "not_modified"
    assert read_updates(root)["channels"][0]["last_success_at"] == "2026-01-05T00:00:00Z"


def test_initial_report_is_explicit_and_dispositions_preserve_event_identity(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    result = apply_observation(root, channel, ok(item()), "2026-01-01T00:00:00+00:00",
                               initial_mode="report")
    assert [event["kind"] for event in result["events"]] == ["discovered"]
    event_id = result["events"][0]["event_id"]
    for disposition in ["read", "selected", "ignored", "unread"]:
        assert mark_event(root, event_id, disposition)["event"]["disposition"] == disposition
        assert read_updates(root)["events"][0]["event_id"] == event_id
    before = (root / "research" / "tracking.json").read_bytes()
    assert mark_event(root, event_id, "unread")["status"] == "unchanged"
    assert (root / "research" / "tracking.json").read_bytes() == before
    with pytest.raises(ResearchError):
        mark_event(root, event_id, "archived")


def test_first_304_fails_without_creating_success_checkpoint(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    result = apply_observation(root, channel, {"status": "not_modified", "items": []},
                               "2026-01-01T00:00:00Z")
    assert result["status"] == "failed"
    summary = read_updates(root)["channels"][0]
    assert summary["last_success_at"] is None
    assert summary["observed_item_count"] == 0
    assert result["diagnostics"][0]["code"] == "baseline_required"


def test_empty_success_is_valid_baseline_and_later_entries_are_new(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    assert apply_observation(root, channel, ok(), "2026-01-01T00:00:00Z")["status"] == "baseline"
    later = apply_observation(root, channel, ok(item()), "2026-01-02T00:00:00Z")
    assert later["events"][0]["kind"] == "new"


def test_stale_configuration_and_out_of_order_observations_never_write(tmp_path):
    root = tmp_path / "home"
    channel = source()
    revision = register_source(root, channel)["revision"]
    apply_observation(root, channel, ok(item()), "2026-01-02T00:00:00Z")
    state = root / "research" / "tracking.json"
    before = state.read_bytes()
    with pytest.raises(ResearchError) as caught:
        apply_observation(root, channel, ok(item()), "2026-01-01T00:00:00Z")
    assert caught.value.exit_code == 5
    register_source(root, {"channel_id": "lab-news", "url": "https://example.test/new-feed"},
                    expected_revision=revision)
    with pytest.raises(ResearchError) as caught:
        apply_observation(root, channel, ok(item()), "2026-01-03T00:00:00Z")
    assert caught.value.exit_code == 5
    assert state.read_bytes() == before
    assert "etag" not in read_updates(root)["channels"][0]
    assert read_updates(root)["channels"][0]["configuration_changed"] is True


def test_changed_channel_cannot_accept_304_or_reuse_baseline(tmp_path):
    root = tmp_path / "home"
    channel = source()
    revision = register_source(root, channel)["revision"]
    apply_observation(root, channel, ok(item(), etag='"old"'), "2026-01-01T00:00:00Z")
    register_source(root, {"channel_id": "lab-news", "name": "Renamed"},
                    expected_revision=revision)
    current = read_sources(root)["channels"][0]
    failed = apply_observation(root, current, {"status": "not_modified", "items": []},
                               "2026-01-02T00:00:00Z")
    assert failed["status"] == "failed"
    assert apply_observation(root, current, ok(item()), "2026-01-03T00:00:00Z")["events"] == []


def test_channel_failures_do_not_corrupt_other_channels(tmp_path):
    root = tmp_path / "home"
    a, b = source("a"), source("b", url="https://example.test/other-feed")
    register_source(root, a)
    register_source(root, b)
    apply_observation(root, a, ok(item()), "2026-01-01T00:00:00Z", initial_mode="report")
    apply_observation(root, b, {"status": "failed", "items": []}, "2026-01-01T00:00:00Z")
    result = read_updates(root)
    assert len(result["events"]) == 1
    assert result["events"][0]["channel_id"] == "a"
    assert {row["channel_id"]: row["status"] for row in result["channels"]} == {
        "a": "observed", "b": "failed"}


@pytest.mark.parametrize("observation", [
    {"status": "ok", "items": [item(), item()]},
    {"status": "ok", "items": [item(content_digest="not-a-hash")]},
    {"status": "ok", "items": [item(body="DO-NOT-STORE")]},
    {"status": "ok", "items": [item(url="https://user:secret@example.test/a")]},
    {"status": "ok", "items": [], "body": "DO-NOT-STORE"},
    {"status": "not_modified", "items": [item()]},
    {"status": "truncated", "items": []},
])
def test_invalid_observations_are_rejected_before_state_initialization(tmp_path, observation):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    with pytest.raises(ResearchError):
        apply_observation(root, channel, observation, "2026-01-01T00:00:00Z")
    assert not (root / "research").exists()


def test_symlink_state_directory_and_private_file_refusals(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (root / "research").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ResearchError) as caught:
        apply_observation(root, channel, ok(), "2026-01-01T00:00:00Z")
    assert caught.value.exit_code == 7
    assert list(outside.iterdir()) == []


def test_tracking_state_rejects_injected_unknown_fields_without_rewriting(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    apply_observation(root, channel, ok(), "2026-01-01T00:00:00Z")
    path = root / "research" / "tracking.json"
    value = json.loads(path.read_text())
    value["body"] = "DO-NOT-STORE"
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    result = read_updates(root)
    assert result["status"] == "invalid"
    assert "DO-NOT-STORE" not in str(result)
    with pytest.raises(ResearchError):
        apply_observation(root, channel, ok(), "2026-01-02T00:00:00Z")
    assert path.read_bytes() == before


def test_disabled_and_unregistered_channels_cannot_apply_or_initialize(tmp_path):
    root = tmp_path / "home"
    channel = source(enabled=False)
    register_source(root, channel)
    for submitted in [channel, source("missing")]:
        with pytest.raises(ResearchError) as caught:
            apply_observation(root, submitted, ok(), "2026-01-01T00:00:00Z")
        assert caught.value.exit_code == 5
    assert not (root / "research").exists()


def test_nonblocking_check_lock_rejects_overlap_and_releases(tmp_path):
    from scholar_workflow.research import check_lock

    root = tmp_path / "home"
    with check_lock(root):
        with pytest.raises(ResearchError) as caught, check_lock(root):
            raise AssertionError("Overlapping check lock was acquired")
        assert caught.value.exit_code == 5
    with check_lock(root):
        assert stat.S_IMODE((root / ".research-check.lock").stat().st_mode) == 0o600


def test_failure_recovery_preserves_known_items_and_does_not_reemit_old_events(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    apply_observation(root, channel, ok(item()), "2026-01-01T00:00:00Z")
    apply_observation(root, channel, {"status": "failed"}, "2026-01-02T00:00:00Z")
    recovered = apply_observation(root, channel, ok(item(), item("entry-2")),
                                 "2026-01-03T00:00:00Z")
    assert [event["item_id"] for event in recovered["events"]] == ["entry-2"]
    assert "diagnostic" not in read_updates(root)["channels"][0]


def test_item_disappearance_is_not_a_deletion_or_new_when_it_returns(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    apply_observation(root, channel, ok(item()), "2026-01-01T00:00:00Z")
    apply_observation(root, channel, ok(), "2026-01-02T00:00:00Z")
    assert read_updates(root)["channels"][0]["observed_item_count"] == 1
    result = apply_observation(root, channel, ok(item()), "2026-01-03T00:00:00Z")
    assert result["events"] == []


def test_http_validators_are_cleared_by_complete_response_without_them(tmp_path):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    apply_observation(root, channel, ok(item(), etag='"one"', last_modified="old"),
                      "2026-01-01T00:00:00Z")
    assert read_updates(root)["channels"][0]["etag"] == '"one"'
    apply_observation(root, channel, ok(item()), "2026-01-02T00:00:00Z")
    assert "etag" not in read_updates(root)["channels"][0]
    assert "last_modified" not in read_updates(root)["channels"][0]


@pytest.mark.parametrize("observation", [
    {"status": []}, {"status": {}}, {"status": "ok", "items": None},
    {"status": "ok", "items": [{"item_id": "a"}]},
])
def test_malformed_observation_types_use_public_sanitized_errors(tmp_path, observation):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    with pytest.raises(ResearchError):
        apply_observation(root, channel, observation, "2026-01-01T00:00:00Z")
    assert not (root / "research").exists()


def test_configuration_edit_during_temp_write_refuses_stale_observation(tmp_path, monkeypatch):
    from scholar_workflow.research import store

    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    apply_observation(root, channel, ok(item()), "2026-01-01T00:00:00Z")
    state = root / "research" / "tracking.json"
    before = state.read_bytes()
    original_read = store.read_bytes
    edited = False

    def editing_read(descriptor, name, limit):
        nonlocal edited
        if name == store.STATE_FILE and not edited:
            edited = True
            path = root / "research-sources.yml"
            path.write_bytes(b"schema_version: 1\nchannels: []\n")
        return original_read(descriptor, name, limit)

    # tracking.py already imported read_bytes; this patches only the final write CAS.
    monkeypatch.setattr(store, "read_bytes", editing_read)
    with pytest.raises(ResearchError) as caught:
        apply_observation(root, channel, ok(item("entry-2")), "2026-01-02T00:00:00Z")
    assert caught.value.exit_code == 5
    assert state.read_bytes() == before
    assert not list((root / "research").glob(".research-*.tmp"))


@pytest.mark.parametrize("code", [
    "network_error", "http_error", "limit_exceeded", "incomplete_pagination", "unsafe_url",
    "invalid_response", "unsafe_xml", "unsupported_content", "invalid_channel",
])
def test_failed_observation_retains_safe_actionable_code_not_external_message(tmp_path, code):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    result = apply_observation(root, channel, {
        "status": "failed", "items": [],
        "diagnostic": {"code": code, "message": "token=DO-NOT-ECHO"},
    }, "2026-01-01T00:00:00Z")
    assert result["diagnostics"][0]["code"] == code
    assert read_updates(root)["channels"][0]["diagnostic"]["code"] == code
    assert "DO-NOT-ECHO" not in (root / "research" / "tracking.json").read_text()


def test_event_preserves_publisher_and_channel_snapshot_after_reconfiguration(tmp_path):
    root = tmp_path / "home"
    channel = source()
    registered = register_source(root, channel)
    first = apply_observation(root, channel, ok(item()), "2026-01-01T00:00:00Z", initial_mode="report")
    expected = {key: channel[key] for key in ("name", "publisher", "url")}
    assert first["events"][0]["source"] == expected
    register_source(root, {"channel_id": "lab-news", "name": "Another channel",
                           "publisher": "Another publisher"}, expected_revision=registered["revision"])
    assert read_updates(root)["events"][0]["source"] == expected


@pytest.mark.parametrize("date_field", ["published_at", "updated_at"])
def test_publisher_date_change_refreshes_metadata_without_content_event(tmp_path, date_field):
    root = tmp_path / "home"
    channel = source()
    register_source(root, channel)
    initial = item(**{date_field: "2026-01-01T00:00:00Z"})
    corrected = item(**{date_field: "2026-01-01T12:00:00Z"})
    apply_observation(root, channel, ok(initial), "2026-01-02T00:00:00Z")
    result = apply_observation(root, channel, ok(corrected), "2026-01-03T00:00:00Z")
    assert result["events"] == []
    checkpoint = json.loads((root / "research" / "tracking.json").read_text())[
        "channels"][channel["channel_id"]]["items"][initial["item_id"]]
    assert checkpoint == {"item": corrected, "sequence": 1}
    assert read_updates(root)["events"] == []
    changed = item(text="actual content change", **{date_field: corrected[date_field]})
    update = apply_observation(root, channel, ok(changed), "2026-01-04T00:00:00Z")
    assert len(update["events"]) == 1
    assert update["events"][0]["kind"] == "updated"
    assert update["events"][0]["sequence"] == 2
