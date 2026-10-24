"""One synthetic source through real CLI, parser, state and readable projection."""
from __future__ import annotations

import json

import httpx
from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.research.runner import run_check


def feed(*articles):
    return ("<rss version='2.0'><channel>" + "".join(
        f"<item><guid>{identifier}</guid><title>{title}</title>"
        f"<link>https://example.org/{identifier}</link><description>{body}</description></item>"
        for identifier, title, body in articles) + "</channel></rss>").encode()


def test_public_registration_real_adapter_incremental_state_and_selection(tmp_path):
    state, spec = tmp_path / "isolated", tmp_path / "channel.json"
    spec.write_text(json.dumps({
        "channel_id": "synthetic-lab", "name": "合成研究动态", "publisher": "示例实验室",
        "publisher_kind": "lab", "kind": "rss", "url": "https://example.org/feed.xml",
        "enabled": True, "topics": ["world models"],
    }), encoding="utf-8")
    env = {"SCHOLAR_WORKFLOW_HOME": str(state)}
    cli = CliRunner()
    registered = cli.invoke(main, ["research", "sources", "register", "--spec", str(spec),
                                   "--format", "json"], env=env)
    assert registered.exit_code == 0, registered.output
    initial = feed(("one", "合成样本：原始结果", "Initial source text."))
    changed = feed(("one", "合成样本：原始结果", "Revised source text."),
                   ("two", "合成样本：新增模型介绍", "A new source document."))
    responses = iter([
        httpx.Response(200, content=initial, headers={"etag": '"v1"'}),
        httpx.Response(200, content=changed, headers={"etag": '"v2"'}),
        httpx.ReadTimeout("Private transport details must not escape"),
        httpx.Response(304, headers={"etag": '"v2"'}),
    ])

    def transport(_request):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        baseline = run_check(state, client=client, checked_at="2026-10-24T12:00:00Z")
        updated = run_check(state, client=client, checked_at="2026-10-24T13:00:00Z")
        failed = run_check(state, client=client, checked_at="2026-10-24T14:00:00Z")
        recovered = run_check(state, client=client, checked_at="2026-10-24T15:00:00Z")
    assert baseline["events"] == []
    assert {event["kind"] for event in updated["events"]} == {"new", "updated"}
    assert failed["status"] == "partial"
    assert failed["channels"][0]["last_success_at"] == "2026-10-24T13:00:00Z"
    assert "Private transport" not in json.dumps(failed)
    assert recovered["events"] == [] and recovered["channels"][0]["status"] == "not_modified"
    selected = updated["events"][0]["event_id"]
    marked = cli.invoke(main, ["research", "mark", selected, "--disposition", "selected"], env=env)
    assert marked.exit_code == 0, marked.output
    retained = cli.invoke(main, ["research", "updates", "--format", "json"], env=env)
    assert retained.exit_code == 0, retained.output
    assert len(json.loads(retained.output)["events"]) == 2
    visible = cli.invoke(main, ["research", "updates", "--language", "zh"], env=env)
    assert "示例实验室" in visible.output and "合成样本：新增模型介绍" in visible.output
    assert "已选待归档" in visible.output and "sha256:" not in visible.output
    assert not (state / "hub").exists()
    assert {path.name for path in tmp_path.iterdir()} == {"isolated", "channel.json"}
