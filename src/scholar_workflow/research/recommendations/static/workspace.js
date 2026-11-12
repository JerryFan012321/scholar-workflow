"use strict";

(() => {
  const bridge = window.ScholarRecommendations;
  const $ = (id) => document.getElementById(id);
  if (!bridge || !$("sources-view") || !$("recommendations-view")) return;
  const {api, element, externalLink} = bridge;
  let activeCandidate = null;
  let activePlan = null;
  let modalSequence = 0;
  let lastFocus = null;
  let settingsPage = "sources";
  let activePage = "recommendations";
  let navigationTouched = false;
  let sourcesLoaded = false;
  let sourcesRevision = 0;
  let sourceItems = [];
  let sourceBusy = false;
  let sourceEditorBase = "";
  let sourceEditorRevision = 0;
  let sourceEditingId = null;
  let latestSourceCatalog = null;
  let sourceOutputName = "source-plugin.json";
  const pageScroll = new Map();
  let contextLoaded = false;
  let contextBusy = false;
  let contextRevision = 0;
  let contextBase = {content: "", revision: 0};
  let latestContext = null;
  const isTestProfile = () => bridge.getProfile?.() === "test";

  function errorText(error) {
    if (error.httpStatus === 401) return "页面访问凭证已失效，请用命令重新打开推荐页。";
    if (error.code === 5) return "资料或入库计划已经变化，请刷新后重新确认。";
    if (error.code === 7) return "操作未完成，请检查当前审阅、选择和授权状态。";
    if (error.code === 3) return "服务暂不可用，请检查连接与账号授权。";
    return "本次操作未完成。请检查输入和服务状态后重试。";
  }

  function switchPage(name, {history = "push", focus = true, preserveDetail = false} = {}) {
    if (name === "settings") name = settingsPage;
    if (!["recommendations", "sources", "ingestion", "context"].includes(name)) return;
    if (name === activePage && history === "push") return;
    pageScroll.set(activePage, window.scrollY || 0);
    const inSettings = name !== "recommendations";
    if (inSettings) settingsPage = name;
    if (!preserveDetail) bridge.closeDetail?.({history: false});
    $("settings-view").hidden = !inSettings;
    for (const page of ["recommendations", "sources", "ingestion", "context"]) $(page + "-view").hidden = page !== name;
    document.querySelectorAll("[data-page]").forEach((button) => {
      if (button.dataset.page === "settings") button.removeAttribute("aria-expanded");
      if (button.dataset.page === name || (button.dataset.page === "settings" && inSettings)) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    activePage = name;
    if (history !== "none" && window.history) {
      const next = {...window.history.state, scholarRecommendationPage: name};
      delete next.scholarRecommendationDetail;
      window.history[history === "replace" ? "replaceState" : "pushState"]?.(next, "");
    }
    const labels = {recommendations: "研究推荐", sources: "推荐源", ingestion: "入库记录", context: "推荐上下文"};
    document.title = name === "recommendations" ? "研究推荐 · Scholar Workflow" : `${labels[name]} · 设置 · Scholar Workflow`;
    const heading = $({recommendations: "page-title", sources: "sources-title", ingestion: "ingestion-title", context: "context-title"}[name]);
    if (focus) heading?.focus?.({preventScroll: true});
    window.scrollTo?.({top: pageScroll.get(name) || 0, behavior: "instant"});
    const notice = $("workspace-notice");
    if (notice) notice.hidden = true;
    if (name === "sources" && !sourcesLoaded) loadSources();
    if (name === "ingestion") loadHistory();
    if (name === "context" && !contextLoaded) loadContext({restore: true});
  }

  function contextNotice(text, failed = false) {
    const notice = $("ranking-context-notice");
    notice.textContent = text; notice.hidden = !text; notice.classList.toggle("error", failed);
  }

  function contextKey() {
    const scope = bridge.getDraftScope?.();
    return typeof scope === "string" && scope ? `scholar-recommendations-draft:${scope}:context` : null;
  }

  function contextDirty() {
    return contextLoaded && $("ranking-context-content").value !== contextBase.content;
  }

  function rememberContext() {
    const key = contextKey();
    if (!key) return;
    try {
      if (!contextDirty()) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, JSON.stringify({content: $("ranking-context-content").value,
        base_content: contextBase.content, revision: contextRevision}));
    } catch (_) { /* Session storage is optional; the visible draft remains intact. */ }
  }

  function contextControls(busy, saving = false) {
    contextBusy = busy;
    $("ranking-context-content").disabled = busy || !contextLoaded;
    $("ranking-context-save").disabled = busy || !contextDirty();
    $("ranking-context-save").textContent = saving ? "保存中…" : "保存修改";
    $("ranking-context-reload").disabled = busy;
    const cancel = $("ranking-context-cancel");
    if (cancel) { cancel.hidden = !contextDirty(); cancel.disabled = busy; }
    const adopt = $("ranking-context-adopt");
    if (adopt) adopt.disabled = busy || !latestContext || latestContext.context.revision === contextRevision;
  }

  function contextMetadata(context) {
    const meta = $("ranking-context-meta");
    meta.replaceChildren(element("span", null, `第 ${context.revision || 0} 版${context.updated_by?.name ? ` · ${context.updated_by.name}` : ""}`));
    if (context.updated_at) meta.append(element("span", null, " · "), managementTime(context.updated_at));
  }

  function showLatestContext(result) {
    latestContext = result;
    const view = $("ranking-context-latest");
    if (!view) return;
    view.hidden = false; view.open = true;
    $("ranking-context-latest-content").textContent = result.context.content || "";
    $("ranking-context-latest-meta").textContent = `最新已保存内容 · 第 ${result.context.revision || 0} 版`;
  }

  function applyContext(result) {
    latestContext = result;
    contextBase = {...result.context, content: result.context.content || ""};
    contextRevision = contextBase.revision || 0;
    $("ranking-context-content").value = contextBase.content;
    contextLoaded = true;
    contextMetadata(contextBase);
    const ranking = result.ranking || {};
    $("ranking-context-state").textContent = ranking.status === "stale" ? "输入已变化，等待更新"
      : ranking.status === "current" ? "排序已更新" : "尚无外部 agent 排序";
    if ($("ranking-context-latest")) $("ranking-context-latest").hidden = true;
  }

  function restoreContextDraft(result) {
    const key = contextKey();
    if (!key) return false;
    try {
      const stored = JSON.parse(sessionStorage.getItem(key) || "null");
      if (!stored || typeof stored.content !== "string" || typeof stored.base_content !== "string"
          || !Number.isInteger(stored.revision) || stored.revision < 0 || stored.content === stored.base_content
          || stored.content === result.context.content) return false;
      contextBase = {content: stored.base_content, revision: stored.revision};
      contextRevision = stored.revision;
      $("ranking-context-content").value = stored.content;
      contextMetadata(contextBase);
      if (result.context.revision !== stored.revision) showLatestContext(result);
      contextNotice(result.context.revision !== stored.revision
        ? "已恢复未保存草稿；服务器内容已更新，请对照最新版继续编辑。" : "已恢复本次会话的未保存草稿。");
      return true;
    } catch (_) { return false; }
  }

  async function loadContext({restore = false} = {}) {
    if (contextBusy) return;
    const dirty = contextDirty();
    contextControls(true); contextNotice("正在读取推荐上下文…");
    try {
      await bridge.ready;
      const result = await api("/api/ranking/context");
      if (dirty) {
        showLatestContext(result);
        contextNotice("已显示最新已保存内容；当前草稿保持不变。");
      } else {
        applyContext(result);
        const restored = restore && restoreContextDraft(result);
        if (!restored) { rememberContext(); contextNotice("已载入最新已保存内容。"); }
      }
    } catch (error) { contextNotice(`${errorText(error)}${dirty ? "当前草稿已保留。" : ""}`, true); }
    finally { contextControls(false); }
  }

  $("ranking-context-content").addEventListener("input", () => {
    rememberContext(); contextControls(false);
    contextNotice(contextDirty() ? "有未保存的修改。" : "没有未保存的修改。");
  });
  $("ranking-context-save").addEventListener("click", async () => {
    if (contextBusy || !contextDirty()) return;
    const content = $("ranking-context-content").value;
    rememberContext();
    if (Array.from(content).length > 16000) { contextNotice("上下文最多 16000 字；当前草稿已保留。", true); return; }
    contextControls(true, true); contextNotice("保存中…");
    try {
      applyContext(await api("/api/ranking/context", {content, expected_revision: contextRevision}));
      rememberContext(); contextNotice("上下文已保存。");
      try { await bridge.reload(); } catch (_) { contextNotice("上下文已保存，推荐列表暂未刷新。"); }
    } catch (error) {
      if (error.code === 5) {
        try { showLatestContext(await api("/api/ranking/context")); } catch (_) { /* A failed comparison never replaces the draft. */ }
        contextNotice("上下文已被更新，当前草稿已保留。请对照最新版后继续编辑，或取消修改。", true);
      } else contextNotice(`上下文未保存，草稿已保留。${errorText(error)}`, true);
    } finally { contextControls(false); }
  });
  $("ranking-context-reload").addEventListener("click", () => loadContext());
  $("ranking-context-cancel")?.addEventListener("click", () => {
    if (contextBusy || !contextDirty()) return;
    if (!window.confirm?.("取消修改会丢弃当前未保存内容，是否继续？")) return;
    applyContext(latestContext); rememberContext(); contextControls(false); contextNotice("修改已取消。");
  });
  $("ranking-context-adopt")?.addEventListener("click", () => {
    if (contextBusy || !latestContext) return;
    contextBase = {...latestContext.context, content: latestContext.context.content || ""};
    contextRevision = contextBase.revision || 0;
    contextMetadata(contextBase); rememberContext(); contextControls(false);
    contextNotice(contextDirty() ? "已采用最新版作为基线；草稿内容保持不变，合并后请保存。" : "内容与最新版相同，无需保存。");
  });

  function sourceNotice(text, failed = false) {
    const notice = $("source-plugin-notice");
    notice.textContent = text; notice.hidden = !text; notice.classList.toggle("error", failed);
  }

  function sourceDirty() {
    return !$("source-plugin-editor").hidden && $("source-plugin-json").value !== sourceEditorBase;
  }

  function sourceControls(busy, saving = false) {
    sourceBusy = busy;
    for (const id of ["sources-new", "sources-import", "sources-refresh", "source-plugin-cancel", "source-plugin-reload", "source-plugin-adopt"]) $(id).disabled = busy;
    $("source-plugin-json").disabled = busy;
    $("source-plugin-save").disabled = busy || !sourceDirty();
    $("source-plugin-save").textContent = saving ? "保存中…" : "保存来源包";
  }

  function newSourcePlugin() {
    return {schema_version: 1, source: {source_id: "", name: "", purpose: "", plugin_version: "1.0.0",
      status: "available", enabled: true, scope: "selected_channel",
      interfaces: [{kind: "mcp", url: ""}], capabilities: [""], documentation: [],
      agent: {connection_name: "", instructions: "", operations: [{operation_id: "discover",
        description: "", effect: "read", inputs: "", outputs: ""}]}}};
  }

  function openSourceEditor(plugin, {editingId = null, imported = false, revision = sourcesRevision} = {}) {
    if (sourceDirty() && !window.confirm?.("当前来源包有未保存的修改，是否放弃这些修改？")) return;
    const value = typeof plugin === "string" ? plugin : JSON.stringify(plugin, null, 2);
    sourceEditingId = editingId; sourceEditorRevision = revision;
    sourceEditorBase = imported ? "" : value;
    latestSourceCatalog = null;
    $("source-plugin-json").value = value;
    $("source-plugin-title").textContent = editingId ? "编辑推荐源" : imported ? "预览导入的来源包" : "添加推荐源";
    $("source-plugin-editor-meta").textContent = `基于目录第 ${revision} 版${editingId ? ` · ${editingId}` : ""}`;
    $("source-plugin-editor").hidden = false;
    $("source-plugin-latest").hidden = true;
    $("source-plugin-output").hidden = true;
    sourceControls(false);
    sourceNotice(imported ? "来源包已载入预览；检查后点击保存，不会自动接入账号或获取内容。" : "填写来源包后保存。导入或编辑不会执行其中的接口和说明。");
    $("source-plugin-title").focus?.({preventScroll: true});
    $("source-plugin-editor").scrollIntoView?.({block: "start", behavior: "smooth"});
  }

  function sourceStatus(source) {
    if (source.status === "planned") return "计划接入";
    if (source.enabled === false) return "已停用";
    return source.status === "available" ? "已启用" : "状态待确认";
  }

  function showSourceOutput(value, {title, filename, note}) {
    $("source-plugin-output-title").textContent = title;
    $("source-plugin-output-note").textContent = note;
    $("source-plugin-output-content").value = JSON.stringify(value, null, 2);
    sourceOutputName = filename;
    $("source-plugin-output").hidden = false;
    $("source-plugin-output-title").focus?.({preventScroll: true});
    $("source-plugin-output").scrollIntoView?.({block: "start", behavior: "smooth"});
  }

  async function sourceRead(source, kind) {
    if (sourceBusy) return;
    sourceControls(true);
    try {
      const value = await api(`/api/sources/${kind}?source_id=${encodeURIComponent(source.source_id)}`);
      showSourceOutput(value, {title: kind === "guide" ? `${source.name} · agent 使用说明` : `${source.name} · 来源包`,
        filename: `${source.source_id}-${kind === "guide" ? "agent-guide" : "source-plugin"}.json`,
        note: kind === "guide" ? "交给外部 agent 使用；工具名称与参数须由当前宿主发现，来源说明不证明已连接或已获账号权限。"
          : source.origin === "builtin" ? "这是插件随包分发的定义。内置定义由插件更新；本地启停设置不写入此包。"
          : "可在其他推荐池导入；不包含当前池的推荐要求、账号凭据或操作历史。"});
    } catch (error) { sourceNotice(errorText(error), true); }
    finally { sourceControls(false); }
  }

  async function editSource(source) {
    if (sourceBusy || source.origin === "builtin") return;
    const revision = sourcesRevision;
    sourceControls(true);
    try {
      const plugin = await api(`/api/sources/export?source_id=${encodeURIComponent(source.source_id)}`);
      openSourceEditor(plugin, {editingId: source.source_id, revision});
    } catch (error) { sourceNotice(errorText(error), true); }
    finally { sourceControls(false); }
  }

  async function setSourceEnabled(source, button) {
    if (sourceBusy) return;
    sourceControls(true); button.disabled = true;
    try {
      const result = await api("/api/sources/enabled", {source_id: source.source_id,
        enabled: source.enabled === false, expected_revision: sourcesRevision});
      sourcesRevision = result.revision;
      await loadSources();
      sourceNotice(result.source.enabled ? "推荐源已启用；实际连接与取源由外部 agent 完成。" : "推荐源已停用；原推荐、要求和历史均保留。");
    } catch (error) {
      sourceNotice(error.code === 5 ? "目录已更新，请刷新后重新选择启停状态。" : errorText(error), true);
    } finally { sourceControls(false); button.disabled = false; }
  }

  function sourceCard(source) {
    const card = element("article", "source-card");
    const heading = element("div", "source-heading");
    heading.append(element("h2", null, source.name || "推荐源"),
      element("span", "status-chip", sourceStatus(source)));
    card.append(heading);
    const meta = `${source.origin === "builtin" ? "内置" : "自定义"} · ${source.plugin_version ? `v${source.plugin_version}` : "旧版描述"}`;
    card.append(element("p", "source-plugin-meta", meta));
    const capabilities = element("p", "source-capabilities", (source.capabilities || []).join(" · "));
    if (capabilities.textContent) card.append(capabilities);
    if (source.purpose) card.append(element("p", "muted", source.purpose));
    const connection = source.connection_status || (source.status === "planned" ? "not_implemented" : "not_checked");
    card.append(element("p", "source-connection", {not_checked: "连接未检查 · 工具由 agent 宿主发现", not_implemented: "连接尚未实现"}[connection] || "连接状态待确认"));
    const definitionComplete = typeof source.plugin_version === "string" && source.plugin_version.length > 0
      && typeof source.agent?.instructions === "string" && source.agent.instructions.trim().length > 0
      && Array.isArray(source.agent?.operations) && source.agent.operations.length > 0;
    card.append(element("p", "source-plugin-readiness", definitionComplete ? "使用说明完整" : "使用说明待补全"));
    const actions = element("div", "source-plugin-actions");
    const enabled = element("button", "secondary source-enabled", source.enabled === false ? "启用" : "停用");
    enabled.type = "button"; enabled.disabled = source.status === "planned";
    if (enabled.disabled) enabled.title = "计划中的来源尚不能启用。";
    enabled.addEventListener("click", () => setSourceEnabled(source, enabled));
    const guide = element("button", "text-button source-guide", "agent 使用说明"); guide.type = "button";
    guide.addEventListener("click", () => sourceRead(source, "guide"));
    const exportButton = element("button", "text-button source-export", "导出来源包"); exportButton.type = "button";
    exportButton.addEventListener("click", () => sourceRead(source, "export"));
    actions.append(enabled, guide, exportButton);
    if (source.origin !== "builtin") {
      const edit = element("button", "text-button source-edit", "编辑"); edit.type = "button";
      edit.addEventListener("click", () => editSource(source)); actions.append(edit);
    }
    card.append(actions);
    const detail = element("details", "source-details");
    detail.append(element("summary", null, "接入信息"));
    const entries = element("dl", "source-info");
    const execution = source.execution || {}, auth = source.auth || {};
    const authNames = {host_oauth: "由 agent 宿主授权", oauth: "账号授权", api_key: "本机安全凭据", none: "无需账号凭据", not_configured: "尚未配置"};
    const scopes = {authorized_account: "按授权账户范围", self_account_only: "仅你选定的本人账号", public_research_feed: "公开研究信息流"};
    for (const [label, value] of [["使用范围", scopes[source.scope] || source.scope], ["授权方式", authNames[auth.method] || auth.method],
      ["agent 入口", source.agent?.connection_name || execution.entry || execution.host_connection_name]]) {
      if (value) entries.append(element("dt", null, label), element("dd", null, value));
    }
    const interfaceKinds = {mcp: "MCP 接口", api: "API 接口", feed: "订阅接口", cli: "命令行接口"};
    for (const item of source.interfaces || []) {
      const value = item.url || item.instructions;
      if (value) entries.append(element("dt", null, interfaceKinds[item.kind] || item.kind || "接口"), element("dd", null, value));
    }
    detail.append(entries);
    if (auth.instructions) detail.append(element("p", "muted", auth.instructions));
    for (const [index, url] of (source.documentation || []).entries()) {
      const docs = externalLink(index ? `补充说明 ${index + 1} ↗` : "官方说明 ↗", url);
      if (docs) detail.append(docs);
    }
    card.append(detail);
    const requirements = element("details", "source-requirements");
    requirements.append(element("summary", null, "推荐要求"));
    const editor = element("div", "source-requirements-mount");
    requirements.append(editor);
    requirements.addEventListener("toggle", () => {
      if (requirements.open) window.ScholarRecommendationRequirements?.mount(editor, source);
    });
    card.append(requirements);
    return card;
  }

  async function loadSources() {
    const list = $("sources-list");
    list.replaceChildren(element("p", "muted", "正在读取推荐源…"));
    try {
      const result = await api("/api/sources");
      sourcesLoaded = true;
      sourcesRevision = Number.isInteger(result.revision) ? result.revision : 0;
      sourceItems = result.items || [];
      list.replaceChildren(...sourceItems.map(sourceCard));
      if (!sourceItems.length) list.append(element("div", "empty-state", "当前没有已登记的推荐源。"));
    } catch (error) { list.textContent = errorText(error); }
  }

  async function showLatestSource() {
    const catalog = await api("/api/sources");
    latestSourceCatalog = catalog;
    const identifier = sourceEditingId;
    let value = catalog;
    if (identifier && catalog.items.some(item => item.source_id === identifier)) {
      value = await api(`/api/sources/export?source_id=${encodeURIComponent(identifier)}`);
    }
    $("source-plugin-latest-content").textContent = JSON.stringify(value, null, 2);
    $("source-plugin-latest").hidden = false; $("source-plugin-latest").open = true;
  }

  $("sources-new").addEventListener("click", () => {
    if (!sourceBusy) openSourceEditor(newSourcePlugin());
  });
  $("sources-import").addEventListener("click", () => { if (!sourceBusy) $("source-plugin-file").click(); });
  $("source-plugin-file").addEventListener("change", async () => {
    const file = $("source-plugin-file").files?.[0];
    if (!file || sourceBusy) return;
    if (file.size > 65536) { sourceNotice("来源包最多 64 KiB，请只保留来源定义，不包含候选、历史或凭据。", true); return; }
    try {
      const raw = await file.text();
      JSON.parse(raw);
      openSourceEditor(raw, {imported: true});
    } catch (_) { sourceNotice("文件不是有效 JSON，当前草稿保持不变。", true); }
    finally { $("source-plugin-file").value = ""; }
  });
  $("source-plugin-json").addEventListener("input", () => {
    sourceControls(false); sourceNotice(sourceDirty() ? "有未保存的来源包修改。" : "没有未保存的修改。");
  });
  $("source-plugin-save").addEventListener("click", async () => {
    if (sourceBusy || !sourceDirty()) return;
    let plugin;
    try { plugin = JSON.parse($("source-plugin-json").value); }
    catch (_) { sourceNotice("JSON 格式有误，当前草稿已保留。", true); return; }
    if (sourceEditingId && plugin?.source?.source_id !== sourceEditingId) {
      sourceNotice("编辑时请保留 source_id；新来源请使用“添加推荐源”。当前草稿已保留。", true); return;
    }
    const existing = sourceItems.find(item => item.source_id === plugin?.source?.source_id);
    if (existing?.origin === "builtin") { sourceNotice("内置来源定义随插件更新，只能在此启停或导出。当前草稿已保留。", true); return; }
    if (!sourceEditingId && existing && !window.confirm?.("相同 source_id 已存在，保存将更新该来源定义。是否继续？")) return;
    sourceControls(true, true); sourceNotice("保存中…");
    try {
      const result = await api("/api/sources/import", {plugin, expected_revision: sourceEditorRevision});
      sourceEditorBase = $("source-plugin-json").value;
      $("source-plugin-editor").hidden = true;
      sourcesRevision = result.revision;
      await loadSources();
      sourceNotice(result.changed ? "来源包已保存。账号连接与取源仍由外部 agent 完成。" : "来源包内容未变化。");
    } catch (error) {
      if (error.code === 5) {
        try { await showLatestSource(); } catch (_) { /* A failed comparison must not replace the draft. */ }
        sourceNotice("来源目录已更新，当前草稿已保留。请对照最新版后继续编辑，或取消修改。", true);
      } else sourceNotice(`来源包未保存，草稿已保留。${errorText(error)}`, true);
    } finally { sourceControls(false); }
  });
  $("source-plugin-cancel").addEventListener("click", () => {
    if (sourceBusy || (sourceDirty() && !window.confirm?.("取消会放弃当前未保存的来源包修改，是否继续？"))) return;
    $("source-plugin-json").value = sourceEditorBase;
    $("source-plugin-editor").hidden = true;
    $("source-plugin-latest").hidden = true;
    sourceControls(false); sourceNotice("编辑已取消。");
  });
  $("source-plugin-reload").addEventListener("click", async () => {
    if (sourceBusy) return;
    sourceControls(true);
    try { await showLatestSource(); sourceNotice("已显示最新已保存内容；当前草稿保持不变。"); }
    catch (error) { sourceNotice(errorText(error), true); }
    finally { sourceControls(false); }
  });
  $("source-plugin-adopt").addEventListener("click", () => {
    if (sourceBusy || !latestSourceCatalog) return;
    sourceEditorRevision = latestSourceCatalog.revision;
    sourceItems = latestSourceCatalog.items || [];
    sourcesRevision = sourceEditorRevision;
    $("source-plugin-editor-meta").textContent = `基于目录第 ${sourceEditorRevision} 版${sourceEditingId ? ` · ${sourceEditingId}` : ""}`;
    sourceNotice("已采用最新版目录编号；草稿保持不变。请合并差异后保存。");
  });
  $("source-plugin-copy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("source-plugin-output-content").value);
      sourceNotice("内容已复制。");
    } catch (_) {
      $("source-plugin-output-content").focus?.(); $("source-plugin-output-content").select?.();
      sourceNotice("请复制已选中的 JSON 内容。");
    }
  });
  $("source-plugin-download").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([$("source-plugin-output-content").value + "\n"], {type: "application/json"}));
    const link = document.createElement("a"); link.href = url; link.download = sourceOutputName;
    document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  });
  $("source-plugin-output-close").addEventListener("click", () => { $("source-plugin-output").hidden = true; });
  window.addEventListener?.("beforeunload", event => {
    if (sourceDirty()) { event.preventDefault(); event.returnValue = ""; }
  });

  function managementTime(value) {
    const time = element("time");
    const parsed = new Date(value);
    time.title = value || "";
    if (!value || Number.isNaN(parsed.getTime())) {
      time.textContent = value || "时间未提供";
    } else {
      time.dateTime = value;
      time.textContent = parsed.toLocaleString("zh-CN", {timeZone: "Asia/Shanghai", year: "numeric",
        month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false}) + "（北京时间）";
    }
    return time;
  }

  function historyStatus(value) {
    if (isTestProfile() && ["completed", "complete", "created", "existing", "existing_updated"].includes(value)) return "模拟书目入库完成";
    return {completed: "书目已入库", complete: "书目已入库", created: "书目已入库", existing: "已复用书目",
      existing_updated: "已更新分类", failed: "入库失败", needs_attention: "需要处理", pending: "等待处理",
      running: "正在处理", retry: "等待重试", cancelled: "已撤销待入库", in_progress: "正在处理", interrupted: "执行中断", conflict: "身份冲突", planned: "已生成计划"}[value] || "状态待确认";
  }

  function receiptView(receipt) {
    const card = element("article", "history-card");
    card.append(element("h2", null, receipt.title || "推荐资料"), element("span", "status-chip", historyStatus(receipt.status)));
    const details = element("dl", "receipt-details");
    for (const [label, value] of [["目标分类", receipt.collection?.name || receipt.collection_name || receipt.collection_key],
      ["处理时间", receipt.completed_at || receipt.updated_at || receipt.created_at]]) {
      if (!value) continue;
      const detail = element("dd");
      if (label === "处理时间") detail.append(managementTime(value));
      else detail.textContent = value;
      details.append(element("dt", null, label), detail);
    }
    details.append(element("dt", null, "完成范围"), element("dd", null, "Zotero 书目；PDF 与 Vault 归档另行处理"));
    card.append(details);
    if (receipt.error) card.append(element("p", "receipt-error", receipt.error));
    if (receipt.message) card.append(element("p", "muted", receipt.message));
    if (typeof receipt.item_key === "string" && /^[A-Z0-9]{8}$/.test(receipt.item_key)) {
      const link = element("a", "zotero-link", "在 Zotero 中查看 ↗");
      link.href = `zotero://select/library/items/${receipt.item_key}`; card.append(link);
    }
    return card;
  }

  function historyRow(receipt) {
    const row = element("details", "history-row");
    const summary = element("summary", "history-row-summary");
    const icon = element("span", "history-row-icon", "▤");
    icon.setAttribute("aria-hidden", "true");
    const title = element("span", "history-row-title", receipt.title || "推荐资料");
    title.title = receipt.title || "推荐资料";
    const timeValue = receipt.completed_at || receipt.updated_at || receipt.created_at;
    const time = managementTime(timeValue);
    time.className = "history-row-time";
    const parsed = new Date(timeValue);
    time.textContent = timeValue && !Number.isNaN(parsed.getTime())
      ? parsed.toLocaleDateString("zh-CN", {timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit"})
      : "时间未提供";
    summary.append(icon, title, element("span", "history-row-status", historyStatus(receipt.status)), time);
    row.append(summary);
    const content = element("div", "history-row-content");
    content.append(receiptView(receipt));
    row.append(content);
    return row;
  }

  async function loadHistory() {
    const list = $("ingestion-history");
    const scope = $("ingestion-view").querySelector?.(".scope-note");
    if (scope) scope.textContent = (isTestProfile() ? "测试记录为模拟结果，不代表资料已写入真实 Zotero。" : "当前页面支持 Zotero 书目入库。")
      + "PDF 附件和 Vault 知识单元的完成情况另行确认。";
    list.replaceChildren(element("p", "muted", "正在读取入库记录…"));
    try {
      const [legacy, current] = await Promise.all([api("/api/ingestion/history"), api("/api/intake/history")]);
      const items = [...current.items.map(job => ({...job, ...job.receipt,
        collection_name: current.configuration.collection_name})), ...(legacy.items || [])];
      list.replaceChildren(...items.map(historyRow));
      if (!items.length) list.append(element("div", "empty-state", "还没有入库记录。先设置接收分类，再在推荐详情中选择入库。"));
      await loadIntakeTarget(current.configuration);
    } catch (error) { list.textContent = errorText(error); }
  }

  let intakeConfiguration = {revision: 0, enabled: false};
  async function loadIntakeTarget(configuration) {
    intakeConfiguration = configuration;
    const select = $("intake-target-collection");
    select.replaceChildren(element("option", null, "请选择接收分类")); select.options[0].value = "";
    $("intake-target-status").textContent = configuration.enabled
      ? `自动接收到：${configuration.collection_name}` : "尚未启用自动接收。";
    try {
      const result = await api("/api/ingestion/targets");
      if (!result.available) throw new Error(result.reason || "Zotero 暂不可用");
      for (const target of result.targets) {
        const option = element("option", null, target.name); option.value = target.key || target.collection_key;
        select.append(option);
      }
      select.value = configuration.collection_key || "";
    } catch (error) { $("intake-target-status").textContent += ` ${errorText(error)}`; }
  }
  async function saveIntakeTarget(enabled) {
    const status = $("intake-target-status");
    const collection = $("intake-target-collection").value;
    if (enabled && !collection) { status.textContent = "请先选择一个现有 Zotero 分类。"; return; }
    $("intake-target-save").disabled = true; $("intake-target-disable").disabled = true;
    try {
      const result = await api("/api/intake/configuration", {collection_key: collection || null,
        expected_revision: intakeConfiguration.revision, enabled});
      await loadIntakeTarget(result); await bridge.reload();
    } catch (error) { status.textContent = errorText(error); }
    finally { $("intake-target-save").disabled = false; $("intake-target-disable").disabled = false; }
  }
  $("intake-target-save").addEventListener("click", () => saveIntakeTarget(true));
  $("intake-target-disable").addEventListener("click", () => saveIntakeTarget(false));
  $("intake-retry").addEventListener("click", async () => {
    $("intake-retry").disabled = true;
    try { await api("/api/intake/process", {retry: true}); await loadHistory(); await bridge.reload(); }
    catch (error) { $("intake-target-status").textContent = errorText(error); }
    finally { $("intake-retry").disabled = false; }
  });

  function modalStatus(text, failed = false) {
    const node = $("ingestion-dialog-status"); node.textContent = text; node.hidden = !text;
    node.classList.toggle("error", failed);
  }

  function closeIngestion() {
    modalSequence++; $("ingestion-overlay").hidden = true;
    activeCandidate = null; activePlan = null;
    if (lastFocus?.focus) lastFocus.focus();
  }

  async function openIngestion(candidate) {
    const sequence = ++modalSequence; activeCandidate = candidate; activePlan = null;
    lastFocus = document.activeElement;
    $("ingestion-overlay").hidden = false; $("ingestion-close").focus();
    $("ingestion-dialog-title").textContent = isTestProfile() ? "模拟书目入库（不写入真实 Zotero）" : "预览 Zotero 书目入库";
    $("ingestion-candidate-title").textContent = candidate.resource.title;
    $("ingestion-plan").hidden = true; $("ingestion-plan").replaceChildren();
    $("ingestion-preview").disabled = true; modalStatus("正在读取 Zotero 分类…");
    const select = $("ingestion-collection"); select.disabled = false;
    select.replaceChildren(element("option", null, "请选择 Zotero 分类")); select.options[0].value = "";
    try {
      const result = await api("/api/ingestion/targets");
      if (sequence !== modalSequence) return;
      if (!result.available) { modalStatus(result.reason || "Zotero Local API 尚未就绪。", true); return; }
      for (const target of result.targets || []) { const option = element("option", null, target.name); option.value = target.key; select.append(option); }
      if (!result.targets?.length) { modalStatus("Zotero 中没有可用分类，请先在 Zotero 创建或选择分类。", true); return; }
      modalStatus(""); $("ingestion-preview").disabled = false;
    } catch (error) { if (sequence === modalSequence) modalStatus(errorText(error), true); }
  }

  $("ingestion-preview").addEventListener("click", async () => {
    if (!activeCandidate || !$("ingestion-collection").value) { modalStatus("请先选择目标分类。", true); return; }
    const sequence = modalSequence, selectedCollection = $("ingestion-collection").value;
    $("ingestion-preview").disabled = true; $("ingestion-collection").disabled = true;
    activePlan = null; $("ingestion-plan").hidden = true; modalStatus("正在检查资料与目标分类…");
    try {
      const plan = await api("/api/ingestion/plan", {candidate_id: activeCandidate.candidate_id,
        expected_revision: activeCandidate.revision, collection_key: selectedCollection});
      if (sequence !== modalSequence || $("ingestion-collection").value !== selectedCollection) return;
      activePlan = plan; modalStatus("");
      const panel = $("ingestion-plan");
      panel.replaceChildren(element("h3", null, isTestProfile() ? "确认模拟书目入库" : "确认书目入库"),
        element("p", null, `${plan.title} → ${plan.collection?.name || "所选分类"}`),
        element("p", "scope-note", (isTestProfile() ? "本次仅模拟书目入库，不写入真实 Zotero；" : "本次加入 Zotero 书目，")
          + "不表示 PDF 已保存或 Vault 知识单元已建立。"));
      const names = {journalArticle: "期刊论文", conferencePaper: "会议论文", preprint: "预印本", blogPost: "博客", webpage: "网页", book: "书籍", report: "报告"};
      if (plan.item_type) panel.append(element("p", "plan-item-type", `书目类型：${names[plan.item_type] || plan.item_type}`));
      panel.append(element("p", "plan-existing", plan.existing ? "已找到对应书目，本次将复用它并加入所选分类。" : "未找到对应书目，本次将创建书目并加入所选分类。"));
      for (const warning of plan.warnings || []) panel.append(element("p", "plan-warning", warning));
      const execute = element("button", "primary ingestion-execute", isTestProfile() ? "确认模拟书目入库" : "确认 Zotero 书目入库"); execute.type = "button";
      execute.addEventListener("click", async () => {
        if (!activePlan || activePlan.plan_id !== plan.plan_id) return;
        execute.disabled = true; $("ingestion-preview").disabled = true; $("ingestion-collection").disabled = true;
        modalStatus("正在入库，请等待结果…");
        try {
          const receipt = await api("/api/ingestion/execute", {plan_id: plan.plan_id, confirmed: true});
          if (sequence !== modalSequence) return;
          activePlan = null; panel.replaceChildren(receiptView(receipt));
          const completed = ["completed", "complete", "created", "existing", "existing_updated"].includes(receipt.status);
          modalStatus(completed ? "处理完成，实际结果如下。" : "本次入库尚未完成，请查看结果。", !completed);
          await bridge.reload();
        } catch (error) { if (sequence === modalSequence) { modalStatus(errorText(error), true); execute.disabled = false; } }
        finally { if (sequence === modalSequence) { $("ingestion-preview").disabled = false; $("ingestion-collection").disabled = false; } }
      });
      panel.append(execute); panel.hidden = false;
    } catch (error) { if (sequence === modalSequence) modalStatus(errorText(error), true); }
    finally { if (sequence === modalSequence) { $("ingestion-preview").disabled = false; $("ingestion-collection").disabled = false; } }
  });
  $("ingestion-collection").addEventListener("change", () => { activePlan = null; $("ingestion-plan").hidden = true; });
  $("ingestion-close").addEventListener("click", closeIngestion);
  $("ingestion-overlay").addEventListener("click", event => { if (event.target === $("ingestion-overlay")) closeIngestion(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !$("ingestion-overlay").hidden) closeIngestion(); });

  document.querySelectorAll("[data-page]").forEach(button => button.addEventListener("click", () => {
    navigationTouched = true; switchPage(button.dataset.page);
  }));
  window.addEventListener?.("popstate", event => {
    const state = event.state || {};
    switchPage(state.scholarRecommendationPage || "recommendations", {history: "none",
      preserveDetail: Boolean(state.scholarRecommendationDetail), focus: !state.scholarRecommendationDetail});
  });
  const initialPage = window.history?.state?.scholarRecommendationPage;
  if (["sources", "ingestion", "context"].includes(initialPage)) {
    Promise.resolve(bridge.ready).then(() => {
      if (!navigationTouched) switchPage(initialPage, {history: "replace", focus: false});
    });
  } else if (window.history) {
    window.history.replaceState?.({...window.history.state, scholarRecommendationPage: "recommendations"}, "");
  }
  $("sources-refresh").addEventListener("click", loadSources);
  $("ingestion-refresh").addEventListener("click", loadHistory);
  window.ScholarRecommendationWorkspace = {
    decorateCard(article, candidate) {
      if (Object.prototype.hasOwnProperty.call(candidate, "intake_target")) {
        const line = element("div", "ingestion-card-action");
        const text = candidate.intake_target
          ? `选择后自动接收到 ${candidate.intake_target.collection_name}` : "先在设置中指定待整理条目的接收分类";
        line.append(element("span", "muted", text));
        const settings = element("button", "text-button", "接收设置"); settings.type = "button";
        settings.addEventListener("click", () => switchPage("ingestion")); line.append(settings);
        if (candidate.intake_job) line.append(element("span", "status-chip", historyStatus(candidate.intake_job.status)));
        (article.querySelector?.(".card-actions") || article).append(line);
        return;
      }
      const button = element("button", "primary ingestion-open", isTestProfile() ? "预览模拟书目入库" : "预览 Zotero 书目入库");
      button.type = "button";
      button.disabled = candidate.decision !== "selected" || (candidate.review_required !== false && !candidate.abstract_reviewed);
      button.title = button.disabled ? "先审阅当前摘要或总结，并选择入库。" : "选择分类并确认加入 Zotero 书目。";
      button.addEventListener("click", () => openIngestion(candidate));
      const line = element("div", "ingestion-card-action");
      line.append(button);
      if (candidate.ingestion) line.append(element("span", "status-chip", candidate.ingestion.matches_current_content === false
        ? "旧内容有入库记录" : historyStatus(candidate.ingestion.status)));
      (article.querySelector?.(".card-actions") || article).append(line);
    }
  };
})();
