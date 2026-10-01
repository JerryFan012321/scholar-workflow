# Scholar Workflow Hub v3 — 历史兼容规格

> 状态：Superseded / product direction retired，2026-10-01。当前目标规格是
> [`project-centered-refactor.md`](project-centered-refactor.md)：整合项目资料、复用原生工具，不再建设
> Hub 前端或内置 Codex 任务控制产品。以下正文保留已接受/实现方案的历史边界，不能当成新增功能授权。
> 尚未移除的 HTTP、文件操作、worker 路径继续受其原安全约束保护；未完成的 Hub 专属验收是 retired，
> 不是 pass。本次没有停止服务、删除代码、迁移 Vault 或证明完整解耦。
>
> 原状态：Accepted 1.0，2026-09-23；曾取代 `hub-control-plane-v2.md` 成为 Hub 的目标规格。
> `0.28.1` 的 lease/binding 行为只保留为迁移与回归基线；本次授权实现 v3 runtime、测试、
> 拟发布包 canary 和首个 Field 的只读预览。真实 Field 写入、其他 Vault/项目迁移、Obsidian 升级、
> 永久删除以及 verified backup 仍各自受独立门禁。
>
> 本文与 `knowledge-system-v2.md`、`project-system-v2.md` 并列，并以 `planning/GOALS.md` 为上位意图层。
> `hub-investigation-conclusion.md` 仍是调查证据，不是运行期契约。

## 1. 纠偏结论

Hub v2 把 cmux workspace lease 同时当成窗口目的地、文件授权和整个页面的可写门禁。真实使用已经证明
这一抽象错误：workspace 关闭只应使“在该 workspace 打开窗口”失败，不应让 Vault 保存、项目文档操作
或其他与 cmux 无关的功能一起变成只读。

v3 固定三组互相独立的概念：

1. **Destination**：浏览器、终端、Codex 或 CLI 窗口在哪个 cmux workspace 出现；
2. **Target**：文件或执行的可信根与能力，决定可以在哪个已登记文件夹内做什么；
3. **Action**：对一个稳定实体执行的预登记操作，声明是否需要 Destination 或 Target。

信息架构固定为：

```text
Libraries
├── Papers
└── Fields
Projects
Tools
```

- Libraries 只容纳文档集合。
- Papers 是 Zotero 全局资源列表。
- Fields 是由一个或多个显式登记的 Obsidian Source 提供的动态科研领域。
- Projects 和 Tools 与 Libraries 平级，不伪装成文档 Library。
- 公开论文类型只有 `Paper | Report | Book | Webpage | Other`；会议、期刊、预印本状态是元数据。
- Project System v2 的 `project_id`、Run/Attempt/Target、promotion 与 backup-pending 语义不变。

## 2. 权威边界

| 对象 | 权威来源 | Hub 角色 |
|---|---|---|
| 论文、附件、正式批注 | Zotero | 分页读取、解析稳定动作、显示状态 |
| Field 正文、Canvas、导航与 Source Note | 登记的 Obsidian Source 及其 manifest | 校验、预览、受控保存 |
| 项目身份与 `docs/` | 项目 manifest + 主机 registry | 按 `project_id` 解析可信根 |
| 工具、URL recipe、任务 recipe | 显式 Tool/Recipe registry | 展示与受控调用 |
| Codex transcript/thread | Codex | 仅保存允许的 thread ID、状态与摘要 |
| cmux workspace/surface | cmux | 只提供短期窗口目的地 |

Hub 不扫描磁盘、workspace 或 `$PATH` 猜测项目、工具、Source 或能力；不保存知识正文；不成为 Zotero
批注、Codex transcript 或项目身份的第二事实源。

## 3. HubDirectory v3

唯一公共根是 breaking schema v3：

```text
HubDirectory {
  schema_version: 3,
  libraries: {
    papers: PaperLibraryDescriptor,
    fields: FieldLibraryDescriptor
  },
  projects: ProjectDescriptor[],
  tools: ToolDescriptor[],
  capabilities: CapabilityMatrix,
  diagnostics: Diagnostic[]
}

EntityRef {
  provider_id,
  entity_type,
  entity_id
}
```

