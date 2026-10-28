"use strict";

// All research content is inserted as text; source HTML is never executed.
const $ = (id) => document.getElementById(id);
const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const copy = (value) => JSON.parse(JSON.stringify(value));
const tokenKey = "scholar-explorer-token:" + location.origin;
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get("token") || sessionStorage.getItem(tokenKey) || "";
if (token) sessionStorage.setItem(tokenKey, token);
if (location.hash) history.replaceState(null, "", location.pathname);
let data, revision = null, dirty = false, selected = null, matches = null, previewAsset = null;
let formSubmit = null, formBusy = false, queryTimer = null, blobUrl = null, queryGeneration = 0, matchesGeneration = -1;
let formBase = null, saveBusy = false, pollBusy = false;
let noticeOwner = null;
let readOnly = false;
let previewGeneration = 0, previewController = null;
let vaultCandidate = null, vaultBusy = false, vaultGeneration = 0, vaultListGeneration = 0, vaultDocumentGeneration = 0;
const previewBlobs = new Set();
const previewImageTypes = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"]);
let selection = {filters: {}, sort_by: "year", descending: true, include_context: true};
const origins = {author: "作者报告", independent: "独立评测", local: "本地复现", analysis: "分析判断"};
const workKinds = {paper: "论文", webpage: "网页", report: "报告", book: "书籍", other: "其他"};
const edgeKinds = {extends: "继承／改进", borrows: "借用", competes: "竞争", fuses: "融合", context: "上下文"};
const readerReasons = {
  refresh_required: "请刷新论文资产列表，再打开阅读器。",
  unit_unavailable: "论文单元的当前归属尚未核实，请先检查登记。",
  identity_mismatch: "论文、附件或文库身份发生变化，请核对后刷新资产。",
  local_pdf_unavailable: "本机原 PDF 不可用；不会转为云端下载。",
  pdf_changed: "本机 PDF 内容已变化，请刷新资产并核对版本。",
  invalid_reader_uri: "阅读器链接参数不完整或格式不合法，请核对来源入口。",
  preview_changed: "正文或链接版本已变化，请关闭预览后重新打开，再核对原文。",
  preview_unavailable: "这份已登记正文暂不能安全读取，请核对文件状态。",
  link_unavailable: "该链接尚不能对应到明确登记的资料，请核对引用目标。",
  link_expired: "这次预览的链接已失效，请关闭后重新打开正文。",
  unsupported_link: "该链接格式暂不支持；原文标签仍予保留。",
  ambiguous_target: "引用对应多个已登记单元，需先明确目标，不能自动选一个。",
  unregistered_target: "引用目标尚未明确登记，不按同名文件猜测打开位置。",
  unregistered_image: "图片未在当前论文单元中明确登记。",
  ambiguous_image: "图片对应多个已登记资产，暂不能确定展示哪一份。",
  cross_paper_image: "图片属于其他论文单元，不能自动混入当前正文。",
  unsupported_image: "图片格式未通过本地栅格图片安全检查。",
  image_too_large: "图片尺寸过大，暂不能安全显示。",
  image_unavailable: "已登记图片暂不能在当前阅读范围中读取。",
  media_expired: "图片预览已失效，请关闭后重新打开正文。",
  zotflow_unavailable: "ZotFlow 本地阅读条件未通过验证，请检查版本、启用状态和本地 PDF 设置。",
  reader_unverified: "当前阅读入口尚未通过本机验证，请刷新资产或检查阅读器。",
};
function readerReason(code) { return readerReasons[code] || readerReasons.reader_unverified; }

