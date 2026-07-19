# Scholar Workflow：Claude Code Skill Plugin 设计文档

> 状态：提案 v0.3  
> 日期：2026-07-19  
> 上位文档：`PROJECT.md`  
> 首要运行环境：Claude Code  
> 未来兼容方向：Codex 可调用同一确定性 CLI，但不改变 Claude 插件的首要设计

## 1. 文档定位

本文把 `PROJECT.md` 中的描述性要求落实为可实现、可测试、可逐步交付的 Claude Code 插件架构。本文不得改变以下上位目标：

1. 管理论文、书籍、技术文档及相关数据，但第一阶段优先实现论文与技术文档。
2. 每个对象只能有一个主存储位置，其他系统只保存索引、投影或管理信息。
3. 论文 PDF 的自动获取和传递源头只能是 arXiv；其他来源只能用于论文身份和元数据核验。
4. 所有外部写入必须先形成计划并获得用户批准。
5. Zotero、Obsidian Vault 和 Notion 各司其职，不互相复制主数据。
6. 大型目录必须采用分层索引，先读索引，再按需读取实体文件。
7. 插件由 Git 管理，功能必须有评测和回归测试。
8. 首要宿主是 Claude Code；未来可通过确定性 CLI 或 `codex exec` 复用底层能力。
9. 当前 Zotero 写入必须通过自研 Zotero 插件在 Zotero 进程内完成；未来只有在官方 Local API 提供并通过完整写能力验证后，才允许切换到 Local API。

## 2. 关键概念与唯一主存储

“唯一主存储”需要区分逻辑主库、物理文件位置和派生投影。

| 对象 | 权威主库 | 物理位置 | 其他系统中的形式 |
|---|---|---|---|
| 论文书目、分类、标签、附件关系 | Zotero | Zotero 数据库由 Zotero 自己管理，禁止外部程序直接写入 | Obsidian 与 Notion 仅保存稳定标识和投影 |
| 论文 PDF | Zotero 管理的附件 | 可配置的 `papers_root`；当前默认 `${HOME}/Documents/3-knowledge base/31-papers` | Obsidian 论文表保存 Zotero key 和相对路径；Notion 保存本地打开链接 |
| 个人知识与笔记 | Obsidian Vault | 可配置的 `vault_root`；当前为 `${HOME}/Documents/3-knowledge base` | Notion 可保存简洁大纲或入口，不复制正文 |
| 技术文档、网站快照、draw.io 等 | Obsidian Vault | Vault 内对应分类目录 | Notion 保存类目、摘要、状态和本地打开链接 |
| 知识大纲、类目、项目、任务 | Notion | Notion 页面和数据库 | 本地只保存同步映射和操作状态，不复制完整 Notion 内容 |
| 插件运行状态 | Scholar Workflow 状态库 | `SCHOLAR_WORKFLOW_HOME` 下的 SQLite/JSON | 仅用于幂等、重试和映射，不成为知识主库 |

### 2.1 必须长期成立的不变量

1. 一篇论文最多对应一个 Zotero 父条目和一个主 PDF 附件。
2. `papers_root` 只能存放论文 PDF；技术文档即使是 PDF，也必须进入 Vault 的技术文档分类，而不是 `31-papers`。
3. 论文 PDF 的位置可以迁移，但必须通过配置和 Zotero 附件关系完成，不得在多个目录复制。
4. Obsidian 论文表是可重建的派生索引，不是论文主库。
5. Notion 不上传论文、技术文档、图片或数据文件。
6. Notion 中的机器字段可以更新；人工撰写内容不得被同步程序覆盖。
7. 运行状态库只记录映射、游标、任务状态和审计信息，不保存知识正文。
8. 外部程序不得直接写 `zotero.sqlite`。
9. 当前 Zotero Local API 只用于读取；所有当前写操作只能通过自研 Zotero Bridge。
10. Zotero 写入必须经过统一 `ZoteroWriteAdapter`。未来 Local API 能力满足要求时可以替换 Bridge，但业务流程、审批和 Contract 不随实现后端变化。
11. 写入后端切换必须基于能力探测、官方文档和合同测试，不能只根据 Zotero 版本号猜测。

## 3. 范围与非目标

### 3.1 第一阶段范围

- 从用户给出的 DOI、arXiv ID、标题、URL、CSV 或本地文件开始处理。
- 通过网络和本地索引获取论文元数据，完成规范化、身份解析和判重。
- 在下载前检查输入批次、运行状态库、论文目录和 Zotero。
- 仅从 arXiv 自动下载论文 PDF。
- 推荐已有 Zotero Collection，并由用户确认最终 Collection。
- 通过本地 Zotero Bridge 创建或更新条目、链接 PDF、添加分类和标签。
- 在 Obsidian 对应主题目录更新论文索引表。
- 在 Notion 更新知识类目、项目状态、任务和本地打开链接。
- 为大型论文集合生成分层索引。
- 生成带证据的文献发展脉络，并渲染为时间线或树图。
- 审计 Zotero、论文目录、Obsidian 索引与 Notion 投影之间的漂移。

