# Hub Control Plane v2 — 正式规格

> 状态：Accepted 1.0，2026-09-22。用户已授权实现契约、测试和非生产 canary；现有 23128 listener、
> LaunchAgent、真实 Vault/项目和 Codex thread 不在本批自动迁移或切换范围内。
>
> `hub-investigation-conclusion.md` 是只读调查证据，不是运行期契约。本文与
> `project-system-v2.md`、`knowledge-system-v2.md` 并列，并以 `planning/GOALS.md` 为上位意图层。

## 1. 目标与边界

Hub Control Plane v2 提供三个可分离能力：

1. **Directory**：以唯一 `HubDirectory` 聚合 typed Libraries 和 Knowledge Contexts。
2. **Operations**：管理 Hub service、workspace binding、显式 registries 和可恢复文件操作。
3. **Task control**：把预登记 TaskRecipe 映射为 LogicalTask、TaskRun 和明确的 Codex thread。

Hub 不成为第四知识数据库，不复制 Zotero/Vault/项目/Codex 的主数据，也不从磁盘、workspace 名称、
`$PATH` 或自由 Markdown 猜测对象。正式切换服务、迁移持久数据和运行真实 Codex task 是独立发布门。

## 2. 调查时已核实基线（2026-09-22 实施前快照）

- 调查时 PATH 上的独立 CLI 为 0.27.1；仓库 package 与双宿主 manifests 为 0.27.2。
- 23128 listener 来自旧 0.18.0 `serve-links` LaunchAgent；旧 PDF 路由可用，但 `/hub/` 与
  `/api/v1/health` 在调查时返回 400。
- 调查时源码有 `HubCatalog`、opaque actions、Vault 冲突保护、PDF Range/HEAD 与 cmux workspace registry。
- 调查时 catalog snapshot 只覆盖 paper/topic/artifact 的部分投影，不是 typed library directory。
- 本机 Codex CLI 支持 `codex exec --json` 和按明确 session ID `resume`；resume/fork 可覆盖部分参数，
  因此配置不可变性必须由本插件策略实现，而不能描述成 Codex 技术限制。

版本号是迁移证据，不得硬编码为永久要求。worker 必须在启动时探测所需 capability。

## 3. 唯一根与公共类型

### 3.1 HubDirectory

唯一公共根：

```text
HubDirectory
├── schema_version
├── libraries
├── knowledge_catalog
├── knowledge_contexts
├── operations
└── diagnostics
```

- `knowledge_catalog` 是版本化知识 provider 输出，承接旧 `HubCatalog`。
- `/api/v1/catalog` 在兼容期只从 `HubDirectory.knowledge_catalog` 派生，禁止独立写入或缓存第二事实根。
- v2 接口以 `/api/v2/` 为命名空间。
- 迁移期每次启动只选择一个 knowledge provider：若显式 provider snapshot 已存在，必须先完整校验后读取；
  若不存在，才使用旧只读兼容 provider。启动服务不得自行创建 snapshot 或迁移 Vault，health 必须报告
  实际选中的 catalog root。

### 3.2 TypedEntityRef

所有跨界面选择和持久引用使用：

```json
{
  "library_id": "papers",
  "item_type": "paper",
  "item_id": "opaque-provider-id"
}
```

端口 URL、绝对路径、进程内 action/workspace ID 和显示名称都不是 entity identity。

`papers`、`projects`、`tools` 对应三个 Library provider；`knowledge` 是
`knowledge_catalog` / Knowledge Context 的保留 typed namespace，不构成第四个 Library，也不得把
Vault analysis 冒充成 Zotero Papers provider 对象。论文 PDF 使用 `papers:attachment:*` landing，
analysis/Canvas 使用 `knowledge:artifact:*` landing。

### 3.3 LibraryDescriptor

每个 Library 声明：

- stable `library_id`、display name、item types 和 provider version；
- provider health/capabilities/authority；
- server-side paging、filter 和 sort 能力；
- 空库诊断，而不是从导航中消失。

## 4. 首批 Libraries

### 4.1 Papers

