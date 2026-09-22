# Hub 调查结论：原子库、cmux workspace 与 Codex CLI

> 状态：调查证据，2026-09-22；不是运行期规格。已确认方向与决策门由
> `planning/hub-control-plane-v2.md` 正式承接，后续实现以 GOALS 和正式规格为准。
>
> 本文只记录当前证据、架构判断、推荐边界与待确认决策。它不是已激活规格，不授权修改
> Hub runtime、23128 服务、Vault、`GOALS.md` 或全局 `CLAUDE.md`。除新增本文外，本轮不实施。

## 1. 结论摘要

用户对 Hub 的判断成立：当前问题不是再加几个按钮就能解决，而是 Hub 的对象模型、运行模型和
workspace 模型都还停留在首版投影器阶段。

结论可以压缩为七点：

1. **Hub 顶层应有明确的一级类型库（typed Library）**，首批至少包括论文库、项目库、工具库；
   每个库承载可独立识别的原子 entity。当前 `HubTopic` 只是 knowledge resource/artifact 的关系节点，
   不应继续兼任顶层目录；只有在后续决策通过后，目标态 Knowledge Space 才扩成跨库关系实体。
2. **库、集合、派生视图、知识空间、实体和附属产物必须分开**。论文库/项目库/工具库是一级域；
   Zotero collection、项目组、工具分类是显式分组；SavedView 是查询投影；Knowledge Space 是认知上下文
   与关系实体；分析、Canvas、笔记等是有领域归属的附属产物。
3. **Hub 与 workspace 的绑定是执行和呈现绑定，不是数据读取绑定**。绑定的含义是“在哪里打开、
   运行和承载窗口”，不是“扫描该 workspace 的文件并把它当作 Hub 内容”。
4. **每个能执行 workspace action 的 operational Hub view 必须有一个主 workspace 绑定**，同时 Hub
   可以登记一组按职责命名的 workspace profile，例如 `hub`、`notion`、`runtime`、`codex:<project>`。
   动作按角色路由，角色可以复用同一个真实 workspace，避免无限增殖；普通浏览器是否保留明确的
   `unbound-readonly` 降级页仍需决策。
5. **Hub 应启动 cmux 中的 Codex CLI 任务，而不是当前的 blank native Codex agent-session**。
   推荐用长期存在的 cmux terminal worker 执行 `codex exec`，由服务端固定 cwd、权限和命令结构，
   用户只选择已登记 recipe、强度以及受限的任务输入。
6. **“每次访问生成一个对话”不能靠事后合并解决**。正确模型是
   `LogicalTask -> Run -> Codex thread`：同一逻辑任务显式保存 Codex thread ID 并 `resume`，分支用
   `fork`，一次性任务用 `--ephemeral`，完成后先保留、再按策略 `archive`。Codex CLI 没有可靠的
   thread merge 语义；
   需要合并的是 Hub 层任务记录和 handoff，而不是伪造会话合并。
7. **在重做 UI 前必须先收口正式服务所有权**。2026-09-22 的实时检查显示 23128 仍由安装目录中的
   0.18.0 服务占用，而当前 PATH CLI 是 0.27.1、仓库 package/插件清单是 0.27.2；`/hub/` 和 `/api/v1/health` 均返回
   HTTP 400。当前页面体验不能被当作新版 Hub 的可靠运行验收。

因此，下一阶段不应把“论文库、项目库、工具库”继续塞进现有 `HubResource` 的可选字段，也不应直接
把浏览器 prompt 接入现有 action endpoint。应先确认新的 Hub 根模型、workspace role 模型和 Task API
安全边界，再进入实现。

## 2. 调查范围与运行快照

本轮只读检查了：

- `HubCatalog`、topic projection、artifact/asset 模型；
- Hub 前端导航、检索、workspace 选择和 action 请求；
- cmux 控制层、workspace registry、Codex launcher、HTTP action 边界和契约测试；
- `serve-hub` / `open-hub` 的环境传递；
- 当前 23128 listener、已安装 CLI、仓库插件版本和实际 catalog；
- 本地 cmux 0.64.24 与 Codex CLI 0.153.4 的可用命令；
- 现有 `GOALS.md`、Hub contract/security policy、`HANDOFF.md`、知识系统 v2 与项目系统 v2。

### 2.1 2026-09-22 运行快照

