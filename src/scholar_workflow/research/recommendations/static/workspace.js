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

  function sourceStatus(source) {
    if (source.status === "planned") return "计划接入";
    if (source.enabled === false) return "已停用";
    return source.status === "available" ? "已收录" : "状态待确认";
  }

  function sourceCard(source) {
    const names = {"x-self": "X 本人精选", "zhihu-self": "知乎本人收藏"};
    const purposes = {
      alphaxiv: "提供热门、个性化研究与主题发现，可由现有 agent 调用原生能力。",
      "hf-daily": "提供社区发现的每日论文与原始投票数据。",
      "x-self": "计划跟踪你选定的本人账号 repost 或书签。",
      "zhihu-self": "计划跟踪你选定的本人账号收藏或收藏夹。"
    };
    const capabilityNames = {"popular research feed": "热门研究", "personalized research feed": "个性化推荐",
      "topic discovery": "主题发现", "paper reading": "论文阅读", "researcher discovery": "查找研究者",
      "researcher follow management": "关注研究者", "native reading-library management": "原生阅读文库",
      "daily paper metadata": "每日论文信息", "community upvotes": "社区投票", "own reposts": "本人 repost",
      "own bookmarks": "本人书签", "own recent collections": "本人近期收藏", "own selected collection folder": "本人指定收藏夹"};
    const instructions = {
      alphaxiv: "账号授权由外部 agent 的宿主连接管理。本目录只描述来源，不证明账号已授权。",
      "hf-daily": "使用既有公开来源适配器；实际获取时确认是否可用。",
      "x-self": "后续接入仅限你选定的本人账号，并需要明确读取费用边界。",
      "zhihu-self": "后续通过官方工具配置本人账号；本目录不会读取账户、收藏或凭据。"
    };
    const card = element("article", "source-card");
    const heading = element("div", "source-heading");
    heading.append(element("h2", null, names[source.source_id] || source.name || "推荐源"),
      element("span", "status-chip", sourceStatus(source)));
    card.append(heading);
    const capabilities = element("p", "source-capabilities", (source.capabilities || [])
      .map(value => capabilityNames[value] || value).join(" · "));
    if (capabilities.textContent) card.append(capabilities);
    if (source.purpose) card.append(element("p", "muted", purposes[source.source_id] || source.purpose));
    const connection = source.connection_status || (source.status === "planned" ? "not_implemented" : "not_checked");
    card.append(element("p", "source-connection", {not_checked: "连接未检查", not_implemented: "连接尚未实现"}[connection] || "连接状态待确认"));
    const detail = element("details", "source-details");
    detail.append(element("summary", null, "接入信息"));
    const entries = element("dl", "source-info");
    const execution = source.execution || {}, auth = source.auth || {};
    const authNames = {host_oauth: "由 agent 宿主授权", oauth: "账号授权", api_key: "本机安全凭据", none: "无需账号凭据", not_configured: "尚未配置"};
    const scopes = {authorized_account: "按授权账户范围", self_account_only: "仅你选定的本人账号", public_research_feed: "公开研究信息流"};
    for (const [label, value] of [["使用范围", scopes[source.scope] || source.scope], ["授权方式", authNames[auth.method] || auth.method],
      ["agent 入口", execution.entry || (execution.host_connection_name ? `宿主 MCP：${execution.host_connection_name}` : null)]]) {
      if (value) entries.append(element("dt", null, label), element("dd", null, value));
    }
    const interfaceKinds = {mcp: "MCP 接口", api: "API 接口", cli: "命令行接口"};
    for (const item of source.interfaces || []) {
      const value = item.url || item.instructions;
      if (value) entries.append(element("dt", null, interfaceKinds[item.kind] || item.kind || "接口"), element("dd", null, value));
    }
    detail.append(entries);
    if (auth.instructions) detail.append(element("p", "muted", instructions[source.source_id] || auth.instructions));
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
      list.replaceChildren(...(result.items || []).map(sourceCard));
      if (!result.items?.length) list.append(element("div", "empty-state", "当前没有已登记的推荐源。"));
    } catch (error) { list.textContent = errorText(error); }
  }

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
      running: "正在处理", in_progress: "正在处理", interrupted: "执行中断", conflict: "身份冲突", planned: "已生成计划"}[value] || "状态待确认";
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
      const result = await api("/api/ingestion/history");
      list.replaceChildren(...(result.items || []).map(historyRow));
      if (!result.items?.length) list.append(element("div", "empty-state", "还没有入库记录。可在推荐详情中审阅、选中资料，再加入 Zotero。"));
    } catch (error) { list.textContent = errorText(error); }
  }

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