### 3.2 暂不实现

- 自动从出版社、网盘、搜索引擎或非 arXiv 站点下载论文 PDF。
- 绕过付费墙、验证码、登录或访问控制。
- 自动删除、覆盖或合并身份冲突的 Zotero 条目。
- 直接写 Zotero SQLite。
- 在当前 Zotero Local API 不具备写能力时绕过自研插件写入。
- 把论文全文或技术文件上传到 Notion。
- 在没有证据的情况下自动宣布某篇论文是“里程碑”或“突破性工作”。
- 第一阶段自动下载书籍、标准或数据集；这些对象先支持元数据和索引，文件策略单独设计。

## 4. 总体架构

```text
用户
  │
  ▼
Claude Code Plugin
  ├─ Agents：岗位、责任、权限边界
  ├─ Skills：可触发的标准作业流程
  ├─ References：分类、来源、安全和数据规则
  ├─ Contracts：结构化输入、输出与交接协议
  └─ Hooks：少量必须自动发生的安全与状态动作
  │
  ▼
scholar-workflow CLI（确定性引擎）
  ├─ resolve / normalize / dedup
  ├─ plan / apply / resume / audit
  ├─ arXiv PDF 下载与校验
  ├─ Obsidian 索引维护
  ├─ Notion 管理投影
  └─ 本地链接解析服务
  │
  ├───────────────────────────┐
  ▼                           ▼
ZoteroWriteAdapter            Obsidian CLI / 文件适配器
  ├─ plugin_bridge（当前）     Notion REST 适配器
  └─ local_api（未来能力门控）
  │
  ▼
Zotero + ZotMoov
```

### 4.1 判断与确定性的分界

Claude 负责：

- 理解用户意图和资源类型；
- 决定调用哪个 Skill 或 Agent；
- 解释候选论文和冲突；
- 推荐 Collection、Vault 分类和 Notion 类目；
- 展示写入计划并取得批准；
- 对文献脉络做基于证据的综合判断。

确定性引擎负责：

- 标识符规范化、路径规范化和散列；
- PDF 下载、文件头校验、内容散列和原子移动；
- Zotero、Obsidian、Notion 的幂等 upsert；
- 状态机、重试、审计和机器可读报告；
- JSON Schema 校验；
- 安全白名单和路径越权检查。

Claude 不得在提示词中重新实现已有的确定性算法。

## 5. Claude Code 插件结构

```text
scholar-workflow/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json              # 发布到个人 marketplace 时启用
├── agents/
│   ├── intake-agent.md
│   ├── library-agent.md
│   ├── knowledge-agent.md
│   ├── lineage-agent.md
│   └── audit-agent.md
├── skills/
│   ├── discover-literature/
│   │   └── SKILL.md
│   ├── plan-paper-import/
│   │   └── SKILL.md
│   ├── import-paper/
│   │   └── SKILL.md
│   ├── file-technical-document/
│   │   └── SKILL.md
│   ├── update-knowledge-index/
│   │   └── SKILL.md
│   ├── sync-notion-structure/
│   │   └── SKILL.md
│   ├── locate-resource/
│   │   └── SKILL.md
│   ├── build-literature-tree/
│   │   └── SKILL.md
│   └── audit-scholar-state/
│       └── SKILL.md
├── bin/
│   └── scholar-workflow
├── src/scholar_workflow/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── identity.py
│   ├── state.py
│   ├── planning.py
│   ├── approvals.py
│   ├── adapters/
│   │   ├── arxiv.py
│   │   ├── zotero_local.py
│   │   ├── zotero_bridge.py
│   │   ├── obsidian.py
│   │   ├── notion.py
│   │   └── local_links.py
│   └── workflows/
│       ├── paper.py
│       ├── document.py
│       ├── lineage.py
│       └── audit.py
├── integrations/
│   └── zotero-bridge/                 # 独立构建并安装到 Zotero 的插件
├── references/
│   ├── storage-policy.md
│   ├── source-policy.md
│   ├── classification-policy.md
│   ├── zotero-fields.md
│   ├── obsidian-index-format.md
│   ├── notion-schema.md
│   ├── literature-edge-evidence.md
│   └── security-policy.md
├── contracts/
│   ├── resource.schema.json
│   ├── action-plan.schema.json
│   ├── zotero-import.schema.json
│   ├── index-entry.schema.json
│   ├── notion-projection.schema.json
│   ├── literature-graph.schema.json
│   └── handoff.schema.json
├── hooks/
│   └── hooks.json
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   └── fixtures/
├── evals/
│   ├── routing.json
│   ├── safety.json
│   └── outcomes.json
├── PROJECT.md
├── DESIGN.md
├── AGENT.md
└── CLAUDE.md
```