| 项目 | 观察结果 | 结论 |
|---|---|---|
| 23128 listener | PID 6727，PPID 1，cwd `/`；日志位于旧 link-service 路径 | 当前是脱离交互 workspace 的常驻服务 |
| 安装环境版本 | `~/.local/share/scholar-workflow/venv/bin/scholar-workflow` 为 0.18.0 | 正式端口没有运行当前实现 |
| 当前 shell CLI | `scholar-workflow` 为 0.27.1 | 与 listener 不同版本 |
| 仓库插件清单 | Codex/Claude plugin 均为 0.27.2 | 又存在一层版本差异 |
| HTTP 探针 | `/hub/`、`/api/v1/health` 均为 HTTP 400 | 统一 Hub API 尚未接管正式 listener |
| cmux | 0.64.24 | 已具备 workspace、terminal surface、session 查询等基础能力 |
| Codex CLI | 0.153.4 | 已具备 `exec`、JSONL、resume/fork、archive 等任务原语；本方案不把独立 app-server 的 `queue` 当作 worker 队列 |

### 2.2 当前持久化 catalog snapshot 实物

`~/.config/scholar-workflow/hub/catalog.json` 当前包含：

- 17 个 resource，全部是 `paper`；
- 1 个 topic；
- 19 个 artifact：17 个 `paper-hub`、1 个 `paper-list`、1 个 `literature-tree`；
- 0 个 asset；
- 唯一 source 是 `literature-tree-payload`。

该文件的 `generated_at` 是 `2026-09-21T16:30:00+08:00`。它不是 Zotero 全库，也不是论文/项目/工具
三库的统一目录；它是一个主题 payload 的 raw 论文投影 snapshot。新版服务原计划还会在读取时叠加 Vault、
Canvas、asset 与 Notion link provider，但正式 listener 仍是旧版，因此本轮不能把这组数字泛化为新版
runtime 的 live assembled catalog。

## 3. 已确认的问题

### 3.1 当前 Hub 不是“库的 Hub”

`HubCatalog` 承载领域对象的顶层集合只有 `sources/resources/topics/artifacts/assets/diagnostics`；另有
schema、revision 和 generated time 元数据。`HubResource` 的字段围绕论文书目信息、Zotero、topic 和
artifact 引用设计；`HubTopic` 是 knowledge resource/artifact 关系节点；
`ArtifactKind.COLLECTION_INDEX` 只是文档产物种类，不是容纳实体的集合模型。

现有 `ResourceKind` 同时包含 `paper`、`technical_document`、`snapshot`、`drawio`、`image`、`dataset`，
混合了语义资源和文件/呈现形态，且没有 `project` 或 `tool`。因此不能通过简单新增两个枚举值，把项目和
工具伪装成与论文同构的 resource。

topic projection 只消费 `paper_list` / literature tree payload，并把所有 entry 固定为
`ResourceKind.PAPER`。`HANDOFF.md` 也已明确：Zotero 全库分页 assembler 尚未完成。

**判断：**当前 `HubCatalog` 适合作为知识投影兼容层，但不足以直接承担新的 Hub 根目录。

### 3.2 当前 UI 是“主题过滤的论文卡片页”

当前侧栏只有“全部资料”和 topic 列表。topic 的 `parent_id` 没有形成层级导航；resource 卡片固定展示
论文式字段；artifact 又在全局文档区单独摊平，没有围绕 resource 的 `artifact_ids` 形成完整详情页。

页面启动时一次性下载完整 `/api/v1/catalog` 和 `/api/v1/actions`，检索也只在浏览器内执行。若直接接入
Zotero 全库、项目库和工具库，载荷、筛选、排序和认知负担都会继续放大。

**判断：**新 UI 应先选 Library，再进入该库自己的搜索、筛选、排序和详情；完整库接入前必须有服务端
分页或 cursor，不能继续全量 boot fetch。

### 3.3 当前 Codex 动作与目标需求相反

当前 `CodexLauncher` 固定调用：

```text
cmux new-surface --type agent-session --provider codex \
  --working-directory <server-trusted-cwd> --workspace <workspace-id>
```

它创建的是 cmux native Codex agent-session，不是 terminal 中的 `codex exec`。前端只提交
`workspace_id`；contract test 明确断言 argv 不含 `--command` 和 prompt。每次点击都会新建 surface，
也没有保存 Codex thread ID、逻辑任务、resume/fork/archive 状态或任务队列。

需要特别区分：**访问 Hub 页面本身不会新建对话；点击当前全局 Codex 动作才会新建一个空白会话。**
用户感受到的“每次一个对话”是 action/task/thread 生命周期缺失，不是页面加载副作用。