- 删除写死的 `papers/projects/tools/knowledge` Library 枚举。
- v3 只有 Papers 和 Fields 两个文档 Library；Projects/Tools 是根级集合。
- `EntityRef` 的 provider namespace 避免不同 Source、Zotero library 和 host registry 的 ID 冲突。
- `/api/v1/catalog` 与 `/api/v2/*` 只从当前 v3 根派生只读兼容响应；不得保留第二份可变状态。
- 旧 v1 artifact PUT、asset upload、action POST 返回 `410 Gone`，不能绕开 v3 的 Field、Target
  或 Destination 校验；兼容层不提供写入和执行入口。
- 空 Fields、Projects、Tools 仍在界面可见，并显示 provider/capability 诊断。

## 4. Papers、PDF 与直接动作

### 4.1 Papers provider

- Zotero Local API 是实时 authority；分页、查询、排序和筛选都在 provider 端完成。
- 附件 locator 必须由 Local API 的 parent/child 关系解析；禁止猜测
  `Zotero/storage/<attachment-key>/*.pdf`。
- 公开类型映射到 `Paper/Report/Book/Webpage/Other`；venue、conference、journal 不进入类型筛选器。
- 同一 work 的投影 ID 可以保留，但判重继续使用 DOI 或规范化 title+authors，不由 Hub ID 替代。

### 4.2 PDF 身份

```text
PdfRef {
  provider: "zotero",
  library_id,
  attachment_key,
  content_hash
}
```

端口、URL、绝对路径、landing route 和进程内 action ID 都不是 PDF 身份。`content_hash` 用于识别附件
字节变化和批注 snapshot 失效，不取代 attachment key。

论文分析的原文深链由结构化 SourceSpan 派生：附件身份＋hash＋零基物理页对应
`zotero://open-pdf/library/items/<key>?page=<一基物理页>`；只有 Local API 核实真实批注属于该附件时
才加入 `annotation=<key>`。它打开独立的 Zotero 原生阅读器，不能解释为在 cmux 嵌入 Zotero。
无批注时仅保证页级打开，其他格式使用各自经过验证的块/章节 locator；详见
`knowledge-system-v2.md` §7.2 与 INV53。

### 4.3 论文卡片动作

卡片直接展示以下预登记动作，不经过可见 paper/attachment landing：

1. `在 Zotero 打开`（默认主动作，执行前复验本机 PDF）；
2. `在 ZotFlow 标注`（仅在本机 storage 模式得到正向验证时可用）；
3. `在 cmux 阅读`；
4. `系统阅读器`；
5. `查看分析`；
6. `打开批注笔记`。

动作不可用时保留按钮位置并显示精确原因。ZotFlow 本机模式无法证明或 PDF 不在本机时禁用，
不得退回云端附件下载；Zotero 的本机附件同样在打开时复验。旧 `/hub/item` 与
`/open/paper` 只保留一个版本周期用于旧链接解析，不进入新 UI、Markdown 或文档示例。
ZotFlow 打开 URI 必须携带服务端选定的**已注册 Vault** 名以便 Obsidian 路由；浏览器不能
自行提交 Vault 名。若同一论文存在多个合格 Source 而动作未明确选定其中之一，失败关闭并
提示选择，不得默选第一个或落入当前活动 Vault。Vault 参数仅是打开位置，不进入 PdfRef 身份。
`在 cmux 阅读` 是本机 PDF 的只读 browser/preview surface，不承诺 Zotero 正式批注写回或原生
reader 内嵌。当前 cmux 版本没有已验证的受支持同步适配器；若日后新增，须单独设计权威写入和
无云端 PDF 下载的门禁，不能把网页登录 Zotero 文库当作本机同步方案。

## 5. 动态 Knowledge Source 与 Field

### 5.1 主机 Source registration

```text
KnowledgeSourceRegistration {
  source_id,
  provider: "obsidian",
  folder_id,
  enabled,
  capabilities
}
```

`folder_id` 由主机 registry 解析为可信根；浏览器永远不提交或接收绝对路径。一个 Source 可以是整个
Vault，也可以是用户明确选择的 Vault 子目录。

### 5.2 便携 Field manifest

每个 Source 使用 `.scholar-workflow/fields.yml`：

```yaml
schema_version: 1
source_id: <stable UUID>
fields:
  - field_id: <stable UUID>
    title: 世界模型
    relative_root: 世界模型
    home: 01-Paperlist.md
    navigation:
      - label: 核心梳理
        items: []
      - label: 论文与资料
        items: []
```

