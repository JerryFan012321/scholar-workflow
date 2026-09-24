"use strict";

const state = {
  directory: null,
  view: "papers",
  libraryItems: [],
  libraryNextCursor: null,
  libraryLoading: false,
  libraryRequestId: 0,
  librarySort: "title",
  libraryDirection: "asc",
  libraryItemType: "",
  query: "",
  actions: {},
  csrfToken: null,
  destinations: {
    items: [],
    selectedId: null,
    capabilityError: "正在读取 cmux 打开位置",
  },
  tasks: {
    actions: [],
    targets: [],
    selectedActionId: null,
    selectedTargetId: null,
    selectedEffort: null,
    capabilityError: null,
    loading: true,
    submitting: false,
    statusMessage: null,
    statusKind: "",
    activeRunId: null,
    activeDestinationName: null,
    pollTimer: null,
  },
  selectedField: null,
  artifacts: [],
  fieldRegistration: {
    preview: null,
    busy: false,
    selectedFieldId: null,
  },
  preview: {
    artifact: null,
    content: null,
    revision: null,
    mode: "read",
    dirty: false,
    saving: false,
    assets: [],
    assetsLoading: false,
    uploading: false,
    requestId: 0,
  },
  projectOps: {
    project: null,
    submitting: false,
  },
};
const byId = (id) => document.getElementById(id);
let previewRenderFrame = null;
let taskFallbackSequence = 0;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function hubInstance() {
  return new URLSearchParams(window.location.search).get("instance");
}

function directoryEndpoint() {
  return "/api/v3/directory";
}

function destinationsEndpoint() {
  const instance = hubInstance();
  if (instance === null) return "/api/v3/destinations";
  return `/api/v3/destinations?${new URLSearchParams({ instance }).toString()}`;
}

function stateChangingHeaders(contentType = "application/json") {
  const headers = {
    "Content-Type": contentType,
    "X-Scholar-Hub-Token": state.csrfToken,
  };
  const instance = hubInstance();
  if (instance) headers["X-Scholar-Hub-Instance"] = instance;
  return headers;
}

function artifactLabel(kind) {
  const labels = {
    "collection-index": "文献集合",
    "paper-list": "论文列表",
    "paper-hub": "论文主页",
    "literature-tree": "文献树",
    "paper-analysis": "论文解析",
    "analysis-canvas": "解析树图",
    "annotation-note": "批注",
    "reading-note": "阅读笔记",
    "direction-note": "研究方向笔记",
    "technical-document": "技术文档",
  };
  return labels[kind] || kind.replaceAll("-", " ");
}

function resourceKindLabel(kind) {
  const labels = {
    paper: "论文",
    technical_document: "技术文档",
    snapshot: "网页快照",
    drawio: "图表",
    image: "图片",
    dataset: "数据集",
  };
  return labels[kind] || kind;
}

function withoutFrontmatter(markdown) {
  const normalized = String(markdown || "").replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  if (lines[0].trim() !== "---") return normalized;
  for (let index = 1; index < lines.length; index += 1) {
    if (["---", "..."].includes(lines[index].trim())) {
      return lines.slice(index + 1).join("\n").replace(/^\n+/, "");
    }
  }
  return normalized;
}

function readableWikiToken(raw, embedded) {
  const parts = raw.split("|");
  const target = parts.shift().trim();
  const alias = parts.join("|").trim();
  const token = node("span", embedded ? "embed-token" : "wikilink");
  token.textContent = embedded ? `附件：${alias || target}` : (alias || target);
  token.title = target;
  return token;
}

function safeWebLink(url) {
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch (_error) {
    return null;
  }
}

function appendInlineMarkdown(parent, source) {
  const pattern = /(`([^`\n]+)`|!\[\[([^\]\n]+)\]\]|\[\[([^\]\n]+)\]\]|\[([^\]\n]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|(?<![\w_])_([^_\n]+)_(?![\w_]))/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    if (match.index > cursor) {
      parent.append(document.createTextNode(source.slice(cursor, match.index)));
    }
    if (match[2] !== undefined) {
      parent.append(node("code", "", match[2]));
    } else if (match[3] !== undefined) {
      parent.append(readableWikiToken(match[3], true));
    } else if (match[4] !== undefined) {
      parent.append(readableWikiToken(match[4], false));
    } else if (match[5] !== undefined) {
      const href = safeWebLink(match[6]);
      if (href) {
        const link = node("a", "", match[5]);
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        parent.append(link);
      } else {
        const token = node("span", "markdown-link-token", match[5]);
        token.title = match[6];
        parent.append(token);
      }
    } else if (match[7] !== undefined || match[8] !== undefined) {
      const strong = node("strong");
      appendInlineMarkdown(strong, match[7] ?? match[8]);
      parent.append(strong);
    } else {
      const emphasis = node("em");
      appendInlineMarkdown(emphasis, match[9] ?? match[10]);
      parent.append(emphasis);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < source.length) {
    parent.append(document.createTextNode(source.slice(cursor)));
  }
}

function hasTablePipe(row) {
  let escaped = false;
  let inCode = false;
  for (const character of row) {
    if (escaped) {
      escaped = false;
    } else if (character === "\\") {
      escaped = true;
    } else if (character === "`") {
      inCode = !inCode;
    } else if (character === "|" && !inCode) {
      return true;
    }
  }
  return false;
}

function splitTableRow(row) {
  let source = row.trim();
  if (source.startsWith("|")) source = source.slice(1);
  if (source.endsWith("|") && !source.endsWith("\\|")) source = source.slice(0, -1);
  const cells = [];
  let cell = "";
  let inCode = false;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === "\\" && source[index + 1] === "|") {
      cell += "|";
      index += 1;
    } else if (character === "`") {
      inCode = !inCode;
      cell += character;
    } else if (character === "|" && !inCode) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function tableDefinition(lines, index) {
  if (index + 1 >= lines.length || !hasTablePipe(lines[index])) return null;
  const headers = splitTableRow(lines[index]);
  const delimiters = splitTableRow(lines[index + 1]);
  if (headers.length !== delimiters.length || delimiters.length === 0) return null;
  if (!delimiters.every((cell) => /^:?-{3,}:?$/.test(cell))) return null;
  const alignments = delimiters.map((cell) => {
    if (cell.startsWith(":") && cell.endsWith(":")) return "center";
    if (cell.endsWith(":")) return "right";
    return "left";
  });
  return { headers, alignments };
}

function renderTable(parent, lines, index, definition) {
  const wrapper = node("div", "markdown-table-wrap");
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", "Markdown 表格");
  const table = node("table", "markdown-table");
  const head = node("thead");
  const headerRow = node("tr");
  definition.headers.forEach((value, column) => {
    const header = node("th", `align-${definition.alignments[column]}`);
    header.scope = "col";
    appendInlineMarkdown(header, value);
    headerRow.append(header);
  });
  head.append(headerRow);
  table.append(head);

  const body = node("tbody");
  let cursor = index + 2;
  while (cursor < lines.length && lines[cursor].trim() && hasTablePipe(lines[cursor])) {
    const values = splitTableRow(lines[cursor]);
    const row = node("tr");
    definition.headers.forEach((_header, column) => {
      const cell = node("td", `align-${definition.alignments[column]}`);
      appendInlineMarkdown(cell, values[column] || "");
      row.append(cell);
    });
    body.append(row);
    cursor += 1;
  }
  table.append(body);
  wrapper.append(table);
  parent.append(wrapper);
  return cursor;
}