### 3.4 当前 workspace 只是临时下拉项，不是绑定

`WorkspaceRegistry` 只在当前进程内把 cmux raw workspace ID 映射为随机 opaque ID。它会随进程、刷新失败
或 workspace 消失而失效；浏览器看到的字段只有 `id/label/is_current/contains_hub`，没有用途、角色、
项目、复用策略或绑定状态。

`open-hub` 每次生成/接收 instance token，用 URL 是否出现在 cmux tree 中推测 `contains_hub`。前端选择
顺序是“内存中的上次选择 -> contains_hub -> current -> 第一个”，页面刷新后上次选择即丢失。所有动作
共享一个全局选中 workspace。

这只能算“动作目标选择器”，不能算 Hub/workspace 绑定。

### 3.5 还存在 cmux 实例错配风险

`open-hub` 使用调用方的 `CMUX_WORKSPACE_ID` 和 `CMUX_SOCKET_PATH` 打开页面；但 server 内的
`CmuxControl` / `WorkspaceRegistry` 使用服务进程环境指定、或 cmux CLI 自动发现的 control instance。
于是页面可能在 cmux B，动作却发给 cmux A；自动发现还会让错配更隐蔽。当前 health 只返回通用
capability，不声明 cmux instance 身份；测试也没有覆盖这种错配。

若 listener 由 LaunchAgent 在 cmux 外启动，在严格 socket policy 下还可能根本没有被授权的 cmux
控制上下文。

**判断：**workspace 绑定前必须先增加 cmux instance handshake；不能只凭 workspace 名称、当前窗口或
URL 猜测。

## 4. 推荐的 Hub 根模型

### 4.1 信息架构

```text
Hub
├── Libraries（一级类型库，承载原子 entity）
│   ├── Papers       <- Zotero library authority
│   ├── Projects     <- project manifest + host-local registration
│   └── Tools        <- provider facts + explicit local allowlist
├── Knowledge Contexts（知识上下文）
│   ├── Topics / Knowledge Spaces（目标态可跨库）
│   ├── core documents
│   └── cross-entity relations / projected views
└── Operations（运行控制面）
    ├── Workspace Profiles / Live Leases / View Bindings
    └── Task Recipes / Logical Tasks / Codex Threads / Runs
```

术语建议固定如下：

| 术语 | 含义 | 示例 |
|---|---|---|
| Library / 库 | Hub 的一级对象域，有独立 authority、schema 和查询能力 | Papers、Projects、Tools |
| Collection / 集合 | 某一库内有显式 membership 的权威或登记分组 | Zotero collection、项目组、工具类别 |
| SavedView / 保存视图 | 由 filter/sort/query 定义的派生投影，不拥有 membership | “最近更新的高优先级论文” |
| Knowledge Space / Topic | 拥有核心文档、关系和认知上下文的实体；目标态可跨库 | 世界模型主题关联论文、项目和工具 |
| Entity | 三个库共享的抽象称呼 | KnowledgeResource、Project、ToolDefinition |
| KnowledgeResource | 现有知识系统中的窄义资源 | paper、technical-document、blog-post |
| KnowledgeArtifact | 隶属于 KnowledgeResource 或 Knowledge Space 的知识产物 | 分析、Canvas、阅读笔记 |
| ExperimentArtifact | 隶属于 Project/Experiment 的项目产物，使用独立契约 | report、metrics、checkpoint |
| Task/Run | 使用工具对对象执行的一次受控工作 | 在项目上运行一次 Codex recipe |

不建议把这五层都叫“集合”。仓库中已经存在 `collection-index` artifact 和 Zotero collection；继续复用
同一个词会把容器、视图和文档混为一谈。

### 4.2 根目录与分库契约

建议新增轻量 `HubDirectory`（名称待定），只列出分库描述，不把所有类型压进一个巨型数组：

```text
LibraryDescriptor
  library_id
  kind
  provider
  authority
  schema_version
  revision
  item_count
  capabilities
  diagnostics
```

每个 library 使用自己的 typed item schema 和分页查询。跨库关系必须使用 namespaced typed reference，
例如 `{library_id, item_id}`，或经验证的全局 namespaced entity ID，不能假设三个 provider 的裸 ID 永不
冲突。

