"use strict";

(() => {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  let token = fragment.get("token") || "";
  // Old fragment links remain readable; new pages initialize their own session.
  try { sessionStorage.removeItem("scholar-recommendations-session"); } catch (_) { /* Optional storage. */ }
  if (window.location.hash) {
    window.history.replaceState(window.history.state || {}, "", window.location.pathname + window.location.search);
  }

  const $ = (id) => document.getElementById(id);
  const kindNames = {paper: "论文", project: "项目主页", blog: "博客"};
  const decisionNames = {unread: "未处理", saved: "稍后看", selected: "已选入库", ignored: "已忽略"};
  const state = {profile: "personal", query: "", kind: "", tag: "", producer_id: "",
    since: "", decision: "", sort: "agent", offset: 0, limit: 20, total: 0, draftScope: null};
  let sequence = 0;
  let searchTimer;
  let detailCandidate = null;
  let detailFocus = null;
  let feedCandidates = [];
  let readerQueue = [];
  let readerOffset = 0;
  let readerTotal = 0;
  let readerBusy = false;
  let listScroll = 0;
  const evaluationDrafts = new Map();
  const evaluationPending = new Set();

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

  function notify(text, error = false, undo = null) {
    $("notice").textContent = text;
    $("notice").classList.toggle("error", error);
    $("notice").hidden = !text;
    const detailNotice = $("detail-notice");
    if (detailNotice) {
      detailNotice.textContent = text;
      detailNotice.classList.toggle("error", error);
      detailNotice.hidden = !text;
    }
    if (undo) for (const notice of [$("notice"), detailNotice].filter(Boolean)) {
      const button = element("button", "text-button notice-undo", "撤销");
      button.type = "button";
      button.addEventListener("click", async () => { button.disabled = true; await undo(); });
      notice.append(button);
    }
  }

  function persistEvaluationDrafts() {
    if (!state.draftScope) return;
    try {
      sessionStorage.setItem(`scholar-evaluation-drafts:${state.draftScope}`,
        JSON.stringify(Object.fromEntries(evaluationDrafts)));
    } catch (_) { /* The current editor remains usable when tab storage is unavailable. */ }
  }

  function restoreEvaluationDrafts() {
    if (!state.draftScope) return;
    try {
      const values = JSON.parse(sessionStorage.getItem(`scholar-evaluation-drafts:${state.draftScope}`) || "{}");
      for (const [id, value] of Object.entries(values)) {
        if (/^candidate-[0-9a-f]{64}$/.test(id) && value && typeof value.comment === "string"
          && value.comment.length <= 4000 && Number.isInteger(value.revision) && value.revision >= 0
          && Number.isInteger(value.candidateRevision) && value.candidateRevision > 0
          && (value.score === null || Number.isInteger(value.score) && value.score >= 1 && value.score <= 5)) {
          evaluationDrafts.set(id, value);
        }
      }
    } catch (_) { /* Invalid optional drafts never change saved evaluations. */ }
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

  function renderActiveFilters() {
    const container = $("active-filters");
    if (!container) return;
    const labels = {kind: "类型", tag: "领域", producer_id: "任务", since: "日期"};
    const entries = Object.keys(labels).filter(key => state[key]);
    container.replaceChildren();
    for (const key of entries) {
      const select = $(key);
      const option = Array.from(select?.options || []).find(item => item.value === state[key]);
      const text = option?.textContent || state[key];
      const button = element("button", "filter-chip", `${labels[key]}：${text} ×`);
      button.type = "button";
      button.setAttribute("aria-label", `移除${labels[key]}筛选：${text}`);
      button.addEventListener("click", () => {
        state[key] = ""; select.value = ""; state.offset = 0; load();
      });
      container.append(button);
    }
    container.hidden = entries.length === 0;
    if ($("filter-summary")) $("filter-summary").textContent = entries.length ? `筛选 · ${entries.length}` : "筛选";
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

  function metricIdentity(metric) {
    return JSON.stringify([metric.platform, metric.metric, metric.url]);
  }

  function metricName(metric) {
    if (metric.platform === "github" && metric.metric === "stars") return "GitHub stars";
    if (metric.platform === "huggingface" && metric.metric === "likes") return "Hugging Face 点赞（likes）";
    return `${metric.platform} ${metric.metric}`;
  }

  function metricTime(value, label) {
    const time = element("time", null, `${label} ${displayDate(value)}`);
    time.title = value || "";
    if (value) time.dateTime = value;
    return time;
  }

  function metricSection(candidate) {
    const section = element("section", "metrics metrics-compact");
    section.setAttribute("aria-label", "平台热度");
    const heading = element("div", "metrics-heading");
    heading.append(element("span", "metrics-label", "平台热度"));
    const targets = candidate.metric_targets || [];
    const refresh = element("button", "text-button metric-refresh", "更新热度");
    refresh.type = "button";
    refresh.disabled = !targets.length;
    refresh.hidden = !targets.length;
    if (!targets.length) refresh.title = "尚无已核验的平台链接";
    refresh.addEventListener("click", async () => {
      refresh.disabled = true;
      refresh.textContent = "更新中…";
      try {
        await updateCandidate(candidate, "/api/metrics", {});
      } finally {
        refresh.disabled = !targets.length;
        refresh.textContent = "更新热度";
      }
    });
    heading.append(refresh);
    section.append(heading);

    const checks = new Map();
    for (const check of candidate.metric_refresh?.checks || []) {
      const key = metricIdentity(check);
      const previous = checks.get(key);
      if (!previous || new Date(check.checked_at).getTime() >= new Date(previous.checked_at).getTime()) {
        checks.set(key, check);
      }
    }
    const observations = latestMetrics(candidate.metrics);
    const overview = element("div", "metric-overview");
    const available = observations.filter(item => typeof item.value === "number" && Number.isFinite(item.value));
    if (available.length) for (const metric of available) {
      overview.append(element("span", null, `${metricName(metric)} ${metric.value}`));
    }
    else {
      section.className += " metrics-empty";
      overview.append(element("span", "quiet", "热度待补齐"));
    }
    heading.append(overview);
    const observed = new Set(observations.map(metricIdentity));
    const values = element("div", "metrics-values");
    for (const metric of [...observations, ...targets.filter(target => !observed.has(metricIdentity(target)))]) {
      const entry = element("div", "metric");
      const anchor = externalLink(metricName(metric), metric.url);
      entry.append(anchor || element("span", null, metricName(metric)));
      const hasValue = typeof metric.value === "number" && Number.isFinite(metric.value);
      entry.append(element("span", hasValue ? "metric-value" : "metric-uncollected", hasValue ? metric.value : "未采集"));
      if (hasValue) entry.append(metricTime(metric.observed_at, "采集于"));
      if (metric.period) entry.append(element("span", null, metric.period));
      const check = checks.get(metricIdentity(metric));
      if (check && check.status !== "ok" && (!hasValue || new Date(check.checked_at) >= new Date(metric.observed_at))) {
        const status = check.status === "rate_limited" ? "平台限流" : "暂时无法采集";
        entry.append(element("span", "metric-status", `${status}${hasValue ? "，保留上次数据" : ""}`));
        entry.append(metricTime(check.checked_at, "检查于"));
      }
      values.append(entry);
    }
    if (!values.childElementCount) values.append(element("span", "metric-uncollected", "未采集"));
    const detail = element("details", "metric-details");
    detail.append(element("summary", null, "采集信息"), values);
    if (!targets.length) detail.append(element("p", "metric-hint", "尚无已核验 GitHub/HF 链接"));
    section.append(detail);
    return section;
  }

  async function updateCandidate(candidate, path, extra, {offerUndo = true} = {}) {
    notify("");
    try {
      const updated = await api(path, {candidate_id: candidate.candidate_id,
        expected_revision: candidate.revision, ...extra});
      if (detailCandidate?.candidate_id === candidate.candidate_id && updated.candidate_id) {
        detailCandidate = updated;
      }
      if (updated.candidate_id) readerQueue = readerQueue.map(row => row.candidate_id === updated.candidate_id ? updated : row);
      await load();
      if (path === "/api/decisions" && offerUndo && updated.decision !== candidate.decision) {
        notify(`已${{saved: "加入稍后看", ignored: "忽略", selected: "选择入库", unread: "恢复未处理"}[updated.decision] || "更新选择"}`, false, async () => {
          const restored = await updateCandidate(updated, "/api/decisions", {decision: candidate.decision}, {offerUndo: false});
          if (restored) notify("已撤销本次选择。");
        });
      }
      return updated;
    } catch (error) {
      notify(path === "/api/metrics" && ![2, 5].includes(error.code) && error.httpStatus !== 401
        ? "热度更新尚未完成，请稍后重试。" : readableError(error), true);
      await load();
      return null;
    }
  }

  function evaluationLabel(evaluation) {
    if (evaluation?.score) return `${"★".repeat(evaluation.score)}${"☆".repeat(5 - evaluation.score)} ${evaluation.score}/5`;
    return evaluation?.comment ? "已评价" : "未评价";
  }

  function evaluationSection(candidate) {
    const stored = candidate.evaluation || {score: null, comment: "", revision: 0};
    const draft = evaluationDrafts.get(candidate.candidate_id) || {
      score: stored.score, comment: stored.comment, revision: stored.revision, candidateRevision: candidate.revision};
    const section = element("details", "evaluation");
    section.open = evaluationDrafts.has(candidate.candidate_id);
    section.append(element("summary", null, `我的评价 · ${evaluationLabel(stored)}`));
    if (stored.matches_current_content === false && (stored.score || stored.comment)) {
      section.append(element("p", "evaluation-changed", "评价后资料已更新，请结合当前内容查看。"));
    }
    const form = element("div", "evaluation-form");
    const scores = element("div", "evaluation-scores");
    scores.setAttribute("role", "group");
    scores.setAttribute("aria-label", "个人评分");
    const scoreButtons = [];
    const remember = () => { evaluationDrafts.set(candidate.candidate_id, draft); persistEvaluationDrafts(); };
    for (const score of [null, 1, 2, 3, 4, 5]) {
      const button = element("button", "evaluation-score", score === null ? "不评分" : `${score} 分`);
      button.type = "button";
      button.setAttribute("aria-pressed", String(draft.score === score));
      button.addEventListener("click", () => {
        draft.score = score; remember();
        for (const [index, item] of scoreButtons.entries()) {
          item.setAttribute("aria-pressed", String(draft.score === (index || null)));
        }
        feedback.textContent = "尚未保存";
      });
      scores.append(button); scoreButtons.push(button);
    }
    const label = element("label", "field-label", "评价备注（选填）");
    const comment = element("textarea", "evaluation-comment");
    comment.rows = 3;
    comment.maxLength = 4000;
    comment.value = draft.comment;
    comment.placeholder = "写下你的判断、用途或保留意见";
    comment.addEventListener("input", () => {
      draft.comment = comment.value; remember(); feedback.textContent = "尚未保存";
    });
    label.append(comment);
    const actions = element("div", "evaluation-actions");
    const save = element("button", "secondary evaluation-save", "保存评价");
    const clear = element("button", "text-button evaluation-clear", "清除评价");
    const restore = element("button", "text-button evaluation-restore", "放弃草稿，载入已保存评价");
    restore.hidden = true;
    for (const button of [save, clear, restore]) button.type = "button";
    const feedback = element("span", "evaluation-feedback");
    feedback.setAttribute("role", "status");
    const controls = [...scoreButtons, comment, save, clear, restore];
    const setBusy = (busy) => { for (const control of controls) control.disabled = busy; };
    setBusy(evaluationPending.has(candidate.candidate_id));
    const persist = async (remove) => {
      if (evaluationPending.has(candidate.candidate_id)) return;
      remember(); evaluationPending.add(candidate.candidate_id); setBusy(true);
      feedback.textContent = "保存中…";
      try {
        const updated = await api("/api/evaluations", {candidate_id: candidate.candidate_id,
          expected_candidate_revision: draft.candidateRevision,
          expected_revision: draft.revision, score: remove ? null : draft.score,
          comment: remove ? "" : draft.comment});
        evaluationDrafts.delete(candidate.candidate_id);
        persistEvaluationDrafts();
        if (detailCandidate?.candidate_id === candidate.candidate_id) detailCandidate = updated;
        evaluationPending.delete(candidate.candidate_id);
        await load();
        notify(remove ? "评价已清除。" : "评价已保存。");
      } catch (error) {
        feedback.textContent = error.code === 5
          ? "资料或评价已更新，草稿已保留。可放弃草稿后载入最新内容。"
          : "评价未保存，草稿已保留，请稍后重试。";
        restore.hidden = error.code !== 5;
      } finally {
        evaluationPending.delete(candidate.candidate_id); setBusy(false);
      }
    };
    save.addEventListener("click", () => persist(false));
    clear.addEventListener("click", () => persist(true));
    restore.addEventListener("click", async () => {
      evaluationDrafts.delete(candidate.candidate_id); persistEvaluationDrafts(); await load();
    });
    actions.append(save, clear, restore, feedback);
    form.append(scores, label, actions); section.append(form);
    return section;
  }

  function detailedCard(candidate) {
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

    const isPaper = resource.kind === "paper";
    const sources = Array.isArray(resource.summary_sources) ? resource.summary_sources : [];
    const hasAbstract = isPaper && Boolean(resource.abstract_original);
    const hasDescription = !isPaper && Boolean(resource.description_zh || resource.description_original);
    const hasSummary = !hasAbstract && Boolean(resource.summary_zh && sources.length);
    const readingKind = candidate.reading_kind || (hasAbstract ? "abstract"
      : hasSummary ? "summary" : hasDescription ? "description" : "unavailable");
    const summaryActive = readingKind === "summary" && hasSummary;
    const reviewRequired = typeof candidate.review_required === "boolean" ? candidate.review_required : isPaper || summaryActive;
    const reviewAvailable = typeof candidate.review_available === "boolean" ? candidate.review_available
      : Boolean((readingKind === "abstract" && resource.abstract_original && resource.abstract_zh) || summaryActive);
    const translated = isPaper ? resource.abstract_zh : resource.description_zh;
    const original = isPaper ? resource.abstract_original : resource.description_original;
    const label = isPaper ? "摘要译文" : "原文简介译文";
    if (summaryActive) {
      article.append(element("div", "summary-label", "资料总结（agent整理，非原文摘要）"));
      article.append(element("p", "summary", resource.summary_zh));
      const references = element("nav", "summary-sources");
      references.setAttribute("aria-label", "总结依据");
      references.append(element("span", null, "总结依据"));
      for (const [index, url] of sources.entries()) {
        const link = externalLink(`来源 ${index + 1} ↗`, url);
        if (link) references.append(link);
      }
      article.append(references);
    } else if (translated) {
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
    if (original && (translated || isPaper || summaryActive)) {
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
    if (tags.childElementCount) article.append(tags);
    if (candidate.ranking_reason) {
      const ranking = element("details", "recommendation-requirement");
      ranking.append(element("summary", null, "本次排序理由"), element("p", "requirement-snapshot", candidate.ranking_reason));
      article.append(ranking);
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
      if (record.recommendation_reason) {
        row.append(element("p", "requirement-snapshot", `推荐理由：${record.recommendation_reason}`));
      }
      if (record.requirement && typeof record.requirement.content === "string") {
        const requirement = element("details", "recommendation-requirement");
        requirement.append(element("summary", null, `当时的推荐要求：${record.requirement.title || "未命名"} · 第 ${record.requirement.revision} 版`),
          element("p", "requirement-snapshot", record.requirement.content));
        row.append(requirement);
      }
      recordList.append(row);
    }
    recommendations.append(recordList);
    article.append(recommendations);
    article.append(metricSection(candidate));
    article.append(evaluationSection(candidate));

    if (reviewRequired) {
      const review = element("label", "review");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(candidate.abstract_reviewed);
      checkbox.disabled = Boolean(candidate.abstract_reviewed) || !reviewAvailable;
      checkbox.addEventListener("change", () => {
        checkbox.disabled = true;
        updateCandidate(candidate, "/api/reviews", {});
      });
      review.append(checkbox, element("span", null, candidate.abstract_reviewed
        ? (summaryActive ? "这份资料总结已确认审阅" : "这份摘要译文已确认审阅")
        : (summaryActive ? "我已阅读这份资料总结" : "我已阅读这份摘要译文")));
      article.append(review);
      if (candidate.abstract_reviewed) {
        const withdrawal = element("div", "action-group");
        const revoke = element("button", "text-button review-revoke", "撤销审阅");
        revoke.type = "button";
        revoke.disabled = candidate.ingestion?.status === "in_progress";
        revoke.addEventListener("click", () => {
          revoke.disabled = true;
          updateCandidate(candidate, "/api/reviews/revoke", {});
        });
        withdrawal.append(revoke, element("span", "muted", revoke.disabled
          ? "正在入库，完成后才能撤销审阅。"
          : "撤销会取消待入库选择，已入库书目保留。"));
        article.append(withdrawal);
      }
    }

    const actions = element("div", "card-actions");
    const selection = element("label", "select-label");
    const selected = element("input", "select-input");
    selected.type = "checkbox";
    selected.checked = candidate.decision === "selected";
    selected.disabled = reviewRequired && !candidate.abstract_reviewed && candidate.decision !== "selected";
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
    const evaluate = element("button", "text-button evaluation-open", "评价");
    evaluate.type = "button";
    evaluate.addEventListener("click", () => {
      const section = article.querySelector(".evaluation");
      section.open = true;
      section.scrollIntoView?.({block: "center", behavior: "smooth"});
      section.querySelector(".evaluation-comment")?.focus?.({preventScroll: true});
    });
    actions.append(evaluate);
    article.append(actions);
    if (candidate.decision && candidate.decision !== "unread") {
      const completed = candidate.ingestion?.status === "completed";
      const changed = candidate.ingestion?.matches_current_content === false;
      article.append(element("div", "decision-note", `${decisionNames[candidate.decision] || ""} · ${changed
        ? "旧内容已有入库记录，当前内容已更新" : completed
          ? (state.profile === "test" ? "模拟书目入库完成" : "Zotero 书目已入库") : "尚未完成入库"}`));
    }
    if (typeof window.ScholarRecommendationWorkspace?.decorateCard === "function") {
      window.ScholarRecommendationWorkspace.decorateCard(article, candidate);
    }
    return article;
  }

  function cardFor(id) {
    return Array.from($("feed").children).find(node => node.dataset.candidateId === id);
  }

  function readerHistory(id, replace = false) {
    const saved = {...(window.history.state || {}), scholarRecommendationPage: "recommendations"};
    if (id) {
      saved.scholarRecommendationDetail = id;
      saved.scholarRecommendationOffset = state.offset;
    }
    else delete saved.scholarRecommendationDetail;
    const method = replace ? "replaceState" : "pushState";
    window.history[method]?.(saved, "", window.location.pathname + window.location.search);
  }

  function closeDetail({history = true} = {}) {
    if (!$("detail-overlay")) return;
    const id = detailCandidate?.candidate_id;
    const wasOpen = !$("detail-overlay").hidden;
    $("detail-overlay").hidden = true;
    $("detail-content").replaceChildren();
    detailCandidate = null;
    document.body.classList.toggle("reader-open", false);
    for (const name of ["recommendations-view", "settings-view", "app-header"]) if ($(name)) $(name).inert = false;
    if (wasOpen) {
      const anchor = cardFor(id)?.querySelector(".entry-title") || detailFocus || $("refresh");
      anchor?.focus?.({preventScroll: true});
      window.scrollTo?.({top: listScroll});
    }
    if (history && window.history.state?.scholarRecommendationDetail) window.history.back?.();
  }

  function readerControls() {
    if (!detailCandidate) return;
    const index = readerQueue.findIndex(row => row.candidate_id === detailCandidate.candidate_id);
    if ($("detail-position")) $("detail-position").textContent = `第 ${readerOffset + Math.max(0, index) + 1} / ${readerTotal} 条`;
    if ($("detail-previous")) $("detail-previous").disabled = readerBusy || index <= 0 && readerOffset === 0;
    if ($("detail-next")) $("detail-next").disabled = readerBusy || index >= readerQueue.length - 1 && readerOffset + readerQueue.length >= readerTotal;
  }

  function renderDetail({preserve = true} = {}) {
    if (!detailCandidate || !$("detail-content")) return;
    const container = $("detail-content"), panel = $("detail-panel");
    const scroll = preserve ? panel?.scrollTop || 0 : 0;
    const folds = preserve ? Array.from(container.querySelectorAll("details")).map(node => node.open) : [];
    const active = document.activeElement;
    const focused = preserve && container.contains?.(active) ? active.dataset?.readerFocus : null;
    const selection = focused && typeof active.selectionStart === "number" ? [active.selectionStart, active.selectionEnd] : null;
    container.replaceChildren(detailedCard(detailCandidate));
    Array.from(container.querySelectorAll("details")).forEach((node, index) => {
      if (preserve && index < folds.length) node.open = folds[index];
    });
    for (const node of container.querySelectorAll("button, a, input, textarea, summary, select")) {
      node.dataset.readerFocus = `${node.tagName}:${node.id || node.className}:${node.type || ""}:${node.textContent.slice(0, 70)}`;
      if (focused && node.dataset.readerFocus === focused) {
        node.focus?.({preventScroll: true});
        if (selection && node.setSelectionRange) node.setSelectionRange(...selection);
      }
    }
    if (panel) panel.scrollTop = scroll;
    readerControls();
  }

  function openDetail(candidate, {recordHistory = true, navigation = false} = {}) {
    if (!$("detail-overlay")) return;
    const alreadyOpen = Boolean(detailCandidate);
    if (!alreadyOpen) {
      readerQueue = [...feedCandidates]; readerOffset = state.offset; readerTotal = state.total;
      detailFocus = document.activeElement; listScroll = window.scrollY || 0;
    }
    detailCandidate = candidate;
    $("detail-notice").hidden = true;
    $("detail-overlay").hidden = false;
    document.body.classList.toggle("reader-open", true);
    for (const name of ["recommendations-view", "settings-view", "app-header"]) if ($(name)) $(name).inert = true;
    renderDetail({preserve: false});
    if (recordHistory) readerHistory(candidate.candidate_id, alreadyOpen);
    if (!navigation) $("detail-close").focus?.({preventScroll: true});
  }

  async function navigateDetail(direction) {
    if (!detailCandidate || readerBusy) return;
    const index = readerQueue.findIndex(row => row.candidate_id === detailCandidate.candidate_id);
    const next = readerQueue[index + direction];
    if (next) { openDetail(next, {navigation: true}); return; }
    const offset = readerOffset + direction * state.limit;
    if (offset < 0 || offset >= readerTotal) return;
    readerBusy = true; readerControls();
    const previousOffset = state.offset;
    state.offset = offset;
    try {
      if (await load() && detailCandidate && feedCandidates.length) {
        readerQueue = [...feedCandidates]; readerOffset = state.offset; readerTotal = state.total;
        openDetail(direction > 0 ? readerQueue[0] : readerQueue[readerQueue.length - 1], {navigation: true});
      } else if (detailCandidate) state.offset = previousOffset;
    } finally { readerBusy = false; readerControls(); }
  }

  function compactCard(candidate) {
    const resource = candidate.resource || {};
    const article = element("article", "compact-card");
    article.dataset.candidateId = candidate.candidate_id;
    const meta = element("div", "compact-meta");
    meta.append(element("span", "kind-label", kindNames[resource.kind] || "资料"),
      element("span", null, displayDate(resource.published_at)));
    if (resource.authors?.length) meta.append(element("span", "compact-authors",
      resource.authors.slice(0, 3).join(" · ") + (resource.authors.length > 3 ? ` 等 ${resource.authors.length} 人` : "")));
    article.append(meta);
    const heading = element("h2");
    const title = element("button", "entry-title", resource.title || "未提供标题");
    title.type = "button";
    title.addEventListener("click", () => openDetail(candidate));
    heading.append(title); article.append(heading);
    const tags = element("div", "compact-tags");
    for (const tag of (candidate.tags || []).slice(0, 3)) tags.append(element("span", "tag", tag));
    if ((candidate.tags || []).length > 3) tags.append(element("span", "quiet", `+${candidate.tags.length - 3}`));
    const introduction = resource.abstract_zh || resource.summary_zh || resource.description_zh || resource.description_original || "";
    if (introduction) {
      const characters = Array.from(introduction.replace(/\s+/g, " "));
      article.append(element("p", "compact-introduction", characters.slice(0, 170).join("") + (characters.length > 170 ? "…" : "")));
    } else article.append(element("p", "compact-introduction muted", "简介待补齐，可展开查看原文和来源。"));
    if (tags.childElementCount) article.append(tags);
    const bottom = element("div", "compact-bottom");
    const observations = latestMetrics(candidate.metrics).filter(item => typeof item.value === "number" && Number.isFinite(item.value));
    const heat = element("div", "compact-metrics");
    if (observations.length) for (const metric of observations) {
      const value = element("span", "compact-metric", `${metricName(metric)} ${metric.value}`);
      value.title = `采集于 ${metric.observed_at || "未提供"}`;
      heat.append(value);
    } else heat.append(element("span", "quiet", "热度待补齐"));
    bottom.append(heat);
    const details = element("button", "text-button entry-details", "查看详情");
    details.type = "button";
    details.addEventListener("click", () => openDetail(candidate));
    const actions = element("div", "compact-actions");
    const original = externalLink("原文 ↗", resource.url, "entry-original");
    if (original) actions.append(original);
    const saved = element("button", "text-button entry-save", candidate.decision === "saved" ? "已稍后看" : "稍后看");
    saved.type = "button";
    saved.setAttribute("aria-pressed", String(candidate.decision === "saved"));
    saved.disabled = candidate.ingestion?.status === "in_progress";
    if (saved.disabled) saved.title = "正在入库，完成后可以修改选择";
    saved.addEventListener("click", async () => {
      saved.disabled = true;
      await updateCandidate(candidate, "/api/decisions", {decision: candidate.decision === "saved" ? "unread" : "saved"});
    });
    const more = element("details", "entry-more");
    more.append(element("summary", null, "更多"));
    const ignore = element("button", "text-button entry-ignore", candidate.decision === "ignored" ? "恢复未处理" : "忽略");
    ignore.type = "button";
    ignore.disabled = candidate.ingestion?.status === "in_progress";
    ignore.addEventListener("click", async () => {
      ignore.disabled = true;
      await updateCandidate(candidate, "/api/decisions", {decision: candidate.decision === "ignored" ? "unread" : "ignored"});
    });
    more.append(ignore);
    actions.append(saved, details, more);
    bottom.append(actions); article.append(bottom);
    const provenance = element("div", "compact-provenance");
    const names = new Set();
    for (const record of candidate.recommendations || []) for (const source of record.channels || []) if (source.name) names.add(source.name);
    if (!names.size) for (const producer of candidate.producers || []) if (producer.name) names.add(producer.name);
    const labels = Array.from(names);
    if (labels.length) provenance.append(element("span", "compact-source", `来源：${labels.slice(0, 2).join("、")}${labels.length > 2 ? ` 等 ${labels.length} 个` : ""}`));
    const receipt = candidate.ingestion;
    const status = receipt?.matches_current_content === false ? "旧内容有入库记录"
      : receipt?.status === "completed" ? (state.profile === "test" ? "模拟书目入库完成" : "书目已入库")
        : decisionNames[candidate.decision] || "未处理";
    provenance.append(element("span", "compact-state", status));
    if (candidate.evaluation?.score || candidate.evaluation?.comment) {
      const evaluation = element("span", "compact-evaluation", `我的评价 ${evaluationLabel(candidate.evaluation)}`);
      if (candidate.evaluation.matches_current_content === false) evaluation.title = "评价后资料已更新";
      provenance.append(evaluation);
    }
    article.append(provenance);
    article.addEventListener("click", event => {
      if (event.target?.closest?.("button, a, input, select, label, summary, details")) return;
      openDetail(candidate);
    });
    return article;
  }

  async function load() {
    const current = ++sequence;
    const active = document.activeElement;
    const focusedCard = active?.closest?.(".compact-card");
    const focusedClass = focusedCard ? active.className.split(" ").find(name => name.startsWith("entry-")) : null;
    const focusedId = focusedCard?.dataset.candidateId;
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
      feedCandidates = result.items || [];
      const currentById = new Map(feedCandidates.map(row => [row.candidate_id, row]));
      readerQueue = readerQueue.map(row => currentById.get(row.candidate_id) || row);
      const rankingStatus = $("ranking-status");
      if (rankingStatus) rankingStatus.textContent = state.sort !== "agent" ? "" : {
        current: "按外部 agent 的推荐顺序显示",
        stale: "排序依据已有更新，暂按发布日期显示",
        empty: "尚无外部 agent 排序，暂按发布日期显示"
      }[result.ranking?.status || "empty"];
      $("feed").replaceChildren(...(result.items || []).map(compactCard));
      if (detailCandidate) {
        const fresh = (result.items || []).find(item => item.candidate_id === detailCandidate.candidate_id);
        if (fresh) detailCandidate = fresh;
        renderDetail();
      }
      $("empty").hidden = Boolean(result.items?.length);
      const filtered = Boolean(state.query || state.kind || state.tag || state.producer_id || state.since || state.decision);
      $("empty-title").textContent = filtered ? "没有符合条件的推荐" : "等待第一批推荐";
      $("empty-description").textContent = filtered ? "可以调整筛选条件，或刷新列表查看最新提交。"
        : "来源与专项 agent 提交的内容会汇集到这里。";
      $("empty-command").hidden = true;
      $("empty-command").textContent = `scholar-research recommendations${state.profile === "test" ? " --profile test" : ""} schema\nscholar-research recommendations${state.profile === "test" ? " --profile test" : ""} submit --input recommendations.json`;
      $("result-count").textContent = `${state.total} 项`;
      $("selected-count").textContent = String(selected.total || 0);
      $("export").disabled = !selected.total;
      $("previous").disabled = state.offset === 0;
      $("next").disabled = state.offset + state.limit >= state.total;
      $("page-number").textContent = state.total ? `${Math.floor(state.offset / state.limit) + 1} / ${Math.ceil(state.total / state.limit)}` : "";
      updateFacet("tag", result.facets?.tags, "全部领域");
      updateFacet("producer_id", result.facets?.producers, "全部任务", "producer_id", "name");
      renderActiveFilters();
      saveFilters();
      if (!detailCandidate && focusedId && focusedClass) cardFor(focusedId)?.querySelector(`.${focusedClass}`)?.focus?.({preventScroll: true});
      return true;
    } catch (error) {
      if (current !== sequence) return;
      if (error.httpStatus === 401) {
        try { sessionStorage.removeItem("scholar-recommendations-session"); } catch (_) { /* No persistent credential is required. */ }
        $("auth-error").hidden = false;
        $("empty").hidden = true;
      }
      notify(readableError(error), true);
      return false;
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
  $("export").addEventListener("click", () => {
    state.decision = "selected";
    state.offset = 0;
    syncDecisionTabs();
    load();
  });
  $("detail-close")?.addEventListener("click", closeDetail);
  $("detail-previous")?.addEventListener("click", () => navigateDetail(-1));
  $("detail-next")?.addEventListener("click", () => navigateDetail(1));
  $("detail-overlay")?.addEventListener("click", event => { if (event.target === $("detail-overlay")) closeDetail(); });
  document.addEventListener?.("keydown", event => {
    if ($("detail-overlay")?.hidden || $("ingestion-overlay")?.hidden === false) return;
    if (event.key === "Escape") { event.preventDefault(); closeDetail(); return; }
    if (event.key === "Tab") {
      const panel = $("detail-panel");
      const controls = Array.from(panel?.querySelectorAll("button, a, input, textarea, summary, select") || [])
        .filter(node => !node.disabled && !node.closest?.("[hidden]") && node.getClientRects?.().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || event.target?.closest?.("input, textarea, select, [contenteditable=true]")) return;
    if (event.key === "j" || event.key === "k") { event.preventDefault(); navigateDetail(event.key === "j" ? 1 : -1); }
  });
  let readerRestoreSequence = 0;
  window.addEventListener?.("popstate", async event => {
    const restoreSequence = ++readerRestoreSequence;
    const id = event.state?.scholarRecommendationDetail;
    if (!/^candidate-[0-9a-f]{64}$/.test(id || "")) { closeDetail({history: false}); return; }
    const offset = event.state?.scholarRecommendationOffset;
    if (Number.isInteger(offset) && offset >= 0 && offset <= 1000000 && offset !== state.offset) {
      state.offset = offset; await load();
    }
    const activeHistory = window.history.state || {};
    if (restoreSequence !== readerRestoreSequence || activeHistory.scholarRecommendationPage !== "recommendations"
        || activeHistory.scholarRecommendationDetail !== id || activeHistory.scholarRecommendationOffset !== offset) return;
    const candidate = feedCandidates.find(row => row.candidate_id === id);
    if (candidate) openDetail(candidate, {recordHistory: false});
    else closeDetail({history: false});
  });

  async function initialize() {
    try {
      const response = await fetch("/health", {cache: "no-store", credentials: "omit"});
      const health = await response.json();
      state.profile = health.profile === "test" ? "test" : "personal";
      if (/^pool-[0-9a-f]{32}$/.test(health.pool_id || "")) state.draftScope = `${state.profile}:${health.pool_id}`;
      $("profile").textContent = state.profile === "test" ? "测试环境" : "个人推荐";
      $("test-banner").hidden = state.profile !== "test";
      $("auth-command").textContent = `scholar-research recommendations${state.profile === "test" ? " --profile test" : ""} open`;
    } catch (_) {
      $("profile").textContent = "连接中断";
    }
    try {
      const response = await fetch("/api/session", {method: "POST", credentials: "omit", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-Scholar-Client": "recommendation-page"}, body: "{}"});
      const session = await response.json();
      if (!response.ok || !/^[A-Za-z0-9_-]{32,256}$/.test(session.token || "")) throw new Error("Session unavailable");
      token = session.token;
      $("auth-error").hidden = true;
    } catch (_) {
      $("auth-error").hidden = false;
      $("feed").setAttribute("aria-busy", "false");
      $("result-count").textContent = "本机会话连接失败";
      return;
    }
    restoreFilters();
    restoreEvaluationDrafts();
    const previousOffset = window.history.state?.scholarRecommendationOffset;
    if (window.history.state?.scholarRecommendationDetail && Number.isInteger(previousOffset)
      && previousOffset >= 0 && previousOffset <= 1000000) state.offset = previousOffset;
    await load();
    const previousId = window.history.state?.scholarRecommendationDetail;
    const previous = feedCandidates.find(row => row.candidate_id === previousId);
    if (previous) openDetail(previous, {recordHistory: false});
  }
  window.ScholarRecommendations = {api, element, externalLink, notify, reload: load,
    getProfile: () => state.profile, getDraftScope: () => state.draftScope, closeDetail};
  window.ScholarRecommendations.ready = initialize();
})();
