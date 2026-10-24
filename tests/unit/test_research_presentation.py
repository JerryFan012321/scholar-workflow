"""Readable projection expectations independent of network and machine storage."""
from scholar_workflow.research.presentation import sources_markdown, updates_markdown


def test_invalid_sources_are_not_claimed_empty():
    output = sources_markdown({"status": "invalid", "channels": [], "diagnostics": []})
    assert "不能判断" in output
    assert "尚无已登记渠道" not in output


def test_historical_source_and_actionable_failure_are_kept_together():
    current = {"channel_id": "lab", "name": "New label", "publisher": "New publisher",
               "url": "https://example.org/feed", "kind": "rss", "enabled": True,
               "status": "failed", "last_success_at": "2026-10-24T12:00:00Z",
               "diagnostic": {"code": "incomplete_pagination", "message": "Unused internal text"}}
    event = {"channel_id": "lab", "observed_at": "2026-10-24T12:00:00Z",
             "kind": "new", "disposition": "selected",
             "source": {"name": "Old label", "publisher": "Original publisher",
                        "url": "https://example.org/old-feed"},
             "item": {"title": "Research result", "url": "https://example.org/result"},
             "event_id": "event-hidden", "config_revision": "sha256:hidden"}
    output = updates_markdown({"status": "available", "channels": [current], "events": [event]})
    assert "Original publisher / Old label" in output
    assert "New publisher / New label" not in output
    assert "分页未完整读完" in output and "2026-10-24T12:00:00Z" in output
    assert "已选待归档" in output
    assert "event-hidden" not in output and "sha256:hidden" not in output


def test_source_titles_cannot_inject_markdown_or_active_html():
    payload = {"status": "available", "channels": [{"channel_id": "lab", "name": "[click] | <img>",
               "publisher": "Example", "url": "https://example.org/feed", "enabled": True,
               "kind": "rss", "topics": []}]}
    output = sources_markdown(payload)
    assert "\\[click\\]" in output and "\\|" in output and "&lt;img&gt;" in output
    assert "<img>" not in output


def test_registered_but_unchecked_source_is_not_labelled_unregistered():
    output = updates_markdown({"status": "available", "events": [], "channels": [{
        "channel_id": "lab", "name": "研究动态", "publisher": "示例实验室",
        "url": "https://example.org/feed", "enabled": True, "status": "uninitialized",
    }]})
    assert "尚未检查" in output
    assert "尚未登记" not in output


def test_proxy_configuration_failure_is_not_a_generic_empty_result(tmp_path):
    from scholar_workflow.research import apply_observation, read_updates, register_source

    source = {"channel_id": "lab", "name": "研究动态", "publisher": "示例实验室",
              "publisher_kind": "lab", "kind": "rss", "url": "https://example.org/feed",
              "enabled": True, "topics": []}
    register_source(tmp_path, source)
    apply_observation(tmp_path, source, {"status": "failed", "diagnostic": {
        "code": "unsupported_proxy", "message": "DO NOT KEEP RAW CREDENTIALS"}},
        "2026-10-24T12:00:00Z")
    current = read_updates(tmp_path)
    assert current["channels"][0]["diagnostic"]["code"] == "unsupported_proxy"
    assert "DO NOT KEEP" not in str(current)
    assert "代理类型不受支持" in updates_markdown(current)