现有 INV29 把 `HubCatalog` 定义为共享上位接口，因此新增 `HubDirectory` 本身就是根 contract 变更，不能
悄悄并存两个根接口。实现前必须决定它是取代 `HubCatalog`，还是成为唯一根并包含 versioned
`knowledge_catalog` 子目录；迁移期也必须指定唯一 canonical root contract。现有 `HubCatalog` 可作为
knowledge projection 和兼容 payload，但不应被原地扩成项目/工具/任务数据库。

### 4.3 三个首批库的权威边界

| 库 | 权威来源 | Hub 可以做什么 | Hub 不应做什么 |
|---|---|---|---|
| Papers | Zotero library；Local API 是访问接口 | 分页读取、检索、投影视图、打开已登记对象 | 复制书目/PDF 成第二真源 |
| Projects | tracked manifest 管 portable identity/layout/profile；host-local registry 管本机 trusted root 与 enablement | 展示项目身份、状态、入口、已登记相对路径和 recipe | 扫描任意 workspace、形成两个都可改 project identity 的真源，或把项目降格为 technical-document |
| Tools | provider/manifest 管版本与 capability facts；`ToolRegistry` 管 provenance、启用和 recipe allowlist | 展示 capability、来源、状态和可用 recipe | 扫描 `$PATH` 后自动变成可执行工具，或让 registry 冒充底层工具真源 |

项目应拥有稳定 `project_id`。项目根路径只在服务端受信注册表中解析；浏览器只接触 project ID 和
repo-relative 的已登记 context/handoff 文件，不接触任意绝对路径。

工具库还需要先确定范围：Scholar Workflow skills、CLI、Codex plugin/app、外部服务、还是可运行 recipe。
无论最终范围如何，**ToolDefinition、TaskRecipe、TaskRun 必须是三种对象**；“工具是什么”不能与“这次用
什么参数执行”混成一个记录。

## 5. Hub 与 workspace 的目标关系

### 5.1 核心原则

> workspace 是 Hub 动作的执行/呈现目的地，不是 Hub 数据 authority，也不是隐式内容扫描范围。

这个原则同时满足两个要求：Hub 有真实绑定，但绑定不会改变 Zotero、Vault、项目 registry 等权威边界。

### 5.2 五个对象

建议把当前单一 `WorkspaceRegistry` 拆成以下概念：

1. **HubService**：唯一 loopback 服务 owner，负责目录、任务和 action API；生命周期独立于某个网页 tab。
2. **HubViewBinding**：每个受控 Hub 实例必须且只能有一个 primary workspace 绑定；binding 直接钉住
   `profile_id + lease_id/lease_generation`，必要时还保存服务端私有 surface ID。
3. **WorkspaceProfile**：持久逻辑角色，记录用途、创建/采用/复用策略和允许动作，不保存为知识 catalog。
4. **WorkspaceLease**：运行时把 profile 解析到某个 cmux instance + raw workspace ID；只暴露 opaque ID，
   且有 freshness/失效状态。
5. **ProjectRegistration**：把 project ID 映射到受信根目录、特殊项目文件和允许的 task recipes。

关系如下：

```text
HubView --binding(profile + lease generation)-------------> cmux workspace
Action  --destination policy--> WorkspaceProfile --lease-> cmux workspace
TaskRun --pinned start lease/generation-------------------> cmux workspace
TaskRecipe --project_id--------> ProjectRegistration ------> trusted root/context file
```

raw cmux UUID 和 socket path 只存在于运行期服务状态。trusted absolute project root 可以持久化在用户本地、
不发布的受信 registry/config 中；context/handoff locator 仍使用 repo-relative path/hash。两者都不得进入
`HubCatalog` 或返回浏览器。

`WorkspaceProfile` 的建议真源是用户本地 Hub config/registry：原子更新，只保存逻辑 profile/spec/alias，
不保存 raw workspace ID。cmux workspace 可带非秘密 role marker 用于 reconcile，但名称只能展示，不能作为
静默认领键；重名或歧义必须回到 `unbound`。

### 5.3 推荐的 workspace profiles

| Profile | 典型用途 | 默认路由 |
|---|---|---|
| `hub` | 承载当前 Hub view、状态页和控制面 | `open-hub` 复用或聚焦 |
| `notion` | 打开 Notion 页面和相关 Web 窗口 | Notion action |
| `runtime` | 基础 CLI、doctor、日志和普通运行 | 非项目专属运维 action |
| `codex:<project_id>` | 项目专属 Codex worker、任务日志和项目上下文 | 对应项目的 `codex exec` recipe |

