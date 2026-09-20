# scholar-workflow

面向 Claude Code 与 Codex 的学术资源管理插件。发现并导入论文、保持 Obsidian 索引与 Notion 投影
同步、构建文献 novelty tree、从四个源推荐每日论文、撰写论文详细分析 —— 由确定性 CLI 承担
可测试的文件操作,宿主 LLM 负责理解、推荐与判断。插件还可初始化由 Git 管理的研究项目骨架,
并在多个 agent 运行时之间协调边界清楚的任务。

[English](./README.md)

## 架构

宿主 LLM 负责理解、分类、排序与推荐;确定性 CLI(`src/scholar_workflow/`)负责可测试的文件和
Zotero 操作。Zotero 适配器只连接 Zotero 10+ 的回环 Local API;其他对外访问均受限且显式声明——
`apply` 从 arXiv 下载 PDF,独立的 `bin/notion-project.py` / `bin/recommend-papers.py` 各自访问其
声明的服务。**Zotero 是权威主库** —— 元数据、存在性核验、索引全文与新增性写入使用官方
Local API。主题召回由 Local API 全字段/全文 quicksearch 加宿主模型排序完成,不需要 MCP server
或本地向量库。破坏性动作仍需批准。**Obsidian** 保存知识笔记与派生索引;**Notion** 保存可选投影。

### 本地研究 Hub

Hub 默认以 cmux 为运行与查看环境。在一个 cmux terminal 中启动服务，再从同一 workspace 的
另一个 terminal surface 打开：

```bash
scholar-workflow serve-hub
# 在另一个 cmux terminal surface 中
scholar-workflow open-hub
```

顶部 workspace 选择器可把 PDF、Markdown/Canvas 与 Notion 打开到 Hub 所在 workspace 或人工
选择的其他 workspace。独立按钮分别把 Vault 文档交给 Obsidian、把论文条目交给 Zotero 原生编辑。
经确认的 Codex 按钮只在所选 workspace 新建一个空白、可见的 native agent-session，绝不接受
浏览器传入的 prompt、command、model、权限或工作目录。若服务不是从 cmux 启动，workspace 动作会
明确显示不可用，但 Hub 内建阅读与受控 Vault 编辑仍可使用。

Hub 在 `http://127.0.0.1:23128/hub/` 提供统一的人类入口：搜索论文、流式读取只读 Zotero PDF、
即时预览受 Catalog 管理的 Markdown/Canvas，也可在版本冲突保护下显式编辑已有 Vault 文档并实时
预览。标准 JSON Canvas 不注入私有字段，而通过 `.scholar-workflow/artifacts.yml` 显式登记。文档
图片、数据与补充文件从默认折叠的附件区新增，字节仍在 Vault，关系记录在可人工检查的 manifest；
Notion 不会静默切到 Safari。HubCatalog 约束三种投影的机器身份；Obsidian 仍保留原有可读
Markdown 正文，Hub 只增加薄的 `sw_*` frontmatter。
详细接口见 [`references/hub-contract.md`](references/hub-contract.md)。既有 `serve-links` 命令与
`/open/paper/<attachment-key>` 链接继续兼容。

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
- **cmux** —— workspace 定向的 PDF/文档/Notion 查看和空白 Codex 会话按钮需要。没有 live cmux
  socket 时，目录、已登记 Vault 文档阅读和 Obsidian/Zotero 编辑跳转仍可用；cmux 专属动作会明确禁用。
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
- **cmux 实机已跑通:** `open-hub` 已在调用者 workspace 新建 Hub browser surface，选择器能识别
  Hub 所在 workspace；确认 Codex 动作后在同一 workspace 新建了空白 native agent-session，未发送 prompt。
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