function isBlockStart(line) {
  return /^\s*(#{1,6})\s+/.test(line)
    || /^\s*(`{3,}|~{3,})/.test(line)
    || /^\s*>/.test(line)
    || /^\s*[-*+]\s+/.test(line)
    || /^\s*\d+[.)]\s+/.test(line);
}

function renderMarkdownBlocks(parent, lines) {
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const table = tableDefinition(lines, index);
    if (table) {
      index = renderTable(parent, lines, index, table);
      continue;
    }

    const fence = line.match(/^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+.-]*)\s*$/);
    if (fence) {
      const marker = fence[1];
      const codeLines = [];
      const closeFence = new RegExp(`^\\s*${marker[0]}{${marker.length},}\\s*$`);
      index += 1;
      while (index < lines.length && !closeFence.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const pre = node("pre", "markdown-code");
      pre.dataset.language = fence[2];
      pre.append(node("code", "", codeLines.join("\n")));
      parent.append(pre);
      continue;
    }

    const heading = line.match(/^\s*(#{1,6})\s+(.+?)(?:\s+#+\s*)?$/);
    if (heading) {
      const title = node(`h${heading[1].length}`);
      appendInlineMarkdown(title, heading[2]);
      parent.append(title);
      index += 1;
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quoted = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) {
        quoted.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      const quote = node("blockquote");
      renderMarkdownBlocks(quote, quoted);
      parent.append(quote);
      continue;
    }

    const ordered = line.match(/^\s*(\d+)[.)]\s+(.+)$/);
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    if (ordered || unordered) {
      const list = node(ordered ? "ol" : "ul");
      if (ordered && Number(ordered[1]) !== 1) list.start = Number(ordered[1]);
      const itemPattern = ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
      while (index < lines.length) {
        const item = lines[index].match(itemPattern);
        if (!item) break;
        const listItem = node("li");
        appendInlineMarkdown(listItem, item[1]);
        list.append(listItem);
        index += 1;
      }
      parent.append(list);
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim()
        && !isBlockStart(lines[index]) && !tableDefinition(lines, index)) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    const paragraph = node("p");
    appendInlineMarkdown(paragraph, paragraphLines.join(" "));
    parent.append(paragraph);
  }
}

function renderReadable(target, artifact, content) {
  const fragment = document.createDocumentFragment();
  if (!artifact || artifact.format !== "markdown") {
    const pre = node("pre", "markdown-code");
    pre.append(node("code", "", String(content || "")));
    fragment.append(pre);
  } else {
    renderMarkdownBlocks(fragment, withoutFrontmatter(content).split("\n"));
  }
  if (!fragment.hasChildNodes()) fragment.append(node("p", "markdown-empty", "暂无正文"));
  target.replaceChildren(fragment);
}

function scheduleLivePreview(content) {
  if (previewRenderFrame !== null) window.cancelAnimationFrame(previewRenderFrame);
  previewRenderFrame = window.requestAnimationFrame(() => {
    renderReadable(byId("preview-live-content"), state.preview.artifact, content);
    previewRenderFrame = null;
  });
}

function documentLibraries() {
  const libraries = state.directory?.libraries || {};
  return ["papers", "fields"]
    .map((libraryId) => libraries[libraryId])
    .filter(Boolean);
}

function descriptorFor(view) {
  return documentLibraries().find((library) => library.library_id === view) || null;
}

function isDocumentLibrary(view = state.view) {
  return ["papers", "fields"].includes(view);
}

function renderLibraries() {
  const nav = byId("library-nav");
  nav.replaceChildren(...documentLibraries().map((library) => {
    const count = library.available ? library.total_count : "!";
    const button = node("button", "nav-item", `${library.label} · ${count}`);
    button.type = "button";
    button.dataset.view = library.library_id;
    button.title = library.detail || library.authority;
    button.classList.toggle("active", state.view === library.library_id);
    button.addEventListener("click", () => selectView(library.library_id));
    return button;
  }));
  byId("project-nav-count").textContent = String(state.directory?.projects?.length || 0);
  byId("tool-nav-count").textContent = String(state.directory?.tools?.length || 0);
  for (const button of document.querySelectorAll("[data-view]")) {
    button.classList.toggle("active", button.dataset.view === state.view);
  }
}

const LIBRARY_TYPE_OPTIONS = {
  papers: [
    ["", "全部类型"],
    ["Paper", "Paper"],
    ["Report", "Report"],
    ["Book", "Book"],
    ["Webpage", "Webpage"],
    ["Other", "Other"],
  ],
  fields: [["", "全部 Fields"]],
};

function syncLibraryQueryControls() {
  const controls = document.querySelector(".library-query-controls");
  controls.hidden = !isDocumentLibrary();
  if (!isDocumentLibrary()) return;
  const sort = byId("library-sort");
  const allowedSorts = state.view === "papers"
    ? [["title", "标题"], ["year", "年份"], ["id", "标识符"]]
    : [["title", "名称"], ["id", "标识符"]];
  if (!allowedSorts.some(([value]) => value === state.librarySort)) {
    state.librarySort = "title";
  }
  sort.replaceChildren(...allowedSorts.map(([value, label]) => {
    const option = node("option", "", label);
    option.value = value;
    return option;
  }));
  sort.value = state.librarySort;

  const type = byId("library-type");
  const typeOptions = LIBRARY_TYPE_OPTIONS[state.view] || [["", "全部类型"]];
  if (!typeOptions.some(([value]) => value === state.libraryItemType)) {
    state.libraryItemType = "";
  }
  type.replaceChildren(...typeOptions.map(([value, label]) => {
    const option = node("option", "", label);
    option.value = value;
    return option;
  }));
  type.value = state.libraryItemType;
  byId("library-direction").value = state.libraryDirection;
}

async function selectView(view) {
  state.view = view;
  state.libraryItemType = "";
  state.selectedField = null;
  const descriptor = descriptorFor(view);
  const labels = {
    projects: "Projects",
    tools: "Tools",
  };
  const title = descriptor?.label || labels[view] || view;
  byId("view-title").textContent = title;
  byId("resource-heading").textContent = title;
  syncLibraryQueryControls();
  if (isDocumentLibrary()) {
    await loadLibraryPage(true);
  } else {
    state.libraryItems = Array.isArray(state.directory?.[view])
      ? [...state.directory[view]]
      : [];
    state.libraryNextCursor = null;
    byId("load-more").hidden = true;
  }
  renderLibraries();
  renderResources();
  renderFieldDetail();
  syncFieldRegisterButton();
}

async function loadLibraryPage(reset = false) {
  if (!isDocumentLibrary()) return;
  if (state.libraryLoading && !reset) return;
  if (!reset && !state.libraryNextCursor) return;
  const requestId = reset ? state.libraryRequestId + 1 : state.libraryRequestId;
  if (reset) state.libraryRequestId = requestId;
  state.libraryLoading = true;
  byId("load-more").disabled = true;
  try {
    const query = new URLSearchParams({ limit: "24" });
    const queryText = state.query.trim();
    if (queryText) query.set("query", queryText);
    query.set("sort", state.librarySort);
    query.set("direction", state.libraryDirection);
    if (state.libraryItemType) query.set("type", state.libraryItemType);
    if (!reset && state.libraryNextCursor) query.set("cursor", state.libraryNextCursor);
    const response = await fetch(
      `/api/v3/libraries/${encodeURIComponent(state.view)}/items?${query}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error(await responseMessage(response));
    const page = await response.json();
    if (requestId !== state.libraryRequestId) return;
    state.libraryItems = reset ? page.items : [...state.libraryItems, ...page.items];
    state.libraryNextCursor = page.next_cursor;
    state.artifacts = state.libraryItems.flatMap((item) => (
      Array.isArray(item.artifacts) ? item.artifacts : []
    ));
    if (state.view === "fields" && reset) {
      state.selectedField = state.libraryItems.find((item) => item.available !== false) || null;
    }
  } catch (error) {
    if (requestId !== state.libraryRequestId) return;
    state.libraryItems = reset ? [] : state.libraryItems;
    state.libraryNextCursor = null;
    byId("revision").textContent = `Library 读取失败：${String(error.message || error)}`;
  } finally {
    if (requestId !== state.libraryRequestId) return;
    state.libraryLoading = false;
    byId("load-more").disabled = false;
    byId("load-more").hidden = !state.libraryNextCursor;
  }
}

function actionUsesDestination(action) {
  return action.destination_required === true
    || ["required", "selectable"].includes(action.workspace_policy);
}

function selectedDestinationId() {
  return state.destinations.selectedId;
}

function unavailableDestinationReason() {
  return state.destinations.capabilityError
    ? "当前无法连接 cmux；请从 cmux 中运行 scholar-workflow open-hub 后选择打开位置"
    : "没有可用的 cmux 打开位置";
}

function applyDestinations(payload) {
  const items = Array.isArray(payload)
    ? payload
    : (payload && Array.isArray(payload.destinations) ? payload.destinations : []);
  state.destinations.items = items.filter((destination) => (
    destination && typeof destination.destination_id === "string"
      && destination.destination_id
  ));
  state.destinations.capabilityError = payload && !Array.isArray(payload)
    ? (payload.capability_error || payload.reason || null)
    : null;

  const previous = state.destinations.selectedId;
  const preferred = state.destinations.items.find(
    (destination) => destination.destination_id === previous,
  ) || state.destinations.items.find((destination) => destination.is_default)
    || state.destinations.items[0];
  state.destinations.selectedId = preferred?.destination_id || null;

  const select = byId("workspace-select");
  if (state.destinations.items.length === 0) {
    select.replaceChildren(node("option", "", "未选择 cmux 位置"));
  } else {
    select.replaceChildren(...state.destinations.items.map((destination) => {
      const suffix = destination.is_default ? " · 默认" : "";
      const option = node("option", "", `${destination.display_name}${suffix}`);
      option.value = destination.destination_id;
      return option;
    }));
  }
  select.disabled = state.destinations.items.length === 0;
  select.value = state.destinations.selectedId || "";

  const status = byId("cmux-status");
  if (state.destinations.capabilityError) {
    status.textContent = "当前无法连接 cmux；阅读与文件操作不受影响。需要打开窗口时，请在 cmux 中运行 scholar-workflow open-hub。";
    status.className = "cmux-status";
  } else if (!state.destinations.selectedId) {
    status.textContent = "仅 cmux 打开动作不可用；阅读与文件能力不受影响";
    status.className = "cmux-status";
  } else {
    status.textContent = "只决定浏览器、终端和 Codex 窗口在哪里出现";
    status.className = "cmux-status";
  }
}

function capability(name) {
  const value = state.directory?.capabilities?.[name];
  return value && typeof value.available === "boolean"
    ? value
    : { available: false, reason: "服务未报告此能力" };
}

const CAPABILITY_LABELS = {
  vault_writes: "Vault 保存",
  project_document_writes: "项目文档",
  cmux_launches: "cmux 打开",
  codex_tasks: "Codex 任务",
  zotflow_annotations: "ZotFlow 标注",
  zotero_local_api: "Zotero Local API",
};

function renderCapabilities() {
  const container = byId("capability-matrix");
  const rows = Object.entries(CAPABILITY_LABELS).map(([name, label]) => {
    const status = capability(name);
    const chip = node("div", `capability-chip ${status.available ? "available" : "unavailable"}`);
    chip.append(node("span", "capability-dot"));
    const copy = node("div", "capability-copy");
    copy.append(node("strong", "", label));
    copy.append(node("small", "", status.available ? "可用" : (status.reason || "不可用")));
    chip.append(copy);
    return chip;
  });
  container.replaceChildren(...rows);
  const available = Object.keys(CAPABILITY_LABELS).filter(
    (name) => capability(name).available,
  ).length;
  byId("operation-status").textContent = `服务就绪 · ${available}/${rows.length} 项能力可用`;
  document.querySelector(".status-dot").classList.toggle(
    "warning",
    state.directory?.diagnostics?.some((entry) => entry.level === "error"),
  );
}

const TASK_EFFORT_LABELS = {
  fast: "快速",
  standard: "标准",
  deep: "深入",
};
const TASK_FINAL_STATES = new Set([
  "succeeded",
  "failed",
  "interrupted",
  "cancelled",
  "timed_out",
  "recovery_required",
]);

function selectedTaskAction() {
  return state.tasks.actions.find(
    (action) => action.action_id === state.tasks.selectedActionId,
  ) || null;
}

function taskTargetsFor(action) {
  if (!action) return [];
  const allowed = Array.isArray(action.allowed_target_ids)
    ? new Set(action.allowed_target_ids)
    : null;
  return state.tasks.targets.filter((target) => (
    target
      && typeof target.target_id === "string"
      && (!allowed || allowed.has(target.target_id))
  ));
}

function readableTaskTarget(target, index) {
  for (const field of ["display_name", "title", "label", "name"]) {
    if (typeof target[field] === "string" && target[field].trim()) {
      return target[field].trim();
    }
  }
  if (target.kind === "project") {
    const project = (state.directory?.projects || []).find((candidate) => {
      const identities = [candidate.project_id, candidate.ref?.entity_id].filter(Boolean);
      return identities.some((identity) => (
        target.target_id === identity || target.target_id.endsWith(`:${identity}`)
      ));
    });
    if (project?.display_name) return project.display_name;
  }
  const kind = {
    project: "项目目标",
    vault: "Vault 目标",
    folder: "文件夹目标",
  }[target.kind] || "受信任目标";
  return `${kind} ${index + 1}`;
}

function currentDestination() {
  return state.destinations.items.find(
    (destination) => destination.destination_id === selectedDestinationId(),
  ) || null;
}

function taskBriefSize() {
  return new TextEncoder().encode(byId("task-brief").value).length;
}

function taskIdempotencyKey() {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
    const values = new Uint32Array(4);
    cryptoApi.getRandomValues(values);
    return `task-${Array.from(values, (value) => value.toString(16).padStart(8, "0")).join("")}`;
  }
  taskFallbackSequence += 1;
  return `task-${Date.now().toString(36)}-${taskFallbackSequence.toString(36)}`;
}