profile 不是“一定新建一个 workspace”。多个 profile 可以经显式 alias 指向同一真实 workspace；当隔离、
可见性或项目 cwd 有要求时再分开。这样既能专门管理任务，也不会因角色数产生 workspace 爆炸。

`open-hub` 的目标行为应是 ensure/reuse/focus 一个有效 binding，而不是每次靠新 instance token 临时猜测。
建议由 `open-hub` 与服务端通过一次性 nonce 完成建绑，记录 service generation、cmux instance fingerprint、
workspace 与可选 surface；复制旧 URL 不得产生第二个有效 binding，服务重启后旧 binding 必须 stale。

HubView 的动作默认只能解析到与 primary binding 相同的 cmux instance；跨 instance 路由默认拒绝，除非另有
显式授权。WorkspaceProfile 改绑后，既有 HubView/TaskRun 不能静默跟随：view 要显式迁移或 stale，run
继续钉住启动时的 lease generation。workspace 被关闭或 instance 不匹配时，应显示 `unbound/stale` 并要求
重绑或按策略重建，绝不能按名称静默接管另一个 workspace。

action destination 也应替代当前 `NONE/REQUIRED + 全局 workspace_id`：建议分为 `native/none`、
`hub_bound`、`fixed_profile`、`allowlisted_profile`。固定目标由服务端 action/recipe 持有 profile ID；人工
override 只能在该 action 的 allowlist 内。opaque lease ID 用于状态与管理，不再成为所有动作的通用下拉参数。

## 6. Codex CLI 的目标执行与管理模型

### 6.1 推荐执行拓扑

调查比较了三种方案：

| 方案 | 优点 | 问题 | 结论 |
|---|---|---|---|
| Hub server 直接 spawn `codex exec` | JSONL 和进程控制简单 | 目标 workspace 中没有可见、可管理的 terminal owner | 不符合“在 cmux 中承载”的目标 |
| 每次 run 新建 terminal surface 并传 `--command` | 任务可见 | surface 继续膨胀；命令字符串和引用边界更危险 | 不推荐作为默认 |
| 每个逻辑 workspace slot 一个长期 terminal worker | 在目标 workspace 中有可见 owner；surface 可复用；可集中管理 thread | 需要 worker protocol 和恢复策略 | **推荐** |

推荐由 cmux 只启动固定命令，例如：

```text
scholar-workflow hub-worker --slot <opaque-slot-id>
```

worker 再以 `subprocess` argv + stdin、`shell=False` 调用 Codex CLI。浏览器不能提交 shell command、cwd、
绝对路径、sandbox、permission 或任意 `-c`；这些都由已登记 TaskRecipe 和 ProjectRegistration 在服务端解析。

`opaque-slot-id` 只用于路由，不能充当认证，因为它会出现在 argv、进程列表和 terminal 中。worker 应通过
权限受限的 Unix IPC 或等价本地通道完成随机凭证、service generation、protocol version 与 recipe digest
握手。Task API 仍需继承 loopback Host/Origin/CSRF 校验，并增加严格 JSON schema、body size、idempotency
key；每个 Codex thread 必须串行加锁/排队，避免双击造成并发 resume 或重复创建 thread。worker supervisor
还必须拥有进程组、heartbeat、cancel、timeout 与 reap 语义。

### 6.2 用户可选的内容

在现有“服务端预登记任务”边界内，UI 建议只开放：

- `recipe_id`：已登记的任务类型；
- `project_id`：recipe 允许的项目；
- `effort`：创建 logical task/thread 时选择有限档位，例如快速/标准/深入，由服务端映射到 allowlisted
  recipe/profile 变体；同一 thread 生命周期内保持不变；
- `brief`：本次任务输入，作为受限任务 brief 经 stdin 交给 `codex exec`；
- `logical_task_id`：继续既有任务时显式选择，不能默认“最近一个”。

模型名、sandbox、权限和配置覆盖仍由 recipe 固定。用户选择“强度”不等于浏览器获得任意 model/config
控制权。

### 6.3 任务、run 与 thread

建议显式保存：

```text
TaskRecipe
  recipe_id, project_id, workspace_role
  allowlisted_relative_workdir, registered_context_file
  codex_profile, fixed_sandbox/permission policy
  prompt template, thread policy

LogicalTask
  task_id, recipe_id, project_id, objective, status
  active_codex_thread_id, workspace_role

TaskRun
  run_id, task_id, input summary, effort/profile
  started_at, finished_at, exit status, output summary
  codex_thread_id, forked_from_thread_id, parent_run_id
  codex_session_root_id (optional grouping only)
```