按照 `PROJECT.md`：日常规则只修改 `AGENT.md`；`CLAUDE.md` 引用 `AGENT.md`、RTK 规则，并写明“所有修改都放到 AGENT.md”。该 `CLAUDE.md` 用于开发此仓库。Claude 官方插件安装后不会自动把插件根目录的 `CLAUDE.md` 注入上下文，因此运行期规则必须放入 Skills、Agents 和 Hooks，不能只写在 `CLAUDE.md`。

## 6. Agent 设计

| Agent | 主要责任 | 默认权限 |
|---|---|---|
| `intake-agent` | 资源分类、论文发现、元数据核验、候选去重 | 本地只读；明确请求或确认后联网；禁止写外部系统 |
| `library-agent` | 论文导入计划、Collection 推荐、调用 `ZoteroWriteAdapter` | 先 dry-run；只有已批准计划可以写 Zotero 和论文目录；当前后端固定为自研 Bridge |
| `knowledge-agent` | Obsidian 索引、技术文档归档、Notion 结构投影 | 只修改计划列出的目标；保护人工区块 |
| `lineage-agent` | 论文关系、里程碑和贡献证据综合 | 默认只读；产物写入前需批准 |
| `audit-agent` | 跨系统一致性检查和漂移报告 | 只读；不得自动修复或删除 |

每个 Agent 文件只定义岗位、输入、输出、可使用 Skills、禁止动作和交接要求。具体操作步骤放在 Skills，详细知识放在 References，结构化交接放在 Contracts。

每个 Agent 在处理具体项目时维护临时知识索引，记录已读索引、关键文件、未决问题和产物位置；它是会话工作记忆，不替代 Vault 或 Zotero 主数据。

## 7. Skill 设计

### 7.1 `discover-literature`

触发：用户要求搜索论文、核验论文身份、整理候选列表或从本地库查找相关论文。

输出：候选列表、匹配依据、已有状态、可获取的 arXiv ID、风险与下一步建议。

约束：

- 用户明确要求联网搜索时，该请求即构成搜索授权；否则先询问。
- 可以使用 Crossref、OpenAlex、Semantic Scholar、出版社页面等核验信息，但不得从这些来源下载或传递论文 PDF。
- 搜索与下载分离；发现阶段不产生文件写入。

### 7.2 `plan-paper-import`

触发：用户给出论文列表或候选，并希望加入系统。

操作：

1. 规范化 DOI、arXiv ID、标题、作者和年份。
2. 检查输入批次、状态库、论文目录和 Zotero。
3. 生成 Collection 与 Vault 索引位置建议。
4. 生成结构化 `action-plan.json`。
5. 向用户展示新增、更新、跳过、冲突、下载和写入目标。

该 Skill 永远是 dry-run。

### 7.3 `import-paper`

触发：用户批准某个导入计划，或明确调用已生成的 `plan_id`。

约束：

- 没有有效 `plan_id` 不得执行。
- 计划内容发生变化时必须重新批准。
- 自动下载只允许 arXiv PDF。
- 所有 Zotero 写入必须调用 `ZoteroWriteAdapter`；当前 Bridge 健康检查失败时停止，不得回退到不可写的 Local API、Web API 或直接数据库写入。
- 强标识符冲突、同名冲突或分类不确定时停止该条目，不影响批次中其他安全条目。
- 完成后返回 Zotero item key、attachment key、PDF 相对路径、索引位置和 Notion 投影状态。

### 7.4 `file-technical-document`

触发：用户要求归档技术文档、网页快照、draw.io、图片或其他非论文技术资料。

约束：

- 先分类 `resource.kind`，不能把技术 PDF 当成论文 PDF。
- 文件进入 Vault 对应分类，不进入 `papers_root`，不创建论文 Zotero 条目。
- Notion 只保存结构、摘要、状态和本地链接。
- 原始来源、抓取时间和内容散列写入元数据。

### 7.5 `update-knowledge-index`

触发：论文导入完成、Collection 调整、PDF 迁移或用户要求重建主题论文表。

约束：

- 从 Zotero 和状态映射重建索引，不把 Obsidian 表当主数据。
- 只更新带管理标记的表格区块，保留区块外的人工笔记。
- 表格至少包含题名、作者、年份、会议/期刊、Zotero item key、PDF 相对路径、arXiv、DOI 和同步时间。
- 大目录先更新上层描述和子索引，再更新叶级表格。

### 7.6 `sync-notion-structure`

触发：用户要求同步知识大纲、类目、项目、任务或资源入口。

约束：

- 不上传文件。
- 只写机器管理字段，保留人工内容。
- 通过稳定 Resource ID upsert，不按标题盲目新建。
- 链接指向本地链接解析服务或稳定 Web 入口。

### 7.7 `locate-resource`

触发：用户询问论文或技术文档在哪里、要求在 cmux 中打开、或把本地文件交给分析工具。

操作：