function setTaskStatus(message, kind = "") {
  state.tasks.statusMessage = message;
  state.tasks.statusKind = kind;
}

function defaultTaskStatus() {
  if (state.tasks.loading) return ["正在读取 Codex 任务能力…", ""];
  if (state.tasks.capabilityError) return [state.tasks.capabilityError, "error"];
  const availableActions = state.tasks.actions.filter(
    (action) => action && action.available !== false,
  );
  if (availableActions.length === 0) {
    const reason = state.tasks.actions.find((action) => action && action.reason)?.reason
      || capability("codex_tasks").reason
      || "当前没有可用的 Codex 任务";
    return [reason, "error"];
  }
  if (!selectedTaskAction()) return ["请选择任务用途", ""];
  if (taskTargetsFor(selectedTaskAction()).length === 0) {
    return ["此任务没有可用的已登记目标", "error"];
  }
  if (!selectedDestinationId()) {
    return ["请先在页面上方选择 cmux 默认打开位置；阅读与文件操作不受影响", "error"];
  }
  return ["工作目录只从所选受信任目标解析；cmux 选项只决定终端出现位置", ""];
}

function renderTaskPanel() {
  const actionSelect = byId("task-action");
  const targetSelect = byId("task-target");
  const effortSelect = byId("task-effort");
  const brief = byId("task-brief");
  const submit = byId("task-submit");

  const validActions = state.tasks.actions.filter(
    (action) => action && typeof action.action_id === "string" && action.action_id,
  );
  const availableActions = validActions.filter((action) => action.available !== false);
  if (!availableActions.some((action) => action.action_id === state.tasks.selectedActionId)) {
    state.tasks.selectedActionId = availableActions[0]?.action_id || null;
  }
  const actionOptions = validActions.map((action) => {
    const unavailable = action.available === false;
    const option = node(
      "option",
      "",
      `${action.title || "未命名任务"}${unavailable ? " · 不可用" : ""}`,
    );
    option.value = action.action_id;
    option.disabled = unavailable;
    if (unavailable && action.reason) option.title = action.reason;
    return option;
  });
  if (actionOptions.length === 0) {
    actionOptions.push(node("option", "", "没有可用任务"));
  }
  actionSelect.replaceChildren(...actionOptions);
  actionSelect.value = state.tasks.selectedActionId || "";

  const action = selectedTaskAction();
  const targets = taskTargetsFor(action);
  if (!targets.some((target) => target.target_id === state.tasks.selectedTargetId)) {
    state.tasks.selectedTargetId = targets[0]?.target_id || null;
  }
  const targetOptions = targets.map((target, index) => {
    const option = node("option", "", readableTaskTarget(target, index));
    option.value = target.target_id;
    return option;
  });
  if (targetOptions.length === 0) {
    targetOptions.push(node("option", "", "没有可用目标"));
  }
  targetSelect.replaceChildren(...targetOptions);
  targetSelect.value = state.tasks.selectedTargetId || "";

  const efforts = (Array.isArray(action?.allowed_efforts) ? action.allowed_efforts : [])
    .filter((effort) => Object.hasOwn(TASK_EFFORT_LABELS, effort));
  if (!efforts.includes(state.tasks.selectedEffort)) {
    state.tasks.selectedEffort = efforts.includes("standard") ? "standard" : (efforts[0] || null);
  }
  const effortOptions = efforts.map((effort) => {
    const option = node("option", "", TASK_EFFORT_LABELS[effort]);
    option.value = effort;
    return option;
  });
  if (effortOptions.length === 0) {
    effortOptions.push(node("option", "", "此任务未开放强度选项"));
  }
  effortSelect.replaceChildren(...effortOptions);
  effortSelect.value = state.tasks.selectedEffort || "";

  const destination = currentDestination();
  byId("task-destination").textContent = destination
    ? `运行窗口：${destination.display_name}`
    : "运行窗口：尚未选择 cmux 位置";

  const bytes = taskBriefSize();
  const size = byId("task-brief-limit");
  size.textContent = `${bytes} / 8192 字节`;
  size.classList.toggle("error", bytes > 8192);
  const trimmedBrief = brief.value.trim();
  const hasSelection = Boolean(
    action
      && state.tasks.selectedTargetId
      && state.tasks.selectedEffort
      && selectedDestinationId(),
  );
  const unavailable = state.tasks.loading || Boolean(state.tasks.capabilityError);
  actionSelect.disabled = state.tasks.submitting || unavailable || availableActions.length === 0;
  targetSelect.disabled = state.tasks.submitting || unavailable || targets.length === 0;
  effortSelect.disabled = state.tasks.submitting || unavailable || efforts.length === 0;
  brief.disabled = state.tasks.submitting || unavailable || !action;
  submit.disabled = state.tasks.submitting
    || unavailable
    || !state.csrfToken
    || !hasSelection
    || !trimmedBrief
    || bytes > 8192;
  submit.textContent = state.tasks.submitting ? "正在提交…" : "运行任务";

  const [defaultMessage, defaultKind] = defaultTaskStatus();
  const status = byId("task-status");
  status.textContent = state.tasks.statusMessage || defaultMessage;
  status.className = `task-status ${state.tasks.statusMessage ? state.tasks.statusKind : defaultKind}`.trim();
}

