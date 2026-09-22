# scholar-workflow

面向 Claude Code 与 Codex 的学术资源管理插件。它把人类优先的知识系统、可复现实验项目档案和
本机 typed Hub 控制面组合在一起：发现并导入论文、维护 Obsidian/Notion 投影、构建文献树、推荐
论文、生成经校验的 Markdown/Canvas 分析、初始化 Git 项目，并在多个 agent 运行时之间协调有界任务。

[English](./README.md)

## 架构

宿主 LLM 负责理解、分类、排序与推荐;确定性 CLI(`src/scholar_workflow/`)负责可测试的文件和
Zotero 操作。Zotero 适配器只连接 Zotero 10+ 的回环 Local API;其他对外访问均受限且显式声明——
`apply` 从 arXiv 下载 PDF,独立的 `bin/notion-project.py` / `bin/recommend-papers.py` 各自访问其
声明的服务。**Zotero 是权威主库** —— 元数据、存在性核验、索引全文与新增性写入使用官方
Local API。主题召回由 Local API 全字段/全文 quicksearch 加宿主模型排序完成,不需要 MCP server
或本地向量库。破坏性动作仍需批准。**Obsidian** 保存知识笔记与派生索引;**Notion** 保存可选投影。

### 三系统边界

- **Knowledge System** 以人类可读 Markdown 为正文。论文、重要技术文档和 Blog 是原子资源；
  分析、Canvas 和附件是显式归属的附属产物。全文分析固定覆盖任务、输入、分步流程、输出和边界，
  Evidence 与对应论点放在一起。
- **Project System** 保存稳定 `project_id`、宿主中立的源码/config profile，以及彼此分离的
  Run、Attempt、Target、成果 promotion 和备份记录。没有独立校验过的第二份副本就不能称为备份完成。
- **Hub Control Plane** 只提供一个 `HubDirectory` 根，聚合 Papers、Projects、Tools 三个 typed
  Library 与 Knowledge Contexts；Zotero、Vault、项目 manifest、显式主机 registry 和 Codex
  仍分别持有权威状态。

知识文档与项目文档之间只能显式复制。副本移除源系统的 `sw_*` 托管身份，获得目标系统身份后独立
演化；系统不建立隐藏同步或托管 provenance 关系。

### 本地研究 Hub

Hub 默认以 cmux 为运行与查看环境。在一个 cmux terminal 中启动服务，再从同一 workspace 的
另一个 terminal surface 打开：

```bash
scholar-workflow serve-hub
# 在另一个 cmux terminal surface 中
scholar-workflow open-hub
# 核验当前实际运行构建以及 provider/worker capability
scholar-workflow hub-doctor --json
# 可选：临时端口、headless/只读 canary，不占用 23128
scholar-workflow serve-hub --canary --port 0
# 仅对已显式初始化的 provider 做 canary；不会创建或迁移 provider
scholar-workflow serve-hub --canary --port 0 \
  --knowledge-provider-state-root /path/to/provider-state
```

v2 API 在 `/api/v2/directory` 提供唯一目录，在 `/api/v2/libraries/` 下分页返回各库内容，并由
`/api/v2/health` 报告可诊断运行状态。旧 `/api/v1/catalog` 只从
`HubDirectory.knowledge_catalog` 派生，不形成第二份状态。空 Library 仍可见并说明 provider 状态；
Projects 与 Tools 只能来自显式 registry，不扫描磁盘或 `$PATH`。
若 `$SCHOLAR_WORKFLOW_HOME/knowledge-provider/knowledge-provider.snapshot.json` 已存在，Hub 会在启动时
校验并读取它；否则继续使用旧只读兼容 provider。启动 Hub 不会创建 snapshot 或迁移 Vault。

所有 mutation 都依赖有效 workspace binding：unbound/headless Hub 仍能读 Library、文档、PDF 和
诊断，但不能写项目文件或运行任务。项目文件 API 只接受已注册 `project_id` 与 `docs/` 相对路径，
拒绝重名覆盖、越界和符号链接逃逸；删除只移入项目 trash。Projects Library 仅在 binding 有效时
显示复制、粘贴、Knowledge 副本和 trash 操作。论文、PDF 附件和分析文档都使用 typed landing；
raw `/open/paper/...` 字节路由只出现在附件落地页内部。任务契约只接受预登记 recipe、typed
target、最多 8 KiB 的 brief 和 `fast`/`standard`/`deep` effort；cwd、model、sandbox、permission、
固定 argv 与明确 thread ID 都由服务端决定，拒绝原始命令和 `--last`。