- 论文先查 Zotero item/attachment，再解析 `papers_root` 下的相对路径。
- 技术文档根据 Vault 相对路径解析。
- 默认只返回和打开，不复制文件。

### 7.8 `build-literature-tree`

触发：用户要求生成某主题的论文时间线、发展脉络、follow-up 关系或突破性贡献图。

输出：

- 规范化 `literature-graph.json`；
- Obsidian Markdown 说明；
- Mermaid、draw.io 或 HTML/PNG 可视化；
- 可选的 Notion 简洁大纲投影。

每条边必须包含关系类型、证据来源、解释、置信度和审核状态。引用关系只能证明“有引用”，不能单独证明“方法继承”或“突破”。

### 7.9 `audit-scholar-state`

触发：用户要求检查库状态，或执行定期维护。

检查：

- Zotero 条目是否存在、是否重复、Collection 是否正确；
- PDF 是否存在于配置根目录，散列与附件是否一致；
- Obsidian 索引是否能解析到 Zotero 和文件；
- Notion Resource ID 是否重复、链接是否可解析；
- 大目录索引是否与实际内容一致。

默认只报告，不自动修复或删除。

## 8. 配置与运行数据

### 8.1 配置分层

1. `.claude-plugin/plugin.json` 的 `userConfig`：首次安装时询问非敏感路径和功能开关。
2. `${SCHOLAR_WORKFLOW_HOME}/config.yml`：复杂映射、项目配置和策略；默认 `${HOME}/.config/scholar-workflow`。
3. Claude 插件的 `${CLAUDE_PLUGIN_DATA}`：插件依赖、虚拟环境和安装缓存，不保存用户知识文件。
4. 系统钥匙串或敏感 `userConfig`：Notion token、Bridge token 等短凭证。

### 8.2 配置示例

```yaml
version: 1

paths:
  papers_root: "${HOME}/Documents/3-knowledge base/31-papers"
  vault_root: "${HOME}/Documents/3-knowledge base"

policy:
  paper_pdf_source: arxiv_only
  require_approval_for_download: true
  require_approval_for_distribution: true
  allow_direct_zotero_sqlite_write: false
  notion_file_upload: false

zotero:
  local_api_url: "http://127.0.0.1:23119/api"
  bridge_url: "http://127.0.0.1:23119/scholar-workflow/v1"
  write_backend: auto
  write_backend_preference:
    - local_api
    - plugin_bridge
  local_api_write: capability_gated
  plugin_bridge_write: enabled
  allow_direct_sqlite_write: false
  attachment_mode: linked_file
  prefer_zotmoov: true

obsidian:
  cli_command: obsidian
  direct_file_fallback: true
  managed_block_start: "<!-- scholar-workflow:start -->"
  managed_block_end: "<!-- scholar-workflow:end -->"

notion:
  enabled: true
  file_upload: false
  preserve_human_content: true

local_links:
  bind: "127.0.0.1"
  port: 23128

projects:
  world-model:
    zotero_collection_key: "..."
    obsidian_index: "32-documents/02-科研技术文档/world-model/论文索引.md"
    notion_project_id: "..."
```

路径必须在运行时展开并规范化；配置文件中不得保存展开后的用户私密绝对路径到 Git。

## 9. 核心数据模型

### 9.1 Resource

```json
{
  "resource_id": "paper:arxiv:2401.01234",
  "kind": "paper",
  "title": "...",
  "identifiers": {
    "doi": "...",
    "arxiv": "2401.01234"
  },
  "zotero": {
    "item_key": null,
    "attachment_key": null,
    "collection_keys": []
  },
  "file": {
    "root": "papers_root",
    "relative_path": null,
    "sha256": null,
    "source": "arxiv"
  },
  "projections": {
    "obsidian_index": null,
    "notion_page_id": null,
    "local_url": null
  }
}
```

`resource_id` 在导入前可以基于 arXiv、DOI 或规范化元数据生成；导入后必须绑定 Zotero item key，但不得因为 Zotero key 变化而创建第二个内部对象。

### 9.2 Action Plan

```json
{
  "plan_id": "uuid",
  "created_at": "...",
  "expires_at": "...",
  "input_digest": "sha256:...",
  "actions": [
    {
      "resource_id": "paper:arxiv:2401.01234",
      "operation": "create",
      "download": "https://arxiv.org/pdf/2401.01234",
      "zotero_collection_key": "...",
      "obsidian_index": "...",
      "notion_projection": true,
      "conflicts": []
    }
  ]
}
```

执行器必须验证 `plan_id`、输入散列、配置版本和批准状态。任何实质变化都会使旧批准失效。

### 9.3 Literature Edge

```json
{
  "from": "paper:zotero:AAAA1111",
  "to": "paper:zotero:BBBB2222",
  "relation": "method-extension",
  "evidence": [
    {
      "type": "paper-text",
      "location": "introduction",
      "summary": "..."
    }
  ],
  "confidence": 0.82,
  "review_status": "proposed"
}
```