async function loadTaskSurface() {
  try {
    const [actionsResponse, targetsResponse] = await Promise.all([
      fetch("/api/v3/task-actions", { credentials: "same-origin" }),
      fetch("/api/v3/execution-targets", { credentials: "same-origin" }),
    ]);
    if (!actionsResponse.ok || !targetsResponse.ok) {
      const status = !actionsResponse.ok ? actionsResponse.status : targetsResponse.status;
      throw new Error(`Codex 任务接口不可用（HTTP ${status}）`);
    }
    const [actionPayload, targetPayload] = await Promise.all([
      actionsResponse.json(),
      targetsResponse.json(),
    ]);
    if (!Array.isArray(actionPayload.actions) || !Array.isArray(targetPayload.targets)) {
      throw new Error("Codex 任务接口返回了无效数据");
    }
    state.tasks.actions = actionPayload.actions;
    state.tasks.targets = targetPayload.targets;
    state.tasks.capabilityError = null;
  } catch (error) {
    state.tasks.actions = [];
    state.tasks.targets = [];
    state.tasks.capabilityError = String(error.message || error);
  } finally {
    state.tasks.loading = false;
    renderTaskPanel();
  }
}

function normalizedTaskStatus(payload) {
  const run = payload && typeof payload.run === "object" ? payload.run : payload;
  return {
    runId: run?.run_id || payload?.run_id || null,
    state: run?.state || payload?.state || "queued",
    terminalRouted: payload?.terminal_routed === true || run?.terminal_routed === true,
  };
}

function taskStatusMessage(payload) {
  const status = normalizedTaskStatus(payload);
  const labels = {
    queued: "任务已排队",
    running: "Codex 正在运行",
    succeeded: "任务已完成",
    failed: "任务执行失败",
    interrupted: "任务已中断",
    cancelled: "任务已取消",
    timed_out: "任务执行超时",
    recovery_required: "任务需要恢复处理",
  };
  let message = labels[status.state] || `任务状态：${status.state}`;
  const destinationName = state.tasks.activeDestinationName
    || currentDestination()?.display_name
    || null;
  if (["queued", "running"].includes(status.state) && destinationName) {
    message += status.terminalRouted
      ? `；终端已路由到“${destinationName}”`
      : `；运行窗口为“${destinationName}”`;
  }
  return [message, status];
}

function clearTaskPoll() {
  if (state.tasks.pollTimer !== null) {
    window.clearTimeout(state.tasks.pollTimer);
    state.tasks.pollTimer = null;
  }
}

async function pollTaskRun(runId) {
  if (!runId || state.tasks.activeRunId !== runId) return;
  try {
    const response = await fetch(
      `/api/v3/task-runs/${encodeURIComponent(runId)}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error(await responseMessage(response));
    if (state.tasks.activeRunId !== runId) return;
    const payload = await response.json();
    const [message, status] = taskStatusMessage(payload);
    setTaskStatus(message, status.state === "succeeded" ? "success" : (
      TASK_FINAL_STATES.has(status.state) ? "error" : ""
    ));
    renderTaskPanel();
    if (!TASK_FINAL_STATES.has(status.state)) {
      state.tasks.pollTimer = window.setTimeout(() => pollTaskRun(runId), 1400);
    }
  } catch (error) {
    if (state.tasks.activeRunId !== runId) return;
    setTaskStatus(`任务已提交，但状态刷新失败：${String(error.message || error)}`, "error");
    renderTaskPanel();
  }
}

async function submitTask(event) {
  event.preventDefault();
  if (state.tasks.submitting) return;
  const action = selectedTaskAction();
  const destinationId = selectedDestinationId();
  const destinationName = currentDestination()?.display_name || null;
  const brief = byId("task-brief").value.trim();
  if (!action || !state.tasks.selectedTargetId || !state.tasks.selectedEffort) {
    setTaskStatus("请选择可用的任务、目标和思考强度", "error");
    renderTaskPanel();
    return;
  }
  if (!destinationId) {
    setTaskStatus("请先在页面上方选择 cmux 默认打开位置", "error");
    renderTaskPanel();
    return;
  }
  if (!brief || new TextEncoder().encode(brief).length > 8192) {
    setTaskStatus("任务说明必须为 1–8192 字节", "error");
    renderTaskPanel();
    return;
  }
  state.tasks.submitting = true;
  setTaskStatus("正在安全提交任务…");
  renderTaskPanel();
  try {
    const response = await fetch("/api/v3/tasks", {
      method: "POST",
      credentials: "same-origin",
      headers: stateChangingHeaders(),
      body: JSON.stringify({
        action_id: action.action_id,
        destination_id: destinationId,
        target_id: state.tasks.selectedTargetId,
        brief,
        effort: state.tasks.selectedEffort,
        idempotency_key: taskIdempotencyKey(),
      }),
    });
    if (!response.ok) throw new Error(await responseMessage(response));
    const payload = await response.json();
    state.tasks.activeDestinationName = destinationName;
    const [message, status] = taskStatusMessage(payload);
    clearTaskPoll();
    state.tasks.activeRunId = status.runId;
    setTaskStatus(message, status.state === "succeeded" ? "success" : (
      TASK_FINAL_STATES.has(status.state) ? "error" : ""
    ));
    if (status.runId && !TASK_FINAL_STATES.has(status.state)) {
      state.tasks.pollTimer = window.setTimeout(() => pollTaskRun(status.runId), 900);
    }
  } catch (error) {
    setTaskStatus(`任务提交失败：${String(error.message || error)}`, "error");
  } finally {
    state.tasks.submitting = false;
    renderTaskPanel();
  }
}

function actionsFor(item) {
  if (Array.isArray(item.actions)) return item.actions;
  const entityId = item.ref?.entity_id;
  const resourceId = item.resource_id;
  return state.actions[entityId] || state.actions[resourceId] || [];
}

function renderHubActions() {
  const container = byId("hub-actions");
  container.replaceChildren(...(state.actions.__hub__ || []).map(actionButton));
}

function actionButton(action) {
  const className = action.primary ? "action-button primary" : "action-button";
  const button = node("button", className, action.label);
  button.type = "button";
  const requiresDestination = actionUsesDestination(action);
  const unavailable = action.available === false;
  const syncDisabled = () => {
    button.disabled = unavailable || (requiresDestination && !selectedDestinationId());
    button.title = unavailable
      ? (action.reason || "此动作当前不可用")
      : (requiresDestination && !selectedDestinationId() ? unavailableDestinationReason() : "");
  };
  syncDisabled();
  button.addEventListener("click", async () => {
    const destinationId = requiresDestination ? selectedDestinationId() : null;
    if (unavailable || (requiresDestination && !destinationId)) return;
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "正在打开…";
    try {
      const response = await fetch(
        `/api/v3/actions/${encodeURIComponent(action.id)}/invoke`, {
        method: "POST",
        credentials: "same-origin",
        headers: stateChangingHeaders(),
        body: JSON.stringify(destinationId ? { destination_id: destinationId } : {}),
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      button.textContent = "已打开";
    } catch (error) {
      button.textContent = `失败：${String(error.message || error)}`;
    } finally {
      window.setTimeout(() => {
        button.textContent = original;
        syncDisabled();
      }, 2800);
    }
  });
  return button;
}
function resourceCard(resource) {
  const card = node("article", "card paper-card");
  const meta = node("div", "card-meta");
  meta.append(node("span", "kind", resource.paper_type || "Other"));
  meta.append(node("span", "", resource.year ? String(resource.year) : "未标年份"));
  card.append(meta);
  card.append(node("h3", "", resource.title || "未命名资料"));
  card.append(node(
    "p",
    "authors",
    (resource.authors || []).join(" · ") || "作者信息由 Zotero 提供",
  ));
  const footer = node("div", "card-footer");
  footer.append(node("span", "card-source", resource.venue || "Zotero"));
  const controls = node("div", "card-actions");
  for (const action of actionsFor(resource)) controls.append(actionButton(action));
  if (!controls.hasChildNodes()) {
    controls.append(node("span", "action-diagnostic", "暂无可执行动作"));
  }
  footer.append(controls);
  card.append(footer);
  return card;
}

function fieldCard(field) {
  const card = node("article", "card field-card");
  const meta = node("div", "card-meta");
  meta.append(node("span", "kind", "Field"));
  meta.append(node("span", "", field.available === false ? "不可用" : "已登记"));
  card.append(meta);
  card.append(node("h3", "", field.title || "未命名 Field"));
  const groupCount = Array.isArray(field.navigation) ? field.navigation.length : 0;
  card.append(node(
    "p",
    "authors",
    field.available === false
      ? (field.detail || "Field 来源当前不可用")
      : `${groupCount} 个导航分组 · 首页 ${field.home || "未设置"}`,
  ));
  const footer = node("div", "card-footer");
  footer.append(node("span", "card-source", field.relative_root || "."));
  const open = node("button", "preview-button", "打开 Field");
  open.type = "button";
  open.disabled = field.available === false;
  open.addEventListener("click", () => {
    selectInitialFieldDocument(field);
    state.selectedField = field;
    renderResources();
    renderFieldDetail();
    byId("field-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  footer.append(open);
  card.classList.toggle(
    "selected",
    state.selectedField?.ref?.entity_id === field.ref?.entity_id,
  );
  card.append(footer);
  return card;
}

function selectInitialFieldDocument(field) {
  if (!field || typeof field.home !== "string") return;
  if (typeof field.selected_document_path === "string") return;
  field.selected_document_path = field.home;
  field.selected_document_content = field.home_content;
  field.selected_document_revision = field.home_revision;
}

async function loadFieldDocument(field, relativePath) {
  const fieldId = field?.field_id || field?.ref?.entity_id;
  if (typeof fieldId !== "string" || typeof relativePath !== "string") return;
  field.selected_document_path = relativePath;
  field.selected_document_content = null;
  field.selected_document_revision = null;
  renderFieldDetail();
  try {
    const query = new URLSearchParams({ relative_path: relativePath });
    const response = await fetch(
      `/api/v3/fields/${encodeURIComponent(fieldId)}/documents?${query.toString()}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error(await responseMessage(response));
    const payload = await response.json();
    if (state.selectedField !== field || field.selected_document_path !== relativePath) return;
    field.selected_document_content = payload.content;
    field.selected_document_revision = payload.revision;
    if (relativePath === field.home) {
      field.home_content = payload.content;
      field.home_revision = payload.revision;
    }
    renderFieldDetail();
  } catch (error) {
    if (state.selectedField !== field || field.selected_document_path !== relativePath) return;
    field.selected_document_content = `> 读取失败：${String(error.message || error)}`;
    field.selected_document_revision = null;
    renderFieldDetail();
  }
}

function syncProjectOperationForm() {
  const kind = byId("project-ops-kind").value;
  byId("project-ops-source-row").hidden = !["copy", "trash"].includes(kind);
  byId("project-ops-artifact-row").hidden = kind !== "copy-knowledge";
  byId("project-ops-destination-row").hidden = !["copy", "copy-knowledge", "paste"].includes(kind);
  byId("project-ops-content-row").hidden = kind !== "paste";
  byId("project-ops-artifact").disabled = state.artifacts.length === 0;
  byId("project-ops-submit").disabled = state.projectOps.submitting
    || !capability("project_document_writes").available;
}

function openProjectOperations(project) {
  if (!capability("project_document_writes").available
      || !project.enabled || !project.docs_available) return;
  state.projectOps.project = project;
  state.projectOps.submitting = false;
  byId("project-ops-project").textContent = `${project.display_name} · ${project.project_id}`;
  byId("project-ops-source").value = "";
  byId("project-ops-destination").value = "";
  byId("project-ops-content").value = "";
  byId("project-ops-confirm").checked = false;
  byId("project-ops-status").textContent = "";
  const artifacts = state.artifacts.filter(
    (artifact) => ["markdown", "canvas"].includes(artifact.format),
  );
  byId("project-ops-artifact").replaceChildren(...artifacts.map((artifact) => {
    const option = node("option", "", `${artifactLabel(artifact.kind)} · ${artifact.vault_path}`);
    option.value = artifact.artifact_id;
    return option;
  }));
  syncProjectOperationForm();
  byId("project-ops-dialog").showModal();
}

async function submitProjectOperation(event) {
  event.preventDefault();
  const project = state.projectOps.project;
  if (!project || state.projectOps.submitting
      || !capability("project_document_writes").available) return;
  const operation = byId("project-ops-kind").value;
  const source = byId("project-ops-source").value.trim();
  const destination = byId("project-ops-destination").value.trim();
  const confirmGit = byId("project-ops-confirm").checked;
  let body;
  if (operation === "copy") {
    body = { source_path: source, destination_path: destination, confirm_git: confirmGit };
  } else if (operation === "copy-knowledge") {
    body = {
      artifact_id: byId("project-ops-artifact").value,
      destination_path: destination,
      confirm_git: confirmGit,
    };
  } else if (operation === "paste") {
    body = {
      destination_path: destination,
      content: byId("project-ops-content").value,
      confirm_git: confirmGit,
    };
  } else if (operation === "trash") {
    body = { relative_path: source, confirm_git: confirmGit };
  } else {
    return;
  }
  state.projectOps.submitting = true;
  byId("project-ops-status").textContent = "正在执行…";
  syncProjectOperationForm();
  try {
    const response = await fetch(
      `/api/v3/projects/${encodeURIComponent(project.project_id)}/docs/${operation}`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: stateChangingHeaders(),
        body: JSON.stringify(body),
      },
    );
    const raw = await response.text();
    let payload = null;
    try { payload = raw ? JSON.parse(raw) : null; } catch (_error) { payload = null; }
    if (!response.ok) {
      if (response.status === 409 && payload?.code === "confirmation_required") {
        const gitState = payload.git_state ? `（Git: ${payload.git_state}）` : "";
        byId("project-ops-status").textContent =
          `需要本次确认 ${gitState}：勾选确认框后重试。`;
        byId("project-ops-confirm").focus();
        return;
      }
      throw new Error(payload?.error || raw || `HTTP ${response.status}`);
    }
    byId("project-ops-status").textContent = payload?.trash_path
      ? `已移入 trash：${payload.trash_path}`
      : `操作完成：${payload?.destination_path || payload?.relative_path || "已写入"}`;
  } catch (error) {
    byId("project-ops-status").textContent =
      `操作失败：${String(error.message || error)}`;
  } finally {
    state.projectOps.submitting = false;
    syncProjectOperationForm();
  }
}

