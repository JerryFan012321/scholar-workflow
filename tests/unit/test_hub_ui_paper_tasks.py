"""Bounded, synthetic browser-state checks for paper files and Codex selection.

These fixtures never connect to Zotero, Obsidian, cmux, or a Codex executable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from importlib import resources

import pytest


NODE_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag = "div") {
    this.tagName = tag; this.children = []; this.listeners = {}; this.value = "";
    this.disabled = false; this.hidden = false; this.open = false; this.dataset = {};
    this._text = ""; this.classList = { toggle() {}, add() {}, remove() {} };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent || "").join(""); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ""; this.children = children; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute() {}
  hasChildNodes() { return this.children.length > 0; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  scrollIntoView() {}
}
const elements = new Map();
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); },
  createElement(tag) { return new Element(tag); },
  createDocumentFragment() { return new Element("fragment"); },
  createTextNode(text) { const result = new Element("text"); result.textContent = text; return result; },
  querySelectorAll() { return []; }, addEventListener() {},
};
const context = vm.createContext({ document, window: {
  location: { search: "" }, localStorage: { getItem() { return null; }, setItem() {} },
  setTimeout() { return 1; }, clearTimeout() {},
}, URL, URLSearchParams, TextEncoder, console, assert, Element,
fetch: async () => { throw new Error("Unexpected network request"); },
});
vm.runInContext(input.source.replace(/boot\(\);\s*$/, ""), context);
Promise.resolve(vm.runInContext(`(async () => { ${input.scenario} })()`, context))
  .catch((error) => { console.error(error); process.exitCode = 1; });
"""