- authority：Zotero Local API。
- 以 Local API 分页读取；不得先拉取整库再在浏览器分页。
- library item 与现有离线 `resource_id` 投影显式映射，但 DOI/title+authors 仍决定 library identity。
- PDF、Zotero、analysis 和 topic views 从 typed ref 派生受控 action/landing。

### 4.2 Projects

- authority：项目 `project-layout.json` 中的稳定 `project_id`。
- `project_id` 是 schema v2 初始化时生成一次的规范小写 UUID；不含主机路径，复制/重跑保持不变。
- 主机 registry 显式保存 `project_id → trusted root、enabled、capabilities`；它是主机定位信息，
  不写回便携项目 manifest。
- 不扫描目录发现项目。重复 project ID 指向多个根时 fail closed，交由人解决。

### 4.3 Tools

- authority：显式 `ToolDefinition` registry。
- 可注册 Scholar Workflow、Codex、cmux、Zotero、Obsidian 与其他外部工具。
- 每项声明 provider/source、capabilities、health probe 和 allowlisted recipe IDs。
- 不扫描 `$PATH` 或把任意 executable 自动暴露为能力。

## 5. Knowledge Contexts

Knowledge Contexts 展示 Knowledge Spaces、核心文档、原子资源、附属产物、relations 和 Saved Views。

- 首版不把 Project/Tool 关系写入 Knowledge Space。
- knowledge relations 只来自 Zotero/Vault manifest/provider。
- Project 和 Tool 是独立 Library；人或 agent 通过显式复制内容在知识与项目之间工作。

## 6. 项目文件边界

### 6.1 输入与解析

任何项目文件 API 只接受：

```text
project_id + docs-relative path
```

服务端从 registry 解析 trusted project root，再固定到 `<root>/docs`。拒绝绝对路径、空路径、`.`、`..`、
NUL、正规化逃逸、symlink escape、未知/disabled project 和非 regular file。客户端不能提交项目根。

### 6.2 Knowledge → Project

- 只复制显式选择的人类可读 Markdown、Canvas 和明确选择的 owned assets。
- 不自动复制 Zotero PDF、正式 annotations 或未选择附件。
- 复制时剥离 `sw_*`、sidecar、baseline marker 和 managed relation identity。
- 目标存在时拒绝；不覆盖、不自动添加后缀。
- 完成后副本具有项目本地身份，系统不保存持续同步或语义 provenance 关系。

### 6.3 Project 内操作

- 首版支持 `copy`、`paste`、`trash`，范围只在同一已注册项目的 `docs/`。
- 删除移动到 `.scholar-workflow/trash/docs/<timestamp>/`，记录原相对路径、SHA-256、时间和恢复元数据。
- trash 不可用、不安全或发生冲突时拒绝删除；首版无 permanent delete/automatic cleanup。
- Git tracked/dirty 文件返回警告并要求该操作的明确确认；Hub 不执行 `git add/commit/push`。

### 6.4 Project → Knowledge

归档调用知识 ingest/archive 流程，在 Vault 创建新的 technical-document identity。源项目文件不被修改，
目标与源不建立同步。通用安全审计可以记录操作结果，但不能充当知识关系或持续 provenance。

## 7. Service 与 workspace binding

### 7.1 HubService

- 默认 owner 是可见 cmux `runtime` workspace 中的唯一进程。
- headless 模式必须显式选择；未绑定 workspace 时仅提供 Library、文档、PDF 和 diagnostics 读取。
- 同一配置只允许一个 listener owner；页面加载不得启动/升级服务或自动打开外部应用。

health/status 至少报告：service/package/build/protocol 版本、owner mode、PID、origin、root schema、
cmux instance fingerprint、provider/worker capabilities 和 log location。对外字段不得泄漏敏感绝对路径。

### 7.2 WorkspaceProfile 与 WorkspaceLease

逻辑 profile 首版包括 `hub`、`runtime`、`notion`、`codex:<project_id>`，允许显式 alias。

实际 binding 使用：