- 一个 Vault/Source 可声明多个 Field；选择子目录时可只初始化一个 Field。
- `field_id` 与 `source_id` 稳定、便携，不含主机路径。
- `home` 可指向已有目录文档；世界模型沿用 `01-Paperlist.md`，不因注册 Field 而强制新建综述首页。
- `home/resource/support` 等内部 role 只用于 owner、模板与校验，不成为公共筛选项。
- navigation 分组由每个 Field 自由定义，不建立全局固定分类树。
- 旧 `research_vault_root` 只作为迁移候选，不再是唯一知识库或启动前置条件。

### 5.3 选择、预览与确认

1. UI 调用系统文件选择器；服务端把选中目录换成进程内、30 分钟内有效且提交后消耗的 candidate token。
2. 无旧分析/旧链接的新建或追加 Field，浏览器确认只提交 candidate token 与预览列出的一个 `field_id`；不能换成
   任意路径，也不能提交未预览的 Field 身份。已有便携 manifest 在新主机首次登记时走另一种
   `token + source_id` 确认形态，明确展示将登记的全部现有 Field。
3. 无 manifest 时先执行零写入扫描，展示候选 Field、入口、导航顺序、重名、模板改写、忽略文件、
   未映射正文和旧链接改写；已有 manifest 时仍扫描尚未登记的同级候选，同时明确列出已登记项。
   明确带有外部 writer owner 标记的 ZotFlow Source Note 单列诊断，不因位于所选 Vault/目录或包含
   Markdown 就自动成为 Field/导航/普通未映射正文；不按 `Source` 等目录名推断 owner。owner 标记
   缺失身份、重复、非法或与 `sw_*` 身份冲突时失败关闭，不在预览中静默吸收。
4. 用户选择并确认一个 Field 后才创建或追加 registration/manifest；CAS、symlink、根 inode 或预览
   内容发生变化时确认失效。选择整个 Vault 不等于授权一次登记其所有候选 Field。
   登记已有便携 Source 只写主机 registry，原 manifest、Field ID 和正文不变。
5. 每个 Field 是独立事务；失败只回滚该 Field。
6. 若首次 Field 含旧分析或旧端口链接，旧式网页确认必须阻断，改由本地操作员统一事务审议
   内容、导航、链接、manifest 和 host registry；不能先登记身份再分批修改内容。operator credential
   只表示同一系统用户进程可信，不构成独立真人批准的密码学证明。
7. 若论文的一篇一目录归属同时涉及 Knowledge provider 的原子资源清单、Field 文件和
   `fields.yml`，这些变化必须共享一个可恢复的 CAS journal 和完整审议摘要，不能分别
   提交 provider 与 Field 后宣称事务完成。旧分析原件默认保留且绑定原始字节；保留区的
   历史链接如何隔离、可读导航如何改写，必须在同一计划中明确。受管分析三件套不能通过
   普通 Markdown/Canvas 搬迁捷径处理。
8. v4 分析提交只能使用已注册 Source 所指定的 provider 状态；旧 provider 快照若无可信
   Vault 根身份，须走显式重绑定/初始化，不能凭操作者传入的任意同名目录取得授权。

Field 首页直接显示 manifest navigation 与选中 Markdown 正文，不再添加文档 landing 中间页。

## 6. Destination、Target 与 Action

```text
CmuxDestination {
  destination_id,
  cmux_instance_fingerprint,
  workspace_id,
  display_name,
  expires_at
}

ExecutionTarget {
  target_id,
  kind: "project" | "vault" | "folder",
  registered_root_id,
  capabilities
}

OpenAction {
  action_id,
  kind: "web" | "pdf" | "file" | "native-app" | "terminal" | "codex",
  entity_ref,
  destination_required
}
```

### 6.1 Destination 规则

- cmux workspace 只决定窗口出现位置，不授予文件权限，也不决定 Hub 是否全局只读。
- HTTP 服务必须作为独立受管进程存活；仅窗口路由 helper 留在 cmux 终端内并经受限私有 IPC
  接受服务端已验证的操作。不得为了 socket 权限把 HTTP 服务放入任一可关闭的 workspace，
  也不得以 `CMUX_SOCKET_MODE=allowAll` 放宽 cmux 默认安全边界。