允许的关系类型必须受控，例如 `cites`、`follow-up`、`method-extension`、`representation-shift`、`benchmark-successor` 和 `contradicts`。

## 10. 端到端工作流

### 10.1 论文发现与导入

```text
用户输入
  → 分类为 paper
  → 本地/Zotero 判重
  → 网络元数据解析
  → 仅确认 arXiv PDF 可用性
  → 推荐 Zotero Collection 与 Obsidian 索引位置
  → 输出 dry-run 计划
  → 用户批准
  → 下载到临时目录
  → 校验 %PDF、大小、页数、SHA-256
  → Zotero Bridge upsert 条目
  → 放入 papers_root 并建立 linked_file
  → 更新 Obsidian 论文表
  → 更新 Notion 管理投影和本地链接
  → 写入完成回执
```

如果 arXiv 不存在，记录元数据和候选状态，但不自动从其他来源获取 PDF。

### 10.2 技术文档归档

```text
用户输入或 URL
  → 分类为 technical_document / snapshot / drawio / image / dataset
  → 推荐 Vault 分类
  → 输出写入计划
  → 用户批准
  → 下载或复制到 Vault
  → 写来源、时间、散列和相对路径元数据
  → 更新上层索引
  → 可选更新 Notion 类目与本地链接
```

该流程不调用论文导入接口，也不把文件放入 `31-papers`。

### 10.3 文献发展脉络

1. 从 Zotero Collection、论文索引或用户列表确定集合。
2. 读取分层索引，按需获取论文摘要或全文。
3. 生成候选引用边和方法关系边。
4. 为每条非纯引用关系提取证据并给出置信度。
5. 区分“里程碑”“突破性贡献”和普通 follow-up。
6. 让用户审核低置信边和里程碑判断。
7. 保存规范化图数据，再生成图片；图片不是唯一数据源。

## 11. Zotero 写入适配器与自研插件

Python 引擎只依赖统一的 `ZoteroWriteAdapter`，不直接依赖具体 Zotero 写入方式。Adapter 必须提供同一组 Contract、幂等语义、错误码和审批约束。

当前 Zotero Local API 不提供本项目需要的完整写能力，因此当前唯一可用的 Adapter 是 `plugin_bridge`：由本项目自行编写、构建并安装的 Zotero 插件，运行在 Zotero 进程内。Claude 插件和 Python 引擎只能通过它暴露的受限本地 HTTP API 请求写操作。

未来 Zotero 官方 Local API 如果提供完整写能力，可以实现 `local_api` Adapter 并优先使用；这属于后端替换，不改变上层 Skill、Action Plan、状态机或用户批准流程。

### 11.1 写入后端能力门槛

只有同时满足以下能力并通过真实合同测试，Local API 才能被选为写入后端：

- 创建和更新论文父条目；
- 写入受控书目字段；
- 添加和调整 Collection；
- 添加和更新标签；
- 创建论文 PDF 子附件；
- 为 `papers_root` 中的文件建立可解析的 `linked_file`；
- 返回 item key、attachment key、对象 version 和最终路径；
- 支持并发保护或等价的条件写入；
- 支持幂等请求或由 Adapter 可靠实现幂等；
- 官方文档明确将相应端点列为可写且稳定接口。

启动时执行 capability probe，并记录选择结果：

```text
Local API 满足全部能力 + 合同测试通过
  → 使用 local_api
否则
  → 使用 plugin_bridge
plugin_bridge 也不可用
  → 失败关闭，禁止写入
```

直接写 `zotero.sqlite` 永远不属于任何 Adapter。

### 11.2 自研 Bridge 必须具备的能力

Bridge 第一阶段必须支持创建或更新父条目、写入元数据、Collection 和标签、建立论文 PDF 子附件、创建 `linked_file`、返回稳定 key/version/path，并在能力验证通过后调用 ZotMoov。

删除、任意字段写入、任意文件附件、执行 JavaScript、执行 SQL 和执行 shell 不进入第一阶段公开接口。

### 11.3 Bridge 固定接口

```text
GET  /scholar-workflow/v1/health
GET  /scholar-workflow/v1/collections
GET  /scholar-workflow/v1/items/{itemKey}
POST /scholar-workflow/v1/papers/upsert
POST /scholar-workflow/v1/attachments/link
POST /scholar-workflow/v1/items/update-metadata
```

接口可以合并为事务型 `papers/upsert`，但不得提供 `eval`、SQL、shell 或任意路径操作。

### 11.4 Bridge 写入事务

Python 引擎生成并校验 `zotero-import.json`，Bridge 在 Zotero 进程内再次校验后执行：

```text
health/version check
  → token + schema + idempotency validation
  → dedup inside Zotero
  → create/update parent item with saveTx()
  → collection/tag update
  → linked PDF attachment
  → optional ZotMoov filing
  → return keys, version and final path
```

