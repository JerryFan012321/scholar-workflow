"use strict";

const state = {
  catalog: null,
  topic: "all",
  query: "",
  actions: {},
  csrfToken: null,
  cmux: {
    capabilities: { workspace_actions: false },
    workspaces: [],
    selectedWorkspaceId: null,
    capabilityError: "正在读取 cmux 工作区",
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
};
const byId = (id) => document.getElementById(id);
let previewRenderFrame = null;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function resourceText(resource) {
  const ids = resource.identifiers || {};
  return [resource.title, ...(resource.authors || []), ids.doi, ids.arxiv, resource.venue]
    .filter(Boolean).join(" ").toLocaleLowerCase();
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

function renderTopics() {
  const nav = byId("topic-nav");
  nav.replaceChildren();
  for (const topic of state.catalog.topics) {
    const button = node("button", "nav-item", topic.name);
    button.type = "button";
    button.dataset.topicId = topic.topic_id;
    button.addEventListener("click", () => selectTopic(topic.topic_id));
    nav.append(button);
  }
}

function selectTopic(topicId) {
  state.topic = topicId;
  for (const item of document.querySelectorAll(".nav-item")) {
    item.classList.toggle("active", topicId === "all" ? item.dataset.view === "all" : item.dataset.topicId === topicId);
  }
  const topic = state.catalog.topics.find((entry) => entry.topic_id === topicId);
  byId("view-title").textContent = topic ? topic.name : "全部资料";
  renderResources();
  renderArtifacts();
}

function actionUsesWorkspace(action) {
  return ["required", "selectable"].includes(action.workspace_policy);
}

function actionIsCodex(action) {
  return String(action.kind || "").split(".").includes("codex");
}

function selectedWorkspaceId() {
  if (!state.cmux.capabilities.workspace_actions) return null;
  return state.cmux.selectedWorkspaceId;
}

function unavailableWorkspaceReason() {
  return state.cmux.capabilityError || "没有可用的 cmux 工作区";
}

function workspaceEndpoint() {
  const instance = new URLSearchParams(window.location.search).get("instance");
  if (instance === null) return "/api/v1/cmux/workspaces";
  const query = new URLSearchParams({ instance });
  return `/api/v1/cmux/workspaces?${query.toString()}`;
}

function applyWorkspaceListing(payload) {
  const capabilities = payload && payload.capabilities;
  const workspaces = payload && Array.isArray(payload.workspaces) ? payload.workspaces : [];
  const available = Boolean(capabilities && capabilities.workspace_actions);
  state.cmux.capabilities = { workspace_actions: available };
  state.cmux.workspaces = workspaces.filter((workspace) => (
    workspace && typeof workspace.id === "string" && workspace.id
  ));
  state.cmux.capabilityError = payload && payload.capability_error
    ? String(payload.capability_error)
    : null;

  const previous = state.cmux.selectedWorkspaceId;
  const preferred = state.cmux.workspaces.find((workspace) => workspace.id === previous)
    || state.cmux.workspaces.find((workspace) => workspace.contains_hub)
    || state.cmux.workspaces.find((workspace) => workspace.is_current)
    || state.cmux.workspaces[0];
  state.cmux.selectedWorkspaceId = available && preferred ? preferred.id : null;

  const select = byId("workspace-select");
  if (state.cmux.workspaces.length === 0) {
    select.replaceChildren(node("option", "", "无可用工作区"));
  } else {
    select.replaceChildren(...state.cmux.workspaces.map((workspace) => {
      const suffix = workspace.contains_hub
        ? " · Hub 所在"
        : (workspace.is_current ? " · 当前" : "");
      const option = node("option", "", `${workspace.label}${suffix}`);
      option.value = workspace.id;
      return option;
    }));
  }
  select.disabled = !available || !state.cmux.selectedWorkspaceId;
  select.value = state.cmux.selectedWorkspaceId || "";

  const status = byId("cmux-status");
  if (state.cmux.capabilityError) {
    status.textContent = state.cmux.capabilityError;
    status.className = "cmux-status error";
  } else if (!state.cmux.selectedWorkspaceId) {
    status.textContent = "没有可选择的 cmux 工作区";
    status.className = "cmux-status error";
  } else {
    status.textContent = "查看和 Codex 将在所选工作区打开";
    status.className = "cmux-status";
  }
}

function renderHubActions() {
  const container = byId("hub-actions");
  container.replaceChildren(...(state.actions["__hub__"] || []).map(actionButton));
}

function actionButton(action) {
  const button = node("button", "action-button", action.label);
  button.type = "button";
  const requiresWorkspace = actionUsesWorkspace(action);
  if (requiresWorkspace && !selectedWorkspaceId()) {
    button.disabled = true;
    button.title = unavailableWorkspaceReason();
  }
  button.addEventListener("click", async () => {
    const workspaceId = requiresWorkspace ? selectedWorkspaceId() : null;
    if (requiresWorkspace && !workspaceId) return;
    if (actionIsCodex(action)
        && !window.confirm("将在所选 cmux 工作区启动空白 Codex 交互会话。继续？")) {
      return;
    }
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "正在打开…";
    try {
      const response = await fetch(`/api/v1/actions/${encodeURIComponent(action.id)}`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Scholar-Hub-Token": state.csrfToken,
        },
        body: JSON.stringify(workspaceId ? { workspace_id: workspaceId } : {}),
      });
      if (!response.ok) {
        throw new Error(await responseMessage(response));
      }
      button.textContent = "已打开";
    } catch (error) {
      button.textContent = `失败：${String(error.message || error)}`;
    } finally {
      window.setTimeout(() => {
        button.textContent = original;
        button.disabled = requiresWorkspace && !selectedWorkspaceId();
      }, 2800);
    }
  });
  return button;
}

