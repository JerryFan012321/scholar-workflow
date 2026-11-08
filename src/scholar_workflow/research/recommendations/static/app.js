"use strict";

(() => {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  let token = fragment.get("token") || "";
  try {
    if (fragment.has("token")) {
      sessionStorage.removeItem("scholar-recommendations-session");
      if (/^[A-Za-z0-9_-]{32,256}$/.test(token)) {
        sessionStorage.setItem("scholar-recommendations-session", token);
      }
    } else {
      token = sessionStorage.getItem("scholar-recommendations-session") || "";
    }
  } catch (_) { /* Without tab storage, the initial authenticated URL still works. */ }
  if (window.location.hash) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }

  const $ = (id) => document.getElementById(id);
  const kindNames = {paper: "论文", project: "项目主页", blog: "博客"};
  const decisionNames = {unread: "未处理", saved: "稍后看", selected: "已选入库", ignored: "已忽略"};
  const state = {profile: "personal", query: "", kind: "", tag: "", producer_id: "",
    since: "", decision: "", sort: "published", offset: 0, limit: 20, total: 0};
  let sequence = 0;
  let searchTimer;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function externalLink(label, value, className) {
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.username || url.password) return null;
      const node = element("a", className, label);
      node.href = url.href;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
      return node;
    } catch (_) {
      return null;
    }
  }

  function notify(text, error = false) {
    $("notice").textContent = text;
    $("notice").classList.toggle("error", error);
    $("notice").hidden = !text;
  }

  function readableError(error) {
    if (error.httpStatus === 401) return "页面访问凭证已失效，请从终端命令重新打开推荐页。";
    if (error.code === 5) return "这项内容刚刚发生变化，请刷新后重试。";
    if (error.code === 7) return "操作尚未完成。请确认论文具有完整摘要译文，并已明确勾选审阅确认。";
    if (error.code === 2) return "操作未完成，请检查筛选或所选对象后重试。";
    return "暂时无法完成操作。请刷新页面，或在终端检查推荐服务状态。";
  }

  async function api(path, payload) {
    const options = {headers: {Authorization: `Bearer ${token}`}, credentials: "omit", cache: "no-store"};
    if (payload !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
    const result = await response.json();
    if (!response.ok) {
      const error = new Error("Recommendation request failed");
      error.code = result.exit_code;
      error.httpStatus = response.status;
      throw error;
    }
    return result;
  }

  function saveFilters() {
    try {
      const stored = Object.fromEntries(["query", "kind", "tag", "producer_id", "since", "decision", "sort"]
        .map((key) => [key, state[key]]));
      sessionStorage.setItem(`scholar-recommendations-${state.profile}-filters`, JSON.stringify(stored));
    } catch (_) { /* Filters are optional convenience state, never authentication. */ }
  }

  function restoreFilters() {
    try {
      const stored = JSON.parse(sessionStorage.getItem(`scholar-recommendations-${state.profile}-filters`) || "{}");
      for (const key of ["query", "kind", "tag", "producer_id", "since", "decision", "sort"]) {
        if (typeof stored[key] === "string" && stored[key].length <= 300) state[key] = stored[key];
      }
    } catch (_) { /* A stale filter does not prevent opening the feed. */ }
    for (const key of ["query", "kind", "since", "sort"]) $(key).value = state[key];
    syncDecisionTabs();
  }

  function syncDecisionTabs() {
    document.querySelectorAll("[data-decision]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.decision === state.decision));
    });
  }

  function updateFacet(id, entries, emptyLabel, valueKey, nameKey) {
    const select = $(id);
    select.replaceChildren(element("option", null, emptyLabel));
    select.options[0].value = "";
    for (const entry of entries || []) {
      const value = valueKey ? entry[valueKey] : entry;
      const name = nameKey ? entry[nameKey] : entry;
      if (typeof value !== "string" || typeof name !== "string") continue;
      const option = element("option", null, name);
      option.value = value;
      select.append(option);
    }
    if (state[id] && !Array.from(select.options).some((option) => option.value === state[id])) {
      const option = element("option", null, state[id]);
      option.value = state[id];
      select.append(option);
    }
    select.value = state[id];
  }

  function publicationSince(days) {
    if (!days) return "";
    const date = new Date();
    date.setDate(date.getDate() - (Number(days) - 1));
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  function displayDate(value) {
    if (!value) return "日期未提供";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("zh-CN");
  }

  function latestMetrics(observations) {
    const latest = new Map();
    for (const observation of observations || []) {
      const key = JSON.stringify([observation.platform, observation.metric,
        observation.url, observation.period || null]);
      const previous = latest.get(key);
      if (!previous || new Date(observation.observed_at).getTime() >= new Date(previous.observed_at).getTime()) {
        latest.set(key, observation);
      }
    }
    return Array.from(latest.values());
  }

  async function updateCandidate(candidate, path, extra) {
    notify("");
    try {
      await api(path, {candidate_id: candidate.candidate_id,
        expected_revision: candidate.revision, ...extra});
      await load();
    } catch (error) {
      notify(readableError(error), true);
      await load();
    }
  }

  function card(candidate) {
    const resource = candidate.resource || {};
    const article = element("article", `card${candidate.decision === "selected" ? " selected" : ""}`);
    const meta = element("div", "card-meta");
    meta.append(element("span", "kind-label", kindNames[resource.kind] || "资料"));
    meta.append(element("span", null, displayDate(resource.published_at)));
    article.append(meta);

    const heading = element("h2");
    const title = externalLink(resource.title, resource.url);
    heading.append(title || element("span", null, resource.title || "未提供标题"));
    article.append(heading);
    if (Array.isArray(resource.authors) && resource.authors.length) {
      article.append(element("p", "authors", resource.authors.join(" · ")));
    }
    const tags = element("div", "tags");
    for (const tag of candidate.tags || []) tags.append(element("span", "tag", tag));
    if (tags.childElementCount) article.append(tags);

    const isPaper = resource.kind === "paper";
    const translated = isPaper ? resource.abstract_zh : resource.description_zh;
    const original = isPaper ? resource.abstract_original : resource.description_original;
    const label = isPaper ? "摘要译文" : "原文简介译文";
    if (translated) {
      article.append(element("div", "summary-label", label));
      article.append(element("p", "summary", translated));
    } else if (original && !isPaper) {
      article.append(element("div", "summary-label", "原文简介"));
      article.append(element("p", "summary", original));
    } else {
      article.append(element("p", "unavailable", isPaper
        ? "尚无完整摘要译文。补齐后才能确认审阅并选择入库。"
        : "尚未提供原文简介，可直接打开原文查看。"));
    }
    if (original && (translated || isPaper)) {
      const detail = element("details", "original");
      detail.append(element("summary", null, isPaper ? "查看原文摘要" : "查看原文简介"));
      detail.append(element("p", null, original));
      article.append(detail);
    }

    const links = element("nav", "links");
    links.setAttribute("aria-label", "资料链接");
    const values = [{label: isPaper ? "论文原文 ↗" : "打开原文 ↗", url: resource.url},
      ...(resource.project_url ? [{label: "项目主页 ↗", url: resource.project_url}] : []),
      ...(resource.links || [])];
    const seen = new Set();
    for (const value of values) {
      if (!value.url || seen.has(value.url)) continue;
      const anchor = externalLink(value.label, value.url);
      if (anchor) { links.append(anchor); seen.add(value.url); }
    }
    article.append(links);

    if ((candidate.metrics || []).length) {
      const metrics = element("div", "metrics");
      for (const metric of latestMetrics(candidate.metrics)) {
        const entry = element("div", "metric");
        const metricName = `${metric.platform} ${metric.metric}`;
        const anchor = externalLink(metricName, metric.url);
        entry.append(anchor || element("span", null, metricName));
        entry.append(element("span", "metric-value", metric.value));
        const time = element("time", null, `采集于 ${displayDate(metric.observed_at)}`);
        time.title = metric.observed_at || "";
        if (metric.observed_at) time.dateTime = metric.observed_at;
        entry.append(time);
        if (metric.period) entry.append(element("span", null, metric.period));
        metrics.append(entry);
      }
      article.append(metrics);
    }

    const records = candidate.recommendations || [];
    const recommendations = element("details", "recommendations");
    const producers = (candidate.producers || []).map((producer) => producer.name);
    recommendations.append(element("summary", null,
      `推荐任务：${producers.join("、") || "未提供"}${records.length > 1 ? ` · ${records.length} 条推荐记录` : ""}`));
    const recordList = element("ul");
    for (const record of records) {
      const row = element("li");
      const producer = record.producer || {};
      row.append(element("span", null,
        `${producer.name || "未提供任务名称"} · ${displayDate(record.received_at)}${record.tags?.length ? ` · ${record.tags.join("、")}` : ""}`));
      for (const channel of record.channels || []) {
        const source = externalLink(` · ${channel.name}`, channel.url);
        if (source) row.append(source);
      }
      recordList.append(row);
    }
    recommendations.append(recordList);
    article.append(recommendations);

    if (isPaper) {
      const review = element("label", "review");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(candidate.abstract_reviewed);
      checkbox.disabled = Boolean(candidate.abstract_reviewed) || !resource.abstract_original || !resource.abstract_zh;
      checkbox.addEventListener("change", () => {
        checkbox.disabled = true;
        updateCandidate(candidate, "/api/reviews", {});
      });
      review.append(checkbox, element("span", null, candidate.abstract_reviewed
        ? "这份摘要译文已确认审阅" : "我已阅读这份摘要译文"));
      article.append(review);
    }

    const actions = element("div", "card-actions");
    const selection = element("label", "select-label");
    const selected = element("input", "select-input");
    selected.type = "checkbox";
    selected.checked = candidate.decision === "selected";
    selected.disabled = isPaper && !candidate.abstract_reviewed && candidate.decision !== "selected";
    selected.addEventListener("change", () => {
      selected.disabled = true;
      updateCandidate(candidate, "/api/decisions", {decision: selected.checked ? "selected" : "unread"});
    });
    selection.append(selected, element("span", null, "选择入库"));
    actions.append(selection);
    const group = element("div", "action-group");
    for (const [decision, text] of [["saved", "稍后看"], ["ignored", "忽略"]]) {
      const button = element("button", "text-button", text);
      button.type = "button";
      button.setAttribute("aria-pressed", String(candidate.decision === decision));
      button.addEventListener("click", () => {
        button.disabled = true;
        updateCandidate(candidate, "/api/decisions", {
          decision: candidate.decision === decision ? "unread" : decision});
      });
      group.append(button);
    }
    actions.append(group);
    article.append(actions);
    if (candidate.decision && candidate.decision !== "unread") {
      article.append(element("div", "decision-note", `${decisionNames[candidate.decision] || ""} · 尚未执行入库`));
    }
    return article;
  }

  async function load() {
    const current = ++sequence;
    $("feed").setAttribute("aria-busy", "true");
    const params = new URLSearchParams({limit: String(state.limit), offset: String(state.offset), sort: state.sort});
    for (const key of ["query", "kind", "tag", "producer_id", "decision"]) {
      if (state[key]) params.set(key, state[key]);
    }
    if (state.since) params.set("since", publicationSince(state.since));
    try {
      const [result, selected] = await Promise.all([
        api(`/api/candidates?${params}`), api("/api/candidates?decision=selected&limit=1")]);
      if (current !== sequence) return;
      state.total = result.total || 0;
      $("feed").replaceChildren(...(result.items || []).map(card));
      $("empty").hidden = Boolean(result.items?.length);
      const filtered = Boolean(state.query || state.kind || state.tag || state.producer_id || state.since || state.decision);
      $("empty-title").textContent = filtered ? "没有符合条件的推荐" : "等待第一批推荐";
      $("empty-description").textContent = filtered ? "可以调整筛选条件，或刷新列表查看最新提交。"
        : "让你的推荐 agent 读取 recommend-papers Skill，并通过统一入口提交论文、项目主页或博客。";
      $("empty-command").hidden = filtered;
      $("empty-command").textContent = `scholar-research recommendations${state.profile === "test" ? " --profile test" : ""} schema\nscholar-research recommendations${state.profile === "test" ? " --profile test" : ""} submit --input recommendations.json`;
      $("result-count").textContent = `${state.total} 项`;
      $("selected-count").textContent = String(selected.total || 0);
      $("export").disabled = !selected.total;
      $("previous").disabled = state.offset === 0;
      $("next").disabled = state.offset + state.limit >= state.total;
      $("page-number").textContent = state.total ? `${Math.floor(state.offset / state.limit) + 1} / ${Math.ceil(state.total / state.limit)}` : "";
      updateFacet("tag", result.facets?.tags, "全部领域");
      updateFacet("producer_id", result.facets?.producers, "全部任务", "producer_id", "name");
      saveFilters();
    } catch (error) {
      if (current !== sequence) return;
      if (error.httpStatus === 401) {
        try { sessionStorage.removeItem("scholar-recommendations-session"); } catch (_) { /* No persistent credential is required. */ }
        $("auth-error").hidden = false;
        $("empty").hidden = true;
      }
      notify(readableError(error), true);
    } finally {
      if (current === sequence) $("feed").setAttribute("aria-busy", "false");
    }
  }

  for (const key of ["kind", "tag", "producer_id", "since", "sort"]) {
    $(key).addEventListener("change", () => { state[key] = $(key).value; state.offset = 0; load(); });
  }
  $("query").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.query = $("query").value; state.offset = 0; load(); }, 250);
  });
  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => {
      state.decision = button.dataset.decision;
      state.offset = 0;
      syncDecisionTabs();
      load();
    });
  });
  $("refresh").addEventListener("click", () => load());
  $("previous").addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); load(); });
  $("next").addEventListener("click", () => { state.offset += state.limit; load(); });
  $("export").addEventListener("click", async () => {
    $("export").disabled = true;
    try {
      const handoff = await api("/api/handoff");
      const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(handoff, null, 2)], {type: "application/json"}));
      const anchor = element("a");
      anchor.href = objectUrl;
      anchor.download = `scholar-ingest-selection-${state.profile}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      notify(`已导出 ${handoff.items?.length || 0} 项入库清单，尚未写入知识库。请将清单交给 ingest-resource Skill 执行。`);
    } catch (error) {
      notify(readableError(error), true);
    } finally {
      await load();
    }
  });

  async function initialize() {
    try {
      const response = await fetch("/health", {cache: "no-store", credentials: "omit"});
      const health = await response.json();
      state.profile = health.profile === "test" ? "test" : "personal";
      $("profile").textContent = state.profile === "test" ? "测试环境" : "个人推荐";
      $("test-banner").hidden = state.profile !== "test";
      $("auth-command").textContent = `scholar-research recommendations${state.profile === "test" ? " --profile test" : ""} open`;
    } catch (_) {
      $("profile").textContent = "连接中断";
    }
    if (!token) {
      $("auth-error").hidden = false;
      $("feed").setAttribute("aria-busy", "false");
      $("result-count").textContent = "等待打开凭证";
      $("refresh").disabled = true;
      return;
    }
    restoreFilters();
    await load();
  }
  initialize();
})();