当前源码已经包含 v2 契约与 canary-safe runtime，但不会静默替换现存 23128 服务、迁移真实 Vault/
项目、启动真实 Codex worker，或把未验证介质称为备份；这些动作各自受 rollout 门禁约束。
详细接口见 [`references/hub-contract.md`](references/hub-contract.md)。既有 `serve-links` 与
`/open/paper/<attachment-key>` 仍是兼容入口。

## Skills

| Skill | 用途 |
|---|---|
| survey-topic | 界定开放式"调研 X"请求的范围,再路由到其他 skill |
| find-resource | 搜索论文、核验身份、定位已有资源 |
| ingest-resource | 导入论文 / 归档技术文档 |
| sync-projections | 重建 Obsidian 索引表 + 同步 Notion 投影 |
| build-literature-tree | 构建 novelty tree(里程碑任务 → pipeline → 论文)+ flat 全集清单 |
| check-consistency | 跨系统一致性审计(只读) |
| export-annotations | 把某篇论文的 Zotero 批注整理成结构化 vault 笔记 |
| recommend-papers | 每日多源论文 feed + NotebookLM 略读 → 推荐清单 |
| analyze-paper | 把论文详细分析投影为 Markdown + 可编辑 Canvas 文档对 |
| env-setup | 搭建并查阅个人 API-key / SSH 服务器 env-records 台账 |
| agent-collaboration | 在 Claude Code、Codex 或其他可用 agent 之间双向协调边界清楚的任务 |
| init-project | 初始化宿主中立、由 Git 管理且不带自定义 agent/hook 的研究项目骨架 |
| config-setup | 初始化、查询和更新插件配置 |
| project-backlog | 维护本仓库的持久化工作项队列 |

## 环境要求

- **Claude Code 或 Codex**(Codex CLI / Codex app;IDE extension 不加载插件)。
- **Python ≥ 3.11** —— 确定性 CLI 是一个 Python 包。
- **Git** —— `init-project` 创建或核验项目骨架时需要。
- **cmux** —— workspace 定向查看、受绑定保护的 mutation 与任何受控 Codex worker 都需要它。
  没有有效 workspace binding 时，Library 与文档仍可读，但 workspace、项目写入和任务动作均禁用。
- **Zotero 10+ 且启用 Local API** —— 权威主库。在 Zotero 的
  **设置 → 高级**中启用;不再需要 Zotero 插件或 MCP server。Codex 在沙箱中运行时可能还需
  放行 localhost/网络权限才能访问 23119;在把 exit 3 判断为 Zotero 离线前,应带该权限重试。
- **按功能可选:**
  - Notion 集成 token —— 仅启用 Notion 投影时需要。
  - `notebooklm-py` + Google 登录 —— 仅 `recommend-papers` 略读级 + 文献树 NotebookLM
    批读需要。
  - Scholar Inbox 账号 —— 仅该推荐源需要。
  - 目标 agent 的 CLI 与既有登录态 —— 仅 `agent-collaboration` 跨宿主运行时调用时需要;
    使用宿主原生 agent 工具时不需要。

## 安装

1. **在宿主中安装插件。**

   release 同时提供 Codex 原生 marketplace 元数据与 Claude 兼容 marketplace 入口；
   两者安装的是同一个插件根目录与同一版本。

   Claude Code:
   ```text
   /plugin marketplace add JerryFan012321/scholar-workflow@release
   /plugin install scholar-workflow@jerry-plugins
   ```

   Codex CLI:
   ```bash
   codex plugin marketplace add JerryFan012321/scholar-workflow --ref release
   codex plugin add scholar-workflow@jerry-plugins
   ```
   安装后新开 Claude Code 或 Codex 会话,让 bundled skills 与 hooks 生效。

2. **装 CLI**(提供 skill 调用的 `scholar-workflow` 命令):
   ```bash
   pip install -e .        # 从 clone 安装
   # 或:pipx install scholar-workflow
   ```
   验证:`scholar-workflow --help`。