function resourceCard(resource) {
  const card = node("article", "card");
  const meta = node("div", "card-meta");
  meta.append(node("span", "kind", resourceKindLabel(resource.kind)));
  meta.append(node("span", "", resource.year ? String(resource.year) : "未标年份"));
  card.append(meta);
  card.append(node("h3", "", resource.title || "未命名资料"));
  card.append(node("p", "authors", (resource.authors || []).join(" · ") || "作者信息由 Zotero 提供"));
  const footer = node("div", "card-footer");
  footer.append(node("span", "", resource.venue || resource.resource_id));
  const controls = node("div", "card-actions");
  for (const action of state.actions[resource.resource_id] || []) {
    controls.append(actionButton(action));
  }
  footer.append(controls);
  card.append(footer);
  return card;
}

function renderResources() {
  const query = state.query.trim().toLocaleLowerCase();
  const resources = state.catalog.resources.filter((resource) => {
    const topicMatch = state.topic === "all" || (resource.topic_ids || []).includes(state.topic);
    const queryMatch = !query || resourceText(resource).includes(query);
    return topicMatch && queryMatch;
  });
  const grid = byId("resource-grid");
  grid.replaceChildren(...resources.map(resourceCard));
  byId("result-count").textContent = `${resources.length} 项`;
  byId("empty").hidden = resources.length !== 0;
}

function artifactMatchesTopic(artifact) {
  if (state.topic === "all" || artifact.topic_id === state.topic) return true;
  if (!artifact.resource_id) return false;
  const resource = state.catalog.resources.find((row) => row.resource_id === artifact.resource_id);
  return Boolean(resource && (resource.topic_ids || []).includes(state.topic));
}

async function showPreview(artifact) {
  const dialog = byId("preview-dialog");
  const requestId = state.preview.requestId + 1;
  if (previewRenderFrame !== null) {
    window.cancelAnimationFrame(previewRenderFrame);
    previewRenderFrame = null;
  }
  state.preview = {
    artifact,
    content: null,
    revision: null,
    mode: "read",
    dirty: false,
    saving: false,
    assets: [],
    assetsLoading: true,
    uploading: false,
    requestId,
  };
  byId("preview-title").textContent = artifactLabel(artifact.kind);
  byId("preview-path").textContent = artifact.vault_path;
  byId("preview-content").replaceChildren(
    node("p", "markdown-empty", "正在读取 Vault 文件…"),
  );
  byId("preview-live-content").replaceChildren();
  byId("preview-editor").value = "";
  byId("attachment-count").textContent = "0";
  setAttachmentStatus("");
  renderAttachments();
  setPreviewStatus("");
  syncPreviewControls();
  if (!dialog.open) dialog.showModal();
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
  byId("preview-edit").disabled = state.preview.content === null;
  byId("preview-save").disabled = !state.preview.dirty || state.preview.saving;
  byId("preview-cancel").disabled = state.preview.saving;
  const upload = byId("attachment-upload");
  upload.disabled = state.preview.uploading || state.preview.artifact === null;
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
    const response = await fetch(
      `/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/content`,
      {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Scholar-Hub-Token": state.csrfToken,
        },
        body: JSON.stringify({ content: proposed, base_revision: state.preview.revision }),
      },
    );
    if (response.status === 409) {
      setPreviewStatus("外部已修改，请重新加载", "error");
      return;
    }
    if (!response.ok) throw new Error(await responseMessage(response));
    const payload = await response.json();
    state.preview.content = payload.content;
    state.preview.revision = payload.revision;
    state.preview.mode = "read";
    state.preview.dirty = false;
    renderReadable(byId("preview-content"), artifact, payload.content);
    byId("preview-editor").value = payload.content;
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
          headers: {
            "Content-Type": file.type || "application/octet-stream",
            "X-Scholar-Hub-Token": state.csrfToken,
          },
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