- `open-hub` 在 cmux 中运行时，记录当前 workspace 为该浏览器会话的默认 Destination。
- 每个需要 cmux 的动作可临时选择其他有效 Destination；workspace 名称只用于显示。
- 当前单个 Hub 服务只保持一个活动 cmux **实例**的路由；同一实例可有多个 workspace。若从另一
  cmux 实例运行 `open-hub`，新实例成为活动路由，旧实例页面仍可阅读，但旧 Destination 的 launch
  必须失效而不能静默投向新实例。多实例并行路由不属于 0.29.0 契约。
- workspace 关闭、cmux instance 改变或 destination 过期时，仅依赖它的 launch action 失效。
- 在 cmux 外运行 `open-hub` 仍可浏览与执行有独立授权的文件操作；需要 cmux 的动作提示先选目的地。
- Obsidian、Zotero、Preview 等原生应用不属于 cmux workspace。

### 6.2 Target 与文件授权

- Vault、Vault 子目录、项目 `docs/` 和 CLI cwd 只从已登记 `folder_id/project_id` 解析。
- 文件权限由注册根、相对路径、operation capability、CAS、inode/symlink 防护与 no-overwrite 决定。
- 项目文件 API 继续只接受 `project_id + docs-relative path`；删除进入项目 trash，Hub 不执行 Git 写入。
- Destination 的存在、消失或选择不得改变同一 Target 的授权结果。

### 6.3 Action 与浏览器输入

浏览器只可提交：`action_id`、可选 `destination_id`、允许的 `target_id`、受限 brief/effort 和
idempotency key。浏览器不得提交任意 URL、shell command、cwd/path、model、sandbox、permission、
环境变量或原始 Codex 配置。

- Notion 等 Web 工具使用预登记 URL recipe，在所选 Destination 打开 browser surface。
- CLI/Codex 使用预登记 recipe，在所选 Destination 打开 terminal surface；cwd 只来自 Target。
- brief 保持 8 KiB 上限并经 stdin 传入；固定 argv 继续使用 `shell=False`。
- resume/fork 继续使用服务端保存的明确 thread ID，禁止 `--last` 与 thread merge。

### 6.4 独立能力矩阵

`bound/read-only` 总状态退场。根至少分别报告：

```text
vault_writes
project_document_writes
cmux_launches
codex_tasks
zotflow_annotations
zotero_local_api
```

每项包含 `available`、结构化 reason、依赖与建议动作。一项失败不得掩盖其他能力。

## 7. Zotero、ZotFlow、Obsidian 与批注

### 7.1 单一权威与密钥边界

- Zotero 是正式批注的唯一权威；ZotFlow 可以作为本机 PDF 人工编辑界面，不另建浏览器批注器。
- 只有 ZotFlow 可以持有 Zotero Web API 读写密钥，且只能保存在 Obsidian SecretStorage。
- Hub、CLI、agent、配置、环境、日志和诊断不得读取、复制或请求该 Web API 密钥。
- 该独占规则只约束云端 Web API 密钥；Scholar Workflow 既有的、存于 macOS Keychain 的 Zotero
  Local API 写密钥继续服务明确入库操作。
- Agent 只经 Zotero Local API 读取批注，形成只读 `AnnotationIR`；IR 是派生结构，不是第四事实源。
- `export-annotations` 迁移到 Local API，取消直接读取 `zotero.sqlite` 的历史例外。
- ZotFlow 的元数据/批注 Web API 同步与 PDF 文件下载是不同能力。用户允许前者，禁止 Hub/ZotFlow
  为阅读 PDF 调用 Zotero Web API/WebDAV 文件端点；本机附件缺失时必须失败关闭，不假装自动补齐。

### 7.2 ZotFlowReaderAdapter

- 使用 `obsidian://zotflow?type=open-attachment...` 与 `open-annotation` 打开目标。
- 调用前检查 Obsidian 安装版本、ZotFlow manifest 版本、`minAppVersion`、启用状态、桌面本机
  `Use Zotero Storage Directory` 模式，以及经 Zotero Local API 定位的当前附件是否仍在本机。
  本机模式必须通过只返回非秘密字段的可信探针正向证明；不得读取 ZotFlow 的完整设置文件或密钥。
- 2026-09-27 复核本机 Obsidian 为 1.13.7，满足当前 Vault 内 ZotFlow 1.6.6 的 1.13.4 最低要求；
  runtime 仍必须逐次探测版本与启用状态。只有已审计其本机优先且缺文件不回退云端的 ZotFlow
  1.6.6 版本可放行；未知升级版本先禁用并重新审计，不得自动升级外部应用。