function notice(message = "", error = false, owner = null) {
  noticeOwner = owner;
  $("notice").textContent = message;
  $("notice").hidden = !message;
  $("notice").classList.toggle("error", error);
}
async function api(path, payload) {
  const response = await fetch(path, {
    method: payload === undefined ? "GET" : "POST",
    headers: {Authorization: "Bearer " + token, ...(payload === undefined ? {} : {"Content-Type": "application/json"})},
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({error: "服务请求失败"}));
    const error = new Error(problem.error || "服务请求失败");
    error.status = response.status;
    error.code = problem.code;
    throw error;
  }
  return response.json();
}
const vaultIssueLabels = {
  "symlink-ignored": "符号链接中的内容已排除，不会读取链接指向的其他目录。",
  "preview-limit": "文档已列出；由于大小限制，本次未检查全部内容。",
  "legacy-link": "发现旧端口链接，需要核实原文身份后再预览替换。",
  "machine-marker": "发现机器标记，可按已认可的正文格式另行整理。",
  "unsafe-manifest": "领域清单暂不能安全读取。普通文档仍可阅读，论文引用需先核对清单。",
  "invalid-manifest": "领域清单格式有误，需要修正后才能核验论文归属。",
  "inspection-truncated": "本次检查未覆盖全部内容。可以选择更小的目录继续检查。",
  "ownership-not-registered": "文档现在可以阅读；正式引用论文前，还需登记领域并确认论文归属。",
  "source-not-attached": "已发现领域清单。先连接已有身份，再检查论文归属。",
  "ownership-needs-review": "领域声明、论文归属或相关文件的可用性需要核对。",
  "provider-unavailable": "已有论文登记暂不可读。原登记保持原样，需核对后才能引用论文。",
  "no-declared-papers": "尚无已核验的论文单元；普通文档仍可阅读。",
  "format-not-verified": "本次未验证内容更新条件。已有正文和 Canvas 保留，修改时另行检查格式与归属。",
};
const vaultDiagnosticLabels = {
  "The selected folder has conflicting registered identities.": "所选目录存在冲突的登记身份，需要先解决冲突。",
  "The existing connection is disabled or does not allow reading.": "现有连接已停用或未允许读取，需要先核对访问设置。",
  "The portable Source identity is registered to another folder.": "这个来源身份已登记在另一目录，需要先确认正确位置。",
  "The selected folder already has another Source identity.": "所选目录已有另一个来源身份，需要先核对。",
  "The connected folder is unavailable, changed or outside this environment.": "目录暂不可用、位置已变化，或不在当前环境允许的范围内。",
};
function vaultMessage(issue) {
  if (typeof issue === "string") return vaultDiagnosticLabels[issue] || (/\p{Script=Han}/u.test(issue) ? issue : "这项检查需要进一步核对。");
  const message = vaultIssueLabels[issue?.code] || "这项检查需要进一步核对。";
  return [issue?.path, message].filter(Boolean).join(" · ");
}
function vaultFailure(error) {
  if (error.code === 6 || error.code === "6") return "连接可能已经写入，但尚不能确认保存结果。请重新读取连接列表，核对后再操作。";
  if (error.code === "cancelled") return "已取消选择，文件未变化。";
  if (error.status === 401) return "当前会话已失效，请重新打开本次服务的完整地址。";
  if (error.status === 409) return "目录或登记在检查后发生了变化。请重新选择并检查；当前研究草稿仍保留。";
  if (error.status === 403) return "所选目录未通过当前环境的访问检查，请核对允许范围和目录状态。";
  if (error.status === 404) return "当前连接或文档暂不可用，请重新读取列表。";
  return "目录选择或检查未完成，请核对目录后重试。";
}
function vaultError(message = "") {
  $("vault-error").textContent = message;
  $("vault-error").hidden = !message;
}
function setVaultBusy(busy) {
  vaultBusy = busy;
  $("add-vault").disabled = busy;
  $("vault-connect").disabled = busy || !vaultCandidate || !!vaultCandidate.blockers?.length
    || vaultCandidate.layers?.readable?.status !== "available";
  $("vault-adjustments").disabled = busy || !vaultCandidate;
  for (const id of ["close-vault", "vault-cancel"]) $(id).disabled = busy;
  $("vault-dialog").setAttribute("aria-busy", String(busy));
}
async function loadEnvironment() {
  const badge = $("environment-label");
  try {
    const environment = await api("/api/environment");
    const test = environment.mode === "test";
    badge.textContent = test ? "测试环境" : environment.mode === "personal" ? "日常环境" : "环境未确认";
    badge.className = "environment-badge" + (test ? " test" : environment.mode === "personal" ? "" : " unavailable");
    $("environment-root").textContent = environment.root_name || "";
    $("environment-root").title = environment.root_name || "";
    $("environment-version").textContent = environment.version ? "v" + environment.version : "版本未确认";
  } catch (_error) {
    badge.textContent = "环境未确认"; badge.className = "environment-badge unavailable";
    $("environment-version").textContent = "";
  }
}
async function loadVaultConnections() {
  const generation = ++vaultListGeneration;
  try {
    const listing = await api("/api/vaults");
    if (generation !== vaultListGeneration) return;
    const host = $("vault-connections"); host.replaceChildren();
    for (const connection of listing.connections || []) {
      const button = node("button", undefined, "vault-connection"), description = node("span");
      const title = connection.title || connection.name || "已连接目录";
      description.append(node("strong", title));
      const unavailable = connection.status === "unavailable";
      const fields = connection.fields || [];
      description.append(node("small", unavailable ? "暂不可用 · 查看诊断" : fields.length ? fields.length + " 个领域 · 只读浏览" : "已连接 · 只读浏览"));
      button.append(node("span", "▱", "vault-symbol"), description);
      button.onclick = () => browseVault(connection);
      host.append(button);
    }
    const diagnostics = (listing.diagnostics || []).map(vaultMessage).filter(Boolean);
    $("vault-list-state").textContent = diagnostics.join(" ") || (listing.connections?.length
      ? "论文引用通过下方“引用论文单元”添加。" : "尚无连接。选择 Vault 或目录后先检查，再确认接入。");
  } catch (error) {
    if (generation !== vaultListGeneration) return;
    $("vault-list-state").textContent = error.status === 404 ? "当前服务尚未提供 Vault 接入。" : "知识库连接暂不能读取，请重新读取。";
  }
}
function renderVaultInspection(inspection) {
  vaultCandidate = inspection;
  $("vault-title").textContent = inspection.title || "检查所选目录";
  $("vault-state").textContent = "检查结果按功能分别说明。只读连接保留现有文档和格式；论文引用与插件维护有各自的条件。";
  const layers = $("vault-layers"); layers.replaceChildren();
  const titles = {readable: "安全阅读", referenceable: "论文单元引用", manageable: "插件维护"};
  const statusLabels = {available: "可用", ready: "可用", "needs-registration": "需要登记", "needs-review": "需要审阅", unavailable: "暂不可用", blocked: "必须修复", incomplete: "尚不完整"};
  for (const [key, title] of Object.entries(titles)) {
    const layer = inspection.layers?.[key] || {status: "needs-review", issues: []};
    const card = node("section", undefined, "vault-layer"), heading = node("div", undefined, "vault-layer-heading");
    const good = ["available", "ready"].includes(layer.status);
    heading.append(node("span", title), node("span", statusLabels[layer.status] || "需要检查", "vault-layer-status" + (good ? "" : ["blocked", "unavailable"].includes(layer.status) ? " blocked" : " pending")));
    card.append(heading);
    if (layer.issues?.length) {
      const issues = node("ul");
      for (const issue of layer.issues) issues.append(node("li", vaultMessage(issue)));
      card.append(issues);
    }
    layers.append(card);
  }
  const layerMessages = new Set(Object.values(inspection.layers || {}).flatMap((layer) => (layer.issues || []).map(vaultMessage)));
  const diagnostics = [...new Set([...(inspection.blockers || []), ...(inspection.diagnostics || []), ...(inspection.issues || [])]
    .map(vaultMessage).filter((message) => message && !layerMessages.has(message)))];
  const host = $("vault-diagnostics"); host.replaceChildren();
  if (diagnostics.length) {
    const list = node("ul", undefined, "vault-diagnostic-list");
    for (const diagnostic of diagnostics) list.append(node("li", diagnostic));
    host.append(list);
  }
  renderVaultChanges(inspection.changes || []);
  setVaultBusy(false);
}
function renderVaultChanges(changes) {
  const host = $("vault-change-list"); host.replaceChildren();
  if (!changes.length) return host.append(node("p", "当前没有需要预览的文件调整。", "form-hint"));
  const operations = {
    create: "新增", update: "更新", register: "登记", attach: "连接", review: "人工审阅", preserve: "保留",
    "connect-read-only": "登记只读连接", "plan-registration": "准备领域登记",
    "review-manifest": "检查领域清单", "review-link": "核对原文链接", "review-format": "核对正文格式",
  };
  const reasons = {
    "connect-read-only": "在本机记住这个目录的只读连接。原有文件保持原样。",
    "plan-registration": "正式引用论文时，再选择领域与入口文档并建立登记；当前可先只读连接。",
    "review-manifest": "先核对现有领域清单。确认前不重建身份或修改清单。",
    "review-link": "核实原文或附件身份后，再预览稳定链接的替换；当前链接保留。",
    "review-format": "按已认可的正文格式核对机器标记，另行预览修改；原文与 Canvas 保留。",
  };
  for (const change of changes) {
    const card = node("div", undefined, "vault-change");
    const path = change.path === "host-registry" ? "本机连接登记" : change.path || change.title || "登记信息";
    card.append(node("strong", (operations[change.operation] || "检查") + " · " + path), node("small", reasons[change.operation] || "具体修改需核对后另行处理。"));
    host.append(card);
  }
}
async function chooseVault() {
  if (vaultBusy) return;
  const generation = ++vaultGeneration;
  vaultCandidate = null; vaultError();
  $("vault-title").textContent = "添加 Vault/目录";
  $("vault-state").textContent = "请在系统文件选择器中选择 Vault 或其中的目录。此时不会改写文档。";
  $("vault-layers").replaceChildren(); $("vault-diagnostics").replaceChildren();
  $("vault-changes").hidden = true; $("vault-change-list").replaceChildren();
  if (!$("vault-dialog").open) $("vault-dialog").showModal();
  setVaultBusy(true);
  try {
    const inspection = await api("/api/vaults/choose", {});
    if (generation !== vaultGeneration || !$("vault-dialog").open) return;
    if (inspection.cancelled) { $("vault-state").textContent = "已取消选择，连接和文件均未变化。"; return; }
    renderVaultInspection(inspection);
  } catch (error) {
    if (generation === vaultGeneration && $("vault-dialog").open) {
      $("vault-state").textContent = "所选目录尚未连接。";
      vaultError(vaultFailure(error));
    }
  } finally { if (generation === vaultGeneration) setVaultBusy(false); }
}
async function previewVaultAdjustments() {
  if (vaultBusy || !vaultCandidate) return;
  const generation = vaultGeneration, candidate = vaultCandidate;
  setVaultBusy(true); vaultError();
  try {
    const inspection = await api("/api/vaults/preview", {candidate_id: candidate.candidate_id});
    if (generation !== vaultGeneration || !$("vault-dialog").open) return;
    renderVaultInspection(inspection); $("vault-changes").hidden = false;
  } catch (error) {
    if (generation === vaultGeneration) vaultError(vaultFailure(error));
  } finally { if (generation === vaultGeneration) setVaultBusy(false); }
}
async function connectVault() {
  if (vaultBusy || !vaultCandidate || $("vault-connect").disabled) return;
  const generation = vaultGeneration, candidate = vaultCandidate;
  setVaultBusy(true); vaultError();
  try {
    await api("/api/vaults/connect", {candidate_id: candidate.candidate_id, expected_revision: candidate.revision});
    if (generation !== vaultGeneration) return;
    $("vault-dialog").close(); vaultCandidate = null;
    await loadVaultConnections();
    // Source selection uses the refreshed registry, not another research-model load.
  } catch (error) {
    if (generation === vaultGeneration) vaultError(vaultFailure(error));
  } finally { if (generation === vaultGeneration) setVaultBusy(false); }
}
async function browseVault(connection) {
  const generation = ++vaultDocumentGeneration;
  $("vault-documents-title").textContent = connection.title || connection.name || "知识库资料";
  const list = $("vault-document-list"), body = $("vault-document-body");
  list.replaceChildren(node("p", "正在读取文档清单…", "preview-message"));
  body.replaceChildren(node("p", "选择一份文档阅读。", "preview-message"));
  if (!$("vault-documents").open) $("vault-documents").showModal();
  try {
    const result = await api("/api/vaults/" + encodeURIComponent(connection.connection_id) + "/documents");
    if (generation !== vaultDocumentGeneration || !$("vault-documents").open) return;
    list.replaceChildren();
    for (const document of result.documents || []) {
      const relative = typeof document === "string" ? document : document.relative_path;
      const button = node("button", relative);
      button.onclick = () => previewVaultDocument(connection.connection_id, relative, button);
      list.append(button);
    }
    if (!result.documents?.length) list.append(node("p", "当前没有可安全预览的 Markdown 文档。", "preview-message"));
    for (const diagnostic of result.diagnostics || []) list.append(node("p", vaultMessage(diagnostic), "preview-message"));
  } catch (error) {
    if (generation === vaultDocumentGeneration) list.replaceChildren(node("p", vaultFailure(error), "preview-message"));
  }
}
async function previewVaultDocument(connectionId, relativePath, button) {
  const generation = ++vaultDocumentGeneration, body = $("vault-document-body");
  body.replaceChildren(node("p", "正在读取文档…", "preview-message"));
  for (const entry of $("vault-document-list").querySelectorAll("button")) entry.classList.toggle("selected", entry === button);
  try {
    const result = await api("/api/vaults/document-preview", {connection_id: connectionId, relative_path: relativePath});
    if (generation !== vaultDocumentGeneration || !$("vault-documents").open) return;
    body.replaceChildren(); renderMarkdown(body, result.text || "", [], []);
  } catch (error) {
    if (generation === vaultDocumentGeneration) body.replaceChildren(node("p", vaultFailure(error), "preview-message"));
  }
}
function status(text, state) {
  $("status").textContent = text;
  $("status-dot").className = "status-dot" + (state ? " " + state : "");
}
function markDirty() {
  dirty = true;
  $("save").disabled = false;
  $("draft-label").hidden = false;
  status("有未保存修改", "dirty");
}
function valueLabel(dimension, value) {
  const defined = (dimension.values || []).find((v) => v.id === value);
  if (defined) return defined.label;
  if (dimension.kind === "reference") return data.works.find((w) => w.id === value)?.title || String(value);
  return String(value);
}
function values(value) { return Array.isArray(value) ? value : value === undefined || value === null ? [] : [value]; }
function supportsValueSorting(dimension) {
  return dimension.multiple === false && ["text", "number", "date"].includes(dimension.kind);
}
function referenceOptions(dimension) {
  const options = new Map((dimension.values || []).map((entry) => [entry.id, entry]));
  for (const work of data.works) if (!options.has(work.id)) options.set(work.id, {id: work.id, label: work.title});
  return [...options.values()];
}
function dimensionsText(record, work) {
  return data.dimensions.map((dimension) => {
    const picked = (dimension.scope === "work" ? work.attributes : record?.dimensions || {})[dimension.id];
    const label = dimension.label + (dimension.unit ? "（" + dimension.unit + "）" : "");
    return values(picked).length ? label + "：" + values(picked).map((v) => valueLabel(dimension, v)).join("、") : "";
  }).filter(Boolean).join("\n");
}

