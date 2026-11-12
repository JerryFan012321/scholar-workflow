"""Execute the shipped browser script against an isolated synthetic DOM.

These complete-content scenarios explicitly open the details drawer. Expected
behavior is declared by fixtures before UI changes: absent observations
stay unknown, refreshes preserve old values and human state, and sourced agent
summaries remain visibly distinct from original abstracts.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "src/scholar_workflow/research/recommendations/static/app.js"
NODE = shutil.which("node")
RUNNER = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) {
    this.tagName = tag.toLowerCase(); this.className = ""; this.children = [];
    this.attributes = {}; this.dataset = {}; this.listeners = {}; this._text = "";
    this.disabled = false; this.checked = false; this.hidden = false; this.value = "";
    this.classList = {toggle: (name, enabled) => {
      const names = new Set(this.className.split(" ").filter(Boolean));
      if (enabled) names.add(name); else names.delete(name);
      this.className = [...names].join(" ");
    }};
  }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(""); }
  set textContent(text) { this._text = String(text); this.children = []; }
  get childElementCount() { return this.children.length; }
  get options() { return this.children; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ""; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  querySelectorAll(selector) {
    const tags = selector.split(",").map(value => value.trim());
    return collect(this).filter(node => node !== this && tags.includes(node.tagName));
  }
  contains(node) { return collect(this).includes(node); }
  focus() {}
  async fire(name) { await Promise.all((this.listeners[name] || []).map(callback => callback({target: this}))); }
}
const ids = new Map();
const get = id => {
  if (!ids.has(id)) ids.set(id, new Element(["tag", "producer_id"].includes(id) ? "select" : "div"));
  return ids.get(id);
};
const tabs = ["", "unread", "saved", "selected", "ignored"].map(decision => {
  const node = new Element("button"); node.dataset.decision = decision; return node;
});
const storage = new Map();
const requests = [];
let current = input.candidate;
const context = {
  URL, URLSearchParams, Date, setTimeout, clearTimeout,
  window: {location: {hash: "#token=" + "a".repeat(32), pathname: "/", search: ""},
    history: {replaceState() {}}},
  document: {getElementById: get, createElement: tag => new Element(tag),
    addEventListener() {}, querySelectorAll: () => tabs, body: new Element("body")},
  sessionStorage: {getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
  fetch: async (path, options = {}) => {
    if (path === "/api/session") return {ok: true, json: async () => ({token: "a".repeat(32)})};
    if (options.method === "POST") {
      requests.push({path, body: JSON.parse(options.body)});
      if (input.refresh_error) return {ok: false, status: 409, json: async () => ({exit_code: 5})};
      current = input.after_refresh || current;
      return {ok: true, status: 200, json: async () => current};
    }
    if (path === "/health") return {ok: true, json: async () => ({profile: "test"})};
    const selected = current.decision === "selected" ? 1 : 0;
    const result = {items: [current], total: path.includes("decision=selected") ? selected : 1,
      facets: {tags: [], producers: [], kinds: [current.resource.kind]}};
    return {ok: true, json: async () => result};
  },
};
function find(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children) { const result = find(child, predicate); if (result) return result; }
}
function collect(node) { return [node, ...node.children.flatMap(collect)]; }
function snapshot(node) {
  return {tag: node.tagName, class: node.className, text: node.textContent,
    attributes: node.attributes, href: node.href || null, title: node.title || null,
    datetime: node.dateTime || null, open: node.open === true, disabled: node.disabled, checked: node.checked,
    children: node.children.map(snapshot)};
}
const settle = async () => { for (let n = 0; n < 5; n++) await new Promise(setImmediate); };
(async () => {
  vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);
  await settle();
  // Complete-content checks explicitly open the recommendation details.
  const detail = find(get("feed"), node => node.className.split(" ").includes("entry-details"));
  if (!detail) throw new Error("Expected details entry");
  await detail.fire("click");
  await settle();
  if (input.action) {
    const className = input.action === "review" ? "review" : "metric-refresh";
    let control = find(get("detail-content"), node => node.className.split(" ").includes(className));
    if (!control) throw new Error("Expected action control: " + className);
    if (input.action === "review") control = control.children.find(node => node.tagName === "input");
    if (control.disabled) throw new Error("Expected enabled action control");
    await control.fire(input.action === "review" ? "change" : "click");
    await settle();
  }
  process.stdout.write(JSON.stringify({feed: snapshot(get("detail-content")), notice: get("notice").textContent,
    selected_count: get("selected-count").textContent, requests}));
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""


def render(candidate, **scenario):
    if not NODE:
        pytest.skip("The system Node runtime is required for synthetic DOM execution.")
    completed = subprocess.run(
        [NODE, "-e", RUNNER, str(APP)],
        input=json.dumps({"candidate": candidate, **scenario}), text=True,
        capture_output=True, check=True,
    )
    return json.loads(completed.stdout)


def nodes(tree, class_name):
    found = [tree] if class_name in tree["class"].split() else []
    for child in tree["children"]:
        found.extend(nodes(child, class_name))
    return found


def candidate():
    return {
        "candidate_id": "candidate-" + "a" * 64, "revision": 4,
        "resource": {"kind": "paper", "title": "Synthetic paper",
                     "url": "https://arxiv.org/abs/2601.12345", "authors": ["A. Example"],
                     "abstract_original": "A complete original abstract.", "abstract_zh": "完整摘要译文。"},
        "tags": ["world-models"], "metrics": [], "metric_targets": [],
        "metric_refresh": {"checks": []}, "decision": "selected", "abstract_reviewed": True,
        "producers": [], "recommendations": [],
    }


def target(platform="github", metric="stars", url="https://github.com/example/model"):
    return {"platform": platform, "metric": metric, "url": url}


def observation(value, **fields):
    return {**target(), "value": value, "observed_at": "2026-11-08T00:00:00Z", **fields}


def test_legacy_card_keeps_unknown_metrics_after_abstract_and_disabled_refresh():
    item = candidate()
    item.pop("metrics")
    item.pop("metric_targets")
    item.pop("metric_refresh")
    result = render(item)
    card = nodes(result["feed"], "card")[0]
    metrics = nodes(card, "metrics")[0]
    assert "未采集" in metrics["text"]
    assert "尚无已核验 GitHub/HF 链接" in metrics["text"]
    assert not nodes(metrics, "metric-value")
    assert nodes(metrics, "metric-refresh")[0]["disabled"]
    assert card["children"].index(nodes(card, "summary")[0]) < card["children"].index(metrics)


def test_target_refresh_posts_only_identity_and_revision_and_preserves_human_state():
    item = candidate()
    item["metric_targets"] = [target()]
    before = render(item)
    metrics = nodes(before["feed"], "metrics")[0]
    assert "未采集" in metrics["text"]
    assert not nodes(metrics, "metric-value")
    assert not nodes(metrics, "metric-refresh")[0]["disabled"]
    refreshed = copy.deepcopy(item)
    refreshed["revision"] += 1
    refreshed["metrics"] = [observation(0)]
    result = render(item, action="refresh", after_refresh=refreshed)
    assert result["requests"] == [{"path": "/api/metrics", "body": {
        "candidate_id": item["candidate_id"], "expected_revision": 4}}]
    assert [node["text"] for node in nodes(result["feed"], "metric-value")] == ["0"]
    assert nodes(result["feed"], "select-input")[0]["checked"]
    assert nodes(result["feed"], "review")[0]["children"][0]["checked"]
    assert result["selected_count"] == "1"


def test_latest_values_standard_labels_links_times_and_failed_checks():
    item = candidate()
    hf = target("huggingface", "likes", "https://huggingface.co/example/model")
    item["metric_targets"] = [target(), hf]
    item["metrics"] = [observation(123), observation(7, observed_at="2026-11-07T00:00:00Z"),
                       {**hf, "value": 9, "observed_at": "2026-11-08T00:00:00Z"}]
    item["metric_refresh"]["checks"] = [
        {**target(), "status": "unavailable", "checked_at": "2026-11-08T01:00:00Z"},
        {**hf, "status": "rate_limited", "checked_at": "2026-11-08T01:00:00Z"},
    ]
    metrics = nodes(render(item)["feed"], "metrics")[0]
    rows = nodes(metrics, "metric")
    assert len(rows) == 2
    assert [node["text"] for node in nodes(metrics, "metric-value")] == ["123", "9"]
    assert rows[0]["children"][0]["text"] == "GitHub stars"
    assert rows[0]["children"][0]["href"] == target()["url"]
    assert rows[1]["children"][0]["text"] == "Hugging Face 点赞（likes）"
    assert "保留上次数据" in rows[0]["text"]
    assert "限流" in rows[1]["text"]
    assert any(child["datetime"] == "2026-11-08T00:00:00Z" for child in rows[0]["children"])


def test_revision_conflict_keeps_observation_visible_and_does_not_change_selection():
    item = candidate()
    item["metric_targets"] = [target()]
    item["metrics"] = [observation(42)]
    result = render(item, action="refresh", refresh_error=True)
    assert [node["text"] for node in nodes(result["feed"], "metric-value")] == ["42"]
    assert "刚刚发生变化" in result["notice"]
    assert nodes(result["feed"], "select-input")[0]["checked"]
    assert [request["path"] for request in result["requests"]] == ["/api/metrics"]


def with_summary(kind="paper"):
    item = candidate()
    item["resource"].pop("abstract_original")
    item["resource"].pop("abstract_zh")
    item["resource"].update(kind=kind, summary_zh="基于实际正文整理的资料总结。",
                            summary_sources=["https://example.org/article"])
    item.update(decision="unread", abstract_reviewed=False)
    return item


@pytest.mark.parametrize("kind", ["paper", "project", "blog"])
@pytest.mark.parametrize("current_contract", [False, True])
def test_sourced_agent_summary_is_labeled_linked_and_reviewable(kind, current_contract):
    item = with_summary(kind)
    if current_contract:
        item.update(reading_kind="summary", review_required=True, review_available=True)
    item["resource"]["links"] = [{"kind": "blog", "label": "相关 Blog", "url": "https://example.org/blog"}]
    result = render(item, action="review")
    card = nodes(result["feed"], "card")[0]
    assert nodes(card, "summary-label")[0]["text"] == ("项目简介" if kind == "project" else "内容简介")
    sources = nodes(card, "summary-sources")[0]
    assert "来源" in sources["text"]
    assert sources["children"][1]["href"] == "https://example.org/article"
    assert "我已阅读这份资料总结" in nodes(card, "review")[0]["text"]
    assert not nodes(card, "review")[0]["children"][0]["disabled"]
    assert nodes(card, "select-input")[0]["disabled"]
    assert any(link["href"] == "https://example.org/blog" for link in nodes(card, "links")[0]["children"])
    assert result["requests"] == [{"path": "/api/reviews", "body": {
        "candidate_id": item["candidate_id"], "expected_revision": item["revision"]}}]


def test_original_abstract_translation_takes_priority_over_agent_summary():
    item = candidate()
    item["resource"].update(summary_zh="An unused summary.", summary_sources=["https://example.org/article"])
    card = nodes(render(item)["feed"], "card")[0]
    assert nodes(card, "summary-label")[0]["text"] == "摘要"
    assert nodes(card, "summary")[0]["text"] == "完整摘要译文。"
    assert not nodes(card, "summary-sources")
    assert "这份摘要译文已确认审阅" in nodes(card, "review")[0]["text"]


def test_reviewed_summary_label_and_selection_survive_metric_refresh():
    item = with_summary()
    item.update(reading_kind="summary", review_required=True, review_available=True,
                abstract_reviewed=True, decision="selected")
    item["metric_targets"] = [target()]
    refreshed = copy.deepcopy(item)
    refreshed["metrics"] = [observation(10)]
    refreshed["revision"] += 1
    result = render(item, action="refresh", after_refresh=refreshed)
    review = nodes(result["feed"], "review")[0]
    assert "这份资料总结已确认审阅" in review["text"]
    assert review["children"][0]["checked"]
    assert nodes(result["feed"], "select-input")[0]["checked"]


def test_summary_without_sources_stays_unavailable_and_cannot_be_reviewed():
    item = with_summary()
    item["resource"]["summary_sources"] = []
    card = nodes(render(item)["feed"], "card")[0]
    assert not nodes(card, "summary")
    assert nodes(card, "unavailable")
    assert nodes(card, "review")[0]["children"][0]["disabled"]
    assert nodes(card, "select-input")[0]["disabled"]


def test_existing_original_abstract_requires_translation_without_summary_bypass():
    item = with_summary()
    item["resource"]["abstract_original"] = "A complete original abstract requiring translation."
    card = nodes(render(item)["feed"], "card")[0]
    assert not nodes(card, "summary")
    assert not nodes(card, "summary-sources")
    assert nodes(card, "unavailable")
    assert nodes(card, "review")[0]["children"][0]["disabled"]
    assert nodes(card, "select-input")[0]["disabled"]


@pytest.mark.parametrize("include_summary", [False, True])
def test_nonpaper_description_is_preserved_with_explicit_summary(include_summary):
    item = candidate()
    item["resource"].update(kind="blog", description_original="Original source introduction.")
    item["resource"].pop("abstract_original")
    item["resource"].pop("abstract_zh")
    if include_summary:
        item["resource"].update(summary_zh="Source-backed summary.", summary_sources=["https://example.org/article"])
        item.update(reading_kind="summary", review_required=True, review_available=True)
    item.update(decision="unread", abstract_reviewed=False)
    card = nodes(render(item)["feed"], "card")[0]
    assert nodes(card, "summary")[0]["text"] == ("Source-backed summary." if include_summary else "Original source introduction.")
    assert bool(nodes(card, "summary-sources")) == include_summary
    assert bool(nodes(card, "review")) == include_summary
    if include_summary:
        assert "Original source introduction." in nodes(card, "original")[0]["text"]
    assert nodes(card, "select-input")[0]["disabled"] == include_summary


@pytest.mark.parametrize("kind", ["paper", "project", "blog"])
def test_summary_provenance_is_folded_away_from_main_reading(kind):
    item = with_summary(kind)
    card = nodes(render(item)["feed"], "card")[0]
    provenance = nodes(card, "provenance")[0]
    assert provenance["tag"] == "details" and not provenance["open"]
    assert provenance["children"][0]["text"] == "出处"
    assert "根据来源正文整理" in provenance["text"]
    assert nodes(provenance, "summary-sources")[0]["children"][1]["href"] == "https://example.org/article"
    assert nodes(card, "summary")[0]["text"] == item["resource"]["summary_zh"]
    assert "非原文摘要" not in card["text"]


@pytest.mark.parametrize("translated", [False, True])
def test_project_with_author_abstract_uses_abstract_without_summary_bypass(translated):
    item = candidate()
    item.update(decision="unread", abstract_reviewed=False)
    item["resource"].update(kind="project", summary_zh="Unused body summary.",
                            summary_sources=["https://example.org/project"])
    if not translated:
        item["resource"].pop("abstract_zh")
    card = nodes(render(item)["feed"], "card")[0]
    assert "Unused body summary." not in card["text"]
    assert not nodes(card, "summary-sources")
    assert item["resource"]["abstract_original"] in nodes(card, "provenance")[0]["text"]
    assert not nodes(card, "provenance")[0]["open"]
    if translated:
        assert nodes(card, "summary-label")[0]["text"] == "摘要"
        assert nodes(card, "summary")[0]["text"] == item["resource"]["abstract_zh"]
        assert nodes(card, "review")[0]["children"][0]["disabled"] is False
    else:
        assert not nodes(card, "summary")
        assert nodes(card, "unavailable")
        assert nodes(card, "review")[0]["children"][0]["disabled"]