- one-time nonce；
- service generation；
- lease generation/expiry；
- cmux instance fingerprint；
- process-local opaque workspace ID。

workspace 名称不是身份或授权依据。nonce 重放、lease 过期、generation 改变、实例不匹配和 workspace
消失都使 binding 失效；不得按名称静默 reclaim。一个可执行 HubView 同时只能有一个 primary binding。

## 8. Codex task control

### 8.1 模型

```text
TaskRecipe -> LogicalTask -> TaskRun -> codex_thread_id
```

- `TaskRecipe`：server-registered purpose、project/library scope、context selector、tool allowlist 和安全策略。
- `LogicalTask`：人类可理解的长期任务 identity 与批准摘要。
- `TaskRun`：create/resume/fork 的一次运行、状态、时间、结果摘要和错误。
- `codex_thread_id`：Codex authority；Hub 不复制完整 transcript。

每个逻辑 workspace slot 使用长期 terminal worker。首版不支持 thread merge；完成线程保留并由用户手动
archive，不自动删除。

### 8.2 浏览器请求

允许字段只有：recipe ID、typed target、最多 8 KiB UTF-8 brief、`fast|standard|deep` effort 和
idempotency key。整个 JSON request 默认上限 32 KiB。

客户端不能提交 shell command、cwd/path、model、sandbox、permission、config、environment、thread ID
或 terminal target。服务端根据 recipe 和 registry 决定这些值。

### 8.3 worker 安全

- brief 经 stdin 传入；不进入 URL、argv prompt、shell 字符串或进程标题。
- subprocess 使用 argv list、`shell=False`、allowlisted environment 和固定 cwd。
- create 使用 `codex exec --json -`；解析 `thread.started.thread_id`。
- resume/fork 使用服务端保存的明确 ID；禁止 `--last`。
- effort/project/cwd/sandbox/permission 改变时创建新 task/thread 或显式 fork，不静默修改原线程。
- 启动先做 capability probe；缺少 JSON thread event 或明确-ID resume 时禁用 task capability。
- 每 thread lock、idempotency、heartbeat、cancel、timeout 和 process-group reap 是必备外部契约。
- interrupted run 标为 interrupted；不得让失联进程继续后台漂移。

Hub 只持久化 title、approved summary、summary hash、status、recipe/target ref、thread ID 和 run outcome。
原始 brief/output 不进入长期 Hub state，除非未来有独立、明确的数据保留决策。

## 9. HTTP/API 与 UI

### 9.1 v2 API 最小面

```text
GET  /api/v2/directory
GET  /api/v2/libraries/<library-id>/items?cursor=&limit=&query=&sort=
GET  /api/v2/health
GET  /hub/item?library_id=&item_type=&item_id=
POST /api/v2/workspaces/nonce
POST /api/v2/workspaces/bind
POST /api/v2/projects/<project-id>/docs/copy
POST /api/v2/projects/<project-id>/docs/copy-knowledge
POST /api/v2/projects/<project-id>/docs/paste
POST /api/v2/projects/<project-id>/docs/trash
```

`operations` 状态属于唯一 `/api/v2/directory` 根，不另设第二个状态端点。单对象的人类入口统一使用
typed landing；直接字节/预览 URL 只在 landing 内解析。TaskRecipe、LogicalTask、TaskRun 的 schema、
store 和 worker 原语已实现，但以下 HTTP 路由在 worker manager 完成独立发布验收前保持**未注册**：

```text
POST /api/v2/tasks
POST /api/v2/tasks/<task-id>/runs
POST /api/v2/runs/<run-id>/cancel
```

写接口继续要求 loopback Host/Origin、CSRF、严格 schema 和 idempotency。unbound/headless 模式对所有
workspace、project-doc 和 task mutation 返回显式不可用，不降级执行。

### 9.2 UI

顶层信息架构固定为：

```text
Libraries
  Papers / Projects / Tools
Knowledge Contexts
Operations
```

- 每个 Library 使用 server pagination/search/filter/sort 和 detail view。
- Operations 显示 service identity、bindings、workers、tasks 和可恢复错误。
- 读取优先；写入、任务、trash 和外部打开按需展开并明确显示当前 binding/target。
- UI 不展示 raw UUID、绝对路径、shell 或未过滤 stderr。