async function load(force = false, discardConfirmed = false) {
  if (saveBusy) return notice("正在保存当前修改，请稍后再编辑。");
  if (formBusy || $("editor").open) return notice("请先完成或取消当前表单，再重新读取。");
  if (dirty && force && !discardConfirmed) {
    if (!$("reload-confirm").open) $("reload-confirm").showModal();
    return;
  }
  const base = data, baseRevision = revision, wasDirty = dirty;
  try {
    const state = await api("/api/state");
    if (data !== base || revision !== baseRevision || dirty !== wasDirty ||
        saveBusy || formBusy || $("editor").open) return;
    data = state.data;
    revision = state.revision;
    dirty = false;
    readOnly = state.read_only === true;
    for (const id of ["save", "save-view", "add-work", "add-dimension", "add-edge", "add-record"]) $(id).hidden = readOnly;
    document.querySelector(".center-footer").textContent = readOnly
      ? "读取同一论文包 · 原文件保持原样 · 研究关系尚未编辑"
      : "资料保持单一入口 · 关系与评价可编辑 · 原有论文包保持原样";
    $("save").disabled = true;
    $("draft-label").hidden = true;
    status(readOnly ? "现有论文包 · 只读浏览" : revision ? "知识库已连接" : "尚未保存探索清单");
    notice((state.diagnostics || []).join(" "));
    renderFilters();
    renderViews();
    await runQuery();
    if (readOnly && !selected && matches?.works.length === 1) selectWork(matches.works[0].id);
  } catch (error) {
    if (data !== base || revision !== baseRevision || saveBusy || formBusy || $("editor").open) return;
    status("读取失败", "error");
    notice(error.status === 401 ? "会话凭证缺失或已失效。请使用命令行显示的完整地址重新打开。" : error.message, true);
  }
}
async function save() {
  if (saveBusy) return notice("正在保存当前修改，请稍后再编辑。");
  if (formBusy || $("editor").open) return notice("请先完成或取消当前表单，再保存。");
  if (!dirty) return;
  const base = data, baseRevision = revision, button = $("save");
  saveBusy = true; button.disabled = true; button.textContent = "正在保存…";
  button.setAttribute("aria-busy", "true"); status("正在保存修改");
  try {
    const state = await api("/api/save", {data: base, expected_revision: baseRevision});
    if (data !== base || revision !== baseRevision) {
      if (revision === baseRevision) { revision = state.revision; dirty = true; }
      status("较早修改已保存，当前内容仍保留", "dirty");
      notice("保存期间页面内容发生变化，未覆盖当前内容；请核对后再保存。");
      return;
    }
    data = state.data; revision = state.revision; dirty = false;
    $("save").disabled = true; $("draft-label").hidden = true;
    status("修改已保存"); notice("已保存关系和定位清单，原有论文文件未改动。");
    await runQuery();
  } catch (error) {
    notice(error.status === 409 ? "文件已被其他编辑器修改。你的修改仍保留在页面中；请先核对差异，再重新读取。" : error.message, true);
    status("保存未完成", "error");
  } finally {
    saveBusy = false; button.disabled = !dirty; button.textContent = "保存修改";
    button.removeAttribute("aria-busy");
  }
}
function renderFilters() {
  const target = $("filters"); target.replaceChildren();
  for (const dimension of data.dimensions) {
    const group = node("div", undefined, "filter-group");
    const heading = node("div", undefined, "filter-heading");
    const edit = node("button", dimension.label, "text-button");
    edit.title = readOnly ? "维度筛选" : "编辑维度定义"; edit.onclick = () => { if (!readOnly) editDimension(dimension); };
    heading.append(edit);
    const mode = node("select"); mode.setAttribute("aria-label", dimension.label + "匹配方式");
    for (const [value, label] of [["any", "满足任一"], ["all", "同时满足全部"]]) {
      const option = node("option", label); option.value = value; mode.append(option);
    }
    mode.value = selection.filters[dimension.id]?.mode || "any";
    mode.onchange = () => {
      if (selection.filters[dimension.id]) selection.filters[dimension.id].mode = mode.value;
      scheduleQuery();
    };
    heading.append(mode); group.append(heading);
    let possible = dimension.values || [];
    if (dimension.kind === "reference") possible = referenceOptions(dimension);
    if (!possible.length && dimension.kind !== "enum" && dimension.kind !== "reference") {
      const recorded = new Set();
      for (const item of dimension.scope === "work" ? data.works : data.records) {
        for (const value of values((dimension.scope === "work" ? item.attributes : item.dimensions)[dimension.id])) recorded.add(value);
      }
      possible = [...recorded].map((value) => ({id: value, label: String(value)}));
    }
    const choices = node("div", undefined, "filter-value-list");
    for (const entry of possible) {
      const label = node("label", undefined, "filter-pill");
      const input = node("input"); input.type = "checkbox";
      input.checked = selection.filters[dimension.id]?.values?.includes(entry.id) || false;
      input.onchange = () => {
        const selectedValues = [...choices.querySelectorAll("input:checked")].map((i) => possible[Number(i.dataset.index)].id);
        if (selectedValues.length) selection.filters[dimension.id] = {mode: mode.value, values: selectedValues};
        else delete selection.filters[dimension.id];
        scheduleQuery();
      };
      input.dataset.index = String(possible.indexOf(entry));
      label.append(input, document.createTextNode(entry.label)); choices.append(label);
    }
    group.append(choices);
    if (!possible.length) group.append(node("p", readOnly ? "尚未录入维度取值" : "暂无取值 · 点击维度名称补充定义", "filter-empty"));
    target.append(group);
  }
  const sort = $("sort"); sort.replaceChildren();
  for (const [id, label] of [["year", "发表时间"], ["title", "标题"], ...data.dimensions.filter((d) => d.sortable && supportsValueSorting(d)).map((d) => [d.id, d.label])]) {
    const option = node("option", label); option.value = id; sort.append(option);
  }
  sort.value = selection.sort_by || "year";
  $("search").value = selection.text || "";
  $("descending").checked = !!selection.descending;
  $("context").checked = selection.include_context !== false;
}
function renderViews() {
  const menu = $("views"); menu.replaceChildren();
  const initial = node("option", "选择一个视图…"); initial.value = ""; menu.append(initial);
  for (const view of data.views) { const option = node("option", view.title); option.value = view.id; menu.append(option); }
}
function scheduleQuery() { ++queryGeneration; clearTimeout(queryTimer); queryTimer = setTimeout(runQuery, 200); }
async function runQuery() {
  const generation = ++queryGeneration, base = data, baseRevision = revision;
  try {
    // Query the displayed model, never mix a newer file with an older editor.
    const result = await api("/api/query", {...selection, _draft: base});
    if (generation !== queryGeneration || data !== base || revision !== baseRevision) return;
    matches = result; matchesGeneration = generation;
    if (noticeOwner === "query") notice();
    renderMatches();
  } catch (error) {
    if (generation === queryGeneration && data === base && revision === baseRevision) notice(error.message, true, "query");
  }
}
function renderMatches() {
  $("result-count").textContent = String(matches.works.length);
  const results = $("results"); results.replaceChildren();
  for (const work of matches.works) {
    const button = node("button", undefined, "result-card" + (selected === work.id ? " selected" : ""));
    button.append(node("strong", work.title), node("span", [work.year, workKinds[work.kind] || work.kind].filter(Boolean).join(" · "), "result-meta"));
    button.onclick = () => selectWork(work.id); results.append(button);
  }
  if (!matches.works.length) results.append(node("p", data.works.length ? "没有满足这组联合条件的工作。可以减少筛选条件。" : "尚未引用论文单元。点击“引用论文单元”，从已登记知识领域选择完整单元。", "empty"));
  $("caption").textContent = `${matches.works.length} 项命中 · ${(matches.context_work_ids || []).length} 项上下文 · ${matches.records.length} 条联合条件记录`;
  renderGraph(); renderTable(); renderDetails();
}
function selectWork(id) { selected = id; renderMatches(); }