ProjectRegistration 使用 `project_id` 解析 server-only trusted root，再对 relative workdir/context file 做
symlink/confinement/hash 校验；TaskRecipe 不自行持有第二份绝对根路径。

Codex JSONL 的稳定机器事件是 `thread.started.thread_id`。Hub 应把该值存成 `codex_thread_id`，用于
resume/fork/archive；不能存进含义不明的 `session_id`。如果以后通过 App Server 读取 fork tree，可另存
`codex_session_root_id` 做聚类，但它不替代具体 thread ID。Codex transcript 仍由 Codex 自己拥有；Hub 只
保存最小调度元数据、状态、摘要和 thread identity，不复制完整对话形成第二真源。

### 6.4 Thread 策略

| 用户意图 | CLI/管理语义 |
|---|---|
| 一次性、不需继续 | `codex exec --ephemeral`；明确标记 non-resumable，不能 resume/fork/archive |
| 继续同一目标、同一项目、同一权限边界 | 使用已保存 thread ID 显式 `exec resume` |
| 从既有任务尝试另一分支 | `exec fork <thread-id>`，记录 `forked_from_thread_id` |
| 完成任务 | 先标记 LogicalTask complete 并保留；到期或人工触发、且无 active descendant 时再 archive |
| 再启用已归档任务 | 显式 unarchive 后恢复，不把 archive 当删除 |
| 改变目标、cwd、项目、profile/effort 或权限边界 | 新建 LogicalTask/thread，不强行 resume |
| 汇总多条任务 | 生成显式 summary/handoff，关联多个 task；不宣称 merge thread |

禁止自动使用“last session”一类隐式选择。同一 workspace 可能承载多个项目或任务，只有保存并核验过的
thread ID 才能 resume。当前本地 `exec resume/fork` 仍支持部分配置/model override；因此
profile/effort、cwd、sandbox 和授权边界在一个 resumable thread 生命周期内固定，是 scholar-workflow 的
安全策略而不是 Codex CLI 的技术限制。若要改变其中任一项，就新建 thread 或按预登记 recipe 显式 fork，
并用 handoff 连接上下文。

### 6.5 建议的任务流

```text
Hub UI
  -> POST Task API(recipe_id, project_id, effort, brief, logical_task_id?)
  -> server 校验 recipe / project / binding / policy
  -> route 到 codex:<project_id> workspace profile
  -> 复用或创建该 slot 的 cmux terminal worker
  -> worker 执行 codex exec 或显式 resume/fork
  -> 解析 JSONL 中的 thread_id 与状态
  -> 更新 LogicalTask + TaskRun
  -> UI 展示队列、运行中、需人工、完成、失败、已归档
```

关闭 cmux surface 本身不能证明 child process 已停止。只有 supervisor 通过 heartbeat、进程组和 worker lease
确认状态后，run 才能转为 interrupted/stale；孤儿进程按已确认策略 cancel/reap，绝不能在不可见的后台或
另一个 cmux instance 中悄悄续跑。

## 7. 与现有根规则的冲突

当前全局根规则已经允许两类动作：“新建可见会话”或“调用服务端预登记任务”；因此把固定 recipe 实现为
`codex exec` **本身不需要扩大根授权**。但现有项目级 GOALS/Hub contract/tests 只实现 blank native
session，并明确禁止浏览器提交 prompt、cwd、model、sandbox 或 command。相关限制分布在：

- `planning/GOALS.md` 的 INV31 与 NG10；
- `references/hub-contract.md`；
- `references/security-policy.md`；
- contract tests；
- 全局 `/Users/jerryfan/.claude/CLAUDE.md`。

真正需要新共识的是：浏览器是否可以提交 bounded `brief`（本质仍是 prompt），以及是否可以在预登记集合
内动态选择 effort。它不能以实现细节名义绕过。当前有两条合法路径：

### 路径 A：保持现有规则

用户只能选择预登记 TaskRecipe 和特殊项目文件，不能输入自由 brief。强度可以由 recipe 固定，也可以让
用户在 `fast/standard/deep` 等预登记 recipe 变体中选择；这仍不是 raw model/config 控制。

优点是边界最小；缺点是不能完整满足本次目标。

### 路径 B：窄幅修改规则（推荐）

允许浏览器在预登记 TaskRecipe 内提交一个受限任务 brief，并在创建 logical task/thread 时选择
allowlisted effort/profile 变体；仍禁止提交 raw command、cwd/path、model、sandbox、permission、任意
config flag。prompt 经 Task API 和 stdin 进入 worker，不放进 URL、shell command 或通用 action target。