Bridge 必须自己完成最后一次 Zotero 内部判重，不能完全信任外部计划。部分失败时返回结构化阶段状态，由 Python 状态机恢复；不得通过自动删除已成功条目模拟回滚。

### 11.5 安全要求

- 仅监听 `127.0.0.1`。
- 使用随机 token，放在请求头，不放在 URL。
- 所有写请求要求 idempotency key。
- 只允许 `papers_root` 和受控临时目录中的规范化路径。
- 拒绝 `..`、符号链接越界、超大请求和非 PDF 附件。
- 对 Origin 和 Content-Type 做限制，防止网页构造简单 POST 触发写入。
- 日志不得记录 token、全文或敏感绝对路径。
- 不直接写 SQLite；只调用 Zotero JavaScript API 并使用事务保存。
- Bridge 的写接口采用动作白名单；所有未声明动作一律拒绝。
- 当前 Local API 适配器不得伪造写能力；能力探测失败时必须返回不可写。

### 11.6 ZotMoov 适配

第一优先级是复用已安装的 ZotMoov，而不是重做它的文件整理能力。实现前先验证当前 ZotMoov 版本是否暴露可由另一个 Zotero 插件稳定调用的内部入口：

- 若入口稳定：Bridge 创建父条目和临时附件，再让 ZotMoov 完成转换与归档。
- 若没有稳定入口：当前仍由 Bridge 在白名单目录内完成原子移动，再用 Zotero JavaScript API 创建 `linked_file`；未来 Local API 只有在同样支持该能力时才可替代 Bridge。

不能把“计划复用 ZotMoov”写成“已经存在可调用 API”的既定事实。

## 12. Obsidian 设计

优先使用官方 Obsidian CLI，以便使用 Vault 的路径解析、链接更新和插件能力。CLI 不可用时允许直接文件适配器，但只执行原子写入，并严格限制在 `vault_root`。

论文索引采用可管理区块：

```markdown
# World Model 论文索引

这里保留人工说明。

<!-- scholar-workflow:start -->
| 论文 | 年份 | Venue | Zotero | PDF | arXiv | DOI |
|---|---:|---|---|---|---|---|
<!-- scholar-workflow:end -->

这里继续保留人工笔记。
```

大型目录的索引结构为：

```text
领域总览
  → 子领域说明与索引
    → 主题论文表 / 技术文档目录
      → 实体文件或 Zotero 条目
```

审计任务负责检查索引与目录是否一致，正常读取遵循“先索引、再按需取实体”的原则。

## 13. Notion 设计

Notion 只承担知识和项目管理投影，不承担文件存储。

建议数据库字段：

| 字段 | 用途 |
|---|---|
| Resource ID | 幂等 upsert 主键 |
| Name | 题名或文档名 |
| Type | Paper / Technical Document / Dataset / Project |
| Category | 知识类目 |
| Project | 所属项目 |
| Status | 阅读、研究或项目状态 |
| Summary | 简洁、重要的知识摘要 |
| Zotero Item Key | 论文跳转和定位 |
| Local URL | cmux 中打开本地资源 |
| Web Source | arXiv、DOI 或原始网站 |
| Sync Revision | 增量同步和冲突判断 |
| Last Synced | 最近机器更新时间 |

同步适配器必须声明机器管理字段列表，不得更新人工正文、人工评论或非管理字段。

### 13.1 本地链接服务

不要在 Notion 中永久写死绝对 `file://` 路径。使用本机回环链接：

```text
http://127.0.0.1:23128/open/paper/{zotero-item-key}
http://127.0.0.1:23128/open/document/{resource-id}
```

解析服务：

- 仅监听回环地址；
- 只接受不透明 ID，不接受任意文件路径；
- 从 Zotero 或状态映射解析当前相对路径；
- 限制最终文件位于 `papers_root` 或 `vault_root`；
- 默认返回一个本地预览/确认页，再交给 cmux 浏览器打开；
- 不提供任意 shell 执行能力。

这样迁移论文目录、Vault 或设备后，只需改变本地配置，不需要批量修改 Notion。

## 14. 权限与用户批准

| 动作 | 默认策略 |
|---|---|
| 读取本地索引、状态、Zotero Local API | 允许 |
| 用户明确要求的网络检索 | 允许；否则先询问 |
| 从 arXiv 下载论文 PDF | 必须先展示计划并批准 |
| 写 Zotero、移动 PDF、写 Vault、写 Notion | 必须先展示计划并批准 |
| 打开本地文档 | 用户请求即构成授权 |
| 修改类目映射 | 展示差异并批准 |
| 删除、覆盖冲突、合并条目 | 禁止自动执行，逐项批准 |
| 直接写 Zotero SQLite | 永久禁止 |

一次批准可以覆盖计划中明确列出的批次，不必对每篇无冲突论文重复询问。新增目标、路径变化或冲突处理会使批准失效。

## 15. CLI 设计