function svg(tag, attrs = {}, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
  if (text !== undefined) element.textContent = text;
  return element;
}
function renderGraph() {
  const graph = $("graph"); graph.replaceChildren();
  const hitIds = new Set(matches.works.map((w) => w.id));
  const included = new Set([...hitIds, ...(matches.context_work_ids || [])]);
  const works = data.works.filter((w) => included.has(w.id));
  const edges = matches.edges.filter((e) => included.has(e.from_id) && included.has(e.to_id));
  if (!works.length) { graph.append(node("p", "在左侧选择研究范围，或引用已有论文单元。", "empty")); return; }
  const rank = Object.fromEntries(works.map((w) => [w.id, 0]));
  const directional = edges.filter((edge) => !["competes", "context"].includes(edge.kind));
  const indegree = Object.fromEntries(works.map((w) => [w.id, 0]));
  directional.forEach((edge) => indegree[edge.to_id]++);
  const queue = works.filter((work) => indegree[work.id] === 0).map((work) => work.id);
  const visited = new Set();
  for (let index = 0; index < queue.length; index++) {
    const id = queue[index]; visited.add(id);
    for (const edge of directional.filter((edge) => edge.from_id === id)) {
      rank[edge.to_id] = Math.max(rank[edge.to_id], rank[id] + 1);
      if (--indegree[edge.to_id] === 0) queue.push(edge.to_id);
    }
  }
  const cycleAffected = works.filter((work) => !visited.has(work.id));
  if (cycleAffected.length) {
    // Cycles have no topological order: retain every node and edge, show the limitation.
    const nextRank = Math.max(...Object.values(rank)) + 1;
    cycleAffected.forEach((work, index) => rank[work.id] = nextRank + index);
    graph.append(node("p", "部分关系包含循环，无法按继承顺序分层；这些节点暂按登记顺序展开，全部关系仍保留。", "form-hint"));
  }
  const columns = new Map();
  for (const work of works) { const level = rank[work.id]; if (!columns.has(level)) columns.set(level, []); columns.get(level).push(work); }
  const positions = new Map(); const cardW = 206, cardH = 78, columnGap = 106, rowGap = 58;
  const height = Math.max(330, ...[...columns.values()].map((items) => items.length * (cardH + rowGap) + 30));
  const width = (Math.max(...Object.values(rank)) + 1) * (cardW + columnGap) - columnGap + 30;
  for (const [level, items] of columns) {
    items.forEach((work, index) => positions.set(work.id, {x: 15 + level * (cardW + columnGap), y: 15 + index * (cardH + rowGap)}));
  }
  const drawing = svg("svg", {width: Math.max(510, width), height, viewBox: `0 0 ${Math.max(510, width)} ${height}`, role: "img", "aria-label": "研究关系路径"});
  const defs = svg("defs");
  const marker = svg("marker", {id: "arrow", markerWidth: 7, markerHeight: 7, refX: 6, refY: 3.5, orient: "auto"});
  marker.append(svg("path", {d: "M0,0 L7,3.5 L0,7", fill: "none", stroke: "#9faf9f"})); defs.append(marker); drawing.append(defs);
  for (const edge of edges) {
    const a = positions.get(edge.from_id), b = positions.get(edge.to_id);
    const forward = b.x > a.x;
    const startX = a.x + (forward ? cardW : cardW / 2), startY = a.y + (forward ? cardH / 2 : cardH);
    const endX = b.x + (forward ? 0 : cardW / 2), endY = b.y + (forward ? cardH / 2 : 0);
    const middleX = (startX + endX) / 2;
    const route = forward ? `M${startX} ${startY} H${middleX} V${endY} H${endX}` : `M${startX} ${startY} V${(startY + endY) / 2} H${endX} V${endY}`;
    const context = !hitIds.has(edge.from_id) || !hitIds.has(edge.to_id);
    const path = svg("path", {d: route, class: "graph-edge" + (context ? " context-edge" : "")});
    if (edge.kind !== "competes") path.setAttribute("marker-end", "url(#arrow)");
    drawing.append(path);
    const label = svg("text", {x: forward ? middleX : startX + 7, y: (startY + endY) / 2 - 7, "text-anchor": forward ? "middle" : "start", class: "graph-label", tabindex: "0"}, edge.label || edgeKinds[edge.kind]);
    label.onclick = () => editEdge(edge); label.onkeydown = (event) => { if (event.key === "Enter") editEdge(edge); }; drawing.append(label);
  }
  for (const work of works) {
    const position = positions.get(work.id), context = !hitIds.has(work.id);
    const group = svg("g", {class: "graph-click", tabindex: "0", role: "button", "aria-label": work.title});
    group.append(svg("rect", {...position, width: cardW, height: cardH, rx: 8, class: "graph-node" + (selected === work.id ? " selected" : "") + (context ? " context-node" : "")}));
    const title = [...work.title]; const lineLength = 21;
    for (let line = 0; line < Math.min(2, Math.ceil(title.length / lineLength)); line++) {
      const value = title.slice(line * lineLength, (line + 1) * lineLength).join("") + (line === 1 && title.length > 42 ? "…" : "");
      group.append(svg("text", {x: position.x + 12, y: position.y + 23 + line * 17, class: "graph-text" + (context ? " context-text" : "")}, value));
    }
    group.append(svg("text", {x: position.x + 12, y: position.y + 63, class: "graph-small"}, [work.year, context ? "路径上下文" : workKinds[work.kind]].filter(Boolean).join(" · ")));
    group.onclick = () => selectWork(work.id); group.onkeydown = (event) => { if (event.key === "Enter") selectWork(work.id); }; drawing.append(group);
  }
  graph.append(drawing);
}
function renderTable() {
  const host = $("comparison"); host.replaceChildren();
  const table = node("table", undefined, "compare-table"), header = node("tr");
  for (const label of ["工作与研究定位", "比较条件", "结果", "评价与适用边界", "依据与来源"]) header.append(node("th", label));
  const thead = node("thead"); thead.append(header); table.append(thead);
  const body = node("tbody");
  for (const record of matches.records) {
    const work = data.works.find((w) => w.id === record.work_id); if (!work) continue;
    const row = node("tr"), title = node("td"), button = node("button", work.title);
    button.onclick = () => selectWork(work.id);
    title.append(button, node("small", dimensionsText(record, work)));
    row.append(title, node("td", Object.entries(record.conditions).map(([key, value]) => key + "：" + value).join("\n") || "条件未记录"), node("td", record.result || "结果未记录"), node("td", record.assessment || "评价未记录"));
    const evidence = node("td"); evidence.append(node("small", origins[record.origin] || record.origin));
    for (const assetId of record.evidence) {
      const found = findAsset(assetId); const link = node("button", found?.asset.label || assetId);
      if (found) link.onclick = () => openAsset(found.work.id, found.asset);
      evidence.append(link, node("br"));
    }
    if (!readOnly) { const edit = node("button", "编辑记录"); edit.onclick = () => editRecord(record); evidence.append(edit); } row.append(evidence); body.append(row);
  }
  table.append(body); host.append(table);
  if (!matches.records.length) host.append(node("p", "当前范围没有研究记录。每条记录把同一组条件、结果和证据放在一起。", "empty"));
}
function findAsset(id) {
  for (const work of data.works) { const asset = work.assets.find((a) => a.id === id); if (asset) return {work, asset}; }
  return null;
}
function section(title) { const element = node("section", undefined, "detail-section"); element.append(node("h3", title)); return element; }
function renderDetails() {
  const host = $("details"); host.replaceChildren();
  const work = data.works.find((w) => w.id === selected);
  if (!work) {
    selected = null;
    const empty = node("div", undefined, "empty-detail"), button = node("button", "引用论文单元", "primary");
    button.id = "first-work"; button.onclick = referencePaperUnits;
    empty.append(node("span", "◇", "empty-symbol"), node("h2", "从一项论文单元开始"),
      node("p", "选择左侧工作或图中节点，查看研究定位、条件、结果与全部相关资产。"), button);
    host.append(empty); return;
  }
  host.append(node("div", [workKinds[work.kind], work.year].filter(Boolean).join(" / "), "detail-kicker"), node("h2", work.title, "detail-title"));
  if (work.summary) host.append(node("p", work.summary, "detail-summary"));
  const editRow = node("div", undefined, "detail-edit"); const edit = node("button", "编辑工作", "text-button"); edit.onclick = () => editWork(work);
  editRow.append(node("span", "资料入口与研究定位")); if (!readOnly) editRow.append(edit); host.append(editRow);
  const body = work.assets.find((asset) => ["analysis", "paper-analysis"].includes(asset.kind) && /\.md(?:#|$)/i.test(asset.uri));
  if (body) { const read = node("button", "阅读分析正文", "primary"); read.onclick = () => openAsset(work.id, body); host.append(read); }
  const positions = section("研究定位");
  const records = data.records.filter((r) => r.work_id === work.id);
  for (const dimension of data.dimensions) {
    const collected = dimension.scope === "work" ? values(work.attributes[dimension.id]) : [...new Set(records.flatMap((r) => values(r.dimensions[dimension.id])))];
    if (!collected.length) continue;
    const row = node("div", undefined, "position-row"), tags = node("span", undefined, "position-tags");
    collected.forEach((v) => tags.append(node("span", valueLabel(dimension, v), "tag")));
    row.append(node("span", dimension.label + (dimension.unit ? "（" + dimension.unit + "）" : "")), tags); positions.append(row);
  }
  positions.append(node("p", "定位汇总用于导航；联合条件请查看下面的独立研究记录。", "form-hint")); host.append(positions);
  const resources = section("相关资产"); const loading = node("p", "正在检查文件…", "form-hint"); resources.append(loading); host.append(resources);
  for (const diagnostic of work.asset_diagnostics || []) resources.append(node("p", diagnostic, "asset-unavailable"));
  const displayAssets = (items) => {
    if (selected !== work.id) return;
    loading.remove();
    if (!items.length) resources.append(node("p", "尚未关联资产。编辑工作可加入已有笔记、Canvas、PDF 或网页。", "form-hint"));
    for (const asset of items) {
      const card = node("div", undefined, "asset-card"), label = node("div", undefined, "asset-label");
      label.append(document.createTextNode(asset.label));
      const location = node("details", undefined, "asset-description");
      location.append(node("summary", asset.local ? "本地文件位置" : "来源地址"), node("span", asset.uri)); label.append(location); card.append(label);
      const actions = node("div", undefined, "asset-actions");
      if (asset.pending) card.append(node("span", "未保存 · 保存后检查文件状态", "asset-description"));
      else if (asset.available !== false) {
        if (!asset.local && /^https?:/.test(asset.uri)) {
          const link = node("a", "打开网页"); link.href = asset.uri; link.target = "_blank"; link.rel = "noopener noreferrer"; actions.append(link);
        } else {
          if (asset.local && !/\.canvas(?:#|$)/i.test(asset.uri)) { const preview = node("button", "预览"); preview.onclick = () => openAsset(work.id, asset); actions.append(preview); }
          if (asset.native_available !== false) {
            const native = node("button", /\.canvas(?:#|$)|\.md(?:#|$)/i.test(asset.uri) ? "Obsidian 打开" : "原生打开"); native.onclick = () => nativeOpen(work.id, asset.id); actions.append(native);
          }
        }
      }
      card.append(actions);
      if (!asset.local && !asset.pending) card.append(node("span", "外部入口 · 尚未验证网页或阅读器实际可用性", "asset-description"));
      if (asset.available === false) card.append(node("span", asset.local ? "文件缺失、不可读取或路径不安全，请核对已登记的相对路径。" : "链接暂不可用，请核对来源。", "asset-unavailable"));
      if (asset.native_available === false && asset.available !== false) {
        card.append(node("span", asset.native_reason_code ? readerReason(asset.native_reason_code) : "此资产不支持原生打开；文档或代码可使用安全预览。", "asset-description"));
        if (asset.native_reason) {
          const diagnostic = node("details", undefined, "asset-description");
          diagnostic.append(node("summary", "技术详情"), node("p", asset.native_reason)); card.append(diagnostic);
        }
      }
      resources.append(card);
    }
  };
  if (dirty) displayAssets(work.assets.map((a) => ({...a, local: !/^[a-z][a-z0-9+.-]*:/i.test(a.uri), pending: true})));
  else api("/api/assets/" + encodeURIComponent(work.id)).then(displayAssets).catch((error) => { loading.textContent = error.message; });
  const research = section("条件、结果与评价");
  const add = node("button", "＋ 为这项工作新增记录", "text-button"); add.onclick = () => editRecord(null, work.id); if (!readOnly) research.append(add);
  if (readOnly && !records.length) research.append(node("p", "本次只读取已有论文包，尚未录入外围定位和比较记录；不从正文自动编造评价。", "form-hint"));
  for (const record of records) {
    const card = node("article", undefined, "record-card"), head = node("div", undefined, "record-head"), edit = node("button", "编辑", "text-button"); edit.onclick = () => editRecord(record);
    head.append(node("span", origins[record.origin] || record.origin)); if (!readOnly) head.append(edit); card.append(head);
    const dimensions = dimensionsText(record, {...work, attributes: {}}); if (dimensions) card.append(node("p", dimensions, "record-field"));
    const conditions = node("div", undefined, "record-conditions");
    Object.entries(record.conditions).forEach(([key, value]) => conditions.append(node("span", key + "：" + value))); card.append(conditions);
    for (const [label, value] of [["结果", record.result], ["评价与适用边界", record.assessment]]) {
      const field = node("p", undefined, "record-field"); field.append(node("b", label), document.createTextNode(value || "未记录")); card.append(field);
    }
    for (const id of record.evidence) { const found = findAsset(id); if (found) { const link = node("button", "依据 · " + found.asset.label, "text-button"); link.onclick = () => openAsset(found.work.id, found.asset); card.append(link); } }
    research.append(card);
  }
  host.append(research);
  const relations = section("相关路径");
  for (const edge of data.edges.filter((e) => e.from_id === work.id || e.to_id === work.id)) {
    const other = data.works.find((w) => w.id === (edge.from_id === work.id ? edge.to_id : edge.from_id));
    const button = node("button", undefined, "relation-card");
    button.append(document.createTextNode((edge.kind === "competes" ? "↔ " : edge.from_id === work.id ? "→ " : "← ") + (other?.title || "未知工作")), node("small", (edge.label || edgeKinds[edge.kind]) + (edge.explanation ? " · " + edge.explanation : "")));
    button.onclick = () => editEdge(edge); relations.append(button);
  }
  host.append(relations);
}

async function nativeOpen(workId, assetId) {
  if (dirty) return notice("请先保存修改，再打开新增或修改后的资产。");
  try {
    const listing = await api("/api/assets/" + encodeURIComponent(workId));
    const asset = listing.find((entry) => entry.id === assetId);
    if (dirty) return notice("请先保存修改，再打开新增或修改后的资产。");
    if (!asset || asset.native_available !== true) return notice(
      asset?.native_reason_code ? readerReason(asset.native_reason_code) : "当前资料尚不能在原生应用打开，请核对资料状态。", true);
    await api("/api/open", {work_id: workId, asset_id: assetId});
    notice("已提交原生打开请求；请在对应应用中查看。");
  } catch (error) { notice(error.code ? readerReason(error.code) : error.message, true); }
}
async function openReadingLink(linkId, button) {
  if (dirty) return notice("请先保存修改，再打开正文中的原文入口。");
  button.disabled = true;
  try {
    const available = await api("/api/reading-link/" + encodeURIComponent(linkId));
    if (!available.native_available) return notice(readerReason(available.native_reason_code), true);
    await api("/api/open-link", {link_id: linkId});
    notice("已提交原文定位请求；请在对应阅读器中核对页面或批注。");
  } catch (error) { notice(error.code ? readerReason(error.code) : error.message, true); }
  finally { button.disabled = false; }
}
async function openAsset(workId, asset) {
  if (/^https?:/.test(asset.uri)) { window.open(asset.uri, "_blank", "noopener,noreferrer"); return; }
  if (/^(obsidian|zotero):/.test(asset.uri) || /\.canvas(?:#|$)/i.test(asset.uri)) return nativeOpen(workId, asset.id);
  if (dirty) return notice("请先保存修改，再预览新增或修改后的资产。");
  clearPreview();
  const generation = previewGeneration, controller = new AbortController(), host = $("preview-body");
  previewController = controller;
  previewAsset = {workId, assetId: asset.id}; $("preview-title").textContent = asset.label;
  $("preview-native").disabled = asset.native_available === false;
  host.replaceChildren(node("p", "正在读取正文…", "preview-message"));
  if (!$("preview").open) $("preview").showModal();
  try {
    let response, previewDocument;
    if (/\.md(?:#|$)/i.test(asset.uri)) {
      previewDocument = await api(`/api/preview/${encodeURIComponent(workId)}/${encodeURIComponent(asset.id)}`);
    } else {
      response = await fetch(`/api/asset/${encodeURIComponent(workId)}/${encodeURIComponent(asset.id)}`, {
        headers: {Authorization: "Bearer " + token}, cache: "no-store", signal: controller.signal,
      });
      if (!response.ok) { const error = await response.json(); throw new Error(error.error); }
    }
    if (generation !== previewGeneration || controller.signal.aborted) return;
    const contentType = previewDocument ? "text/markdown" : (response.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
    if (previewImageTypes.has(contentType) || contentType === "application/pdf") {
      const blob = await response.blob();
      if (generation !== previewGeneration || controller.signal.aborted) return;
      blobUrl = URL.createObjectURL(blob);
      const media = node(previewImageTypes.has(contentType) ? "img" : "iframe"); media.src = blobUrl; media.title = asset.label;
      if (media.tagName === "IMG") media.alt = asset.label;
      host.replaceChildren(media);
    } else {
      const text = previewDocument?.text ?? await response.text();
      if (generation !== previewGeneration || controller.signal.aborted) return;
      host.replaceChildren();
      if (previewDocument) renderMarkdown(host, text, previewDocument.links || [], previewDocument.images || [], {generation, signal: controller.signal});
      else { const pre = node("pre"); pre.append(node("code", text)); host.append(pre); }
    }
  } catch (error) {
    if (generation !== previewGeneration || controller.signal.aborted) return;
    const message = error.code ? readerReason(error.code) : error.message;
    host.replaceChildren(node("p", message, "preview-message")); notice(message, true);
  }
}
function clearPreview() {
  ++previewGeneration;
  previewController?.abort(); previewController = null; previewAsset = null;
  if (blobUrl) URL.revokeObjectURL(blobUrl);
  blobUrl = null;
  for (const uri of previewBlobs) URL.revokeObjectURL(uri);
  previewBlobs.clear();
  $("preview-body").replaceChildren();
}
function displayText(text) {
  // Decode text entities without asking the browser to parse material HTML.
  return text.replace(/&(?:lt|gt|amp|quot|apos|#\d+|#x[\da-f]+);/gi, (entity) => {
    const names = {lt: "<", gt: ">", amp: "&", quot: '"', apos: "'"}, value = entity.slice(1, -1).toLowerCase();
    if (value in names) return names[value];
    const point = value.startsWith("#x") ? parseInt(value.slice(2), 16) : Number(value.slice(1));
    return point > 0 && point <= 0x10ffff && !(point >= 0xd800 && point <= 0xdfff) ? String.fromCodePoint(point) : entity;
  });
}
function previewFigure(entry, context) {
  const figure = node("figure", undefined, "preview-figure"), caption = node("figcaption", displayText(entry.label || "正文图片"));
  const message = node("p", entry.media_id ? "正在读取本地图片…" : readerReason(entry.reason_code || "image_unavailable") + "原图注保留。", "preview-media-state");
  figure.append(message, caption);
  if (!entry.media_id) { message.title = readerReason(entry.reason_code || "preview_unavailable"); return figure; }
  const current = () => context.generation === previewGeneration && !context.signal?.aborted;
  (async () => {
    try {
      const response = await fetch("/api/preview-media/" + encodeURIComponent(entry.media_id), {
        headers: {Authorization: "Bearer " + token}, cache: "no-store", signal: context.signal,
      });
      if (!response.ok) {
        const problem = await response.json().catch(() => ({}));
        throw new Error(readerReason(problem.code || "preview_unavailable"));
      }
      const contentType = (response.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
      if (!previewImageTypes.has(contentType)) throw new Error("图片格式未通过安全检查；原图注保留。");
      const blob = await response.blob();
      if (!current()) return;
      const uri = URL.createObjectURL(blob); previewBlobs.add(uri);
      const image = node("img"); image.alt = displayText(entry.label || "正文图片");
      image.onload = () => { if (current()) message.remove(); };
      image.onerror = () => {
        URL.revokeObjectURL(uri); previewBlobs.delete(uri); image.remove();
        if (current()) message.textContent = "本地图片未能显示；原图注保留。";
      };
      image.src = uri; figure.insertBefore(image, message);
    } catch (error) {
      if (current()) message.textContent = error.message || "本地图片暂不可用；原图注保留。";
    }
  })();
  return figure;
}
function renderMarkdown(host, text, links = [], images = [], context = {}) {
  // Only declared spans become links or images; unsupported material remains text.
  context = {generation: previewGeneration, signal: previewController?.signal, ...context};
  const validSpan = (entry) => Number.isInteger(entry.start) && Number.isInteger(entry.end) && entry.start >= 0 && entry.end > entry.start && entry.end <= text.length;
  const spans = [...links.filter(validSpan).map((entry) => ({...entry, image: false})), ...images.filter(validSpan).map((entry) => ({...entry, image: true}))].sort((a, b) => a.start - b.start || b.end - a.end);
  const at = new Map();
  let previousEnd = -1;
  for (const entry of spans) {
    if (entry.start < previousEnd) continue;
    at.set(entry.start, entry); previousEnd = entry.end;
  }
  const punctuation = (character) => {
    const code = character?.charCodeAt(0);
    return code >= 33 && code <= 47 || code >= 58 && code <= 64 || code >= 91 && code <= 96 || code >= 123 && code <= 126;
  };
  const codeEnd = (start, end) => {
    let size = 1; while (text[start + size] === "`") ++size;
    let next = start + size;
    while (next < end) {
      next = text.indexOf("`", next); if (next < 0 || next >= end) break;
      let length = 1; while (text[next + length] === "`") ++length;
      if (length === size) return {start: start + size, end: next, next: next + size};
      next += length;
    }
    return null;
  };
  const strongEnd = (start, end) => {
    for (let i = start; i < end - 1; ++i) {
      if (text[i] === "\\") { ++i; continue; }
      if (text[i] === "`") { const code = codeEnd(i, end); if (code) { i = code.next - 1; continue; } }
      if (text.slice(i, i + 2) === "**") return i;
    }
    return -1;
  };
  const emphasisEnd = (start, end) => {
    for (let i = start; i < end; ++i) {
      if (text[i] === "\\") { ++i; continue; }
      if (text[i] === "`") { const code = codeEnd(i, end); if (code) { i = code.next - 1; continue; } }
      if (text.slice(i, i + 2) === "**") { ++i; continue; }
      if (text[i] === "*" && !/\s/.test(text[i - 1])) return i;
    }
    return -1;
  };
  function appendLink(target, entry) {
    const label = displayText(entry.label || "链接");
    let web = null;
    if (entry.kind === "web") {
      try { const uri = new URL(entry.uri); if (["https:", "http:"].includes(uri.protocol) && !uri.username && !uri.password) web = uri.href; } catch (_) { /* Keep an invalid declaration readable. */ }
    }
    if (web) {
      const link = node("a", label); link.href = web; link.target = "_blank"; link.rel = "noopener noreferrer"; target.append(link);
    } else if (entry.kind === "native" && entry.link_id) {
      const link = node("button", label, "reading-link"); link.type = "button";
      link.onclick = (event) => { event.preventDefault(); event.stopPropagation(); openReadingLink(entry.link_id, link); };
      target.append(link);
    } else {
      const labelNode = node("span", label + "（链接暂不可用）", "reading-link-unavailable");
      labelNode.title = readerReason(entry.reason_code || "link_unavailable"); target.append(labelNode);
    }
  }
  function inline(target, start, end, depth = 0) {
    let plain = "";
    const flush = () => { if (plain) target.append(document.createTextNode(displayText(plain))); plain = ""; };
    for (let i = start; i < end;) {
      if (text[i] === "\\" && i + 1 < end && punctuation(text[i + 1])) { plain += text[i + 1]; i += 2; continue; }
      if (text[i] === "`") {
        const code = codeEnd(i, end);
        if (code) { flush(); target.append(node("code", text.slice(code.start, code.end))); i = code.next; continue; }
      }
      const entry = at.get(i);
      if (entry && entry.end <= end) {
        flush();
        if (entry.image) target.append(previewFigure(entry, context)); else appendLink(target, entry);
        i = entry.end; continue;
      }
      if (depth < 8 && text.slice(i, i + 2) === "**") {
        const close = strongEnd(i + 2, end);
        if (close > i + 2) { flush(); const strong = node("strong"); inline(strong, i + 2, close, depth + 1); target.append(strong); i = close + 2; continue; }
      }
      if (depth < 8 && text[i] === "*" && text[i - 1] !== "*" && text[i + 1] !== "*" && i + 1 < end && !/\s/.test(text[i + 1])) {
        const close = emphasisEnd(i + 1, end);
        if (close > i + 1) { flush(); const emphasis = node("em"); inline(emphasis, i + 1, close, depth + 1); target.append(emphasis); i = close + 1; continue; }
      }
      plain += text[i++];
    }
    flush();
  }
  let offset = 0;
  const lines = text.split("\n").map((raw) => {
    const line = {text: raw.replace(/\r$/, ""), start: offset}; offset += raw.length + 1; return line;
  });
  const trimAnchor = (line) => {
    const match = /(?:\s+|^)\^[\w-]+\s*$/.exec(line.text);
    return match ? {...line, text: line.text.slice(0, match.index)} : line;
  };
  const quotePrefix = (line) => /^ {0,3}>\s?/.exec(line.text);
  const listPrefix = (line) => /^\s{0,3}([-+*]|\d+[.)])\s+/.exec(line.text);
  const fenceMarker = (line) => /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line.text);
  const cells = (line) => {
    const result = [], value = line.text;
    let begin = /^\s*\|/.test(value) ? value.indexOf("|") + 1 : 0;
    for (let i = begin; i <= value.length; ++i) {
      if (value[i] === "\\") { ++i; continue; }
      if (i === value.length || value[i] === "|") {
        const cell = value.slice(begin, i), left = cell.length - cell.trimStart().length;
        result.push({text: cell.trim(), start: line.start + begin + left}); begin = i + 1;
      }
    }
    if (/\|\s*$/.test(value)) result.pop();
    return result;
  };
  const tableSeparator = (line) => line.text.includes("|") && cells(line).length > 1 && cells(line).every((cell) => /^:?-{3,}:?$/.test(cell.text));
  const tableStart = (rows, index) => index + 1 < rows.length && rows[index].text.includes("|") && tableSeparator(rows[index + 1]) && cells(rows[index]).length === cells(rows[index + 1]).length;
  function paragraph(target, group) {
    let block = null;
    for (const line of group) {
      const clean = trimAnchor(line), end = clean.start + clean.text.length;
      if (!clean.text.trim()) continue;
      let start = clean.start;
      const pictureSpans = spans.filter((entry) => entry.image && entry.start >= start && entry.end <= end && at.get(entry.start) === entry);
      for (const entry of pictureSpans) {
        if (entry.start > start) { if (!block) { block = node("p"); target.append(block); } inline(block, start, entry.start); }
        target.append(previewFigure(entry, context)); block = null; start = entry.end;
      }
      if (start < end) {
        if (!block) { block = node("p"); target.append(block); } else if (block.childNodes.length) block.append(document.createTextNode(" "));
        inline(block, start, end);
      }
    }
  }
  function blocks(target, rows) {
    for (let i = 0; i < rows.length;) {
      const line = trimAnchor(rows[i]);
      if (!line.text.trim()) { ++i; continue; }
      const marker = fenceMarker(line);
      if (marker) {
        const code = node("code"), pre = node("pre"); pre.append(code); target.append(pre); ++i;
        while (i < rows.length) {
          const close = fenceMarker(rows[i]);
          if (close && close[1][0] === marker[1][0] && close[1].length >= marker[1].length && !close[2].trim()) { ++i; break; }
          code.append(document.createTextNode(rows[i++].text + "\n"));
        }
        continue;
      }
      const quote = quotePrefix(line);
      if (quote) {
        const callout = /^ {0,3}>\s?\[!quote\]([+-])?(?:\s+(.*))?$/i.exec(line.text), quoted = [];
        if (callout) {
          const details = node("details", undefined, "quote-callout"), summary = node("summary");
          details.open = callout[1] === "+";
          if (callout[2]) inline(summary, line.start + line.text.length - callout[2].length, line.start + line.text.length);
          else summary.append(document.createTextNode("原文摘录"));
          details.append(summary); const body = node("div", undefined, "quote-callout-body"); details.append(body); target.append(details); ++i;
          while (i < rows.length && quotePrefix(rows[i])) { const prefix = quotePrefix(rows[i])[0].length; quoted.push({text: rows[i].text.slice(prefix), start: rows[i].start + prefix}); ++i; }
          blocks(body, quoted);
        } else {
          while (i < rows.length && quotePrefix(rows[i])) { const prefix = quotePrefix(rows[i])[0].length; quoted.push({text: rows[i].text.slice(prefix), start: rows[i].start + prefix}); ++i; }
          const block = node("blockquote"); target.append(block); blocks(block, quoted);
        }
        continue;
      }
      const heading = /^ {0,3}(#{1,6})\s+(.*)$/.exec(line.text);
      if (heading) { const block = node("h" + heading[1].length); inline(block, line.start + line.text.length - heading[2].length, line.start + line.text.length); target.append(block); ++i; continue; }
      if (tableStart(rows, i)) {
        const wrapper = node("div", undefined, "preview-table-wrap"), table = node("table"), head = node("thead"), body = node("tbody"), headers = cells(line), alignments = cells(rows[i + 1]);
        const row = node("tr");
        headers.forEach((cell, index) => {
          const th = node("th"); inline(th, cell.start, cell.start + cell.text.length);
          const alignment = alignments[index]?.text || ""; th.style.textAlign = alignment.startsWith(":") ? alignment.endsWith(":") ? "center" : "left" : alignment.endsWith(":") ? "right" : "left";
          row.append(th);
        });
        head.append(row); table.append(head, body); wrapper.append(table); target.append(wrapper); i += 2;
        while (i < rows.length && rows[i].text.trim() && rows[i].text.includes("|")) {
          const row = node("tr"), values = cells(trimAnchor(rows[i]));
          if (values.length !== headers.length) break;
          ++i;
          headers.forEach((_, index) => { const cell = values[index], td = node("td"); if (cell) inline(td, cell.start, cell.start + cell.text.length); row.append(td); }); body.append(row);
        }
        continue;
      }
      const list = listPrefix(line);
      if (list) {
        const ordered = /^\d/.test(list[1]), block = node(ordered ? "ol" : "ul");
        if (ordered) block.start = parseInt(list[1], 10); target.append(block);
        while (i < rows.length) {
          const current = trimAnchor(rows[i]), prefix = listPrefix(current);
          if (!prefix || /^\d/.test(prefix[1]) !== ordered) break;
          const item = node("li"); inline(item, current.start + prefix[0].length, current.start + current.text.length); block.append(item); ++i;
        }
        continue;
      }
      const group = [rows[i++]];
      while (i < rows.length && rows[i].text.trim() && !fenceMarker(rows[i]) && !quotePrefix(rows[i]) && !listPrefix(rows[i]) && !/^ {0,3}#{1,6}\s+/.test(rows[i].text) && !tableStart(rows, i)) group.push(rows[i++]);
      paragraph(target, group);
    }
  }
  let first = 0;
  if (lines[0]?.text.replace(/^\uFEFF/, "") === "---") {
    const close = lines.findIndex((line, index) => index > 0 && /^(---|\.\.\.)\s*$/.test(line.text));
    if (close > 0) first = close + 1;
  }
  blocks(host, lines.slice(first));
}

function field(label, initial = "", type = "text", hint) {
  const wrapper = node("label", undefined, "form-field"), input = node(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") input.type = type;
  input.value = initial ?? ""; wrapper.append(node("span", label), input);
  if (hint) wrapper.append(node("small", hint, "form-hint"));
  return {wrapper, input};
}
function choose(label, options, initial) {
  const wrapper = node("label", undefined, "form-field"), input = node("select");
  for (const [value, text] of options) { const option = node("option", text); option.value = value; input.append(option); }
  input.value = initial; wrapper.append(node("span", label), input); return {wrapper, input};
}
function dialog(title, render, submit) {
  if (readOnly) return notice("当前为已有论文包的只读浏览，不会修改文件或研究关系。");
  if (saveBusy) return notice("正在保存当前修改，请稍后再编辑。");
  if (formBusy) return notice("正在检查当前表单，请稍后再编辑。");
  $("editor-title").textContent = title; $("editor-fields").replaceChildren(); $("form-error").hidden = true;
  formBase = {data, revision}; formSubmit = submit; $("editor").showModal();
  Promise.resolve().then(() => render($("editor-fields"))).catch((error) => {
    if (formSubmit === submit && $("editor").open) { $("form-error").textContent = error.message; $("form-error").hidden = false; }
  });
}
function newId(prefix) { return prefix + "-" + crypto.randomUUID().slice(0, 8); }
function upsert(collection, item) { const i = collection.findIndex((existing) => existing.id === item.id); if (i < 0) collection.push(item); else collection[i] = item; }
function diagnosticText(entry) {
  if (typeof entry === "string") return entry;
  return entry?.message || entry?.reason || "部分资料暂无法核验。";
}
function referencePaperUnits() {
  let fields = [], units = [], choices = [], fieldChoice, ready = false, loading = true, requestGeneration = 0;
  dialog("引用已登记论文单元", async (host) => {
    host.append(node("p", "选择知识领域，再勾选完整论文单元。分析、Canvas、批注与其他已登记资产一并引用，不复制或修改论文包。", "form-hint"));
    fieldChoice = choose("选择知识领域", [["", "正在读取已登记知识领域…"]], "");
    fieldChoice.input.disabled = true;
    const diagnostics = node("div"), list = node("div"); host.append(fieldChoice.wrapper, diagnostics, list);
    const showDiagnostics = (entries) => entries.forEach((entry) => diagnostics.append(node("p", diagnosticText(entry), "form-hint")));
    fieldChoice.input.onchange = async () => {
      const generation = ++requestGeneration;
      ready = false; units = []; choices = []; diagnostics.replaceChildren(); list.replaceChildren();
      const selectedField = fields[Number(fieldChoice.input.value)];
      if (!fieldChoice.input.value || !selectedField) { loading = false; return; }
      loading = true; list.append(node("p", "正在读取完整论文单元…", "form-hint"));
      try {
        const response = await api("/api/unit-options", {source_id: selectedField.source_id, field_id: selectedField.field_id});
        if (generation !== requestGeneration || !list.isConnected) return;
        list.replaceChildren(); showDiagnostics(response.diagnostics || []); units = response.units || [];
        for (const unit of units) {
          const label = node("label", undefined, "check"), input = node("input"); input.type = "checkbox";
          label.append(input, node("span", unit.title), node("small", String(unit.asset_count) + " 项资料", "form-hint")); list.append(label);
          for (const diagnostic of unit.diagnostics || []) list.append(node("p", diagnosticText(diagnostic), "form-hint"));
          choices.push({input, entity_ref: unit.entity_ref});
        }
        if (!units.length) list.append(node("p", "该领域没有可引用的已登记论文单元；请先完成原有论文登记。", "form-hint"));
        ready = true;
      } catch (error) {
        if (generation === requestGeneration && list.isConnected) { list.replaceChildren(); showDiagnostics([error.message]); }
      } finally { if (generation === requestGeneration) loading = false; }
    };
    const response = await api("/api/unit-fields");
    if (!list.isConnected) return;
    fields = response.fields || []; showDiagnostics(response.diagnostics || []); fieldChoice.input.replaceChildren();
    const placeholder = node("option", "请选择知识领域…"); placeholder.value = ""; fieldChoice.input.append(placeholder);
    fields.forEach((entry, index) => {
      const option = node("option", entry.title + (entry.source_title ? " · " + entry.source_title : "")); option.value = String(index); fieldChoice.input.append(option);
    });
    fieldChoice.input.disabled = !fields.length; loading = false;
    if (!fields.length) list.append(node("p", "没有可引用的已登记知识领域。请先登记知识来源与领域；这里不会创建标题卡片或假论文。", "form-hint"));
  }, async (candidate, context) => {
    if (loading || !ready || !fieldChoice.input.value) throw new Error("请先选择一个可用的知识领域。");
    const picked = choices.filter((choice) => choice.input.checked).map((choice) => copy(choice.entity_ref));
    if (!picked.length) throw new Error("请至少勾选一个完整论文单元。");
    const selectedField = fields[Number(fieldChoice.input.value)];
    const response = await api("/api/unit-reference", {data: candidate, source_id: selectedField.source_id, field_id: selectedField.field_id, unit_refs: picked});
    const first = response.data.works.find((work) => work.entity_ref?.source_id === picked[0].source_id && work.entity_ref?.object_id === picked[0].object_id);
    if (first) context.selected = first.id;
    return response.data;
  });
}
function dimensionFields(host, scope, initial) {
  const readers = [];
  for (const dimension of data.dimensions.filter((d) => d.scope === scope)) {
    const picked = values(initial[dimension.id]);
    if (dimension.kind === "enum" || dimension.kind === "reference") {
      const wrapper = node("div", undefined, "form-field"); wrapper.append(node("span", dimension.label));
      const choices = node("div", undefined, "form-checkboxes");
      const options = dimension.kind === "reference" ? referenceOptions(dimension) : dimension.values;
      const inputs = [];
      for (const option of options) {
        const label = node("label"), input = node("input"); input.type = dimension.multiple ? "checkbox" : "radio"; input.name = "dimension-" + dimension.id;
        input.checked = picked.includes(option.id); inputs.push([input, option.id]); label.append(input, document.createTextNode(option.label)); choices.append(label);
      }
      if (!options.length) choices.append(node("small", "先在维度定义中添加取值。", "form-hint"));
      wrapper.append(choices); host.append(wrapper);
      readers.push(() => { const v = inputs.filter(([input]) => input.checked).map(([, id]) => id); return [dimension.id, dimension.multiple ? v : v[0]]; });
    } else {
      const entry = field(dimension.label + (dimension.unit ? "（" + dimension.unit + "）" : ""), picked.join("；"), dimension.multiple ? "text" : dimension.kind === "number" ? "number" : dimension.kind === "date" ? "date" : "text", dimension.multiple ? "多个值用中文或英文分号分隔。" : undefined);
      if (dimension.kind === "number" && !dimension.multiple) entry.input.step = "any";
      host.append(entry.wrapper);
      readers.push(() => {
        const convert = (value) => dimension.kind === "number" ? Number(value) : value;
        const v = entry.input.value.trim(); return [dimension.id, !v ? undefined : dimension.multiple ? v.split(/[;；]/).map((s) => s.trim()).filter(Boolean).map(convert) : convert(v)];
      });
    }
  }
  return () => Object.fromEntries(readers.map((read) => read()).filter(([, v]) => v !== undefined && (!Array.isArray(v) || v.length)));
}
function editDimension(existing) {
  let label, id, kind, scope, multiple, sortable, unit, entries, description;
  dialog(existing ? "编辑维度 · " + existing.label : "新增维度", (host) => {
    label = field("名称", existing?.label); id = field("稳定标识", existing?.id || newId("dimension"), "text", "标识用于关联，已有维度不修改标识。"); id.input.disabled = !!existing;
    kind = choose("数据类型", [["enum", "选项"], ["reference", "工作引用"], ["text", "文字"], ["number", "数值"], ["date", "日期"]], existing?.kind || "enum");
    scope = choose("适用对象", [["record", "研究记录（条件与结果）"], ["work", "工作整体"]], existing?.scope || "record");
    multiple = choose("取值数量", [["yes", "允许多个值"], ["no", "单个值"]], existing?.multiple === false ? "no" : "yes");
    sortable = choose("排序", [["no", "不提供顺序"], ["yes", "允许按值排序"]], existing?.sortable ? "yes" : "no");
    const sortingHint = node("small", undefined, "form-hint");
    sortingHint.id = "dimension-sort-hint";
    sortable.input.setAttribute("aria-describedby", sortingHint.id);
    sortable.wrapper.append(sortingHint);
    const updateSorting = () => {
      const allowed = supportsValueSorting({kind: kind.input.value, multiple: multiple.input.value === "yes"});
      sortable.input.disabled = !allowed;
      if (!allowed) sortable.input.value = "no";
      sortingHint.textContent = allowed
        ? "按单个文字、数值或日期值排序；缺失值排在最后。"
        : "只有单值的文字、数值或日期可以排序；选项、工作引用和多值不提供排序。";
    };
    kind.input.onchange = multiple.input.onchange = updateSorting;
    updateSorting();
    unit = field("单位（数值可选）", existing?.unit);
    entries = field("选项定义", (existing?.values || []).map((v) => v.parent_id ? v.id + " | " + v.label + " | " + v.parent_id : v.label).join("\n"), "textarea", "每行填写一个名称，如“视频”“图像”，内部标识自动生成。已有同名选项保留标识；改名或设置层级可用高级格式：标识 | 名称 | 上级标识（可选）。文字、数值、日期无需填写。");
    description = field("含义说明", existing?.description, "textarea");
    [label, kind, scope, multiple, sortable, unit, entries, description].forEach((f) => host.append(f.wrapper));
    const advanced = node("details"); advanced.append(node("summary", "高级设置"), id.wrapper);
    if (existing?.values?.length) advanced.append(node("pre", existing.values.map((v) => v.id + " | " + v.label + (v.parent_id ? " | " + v.parent_id : "")).join("\n"), "form-hint"));
    host.append(advanced);
  }, (candidate) => {
    if (!label.input.value.trim() || !id.input.value.trim()) throw new Error("请填写名称和稳定标识。");
    const existingValues = new Map((existing?.values || []).map((value) => [value.label, value]));
    const item = {id: id.input.value.trim(), label: label.input.value.trim(), kind: kind.input.value, scope: scope.input.value, multiple: multiple.input.value === "yes", sortable: sortable.input.value === "yes", values: entries.input.value.split("\n").filter((s) => s.trim()).map((line) => {
      if (!line.includes("|")) {
        const label = line.trim(), known = existingValues.get(label);
        return known ? copy(known) : {id: newId("value"), label};
      }
      const [id, label, parent] = line.split("|").map((s) => s.trim());
      if (!id || !label) throw new Error("高级格式需要同时填写标识和名称；普通选项只填写名称即可。");
      return {id, label, ...(parent ? {parent_id: parent} : {})};
    })};
    if (unit.input.value.trim()) item.unit = unit.input.value.trim();
    if (description.input.value.trim()) item.description = description.input.value.trim();
    upsert(candidate.dimensions, item);
  });
}
function editWork(existing) {
  if (!existing) return referencePaperUnits();
  const paper = existing.kind === "paper";
  let title, kind, year, summary, getDimensions; const rows = [];
  dialog("编辑工作", (host) => {
    title = field("标题", existing?.title); kind = choose("材料类型", Object.entries(workKinds).filter(([key]) => paper ? key === "paper" : key !== "paper"), existing.kind); kind.input.disabled = paper; year = field("发表年份（可选）", existing?.year, "number"); summary = field("简短说明", existing?.summary, "textarea");
    [title, kind, year, summary].forEach((f) => host.append(f.wrapper));
    host.append(node("h3", "工作整体属性", "form-subtitle")); getDimensions = dimensionFields(host, "work", existing?.attributes || {});
    host.append(node("h3", "相关资产 · 引用现有文件和网址", "form-subtitle"));
    if (paper) {
      host.append(node("p", "论文包资产由原有登记与维护流程管理，在这里仅查看，不能删除、替换或挑选部分文件。", "form-hint"));
      for (const asset of existing.assets) host.append(node("p", asset.label + " · " + asset.kind + "\n" + asset.uri, "form-hint"));
      return;
    }
    host.append(node("p", "本地文件填写相对于所选知识库的路径；支持网页和 Obsidian / Zotero 原生链接。不会写入被引用的文件。", "form-hint"));
    const list = node("div"); host.append(list);
    const addAsset = (asset = {}) => {
      const row = node("div", undefined, "asset-edit-row"), label = node("input"), kind = node("input"), uri = node("input"), remove = node("button", "移除");
      label.placeholder = "名称"; label.value = asset.label || ""; kind.placeholder = "类型（如 markdown）"; kind.value = asset.kind || "document"; uri.placeholder = "文件相对路径或网址"; uri.value = asset.uri || "";
      remove.type = "button"; remove.onclick = () => { row.remove(); rows.splice(rows.indexOf(entry), 1); };
      const entry = {id: asset.id || newId("asset"), label, kind, uri}; rows.push(entry); row.append(label, kind, uri, remove); list.append(row);
    };
    (existing?.assets || []).forEach(addAsset);
    const add = node("button", "＋ 关联资产", "text-button"); add.type = "button"; add.onclick = () => addAsset(); host.append(add);
  }, (candidate, context) => {
    if (!title.input.value.trim()) throw new Error("请填写标题。");
    const work = {id: existing.id, title: title.input.value.trim(), kind: paper ? "paper" : kind.input.value, attributes: getDimensions(), assets: paper ? copy(existing.assets) : rows.map((r) => ({id: r.id, label: r.label.value.trim(), kind: r.kind.value.trim(), uri: r.uri.value.trim()}))};
    if (existing?.entity_ref) work.entity_ref = copy(existing.entity_ref);
    if (existing?.asset_diagnostics) work.asset_diagnostics = copy(existing.asset_diagnostics);
    if (work.assets.some((a) => !a.label || !a.uri || !a.kind)) throw new Error("每项资产需要名称、类型和路径／网址。");
    if (year.input.value) work.year = Number(year.input.value);
    if (summary.input.value.trim()) work.summary = summary.input.value.trim();
    upsert(candidate.works, work); context.selected = work.id;
  });
}
function evidenceFields(host, picked) {
  const wrapper = node("div", undefined, "form-field"); wrapper.append(node("span", "依据材料")); const choices = node("div", undefined, "form-checkboxes"); const inputs = [];
  for (const work of data.works) for (const asset of work.assets) {
    const label = node("label"), input = node("input"); input.type = "checkbox"; input.checked = picked.includes(asset.id); inputs.push([input, asset.id]); label.append(input, document.createTextNode(work.title + " · " + asset.label)); choices.append(label);
  }
  if (!inputs.length) choices.append(node("small", "先为工作关联依据材料。", "form-hint"));
  wrapper.append(choices); host.append(wrapper); return () => inputs.filter(([input]) => input.checked).map(([, id]) => id);
}
function suggestedWork(explicit) {
  for (const id of [explicit, selected]) if (id && data.works.some((work) => work.id === id)) return id;
  return matchesGeneration === queryGeneration && matches?.works.length === 1 ? matches.works[0].id : "";
}
function editRecord(existing, workId) {
  if (!data.works.length) return notice("先引用一个完整论文单元，再记录研究条件和结果。");
  let work, origin, conditions, result, assessment, getDimensions, getEvidence;
  dialog(existing ? "编辑研究记录" : "新增研究记录", (host) => {
    work = choose("所属工作", [["", "请选择工作"], ...data.works.map((w) => [w.id, w.title])], existing?.work_id || suggestedWork(workId));
    origin = choose("结果来源", Object.entries(origins), existing?.origin || "analysis"); host.append(work.wrapper, origin.wrapper);
    host.append(node("h3", "这组研究条件下的定位", "form-subtitle")); getDimensions = dimensionFields(host, "record", existing?.dimensions || {});
    conditions = field("比较条件", Object.entries(existing?.conditions || {}).map(([key, value]) => key + "：" + value).join("\n"), "textarea", "每行一个条件：名称：内容。说明相同条件、所比较差别及尚未对齐的条件。");
    result = field("结果", existing?.result || "尚未记录结果", "textarea"); assessment = field("评价与适用边界", existing?.assessment || "待评价", "textarea");
    [conditions, result, assessment].forEach((f) => host.append(f.wrapper)); getEvidence = evidenceFields(host, existing?.evidence || []);
  }, (candidate) => {
    if (!candidate.works.some((entry) => entry.id === work.input.value)) throw new Error("请先选择这条研究记录所属的工作。");
    const conditionValues = {};
    for (const line of conditions.input.value.split("\n").filter((s) => s.trim())) {
      const split = line.search(/[:：]/); if (split < 1) throw new Error("条件每行按“名称：内容”填写。");
      conditionValues[line.slice(0, split).trim()] = line.slice(split + 1).trim();
    }
    if (!result.input.value.trim() || !assessment.input.value.trim()) throw new Error("结果与评价不能留空；尚未确定时请明确填写“待记录”或“待评价”。");
    upsert(candidate.records, {id: existing?.id || newId("record"), work_id: work.input.value, dimensions: getDimensions(), conditions: conditionValues, result: result.input.value, assessment: assessment.input.value, origin: origin.input.value, evidence: getEvidence()});
  });
}
function editEdge(existing) {
  if (data.works.length < 2) return notice("至少两项工作才能建立工作间关系。");
  let from, to, kind, label, explanation, getEvidence;
  dialog(existing ? "编辑关系与依据" : "新增工作关系", (host) => {
    const options = [["", "请选择工作"], ...data.works.map((w) => [w.id, w.title])];
    from = choose("起点工作", options, existing?.from_id || suggestedWork()); to = choose("终点工作", options, existing?.to_id || "");
    kind = choose("关系含义", Object.entries(edgeKinds), existing?.kind || "extends"); label = field("连线简短说明", existing?.label); explanation = field("依据与说明", existing?.explanation, "textarea", "解释关系成立的理由和适用范围；时间相邻本身不能证明继承。");
    [from, to, kind, label, explanation].forEach((f) => host.append(f.wrapper)); getEvidence = evidenceFields(host, existing?.evidence || []);
  }, (candidate) => {
    if (![from.input.value, to.input.value].every((id) => candidate.works.some((work) => work.id === id))) throw new Error("请明确选择关系的起点和终点工作。");
    if (from.input.value === to.input.value) throw new Error("关系的起点和终点应为不同工作。");
    if (!explanation.input.value.trim() || !getEvidence().length) throw new Error("请说明关系成立的依据，并选择至少一项依据材料。");
    upsert(candidate.edges, {id: existing?.id || newId("edge"), from_id: from.input.value, to_id: to.input.value, kind: kind.input.value, label: label.input.value.trim() || edgeKinds[kind.input.value], explanation: explanation.input.value, evidence: getEvidence()});
  });
}
function saveView() {
  let title;
  dialog("保存当前研究视图", (host) => { title = field("视图名称", ""); host.append(title.wrapper, node("p", "保存筛选条件、排序方式和上下文设置；匹配结果仍从最新文件计算。", "form-hint")); }, (candidate) => {
    if (!title.input.value.trim()) throw new Error("请填写视图名称。");
    candidate.views.push({id: newId("view"), title: title.input.value.trim(), query: copy(selection)});
  });
}

$("save").onclick = save; $("reload").onclick = () => { load(true); loadEnvironment(); loadVaultConnections(); };
$("add-vault").onclick = chooseVault;
$("vault-adjustments").onclick = previewVaultAdjustments;
$("vault-connect").onclick = connectVault;
$("close-vault").onclick = $("vault-cancel").onclick = () => {
  if (vaultBusy) return;
  ++vaultGeneration; vaultCandidate = null; $("vault-dialog").close();
};
$("vault-dialog").addEventListener("cancel", (event) => {
  if (vaultBusy) event.preventDefault();
  else { ++vaultGeneration; vaultCandidate = null; }
});
$("close-vault-documents").onclick = () => { ++vaultDocumentGeneration; $("vault-documents").close(); };
$("vault-documents").addEventListener("cancel", () => { ++vaultDocumentGeneration; });
$("reload-keep").onclick = () => $("reload-confirm").close();
$("reload-discard").onclick = () => { $("reload-confirm").close(); load(true, true); };
$("search").oninput = () => { if ($("search").value.trim()) selection.text = $("search").value; else delete selection.text; scheduleQuery(); };
$("sort").onchange = () => { selection.sort_by = $("sort").value; runQuery(); };
$("descending").onchange = () => { selection.descending = $("descending").checked; runQuery(); };
$("context").onchange = () => { selection.include_context = $("context").checked; runQuery(); };
$("clear-filter").onclick = () => { selection.filters = {}; delete selection.text; renderFilters(); runQuery(); };
$("views").onchange = () => { const view = data.views.find((v) => v.id === $("views").value); if (view) { selection = copy(view.query); renderFilters(); runQuery(); } };
$("save-view").onclick = saveView;
$("add-dimension").onclick = () => editDimension(); $("add-work").onclick = referencePaperUnits; $("first-work").onclick = referencePaperUnits;
$("add-record").onclick = () => editRecord(); $("add-edge").onclick = () => editEdge();
function switchTab(graph) {
  $("graph-view").hidden = !graph; $("table-view").hidden = graph;
  $("graph-tab").classList.toggle("active", graph); $("table-tab").classList.toggle("active", !graph);
  $("graph-tab").setAttribute("aria-selected", String(graph)); $("table-tab").setAttribute("aria-selected", String(!graph));
}
$("graph-tab").onclick = () => switchTab(true); $("table-tab").onclick = () => switchTab(false);
$("close-editor").onclick = $("cancel-editor").onclick = () => $("editor").close();
$("editor-form").onsubmit = async (event) => {
  event.preventDefault();
  if (formBusy) return;
  const submit = formSubmit, opened = formBase, base = opened?.data,
    baseRevision = opened?.revision, context = {selected, selection: copy(selection)};
  const conflict = "文件或草稿已变化。当前输入已保留，请取消表单并重新读取后再编辑。";
  const button = $("editor-form").querySelector('button[type="submit"]');
  formBusy = true; button.disabled = true; $("form-error").hidden = true;
  try {
    if (!opened || data !== base || revision !== baseRevision || saveBusy) throw new Error(conflict);
    const current = await api("/api/state");
    if (formSubmit !== submit || !$("editor").open) return;
    if (current.revision !== baseRevision || data !== base || revision !== baseRevision) throw new Error(conflict);
    const candidate = copy(base), proposed = await submit(candidate, context) || candidate;
    const result = await api("/api/query", {...context.selection, _draft: proposed});
    const confirmed = await api("/api/state");
    if (formSubmit !== submit || !$("editor").open) return;
    if (confirmed.revision !== baseRevision || data !== base || revision !== baseRevision || saveBusy) throw new Error(conflict);
    data = proposed; selected = context.selected; selection = context.selection; matches = result; matchesGeneration = ++queryGeneration;
    markDirty(); renderFilters(); renderViews(); renderMatches(); $("editor").close();
  } catch (error) {
    if (formSubmit === submit && $("editor").open) { $("form-error").textContent = error.message; $("form-error").hidden = false; }
  } finally { formBusy = false; button.disabled = false; }
};
$("close-preview").onclick = () => { clearPreview(); $("preview").close(); };
$("preview").addEventListener("close", () => { if (!$("preview").open) clearPreview(); });
$("preview").addEventListener("cancel", clearPreview);
$("preview-native").onclick = () => { if (previewAsset) nativeOpen(previewAsset.workId, previewAsset.assetId); };
window.addEventListener("pagehide", clearPreview);
window.addEventListener("beforeunload", (event) => { if (dirty || $("editor").open) event.preventDefault(); });
setInterval(async () => {
  if (!data || document.hidden || pollBusy || saveBusy || formBusy) return;
  const base = data, baseRevision = revision;
  pollBusy = true;
  try {
    const state = await api("/api/state");
    if (data !== base || revision !== baseRevision || saveBusy || formBusy) return;
    if (state.revision === revision) return;
    if (dirty || $("editor").open) {
      status("文件已变化，修改待核对", "error");
      notice("知识库文件已在外部修改。当前输入和未保存内容仍保留，请核对后重新读取。保存仍检查原版本。");
      if ($("editor").open) {
        $("form-error").textContent = "知识库文件已在外部修改。当前输入已保留，请取消表单并重新读取后再编辑。";
        $("form-error").hidden = false;
      }
    }
    else { data = state.data; revision = state.revision; renderFilters(); renderViews(); status("已跟随文件更新"); await runQuery(); }
  } catch (error) {
    if (data === base && revision === baseRevision && !saveBusy && !formBusy) status("等待重新连接", "error");
  } finally { pollBusy = false; }
}, 5000);
loadEnvironment();
loadVaultConnections();
load();