路径 B 满足“可选强度 + 输入 prompt”，同时不把 Hub 变成任意命令执行器。它必须作为新共识显式同步到
全局 `CLAUDE.md`、`GOALS.md`、contract/security policy 和 eval/tests 后才算生效。

**本文只推荐路径 B，没有激活它。**

## 8. 已确认方向与待确认决策

### 8.1 从本次反馈可视为已确认的产品方向

- Hub 顶层不再只有“全部资料 + topic”，而应有论文、项目、工具等一级类型库，每个库承载原子 entity。
- workspace 绑定用于打开窗口和运行任务，不用于隐式读取其资源。
- Hub 应能登记按任务分工的 workspace。
- Codex 集成目标是 cmux 中的 Codex CLI/`codex exec`，不是 blank native agent-session。
- 必须有逻辑任务和 thread/run 管理，不能每个动作无条件新建会话。

这些是调查结论中的目标方向；仍需进入上位规格确认后才能修改 runtime。

### 8.2 调查时的决策门（现由正式规格冻结）

| ID | 待决策项 | 推荐默认值 |
|---|---|---|
| H-D1 | Papers/Projects/Tools 是固定核心库还是 provider-extensible | 固定三类首批库，descriptor/provider 可扩展 |
| H-D2 | Tool library 的对象范围 | 先收 allowlisted capability/tool definitions；recipe 与 run 分离 |
| H-D3 | Project identity 与本机注册分别由谁拥有 | tracked manifest 管 portable identity/layout；host-local registry 管 trusted root/enablement；禁止双写同一字段 |
| H-D4 | Knowledge Space 能否关联 project/tool | 可以；使用跨库 typed reference，当前 `HubTopic` 需升级而非直接复用 |
| H-D5 | provider 不可用时是否仍显示空库 | 显示空库、状态和诊断，不静默消失 |
| H-D6 | 服务、operational view 与普通浏览器的关系 | operational view 必须绑定；保留显式 `unbound-readonly` 诊断/阅读降级；headless service 不得无绑定执行 workspace action |
| H-D7 | prompt 安全路径 | 采用第 7 节路径 B |
| H-D8 | effort 展示和映射 | 创建 task/thread 时从预登记档位映射 named profile；thread 内不可变，不暴露任意模型/config |
| H-D9 | workspace role 复用 | 允许显式 alias；默认不为每个动作新建 workspace |
| H-D10 | thread 保留、归档和删除策略 | complete 后先保留；到期/人工触发且无 active descendant 时 archive；自动删除另行确认 |
| H-D11 | brief/output 的留存与隐私 | 只保留最小摘要和 thread identity；完整 transcript 留在 Codex |
| H-D12 | workspace/worker 被关闭后的行为 | 显式 interrupted，等待重绑/恢复；不后台漂移 |
| H-D13 | `HubDirectory` 与现行 INV29/`HubCatalog` 的关系 | 唯一 root contract 包含 versioned `knowledge_catalog`；不要长期并列两个共享根接口 |
| H-D14 | 跨库身份和引用格式 | `{library_id,item_id}` 或等价 namespaced typed ref；禁止裸 ID 跨 provider 连接 |
| H-D15 | WorkspaceProfile 真源与 reconcile | 用户本地 Hub registry 原子维护逻辑 spec/alias；marker 辅助核验，名称不自动认领 |
| H-D16 | action destination policy | `native/none`、`hub_bound`、`fixed_profile`、`allowlisted_profile`，不再使用任意全局 workspace 下拉 |
| H-D17 | 建绑与 instance scope | 一次性 nonce + service/lease generation + cmux instance fingerprint；默认拒绝跨 instance 路由 |
| H-D18 | worker/API 一致性与回收 | 认证 IPC + version/recipe digest、HTTP 幂等、每 thread 串行锁、heartbeat/cancel/process-group reap |

## 9. 推荐实施顺序（仅用于后续规划）

1. **先锁定决策**：确认第 7 节规则变更和 H-D1～H-D18。
2. **收口服务**：统一 23128 owner、版本、启动/停止/升级方式和 cmux instance handshake。
3. **建立根目录和分库**：HubDirectory、typed library API、Zotero 分页 provider、ProjectRegistry、
   ToolRegistry。