```text
scholar-workflow doctor
scholar-workflow discover <query-or-input>
scholar-workflow resolve <input>
scholar-workflow plan paper-import <input>
scholar-workflow apply <plan-id>
scholar-workflow resume <job-id>
scholar-workflow locate <identifier>
scholar-workflow index rebuild <project-or-category>
scholar-workflow notion sync <project-or-category>
scholar-workflow lineage build <topic-or-collection>
scholar-workflow audit [--scope ...]
scholar-workflow report <job-id> --format json|md|csv
```

所有命令支持 `--json`；Claude 应优先消费 JSON，避免解析面向人的文本。写命令必须返回 `job_id`、逐项状态和可重试错误码。

推荐退出码：

| 退出码 | 含义 |
|---:|---|
| 0 | 完成 |
| 2 | 输入或配置错误 |
| 3 | 依赖未运行，例如 Zotero/Obsidian 未启动 |
| 4 | 需要用户批准或人工判断 |
| 5 | 身份或分类冲突 |
| 6 | 部分完成，可恢复 |
| 7 | 安全策略拒绝 |
| 8 | 外部服务错误 |

## 16. 状态机、幂等与恢复

论文任务状态：

```text
received
  → classified
  → resolved
  → deduplicated
  → planned
  → approved
  → downloaded
  → zotero_synced
  → obsidian_indexed
  → notion_projected
  → completed
```

异常状态：

```text
awaiting_approval
identity_conflict
classification_conflict
no_arxiv_pdf
download_failed
zotero_failed
obsidian_failed
notion_failed
policy_denied
```

每一步保存输入散列、输出标识和完成时间。重试从最后一个成功步骤继续，不重复下载、创建 Zotero 条目或新建 Notion 页面。

跨系统事务无法做到真正原子，因此采用 Saga：每一步可重试，失败后保留已成功结果并报告；不得用自动删除已成功数据来模拟回滚。

## 17. Hooks 设计

Hooks 只用于必须自动发生且适合确定性检查的动作：

1. `SessionStart`：运行轻量 `doctor --json`，只报告关键依赖状态，不自动安装或写外部系统。
2. `PreToolUse`：拦截直接写 `zotero.sqlite`、越界文件写入和未批准的 apply 命令。
3. `PreCompact`：若存在进行中的 job，保存最小 handoff，包括 `job_id`、最后成功状态、待处理冲突和产物路径。

不要用 Hooks 承载业务流程，不要为每次普通读取增加门禁。

## 18. 评测与验收

### 18.1 Skill 路由评测

- “帮我找最近的 world model 论文”触发 `discover-literature`，不触发写入。
- “把这些论文加入 Zotero”先触发 `plan-paper-import`，不会直接执行。
- “归档这个 CUDA 官方 PDF”被识别为技术文档，不进入 `papers_root`。
- “这篇论文在哪”触发 `locate-resource`。
- “画出 NeRF 到 3DGS 的发展脉络”触发 `build-literature-tree`。
- 普通代码任务不触发本插件。

### 18.2 功能验收

1. 相同 DOI 或 arXiv 基础 ID 重复输入，只产生一个 Zotero 父条目和一份 PDF。
2. `v1`、`v2`、`v3` 被识别为同一 arXiv 论文。
3. 没有 arXiv PDF 时不从其他网站自动下载论文全文。
4. 同名但作者、年份或强标识符冲突时停止并报告。
5. `papers_root` 改变后，所有路径通过配置重新解析，不需改代码。
6. 技术 PDF 不会进入论文目录或论文 Zotero 流程。
7. Zotero 已有条目时只补充缺失元数据、Collection 或附件。
8. 未批准计划无法执行任何外部写入。
9. 路径穿越、符号链接越界和非白名单根目录被拒绝。
10. Obsidian 索引重建不覆盖人工区块。
11. Notion 同步不上传文件、不覆盖人工正文、不创建重复页面。
12. 任一步骤失败后可以恢复且不重复副作用。
13. 文献图的每条方法关系都有证据、置信度和审核状态。
14. 审计可以发现孤立 PDF、失效 Zotero key、陈旧索引和失效本地链接。
15. 当前自研 Bridge 关闭或卸载后，Zotero 写入必须失败关闭，不会回退到不可写的 Local API 或其他旁路。
16. 模拟未来 Local API 完整写能力时，同一 Adapter 合同测试可以在不修改上层 Skill 的情况下通过。
17. 任何写入后端都无法绕过 Action Plan、用户批准、路径白名单和幂等要求。

### 18.3 测试层次

- 单元测试：规范化、身份键、路径、散列、配置和状态机。
- Contract 测试：CLI JSON、Bridge HTTP、Notion 投影和文献图 Schema。
- 集成测试：临时 Vault、模拟 Notion、测试 Zotero profile。
- 真实只读测试：当前 Zotero Local API 和 Obsidian CLI。
- 受控写入测试：专用测试 Collection、临时 papers root 和测试 Notion 数据库。
- Skill eval：触发率、误触发率、计划质量、安全行为、token 与时延。
- 回归测试：每次插件版本升级前运行固定场景。