## 10. 服务迁移与回滚

1. 先记录旧 listener 的 GET 基线、plist/venv/owner/port，不修改它。
2. 在临时端口启动新构建 canary，验证 health、Directory、Libraries、PDF 和只读 UI。
3. 再验证 workspace lease、项目 docs 安全和 fake worker；不运行真实 Codex task。
4. 完成兼容矩阵和回滚演练后，另行取得用户对 23128 切换的确认。
5. 切换失败恢复旧 plist/venv/port，并验证旧服务原有 GET 行为；不要求旧服务支持新 HEAD/health。
6. 旧 raw URLs 不批量改写，稳定 landing 契约通过后另建迁移批次。

## 11. 实施阶段

- **H-A 契约冻结**：正式规格、GOALS/BACKLOG/HANDOFF、schemas 和失败优先 contract tests。
- **H-B 只读可诊断服务**：identity/health/doctor、temporary-port canary；无正式 cutover。
- **H-C Directory/Libraries**：HubDirectory、Papers provider、compat catalog、Projects/Tools registries。
- **H-D 安全操作**：project docs resolver/copy/trash 和 independent-copy contract。
- **H-E Binding**：WorkspaceProfile/Lease/ViewBinding 与 unbound gating。
- **H-F Task control**：recipes/tasks/runs、capability probe、fake worker、locks/cancel/reap。
- **H-G UI 与兼容发布**：library-first UI、operations surface、完整回归；23128 仍是单独批准门。

## 12. 测试矩阵

必须至少验证：

- `HubDirectory` 唯一根；v1 catalog 与 v2 knowledge catalog 语义一致且无独立状态。
- typed refs 跨 Library 不冲突；cursor pagination 稳定；空 provider 可见且有诊断。
- Papers 分页消费 fake Zotero Local API，不拉取整库。
- Projects/Tools 只来自显式 registry，扫描代码路径不存在。
- duplicate project ID、unknown tool、invalid capability 和 registry corruption fail closed。
- project docs 绝对路径、traversal、symlink、disabled project、跨 docs 和覆盖全部拒绝。
- trash 记录 hash/原路径且可恢复；Hub 不调用 Git 写命令。
- independent copy 剥离知识 identity，且 catalog/manifest 中不出现跨副本关系。
- nonce replay、expired lease、generation/fingerprint mismatch 和 cross-instance binding 拒绝。
- unbound/headless 可读而所有 external-open/file/task actions 禁用。
- brief >8 KiB、request >32 KiB、未知 recipe/effort/target 和多余字段拒绝。
- shell metacharacters 只作为 stdin 文本；argv/cwd/env 只能来自 server recipe。
- fake JSONL worker 提取 thread ID；resume/fork 使用明确 ID；代码中无 `--last`。
- idempotency 与 per-thread lock 阻止重复/并发 run；cancel/timeout 回收进程组并记录 interrupted。
- old service/capability/version mismatch 有可解释 diagnostics；canary/rollback 不改 23128。
- PDF Range/HEAD、Vault 原子保存、Origin/CSRF 和旧 opaque actions 不回归。

## 13. 完成定义

实现阶段只有同时满足以下条件才可称为 Hub Control Plane v2 runtime 完成：

1. 人类从一个 HubDirectory 浏览 Papers、Projects、Tools 和 Knowledge Contexts；
2. 每个对象能说明 authority/provider，Hub 不成为正文或 transcript 真源；
3. 项目写入无法越过 registered `docs/`，删除可恢复，跨知识/项目复制无隐藏同步；
4. workspace binding 可验证且失效安全，unbound/headless 严格只读；
5. task input/worker/thread 通过安全和故障测试，不接收浏览器命令或配置；
6. health 能识别实际运行构建，canary 和回滚证据完整；
7. 未经单独批准没有迁移真实数据、切换 23128、修改 LaunchAgent 或运行真实 Codex task。