function projectToolCard(item) {
  const card = node("article", "card");
  const meta = node("div", "card-meta");
  const type = state.view === "projects" ? "Project" : (item.tool_type || "Tool");
  meta.append(node("span", "kind", type));
  meta.append(node("span", "", item.enabled ? "已启用" : "已停用"));
  card.append(meta);
  card.append(node("h3", "", item.display_name || item.project_id || item.tool_id));
  const declared = (item.capabilities || []).join(" · ") || "尚未声明能力";
  card.append(node("p", "authors", declared));
  const footer = node("div", "card-footer");
  footer.append(node(
    "span",
    "card-source",
    state.view === "projects" ? item.project_id : (item.source || item.tool_id),
  ));
  if (state.view === "projects") {
    const operations = node("button", "preview-button", "文档操作");
    operations.type = "button";
    operations.disabled = !item.enabled || !item.docs_available
      || !capability("project_document_writes").available;
    operations.title = operations.disabled
      ? (capability("project_document_writes").reason || "项目 docs 当前不可用")
      : "复制、粘贴或移入可恢复 trash";
    operations.addEventListener("click", () => openProjectOperations(item));
    footer.append(operations);
  }
  card.append(footer);
  return card;
}

function libraryCard(item) {
  if (state.view === "papers") return resourceCard(item);
  if (state.view === "fields") return fieldCard(item);
  return projectToolCard(item);
}

function renderResources() {
  const normalizedQuery = state.query.trim().toLocaleLowerCase();
  const resources = state.libraryItems.filter((item) => (
    !normalizedQuery
    || JSON.stringify(item).toLocaleLowerCase().includes(normalizedQuery)
  ));
  const grid = byId("resource-grid");
  grid.replaceChildren(...resources.map(libraryCard));
  byId("result-count").textContent = `${resources.length} 项`;
  byId("empty").hidden = resources.length !== 0;
}

function fieldHomeArtifact(field) {
  if (field?.home_artifact && typeof field.home_artifact === "object") {
    return field.home_artifact;
  }
  const fieldId = field?.field_id || field?.ref?.entity_id;
  selectInitialFieldDocument(field);
  const relativePath = field?.selected_document_path;
  const content = field?.selected_document_content;
  const revision = field?.selected_document_revision;
  if (typeof fieldId !== "string" || typeof relativePath !== "string"
      || typeof content !== "string" || typeof revision !== "string") return null;
  return {
    artifact_id: `field:${fieldId}:${relativePath}`,
    field_id: fieldId,
    field_document: true,
    relative_path: relativePath,
    content,
    revision,
    title: `${field.title} · ${relativePath}`,
    kind: "technical-document",
    format: "markdown",
    vault_path: relativePath,
  };
}