3. **建配置。** 直接在对话中说「配置插件,我的知识库在 ~/path/to/vault」,`config-setup`
   skill 会替你执行;或手动跑:
   ```bash
   scholar-workflow config init --research-vault-root ~/path/to/obsidian/vault
   # 额外设置可内联 KEY=VALUE,如:
   #   scholar-workflow config init --research-vault-root ~/vault notion.enabled=true
   scholar-workflow config set paper_inbox ~/path/to/download/inbox   # 后续改单项
   scholar-workflow config show                                       # 查看生效值
   ```
   这会写 `~/.config/scholar-workflow/config.yml`(只写你指定的键,非全倒默认值)、校验、
   后续编辑时保留注释。需要时用 `SCHOLAR_WORKFLOW_HOME` 覆盖位置。

4. **授权 Zotero 写入。** 启动 Zotero 后运行:
   ```bash
   scholar-workflow zotero probe
   scholar-workflow zotero authorize
   ```
   多阶段 PDF 导入请选择 Zotero 弹窗中的 **Always Allow**。密钥存入 macOS Keychain,
   不会打印或写进 config/git;读命令不需要密钥。

5. **按需提供其他凭证**(见[环境要求](#环境要求))。token / cookie 存环境变量或各工具自己的
   登录态,**绝不进配置或 git**。如 Notion:`export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`。

## 更新

两个宿主 manifest(`.claude-plugin/plugin.json` 与 `.codex-plugin/plugin.json`)共用同一版本
(改动见 [CHANGELOG.md](./CHANGELOG.md))。刷新 marketplace 或拉取最新 `release` 分支,
若 CLI 版本有变则重跑 `pip install -e .`(或 `pipx upgrade
scholar-workflow`)。你的 `config.yml` 与凭证在仓库之外,更新不受影响。

## 使用

直接用自然语言跟 Claude Code 或 Codex 说,每个 skill 按意图触发;Codex 也可用
`$skill-name` 显式调用,例如:

- *"帮我调研一下世界模型这个方向"* → survey-topic →(推荐 / 查找 / 文献树…)
- *"找 DreamerV3 这篇论文并导入"* → find-resource → ingest-resource
- *"推荐今天世界模型方向的论文"* → recommend-papers
- *"分析这篇论文的方法部分"* → analyze-paper
- *"画一棵从 NeRF 到 3DGS 的文献树"* → build-literature-tree
- *"导出我对这篇论文的批注"* → export-annotations
- *"同步 Obsidian 索引和 Notion"* → sync-projections
- *"让 Claude Code 和 Codex 分工完成这次迁移并整合"* → agent-collaboration
- *"用标准骨架初始化这个项目"* → init-project

各 skill 自己的 `README`(在 `skills/<名>/` 下)详述其选项与配置。推荐清单是临时的;你
留下的论文走常规 find/ingest 管线,不经判重不入库。

## 状态与已知限制

插件仍处于 `0.x` 活跃开发期。哪些已稳、哪些仍在打磨:

- **Zotero 10.0.2 实机已跑通:** Local API 已完成 probe、search、collections、持久写授权、
  条目创建、imported PDF 上传、精确 DOI 复用与附件复用。同一 ingest payload 重跑会返回原
  item/attachment，不重复上传。
- **v0.27 cmux 兼容链路已实机跑通:** `open-hub` 能创建 Hub browser surface，旧 action 能创建空白
  native agent-session。v2 lease/binding 与 bounded TaskRecipe 契约已有测试，但本次源码变更不会启用
  真实 worker，也不会切换 23128。
- **v2 知识/项目契约只经 fixture 验证，尚未迁移真实数据:** 既有 Vault 与项目保持不动；首个知识
  pilot 仍是 JEPA，首个真实项目仍等待用户决定。
- **已实现但尚未真实端到端跑通:** `build-literature-tree` 的 CLI 渲染路径(尤其第四层
  `module` 和落盘到 vault 的挑战洞见树)、`recommend-papers` 的 NotebookLM 略读层、
  `check-consistency`。
- **不支持跨运行续跑:** 重跑 `apply` 是全新任务、会把每一项从头下载,不会接着上次的进度。
- **身份安全双层执行:** skill 先预览候选,`zotero ingest` 在创建前再次执行 DOI 或规范化
  title+creators 精确核验。当前 CLI 不暴露破坏性 Zotero 命令;未来若增加仍需审批。

## 开发

这是 `release` 分支(仅运行时,包含 Codex 原生 marketplace、Claude 兼容 marketplace 与两个宿主
manifest)。开发内容 —— 规范、规划文档、测试、评估 —— 在 `main` 分支,贡献指南见其
`AGENT.md`。测试在那边跑:`pytest tests/unit tests/contract`。