## 19. 实施阶段

### Phase 0：规格与安全骨架

- 确定配置、Resource、Action Plan、`ZoteroWriteAdapter` 和 Bridge contract。
- 建立 Claude 插件清单、Agents、Skills 空壳和 `doctor`。
- 建立测试框架和 eval 基线。

### Phase 1：只读发现、判重与定位

- 复用或迁移 `paper-manager` 已验证的 normalize、identity、dedup、resolve、Zotero Local API 和 locate。
- 严格改为 arXiv-only 论文 PDF 策略。
- 输出导入计划，不写外部系统。

### Phase 2：Zotero Bridge 与单篇论文 MVP

- 自行实现、构建并安装受限本地 HTTP Zotero 插件；它是当前唯一写入后端。
- 实现 Adapter 能力探测、版本协商、健康检查、幂等和失败关闭测试。
- 禁用 Python 引擎中任何 Web API、Local API 或 SQLite 写入旁路。
- 验证 ZotMoov 能否被稳定复用。
- 跑通单篇论文：批准 → arXiv 下载 → Zotero → linked file → 回执。

### Phase 3：Obsidian 索引和技术文档

- 接入 Obsidian CLI。
- 实现受控表格区块、分层目录索引和技术文档归档。

### Phase 4：Notion 与本地链接

- 实现管理投影、机器字段保护和增量同步。
- 实现 cmux 可用的本地链接解析服务。

### Phase 5：文献脉络

- 实现证据化 graph contract、人工审核和多种渲染输出。

### Phase 6：审计、评测与分发

- 完成跨系统审计、定期维护、Claude Skill eval、Git 版本和个人 marketplace 发布。
- 保留 Local API capability probe 和合同测试，以便 Zotero 未来提供写能力时安全切换。

## 20. 与 `paper-manager` 的关系

`paper-manager` 不是最终系统边界，但包含可复用的验证成果：

- 输入解析、标识规范化和三层判重；
- arXiv/Crossref 等元数据解析；
- Zotero Local API 只读查询与 locate；
- Collection 拉取、缓存和分配规划；
- PDF 下载、校验与散列；
- 状态机与 CLI 骨架。

迁移原则：

1. 先通过测试固定已有行为，再迁移模块。
2. 废弃“向 Zotero Cloud 上传主 PDF”的设计。
3. 废弃“Notion 是论文记录镜像主库”的表述，改为管理投影。
4. 把自研 Zotero Bridge 固定为当前唯一写入组件，并通过 `ZoteroWriteAdapter` 为未来官方 Local API 写能力保留替换点。
5. 不把旧项目的运行目录、密钥、测试残留或绝对路径带入新插件。

## 21. 仍需用户确认的产品决策

以下问题不阻塞 Phase 0，但应在相应阶段开始前确认：

1. `papers_root` 的最终目录模板：按 Zotero Collection、年份、主题还是其他规则组织。
2. 一篇论文属于多个 Collection 时，PDF 的唯一物理目录如何选择。
3. ZotMoov 当前版本是否提供可供 Bridge 稳定调用的能力；否则采用何种兼容路径模板。
4. Obsidian 各主题论文索引的统一位置和表格字段。
5. Notion 是使用一个统一 Resource 数据库，还是按知识类目拆分数据库。
6. 本地链接服务在 cmux 中是直接打开，还是先显示本地确认页。
7. 文献图默认输出 Mermaid、draw.io 还是交互式 HTML；PNG 仅作为渲染结果。

## 22. 官方实现依据

- Claude Code 插件结构与运行期路径：<https://code.claude.com/docs/en/plugins-reference>
- Claude Code 插件创建指南：<https://code.claude.com/docs/en/plugins>
- Obsidian CLI：<https://obsidian.md/help/cli>
- Zotero Connector HTTP Server 扩展：<https://www.zotero.org/support/dev/client_coding/connector_http_server>
- Zotero JavaScript API：<https://www.zotero.org/support/dev/client_coding/javascript_api>
- Zotero 文件与 linked file：<https://www.zotero.org/support/attaching_files>
- Zotero Local/Web API：<https://www.zotero.org/support/dev/web_api/v3/basics>

## 23. 一句话架构结论

`scholar-workflow` 是一个以 Claude Code 为首要宿主的多 Agent、多 Skill 插件：Claude 负责理解、推荐和审批交互；确定性 CLI 负责可测试、可恢复的执行；Zotero 是论文主库，当前所有写入通过项目自研、运行在 Zotero 进程内的 Bridge 完成，并在未来官方 Local API 具备完整写能力后通过统一 Adapter 安全切换；Obsidian 保存知识、技术文档和派生论文索引；Notion 保存知识结构与项目管理投影，所有文件仍留在本地唯一主存储。