function renderFieldDetail() {
  const section = byId("field-detail");
  const field = state.view === "fields" ? state.selectedField : null;
  section.hidden = !field;
  if (!field) return;
  selectInitialFieldDocument(field);
  const navigation = byId("field-navigation");
  const groups = Array.isArray(field.navigation) ? field.navigation : [];
  navigation.replaceChildren(...groups.map((group) => {
    const wrapper = node("section", "field-navigation-group");
    wrapper.append(node("h3", "", group.label || "导航"));
    const list = node("ul");
    for (const item of group.items || []) {
      const entry = node("li");
      const openDocument = node("button", "field-navigation-item", item);
      openDocument.type = "button";
      openDocument.classList.toggle("selected", field.selected_document_path === item);
      openDocument.addEventListener("click", () => loadFieldDocument(field, item));
      entry.append(openDocument);
      list.append(entry);
    }
    wrapper.append(list);
    return wrapper;
  }));
  if (!navigation.hasChildNodes()) {
    navigation.append(node("p", "action-diagnostic", "该 Field 尚未声明导航分组"));
  }

  byId("field-document-title").textContent = field.title || "Field";
  byId("field-document-path").textContent = field.selected_document_path || field.home || "";
  const content = typeof field.selected_document_content === "string"
    ? field.selected_document_content
    : (field.detail ? `> ${field.detail}` : "正在读取文档…");
  renderReadable(
    byId("field-document-content"),
    { format: "markdown" },
    content,
  );
  const artifact = fieldHomeArtifact(field);
  const edit = byId("field-document-edit");
  edit.hidden = !artifact;
  edit.disabled = !capability("vault_writes").available;
  edit.title = edit.disabled ? (capability("vault_writes").reason || "Vault 保存不可用") : "";
  edit.onclick = artifact ? () => showPreview(artifact) : null;
}

function syncFieldRegisterButton() {
  const button = byId("field-register");
  button.hidden = state.view !== "fields";
  button.disabled = state.fieldRegistration.busy;
}

function previewListSection(title, values, tone = "") {
  const section = node("section", `field-preview-section${tone ? ` ${tone}` : ""}`);
  section.append(node("h3", "", title));
  if (!Array.isArray(values) || values.length === 0) {
    section.append(node("p", "action-diagnostic", "无"));
    return section;
  }
  const list = node("ul");
  for (const value of values) list.append(node("li", "", String(value)));
  section.append(list);
  return section;
}

function renderFieldRegistrationPreview() {
  const target = byId("field-register-preview");
  const preview = state.fieldRegistration.preview;
  if (!preview) {
    target.replaceChildren(node("p", "markdown-empty", "请在系统文件选择器中选择 Vault 或目录…"));
    byId("field-register-confirm").disabled = true;
    return;
  }
  const summary = node("div", "field-preview-summary");
  summary.append(node(
    "strong",
    "",
    preview.registration_only
      ? "检测到可携带的 Field manifest；本机尚未登记 Source"
      : (preview.existing_manifest ? "检测到现有 Field manifest" : "将创建 Field manifest"),
  ));
  summary.append(node(
    "small",
    "",
    preview.registration_only
      ? `确认后将在本机启用 manifest 已有的全部 ${preview.registered_fields?.length || 0} 个 Fields · source ${preview.source_id}`
      : `${preview.fields?.length || 0} 个待初始化 · ${preview.registered_fields?.length || 0} 个已登记 · source ${preview.source_id}`,
  ));
  const fields = node("section", "field-preview-section");
  fields.append(node("h3", "", "请选择本次要初始化的一个 Field"));
  const fieldCards = node("div", "field-preview-candidates");
  for (const field of preview.fields || []) {
    const card = node("label", "field-preview-candidate selectable");
    const input = node("input");
    input.type = "radio";
    input.name = "field-register-choice";
    input.value = field.field_id;
    input.checked = state.fieldRegistration.selectedFieldId === field.field_id;
    input.addEventListener("change", () => {
      state.fieldRegistration.selectedFieldId = field.field_id;
      renderFieldRegistrationPreview();
    });
    const detail = node("span", "field-preview-candidate-detail");
    detail.append(node("strong", "", field.title));
    detail.append(node("small", "", `${field.relative_root} · 首页 ${field.home}`));
    const groups = (field.navigation || []).map((group) => group.label).join(" · ");
    detail.append(node("span", "", groups || "无导航分组"));
    card.append(input, detail);
    fieldCards.append(card);
  }
  if (!fieldCards.hasChildNodes()) {
    fieldCards.append(node("p", "action-diagnostic", "没有找到可初始化的 Markdown Field"));
  }
  fields.append(fieldCards);
  const registered = (preview.registered_fields || []).map((field) => (
    `${field.title} · ${field.relative_root}`
  ));
  const selected = (preview.fields || []).find(
    (field) => field.field_id === state.fieldRegistration.selectedFieldId,
  );
  const linkChanges = (preview.legacy_link_changes || []).filter((change) => (
    preview.registration_only || (selected && (selected.relative_root === "."
      || change.relative_path.startsWith(`${selected.relative_root}/`))
    )
  )).map((change) => (
    `${change.relative_path} · ${change.occurrences} 处 · `
    + `${change.attachment_key} → ${change.replacement}`
  ));
  target.replaceChildren(
    summary,
    ...(preview.registration_only ? [] : [fields]),
    previewListSection(
      preview.registration_only
        ? "现有 manifest 的全部 Fields（确认后在本机可见，文件不修改）"
        : "已登记 Fields（本次不会修改）",
      registered,
    ),
    previewListSection("冲突", preview.conflicts, "error"),
    previewListSection("将发生的模板变更", preview.template_changes),
    previewListSection("未映射 Markdown", preview.unmapped_markdown),
    previewListSection(
      preview.registration_only
        ? "现有 Source 的旧 23128 链接（本次不改写）"
        : "所选 Field 的旧 23128 链接（本次不改写）",
      linkChanges,
    ),
    previewListSection("忽略文件", preview.ignored_files),
  );
  const confirm = byId("field-register-confirm");
  confirm.textContent = preview.registration_only
    ? `登记现有 Source（${preview.registered_fields?.length || 0} 个 Fields）`
    : "初始化所选 Field";
  confirm.disabled = state.fieldRegistration.busy || !preview.candidate_token
    || (!preview.registration_only && !selected)
    || (preview.conflicts || []).length !== 0;
}

function setFieldRegistrationStatus(message, tone = "") {
  const status = byId("field-register-status");
  status.textContent = message;
  status.className = `preview-status${tone ? ` ${tone}` : ""}`;
}

async function openFieldRegistration() {
  if (state.fieldRegistration.busy) return;
  const dialog = byId("field-register-dialog");
  state.fieldRegistration = { preview: null, busy: true, selectedFieldId: null };
  syncFieldRegisterButton();
  renderFieldRegistrationPreview();
  setFieldRegistrationStatus("正在等待系统文件选择器…");
  if (!dialog.open) dialog.showModal();
  try {
    const response = await fetch("/api/v3/fields/select", {
      method: "POST",
      credentials: "same-origin",
      headers: stateChangingHeaders(),
      body: "{}",
    });
    if (!response.ok) throw new Error(await responseMessage(response));
    const payload = await response.json();
    state.fieldRegistration.preview = payload.preview;
    setFieldRegistrationStatus(
      payload.preview.registration_only
        ? "预览未写入所选目录；确认后只登记本机 Source，原 manifest 与全部 Field ID 保持不变。"
        : "预览不会写入所选目录；请选择一个 Field 后确认。",
      "success",
    );
  } catch (error) {
    setFieldRegistrationStatus(`无法生成预览：${String(error.message || error)}`, "error");
  } finally {
    state.fieldRegistration.busy = false;
    syncFieldRegisterButton();
    renderFieldRegistrationPreview();
  }
}