4. **建立 workspace 控制面**：WorkspaceProfile、Lease、HubViewBinding、角色路由和 stale/rebind 状态。
5. **建立任务控制面**：TaskRecipe、LogicalTask、TaskRun、cmux worker、显式 thread resume/fork/archive。
6. **重做 UI**：library-first 导航、各库分页查询、entity detail、关联 artifacts、workspace/task 状态页。
7. **最后迁移与验收**：兼容旧 HubCatalog，补安全/契约/e2e 测试，再切换正式 listener。

不能反过来先改 UI：否则新的库、workspace 和 task 语义仍会被旧 action/catalog 边界绑死。

## 10. 明确不做的事

- 不把 Hub 变成论文、项目或工具的第二权威数据库；
- 不因绑定 workspace 而扫描其文件、shell history 或运行进程；
- 不把 raw workspace UUID、socket path、绝对路径或 shell command 暴露给浏览器；
- 不从 `$PATH` 自动发现并授权工具；
- 不让浏览器自由选择 model、sandbox、permission 或任意 Codex config；
- 不为每次打开 Hub、每个 action 或每个 run 无条件新建 workspace/surface/thread；
- 不把多个 Codex thread 的关联或摘要冒充真正的 thread merge；
- 不在本结论确认前替换 23128 listener、改 runtime 或迁移 Vault。

## 11. 证据索引

| 结论 | 主要证据 |
|---|---|
| Catalog 没有 library 层 | `src/scholar_workflow/hub/models.py:97-129,233-242` |
| ResourceKind 混合语义资源与文件形态 | `src/scholar_workflow/models.py:10-17` |
| topic assembler 固定生成 paper | `src/scholar_workflow/workflows/hub_projection.py:50-155` |
| UI 只有全部资料和 topic 导航 | `src/scholar_workflow/hub/static/index.html:16-19`、`hub.js:352-373` |
| UI 全量抓 catalog/actions | `src/scholar_workflow/hub/static/hub.js:822-875` |
| 当前 Codex 是 blank agent-session | `src/scholar_workflow/hub/cmux.py:104-135`、`actions.py:262-269,729-767` |
| 测试禁止 command/prompt | `tests/contract/test_hub_actions.py:760-805` |
| workspace registry 只是 runtime opaque 映射 | `src/scholar_workflow/hub/cmux.py:198-270` |
| instance token 只用于 tree URL 匹配 | `src/scholar_workflow/hub/cmux.py:357-385` |
| 前端只有一个临时 selected workspace | `src/scholar_workflow/hub/static/hub.js:383-479,900` |
| action 请求只接受 workspace_id | `src/scholar_workflow/hub/server.py:292-359` |
| open-hub 与 server cmux env 存在分离 | `src/scholar_workflow/cli.py:114-128,176-191,671-729` |
| 正式 listener 仍为旧 0.18.0 | `planning/HANDOFF.md:52-56,300-309`，以及 2026-09-22 实时探针 |
| Zotero 全库分页 assembler 未完成 | `planning/HANDOFF.md:209-214` |
| 现行规则禁止 prompt/model/sandbox/command | `planning/GOALS.md:69,94`、`references/security-policy.md:82-84` |
| 知识系统 v2 已识别核心/原子/附属层，但未覆盖本次控制面 | `planning/knowledge-system-v2.md:1-125` |
| 持久化 snapshot 的 17/1/19/0 构成 | `~/.config/scholar-workflow/hub/catalog.json`（2026-09-22 read-only `jq`；文件 `generated_at=2026-09-21T16:30:00+08:00`） |

Codex CLI 行为的外部核验：

- [OpenAI Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)：
  `codex exec`、`--ephemeral`、JSONL `thread.started` 和显式 `resume <SESSION_ID>`。
- [OpenAI Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)：
  named profiles、model 与 `model_reasoning_effort` 配置。
- [OpenAI Codex App Server](https://learn.chatgpt.com/docs/app-server)：
  thread ID、fork lineage 与 thread `sessionId` 的区别。

## 12. 最终判断

Hub 的下一版应被定义为：

> **以论文、项目、工具等 typed libraries 为信息入口，以可跨库的 Knowledge Space 为认知上下文与关系
> 实体，以显式 workspace profiles 为窗口/运行目的地，以受控 TaskRecipe 和 Codex CLI thread 为执行
> 单元的本地研究控制面。**

当前 Hub 是这套系统的一个论文/topic 投影原型，不是可继续局部堆叠功能的最终骨架。真正的第一步是确认
上述根模型和 prompt 安全规则，然后再实现；在此之前不应动 runtime。