- Obsidian CLI 可作为本机模式的可选窄探针；不可用时只禁用 ZotFlow 动作，不影响 Zotero 原生
  阅读、Hub 阅读和其他能力。它不是访问 PDF 或打开 Zotero 的通用前置条件。

### 7.3 多 writer 隔离

- ZotFlow Source Note 是批注与来源信息的可读投影，与 Scholar analysis Markdown 分开存放并标记 owner。
- Field 可以在独立的非受管资源关系中引用 Source Note，但它不能作为 Field 首页、受管导航文档或
  深度分析真源；现有 `fields.yml` 的 `home`/`navigation.items` 只接受 Field 自己管理的 Markdown，
  manifest 校验及文件写入/统一事务均拒绝接管外部 owner 文件。非受管引用能力未落地前，不得通过
  把 Source Note 塞进导航路径来变相实现。
- ZotFlow、Better Notes 和 Scholar Workflow 不得写同一文件或路径前缀。
- Better Notes 可继续管理独立 Zotero Notes；不得同步到 ZotFlow Source Note 或 Scholar 管理目录。
- 已安装但未启用且上游已归档的 Zotero Integration 不进入正式依赖。

### 7.4 显式带批注 snapshot

其他 PDF 阅读器只能读取显式生成的独立 snapshot：

```text
AnnotatedPdfSnapshot {
  pdf_ref,
  source_pdf_hash,
  annotation_set_hash,
  output_hash,
  supported_types,
  omitted_types
}
```

- 永不覆盖 Zotero 原附件，也不自动导入回 Zotero。
- 原 PDF 或批注集合变化后旧 snapshot 失效，必须重建。
- snapshot 上的编辑不参与同步。
- highlight、note、underline、ink/image 分类型验证；不能无损表示时明确失败，不宣称完整导出。

## 8. 服务生命周期与 discovery

公共命令：

```text
scholar-workflow open-hub
scholar-workflow hub start
scholar-workflow hub status
scholar-workflow hub stop
scholar-workflow hub restart
scholar-workflow hub doctor
```

- `open-hub` 核对已安装 package 协议与 build，启动或安全重启 Scholar Workflow 自己管理的
  服务，再打开当前 discovery URL；用户无需知道端口、nonce、lease、源码路径或进程细节。
- 服务从已安装包启动，不接受、不读取也不依赖 code repo root。
- 监听 loopback 动态端口；PID、port、已安装 package 版本与代码 build hash、protocol、generation、
  started_at、executable、log path 写入权限 `0600` 的 runtime discovery record。插件 manifest
  版本在发布校验中另行核对；浏览器认证 token 不写入 discovery record。
- 浏览器 session auth token 与 `CmuxDestination` 分离：前者保护 API，后者只路由窗口。
- 版本/协议不符时，只能停止经 discovery、进程身份与健康握手共同证明属于 Scholar Workflow 的进程。
  未知 PID/端口或身份不一致时拒绝自动终止并给出诊断。
- 生命周期身份握手使用不访问 provider、Zotero 或 cmux 的轻量 `/api/v3/identity`；详细
  `/api/v3/health` 负责能力诊断，但其慢速/失败不能使已验证的受管 HTTP 服务被误判为失联。
  旧版本缺少 identity 端点时才对其既有 health 做兼容回退。
- `status` 显示实际 executable、版本、build、协议、端口、PID、generation、启动时间与日志。
- `stop` 幂等；确认受管进程退出后删除失效 discovery。`restart` 等于安全 stop + start。
- `/api/v3/health` 报告服务身份、根 schema、providers、capabilities 和 diagnostics；不泄漏密钥或敏感路径。

固定 23128、LaunchAgent 和旧 listener 不属于长期架构。兼容 listener 只能在迁移窗口存在。

## 9. HTTP/UI 最小面

首版已实现的核心 API（Projects/Tools 列表由 Directory 根投影）：

```text
GET  /hub/
GET  /api/v3/directory
GET  /api/v3/libraries/papers/items
GET  /api/v3/libraries/fields/items
GET  /api/v3/destinations
GET  /api/v3/actions
GET  /api/v3/execution-targets
GET  /api/v3/task-actions
POST /api/v3/actions/<action-id>
POST /api/v3/fields/select
POST /api/v3/fields/confirm
GET  /api/v3/health
```

