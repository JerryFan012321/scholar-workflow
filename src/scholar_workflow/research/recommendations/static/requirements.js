"use strict";

(() => {
  const bridge = window.ScholarRecommendations;
  if (!bridge) return;
  const {api, element} = bridge;
  const widgets = new Map();

  function createWidget(source) {
    const sourceId = source.source_id;
    const nodes = {};
    const $ = id => nodes[id];
    function node(id, tag, className, text) {
      const value = element(tag, className, text);
      nodes[id] = value;
      value.dataset.field = id;
      return value;
    }
    const root = element("section", "source-requirement-editor");
    root.dataset.source = sourceId;
    const toolbar = element("div", "requirement-toolbar");
    const refresh = node("requirements-refresh", "button", "text-button", "刷新要求"); refresh.type = "button";
    const add = node("requirements-new", "button", "secondary", "新建要求"); add.type = "button";
    toolbar.append(refresh, add); root.append(toolbar);
    root.append(node("requirements-list", "div", "requirement-list"));
    const editor = element("section", "requirement-editor");
    editor.append(node("requirement-editor-title", "h3", null, "新建推荐要求"),
      node("requirement-editor-meta", "p", "quiet", "尚未保存"));
    const statusNode = node("requirement-notice", "div", "notice");
    statusNode.setAttribute("role", "status"); statusNode.setAttribute("aria-live", "polite"); statusNode.hidden = true;
    editor.append(statusNode);
    const form = node("requirement-form", "form", "requirement-form");
    const titleLabel = element("label", "field-label", "名称");
    const title = node("requirement-title", "input"); title.type = "text"; title.required = true; title.autocomplete = "off";
    title.placeholder = "为这份要求命名"; titleLabel.append(title);
    const contentLabel = element("label", "field-label", "具体要求");
    const content = node("requirement-content", "textarea"); content.rows = 10; content.required = true;
    content.placeholder = "填写这个推荐源对应的要求。"; contentLabel.append(content);
    const enabledLabel = element("label", "requirement-enabled");
    const enabled = node("requirement-enabled", "input"); enabled.type = "checkbox";
    enabledLabel.append(enabled, element("span", null, "允许任务选用"));
    const identity = element("details", "requirement-identity"); identity.append(element("summary", null, "标识（供任务引用）"));
    const identityLabel = element("label", "field-label", "要求标识");
    const identityInput = node("requirement-id", "input"); identityInput.type = "text"; identityInput.required = true;
    identityInput.autocomplete = "off"; identityInput.spellcheck = false; identityLabel.append(identityInput);
    identity.append(identityLabel, element("p", "quiet", "新建时可自行填写，保存后保持稳定。所属推荐源由当前条目确定。"));
    const actions = element("div", "requirement-form-actions");
    const save = node("requirement-save", "button", "primary", "保存要求"); save.type = "submit";
    const cancel = node("requirement-cancel", "button", "text-button", "取消修改"); cancel.type = "button"; cancel.hidden = true;
    const reload = node("requirement-reload", "button", "secondary", "重新载入已保存版本"); reload.type = "button"; reload.hidden = true;
    actions.append(save, cancel, reload); form.append(titleLabel, contentLabel, enabledLabel, identity, actions);
    editor.append(form, element("p", "quiet requirement-scope", "保存只更新本来源的要求，不表示来源已连接，也不会启动推荐任务。"));
    root.append(editor);
  let revision = 0;
  let initialized = false;
  let saving = false;
  let savedDraft = "";
  let savedItem = null;
  let listSequence = 0;
  let editorSequence = 0;

  function notice(text, failed = false) {
    const node = $("requirement-notice");
    node.textContent = text;
    node.hidden = !text;
    node.classList.toggle("error", failed);
  }

  function safeId() {
    if (typeof window.crypto?.randomUUID === "function") return "req-" + window.crypto.randomUUID();
    if (typeof window.crypto?.getRandomValues === "function") {
      const bytes = new Uint8Array(16); window.crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
      const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
      return `req-${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    return "";
  }

  function draft() {
    return {requirement_id: $("requirement-id").value, title: $("requirement-title").value,
      content: $("requirement-content").value, enabled: $("requirement-enabled").checked};
  }

  function draftKey() {
    const scope = bridge.getDraftScope?.();
    return typeof scope === "string" && scope ? `scholar-recommendations-draft:${scope}:source:${sourceId}` : null;
  }

  function dirty() { return initialized && JSON.stringify(draft()) !== savedDraft; }

  function rememberDraft() {
    const key = draftKey();
    if (!key) return;
    try {
      if (!dirty()) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, JSON.stringify({source_id: sourceId, revision, base_item: savedItem,
        base: JSON.parse(savedDraft), draft: draft()}));
    } catch (_) { /* Storage failures do not alter the current editor or its draft. */ }
  }

  function clearSessionDraft() {
    const key = draftKey();
    if (key) { try { sessionStorage.removeItem(key); } catch (_) { /* Keep editing available. */ } }
  }

  function restoreSessionDraft() {
    const key = draftKey();
    if (!key) return;
    try {
      const stored = JSON.parse(sessionStorage.getItem(key) || "null");
      if (!stored || stored.source_id !== sourceId || !Number.isInteger(stored.revision) || stored.revision < 0
          || !stored.base || !stored.draft || (stored.base_item && stored.base_item.source_id !== sourceId)) return;
      for (const data of [stored.base, stored.draft]) {
        if (!["requirement_id", "title", "content"].every(field => typeof data[field] === "string") || typeof data.enabled !== "boolean") return;
      }
      loadEditor(stored.base_item, {clearDraft: false});
      revision = stored.revision;
      savedDraft = JSON.stringify(stored.base);
      $("requirement-id").value = stored.draft.requirement_id;
      $("requirement-title").value = stored.draft.title;
      $("requirement-content").value = stored.draft.content;
      $("requirement-enabled").checked = stored.draft.enabled;
      setBusy(false);
      notice("已恢复本来源在本次会话中的未保存草稿。");
    } catch (_) { /* An invalid local draft never replaces provider records. */ }
  }

  function canReplaceDraft() {
    if (saving) return false;
    if (!dirty()) return true;
    return typeof window.confirm === "function" && window.confirm("当前输入尚未保存。继续会替换这份草稿，是否继续？");
  }

  function displayTime(value) {
    const node = element("time");
    const date = new Date(value);
    node.title = value || "";
    if (!value || Number.isNaN(date.getTime())) node.textContent = "时间未提供";
    else {
      node.dateTime = value;
      node.textContent = date.toLocaleString("zh-CN", {timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit",
        day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false}) + "（北京时间）";
    }
    return node;
  }

  function editorAttribution(item) {
    const source = item.updated_by || {};
    const label = source.kind === "human" ? "用户" : source.kind === "agent" ? "agent" : "未提供";
    return label + (source.name ? ` · ${source.name}` : "");
  }

  function loadEditor(item = null, {clearDraft = true, preserveBusy = false} = {}) {
    editorSequence++;
    initialized = true;
    revision = item?.revision || 0;
    savedItem = item ? {...item} : null;
    $("requirement-id").value = item?.requirement_id || safeId();
    $("requirement-id").readOnly = Boolean(revision);
    $("requirement-title").value = item?.title || "";
    $("requirement-content").value = item?.content || "";
    $("requirement-enabled").checked = item ? Boolean(item.enabled) : true;
    $("requirement-editor-title").textContent = item ? "编辑推荐要求" : "新建推荐要求";
    const meta = $("requirement-editor-meta");
    meta.replaceChildren();
    if (item) meta.append(element("span", null, `第 ${item.revision} 版 · 编辑来源：${editorAttribution(item)} · `), displayTime(item.updated_at));
    else meta.textContent = "尚未保存";
    $("requirement-reload").hidden = !item;
    notice("");
    savedDraft = JSON.stringify(draft());
    if (clearDraft) clearSessionDraft();
    setBusy(preserveBusy && saving);
  }

  async function selectRequirement(id, {discard = false} = {}) {
    if (saving || (!discard && !canReplaceDraft())) return;
    const sequence = ++editorSequence;
    const loadingDraft = JSON.stringify(draft());
    notice("正在读取已保存的要求…");
    try {
      const item = await api(`/api/requirements/${encodeURIComponent(id)}`);
      if (sequence !== editorSequence) return;
      if (item.source_id !== sourceId) {
        notice("这份要求没有归属当前推荐源，当前草稿已保留。请使用本来源的要求或新建。", true); return;
      }
      if (JSON.stringify(draft()) !== loadingDraft) {
        notice("读取期间输入发生了变化，当前草稿已保留。需要时请重新选择已保存的要求。", true); return;
      }
      loadEditor(item);
    } catch (error) {
      if (sequence === editorSequence) notice(error.httpStatus === 401 ? "页面访问凭证已失效，请重新打开页面。" : "这份要求暂时无法读取；当前输入已保留。", true);
    }
  }

  function requirementCard(item) {
    const card = element("article", "requirement-card");
    const heading = element("div", "source-heading");
    heading.append(element("h2", null, item.title), element("span", "status-chip", item.enabled ? "可选用" : "已停用"));
    card.append(heading);
    const metadata = element("p", "quiet");
    metadata.append(element("span", null, `第 ${item.revision} 版 · ${editorAttribution(item)} · `), displayTime(item.updated_at));
    card.append(metadata);
    const characters = Array.from(item.content || "");
    card.append(element("p", "requirement-preview", characters.slice(0, 160).join("") + (characters.length > 160 ? "…" : "")));
    const edit = element("button", "text-button requirement-edit", "查看与编辑");
    edit.type = "button";
    edit.addEventListener("click", () => selectRequirement(item.requirement_id));
    card.append(edit);
    return card;
  }

  async function load() {
    const sequence = ++listSequence;
    if (!initialized) { setBusy(true); $("requirement-save").textContent = "载入中…"; }
    await bridge.ready;
    if (!initialized) { loadEditor(null, {clearDraft: false}); restoreSessionDraft(); }
    const list = $("requirements-list");
    list.replaceChildren(element("p", "muted", "正在读取推荐要求…"));
    try {
      const result = await api(`/api/requirements?source_id=${encodeURIComponent(sourceId)}`);
      if ((result.items || []).some(item => item.source_id !== sourceId)) throw new Error("Requirement source mismatch");
      if (sequence !== listSequence) return;
      list.replaceChildren(...(result.items || []).map(requirementCard));
      if (!result.items?.length) list.append(element("div", "requirements-empty", "本来源还没有推荐要求。可在下方填写，也可由本地 agent 使用同一入口保存。"));
    } catch (error) {
      if (sequence === listSequence) list.textContent = error.httpStatus === 401 ? "请重新打开已认证的推荐页面。" : "推荐要求暂时无法读取；不会把读取失败当作空列表。";
    }
  }

  function setBusy(value) {
    saving = value;
    for (const id of ["requirement-id", "requirement-title", "requirement-content", "requirement-enabled", "requirement-reload", "requirement-cancel", "requirements-new"]) $(id).disabled = value;
    $("requirement-save").disabled = value || !dirty();
    $("requirement-cancel").hidden = !dirty();
    $("requirement-save").textContent = value ? "保存中…" : "保存要求";
  }

  $("requirement-form").addEventListener("submit", async event => {
    event.preventDefault();
    if (saving || !dirty()) return;
    const data = draft();
    rememberDraft();
    if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(data.requirement_id)) {
      notice("要求标识须为 1–128 位字母、数字、下划线、点或连字符，并以字母或数字开头。", true); return;
    }
    if (!data.title.trim() || Array.from(data.title).length > 200) { notice("请填写名称，最多 200 个字符。", true); return; }
    if (!data.content.trim() || Array.from(data.content).length > 20000) { notice("请填写具体要求，最多 20000 个字符；当前输入已保留。", true); return; }
    const payload = {...data, source_id: sourceId, expected_revision: revision};
    if (new TextEncoder().encode(JSON.stringify(payload)).length > 96 * 1024) {
      notice("本次提交超过 96 KiB，请缩短内容后重试；当前输入没有被截断。", true); return;
    }
    const sequence = editorSequence;
    setBusy(true); notice("正在保存…");
    try {
      const item = await api("/api/requirements", payload);
      if (sequence !== editorSequence) return;
      if (item.source_id !== sourceId) throw new Error("Requirement source mismatch");
      loadEditor(item, {preserveBusy: true});
      notice(`已保存“${item.title}”第 ${item.revision} 版。${item.enabled ? "任务可显式选用这份要求。" : "这份要求已停用。"}`);
      await load();
    } catch (error) {
      if (sequence !== editorSequence) return;
      if (error.code === 5) {
        notice("已保存版本发生变化。你的输入已保留；重新载入会用最新已保存版本替换当前草稿。", true);
        $("requirement-reload").hidden = false;
      } else notice(error.httpStatus === 401 ? "页面凭证已失效。你的输入已保留，请重新打开页面。" : "保存未完成。你的输入已保留，请检查服务状态后重试。", true);
    } finally { setBusy(false); }
  });

  $("requirements-new").addEventListener("click", () => { if (canReplaceDraft()) loadEditor(); });
  $("requirements-refresh").addEventListener("click", load);
  for (const [id, event] of [["requirement-id", "input"], ["requirement-title", "input"], ["requirement-content", "input"], ["requirement-enabled", "change"]]) {
    $(id).addEventListener(event, () => {
      rememberDraft(); setBusy(false);
      notice(dirty() ? "有未保存的修改。" : "没有未保存的修改。");
    });
  }
  $("requirement-cancel").addEventListener("click", () => {
    if (saving || !dirty() || !canReplaceDraft()) return;
    loadEditor(savedItem); notice("修改已取消。");
  });
  $("requirement-reload").addEventListener("click", () => {
    if (saving || !$("requirement-id").value) return;
    if (dirty() && !window.confirm?.("重新载入将丢弃当前未保存输入，改用最新已保存版本。是否继续？")) return;
    selectRequirement($("requirement-id").value, {discard: true});
  });
    return {root, load, started: false};
  }

  window.ScholarRecommendationRequirements = {
    mount(container, source) {
      if (!container || typeof source?.source_id !== "string") return;
      const id = source.source_id;
      if (!widgets.has(id)) widgets.set(id, createWidget(source));
      const widget = widgets.get(id);
      // Moving the same per-source DOM preserves its draft and in-flight request state.
      container.replaceChildren(widget.root);
      if (!widget.started) { widget.started = true; widget.load(); }
    }
  };
})();