function renderArtifacts() {
  const query = state.query.trim().toLocaleLowerCase();
  const artifacts = state.catalog.artifacts.filter((artifact) => {
    const searchable = `${artifact.kind} ${artifact.vault_path} ${artifact.artifact_id}`.toLocaleLowerCase();
    return artifactMatchesTopic(artifact) && (!query || searchable.includes(query));
  });
  const list = byId("artifact-list");
  list.replaceChildren(...artifacts.map((artifact) => {
    const row = node("article", "artifact-row");
    const copy = node("div", "artifact-copy");
    copy.append(node("strong", "", artifactLabel(artifact.kind)));
    copy.append(node("small", "", artifact.vault_path));
    const controls = node("div", "artifact-controls");
    if (["markdown", "canvas"].includes(artifact.format)) {
      const preview = node("button", "preview-button", "阅读");
      preview.type = "button";
      preview.addEventListener("click", () => showPreview(artifact));
      controls.append(preview);
    }
    for (const action of state.actions[artifact.artifact_id] || []) {
      controls.append(actionButton(action));
    }
    row.append(copy, controls);
    return row;
  }));
  byId("document-count").textContent = `${artifacts.length} 个文档`;
}

async function boot() {
  try {
    const [catalogResponse, actionsResponse, sessionResponse, workspacesResponse] = await Promise.all([
      fetch("/api/v1/catalog", { credentials: "same-origin" }),
      fetch("/api/v1/actions", { credentials: "same-origin" }),
      fetch("/api/v1/session", { credentials: "same-origin" }),
      fetch(workspaceEndpoint(), { credentials: "same-origin" }),
    ]);
    if (!catalogResponse.ok || !actionsResponse.ok || !sessionResponse.ok) {
      throw new Error("Hub API 暂时不可用");
    }
    state.catalog = await catalogResponse.json();
    state.actions = await actionsResponse.json();
    state.csrfToken = (await sessionResponse.json()).csrf_token;
    if (workspacesResponse.ok) {
      applyWorkspaceListing(await workspacesResponse.json());
    } else {
      applyWorkspaceListing({
        capabilities: { workspace_actions: false },
        workspaces: [],
        capability_error: `cmux 工作区接口不可用（HTTP ${workspacesResponse.status}）`,
      });
    }
    byId("paper-count").textContent = String(state.catalog.resources.length);
    byId("topic-count").textContent = String(state.catalog.topics.length);
    byId("artifact-count").textContent = String(state.catalog.artifacts.length);
    byId("revision").textContent = `快照 ${state.catalog.revision.slice(0, 18)}…`;
    renderTopics();
    renderHubActions();
    renderResources();
    renderArtifacts();
  } catch (error) {
    applyWorkspaceListing({
      capabilities: { workspace_actions: false },
      workspaces: [],
      capability_error: "cmux 工作区暂不可用",
    });
    byId("revision").textContent = "Hub 暂时无法读取目录";
    byId("empty").hidden = false;
    byId("empty").querySelector("p").textContent = String(error);
  }
}

document.querySelector('[data-view="all"]').addEventListener("click", () => selectTopic("all"));
byId("search").addEventListener("input", (event) => {
  state.query = event.target.value;
  renderResources();
  renderArtifacts();
});
byId("workspace-select").addEventListener("change", (event) => {
  state.cmux.selectedWorkspaceId = event.target.value || null;
  renderHubActions();
  renderResources();
  renderArtifacts();
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
});
document.addEventListener("keydown", (event) => {
  if (!byId("preview-dialog").open || state.preview.mode !== "edit") return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "s") {
    event.preventDefault();
    savePreview();
  }
});
boot();