项目文档、Field save 和 task routes 继续使用各自严格 schema。所有 state-changing route 都要求
loopback Host、same-origin、服务级 anti-CSRF token、严格 content type 和 bounded body；任务创建另有
idempotency key。candidate token 是一次性、短期有效的进程内句柄，不冒充独立浏览器会话身份。

UI 规则：

- 左侧只显示 Libraries/Papers、Libraries/Fields、Projects、Tools；Operations 进入轻量状态/诊断面板，
  不成为第五个内容分类。
- 页头使用“默认打开位置”，不使用会暗示授权的“已绑定工作区”。
- 卡片上直接显示主要动作；详情抽屉只用于补充元数据，不成为必经中间页。
- Field 首页同屏展示 navigation 与正文。
- capability 逐项禁用和解释，不使用一个全局只读遮罩。
- 不显示 raw UUID、绝对路径、端口、token、shell 或未过滤 stderr。

## 10. 迁移

### 10.1 兼容与服务迁移

1. 保存 0.28.1 API/UI/PDF 兼容基线和旧服务身份。
2. 先以拟发布包在动态端口验证 lifecycle/discovery、v3 root、Papers、direct actions 和 capability matrix。
3. v1/v2 响应从 v3 根派生；`/hub/item`、`/open/paper` 保留一个版本周期只作解析。
4. 用拟发布安装包完成真实 `open-hub`、workspace 关闭/重连、Destination、Field preview、
   ZotFlow 往返与隔离 writer 检查、独立 PDF 阅读器、JEPA/Field、Codex worker 和回归门禁；未获
   真实 Vault 写入授权时只保留只读预览，不把它记为通过的迁移验收。
5. 向用户展示上述证据与未完成项，取得发布验收；真实 Vault/Field 迁移另须逐项显式确认。
6. 验收通过后才发布 0.29.0、更新本机插件缓存；确认新服务健康后再停止已证明身份的旧兼容
   服务并移除固定 23128 依赖。旧服务不得因端口相同而被假定为 Scholar Workflow 所有。

### 10.2 首个 Source/Field

首个 Source 是当前 `02-科研技术文档` Vault，首个 Field 是“世界模型”，JEPA/V-JEPA 是首个验收样本。

每个 Field 独立执行：

1. 零写入扫描并生成 source/field preview；
2. 展示入口、导航、模板变更、重名、未映射正文、忽略项与链接改写；
3. 确认后在 Scholar 状态目录创建 recovery snapshot，并明确标记“不是 verified backup”；
4. 按完整人类模板重排受管文档，无法映射内容按原顺序进入“保留内容”；
5. CAS 校验后以 Field 为单位提交 manifest、Markdown、Canvas 与 sidecar；
6. 用户验收后才开始下一个 Field；失败只回滚当前 Field。

现有 168 条固定 `127.0.0.1:23128/open/paper/...` 链接在经确认的 Field 迁移中改为稳定
`zotero://open-pdf/...`；ZotFlow 管理内容可用其 `obsidian://zotflow?...` 协议；机器关系只存
`PdfRef`。新文档 raw loopback URL 数量必须为零。

## 11. 实施编排

```text
WI-042
├─ WI-043
├─ WI-044 → WI-047
└─ WI-045
WI-044 + WI-045 + WI-047 → WI-046
WI-045 + WI-046 + WI-047 → WI-048
WI-043 + WI-044 + WI-046 + WI-048 → WI-049
```

- WI-038 的 lease/binding 目标由 WI-044 取代；已完成事实保留，不回写历史。
- WI-034、WI-040 保留为 v2 历史记录，未完成生命周期/UI 目标分别进入 WI-043、WI-046/049。
- WI-041 的真实备份介质、保留规则和恢复演练继续独立等待决策。

## 12. 测试矩阵

### 12.1 根、身份与 provider

- 只有一个 v3 HubDirectory；v1/v2 兼容响应从它确定性派生。
- Projects/Tools 不在 `libraries`；Fields 动态来自显式 Source/manifest。
- Papers 使用 Local API 分页与附件关系，代码不猜 storage glob。
- EntityRef/PdfRef 在多 provider/library 下无冲突；持久层无端口、绝对路径和 action ID。
- 公共论文类型只有五种；venue 不成为类型。

### 12.2 Destination/Target/Action