async function confirmFieldRegistration() {
  const preview = state.fieldRegistration.preview;
  const fieldId = state.fieldRegistration.selectedFieldId;
  const registerExistingSource = preview?.registration_only === true;
  if (!preview?.candidate_token || state.fieldRegistration.busy
      || (!registerExistingSource && (!fieldId
        || !(preview.fields || []).some((field) => field.field_id === fieldId)))
      || (preview.conflicts || []).length !== 0) return;
  state.fieldRegistration.busy = true;
  syncFieldRegisterButton();
  renderFieldRegistrationPreview();
  setFieldRegistrationStatus(
    registerExistingSource ? "正在登记现有 Source；不会改写 manifest…" : "正在初始化选定的一个 Field…",
  );
  let confirmationAccepted = false;
  try {
    const response = await fetch("/api/v3/fields/confirm", {
      method: "POST",
      credentials: "same-origin",
      headers: stateChangingHeaders(),
      body: JSON.stringify(registerExistingSource
        ? { candidate_token: preview.candidate_token, source_id: preview.source_id }
        : { candidate_token: preview.candidate_token, field_id: fieldId }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const error = new Error(payload?.error || `HTTP ${response.status}`);
      error.commitUncertain = payload?.code === "field_registration_commit_uncertain";
      throw error;
    }
    confirmationAccepted = true;
    await response.json();
    const directoryResponse = await fetch(directoryEndpoint(), { credentials: "same-origin" });
    if (!directoryResponse.ok) throw new Error(await responseMessage(directoryResponse));
    state.directory = await directoryResponse.json();
    await loadLibraryPage(true);
    const fields = descriptorFor("fields");
    byId("field-count").textContent = String(fields?.total_count || 0);
    renderCapabilities();
    renderLibraries();
    renderResources();
    renderFieldDetail();
    state.fieldRegistration.preview = null;
    state.fieldRegistration.selectedFieldId = null;
    setFieldRegistrationStatus(
      registerExistingSource
        ? "现有 Source 已在本机登记；全部原有 Fields 可见，manifest 未改动。"
        : "所选 Field 已初始化；其他候选未改变。",
      "success",
    );
    window.setTimeout(() => byId("field-register-dialog").close(), 600);
  } catch (error) {
    state.fieldRegistration.preview = null;
    state.fieldRegistration.selectedFieldId = null;
    const detail = String(error.message || error);
    if (confirmationAccepted) {
      setFieldRegistrationStatus(
        `登记已成功，但列表刷新失败：${detail}。请重载 Hub 页面查看，不要重复确认。`, "error",
      );
    } else if (error.commitUncertain) {
      setFieldRegistrationStatus(
        `登记状态尚不能确认：${detail}。请先重载并检查 Fields，勿立即重试。`, "error",
      );
    } else {
      setFieldRegistrationStatus(`登记失败：${detail}。请关闭后重新选择并预览。`, "error");
    }
  } finally {
    state.fieldRegistration.busy = false;
    syncFieldRegisterButton();
    renderFieldRegistrationPreview();
  }
}

async function showPreview(artifact) {
  const dialog = byId("preview-dialog");
  const isFieldDocument = artifact.field_document === true;
  const requestId = state.preview.requestId + 1;
  if (previewRenderFrame !== null) {
    window.cancelAnimationFrame(previewRenderFrame);
    previewRenderFrame = null;
  }
  state.preview = {
    artifact,
    content: isFieldDocument ? artifact.content : null,
    revision: isFieldDocument ? artifact.revision : null,
    mode: "read",
    dirty: false,
    saving: false,
    assets: [],
    assetsLoading: !isFieldDocument,
    uploading: false,
    requestId,
  };
  dialog.classList.toggle("field-document-preview", isFieldDocument);
  byId("preview-title").textContent = artifact.title || artifactLabel(artifact.kind);
  byId("preview-path").textContent = artifact.vault_path;
  if (isFieldDocument) {
    renderReadable(byId("preview-content"), artifact, artifact.content);
  } else {
    byId("preview-content").replaceChildren(
      node("p", "markdown-empty", "正在读取 Vault 文件…"),
    );
  }
  byId("preview-live-content").replaceChildren();
  byId("preview-editor").value = "";
  byId("attachment-count").textContent = "0";
  setAttachmentStatus("");
  renderAttachments();
  setPreviewStatus("");
  syncPreviewControls();
  if (!dialog.open) dialog.showModal();
  if (isFieldDocument) return;
  loadAttachments(artifact, requestId);
  try {
    const response = await fetch(
      `/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/content`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (requestId !== state.preview.requestId || !dialog.open) return;
    state.preview.content = payload.content;
    state.preview.revision = payload.revision;
    renderReadable(byId("preview-content"), artifact, payload.content);
    byId("preview-edit").disabled = false;
  } catch (error) {
    if (requestId !== state.preview.requestId || !dialog.open) return;
    byId("preview-content").replaceChildren(
      node("p", "markdown-empty", `无法预览：${String(error.message || error)}`),
    );
    byId("preview-edit").disabled = true;
    setPreviewStatus("文档读取失败", "error");
  }
}

function setPreviewStatus(message, tone = "") {
  const status = byId("preview-status");
  status.textContent = message;
  status.className = `preview-status${tone ? ` ${tone}` : ""}`;
}

function syncPreviewControls() {
  const editing = state.preview.mode === "edit";
  byId("preview-content").hidden = editing;
  byId("preview-editor-layout").hidden = !editing;
  byId("preview-edit").hidden = editing;
  byId("preview-save").hidden = !editing;
  byId("preview-cancel").hidden = !editing;
  const vaultWrites = capability("vault_writes").available;
  byId("preview-edit").disabled = state.preview.content === null || !vaultWrites;
  byId("preview-save").disabled = !state.preview.dirty || state.preview.saving;
  byId("preview-cancel").disabled = state.preview.saving;
  const upload = byId("attachment-upload");
  upload.disabled = !vaultWrites || state.preview.uploading
    || state.preview.artifact === null || state.preview.artifact.field_document === true;
  byId("attachment-upload-label").classList.toggle("disabled", upload.disabled);
  renderAttachments();
}

function beginEditing() {
  if (state.preview.content === null || state.preview.saving) return;
  state.preview.mode = "edit";
  state.preview.dirty = false;
  const editor = byId("preview-editor");
  editor.value = state.preview.content;
  renderReadable(byId("preview-live-content"), state.preview.artifact, editor.value);
  setPreviewStatus("修改只会在点击“保存”后写入文件");
  syncPreviewControls();
  editor.focus();
}

function discardEditing() {
  if (state.preview.saving) return false;
  if (state.preview.dirty && !window.confirm("放弃尚未保存的修改？")) return false;
  state.preview.mode = "read";
  state.preview.dirty = false;
  byId("preview-editor").value = state.preview.content || "";
  setPreviewStatus("");
  syncPreviewControls();
  byId("preview-edit").focus();
  return true;
}

function requestPreviewClose() {
  if (state.preview.saving || state.preview.uploading) {
    setPreviewStatus(state.preview.saving ? "正在保存，请稍候" : "正在添加附件，请稍候");
    return;
  }
  if (state.preview.mode === "edit" && state.preview.dirty
      && !window.confirm("尚有未保存的修改，仍要关闭吗？")) return;
  byId("preview-dialog").close();
}

async function responseMessage(response) {
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;
  try {
    const payload = JSON.parse(text);
    return payload.error || text;
  } catch (_error) {
    return text;
  }
}

async function savePreview() {
  if (state.preview.mode !== "edit" || !state.preview.dirty || state.preview.saving) return;
  const artifact = state.preview.artifact;
  const proposed = byId("preview-editor").value;
  state.preview.saving = true;
  setPreviewStatus("正在保存…");
  syncPreviewControls();
  try {
    const fieldDocument = artifact.field_document === true;
    const endpoint = fieldDocument
      ? `/api/v3/fields/${encodeURIComponent(artifact.field_id)}/documents`
      : `/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/content`;
    const requestBody = fieldDocument
      ? {
        relative_path: artifact.relative_path,
        content: proposed,
        base_revision: state.preview.revision,
      }
      : { content: proposed, base_revision: state.preview.revision };
    const response = await fetch(
      endpoint,
      {
        method: "PUT",
        credentials: "same-origin",
        headers: stateChangingHeaders(),
        body: JSON.stringify(requestBody),
      },
    );
    if (response.status === 409) {
      setPreviewStatus("外部已修改，请重新加载", "error");
      return;
    }
    if (!response.ok) throw new Error(await responseMessage(response));
    const payload = await response.json();
    const savedContent = typeof payload.content === "string" ? payload.content : proposed;
    state.preview.content = savedContent;
    state.preview.revision = payload.revision;
    state.preview.mode = "read";
    state.preview.dirty = false;
    renderReadable(byId("preview-content"), artifact, savedContent);
    byId("preview-editor").value = savedContent;
    if (fieldDocument) {
      const field = state.libraryItems.find((item) => (
        (item.field_id || item.ref?.entity_id) === artifact.field_id
      ));
      if (field) {
        field.selected_document_path = artifact.relative_path;
        field.selected_document_content = savedContent;
        field.selected_document_revision = payload.revision;
        if (artifact.relative_path === field.home) {
          field.home_content = savedContent;
          field.home_revision = payload.revision;
        }
        artifact.content = savedContent;
        artifact.revision = payload.revision;
        state.selectedField = field;
        renderFieldDetail();
      }
    }
    setPreviewStatus("已保存", "success");
    setAttachmentStatus("");
  } catch (error) {
    setPreviewStatus(`保存失败：${String(error.message || error)}`, "error");
  } finally {
    state.preview.saving = false;
    syncPreviewControls();
    if (state.preview.mode === "read") byId("preview-edit").focus();
  }
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function setAttachmentStatus(message, tone = "") {
  const status = byId("attachment-status");
  status.textContent = message;
  status.className = `attachment-status${tone ? ` ${tone}` : ""}`;
}

function insertAttachmentLink(asset) {
  if (state.preview.mode !== "edit") return;
  const editor = byId("preview-editor");
  const start = editor.selectionStart;
  const end = editor.selectionEnd;
  editor.setRangeText(asset.obsidian_link, start, end, "end");
  state.preview.dirty = editor.value !== state.preview.content;
  scheduleLivePreview(editor.value);
  syncPreviewControls();
  editor.focus();
  setAttachmentStatus("已插入链接；保存文档后生效", "success");
}

function renderAttachments() {
  const list = byId("attachment-list");
  if (state.preview.assetsLoading) {
    list.replaceChildren(node("p", "attachment-empty", "正在读取附件…"));
    return;
  }
  if (state.preview.assets.length === 0) {
    list.replaceChildren(node("p", "attachment-empty", "还没有附件"));
    return;
  }
  list.replaceChildren(...state.preview.assets.map((asset) => {
    const row = node("div", "attachment-row");
    const copy = node("div", "attachment-copy");
    copy.append(node("strong", "", asset.display_name));
    copy.append(node("small", "", `${formatBytes(asset.size)} · ${asset.role}`));
    const controls = node("div", "attachment-controls");
    const open = node("a", "attachment-open", "打开");
    open.href = asset.content_url;
    open.target = "_blank";
    open.rel = "noopener";
    controls.append(open);
    if (state.preview.mode === "edit") {
      const insert = node("button", "attachment-insert", "插入链接");
      insert.type = "button";
      insert.addEventListener("click", () => insertAttachmentLink(asset));
      controls.append(insert);
    }
    row.append(copy, controls);
    return row;
  }));
}

async function loadAttachments(artifact, requestId = state.preview.requestId) {
  state.preview.assetsLoading = true;
  renderAttachments();
  try {
    const response = await fetch(
      `/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/assets`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error(await responseMessage(response));
    const payload = await response.json();
    if (requestId !== state.preview.requestId) return;
    state.preview.assets = payload.assets || [];
    byId("attachment-count").textContent = String(state.preview.assets.length);
  } catch (error) {
    if (requestId !== state.preview.requestId) return;
    state.preview.assets = [];
    setAttachmentStatus(`附件读取失败：${String(error.message || error)}`, "error");
  } finally {
    if (requestId === state.preview.requestId) {
      state.preview.assetsLoading = false;
      renderAttachments();
    }
  }
}

async function uploadAttachments(files) {
  const artifact = state.preview.artifact;
  if (!artifact || files.length === 0 || state.preview.uploading) return;
  state.preview.uploading = true;
  setAttachmentStatus(`正在添加 ${files.length} 个附件…`);
  syncPreviewControls();
  let added = 0;
  try {
    for (const file of files) {
      const query = new URLSearchParams({
        name: file.name,
        role: file.type.startsWith("image/") ? "embed" : "supplement",
      });
      const response = await fetch(
        `/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/assets?${query}`,
        {
          method: "POST",
          credentials: "same-origin",
          headers: stateChangingHeaders(file.type || "application/octet-stream"),
          body: file,
        },
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      added += 1;
    }
    await loadAttachments(artifact);
    setAttachmentStatus(`已添加 ${added} 个附件`, "success");
  } catch (error) {
    await loadAttachments(artifact);
    const prefix = added ? `已添加 ${added} 个；` : "";
    setAttachmentStatus(`${prefix}添加失败：${String(error.message || error)}`, "error");
  } finally {
    state.preview.uploading = false;
    syncPreviewControls();
  }
}

async function boot() {
  try {
    const [directoryResponse, actionsResponse, sessionResponse, destinationsResponse] =
      await Promise.all([
        fetch(directoryEndpoint(), { credentials: "same-origin" }),
        fetch("/api/v3/actions", { credentials: "same-origin" }),
        fetch("/api/v1/session", { credentials: "same-origin" }),
        fetch(destinationsEndpoint(), { credentials: "same-origin" }),
        loadTaskSurface(),
      ]);
    if (!directoryResponse.ok || !actionsResponse.ok || !sessionResponse.ok) {
      throw new Error("Hub v3 API 暂时不可用");
    }
    state.directory = await directoryResponse.json();
    if (state.directory.schema_version !== 3) {
      throw new Error("HubDirectory 不是 schema 3");
    }
    const actionPayload = await actionsResponse.json();
    state.actions = actionPayload.actions || actionPayload;
    state.csrfToken = (await sessionResponse.json()).csrf_token;
    if (destinationsResponse.ok) {
      applyDestinations(await destinationsResponse.json());
    } else {
      applyDestinations({
        destinations: [],
        capability_error: `cmux 打开位置不可用（HTTP ${destinationsResponse.status}）`,
      });
    }
    syncLibraryQueryControls();
    await loadLibraryPage(true);
    const papers = descriptorFor("papers");
    const fields = descriptorFor("fields");
    byId("paper-count").textContent = String(papers?.total_count || 0);
    byId("field-count").textContent = String(fields?.total_count || 0);
    byId("project-count").textContent = String(state.directory.projects?.length || 0);
    byId("tool-count").textContent = String(state.directory.tools?.length || 0);
    byId("revision").textContent = "HubDirectory schema 3 · 实时 provider 投影";
    renderCapabilities();
    renderLibraries();
    renderHubActions();
    renderResources();
    renderFieldDetail();
    syncFieldRegisterButton();
    renderTaskPanel();
  } catch (error) {
    applyDestinations({
      destinations: [],
      capability_error: "cmux 打开位置暂不可用",
    });
    byId("revision").textContent = "Hub 暂时无法读取 v3 目录";
    byId("empty").hidden = false;
    byId("empty").querySelector("p").textContent = String(error);
    renderTaskPanel();
  }
}

for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => selectView(button.dataset.view));
}
let librarySearchTimer = null;
byId("search").addEventListener("input", (event) => {
  state.query = event.target.value;
  if (librarySearchTimer !== null) window.clearTimeout(librarySearchTimer);
  librarySearchTimer = window.setTimeout(async () => {
    if (isDocumentLibrary()) await loadLibraryPage(true);
    renderResources();
    renderFieldDetail();
  }, 250);
});
byId("library-sort").addEventListener("change", async (event) => {
  state.librarySort = event.target.value;
  await loadLibraryPage(true);
  renderResources();
  renderFieldDetail();
});
byId("library-direction").addEventListener("change", async (event) => {
  state.libraryDirection = event.target.value;
  await loadLibraryPage(true);
  renderResources();
  renderFieldDetail();
});
byId("library-type").addEventListener("change", async (event) => {
  state.libraryItemType = event.target.value;
  await loadLibraryPage(true);
  renderResources();
  renderFieldDetail();
});
byId("workspace-select").addEventListener("change", (event) => {
  state.destinations.selectedId = event.target.value || null;
  renderHubActions();
  renderResources();
  setTaskStatus(null);
  renderTaskPanel();
});
byId("task-action").addEventListener("change", (event) => {
  state.tasks.selectedActionId = event.target.value || null;
  state.tasks.selectedTargetId = null;
  state.tasks.selectedEffort = null;
  setTaskStatus(null);
  renderTaskPanel();
});
byId("task-target").addEventListener("change", (event) => {
  state.tasks.selectedTargetId = event.target.value || null;
  setTaskStatus(null);
  renderTaskPanel();
});
byId("task-effort").addEventListener("change", (event) => {
  state.tasks.selectedEffort = event.target.value || null;
  setTaskStatus(null);
  renderTaskPanel();
});
byId("task-brief").addEventListener("input", () => {
  setTaskStatus(null);
  renderTaskPanel();
});
byId("task-form").addEventListener("submit", submitTask);
byId("field-register").addEventListener("click", openFieldRegistration);
byId("field-register-confirm").addEventListener("click", confirmFieldRegistration);
for (const id of ["field-register-close", "field-register-cancel"]) {
  byId(id).addEventListener("click", () => {
    if (!state.fieldRegistration.busy) byId("field-register-dialog").close();
  });
}
byId("field-register-dialog").addEventListener("cancel", (event) => {
  if (state.fieldRegistration.busy) event.preventDefault();
});
byId("field-register-dialog").addEventListener("close", () => {
  state.fieldRegistration.preview = null;
  setFieldRegistrationStatus("");
  renderFieldRegistrationPreview();
});
byId("load-more").addEventListener("click", async () => {
  await loadLibraryPage(false);
  renderResources();
  renderFieldDetail();
});
byId("preview-edit").addEventListener("click", beginEditing);
byId("preview-save").addEventListener("click", savePreview);
byId("preview-cancel").addEventListener("click", discardEditing);
byId("preview-close").addEventListener("click", requestPreviewClose);
byId("preview-editor").addEventListener("input", (event) => {
  state.preview.dirty = event.target.value !== state.preview.content;
  scheduleLivePreview(event.target.value);
  syncPreviewControls();
});
byId("attachment-upload").addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  event.target.value = "";
  uploadAttachments(files);
});
byId("preview-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  requestPreviewClose();
});
byId("preview-dialog").addEventListener("close", () => {
  if (previewRenderFrame !== null) {
    window.cancelAnimationFrame(previewRenderFrame);
    previewRenderFrame = null;
  }
  state.preview.requestId += 1;
  state.preview.artifact = null;
  byId("preview-dialog").classList.remove("field-document-preview");
});
byId("project-ops-kind").addEventListener("change", syncProjectOperationForm);
byId("project-ops-form").addEventListener("submit", submitProjectOperation);
byId("project-ops-close").addEventListener("click", () => {
  if (!state.projectOps.submitting) byId("project-ops-dialog").close();
});
byId("project-ops-dialog").addEventListener("cancel", (event) => {
  if (state.projectOps.submitting) event.preventDefault();
});
byId("project-ops-dialog").addEventListener("close", () => {
  state.projectOps.project = null;
  byId("project-ops-status").textContent = "";
});
document.addEventListener("keydown", (event) => {
  if (!byId("preview-dialog").open || state.preview.mode !== "edit") return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "s") {
    event.preventDefault();
    savePreview();
  }
});
boot();