def run_ui_scenario(scenario: str) -> None:
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node.js is required for isolated Hub browser-state fixtures")
    source = resources.files("scholar_workflow.hub.static").joinpath("hub.js").read_text()
    result = subprocess.run(
        [executable, "-e", NODE_HARNESS],
        input=json.dumps({"source": source, "scenario": scenario}),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_context_selection_never_uses_first_unrelated_target() -> None:
    run_ui_scenario("""
      state.tasks.loading = false;
      state.tasks.actions = [{ action_id: 'review', title: 'Review', available: true }];
      state.tasks.targets = [
        { target_id: 'unrelated', kind: 'vault', registered_root_id: 'other' },
        { target_id: 'matched', kind: 'vault', registered_root_id: 'source-a' },
      ];
      state.tasks.modelProfiles = [{ profile_id: 'm', title: 'Model', supported_reasoning_efforts: ['medium', 'high'], default_reasoning_effort: 'medium' }];
      state.tasks.defaultProfileId = 'm';
      selectTaskContext({ kind: 'paper', title: 'Synthetic paper', fields: [{ source_id: 'source-a', field_id: 'field-a' }] });
      assert.equal(state.tasks.selectedActionId, 'review');
      assert.equal(state.tasks.selectedTargetId, 'matched');
      selectTaskContext({ kind: 'paper', title: 'Ambiguous paper', fields: [{ source_id: 'source-a' }, { source_id: 'other' }] });
      assert.equal(state.tasks.selectedTargetId, null);
      state.tasks.actions.push({ action_id: 'analyze', title: 'Analyze', available: true });
      state.tasks.selectedActionId = null;
      renderTaskPanel();
      assert.equal(state.tasks.selectedActionId, null);
    """)


def test_task_payload_uses_profiles_and_typed_context_only() -> None:
    run_ui_scenario("""
      state.tasks.loading = false;
      state.tasks.actions = [{ action_id: 'review', title: 'Review', available: true }];
      state.tasks.targets = [{ target_id: 'test', kind: 'folder' }];
      state.tasks.selectedActionId = 'review'; state.tasks.selectedTargetId = 'test';
      state.tasks.modelProfiles = [{ profile_id: 'model-safe', title: 'Model', supported_reasoning_efforts: ['high'] }];
      state.tasks.defaultProfileId = 'model-safe'; state.tasks.selectedEffort = 'high';
      state.tasks.context = { ref: { provider_id: 'zotero', entity_type: 'paper', entity_id: 'ABC12345' } };
      state.destinations.selectedId = 'destination'; state.csrfToken = 'synthetic-token';
      byId('task-brief').value = 'Describe this synthetic paper';
      let request;
      fetch = async (_url, options) => { request = JSON.parse(options.body); return { ok: true, json: async () => ({ run_id: 'run', state: 'succeeded' }) }; };
      await submitTask({ preventDefault() {} });
      assert.equal(request.model_profile_id, 'model-safe');
      assert.equal(request.reasoning_effort, 'high');
      assert.equal(request.entity_refs[0].entity_id, 'ABC12345');
      for (const forbidden of ['model', 'cwd', 'sandbox', 'command', 'environment']) assert.equal(Object.hasOwn(request, forbidden), false);
    """)


def test_related_documents_are_lazy_cached_and_missing_items_remain_visible() -> None:
    run_ui_scenario("""
      let reads = 0;
      fetch = async () => { reads += 1; return { ok: true, json: async () => ({ documents: [{ title: 'Missing analysis', role: 'paper-analysis', format: 'markdown', available: false, reason: 'File missing', actions: [] }], field_contexts: [] }) }; };
      const resource = { zotero_item_key: 'ABC12345', title: 'Fixture', authors: [], actions: [] };
      resourceCard(resource);
      assert.equal(reads, 0);
      const [first, second] = await Promise.all([loadPaperRelated(resource), loadPaperRelated(resource)]);
      assert.equal(reads, 1); assert.equal(first, second);
      const container = new Element(); renderPaperRelated(container, first);
      assert.match(container.textContent, /Missing analysis/); assert.match(container.textContent, /File missing/);
    """)


def test_source_links_are_supported_without_exposing_machine_claims() -> None:
    run_ui_scenario("""
      assert.ok(safeReadableLink('obsidian://zotflow?type=open-attachment&key=ABC12345&page=4'));
      assert.ok(safeReadableLink('zotero://open-pdf/library/items/ABC12345?page=4'));
      assert.equal(safeReadableLink('javascript:alert(1)'), null);
      assert.equal(safeReadableLink('file:///private/example.md'), null);
      assert.equal(readableActionLabel({ kind: 'obsidian.related-file', label: 'Open in Obsidian' }), '在 Obsidian 打开');
      assert.match(readableActionLabel({ kind: 'resource.cmux', label: 'Read original PDF in cmux (no Zotero annotations)' }), /不含批注/);
      const container = new Element();
      renderReadable(container, { format: 'markdown' }, '<!-- sw-analysis-claim id="fixture" -->\\nReadable claim.');
      assert.equal(container.textContent, 'Readable claim.');
      renderReadable(container, { format: 'markdown' }, 'Readable claim. ^claim-fixture');
      assert.equal(container.textContent, 'Readable claim.');
      const paragraph = new Element();
      appendInlineMarkdown(paragraph, 'Readable claim. ^claim-fixture');
      assert.equal(paragraph.id, 'claim-fixture');
      renderReadable(container, { format: 'markdown' }, '`literal ^point-fixture`');
      assert.equal(container.textContent, 'literal ^point-fixture');
      assert.equal(readableActionLabel({ kind: 'zotero.item', label: 'Open in Zotero' }), '在 Zotero 选择条目');
      assert.equal(readableActionLabel({ kind: 'zotero.pdf', label: 'Read in Zotero' }), '在 Zotero 打开');
    """)


def test_server_owned_model_preference_overrides_browser_fallback_and_saves_choice() -> None:
    run_ui_scenario("""
      state.tasks.selectedModelId = 'stale-browser-profile';
      state.tasks.selectedEffort = 'minimal';
      state.csrfToken = 'synthetic-token';
      const requests = [];
      fetch = async (url, options) => {
        requests.push({ url, options });
        if (url === '/api/v3/task-actions') return { ok: true, json: async () => ({ actions: [{ action_id: 'review', available: true }] }) };
        if (url === '/api/v3/execution-targets') return { ok: true, json: async () => ({ targets: [] }) };
        if (url === '/api/v3/task-options') return { ok: true, json: async () => ({ model_profiles: [{ profile_id: 'approved', title: 'Model', supported_reasoning_efforts: ['medium', 'high'] }], default_profile_id: 'approved', selected_model_profile_id: 'approved', selected_reasoning_effort: 'high' }) };
        if (url === '/api/v3/task-options/preferences') return { ok: true };
        throw new Error('Unexpected request ' + url);
      };
      await loadTaskSurface();
      assert.equal(state.tasks.selectedModelId, 'approved');
      assert.equal(state.tasks.selectedEffort, 'high');
      assert.equal(requests.some((entry) => entry.options?.method === 'POST'), false);
      state.tasks.selectedEffort = 'medium';
      await persistTaskChoice();
      const saved = requests.find((entry) => entry.url === '/api/v3/task-options/preferences');
      assert.equal(saved.options.method, 'POST');
      assert.equal(saved.options.headers['X-Scholar-Hub-Token'], 'synthetic-token');
      const payload = JSON.parse(saved.options.body);
      assert.equal(payload.model_profile_id, 'approved');
      assert.equal(payload.reasoning_effort, 'medium');
      assert.equal(Object.keys(payload).length, 2);
    """)


def test_setup_probe_requires_session_token_and_shows_target_permission() -> None:
    run_ui_scenario("""
      state.csrfToken = 'synthetic-token';
      let probeOptions;
      fetch = async (url, options) => {
        assert.equal(url, '/api/v3/codex/setup');
        probeOptions = options;
        return { ok: true, json: async () => ({ candidates: [{ candidate_id: 'candidate', title: 'Codex', available: true }], model_profiles: [], targets: [{ target_id: 'suggested', title: 'Test Vault', kind: 'vault', available: true, permission_note: 'Confirming authorizes Codex in this selected Field or Vault folder' }] }) };
      };
      await loadCodexSetup();
      assert.equal(probeOptions.credentials, 'same-origin');
      assert.equal(probeOptions.headers['X-Scholar-Hub-Token'], 'synthetic-token');
      assert.equal(probeOptions.method, undefined);
      renderCodexSetup();
      assert.match(byId('codex-setup-target-list').textContent, /Test Vault/);
      assert.match(byId('codex-setup-target-list').textContent, /确认后/);
      assert.equal(byId('codex-setup-save').disabled, true);
    """)