- `open-hub` 在 cmux 内设置当前默认 Destination；同页动作可覆盖到其他 workspace。
- Notion 在目标 browser surface 打开，Codex/CLI 在目标 terminal surface 启动。
- cwd 只从 Target 解析；浏览器提交 URL/command/cwd/model/permission/env 都被拒绝。
- workspace 关闭只使相关 cmux action 失败；Vault/project 写权限结果不变，页面不全局只读。
- 无 Destination 时仍可阅读和执行有独立授权的文件操作。

### 12.3 Source/Field 与文件安全

- 整个 Vault 或子目录均可产生 preview；一个 Source 可暴露多个 Field。
- 无 manifest 必须 preview + confirm；candidate token 不能替换为绝对路径。
- 含旧分析/旧链接的首个 Field 不能经旧 confirm 先登记：operator 同一事务提交经批准的内容、
  导航、manifest、host registry 与链接；遗漏预览文档、跳过旧分析 payload、摘要过期均失败关闭。
- Hub 单文件编辑与旧 link-only 迁移均不能拆开改写受管分析 Markdown/Canvas/sidecar。
- 未登记根、traversal、symlink swap、CAS 冲突、隐式覆盖全部拒绝。
- Field 首页直接展示 navigation/Markdown；内部 role 不进入复杂公共筛选。
- 项目 `docs/`、trash、Git warning 与 no-Git-write 契约不回归。

### 12.4 ZotFlow 与批注

- Obsidian/ZotFlow 版本不满足 manifest 时禁用动作并报告精确升级条件。
- 本机 storage 开关/目录未被正向验证或附件文件缺失、变化时，ZotFlow 和 Zotero 原生动作均不得
  以旧卡片状态继续打开；不得借此触发云端 PDF 下载。
- ZotFlow 创建的 annotation 同步到 Zotero 后可用同一 annotation key 经 Local API 读取。
- Zotero 侧改变由 ZotFlow 自己的显式 diff 同步，不由 Hub 推断冲突。
- 2026-09-29 隔离真实卡片 canary 已验证注册 Source `02-科研技术文档` 的服务端动作及系统打开可到达正式 Vault Reader；这不替代从开发版 Hub 页面连续点击至 Reader 的 UI 验收，也不构成发布批准。
- 配置、环境、日志、诊断和进程中均不存在 Zotero Web API 密钥。
- ZotFlow Source Note、Better Notes 和 Scholar analysis writer/path 无重叠。
- snapshot 至少被两个独立阅读器识别；不支持类型必须明确失败。

### 12.5 Lifecycle、知识与项目回归

- start/status/stop/restart 幂等；discovery mode 为 0600，stale record 可安全清理。
- build/version 不匹配只重启自身受管进程；未知 listener/PID 不被终止。
- `open-hub` 不依赖源码目录或固定端口，状态能证明真实 executable/build。
- JEPA 分析继续满足人类 Markdown、inline evidence、反链、单一流程和 Canvas 节点预算。
- Run/Attempt/Target、promotion 与 backup-pending 继续通过既有回归。
- 新文档 raw 23128 链接为零；未确认迁移时真实 Vault 逐字节不变。

## 13. 发布与完成定义

目标版本为 `0.29.0`，双宿主 manifest 必须同步。先在隔离环境从当前 main 构建候选安装包，
完成完整回归、runtime 边界与个人路径/密钥泄漏检查、真实 canary 和用户验收；只有验收通过后，
才由既有 release builder 生成正式 release 分支、推送并更新用户安装。

完成必须同时满足：

1. 用户只运行 `scholar-workflow open-hub` 即可打开正确构建，无需知道端口、lease 或源码目录；
2. workspace 只表示“默认打开位置”，不改变任何文件授权；
3. 新知识库按“选择 Vault/目录 → 预览 → 确认”增加，Fields 无固定枚举；
4. Libraries 只有 Papers/Fields，Projects/Tools 平级；
5. 论文卡片以 Zotero 本机附件为默认一跳入口；已证明本机模式时另可一跳打开 ZotFlow，
   cmux、系统阅读器及分析/批注文档仍为直接动作；
6. Zotero 是批注唯一权威，ZotFlow 独占 Web API 密钥，agent 只经 Local API 读取；
7. 服务可发现、可停止、可重启并证明运行版本，新知识内容不含固定 23128 链接；
8. 未明确进入相应迁移步骤前，不升级 Obsidian、不卸载插件、不迁移其他 Vault/项目，也不宣称
   recovery snapshot 是 verified backup。
